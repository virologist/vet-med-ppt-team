#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mirror_sync.py — 仓库根 ⇄ 分发镜像 的安全同步器（v3.27.0 · L-7）

══════════════════════════════════════════════════════════════════════
为什么需要这个文件（三次真实事故）：
  ① **删除传播**：有人用了 `rsync -a --delete` ⇒ 仓库根的删除被**传播**到镜像
     ⇒ `settings.json` 一次丢失（该文件由体检第 1 项自愈，但那是**事后**补救）。
  ② **自复制**：有人忘了排除 `packages` ⇒ rsync 把镜像目录**同步进它自己**
     ⇒ 产出嵌套的 `packages/packages/vet-med-ppt-team/`（5.6MB 污染）。
  ③ **忘记同步**：改完包根没同步 ⇒ 根与镜像内容漂移（曾出现镜像差集 1 个文件）。

本脚本把上述「人工纪律」固化成代码，要点：
  · **默认 dry-run**：只打印「将要做什么 + 差异清单」，**不写任何文件**。
    —— 这是铁律（对齐既有 `release-sync.sh` 约定：dry-run 默认，`--confirm` 才真推）。
  · **排除清单硬编码**在本文件里，不靠调用方记得传参数。
    ★ `packages` 在清单内 ⇒ **不可能**自复制（事故 ② 结构性封死）。
  · **默认不做删除传播**：镜像多出来的文件只**报告**，不删。
    —— 只有显式 `--prune` 才会删，且逐条列出待删文件供人工确认。
  · **同步前自动备份**：将被覆盖的文件先备份到 `packages/.mirror_backups/<时间戳>/`。
    —— 镜像漂移意味着镜像里可能有根上不存在的内容，覆盖会丢东西。
  · **同步后逐文件校验**：用 `diff -q` 比对根与镜像，打印「零差异」或差异清单。

用法：
    python3 scripts/mirror_sync.py                 # dry-run（默认，不写任何文件）
    python3 scripts/mirror_sync.py --confirm       # 真正执行同步
    python3 scripts/mirror_sync.py --prune         # 额外允许删除镜像多出的文件
    python3 scripts/mirror_sync.py --pkg-root DIR  # 指定包根（默认由脚本位置推导）

退出码：
    0 = 成功（dry-run 且完全无差异；或已同步且「必须修的差异」已清零）
    1 = 存在差异且未同步（dry-run 发现差异 ⇒ CI 可据此发现漂移）
    2 = 用法/环境错误（包根不存在等）

⚠ 「差异」分两类，性质不同（贯穿全文）：
  · **必须修**（根有镜像无 / 内容不同）⇒ 同步会修好 ⇒ 修完即清零。
  · **镜像多出**（镜像有根无）⇒ 默认**不删**（纪律：不做删除传播）
    ⇒ 它会一直存在 ⇒ dry-run 仍报 rc=1（这是**如实报告**，不是失败）。
"""

import argparse
import filecmp
import fnmatch
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ───────────────────────────────────────────────────── 排除清单（硬编码）
#: 目录/文件排除模式。语义与 rsync `--exclude` 一致：按** basename **匹配，
#: 即「任意层级」出现该名字就排除（`rsync --exclude=packages` 也是这个语义）。
#:
#: ★ `packages` 是**最关键**的一条：镜像位于 `<包根>/packages/<包名>/`，
#:   若不排除它，rsync/本脚本会把镜像同步进它自己 ⇒ 嵌套 `packages/packages/`
#:   （事故 ②）。它在清单里 ⇒ 事故 ② 结构性不可能复发。
#: ★ `vetmed-iso*` 对齐 v3.26.0 补的 .gitignore 规则（隔离副本残留）。
#:
#: ⚠ 这些是**同步**层面的排除（不进入镜像）。
#:   `.workbuddy` 是运行时 trace 目录，不该进分发包。
EXCLUDE_PATTERNS = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
    ".DS_Store",
    ".workbuddy",
    "packages",
    "vetmed-iso*",
)

#: 镜像目录名（相对于包根）：`packages/<包名>/`。
#: 默认与包根同名；可用 `--mirror-name` 覆盖。
DEFAULT_MIRROR_NAME = "vet-med-ppt-team"

#: 备份目录名（相对于包根的 `packages/` 下）：`packages/.mirror_backups/<时间戳>/`。
BACKUP_DIRNAME = ".mirror_backups"

#: 镜像目录名在**包根内**的父目录名。
MIRROR_PARENT = "packages"


# ───────────────────────────────────────────────────── 基础工具
def is_excluded(name: str) -> bool:
    """该** basename **是否命中排除清单。

    语义与 rsync `--exclude` 一致：按 basename 匹配 ⇒ 任意层级同名都排除。
    """
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_PATTERNS)


def iter_files(root: Path):
    """遍历 root 下所有「应同步」文件，返回 {相对路径: 绝对路径}。

    排除清单在**任意层级**生效（目录剪枝 + 文件过滤）。
    """
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # 目录剪枝：被排除的目录整棵不进（`.git`/`packages`/`__pycache__`…）
        dirnames[:] = [d for d in dirnames if not is_excluded(d)]
        for fn in filenames:
            if is_excluded(fn):
                continue
            full = Path(dirpath) / fn
            rel = full.relative_to(root)
            out[str(rel)] = full
    return out


def iter_dirs(root: Path):
    """遍历 root 下所有「应同步」的**目录**（相对路径集合）。

    仅用于删除传播后的空目录清理 ⇒ 必须与 iter_files 用同一套排除规则，
    否则会把根上存在、镜像上也不该动的空目录误删。
    """
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_excluded(d)]
        rel = Path(dirpath).relative_to(root)
        if str(rel) != ".":
            out.add(str(rel))
        for d in dirnames:
            out.add(str(rel / d) if str(rel) != "." else d)
    return out


def same_content(a: Path, b: Path) -> bool:
    """两个文件内容是否逐字节相同（不比元数据）。"""
    try:
        return filecmp.cmp(str(a), str(b), shallow=False)
    except OSError:
        return False


def _fmt_list(items, limit=20):
    """把路径列表格式化成可读文本（超量截断并给出总数）。"""
    items = sorted(items)
    if not items:
        return "    （无）"
    lines = [f"    - {p}" for p in items[:limit]]
    if len(items) > limit:
        lines.append(f"    …… 另有 {len(items) - limit} 个（未逐条列出）")
    return "\n".join(lines)


# ───────────────────────────────────────────────────── 差异计算
def compute_diff(src_root: Path, mirror_root: Path):
    """算出根与镜像的差异。

    返回 (missing, differing, extra)：
      · missing  —— 根有、镜像无 ⇒ 需新增
      · differing—— 两边都有但内容不同 ⇒ 需覆盖
      · extra    —— 镜像有、根无 ⇒ 「镜像多出的文件」（**默认不删**，只报告）
    """
    src = iter_files(src_root)
    dst = iter_files(mirror_root) if mirror_root.is_dir() else {}

    missing = []
    differing = []
    for rel, s in src.items():
        d = dst.get(rel)
        if d is None:
            missing.append(rel)
        elif not same_content(s, d):
            differing.append(rel)

    extra = [rel for rel in dst if rel not in src]
    return missing, differing, extra


# ───────────────────────────────────────────────────── 备份
def backup_files(mirror_root: Path, rels, backup_dir: Path):
    """把镜像中即将被覆盖/删除的文件复制到备份目录。

    返回实际备份的文件数。备份保留**相对路径结构**，便于人工比对与回滚。
    """
    if not rels:
        return 0
    n = 0
    for rel in sorted(rels):
        src = mirror_root / rel
        if not src.is_file():
            continue
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        n += 1
    return n


# ───────────────────────────────────────────────────── 同步执行
def do_sync(src_root: Path, mirror_root: Path, missing, differing, extra,
            prune: bool, backup_root: Path):
    """真正执行同步。返回 (新增数, 覆盖数, 删除数, 备份目录 或 None)。"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / ts

    # ① 先备份「将被覆盖」的文件（镜像漂移时镜像里可能有根上没有的内容 ⇒ 覆盖会丢东西）
    to_backup = list(differing)
    if prune:
        to_backup += list(extra)
    n_backup = backup_files(mirror_root, to_backup, backup_dir)

    # ② 新增 + 覆盖
    n_new = 0
    n_upd = 0
    for rel in missing:
        s = src_root / rel
        d = mirror_root / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(s), str(d))
        n_new += 1
    for rel in differing:
        s = src_root / rel
        d = mirror_root / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(s), str(d))
        n_upd += 1

    # ③ 删除传播（**仅在 --prune 显式开启时**；默认关闭 ⇒ 事故 ① 结构性封死）
    n_del = 0
    if prune:
        for rel in extra:
            d = mirror_root / rel
            if d.is_file():
                d.unlink()
                n_del += 1
        # 清理因删除而空掉的目录（从深到浅）
        # ⚠ 两条护栏：
        #   ① 不得删掉镜像根本身（否则下一轮同步会失去目标目录）；
        #   ② **不得**删掉「根上也存在」的空目录（那不是残留，是包内容的一部分）
        #      ⇒ 用同一套排除规则算出根侧目录集合，据此判别。
        src_dirs = iter_dirs(src_root)
        for dirpath, dirnames, filenames in os.walk(mirror_root, topdown=False):
            p = Path(dirpath)
            if p.resolve() == mirror_root.resolve():
                continue
            rel_dir = str(p.relative_to(mirror_root))
            if rel_dir in src_dirs:
                continue  # 根上也有 ⇒ 是包内容，不是残留
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass

    return n_new, n_upd, n_del, (backup_dir if n_backup else None)


# ───────────────────────────────────────────────────── 同步后校验
def verify_with_diff(src_root: Path, mirror_root: Path):
    """用 `diff -q` 逐文件校验根与镜像。

    返回 (差异分类, 受管文件数)。差异分类为 dict：
      · ``missing`` —— 根有、镜像无（**必须修**：镜像内容不全）
      · ``differing`` —— 两边都有但内容不同（**必须修**：镜像内容过期）
      · ``extra``   —— 镜像有、根无（**按默认纪律保留**：不删，只报告）

    ⚠ 三类差异性质不同 ⇒ 不能混为一谈：
      「必须修」的两类说明同步没做到位；
      「extra」在**默认模式**下是**预期结果**（纪律：默认不做删除传播）
      ⇒ 不能把它算成同步失败，否则默认模式永远无法「零差异」。
    """
    src = iter_files(src_root)
    dst = iter_files(mirror_root) if mirror_root.is_dir() else {}
    missing = []
    differing = []
    n = 0
    for rel, s in sorted(src.items()):
        d = dst.get(rel)
        if d is None:
            missing.append(rel)
            continue
        n += 1
        # 用系统 diff -q 做**独立于本脚本 copy 逻辑**的内容比对
        rc = subprocess.run(["diff", "-q", str(s), str(d)],
                            capture_output=True).returncode
        if rc != 0:
            differing.append(rel)
    extra = sorted(rel for rel in dst if rel not in src)
    return {
        "missing": missing,
        "differing": differing,
        "extra": extra,
    }, n


# ───────────────────────────────────────────────────── 提交态一致性（供体检复用）
def git_committed_parity(repo_root: Path):
    """比较**提交态**（HEAD）的「根侧」与各「镜像侧」内容是否一致。

    自动发现镜像：提交树里凡是 ``packages/<子目录>/...`` 的都算镜像侧
    （不写死镜像名 ⇒ 换个目录名/多个镜像都能用）。

    返回 {镜像名: (missing, differing, extra)}；无镜像则返回 {}。
      · missing  —— 根有、镜像无（**必须修**）
      · differing—— 两边都有但内容不同（**必须修**）
      · extra    —— 镜像有、根无（镜像里的历史残留；**只报告不删**）

    ⚠ **为什么体检要查「提交态」而不是工作区**：
      工作区在「改包但还没同步镜像」的正常开发中间态里**必然**有差异
      （根侧改了、镜像还没跟）⇒ 用工作区比对会**常态性假红**。
      而提交态是**发布单元**：一旦提交了漂移的组合，说明那次发布就带上了漂移。
      ⇒ 提交态比对 = 零假红 + 仍能抓住真实事故（历史提交里确有 3 次漂移）。

    ⚠ 依赖 git ⇒ 非 git 仓库 / 无 HEAD 时返回 None（调用方应「不判定」而非判红）。
    """
    try:
        raw = subprocess.run(
            ["git", "-C", str(repo_root), "ls-tree", "-r", "-z", "HEAD"],
            capture_output=True).stdout.decode("utf-8", "surrogateescape")
    except OSError:
        return None
    if not raw:
        return None

    root_side = {}
    mirrors = {}
    for rec in raw.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        sha = meta.split()[2]
        if path.startswith("packages/"):
            rest = path[len("packages/"):]
            name, _, rel = rest.partition("/")
            if rel:
                mirrors.setdefault(name, {})[rel] = sha
        else:
            root_side[path] = sha

    out = {}
    for name, mirror_side in mirrors.items():
        missing = sorted(set(root_side) - set(mirror_side))
        extra = sorted(set(mirror_side) - set(root_side))
        differing = sorted(
            k for k in set(root_side) & set(mirror_side)
            if root_side[k] != mirror_side[k])
        out[name] = (missing, differing, extra)
    return out


# ───────────────────────────────────────────────────── 包根解析
def resolve_pkg_root(explicit=None) -> Path:
    """解析包根。

    优先级：`--pkg-root` 显式参数 > 环境变量 `VETMED_MIRROR_PKG_ROOT`
            > 由脚本自身位置推导（`<包根>/scripts/mirror_sync.py` → `<包根>`）。

    ⚠ **禁硬编码绝对路径** ⇒ 默认值只由 `__file__` 推导。
    ⚠ 可注入 ⇒ 自动化测试能在临时沙盒里跑（绝不碰生产 `packages/`）。
    """
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("VETMED_MIRROR_PKG_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def _guess_mirror_name(root: Path) -> str:
    """推断镜像目录名。

    优先取 `packages/` 下**唯一**存在的子目录名（跟随实际布局，不写死）；
    没有或多个 ⇒ 回落到默认名。
    ⚠ 回落到默认名而不是报错：镜像还没建出来时，也应能报「需新增 N 个文件」。
    """
    pkg_dir = root / MIRROR_PARENT
    if pkg_dir.is_dir():
        subs = [d.name for d in pkg_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")]
        if len(subs) == 1:
            return subs[0]
    return DEFAULT_MIRROR_NAME


# ───────────────────────────────────────────────────── 主流程
def main(argv=None, pkg_root=None) -> int:
    """主入口。

    `pkg_root` 参数可注入包根（测试用沙盒）；CLI 走 `--pkg-root`。
    """
    ap = argparse.ArgumentParser(
        prog="mirror_sync.py",
        description="仓库根 ⇄ 分发镜像 的安全同步器（默认 dry-run，不写任何文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：\n"
            "  0 = 成功（dry-run 且完全无差异；或已同步且「必须修的差异」已清零）\n"
            "  1 = 存在差异且未同步（dry-run 发现差异 ⇒ CI 可发现漂移）\n"
            "  2 = 用法/环境错误\n"
            "\n"
            "⚠ 「差异」分两类，性质不同：\n"
            "  · 必须修（根有镜像无 / 内容不同）⇒ 同步会修好\n"
            "  · 镜像多出（镜像有根无）  ⇒ 默认**不删**（--prune 才删）⇒ 仍在 ⇒ rc=1\n"
        ),
    )
    ap.add_argument("--confirm", action="store_true",
                    help="真正执行同步（默认 dry-run：只报告，不写任何文件）")
    ap.add_argument("--prune", action="store_true",
                    help="额外允许删除「镜像多出的文件」（默认关闭；关闭时只报告不删）")
    ap.add_argument("--pkg-root", default=None,
                    help="指定包根（默认由脚本位置推导；也可用环境变量 "
                         "VETMED_MIRROR_PKG_ROOT）")
    ap.add_argument("--mirror-name", default=None,
                    help=f"镜像目录名（默认 {DEFAULT_MIRROR_NAME}）")
    args = ap.parse_args(argv)

    root = resolve_pkg_root(args.pkg_root or pkg_root)
    if not root.is_dir():
        print(f"✗ 包根不存在：{root}", file=sys.stderr)
        return 2

    mirror_name = args.mirror_name or _guess_mirror_name(root)
    mirror_root = root / MIRROR_PARENT / mirror_name
    backup_root = root / MIRROR_PARENT / BACKUP_DIRNAME

    mode = "确认执行" if args.confirm else "预演（dry-run）"
    print("=" * 66)
    print(f"镜像同步 · {mode}")
    print("=" * 66)
    print(f"包根（源）  ：{root}")
    print(f"镜像（目标）：{mirror_root}")
    print(f"排除清单    ：{', '.join(EXCLUDE_PATTERNS)}")
    print(f"删除传播    ：{'开启（--prune）' if args.prune else '关闭（默认·仅报告不删）'}")
    print()

    missing, differing, extra = compute_diff(root, mirror_root)

    print(f"【差异清单】新增 {len(missing)} 个 / 内容不同 {len(differing)} 个 / "
          f"镜像多出 {len(extra)} 个")
    print()
    print("  需新增（根有·镜像无）：")
    print(_fmt_list(missing))
    print()
    print("  需覆盖（两边都有·内容不同）：")
    print(_fmt_list(differing))
    print()
    print("  镜像多出（镜像有·根无）：")
    print(_fmt_list(extra))
    if extra and not args.prune:
        print("    ↑ 默认**不做删除传播**（--prune 未开启 ⇒ 只报告、不删）。")
        print("      若确认这些文件确实该删，请显式加 --prune 重跑。")
    print()

    if not args.confirm:
        print("─" * 66)
        print("预演模式：未写入任何文件。确认无误后加 --confirm 真正执行。")
        total = len(missing) + len(differing) + len(extra)
        if total:
            print(f"结论：存在 {total} 处差异（rc=1，便于 CI 发现漂移）。")
            return 1
        print("结论：根与镜像零差异，无需同步（rc=0）。")
        return 0

    # ── 真正执行
    print("─" * 66)
    print("开始同步……")
    n_new, n_upd, n_del, backup_dir = do_sync(
        root, mirror_root, missing, differing, extra,
        prune=args.prune, backup_root=backup_root)
    print(f"  新增 {n_new} 个 / 覆盖 {n_upd} 个 / 删除 {n_del} 个")
    if backup_dir:
        print(f"  备份目录：{backup_dir}")
    else:
        print("  （无文件被覆盖/删除 ⇒ 无需备份）")
    print()

    # ── 同步后校验（用 diff -q 逐文件比对）
    print("【同步后校验】（diff -q 逐文件比对）")
    cats, n_checked = verify_with_diff(root, mirror_root)
    must_fix = cats["missing"] + cats["differing"]
    if must_fix:
        print(f"  ✗ 仍有 {len(must_fix)} 处必须修的差异：")
        if cats["missing"]:
            print("    仅根有（镜像缺）:")
            print(_fmt_list(cats["missing"]))
        if cats["differing"]:
            print("    内容不同（镜像过期）:")
            print(_fmt_list(cats["differing"]))
        print()
        print("结论：同步后校验未通过（rc=1）。")
        return 1

    if cats["extra"]:
        # ⚠ 默认模式下这属于**预期**：纪律要求「默认不做删除传播」
        print(f"  ✓ 根侧受管文件零差异（{n_checked} 个逐字节一致）")
        print(f"  ⚠ 镜像多出 {len(cats['extra'])} 个文件（按默认纪律**保留未删**）：")
        print(_fmt_list(cats["extra"]))
        print("    ↑ 若确认这些文件该删，用 `--confirm --prune` 重跑。")
        print()
        print("结论：同步完成，「必须修的差异」已清零；镜像多出项按默认纪律保留（rc=0）。")
        return 0
    print(f"  ✓ 零差异（{n_checked} 个受管文件逐字节一致）")
    print()
    print("结论：同步完成且校验零差异（rc=0）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

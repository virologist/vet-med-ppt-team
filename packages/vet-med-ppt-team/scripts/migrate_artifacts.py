#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate_artifacts.py — 旧数据迁移与归档清理（v3.28.0 · L-9）

══════════════════════════════════════════════════════════════════════
要解决什么（用户原话：「每次改动都新建一份」→ 存储无限膨胀）：

  v3.28.0 实测盘点（本包 + WorkBuddy 工作空间）合计浪费 ≈ **4.43 MiB**，
  且**每做一次改动就再涨一份**。四个落点：

    ① `packages/` 分发镜像          —— 每次改动 ×2 份（根 + 镜像）
    ② `packages/.mirror_backups/`   —— 每次同步产生，**无上限**（实测 1.02 MiB）
    ③ 工作空间 zip 发布包           —— 每版本一份全量（实测 3.07 MiB）
    ④ 工作空间文档副本              —— 3 个目录各存一份（实测 0.20 MiB）

  本脚本负责 ②③④ 的**迁移与归档**（① 由 `mirror_sync.py` 负责增量同步，
  且 v3.27.0 已把它固化为「同步前备份 + 逐文件校验」）。

══════════════════════════════════════════════════════════════════════
**不可协商的纪律**：

  ① **只归档不删除** —— 本脚本**不执行任何 rm / unlink / rmtree**。
     一切「清理」都是**移动**到归档区，并写 `ARCHIVE_MANIFEST.json`
     记录 from/to ⇒ 随时可原样恢复。

  ② **归档前必须验「内容已被权威持有」** —— 三档判定：
       · **git 持有**：内容 SHA-256 命中 git 对象库 ⇒ 可安全归档
         （因为 git 已能还原它，且它**不占额外空间**——对象库是增量共享的）
       · **另有副本**：与另一文件**逐字节相同** ⇒ 可安全归档
       · **无主**：两者皆非 ⇒ **拒绝归档**，原样留下并报告
     ★ 这一档判定是本脚本的**核心安全阀**：把「看起来是重复的」东西
       归档掉，可能毁掉唯一一份。

  ③ **默认 dry-run** —— 须显式 `--confirm` 才真正移动。对齐
     `release-sync.sh` / `mirror_sync.py` / `versionctl.py` 的既有约定。

  ④ **幂等可重入** —— 同一目标重复跑，结果不变；已归档的不再重复归档。

  ⑤ **不动用户个人工作区** —— `养禽与禽病防治/` 与任何未被显式登记的
     目录，一律零动作。本脚本只处理**登记表**里明确列出的路径。

  ⑥ **不越界** —— 工作空间侧的产物，脚本**只登记与报告**，实际移动须
     由人在工作空间里执行（脚本对工作空间路径默认只读），
     除非显式加 `--allow-workspace-move`。

══════════════════════════════════════════════════════════════════════
登记与默认处置（`ARTIFACT_RULES`）：

  R1  `packages/.mirror_backups/<时间戳>/`  → 归档，保留最近 `keep_backups` 份
  R2  工作空间 `<pkg>_v<版本>_<日期>.zip`     → 归档（需 git 持有），保留最近 `keep_zips` 份
  R3  工作空间 `.wiki-creator/raw/*.md`      → 归档（需与 01-research/02-design 有同字节副本）
  R4  `.versionctl/archive/<时间戳>/`        → 归档，保留最近 `keep_archives` 份

用法：
    python3 scripts/migrate_artifacts.py --scan
    python3 scripts/migrate_artifacts.py --confirm
    python3 scripts/migrate_artifacts.py --scan --json

退出码：
    0 = 成功（dry-run 且无待归档项；或已归档且必须清的项已清零）
    1 = 存在待归档项但未 --confirm，或存在「无主」项（需人工判断）
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ───────────────────────────────────────────────────── 常量

#: 归档根目录名（相对**包根**）。
ARCHIVE_ROOT = ".versionctl/archive"

#: 归档清单文件名。
MANIFEST_NAME = "ARCHIVE_MANIFEST.json"

#: 工作空间默认位置（可用 --workspace 覆盖）。
#: ★ 默认值是**相对**的常见路径候选，不硬编码用户主目录。
DEFAULT_WORKSPACE_CANDIDATES = (
    "../WorkBuddy/2026-09-10-08-59-15",
    "../../WorkBuddy/2026-09-10-08-59-15",
)

#: 保留策略默认值。
DEFAULT_KEEP = {
    "keep_backups": 3,      # `.mirror_backups` 保留最近 3 份
    "keep_zips": 2,        # 工作空间 zip 保留最近 2 个
    "keep_archives": 5,     # `.versionctl/archive` 保留最近 5 份
}

#: ★ 登记表：每条规则描述「在哪里、找什么、怎么处理、保留几份」。
#:
#: ★ 为什么用登记表而不是自动扫描全盘：
#:   自动扫描 = 误伤风险（本包有用户个人工作区、有快照库 376MB）。
#:   登记表 = 显式、可审计、范围封闭。
ARTIFACT_RULES = (
    {
        "id": "R1",
        "name": "镜像同步备份目录",
        "base": "pkg",              # 相对包根
        "pattern": "packages/.mirror_backups/*",
        "kind": "dir",
        "keep": "keep_backups",
        "require": "git",           # 必须 git 持有才归档
    },
    {
        "id": "R2",
        "name": "工作空间发布 zip 包",
        "base": "workspace",
        "pattern": "vet-med-ppt-team_v*_*.zip",
        "kind": "file",
        "keep": "keep_zips",
        "require": "git",
    },
    {
        "id": "R3",
        "name": "工作空间文档副本（.wiki-creator/raw）",
        "base": "workspace",
        "pattern": ".wiki-creator/raw/*.md",
        "kind": "file",
        "keep": None,               # 副本类不按份数保留，去重即止
        "require": "duplicate",     # 必须与另一处逐字节相同
        "dup_targets": ("01-research", "02-design"),
    },
    {
        "id": "R4",
        "name": "versionctl 归档区自身",
        "base": "pkg",
        "pattern": ".versionctl/archive/*",
        "kind": "dir",
        "keep": "keep_archives",
        "require": "git",           # 归档区内容多已入 git
        "skip_if_manifest": True,   # 含清单的目录本身不归档（避免自吞）
    },
)


# ───────────────────────────────────────────────────── 纯函数层（无 I/O，可直接测）

def sha256_file(path):
    """文件 SHA-256（十六进制）；读不了返回 None。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def dir_size_and_count(path):
    """目录的（总字节, 文件数）；不是目录则返回 (0,0)。"""
    total, count = 0, 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    total += fp.stat().st_size
                    count += 1
                except OSError:
                    pass
    except OSError:
        pass
    return total, count


def dir_content_hashes(path):
    """目录内**每个文件**的 SHA-256 集合（内容寻址，用于安全阀）。

    ★ 为什么目录不能算「一个哈希」：目录不是 git blob，安全阀必须逐文件判定。
      只要有**任一文件**不被 git 持有 ⇒ 整个目录判为「无主」⇒ 拒绝归档。
    """
    hs = []
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                h = sha256_file(Path(dirpath) / fn)
                if h:
                    hs.append(h)
    except OSError:
        pass
    return hs


def classify_sort_key(name, kind):
    """产物排序键：**时间倒序**（新的在前）。

    ⇒ 「保留最近 N 份」= 取排序后的前 N 个。

    ★ 只取**日期部分**，绝不把版本号拼进来。
      实测坑：zip 名 `vet-med-ppt-team_v3.17.0_20261024.zip` 若把所有数字
      拼成 `317020261024`，版本号 `3.17` 就会污染日期排序 ⇒ 新旧顺序错乱。
      ⇒ 目录名取 `YYYYMMDD-HHMMSS`；文件名取尾部 `_YYYYMMDD`。
    """
    # ① 目录时间戳 `YYYYMMDD-HHMMSS`
    m = re.match(r"^(\d{8})-(\d{6})$", name)
    if m:
        return (m.group(1), m.group(2), name)
    # ② 文件名尾部 `_YYYYMMDD`（版本号在前面，不参与）
    m = re.search(r"_(\d{8})(?!\d)", name)
    if m:
        return (m.group(1), "", name)
    # ③ 兜底：任意 8 位日期串
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", name)
    if m:
        return (m.group(1), "", name)
    return ("", "", name)


def content_evidence(cand):
    """候选项的**内容证据**：(证据哈希列表, 主哈希)。

    ★ 文件 ⇒ 一个哈希；目录 ⇒ **每个文件**一个哈希（目录不是 git blob，
      必须逐文件判定安全阀）。主哈希用于清单追溯：
      文件 = 其自身 sha256；目录 = 内容哈希集合的复合摘要。
    """
    kind = cand.get("kind", "file")
    if kind == "dir":
        hs = list(cand.get("content_hashes") or [])
        if not hs:
            pre = cand.get("sha256")
            hs = [pre] if pre else dir_content_hashes(cand["path"])
        digest = hashlib.sha256("\n".join(sorted(hs)).encode("utf-8")).hexdigest()
        return hs, digest
    h = cand.get("sha256") or sha256_file(cand["path"])
    return ([h] if h else []), h


def plan_archive(candidates, keep_n, require="git", dup_targets=None,
                 git_hashes=None, local_hashes=None):
    """规划归档（**纯函数**：不碰文件系统）。

    参数：
      candidates   —— [{path, name, bytes, count}] 待考察项
      keep_n       —— 保留最近 N 份（None = 全保留，即不按份数裁剪）
      require      —— "git" / "duplicate" / "none"
      dup_targets  —— 副本判定的对照目录列表
      git_hashes   —— {sha256: 相对路径}：git 对象库里存在的 blob
      local_hashes —— {sha256: [绝对路径]}：本地其它副本

    返回 {
      "archive": [{path, name, bytes, reason, sha256}],
      "keep":   [{path, name, bytes, reason}],
      "orphan": [{path, name, bytes, reason}],   # 无主 ⇒ 拒绝归档
      "reclaimed_bytes": int,
    }

    ★ 「无主」的判定是**安全阀**：
      require="git" ⇒ 该内容的 SHA-256 必须命中 git 对象库；
                      目录 ⇒ **每个文件**都必须命中；
      require="duplicate" ⇒ 必须与 dup_targets 里某文件逐字节相同；
      两项都不过 ⇒ 进 orphan（**原样留下**，只报告）。
    """
    items = sorted(candidates, key=lambda c: classify_sort_key(c["name"], c.get("kind")),
                   reverse=True)
    archive, keep, orphan = [], [], []
    # ★ 份数上限的语义：「**总量**不得超过 keep_n」⇒ 超出的**最旧**那些才归档。
    #   —— 不是「最近的 keep_n 个无条件保留」。
    #   理由：keep_n 是**上限**（防无限膨胀），不是**配额**。
    #   实测：R1 只有 1 份、keep_n=3 ⇒ 未超上限 ⇒ 全部保留（不是「取 1 份留 2 份」）；
    #        若有 5 份 ⇒ 超上限 ⇒ 归档最旧的 2 份。
    over = 0
    if keep_n is not None and len(items) > keep_n:
        over = len(items) - keep_n
    for i, c in enumerate(items):
        path = c["path"]
        hashes, primary = content_evidence(c)
        # 份数裁剪：只有**超出上限的最旧项**才进入归档判定
        in_overflow = (i >= len(items) - over) if over > 0 else False
        if keep_n is not None and not in_overflow:
            keep.append({**c, "reason": "保留（未超出上限 %d 份）" % keep_n})
            continue
        # 安全阀判定
        if require == "git":
            # ★ 目录：逐文件命中才算 git 持有
            held = bool(hashes) and all(h in (git_hashes or {}) for h in hashes)
            if held:
                archive.append({**c, "sha256": primary,
                                "reason": "git 对象库已持有（%d 个文件，sha256 %s…，"
                                          "可从 git 还原且不占额外空间）"
                                          % (len(hashes), str(primary)[:12])})
            else:
                orphan.append({**c, "sha256": primary,
                               "reason": "git 未持有其内容（%d/%d 个文件命中）⇒ 拒绝归档"
                                         "（避免毁掉唯一一份）"
                                         % (sum(1 for h in hashes if h in (git_hashes or {})),
                                            len(hashes))})
        elif require == "duplicate":
            hit = None
            for h in hashes:
                if h in (local_hashes or {}):
                    hit = h
                    break
            if hit:
                peers = [p for p in local_hashes[hit] if p != path]
                archive.append({**c, "sha256": primary,
                                "reason": "与 %s 逐字节相同（sha256 %s…）"
                                          % (peers[0] if peers else "另一副本", hit[:12])})
            else:
                orphan.append({**c, "sha256": primary,
                               "reason": "未找到逐字节相同的另一副本 ⇒ 拒绝归档"})
        else:
            archive.append({**c, "sha256": primary, "reason": "策略指定归档"})
    return {
        "archive": archive,
        "keep": keep,
        "orphan": orphan,
        "reclaimed_bytes": sum(int(a.get("bytes", 0)) for a in archive),
    }


def build_manifest(entries, kind="archive"):
    """构造归档清单（可被测试直接断言的纯函数）。"""
    return {
        "manifest_version": 1,
        "kind": kind,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "归档而非删除；恢复方式：把 to 路径下的条目移回 from 路径",
        "items": entries,
    }


# ───────────────────────────────────────────────────── I/O 层

def git_blob_hashes(root):
    """git 对象库里所有 blob 的 SHA-256（内容寻址）。

    ★ 用 `git cat-file --batch-all-objects --batch-check` 拿对象，
      再对 blob 逐个算 sha256 —— git 内部用的是 sha1/sha256 两种，
      我们的判定统一用 **sha256**（与 git 内部哈希无关，只看内容）。
    """
    hashes = {}
    try:
        out = subprocess.run(
            ["git", "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)"],
            cwd=str(root), capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return hashes
    blobs = [ln.split()[0] for ln in out.splitlines()
             if len(ln.split()) == 2 and ln.split()[1] == "blob"]
    if not blobs:
        return hashes
    # 逐个取内容算 sha256（分批，避免命令行过长）
    for i in range(0, len(blobs), 200):
        batch = blobs[i:i + 200]
        try:
            proc = subprocess.run(["git", "cat-file", "--batch"], cwd=str(root),
                                  input="\n".join(batch) + "\n",
                                  capture_output=True, timeout=180)
        except Exception:
            continue
        # --batch 输出是 "sha type size\n<content>\n"，逐个解析
        data = proc.stdout
        pos = 0
        for sha in batch:
            nl = data.find(b"\n", pos)
            if nl < 0:
                break
            header = data[pos:nl].decode("utf-8", "replace").split()
            if len(header) < 3:
                pos = nl + 1
                continue
            try:
                size = int(header[2])
            except ValueError:
                pos = nl + 1
                continue
            content = data[nl + 1:nl + 1 + size]
            hashes[hashlib.sha256(content).hexdigest()] = sha
            pos = nl + 1 + size + 1
    return hashes


def expand_pattern(base, pattern):
    """把登记表里的 pattern 展开成实际存在的路径列表。"""
    if "*" in pattern:
        # 只支持最后一段含 *（本工具的规则都是这种）
        parent = os.path.dirname(pattern)
        leaf = os.path.basename(pattern)
        p = Path(base) / parent if parent else Path(base)
        if not p.is_dir():
            return []
        import fnmatch
        return sorted([x for x in p.iterdir() if fnmatch.fnmatch(x.name, leaf)])
    p = Path(base) / pattern
    return [p] if p.exists() else []


def find_workspace(start):
    """定位 WorkBuddy 工作空间目录（**只读探测**）。

    ★ 现实约束（v3.28.0 实测）：包根在 `~/.workbuddy/plugins/...` 下，
      工作空间在 `~/Library/CloudStorage/OneDrive-Personal/GPT/WorkBuddy/<会话目录>/` ——
      两者**不在同一条路径树下** ⇒ 单纯「从包根上溯找 WorkBuddy」找不到。

      ⇒ 探测策略（按优先级）：
        ① **递归**在用户主目录里找名为 `WorkBuddy` 的目录（限深度 6），
           再在它下面找含 `01-research` 的会话目录
        ② 从包根上溯找 `WorkBuddy`（覆盖「同树」部署）
        ③ 常见相对路径候选
        ④ 都找不到 ⇒ 返回空列表（工作空间侧产物不扫描，**绝不猜**）

    ★ 用 `os.walk` 但**剪枝**掉明显的大目录（Library/Caches、node_modules 等），
      避免在 OneDrive 云盘里空转。
    """
    cands = []
    seen = set()

    def _add(p):
        s = str(p)
        if s not in seen and p.is_dir() and (p / "01-research").is_dir():
            seen.add(s)
            cands.append(p)

    # ① 递归找 WorkBuddy 目录
    #    ★ 剪枝清单**不能含 Library**：实测工作空间就在
    #      `~/Library/CloudStorage/OneDrive-Personal/GPT/WorkBuddy/` 下
    #      （v3.28.0 第一次实现把 Library 剪掉了 ⇒ 探测永远失败）
    home = Path(os.path.expanduser("~"))
    skip_names = {"node_modules", ".git", "Caches", ".cache",
                  ".Trash", "Applications", "venv", ".venv",
                  "__pycache__", ".pytest_cache", ".alma-snapshots"}
    for root, dirnames, _ in os.walk(str(home), topdown=True):
        depth = Path(root).relative_to(home).parts
        if len(depth) > 7:
            dirnames[:] = []
            continue
        for d in list(dirnames):
            if d in skip_names:
                dirnames.remove(d)
        if Path(root).name == "WorkBuddy":
            for child in sorted(Path(root).iterdir()):
                _add(child)
            dirnames[:] = []
            continue
        # 命中 GPT/WorkBuddy 这类命名
        for d in list(dirnames):
            if d == "WorkBuddy":
                for child in sorted((Path(root) / d).iterdir()):
                    _add(child)

    # ② 从包根上溯找
    here = Path(start).resolve()
    for parent in [here] + list(here.parents):
        wb = parent / "WorkBuddy"
        if wb.is_dir():
            for child in sorted(wb.iterdir()):
                _add(child)

    # ③ 常见相对路径候选
    for c in DEFAULT_WORKSPACE_CANDIDATES:
        _add((here / c).resolve())

    return cands


def collect_candidates(rule, pkg_root, workspace_root):
    """按规则收集候选产物项。"""
    base = pkg_root if rule["base"] == "pkg" else workspace_root
    if base is None:
        return []
    paths = expand_pattern(base, rule["pattern"])
    out = []
    for p in paths:
        if rule.get("skip_if_manifest") and p.is_dir() and (p / MANIFEST_NAME).exists():
            continue
        if p.is_dir():
            size, count = dir_size_and_count(p)
            out.append({"path": str(p), "name": p.name, "bytes": size,
                        "count": count, "kind": "dir"})
        elif p.is_file():
            try:
                out.append({"path": str(p), "name": p.name,
                            "bytes": p.stat().st_size, "count": 1, "kind": "file"})
            except OSError:
                pass
    return out


def collect_duplicate_hashes(workspace_root, dup_targets):
    """收集对照目录里所有文件的 sha256（用于副本判定）。"""
    hashes = {}
    if not workspace_root:
        return hashes
    for t in dup_targets:
        d = Path(workspace_root) / t
        if not d.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x not in ("__pycache__", ".git")]
            for fn in filenames:
                fp = Path(dirpath) / fn
                h = sha256_file(fp)
                if h:
                    hashes.setdefault(h, []).append(str(fp))
    return hashes


# ───────────────────────────────────────────────────── 执行

def do_archive(pkg_root, entries, dry_run=True, allow_workspace_move=False):
    """把产物**移动**到归档区（★ 不删除）。"""
    moved = []
    skipped = []
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest_root = Path(pkg_root) / ARCHIVE_ROOT / ts
    for e in entries:
        src = Path(e["path"])
        if not src.exists():
            skipped.append({"path": str(src), "reason": "已不存在（幂等）"})
            continue
        # 工作空间路径默认只读
        if not str(src).startswith(str(pkg_root)) and not allow_workspace_move:
            skipped.append({"path": str(src),
                            "reason": "工作空间侧产物需显式 --allow-workspace-move 才移动"})
            continue
        dest = dest_root / src.name
        n = 1
        while dest.exists():
            dest = dest_root / ("%s.%d" % (src.name, n))
            n += 1
        if dry_run:
            moved.append({"from": str(src), "to": str(dest), "bytes": e.get("bytes", 0),
                          "reason": e.get("reason", "")})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        moved.append({"from": str(src), "to": str(dest), "bytes": e.get("bytes", 0),
                      "reason": e.get("reason", "")})
    return dest_root, moved, skipped


def run_scan(pkg_root, workspace_root, keep, verbose=True):
    """扫描：算出各规则的归档计划（只读）。"""
    git_hashes = git_blob_hashes(pkg_root)
    results = []
    total_archive = 0
    total_orphan = 0
    for rule in ARTIFACT_RULES:
        cands = collect_candidates(rule, pkg_root, workspace_root)
        if not cands:
            results.append({"rule": rule["id"], "name": rule["name"],
                            "candidates": 0, "archive": [], "keep": [],
                            "orphan": []})
            continue
        local_hashes = {}
        if rule.get("require") == "duplicate":
            local_hashes = collect_duplicate_hashes(
                workspace_root, rule.get("dup_targets") or ())
        plan = plan_archive(cands, keep.get(rule["keep"]) if rule.get("keep") else None,
                            require=rule.get("require", "none"),
                            dup_targets=rule.get("dup_targets"),
                            git_hashes=git_hashes, local_hashes=local_hashes)
        total_archive += plan["reclaimed_bytes"]
        total_orphan += sum(int(o.get("bytes", 0)) for o in plan["orphan"])
        results.append({"rule": rule["id"], "name": rule["name"],
                        "candidates": len(cands),
                        "archive": plan["archive"], "keep": plan["keep"],
                        "orphan": plan["orphan"]})
        if verbose:
            print("\n[%s] %s —— 候选 %d 项" % (rule["id"], rule["name"], len(cands)))
            for a in plan["archive"]:
                print("   ⇢ 归档 %-46s %8d 字节  (%s)"
                      % (a["name"][:46], a.get("bytes", 0), a["reason"][:52]))
            for k in plan["keep"]:
                print("   · 保留 %-46s %8d 字节  (%s)"
                      % (k["name"][:46], k.get("bytes", 0), k["reason"][:52]))
            for o in plan["orphan"]:
                print("   ✗ 拒绝 %-46s %8d 字节  (%s)"
                      % (o["name"][:46], o.get("bytes", 0), o["reason"][:52]))
    return results, total_archive, total_orphan


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="migrate_artifacts.py",
        description="旧产物迁移与归档清理（只归档不删除）")
    ap.add_argument("--scan", action="store_true", help="只扫描不动作（默认行为）")
    ap.add_argument("--confirm", action="store_true", help="真正执行归档（移动）")
    ap.add_argument("--workspace", default=None, help="工作空间目录（显式指定）")
    ap.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP["keep_backups"])
    ap.add_argument("--keep-zips", type=int, default=DEFAULT_KEEP["keep_zips"])
    ap.add_argument("--keep-archives", type=int, default=DEFAULT_KEEP["keep_archives"])
    ap.add_argument("--allow-workspace-move", action="store_true",
                    help="允许移动工作空间侧产物（默认只报告）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args(argv)

    pkg_root = Path(__file__).resolve().parent.parent
    workspace_root = None
    if args.workspace:
        workspace_root = Path(args.workspace).resolve()
        if not workspace_root.is_dir():
            print("✗ 工作空间不存在：%s" % workspace_root)
            return 2
    else:
        found = find_workspace(pkg_root)
        workspace_root = found[0] if found else None

    keep = {
        "keep_backups": args.keep_backups,
        "keep_zips": args.keep_zips,
        "keep_archives": args.keep_archives,
    }

    results, total_archive, total_orphan = run_scan(pkg_root, workspace_root, keep)

    if args.json:
        print(json.dumps({"results": results, "reclaimable_bytes": total_archive,
                          "orphan_bytes": total_orphan,
                          "workspace": str(workspace_root) if workspace_root else None},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("产物归档扫描")
        print("  包根：%s" % pkg_root)
        print("  工作空间：%s" % (workspace_root or "未找到（工作空间侧产物不扫描）"))
        print("  保留策略：%s" % json.dumps(keep, ensure_ascii=False))
        print("=" *72)
        print("\n可回收（归档后释放）：%d 字节（%.2f MiB）"
              % (total_archive, total_archive / 1048576.0))
        if total_orphan:
            print("拒绝归档（无主，原样保留）：%d 字节（%.2f MiB）"
                  % (total_orphan, total_orphan / 1048576.0))

    if not args.confirm:
        if not args.json:
            print("\n（dry-run：加 --confirm 才真正移动；★ 移动到归档区，不删除）")
        return 0 if total_orphan == 0 else 1

    # ── 执行：收集全部待归档项
    entries = []
    for r in results:
        entries.extend(r["archive"])
    if not entries:
        if not args.json:
            print("\n✓ 无待归档产物")
        return 0
    dest_root, moved, skipped = do_archive(pkg_root, entries, dry_run=False,
                                            allow_workspace_move=args.allow_workspace_move)
    manifest = build_manifest(moved)
    dest_root.mkdir(parents=True, exist_ok=True)
    (dest_root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.json:
        print("\n✓ 已归档 %d 项 → %s" % (len(moved), dest_root))
        print("   清单：%s" % (dest_root / MANIFEST_NAME))
        print("   ★ 未删除任何文件；恢复方式见清单 from/to 字段")
        for s in skipped:
            print("   ⊘ 跳过：%s（%s）" % (s["path"], s["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

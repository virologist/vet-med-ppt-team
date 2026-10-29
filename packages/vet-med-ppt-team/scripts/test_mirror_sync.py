#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_mirror_sync.py — 「镜像同步纪律」的守卫（v3.27.0 · L-7）

══════════════════════════════════════════════════════════════════════
被守卫的纪律（每条都必须有**能红的反例**，否则本文件形同虚设）：
  D1 排除清单**必须含 `packages`** ⇒ 自复制事故（嵌套 `packages/packages/`）不可能复发
  D2 默认**不做删除传播** ⇒ 镜像多出的文件只报告、不删
  D3 dry-run **不改任何文件** ⇒ 目标文件逐字节不变
  D4 真同步前**有备份** ⇒ 被覆盖的文件留有副本且内容与原文件一致
  D5 真同步后**零差异** ⇒ 根与镜像逐字节一致
  D6 **嵌套防护** ⇒ 脚本执行后不得产出 `packages/packages/`

⚠ **本文件绝不污染生产 `packages/vet-med-ppt-team/`**：
  所有用例都在 `tempfile` 造的**沙盒包根**里跑（沙盒自带一个假的 `packages/` 子目录），
  通过 `main(argv, pkg_root=...)` 注入包根 ⇒ 生产目录零写入。
  末尾的 T8 专门断言「生产镜像未被本套件改动」。

运行：
    python3 -m pytest scripts/test_mirror_sync.py -q
    python3 scripts/test_mirror_sync.py          # 直跑（体检第 7 项按此方式）
"""

import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

#: 沙盒镜像目录名（与生产一致，便于脚本按同一套逻辑跑）。
MIRROR_NAME = "vet-med-ppt-team"


def _load_ms():
    """按路径加载 mirror_sync 模块（不依赖包内 import 副作用）。"""
    spec = importlib.util.spec_from_file_location(
        "mirror_sync_ut", HERE / "mirror_sync.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["mirror_sync_ut"] = m
    spec.loader.exec_module(m)
    return m


MS = _load_ms()


def _digest(path: Path):
    """文件内容摘要（用于「逐字节不变」断言）。"""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MirrorSandbox:
    """沙盒包根：自带一个假的 `packages/<镜像名>/` 子目录。

    布局：
        <sandbox>/                 ← 包根（源）
            a.txt                 ← 根有、镜像无
            b.txt                 ← 两边都有但内容不同
            same.txt              ← 两边一致
            packages/
                vet-med-ppt-team/  ← 镜像（目标）
                    b.txt         ← 旧内容
                    same.txt      ← 同内容
                    extra.txt     ← 镜像多出（根上没有）
                    stale/old.txt ← 镜像多出的子目录内容
    """

    def __init__(self, tmp: Path):
        self.root = tmp / "pkg"
        self.mirror = self.root / "packages" / MIRROR_NAME
        self.root.mkdir(parents=True)
        self.mirror.mkdir(parents=True)

        (self.root / "a.txt").write_text("A-根\n", encoding="utf-8")
        (self.root / "b.txt").write_text("B-新\n", encoding="utf-8")
        (self.root / "same.txt").write_text("SAME\n", encoding="utf-8")

        (self.mirror / "b.txt").write_text("B-旧\n", encoding="utf-8")
        (self.mirror / "same.txt").write_text("SAME\n", encoding="utf-8")
        (self.mirror / "extra.txt").write_text("EXTRA\n", encoding="utf-8")
        (self.mirror / "stale").mkdir()
        (self.mirror / "stale" / "old.txt").write_text("OLD\n", encoding="utf-8")

    def run(self, argv):
        """跑脚本，返回 (rc, 输出文本)。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = MS.main(argv, pkg_root=str(self.root))
        return rc, buf.getvalue()


class TestMirrorSyncDiscipline(unittest.TestCase):
    """镜像同步纪律守卫（每条判据都有能红的反例）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vetmed-mirror-sync-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # 每个用例一个独立沙盒 ⇒ 用例之间零互相污染
        self.sandbox_dir = Path(tempfile.mkdtemp(prefix="vetmed-mirror-case-",
                                                 dir=str(self.tmp)))
        self.s = MirrorSandbox(self.sandbox_dir)

    def tearDown(self):
        shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    # ── D1：排除清单必须含 `packages`（防自复制）────────────────
    def test_D1_exclude_list_contains_packages(self):
        """D1：排除清单必须含 `packages`。

        ★ **能红反例**：把 `packages` 从清单里删掉 ⇒ 本用例判红。
          （若清单不含 `packages`，脚本会把镜像目录同步进它自己。）
        """
        self.assertIn(
            "packages", MS.EXCLUDE_PATTERNS,
            "排除清单必须含 `packages`——否则镜像会被同步进它自己"
            "（嵌套 packages/packages/，5.6MB 污染事故）")

    def test_D1b_excluding_packages_prevents_self_copy(self):
        """D1b（能红反例的行为面）：清单含 `packages` ⇒ 遍历时**看不见** packages/。

        反例：若把 `packages` 从清单移除，下面这个断言立刻失败。
        """
        found = MS.iter_files(self.s.root)
        leaked = [r for r in found if r.split(os.sep)[0] == "packages"]
        self.assertEqual(
            leaked, [],
            f"遍历结果里泄漏了 packages/ 下的文件：{leaked}")

    def test_D1c_mirror_dir_never_synced_into_itself(self):
        """D1c：真同步后，镜像里**不得**出现 packages/packages/ 嵌套目录。

        这是事故 ② 的直接行为断言（不是只看清单文本）。
        """
        rc, out = self.s.run(["--confirm"])
        nested = self.s.mirror / "packages"
        self.assertFalse(
            nested.exists(),
            f"同步后产出了嵌套目录 {nested}（自复制事故复发）")
        # 嵌套下也不该有任何内容
        if nested.exists():
            self.assertEqual(list(nested.rglob("*")), [])

    # ── D2：默认不做删除传播 ───────────────────────────────
    def test_D2_default_does_not_delete_extra_files(self):
        """D2：默认模式**不得**删除「镜像多出的文件」，且**必须报告**它。

        ★ **能红反例**：若默认开启删除传播 ⇒ extra.txt 会消失 ⇒ 判红。
        """
        extra = self.s.mirror / "extra.txt"
        stale = self.s.mirror / "stale" / "old.txt"
        self.assertTrue(extra.is_file(), "沙盒前置条件失效：extra.txt 不存在")

        # dry-run（默认）：不得删，且必须报告
        rc, out = self.s.run([])
        self.assertTrue(extra.is_file(), "dry-run 删除了 extra.txt（纪律 D2 被破）")
        self.assertTrue(stale.is_file(), "dry-run 删除了 stale/old.txt（纪律 D2 被破）")
        self.assertIn("extra.txt", out, "dry-run 未报告 extra.txt（纪律 D2 被破）")
        self.assertIn("stale/old.txt", out.replace(os.sep, "/"),
                      "dry-run 未报告 stale/old.txt（纪律 D2 被破）")

        # 真同步（默认，无 --prune）：仍不得删
        rc, out = self.s.run(["--confirm"])
        self.assertTrue(extra.is_file(),
                        "真同步（未加 --prune）删除了 extra.txt（纪律 D2 被破）")
        self.assertTrue(stale.is_file(),
                        "真同步（未加 --prune）删除了 stale/old.txt（纪律 D2 被破）")
        self.assertIn("extra.txt", out,
                      "真同步未报告 extra.txt（纪律 D2 被破）")

    def test_D2b_prune_is_opt_in_and_lists_files_before_deleting(self):
        """D2b：`--prune` 是**显式开关**，默认关闭；开启时须逐条列出待删文件。

        ★ **能红反例**：若 `--prune` 默认开启 ⇒ 上一个用例 D2 就会红。
        """
        # 默认（无 --prune）时，--prune 的效果必须不发生
        rc, out = self.s.run(["--confirm"])
        self.assertTrue((self.s.mirror / "extra.txt").is_file(),
                        "--prune 未显式开启却删了文件（纪律 D2 被破）")
        self.assertIn("默认", out)

        # 显式 --prune + --confirm ⇒ 允许删（证明开关本身有效，不是死代码）
        rc, out = self.s.run(["--confirm", "--prune"])
        self.assertFalse((self.s.mirror / "extra.txt").is_file(),
                         "--prune --confirm 未删除 extra.txt（开关失效）")

    # ── D3：dry-run 不改任何文件 ─────────────────────────────
    def test_D3_dry_run_changes_nothing(self):
        """D3：dry-run 后目标文件**逐字节不变**。

        ★ **能红反例**：若 dry-run 真的写了 ⇒ b.txt 的摘要会变 ⇒ 判红。
        """
        b = self.s.mirror / "b.txt"
        extra = self.s.mirror / "extra.txt"
        before_b = _digest(b)
        before_extra = _digest(extra)
        before_mtime = b.stat().st_mtime_ns

        rc, out = self.s.run([])

        self.assertEqual(_digest(b), before_b,
                         "dry-run 改动了 b.txt 的内容（纪律 D3 被破）")
        self.assertEqual(_digest(extra), before_extra,
                         "dry-run 改动了 extra.txt（纪律 D3 被破）")
        self.assertEqual(b.stat().st_mtime_ns, before_mtime,
                         "dry-run 触碰了 b.txt 的 mtime（纪律 D3 被破）")
        # 新增文件也不该被创建
        self.assertFalse((self.s.mirror / "a.txt").exists(),
                         "dry-run 创建了 a.txt（纪律 D3 被破）")
        # dry-run 发现差异 ⇒ rc=1（CI 可发现漂移）
        self.assertEqual(rc, 1,
                         f"dry-run 发现差异时应 rc=1，实际 {rc}")

    def test_D3b_dry_run_creates_no_backup_dir(self):
        """D3b：dry-run **不得**创建备份目录（备份只在真同步时产生）。

        ★ **能红反例**：若 dry-run 也建备份目录 ⇒ 下面断言判红。
        """
        self.s.run([])
        backups = self.s.root / "packages" / ".mirror_backups"
        self.assertFalse(
            backups.exists(),
            f"dry-run 创建了备份目录 {backups}（纪律 D3 被破）")

    # ── D4：真同步前有备份 ───────────────────────────────────
    def test_D4_backup_exists_and_matches_original(self):
        """D4：真同步前，被覆盖的文件有备份副本，且内容与**原文件**一致。

        ★ **能红反例**：若无备份 ⇒ 断言失败；备份内容若取的是**新**内容
          （而非覆盖前的旧内容）⇒ 摘要不等 ⇒ 判红。
        """
        b = self.s.mirror / "b.txt"
        original = _digest(b)

        rc, out = self.s.run(["--confirm"])

        backups = self.s.root / "packages" / ".mirror_backups"
        self.assertTrue(backups.is_dir(), "真同步未创建备份目录（纪律 D4 被破）")
        # 备份保留相对路径结构
        candidates = list(backups.rglob("b.txt"))
        self.assertTrue(candidates,
                        "备份目录里没有 b.txt 的副本（纪律 D4 被破）")
        backed = _digest(candidates[0])
        self.assertEqual(
            backed, original,
            "备份内容与覆盖前的原文件不一致（纪律 D4 被破：备份没保住旧内容）")
        # 覆盖本身应当生效
        self.assertEqual(_digest(b), _digest(self.s.root / "b.txt"),
                         "b.txt 未被正确覆盖")

    # ── D5：真同步后零差异 ───────────────────────────────────
    def test_D5_real_sync_yields_zero_diff(self):
        """D5：真同步后，根侧受管文件在镜像中**零差异**（沙盒内跑）。

        ⚠ 「零差异」的准确含义：根侧每个受管文件在镜像中都有**逐字节相同**的副本。
          镜像**多出**的文件（extra）默认**保留不删**（纪律 D2），
          故它不属于「必须修」的那一类，单独断言。

        ★ **能红反例**：若同步有漏（漏新增/漏覆盖）⇒ missing/differing 非空 ⇒ 判红。
        """
        rc, out = self.s.run(["--confirm"])
        self.assertEqual(rc, 0, f"真同步后 rc 应为 0，实际 {rc}\n{out}")

        cats, n = MS.verify_with_diff(self.s.root, self.s.mirror)
        self.assertEqual(cats["missing"], [],
                         f"真同步后镜像仍缺文件：{cats['missing']}")
        self.assertEqual(cats["differing"], [],
                         f"真同步后镜像内容仍过期：{cats['differing']}")
        self.assertGreater(n, 0, "受管文件数为 0（沙盒前置条件失效）")
        self.assertIn("零差异", out, "输出未报告「零差异」")

    def test_D5b_prune_sync_reaches_full_zero_difference(self):
        """D5b：加上 `--prune` 后，根与镜像**完全**零差异（含无多余文件）。

        这是「严格零差异」的那一档：extra 也被清掉 ⇒ 两棵树完全一致。

        ★ **能红反例**：若 --prune 未生效 ⇒ extra 非空 ⇒ 判红。
        """
        rc, out = self.s.run(["--confirm", "--prune"])
        self.assertEqual(rc, 0, f"真同步(--prune) 应 rc=0，实际 {rc}\n{out}")

        cats, n = MS.verify_with_diff(self.s.root, self.s.mirror)
        self.assertEqual(cats["missing"], [], "镜像仍缺文件")
        self.assertEqual(cats["differing"], [], "镜像内容仍过期")
        self.assertEqual(cats["extra"], [],
                         f"--prune 后镜像仍有多余文件：{cats['extra']}")
        # 两棵树逐文件集合也必须一致
        self.assertEqual(set(MS.iter_files(self.s.root)),
                         set(MS.iter_files(self.s.mirror)),
                         "--prune 后两棵树的受管文件集合仍不一致")
        self.assertIn("零差异", out, "输出未报告「零差异」")

    def test_D5c_no_diff_means_rc0_and_no_sync_needed(self):
        """D5c：完全同步后（--prune）再跑 dry-run ⇒ rc=0。

        ★ **能红反例**：若 dry-run 总报 rc=1 ⇒ 判红（CI 会被误报）。
        """
        self.s.run(["--confirm", "--prune"])
        rc, out = self.s.run([])
        self.assertEqual(rc, 0,
                         f"已同步状态下 dry-run 应 rc=0，实际 {rc}\n{out}")
        self.assertIn("零差异", out)

    def test_D2c_prune_keeps_dirs_that_exist_in_root(self):
        """D2c：`--prune` 清理空目录时，**不得**删掉「根上也存在」的空目录。

        空目录是包内容的一部分（不是镜像残留）⇒ 删了就是误伤。

        ★ **能红反例**：若清理逻辑不看根侧目录集合 ⇒ 本用例判红。
        """
        # 根与镜像**都**有 emptydir/（根侧是空的 ⇒ 镜像侧也该保留）
        (self.s.root / "emptydir").mkdir()
        (self.s.mirror / "emptydir").mkdir()

        rc, out = self.s.run(["--confirm", "--prune"])
        self.assertTrue(
            (self.s.mirror / "emptydir").is_dir(),
            "--prune 删掉了根上也存在的空目录（误伤包内容）")

    def test_D2d_extra_files_keep_dry_run_rc1_but_sync_rc0(self):
        """D2d：退出码语义必须与「差异分两类」一致（--help 里已写明）。

        · dry-run 且存在「镜像多出」⇒ rc=1（如实报告漂移，CI 可见）
        · 真同步（默认，不删）⇒ rc=0（同步做完了它该做的事）

        ★ **能红反例**：若把 extra 也算成「同步失败」⇒ 真同步会误报 rc=1 ⇒ 判红。
        """
        rc, out = self.s.run([])
        self.assertEqual(rc, 1,
                         f"存在镜像多出文件时 dry-run 应 rc=1，实际 {rc}\n{out}")
        rc, out = self.s.run(["--confirm"])
        self.assertEqual(rc, 0,
                         f"真同步（默认不删）应 rc=0，实际 {rc}\n{out}")
        self.assertIn("保留", out, "输出未说明镜像多出项被保留")

    # ── D6：嵌套防护 ─────────────────────────────────────────
    def test_D6_no_nested_packages_after_sync(self):
        """D6：脚本执行后**不得**产出 packages/packages/ 目录。

        ★ **能红反例**：若排除清单漏了 `packages` ⇒ 嵌套目录出现 ⇒ 判红。
        """
        self.s.run(["--confirm"])
        nested = self.s.mirror / "packages"
        self.assertFalse(nested.exists(),
                         f"同步后出现嵌套目录 {nested}（事故 ② 复发）")
        # 整棵镜像树下都不该有第二层 packages
        for p in self.s.mirror.rglob("packages"):
            self.assertFalse(
                p.is_dir() and p != self.s.mirror,
                f"镜像下出现嵌套 packages 目录：{p}")

    # ── 通用：脚本可注入包根 / --help / 退出码 ────────────────
    def test_T7_pkg_root_is_injectable(self):
        """T7：包根**可注入**（测试指向沙盒，生产目录零写入）。

        这是整个测试文件成立的前提 ⇒ 单独钉一条用例。
        """
        rc, out = self.s.run([])
        self.assertIn(str(self.s.root), out,
                      "输出未显示注入的包根（可注入性失效）")
        self.assertIn(str(self.s.mirror), out,
                      "输出未显示注入的镜像路径（可注入性失效）")

    def test_T7b_help_works_and_documents_exit_codes(self):
        """T7b：`--help` 可用，且写明了退出码语义。"""
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stdout(buf):
                MS.main(["--help"])
        self.assertEqual(cm.exception.code, 0, "--help 应以 0 退出")
        text = buf.getvalue()
        for kw in ("--confirm", "--prune", "退出码"):
            self.assertIn(kw, text, f"--help 未说明 {kw}")

    def test_T7c_missing_pkg_root_exits_2(self):
        """T7c：包根不存在 ⇒ rc=2（用法/环境错误），不抛异常。"""
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = MS.main(["--pkg-root", str(self.sandbox_dir / "不存在")])
        self.assertEqual(rc, 2, f"包根不存在应 rc=2，实际 {rc}")

    def test_T7d_dry_run_exit_code_zero_when_already_synced(self):
        """T7d：无差异时 dry-run ⇒ rc=0（差异时 rc=1，见 D3）。

        两条合起来把「0=无差异 / 1=有差异」的退出码语义钉死。
        """
        rc, out = self.s.run(["--confirm", "--prune"])
        self.assertEqual(rc, 0, f"首次真同步应 rc=0，实际 {rc}\n{out}")
        rc, out = self.s.run([])
        self.assertEqual(rc, 0, f"同步后 dry-run 应 rc=0，实际 {rc}\n{out}")


class TestDoctorCommittedParityGuard(unittest.TestCase):
    """T9：体检第 26 项「根 ⇄ 镜像提交态一致性」的**双向**护栏。

    ① 正向：两侧提交态一致 ⇒ rc=0（不得常态性假红）。
    ② 反例：根侧提交了而镜像没跟 ⇒ **必须判红**（能红的反例）。
    ③ 防误伤：仅**工作区**改动（未提交）⇒ 仍判绿
       （「改包但还没同步镜像」是正常开发中间态，不该报警）。

    ⚠ 全程在 `tempfile` 造的**临时 git 仓库**里跑 ⇒ 不碰生产仓库。
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vetmed-parity-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _make_repo(self, sync: bool) -> Path:
        """造一个临时 git 仓库：根侧 + 镜像侧。

        sync=True  ⇒ 两侧内容相同（提交态一致）
        sync=False ⇒ 根侧有文件镜像没有（提交态漂移）
        """
        repo = Path(tempfile.mkdtemp(prefix="vetmed-parity-case-", dir=str(self.tmp)))
        self._git(repo, "init", "-q", ".")
        (repo / "scripts").mkdir(parents=True)
        (repo / "packages" / "vet-med-ppt-team" / "scripts").mkdir(parents=True)
        # 体检第 26 项要加载仓库里的 mirror_sync.py
        shutil.copy2(str(HERE / "mirror_sync.py"),
                     str(repo / "scripts" / "mirror_sync.py"))
        shutil.copy2(str(HERE / "mirror_sync.py"),
                     str(repo / "packages" / "vet-med-ppt-team" / "scripts" / "mirror_sync.py"))
        (repo / "doc.txt").write_text("DOC\n", encoding="utf-8")
        if sync:
            (repo / "packages" / "vet-med-ppt-team" / "doc.txt").write_text(
                "DOC\n", encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "-c", "user.email=t@t", "-c", "user.name=t",
                  "commit", "-qm", "init")
        return repo

    @staticmethod
    def _git(repo: Path, *args):
        subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, check=False)

    def _run_check(self, repo: Path):
        """跑体检第 26 项，返回 (rc, 输出)。"""
        spec = importlib.util.spec_from_file_location(
            "es_parity_ut", HERE / "ensure_settings.py")
        es = importlib.util.module_from_spec(spec)
        sys.modules["es_parity_ut"] = es
        spec.loader.exec_module(es)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = es.check_mirror_committed_parity(str(repo))
        return rc, buf.getvalue()

    def test_T9a_consistent_commit_state_passes(self):
        """T9a：两侧提交态一致 ⇒ rc=0。"""
        repo = self._make_repo(sync=True)
        rc, out = self._run_check(repo)
        self.assertEqual(rc, 0, f"一致时不该判红（rc={rc}）\n{out}")
        self.assertIn("一致", out)

    def test_T9b_drifted_commit_state_fails(self):
        """T9b（能红反例）：根侧提交了、镜像没跟 ⇒ **必须判红**。

        若这项恒绿 ⇒ 「忘记同步 ⇒ 漂移进入发布」的事故就没人拦。
        """
        repo = self._make_repo(sync=False)
        rc, out = self._run_check(repo)
        self.assertNotEqual(rc, 0,
                            f"提交态漂移未判红（第 26 项恒绿 = 假绿）\n{out}")
        self.assertIn("doc.txt", out, "未指出具体漂移文件")

    def test_T9c_worktree_only_edit_does_not_false_red(self):
        """T9c（防误伤）：仅**工作区**改动（未提交）⇒ 仍判绿。

        「改包但还没同步镜像」是**正常开发中间态** ⇒ 不该常态性假红。
        这是本项采用「提交态」而非「工作区」比对的**根本理由**。
        """
        repo = self._make_repo(sync=True)
        # 工作区改根侧 + 新增未跟踪文件，但**不提交**
        (repo / "doc.txt").write_text("EDITED-IN-WORKTREE\n", encoding="utf-8")
        (repo / "untracked.txt").write_text("NEW\n", encoding="utf-8")
        rc, out = self._run_check(repo)
        self.assertEqual(rc, 0,
                         f"仅工作区改动被判红（假红）\n{out}")


class TestProductionNotPolluted(unittest.TestCase):
    """T8：本套件**绝不**污染生产 `packages/vet-med-ppt-team/`。

    用例全程只写 tempfile 沙盒；这里额外把生产的镜像目录快照下来对比，
    把「测试不得污染生产」这条纪律变成**可执行**的断言。
    """

    def test_T8_production_mirror_untouched(self):
        prod = PKG / "packages" / MIRROR_NAME
        if not prod.is_dir():
            self.skipTest("生产镜像目录不存在（未安装镜像），跳过")

        def snapshot():
            out = {}
            for p in sorted(prod.rglob("*")):
                if p.is_file():
                    out[str(p.relative_to(prod))] = _digest(p)
            return out

        before = snapshot()

        # 在沙盒里跑一整套（新增 + 覆盖 + 删除传播全开）
        tmp = Path(tempfile.mkdtemp(prefix="vetmed-mirror-prod-guard-"))
        try:
            s = MirrorSandbox(tmp)
            s.run(["--confirm"])
            s.run(["--confirm", "--prune"])
            s.run([])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        after = snapshot()
        self.assertEqual(
            before, after,
            "生产镜像目录被本测试套件改动了（纪律被破）")


if __name__ == "__main__":
    unittest.main(verbosity=2)

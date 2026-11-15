#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# b2026111504 · A0-批1 退出码契约「能红反例」回归测试（v3.31.3 内整改）
#
# 本文件 4 条用例专门盯「失败路径恒 exit 0」这一契约缺陷：
#   在修复前的旧代码上必须失败（能红），在修复后的新代码上必须全部通过。
#   - snapshot.py / surgery_deck.py：main() 有非零返回值却被直接调用，返回值被丢弃 ⇒ 失败仍 exit 0。
#   - ooxml_lint.py：--level WARN 会把 ERROR 从显示里过滤掉，连带把退出码算成 0；
#     检查器异常被静默吞掉后，扫描不完整却按「0 ERROR 通过」放行。
# 运行方式（在 scripts/ 目录下）：python3 -m unittest -v test_a0_exit_contract_red
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

# 让同目录的生产脚本可被 import（ooxml_lint.LintRunner 等）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ooxml_lint import LintRunner  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PY = os.path.join(HERE, "snapshot.py")
SURGERY_DECK_PY = os.path.join(HERE, "surgery_deck.py")


class A0ExitContractRedTest(unittest.TestCase):
    """退出码契约的能红反例集合。"""

    def setUp(self):
        # 每个用例独立的临时目录，避免相互污染
        self.tmp = tempfile.mkdtemp(prefix="a0_exit_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_clean_pptx(self, name="clean.pptx"):
        """用 python-pptx 生成一份 0 ERROR 的干净课件。"""
        from pptx import Presentation
        path = os.path.join(self.tmp, name)
        Presentation().save(path)
        return path

    # ① snapshot.py：缺 deck 时 main() 返回 3，旧代码直接调用丢弃返回值 ⇒ exit 0
    def test_snapshot_missing_deck_exit3(self):
        missing = os.path.join(self.tmp, "no_such_deck.pptx")
        result = subprocess.run(
            [sys.executable, SNAPSHOT_PY, "snap", missing, "--workspace", self.tmp],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 3,
                         f"snapshot 缺 deck 应 exit 3；stdout={result.stdout!r} stderr={result.stderr!r}")

    # ② surgery_deck.py：清单里课件不存在时累计失败并返回 1，旧代码隐式 None ⇒ exit 0
    def test_surgery_deck_missing_deck_exit1(self):
        decks_txt = os.path.join(self.tmp, "decks.txt")
        with open(decks_txt, "w", encoding="utf-8") as f:
            f.write("ghost.pptx\n")   # 相对 base 的不存在路径
        # --dry-run 避免对（本就不存在的）课件产生备份文件
        result = subprocess.run(
            [sys.executable, SURGERY_DECK_PY, "--base", self.tmp,
             "--decks", decks_txt, "--dry-run"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1,
                         f"surgery_deck 缺课件应 exit 1；stdout={result.stdout!r} stderr={result.stderr!r}")
        # 输出里须能体现失败（stderr 告警 + 汇总），不能静默通过
        self.assertTrue("文件不存在" in result.stderr or "处理失败" in result.stderr,
                        f"stderr 应体现失败：{result.stderr!r}")

    # ③ ooxml_lint.py：--level WARN 不应把 ERROR 藏成 exit 0
    def test_ooxml_lint_level_warn_keeps_error_exit1(self):
        path = self._make_clean_pptx()
        # 追加一个与已有 part 同名的条目，制造 zip 重复名 → PKG-001 ERROR
        with zipfile.ZipFile(path, "r") as z:
            dup_data = z.read("ppt/presentation.xml")
        with zipfile.ZipFile(path, "a") as z:
            z.writestr("ppt/presentation.xml", dup_data)

        runner = LintRunner(str(path), level="WARN")
        rc = runner.run()
        self.assertEqual(rc, 1, "--level WARN 不得把 ERROR 过滤成 exit 0")
        self.assertGreaterEqual(runner.raw_error_count, 1,
                                "判定计数须基于过滤前的全部 issues")

    # ④ ooxml_lint.py：检查器崩溃不得静默吞掉，须 fail-closed 走缺陷回流 exit 4
    def test_ooxml_lint_checker_crash_fails_closed(self):
        path = self._make_clean_pptx()
        with mock.patch("ooxml_lint.PkgChecker.check",
                        side_effect=RuntimeError("注入的检查器崩溃")):
            runner = LintRunner(str(path))
            rc = runner.run()
        self.assertEqual(rc, 4, "检查器崩溃须 fail-closed 返回 4，不得当作 0 ERROR 通过")
        self.assertGreaterEqual(len(runner._checker_failures), 1,
                                "崩溃须登记进 _checker_failures")


if __name__ == "__main__":
    unittest.main(verbosity=2)

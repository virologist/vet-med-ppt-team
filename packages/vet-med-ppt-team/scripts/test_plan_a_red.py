#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# b2026111506 · 方案A「幂等状态查询 / 闸4.5 接线订正」能红反例（v3.31.3 内整改）
#
# 4 条用例，旧码（7f858af）须失败、新码须全绿：
#   - B1.3：install() 的 return True 是**幂等标记**（首次装 / 重复调），不是
#     「六个补丁全部成功」的证明；旧码没有独立状态查询，补丁静默失败仍报成功。
#   - B1.4：原诊断「护栏装在闸外、闸4.5 从不联网验 PMID」是 v3.11 历史状态，
#     v3.17.0 起 verify_deck.py#three_source_check 与 cmd_verify_ref --online
#     都已调用带 yaml 参数的 pmid_existence_check；零引用的薄封装应删除而非接回。
# 运行方式（在 scripts/ 目录下）：python3 -m unittest -v test_plan_a_red
import ast
import contextlib
import os
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import host_safe_tmp  # noqa: E402

HERE = Path(__file__).resolve().parent


@contextlib.contextmanager
def _install_guard():
    """install() 改的是进程级全局 ⇒ 用例退出时逐项还原，避免污染同进程其它套件。"""
    snap = {
        "mkdir": os.mkdir, "makedirs": os.makedirs,
        "replace": os.replace, "rename": os.rename,
        "mkdtemp": tempfile.mkdtemp,
        "Path.mkdir": pathlib.Path.mkdir, "Path.touch": pathlib.Path.touch,
        "installed": dict(host_safe_tmp._INSTALLED),
        "orig_path_mkdir": getattr(host_safe_tmp, "_ORIG_PATH_MKDIR", None),
        "orig_path_touch": getattr(host_safe_tmp, "_ORIG_PATH_TOUCH", None),
    }
    try:
        yield
    finally:
        os.mkdir = snap["mkdir"]
        os.makedirs = snap["makedirs"]
        os.replace = snap["replace"]
        os.rename = snap["rename"]
        tempfile.mkdtemp = snap["mkdtemp"]
        pathlib.Path.mkdir = snap["Path.mkdir"]
        pathlib.Path.touch = snap["Path.touch"]
        host_safe_tmp._INSTALLED.clear()
        host_safe_tmp._INSTALLED.update(snap["installed"])
        host_safe_tmp._ORIG_PATH_MKDIR = snap["orig_path_mkdir"]
        host_safe_tmp._ORIG_PATH_TOUCH = snap["orig_path_touch"]
        if hasattr(host_safe_tmp, "_PATCH_STATUS"):
            host_safe_tmp._PATCH_STATUS.clear()
        if hasattr(host_safe_tmp, "_PATCH_FAILURES"):
            host_safe_tmp._PATCH_FAILURES.clear()


class _FailingTempfile:
    """代理：只让 `tempfile.mkdtemp = ...` 这一处赋值抛错，其余委托真实 tempfile。"""

    def __init__(self, real):
        object.__setattr__(self, "_real", real)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        if name == "mkdtemp":
            raise RuntimeError("注入：tempfile.mkdtemp 补丁失败")
        setattr(object.__getattribute__(self, "_real"), name, value)


class PlanARedTest(unittest.TestCase):
    """方案A 能红反例集合。"""

    def setUp(self):
        self._guard = _install_guard()
        self._guard.__enter__()
        if hasattr(host_safe_tmp, "_PATCH_STATUS"):
            host_safe_tmp._PATCH_STATUS.clear()
        if hasattr(host_safe_tmp, "_PATCH_FAILURES"):
            host_safe_tmp._PATCH_FAILURES.clear()
        host_safe_tmp._INSTALLED["done"] = False

    def tearDown(self):
        self._guard.__exit__(None, None, None)

    # ---------- T1：正常安装后状态查询须逐项可信 ----------
    def test_T1_install_status_reports_all_patches(self):
        self.assertTrue(host_safe_tmp.install())
        self.assertTrue(hasattr(host_safe_tmp, "install_status"),
                        "旧码没有独立状态查询 ⇒ 无法区分「幂等标记」与「补丁全成功」")
        st = host_safe_tmp.install_status()
        self.assertTrue(st["installed"])
        self.assertTrue(st["all_applied"], f"应全部生效，实际 {st}")
        self.assertEqual(st["failed_patches"], [])
        self.assertEqual(len(st["patches"]), 6,
                         f"六处补丁应逐一登记，实际 {st['patches']}")

    # ---------- T2：幂等返回值与状态查询互不干扰 ----------
    def test_T2_idempotent_return_unchanged(self):
        self.assertTrue(host_safe_tmp.install(), "首次安装返回 True（幂等标记）")
        before = host_safe_tmp.install_status()
        self.assertFalse(host_safe_tmp.install(), "重复调用返回 False（幂等标记，语义不变）")
        self.assertEqual(before, host_safe_tmp.install_status(),
                         "重复调用不得改变补丁实况")

    # ---------- T3：单个补丁失败时能被查出来，且不改 install() 返回值 ----------
    def test_T3_failed_patch_is_observable(self):
        real_tf = host_safe_tmp.tempfile
        host_safe_tmp.tempfile = _FailingTempfile(real_tf)
        try:
            rc = host_safe_tmp.install()
        finally:
            host_safe_tmp.tempfile = real_tf
        self.assertTrue(rc, "install() 仍返回幂等标记，不因单补丁失败而改变返回值语义")
        st = host_safe_tmp.install_status()
        self.assertFalse(st["all_applied"], f"有补丁失败时不得报全部生效：{st}")
        self.assertIn("tempfile.mkdtemp", st["failed_patches"])
        self.assertTrue(st["failures"], "失败原因应可追溯")

    # ---------- T4：闸4.5 在线核验接线守护 + 死封装已删 ----------
    def test_T4_gate45_online_wiring_guard(self):
        hp = (HERE / "harness.py").read_text(encoding="utf-8")
        funcs = [n.name for n in ast.walk(ast.parse(hp))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.assertNotIn("_pmid_online_check", funcs,
                         "零引用的薄封装应按死代码删除（不是接回闸里丢掉 yaml 参数）")
        self.assertIn("pmid_existence_check(sorted(todo)", hp,
                      "编排侧 cmd_verify_ref --online 的真实接线不得回退")
        vd = (HERE / "verify_deck.py").read_text(encoding="utf-8")
        self.assertIn("kernel.pmid_existence_check(", vd,
                      "裁判侧三源核验的真实接线不得回退")


if __name__ == "__main__":
    unittest.main(verbosity=2)

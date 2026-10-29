#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_regression_skip_report.py — 体检第 7 项「跳过可见化」判据守卫（v3.27.0 P0 收尾）
=================================================================================
背景（真实缺陷，非假设）：
  体检第 7 项（`ensure_settings.py#check_regression`）此前**只看子进程退出码 rc**。
  但 `unittest` 的 **skip 不改变 rc** —— 被 `skipTest()` 跳过的用例，
  套件仍然 rc=0、summary 仍是 `OK (skipped=N)`。
  ⇒ v3.27.0 P0 已把 11 个反例守卫改成「隔离副本构造失败 ⇒ 可诊断 skip」，
    于是出现一个**新的假绿形态**：
      「11 个反例全部因环境限制被跳过（= 守卫的『能红』属性根本没验证）」
      在体检汇总里**显示为**「✓ 回归测试通过 … test_arch_drift.py=rc=0」。
  ⇒ 排查者会把「反例全跳过」误读成「守卫没问题」⇒ 这正是本文件要锁死的缺陷。

本守卫覆盖（每条判据都有**能红的反例**）：
  T1 正向：marker + `skipped=N` ⇒ 判「通过但有跳过」（不是「真通过」）
  T2 反向对照：只有 marker、没有 `skipped=N` ⇒ **不得**判「未验证」
            （marker 会被受控自测故意触发 ⇒ 单看 marker 是恒真误报）
  T3 反向对照：只有 `skipped=N`、没有 marker ⇒ **不得**判「未验证」
            （与反例无关的 skip，如「外网不可达」「缺 python-pptx」，不该误报）
  T4 失败优先：rc≠0 ⇒ 一律判「失败」，跳过信号**不得**掩盖失败
  T5 漂移锁定：`ensure_settings.ANTIEXAMPLE_SKIP_MARKER` 与
            `test_arch_drift.ANTIEXAMPLE_SKIP_MARKER` **逐字一致**
            （体检侧刻意复制而非 import ⇒ 用测试锁死漂移）
  T6 报告分级：真通过 / 有跳过 / 失败 三态的**报告文案**各不相同且都自证
  T7 结论透传：`main()` 的结论区在「有未验证项」时**不得**写「✅ 全部通过」
            （守卫 `REGRESSION_UNVERIFIED` 被填充却不被读取这一死代码形态）

为何不会假阳性：
  ① 本文件只测**纯函数**（`count_suite_skips` / `has_env_skip` /
     `analyze_suite_output` / `format_regression_report`）⇒ 不起子进程、
     不碰文件系统、不依赖宿主 broker ⇒ 判据本身不受环境干扰；
  ② 所有输入都是**构造的**输出样本（stdout/stderr 字符串）⇒ 与真实回归无关；
  ③ T5 用「逐字相等」而非「包含」⇒ marker 改一个字即判红（防漂移）；
  ④ T7 用**静态读源码 + 结构断言**（不执行 main()）⇒ 不引入真实体检副作用。

用法：
    python3 -m pytest scripts/test_regression_skip_report.py -q
    python3 scripts/test_regression_skip_report.py          # 体检第 7 项按此方式跑
退出码：0 通过 / 1 失败（unittest 语义）
"""

import ast
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

# ⚠ 用 importlib 按**文件路径**加载，避免 `import ensure_settings` 触发其
#   顶层副作用（该模块在 import 期会做路径推导；虽无 I/O，但保持隔离）。
import importlib.util


def _load_module(name: str, path: Path):
    """按文件路径加载模块（不污染 sys.modules 的常规导入路径）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ES_PATH = HERE / "ensure_settings.py"
_TAD_PATH = HERE / "test_arch_drift.py"

#: 构造用的 marker 文本（**故意不 import** ensure_settings —— 免得两处
#: 一旦漂移，测试自己跟着漂移就发现不了 ⇒ T5 才是真正的漂移锁）。
_CANONICAL_MARKER = "[WARN][vet-med-ppt-team] 反例批次因环境限制被跳过"


class _SkipSemanticsBase(unittest.TestCase):
    """共用夹具：加载 ensure_settings（被测模块）。"""

    @classmethod
    def setUpClass(cls):
        if not _ES_PATH.exists():
            raise unittest.SkipTest(f"缺 {_ES_PATH.name}（局部树）")
        cls.es = _load_module("v327_ensure_settings_under_test", _ES_PATH)


class TestSkipDetection(_SkipSemanticsBase):
    """T1–T4：跳过信号的三态判定。"""

    def test_t1_positive_marker_and_skipped_count(self):
        """T1 正向：marker + `skipped=N` ⇒ 判「通过但有跳过」。

        这是本守卫存在的**核心判据**：反例批次因环境限制被跳过时，
        体检**必须**把它从「真通过」里摘出来 ⇒ 否则「未验」会显示成「已验」。
        """
        stdout = f"{_CANONICAL_MARKER}：隔离副本构造失败（环境限制）\n"
        stderr = "----------------------------------------------------------------------\nRan 40 tests in 58.5s\n\nOK (skipped=11)\n"
        status, detail = self.es.analyze_suite_output("test_arch_drift.py", 0, stdout, stderr)
        self.assertEqual(
            status, self.es.REG_PASS_WITH_SKIPS,
            f"marker+skipped=N 必须判「通过但有跳过」，实得 {status!r}")
        self.assertTrue(detail["marker_hit"], "detail 必须记录 marker 命中")
        self.assertEqual(detail["skipped_cases"], 11, "必须读出跳过的用例数")

    def test_t2_marker_only_is_not_a_verdict(self):
        """T2 反向对照：只有 marker、无 `skipped=N` ⇒ **不得**判「未验证」。

        为何必须这样：`test_arch_drift.py::TestAntiExampleSkipSemantics`
        是**受控自测**，它故意触发「环境限制 ⇒ skip」分支来证明跳过语义没坏，
        每次运行都会往 stdout 打**同一个 marker**（实测：健康环境下 2 处）。
        ⇒ 若只认 marker，每次体检都误报「反例未验证」⇒ 那是另一种假绿。
        """
        stdout = f"{_CANONICAL_MARKER}：受控自测故意触发\n"
        stderr = "Ran 40 tests in 58.5s\n\nOK\n"          # ← 无 skipped=
        status, _ = self.es.analyze_suite_output("test_arch_drift.py", 0, stdout, stderr)
        self.assertEqual(
            status, self.es.REG_PASS,
            f"仅 marker（无 skipped=N）不得判「未验证」，实得 {status!r}")

    def test_t3_skipped_without_marker_is_not_a_verdict(self):
        """T3 反向对照：只有 `skipped=N`、无 marker ⇒ **不得**判「未验证」。

        与反例无关的 skip 是常态：`test_three_source_online.py`（外网不可达）、
        `test_ooxml_lint.py`（缺 python-pptx）等 ⇒ 若把它们误报成
        「反例未验证」，告警会泛滥 ⇒ 告警疲劳 ⇒ 真告警失效。
        """
        stdout = ""
        stderr = "Ran 3 tests in 1.2s\n\nOK (skipped=2)\n"
        status, _ = self.es.analyze_suite_output("test_three_source_online.py", 0, stdout, stderr)
        self.assertEqual(
            status, self.es.REG_PASS,
            f"仅 skipped=N（无 marker）不得判「未验证」，实得 {status!r}")

    def test_t4_failure_takes_precedence_over_skips(self):
        """T4 失败优先：rc≠0 ⇒ 一律判「失败」，跳过信号不得掩盖失败。

        反例：套件既失败又跳过 ⇒ 若「有跳过」优先，就会把**真实失败**
        降级成「⚠ 未验证」⇒ 失败被洗白 ⇒ 比假绿更危险。
        """
        stdout = f"{_CANONICAL_MARKER}：环境限制\n"
        stderr = "Ran 40 tests in 58.5s\n\nFAILED (failures=2, skipped=11)\n"
        status, _ = self.es.analyze_suite_output("test_arch_drift.py", 1, stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"rc≠0 必须判失败（跳过信号不得掩盖），实得 {status!r}")


class TestReportGrading(_SkipSemanticsBase):
    """T6：报告分级文案。"""

    def test_t6_three_states_have_distinct_report_lines(self):
        """T6：三态的**报告文案**必须各不相同，且各自自证。

        · 真通过 ⇒ 「✓ 回归测试通过」
        · 有跳过 ⇒ 「⚠ 回归测试通过但有 N 个套件因环境限制跳过」+ 明写「未验 ≠ 已验」
        · 失败   ⇒ 「🔴 回归测试失败」
        """
        # ① 真通过
        lines, rc = self.es.format_regression_report(
            [("test_a.py", self.es.REG_PASS, {"text": "rc=0", "skipped_cases": 0})], 1)
        self.assertEqual(rc, 0, "真通过不阻断")
        self.assertTrue(any("✓" in ln for ln in lines), f"真通过应打 ✓，实得 {lines}")

        # ② 有跳过
        detail = {"text": "rc=0 / 检出跳过", "skipped_cases": 11, "anti_skips": 11,
                  "marker_hit": True}
        lines, rc = self.es.format_regression_report(
            [("test_arch_drift.py", self.es.REG_PASS_WITH_SKIPS, detail)], 1)
        self.assertTrue(any("⚠" in ln for ln in lines), f"有跳过应打 ⚠，实得 {lines}")
        #: ⚠ 同样咬住完整标识「未验证」/「未验 ≠ 已验」，
        #:   避免宽匹配（`"未验" in ln` 会被警示语里的半句蒙混过关）。
        self.assertTrue(
            any("未验证" in ln for ln in lines),
            f"有跳过必须明写「未验证」，实得 {lines}")

        # ③ 失败
        lines, rc = self.es.format_regression_report(
            [("test_b.py", self.es.REG_FAIL, {"text": "rc=1", "fail_tail": "boom",
                                               "skipped_cases": 0})], 1)
        self.assertEqual(rc, 1, "失败必须阻断")
        self.assertTrue(any("🔴" in ln for ln in lines), f"失败应打 🔴，实得 {lines}")


class TestMarkerDriftLock(_SkipSemanticsBase):
    """T5：marker 字面量漂移锁。"""

    def test_t5_marker_literals_identical_in_both_files(self):
        """T5：`ensure_settings` 与 `test_arch_drift` 的 marker 必须**逐字一致**。

        为何要锁：体检侧**刻意复制** marker 常量而非 `import`（import 该测试模块
        会把整个测试模块拉进体检进程 —— 重 + 有副作用）。
        ⇒ 复制的代价就是**漂移风险** ⇒ 必须用测试锁死。
        ⚠ 本断言刻意**不 import** test_arch_drift（避免两处一起漂移时
          测试跟着漂移、发现不了）⇒ 直接读源码里的字面量。
        """
        def _literal_from(path: Path, var: str) -> str:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == var:
                            val = node.value
                            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                                return val.value
            self.fail(f"{path.name} 里找不到 {var} 的字符串字面量赋值")

        if not _TAD_PATH.exists():
            self.skipTest(f"缺 {_TAD_PATH.name}（局部树）")
        a = _literal_from(_ES_PATH, "ANTIEXAMPLE_SKIP_MARKER")
        b = _literal_from(_TAD_PATH, "ANTIEXAMPLE_SKIP_MARKER")
        self.assertEqual(
            a, b,
            "两处 marker 字面量必须逐字一致（体检侧为避免副作用刻意复制，"
            "漂移风险由本测试锁死）")
        self.assertEqual(
            a, _CANONICAL_MARKER,
            "marker 字面量必须与本文件内的基准常量一致（防止两处同时漂移）")


class TestConclusionTransparency(_SkipSemanticsBase):
    """T7：`main()` 结论区必须把「未验证」透传到结论。"""

    def test_t7_conclusion_downgrades_when_unverified_exists(self):
        """T7a（**执行真实纯函数**）：有未验证项 ⇒ 结论**不得**写「✅ 全部通过」。

        v3.27.0 实测：`check_regression()` 填充了 `REGRESSION_UNVERIFIED`，
        而 `main()` 的结论区只读 `rc` ⇒ 即便第 7 项打了「⚠ 有跳过」，
        最终结论仍写「✅ 全部通过，可发布」⇒ **未验被显示成已验**。

        ⚠ 为何必须**执行**而不是静态扫描源码：本轮首版判据用 AST 查
          「main() 里有没有出现 `REGRESSION_UNVERIFIED` 这个名字」，
          实测**反向对照失败** —— 把 `REGRESSION_UNVERIFIED.get("suites")`
          改成 `[]`、而 `.get("cases")` 那行仍引用着它 ⇒ 静态检查照样通过
          ⇒ 变异后 8 passed，判据没抓住 ⇒ **判据红了假绿**。
          ⇒ 故把结论渲染抽成纯函数 `format_final_conclusion()`，此处直接调用。
        """
        unverified = {"suites": ["test_arch_drift.py"], "cases": 11}
        lines = self.es.format_final_conclusion(0, unverified)
        blob = "\n".join(lines)
        self.assertNotIn(
            "✅ 全部通过", blob,
            f"有未验证项时结论不得写「✅ 全部通过」（未验≠已验），实得：{blob}")
        #: ⚠ 断言必须咬住**具体标识**「未验证项」——
        #:   首版写的是 `"未验证" in ln or "未验" in ln` ⇒ 太宽：
        #:   结论里「**未验 ≠ 已验**」那句含「未验」⇒ 把「未验证项」改成
        #:   「存在告警」后断言**照样通过** ⇒ 实测该变异（M4）**没红** ⇒ 假绿。
        #:   ⇒ 改为必须出现「未验证项」这一完整标识。
        self.assertTrue(
            any("未验证项" in ln for ln in lines),
            f"结论必须显式写「未验证项」（完整标识），实得：{blob}")
        self.assertTrue(
            any("test_arch_drift.py" in ln for ln in lines),
            f"结论必须点名未验证的套件（可定位），实得：{blob}")
        #: ⚠ 还须锁住「未验 ≠ 已验」这半句（它是给排查者看的**警示语**）：
        #:   删掉它 ⇒ 结论只剩「存在未验证项」⇒ 读者可能当成普通告警跳过。
        self.assertTrue(
            any("未验 ≠ 已验" in ln or "未验≠已验" in ln for ln in lines),
            f"结论必须保留「未验 ≠ 已验」警示语，实得：{blob}")

    def test_t7b_clean_run_keeps_success_wording(self):
        """T7b（反向对照）：**无**未验证项 ⇒ 仍写「✅ 全部通过」（不误伤成功路径）。

        防的是另一个方向的假红：把结论**永远**降级成 ⚠，那也是错的
        （真全绿就该说真全绿）⇒ 判据必须同时锁住两端。
        """
        lines = self.es.format_final_conclusion(0, {"suites": [], "cases": 0})
        blob = "\n".join(lines)
        self.assertIn("✅ 全部通过", blob, f"真全绿必须写「✅ 全部通过」，实得：{blob}")
        self.assertNotIn("未验证", blob, f"真全绿不该提「未验证」，实得：{blob}")

    def test_t7c_rc_nonzero_keeps_alert_wording(self):
        """T7c（反向对照）：rc≠0 ⇒ 结论写「⚠️ 存在告警」（沿用 v3.26.0 语义）。"""
        lines = self.es.format_final_conclusion(1, {"suites": [], "cases": 0})
        blob = "\n".join(lines)
        self.assertIn("存在告警", blob, f"rc≠0 必须写告警结论，实得：{blob}")
        self.assertNotIn("✅ 全部通过", blob, f"rc≠0 不得写「全部通过」，实得：{blob}")

    def test_t7d_main_is_wired_to_the_pure_function(self):
        """T7d（接线检查）：`main()` 必须**调用** `format_final_conclusion()`。

        ⚠ 这一条是**静态**检查，故只断言「调用存在」这一件事实，
          **不**用它来证明结论内容正确（内容由 T7a 执行验证）⇒
          避免重蹈「静态检查假绿」的覆辙。
        """
        src = _ES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        main_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                main_fn = node
                break
        self.assertIsNotNone(main_fn, "ensure_settings.py 里找不到 main()")
        called = set()
        for node in ast.walk(main_fn):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        self.assertIn(
            "format_final_conclusion", called,
            "main() 必须调用 format_final_conclusion() —— 否则结论渲染"
            "与被测函数脱钩，改纯函数不会影响真实结论（接线断裂）")
        #: 接线必须把累加器**传进去**（不是传空 dict）
        args_ok = False
        for node in ast.walk(main_fn):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "format_final_conclusion"):
                if any(isinstance(a, ast.Name) and a.id == "REGRESSION_UNVERIFIED"
                       for a in node.args):
                    args_ok = True
        self.assertTrue(
            args_ok,
            "main() 调用 format_final_conclusion() 时必须把 REGRESSION_UNVERIFIED "
            "作为实参传入 —— 传空 dict 会让结论永远看不到未验项")


class TestAntiExampleGuardCanStillFail(_SkipSemanticsBase):
    """反向对照：跳过机制**不得**把守卫的「能红」属性废掉。"""

    def test_reverse_skips_do_not_hide_real_failures(self):
        """反向对照：即使同一次输出里既有 marker 又有 skipped=N，rc≠0 仍判失败。

        （与 T4 呼应，但走**汇总层** `format_regression_report` ⇒
          覆盖「失败套件不会因为同批另有跳过套件而被降级」。）
        """
        results = [
            ("test_ok_but_skipped.py", self.es.REG_PASS_WITH_SKIPS,
             {"text": "rc=0 / 检出跳过", "skipped_cases": 11, "marker_hit": True}),
            ("test_hard_fail.py", self.es.REG_FAIL,
             {"text": "rc=1", "fail_tail": "AssertionError", "skipped_cases": 0}),
        ]
        lines, rc = self.es.format_regression_report(results, 2)
        self.assertEqual(rc, 1, "只要有一个硬失败就必须阻断")
        self.assertTrue(any("🔴" in ln for ln in lines),
                        f"硬失败必须以 🔴 呈现（不能被跳过项掩盖），实得 {lines}")


class TestPureFunctionNotInlined(_SkipSemanticsBase):
    """防退化：结论渲染必须留在**纯函数**里（不得内联回 main()）。"""

    def test_final_conclusion_renderer_is_module_level_function(self):
        """`format_final_conclusion` 必须是模块级函数（可被单测直接调用）。

        ⚠ 为何这条重要：本守卫的价值全部建立在「结论渲染是纯函数」之上 ——
          若有人把渲染逻辑内联回 `main()`，纯函数会退化成空壳，
          T7a 执行验证就会**测一个没人用的函数** ⇒ 假绿。
          ⇒ 故显式锁住「模块级 + 被 main() 调用」（后者由 T7d 覆盖）。
        """
        self.assertTrue(
            hasattr(self.es, "format_final_conclusion"),
            "ensure_settings.py 缺少模块级 format_final_conclusion()")
        fn = self.es.format_final_conclusion
        self.assertTrue(callable(fn), "format_final_conclusion 必须可调用")
        #: 纯函数性：同输入必须同输出（无隐藏状态）
        a = self.es.format_final_conclusion(0, {"suites": ["x.py"], "cases": 3})
        b = self.es.format_final_conclusion(0, {"suites": ["x.py"], "cases": 3})
        self.assertEqual(a, b, "结论渲染必须是纯函数（同输入同输出）")


if __name__ == "__main__":
    unittest.main()

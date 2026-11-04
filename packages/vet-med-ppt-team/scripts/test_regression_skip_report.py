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

═══════════════════════════════════════════════════════════════════════════
R18（v3.28.8）新增覆盖：体检失败语义分离 ——「真缺陷失败」vs「宿主环境受限失败」
═══════════════════════════════════════════════════════════════════════════
背景（真实缺陷，非假设）：
  体检第 7 项此前把「套件因**宿主 broker 拦 mkdir** 而报错」与
  「套件**真检出缺陷**」**一律**判 `REG_FAIL`
  ⇒ 真环境噪声伪装成生产缺陷，掩盖真实告警。
  ⇒ R18 用**三重合取**把两类分开：真缺陷仍阻断；
    环境受限**不阻断但必须进未验证累加器**（否则结论区假绿）。

  T-R18-1  正向：PermissionError + broker + `FAILED (errors=N)` ⇒ 环境受限
  T-R18-2  `FAILED (failures=N)`（断言失败）⇒ **真缺陷** ⇒ 硬红
  T-R18-3  PermissionError 但**无 broker 特征** ⇒ **真权限缺陷** ⇒ 硬红
  T-R18-4  BlockingIOError + `Resource temporarily unavailable` 变体 ⇒ 环境受限
  T-R18-5  AttributeError（代码 bug）⇒ 硬红（条件①的闸门）
  T-R18-6  正文含 `AssertionError` ⇒ 硬红（条件③的两道闸之一）
  T-R18-7  rc=0 + 跳过信号 ⇒ 仍是「通过但有跳过」（**不得**被误判成环境受限）
  T-R18-8  rc=0 + 无信号 ⇒ 真通过（新逻辑不得误伤成功路径）
  T-R18-9  仅环境受限 ⇒ 报告 **rc=0**（不阻断）+ ⚠ 可见 + 明写「未验证」
  T-R18-10 环境受限混真缺陷 ⇒ 报告 **rc=1**（真缺陷不得被顺带洗白）
  V4 断言   环境受限套件**必须**进未验证累加器（成对判据：不假绿）
  V5 断言   **反向对照**：改坏三重合取任一条件 ⇒ 断言必须翻红

为何不会假阳性：
  ① 本文件只测**纯函数**（`count_suite_skips` / `has_env_skip` /
     `analyze_suite_output` / `format_regression_report` / `collect_unverified`）
     ⇒ 不起子进程、不碰文件系统、不依赖宿主 broker ⇒ 判据本身不受环境干扰；
  ② 所有输入都是**构造的**输出样本（stdout/stderr 字符串）⇒ 与真实回归无关；
  ③ T5 用「逐字相等」而非「包含」⇒ marker 改一个字即判红（防漂移）；
  ④ T7 用**静态读源码 + 结构断言**（不执行 main()）⇒ 不引入真实体检副作用；
  ⑤ **R18 的三重合取词表是模块级常量** ⇒ 反向对照只需覆写属性即可制造
     「判据恒假」⇒ 对照是**真对照**（改源码才能改坏的判据，不是摆设）。

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


class TestEnvLimitedFailureSemantics(_SkipSemanticsBase):
    """T-R18-1 ~ T-R18-10：R18「真缺陷失败」vs「宿主环境受限失败」的语义分离。

    背景（真实缺陷）：体检第 7 项此前把「套件因宿主 broker 拦 mkdir 而报错」
    与「套件**真检出缺陷**」**一律**判 `REG_FAIL`
    ⇒ 真环境噪声伪装成生产缺陷，掩盖真实告警。
    ⇒ R18 用**三重合取**把两类分开：真缺陷仍阻断；环境受限**不阻断但计入未验证**。
    """

    # ── 构造用的**真实形态**输出样本（贴近宿主 broker 实际拦截时的文本）────
    #: 环境类样本：PermissionError + broker 特征 + `FAILED (errors=N)` 摘要。
    _ENV_STDOUT = (
        "Traceback (most recent call last):\n"
        "  File \"scripts/test_arch_drift.py\", line 42, in _make_isolated_copy\n"
        "    os.makedirs(dest)\n"
        "PermissionError: [Errno 13] Permission denied: '/tmp/vet-sandbox'\n"
        "  raised by brokered-sandbox-bash-env.sh\n"
    )
    _ENV_STDERR = (
        "----------------------------------------------------------------------\n"
        "Ran 40 tests in 12.3s\n\n"
        "FAILED (errors=3)\n"
    )

    def _analyze(self, stdout, stderr, rc=1):
        return self.es.analyze_suite_output("test_arch_drift.py", rc, stdout, stderr)

    # ── T-R18-1：正常环境类 ⇒ REG_ENV_LIMITED ────────────────────────────
    def test_tr18_1_env_limited_positive(self):
        """T-R18-1 正向：PermissionError + broker + `FAILED (errors=N)` ⇒ 环境受限。

        这是 R18 的**核心判据**：真环境噪声不得被当成生产缺陷 ⇒ 降级为
        `REG_ENV_LIMITED`（不阻断，但计入未验证）。
        """
        status, detail = self._analyze(self._ENV_STDOUT, self._ENV_STDERR)
        self.assertEqual(
            status, self.es.REG_ENV_LIMITED,
            f"PermissionError+broker+errors= 必须判「宿主环境受限」，实得 {status!r}")
        self.assertTrue(detail["env_limited"], "detail 必须记录 env_limited=True")
        self.assertEqual(detail["env_limited_cases"], 3,
                         "受影响用例数须从 `errors=3` 读出")
        #: ⚠ 文案**不得**写「通过」（那会把未验证显示成已验）
        self.assertNotIn("通过", detail["text"],
                         f"环境类文案不得写「通过」，实得：{detail['text']}")
        self.assertIn("环境受限", detail["text"],
                      f"环境类文案须明写「环境受限」，实得：{detail['text']}")

    # ── T-R18-2：断言失败（failures=）⇒ 真缺陷 ⇒ REG_FAIL ─────────────────
    def test_tr18_2_assertion_failure_is_real_defect(self):
        """T-R18-2：`FAILED (failures=1)` ⇒ **真缺陷** ⇒ 硬红 REG_FAIL。

        ⚠ unittest 两种失败摘要形态含义完全不同：
          `FAILED (failures=N)` = 断言失败 = **真缺陷**；
          `FAILED (errors=N)`   = 异常抛出（才可能是环境类）。
        ⇒ 断言失败**绝不能**被环境理由掩盖（条件③）。
        """
        stdout = self._ENV_STDOUT.replace(
            "PermissionError: [Errno 13] Permission denied: '/tmp/vet-sandbox'",
            "AssertionError: 3 != 4")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 40 tests in 12.3s\n\n"
                  "FAILED (failures=1)\n")
        status, _ = self._analyze(stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"断言失败是真缺陷必须硬红（不得被 broker 特征洗白），实得 {status!r}")

    # ── T-R18-3：无 broker 特征的真权限缺陷 ⇒ REG_FAIL ───────────────────
    def test_tr18_3_permission_without_broker_is_real_defect(self):
        """T-R18-3：PermissionError 但**无 broker 特征** ⇒ **真权限缺陷** ⇒ REG_FAIL。

        ⚠ 这是条件②的作用：只看异常类型 ⇒ 任何权限问题都算环境问题
        ⇒ 包内某个测试写错路径/权限被改的真实缺陷会被洗白成「未验证」。
        """
        stdout = ("Traceback (most recent call last):\n"
                  "  File \"scripts/test_x.py\", line 10, in _w\n"
                  "    open('/etc/some/conf', 'w')\n"
                  "PermissionError: [Errno 13] Permission denied: '/etc/some/conf'\n")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 40 tests in 12.3s\n\n"
                  "FAILED (errors=1)\n")
        status, _ = self._analyze(stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"无 broker 特征的权限缺陷必须判失败（真缺陷），实得 {status!r}")

    # ── T-R18-4：BlockingIOError 变体 ⇒ REG_ENV_LIMITED ─────────────────
    def test_tr18_4_blocking_io_error_variant(self):
        """T-R18-4：`BlockingIOError` + `Resource temporarily unavailable` ⇒ 环境受限。

        覆盖 errno 11 变体（与 errno 13 Permission denied 是**不同**的失败面：
        文件锁 / 临时资源争用），两者都要能被环境类识别。
        """
        stdout = ("Traceback (most recent call last):\n"
                  "  File \"scripts/test_y.py\", line 7, in _r\n"
                  "    os.rename(tmp, dest)\n"
                  "BlockingIOError: [Errno 11] Resource temporarily unavailable: '/tmp/x'\n"
                  "  broker: sandbox-bash wrapper denied the operation\n")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 12 tests in 3.1s\n\n"
                  "FAILED (errors=1)\n")
        status, detail = self._analyze(stdout, stderr)
        self.assertEqual(
            status, self.es.REG_ENV_LIMITED,
            f"BlockingIOError 变体必须判「宿主环境受限」，实得 {status!r}")
        self.assertEqual(detail["env_limited_cases"], 1, "受影响用例数应为 1")

    # ── T-R18-5：AttributeError（代码 bug）⇒ REG_FAIL ─────────────────────
    def test_tr18_5_attribute_error_is_code_bug(self):
        """T-R18-5：`AttributeError` + broker 特征 ⇒ **代码 bug** ⇒ REG_FAIL。

        ⚠ 这是**反向陷阱**：`errors=N` 也可能是代码 bug（如属性名写错）⇒
        条件①（异常类型必须 ∈ PermissionError/BlockingIOError）就是闸门。
        """
        stdout = ("Traceback (most recent call last):\n"
                  "  File \"scripts/test_z.py\", line 99, in _run\n"
                  "    self.assertions.append(r)\n"
                  "AttributeError: 'NoneType' object has no attribute 'append'\n"
                  "  brokered-sandbox-bash-env.sh\n")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 12 tests in 3.1s\n\n"
                  "FAILED (errors=1)\n")
        status, _ = self._analyze(stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"AttributeError 是代码 bug 不得算环境类，实得 {status!r}")

    # ── T-R18-6：AssertionError 出现在正文 ⇒ REG_FAIL ───────────────────
    def test_tr18_6_assertion_error_in_body_is_real_defect(self):
        """T-R18-6：正文含 `AssertionError`（即便摘要无 `failures=`）⇒ REG_FAIL。

        ⚠ 条件③ 的**两道闸**都要在：`AssertionError` 与 `failures=` 任一命中即否决。
        此用例专门覆盖「traceback 正文里出现 AssertionError 但摘要形态异常」
        的情形（自定义 runner / 输出被截断）。
        """
        stdout = ("Traceback (most recent call last):\n"
                  "  File \"scripts/test_w.py\", line 5, in _t\n"
                  "    self.assertEqual(a, b)\n"
                  "AssertionError: 'x' != 'y'\n"
                  "  brokered-sandbox-bash-env.sh\n")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 12 tests in 3.1s\n\n"
                  "FAILED (errors=1)\n")
        status, _ = self._analyze(stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"AssertionError 出现即否决环境类，实得 {status!r}")

    # ── T-R18-7：rc=0 + 环境 skip 信号 ⇒ 不得被误判成 env_limited ────────
    def test_tr18_7_rc_zero_skip_not_env_limited(self):
        """T-R18-7：rc=0 + marker + `skipped=N` ⇒ 仍是 `REG_PASS_WITH_SKIPS`。

        ⚠ 防的是**误伤**：`REG_ENV_LIMITED` 是 rc≠0 才可能的状态
        ⇒ rc=0 的跳过路径**不得**被新逻辑改判（否则「跳过」与「环境受限」
        两类语义被搅乱，报告文案会自相矛盾）。
        """
        stdout = f"{_CANONICAL_MARKER}：隔离副本构造失败（环境限制）\n"
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 40 tests in 58.5s\n\n"
                  "OK (skipped=11)\n")
        status, detail = self._analyze(stdout, stderr, rc=0)
        self.assertEqual(
            status, self.es.REG_PASS_WITH_SKIPS,
            f"rc=0 的跳过路径不得被改判为 env_limited，实得 {status!r}")
        self.assertFalse(detail["env_limited"], "rc=0 不得标记 env_limited")

    # ── T-R18-8：rc=0 + 无任何信号 ⇒ REG_PASS ────────────────────────────
    def test_tr18_8_rc_zero_clean_is_pass(self):
        """T-R18-8：rc=0 + 无信号 ⇒ `REG_PASS`（新逻辑不得误伤成功路径）。"""
        status, detail = self._analyze("", "Ran 5 tests in 0.4s\n\nOK\n", rc=0)
        self.assertEqual(
            status, self.es.REG_PASS,
            f"rc=0 且无信号必须判真通过，实得 {status!r}")
        self.assertFalse(detail["env_limited"], "真通过不得标记 env_limited")

    # ── T-R18-9：报告层：仅 env_limited ⇒ 不阻断（rc=0）──────────────────
    def test_tr18_9_env_limited_report_does_not_block(self):
        """T-R18-9：`format_regression_report([(env_limited)])` ⇒ **rc=0**（不阻断）。

        ⚠ 这是 R18 的**核心交付语义**：环境噪声不阻断发布（否则体检恒红 ⇒
        用户学会忽略体检 ⇒ 后续真告警全部失效）。
        ⚠ 但**必须同时**可见（⚠ 行 + 明写「未验证」）⇒ 不是「假装没事」。
        """
        detail = {"text": "rc=1 / 判定为宿主环境受限（PermissionError + broker），"
                          "未计入阻断",
                  "skipped_cases": 0, "env_limited": True,
                  "env_limited_cases": 3, "fail_tail": "rc=1"}
        lines, rc = self.es.format_regression_report(
            [("test_arch_drift.py", self.es.REG_ENV_LIMITED, detail)], 1)
        self.assertEqual(rc, 0, "环境受限**不阻断**（rc 必须为 0）")
        self.assertFalse(any("🔴" in ln for ln in lines),
                         f"环境受限不得以 🔴 呈现（那会被算成阻断），实得 {lines}")
        self.assertTrue(any("⚠" in ln for ln in lines),
                        f"环境受限必须以 ⚠ 呈现（可见性），实得 {lines}")
        #: ⚠ 必须明写「未验证」——不写就等于让用户以为已验（假绿）
        self.assertTrue(any("未验证" in ln for ln in lines),
                        f"环境受限必须明写「未验证」，实得 {lines}")
        #: ⚠ **不得**进 failed 列表（失败列表的语义 = 阻断）
        self.assertFalse(any("回归测试失败" in ln for ln in lines),
                         f"环境受限不得进失败分支，实得 {lines}")

    # ── T-R18-10：报告层：env_limited 混 REG_FAIL ⇒ rc=1（真缺陷仍阻断）──
    def test_tr18_10_mixed_env_limited_and_real_fail_blocks(self):
        """T-R18-10：`REG_ENV_LIMITED` + `REG_FAIL` 混合 ⇒ **rc=1**（真缺陷仍阻断）。

        ⚠ 这是 R18 的**另一半交付语义**：降级只对**环境类**生效
        ⇒ 真缺陷**绝不能**被环境类同伴"顺带洗白"（那比假绿更危险）。
        """
        results = [
            ("test_env_broker.py", self.es.REG_ENV_LIMITED,
             {"text": "rc=1 / 判定为宿主环境受限", "skipped_cases": 0,
              "env_limited": True, "env_limited_cases": 2, "fail_tail": "rc=1"}),
            ("test_real_defect.py", self.es.REG_FAIL,
             {"text": "rc=1", "fail_tail": "AssertionError", "skipped_cases": 0}),
        ]
        lines, rc = self.es.format_regression_report(results, 2)
        self.assertEqual(rc, 1, "真缺陷存在时必须阻断（环境类不得顺带洗白）")
        self.assertTrue(any("🔴" in ln for ln in lines),
                        f"真缺陷必须以 🔴 呈现，实得 {lines}")


class TestEnvLimitedAccumulator(_SkipSemanticsBase):
    """R18 验收判据 V4（不假绿）：环境受限套件必须进未验证累加器。"""

    def test_tr18_v4_env_limited_enters_unverified_accumulator(self):
        """V4：环境受限套件必须出现在 `collect_unverified()` 的结果里。

        ⚠ **成对判据**：只验「不阻断」（T-R18-9）而漏「不假绿」（本条）
        ⇒ 会出现「环境受限 ⇒ rc=0 且结论写着『✅ 全部通过』」的假绿形态
        ⇒ 那比假红更危险（用户以为没问题）。
        ⚠ **执行真实纯函数** `collect_unverified()`（不是 AST 静态检查）——
          本包 v3.27.0 实测：静态检查曾**反向对照失败**（判据红了假绿）。
        """
        results = [
            ("test_env_broker.py", self.es.REG_ENV_LIMITED,
             {"text": "rc=1 / 宿主环境受限", "skipped_cases": 0,
              "env_limited": True, "env_limited_cases": 2}),
            ("test_ok.py", self.es.REG_PASS,
             {"text": "rc=0", "skipped_cases": 0}),
        ]
        suites, cases = self.es.collect_unverified(results)
        self.assertIn(
            "test_env_broker.py", suites,
            "环境受限套件必须进未验证累加器（否则结论区假绿）")
        self.assertEqual(cases, 2, "受影响用例数须计入累加器")

    def test_tr18_v4_real_fail_not_in_unverified(self):
        """V4 反向对照：`REG_FAIL` **不得**进未验证累加器。

        ⚠ 真缺陷是「**已验证的失败**」，不是「未验证」⇒ 混进去会稀释
        未验证信号（让结论区的告警语义变模糊）。
        """
        results = [
            ("test_real_defect.py", self.es.REG_FAIL,
             {"text": "rc=1", "fail_tail": "AssertionError", "skipped_cases": 0}),
        ]
        suites, cases = self.es.collect_unverified(results)
        self.assertEqual(suites, [], "真缺陷不得进未验证累加器")
        self.assertEqual(cases, 0, "真缺陷不得贡献未验证用例数")

    def test_tr18_v4_conclusion_not_green_with_env_limited(self):
        """V4 连带：环境受限存在时，结论**不得**写「✅ 全部通过」。

        ⚠ 这是「假绿」的**最终形态**：体检第 7 项打了 ⚠，但总结论说全通过
        ⇒ 用户只读结论 ⇒ 误以为守卫有效。
        """
        unverified = {"suites": ["test_env_broker.py"], "cases": 2}
        lines = self.es.format_final_conclusion(0, unverified)
        blob = "\n".join(lines)
        self.assertNotIn("✅ 全部通过", blob,
                         f"有未验证项时结论不得写「✅ 全部通过」，实得：{blob}")
        self.assertTrue(any("未验证项" in ln for ln in lines),
                        f"结论必须写「未验证项」，实得：{blob}")
        self.assertTrue(any("test_env_broker.py" in ln for ln in lines),
                        f"结论必须点名未验证的套件，实得：{blob}")


class TestEnvLimitedReverseControl(_SkipSemanticsBase):
    """R18 验收判据 V5：反向对照——改坏条件 ⇒ 断言必须翻红。

    ⚠ 本包历史教训（v3.27.0）：用 AST 查「代码里有没有出现某个名字」当判据
      ⇒ 实测**反向对照失败** ⇒ 判据可能是恒真摆设而看不出来。
    ⇒ 本类**真改坏条件**（覆写模块级词表常量）⇒ 断言必须真的翻红。

    ⚠ 为何能覆写：`ENV_LIMITED_BROKER_MARKERS` 等是**模块级元组常量**
      （规格 §八 第 5 项）⇒ 覆写属性即可制造「判据恒假」，
      无需改源码、无需 mock 内部调用 ⇒ 对照是**真对照**。
    """

    def test_tr18_v5_reverse_control_break_broker_condition(self):
        """V5 反向对照：把 broker 特征词表改成**永假** ⇒ T-R18-1 必须翻红。

        ⚠ **实测要求**（不接受「逻辑上应该会翻红」）：
          覆写 ⇒ 断言失败 ⇒ 恢复 ⇒ 断言通过 ⇒ 证明判据**真在读这个条件**。
        """
        original = self.es.ENV_LIMITED_BROKER_MARKERS
        try:
            #: 改坏条件②：broker 特征永假 ⇒ 环境类判不出来 ⇒ 须回退 REG_FAIL
            self.es.ENV_LIMITED_BROKER_MARKERS = ("__never_matches_xyz__",)
            status, _ = self.es.analyze_suite_output(
                "test_arch_drift.py", 1,
                TestEnvLimitedFailureSemantics._ENV_STDOUT,
                TestEnvLimitedFailureSemantics._ENV_STDERR)
            self.assertNotEqual(
                status, self.es.REG_ENV_LIMITED,
                "反向对照失败：broker 特征改坏后仍判 env_limited ⇒ 判据恒真摆设")
            self.assertEqual(
                status, self.es.REG_FAIL,
                f"broker 特征改坏后必须回退 REG_FAIL，实得 {status!r}")
        finally:
            self.es.ENV_LIMITED_BROKER_MARKERS = original
        #: 恢复后必须重新判回环境类（证明对照是**可逆**的，不是残留污染）
        status, _ = self.es.analyze_suite_output(
            "test_arch_drift.py", 1,
            TestEnvLimitedFailureSemantics._ENV_STDOUT,
            TestEnvLimitedFailureSemantics._ENV_STDERR)
        self.assertEqual(
            status, self.es.REG_ENV_LIMITED,
            f"恢复常量后必须重新判回 env_limited（对照可逆），实得 {status!r}")

    def test_tr18_v5_reverse_control_break_exception_condition(self):
        """V5 反向对照②：把异常类型词表改成**永假** ⇒ 必须回退 REG_FAIL。

        ⚠ 锁住条件①（异常类型白名单）——它是挡住「`errors=N` 其实是代码 bug」
          的那道闸（见 T-R18-5）。
        """
        original = self.es.ENV_LIMITED_EXCEPTION_MARKERS
        try:
            self.es.ENV_LIMITED_EXCEPTION_MARKERS = ("__never_matches_xyz__",)
            status, _ = self.es.analyze_suite_output(
                "test_arch_drift.py", 1,
                TestEnvLimitedFailureSemantics._ENV_STDOUT,
                TestEnvLimitedFailureSemantics._ENV_STDERR)
            self.assertEqual(
                status, self.es.REG_FAIL,
                f"异常类型词表改坏后必须回退 REG_FAIL，实得 {status!r}")
        finally:
            self.es.ENV_LIMITED_EXCEPTION_MARKERS = original

    def test_tr18_v5_reverse_control_break_false_defect_condition(self):
        """V5 反向对照③：把「真缺陷信号」词表改成**永假** ⇒ `failures=` 也会判环境类。

        ⚠ 锁住条件③：若它失效，断言失败（`failures=1`）会被洗白成「环境受限」
          ⇒ 真缺陷被降级 ⇒ **比假红更危险**。
        ⚠ 本对照的**期望结果是危险态**（能判成 env_limited）
          —— 正说明条件③ 在正常态下确实在起作用。

        ⚠ **样本必须同时含三要素**（PermissionError + broker + AssertionError/
          `failures=`）⇒ 否则改坏条件③ 时会**先**被条件①/②挡掉
          ⇒ 对照就测不到条件③ 本身（首版实况：替换掉 PermissionError 行
          ⇒ 条件① 先失败 ⇒ 对照失真 ⇒ 已修正为「三要素并存」的样本）。
        """
        #: 三要素并存的样本：同一批输出里既有环境异常、又有断言失败
        stdout = ("Traceback (most recent call last):\n"
                  "  File \"scripts/test_mix.py\", line 5, in _t\n"
                  "    os.makedirs(dest)\n"
                  "PermissionError: [Errno 13] Permission denied: '/tmp/vet-sandbox'\n"
                  "  raised by brokered-sandbox-bash-env.sh\n"
                  "Traceback (most recent call last):\n"
                  "  File \"scripts/test_mix.py\", line 9, in _t2\n"
                  "    self.assertEqual(a, b)\n"
                  "AssertionError: 3 != 4\n")
        stderr = ("----------------------------------------------------------------------\n"
                  "Ran 40 tests in 12.3s\n\n"
                  "FAILED (failures=1)\n")
        original = self.es.ENV_LIMITED_FALSE_DEFECT_MARKERS
        try:
            self.es.ENV_LIMITED_FALSE_DEFECT_MARKERS = ("__never_matches_xyz__",)
            status, _ = self.es.analyze_suite_output(
                "test_mix.py", 1, stdout, stderr)
            self.assertEqual(
                status, self.es.REG_ENV_LIMITED,
                "条件③ 失效后断言失败会被洗白成环境类（= 对照命中危险态）")
        finally:
            self.es.ENV_LIMITED_FALSE_DEFECT_MARKERS = original
        #: 恢复后必须重新判回 REG_FAIL（证明对照可逆，且条件③ 真的在起作用）
        status, _ = self.es.analyze_suite_output(
            "test_mix.py", 1, stdout, stderr)
        self.assertEqual(
            status, self.es.REG_FAIL,
            f"恢复后断言失败必须重新判 REG_FAIL（条件③ 真的在起作用），实得 {status!r}")


# ══════════════════════════════════════════════════════════════════════════
# R18-续（v3.28.8）：超时第三类状态 `REG_TIMEOUT`
# ══════════════════════════════════════════════════════════════════════════
# 背景（真实缺陷，非假设）：
#   体检第 7 项此前把「套件超时」**判成 `REG_FAIL`**（阻断、🔴）
#   ⇒ 假红：超时的真因通常是「套件太慢 / 阈值不够」，**不是包缺陷**
#   ⇒ 拿它阻断发布属误伤，且会让体检恒红 ⇒ 用户学会忽略体检输出。
#   ⇒ 但也**不能**判成 `REG_PASS`（压根没跑完，写「通过」是硬造假）
#   ⇒ 也不能判成 `REG_ENV_LIMITED`（把「套件太慢」误归因成「环境不允许」）
#   ⇒ 故新增第五态 `REG_TIMEOUT`：**不阻断，但必须进未验证累加器**。
#
#   T-R18-11 正向：超时 ⇒ 判 `REG_TIMEOUT`（**不是** REG_FAIL，**不是** REG_PASS）
#   T-R18-12 超时单独出现 ⇒ 报告 **rc=0**（不阻断）+ ⚠ 可见 + 明写「未验证」
#   T-R18-13 超时**必须**进未验证累加器（**不假绿**——漏了 ⇒ 结论写「✅ 全部通过」）
#   T-R18-14 阈值真源：读 `harness.yaml#loop_a.regression_timeout_s`（禁硬编码）
#   V6 断言  **反向对照**：把超时判据改回 `REG_FAIL` ⇒ 断言必须翻红
class TestTimeoutSemantics(_SkipSemanticsBase):
    """R18-续：超时第三类状态（`REG_TIMEOUT`）判据守卫。"""

    def test_tr18_11_timeout_is_its_own_state(self):
        """T-R18-11：超时 ⇒ `REG_TIMEOUT`（既不是失败，也不是通过）。"""
        status, detail = self.es.analyze_timeout_suite("test_slow.py", 300)
        self.assertEqual(
            status, self.es.REG_TIMEOUT,
            f"超时应判 REG_TIMEOUT（不阻断但未验证），实得 {status!r}")
        self.assertNotEqual(status, self.es.REG_FAIL,
                            "超时不属真缺陷 ⇒ 不得判 REG_FAIL（假红）")
        self.assertNotEqual(status, self.es.REG_PASS,
                            "超时的套件没跑完 ⇒ 不得判 REG_PASS（假绿）")
        self.assertNotEqual(status, self.es.REG_ENV_LIMITED,
                            "超时不属环境受限 ⇒ 不得判 REG_ENV_LIMITED（误归因）")
        self.assertIn("300", detail.get("text", ""),
                      "文案须含阈值秒数，便于定位")

    def test_tr18_12_timeout_alone_does_not_block(self):
        """T-R18-12：仅超时时报告 rc=0（不阻断）+ ⚠ 可见 + 明写「未验证」。"""
        status, detail = self.es.analyze_timeout_suite("test_slow.py", 300)
        lines, rc = self.es.format_regression_report(
            [("test_slow.py", status, detail)], 1)
        self.assertEqual(rc, 0,
                         "超时不得阻断体检（假红）")
        blob = "\n".join(lines)
        self.assertIn("超时", blob, "超时必须单列可见")
        self.assertIn("未验证", blob,
                      "超时必须明写「未验证」——未验 ≠ 已验")
        self.assertNotIn("✓ 回归测试通过", blob,
                         "超时套件不得出现在「✓ 全部通过」分支（假绿）")

    def test_tr18_13_timeout_enters_unverified_accumulator(self):
        """T-R18-13：超时**必须**进未验证累加器（成对判据：不假绿）。

        ⚠ **本条是本批最关键的一条**：若 `collect_unverified` 漏掉 `REG_TIMEOUT`
          ⇒ 超时是 rc=0（不阻断）⇒ 结论区走「rc=0 且无未验证项」分支
          ⇒ 写出「✅ 全部通过，可发布」⇒ **假绿**（比假红更危险）。
        """
        status, detail = self.es.analyze_timeout_suite("test_slow.py", 300)
        suites, cases = self.es.collect_unverified(
            [("test_slow.py", status, detail)])
        self.assertIn("test_slow.py", suites,
                      "超时套件必须计入未验证累加器（漏了 ⇒ 结论区假绿）")
        self.assertGreaterEqual(cases, 1,
                                "未验证用例数须 ≥1（不得写「0 个用例未验证」）")
        #: 结论区必须降级，不得写「✅ 全部通过」
        concl = "\n".join(self.es.format_final_conclusion(
            0, {"suites": suites, "cases": cases}))
        self.assertNotIn("✅ 全部通过", concl,
                         "有未验证项时结论不得写「✅ 全部通过」（假绿）")
        self.assertIn("未验证", concl, "结论须显式写「未验证」")

    def test_tr18_14_timeout_threshold_reads_from_yaml(self):
        """T-R18-14：超时阈值真源在 `harness.yaml#loop_a.regression_timeout_s`。

        ⚠ 禁硬编码：阈值是**机器判据参数**（机器性能差异大）⇒ 必须在 yaml。
        """
        val, src = self.es.load_regression_timeout_s(str(PKG))
        self.assertEqual(src, "yaml",
                         f"阈值必须从 harness.yaml 读到（禁硬编码），实得 src={src!r}")
        self.assertGreater(val, 0, "阈值必须为正数")
        #: yaml 里必须真的声明了这个键（防止「读不到但静默回落」）
        import yaml as _yaml
        cfg = _yaml.safe_load(
            (PKG / "config" / "harness.yaml").read_text(encoding="utf-8"))
        self.assertIn("regression_timeout_s", (cfg.get("loop_a") or {}),
                      "harness.yaml#loop_a 必须声明 regression_timeout_s")

    def test_tr18_v6_reverse_control_timeout_must_not_be_fail(self):
        """V6 反向对照：把超时判据改回 `REG_FAIL` ⇒ 断言必须翻红。

        ⚠ **真对照**（不接受「逻辑上应该会翻红」）：
          覆写 ⇒ 断言失败 ⇒ 恢复 ⇒ 断言通过 ⇒ 证明判据**真在读**这个状态。
        """
        original = self.es.analyze_timeout_suite
        try:
            #: 改坏：超时又判回 REG_FAIL（假红回归）
            def _broken(name, timeout_s):
                return self.es.REG_FAIL, {"text": "超时", "fail_tail": "超时",
                                          "marker_hit": False, "skipped_cases": 0,
                                          "anti_skips": 0, "timeout_cases": 1}
            self.es.analyze_timeout_suite = _broken
            status, _ = self.es.analyze_timeout_suite("test_slow.py", 300)
            self.assertEqual(
                status, self.es.REG_FAIL,
                "对照命中：改坏后超时被判 REG_FAIL（假红已回归）")
            self.assertNotEqual(
                status, self.es.REG_TIMEOUT,
                "反向对照失败：判据恒真摆设（改不坏）")
        finally:
            self.es.analyze_timeout_suite = original
        #: 恢复后必须重新判回 REG_TIMEOUT（证明对照可逆）
        status, _ = self.es.analyze_timeout_suite("test_slow.py", 300)
        self.assertEqual(
            status, self.es.REG_TIMEOUT,
            f"恢复后必须重新判 REG_TIMEOUT（对照可逆），实得 {status!r}")

    def test_tr18_v6b_reverse_control_unverified_must_include_timeout(self):
        """V6 反向对照②：把未验证集合改回不含 `REG_TIMEOUT` ⇒ 断言必须翻红。

        ⚠ **对照必须落在「真被读到的那一处」**：
          首版误设计为「覆写模块常量 `REG_TIMEOUT`」⇒ 但该常量**同时**被
          `analyze_timeout_suite`（返回状态）与 `collect_unverified`（并集条件）
          两处读取 ⇒ 覆写后两处**同步**变化 ⇒ 未验证集合仍含它 ⇒ 对照**失真**
          （实测：34 tests 中本条报红，方向反了）。
          ⇒ 正确做法：**源码级 mutator** —— 只改 `collect_unverified` 的并集条件
            （把 `, REG_TIMEOUT` 删掉），**不动**其他任何一处
            ⇒ 该套件**真被判据改坏** ⇒ T-R18-13 必须真的失败。

        ⚠ 对照走**隔离副本**：在临时目录里复制被测模块并改一处源码，
          绝不碰真包文件（对照不得污染被测对象）。
        """
        import shutil
        import tempfile

        src = _ES_PATH.read_text(encoding="utf-8")
        mutated = src.replace(
            "if s in (REG_PASS_WITH_SKIPS, REG_ENV_LIMITED, REG_TIMEOUT)]",
            "if s in (REG_PASS_WITH_SKIPS, REG_ENV_LIMITED)]")
        self.assertNotEqual(
            mutated, src,
            "变异失败：未找到 `collect_unverified` 的并集条件源码"
            "（改了判据的写法 ⇒ 对照失真）")

        tmpdir = Path(tempfile.mkdtemp(prefix="vet-r18-timeout-mut-"))
        try:
            mut_path = tmpdir / "ensure_settings.py"
            mut_path.write_text(mutated, encoding="utf-8")
            mut = _load_module("v328_ensure_settings_mutant", mut_path)
            status, detail = mut.analyze_timeout_suite("test_slow.py", 300)
            self.assertEqual(
                status, mut.REG_TIMEOUT,
                "变异体自身：超时仍须判 REG_TIMEOUT（只改未验证集合）")
            suites, _cases = mut.collect_unverified(
                [("test_slow.py", status, detail)])
            self.assertNotIn(
                "test_slow.py", suites,
                "对照命中：变异体把超时踢出未验证集合 ⇒ 假绿路径已打开")
            #: 变异体的结论区必须写「✅ 全部通过」——这正是要防的假绿形态
            concl = "\n".join(mut.format_final_conclusion(
                0, {"suites": suites, "cases": 0}))
            self.assertIn(
                "✅ 全部通过", concl,
                "对照命中：变异体写出「✅ 全部通过」⇒ 证实假绿路径真实存在")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        #: 真包必须不受影响（对照不得污染被测对象）
        status, detail = self.es.analyze_timeout_suite("test_slow.py", 300)
        suites, _cases = self.es.collect_unverified(
            [("test_slow.py", status, detail)])
        self.assertIn("test_slow.py", suites,
                      "真包：超时必须计入未验证累加器（对照不得污染真包）")


if __name__ == "__main__":
    unittest.main()

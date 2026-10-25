#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""loop_contract.py 正例 + 反向例回归护栏（v3.20.0）。

为什么这份测试必须存在（不是"补个覆盖率"）：
  config/harness.yaml 的 loop_a / loop_b / delta_gate 三段共 34 个叶子键，
  此前 32 个**零代码读取者**——配置写了、代码不读，看起来有护栏、实际不设防，
  正是本包反复治理的"声明层 ≠ 执行层"。v3.20.0 由 loop_contract.py 落地为判据后，
  若只测"接口能跑通"，就无法区分**真接线**与**假绿**：
    · 假绿形态 A：键出现在代码里，但改它的值不改行为（配置不生效）；
    · 假绿形态 B：反例破坏的是**调用点**而不是被测对象，反例恒真、永远绿。

  故本文件定两条硬规矩（每条反向例都按此构造）：
    1. 反向例必须**破坏被测对象本身**——要么改 harness.yaml 的取值（配置侧），
       要么破坏 loop_contract 里的判据实现（代码侧），然后断言"行为跟着变"；
    2. 双向验证：登记改了 ⇒ 行为变；**破坏实现 ⇒ 反向例翻转**。
       后者由 TestImplementationBreak 承担（把实现破坏成硬编码/恒真，
       确认原本会红的断言真的会翻绿——翻不动就说明反例是恒真断言）。

  每条反向例的注释里都写明一句话：**"如果这个值改了，哪个函数的行为应该跟着变"**。

  配置改动一律走「读原文 → 改文本 → 重载 dict」；**从不写回包内真实 yaml**，
  模块级 setUpModule/tearDownModule 用 sha256 前后比对守住这一点。

── 假阴性自检记录（2026-10-26）──────────────────────────────────────────
  做法：随机挑 4 条反向例，把它们断言的"破坏"去掉（恢复成正常配置/正常数据），
  跑该文件 → 这 4 条**必须转红**。转红 = 反例真的在测东西；不转红 = 恒真断言。
    · test_T1_reverse_loop_b_disabled（loop_b.enabled 改回 true）  → 转红 ✅
    · test_T9_reverse_limit_from_yaml（retrieval_budget 上限改回 30） → 转红 ✅
    · test_T16_reverse_missing_source_element（补回「来源与许可」）  → 转红 ✅
    · test_T13_reverse_p0_rises_blocks（p0 由 7 改回 6）            → 转红 ✅
  另由 TestImplementationBreak 从**代码侧**做了 5 组双向验证（破坏实现 ⇒ 判定翻转），
  两侧合起来才敢说"判的是这件事本身"。
"""
import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
LC_PATH = os.path.join(HERE, "loop_contract.py")
HARNESS_YAML = os.path.join(PKG, "config", "harness.yaml")

LC = None            # loop_contract 模块（setUpModule 载入）
HARNESS_TEXT = ""    # 真实 harness.yaml 原文（只读，永不写回）
_SHA_BEFORE = ""


def setUpModule():
    global LC, HARNESS_TEXT, _SHA_BEFORE
    spec = importlib.util.spec_from_file_location("loop_contract_ut", LC_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["loop_contract_ut"] = m
    spec.loader.exec_module(m)
    LC = m
    with open(HARNESS_YAML, encoding="utf-8") as f:
        HARNESS_TEXT = f.read()
    with open(HARNESS_YAML, "rb") as f:
        _SHA_BEFORE = hashlib.sha256(f.read()).hexdigest()


def tearDownModule():
    """跑完必须与原文件逐字节一致——任何用例都不许在包内 yaml 留下脏数据。"""
    with open(HARNESS_YAML, "rb") as f:
        after = hashlib.sha256(f.read()).hexdigest()
    assert after == _SHA_BEFORE, (
        f"config/harness.yaml 被改动且未还原：\n  before={_SHA_BEFORE}\n  after ={after}")


def cfg_of(text=None):
    """从（可能被改过的）yaml **文本**重新解析配置——证明键路径在文本里真实存在。"""
    return yaml.safe_load(text if text is not None else HARNESS_TEXT) or {}


def patch_text(text, old, new):
    """改 yaml 文本并强制校验命中次数为 1。

    为什么必须 assertEqual(count, 1)：替换 0 次 = 反例没构造出来（假绿）；
    替换多次 = 改到了不该改的段（反例测的就不是这条判据了）。
    """
    n = text.count(old)
    assert n == 1, f"反例构造失败：{old!r} 命中 {n} 次（应为 1 次）"
    return text.replace(old, new, 1)


def _fallback_literal_is_dict(src):
    """回落表 `_FALLBACK` 的声明处是不是**字典字面量**（第 18 项会当读取点收集）。

    返回 True / False；找不到 `_FALLBACK` 赋值时返回 None（声明被改名/删除，
    由调用方单独处理——不能让"找不到"悄悄等于"没问题"）。
    """
    import ast
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "_FALLBACK"
                                             for t in n.targets):
            return isinstance(n.value, ast.Dict)
    return None


def drop_line(text, line):
    """删掉 yaml 里某一行（模拟"键被删掉"），同样强制校验只命中一次。"""
    n = text.count(line)
    assert n == 1, f"反例构造失败：待删行 {line!r} 命中 {n} 次（应为 1 次）"
    return text.replace(line, "", 1)


class _Base(unittest.TestCase):
    """公共夹具：临时工作区（避免 <工作区> 解析到真实目录而误伤文件）。"""

    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="lc_ws_")
        self.cfg = cfg_of()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)


# ══════════════════════════ T1–T3：两环身份与路径 ══════════════════════════
class TestT1Enabled(_Base):
    """T1：loop_{a,b}.enabled —— 环开关是否真的能关掉。"""

    def test_T1_positive_both_loops_enabled_from_yaml(self):
        notes = []
        ok_a = LC.enabled(self.cfg, "a", notes)
        ok_b = LC.enabled(self.cfg, "b", notes)
        self.assertTrue(ok_a, "loop_a.enabled=true 应读到 True")
        self.assertTrue(ok_b, "loop_b.enabled=true 应读到 True")
        # 配置齐全时不许走回落：走了回落说明键没被读到（与本包"声明未接线"同型缺陷）
        self.assertEqual(notes, [], f"配置齐全却出现回落：{notes}")

    def test_T1_positive_returns_scalar_bool_not_tuple(self):
        """正例（形态守卫）：enabled 必须返回**标量 bool**，不得是 (值, 是否回落) 元组。

        为什么单独测这个：调用点写成 `if not loop_contract.enabled(...): 拦截`，
        返回非空元组时 `not (True, False)` 恒为 False ⇒ **拦截永不触发**——
        "接线了但不设防"比没接线更危险（看起来有开关，实际没有）。
        是否回落一律由 notes 传递，不占返回值。
        """
        for loop in ("a", "b"):
            v = LC.enabled(self.cfg, loop)
            self.assertIsInstance(v, bool,
                                  f"enabled(cfg,{loop!r}) 返回了 {type(v).__name__}，"
                                  f"必须是标量 bool（元组会让拦截分支永不生效）")
            self.assertNotIsInstance(v, tuple)

    def test_T1_reverse_loop_b_disabled(self):
        """反例：改 loop_b.enabled=false ⇒ `enabled()` 必须返回 False。

        如果这个值改了，**enabled(cfg,'b')** 的行为应该跟着变（True→False）。
        该键此前零读取者：改成 false 全包无任何行为变化，"停用某环"在代码层无法表达。
        """
        t = patch_text(HARNESS_TEXT, "loop_b:\n  enabled: true",
                       "loop_b:\n  enabled: false")
        self.assertFalse(LC.enabled(cfg_of(t), "b"),
                         "loop_b.enabled=false 后 enabled() 仍返回 True——开关未接线")
        # 同批必须不影响 Loop A（证明读的是 loop_b 段而不是某个全局常量）
        self.assertTrue(LC.enabled(cfg_of(t), "a"), "改 loop_b 不该影响 loop_a")


class TestT2StatePath(_Base):
    """T2：loop_{a,b}.state_file —— 状态文件路径是否真的由配置决定。"""

    def test_T2_positive_loop_a_state_in_package(self):
        p, notes = LC.state_path(self.cfg, self.ws, "a")
        self.assertEqual(p, os.path.join(LC.PKG, ".workbuddy", "loopA_state.json"),
                         "Loop A 状态文件应落在 <包>/.workbuddy/（配置声明处）")
        self.assertEqual(notes, [], "配置齐全时 state_path 不应产生回落提示")

    def test_T2_positive_loop_b_state_in_workspace(self):
        p, _ = LC.state_path(self.cfg, self.ws, "b")
        self.assertEqual(p, os.path.join(self.ws, ".workbuddy", "loopB_state.json"),
                         "Loop B 状态文件应落在 <工作区>/.workbuddy/")

    def test_T2_reverse_state_file_placeholder_moves_path(self):
        """反例：改 loop_a.state_file 的占位符 ⇒ 解析出的路径必须跟着搬走。

        如果这个值改了，**state_path(cfg, ws, 'a')** 的行为应该跟着变。
        v3.20.0 修的就是这里：配置写 `<包>/.workbuddy/`，代码硬写 `<工作区>/.workbuddy/`，
        改配置不改行为（且 Loop B 两者恰好同值，故长期无人发现）。
        """
        t = patch_text(HARNESS_TEXT,
                       'state_file: "<包>/.workbuddy/loopA_state.json"',
                       'state_file: "<包>/.workbuddy/alt/loopA_state.json"')
        p, notes = LC.state_path(cfg_of(t), self.ws, "a")
        self.assertEqual(p, os.path.join(LC.PKG, ".workbuddy", "alt", "loopA_state.json"),
                         "改了 state_file 但解析路径没变——路径被硬编码了")
        self.assertNotEqual(p, os.path.join(LC.PKG, ".workbuddy", "loopA_state.json"))
        self.assertEqual(notes, [])


class TestT3CoexistGuard(_Base):
    """T3：loop_b.coexist_with —— 「并存，不覆盖」守卫。"""

    def test_T3_positive_two_paths_differ(self):
        ok, msg, info = LC.coexist_guard(self.cfg, self.ws)
        self.assertTrue(ok, f"两路径不同时应判 ok，实得：{msg}")
        self.assertNotEqual(info["state_file"], info["coexist_with"])
        # 守卫是纯判定：不得在判定过程中创建/覆盖任何状态文件
        self.assertFalse(os.path.exists(info["state_file"]), "守卫不得写状态文件")
        self.assertFalse(os.path.exists(info["coexist_with"]), "守卫不得触碰 task_state.json")

    def test_T3_reverse_same_path_is_rejected(self):
        """反例：把 loop_b.state_file 改成与 coexist_with 同值 ⇒ 必须判 False。

        如果这个值改了，**coexist_guard()** 的行为应该跟着变（ok → 不 ok）。
        两者撞车时写 Loop B 状态会直接覆盖五道闸的 task_state.json
        （round-review-sop.md#10「并存，不覆盖」）；该键此前零读取者，
        改成同值系统照样启动。
        """
        t = patch_text(HARNESS_TEXT,
                       'state_file: "<工作区>/.workbuddy/loopB_state.json"',
                       'state_file: "<工作区>/.workbuddy/task_state.json"')
        ok, msg, info = LC.coexist_guard(cfg_of(t), self.ws)
        self.assertFalse(ok, "state_file 与 coexist_with 撞车却判 ok——并存守卫失效")
        self.assertIn("覆盖", msg, "失败原因必须点明是覆盖既有状态机")
        self.assertEqual(info["state_file"], info["coexist_with"])
        # 关键：判 False 的**同时**不许动 task_state.json（守卫只判不修）
        self.assertFalse(os.path.exists(info["coexist_with"]),
                         "守卫判定失败时不得覆盖/创建 task_state.json")

    def test_T3_reverse_missing_coexist_is_skipped_not_passed(self):
        """反例：删掉 coexist_with ⇒ 守卫必须**显式跳过**并写明，不得静默判 ok。

        如果这个值没了，**coexist_guard()** 必须交出"跳过"而不是"通过"——
        否则"没配"与"配了且没问题"在调用方眼里是一样的（静默通过 = 未设防）。
        """
        t = drop_line(HARNESS_TEXT,
                      '  coexist_with: "<工作区>/.workbuddy/task_state.json"   '
                      '# 并存，不覆盖（五道闸状态机语义不变）\n')
        ok, msg, info = LC.coexist_guard(cfg_of(t), self.ws)
        self.assertTrue(ok, "跳过仍返回 ok（不阻断），但必须写明")
        self.assertIn("跳过", msg, "未配置 coexist_with 时必须写明跳过，不得静默判 ok")
        self.assertEqual(info["coexist_with"], "")


# ══════════════════════════ T4–T5：写者与原件 ══════════════════════════
class TestT4SingleWriter(_Base):
    """T4：loop_b.single_writer —— 唯一写者校验。"""

    def test_T4_positive_declared_writer(self):
        ok, msg, writer = LC.single_writer_check(self.cfg, "team-lead")
        self.assertTrue(ok, f"actor=team-lead 应通过，实得：{msg}")
        self.assertEqual(writer, "team-lead")

    def test_T4_reverse_other_actor_rejected(self):
        """反例：actor 换成非登记写者 ⇒ 必须拒绝。

        如果这个值改了，**single_writer_check()** 的行为应该跟着变。
        诚实边界：挡的是误用与无声越权，不是冒名（平台无身份认证）。
        """
        ok, msg, _ = LC.single_writer_check(self.cfg, "visual-slide-designer")
        self.assertFalse(ok, "非登记写者却判 ok——单写者纪律未接线")
        self.assertIn("team-lead", msg, "失败原因应点名唯一写者是谁")

    def test_T4_reverse_empty_actor_is_not_silent(self):
        """反例：actor 为空 ⇒ 放行但**必须留痕**（不得当成"已校验通过"）。"""
        notes = []
        ok, msg, _ = LC.single_writer_check(self.cfg, "", notes)
        self.assertTrue(ok, "未声明写者时不阻断（避免误伤）")
        self.assertTrue(notes, "未声明写者必须记 note——静默放行等于没校验")
        self.assertIn("未声明", msg)

    def test_T4_reverse_writer_value_from_yaml(self):
        """反例：改 yaml 的 single_writer ⇒ 原来合法的 team-lead 必须变非法。

        如果这个值改了，**single_writer_check()** 的判定基准应该跟着变。
        """
        t = patch_text(HARNESS_TEXT, 'single_writer: "team-lead"',
                       'single_writer: "housekeeper"')
        ok, msg, writer = LC.single_writer_check(cfg_of(t), "team-lead")
        self.assertFalse(ok, "改了唯一写者后 team-lead 仍被判合法——值不是从 yaml 读的")
        self.assertEqual(writer, "housekeeper")
        self.assertTrue(LC.single_writer_check(cfg_of(t), "housekeeper")[0])


class TestT5OriginalReadonly(_Base):
    """T5：loop_b.original_readonly —— 原件只读开关。"""

    def test_T5_positive_true_from_yaml(self):
        notes = []
        v = LC.original_readonly(self.cfg, notes)
        self.assertIsInstance(v, bool, "原件只读开关必须返回标量 bool（元组会让关闭分支永不生效）")
        self.assertTrue(v, "original_readonly=true 应读到 True")
        self.assertEqual(notes, [], f"配置齐全却出现回落：{notes}")

    def test_T5_reverse_false(self):
        """反例：改 false ⇒ 必须读到 False。

        如果这个值改了，**original_readonly()** 的返回值应该跟着变。
        """
        t = patch_text(HARNESS_TEXT, "original_readonly: true", "original_readonly: false")
        self.assertFalse(LC.original_readonly(cfg_of(t)),
                         "original_readonly=false 后仍读到 True——开关未接线")


# ══════════════════════════ T6–T7：Loop A 批次门 ══════════════════════════
class TestT6Regression(_Base):
    """T6：loop_a.regression_required —— 回归项是否跑齐。"""

    def test_T6_positive_all_ran(self):
        ok, missing, required, extra = LC.regression_check(
            self.cfg, ["ensure_settings", "test_harness", "test_five_gates"])
        self.assertTrue(ok, f"三项齐应通过，缺：{missing}")
        self.assertEqual(missing, [])
        self.assertEqual(sorted(required),
                         ["ensure_settings", "test_five_gates", "test_harness"])
        self.assertEqual(extra, [])

    def test_T6_reverse_two_of_three(self):
        """反例：只跑两项 ⇒ missing 必须非空且指名缺哪一项。

        如果这个值改了，**regression_check()** 的 missing 应该跟着变。
        "跑了两项就算了"是 Loop A 最典型的自评失真入口。
        """
        ok, missing, _required, _extra = LC.regression_check(
            self.cfg, ["ensure_settings", "test_harness"])
        self.assertFalse(ok, "只跑两项却判合格——回归门形同虚设")
        self.assertEqual(missing, ["test_five_gates"])

    def test_T6_reverse_required_list_from_yaml(self):
        """反例：往 yaml 的 regression_required 加一项 ⇒ 原"全跑"组合立刻判缺。

        如果这个值改了，**regression_check()** 的 required/missing 应该跟着变
        ——证明"跑齐"的清单真的来自配置，而不是写死在函数里。
        """
        t = patch_text(HARNESS_TEXT,
                       "regression_required: [\"ensure_settings\", \"test_harness\", "
                       "\"test_five_gates\"]",
                       "regression_required: [\"ensure_settings\", \"test_harness\", "
                       "\"test_five_gates\", \"test_loop_contract\"]")
        ok, missing, required, _ = LC.regression_check(
            cfg_of(t), ["ensure_settings", "test_harness", "test_five_gates"])
        self.assertFalse(ok, "yaml 加了第四项后原组合仍判合格——清单不是从配置读的")
        self.assertEqual(missing, ["test_loop_contract"])
        self.assertIn("test_loop_contract", required)


class TestT7PatchDiscipline(_Base):
    """T7：loop_a.patch_discipline —— 最小补丁纪律（可判定部分）。"""

    def test_T7_positive_declared_covers_actual(self):
        ok, problems, declared = LC.patch_discipline_check(
            self.cfg, ["scripts/a.py"], ["scripts/a.py"])
        self.assertTrue(ok, f"声明与实际一致应无问题，实得：{problems}")
        self.assertEqual(problems, [])
        self.assertEqual(declared, ["scripts/a.py"])

    def test_T7_reverse_undeclared_change(self):
        """反例：实际改动超出声明 ⇒ 必须报 undeclared_changes。

        如果这个值改了，**patch_discipline_check()** 的 problems 应该跟着变。
        """
        ok, problems, _ = LC.patch_discipline_check(
            self.cfg, ["scripts/a.py"], ["scripts/a.py", "config/harness.yaml"])
        self.assertFalse(ok, "改动超出声明却判合格——最小补丁纪律未接线")
        self.assertEqual([p[0] for p in problems], ["undeclared_changes"])

    def test_T7_reverse_no_declared_files(self):
        """反例：开工前未声明 ⇒ 必须报 no_declared_files（不是"没改就算最小"）。"""
        ok, problems, _ = LC.patch_discipline_check(self.cfg, [], ["scripts/a.py"])
        self.assertFalse(ok, "未声明改动文件却判合格——无法判定是否最小")
        self.assertEqual([p[0] for p in problems], ["no_declared_files"])

    def test_T7_reverse_non_minimal_policy_not_judged(self):
        """反例：patch_discipline 改成非 minimal ⇒ **不判定**且必须写明无执行器。

        如果这个值改了，**patch_discipline_check()** 应从"判定"翻转为"不判定"。
        不得把"没执行器"包装成"检查通过"——那是本包最忌的假绿。
        """
        t = patch_text(HARNESS_TEXT, 'patch_discipline: "minimal"',
                       'patch_discipline: "thorough"')
        notes = []
        ok, problems, _ = LC.patch_discipline_check(
            cfg_of(t), ["scripts/a.py"], ["scripts/a.py", "config/harness.yaml"], notes)
        self.assertTrue(ok, "非 minimal 时不阻断（无执行器不该假装判了）")
        self.assertEqual(problems, [], "无执行器时不得产出判定结论")
        self.assertTrue(any("有执行器" in n and "不判定" in n for n in notes),
                        f"必须写明当前仅 'minimal' 有执行器、本批不判定，实得 notes={notes}")

    def test_T7_reverse_actual_unavailable_is_not_silent(self):
        """反例：拿不到实际改动集合 ⇒ 不静默通过，notes 必须写明**未做**比对。"""
        notes = []
        ok, problems, _ = LC.patch_discipline_check(
            self.cfg, ["scripts/a.py"], None, notes)
        self.assertTrue(ok, "不可得时不阻断，但必须留痕")
        self.assertTrue(any("未做" in n for n in notes),
                        f"必须写明未做改动集合比对，实得 notes={notes}")


# ══════════════════════════ T8–T9：Loop B 轮审与预算 ══════════════════════════
class TestT8RoundReview(_Base):
    """T8：loop_b.round_review.required + required_items —— 轮报完整性。"""

    SIX = {"本轮改了什么": "x", "证据": "y", "未决项": "z",
           "下轮计划": "a", "风险": "b", "需用户确认": "c"}

    def test_T8_positive_six_items(self):
        ok, n, req = LC.round_review_check(self.cfg, dict(self.SIX))
        self.assertTrue(ok, "六项非空应通过")
        self.assertEqual(n, 6)
        self.assertEqual(req, 6)

    def test_T8_reverse_five_items(self):
        """反例：只给 5 项 ⇒ 必须判 False。

        如果这个值改了，**round_review_check()** 的判定应该跟着变
        （统计的是非空项数，不是查键名——SOP 只规定内容不规定键名）。
        """
        five = dict(self.SIX)
        five.pop("需用户确认")
        ok, n, req = LC.round_review_check(self.cfg, five)
        self.assertFalse(ok, "只给 5 项却判合格——六项齐的判据未生效")
        self.assertEqual(n, 5)
        # 空串不算一项：防止"键填了但没内容"蒙混过关
        padded = dict(five)
        padded["需用户确认"] = ""
        self.assertFalse(LC.round_review_check(self.cfg, padded)[0],
                         "空串不得计入有效项")

    def test_T8_reverse_required_false_disables(self):
        """反例：round_review.required=false ⇒ 不强制（但必须写明不阻断）。"""
        t = patch_text(HARNESS_TEXT,
                       "  round_review:\n    required: true",
                       "  round_review:\n    required: false")
        notes = []
        ok, n, req = LC.round_review_check(cfg_of(t), {"只有一项": "x"}, notes)
        self.assertTrue(ok, "required=false 时不阻断")
        self.assertEqual(n, 0, "不强制时不做项数统计")
        self.assertTrue(any("不强制" in x or "不阻断" in x for x in notes),
                        f"必须写明本轮不强制轮报，实得 notes={notes}")

    def test_T8_reverse_required_items_from_yaml(self):
        """反例：yaml 的 required_items 改成 7 ⇒ 六项轮报立刻判不合格。

        如果这个值改了，**round_review_check()** 的阈值应该跟着变
        （6 这个数此前只存在于 round-review-sop.md#5，代码无从得知）。
        """
        t = patch_text(HARNESS_TEXT, "    required_items: 6", "    required_items: 7")
        ok, n, req = LC.round_review_check(cfg_of(t), dict(self.SIX))
        self.assertFalse(ok, "required_items=7 后六项仍判合格——阈值不是从 yaml 读的")
        self.assertEqual((n, req), (6, 7))


class TestT9RetrievalBudget(_Base):
    """T9：loop_b.budgets.retrieval_budget_per_round —— 检索预算是否触顶。"""

    def test_T9_positive_at_limit(self):
        ok, msg = LC.retrieval_check(self.cfg, 30)
        self.assertTrue(ok, f"30 ≤ 30 应通过，实得：{msg}")
        self.assertIn("30/30", msg)

    def test_T9_reverse_over_limit(self):
        """反例：used=31 ⇒ 必须判超预算。

        如果这个值改了，**retrieval_check()** 的判定应该跟着变。
        此键此前零读取者：配了 30 次/轮的上限，机器从不计数。
        """
        ok, msg = LC.retrieval_check(self.cfg, 31)
        self.assertFalse(ok, "31 > 30 却判未超预算——预算键未接线")
        self.assertIn("31", msg)

    def test_T9_reverse_limit_from_yaml(self):
        """反例：yaml 上限 30→5 ⇒ used=6 必须判超（used=5 仍通过）。

        如果这个值改了，**retrieval_check()** 的阈值应该跟着变。
        """
        t = patch_text(HARNESS_TEXT, "    retrieval_budget_per_round: 30",
                       "    retrieval_budget_per_round: 5")
        cfg5 = cfg_of(t)
        ok6, msg6 = LC.retrieval_check(cfg5, 6)
        self.assertFalse(ok6, "上限改为 5 后 used=6 仍判通过——上限不是从 yaml 读的")
        self.assertIn("5", msg6)
        self.assertTrue(LC.retrieval_check(cfg5, 5)[0], "used=5 恰好等于新上限，应通过")


# ══════════════════════ T10–T12：基线字段与增量报告 ══════════════════════
class TestT10Baseline(_Base):
    """T10：delta_gate.baseline_fields —— 基线必填字段（字段名本身来自配置）。"""

    FULL = {"p0": 6, "p1": 2, "p2": 1, "pages_physical": 30,
            "pages_visible": 30, "md5": "abc"}

    def test_T10_positive_all_fields(self):
        ok, missing, fields = LC.baseline_check(self.cfg, dict(self.FULL))
        self.assertTrue(ok, f"六字段齐应通过，缺：{missing}")
        self.assertEqual(missing, [])
        self.assertEqual(fields, ["p0", "p1", "p2", "pages_physical",
                                  "pages_visible", "md5"])

    def test_T10_reverse_missing_md5(self):
        """反例：删掉 md5 ⇒ missing 必须含 md5 且 note 说明缺了几个。

        如果这个值改了，**baseline_check()** 的 missing 应该跟着变。
        """
        d = dict(self.FULL)
        d.pop("md5")
        notes = []
        ok, missing, _ = LC.baseline_check(self.cfg, d, notes)
        self.assertFalse(ok, "缺 md5 却判合格——基线必填形同虚设")
        self.assertEqual(missing, ["md5"])
        self.assertTrue(any("md5" in n for n in notes), "缺失必须写进 notes（不静默）")

    def test_T10_reverse_field_name_from_yaml(self):
        """反例：往 yaml 的 baseline_fields 加一个字段 ⇒ 旧数据立刻判缺。

        如果这个值改了，**baseline_check()** 的 fields/missing 应该跟着变
        ——证明字段名真的来自配置（加字段不用改代码即生效）。
        """
        t = patch_text(HARNESS_TEXT,
                       'baseline_fields: ["p0", "p1", "p2", "pages_physical", '
                       '"pages_visible", "md5"]',
                       'baseline_fields: ["p0", "p1", "p2", "pages_physical", '
                       '"pages_visible", "md5", "export_pages"]')
        ok, missing, fields = LC.baseline_check(cfg_of(t), dict(self.FULL))
        self.assertFalse(ok, "yaml 加了 export_pages 后旧数据仍判合格——字段名不是从配置读的")
        self.assertEqual(missing, ["export_pages"])
        self.assertIn("export_pages", fields)


class TestT11RenderDeltaReport(_Base):
    """T11：delta_gate.report_format —— 报告行渲染 + 格式合规。"""

    def test_T11_positive_default_format(self):
        r = LC.render_delta_report(self.cfg, 6, 6)
        self.assertEqual(r["text"], "P0=6（基线 6，自引入 0）",
                         "渲染结果必须与 yaml 声明的格式串一致")
        self.assertTrue(r["ok"], f"应判合规，实得 notes={r['notes']}")
        self.assertTrue(r["pattern_ok"], "渲染结果必须能通过由同一格式串生成的正则")
        self.assertTrue(r["conserved"], "6 = 6 + 0 应守恒")
        self.assertEqual(r["delta"], 0)

    def test_T11_positive_self_introduced_two(self):
        r = LC.render_delta_report(self.cfg, 8, 6)
        self.assertEqual(r["text"], "P0=8（基线 6，自引入 2）")
        self.assertEqual(r["delta"], 2)
        self.assertTrue(r["ok"], "8 = 6 + 2 应守恒且合规")

    def test_T11_positive_fixed_two(self):
        r = LC.render_delta_report(self.cfg, 4, 6)
        self.assertEqual(r["text"], "P0=4（基线 6，自引入 -2）")
        self.assertTrue(r["ok"], "自引入为负（修好了 2 个）是合法的，不得判不守恒")

    def test_T11_reverse_format_string_drives_output(self):
        """反例：改 yaml 的 report_format ⇒ 渲染文本**和**校验正则都要跟着变。

        如果这个值改了，**render_delta_report()** 与 **delta_pattern()** 的行为
        应该跟着变——这是"报告格式"从 Markdown 文档变成机器判据的关键。
        """
        t = patch_text(HARNESS_TEXT,
                       '  report_format: "P0=6（基线 6，自引入 0）"',
                       '  report_format: "P0=6 / 基线 6 / 新增 0"')
        cfg2 = cfg_of(t)
        r = LC.render_delta_report(cfg2, 6, 6)
        self.assertEqual(r["text"], "P0=6 / 基线 6 / 新增 0",
                         "改了格式串但渲染文本没变——格式串被硬编码了")
        self.assertTrue(r["ok"], "新格式下应按新格式判合规")
        pat, _ = LC.delta_pattern(cfg2)
        self.assertIsNotNone(pat, "新格式串应能生成校验正则")
        self.assertTrue(pat.fullmatch("P0=9 / 基线 6 / 新增 3"), "正则应随格式串改变")
        self.assertFalse(pat.fullmatch("P0=9（基线 6，自引入 3）"),
                         "旧格式的行必须不再被判合规（否则格式串没生效）")
        # 旧格式的行在新配置下渲染必须判不合规
        self.assertFalse(LC.render_delta_report(cfg2, 6, 6)["text"].startswith("P0=6（"))

    def test_T11_reverse_format_without_three_slots_is_not_silently_ok(self):
        """反例：格式串只有 2 个数值位 ⇒ 渲染与守恒校验**未生效**，必须报错而非静默。

        为什么必须显式失败：`_format_slots` 识别不出 3 个数值位时无法构造模板，
        此时若返回 ok=True，等于"报告格式"这条纪律被悄悄跳过（本包最忌的假绿）。
        """
        t = patch_text(HARNESS_TEXT,
                       '  report_format: "P0=6（基线 6，自引入 0）"',
                       '  report_format: "P0=6（基线 6）"')
        notes = []
        r = LC.render_delta_report(cfg_of(t), 6, 6, notes)
        self.assertFalse(r["ok"], "格式串不可解析时必须判不合规，不得静默通过")
        self.assertEqual(r["text"], "", "不可解析时不产出报告行")
        self.assertTrue(any("未生效" in n for n in notes),
                        f"必须写明格式渲染与合规校验未生效，实得 notes={notes}")
        pat, _ = LC.delta_pattern(cfg_of(t))
        self.assertIsNone(pat, "数值位不足时不应产出校验正则")


class TestT12Conservation(_Base):
    """T12：三个数必须守恒（P0 = 基线 + 自引入）。"""

    def test_T12_positive_rendered_report_is_conserved(self):
        r = LC.render_delta_report(self.cfg, 7, 5)
        self.assertTrue(r["conserved"], "渲染器产出的报告必须自洽")
        self.assertEqual(r["text"], "P0=7（基线 5，自引入 2）")

    def test_T12_reverse_handwritten_unconserved_string(self):
        """反例：绕过 render，**手写**一个三数不相符的串交给由格式串生成的正则。

        如果这个值改了，**delta_pattern() 生成的正则 + 守恒算式** 必须抓出来
        ——报告里三个数对不上，说明报告与基线不是同一套数，应退回复算而不是猜。
        """
        pat, _ = LC.delta_pattern(self.cfg)
        m = pat.fullmatch("P0=8（基线 6，自引入 1）")
        self.assertIsNotNone(m, "格式匹配应通过（格式没问题，是数有问题）")
        self.assertNotEqual(int(m.group(1)), int(m.group(2)) + int(m.group(3)),
                            "8 ≠ 6 + 1：守恒校验必须判不守恒")
        notes = []
        LC.render_delta_report(self.cfg, 8, 6, notes)  # 正常路径应守恒
        self.assertFalse(any("不守恒" in n for n in notes), "8 = 6 + 2 不应报不守恒")

    def test_T12_reverse_malformed_string_not_matched(self):
        """反例：手写一个格式不符的串 ⇒ 正则必须**不匹配**（挡住"只报绝对数"）。

        如果这个值改了，**delta_pattern()** 生成的正则应该跟着不匹配。
        yaml 注释写明：只报绝对数（如 "P0=6"）的报告视为不合格，退回复算。
        """
        pat, _ = LC.delta_pattern(self.cfg)
        for bad in ("P0=6", "P0=六（基线 6，自引入 0）", "P0=6（自引入 0）",
                    "共 6 处问题"):
            self.assertIsNone(pat.fullmatch(bad), f"{bad!r} 不应被判为合规报告行")


# ══════════════════════════ T13–T14：增量门禁总判 ══════════════════════════
class TestT13DeltaVerdict(_Base):
    """T13：delta_gate.block_on_new_defects —— 自引入新缺陷是否阻断。"""

    BASE = {"p0": 6, "p1": 2, "p2": 1}

    def test_T13_positive_dropped_not_blocked(self):
        v = LC.delta_verdict(self.cfg, dict(self.BASE), {"p0": 5, "p1": 2, "p2": 1})
        self.assertFalse(v["blocked"], "缺陷下降不得阻断")
        self.assertTrue(v["ok"], f"应判 ok，实得 notes={v['notes']}")
        self.assertEqual(v["increased"], [])
        self.assertEqual(v["reason"], "")

    def test_T13_positive_flat_not_blocked(self):
        v = LC.delta_verdict(self.cfg, dict(self.BASE), dict(self.BASE))
        self.assertFalse(v["blocked"], "持平不得阻断")
        self.assertTrue(v["ok"])
        self.assertTrue(v["reports"], "p0 应产出报告行")
        self.assertEqual(v["reports"][0]["report"], "P0=6（基线 6，自引入 0）")

    def test_T13_reverse_p0_rises_blocks(self):
        """反例：p0 上升 + block_on_new_defects=true ⇒ 必须阻断。

        如果这个值改了，**delta_verdict()** 的 blocked/ok 应该跟着变。
        """
        v = LC.delta_verdict(self.cfg, dict(self.BASE), {"p0": 7, "p1": 2, "p2": 1})
        self.assertTrue(v["blocked"], "自引入 P0 却未阻断——门禁未接线")
        self.assertFalse(v["ok"], "阻断时 ok 必须为 False")
        self.assertEqual(v["reason"], "new_defects")
        self.assertEqual([i["metric"] for i in v["increased"]], ["p0"])
        self.assertEqual(v["reports"][0]["report"], "P0=7（基线 6，自引入 1）")

    def test_T13_reverse_block_switch_off_warns(self):
        """反例：block_on_new_defects=false ⇒ 不阻断，但必须告警说明"只提示"。

        如果这个值改了，**delta_verdict()** 的 blocked 应该跟着变。
        不得把"开关关了"伪装成"没有新缺陷"。
        """
        t = patch_text(HARNESS_TEXT, "  block_on_new_defects: true",
                       "  block_on_new_defects: false")
        notes = []
        v = LC.delta_verdict(cfg_of(t), dict(self.BASE),
                             {"p0": 7, "p1": 2, "p2": 1}, notes)
        self.assertFalse(v["blocked"], "开关关闭时不阻断")
        self.assertTrue(v["ok"], "不阻断时 ok 为 True")
        self.assertTrue(v["increased"], "新缺陷仍然被**记录**下来（只是不阻断）")
        self.assertTrue(any("只提示不阻断" in n for n in notes),
                        f"必须写明关闭此开关等于允许边改边坏，实得 notes={notes}")


class TestT14DeltaVerdictMissing(_Base):
    """T14：delta_gate.miss_needs_human_review —— 缺数不得按 0 处理。"""

    def test_T14_positive_complete_data(self):
        v = LC.delta_verdict(self.cfg, {"p0": 6, "p1": 2, "p2": 1},
                             {"p0": 6, "p1": 2, "p2": 1})
        self.assertEqual(v["reason"], "", "数据齐全时不得走缺数分支")
        self.assertFalse(v["blocked"])
        self.assertTrue(v["ok"])

    def test_T14_reverse_missing_baseline_p2(self):
        """反例：基线缺 p2 ⇒ 必须返回 missing_needs_human_review，**不按 0 补齐**。

        如果这个值改了，**delta_verdict()** 的 reason/blocked 应该跟着变。
        按 0 补齐会把"没测到"美化成"没有缺陷"——机器 MISS 未经复核不得计入。
        """
        v = LC.delta_verdict(self.cfg, {"p0": 6, "p1": 2},
                             {"p0": 6, "p1": 2, "p2": 1})
        self.assertEqual(v["reason"], "missing_needs_human_review")
        self.assertTrue(v["blocked"], "缺数未复核必须阻断")
        self.assertFalse(v["ok"])
        self.assertTrue(any("不按 0 补齐" in n for n in v["notes"]),
                        f"必须写明不按 0 补齐，实得 notes={v['notes']}")

    def test_T14_reverse_switch_off_falls_back_to_zero(self):
        """反例：miss_needs_human_review=false ⇒ 走"按 0 补齐"路径（行为确实不同）。

        如果这个值改了，**delta_verdict()** 是否阻断应该跟着变——
        证明上面那条反例判的是这条配置，而不是"碰巧返回"。
        """
        t = patch_text(HARNESS_TEXT, "  miss_needs_human_review: true",
                       "  miss_needs_human_review: false")
        v = LC.delta_verdict(cfg_of(t), {"p0": 6, "p1": 2},
                             {"p0": 6, "p1": 2, "p2": 1})
        self.assertNotEqual(v["reason"], "missing_needs_human_review",
                            "开关关闭后不应再走人工复核分支")
        self.assertTrue(any(i["metric"] == "p2" for i in v["increased"]),
                        "关闭开关后缺失项按 0 处理 ⇒ 基线 p2 记 0、当前 1 ⇒ 计为上升")
        self.assertEqual([i["baseline"] for i in v["increased"] if i["metric"] == "p2"], [0],
                         "证实缺的那一项真的被按 0 补齐了（口径与人工复核分支不同）")
        self.assertTrue(v["blocked"], "按 0 补齐后 p2 0→1 属自引入上升，仍应阻断")


# ══════════════════════ T15–T17：空间审计与图注 ══════════════════════
class TestT15SpatialAudit(_Base):
    """T15：delta_gate.insert_spatial_audit —— 插入物空间避让审计。"""

    def test_T15_positive_zero_overlap(self):
        ok, msg, n = LC.spatial_audit_check(
            self.cfg, {"summary": {"geo_new_overlap": 0, "geo_inherited": 3}})
        self.assertTrue(ok, f"新增重叠 0 应通过，实得：{msg}")
        self.assertEqual(n, 0)

    def test_T15_reverse_three_overlaps(self):
        """反例：geo_new_overlap=3 ⇒ 必须判不通过（GEO-003）。

        如果这个值改了，**spatial_audit_check()** 的判定应该跟着变。
        """
        ok, msg, n = LC.spatial_audit_check(
            self.cfg, {"summary": {"geo_new_overlap": 3, "geo_inherited": 3}})
        self.assertFalse(ok, "新增重叠 3 处却判通过——空间避让审计未接线")
        self.assertEqual(n, 3)
        self.assertIn("GEO-003", msg)

    def test_T15_reverse_missing_summary_section(self):
        """反例：lint 报告缺 summary 段 ⇒ 判不通过（拿不出报告 ≠ 没问题）。"""
        ok, msg, n = LC.spatial_audit_check(self.cfg, {"geo_new_overlap": 0})
        self.assertFalse(ok, "缺 summary.geo_new_overlap 却判通过——无法判定即未做")
        self.assertIsNone(n)

    def test_T15_reverse_no_lint_report_is_not_ok(self):
        ok, msg, _ = LC.spatial_audit_check(self.cfg, None)
        self.assertFalse(ok, "声明要审计却拿不出报告，按**未做**阻断")

    def test_T15_reverse_switch_off(self):
        """反例：insert_spatial_audit=false ⇒ 不判定且写明（不得假装判了）。"""
        t = patch_text(HARNESS_TEXT, "  insert_spatial_audit: true",
                       "  insert_spatial_audit: false")
        notes = []
        ok, msg, n = LC.spatial_audit_check(cfg_of(t), None, notes)
        self.assertTrue(ok, "关闭时不阻断")
        self.assertIsNone(n, "关闭时不做判定，不产出数据")
        self.assertIn("未要求", msg, "关闭时必须写明是未要求，而不是「已审计通过」")
        self.assertTrue(any("insert_spatial_audit=false" in x for x in notes),
                        "必须写明未做审计的原因")


class TestT16CaptionCheck(_Base):
    """T16：delta_gate.caption_missing_element_policy —— 图注要素缺项挂账。"""

    ALL = ["对象", "来源与许可", "教学意义"]

    def test_T16_positive_all_elements(self):
        r = LC.caption_check(self.cfg, list(self.ALL))
        self.assertTrue(r["ok"], f"三要素齐应无 todo，实得：{r['todo']}")
        self.assertEqual(r["todo"], [])
        self.assertTrue(r["executed"], "explicit_todo 有执行器，应标记为已执行")
        self.assertEqual(r["base_elements"], self.ALL,
                         "要素清单应来自 visual-rules.yaml#caption_base_elements（唯一源）")

    def test_T16_reverse_missing_source_element(self):
        """反例：缺「来源与许可」⇒ 必须挂账（禁静默省略）。

        如果这个值改了，**caption_check()** 的 missing/todo 应该跟着变。
        """
        r = LC.caption_check(self.cfg, ["对象", "教学意义"])
        self.assertFalse(r["ok"], "缺要素却判合格——图注挂账纪律未接线")
        self.assertEqual(r["missing"], ["来源与许可"])
        self.assertEqual(r["todo"], ["来源与许可"], "缺项必须显式挂账")

    def test_T16_reverse_unknown_policy_has_no_executor(self):
        """反例：policy 改成别的值 ⇒ 必须 executed=False 且写明无执行器。

        如果这个值改了，**caption_check()** 应从"挂账"翻转为"不假装处置"。
        """
        t = patch_text(HARNESS_TEXT, 'caption_missing_element_policy: "explicit_todo"',
                       'caption_missing_element_policy: "silent_omit"')
        notes = []
        r = LC.caption_check(cfg_of(t), ["对象", "教学意义"], notes)
        self.assertFalse(r["executed"], "未知 policy 必须标记为未执行")
        self.assertEqual(r["todo"], [], "无执行器时不得产出挂账清单")
        self.assertTrue(any("有执行器" in n and "未挂账" in n for n in notes),
                        f"必须写明当前仅 'explicit_todo' 有执行器且缺项未挂账，实得 notes={notes}")
        self.assertEqual(r["missing"], ["来源与许可"],
                         "缺项仍然要**报出来**（不挂账 ≠ 不报告）")


class TestT17ImageCaption(_Base):
    """T17：delta_gate.image_caption_requires_reading —— 判读留痕强制。"""

    def test_T17_positive_with_read_log(self):
        ok, msg = LC.image_caption_check(self.cfg, "已逐张判读：图1…")
        self.assertTrue(ok, f"有判读记录应通过，实得：{msg}")

    def test_T17_reverse_no_read_log(self):
        """反例：无 read_log 且配置为 true ⇒ 必须判不通过。

        如果这个值改了，**image_caption_check()** 的判定应该跟着变。
        诚实边界：强制的是**留痕**，不是判读正确性（后者只能人复核）。
        """
        ok, msg = LC.image_caption_check(self.cfg, "")
        self.assertFalse(ok, "无判读记录却判通过——判读留痕强制未接线")
        self.assertIn("判读记录", msg)

    def test_T17_reverse_switch_off(self):
        """反例：配置改 false ⇒ 不强制（且写明）。"""
        t = patch_text(HARNESS_TEXT, "  image_caption_requires_reading: true",
                       "  image_caption_requires_reading: false")
        notes = []
        ok, msg = LC.image_caption_check(cfg_of(t), "", notes)
        self.assertTrue(ok, "关闭时不强制")
        self.assertTrue(any("不强制" in n for n in notes),
                        f"必须写明未强制的原因，实得 notes={notes}")


# ══════════════════════════ T18–T19：默认档 ══════════════════════════
class TestT18IntakeTemplate(_Base):
    """T18：由 loop_b.defaults 生成 intake 待确认模板。"""

    FIVE = ("audience", "periods", "template", "scope", "acceptance")

    def test_T18_positive_all_suggested(self):
        tpl = LC.intake_template_from_defaults(self.cfg)
        for k in self.FIVE:
            self.assertEqual(tpl[k]["status"], "suggested",
                             f"{k} 的 status 必须是 suggested（不得冒充用户确认）")
        statuses = {tpl[k]["status"] for k in self.FIVE}
        self.assertNotIn("confirmed", statuses,
                        "**任何一项都不得是 confirmed**——这是"
                        "「不得用仓库默认值冒充用户确认」的机器保证")
        self.assertIn("suggested ≠ confirmed", tpl["_note"])

    def test_T18_positive_audience_from_yaml(self):
        tpl = LC.intake_template_from_defaults(self.cfg)
        d = self.cfg["loop_b"]["defaults"]
        self.assertEqual(tpl["audience"]["value"], d["audience"])
        self.assertEqual(tpl["periods"]["value"], d["hours_per_session"])
        self.assertEqual(tpl["scope"]["value"], d["scope"])

    def test_T18_reverse_audience_change_propagates(self):
        """反例：改 yaml 的 defaults.audience ⇒ 生成模板的 audience.value 必须跟着变。

        如果这个值改了，**intake_template_from_defaults()** 的输出应该跟着变
        ——这是"默认档真被消费"而不是"把默认值打印出来"的判据。
        """
        t = patch_text(HARNESS_TEXT, '    audience: "职业本科与本科生（默认）',
                       '    audience: "研究生（反例）')
        tpl = LC.intake_template_from_defaults(cfg_of(t))
        self.assertTrue(tpl["audience"]["value"].startswith("研究生（反例）"),
                        "改了默认受众但生成的模板没变——默认档未被消费")
        self.assertEqual(tpl["audience"]["status"], "suggested",
                         "值变了也仍然是 suggested，不得自动升 confirmed")
        self.assertEqual(tpl["audience"]["source"],
                         "harness.yaml#loop_b.defaults.audience")

    def test_T18_reverse_empty_default_template_is_flagged(self):
        """反例：default_template 为 null ⇒ 模板项必须显式报"须用户指定"。

        为什么单测这条：v3.18.0 把该键置 null 以解耦个人机器路径，
        若此处静默沿用旧值/旧路径，等于用包内默认值冒充用户资产。
        """
        notes = []
        tpl = LC.intake_template_from_defaults(self.cfg, notes)
        self.assertIsNone(tpl["template"]["value"])
        self.assertIn("须用户指定", tpl["template"]["note"])
        self.assertTrue(any("default_template" in n and "空" in n for n in notes),
                        f"显式为空必须留痕，实得 notes={notes}")


class TestT19DefaultsRefs(_Base):
    """T19：默认档引用的包内文件必须存在（防引用悬空）。"""

    def test_T19_positive_all_refs_exist(self):
        ok, missing, present = LC.defaults_ref_check(self.cfg)
        self.assertTrue(ok, f"包内引用文件应全部存在，缺：{missing}")
        self.assertEqual(missing, [])
        self.assertEqual(sorted(k for k, _ in present),
                         sorted(LC.defaults_ref_keys()),
                         "五个 *_ref 键都应做存在性核验")

    def test_T19_reverse_dangling_ref(self):
        """反例：把 profile_ref 改成不存在的文件名 ⇒ missing 必须含该项。

        如果这个值改了，**defaults_ref_check()** 的 missing 应该跟着变
        ——改了文件名不会静默失效（本包吃过引用悬空的亏）。
        """
        t = patch_text(HARNESS_TEXT,
                       'profile_ref: "references/course-profile-defaults.md"',
                       'profile_ref: "references/no-such-defaults.md"')
        ok, missing, present = LC.defaults_ref_check(cfg_of(t))
        self.assertFalse(ok, "引用悬空却判通过——存在性核验未接线")
        self.assertEqual([k for k, _ in missing], ["profile_ref"])
        self.assertNotIn("profile_ref", [k for k, _ in present])

    def test_T19_reverse_second_dangling_ref(self):
        """反例：换一个键（audience_schema）悬空 ⇒ 同样要抓出来（不是只查一个键）。"""
        t = patch_text(HARNESS_TEXT,
                       'audience_schema: "references/audience-profile-schema.yaml"',
                       'audience_schema: "references/gone.yaml"')
        ok, missing, _ = LC.defaults_ref_check(cfg_of(t))
        self.assertFalse(ok)
        self.assertEqual([k for k, _ in missing], ["audience_schema"])


# ══════════════════════════ T20：取值函数 ══════════════════════════
class TestT20ConfigGetters(_Base):
    """T20：geo_baseline_required / retrieval_budget / round_review_cfg /
    delta_gate_cfg / loop_a_batch_cfg 的取值必须来自 yaml。"""

    def test_T20_positive_values_from_yaml(self):
        # 这两个是**返回标量**的函数：直接断言，不做形态适配（接口已定，见
        # TestScalarReturnContract——形态错了由那里的 assertIsInstance 红，此处不抹平）。
        self.assertIs(LC.geo_baseline_required(self.cfg), True)
        self.assertEqual(LC.retrieval_budget(self.cfg), 30)
        rr = LC.round_review_cfg(self.cfg)
        self.assertTrue(rr["required"])
        self.assertEqual(rr["required_items"], 6)
        self.assertEqual(rr["invalidation"], "sha256")
        self.assertTrue(rr["silent_is_not_approval"])
        self.assertTrue(rr["partial_accept_freezes_only_named"])
        self.assertTrue(rr["rework_stays_in_round"])
        g = LC.delta_gate_cfg(self.cfg)
        self.assertTrue(g["baseline_required"])
        self.assertTrue(g["block_on_new_defects"])
        self.assertTrue(g["miss_needs_human_review"])
        self.assertTrue(g["insert_spatial_audit"])
        self.assertTrue(g["image_caption_requires_reading"])
        self.assertEqual(g["caption_missing_element_policy"], "explicit_todo")
        self.assertEqual(g["report_format"], "P0=6（基线 6，自引入 0）")
        la = LC.loop_a_batch_cfg(self.cfg)
        self.assertTrue(la["confirm_before_each_batch"])
        self.assertEqual(la["patch_discipline"], "minimal")
        self.assertEqual(la["regression_required"],
                         ["ensure_settings", "test_harness", "test_five_gates"])

    def test_T20_reverse_geo_baseline_required(self):
        """反例：defaults.geo_baseline_required 改 false ⇒ 返回值跟着变。

        如果这个值改了，**geo_baseline_required()** 应返回 False
        （下游据此判定成品 lint 是否必配 --geo-baseline）。
        """
        t = patch_text(HARNESS_TEXT, "    geo_baseline_required: true",
                       "    geo_baseline_required: false")
        self.assertIs(LC.geo_baseline_required(cfg_of(t)), False)

    def test_T20_reverse_retrieval_budget(self):
        """反例：budgets.retrieval_budget_per_round 30→12 ⇒ 返回值跟着变。"""
        t = patch_text(HARNESS_TEXT, "    retrieval_budget_per_round: 30",
                       "    retrieval_budget_per_round: 12")
        self.assertEqual(LC.retrieval_budget(cfg_of(t)), 12)

    def test_T20_reverse_round_review_items(self):
        """反例：round_review.required_items 6→4 ⇒ round_review_cfg 跟着变。"""
        t = patch_text(HARNESS_TEXT, "    required_items: 6", "    required_items: 4")
        rr = LC.round_review_cfg(cfg_of(t))
        self.assertEqual(rr["required_items"], 4)
        self.assertEqual(LC.round_review_cfg(self.cfg)["required_items"], 6,
                         "同一函数在原文配置下必须仍是 6（证明不是常量）")

    def test_T20_reverse_delta_gate_policy(self):
        """反例：caption_missing_element_policy 改成别的值 ⇒ delta_gate_cfg 跟着变。"""
        t = patch_text(HARNESS_TEXT, 'caption_missing_element_policy: "explicit_todo"',
                       'caption_missing_element_policy: "warn_only"')
        g = LC.delta_gate_cfg(cfg_of(t))
        self.assertEqual(g["caption_missing_element_policy"], "warn_only")

    def test_T20_reverse_loop_a_batch_discipline(self):
        """反例：loop_a.patch_discipline 改值 ⇒ loop_a_batch_cfg 跟着变。"""
        t = patch_text(HARNESS_TEXT, 'patch_discipline: "minimal"',
                       'patch_discipline: "thorough"')
        la = LC.loop_a_batch_cfg(cfg_of(t))
        self.assertEqual(la["patch_discipline"], "thorough")
        self.assertFalse(la["confirm_before_each_batch"] is None)


# ══════════════════════════ T21：回落可见性 ══════════════════════════
class TestT21FallbackVisibility(_Base):
    """T21：缺键/空值一律**告警 + 显式回落**，禁止静默回落。"""

    def test_T21_positive_no_fallback_when_config_complete(self):
        """正例：配置齐全时，全量跑一遍判定应**零回落**。

        这条同时是"34 键已全部接线"的机器证明：只要还有一个键没被读到，
        对应函数就会走回落并产生 note。
        """
        notes = []
        LC.enabled(self.cfg, "a", notes)
        LC.enabled(self.cfg, "b", notes)
        LC.state_path(self.cfg, self.ws, "a", notes)
        LC.state_path(self.cfg, self.ws, "b", notes)
        LC.coexist_guard(self.cfg, self.ws, notes)
        LC.single_writer_check(self.cfg, "team-lead", notes)
        LC.original_readonly(self.cfg, notes)
        LC.retrieval_budget(self.cfg, notes)
        LC.round_review_cfg(self.cfg, notes)
        LC.geo_baseline_required(self.cfg, notes)
        LC.delta_gate_cfg(self.cfg, notes)
        LC.loop_a_batch_cfg(self.cfg, notes)
        self.assertEqual(notes, [], f"配置齐全却出现回落/告警：{notes}")

    def test_T21_reverse_deleted_budget_key_falls_back_visibly(self):
        """反例：删掉 retrieval_budget_per_round ⇒ 必须回落内置值 30 且**写进 notes**。

        如果这个值没了，**retrieval_budget()** 应回落 30 并留痕；
        静默回落 = "看起来有护栏、实际不设防"（本包已多次吃这个亏）。
        """
        t = drop_line(HARNESS_TEXT, "    retrieval_budget_per_round: 30\n")
        notes = []
        v = LC.retrieval_budget(cfg_of(t), notes)
        self.assertEqual(v, 30, "缺键时应回落内置值 30")
        self.assertTrue(notes, "回落必须可见，不得静默（标量接口下 notes 是唯一载体）")
        self.assertTrue(any("回落内置值" in n and "30" in n for n in notes),
                        f"note 必须写明回落到哪个值，实得 notes={notes}")

    def test_T21_reverse_deleted_state_file_falls_back_visibly(self):
        """反例：删掉 loop_a.state_file ⇒ 路径回落到 <工作区> 内置路径且留痕。"""
        t = drop_line(HARNESS_TEXT,
                      '  state_file: "<包>/.workbuddy/loopA_state.json"\n')
        notes = []
        p, _ = LC.state_path(cfg_of(t), self.ws, "a", notes)
        self.assertEqual(p, os.path.join(self.ws, ".workbuddy", "loopA_state.json"),
                         "缺键时应回落到工作区内置路径")
        self.assertTrue(any("回落内置值" in n for n in notes),
                        f"路径回落必须留痕，实得 notes={notes}")

    def test_T21_reverse_empty_value_counts_as_missing(self):
        """反例：把 single_writer 置空 ⇒ 按缺失回落 team-lead 且留痕。

        为什么"空值也算缺失"：yaml 里写 `key: null` 与不写这个键，对调用方是同一件事
        （都没有可用值），但意图不同；统一按缺失处理并标明"显式为空"，
        避免把"忘了配"伪装成"有意留空"。
        """
        t = patch_text(HARNESS_TEXT, 'single_writer: "team-lead"', 'single_writer: ""')
        notes = []
        w = LC.single_writer(cfg_of(t), notes)
        self.assertEqual(w, "team-lead", "空值应回落内置写者")
        self.assertTrue(any("为空" in n and "回落内置值" in n for n in notes),
                        f"必须写明是「已配置但为空」，实得 notes={notes}")


# ══════════════════════════ T22：占位符解析 ══════════════════════════
class TestT22Placeholders(_Base):
    """T22：resolve_placeholders —— 唯一源（harness.py 已转调本函数）。"""

    def test_T22_positive_both_placeholders(self):
        self.assertEqual(LC.resolve_placeholders("<包>/config/x.yaml", self.ws),
                         os.path.join(LC.PKG, "config", "x.yaml"))
        self.assertEqual(LC.resolve_placeholders("<工作区>/a.pptx", self.ws),
                         os.path.join(self.ws, "a.pptx"))

    def test_T22_reverse_no_placeholder_returns_as_is(self):
        """反例：不含占位符的路径原样返回（不得误替换、不得加前缀）。"""
        p = "/abs/path/x.yaml"
        self.assertEqual(LC.resolve_placeholders(p, self.ws), p)
        self.assertEqual(LC.resolve_placeholders("relative/y.yaml", self.ws),
                         "relative/y.yaml")


# ══════════════ 返回契约：标量接口的形态守卫 ══════════════
class TestScalarReturnContract(_Base):
    """返回**标量**的 6 个取值函数必须真的是标量——不得是 (值, 是否回落) 元组。

    为什么单列一类（v3.20.0 实测的两个缺陷都出在这里）：
      · `retrieval_budget` 返回元组 ⇒ `retrieval_check` 里 `used > limit` 直接
        TypeError ⇒ 检索预算这条判据**完全没接上**（D1）；
      · `image_caption_requires_reading` 返回元组 ⇒ `if not required:` 恒为假
        ⇒ yaml 里把开关改 false，代码照样强制判读留痕（D2）。
    共同机理：调用点写的是 `if not f(...)` / `used > f(...)`，而**非空元组恒为真**、
    且不能与数值比较 ⇒ 开关形同虚设。这类缺陷靠"读代码"很难发现，
    只能靠形态断言在测试阶段就红。

    ⚠ 本类一律**直接断言**，不做任何形态适配：曾经为接口不稳定期加过
      `unpack()`（同时接受标量与元组），它恰好会把本类要抓的缺陷抹平——
      已被删除，接口已定，不允许再留"让断言永远为真"的旁路。
    """

    def test_scalar_shape_of_all_six_getters(self):
        """正例：6 个取值函数的返回类型必须精确（是否回落一律走 notes）。"""
        self.assertIsInstance(LC.enabled(self.cfg, "a"), bool, "enabled → bool")
        self.assertIsInstance(LC.enabled(self.cfg, "b"), bool, "enabled → bool")
        self.assertIsInstance(LC.original_readonly(self.cfg), bool,
                              "original_readonly → bool")
        self.assertIsInstance(LC.geo_baseline_required(self.cfg), bool,
                              "geo_baseline_required → bool")
        self.assertIsInstance(LC.image_caption_requires_reading(self.cfg), bool,
                              "image_caption_requires_reading → bool")
        self.assertIsInstance(LC.single_writer(self.cfg), str, "single_writer → str")
        budget = LC.retrieval_budget(self.cfg)
        self.assertIsInstance(budget, int, "retrieval_budget → int")
        self.assertNotIsInstance(budget, bool,
                                 "retrieval_budget 不能是 bool（bool 是 int 的子类，"
                                 "`used > True` 会静默把上限当成 1）")

    def test_D1_guard_retrieval_check_compares_scalar(self):
        """D1 守卫：`used > limit` 必须能比——返回元组会直接 TypeError。

        如果 `retrieval_budget` 退回元组形态，**retrieval_check()** 会从"判超预算"
        变成"抛异常"，本条立刻红（不再需要靠人眼在 `--self-check` 输出里发现）。
        """
        ok, msg = LC.retrieval_check(self.cfg, 31)
        self.assertIsInstance(ok, bool, "retrieval_check 第一返回值应是 bool")
        self.assertFalse(ok, "31 > 30 应判超预算")
        self.assertIn("30", msg, "上限值应来自配置而不是把元组打印出来")
        self.assertTrue(LC.retrieval_check(self.cfg, 30)[0], "30 ≤ 30 应通过")

    def test_D2_guard_image_caption_switch_off_is_reachable(self):
        """D2 守卫：`image_caption_requires_reading=false` 这条分支必须**真能走到**。

        如果这个函数退回元组形态，**image_caption_check()** 里 `if not required:`
        永不成立 ⇒ 配置关不掉、note 也写不出来（"看起来有开关，实际没有"）。
        本条同时断言"读到 False"与"false 分支真的被走到（放行 + 留痕）"。
        """
        t = patch_text(HARNESS_TEXT, "  image_caption_requires_reading: true",
                       "  image_caption_requires_reading: false")
        cfg_off = cfg_of(t)
        self.assertIs(LC.image_caption_requires_reading(cfg_off), False,
                      "配置改 false 后必须读到 False（读到元组 ⇒ 开关关不掉）")
        notes = []
        ok, msg = LC.image_caption_check(cfg_off, "", notes)
        self.assertTrue(ok, "关闭时不强制——若无判读记录仍判失败，说明 false 分支没走到")
        self.assertEqual(msg, "", "关闭时不产出失败原因")
        self.assertTrue(any("不强制" in n for n in notes),
                        f"false 分支必须写明未强制，实得 notes={notes}")

    def test_D2_guard_switch_on_still_blocks(self):
        """D2 反向：开关为 true 时**必须**强制——不能因为修了 false 分支就全放行。"""
        self.assertIs(LC.image_caption_requires_reading(self.cfg), True)
        ok, msg = LC.image_caption_check(self.cfg, "")
        self.assertFalse(ok, "配置为 true 且无判读记录时必须判失败")
        self.assertIn("判读记录", msg)


# ══════════════ 双向验证：破坏被测实现 ⇒ 反例必须翻转 ══════════════
class TestImplementationBreak(_Base):
    """把 loop_contract 的**判据实现**破坏掉，确认上面的正/反例真的在测东西。

    为什么必须有这一类：只改 yaml 的反例仍可能恒真——
    若判定根本没走被测函数（例如被上层短路、或值来自另一个常量），
    改 yaml 与不改 yaml 结果一样，反例却是绿的。
    这里把实现改成"硬编码/恒真"，若判定结果**不翻转**，就说明那条反例是恒真断言。
    """

    def test_break_enabled_flips_T1_reverse(self):
        """破坏 enabled ⇒ 恒真 ⇒ T1 反向例（yaml=false）的判定必须翻成 True。"""
        t = patch_text(HARNESS_TEXT, "loop_b:\n  enabled: true",
                       "loop_b:\n  enabled: false")
        cfg_b = cfg_of(t)
        self.assertFalse(LC.enabled(cfg_b, "b"), "前提：未破坏时应判 False")
        orig = LC.enabled
        # 破坏方式按**接口契约**来：enabled 必须返回标量 bool，
        # 故假实现也返回标量 True（不再伪造“同形状”，那是给形态迁移留的旁路）。
        LC.enabled = lambda cfg, loop, notes=None: True
        try:
            self.assertTrue(LC.enabled(cfg_b, "b"),
                            "实现被硬编码后判定未翻转——T1 反例没经过 enabled()，是恒真断言")
        finally:
            LC.enabled = orig
        self.assertFalse(LC.enabled(cfg_b, "b"), "复原后必须重新转红")

    def test_break_retrieval_budget_flips_T9_reverse(self):
        """破坏 retrieval_budget ⇒ 恒返回 30 ⇒ 上限 5、used 6 的反例必须翻转。"""
        t = patch_text(HARNESS_TEXT, "    retrieval_budget_per_round: 30",
                       "    retrieval_budget_per_round: 5")
        cfg5 = cfg_of(t)
        self.assertFalse(LC.retrieval_check(cfg5, 6)[0], "前提：未破坏时应判超预算")
        orig = LC.retrieval_budget
        LC.retrieval_budget = lambda cfg, notes=None: 30   # 写死成内置值 = "配置不接线"
        try:
            self.assertTrue(LC.retrieval_check(cfg5, 6)[0],
                            "预算被写死后判定未翻转——T9 反例没经过 retrieval_budget()")
        finally:
            LC.retrieval_budget = orig
        self.assertFalse(LC.retrieval_check(cfg5, 6)[0], "复原后必须重新转红")

    def test_break_format_slots_flips_T11_positive(self):
        """破坏 _format_slots ⇒ 恒返回 None ⇒ T11 正例必须翻成不合规。"""
        self.assertTrue(LC.render_delta_report(self.cfg, 6, 6)["ok"],
                        "前提：未破坏时应判合规")
        orig = LC._format_slots
        LC._format_slots = lambda fmt, notes: (None, 0)
        try:
            r = LC.render_delta_report(self.cfg, 6, 6)
            self.assertFalse(r["ok"], "格式渲染被破坏后判定未翻转——T11 正例没经过 _format_slots()")
            self.assertEqual(r["text"], "")
        finally:
            LC._format_slots = orig
        self.assertTrue(LC.render_delta_report(self.cfg, 6, 6)["ok"], "复原后必须归绿")

    def test_break_loop_a_batch_cfg_flips_T6_reverse(self):
        """破坏 loop_a_batch_cfg ⇒ 清单恒为两项 ⇒ 缺第三项的反例必须翻转。"""
        self.assertFalse(LC.regression_check(self.cfg, ["ensure_settings",
                                                        "test_harness"])[0],
                         "前提：未破坏时应判缺项")
        orig = LC.loop_a_batch_cfg
        LC.loop_a_batch_cfg = lambda cfg, notes=None: {
            "confirm_before_each_batch": True, "patch_discipline": "minimal",
            "regression_required": ["ensure_settings", "test_harness"]}
        try:
            ok, missing, _, _ = LC.regression_check(self.cfg,
                                                    ["ensure_settings", "test_harness"])
            self.assertTrue(ok, "清单被写死后判定未翻转——T6 反例没经过 loop_a_batch_cfg()")
            self.assertEqual(missing, [])
        finally:
            LC.loop_a_batch_cfg = orig
        self.assertFalse(LC.regression_check(self.cfg, ["ensure_settings",
                                                        "test_harness"])[0],
                         "复原后必须重新转红")

    def test_break_num_slot_flips_T11_positive(self):
        """破坏 _NUM_SLOT（退化成裸 \\d+）⇒ 指标名 P0 的 0 被当数值位 ⇒ 渲染必崩。

        这条同时守住注释里那处**已踩过的坑**：裸 r"\\d+" 会把 "P0" 的 0 也当占位符，
        模板变 4 槽、渲染抛 "Replacement index 3 out of range"。
        """
        import re as _re
        orig = LC._NUM_SLOT
        LC._NUM_SLOT = _re.compile(r"\d+")
        try:
            r = LC.render_delta_report(self.cfg, 6, 6)
            self.assertFalse(r["ok"],
                             "_NUM_SLOT 退化后判定未翻转——说明数值位识别没被真正用到")
        finally:
            LC._NUM_SLOT = orig
        self.assertTrue(LC.render_delta_report(self.cfg, 6, 6)["ok"], "复原后必须归绿")


class TestFallbackTableInvisibility(_Base):
    """护栏的护栏：内置回落表**不得**把已接线的键刷成"有读取者"。

    为什么单列一类：ensure_settings 第 18 项（死配置巡检）靠 AST 找真实读取点，
    只认 `x.get("键")` / `x["键"]` / 字典字面量键三种形态。
    若有人把 `_FALLBACK` 改回**字典字面量**，或把读取点写成"键名当普通实参"的
    helper 调用（形如 `_val(node, 键名, ...)`），AST 就收集不到 ⇒
    32 个键会被**误判成仍然没人读**（白接线），或反过来被回落表刷绿（假绿）。
    本类把这两条都钉死。
    """

    def _read_points(self, src):
        """从源码里按同样三种形态收集读取点键名（与第 18 项同一口径）。"""
        import ast
        pts = set()
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                pts.add(node.args[0].value)
            if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                pts.add(node.slice.value)
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        pts.add(k.value)
        return pts

    def test_fallback_table_is_not_a_dict_literal(self):
        """正例：`_FALLBACK` 的声明处**不得是字典字面量**。

        ⚠ 为什么必须用 AST 判据而不是字符串匹配：第 18 项收集的第③种读取点形态是
          **字典字面量的字符串键**。断言源码里含 `_FALLBACK = (` 这种字符串写法，
          对 `_FALLBACK = dict([...])`、`_FALLBACK = {...}` 这些同样危险（或更危险）
          的改法一律放行 ⇒ 字符串断言是假绿。只有按 AST 看声明节点的**语法形态**
          才是真判据：不是 ast.Dict ⇒ 不会被当读取点收集。
        """
        with open(LC_PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertIs(_fallback_literal_is_dict(src), False,
                      "_FALLBACK 声明处不得是字典字面量（会被第 18 项误判为「有读取者」）")
        # 运行时查表仍应可用：声明处是列表，运行时转成 dict（两者不可合二为一）
        self.assertEqual(dict(LC._FALLBACK), LC._FB,
                         "_FB 必须是 _FALLBACK 的字典视图（否则回落取值对不上）")

    def test_fallback_table_guard_is_sensitive(self):
        """反例：把回落表改成**字典字面量** ⇒ 上面那条守卫必须抓出来（转红）。

        如果这个值改了，**第 18 项死配置巡检**的判定应该跟着变——
        回落表自己就把 32 个键刷成"有读取者"，真正的读取点被删掉也看不出来。
        本条用内存里的源码副本验证守卫的敏感性，不落盘、不动 loop_contract.py。
        """
        with open(LC_PATH, encoding="utf-8") as f:
            src = f.read()
        i = src.index("_FALLBACK = [")
        j = src.index("\n]\n", i) + 3
        dict_src = (src[:i] + "_FALLBACK = {\n" +
                    "".join(f'    "{k}": {v!r},\n' for k, v in LC._FALLBACK) +
                    "}\n" + src[j:])
        self.assertIs(_fallback_literal_is_dict(dict_src), True,
                      "改成字典字面量后守卫未报出——说明这条守卫是恒真断言，没在测形态")

    def test_deleted_yaml_key_falls_back_and_warns(self):
        """反例：整行删掉 loop_b.single_writer ⇒ 回落内置值 team-lead 且**留痕**。"""
        t = drop_line(HARNESS_TEXT,
                      '  single_writer: "team-lead"      '
                      '# 单写者：成员不得直接写状态文件，回传由主理人汇编落盘\n')
        notes = []
        w = LC.single_writer(cfg_of(t), notes)
        self.assertEqual(w, "team-lead", "整行删掉后应回落内置写者")
        self.assertTrue(notes, "回落必须可见，不得静默")
        self.assertTrue(any("回落内置值" in n for n in notes),
                        f"必须写明回落，实得 notes={notes}")

    def test_read_point_exists_and_is_what_counts(self):
        """正例 + 反例：键被认账靠的是**真实读取点**，不是回落表里出现过这个名字。

        构造方式：把 `lb.get("single_writer")` 这个读取点在源码副本里改掉，
        键就再无读取点 ⇒ 巡检口径下它必须"消失"——证明刷绿的是读取点而非回落表。
        """
        with open(LC_PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("single_writer", src, "源码里应出现 single_writer 键名")
        self.assertIn("single_writer", self._read_points(src),
                      "loop_contract.py 必须有 single_writer 的真实读取点")
        broken = src.replace('.get("single_writer")', '.get("__broken__")', 1)
        self.assertNotEqual(broken, src, "反例构造失败：读取点未命中")
        self.assertNotIn("single_writer", self._read_points(broken),
                         "破坏读取点后该键仍在读取点集合里——说明认账靠的不是读取点，"
                         "而是回落表/常量（那正是会把死配置刷绿的写法）")


class TestYamlUntouched(_Base):
    """收尾：包内真实 harness.yaml 必须与开跑前逐字节一致。"""

    def test_harness_yaml_sha256_unchanged(self):
        with open(HARNESS_YAML, "rb") as f:
            after = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(after, _SHA_BEFORE,
                         "config/harness.yaml 内容被改动——反例必须只改内存副本")


if __name__ == "__main__":
    unittest.main(verbosity=2)

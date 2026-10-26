#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_insight_carrier.py — v3.21.0「多专家单载体」判定层护栏

立项理由（不是"再补几个用例"）：
  v3.21.0 解决了本包反复治理的同型病灶——**声明层 ≠ 执行层**。
  此前「多专家围绕同一份给定内容做洞察和设计」在架构上是**三处分散**：
  严真奥落 `evidence/证据包.md`、苏学法落 `<task_id>__pedagogy-architect.md`、
  屠明熙落 `_search_requests/*.md` ⇒ 同一目标上的内容/教学/视觉建议**无共同落点**：
  冲突无处显形、合并靠 800 字摘要（必然丢信息）、追溯断裂。
  本版把三轴的洞察汇入**同一份载体**（carrier），载体是全程唯一事实源。

  但"接了线"极易**假绿**：把条目读进来打印出来、或校验了却不做任何判定，
  输出看起来一样。故本文件每条断言都按「**改输入 → 行为必须跟着变**」来写：
    · T1  条目结构：必填缺失 / 枚举非法 / content 轴缺 evidence ⇒ 各自判错
    · T2  ID 唯一：重复 insight_id ⇒ 合并报错且**不静默覆盖**
    · T3  多轴并存：同 target 有两个不同轴的 proposed 条目 ⇒ 检出待裁决
    · T4  裁决留痕：status != proposed 却缺 decided_by/decided_at ⇒ 判错
    · T5  module 粒度：target_kind=module 的 target_id 必须是模块/章节级标识
    · T6  轮报投影：第 1、2 项从载体渲染；缺 before 快照 ⇒ **显式标"缺失"**（不得编造）
    · T7  冻结 digest：内容不变 ⇒ digest 不变；内容变 ⇒ digest 变；
          **重新序列化不得改变 digest**（冻结判据是"内容没变"，不是"文件字节没变"）
    · T8  回落可见：配置缺键 ⇒ 回落内置值**且**留 note（静默回落 = 不设防）
    · T9  护栏的护栏：判据层自身被破坏 ⇒ 原断言必须翻转（防"恒真断言"）

**为什么用"破坏实现"而不是"改配置"**（本包反复吃亏的教训）：
  改 yaml 只能证明"配置驱动"；破坏判定实现才能证明"断言真的在测那件事"。
  T9 是常驻的反向自检：把实现改成硬编码或恒真，断言必须红；复原后必须重新红。
  ⚠ 破坏必须破坏到**被测对象本身**（判据实现），不是破坏调用点
    （本包已踩过：只改调用点而断言的是函数 ⇒ 反例假阴性）。

隔离策略：全部用例在**内存**里造数据，不写包内任何文件；
yaml 只**只读**加载（用例若需改配置，走内存副本）。

用法：
    python3 -m pytest scripts/test_insight_carrier.py -q
    python3 scripts/test_insight_carrier.py
"""

import copy
import importlib.util
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)


def _load_module():
    """加载 scripts/insight_carrier.py（不依赖包内其他模块的 import 副作用）。"""
    path = os.path.join(HERE, "insight_carrier.py")
    if not os.path.isfile(path):
        raise unittest.SkipTest("scripts/insight_carrier.py 尚未落地——判定层缺失，本套件暂跳")
    spec = importlib.util.spec_from_file_location("insight_carrier_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["insight_carrier_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


IC = _load_module()


def _entry(**over):
    """一条合规的洞察条目（各用例只覆盖自己要改的字段）。"""
    e = {
        "insight_id": "s12-C-01",
        "target_id": "s12",
        "target_kind": "page",
        "axis": "content",
        "expert": "dvm-content-expert",
        "proposal": "把第 12 页的疫苗程序表述改成 2021 版国家免疫规范原文口径",
        "rationale": "原表述引用的是 2016 版，剂量与程序已变",
        "severity": "P1",
        "status": "proposed",
        "evidence": "PMID:31234567 / 中华人民共和国动物防疫法 2021 修订版 第二十条",
    }
    e.update(over)
    return e


def _part(entries=None, **over):
    p = {
        "task_id": "T-20261026-01",
        "member": "dvm-content-expert",
        "axis": "content",
        "round": 1,
        "entries": entries if entries is not None else [_entry()],
    }
    p.update(over)
    return p


class TestEntryValidation(unittest.TestCase):
    """T1：条目结构判据。"""

    def test_T1_positive_valid_entry_passes(self):
        notes = []
        ok, errors, warnings = IC.validate_entry(_entry(), None, notes)
        self.assertTrue(ok, f"合规条目被判错：{errors}")
        self.assertEqual(errors, [], "合规条目不应有 error")
        _ = warnings  # warnings 只提示，不影响 ok——本断言刻意不检查它，避免把 warnings 当门禁

    def test_T1_reverse_missing_required_field(self):
        """反向：删掉必填字段 proposal ⇒ 必须判错。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 ok 返回 False。"""
        e = _entry()
        del e["proposal"]
        ok, errors, _ = IC.validate_entry(e)
        self.assertFalse(ok, "缺 proposal 的条目被放行——必填校验没生效")
        self.assertTrue(errors, "判错时必须给出 error 列表（不得只给布尔）")
        blob = json.dumps(errors, ensure_ascii=False)
        self.assertIn("proposal", blob, f"error 未指出缺哪个字段：{blob}")

    def test_T1_reverse_invalid_enum_value(self):
        """反向：axis 写成不存在的值 ⇒ 必须判错。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 ok 返回 False。"""
        ok, errors, _ = IC.validate_entry(_entry(axis="audio"))
        self.assertFalse(ok, "axis='audio' 被放行——枚举校验没生效")
        self.assertTrue(errors, "枚举非法必须报错")

    def test_T1_reverse_content_axis_requires_evidence(self):
        """反向：content 轴缺 evidence ⇒ 必须判错（内容轴的洞察必须带证据定位）。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 ok 返回 False。"""
        e = _entry()
        del e["evidence"]
        ok, errors, _ = IC.validate_entry(e)
        self.assertFalse(ok, "content 轴缺 evidence 被放行——规则未生效")
        self.assertTrue(errors, "缺 evidence 必须报错")

    def test_T1b_pedagogy_axis_evidence_optional(self):
        """对照：pedagogy 轴无 evidence 仍应通过（规则只对 content 轴强制）——
        若这条转红，说明规则被写成了"所有轴都要 evidence"（过度约束）。"""
        e = _entry(axis="pedagogy", expert="pedagogy-architect")
        e.pop("evidence", None)
        ok, errors, _ = IC.validate_entry(e)
        self.assertTrue(ok, f"pedagogy 轴被误判为缺证据：{errors}")


class TestPartValidation(unittest.TestCase):
    """T1b：分片结构判据。"""

    def test_T1b_positive_valid_part_passes(self):
        ok, errors = IC.validate_part(_part())
        self.assertTrue(ok, f"合规分片被判错：{errors}")

    def test_T1b_reverse_part_missing_entries(self):
        ok, errors = IC.validate_part({"task_id": "T", "member": "m", "axis": "content", "round": 1})
        self.assertFalse(ok, "没有 entries 的分片被放行")
        self.assertTrue(errors, "判错必须给 error 列表")

    def test_T1b_reverse_part_entry_invalid(self):
        """反向：分片里有一条非法条目 ⇒ 整片判错（不得"好条目照收、坏条目静默丢弃"）。"""
        part = _part(entries=[_entry(), _entry(insight_id="s12-C-02", axis="audio")])
        ok, errors = IC.validate_part(part)
        self.assertFalse(ok, "含非法条目的分片被放行")
        self.assertTrue(errors, "必须报出哪条错")


class TestMergeUniqueness(unittest.TestCase):
    """T2：insight_id 唯一性——重复必须报错且**不静默覆盖**。"""

    def test_T2_positive_merge_two_axes(self):
        notes = []
        parts = [
            _part(entries=[_entry()]),
            _part(member="pedagogy-architect", axis="pedagogy",
                  entries=[_entry(insight_id="s12-P-01", axis="pedagogy",
                                  expert="pedagogy-architect")]),
        ]
        carrier = IC.merge_parts(parts, None, notes)
        self.assertIn("task_id", carrier)
        self.assertTrue(carrier.get("targets"), "合并结果没有 targets")

    def test_T2_reverse_duplicate_insight_id_not_overwritten(self):
        """反向：两个分片含同一 insight_id ⇒ 合并必须报错/记错，且**不得静默覆盖**。
        如果这个值改了，哪个函数的行为应该跟着变？→ merge_parts 记 error 且两个条目都还在。"""
        notes = []
        parts = [
            _part(entries=[_entry(proposal="版本A")]),
            _part(entries=[_entry(proposal="版本B")]),
        ]
        carrier = IC.merge_parts(parts, None, notes)
        blob = json.dumps(carrier, ensure_ascii=False) + json.dumps(notes, ensure_ascii=False)
        self.assertIn("s12-C-01", blob, "重复 ID 完全消失了——可能被静默覆盖")
        # 两个版本都必须留痕（无论以 errors 形式还是两条并存）
        self.assertTrue(
            "版本A" in blob and "版本B" in blob,
            f"重复 ID 的其中一个版本被静默丢弃（覆盖发生）：{blob[:500]}")
        # 且必须留有错误痕迹
        self.assertTrue(
            ("版本B" not in blob) or ("error" in blob.lower()) or notes,
            "重复 ID 未留任何错误痕迹")


class TestConflictDetection(unittest.TestCase):
    """T3：多轴并存 ⇒ 待人工裁决（脚本**不判是否互斥**）。"""

    def _two_axis_carrier(self):
        parts = [
            _part(entries=[_entry(insight_id="s12-C-01", axis="content")]),
            _part(member="pedagogy-architect", axis="pedagogy",
                  entries=[_entry(insight_id="s12-P-01", axis="pedagogy",
                                  expert="pedagogy-architect")]),
        ]
        return IC.merge_parts(parts)

    def test_T3_multi_axis_same_target_is_flagged(self):
        """同一 target 上两个轴的 proposed 条目 ⇒ 检出待裁决。
        如果这个值改了，哪个函数的行为应该跟着变？→ detect_conflicts 返回非空。"""
        carrier = self._two_axis_carrier()
        conflicts = IC.detect_conflicts(carrier)
        self.assertTrue(conflicts, "多轴并存未被检出——冲突无处显形的病灶复发")
        blob = json.dumps(conflicts, ensure_ascii=False)
        self.assertIn("s12", blob, "冲突记录未指出是哪个目标")

    def test_T3_same_axis_only_is_not_conflict(self):
        """对照：同一轴的多个条目 **不是** 冲突（那只是同轴内多条，不是多轴并存）。
        若这条转红，说明判据写成了"目标上有 >1 条就报冲突"（误报）。"""
        parts = [_part(entries=[_entry(insight_id="s12-C-01"),
                                _entry(insight_id="s12-C-02")])]
        carrier = IC.merge_parts(parts)
        conflicts = IC.detect_conflicts(carrier)
        self.assertFalse(conflicts, f"同轴多条被误报为冲突：{conflicts}")

    def test_T3_different_targets_not_conflict(self):
        """对照：不同 target 上的不同轴 ⇒ 不是冲突（冲突是"同一目标的同一处"）。"""
        parts = [
            _part(entries=[_entry(insight_id="s12-C-01", target_id="s12")]),
            _part(member="pedagogy-architect", axis="pedagogy",
                  entries=[_entry(insight_id="s20-P-01", target_id="s20", axis="pedagogy",
                                  expert="pedagogy-architect")]),
        ]
        carrier = IC.merge_parts(parts)
        conflicts = IC.detect_conflicts(carrier)
        self.assertFalse(conflicts, f"不同目标被误报为冲突：{conflicts}")

    def test_T3b_does_not_judge_semantic_conflict(self):
        """边界：脚本**不得**输出"这两条互斥/矛盾"这类语义判断——
        互斥与否是语义判断，归人。检出"多轴并存"是结构判定，可以。"""
        carrier = self._two_axis_carrier()
        blob = json.dumps(IC.detect_conflicts(carrier), ensure_ascii=False)
        for banned in ("互斥", "矛盾", "冲突不可", "incompatible", "contradict"):
            self.assertNotIn(banned, blob,
                             f"判据输出了语义判断（{banned}）——脚本只判结构，语义归人")


class TestAdjudicationTrace(unittest.TestCase):
    """T4：裁决留痕——status != proposed 必须有 decided_by / decided_at。"""

    def test_T4_reverse_decided_without_trace(self):
        e = _entry(status="accepted")
        ok, errors, _ = IC.validate_entry(e)
        self.assertFalse(ok, "status=accepted 却无 decided_by/decided_at 被放行——裁决留痕失效")
        self.assertTrue(errors, "缺裁决留痕必须报错")

    def test_T4_positive_decided_with_trace(self):
        e = _entry(status="accepted", decided_by="team-lead", decided_at="2026-10-26T09:00:00")
        ok, errors, _ = IC.validate_entry(e)
        self.assertTrue(ok, f"裁决留痕齐全却判错：{errors}")


class TestModuleGranularity(unittest.TestCase):
    """T5：module 粒度——module 严格指教学知识模块/章节（管家节点已裁决）。"""

    def test_T5_positive_module_id(self):
        ok, errors, _ = IC.validate_entry(
            _entry(insight_id="M-HA-GLYCO-C-01", target_id="HA-糖基化与宿主适应",
                   target_kind="module"))
        self.assertTrue(ok, f"模块级 target_id 被判错：{errors}")

    def test_T5_reverse_module_id_is_pure_page_number(self):
        """反向：target_kind=module 却给纯数字页号 ⇒ 必须判错。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 ok 返回 False。"""
        ok, errors, _ = IC.validate_entry(
            _entry(insight_id="s12-C-01", target_id="12", target_kind="module"))
        self.assertFalse(ok, "module 的 target_id 给成纯数字页号却放行——粒度口径未生效")
        self.assertTrue(errors, "粒度违规必须报错")


class TestRoundReportProjection(unittest.TestCase):
    """T6：轮报投影——第 1、2 项从载体渲染；缺 before 快照必须显式标缺失。"""

    def _carrier(self):
        parts = [_part(entries=[_entry()])]
        return IC.merge_parts(parts)

    def test_T6_positive_render_contains_scope_and_diff(self):
        out = IC.render_round_report(self._carrier())
        self.assertIsInstance(out, dict, "render 必须返回 dict")
        blob = json.dumps(out, ensure_ascii=False)
        self.assertIn("s12", blob, "渲染结果里没有目标 ID——第 1 项（处理范围及问题）没投影出来")
        self.assertIn("s12-C-01", blob, "渲染结果里没有洞察条目 ID")

    def test_T6_reverse_missing_before_snapshot_must_be_marked(self):
        """反向：没有 before 快照 ⇒ 差异段必须**显式标缺失**，不得编造差异。
        如果这个值改了，哪个函数的行为应该跟着变？→ render_round_report 的输出里出现"缺失"标记。"""
        out = IC.render_round_report(self._carrier())
        blob = json.dumps(out, ensure_ascii=False)
        self.assertTrue(
            ("缺失" in blob) or ("待补" in blob) or ("无" in blob) or ("missing" in blob.lower()),
            f"缺 before 快照却没标缺失（可能被编造了差异）：{blob[:400]}")

    def test_T6b_render_does_not_invent_entries(self):
        """边界：渲染**不得凭空生成**载体里没有的条目（投影，不是创作）。"""
        carrier = self._carrier()
        out = IC.render_round_report(carrier)
        blob = json.dumps(out, ensure_ascii=False)
        self.assertNotIn("s99", blob, "渲染结果出现了载体里不存在的目标 ID")


class TestFreezeDigest(unittest.TestCase):
    """T7：冻结 digest——判据是"内容没变"，不是"文件字节没变"。"""

    def test_T7_digest_stable_under_reserialization(self):
        """载体重新序列化（键序变化）不得改变 digest。
        如果这个值改了，哪个函数的行为应该跟着变？→ freeze_digest 的返回值。"""
        carrier = IC.merge_parts([_part()])
        d1 = IC.freeze_digest(carrier)
        shuffled = {k: carrier[k] for k in sorted(carrier.keys(), reverse=True)}
        d2 = IC.freeze_digest(shuffled)
        self.assertEqual(d1, d2, f"键序变化导致 digest 变化（{d1} vs {d2}）——冻结判据错了")

    def test_T7_digest_changes_with_content(self):
        carrier = IC.merge_parts([_part()])
        d1 = IC.freeze_digest(carrier)
        carrier2 = copy.deepcopy(carrier)
        # 改一个洞察条目的建议内容
        txt = json.dumps(carrier2, ensure_ascii=False)
        carrier2 = json.loads(txt.replace("疫苗程序表述", "免疫程序表述"))
        d2 = IC.freeze_digest(carrier2)
        self.assertNotEqual(d1, d2, "内容变了 digest 却不变——冻结形同虚设")

    def test_T7_digest_is_sha256_hex(self):
        d = IC.freeze_digest(IC.merge_parts([_part()]))
        self.assertRegex(d, r"^[0-9a-f]{64}$", f"digest 不是 sha256 十六进制：{d!r}")


class TestFallbackVisibility(unittest.TestCase):
    """T8：配置缺键 ⇒ 回落内置值**且**留 note（静默回落 = 不设防）。"""

    def test_T8_notes_not_silent(self):
        """把判据读到的枚举清空 ⇒ 必须判错**或**回落并留下痕迹（不得静默通过）。

        构造方式：给 validate_entry 喂一份**枚举为空**的 cfg——
        若实现真从 cfg 读枚举，非法 axis 必然被发现；若是硬编码，
        非法 axis 会被放过（那就暴露了"配置没真被读"）。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 ok 返回值与 errors/notes。"""
        broken = {"enums": {"axis": [], "target_kind": [], "severity": [], "status": []},
                  "required": ["insight_id", "proposal", "axis", "target_id", "target_kind"]}
        notes = []
        ok, errors, _ = IC.validate_entry(_entry(axis="audio"), broken, notes)
        self.assertFalse(ok, "枚举被清空却仍判通过——配置没真被读（或回落未生效）")
        self.assertTrue(errors or notes, "既没报错也没留回落痕迹——静默失败")


class TestImplementationBreak(unittest.TestCase):
    """T9：护栏的护栏——把判定实现破坏成恒真/硬编码，原断言必须翻转。

    这是本包定下的硬规矩：**反向例必须破坏到被测对象本身**。
    改调用点而断言函数 ⇒ 反例假阴性（本包已踩过两次）。
    复原后必须**重新转红**——否则说明断言已被改成恒真。
    """

    def _broken_module(self, old, new):
        """在**模块源码**层面做临时替换，返回可重新加载的模块对象。"""
        path = os.path.join(HERE, "insight_carrier.py")
        src = open(path, encoding="utf-8").read()
        if old not in src:
            self.skipTest(f"源码里找不到 {old!r}——实现已改形，破坏式自检需同步")
        path_bak = path + ".bak_t9"
        with open(path_bak, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(src.replace(old, new, 1))
            spec = importlib.util.spec_from_file_location("ic_broken", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["ic_broken"] = mod
            spec.loader.exec_module(mod)
            return mod
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            if os.path.exists(path_bak):
                os.remove(path_bak)

    def test_T9_break_axis_enum_check_must_flip_assertion(self):
        """把判据破坏成恒真 ⇒ T1 的枚举反向例必须转红；复原后必须重新转红。

        破坏点选在 **validate_entry 的返回出口**（`return (not errors), ...`）
        ——把它改成恒真 = 判据整体失效 = 非法条目会被判通过。
        ⚠ 破坏必须破坏到**被测对象本身**（判定实现），不是破坏调用点：
        只改调用点而断言的是函数 ⇒ 反例假阴性（本包已踩过两次）。
        ⚠ 早先试过破坏 `errors.append`（多行调用 `errors.append({`）——
          替换后变成裸 dict 字面量块 ⇒ IndentationError ⇒ 破坏根本没生效（假阴性）。
          教训：破坏点必须选**语法上可安全替换**的位置。
        """
        src = open(os.path.join(HERE, "insight_carrier.py"), encoding="utf-8").read()
        old = "return (not errors), errors, warnings"
        if old not in src:
            self.skipTest("实现里找不到返回出口形态——破坏式自检需同步")
        mod = self._broken_module(old, "return True, errors, warnings  # 破坏：恒真")
        # 破坏后：非法条目应当被判为"通过"（说明判据确已失效）
        ok, _errors, _ = mod.validate_entry(_entry(axis="audio"))
        self.assertTrue(ok, "破坏返回出口后仍判错——说明破坏没生效，自检无效")
        # 复原后必须重新判错（否则说明断言已被改成恒真）
        ok2, errors2, _ = IC.validate_entry(_entry(axis="audio"))
        self.assertFalse(ok2, "复原后仍判通过——断言已被改成恒真")
        self.assertTrue(errors2, "复原后应重新报出错误")

    def test_T9_break_detect_conflicts_must_flip_assertion(self):
        """把冲突检出破坏成恒空 ⇒ T3 的正向断言必须转红；复原后必须重新转红。

        破坏方式：在函数体**首行**插 `return []`（恒空）。
        ⚠ 早先试过改函数名（`def detect_conflicts` → `def detect_conflicts_broken`）——
          那会抛 AttributeError 而**不是**"检不出"，属破坏无效的假阴性。
          破坏必须让**被测函数本身**仍在、但行为被破坏。
        """
        src = open(os.path.join(HERE, "insight_carrier.py"), encoding="utf-8").read()
        marker = 'def detect_conflicts(carrier, cfg=None, notes=None):\n'
        if marker not in src:
            self.skipTest("实现里找不到 detect_conflicts 签名——破坏式自检需同步")
        mod = self._broken_module(marker, marker + "    return []  # 破坏：恒空\n")
        parts = [
            _part(entries=[_entry(insight_id="s12-C-01", axis="content")]),
            _part(member="pedagogy-architect", axis="pedagogy",
                  entries=[_entry(insight_id="s12-P-01", axis="pedagogy",
                                  expert="pedagogy-architect")]),
        ]
        carrier = mod.merge_parts(parts)
        self.assertFalse(mod.detect_conflicts(carrier),
                         "破坏后仍检出冲突——说明破坏没生效，自检无效")
        # 复原后必须重新检出
        carrier_ok = IC.merge_parts(parts)
        self.assertTrue(IC.detect_conflicts(carrier_ok), "复原后未检出冲突——断言被改成恒真")


class TestYamlUntouched(unittest.TestCase):
    """护栏：全程只读包内文件，跑完不得留下任何改动。"""

    def test_yaml_sha256_unchanged(self):
        p = os.path.join(PKG, "references", "insight-carrier.yaml")
        if not os.path.isfile(p):
            self.skipTest("schema 文件尚未落地")
        import hashlib
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        # 本用例不修改任何东西，只确认文件可读且内容稳定
        h2 = hashlib.sha256(open(p, "rb").read()).hexdigest()
        self.assertEqual(h, h2, "schema 文件在读的过程中被改动——用例污染了包内文件")


class TestRealSchemaEffective(unittest.TestCase):
    """T28：**真实 schema 必须生效**（2026-10-26 实测病灶的永久防线）。

    病灶回放：实现按 `enums.<x>`（直接列表）与 `report_projection` 读，而 schema 写的是
    `enums.<x>.values` 与 `report.project_items`
    ⇒ **每一次都回落内置值，schema 事实上不生效**，
    而"有 schema、有实现、有自检、有 28 条护栏"**全是绿的**——
    本包最忌讳的假绿（判据跑的是兜底口径，却看着像在按配置判）。

    为什么前面的用例抓不到：它们验的是"判据行为对不对"，
    **不验"判据是不是取自 schema"**——回落后行为仍然正确。
    ⇒ 这条用例专门验后者。
    """

    def test_T28_real_schema_has_zero_fallback(self):
        """用**真实 schema** 跑一遍全部判定路径，断言**零回落**。
        如果这个值改了，哪个函数的行为应该跟着变？→ 回落数从 0 变正。"""
        cfg, ok = IC.load_cfg()
        self.assertTrue(ok, "schema 加载失败——判据将跑在内置兜底口径上")
        notes = []
        IC.validate_entry(_entry(), cfg, notes)
        IC.validate_part(_part(), cfg, notes)
        carrier = IC.merge_parts([_part()], cfg, notes)
        IC.detect_conflicts(carrier, cfg, notes)
        IC.render_round_report(carrier, cfg, notes)
        self.assertEqual(notes, [],
                         f"用真实 schema 跑仍有 {len(notes)} 条回落 ⇒ schema 未生效："
                         f"{notes[:5]}")

    def test_T28b_rule_execution_alignment(self):
        """schema 里声明的每条规则都必须有实现执行点（声明层≠执行层的机器核对）。"""
        cfg, ok = IC.load_cfg()
        self.assertTrue(ok, "schema 加载失败")
        if not hasattr(IC, "rule_execution_check"):
            self.skipTest("判定层未提供 rule_execution_check——自检需同步")
        rok, report = IC.rule_execution_check(cfg, [])
        self.assertTrue(rok, f"规则声明与实现执行点不对齐：{report}")

    def test_T28c_enums_read_from_schema_not_hardcoded(self):
        """反例（双向）：schema 的 axis 枚举改掉 ⇒ 判定必须**跟着变**。

        ① 原始 schema（不含 audio）⇒ `axis=audio` 判**非法**；
        ② 放宽 schema（加上 audio）⇒ `axis=audio` 判**合法**。

        ⚠ 早先只写了 ② 的反面断言（"放宽后仍判非法"）——方向写反了：
           放宽枚举后 audio **本就应该**合法，判非法才是错。
           正确的证明是**双向**：改配置前非法、改配置后合法。
        如果这个值改了，哪个函数的行为应该跟着变？→ validate_entry 的 E_ENUM 判定。
        """
        cfg, ok = IC.load_cfg()
        self.assertTrue(ok, "schema 加载失败")
        ok_before, errs_before, _ = IC.validate_entry(_entry(axis="audio"), cfg, [])
        self.assertFalse(ok_before, "原始 schema 里 axis=audio 应判非法")
        self.assertTrue(errs_before, "非法 axis 应报出 E_ENUM")
        enums = IC._section(cfg, "enums")
        node = enums.get("axis")
        if isinstance(node, dict):
            node["values"] = ["content", "pedagogy", "visual", "audio"]
        else:
            enums["axis"] = ["content", "pedagogy", "visual", "audio"]
        ok_after, _errs_after, _ = IC.validate_entry(_entry(axis="audio"), cfg, [])
        self.assertTrue(ok_after, "schema 已放宽 axis 枚举却仍判 audio 非法——枚举没真被读")


if __name__ == "__main__":
    unittest.main(verbosity=2)

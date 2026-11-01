#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_collapse_quality_eval.py — 坍缩产物结构完整性评估器的能红证明（v3.28.2 B3）

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（本轮十三维度诊断 D1/P1-2 实测缺口）】
─────────────────────────────────────────────────────────────────────────────
坍缩是全域流程源头，但「知识覆盖深度 / 领域匹配度 / 输出准确性」
**没有任何评估器与判据**（rg 评估器关键词 0 命中）。

⚠ **诚实边界**：语义质量（覆盖够不够深、领域是否真匹配、输出是否准确）
**机器不判**（三件事分工：识别/分类/权衡归 LLM 与人）。
本文件锁的是**可判定的结构完整性**六项：
  ① panel_subset   选中专家 ⊆ 该域面板（不许凭空造人）
  ② persona_fields role_persona 四要素齐
  ③ evidence_axes  证据两轴都非空
  ④ content_axes   覆盖方向非空
  ⑤ kb_routing     有库 或 显式"本域无库"
  ⑥ panel_hints    每个选中专家都有激活提示

每条都配「改坏 ⇒ 必须红」，防判据恒真。
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"


def _load(name="harness_qe"):
    spec = importlib.util.spec_from_file_location(name, HARNESS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cfg(block=False):
    return {"collapse": {"quality_eval": {
        "enabled": True, "require_panel_hints": True,
        "block_on_structural_gap": block}}}


def _good_obj():
    return {
        "expert_panel": [
            {"id": "a", "activation_hints": ["h1"]},
            {"id": "b", "activation_hints": ["h2"]},
        ],
        "selected_experts": [{"id": "a"}],
        "role_persona": {"title": "T", "background": "B", "stance": "S", "duty_boundary": "D"},
        "evidence_hierarchy": {"institutional": ["i"], "literature": ["l"]},
        "content_axes": ["ax"],
        "knowledge_bases": [{"id": "kb1"}],
        "knowledge_bases_ref": "config/external-tools.yaml#knowledge_bases",
    }


class TestCollapseQualityEval(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.h = _load()

    # ── 正向：结构齐全必须绿（防误伤）──────────────────────────────
    def test_T1_complete_structure_passes(self):
        r = self.h._collapse_quality_eval(_cfg(), _good_obj())
        self.assertTrue(r["ok"], f"结构齐全却判红（假阳性）：{r['checks']}")
        self.assertEqual(r["score"], "6/6", f"检查项数不符：{r['score']}")
        self.assertIn("机器不判", r["boundary"], "边界声明必须随结果返回")

    # ── ① 面板子集：凭空造人必须红 ─────────────────────────────────
    def test_T2_selected_not_in_panel_is_red(self):
        o = _good_obj()
        o["selected_experts"] = [{"id": "ghost"}]
        r = self.h._collapse_quality_eval(_cfg(), o)
        self.assertFalse(r["ok"], "选中面板外的专家未判红")
        bad = [c for c in r["checks"] if c["id"] == "panel_subset"][0]
        self.assertFalse(bad["ok"])
        self.assertIn("ghost", bad["detail"])

    # ── ② 人格四要素缺一必须红 ─────────────────────────────────────
    def test_T3_persona_missing_field_is_red(self):
        o = _good_obj()
        o["role_persona"] = {"title": "T", "background": "B"}
        r = self.h._collapse_quality_eval(_cfg(), o)
        self.assertFalse(r["ok"], "人格字段缺失未判红")
        bad = [c for c in r["checks"] if c["id"] == "persona_fields"][0]
        self.assertIn("stance", bad["detail"])

    # ── ③ 证据轴只给一轴必须红（两轴独立是硬要求）──────────────────
    def test_T4_single_evidence_axis_is_red(self):
        o = _good_obj()
        o["evidence_hierarchy"] = {"institutional": ["i"]}
        r = self.h._collapse_quality_eval(_cfg(), o)
        self.assertFalse(r["ok"], "证据只给机构轴（缺文献轴）未判红")
        self.assertFalse([c for c in r["checks"] if c["id"] == "evidence_axes"][0]["ok"])

    # ── ⑤ 库路由：既无库又无"本域无库"指针必须红 ────────────────────
    def test_T5_kb_routing_without_pointer_is_red(self):
        o = _good_obj()
        o["knowledge_bases"] = []
        o["knowledge_bases_ref"] = ""
        r = self.h._collapse_quality_eval(_cfg(), o)
        self.assertFalse(r["ok"], "无库且无指针未判红")
        o2 = _good_obj()
        o2["knowledge_bases"] = []
        o2["knowledge_bases_ref"] = "config/external-tools.yaml#domains_without_knowledge_bases"
        r2 = self.h._collapse_quality_eval(_cfg(), o2)
        self.assertTrue(r2["ok"], "显式「本域无库」指针应放行（假阳性）")

    # ── ⑥ 选中专家无激活提示必须红；未选中的不要求 ──────────────────
    def test_T6_selected_without_hints_is_red(self):
        o = _good_obj()
        o["expert_panel"] = [
            {"id": "a", "activation_hints": []},        # 选中但无提示 ⇒ 红
            {"id": "b", "activation_hints": ["h2"]},    # 未选中 ⇒ 不要求
        ]
        r = self.h._collapse_quality_eval(_cfg(), o)
        self.assertFalse(r["ok"], "选中专家无激活提示未判红")
        self.assertFalse([c for c in r["checks"] if c["id"] == "panel_hints"][0]["ok"])

    # ── 关闭开关 ⇒ 不判（enabled=false 时 ok 恒真且 checks 为空）──────
    def test_T7_disabled_returns_passthrough(self):
        cfg = {"collapse": {"quality_eval": {"enabled": False}}}
        r = self.h._collapse_quality_eval(cfg, {})
        self.assertTrue(r["ok"], "enabled=false 时不应判红")
        self.assertEqual(r["checks"], [], "enabled=false 时应返回空 checks（不假装判过）")


class TestCollapseQualityEvalMutant(unittest.TestCase):
    """变异：掏空面板子集判据 ⇒ 凭空造人不再被发现。"""

    _ANCHOR = '        bad = sorted(sel_ids - panel_ids)'
    _MUT = '        bad = []  # MUTANT: 面板子集判据被掏空'

    def test_T8_mutant_kills_subset_check(self):
        src = HARNESS.read_text(encoding="utf-8")
        self.assertEqual(1, src.count(self._ANCHOR),
                         f"变异锚点不唯一（{src.count(self._ANCHOR)}）⇒ mutant 不可靠")
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp(prefix="vetmed-qe-mut-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy2(HARNESS, tmp / "h_mut.py")
        (tmp / "h_mut.py").write_text(src.replace(self._ANCHOR, self._MUT, 1), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("h_qe_mut", tmp / "h_mut.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["h_qe_mut"] = mod
        spec.loader.exec_module(mod)
        o = _good_obj()
        o["selected_experts"] = [{"id": "ghost"}]
        r = mod._collapse_quality_eval(_cfg(), o)
        ok = [c for c in r["checks"] if c["id"] == "panel_subset"][0]["ok"]
        self.assertTrue(ok, f"掏空判据后仍检出面板外选人 ⇒ 变异体没生效（证明会恒真）：{r['checks']}")


if __name__ == "__main__":
    unittest.main()

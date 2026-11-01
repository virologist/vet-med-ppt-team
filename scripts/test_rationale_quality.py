#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_rationale_quality.py — 坍缩选型理由「格式下限」判据的能红证明（v3.28.2 B2）

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（本轮十三维度诊断 P1-1 实测缺口）】
─────────────────────────────────────────────────────────────────────────────
`config/harness.yaml#collapse.rationale_filled_by = team-lead` 此前只判
「**填没填**」（`selection_rationale_status` = filled / pending_team_lead），
**理由质量无任何判据**——随便写个「待补」也能过确认门。
而坍缩是全流程源头：选错域/选错人，后面五闸全白做。

⚠ **宪法边界（本文件也在守它）**：本包三件事分工写死
「识别/分类/权衡 = LLM 与人；机器只做结构与格式校验」。
故判据**不判语义质量**，只判两条可判定项：
  ① 长度下限（`collapse.rationale_quality.min_chars`）
  ② 占位符值（`placeholder_values`：待补 / TODO / 略 …）——**值域格式检查**，
     不是内容含义匹配。
通过 ≠ 理由说得好；语义质量归管家节点在 `--decision` 确认门裁决。

─────────────────────────────────────────────────────────────────────────────
【判据设计（每条都能红）】
─────────────────────────────────────────────────────────────────────────────
  T1 合规理由 ⇒ ok（防误伤：守卫不能把正常理由判红）
  T2 过短 ⇒ E_RATIONALE_TOO_SHORT
  T3 纯占位符 ⇒ E_RATIONALE_PLACEHOLDER
  T4 豁免位「待补：xxx」且过短 ⇒ E_RATIONALE_PLACEHOLDER（防伪装成正文）
  T5 配置缺该段 ⇒ 回落内置下限 + 仍能判（不静默放行）
  T6 **变异**：掏空长度判据 ⇒ T2 型违规不再被发现（证明判据不恒真）
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"


def _load_harness(name="harness_under_test"):
    spec = importlib.util.spec_from_file_location(name, HARNESS)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _cfg(min_chars=30, placeholders=None, block=True):
    return {"collapse": {"rationale_quality": {
        "min_chars": min_chars,
        "placeholder_values": placeholders if placeholders is not None
        else ["待补", "TODO", "TBD", "略", "无", "同上", "见上", "N/A"],
        "block_on_fail": block,
    }}}


GOOD = ("选动物医学域，因为本次是禽病防治技术课程的 PPT，需专业教学标准与禽病知识库支撑；"
        "选严真奥（内容）+苏学法（教学）+屠明熙（视觉）三人，因为任务同时涉及科学性核验、"
        "课时结构与版式改造，三人职责不重叠。")


class TestRationaleQuality(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.h = _load_harness()

    # ── T1 正向（防误伤）────────────────────────────────────────────
    def test_T1_good_rationale_passes(self):
        ok, probs, metrics, block = self.h._rationale_quality(_cfg(), GOOD)
        self.assertTrue(ok, f"合规理由被判红（假阳性）：{probs}")
        self.assertTrue(block, "block_on_fail 应取自配置（true）")
        self.assertEqual(metrics["chars"], len(GOOD.strip()))
        self.assertIn("语义质量归管家节点", metrics["boundary"],
                      "边界声明必须随指标一起返回（不得装成已评估质量）")

    # ── T2 过短必须红 ───────────────────────────────────────────────
    def test_T2_too_short_is_red(self):
        ok, probs, metrics, _ = self.h._rationale_quality(_cfg(), "选动物医学域。")
        self.assertFalse(ok, "过短理由未判红 ⇒ 判据形同虚设")
        self.assertTrue(any("E_RATIONALE_TOO_SHORT" in p for p in probs), probs)

    # ── T3 纯占位符必须红 ───────────────────────────────────────────
    def test_T3_placeholder_is_red(self):
        ok, probs, _, _ = self.h._rationale_quality(_cfg(), "待补")
        self.assertFalse(ok, "纯占位符未判红")
        self.assertTrue(any("E_RATIONALE_PLACEHOLDER" in p for p in probs), probs)

    # ── T4 伪装成正文的占位符（「待补：……」且过短）必须红 ──────────
    def test_T4_camouflaged_placeholder_is_red(self):
        ok, probs, _, _ = self.h._rationale_quality(_cfg(), "待补：回头再说")
        self.assertFalse(ok, "占位符+短正文的伪装写法未判红")
        self.assertTrue(any("E_RATIONALE_PLACEHOLDER" in p for p in probs), probs)

    # ── T5 配置缺段 ⇒ 回落内置下限，仍能判（不静默放行）──────────────
    def test_T5_missing_config_falls_back_and_still_judges(self):
        ok, probs, metrics, block = self.h._rationale_quality({}, "短")
        self.assertFalse(ok, "配置缺失时未回落判据（静默放行）")
        self.assertEqual(metrics["min_chars"], 30, "缺配置应回落 30 字下限")
        self.assertTrue(block, "缺配置应回落 block_on_fail=true（最保守）")


class TestRationaleQualityMutant(unittest.TestCase):
    """T6：掏空长度判据 ⇒ 过短理由不再被发现。"""

    _ANCHOR = '    if n < min_chars:'
    _MUT = '    if False:  # MUTANT: 长度判据被掏空'

    def test_T6_mutant_kills_length_check(self):
        src = HARNESS.read_text(encoding="utf-8")
        self.assertEqual(1, src.count(self._ANCHOR),
                         f"变异锚点不唯一（{src.count(self._ANCHOR)} 处）⇒ mutant 不可靠")
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp(prefix="vetmed-rq-mut-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy2(HARNESS, tmp / "harness_mut.py")
        (tmp / "harness_mut.py").write_text(
            src.replace(self._ANCHOR, self._MUT, 1), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("harness_mut", tmp / "harness_mut.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["harness_mut"] = mod
        spec.loader.exec_module(mod)
        ok, probs, _, _ = mod._rationale_quality(_cfg(), "选动物医学域。")
        self.assertTrue(ok, f"掏空长度判据后仍报错 ⇒ 变异体没生效（证明会恒真）：{probs}")


if __name__ == "__main__":
    unittest.main()

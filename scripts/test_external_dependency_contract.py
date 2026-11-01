#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_external_dependency_contract.py — 外部 skill 接入契约的能红证明（v3.28.2 B4）

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（本轮十三维度诊断 D13③④ 实测缺口）】
─────────────────────────────────────────────────────────────────────────────
D13 四问里 ①② 已落地（①登记面结构支持五要素 ②「以包内为准」成文），
但 ③「PPT 美化类 skill 与 visual-slide-designer / visual-rules.yaml 的职责边界」
与 ④「外部标准类 skill 与包内 standards 的收录归口」**均无成文规则**
（rg「美化」在 visual-rules.yaml 与 visual-slide-designer.md 0 命中）
⇒ 未来接入美化类/标准类 skill 时**无裁决依据**，必然双源漂移。

本文件锁 ③④ 与五要素的可判定部分（契约源
`references/dependency-manifest.yaml#skill_contract`，执行器
`scripts/check_external_deps.py::validate_contract`）：
  T1 真实登记表合规（防误伤）
  T2 依赖条目缺五要素之一 ⇒ 红（E_DEP_MISSING_FIELD）
  T3 缺 beautify_boundary ⇒ 红（③ 未立规）
  T4 beautify_boundary.decision_authority 指错文件 ⇒ 红（判据唯一源不得旁落）
  T5 缺 standard_authority ⇒ 红（④ 未立规）
  T6 standard_authority.registry 指错登记面 ⇒ 红（防双源）
  T7 **变异**：掏空五要素校验循环 ⇒ T2 型违规不再被发现
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
CHECKER = HERE / "check_external_deps.py"


def _load(name="checker_under_test"):
    spec = importlib.util.spec_from_file_location(name, CHECKER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _real_manifest():
    import yaml
    with open(PKG / "references" / "dependency-manifest.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _good():
    return {
        "dependencies": [{
            "id": "x", "kind": "external_skill", "required": False, "blocking": False,
            "purpose": "p", "probe_roots": ["~/x"], "probe_files": ["SKILL.md"],
            "internal_fallback": {"path": "references/y.md"}, "messages": {"found": "f", "missing": "m"},
        }],
        "skill_contract": {
            "required_fields": ["id", "kind", "required", "blocking", "purpose",
                                "probe_roots", "probe_files", "internal_fallback", "messages"],
            "beautify_boundary": {
                "decision_authority": "config/visual-rules.yaml",
                "executor": "visual-slide-designer",
                "allowed": ["advisory"],
                "forbidden": ["rewrite thresholds"],
                "dedupe_rule": "以包内为准",
            },
            "standard_authority": {
                "registry": "config/external-tools.yaml#standards",
                "rule": "登记面唯一",
                "on_conflict": "以官方源现查为准",
                "anti_dual_source": "不得双源",
            },
        },
    }


class TestContractValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.c = _load()

    # ── T1 真实登记表合规（防误伤）──────────────────────────────────
    def test_T1_real_manifest_passes(self):
        ok, probs, summary = self.c.validate_contract(_real_manifest())
        self.assertTrue(ok, f"真实登记表被判红（假阳性）：{probs}")
        self.assertTrue(summary["contract"], "契约段应被识别")
        self.assertGreaterEqual(summary["required_field_count"], 9,
                                f"五要素字段数不足：{summary}")
        self.assertIn("teaching-ppt-studio", summary["decoupled_deps"],
                      "teaching-ppt-studio 应被识别为可解耦依赖（required/blocking 均 false）")

    # ── T2 缺五要素之一 ⇒ 红 ────────────────────────────────────────
    def test_T2_dep_missing_field_is_red(self):
        m = _good()
        m["dependencies"][0].pop("internal_fallback")
        ok, probs, _ = self.c.validate_contract(m)
        self.assertFalse(ok, "缺 internal_fallback（降级路径）未判红")
        self.assertTrue(any(p["code"] == "E_DEP_MISSING_FIELD" for p in probs), probs)

    # ── T3 缺美化边界 ⇒ 红 ─────────────────────────────────────────
    def test_T3_missing_beautify_boundary_is_red(self):
        m = _good()
        m["skill_contract"].pop("beautify_boundary")
        ok, probs, _ = self.c.validate_contract(m)
        self.assertFalse(ok, "③ 美化类边界缺失未判红")
        self.assertTrue(any(p["code"] == "E_NO_BEAUTIFY_BOUNDARY" for p in probs), probs)

    # ── T4 判据唯一源被旁落 ⇒ 红 ───────────────────────────────────
    def test_T4_beautify_authority_drift_is_red(self):
        m = _good()
        m["skill_contract"]["beautify_boundary"]["decision_authority"] = "some-skill/rules.md"
        ok, probs, _ = self.c.validate_contract(m)
        self.assertFalse(ok, "美化判据源指到外部 skill 未判红（双源风险）")
        self.assertTrue(any(p["code"] == "E_BEAUTIFY_AUTHORITY_DRIFT" for p in probs), probs)

    # ── T5 缺标准归口 ⇒ 红 ─────────────────────────────────────────
    def test_T5_missing_standard_authority_is_red(self):
        m = _good()
        m["skill_contract"].pop("standard_authority")
        ok, probs, _ = self.c.validate_contract(m)
        self.assertFalse(ok, "④ 标准归口缺失未判红")
        self.assertTrue(any(p["code"] == "E_NO_STANDARD_AUTHORITY" for p in probs), probs)

    # ── T6 标准登记面指错 ⇒ 红 ────────────────────────────────────
    def test_T6_standard_registry_drift_is_red(self):
        m = _good()
        m["skill_contract"]["standard_authority"]["registry"] = "inline"
        ok, probs, _ = self.c.validate_contract(m)
        self.assertFalse(ok, "标准登记面指错未判红（双源风险）")
        self.assertTrue(any(p["code"] == "E_STANDARD_REGISTRY_DRIFT" for p in probs), probs)

    # ── T7 无依赖时缺契约不判红（自包含包可独立运行）────────────────
    def test_T7_no_deps_no_contract_is_ok(self):
        ok, probs, summary = self.c.validate_contract({"dependencies": []})
        self.assertTrue(ok, f"无外部依赖时不应要求契约段：{probs}")
        self.assertFalse(summary["contract"])


class TestContractMutant(unittest.TestCase):
    """变异：掏空五要素校验循环 ⇒ 缺字段不再被发现。"""

    _ANCHOR = '        for f in req:'
    _MUT = '        for f in []:  # MUTANT: 五要素判据被掏空'

    def test_T8_mutant_kills_field_check(self):
        src = CHECKER.read_text(encoding="utf-8")
        self.assertEqual(1, src.count(self._ANCHOR),
                         f"变异锚点不唯一（{src.count(self._ANCHOR)}）⇒ mutant 不可靠")
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp(prefix="vetmed-ct-mut-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy2(CHECKER, tmp / "chk_mut.py")
        (tmp / "chk_mut.py").write_text(src.replace(self._ANCHOR, self._MUT, 1), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("chk_mut", tmp / "chk_mut.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["chk_mut"] = mod
        spec.loader.exec_module(mod)
        m = _good()
        m["dependencies"][0].pop("internal_fallback")
        ok, probs, _ = mod.validate_contract(m)
        self.assertTrue(ok, f"掏空判据后仍检出缺字段 ⇒ 变异体没生效（证明会恒真）：{probs}")


if __name__ == "__main__":
    unittest.main()

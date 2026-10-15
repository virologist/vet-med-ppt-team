#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_five_gates.py — 5 闸扩展回归测试 v3.3.0

T1  stage 0-4 合法性（harness.py state set 接受）
T2  stage 5+ 非法拒绝
T3  闸 4.5 描述在 harness.yaml stages 配置中
T4  verify_deck --three-source-check 模式产出 verdict
T5  双轨期：stage 0-3 旧任务仍合法
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
VERIFY = HERE / "verify_deck.py"
HARNESS_YAML = PKG / "config" / "harness.yaml"
DOMAIN_YAML = PKG / "config" / "domain_config.yaml"
PY = sys.executable


def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


class TestFiveGatesConfig(unittest.TestCase):
    def test_T3_yaml_has_stage_4(self):
        """闸 4.5 描述在 harness.yaml stages 配置中。"""
        import yaml
        with open(HARNESS_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        stages = cfg.get("stages", {})
        self.assertIn(4, stages, "harness.yaml 缺 stage 4（闸4.5 三源核验）")
        self.assertIn("三源", stages[4]["name"], "stage 4 描述未含'三源'")
        self.assertEqual(stages[4]["gate"], "three_source_check")

    def test_T_yaml_domain_config(self):
        """domain_config.yaml 4 domain 齐。"""
        import yaml
        with open(DOMAIN_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        domains = [d["id"] for d in cfg.get("domains", [])]
        self.assertEqual(set(domains), {"animal-medicine", "microbiology", "pet", "tcm-vet"})


class TestHarnessStateTransitions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_T1_stage_0_to_4_accepted(self):
        """stage 0-4 全部合法。"""
        for s in range(5):
            rc, out, err = _run([PY, str(HARNESS), "state", "set", "--stage", str(s),
                                 "--workspace", str(self.tmp), "--detail", f"测试 stage={s}"])
            self.assertEqual(rc, 0, f"stage {s} 拒绝: {err}")

    def test_T2_stage_5plus_rejected(self):
        """stage 5+ 非法拒绝。"""
        rc, out, err = _run([PY, str(HARNESS), "state", "set", "--stage", "5",
                             "--workspace", str(self.tmp)])
        self.assertEqual(rc, 1)
        self.assertIn("拒绝写入", err)

    def test_T5_legacy_0_to_3_still_works(self):
        """双轨期：旧任务 0-3 仍合法。"""
        for s in range(4):
            rc, _, err = _run([PY, str(HARNESS), "state", "set", "--stage", str(s),
                               "--workspace", str(self.tmp)])
            self.assertEqual(rc, 0, f"旧 stage {s} 拒绝（双轨期不通过）: {err}")


class TestThreeSourceCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # 建一份含 5 案例（3 unverified + 2 verified）的登记册
        cases_dir = self.tmp / ".workbuddy" / "cases"
        cases_dir.mkdir(parents=True)
        lib = {
            "schema_version": 1,
            "cases": [
                {"case_id": f"C-M4A1-{i:03d}", "deck_path": str(self.tmp / "demo.pptx"),
                 "title": f"案例{i}", "scenario": "s", "severity": "普通",
                 "unverified": i < 3,
                 "sources": [{"kind": "pubmed", "ref": "PMID:1", "ok": i >= 3}]}
                for i in range(1, 6)
            ]
        }
        with open(cases_dir / "cases_library.json", "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False)
        # 建一个空 pptx 占位
        (self.tmp / "demo.pptx").touch()

    def test_T4_three_source_check_runs(self):
        """verify_deck --three-source-check 模式产出 verdict。"""
        rc, out, err = _run([PY, str(VERIFY), str(self.tmp / "demo.pptx"),
                             "--hours", "1", "--three-source-check",
                             "--workspace", str(self.tmp)])
        # 解析 JSON 输出
        try:
            r = json.loads(out)
        except Exception as e:
            self.fail(f"输出不是 JSON: {out}\nERR: {err}")
        self.assertIn("verdict", r)
        self.assertIn(r["verdict"], ("pass", "needs_more_verification", "no_library"))
        self.assertIn("pass_rate", r)
        self.assertEqual(r["threshold"], 0.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)

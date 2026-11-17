#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案A 门禁语义能红反例（b2026111715）——旧代码上必须失败、新代码必须通过。

覆盖三处门禁语义修复（全项目审计 B 栏 B1.1③ / B1.2 / B2.2）：
  B1.1③ 双层 skip 阻断：
    ① ensure_settings.REGRESSION_SKIP_BLOCKS_RELEASE 必须 True（体检 rc 层阻断）
    ② harness._regression_evidence_verdict 对含 status（skip）的证据必须拒收
       （reason=evidence_contains_skip，旧码放行）
  B1.2 批次归属：
    ③ 缺 batch_id/start_commit 的旧格式证据 → evidence_missing_batch_binding（旧码放行）
    ④ 证据 batch_id ≠ 收批批次 → evidence_batch_mismatch（旧码放行）
    ⑤ batch_id 匹配的正常证据 → evidence_ok（新旧行为一致的对照）
  B1.3 两层名单：
    ⑥ harness.yaml#loop_a.regression_required_pre_commit 存在且不含体检
       （pre_commit 层不得包含 ensure_settings——它读 HEAD 提交树）
  B2.2 工具版本动态读：
    ⑦ deck_surgery._pkg_version() 返回包权威版本（非硬编码 3.28.6）

运行方式（scripts/ 目录下）：python3 -m unittest -v test_gate_semantics_red
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ensure_settings as ES         # noqa: E402
import harness as H                  # noqa: E402
import deck_surgery as DS            # noqa: E402

_PKG = Path(__file__).resolve().parent.parent


def _verdict(suites_payload, batch="bTest", ev_path=None):
    """构造 args 调裁决函数，返回 verdict dict。"""
    tmp = ev_path or tempfile.mktemp(prefix="ev_", suffix=".json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(suites_payload, f, ensure_ascii=False)
    H._EVIDENCE_LAST_PAYLOAD = {}

    class _A:
        def __init__(self, ev, b):
            self.regression_evidence = ev
            self.batch = b
    return H._regression_evidence_verdict(_A(tmp, batch), ["test_harness"])


class GateSemanticsRed(unittest.TestCase):
    # ── B1.1③ 第一层 ──
    def test_01_skip_blocks_release_true(self):
        """① 常量必须 True（旧码 False）。"""
        self.assertTrue(ES.REGRESSION_SKIP_BLOCKS_RELEASE,
                        "B1.1③：REGRESSION_SKIP_BLOCKS_RELEASE 必须为 True"
                        "（skip 不阻断 = 守卫可被环境噪声整批旁路）")

    # ── B1.1③ 第二层 ──
    def test_02_evidence_with_skip_rejected(self):
        """② 证据含 status=skipped 的套件 → 拒收（旧码放行 evidence_ok）。"""
        payload = {"suites": [
            {"suite": "test_harness", "rc": 0, "duration_s": 1.0,
             "status": "skipped: 宿主环境限制"},
        ], "batch_id": "bTest", "start_commit": "abc123"}
        v = _verdict(payload)
        self.assertFalse(v["ok"], "B1.1③：含 skip 的证据不得放行收批")
        self.assertEqual(v["reason"], "evidence_contains_skip")

    # ── B1.2 ──
    def test_03_evidence_missing_batch_binding_rejected(self):
        """③ 旧格式证据（无 batch_id）→ 拒收（旧码放行）。"""
        payload = {"suites": [{"suite": "test_harness", "rc": 0, "duration_s": 1.0}]}
        v = _verdict(payload)
        self.assertFalse(v["ok"], "B1.2：缺批次归属的证据不得收批（旧批证据可复用收新批）")
        self.assertEqual(v["reason"], "evidence_missing_batch_binding")

    def test_04_evidence_batch_mismatch_rejected(self):
        """④ 证据 batch_id 与收批批次不一致 → 拒收。"""
        payload = {"suites": [{"suite": "test_harness", "rc": 0, "duration_s": 1.0}],
                   "batch_id": "bOther", "start_commit": "abc123"}
        v = _verdict(payload, batch="bTest")
        self.assertFalse(v["ok"], "B1.2：张冠李戴的证据不得收批")
        self.assertEqual(v["reason"], "evidence_batch_mismatch")

    def test_05_well_bound_evidence_ok(self):
        """⑤ 对照：批次归属匹配的证据 → evidence_ok。"""
        payload = {"suites": [{"suite": "test_harness", "rc": 0, "duration_s": 1.0}],
                   "batch_id": "bTest", "start_commit": "abc123def"}
        v = _verdict(payload, batch="bTest")
        self.assertTrue(v["ok"])
        self.assertEqual(v["reason"], "evidence_ok")
        self.assertEqual(v["detail"].get("batch_id"), "bTest")

    # ── B1.3 ──
    def test_06_pre_commit_layer_exists_and_pure(self):
        """⑥ pre_commit 层存在、非空、且不含体检（ensure_settings 读 HEAD 提交树）。"""
        import yaml
        cfg = yaml.safe_load(open(_PKG / "config" / "harness.yaml", encoding="utf-8"))
        la = cfg["loop_a"]
        pre = la.get("regression_required_pre_commit")
        self.assertIsInstance(pre, list, "B1.3：缺 pre_commit 层定义")
        self.assertTrue(pre, "B1.3：pre_commit 层不得为空")
        self.assertNotIn("ensure_settings", pre,
                         "B1.3：pre_commit 层不得含体检（[26] 未提交时结构性必红）")
        # 完整层必须包含 pre_commit 层（纯回归是完整层的子集）
        full = set(la["regression_required"])
        self.assertTrue(full.issuperset(set(pre)),
                        "B1.3：pre_commit 层必须是完整层的子集")

    # ── B2.2 ──
    def test_07_tool_version_dynamic(self):
        """⑦ _pkg_version 返回包权威版本（旧码硬编码 3.28.6）。"""
        v = DS._pkg_version()
        self.assertNotEqual(v, "3.28.6", "B2.2：报告版本不得再是硬编码工具定型版")
        import json as _j
        authoritative = _j.load(open(_PKG / ".codebuddy-plugin" / "plugin.json",
                                     encoding="utf-8"))["version"]
        self.assertEqual(v, authoritative, "B2.2：动态读必须与 plugin.json 一致")


if __name__ == "__main__":
    unittest.main()

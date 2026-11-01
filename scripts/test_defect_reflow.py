#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_defect_reflow.py — 缺陷回流台账判据的**能红**证明（v3.28.2 B1）

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（本轮十三维度诊断 D6 / P0-1 实测缺口）】
─────────────────────────────────────────────────────────────────────────────
Loop A 长期存在「**改规则不改输出**」：config/references 的判据条款改了、
判据代码也改了，同一任务重跑的产出**毫无变化**，而全包**没有任何触发记录与台账**
（rg「回流/改规则不改输出」在 config/ 与 dual-loop-governance.md 0 命中）。
⇒ 规则改动与产出效果之间无可回证的链路；改完只能靠人记。

本文件锁住新台账机制的**判据本体**：字段齐备、产出证据/豁免齐备、
rule_hash_after 与当前文件一致（防事后改账）、id 唯一。
每条判据都配一条「改坏 ⇒ 必须红」的变异，防判据恒真。

⚠ 全程在**临时目录**造台账 fixture，**不写**包内真台账（真台账只由人工登记）。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
CONTRACT = HERE / "loop_contract.py"


def _run_reflow(ledger_path):
    """跑 `harness.py loop reflow --loop a --file <台账>`，返回 (rc, out, err)。"""
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "loop", "reflow", "--loop", "a",
         "--actor", "team-lead", "--file", str(ledger_path)],
        capture_output=True, text=True, cwd=str(PKG), timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _sha12(rel_path):
    import hashlib
    with open(PKG / rel_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


class _Ledger:
    """临时台账构造器（写 yaml，不碰包内真台账）。"""

    def __init__(self, tmp: Path):
        self.path = tmp / "ledger.yaml"

    def write(self, entries):
        import yaml
        self.path.write_text(
            yaml.safe_dump({"schema": "defect-reflow/1", "entries": entries},
                           allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        return self.path

    def good_entry(self, **over):
        import yaml
        e = {
            "id": "RF-TEST-001",
            "rule_ref": "config/harness.yaml#loop_a.regression_required",
            "change": "回归必跑项由 3 项扩到 5 项",
            "rule_hash_before": "000000000000",
            "rule_hash_after": _sha12("config/harness.yaml"),
            "output_evidence": "test: test_defect_reflow.py::T1",
        }
        e.update(over)
        return e


class TestDefectReflowJudge(unittest.TestCase):
    """判据本体：合规必须绿、每条违规必须红。"""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="vetmed-reflow-"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self.L = _Ledger(self._tmp)

    # ── T1 正向：合规条目必须绿（防判据过度敏感）────────────────────
    def test_T1_good_entry_is_green(self):
        """T1：字段齐备 + 哈希与当前文件一致 + 有产出证据 ⇒ rc=0。

        这条同时是「防误伤」验证：守卫不能把正常登记判红，
        否则第一跑就被关掉（与镜像块零假阳性同一纪律）。
        """
        rc, out, err = _run_reflow(self.L.write([self.L.good_entry()]))
        self.assertEqual(rc, 0, f"合规条目被判红（假阳性）：\n{out}\n{err}")
        self.assertIn("台账合规", out)

    # ── T2 缺必填字段必须红 ─────────────────────────────────────────
    def test_T2_missing_required_field_is_red(self):
        """T2：删掉 change ⇒ 必须报 E_MISSING_FIELD（缺字段不得静默放行）。"""
        e = self.L.good_entry()
        e.pop("change")
        rc, out, err = _run_reflow(self.L.write([e]))
        self.assertEqual(rc, 1, f"缺必填字段未判红 ⇒ 判据恒真：\n{out}")
        self.assertIn("E_MISSING_FIELD", out)

    # ── T3 哈希过期（事后改账）必须红 ───────────────────────────────
    def test_T3_stale_hash_is_red(self):
        """T3：rule_hash_after 写错 ⇒ 报 E_HASH_STALE。

        防的是「规则又改了却没更新台账」——台账一旦与文件脱钩，
        它就退化成一张没人维护的纸。
        """
        rc, out, err = _run_reflow(
            self.L.write([self.L.good_entry(rule_hash_after="ffffffffffff")]))
        self.assertEqual(rc, 1, f"哈希过期未判红：\n{out}")
        self.assertIn("E_HASH_STALE", out)

    # ── T4 无产出证据：空 ⇒ 红；补豁免三要素 ⇒ 绿 ────────────────────
    def test_T4_missing_output_evidence_needs_waiver(self):
        """T4：output_evidence 为空且无豁免 ⇒ 红；补齐豁免三要素 ⇒ 绿。

        这是本机制的核心判据：**「改规则不改输出」必须有产出证据或显式豁免**。
        豁免不是免检——它要留下理由、批准人、时间，口头豁免不算。
        """
        rc, out, _ = _run_reflow(
            self.L.write([self.L.good_entry(output_evidence="")]))
        self.assertEqual(rc, 1, f"无产出证据且无豁免仍放行 ⇒ 核心判据失效：\n{out}")
        self.assertIn("E_NO_OUTPUT_EVIDENCE", out)

        rc2, out2, _ = _run_reflow(self.L.write([self.L.good_entry(
            output_evidence="",
            waiver_reason="纯文档措辞订正，无判定语义变化",
            waiver_by="team-lead",
            waiver_at="2026-11-01T10:00:00+08:00")]))
        self.assertEqual(rc2, 0, f"合法豁免被判红（假阳性）：\n{out2}")

    # ── T5 重复 id 必须红 ───────────────────────────────────────────
    def test_T5_duplicate_id_is_red(self):
        """T5：同一 id 登记两次 ⇒ 报 E_DUPLICATE_ID（防重复登记冲抵）。"""
        e = self.L.good_entry()
        rc, out, _ = _run_reflow(self.L.write([e, dict(e)]))
        self.assertEqual(rc, 1, f"重复 id 未判红：\n{out}")
        self.assertIn("E_DUPLICATE_ID", out)

    # ── T6 台账不存在 ⇒ 依赖缺失 3（不是静默通过）────────────────────
    def test_T6_missing_ledger_is_dependency_error(self):
        """T6：台账文件不存在 ⇒ rc=3（依赖缺失），**不得**当成"空台账通过"。"""
        rc, out, err = _run_reflow(self._tmp / "nope.yaml")
        self.assertEqual(rc, 3, f"台账缺失未按依赖错误处理：rc={rc}\n{out}\n{err}")


class TestDefectReflowMutants(unittest.TestCase):
    """变异证明：把判据分支掏空后，正向反例必须失效。"""

    #: 变异锚点 = 必填字段循环（掏空它 ⇒ 缺字段不再被检出）
    _ANCHOR = '        for f in rc["required_fields"]:'
    _MUT = '        for f in []:  # MUTANT: 必填字段判据被掏空'

    def test_T7_mutant_kills_detection(self):
        """T7：把必填字段判据掏空 ⇒ T2 型违规**不再**被判红（证明判据不恒真）。"""
        src = CONTRACT.read_text(encoding="utf-8")
        self.assertEqual(1, src.count(self._ANCHOR),
                         f"变异锚点不唯一（{src.count(self._ANCHOR)} 处）⇒ mutant 不可靠")
        tmp = Path(tempfile.mkdtemp(prefix="vetmed-reflow-mut-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copy2(CONTRACT, tmp / "loop_contract.py")
        (tmp / "loop_contract.py").write_text(
            src.replace(self._ANCHOR, self._MUT, 1), encoding="utf-8")

        # 直接加载变异体判据并跑 T2 型条目
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lc_mutant", tmp / "loop_contract.py")
        lc = importlib.util.module_from_spec(spec)
        sys.modules["lc_mutant"] = lc
        spec.loader.exec_module(lc)

        import yaml
        cfg = yaml.safe_load((PKG / "config/harness.yaml").read_text(encoding="utf-8"))
        e = {"id": "RF-M-001", "rule_ref": "config/harness.yaml#loop_a",
             "rule_hash_before": "000000000000",
             "rule_hash_after": _sha12("config/harness.yaml"),
             "output_evidence": "test: x"}          # 故意缺 change
        ok, problems, _ = lc.defect_reflow_check(
            cfg, {"entries": [e]},
            {"config/harness.yaml": _sha12("config/harness.yaml")})
        self.assertTrue(ok,
                        f"掏空判据后仍检出缺字段 ⇒ 变异体没生效（证明会恒真）：{problems}")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_quality_closure.py —— B16 质量闭环守卫（升级方案 P4 · R5）

覆盖三支新机制：
  ① 验证风险分级（verify-tier）：高危全检 / 中危抽检 / 低危登记待办 + 占比超限阻断
  ② 跨任务质量趋势聚合（trend）：gate 事件 counts 时间序列；无数据不当 0
  ③ 闸4.5 之后的可选沉淀动作（sediment）：带 evidence_ref 回流，缺证据拒绝

纪律（同全包）：
  · 每条判据都必须**能红**——含变异测试：把判据掏空后场景必须翻松（证明覆盖）。
  · 变异测试必须跑**变异副本**的 harness.py（首版即踩此坑：跑真包 → 假红）。
  · 缺键即 fail-closed：分级配置缺键 ⇒ 拒绝出结论，不补内置值。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
TIERS = PKG / "config" / "verification-tiers.yaml"

PY = sys.executable


def _run(args, cwd=None, env=None):
    """跑 harness.py（真包），返回 (rc, stdout, stderr)。"""
    e = dict(os.environ)
    e.setdefault("VETMED_NOBROKER", "1")
    if env:
        e.update(env)
    proc = subprocess.run([PY, str(HARNESS)] + args, capture_output=True,
                          text=True, cwd=str(cwd or PKG), timeout=180, env=e)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _ws_with_cases(cases):
    """造一个带 cases_library.json 的临时工作区。"""
    ws = Path(tempfile.mkdtemp(prefix="b16-ws-"))
    d = ws / ".workbuddy" / "cases"
    d.mkdir(parents=True, exist_ok=True)
    (d / "cases_library.json").write_text(
        json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")
    return ws


def _read_trace(ws):
    f = ws / ".workbuddy" / "harness_trace.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _mutant_copy(mutate):
    """复制包到临时目录并对 harness.py 施加变异，返回 (tmp_pkg, harness_path)。"""
    tmp = Path(tempfile.mkdtemp(prefix="b16-mut-"))
    shutil.copytree(PKG / "scripts", tmp / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PKG / "config", tmp / "config")
    for rel in (".codebuddy-plugin/plugin.json", "agents"):
        src = PKG / rel
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    h = tmp / "scripts" / "harness.py"
    s = h.read_text(encoding="utf-8")
    mutated = mutate(s)
    assert mutated != s, "变异未生效（锚点未命中）"
    h.write_text(mutated, encoding="utf-8")
    return tmp, h


class TestVerificationTiers(unittest.TestCase):
    """① 验证风险分级。"""

    def test_T1_high_risk_keyword_goes_full(self):
        """高危关键词命中 ⇒ full（全检）。"""
        cases = [{"case_id": "C-001", "disease_name": "禽流感",
                  "title": "高致病性禽流感典型案例", "scenario": "某场爆发"}]
        ws = _ws_with_cases(cases)
        try:
            rc, out, err = _run(["verify-tier", "--workspace", str(ws)])
            self.assertEqual(rc, 0, f"verify-tier 失败: {err[:400]}")
            plan = json.loads(out)
            self.assertEqual(plan["buckets"]["full"], 1, "高危案例应入 full 桶")
            self.assertEqual(plan["cases"]["full"][0]["case_id"], "C-001")
            self.assertEqual(plan["cases"]["full"][0]["risk_tier"], "high")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T2_low_risk_explicit_goes_deferred_and_backlog_written(self):
        """显式低危 ⇒ deferred，且必须登记到待办清单（不得静默丢弃）。"""
        # 造 1 高危 + 1 低危 ⇒ deferred 占比 50%（不超 max_deferred_ratio），
        # 隔离验证「低危入 deferred + 待办登记」这一行为本身。
        cases = [{"case_id": "C-LOW", "disease_name": "普通背景",
                  "risk_tier": "low", "title": "背景补充"},
                 {"case_id": "C-HIGH", "disease_name": "禽流感",
                  "title": "高致病性禽流感典型案例", "scenario": "爆发"}]
        ws = _ws_with_cases(cases)
        try:
            rc, out, err = _run(["verify-tier", "--workspace", str(ws)])
            self.assertEqual(rc, 0, err[:400])
            plan = json.loads(out)
            self.assertEqual(plan["buckets"]["deferred"], 1, "显式低危应入 deferred")
            bp = ws / ".workbuddy" / "verification_backlog.json"
            self.assertTrue(bp.exists(), "deferred 案例必须写入待办清单")
            data = json.loads(bp.read_text(encoding="utf-8"))
            ids = [e.get("case_id") for e in data.get("entries", [])]
            self.assertIn("C-LOW", ids, "待办清单漏登记 deferred 案例")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T3_deferred_ratio_over_limit_blocks(self):
        """deferred 占比超上限 ⇒ rc=3 阻断（不静默降级为 sampled）。"""
        cases = [{"case_id": f"C-{i}", "disease_name": "背景",
                  "risk_tier": "low", "title": "背景"} for i in range(5)]
        cases.append({"case_id": "C-H", "disease_name": "禽流感",
                      "title": "高致病性禽流感案例", "scenario": "爆发"})
        ws = _ws_with_cases(cases)
        try:
            rc, out, err = _run(["verify-tier", "--workspace", str(ws)])
            self.assertEqual(rc, 3, f"占比超限应 rc=3 阻断，实得 {rc}（stderr {err[:200]}）")
            self.assertIn("超上限", err)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T4_missing_tiers_config_is_fail_closed(self):
        """分级配置缺键 ⇒ fail-closed（rc=1），不补内置值出结论。"""
        # 变异：让副本指向不存在的分级配置（模拟「配置缺失」场景）
        def mutate(s):
            return s.replace('os.path.join(PKG, "config", "verification-tiers.yaml")',
                             'os.path.join(PKG, "config", "__absent__.yaml")', 1)

        tmp, h = _mutant_copy(mutate)
        tiers_c = tmp / "config" / "verification-tiers.yaml"
        self.assertTrue(tiers_c.exists())
        tiers_c.unlink()
        ws = _ws_with_cases([{"case_id": "C-1", "title": "案例"}])
        try:
            proc = subprocess.run([PY, str(h), "verify-tier", "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 1,
                             f"配置缺失应 fail-closed rc=1，实得 {proc.returncode}")
            self.assertIn("fail-closed", proc.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T5_verify_tier_lands_in_trace(self):
        """分级动作必须入 trace（可审计）。"""
        ws = _ws_with_cases([{"case_id": "C-1", "title": "高致病性禽流感案例"}])
        try:
            _run(["verify-tier", "--workspace", str(ws)])
            evs = [e for e in _read_trace(ws) if e.get("event") == "verify_tier"]
            self.assertTrue(evs, "verify_tier 事件未落 trace")
            self.assertEqual(evs[-1]["detail"]["buckets"]["full"], 1)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class TestTrendAggregation(unittest.TestCase):
    """② 跨任务质量趋势聚合。"""

    def _seed_gate_events(self, ws, seq):
        """往 trace 写若干 gate 事件（counts 序列）。"""
        d = ws / ".workbuddy"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "harness_trace.jsonl").open("w", encoding="utf-8") as f:
            for i, c in enumerate(seq):
                rec = {"ts": f"2026-11-0{i+1}T10:00:00", "event": "gate",
                       "actor": "ppt-producer",
                       "detail": {"deck": f"d{i}.pptx", "exit": 0,
                                  "counts": c}}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def test_T6_trend_computes_p0_delta(self):
        """P0 序列 5→2 ⇒ 趋势 delta=-3 且判「改善」。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-trend-"))
        try:
            self._seed_gate_events(ws, [{"p0": 5, "p1": 3}, {"p0": 2, "p1": 1}])
            rc, out, err = _run(["trend", "--workspace", str(ws)])
            self.assertEqual(rc, 0, err[:300])
            rep = json.loads(out[out.index("{"):out.rindex("}") + 1])
            self.assertEqual(rep["with_counts"], 2)
            self.assertEqual(rep["p0_trend"]["delta"], -3)
            self.assertEqual(rep["p0_trend"]["verdict"], "改善")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T7_missing_counts_not_counted_as_zero(self):
        """counts 缺失的事件计入 without_counts，**不当成 P0=0**。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-trend2-"))
        try:
            d = ws / ".workbuddy"
            d.mkdir(parents=True, exist_ok=True)
            with (d / "harness_trace.jsonl").open("w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": "t0", "event": "gate", "actor": "x",
                                    "detail": {"deck": "a.pptx", "exit": 0}}) + "\n")
                f.write(json.dumps({"ts": "t1", "event": "gate", "actor": "x",
                                    "detail": {"deck": "b.pptx", "exit": 0,
                                               "counts": {"p0": 4, "p1": 2}}}) + "\n")
            rc, out, err = _run(["trend", "--workspace", str(ws)])
            self.assertEqual(rc, 0, err[:300])
            rep = json.loads(out[out.index("{"):out.rindex("}") + 1])
            self.assertEqual(rep["without_counts"], 1, "缺 counts 的事件应单独计桶")
            self.assertEqual(rep["with_counts"], 1)
            self.assertIsNone(rep["p0_trend"]["delta"],
                              "只有 1 个有计数的数据点不得算出趋势")
            self.assertIn("数据不足", rep["p0_trend"]["verdict"])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T8_trend_artifact_written(self):
        """趋势报告落盘（可复看）。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-trend3-"))
        try:
            self._seed_gate_events(ws, [{"p0": 3, "p1": 1}, {"p0": 1, "p1": 0}])
            _run(["trend", "--workspace", str(ws)])
            art = ws / ".workbuddy" / "artifacts" / "quality_trend.json"
            self.assertTrue(art.exists(), "趋势报告未落盘")
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class TestSedimentation(unittest.TestCase):
    """③ 闸4.5 之后的可选沉淀动作。"""

    def test_T9_sediment_requires_evidence_ref(self):
        """缺 --evidence-ref ⇒ 拒绝（无证据的沉淀=新增幻觉源）。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-sed-"))
        try:
            rc, out, err = _run(["sediment", "--target", "domain_profile",
                                 "--workspace", str(ws)])
            self.assertEqual(rc, 2, f"缺证据引用应 rc=2，实得 {rc}")
            self.assertIn("evidence-ref", err)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T10_sediment_writes_log_and_trace(self):
        """合法沉淀 ⇒ 写 sedimentation_log.jsonl + trace sediment 事件。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-sed2-"))
        try:
            rc, out, err = _run(["sediment", "--target", "domain_profile",
                                 "--evidence-ref", "domain-profiles.yaml#avian",
                                 "--summary", "禽流感要点回流",
                                 "--workspace", str(ws)])
            self.assertEqual(rc, 0, err[:300])
            log = ws / ".workbuddy" / "sedimentation_log.jsonl"
            self.assertTrue(log.exists(), "沉淀日志未落盘")
            entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["target"], "domain_profile")
            self.assertEqual(entry["evidence_ref"], "domain-profiles.yaml#avian")
            evs = [e for e in _read_trace(ws) if e.get("event") == "sediment"]
            self.assertTrue(evs, "sediment 事件未落 trace")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T11_unknown_target_rejected(self):
        """未知沉淀目标 ⇒ 拒绝（不得静默丢弃）。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-sed3-"))
        try:
            rc, out, err = _run(["sediment", "--target", "not_exist",
                                 "--evidence-ref", "abc-123",
                                 "--workspace", str(ws)])
            self.assertEqual(rc, 2, f"未知目标应 rc=2，实得 {rc}")
            self.assertIn("未知沉淀目标", err)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T12_sediment_is_not_a_stage(self):
        """沉淀**不得**占用 stage 号（既有契约锁死 stages 恰好 0-4）。"""
        ws = Path(tempfile.mkdtemp(prefix="b16-sed4-"))
        try:
            rc, out, err = _run(["state", "set", "--stage", "5",
                                 "--workspace", str(ws)])
            self.assertEqual(rc, 1, "stage 5 仍须被既有守卫拒绝")
            self.assertIn("拒绝写入", err)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class TestMutantsAreKilled(unittest.TestCase):
    """变异能红证明——掏空判据 ⇒ 场景必须翻松。"""

    def test_mutant_M1_drop_keyword_rule_makes_T1_red(self):
        """掏空高危关键词规则 ⇒ 高危案例不再入 full 桶（T1 翻松）。"""
        def mutate(s):
            old = '''    hit_kw = [k for k in kw if k and k in blob]'''
            new = '''    hit_kw = []  # MUTANT'''
            assert old in s
            return s.replace(old, new, 1)

        tmp, h = _mutant_copy(mutate)
        ws = _ws_with_cases([{"case_id": "C-001", "disease_name": "禽流感",
                              "title": "高致病性禽流感典型案例", "scenario": "爆发"}])
        try:
            proc = subprocess.run([PY, str(h), "verify-tier", "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0, "变异体自身不该崩")
            plan = json.loads(proc.stdout)
            self.assertEqual(plan["buckets"]["full"], 0,
                             "变异体仍判 full ⇒ 关键词规则没被 T1 覆盖（守卫空转）")
            self.assertNotEqual(plan["buckets"]["full"], 1,
                                "变异体行为与真源一致 ⇒ 变异未生效")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mutant_M2_drop_evidence_check_makes_T9_red(self):
        """掏空 evidence_ref 必填校验 ⇒ 缺证据也能沉淀（T9 翻松）。"""
        def mutate(s):
            old = '''    if sed.get("require_evidence_ref") and not ev_ref:'''
            new = '''    if False:  # MUTANT'''
            assert old in s
            return s.replace(old, new, 1)

        tmp, h = _mutant_copy(mutate)
        ws = Path(tempfile.mkdtemp(prefix="b16-mut-sed-"))
        try:
            proc = subprocess.run([PY, str(h), "sediment", "--target", "domain_profile",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0,
                             "变异体自身不该拒绝（掏空校验后应放行）")
            self.assertTrue((ws / ".workbuddy" / "sedimentation_log.jsonl").exists(),
                            "变异体未放行 ⇒ evidence_ref 判据没被 T9 覆盖")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mutant_M3_count_missing_as_zero_makes_T7_red(self):
        """把无 counts 当 P0=0 ⇒ T7 的「不当 0」判据必须翻红。"""
        def mutate(s):
            old = '''            if not isinstance(c, dict) or c.get("p0") is None:
                no_data += 1
                continue'''
            new = '''            if not isinstance(c, dict) or c.get("p0") is None:
                gates.append({"ts": r.get("ts"), "actor": r.get("actor"),
                              "deck": (r.get("detail") or {}).get("deck"),
                              "exit": (r.get("detail") or {}).get("exit"),
                              "p0": 0, "p1": 0, "note_coverage": None})
                continue  # MUTANT'''
            assert old in s
            return s.replace(old, new, 1)

        tmp, h = _mutant_copy(mutate)
        ws = Path(tempfile.mkdtemp(prefix="b16-mut-trend-"))
        try:
            d = ws / ".workbuddy"
            d.mkdir(parents=True, exist_ok=True)
            with (d / "harness_trace.jsonl").open("w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": "t0", "event": "gate", "actor": "x",
                                    "detail": {"deck": "a.pptx", "exit": 0}}) + "\n")
                f.write(json.dumps({"ts": "t1", "event": "gate", "actor": "x",
                                    "detail": {"deck": "b.pptx", "exit": 0,
                                               "counts": {"p0": 4, "p1": 2}}}) + "\n")
            proc = subprocess.run([PY, str(h), "trend", "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0)
            rep = json.loads(proc.stdout[proc.stdout.index("{"):proc.stdout.rindex("}") + 1])
            self.assertEqual(rep["without_counts"], 0,
                             "变异体把无数据当 0 ⇒ without_counts 判据没被 T7 覆盖")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_batch_gate_b21.py — B21/B22（第四轮诊断 F1/F2/F3/F5）回归守卫

立项背景（2026-11-03 第四轮从零诊断，全部本轮实证）：
  F1【P1】任务包校验是子串弱校验——acceptance_criteria 第五要素代码侧零校验
       （v3.17.0 标注跨批需求，两轮未清偿）。
  F2【P2】spawn 登记与真实拉起无对账（self-report 最后死角）。
  F3【P1】gate/verify_tier/trend/sediment 事件全 0——质量闭环零生产流量。
  F5【P3】智能化提升度指标无定义无采集。

本文件钉死的机器断言：
  T1  任务包 v5 正例（五要素+三件套合法）⇒ 通过
  T2  缺 acceptance_criteria ⇒ 拒（第五要素不再是文档级）
  T3  占位值（"x"/空串）⇒ 拒（子串时代的糊弄法失效）
  T4  judge_mode 不在枚举 / threshold 无「源 」引用 ⇒ 拒
  T5  散文提及字段名（无 JSON 结构）⇒ 拒（旧子串口径的死角封堵）
  T6  batch-open 写 gate 事件（counts.p0=拒收数, deck=[loopA]<bid>）
  T7  batch-close 写 gate 事件（counts 含 regression_ran/files_changed）
  T8  trend 聚合首通：含 [loopA] gate 事件后 trend 不再「无数据」
  T9  spawn --envelope：合法信封回填 sha256；缺六必填拒绝
  T10 收批对账：批内有无信封 spawn ⇒ envelopes_missing 非空 + stderr warning
  T11 智能化指标文件四指标三件套齐备（M1-M4 各含定义+数据源+公式）

用法：
    python3 -m pytest scripts/test_batch_gate_b21.py -q
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import harness  # noqa: E402

PKG = os.path.dirname(_HERE)
SHARED_CORE = os.path.join(os.path.dirname(PKG), "shared-core")


def _load_v5():
    """加载联邦真源的 check_task_package_v5（B21 新函数）。"""
    sys.path.insert(0, SHARED_CORE)
    import assemble_spawn_prompt as asp
    return asp


GOOD_PKG = {
    "objective": "产出呼吸症候群鉴别诊断教学蓝图",
    "output_format": "回传信封 result-envelope.yaml 六必填",
    "constraints": ["受众：高职大二"],
    "task_boundary": "只做教学设计不做逐页实现",
    "acceptance_criteria": [
        {"check": "学习目标三层可观察", "judge_mode": "人",
         "threshold": "三层各含动词，源 references/seven-dimension-rubric.md#维2"},
        {"check": "正文字号达标", "judge_mode": "机",
         "threshold": ">= 12.0，源 config/visual-rules.yaml#font.body_min_pt"},
    ],
}


class TestTaskPackageV5(unittest.TestCase):
    """T1-T5：任务包校验升维（F1）。"""

    @classmethod
    def setUpClass(cls):
        cls.asp = _load_v5()

    def test_T1_good_package_passes(self):
        ok, problems = self.asp.check_task_package_v5(json.dumps(GOOD_PKG, ensure_ascii=False))
        self.assertTrue(ok, f"合法任务包被拒：{problems}")

    def test_T2_missing_acceptance_criteria_rejected(self):
        bad = {k: v for k, v in GOOD_PKG.items() if k != "acceptance_criteria"}
        ok, problems = self.asp.check_task_package_v5(json.dumps(bad, ensure_ascii=False))
        self.assertFalse(ok, "缺第五要素竟通过——v3.17.0 跨批需求仍未清偿")
        # 断言消息口径：必须是「缺要素」（存在性层判定）——若只剩类型层报错，
        # 说明 TASK_PACKAGE_FIELDS_V5 清单被退化为四要素（变异 V1 的等价逃逸点）
        self.assertTrue(any("缺要素" in p and "acceptance_criteria" in p for p in problems),
                        f"缺第五要素应报「缺要素」而非仅类型错：{problems}")

    def test_T3_placeholder_values_rejected(self):
        bad = dict(GOOD_PKG)
        bad["objective"] = "x"
        ok, problems = self.asp.check_task_package_v5(json.dumps(bad, ensure_ascii=False))
        self.assertFalse(ok, "占位值 'x' 竟通过")
        self.assertTrue(any("占位" in p for p in problems))

    def test_T4_bad_enum_and_bare_threshold_rejected(self):
        bad = dict(GOOD_PKG)
        bad["acceptance_criteria"] = [
            {"check": "字号", "judge_mode": "机器", "threshold": "12pt"}]
        ok, problems = self.asp.check_task_package_v5(json.dumps(bad, ensure_ascii=False))
        self.assertFalse(ok)
        self.assertTrue(any("judge_mode" in p for p in problems), "枚举外值未抓")
        self.assertTrue(any("源" in p for p in problems), "裸阈值未抓")

    def test_T5_prose_mention_not_enough(self):
        """旧子串口径的死角：字段名出现在散文里（无 JSON 结构）必须拒。"""
        prose = ("本任务包五要素齐全：objective 是做蓝图，output_format 是信封，"
                 "constraints 有受众，task_boundary 明确，acceptance_criteria 含三件套"
                 "check/judge_mode/threshold。")
        ok, problems = self.asp.check_task_package_v5(prose)
        self.assertFalse(ok, "散文提及字段名竟通过——旧子串口径的糊弄法必须失效")


class _TmpLoopA(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = self._tmp.name
        self.cfg = _base_cfg()
        self.cfg.setdefault("loop_a", {})["state_file"] = \
            os.path.join(self.w, ".workbuddy", "loopA_state.json")
        self.cfg.setdefault("loop_b", {})["state_file"] = \
            os.path.join(self.w, ".workbuddy", "loopB_state.json")
        self._orig_load = harness.load_cfg
        harness.load_cfg = lambda: (self.cfg, True)

    def tearDown(self):
        harness.load_cfg = self._orig_load
        self._tmp.cleanup()


def _base_cfg():
    import yaml
    with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _args(**kw):
    base = dict(
        action="", loop="a", workspace="", actor="team-lead", deck="", wip="",
        task_id="", max_rounds=0, file="", replace=False, items="", item="",
        page="", severity="", owner="", decision=None, confirmed=False, reason="",
        p0=None, p1=None, p2=None, verify_json="", allow_unverified=False,
        files="", batch="", regression="", n=1, lint_json="", geo_baseline="",
        read_log="", elements="", caption=False, out="", check_refs=False,
        kind="", note="", path="", force=False,
        keep=0, drop_open="", dry_run=False,
        agent="", stage=None, input_bytes=0, output_bytes=0, envelope="",
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def _run(cmd_args):
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            rc = harness.cmd_loop(cmd_args)
        except SystemExit as e:
            rc = e.code
    return rc, so.getvalue(), se.getvalue()


def _run_spawn(a):
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            rc = harness.cmd_spawn(a)
        except SystemExit as e:
            rc = e.code
    return rc, so.getvalue(), se.getvalue()


def _trace_events_of(w, ev):
    tp = os.path.join(w, ".workbuddy", "harness_trace.jsonl")
    out = []
    if not os.path.isfile(tp):
        return out
    with open(tp, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == ev:
                out.append(r)
    return out


class TestBatchGateEvents(_TmpLoopA):
    """T6-T8：批次生命周期接入 gate 事件面（F3 可行子集）。"""

    def test_T6_batch_open_writes_gate_event(self):
        rc, _so, _se = _run(_args(action="batch-open", loop="a", workspace=self.w,
                                  files=os.path.join(PKG, "scripts", "harness.py"),
                                  batch="b9000000001", note="T6"))
        self.assertEqual(rc, 0)
        gates = _trace_events_of(self.w, "gate")
        self.assertTrue(gates, "batch-open 未写 gate 事件——工程环流量未接线")
        g = gates[-1]["detail"]
        self.assertEqual(g["deck"], "[loopA]b9000000001")
        self.assertEqual(g["level"], "batch-open")
        self.assertEqual(g["counts"]["p0"], 0)

    def test_T7_batch_close_writes_gate_event(self):
        _run(_args(action="batch-open", loop="a", workspace=self.w,
                   files=os.path.join(PKG, "scripts", "harness.py"),
                   batch="b9000000002", note="T7"))
        # 隔离 git（patch 层与本测试无关）
        harness._git_changed_files = lambda scope=None: ([os.path.join(PKG, "scripts", "harness.py")], "")
        try:
            req = ",".join(_base_cfg()["loop_a"]["regression_required"])
            rc, _so, _se = _run(_args(action="batch-close", loop="a", workspace=self.w,
                                      batch="b9000000002", confirmed=True,
                                      regression=req))
        finally:
            del harness._git_changed_files
        self.assertEqual(rc, 0)
        gates = _trace_events_of(self.w, "gate")
        closes = [g for g in gates if g["detail"]["level"] == "batch-close"]
        self.assertTrue(closes, "batch-close 未写 gate 事件")
        c = closes[-1]["detail"]
        self.assertEqual(c["counts"]["p0"], 0)
        self.assertGreaterEqual(c["counts"]["regression_ran"], 7)  # B20 扩容后 7 项

    def test_T8_trend_has_data_after_batch_flow(self):
        """trend 数据源闭环：batch 流量写入后 trend 不再全无数据。"""
        self.test_T7_batch_close_writes_gate_event()   # 复用：开+收一批
        so = io.StringIO()
        args = types.SimpleNamespace(workspace=self.w, actor="team-lead")
        with contextlib.redirect_stdout(so):
            rc = harness.cmd_trend(args)
        self.assertEqual(rc, 0)
        raw = so.getvalue()
        # trend 输出 = JSON + 报告路径行（取首个平衡 JSON 段）
        i, j = raw.find("{"), raw.rfind("}")
        rep = json.loads(raw[i:j + 1])
        # 不再是无数据：with_counts ≥1（[loopA] gate 流量被聚合）
        self.assertGreaterEqual(rep.get("with_counts", 0), 1,
                                f"trend 仍无数据（rep={str(rep)[:300]}）——F3 未闭合")


class TestSpawnEnvelope(_TmpLoopA):
    """T9-T10：spawn-信封对账（F2）。"""

    def _make_envelope(self, complete=True):
        env = {"agent_id": "dvm-content-expert", "task_id": "T-B21",
               "phase": "2", "status": "success",
               "confidence": "high", "deliverable_summary": "蓝图 v1"}
        if not complete:
            del env["confidence"]
        p = os.path.join(self.w, "env.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(env, f, ensure_ascii=False)
        return p

    def test_T9_envelope_backfills_sha256(self):
        env = self._make_envelope()
        rc, so, _se = _run_spawn(_args(workspace=self.w, agent="dvm-content-expert",
                                       task_id="T-B21", stage=2,
                                       input_bytes=100, output_bytes=50,
                                       envelope=env))
        self.assertEqual(rc, 0, so[:200])
        spawns = _trace_events_of(self.w, "spawn")
        self.assertTrue(spawns)
        self.assertIn("envelope_sha256", spawns[-1]["detail"],
                      "信封 sha256 未回填——对账锚点缺失")
        self.assertEqual(spawns[-1]["detail"]["envelope_sha256"],
                         harness._sha256_file(env))

    def test_T9b_incomplete_envelope_rejected(self):
        env = self._make_envelope(complete=False)   # 缺 confidence
        rc, _so, se = _run_spawn(_args(workspace=self.w, agent="dvm-content-expert",
                                       task_id="T-B21", envelope=env))
        self.assertEqual(rc, 2, "缺六必填的信封竟被接受")
        self.assertIn("六必填", se)

    def test_T10_close_reconciles_missing_envelopes(self):
        """批内 spawn 无信封 ⇒ 收批 gate 事件 envelopes_missing 非空 + stderr warning。"""
        # 开批
        _run(_args(action="batch-open", loop="a", workspace=self.w,
                   files=os.path.join(PKG, "scripts", "harness.py"),
                   batch="b9000000003", note="T10"))
        # 批内登记一个 spawn（不带信封）
        _run_spawn(_args(workspace=self.w, agent="pedagogy-architect",
                         task_id="T-B21", stage=2))
        # 收批
        harness._git_changed_files = lambda scope=None: ([os.path.join(PKG, "scripts", "harness.py")], "")
        try:
            req = ",".join(_base_cfg()["loop_a"]["regression_required"])
            rc, _so, se = _run(_args(action="batch-close", loop="a", workspace=self.w,
                                     batch="b9000000003", confirmed=True,
                                     regression=req))
        finally:
            del harness._git_changed_files
        self.assertEqual(rc, 0)
        self.assertIn("未见回传信封", se, "无信封 spawn 未在 stderr 可见化")
        closes = [g for g in _trace_events_of(self.w, "gate")
                  if g["detail"]["level"] == "batch-close"]
        self.assertTrue(closes)
        d = closes[-1]["detail"]
        self.assertTrue(d.get("envelopes_missing"),
                        "envelopes_missing 为空——对账失效")
        self.assertEqual(d["counts"]["p1"], 1, "无信封 spawn 未计入 p1 warning 面")


class TestIntelligenceMetrics(unittest.TestCase):
    """T11：智能化指标定义齐备（F5）。"""

    def test_T11_metrics_file_complete(self):
        p = os.path.join(PKG, "references", "intelligence-metrics.md")
        self.assertTrue(os.path.isfile(p), "intelligence-metrics.md 不存在")
        src = open(p, encoding="utf-8").read()
        for m in ("M1", "M2", "M3", "M4"):
            self.assertIn(m, src, f"缺指标 {m}")
        # 三件套关键词（定义/数据源/公式）
        for kw in ("定义", "数据源事件", "口径公式"):
            self.assertIn(kw, src, f"三件套缺 {kw}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

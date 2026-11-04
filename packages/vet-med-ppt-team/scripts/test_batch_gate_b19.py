#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_batch_gate_b19.py — B19/B20（第三轮诊断 P1-1/P1-2/P2-1/P2-2）回归守卫

立项背景（2026-11-02 第三轮从零诊断，全部隔离实证）：
  P1-1  batch-close 不校验回归套件名真实性——传 nonexist_suite 被静默接受且
        ok:true，「跑过回归」可以是幻觉声明；且任意旧批次可被后续调用顺手闭合
        （诊断探针用假套件名闭合了 28 天前的 b1793532390，已回滚）。
  P1-2  trace_events 声明双向漂移——harness 常量有 domain_pack_check 而 yaml
        没有；yaml 有 compaction 而 harness 没有（「声明层≠执行层」复发）。
  P2-1  loopA_state 无压缩策略——71 批次/200KB，28 个测试残留未闭合批次。
  P2-2  regression_required 只有 3 项——四套高频连带守卫全靠记忆传参。

本文件钉死的机器断言：
  T1  未知套件名 ⇒ rc=2 拒绝，且批次保持 open（fail-closed：不落 closed 状态）
  T2  已知套件名 + 齐备 ⇒ 正常收批（防卫过度：真实路径不能被误伤）
  T3  闭合旧批次（存在更新未闭合批次时）⇒ rc=2 拒绝 stale_batch_close
  T4  trace 事件双向对账：yaml 集合 == harness#TRACE_EVENTS_DECLARED 集合
  T5  yaml 含 B17 后新增的 domain_pack_check + compaction（漂移修复的定向断言）
  T6  batch-gc dry-run：只打印计划不落状态
  T7  batch-gc 真跑：closed 超保留数压入 archived；batches 数下降；未闭合不动
  T8  batch-gc --drop-open：误开批次标记 abandoned（留痕），closed 批次拒绝 drop
  T9  regression_required 扩容后 7 项生效（漏带任一 ⇒ regression_incomplete）
  T10 batch-gc 出现在 doctor 表（对 LLM 冷启动可发现）

用法：
    python3 -m pytest scripts/test_batch_gate_b19.py -q
    python3 scripts/test_batch_gate_b19.py
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
import loop_contract  # noqa: E402

PKG = os.path.dirname(_HERE)


def _base_cfg():
    """读真实配置（判据值与生产同源；测试另写一份=双源漂移）。"""
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


def _jout(s):
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        return json.loads(s[i:j + 1]) if 0 <= i < j else {}


class _TmpLoopA(unittest.TestCase):
    """每用例独立临时 state；不碰包目录真状态。"""

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

    # ── 辅助：开一个批次（走真实 batch-open 路径）─────────────────────────
    def _open(self, files, batch="b1000000000", note="B19测试批次"):
        return _run(_args(action="batch-open", loop="a", workspace=self.w,
                          files=files, batch=batch, note=note))

    def _close(self, batch, regression, confirmed=True):
        """收批时隔离真包 git 状态：改动集=声明集（模拟最小补丁合规态）。

        不隔离的话，batch-close 的 patch_discipline 校验会拿**真包当前
        git status** 比对（本批开发中的真实改动）⇒ 必然 undeclared_changes 红——
        那是 patch 层的事，与本文件聚焦的套件真实性/归属校验层无关。
        """
        declared = None
        p = self.cfg["loop_a"]["state_file"]
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                st0 = json.load(f)
            b0 = st0.get("batches", {}).get(batch) or {}
            declared = list(b0.get("declared_files") or [])
        orig = harness._git_changed_files
        harness._git_changed_files = lambda scope=None: (declared, "")
        try:
            return _run(_args(action="batch-close", loop="a", workspace=self.w,
                              batch=batch, confirmed=confirmed,
                              regression=regression))
        finally:
            harness._git_changed_files = orig

    def _state(self):
        p = self.cfg["loop_a"]["state_file"]
        with open(p, encoding="utf-8") as f:
            return json.load(f)


class TestSuiteReality(_TmpLoopA):
    """T1-T3：套件名真实性 + 闭合归属（P1-1）。"""

    def test_T1_unknown_suite_rejected_batch_stays_open(self):
        """T1：回归清单含不存在套件 ⇒ rc=2 拒绝，批次保持 open（fail-closed）。

        ⚠ 必须带齐全部 7 项真名再掺 1 个假名——否则先撞
        regression_incomplete（rc=1），测不到真实性校验层。
        """
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        req = ",".join(_base_cfg()["loop_a"]["regression_required"])
        rc, so, se = self._close("b1000000000", f"{req},nonexist_suite")
        self.assertEqual(rc, 2, f"幻觉套件名竟被接受：{se[:200]}")
        out = _jout(so)
        self.assertEqual(out["reason"], "unknown_regression_suite")
        self.assertIn("nonexist_suite", out["unknown_suites"])
        # fail-closed：批次必须保持 open（状态未污染）
        st = self._state()
        self.assertFalse(st["batches"]["b1000000000"]["closed"],
                         "被拒收批后批次竟变 closed——状态被污染")

    def test_T2_known_suites_close_normally(self):
        """T2：全部真实套件名 + 齐备 ⇒ 正常收批（不得误伤真实路径）。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        req = ",".join(_base_cfg()["loop_a"]["regression_required"])
        rc, so, _ = self._close("b1000000000", req)
        self.assertEqual(rc, 0, f"真实套件名齐备竟收批失败：{so[:300]}")
        st = self._state()
        self.assertTrue(st["batches"]["b1000000000"]["closed"])

    def test_T3_stale_batch_close_rejected(self):
        """T3：存在更新未闭合批次时闭合旧批次 ⇒ rc=2 拒绝 stale_batch_close。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"),
                   batch="b1000000000")
        self._open(files=os.path.join(PKG, "scripts", "harness.py"),
                   batch="b2000000000")
        req = ",".join(_base_cfg()["loop_a"]["regression_required"])
        rc, so, se = self._close("b1000000000", req)
        self.assertEqual(rc, 2, f"旧批次竟被顺手闭合：{se[:200]}")
        out = _jout(so)
        self.assertEqual(out["reason"], "stale_batch_close")
        self.assertEqual(out["newest_open_batch"], "b2000000000")


class TestTraceReconcile(_TmpLoopA):
    """T4-T5：trace_events 双向对账（P1-2）。"""

    def test_T4_yaml_equals_harness_constant(self):
        """T4：yaml#observability.trace_events 集合 == harness#TRACE_EVENTS_DECLARED 集合。

        双向差集都必须为空——这是 B17 漏 yaml 侧、v3.18.0 漏常量侧的
        双向漂移病灶的定向封堵。
        """
        import yaml
        with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        yset = set((cfg.get("observability") or {}).get("trace_events") or [])
        hset = set(harness.TRACE_EVENTS_DECLARED)
        self.assertEqual(yset - hset, set(),
                         f"yaml 有而 harness 常量没有（声明层≠执行层）：{sorted(yset - hset)}")
        self.assertEqual(hset - yset, set(),
                         f"harness 常量有而 yaml 没有（产出无声明）：{sorted(hset - yset)}")

    def test_T5_new_events_present(self):
        """T5：domain_pack_check（B17）与 compaction（v3.18.0）双侧均在——
        两个历史漂移点的定向回归。"""
        yset = set((_base_cfg().get("observability") or {}).get("trace_events") or [])
        hset = set(harness.TRACE_EVENTS_DECLARED)
        for ev in ("domain_pack_check", "compaction"):
            self.assertIn(ev, yset, f"{ev} 不在 yaml——B17 漂移复发")
            self.assertIn(ev, hset, f"{ev} 不在 harness 常量——v3.18.0 漂移复发")


class TestBatchGc(_TmpLoopA):
    """T6-T8：批次历史压缩（P2-1）。"""

    def _setup_batches(self, n_closed=3, n_open=2, keep_default=None):
        """直接构造 state：n_closed 个 closed + n_open 个未闭合批次。"""
        p = self.cfg["loop_a"]["state_file"]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        batches = {}
        for i in range(n_closed):
            batches[f"b{1000000000 + i}"] = {
                "id": f"b{1000000000 + i}", "theme": f"旧批次{i}",
                "closed": True, "closed_at": f"2026-10-{i + 1:02d}T00:00:00+08:00",
                "declared_files": [], "regression_ran": []}
        for i in range(n_open):
            batches[f"b{2000000000 + i}"] = {
                "id": f"b{2000000000 + i}", "theme": f"在途批次{i}",
                "closed": False, "declared_files": []}
        st = {"batches": batches, "last_writer": "team-lead", "history": []}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        return st

    def test_T6_dry_run_no_mutation(self):
        """T6：--dry-run 只打印计划，状态文件不变。"""
        self._setup_batches(n_closed=3, n_open=2)
        rc, so, _ = _run(_args(action="batch-gc", loop="a", workspace=self.w,
                               keep=1, dry_run=True))
        self.assertEqual(rc, 0)
        out = _jout(so)
        self.assertTrue(out["ok"])
        self.assertEqual(out["mode"], "dry-run")
        self.assertEqual(len(out["plan"]["archive"]), 2)  # 3 closed 保 1 ⇒ 压 2
        st = self._state()
        self.assertEqual(len(st["batches"]), 5, "dry-run 竟然改了状态")

    def test_T7_gc_archives_old_closed_only(self):
        """T7：真跑——closed 超保留压入 archived；未闭合批次原封不动。"""
        self._setup_batches(n_closed=3, n_open=2)
        rc, so, _ = _run(_args(action="batch-gc", loop="a", workspace=self.w,
                               keep=1))
        self.assertEqual(rc, 0)
        st = self._state()
        # 3 closed 保 1 ⇒ batches 剩 1 closed + 2 open = 3
        self.assertEqual(len(st["batches"]), 3,
                         f"压缩后 batches 数不对：{sorted(st['batches'])}")
        arch = st.get("archived_batches") or []
        self.assertEqual(len(arch), 2, "archived 摘要区数量不对")
        for a in arch:
            self.assertIn("id", a) and self.assertIn("theme", a) \
                and self.assertIn("closed_at", a)
        # 未闭合批次必须在（不被误压缩）
        for i in range(2):
            self.assertIn(f"b{2000000000 + i}", st["batches"],
                          "未闭合批次竟被压缩——在途信号被毁")
            self.assertFalse(st["batches"][f"b{2000000000 + i}"]["closed"])

    def test_T8_drop_open_marks_abandoned(self):
        """T8：误开批次显式废弃（标记 abandoned 留痕）；closed 批次拒绝 drop。"""
        self._setup_batches(n_closed=1, n_open=2)
        rc, so, _ = _run(_args(action="batch-gc", loop="a", workspace=self.w,
                               drop_open="b2000000000", keep=10))
        self.assertEqual(rc, 0)
        st = self._state()
        self.assertTrue(st["batches"]["b2000000000"].get("abandoned"),
                        "drop-open 未标记 abandoned（静默删=不可溯）")
        self.assertIn("abandoned_at", st["batches"]["b2000000000"])
        # closed 批次走 drop-open ⇒ 拒绝
        rc2, _so2, _se2 = _run(_args(action="batch-gc", loop="a", workspace=self.w,
                                     drop_open="b1000000000", keep=10))
        self.assertEqual(rc2, 2, "closed 批次竟可被 drop-open 废弃")


class TestRegressionExpansion(_TmpLoopA):
    """T9：regression_required 扩容（P2-2）。"""

    def test_T9_seven_items_enforced(self):
        """T9：7 项必备生效——只带旧 3 项 ⇒ 拒绝并报缺 4 项新套件。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        rc, so, _ = self._close(
            "b1000000000",
            "ensure_settings,test_harness,test_five_gates")
        self.assertEqual(rc, 1, "扩容前 3 项竟还能收批——扩容没生效")
        out = _jout(so)
        self.assertEqual(out["reason"], "regression_incomplete")
        for s in ("test_dead_config_disposition", "test_inspection_zone_registry_red",
                  "test_arch_drift", "test_domain_pack"):
            self.assertIn(s, out["missing"], f"{s} 未被报缺")


class TestDoctorDiscoverability(_TmpLoopA):
    """T10：batch-gc 可发现性（对 LLM 冷启动存在）。"""

    def test_T10_batch_gc_in_doctor(self):
        args = types.SimpleNamespace(workspace=tempfile.mkdtemp())
        so = io.StringIO()
        with contextlib.redirect_stdout(so):
            rc = harness.cmd_doctor(args)
        self.assertEqual(rc, 0)
        doc = json.loads(so.getvalue())
        actions = {a["action"] for a in doc.get("loop_actions", [])}
        self.assertIn("batch-gc", actions,
                      "batch-gc 未入 doctor 表——对 LLM 冷启动不存在")
        for a in doc["loop_actions"]:
            if a["action"] == "batch-gc":
                self.assertTrue(a.get("judge_source"),
                                "batch-gc 缺 judge_source（有动作、无判据）")


if __name__ == "__main__":
    unittest.main(verbosity=2)

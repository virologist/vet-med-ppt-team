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

  ── 任务F·病灶②（回归实测证据通道）：T-EV-1..T-EV-7 ────────────────────
  病灶（P0 级纪律漏洞）：`b["regression_ran"] = ran` 里的 ran 就是 --regression
        **命令行传入的名字列表**——它是**声明**，不是实测。B19 的真实性校验只验
        「套件名真实存在」，**从不验「套件是否真跑过」** ⇒ 纯声明即可收批
        （实测 b1793794707 在 1 秒内完成 open→close，却记录了 7 项回归清单）。
  本组用例钉死「声明 vs 实测分列」：
  T-EV-1 完整 evidence（全 rc=0）⇒ 收批成功，confirmed=true，regression_verified 非空
  T-EV-2 **不带** evidence ⇒ 收批成功但 confirmed=false（confirmed_reason=
        no_regression_evidence）——「没验证过」不得看起来像「验证过」
  T-EV-3 evidence 里有套件 rc=1 ⇒ **rc=1 拒绝**，批次保持 open
  T-EV-4 evidence 套件名与 --regression 名单不一致 ⇒ **rc=2 拒绝**，批次保持 open
  T-EV-5 evidence 少一项（未覆盖全部名单）⇒ **rc=2 拒绝**，批次保持 open
  T-EV-6 evidence 文件不存在 / JSON 非法 ⇒ **rc=2 拒绝**，错误信息清晰
  T-EV-7 **反向对照**：把 evidence 校验逻辑改坏（rc≠0 不判失败）⇒ T-EV-3 必须翻红

用法：
    python3 -m pytest scripts/test_batch_gate_b19.py -q
    python3 scripts/test_batch_gate_b19.py
    # 反向对照（整份测试跑在变异副本上）：
    python3 scripts/test_batch_gate_b19.py   #（VET_EV_MUTANT_PKG 指向变异包）
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))

# ── 反向对照开关（任务F·病灶② T-EV-7）──────────────────────────────────
# ⚠ 判据失效时看不出来（v3.27.0 教训）：本文件**不得**用「AST 里有没有出现某个
#   名字」当反向对照的判据——必须**真实改坏代码并让真实用例翻红**。
#   机制：把 scripts/ + config/ 复制到临时目录 → 改坏其中的 harness.py →
#   用 VET_EV_MUTANT_PKG 指向该副本 → 本文件**整份**跑在变异体上
#   ⇒ 若 T-EV-3 在变异体上仍绿 ⇒ 判据没被覆盖（真包守卫会假绿）。
_EV_MUTANT_PKG = os.environ.get("VET_EV_MUTANT_PKG", "").strip()

if _EV_MUTANT_PKG:
    # 反向对照模式：harness/loop_contract 均从变异副本导入（变异副本优先入 path）
    _EV_MUTANT_PKG = os.path.abspath(_EV_MUTANT_PKG)
    sys.path.insert(0, os.path.join(_EV_MUTANT_PKG, "scripts"))
    PKG = _EV_MUTANT_PKG
else:
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    PKG = os.path.dirname(_HERE)

import harness  # noqa: E402
import loop_contract  # noqa: E402

PY = sys.executable


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
        files="", batch="", regression="", regression_evidence="",
        n=1, lint_json="", geo_baseline="",
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

    def _close(self, batch, regression, confirmed=True, evidence=""):
        """收批时隔离真包 git 状态：改动集=声明集（模拟最小补丁合规态）。

        不隔离的话，batch-close 的 patch_discipline 校验会拿**真包当前
        git status** 比对（本批开发中的真实改动）⇒ 必然 undeclared_changes 红——
        那是 patch 层的事，与本文件聚焦的套件真实性/归属校验层无关。

        ⚠ `evidence` = --regression-evidence 的路径（任务F·病灶②）。传空串 =
           不提供实测证据 ⇒ 走降级路径（confirmed=false）。
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
                              regression=regression,
                              regression_evidence=evidence))
        finally:
            harness._git_changed_files = orig

    def _state(self):
        p = self.cfg["loop_a"]["state_file"]
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    # ── 辅助：写一份实测证据文件（任务F·病灶②）───────────────────────────
    def _evidence(self, suites, name="ev.json", raw=None):
        """在临时工作区写证据文件，返回绝对路径。

        suites: [{"suite": ..., "rc": 0, "duration_s": ...}, ...]
        raw:    直接写原始文本（用于「JSON 非法」场景）
        """
        p = os.path.join(self.w, name)
        with open(p, "w", encoding="utf-8") as f:
            if raw is not None:
                f.write(raw)
            else:
                json.dump({"suites": suites}, f, ensure_ascii=False)
        return p

    def _req(self):
        """当前 yaml 的 regression_required 清单（动态取，不硬编码）。"""
        return list(_base_cfg()["loop_a"]["regression_required"])

    def _open_and_prepare(self, batch="b1000000000"):
        """开批 + 返回 (声明清单, 证据模板)——任务F·病灶② 专用。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"), batch=batch)
        req = self._req()
        suites = [{"suite": s, "rc": 0, "duration_s": 1.0} for s in req]
        return req, suites


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


# ══════════════════════════════════════════════════════════════════════════
# 任务F·病灶⑤：abandoned 口径一致性（batch-gc 认废弃 / batch-close 不认）
# ══════════════════════════════════════════════════════════════════════════
# 背景（真实缺陷，非假设）：
#   `batch-gc --drop-open` 的 `before_open` 统计**认** `abandoned`，
#   而 `batch-close` 的归属校验 `opened_ids` **不认** ⇒ 两处口径漂移 ⇒
#   「**标记废弃**」≠「**判定废弃**」⇒
#     ① 真正的最新批次可能因一个已废弃的更晚批次而被 stale 误拦（收不掉）
#     ② batch-gc 报告的 open 数与 batch-close 实际认定的 open 数对不上
#        ⇒ **操作成功、效果为零**
#   ⇒ 根治：抽 `_open_batches()` 单一真源，两处调用同一函数。
class TestAbandonedConsistency(_TmpLoopA):
    """病灶⑤：废弃口径一致（能红反例：改回旧口径 ⇒ 断言翻红）。"""

    def _setup_mixed(self):
        """构造：1 个正常 open + 1 个**较新**但已 abandoned 的批次。

        ⚠ 关键是 abandoned 那个**序号更大**（更新）⇒ 旧口径下它会
          成为「最新未闭合批次」⇒ 正常那个被 stale 误拦。

        ⚠ 正常批次的 `declared_files` 必须**非空**且为包内真实文件
          （最小补丁纪律要求「开工前声明」；声明集为空会被
          `patch_discipline=minimal` 先拦掉 ⇒ 测不到 stale 层）。
        """
        p = self.cfg["loop_a"]["state_file"]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        decl = [os.path.join(PKG, "scripts", "harness.py")]
        batches = {
            "b1000000000": {"id": "b1000000000", "theme": "正常在途批次",
                            "closed": False, "declared_files": list(decl),
                            "regression_required": list(self._req()),
                            "confirmed": False},
            "b2000000000": {"id": "b2000000000", "theme": "已废弃的误开批次",
                            "closed": False, "abandoned": True,
                            "abandoned_at": "2026-11-04T00:00:00+08:00",
                            "declared_files": list(decl),
                            "regression_required": list(self._req()),
                            "confirmed": False},
        }
        st = {"batches": batches, "last_writer": "team-lead", "history": []}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        return st

    def test_T9a_open_batches_excludes_abandoned(self):
        """T9a：`_open_batches()` 必须排除 abandoned 与 closed（口径真源）。"""
        batches = {"b1": {"closed": False},
                   "b2": {"closed": False, "abandoned": True},
                   "b3": {"closed": True},
                   "b4": {"closed": False, "abandoned": True},
                   "b5": "not-a-dict"}
        got = harness._open_batches(batches)
        self.assertEqual(got, ["b1"],
                         f"未闭合且未废弃的批次集不对：{got}")
        self.assertIsInstance(got, list,
                              "必须返回 list（下游 max()/JSON 序列化依赖）")

    def test_T9b_gc_before_open_and_close_use_same_criterion(self):
        """T9b：两处口径**必须一致**（batch-gc 的 before_open == _open_batches 长度）。

        ⚠ 这是病灶⑤ 的**核心判据**：口径漂移 ⇒ 「操作成功、效果为零」。
        """
        self._setup_mixed()
        rc, so, _ = _run(_args(action="batch-gc", loop="a", workspace=self.w,
                               dry_run=True))
        self.assertEqual(rc, 0)
        plan = _jout(so).get("plan") or {}
        st = self._state()
        self.assertEqual(
            plan.get("before_open"), len(harness._open_batches(st["batches"])),
            "batch-gc 的 before_open 与 batch-close 的口径不一致"
            "（标记废弃 ≠ 判定废弃）")

    def test_T9c_abandoned_newer_batch_does_not_block_close(self):
        """T9c：较新的**已废弃**批次不得 stale 拦住正常批次（能红反例）。

        ⚠ 旧口径下 `opened_ids` 含 abandoned 批次 ⇒ `max()` 取到它 ⇒
          正常批次被判 stale ⇒ rc=2 收不掉 ⇒ 端到端可观测。
        """
        self._setup_mixed()
        req = ",".join(self._req())
        rc, so, se = self._close("b1000000000", req)
        self.assertNotEqual(
            rc, 2,
            f"被已废弃的较新批次 stale 拦住了（口径漂移）：{se[:300]}")
        self.assertEqual(rc, 0,
                         f"正常批次收批失败（应成功）：{se[:300]}")
        st = self._state()
        self.assertTrue(st["batches"]["b1000000000"].get("closed"),
                        "正常批次未闭合 ⇒ 收批未生效")

    def test_T9d_reverse_control_old_criterion_blocks_close(self):
        """T9d 反向对照：把口径改回「只认 closed」⇒ T9c 必须真的失败。

        ⚠ **真对照**（隔离副本 + 源码级 mutator）：
          在临时目录复制 harness.py，把 `_open_batches` 的判据删掉
          `abandoned` 那一项 ⇒ 变回旧口径 ⇒ 复跑 T9c 的场景
          ⇒ 必须复现「stale 拦截」（rc=2）⇒ 证明 T9c 真在读这个口径。

        ⚠ 对照走**隔离副本**：绝不改真包文件。
        """
        import shutil
        tmpdir = tempfile.mkdtemp(prefix="vet-b19-abandoned-mut-")
        try:
            mut_dir = os.path.join(tmpdir, "scripts")
            os.makedirs(mut_dir, exist_ok=True)
            src = Path(harness.__file__).read_text(encoding="utf-8")
            mutated = src.replace(
                'if isinstance(v, dict) and not v.get("closed")\n'
                '            and not v.get("abandoned")]',
                'if isinstance(v, dict) and not v.get("closed")]')
            self.assertNotEqual(
                mutated, src,
                "变异失败：未找到 `_open_batches` 的判据源码（对照失真）")
            mut_path = os.path.join(mut_dir, "harness.py")
            with open(mut_path, "w", encoding="utf-8") as f:
                f.write(mutated)
            mut = _load_harness_from_path(mut_path)
            batches = {"b1000000000": {"closed": False},
                       "b2000000000": {"closed": False, "abandoned": True}}
            self.assertEqual(
                mut._open_batches(batches), ["b1000000000", "b2000000000"],
                "变异体未复现旧口径（含 abandoned）⇒ 对照失真")
            #: 旧口径下 b1000000000 会被 stale 拦
            opened = mut._open_batches(batches)
            bid = "b1000000000"
            blocked = (bid in opened
                       and bid != max(opened, key=mut._batch_seq))
            self.assertTrue(
                blocked,
                "对照失真：旧口径下正常批次未被 stale 拦 ⇒ 该对照证明不了缺陷")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        #: 真包必须仍是新口径
        batches = {"b1000000000": {"closed": False},
                   "b2000000000": {"closed": False, "abandoned": True}}
        self.assertEqual(harness._open_batches(batches), ["b1000000000"],
                         "真包口径被污染（对照不得改真包）")


def _load_harness_from_path(path):
    """按文件路径加载 harness 模块（隔离副本用）。"""
    import importlib.util as _iu
    spec = _iu.spec_from_file_location("v328_harness_mutant", path)
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class TestRegressionEvidence(_TmpLoopA):
    """T-EV-1..T-EV-6：回归**实测证据**通道（任务F·病灶②）。

    核心口径（**声明 vs 实测分列**）：
      · regression_ran      —— **声明**（--regression 传入的名字列表）
      · regression_verified —— **实测**（--regression-evidence 提供的证据）
      · confirmed           —— 账本里**唯一**代表「这批验收过」的标记
    ⚠ 没有实测证据却置 confirmed=true ⇒ 漏洞原样保留 ⇒ 必须降级。
    """

    # ── T-EV-1：完整 evidence（全 rc=0）⇒ confirmed=true ─────────────────
    def test_TEV1_full_evidence_confirms(self):
        """T-EV-1：证据齐备且全绿 ⇒ 收批成功，confirmed=true，regression_verified 非空。"""
        req, suites = self._open_and_prepare()
        ev = self._evidence(suites)
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 0, f"证据齐备却收批失败：{so[:300]}{se[:300]}")
        b = self._state()["batches"]["b1000000000"]
        self.assertTrue(b.get("closed"), "批次未闭合")
        self.assertIs(b.get("confirmed"), True,
                      f"有完整实测证据却未 confirmed=true：{b.get('confirmed_reason')}")
        self.assertEqual(b.get("confirmed_reason"), "evidence_ok")
        # 实测证据必须**分列**落账（且非空）
        self.assertTrue(b.get("regression_verified"),
                        "regression_verified 为空——实测证据未落账")
        self.assertEqual(len(b["regression_verified"]), len(req))
        for s in b["regression_verified"]:
            self.assertEqual(s["rc"], 0)
        # 声明清单（regression_ran）保持既有行为，不被实测证据改写
        self.assertEqual(sorted(b.get("regression_ran") or []), sorted(req),
                         "regression_ran（声明）被改写——既有字段语义被破坏")

    # ── T-EV-2：不给 evidence ⇒ 放行但 confirmed 降级 ───────────────────
    def test_TEV2_no_evidence_downgrades_confirmed(self):
        """T-EV-2：**不带** evidence ⇒ 收批成功但 confirmed=false。

        ⚠ 这是本批的**核心**：confirmed 是账本里唯一代表「这批验收过」的标记。
        若无实测证据仍置 confirmed=true ⇒ 纯声明收批的漏洞原样保留。
        """
        req, _ = self._open_and_prepare()
        rc, so, se = self._close("b1000000000", ",".join(req))
        self.assertEqual(rc, 0, f"未提供证据竟拒批（向后兼容被破坏）：{so[:300]}{se[:300]}")
        b = self._state()["batches"]["b1000000000"]
        self.assertTrue(b.get("closed"), "批次未闭合（未提供证据不该阻断收批）")
        self.assertIs(b.get("confirmed"), False,
                      "未提供实测证据却 confirmed=true——「跑过回归」仍可是一句纯声明")
        self.assertEqual(b.get("confirmed_reason"), "no_regression_evidence")
        self.assertEqual(b.get("regression_verified"), [],
                         "无实测证据却记了 regression_verified——凭空造证")
        # 声明清单仍在（向后兼容：既有字段不被删）
        self.assertEqual(sorted(b.get("regression_ran") or []), sorted(req))
        # 降级必须**显式告警**（不得静默降级）
        self.assertIn("未提供实测证据", se,
                      "降级未在 stderr 显式告警——静默降级会让『没验证过』"
                      "看起来像『验证过』")

    # ── T-EV-3：evidence 里有 rc=1 ⇒ rc=1 拒绝，批次保持 open ───────────
    def test_TEV3_nonzero_rc_rejects(self):
        """T-EV-3：实测证据显示某套件 rc=1 ⇒ **rc=1 拒绝收批**，批次保持 open。"""
        req, suites = self._open_and_prepare()
        suites[2]["rc"] = 1
        ev = self._evidence(suites)
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 1, f"实测证据显示失败竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_rc_nonzero")
        # 必须点名哪一项失败
        failed = out.get("detail", {}).get("failed") or []
        self.assertTrue(failed, "未点名失败套件——错误信息不可用")
        self.assertEqual(failed[0]["suite"], suites[2]["suite"])
        self.assertEqual(failed[0]["rc"], 1)
        self.assertIn(suites[2]["suite"], se, "stderr 未点名失败套件")
        # fail-closed：批次必须保持 open
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed——状态被污染")
        self.assertIsNot(b.get("confirmed"), True, "被拒收批却标了 confirmed=true")

    # ── T-EV-4：evidence 套件名与 --regression 名单不一致 ⇒ rc=2 ────────
    def test_TEV4_suite_name_mismatch_rejects(self):
        """T-EV-4：evidence 套件名与 --regression 名单不一致 ⇒ **rc=2 拒绝**（防张冠李戴）。"""
        req, suites = self._open_and_prepare()
        # 名单里没有这一项 ⇒ 张冠李戴（拿了别的批次的证据）
        suites.append({"suite": "some_other_suite", "rc": 0, "duration_s": 0.5})
        ev = self._evidence(suites)
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 2, f"套件名对不上竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_suite_mismatch")
        self.assertIn("some_other_suite", out["detail"]["extra"])
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed")

    # ── T-EV-5：evidence 少一项 ⇒ rc=2 拒绝 ─────────────────────────────
    def test_TEV5_incomplete_coverage_rejects(self):
        """T-EV-5：evidence 少一项（未覆盖全部名单）⇒ **rc=2 拒绝**。

        语义：有声明项没实测 ⇒ 实测证据**不覆盖**声明清单 ⇒ 不能算「已验证」。
        """
        req, suites = self._open_and_prepare()
        dropped = suites.pop()["suite"]
        ev = self._evidence(suites)
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 2, f"证据少一项竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_suite_mismatch")
        self.assertIn(dropped, out["detail"]["missing"])
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed")

    # ── T-EV-6：evidence 文件不存在 / JSON 非法 ⇒ rc=2 ──────────────────
    def test_TEV6_missing_evidence_file_rejects(self):
        """T-EV-6-a：evidence 文件不存在 ⇒ **rc=2 拒绝**，错误信息清晰。"""
        req, _ = self._open_and_prepare()
        missing = os.path.join(self.w, "no_such_evidence.json")
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=missing)
        self.assertEqual(rc, 2, f"证据文件缺失竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_invalid")
        self.assertIn("不存在", se)
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed")

    def test_TEV6b_invalid_evidence_json_rejects(self):
        """T-EV-6-b：evidence JSON 非法 ⇒ **rc=2 拒绝**，错误信息清晰。"""
        req, _ = self._open_and_prepare()
        ev = self._evidence(None, name="bad.json", raw="{ this is not json ]")
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 2, f"JSON 非法竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_invalid")
        self.assertIn("不可解析", se)
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed")

    def test_TEV6c_evidence_wrong_shape_rejects(self):
        """T-EV-6-c：evidence 结构非法（suites 缺失/为空）⇒ rc=2 拒绝。

        ⚠ 结构非法**不得**按「空 = 全绿」处理——静默取默认 = 造假。
        """
        req, _ = self._open_and_prepare()
        ev = self._evidence(None, name="empty.json", raw='{"suites": []}')
        rc, so, se = self._close("b1000000000", ",".join(req), evidence=ev)
        self.assertEqual(rc, 2, f"空证据竟收批成功：{so[:300]}{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("reason"), "evidence_invalid")
        b = self._state()["batches"]["b1000000000"]
        self.assertFalse(b.get("closed"), "被拒收批后批次竟变 closed")


class TestRegressionEvidenceMutant(_TmpLoopA):
    """T-EV-7：**反向对照**——把证据校验逻辑改坏 ⇒ T-EV-3 必须翻红。

    ⚠ 本包历史教训（v3.27.0）：用「AST 里有没有出现某个名字」当反向对照判据
      ⇒ **反向对照失败**，判据失效时看不出来。
    ⇒ 本用例**真实改坏代码**（复制包到临时目录 → 改坏其中的 harness.py），
      再让**真实的 T-EV-3 断言**跑在变异体上：
        · 变异体下 T-EV-3 必须**翻红**（rc≠1 ⇒ 收批成功 ⇒ 断言失败）；
        · 真包下 T-EV-3 必须**绿**。
    ⚠ 用 subprocess 起独立进程跑变异体，避免 import 期缓存污染真包模块。
    """

    MUTANT_ANCHOR = '''    fails = _evidence_failures(suites)
    if fails:
        return {"ok": False, "rc": 1, "reason": "evidence_rc_nonzero",'''
    MUTANT_NEW = '''    fails = []  # MUTANT: 故意不判 rc≠0（模拟「实测证据校验失效」）
    if fails:
        return {"ok": False, "rc": 1, "reason": "evidence_rc_nonzero",'''

    def _mutant_pkg(self):
        """复制包到临时目录并改坏 harness.py 的证据校验；返回 (tmp_pkg, harness_path)。"""
        tmp = tempfile.mkdtemp(prefix="ev-mutant-")
        shutil.copytree(os.path.join(PKG, "scripts"),
                        os.path.join(tmp, "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(PKG, "config"), os.path.join(tmp, "config"))
        for rel in (".codebuddy-plugin/plugin.json", "agents"):
            src = os.path.join(PKG, rel)
            dst = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        h = os.path.join(tmp, "scripts", "harness.py")
        with open(h, encoding="utf-8") as f:
            s = f.read()
        self.assertIn(self.MUTANT_ANCHOR, s,
                      "变异锚点未命中——harness.py 结构变了，反向对照失效")
        s2 = s.replace(self.MUTANT_ANCHOR, self.MUTANT_NEW, 1)
        self.assertNotEqual(s2, s, "变异未生效")
        with open(h, "w", encoding="utf-8") as f:
            f.write(s2)
        return tmp, h

    def test_TEV7_mutant_makes_TEV3_red(self):
        """T-EV-7：真实改坏证据校验 ⇒ T-EV-3 判据必须翻红。

        判据不是「代码里有没有出现某个名字」，而是**真实行为差异**：
          · 变异体下 batch-close 对 rc=1 的证据**不得**拒批（若仍拒批 ⇒ 变异没生效
            或 T-EV-3 根本没测到这一层）；
          · 真包下 T-EV-3 绿（否则是「变异体与真包都不判」——判据本身失效）。
        """
        tmp, h = self._mutant_pkg()
        try:
            # ① 变异体：rc=1 的证据**竟被收批**（⇒ 证据校验层被改坏）
            ws = tempfile.mkdtemp(prefix="ev-mutant-ws-")
            try:
                req = list(_base_cfg()["loop_a"]["regression_required"])
                ev = os.path.join(ws, "ev.json")
                with open(ev, "w", encoding="utf-8") as f:
                    json.dump({"suites": [{"suite": s, "rc": 0, "duration_s": 1.0}
                                           for s in req]}, f)
                # 先开批（走变异体自己的 harness）
                proc = subprocess.run(
                    [PY, h, "loop", "batch-open", "--loop", "a", "--actor", "team-lead",
                     "--note", "T-EV-7 变异体", "--files",
                     os.path.join(tmp, "scripts", "harness.py"), "--workspace", ws],
                    capture_output=True, text=True, timeout=180)
                self.assertEqual(proc.returncode, 0,
                                 f"变异体开批失败：{proc.stderr[:300]}")
                bid = str((json.loads(proc.stdout) or {}).get("batch", {}).get("id") or "")
                # 把证据里的一项改成 rc=1
                with open(ev, "w", encoding="utf-8") as f:
                    bad = [{"suite": s, "rc": 0, "duration_s": 1.0} for s in req]
                    bad[1]["rc"] = 1
                    json.dump({"suites": bad}, f)
                proc2 = subprocess.run(
                    [PY, h, "loop", "batch-close", "--loop", "a", "--actor", "team-lead",
                     "--batch", bid, "--confirmed", "--regression", ",".join(req),
                     "--regression-evidence", ev, "--workspace", ws],
                    capture_output=True, text=True, timeout=180)
                self.assertNotEqual(proc2.returncode, 1,
                                    "变异体仍拒批（rc=1）⇒ 变异未真正改坏证据校验层；"
                                    "或 T-EV-3 根本没测到这一层")
                self.assertEqual(proc2.returncode, 0,
                                 f"变异体收批失败（应放行——校验被改坏）："
                                 f"{proc2.stderr[:300]}")
            finally:
                shutil.rmtree(ws, ignore_errors=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # ② 真包：T-EV-3 判据必须成立（rc=1 ⇒ 拒批）
        req, suites = self._open_and_prepare(batch="b1000000009")
        suites[1]["rc"] = 1
        ev = self._evidence(suites)
        rc, so, se = self._close("b1000000009", ",".join(req), evidence=ev)
        self.assertEqual(rc, 1,
                         "真包下 rc=1 的证据竟被收批——T-EV-3 判据本身失效")


if __name__ == "__main__":
    unittest.main(verbosity=2)

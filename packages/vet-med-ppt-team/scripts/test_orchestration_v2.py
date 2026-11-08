#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_orchestration_v2.py — B15 编排升级的能红证明（3.28.3 批次 B15 · 升级方案 P3）

─────────────────────────────────────────────────────────────────────────────
【缺口（升级方案诊断 P-协1/P-协3）】
· P-协3：trace 实测 684 次 team_create 对 5 次 preflight——同任务反复重建
  团队记录、状态未复用（每次重建的上下文成本被反复支付）。
· P-协1：闸2 两人强制串行（parallel=no）无机器判据——吞吐瓶颈。
（上下文预算 R3：cmd_spawn input_chars 超限告警入 trace。）

本文件锁住（全程临时 workspace）：
  T1 team_create 幂等：同签名 route 两次 ⇒ 仅 1 条 team_create + 二次标 reused
  T2 配置面：闸2 parallel=true 且 context.per_stage_inject_cap 存在
  T3 spawn 超限 ⇒ trace.context_over_budget=true + stderr 告警
  T4 变异：掏空幂等检查 ⇒ T1 场景翻松（二次也写事件，证校验被覆盖）
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"


def _run(args, cwd):
    proc = subprocess.run([sys.executable, str(HARNESS)] + args,
                          capture_output=True, text=True,
                          cwd=str(cwd), timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _events(ws):
    f = ws / ".workbuddy" / "harness_trace.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in
            f.read_text(encoding="utf-8").splitlines() if l.strip()]


class TestOrchestrationV2(unittest.TestCase):

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="b15-"))
        (self.ws / ".workbuddy").mkdir()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def _route(self, task="T1"):
        return _run(["route", "--level", "L1", "--domain", "animal-medicine",
                     "--task-id", task, "--workspace", str(self.ws)], self.ws)

    def test_T1_team_create_idempotent(self):
        """T1 同签名 route 两次 ⇒ trace 只 1 条 team_create，第二次标 reused。"""
        rc1, so1, _ = self._route()
        self.assertEqual(rc1, 0)
        plan1 = json.loads(so1[so1.find("{"):])
        self.assertNotIn("team_reused", plan1, "首次创建不应标 reused")
        rc2, so2, _ = self._route()
        self.assertEqual(rc2, 0)
        plan2 = json.loads(so2[so2.find("{"):])
        self.assertTrue(plan2.get("team_reused"),
                        "二次同签名应标 team_reused（幂等复用）")
        self.assertIn("team_reused_ts", plan2)
        n = len([e for e in _events(self.ws)
                 if e["event"] == "team_create"])
        self.assertEqual(n, 1, f"应只 1 条 team_create，实得 {n}")

    def test_T2_config_flags(self):
        """T2 闸2 parallel=false（v3.17.0 串行修正，v3.30.0 B0 值落地）+ 上下文预算键在配置面。

        ⚠ 历史教训（LRN-20261104-001）：本断言曾 assertTrue(parallel)——
        守卫断言了与事实（SOP 串行叙述）相反的口径，把错误焊死。
        """
        import yaml
        cfg = yaml.safe_load((PKG / "config" / "harness.yaml")
                             .read_text(encoding="utf-8"))
        self.assertFalse(cfg["stages"][1]["parallel"],
                         "闸2 应串行（v3.17.0 批次 B 数据依赖修正；v3.30.0 B0 值落地）")
        self.assertIn("per_stage_inject_cap", cfg["context"])

    def test_T3_spawn_over_budget_flags_trace(self):
        """T3 spawn 注入超限 ⇒ context_over_budget=true + stderr 告警。"""
        rc, _, err = _run(["spawn", "--agent", "dvm-content-expert",
                           "--task-id", "T1", "--stage", "1",
                           "--input-bytes", "99999",
                           "--workspace", str(self.ws)], self.ws)
        self.assertEqual(rc, 0)
        self.assertIn("预算", err)
        ev = [e for e in _events(self.ws) if e["event"] == "spawn"][0]
        self.assertTrue(ev["detail"].get("context_over_budget"),
                        "超限须入 trace（可审计）")

    def test_T4_mutation_flips_t1(self):
        """T4 变异：掏空幂等检查 ⇒ 二次 route 也写事件（T1 防线被证覆盖）。"""
        tmp = Path(tempfile.mkdtemp(prefix="b15mut-"))
        try:
            shutil.copytree(PKG / "scripts", tmp / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(PKG / "config", tmp / "config")
            for rel in (".codebuddy-plugin/plugin.json", "agents",
                        "vendor/shared-core"):
                src = PKG / rel
                dst = tmp / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
            h = tmp / "scripts" / "harness.py"
            s = h.read_text(encoding="utf-8")
            anchor = "        if reused_ts:"
            assert s.count(anchor) == 1, s.count(anchor)
            h.write_text(s.replace(anchor,
                                   "        if False:  # MUTANT: 幂等复用被掏空", 1),
                         encoding="utf-8")
            ws = tmp / "ws"
            (ws / ".workbuddy").mkdir(parents=True)
            def run2():
                for _ in range(2):
                    subprocess.run(
                        [sys.executable, str(tmp / "scripts" / "harness.py"),
                         "route", "--level", "L1", "--domain",
                         "animal-medicine", "--task-id", "T1",
                         "--workspace", str(ws)],
                        capture_output=True, text=True, timeout=120)
            run2()
            n = len([e for e in _events(ws) if e["event"] == "team_create"])
            self.assertEqual(n, 2,
                             f"变异体应双写（幂等被掏空），实得 {n} ⇒ 守卫空转")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

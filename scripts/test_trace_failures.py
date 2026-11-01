#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trace_failures.py — B13 可观察性地基的能红证明（v3.28.4）

─────────────────────────────────────────────────────────────────────────────
【缺口（Loop A 第二轮诊断 P-断1/P-断2/P-断3）】
· P-断1：trace 里 spawn_failed 的 reason=""（空）——失败无法归因
· P-断2：沙箱类 PermissionError 只留裸 traceback，无用户处置指引
· P-断3：batch_open/close/reflow 只进 state.history，不进统一 trace 账本
  ⇒ 产出链路端到端不可回放

本文件锁住 B13 三项修复的判据（全程临时 workspace，不碰真包状态）：
  T1 空 reason 的 spawn-failed 被拒绝（rc=2，不写 trace）
  T2 合法枚举 reason 通过且落 trace 的 reason 字段=枚举值
  T3 非枚举自由文本 → 归类 unknown 且 legacy_reason 保留（向后兼容）
  T4 batch_open 动作在统一 trace 账本产生事件（P-断3 闭合）
  T5 reflow 动作在统一 trace 账本产生事件
变异：掏空 reason 校验 ⇒ T1 场景不再被拒（证守卫覆盖真实判据）。
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


class _Ws:
    """临时工作区（.workbuddy 目录现建）。"""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="b13-"))
        (self.root / ".workbuddy").mkdir()

    @property
    def trace(self):
        return self.root / ".workbuddy" / "harness_trace.jsonl"

    def events(self):
        if not self.trace.exists():
            return []
        return [json.loads(l) for l in
                self.trace.read_text(encoding="utf-8").splitlines() if l.strip()]

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def _run(args, cwd):
    proc = subprocess.run([sys.executable, str(HARNESS)] + args,
                          capture_output=True, text=True,
                          cwd=str(cwd), timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


class TestSpawnFailedReasonEnum(unittest.TestCase):

    def setUp(self):
        self.ws = _Ws()

    def tearDown(self):
        self.ws.cleanup()

    def _sf(self, reason, extra=()):
        return _run(["spawn-failed", "--agent", "verifier",
                     "--task-id", "t1", "--attempt", "1",
                     "--reason", reason, *extra], self.ws.root)

    def test_T1_empty_reason_rejected(self):
        """T1 空 reason ⇒ rc=2 + 不写 trace（归因黑洞堵死）。"""
        rc, _, err = self._sf("")
        self.assertEqual(rc, 2, f"空 reason 应被拒绝 rc=2，实得 {rc}")
        self.assertIn("枚举", err)
        self.assertEqual([e for e in self.ws.events()
                          if e["event"] == "spawn_failed"], [],
                         "被拒的空 reason 不得落 trace")

    def test_T2_enum_reason_passes_and_lands(self):
        """T2 合法枚举（platform_sandbox）⇒ rc=0 + trace.reason=枚举值。"""
        rc, _, _ = self._sf("platform_sandbox",
                            ("--detail", "Brokered host mkdir"))
        self.assertEqual(rc, 0)
        evs = [e for e in self.ws.events() if e["event"] == "spawn_failed"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["detail"]["reason"], "platform_sandbox")
        self.assertIn("Brokered", evs[0]["detail"].get("detail", ""))

    def test_T3_legacy_free_text_becomes_unknown(self):
        """T3 非枚举自由文本 ⇒ reason=unknown + legacy_reason 保留（兼容）。"""
        rc, _, _ = self._sf("平台返回 not available")
        self.assertEqual(rc, 0)
        ev = [e for e in self.ws.events()
              if e["event"] == "spawn_failed"][0]
        self.assertEqual(ev["detail"]["reason"], "unknown")
        self.assertIn("not available",
                      ev["detail"].get("detail", ""))

    def test_T4_batch_open_lands_in_trace(self):
        """T4 batch-open 在统一 trace 账本产生 batch_open 事件（P-断3）。"""
        rc, _, _ = _run(["loop", "batch-open", "--loop", "a", "--actor",
                         "team-lead", "--workspace", str(self.ws.root),
                         "--note", "T4", "--files", "scripts/harness.py"],
                        self.ws.root)
        self.assertEqual(rc, 0)
        evs = [e for e in self.ws.events() if e["event"] == "batch_open"]
        self.assertEqual(len(evs), 1, "batch_open 必须进统一 trace 账本")
        self.assertEqual(evs[0]["actor"], "team-lead")

    def test_T5_reflow_lands_in_trace(self):
        """T5 reflow 在统一 trace 账本产生 reflow 事件（含 ok 布尔）。"""
        rc, _, _ = _run(["loop", "reflow", "--loop", "a", "--actor",
                         "team-lead", "--workspace", str(self.ws.root)],
                        self.ws.root)
        # rc 口径：0=台账合规；1=台账判据不通过（临时区无 --file，回退真包台账
        # 而 rule_hash 对不上——预期）；3=判据器缺失。本测试只锁"动作入账本"。
        self.assertIn(rc, (0, 1, 3))
        evs = [e for e in self.ws.events() if e["event"] == "reflow"]
        self.assertEqual(len(evs), 1, "reflow 必须进统一 trace 账本")
        self.assertIn("ok", evs[0]["detail"])


class TestMutantsAreKilled(unittest.TestCase):
    """变异：掏空 reason 必填校验 ⇒ T1 场景必须翻松（证明校验被测试覆盖）。"""

    def test_mutant_allow_empty_reason_makes_T1_red(self):
        tmp = Path(tempfile.mkdtemp(prefix="b13mut-"))
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
            anchor = '''    if not raw_reason:
        print("⛔ --reason 必填且须为枚举值之一：timeout / tool_error / "
              "content_reject / platform_sandbox / quota / unknown\\n"
              "   空 reason 的失败记录无法归因（诊断 P-断1）；"
              "补充上下文用 --detail '自由文本'。", file=sys.stderr)
        return 2'''
            assert s.count(anchor) == 1, s.count(anchor)
            h.write_text(s.replace(anchor, "    raw_reason = raw_reason or 'unknown'  # MUTANT", 1),
                         encoding="utf-8")
            ws = tmp / "ws"
            (ws / ".workbuddy").mkdir(parents=True)
            # ⚠ 必须跑**变异副本**的 harness.py（模块级 _run 指向真包——
            #   首版即踩此坑：变异体没被跑，断言的是真包的拒绝行为（假红）。
            proc = subprocess.run(
                [sys.executable, str(tmp / "scripts" / "harness.py"),
                 "spawn-failed", "--agent", "verifier", "--reason", ""],
                capture_output=True, text=True, cwd=str(ws), timeout=120)
            rc, so, se = proc.returncode, proc.stdout or "", proc.stderr or ""
            if rc == 2 and "枚举" not in se and "usage" in se.lower():
                # argparse 用法错误（参数名不识别等）——打印诊断信息供定位
                self.fail(f"变异副本 argparse 报错（非判据拒绝）：{se[:200]}")
            # 变异后空 reason 不再被拒（rc=0 且落 trace）⇒ T1 的防线真实存在
            self.assertEqual(rc, 0,
                             "变异体仍拒绝空 reason ⇒ 空转（mutant 未生效）")
            trace = ws / ".workbuddy" / "harness_trace.jsonl"
            self.assertTrue(trace.exists(), "变异体应把空 reason 记为 unknown 落 trace")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_member_write_scope.py — B14 分级权限 L2（写前校验）的能红证明（v3.28.4）

─────────────────────────────────────────────────────────────────────────────
【缺口（升级方案诊断 P-权1/P-权3）】
writes_allowed 只有 bool 粒度——产出期成员写入面无强制约束（verifier 改 deck
在权限面上无拦截）。职责边界散在 SOP 文字里，无结构化矩阵。

【判据源】config/responsibility-matrix.yaml#write_scope（唯一源）
【执行器】harness.py member-write-check --agent X --path P（rc=0 放行 / 2 拒绝）

本文件锁住（全程临时 workspace + 真实矩阵）：
  T1 verifier 写 deck 被拒（独立性铁律）
  T2 ppt-producer 写 deck 放行
  T3 未登记成员 = 零权限默认拒绝
  T4 拒绝/放行均落 trace（member_write_check）
  T5 verifier 写 reports 放行（自己的产出面）
变异：掏空目录前缀匹配 ⇒ T1 场景翻松（证校验被覆盖）。
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


class TestMemberWriteScope(unittest.TestCase):

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="b14-"))
        (self.ws / ".workbuddy").mkdir()
        for d in ("deck", "wip", "reports", "content"):
            (self.ws / d).mkdir()

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def _wc(self, agent, path):
        return _run(["member-write-check", "--agent", agent,
                     "--path", str(path), "--workspace", str(self.ws)],
                    self.ws)

    def _events(self):
        f = self.ws / ".workbuddy" / "harness_trace.jsonl"
        if not f.exists():
            return []
        return [json.loads(l) for l in
                f.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_T1_verifier_cannot_write_deck(self):
        """T1 verifier 写 deck ⇒ 拒绝（独立性铁律：验证者永不碰产出）。"""
        rc, _, err = self._wc("verifier", self.ws / "deck" / "x.pptx")
        self.assertEqual(rc, 2, f"verifier 写 deck 应被拒，实得 rc={rc}")
        self.assertIn("不得写", err)
        self.assertIn("write_scope", err)

    def test_T2_producer_can_write_deck(self):
        """T2 ppt-producer 写 deck ⇒ 放行（own 产出面）。"""
        rc, out, _ = self._wc("ppt-producer", self.ws / "deck" / "x.pptx")
        self.assertEqual(rc, 0)
        self.assertIn("matched_pattern", out)

    def test_T3_unregistered_member_denied(self):
        """T3 未登记成员（如临时角色）⇒ 零权限默认拒绝。"""
        rc, _, err = self._wc("rogue-agent", self.ws / "wip" / "a.md")
        self.assertEqual(rc, 2)
        self.assertIn("未在", err)

    def test_T4_both_outcomes_land_in_trace(self):
        """T4 拒绝与放行均入 trace（L3 审计对账的数据面）。"""
        self._wc("verifier", self.ws / "deck" / "x.pptx")     # 拒
        self._wc("verifier", self.ws / "reports" / "r.md")    # 放
        evs = [e for e in self._events()
               if e["event"] == "member_write_check"]
        self.assertEqual(len(evs), 2)
        self.assertFalse(evs[0]["detail"]["allowed"])
        self.assertTrue(evs[1]["detail"]["allowed"])

    def test_T5_verifier_can_write_reports(self):
        """T5 verifier 写 reports ⇒ 放行（自己的产出面）。"""
        rc, _, _ = self._wc("verifier", self.ws / "reports" / "r.md")
        self.assertEqual(rc, 0)


class TestMutantsAreKilled(unittest.TestCase):

    def test_mutant_allow_all_writes_makes_T1_red(self):
        """变异：校验函数恒放行 ⇒ T1 场景翻松（证校验被覆盖，守卫非空转）。"""
        tmp = Path(tempfile.mkdtemp(prefix="b14mut-"))
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
            anchor = '''    allowed = False
    hit = ""
    for pat in patterns:'''
            assert s.count(anchor) == 1, s.count(anchor)
            s = s.replace(anchor,
                          "    allowed = True  # MUTANT: 恒放行\n    hit = 'MUTANT'\n    for pat in []:", 1)
            h.write_text(s, encoding="utf-8")
            ws = tmp / "ws"
            (ws / ".workbuddy").mkdir(parents=True)
            (ws / "deck").mkdir()
            # 跑**变异副本**（模块级 HARNESS 指向真包——B13 踩坑教训，勿重犯）
            proc = subprocess.run(
                [sys.executable, str(tmp / "scripts" / "harness.py"),
                 "member-write-check", "--agent", "verifier",
                 "--path", str(ws / "deck" / "x.pptx"),
                 "--workspace", str(ws)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0,
                             "变异体仍拒绝 ⇒ 校验没被测试覆盖（守卫空转）")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

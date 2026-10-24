#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_no_progress_p2.py — 质量收敛判据「P2 必须计入」回归（v3.17.0 B3-4）

缺陷场景（可构造，非假设）：
  一轮只把**备注覆盖率**补达标（P2 阻断解除：p2 1 → 0），P0/P1 一个没动。
  旧判据（`_loop_no_progress_streak` 只看 p0p1）看 p0p1 持平 ⇒ 判「无进展」，
  连续 N 轮后**终止任务**——但质量**实际在推进**（P2 门禁从阻断变通过）。
  这是把"有效推进"误杀为"空转"，且终止是**不可逆**动作（要重跑整个 Loop B）。

方向纪律（**本文件的核心断言**）：
  P0/P1/P2 在本包口径里**同向**——都是"缺陷/阻断计数"，**越少越好**。
  P2 的语义是「备注覆盖率**未达标**」（1=未达标/阻断，0=达标），
  不是"覆盖率百分比"本身 ⇒ 可与 P0/P1 直接相加。
  ⚠ 若将来把 p2 改成"覆盖率百分比（越高越好）"，本项目必须同步改向，
    不能简单相加——本文件的 T3 就是这条纪律的守门人。

运行：
    python3 -m pytest scripts/test_no_progress_p2.py -q
    python3 scripts/test_no_progress_p2.py
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import harness  # noqa: E402


def _snap(round_no, p0, p1, p2, legacy=False):
    """构造一条质量快照；legacy=True 模拟旧快照（无 p2 / p0p1p2 键）。"""
    s = {"round": round_no, "p0": p0, "p1": p1, "p0p1": p0 + p1, "ts": "2026-10-25T00:00:00"}
    if not legacy:
        s["p2"] = p2
        s["p0p1p2"] = p0 + p1 + p2
    return s


class TestNoProgressP2(unittest.TestCase):

    def test_T1_only_p2_improves_must_not_count_as_no_progress(self):
        """【核心】仅 P2 改善（p0/p1 不动）→ 不得判为无进展"""
        hist = [_snap(1, 3, 2, 1),      # 轮1：P0=3 P1=2 P2=1（备注覆盖率未达标）
                _snap(2, 3, 2, 0)]      # 轮2：P0/P1 未动，P2 阻断解除
        self.assertEqual(harness._loop_no_progress_streak(hist), 0,
                         "仅 P2 改善被误判为无进展——有效推进被当成空转（会误杀任务）")

    def test_T2_true_no_progress_still_detected(self):
        """三者全不动 → 连续两轮无进展必须检出（判据不得被改废）"""
        hist = [_snap(1, 3, 2, 1), _snap(2, 3, 2, 1), _snap(3, 3, 2, 1)]
        self.assertEqual(harness._loop_no_progress_streak(hist), 2,
                         "真无进展未被检出——判据被改废（收敛护栏失效）")

    def test_T3_direction_not_inverted(self):
        """方向守门：P2 变**大**（更差）必须算无进展，不得因纳入 P2 而反向"""
        hist = [_snap(1, 3, 2, 0), _snap(2, 3, 2, 1)]   # P2 从达标变未达标
        self.assertEqual(harness._loop_no_progress_streak(hist), 1,
                         "P2 变差却未被判无进展——纳入 P2 时方向搞反了")

    def test_T4_p0_improvement_resets_streak(self):
        """P0 下降 → 进展（既有行为不得回归）"""
        hist = [_snap(1, 3, 2, 1), _snap(2, 1, 2, 1)]
        self.assertEqual(harness._loop_no_progress_streak(hist), 0)

    def test_T5_legacy_snapshots_without_p2(self):
        """向后兼容：旧快照缺 p2/p0p1p2 键 → 按 p0p1 计（p2 视为 0），不得报错"""
        hist = [_snap(1, 3, 2, 0, legacy=True), _snap(2, 3, 2, 0, legacy=True)]
        self.assertEqual(harness._loop_no_progress_streak(hist), 1)
        hist2 = [_snap(1, 3, 2, 0, legacy=True), _snap(2, 2, 2, 0, legacy=True)]
        self.assertEqual(harness._loop_no_progress_streak(hist2), 0)

    def test_T6_single_snapshot_never_triggers(self):
        """只有 1 条快照 → 无从比较，返回 0（宁可不判，也不凭空触发）"""
        self.assertEqual(harness._loop_no_progress_streak([_snap(1, 3, 2, 1)]), 0)
        self.assertEqual(harness._loop_no_progress_streak([]), 0)

    def test_T7_snapshot_writes_p0p1p2(self):
        """新快照必须写 p0p1p2 键（判据的主读键）"""
        st = {}
        snap = harness._loop_quality_snapshot(st, 1, 3, 2, 1, source="manual")
        self.assertEqual(snap["p0p1p2"], 6)
        self.assertEqual(snap["p0p1"], 5)     # 旧键保留（兼容既有报表）


if __name__ == "__main__":
    unittest.main(verbosity=2)

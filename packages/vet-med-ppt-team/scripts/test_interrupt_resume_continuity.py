#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_interrupt_resume_continuity.py — 中断恢复的**质量连续性**端到端实测（v3.28.2 B5）

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（本轮十三维度诊断 D12/P1-4 实测缺口）】
─────────────────────────────────────────────────────────────────────────────
D12「中断恢复」的**机制**齐备（loop resume / 幂等续跑 / 两环状态并存），
但**「意外中断后质量连续性」没有任何端到端实测**：
  · `docs/v3.19.2-verification-report.md` 的「12 中断恢复 ✅」只证明
    `doctor.pending_work` + `resume_hint` **可执行**；
  · 它**不证明**「中断后恢复，已冻结的成果与质量基线原样还在」。
⇒ 按本包口径「配置在而场景未实测 ⇒ 判缺口，不得判合格」。

本文件补的就是这一层：**中断（进程退出）→ 新进程 resume → 逐项比对中断前快照**。

─────────────────────────────────────────────────────────────────────────────
【判据设计（每条都可复核）】
─────────────────────────────────────────────────────────────────────────────
  C1 resume 成功且**强制等确认**（awaiting_user_confirm=true，禁止自动续跑）
  C2 原件指纹不变（source_ppt.sha256 与中断前一致）—— 恢复过程不得碰原件
  C3 已冻结条目逐条不变（条数 + 每条 sha256 + status=frozen）—— 成果不丢
  C4 待办条目逐条不变（条数 + 每条 sha256）—— 未加工内容不丢
  C5 轮次不倒退（current_round 不变）；history **只增不减**（留痕不丢）
  C6 恢复后完成一轮：轮次前进 +1、quality_history 记下本轮 P0/P1/P2
      ⇒ 「恢复后还能正常推进」而不只是「能读出来」

⚠ 全程在**临时工作区**，不碰任何真实课件；状态文件由 harness 自己写。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
HARNESS = os.path.join(HERE, "harness.py")


def _run(args, cwd=None):
    p = subprocess.run([sys.executable, HARNESS] + args,
                       capture_output=True, text=True, cwd=cwd, timeout=180)
    return p.returncode, p.stdout or "", p.stderr or ""


def _jout(s):
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        return json.loads(s[i:j + 1]) if i >= 0 and j > i else {}


def _make_deck(path):
    """最小 pptx；python-pptx 不可用时退化为占位文件（本测试只关心只读指纹）。"""
    try:
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(path)
        return True
    except Exception:
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04fake-deck-for-resume-test")
        return False


def _state(w):
    p = os.path.join(w, ".workbuddy", "loopB_state.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _round_review(w, tag="rr"):
    """登记一份六项齐全的轮报（continue 的前置判据）。"""
    p = os.path.join(w, f"{tag}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "本轮改了什么": "按用户裁决修订 3 处表述",
            "依据": "verify_deck 报告 + 七维量规逐条对照",
            "未解决": "2 张配图分辨率待补",
            "下一步": "补齐配图后请用户复裁",
            "风险": "配图补不齐则第 12 页结论页强度不足",
            "需用户裁决": "是否接受降低配图标准先交付",
        }, f, ensure_ascii=False)
    return _run(["loop", "review", "--file", p, "--workspace", w])


def _snapshot(st):
    """中断前快照：原件指纹 + 冻结/待办逐条 + 轮次 + 留痕条数。"""
    items = st.get("items") or {}
    frozen = {k: v.get("sha256") for k, v in items.items() if v.get("status") == "frozen"}
    pending = {k: v.get("sha256") for k, v in items.items() if v.get("status") != "frozen"}
    return {
        "source_sha": (st.get("source_ppt") or {}).get("sha256"),
        "frozen": frozen,
        "pending": pending,
        "round": st.get("current_round"),
        "history_len": len(st.get("history") or []),
    }


class TestInterruptResumeContinuity(unittest.TestCase):
    """中断 → 新进程 resume → 逐项比对（质量连续性）。"""

    def test_resume_preserves_all_state_and_quality(self):
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "demo.pptx")
            _make_deck(deck)

            # ── ① 建任务：start → intake → 3 条登记 → 冻结 1 条 ──────
            rc, so, se = _run(["loop", "start", "--deck", deck, "--workspace", w])
            self.assertEqual(rc, 0, f"start 失败：{se[:300]}")
            intake = os.path.join(w, "intake.json")
            with open(intake, "w", encoding="utf-8") as f:
                json.dump({"audience": "高职大二", "periods": "2 课时",
                           "template": "沿用原模板", "scope": "全页",
                           "acceptance": "P0 清零且每轮我确认"}, f, ensure_ascii=False)
            rc, so, se = _run(["loop", "intake", "--file", intake, "--workspace", w])
            self.assertEqual(rc, 0, f"intake 失败：{se[:300]}")

            wip = os.path.join(w, "demo_wip")
            for iid in ("I-001", "I-002", "I-003"):
                fp = os.path.join(wip, f"{iid}_draft.md")
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(f"# {iid} 内容\n")
                rc, _, se = _run(["loop", "add-item", "--item", iid, "--page", "s1",
                                  "--file", fp, "--severity", "P1", "--owner", "dvm",
                                  "--workspace", w])
                self.assertEqual(rc, 0, f"add-item {iid} 失败：{se[:200]}")
            rc, so, se = _run(["loop", "freeze", "--items", "I-001",
                               "--decision", "partial_accept", "--workspace", w])
            self.assertEqual(rc, 0, f"freeze 失败：{se[:300]}")

            # ── ② 中断前快照 ────────────────────────────────────────
            base = _snapshot(_state(w))
            self.assertEqual(len(base["frozen"]), 1, "基线应有 1 条冻结")
            self.assertEqual(len(base["pending"]), 2, "基线应有 2 条待办")
            self.assertTrue(base["source_sha"], "基线缺原件指纹")

            # ── ③ 模拟中断后的新进程：resume ────────────────────────
            # ⚠ 先把 awaiting_user_confirm 置 false（模拟"用户已确认、工作正在进行中"
            #   的真实中断态）——否则 resume 之前它就是 true，C1 断言会**恒真**
            #   （那样测的是"本来就是 true"，不是"resume 把它置回 true"）。
            sp = os.path.join(w, ".workbuddy", "loopB_state.json")
            _st = _state(w)
            _st["awaiting_user_confirm"] = False
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(_st, f, ensure_ascii=False)
            self.assertFalse(_state(w).get("awaiting_user_confirm"),
                             "前置：中断态应为 awaiting_user_confirm=false（工作中）")

            rc, so, se = _run(["loop", "resume", "--workspace", w])
            self.assertEqual(rc, 0, f"resume 失败：rc={rc}\n{se[:300]}")
            msg = _jout(so)
            # C1：强制等确认，禁止自动续跑
            # ⚠ 必须断言**落盘状态**，不能只断言 stdout 里的 JSON——
            #   实测踩坑：resume 的打印体里 `awaiting_user_confirm` 是**字面量 True**，
            #   即使代码不再写状态位也照样打印 True（断言打印体 = 恒真）。
            self.assertTrue(_state(w).get("awaiting_user_confirm") is True,
                            f"C1 resume 未把 awaiting_user_confirm **落盘**为 true"
                            f"（恢复后可能自动续跑）")
            self.assertTrue(msg.get("awaiting_user_confirm") is True,
                            f"C1 resume 输出未声明等待确认：{msg}")
            self.assertIn("恢复", str(msg.get("message") or ""),
                          f"C1 resume 未给出恢复说明：{msg.get('message')!r}")

            # ── ④ 逐项比对（质量连续性）────────────────────────────
            after = _snapshot(_state(w))
            # C2 原件指纹不变
            self.assertEqual(after["source_sha"], base["source_sha"],
                             "C2 恢复后原件指纹变了——恢复过程动了原件（越权写）")
            # C3 冻结条目逐条不变
            self.assertEqual(after["frozen"], base["frozen"],
                             f"C3 冻结成果丢失/被改：before={base['frozen']} after={after['frozen']}")
            # C4 待办条目逐条不变
            self.assertEqual(after["pending"], base["pending"],
                             f"C4 待办内容丢失/被改：before={base['pending']} after={after['pending']}")
            # C5 轮次不倒退 + 留痕只增不减
            self.assertEqual(after["round"], base["round"], "C5 恢复后轮次被重置")
            self.assertGreaterEqual(after["history_len"], base["history_len"],
                                    "C5 恢复后留痕条数减少了（history 被截断）")

            # ── ⑤ C6：恢复后还能正常推进一轮 ────────────────────────
            rc, _, se = _round_review(w, "rr1")
            self.assertEqual(rc, 0, f"轮报登记失败：{se[:300]}")
            rc, so, se = _run(["loop", "continue", "--decision", "accept",
                               "--confirmed", "--p0", "6", "--p1", "2", "--p2", "4",
                               "--workspace", w])
            self.assertEqual(rc, 0, f"C6 恢复后无法进位：rc={rc}\n{se[:400]}")
            st2 = _state(w)
            self.assertEqual(int(st2.get("current_round") or 0), int(base["round"]) + 1,
                             f"C6 轮次未前进：{st2.get('current_round')}")
            qh = st2.get("quality_history") or []
            self.assertTrue(qh, "C6 quality_history 未记录本轮质量指标")
            last = qh[-1] if isinstance(qh[-1], dict) else {}
            self.assertEqual((last.get("p0"), last.get("p1"), last.get("p2")), (6, 2, 4),
                             f"C6 质量指标记录不符：{last}")
            # 冻结成果在进位后仍在（不被轮次推进清空）
            st_frozen = {k for k, v in (st2.get("items") or {}).items()
                         if v.get("status") == "frozen"}
            self.assertEqual(st_frozen, set(base["frozen"]),
                             f"C6 进位后冻结条目被清空：{st_frozen}")


if __name__ == "__main__":
    unittest.main()

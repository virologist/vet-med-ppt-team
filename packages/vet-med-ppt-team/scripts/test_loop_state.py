#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_loop_state.py — 双层 Loop 状态机回归测试（v3.9.0 新增）

背景（2026-10-22 需求核对实证）：
  v3.8.0/3.8.1 把双层 Loop 写进了 config/harness.yaml 与 references/dual-loop-governance.md，
  但 harness.py **从未含 loop 子命令**——"逐轮停等""部分接受只冻点名条目""sha256 漂移即
  失效""沉默不推进""预算触顶不宣布通过"全是 Markdown 纪律，同一文档 §8 第 3 项自认
  "非代码级强制"。v3.9.0 把这些可判定条款下沉为代码，本文件锁死它们。

本文件同时是 references/dual-loop-governance.md#9「本地最小实测清单」中
此前**未实测**的 1/2/3/4/6/7 号场景的机器背书（5 号缺图、9 号新建回归已由
test_fix_md_image_refs.py 与 ensure_settings 覆盖）。

用法：
    python3 scripts/test_loop_state.py
退出码：0=全通过 1=有用例失败
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "harness.py")
PKG = os.path.dirname(HERE)

PASS, FAIL = [], []


def run(args, cwd=None):
    p = subprocess.run([sys.executable, HARNESS] + args, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def jout(s):
    """取 stdout 里的 JSON（脚本可能先打印告警行）。"""
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        return json.loads(s[i:j + 1]) if i >= 0 and j > i else {}


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra and not cond else ""))


def make_deck(path):
    """造一份最小 pptx；python-pptx 不可用时退化为空文件（本测试只关心只读指纹）。"""
    try:
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(path)
        return True
    except Exception:
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04fake-deck-for-loop-state-test")
        return False


def main():
    print("== 回归测试：vet-med-ppt-team loop 状态机 v3.9.0 ==")

    with tempfile.TemporaryDirectory() as w:
        deck = os.path.join(w, "demo.pptx")
        make_deck(deck)
        base_hash = None

        # ── 启动：原件指纹存档 + 工作副本建立 + 默认待确认 ──────────────
        rc, so, se = run(["loop", "start", "--deck", deck, "--workspace", w])
        st = jout(so)
        check("start 成功建状态（exit 0）", rc == 0, f"rc={rc} {se[:120]}")
        check("原件指纹存档 sha256+size+mtime",
              bool(st.get("source_ppt", {}).get("sha256")) and st["source_ppt"].get("size"))
        check("工作副本为 <课件名>_wip 且已建目录",
              st.get("wip_dir", "").endswith("demo_wip") and os.path.isdir(st.get("wip_dir", "")))
        check("启动即 awaiting_user_confirm=true（未对齐九项不得开工）",
              st.get("awaiting_user_confirm") is True)
        base_hash = st.get("source_ppt", {}).get("sha256")

        # 重复 start 不得静默覆盖既有冻结现场
        rc2, _, se2 = run(["loop", "start", "--deck", deck, "--workspace", w])
        check("重复 start 被拒（exit 1，提示用 resume）", rc2 == 1 and "resume" in (se2 or ""))

        # ── 越界校验（两环目录隔离）────────────────────────────────
        rc3, _, _ = run(["loop", "check-path", "--loop", "a", "--path", deck, "--workspace", w])
        check("Loop A 触碰用户课件 → 越界拦截（exit 1）", rc3 == 1)
        rc4, _, _ = run(["loop", "check-path", "--loop", "a",
                         "--path", os.path.join(PKG, "scripts", "harness.py"), "--workspace", w])
        check("Loop A 改包内白名单目录 → 放行（exit 0）", rc4 == 0)
        rc5, _, _ = run(["loop", "check-path", "--loop", "b",
                         "--path", os.path.join(PKG, "scripts", "harness.py"), "--workspace", w])
        check("Loop B 改专家包 → 拦截（单课件诉求不得改全局规则）", rc5 == 1)
        rc6, _, _ = run(["loop", "check-path", "--loop", "b", "--path", deck, "--workspace", w])
        check("Loop B 写原件 → 拦截（原件只读）", rc6 == 1)

        # ── 九项接单：A 类缺项不得放行 ──────────────────────────────
        intake_partial = os.path.join(w, "intake_partial.json")
        with open(intake_partial, "w", encoding="utf-8") as f:
            json.dump({"audience": "高职大二", "periods": "2 课时"}, f)
        rc7, so7, _ = run(["loop", "intake", "--file", intake_partial, "--workspace", w])
        check("九项 A 类缺 3 项 → confirmed=false 且 exit 1",
              rc7 == 1 and jout(so7).get("confirmed") is False and len(jout(so7).get("missing_A", [])) == 3,
              f"got {so7[:150]}")

        intake_full = os.path.join(w, "intake_full.json")
        with open(intake_full, "w", encoding="utf-8") as f:
            json.dump({"audience": "高职大二", "periods": "2 课时", "template": "沿用原模板",
                       "scope": "全页", "acceptance": "P0 清零且每轮我确认"}, f)
        rc8, so8, _ = run(["loop", "intake", "--file", intake_full, "--workspace", w])
        check("九项 A 类齐 → confirmed=true 且 exit 0",
              rc8 == 0 and jout(so8).get("confirmed") is True)

        # ── 条目登记 ────────────────────────────────────────────
        wip = os.path.join(w, "demo_wip")
        drafts = {}
        for iid in ("I-001", "I-002", "I-003", "I-004", "I-005"):
            fp = os.path.join(wip, f"{iid}_draft.md")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(f"# {iid} 原始内容\n")
            drafts[iid] = fp
            rc9, _, _ = run(["loop", "add-item", "--item", iid, "--page", f"s{iid[-1]}",
                             "--file", fp, "--severity", "P1", "--owner", "dvm",
                             "--workspace", w])
            if rc9 != 0:
                check(f"add-item {iid}", False)
        rc10, so10, _ = run(["loop", "status", "--workspace", w])
        s10 = jout(so10)
        check("5 条登记成功（pending=5, frozen=0）",
              s10.get("pending") == 5 and s10.get("frozen") == 0, f"got {so10[:150]}")
        check("status 报原件未改动", s10.get("original_unchanged") is True)

        # ── 场景 2：部分批准 → 只冻结被点名条目，round 不变 ────────────
        rc11, so11, _ = run(["loop", "freeze", "--items", "I-001,I-002",
                             "--decision", "partial_accept", "--workspace", w])
        s11 = jout(so11)
        check("部分接受：frozen=2 / pending=3（未点名条目不被连带冻结）",
              s11.get("frozen_total") == 2 and s11.get("pending_total") == 3, f"got {so11[:150]}")
        rc12, so12, _ = run(["loop", "status", "--workspace", w])
        check("部分接受：current_round 仍为 1（不消耗轮次配额）",
              jout(so12).get("current_round") == 1)

        # ── 场景 5（沉默不推进）：continue 不带裁决即拒绝 ──────────────
        rc13, _, se13 = run(["loop", "continue", "--confirmed", "--workspace", w])
        check("沉默不构成确认：continue 缺 --decision → exit 2",
              rc13 == 2 and "沉默" in (se13 or ""), f"rc={rc13} {se13[:120]}")

        # ── 场景 3：人工改稿 → sha256 漂移 → 批准自动失效 ─────────────
        with open(drafts["I-001"], "a", encoding="utf-8") as f:
            f.write("用户手工补了一段\n")
        rc14, so14, _ = run(["loop", "verify", "--workspace", w])
        s14 = jout(so14)
        kinds = [p.get("kind") for p in s14.get("problems", [])]
        check("人工改稿：verify 检出 sha256_drift 并标记 invalidated（exit 1）",
              rc14 == 1 and "sha256_drift" in kinds, f"got {so14[:200]}")
        rc15, so15, _ = run(["loop", "status", "--workspace", w])
        check("失效条目计入 invalidated（不得混入制作包）",
              jout(so15).get("invalidated") == 1, f"got {so15[:150]}")

        # ── 场景 6（制作前置门）：有失效/未冻结项时不得放行 ─────────────
        rc16, so16, _ = run(["loop", "make-gate", "--workspace", w])
        check("制作前置门：存在失效 + 未冻结条目 → 阻断（exit 1）",
              rc16 == 1 and len(jout(so16).get("reasons", [])) >= 2, f"got {so16[:200]}")

        # ── 场景 4（断线恢复）：只报不推进 ──────────────────────────
        rc17, so17, _ = run(["loop", "resume", "--workspace", w])
        s17 = jout(so17)
        check("断线恢复：报「恢复到第 R 轮，已冻结 N 条，待办 M 条」",
              "恢复到第 1 轮" in s17.get("message", "") and "已冻结 1" in s17.get("message", ""),
              f"got {s17.get('message')}")
        check("断线恢复：置 awaiting_user_confirm=true（不自动续跑）",
              jout(so17).get("awaiting_user_confirm") is True)

        # ── 场景 1（用户拒绝/返修）：返修不进位，超上限挂阻塞 ───────────
        rc18, so18, _ = run(["loop", "rework", "--item", "I-003", "--workspace", w])
        check("返修：exit 0 且 current_round 不变（仍属当前轮）",
              rc18 == 0 and jout(so18).get("round_unchanged") is True, f"got {so18[:150]}")
        run(["loop", "rework", "--item", "I-003", "--workspace", w])
        rc19, _, se19 = run(["loop", "rework", "--item", "I-003", "--workspace", w])
        check("返修超单条目上限 → 挂阻塞（exit 1）",
              rc19 == 1 and "上限" in (se19 or ""), f"rc={rc19} {se19[:120]}")
        rc20, so20, _ = run(["loop", "status", "--workspace", w])
        check("阻塞项入 blockers 列表", len(jout(so20).get("blockers", [])) >= 1)

        # ── 场景 7（预算触顶）：只暂停报告，不宣布通过 ─────────────────
        with tempfile.TemporaryDirectory() as w2:
            deck2 = os.path.join(w2, "b.pptx")
            make_deck(deck2)
            run(["loop", "start", "--deck", deck2, "--max-rounds", "1", "--workspace", w2])
            rc21, _, se21 = run(["loop", "continue", "--decision", "accept",
                                 "--confirmed", "--workspace", w2])
            s21 = jout(run(["loop", "status", "--workspace", w2])[1])
            check("轮次预算触顶 → 置「达到预算但未完成」且 exit 1（不宣布通过）",
                  rc21 == 1 and s21.get("termination") == "达到预算但未完成",
                  f"rc={rc21} term={s21.get('termination')} {se21[:120]}")
            rc22, _, _ = run(["loop", "continue", "--decision", "accept",
                              "--confirmed", "--workspace", w2])
            check("已终止任务不得再进位（exit 1）", rc22 == 1)

        # ── 原件只读（验收清单第 1 项）──────────────────────────────
        with open(deck, "ab") as f:
            f.write(b"tampered")
        rc23, so23, _ = run(["loop", "status", "--workspace", w])
        check("原件被改动 → status 报 original_unchanged=false 且 exit 1",
              rc23 == 1 and jout(so23).get("original_unchanged") is False, f"got {so23[:150]}")
        rc24, so24, _ = run(["loop", "verify", "--workspace", w])
        check("原件被改动 → verify 报 original_modified",
              any(p.get("kind") == "original_modified" for p in jout(so24).get("problems", [])),
              f"got {so24[:200]}")
        # 还原以便后续用例（原件必须保持只读）
        with open(deck, "wb") as f:
            f.truncate()
        make_deck(deck)

        # ── 制作前置门：全部冻结且九项齐 → 放行 ──────────────────────
        rc25, so25, _ = run(["loop", "terminate", "--reason", "用户取消", "--workspace", w])
        check("终止态写入（用户取消）", rc25 == 0 and jout(so25).get("termination") == "用户取消")
        rc26, _, se26 = run(["loop", "terminate", "--reason", "瞎写的状态", "--workspace", w])
        check("终止态穷举：自造状态被拒（exit 2）", rc26 == 2)

        with tempfile.TemporaryDirectory() as w3:
            deck3 = os.path.join(w3, "c.pptx")
            make_deck(deck3)
            run(["loop", "start", "--deck", deck3, "--workspace", w3])
            wip3 = os.path.join(w3, "c_wip")
            os.makedirs(wip3, exist_ok=True)
            with open(os.path.join(w3, "i.json"), "w", encoding="utf-8") as f:
                json.dump({"audience": "高职大三", "periods": "4 课时", "template": "沿用原模板",
                           "scope": "s1-s20", "acceptance": "每轮确认"}, f)
            run(["loop", "intake", "--file", os.path.join(w3, "i.json"), "--workspace", w3])
            fp3 = os.path.join(wip3, "J-001_draft.md")
            with open(fp3, "w", encoding="utf-8") as f:
                f.write("# J-001\n")
            run(["loop", "add-item", "--item", "J-001", "--page", "s1",
                 "--file", fp3, "--workspace", w3])
            rc27, so27, _ = run(["loop", "make-gate", "--workspace", w3])
            check("制作前置门：九项齐但仍有未冻结条目 → 阻断", rc27 == 1, f"got {so27[:150]}")
            run(["loop", "freeze", "--items", "J-001", "--decision", "accept", "--workspace", w3])
            rc28, so28, _ = run(["loop", "make-gate", "--workspace", w3])
            check("制作前置门：全冻结 + 九项齐 + 原件未改 → 放行（exit 0）",
                  rc28 == 0 and jout(so28).get("ok") is True, f"got {so28[:200]}")
            rc29, so29, _ = run(["loop", "terminate", "--reason", "成功完成",
                                 "--confirmed", "--workspace", w3])
            check("全部冻结后可报「成功完成」", rc29 == 0)

        # ── 场景 8（v3.16.0 F6）：质量收敛判据 ──────────────────────────
        # 背景：loop_b.budgets.no_progress_threshold 此前**零命中**（配了无执行者），
        #   五类终止条件全是工作量/交互维度，机器检不出"缺陷数已不再下降"。
        # v3.17.0 B2-2：手工 --p0/--p1/--p2 在"已有手工历史"后被**强制**要求
        #   --verify-json（治递减假数序列绕过）——本用例用手工值，故显式声明
        #   --allow-unverified（逃生口，须留痕）以继续验证 streak 逻辑本身。
        with tempfile.TemporaryDirectory() as w4:
            deck4 = os.path.join(w4, "d.pptx")
            make_deck(deck4)
            run(["loop", "start", "--deck", deck4, "--workspace", w4])
            # 三轮 P0+P1 恒为 5（P0=3/P1=2），no_progress_threshold=2 → 第 3 轮触发
            r1, _, _ = run(["loop", "continue", "--decision", "accept", "--confirmed",
                            "--p0", "3", "--p1", "2", "--p2", "5", "--workspace", w4])
            r2, so2, _ = run(["loop", "continue", "--decision", "accept", "--confirmed",
                              "--p0", "3", "--p1", "2", "--p2", "5",
                              "--allow-unverified", "--workspace", w4])
            r3, so3, se3 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--p0", "3", "--p1", "2", "--p2", "5",
                                "--allow-unverified", "--workspace", w4])
            s2 = jout(so2)
            check("质量收敛：第 1、2 轮未达阈值（exit 0，streak=0/1），第 3 轮触发（exit 1）",
                  r1 == 0 and r2 == 0 and s2.get("no_progress_streak") == 1 and r3 == 1,
                  f"got {r1},{r2},{r3} streak={s2.get('no_progress_streak')}")
            check("质量收敛：stdout 与 stderr 都明示「连续 N 轮无质量进展」",
                  "连续 2 轮无质量进展" in so3 and "连续 2 轮无质量进展" in (se3 or ""),
                  f"got so={so3[:120]} se={se3[:120]}")
            # trace 事件登记（observability.trace_events 已含 no_progress）
            tp = os.path.join(w4, ".workbuddy", "harness_trace.jsonl")
            evs = []
            if os.path.exists(tp):
                evs = [json.loads(l).get("event") for l in open(tp, encoding="utf-8") if l.strip()]
            check("质量收敛：写出 trace 事件 no_progress", "no_progress" in evs, f"got {evs}")
            s4 = jout(run(["loop", "status", "--workspace", w4])[1])
            check("质量收敛：quality_history 落盘（3 条，P0+P1 序列 [5,5,5]）",
                  [h.get("p0p1") for h in s4.get("quality_history", [])] == [5, 5, 5],
                  f"got {s4.get('quality_history')}")

        # 反向：有下降即不触发（5 → 3 → 4，streak 被下降打断，阈值 2 未达）
        with tempfile.TemporaryDirectory() as w5:
            deck5 = os.path.join(w5, "e.pptx")
            make_deck(deck5)
            run(["loop", "start", "--deck", deck5, "--workspace", w5])
            run(["loop", "continue", "--decision", "accept", "--confirmed",
                 "--p0", "3", "--p1", "2", "--p2", "5", "--workspace", w5])   # 5
            run(["loop", "continue", "--decision", "accept", "--confirmed",
                 "--p0", "1", "--p1", "2", "--p2", "5",
                 "--allow-unverified", "--workspace", w5])   # 3（下降）
            r6, so6, _ = run(["loop", "continue", "--decision", "accept", "--confirmed",
                              "--p0", "2", "--p1", "2", "--p2", "5",
                              "--allow-unverified", "--workspace", w5])  # 4
            s6 = jout(so6)
            check("质量收敛：出现下降后 streak 归零 → 不触发（exit 0）",
                  r6 == 0 and s6.get("no_progress") is False
                  and s6.get("no_progress_streak") == 1, f"got {r6} {so6[:160]}")

        # ── 场景 9（v3.16.0 F6 补）：质量数**报告优先**，自报为辅 ──────────
        # 背景：--p0/--p1/--p2 手工值理论可注水；verify_deck 早有 --json 报告，
        #   机器复算必须是第一数据源，且来源要写进快照（可追溯 > 看起来自动）。
        # v3.17.0 B2-2：报告必须**绑定本轮课件**（stats.file），否则"别处课件的报告"
        #   会被照单全收参与收敛判定 —— 本节 report() 一律带上本轮课件路径。
        with tempfile.TemporaryDirectory() as w8:
            deck8 = os.path.join(w8, "g.pptx")
            make_deck(deck8)
            other8 = os.path.join(w8, "other.pptx")
            make_deck(other8)
            run(["loop", "start", "--deck", deck8, "--workspace", w8])

            def report(name, gate, stats_file=None):
                p = os.path.join(w8, f"{name}.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump({"gate": gate,
                               "stats": {"file": stats_file or deck8}}, f)
                return p

            real = report("real", {"p0": 5, "p1": 1, "note_coverage": 0.62,
                                   "p2_threshold": 0.8, "p2_block": True, "p3": 2})
            # 灌水报告：把 p0 改成 1（模拟改报告而非改课件）
            tampered = report("tampered", {"p0": 1, "p1": 0, "note_coverage": 0.95,
                                           "p2_threshold": 0.8, "p2_block": False, "p3": 0})
            # ① 真实报告：取到 gate.p0/p1，来源为 verify_json
            rv1, sov1, _ = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--verify-json", real, "--workspace", w8])
            s1 = jout(sov1)
            check("报告优先：--verify-json 取 gate.p0/p1（5/1），source=verify_json",
                  rv1 == 0 and s1.get("quality_snapshot", {}).get("p0") == 5
                  and s1.get("quality_snapshot", {}).get("p1") == 1
                  and s1.get("quality_source", "").startswith("verify_json|"), f"got {sov1[:200]}")

            # ② 灌水报告 + 冲突手工值 → 取报告值，手工值只存证不采用
            rv2, sov2, sev2 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                   "--p0", "9", "--p1", "9", "--p2", "9",
                                   "--verify-json", tampered, "--workspace", w8])
            s2 = jout(sov2)
            check("冲突场景：手工 9/9/9 vs 报告 1/0/0 → 取报告值并存证 manual_ignored",
                  rv2 == 0 and s2.get("quality_snapshot", {}).get("p0") == 1
                  and s2.get("quality_snapshot", {}).get("manual_ignored") == {"p0": 9, "p1": 9, "p2": 9}
                  and "以报告为准" in (sev2 or ""), f"got {sov2[:200]} se={sev2[:120]}")

            # ③ 报告缺 p0 → 显式报错（exit 2），**不静默取 0**、不退回手工值
            badp0 = report("bad_nop0", {"p1": 1, "note_coverage": 0.9, "p2_block": False})
            rv3, _, sev3 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--p0", "0", "--p1", "0", "--p2", "0",
                                "--verify-json", badp0, "--workspace", w8])
            check("报告缺 gate.p0 → exit 2 且原文说明不按 0 处理（不退回手工值）",
                  rv3 == 2 and "gate 缺 p0" in (sev3 or "") and "不按 0 处理" in (sev3 or ""),
                  f"got {rv3} {sev3[:160]}")

            # ④ 报告文件不存在 → exit 3（依赖缺失）
            rv4, _, sev4 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--verify-json", os.path.join(w8, "nope.json"), "--workspace", w8])
            check("报告不存在 → exit 3（依赖缺失，不静默取 0）", rv4 == 3 and "报告不存在" in (sev4 or ""),
                  f"got {rv4} {sev4[:160]}")

            # ⑤ 仅手工（无报告）→ source=manual 且标记未核验
            #    ⚠ v3.17.0 B2-2：本轮 history 里已有 verify_json 来源（无手工条目），
            #    故手工值仍可作为"首次自报"进入（source=manual）。
            rv5, sov5, sev5 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                   "--p0", "2", "--p1", "1", "--p2", "3", "--workspace", w8])
            s5 = jout(sov5)
            check("仅手工值 → source=manual 且标注未经 --verify-json 交叉核验",
                  rv5 == 0 and s5.get("quality_source") == "manual"
                  and s5.get("quality_snapshot", {}).get("unverified")
                  and "source=manual" in (sev5 or ""), f"got {sov5[:200]} se={sev5[:120]}")

            # ⑥ 报告不可解析 → 显式报错（不取 0、不退回手工值）
            badjson = os.path.join(w8, "broken.json")
            with open(badjson, "w", encoding="utf-8") as f:
                f.write("{ NOT JSON")
            rv6, _, sev6 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--verify-json", badjson, "--workspace", w8])
            check("报告不可解析 → exit 2 且原文说明不按 0 处理",
                  rv6 == 2 and "不可解析" in (sev6 or "") and "不按 0 处理" in (sev6 or ""),
                  f"got {rv6} {sev6[:160]}")

            # ⑦ **别处课件的报告** → 必须被拒（不得参与本轮收敛判定）
            wrong = report("wrong_deck", {"p0": 0, "p1": 0, "p2_block": False},
                           stats_file=other8)
            rv7, _, sev7 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--verify-json", wrong, "--workspace", w8])
            check("别处课件的报告 → 拒绝采用（exit 2，原文明示不匹配）",
                  rv7 == 2 and "另一份课件" in (sev7 or ""),
                  f"got {rv7} {sev7[:200]}")

            # ⑧ 报告缺 stats.file → 无法确认归属，必须被拒（不得静默接受）
            nostats = os.path.join(w8, "nostats.json")
            with open(nostats, "w", encoding="utf-8") as f:
                json.dump({"gate": {"p0": 1, "p1": 0, "p2_block": False}}, f)
            rv8, _, sev8 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--verify-json", nostats, "--workspace", w8])
            check("报告缺 stats.file → 拒绝采用（无法确认对应哪份课件）",
                  rv8 == 2 and "stats" in (sev8 or ""),
                  f"got {rv8} {sev8[:200]}")

        # ── 场景 10（v3.17.0 B2-2）：手工填数被"强制 verify-json"规则拦下 ─────
        # 攻击实测：手工 --p0 逐轮递减（9→7→5→3）能让每轮都判"有进展"，
        #   而真实情况该课件 P0 恒为 3、从未变好 → 收敛判据永不触发。
        with tempfile.TemporaryDirectory() as w9:
            deck9 = os.path.join(w9, "h.pptx")
            make_deck(deck9)
            run(["loop", "start", "--deck", deck9, "--workspace", w9])
            ra1, _, sea1 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--p0", "9", "--p1", "0", "--p2", "0", "--workspace", w9])
            check("递减假数序列：第 1 轮手工自报放行（exit 0，source=manual）",
                  ra1 == 0, f"got {ra1} {sea1[:160]}")
            ra2, _, sea2 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--p0", "7", "--p1", "0", "--p2", "0", "--workspace", w9])
            check("递减假数序列：第 2 轮手工自报被拦下（exit 2，明示须用 --verify-json）",
                  ra2 == 2 and "拒绝进位" in (sea2 or "") and "--verify-json" in (sea2 or ""),
                  f"got {ra2} {sea2[:200]}")
            sa9 = jout(run(["loop", "status", "--workspace", w9])[1])
            check("递减假数序列：被拦下的轮次**未**进位（quality_history 仍只有 1 条）",
                  len(sa9.get("quality_history", [])) == 1,
                  f"got {sa9.get('quality_history')}")
            # 逃生口：显式 --allow-unverified → 放行但**留痕**（blocker + source 标记）
            ra3, _, sea3 = run(["loop", "continue", "--decision", "accept", "--confirmed",
                                "--p0", "7", "--p1", "0", "--p2", "0",
                                "--allow-unverified", "--workspace", w9])
            sa9b = jout(run(["loop", "status", "--workspace", w9])[1])
            kinds = [b.get("kind") for b in sa9b.get("blockers", [])]
            check("逃生口 --allow-unverified：放行但登记 blocker 事件（留痕）",
                  ra3 == 0 and "unverified_quality_source" in kinds,
                  f"got {ra3} blockers={kinds}")
            check("逃生口 --allow-unverified：快照 source 标为 manual_unverified（可被下游发现）",
                  any(h.get("source") == "manual_unverified"
                      for h in sa9b.get("quality_history", [])),
                  f"got {[h.get('source') for h in sa9b.get('quality_history', [])]}")

        # ── 场景 11（v3.17.0 B2-2）：make-gate 必须发现 manual 来源 ──────────
        with tempfile.TemporaryDirectory() as w10:
            deck10 = os.path.join(w10, "i.pptx")
            make_deck(deck10)
            run(["loop", "start", "--deck", deck10, "--workspace", w10])
            run(["loop", "continue", "--decision", "accept", "--confirmed",
                 "--p0", "3", "--p1", "1", "--p2", "0", "--workspace", w10])
            rm1, som1, _ = run(["loop", "make-gate", "--workspace", w10])
            reasons = " ".join(jout(som1).get("reasons", []))
            check("make-gate：quality_history 含手工来源 → 阻断并指明（exit≠0）",
                  rm1 != 0 and "非机器复算来源" in reasons,
                  f"got {rm1} {reasons[:200]}")

        # ── 场景 12（v3.17.0 B2-2）：收敛判据三情形（单元级）────────────────
        # 比较次数 = len(hist)-1：只有 1 条快照 → 无从比较 → 不触发。
        try:
            sys.path.insert(0, HERE)
            import harness as _h
            streak1 = _h._loop_no_progress_streak([{"round": 1, "p0p1": 5}])
            streak_flat = _h._loop_no_progress_streak(
                [{"round": 1, "p0p1": 5}, {"round": 2, "p0p1": 5}, {"round": 3, "p0p1": 5}])
            streak_down = _h._loop_no_progress_streak(
                [{"round": 1, "p0p1": 5}, {"round": 2, "p0p1": 3}, {"round": 3, "p0p1": 2}])
            check("收敛判据③：只有 1 条快照 → 不触发（比较次数 = len-1，streak=0）",
                  streak1 == 0, f"got {streak1}")
            check("收敛判据①：连续持平 → streak 累积（2 次比较 → streak=2）",
                  streak_flat == 2, f"got {streak_flat}")
            check("收敛判据②：逐轮下降 → streak 归零（不触发）",
                  streak_down == 0, f"got {streak_down}")
        except Exception as e:
            check("收敛判据三情形（单元级）", False, f"import/调用失败：{e}")

        # ── 场景 13（v3.17.0 B2-3）：task_state.json 持久化加固 ──────────────
        with tempfile.TemporaryDirectory() as w11:
            ws = os.path.join(w11, ".workbuddy")
            os.makedirs(ws, exist_ok=True)
            sp = os.path.join(ws, "task_state.json")
            run(["state", "init", "--workspace", w11])
            rs1, _, _ = run(["state", "set", "--stage", "2", "--workspace", w11])
            check("task_state：正常 set 放行（exit 0）", rs1 == 0, f"got {rs1}")
            # ① 篡改 task_id → 报警 + 非 0 退出 + 不推进
            with open(sp, encoding="utf-8") as f:
                d = json.load(f)
            d["task_id"] = "t-DIFFERENT-PROCESS"
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            rs2, _, se2 = run(["state", "set", "--stage", "3", "--workspace", w11])
            with open(sp, encoding="utf-8") as f:
                d2 = json.load(f)
            check("task_state：篡改 task_id 后 set → 报警 + 非 0 退出（并发防护命中）",
                  rs2 != 0 and "task_id" in (se2 or ""), f"got {rs2} {se2[:200]}")
            check("task_state：篡改后**未推进**（current_stage 仍为 2）",
                  d2.get("current_stage") == 2, f"got {d2.get('current_stage')}")
            # ② 损坏文件 → 拒绝写入 + 原文件不被覆盖
            with open(sp, "w", encoding="utf-8") as f:
                f.write("BAD")
            before = open(sp, encoding="utf-8").read()
            rs3, _, se3 = run(["state", "set", "--stage", "3", "--workspace", w11])
            after = open(sp, encoding="utf-8").read()
            check("task_state：文件损坏 → set 拒绝写入（非 0 退出）",
                  rs3 != 0 and "损坏" in (se3 or ""), f"got {rs3} {se3[:200]}")
            check("task_state：文件损坏 → 原文件**不被覆盖**（保留供人工修）",
                  after == before == "BAD", f"got {after!r}")
            # ③ 非法 JSON 值 → 显式报错（不静默存字符串）
            with tempfile.TemporaryDirectory() as w12:
                run(["state", "init", "--workspace", w12])
                rs4, _, se4 = run(["state", "set", "--key", "quality_history",
                                   "--value", "xxx", "--workspace", w12])
                sp12 = os.path.join(w12, ".workbuddy", "task_state.json")
                d12 = json.load(open(sp12, encoding="utf-8"))
                check("task_state：--value 非法 JSON → 显式报错（非 0 退出）",
                      rs4 != 0 and "不是合法 JSON" in (se4 or ""), f"got {rs4} {se4[:200]}")
                check("task_state：--value 非法 JSON → **不得静默存字符串**（键不存在）",
                      "quality_history" not in d12, f"got {d12.get('quality_history')!r}")

        # 终止原因唯一源：yaml 新增的「连续 N 轮无质量进展」可用，自造原因仍被拒
        with tempfile.TemporaryDirectory() as w6:
            deck6 = os.path.join(w6, "f.pptx")
            make_deck(deck6)
            run(["loop", "start", "--deck", deck6, "--workspace", w6])
            r7, so7, _ = run(["loop", "terminate", "--reason", "连续 N 轮无质量进展",
                              "--workspace", w6])
            check("终止原因读 yaml：新登记的「连续 N 轮无质量进展」被接受（exit 0）",
                  r7 == 0 and jout(so7).get("termination") == "连续 N 轮无质量进展",
                  f"got {r7} {so7[:120]}")
            r8, _, se8 = run(["loop", "terminate", "--reason", "我自造的原因", "--workspace", w6])
            check("终止原因穷举：自造原因仍被拒（exit 2）", r8 == 2, f"got {r8} {se8[:120]}")

        # 白名单联动：quality_history 必须能写进 task_state.json（否则静默失败）
        with tempfile.TemporaryDirectory() as w7:
            run(["state", "init", "--workspace", w7])
            r9, _, se9 = run(["state", "set", "--key", "quality_history", "--value",
                              '[{"round":1,"p0":3,"p1":2,"p2":5}]', "--workspace", w7])
            check("白名单联动：quality_history 可写入 task_state.json（context.state_allowed_keys）",
                  r9 == 0, f"got {r9} {se9[:120]}")
            # v3.17.0 补强：不只看 exit 0，还要确认**值真的以 list 形态落盘**
            #   （静默存字符串会让下游 isinstance(h, dict) 过滤掉 → 判据静默失效）
            sp7 = os.path.join(w7, ".workbuddy", "task_state.json")
            d7 = json.load(open(sp7, encoding="utf-8"))
            qh7 = d7.get("quality_history")
            check("白名单联动：quality_history 以 list[dict] 形态落盘（非字符串）",
                  isinstance(qh7, list) and isinstance(qh7[0], dict)
                  and qh7[0].get("p0") == 3, f"got {qh7!r}")

    # ── 场景 14（v3.17.0 收尾）：NCBI api_key / 限速 / 退避告警 / label 真读 ──
    # 背景：NCBI 对无 key 的匿名访问限速 3 req/s，连续批量请求会被 abuse 系统封禁
    #   （Access Denied / 429，部分网络路径下表现为 SSL EOF）→ 存量清单跑不完。
    # 收尾批：api_key 支持（真值只从环境变量读）+ 可配限速 + 遇速率限制指数退避
    #   并**显式告警**（不静默重试到超时）。
    try:
        sys.path.insert(0, HERE)
        import harness as _h
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        stub_state = {"queries": [], "mode": "ok"}

        class _Stub(BaseHTTPRequestHandler):
            def do_GET(self):
                stub_state["queries"].append(self.path)
                if stub_state["mode"] == "429":
                    self.send_response(429)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                m = re.search(r"term=(\d+)", self.path)
                ids = [m.group(1)] if m and m.group(1) == "1954218" else []
                body = json.dumps({"esearchresult": {"count": str(len(ids)),
                                                     "idlist": ids}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), _Stub)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        ep_url = f"http://127.0.0.1:{port}/esearch.fcgi"
        try:
            # ① api_key 进 URL（key 真值只从环境变量读 → 这里直接传函数参数）
            stub_state["queries"].clear()
            r = _h.pmid_existence_check(["1954218"], endpoint=ep_url, sleep=0,
                                        api_key="TESTKEY-123")
            check("api_key：请求 URL 带 &api_key=（key 只来自环境变量→函数参数）",
                  r.get("1954218") is True
                  and stub_state["queries"]
                  and "api_key=TESTKEY-123" in stub_state["queries"][0],
                  f"got {r} q={stub_state['queries']}")
            # ② 无 key：URL 不带 api_key，且限速仍为匿名档
            stub_state["queries"].clear()
            r2 = _h.pmid_existence_check(["1954218"], endpoint=ep_url, sleep=0)
            check("无 key：URL 不含 api_key（不泄漏/不乱拼参数）",
                  r2.get("1954218") is True
                  and stub_state["queries"]
                  and "api_key" not in stub_state["queries"][0],
                  f"got {r2} q={stub_state['queries']}")
            tsc = _h.load_three_source_config()
            ep_nokey = _h._esearch_params(tsc)
            ep_key = _h._esearch_params({**tsc, "source_verification": {
                **tsc.get("source_verification", {}),
                "pubmed": {**((tsc.get("source_verification") or {}).get("pubmed") or {}),
                           "api_key_env": "VET_B2_TEST_KEY"}}})
            os.environ["VET_B2_TEST_KEY"] = "FAKE-KEY"
            try:
                ep_key = _h._esearch_params({**tsc, "source_verification": {
                    **tsc.get("source_verification", {}),
                    "pubmed": {**((tsc.get("source_verification") or {}).get("pubmed") or {}),
                               "api_key_env": "VET_B2_TEST_KEY"}}})
            finally:
                os.environ.pop("VET_B2_TEST_KEY", None)
            check("api_key：yaml 只存**环境变量名**，真值从环境取（有 key→限速 0.11s / 无 key→0.4s）",
                  ep_nokey["api_key"] == "" and ep_nokey["sleep"] == 0.4
                  and ep_key["api_key"] == "FAKE-KEY" and ep_key["sleep"] == 0.11,
                  f"nokey={ep_nokey['api_key']!r}/{ep_nokey['sleep']} "
                  f"key={ep_key['api_key']!r}/{ep_key['sleep']}")
            # ③ 429 → 指数退避 + **显式告警**（不静默重试到超时）
            stub_state["mode"] = "429"
            stub_state["queries"].clear()
            alarms = []
            r3 = _h.pmid_existence_check(["1954218"], endpoint=ep_url, sleep=0,
                                        max_retries=1, backoff_base=0.05, backoff_cap=0.05,
                                        suspect_threshold=2, on_alarm=alarms.append)
            check("429：退避重试后仍失败 → 记 None（网络失败，不计已验证）",
                  r3.get("1954218") is None, f"got {r3}")
            check("429：退避**显式告警**「疑似触发 NCBI 速率限制」（不静默重试）",
                  any("疑似触发 NCBI 速率限制" in a for a in alarms),
                  f"got {alarms}")
            check("429：退避后仍再发请求（真退避，不是直接放弃）",
                  len(stub_state["queries"]) >= 2, f"got {len(stub_state['queries'])}")
            stub_state["mode"] = "ok"
        finally:
            srv.shutdown()
            srv.server_close()

        # ④ sources[*].label 必须被代码真读（此前是"配了无人读"的死配置键）
        labels = _h._source_labels(_h.load_three_source_config())
        check("label 死键：sources[*].label 被代码真读（三类来源名都拿到）",
              labels.get("pubmed") and labels.get("textbook") and labels.get("regulation"),
              f"got {labels}")
        src = _h.classify_source({"kind": "textbook", "ref": "ISBN:978-7-117-22282-2"},
                                 _h.load_three_source_config(), {})
        check("label 死键：定档结果带来源类型显示名（报告里可见）",
              src.get("label") == labels.get("textbook"), f"got {src.get('label')!r}")
    except Exception as e:
        check("B2 收尾：api_key / 退避 / label 用例", False, f"import/调用失败：{e}")

    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例：", FAIL)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

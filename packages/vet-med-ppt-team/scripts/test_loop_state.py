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

    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例：", FAIL)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

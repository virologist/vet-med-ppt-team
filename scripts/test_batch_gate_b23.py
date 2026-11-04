#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_batch_gate_b23.py — B23/B24/B25（第五轮诊断 N1–N9）回归守卫

立项背景（2026-11-03 第五轮**生产实证**诊断，全部问题首次有真实 trace 佐证）：
  N7【P1】verify-tier 未接入调度面：continue 质量计数走 source="manual"（主理人手填），
       `--verify-json` 通道闲置 ⇒ 自报数一路走到 make-gate，无任何机器交叉核验。
  N3【P1】结构判据时序错位：题页/目录/随堂测等 gate 结构项不在闸2 蓝图检查单
       ⇒ 首跑 M2=0/1 必然、缺题页闸4 才发现。
  N2【P2】缺 `ai_unfixable` 缺陷类别：AI 不可修复缺陷混入施工清单
       （几何版式修复三轮证伪：重叠 4→16→19，白烧 3 轮还引入过自引入缺陷）。
  N4【P2】spawn 无成员通道前置探测：degrade 5 条**全是事后记录**。
  N6【P2】成员调用无配额/时长预算护栏：严真奥撞 429，撞限前零预警。
  N1【P3】闸3 施工脚本一次性（未沉淀通用手术工具）。
  N5【P3】insights 分片缺成员侧模板：首用踩 schema 3 次。
  N9【P3】「何时值得 spawn 成员」无决策判据。

本文件钉死的机器断言（对应诊断报告「验证标准」全部条目）：
  T1  continue 用手工自报数 ⇒ rc=1（首轮硬拦，B23①）
  T2  continue 带 verify 报告 ⇒ 放行且 source=verify_json|…（B23①）
  T3  逃生口 --allow-unverified ⇒ 放行但登记 blocker + 快照标 manual_unverified
  T4  配置键 quality_source_required 被改成非法值 ⇒ rc=2（配了要生效，不得回落）
  T5  蓝图模板 5 项 gate 结构预检清单在 sop-stages.md 可 grep（B23②）
  T6  同一 5 项检查单在 course-profile-defaults.md 同步存在（镜像一致）
  T7  fix_class 分流：ai_unfixable 进人工挂账区，不进 AI 清单（B24③）
  T8  未登记类型落缺省 ai（不影响存量判据）
  T9  preflight --probe-members 输出 member_channel_mismatch 清单（B24④）
  T10 超 15 分钟 spawn→member-return 对 ⇒ trace warning（B24⑤）
  T11 deck_surgery.py --help 可用（B25⑥）
  T12 insight-part-template.json 存在且被装配器注入（B25⑦）
  T13 主理人 MD「何时值得拉成员」三行判据可 grep（B25⑧）

用法：
    python3 -m pytest scripts/test_batch_gate_b23.py -q
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import harness  # noqa: E402

PKG = os.path.dirname(_HERE)
HARNESS = os.path.join(_HERE, "harness.py")
SHARED_CORE = os.path.join(os.path.dirname(PKG), "shared-core")


# ─────────────────────────── 工具 ───────────────────────────

def _run_cli(args):
    """走真实 CLI（子进程）——保证 argparse 接线也被覆盖。"""
    p = subprocess.run([sys.executable, HARNESS] + list(args),
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _jout(s):
    """取 stdout 里的 JSON（脚本可能先打印告警行）。

    用**末尾配平扫描**而非 find('{')/rfind('}')——后者在 JSON 里含嵌套对象时
    会截错边界（preflight 的 report 有多层嵌套 + 前置告警行）。
    """
    try:
        return json.loads(s)
    except Exception:
        pass
    # 从后往前找一个能完整解析的 JSON 对象
    for end in range(len(s), 0, -1):
        if s[end - 1:end] != "}":
            continue
        depth = 0
        start = None
        for i in range(end - 1, -1, -1):
            if s[i] == "}":
                depth += 1
            elif s[i] == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start is None:
            continue
        try:
            return json.loads(s[start:end])
        except Exception:
            continue
    return {}


def _make_deck(path):
    """造一份最小 pptx（python-pptx 不可用时退化为占位文件）。"""
    try:
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(path)
    except Exception:
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04fake-deck")


def _round_review(w, tag="rr"):
    """登记一份六项齐全的轮报（continue 的前置硬判据）。"""
    p = os.path.join(w, f"{tag}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "本轮改了什么": "按用户裁决修订了 3 处表述",
            "依据": "verify_deck 报告 + 七维量规逐条对照",
            "未解决": "2 张配图分辨率待补",
            "下一步": "补齐配图后请用户复裁",
            "风险": "配图若补不齐，第 12 页结论页强度不足",
            "需用户裁决": "是否接受降低配图标准先交付",
        }, f, ensure_ascii=False)
    return _run_cli(["loop", "review", "--file", p, "--workspace", w])


def _verify_report(w, deck, p0=1, p1=0, name="rep"):
    """造一份**绑定本轮课件**的 verify_deck 报告（stats.file 必须指向 deck）。"""
    p = os.path.join(w, f"{name}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "gate": {"p0": p0, "p1": p1, "note_coverage": 0.62,
                     "p2_threshold": 0.8, "p2_block": True, "p3": 0},
            "stats": {"file": deck},
        }, f, ensure_ascii=False)
    return p


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


def _read(rel):
    with open(os.path.join(PKG, rel), encoding="utf-8") as f:
        return f.read()


# ─────────────────────────── B23① 质量来源硬约束 ───────────────────────────

class TestQualitySourceGate(unittest.TestCase):
    """T1–T4：治 N7「自报数一路走到制作门」。"""

    def _start(self, w, deck):
        rc, so, se = _run_cli(["loop", "start", "--deck", deck, "--workspace", w])
        self.assertEqual(rc, 0, f"loop start 失败：{so[:200]} {se[:200]}")

    def test_T1_manual_quality_counts_blocked(self):
        """手工自报数 continue ⇒ rc=1 硬拦（B23① 核心断言）。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            self._start(w, deck)
            _round_review(w, "rr1")
            rc, so, se = _run_cli([
                "loop", "continue", "--decision", "accept", "--confirmed",
                "--p0", "3", "--p1", "1", "--p2", "0", "--workspace", w])
            self.assertEqual(rc, 1,
                             f"手工自报数竟被放行（rc={rc}）——质量来源纪律失效\n{se[:400]}")
            self.assertIn("拒绝进位", se, "未明示拒绝进位")
            self.assertIn("quality_source_required", se,
                          "未指明约束来自哪个配置键（无法自查）")
            # 未进位 ⇒ quality_history 不应出现
            st = _jout(_run_cli(["loop", "status", "--workspace", w])[1])
            self.assertEqual(st.get("quality_history"), [],
                             "被拦下的轮次仍写进了 quality_history")

    def test_T2_verify_report_accepted_and_source_marked(self):
        """带 verify 报告 ⇒ 放行且 source=verify_json|<路径>（机器复算来源）。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            self._start(w, deck)
            rep = _verify_report(w, deck, p0=5, p1=1)
            _round_review(w, "rr1")
            rc, so, se = _run_cli([
                "loop", "continue", "--decision", "accept", "--confirmed",
                "--verify-json", rep, "--workspace", w])
            self.assertEqual(rc, 0, f"带 verify 报告竟被拦：{se[:400]}")
            out = _jout(so)
            self.assertTrue(str(out.get("quality_source", "")).startswith("verify_json|"),
                            f"source 未标为 verify_json：{out.get('quality_source')}")
            st = _jout(_run_cli(["loop", "status", "--workspace", w])[1])
            hist = st.get("quality_history") or []
            self.assertTrue(hist, "quality_history 未落盘")
            self.assertTrue(str(hist[-1].get("source", "")).startswith("verify_json|"),
                            f"快照 source 未标机器复算：{hist[-1]}")

    def test_T3_escape_hatch_leaves_trace(self):
        """逃生口 --allow-unverified ⇒ 放行但登记 blocker + 快照标 manual_unverified。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            self._start(w, deck)
            _round_review(w, "rr1")
            rc, so, se = _run_cli([
                "loop", "continue", "--decision", "accept", "--confirmed",
                "--p0", "3", "--p1", "1", "--p2", "0",
                "--allow-unverified", "--workspace", w])
            self.assertEqual(rc, 0, f"逃生口竟不放行：{se[:300]}")
            st = _jout(_run_cli(["loop", "status", "--workspace", w])[1])
            kinds = [b.get("kind") for b in (st.get("blockers") or [])]
            self.assertIn("unverified_quality_source", kinds,
                          f"逃生口未留痕（blockers={kinds}）")
            hist = st.get("quality_history") or []
            self.assertTrue(any(h.get("source") == "manual_unverified" for h in hist),
                            f"快照未标 manual_unverified：{hist}")

    def test_T4_illegal_quality_source_config_rejected(self):
        """配置键改成非法值 ⇒ rc=2（配了要生效，不得静默回落成"照样拦"）。"""
        import yaml
        cfgp = os.path.join(PKG, "config", "harness.yaml")
        with open(cfgp, encoding="utf-8") as f:
            raw = f.read()
        cfg = yaml.safe_load(raw)
        cfg["loop_b"]["budgets"]["quality_source_required"] = "manual"
        backup = raw
        try:
            with open(cfgp, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
            with tempfile.TemporaryDirectory() as w:
                deck = os.path.join(w, "d.pptx")
                _make_deck(deck)
                self._start(w, deck)
                _round_review(w, "rr1")
                rc, so, se = _run_cli([
                    "loop", "continue", "--decision", "accept", "--confirmed",
                    "--p0", "3", "--p1", "1", "--p2", "0", "--workspace", w])
                self.assertEqual(rc, 2,
                                 f"非法配置值竟未被拒（rc={rc}）——配了不生效\n{se[:300]}")
                self.assertIn("quality_source_required", se)
        finally:
            with open(cfgp, "w", encoding="utf-8") as f:
                f.write(backup)
        # 还原校验
        with open(cfgp, encoding="utf-8") as f:
            self.assertEqual(yaml.safe_load(f)["loop_b"]["budgets"]["quality_source_required"],
                             "verify", "配置未还原干净")


# ─────────────────────────── B23② 结构判据前置 ───────────────────────────

GATE_CHECKLIST_ITEMS = ("题页", "目录页", "随堂测", "课时", "口径")


class TestGateChecklistFrontload(unittest.TestCase):
    """T5–T6：治 N3「结构判据时序错位」。"""

    def test_T5_checklist_in_sop_stages(self):
        src = _read("references/sop-stages.md")
        self.assertIn("gate 结构项预检清单", src,
                      "sop-stages.md 缺「gate 结构项预检清单」节（B23②）")
        for it in GATE_CHECKLIST_ITEMS:
            self.assertIn(it, src, f"sop-stages.md 检查单缺项：{it}")

    def test_T6_checklist_mirrored_in_course_profile(self):
        """双文件镜像：course-profile-defaults.md 必须有同一份检查单。"""
        src = _read("references/course-profile-defaults.md")
        self.assertIn("gate 结构项预检清单", src,
                      "course-profile-defaults.md 缺同名检查单节（镜像不一致）")
        for it in GATE_CHECKLIST_ITEMS:
            self.assertIn(it, src, f"course-profile-defaults.md 检查单缺项：{it}")

    def test_T6b_mirror_checklist_items_identical(self):
        """两份文档的镜像块**逐字相等**（由 test_arch_drift 的 GATE_CHECKLIST_MIRROR 守卫）。

        本用例只做**入口断言**（哨兵存在 + 5 项都在），
        逐字相等由 scripts/test_arch_drift.py::TestGateChecklistMirror 负责。
        """
        import re

        def block(text, rel):
            m = re.search(r"<!-- GATE_CHECKLIST_MIRROR_BEGIN -->(.*?)"
                          r"<!-- GATE_CHECKLIST_MIRROR_END -->",
                          text, re.S)
            self.assertIsNotNone(m, f"{rel} 缺 GATE_CHECKLIST_MIRROR 哨兵块")
            return m.group(1)

        a = block(_read("references/sop-stages.md"), "sop-stages.md")
        b = block(_read("references/course-profile-defaults.md"),
                  "course-profile-defaults.md")
        for it in GATE_CHECKLIST_ITEMS:
            self.assertIn(it, a, f"sop-stages.md 镜像块缺项：{it}")
            self.assertIn(it, b, f"course-profile-defaults.md 镜像块缺项：{it}")


# ─────────────────────────── B24③ fix_class 分流 ───────────────────────────

class TestFixClassSplit(unittest.TestCase):
    """T7–T8：治 N2「AI 修不了的缺陷混进施工清单」。"""

    def test_T7_unfixable_routed_to_manual_backlog(self):
        import loop_contract as lc
        notes = []
        issues = [
            {"type": "文字墙", "slide": 3, "detail": "整页字数超限"},
            {"type": "配色混乱", "slide": 5, "detail": "色板不统一"},
            {"type": "字号过小(正文)", "slide": 7, "detail": "正文 10pt"},
        ]
        split = lc.fix_class_split(issues, notes)
        types_by_class = {k: [i.get("type") for i in v] for k, v in split.items()
                          if isinstance(v, list)}
        self.assertIn("文字墙", types_by_class.get("ai_unfixable", []),
                      f"文字墙未进人工挂账区：{types_by_class}")
        self.assertIn("配色混乱", types_by_class.get("human", []),
                      f"配色混乱未进人工确认区：{types_by_class}")
        self.assertIn("字号过小(正文)", types_by_class.get("ai", []),
                      f"字号过小未进 AI 清单：{types_by_class}")
        # ai_unfixable 的条目必须带**为什么 AI 修不了**的理由
        unfix = [i for i in split["ai_unfixable"] if i.get("type") == "文字墙"]
        self.assertTrue(unfix and unfix[0].get("fix_class_reason"),
                        "ai_unfixable 条目缺 fix_class_reason（挂账须给理由）")
        # 互斥：同一条不得同时出现在两张清单
        all_types = (types_by_class.get("ai", []) + types_by_class.get("human", [])
                     + types_by_class.get("ai_unfixable", []))
        self.assertEqual(len(all_types), len(set(all_types)),
                         "同一条缺陷被分流进多张清单（清单互斥性失效）")

    def test_T8_unregistered_type_defaults_to_ai(self):
        import loop_contract as lc
        notes = []
        split = lc.fix_class_split([{"type": "某个从未登记过的类型", "slide": 1}], notes)
        self.assertEqual(len(split["ai"]), 1,
                         "未登记类型未落缺省 ai——存量判据受影响")
        self.assertEqual(split["ai_unfixable"], [])
        self.assertEqual(split["human"], [])

    def test_T7b_worklist_command_splits_three_lists(self):
        """`loop worklist --verify-json <报告>` ⇒ 产出 ai/human/ai_unfixable 三张清单。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            rc, so, se = _run_cli(["loop", "start", "--deck", deck, "--workspace", w])
            self.assertEqual(rc, 0, se[:200])
            rp = os.path.join(w, "rep.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump({"stats": {"file": deck}, "issues": [
                    {"type": "文字墙", "slide": 3},
                    {"type": "配色混乱", "slide": 5},
                    {"type": "字号过小(正文)", "slide": 7},
                ]}, f, ensure_ascii=False)
            outp = os.path.join(w, "wl.json")
            rc, so, se = _run_cli([
                "loop", "worklist", "--verify-json", rp,
                "--out", outp, "--workspace", w])
            self.assertEqual(rc, 0, f"worklist 失败：{se[:300]}")
            wl = _jout(so)
            self.assertEqual(wl["counts"]["ai_unfixable"], 1, f"分流计数错：{wl['counts']}")
            self.assertEqual(wl["counts"]["human"], 1, f"分流计数错：{wl['counts']}")
            self.assertEqual(wl["counts"]["ai"], 1, f"分流计数错：{wl['counts']}")
            # 落盘文件存在且可回读
            self.assertTrue(os.path.isfile(outp), "worklist 未落盘")
            with open(outp, encoding="utf-8") as f:
                disk = json.load(f)
            self.assertEqual(disk["counts"]["ai_unfixable"], 1)

    def test_T7c_add_item_fix_class_persisted(self):
        """`loop add-item --fix-class ai_unfixable` ⇒ 条目落盘带分类。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            rc, so, se = _run_cli(["loop", "start", "--deck", deck, "--workspace", w])
            self.assertEqual(rc, 0, se[:200])
            fp = os.path.join(w, "J-001.md")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("# J-001\n")
            rc, so, se = _run_cli([
                "loop", "add-item", "--item", "J-001", "--page", "s3",
                "--file", fp, "--fix-class", "ai_unfixable", "--workspace", w])
            self.assertEqual(rc, 0, f"add-item 失败：{se[:300]}")
            st = _jout(_run_cli(["loop", "status", "--workspace", w])[1])
            counts = st.get("fix_class_counts") or {}
            self.assertEqual(counts.get("ai_unfixable"), 1,
                             f"status 未暴露人工挂账计数：{counts}")
            # 明细仍在 state 里（status 是摘要视图，不吐 items 明细）
            sp = os.path.join(w, ".workbuddy", "loopB_state.json")
            with open(sp, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual((raw.get("items") or {}).get("J-001", {}).get("fix_class"),
                             "ai_unfixable", "state 里条目未落 fix_class")

    def test_T7d_add_item_rejects_illegal_fix_class(self):
        """枚举外分类 ⇒ 拒（拼错的分类不得静默混入）。"""
        with tempfile.TemporaryDirectory() as w:
            deck = os.path.join(w, "d.pptx")
            _make_deck(deck)
            _run_cli(["loop", "start", "--deck", deck, "--workspace", w])
            fp = os.path.join(w, "J-002.md")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("# J-002\n")
            # CLI 层 argparse choices 已拦；此处直接打函数层，验证不靠 CLI 也能拦
            args = types.SimpleNamespace(
                action="add-item", loop="b", workspace=w, actor="team-lead",
                deck="", wip="", task_id="", max_rounds=0, file="", replace=False,
                items="", item="J-002", page="s1", severity="", owner="",
                decision=None, confirmed=False, reason="", p0=None, p1=None,
                p2=None, verify_json="", allow_unverified=False, files="",
                batch="", regression="", n=1, lint_json="", geo_baseline="",
                read_log="", elements="", caption=False, out="", check_refs=False,
                kind="", note="", path="", force=False, keep=0, drop_open="",
                dry_run=False, agent="", stage=None, input_bytes=0,
                output_bytes=0, envelope="", fix_class="bogus_class",
            )
            so, se = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
                try:
                    rc = harness.cmd_loop(args)
                except SystemExit as e:
                    rc = e.code
            self.assertNotEqual(rc, 0, "非法 fix_class 竟被接受")
            self.assertIn("fix-class", se.getvalue())


# ─────────────────────────── B24④ spawn 前通道探测 ───────────────────────────

class TestProbeMembers(unittest.TestCase):
    """T9：治 N4「degrade 从事后变事前」。"""

    def test_T9_probe_members_reports_mismatch(self):
        """登记为 general-purpose 的成员 ⇒ member_channel_mismatch + 降级预案。"""
        with tempfile.TemporaryDirectory() as w:
            # 造一份"团队登记"：某成员的 agentType 被平台回落成 general-purpose
            # ⚠ 用**临时目录**当 teams 根，不污染 ~/.workbuddy/teams
            teams_root = os.path.join(w, "teams")
            os.makedirs(teams_root, exist_ok=True)
            teams_dir = os.path.join(teams_root, "test-b24-team")
            os.makedirs(teams_dir, exist_ok=True)
            cfgp = os.path.join(teams_dir, "config.json")
            members = list((harness.load_cfg()[0].get("members") or {}).keys())
            if not members:
                self.skipTest("members 表为空，跳过")
            mid = members[0]
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"members": [{"name": mid, "agentType": "general-purpose"}]},
                          f, ensure_ascii=False)
            # 通过环境变量把 teams 根指到临时目录（TEAMS_DIR 是模块常量）
            import shutil
            shutil.copy(os.path.join(_HERE, "harness.py"),
                        os.path.join(w, "harness_copy.py"))
            # 直接调函数层（CLI 子进程拿不到 monkeypatch）
            so, se = io.StringIO(), io.StringIO()
            orig = harness.TEAMS_DIR
            harness.TEAMS_DIR = teams_root
            try:
                args = types.SimpleNamespace(
                    team="test-b24-team", workspace=w, probe_channels=False,
                    probe_members=True, domain="", task_id="T-B24",
                )
                with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
                    try:
                        rc = harness.cmd_preflight(args)
                    except SystemExit as e:
                        rc = e.code
            finally:
                harness.TEAMS_DIR = orig
            out = so.getvalue()
            err = se.getvalue()
            rep = _jout(out)
            mp = rep.get("member_probe")
            self.assertIsNotNone(mp, f"无 member_probe 段：{sorted(rep)}")
            self.assertEqual(mp.get("status"), "ran")
            self.assertIn(mid, mp.get("mismatches", []),
                          f"回落成员未进 mismatches：{mp}")
            entry = (mp.get("members") or {}).get(mid)
            self.assertEqual(entry, "member_channel_mismatch",
                             f"成员状态判错：{entry}")
            self.assertIn("member_channel_mismatch", err,
                          "stderr 未明示通道不一致")
            # 不阻断（通道回落是平台行为，不是主理人错误）
            self.assertIn(rc, (0, 1))

    def test_T9b_probe_members_writes_trace(self):
        """探测须留痕（preflight trace 事件带 probe=members）。"""
        with tempfile.TemporaryDirectory() as w:
            teams_root = os.path.join(w, "teams")
            os.makedirs(teams_root, exist_ok=True)
            so, se = io.StringIO(), io.StringIO()
            orig = harness.TEAMS_DIR
            harness.TEAMS_DIR = teams_root
            try:
                args = types.SimpleNamespace(
                    team="test-b24-none", workspace=w, probe_channels=False,
                    probe_members=True, domain="", task_id="T-B24",
                )
                with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
                    try:
                        rc = harness.cmd_preflight(args)
                    except SystemExit as e:
                        rc = e.code
            finally:
                harness.TEAMS_DIR = orig
            self.assertIn(rc, (0, 1))
            evs = _trace_events_of(w, "preflight")
            self.assertTrue(evs, "preflight 未写 trace 事件")
            probes = [e for e in evs if e.get("detail", {}).get("probe") == "members"]
            self.assertTrue(probes, f"未见 probe=members 的 preflight 事件：{evs}")


# ─────────────────────────── B24⑤ 成员调用预算护栏 ───────────────────────────

class TestMemberCallBudget(unittest.TestCase):
    """T10：治 N6「撞限前零预警」。"""

    def test_T10_over_budget_member_return_warns(self):
        with tempfile.TemporaryDirectory() as w:
            rc, so, se = _run_cli([
                "spawn", "--agent", "dvm-content-expert", "--task-id", "T-B24",
                "--stage", "2", "--workspace", w])
            self.assertEqual(rc, 0, so[:200])
            spawns = _trace_events_of(w, "spawn")
            self.assertTrue(spawns, "spawn 未写 trace")
            d = spawns[-1]["detail"]
            self.assertIn("member_call_started_at", d,
                          "spawn 未记起始时间戳——耗时无从差算")
            self.assertIn("member_call_budget_minutes", d,
                          "spawn 未记预算分钟数")
            # 回填超预算耗时
            rc, so, se = _run_cli([
                "member-return", "--agent", "dvm-content-expert",
                "--task-id", "T-B24", "--status", "success",
                "--elapsed-minutes", "42", "--workspace", w])
            self.assertEqual(rc, 0, se[:200])
            self.assertIn("预算", se, "超预算未在 stderr 可见化")
            self.assertIn("拆分任务", se, "超预算未给拆分任务建议")
            mrs = _trace_events_of(w, "member_return")
            self.assertTrue(mrs, "member_return 未写 trace")
            md = mrs[-1]["detail"]
            self.assertTrue(md.get("over_member_call_budget"),
                            f"trace 未标超预算：{md}")
            self.assertEqual(md.get("elapsed_minutes"), 42.0)
            # 不阻断
            self.assertEqual(rc, 0)

    def test_T10b_within_budget_no_warning(self):
        with tempfile.TemporaryDirectory() as w:
            rc, so, se = _run_cli([
                "member-return", "--agent", "dvm-content-expert",
                "--task-id", "T-B24", "--status", "success",
                "--elapsed-minutes", "3", "--workspace", w])
            self.assertEqual(rc, 0)
            self.assertNotIn("拆分任务", se)
            mrs = _trace_events_of(w, "member_return")
            self.assertFalse(mrs[-1]["detail"].get("over_member_call_budget"))

    def test_T10c_budget_is_config_driven(self):
        """预算分钟数取自配置（禁硬编码）。"""
        import yaml
        cfg = yaml.safe_load(_read("config/harness.yaml"))
        self.assertIn("member_call_minutes", cfg["loop_b"]["budgets"],
                      "缺 member_call_minutes 配置键")
        self.assertEqual(cfg["loop_b"]["budgets"]["member_call_minutes"], 15)


# ─────────────────────────── B25⑥⑦⑧ 沉淀与判据 ───────────────────────────

class TestB25Artifacts(unittest.TestCase):
    """T11–T13：治 N1/N5/N9。"""

    def test_T11_deck_surgery_help(self):
        p = subprocess.run([sys.executable, os.path.join(PKG, "scripts", "deck_surgery.py"),
                            "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, f"deck_surgery --help 失败：{p.stderr[:300]}")
        self.assertIn("--fix", p.stdout, "缺 --fix 参数")
        for fix in ("superscript", "note", "font", "color", "density"):
            self.assertIn(fix, p.stdout, f"--fix 枚举缺 {fix}")

    def test_T12_insight_part_template_exists_and_injected(self):
        """模板存在 + 被联邦装配器注入（spawn prompt 的资源路径里出现）。"""
        tpl = os.path.join(PKG, "references", "insight-part-template.json")
        self.assertTrue(os.path.isfile(tpl), "insight-part-template.json 不存在")
        with open(tpl, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("_part_template", data, "模板缺 _part_template 段")
        # 被装配器收录（resolve_shared_refs 收 references/ 下的 .md/.yaml/.yml/.json）
        from pathlib import Path
        sys.path.insert(0, SHARED_CORE)
        import assemble_spawn_prompt as asp
        refs = asp.resolve_shared_refs(Path(PKG))
        names = [os.path.basename(r) for r in refs]
        self.assertIn("insight-part-template.json", names,
                      f"装配器未收录分片模板：{names}")

    def test_T12b_template_part_validates(self):
        """模板内的示例分片必须能通过 validate_part（否则模板本身是坑）。"""
        import insight_carrier as ic
        tpl = os.path.join(PKG, "references", "insight-part-template.json")
        with open(tpl, encoding="utf-8") as f:
            data = json.load(f)
        part = data.get("_part_template")
        self.assertIsInstance(part, dict, "缺 _part_template")
        ok, errs = ic.validate_part(part)
        self.assertTrue(ok, f"模板示例分片未通过 validate_part：{errs}")

    def test_T13_team_lead_spawn_criteria(self):
        """主理人 MD 的「何时值得拉成员」三行判据可 grep。"""
        src = _read("agents/vet-med-ppt-team-team-lead.md")
        self.assertIn("何时值得拉成员", src, "主理人 MD 缺 spawn 决策判据节")
        for kw in ("证据核验", "独立验证", "版式设计"):
            self.assertIn(kw, src, f"判据缺必拉场景：{kw}")
        self.assertIn("不拉", src, "判据缺「不拉成员」口径")
        self.assertIn("领域判断", src, "判据缺一句话测")

    def test_T13b_sop_documents_b23_b24_discipline(self):
        """SOP 双文件必须写清「continue 前出机器数」与分流纪律。"""
        for rel, kws in (
            ("references/dual-loop-governance.md",
             ("quality_source_required", "allow-unverified", "verify-json")),
            ("references/harness-engine.md",
             ("member_call_minutes", "quality_source_required")),
        ):
            src = _read(rel)
            for kw in kws:
                self.assertIn(kw, src, f"{rel} 缺关键项：{kw}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

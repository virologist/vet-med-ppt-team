#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_loop_wiring.py — v3.20.0「判据层接线」回归（harness.py × loop_contract.py）

立项理由（不是"再补几个用例"）：
  v3.20.0 逐键取证发现：config/harness.yaml 的 loop_a / loop_b / delta_gate 三段
  34 个叶子键里 32 个**没有任何代码读取者**——"配了但没生效"，正是本包反复治理的
  同型缺陷（声明层 ≠ 执行层）。本批把它们接到 scripts/loop_contract.py 上。

  接线这件事**极易假绿**：把配置值打印出来、或读进来却不做判定，输出看起来一样。
  故本文件的每条断言都按「**改配置 → 行为必须跟着变**」来写（反例优先）：
    · T1  state_file：改 loop_a.state_file ⇒ 状态文件真的换个地方落（不是打印出来）
    · T2  enabled：置 false ⇒ 动作被拒（此前恒为放行，改配置零效果）
    · T3  single_writer：--actor 不符 ⇒ 被拒
    · T4  confirm_before_each_batch / regression_required / patch_discipline：
          批次门三条**逐条**能拦住（缺一即是"配了没生效"）
    · T5  round_review.required：无轮报 ⇒ continue 被拦（此前文档纪律而已）
    · T6  baseline_fields / block_on_new_defects / insert_spatial_audit：
          缺字段、自引入、拿不出 lint 报告 ⇒ 各自被拦
    · T7  defaults：--out 产出的模板**必须全是 suggested**（防"仓库默认值冒充确认"）
    · T8  geo_baseline_required / baseline_required：make-gate 的两条新 reason
    · T9  doctor 可发现性：新动作必须出现在 doctor 输出里（不可发现 = 对 LLM 不存在）

隔离策略（重要）：Loop A 状态的**默认**落点是 `<包>/.workbuddy/`（包目录）。
  测试若走默认配置会往包目录写状态文件（虽被 .gitignore 忽略，但会干扰人工排查）。
  故本文件统一 monkeypatch `harness.load_cfg`，把两个 state_file 指到临时目录，
  全程不碰包内任何文件。

用法：
    python3 -m pytest scripts/test_loop_wiring.py -q
    python3 scripts/test_loop_wiring.py
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
    """读真实配置（判据值必须与生产同源，测试里另写一份就是双源）。"""
    import yaml
    with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _args(**kw):
    """构造 cmd_loop 的 args（字段与 main() 里 loop parser 一一对应，缺一即 AttributeError）。"""
    base = dict(
        action="", loop="b", workspace="", actor="team-lead", deck="", wip="",
        task_id="", max_rounds=0, file="", replace=False, items="", item="",
        page="", severity="", owner="", decision=None, confirmed=False, reason="",
        p0=None, p1=None, p2=None, verify_json="", allow_unverified=False,
        files="", batch="", regression="", n=1, lint_json="", geo_baseline="",
        read_log="", elements="", caption=False, out="", check_refs=False,
        kind="", note="", path="", force=False,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def _run(cmd_args):
    """跑 cmd_loop，返回 (退出码, stdout, stderr)。"""
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            rc = harness.cmd_loop(cmd_args)
        except SystemExit as e:            # argparse 路径（本文件不走 main，留作兜底）
            rc = e.code
    return rc, so.getvalue(), se.getvalue()


def _jout(s):
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        return json.loads(s[i:j + 1]) if 0 <= i < j else {}


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


ROUND_REVIEW_6 = {
    "本轮改了什么": "x", "依据": "y", "未解决": "z",
    "下一步": "a", "风险": "b", "需用户裁决": "c",
}


class _TmpLoop(unittest.TestCase):
    """每个用例一个临时工作区；state_file 指到临时目录（不碰包目录）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.w = self._tmp.name
        self.cfg = _base_cfg()
        self.cfg.setdefault("loop_a", {})["state_file"] = \
            os.path.join(self.w, ".workbuddy", "loopA_state.json")
        self.cfg.setdefault("loop_b", {})["state_file"] = \
            os.path.join(self.w, ".workbuddy", "loopB_state.json")
        self.cfg["loop_b"]["coexist_with"] = \
            os.path.join(self.w, ".workbuddy", "task_state.json")
        self._orig_load = harness.load_cfg
        harness.load_cfg = lambda: (self.cfg, True)
        deck = os.path.join(self.w, "demo.pptx")
        with open(deck, "wb") as f:
            f.write(b"PK\x03\x04fake-deck-for-wiring-test")
        self.deck = deck

    def tearDown(self):
        harness.load_cfg = self._orig_load
        self._tmp.cleanup()

    def start_b(self):
        rc, so, se = _run(_args(action="start", workspace=self.w, deck=self.deck,
                                loop="b"))
        self.assertEqual(rc, 0, f"start 失败：{se[:300]}")
        return _jout(so)


class TestStateFileAndIdentity(_TmpLoop):
    """T1–T3：路径与身份三键（state_file / enabled / single_writer）。"""

    def test_T1_state_file_from_config_not_hardcoded(self):
        """T1 反例：改 loop_a.state_file ⇒ 状态文件**真的**换个地方落（不是只打印）。"""
        custom = os.path.join(self.w, "custom", "loopA.json")
        self.cfg["loop_a"]["state_file"] = custom
        p, notes = harness._loop_path_for(self.cfg, self.w, "a")
        self.assertEqual(os.path.abspath(p), os.path.abspath(custom),
                         "改了 loop_a.state_file 却仍落到别处——路径仍是硬编码")
        self.assertEqual(notes, [], "配置齐全时不该有回落 note")

    def test_T1b_fallback_warns_not_silent(self):
        """T1b：配置缺 state_file ⇒ 回落内置值**且**留 note（静默回落 = 不设防）。"""
        cfg = {"loop_b": {}}
        se = io.StringIO()
        with contextlib.redirect_stderr(se):
            p, notes = harness._loop_path_for(cfg, self.w, "b")
        self.assertTrue(notes, "缺 state_file 时未记录回落 note——调用方无从得知")
        self.assertTrue(se.getvalue().strip(), "回落 note 未透到 stderr（不得吞掉）")
        self.assertTrue(p.endswith("loopB_state.json"))

    def test_T2_enabled_false_blocks(self):
        """T2 反例：enabled=false ⇒ 动作被拒（此前该键零读取者，改它零效果）。"""
        self.cfg["loop_b"]["enabled"] = False
        rc, _so, se = _run(_args(action="status", workspace=self.w))
        self.assertEqual(rc, 1, f"enabled=false 仍放行——该键没被代码消费：{se[:200]}")
        self.assertIn("停用", se)

    def test_T2b_enabled_true_allows(self):
        """T2b 正例：enabled=true ⇒ 正常放行（守卫不得误杀）。"""
        self.start_b()
        rc, _so, se = _run(_args(action="status", workspace=self.w))
        self.assertEqual(rc, 0, f"enabled=true 却被拦：{se[:200]}")

    def test_T3_single_writer_mismatch_blocked(self):
        """T3 反例：--actor 与 single_writer 不符 ⇒ 拒绝写状态。"""
        self.start_b()
        rc, _so, se = _run(_args(action="add-item", item="I-1", workspace=self.w,
                                 actor="dvm-content-expert"))
        self.assertEqual(rc, 1, f"非唯一写者仍被放行：{se[:200]}")
        self.assertIn("写者不符", se)

    def test_T3b_writer_recorded(self):
        """T3b：写者留痕——落盘的 last_writer 必须是本次 --actor。"""
        self.start_b()
        _run(_args(action="add-item", item="I-1", workspace=self.w, actor="team-lead"))
        st = json.load(open(os.path.join(self.w, ".workbuddy", "loopB_state.json")))
        self.assertEqual(st.get("last_writer"), "team-lead")
        # 未声明写者 ⇒ 记「未声明」（不得留空，空 = 无从追责）
        _run(_args(action="add-item", item="I-2", workspace=self.w, actor="", force=True))
        st = json.load(open(os.path.join(self.w, ".workbuddy", "loopB_state.json")))
        self.assertEqual(st.get("last_writer"), "未声明")

    def test_T3c_start_records_paths(self):
        """T3c：start 把 state_file / coexist_with 两条绝对路径写进 _paths（可追溯）。"""
        st = self.start_b()
        self.assertEqual(st["_paths"]["state_file"],
                         os.path.join(self.w, ".workbuddy", "loopB_state.json"))
        self.assertTrue(st["_paths"]["coexist_with"].endswith("task_state.json"))


class TestLoopABatchGate(_TmpLoop):
    """T4：Loop A 批次门三件套必须**逐条**能拦住。"""

    def _open(self, files="", batch="b1"):
        return _run(_args(action="batch-open", loop="a", workspace=self.w,
                          files=files, batch=batch, note="测试批次"))

    def test_T4a_confirm_gate(self):
        """T4a：confirm_before_each_batch=true 且未 --confirmed ⇒ 拒绝收批。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        rc, _so, se = _run(_args(action="batch-close", loop="a", workspace=self.w,
                                 batch="b1",
                                 regression="ensure_settings,test_harness,test_five_gates"))
        self.assertEqual(rc, 1, f"未确认却收批成功：{se[:200]}")
        self.assertIn("未确认", se)

    def test_T4b_regression_gate(self):
        """T4b：regression_required 缺一 ⇒ 收批被拒（"跑两项就算了"必须拦住）。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        rc, so, se = _run(_args(action="batch-close", loop="a", workspace=self.w,
                                batch="b1", confirmed=True, regression="ensure_settings"))
        self.assertEqual(rc, 1, f"回归缺 2 项仍收批：{se[:200]}")
        out = _jout(so)
        self.assertEqual(out["reason"], "regression_incomplete")
        self.assertEqual(sorted(out["missing"]), ["test_five_gates", "test_harness"])

    def test_T4c_declared_file_scope_check(self):
        """T4c：声明文件越出 loop_a.scope ⇒ **开批即被拒**（与 check-path 同一份判定）。"""
        outside = os.path.join(self.w, "用户课件.pptx")
        with open(outside, "wb") as f:
            f.write(b"PK\x03\x04")
        rc, so, se = self._open(files=outside)
        self.assertEqual(rc, 1, f"越界文件竟能开批：{se[:200]}")
        self.assertEqual(_jout(so)["rejected"][0]["kind"], "forbidden")

    def test_T4d_in_scope_opens_and_judge_source_visible(self):
        """T4d：白名单内文件可开批；batch-status 须报出每个判据键的取值来源。"""
        rc, so, se = self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        self.assertEqual(rc, 0, f"白名单内文件开批失败：{se[:300]}")
        rc2, so2, _ = _run(_args(action="batch-status", loop="a", workspace=self.w))
        self.assertEqual(rc2, 0)
        out = _jout(so2)
        self.assertTrue(out["batches"]["b1"]["start_commit"] or
                        out["batches"]["b1"]["start_commit"] is None)
        for k in ("confirm_before_each_batch", "patch_discipline", "regression_required"):
            self.assertIn(k, out["judge"], f"batch-status 未报判据键 {k} 的来源")
            self.assertEqual(out["judge"][k]["source"], "取自 yaml",
                             f"{k} 应为取自 yaml（走了回落说明配置没读到）")

    def test_T4e_batch_actions_reject_loop_b(self):
        """T4e：batch-* 属 Loop A，误用 --loop b ⇒ 用法错误（exit 2）。"""
        rc, _so, se = _run(_args(action="batch-status", loop="b", workspace=self.w))
        self.assertEqual(rc, 2, f"Loop B 下 batch-* 未被拒：{se[:200]}")


class TestLoopBReviewAndDelta(_TmpLoop):
    """T5–T6：轮报门禁与增量门禁。"""

    def test_T5_continue_requires_round_review(self):
        """T5 反例：本轮无轮报 ⇒ continue 被拦（此前"每轮轮报"只是文档纪律）。"""
        self.start_b()
        rc, _so, se = _run(_args(action="continue", workspace=self.w,
                                 decision="accept", confirmed=True))
        self.assertEqual(rc, 1, f"无轮报竟能进位：{se[:300]}")
        self.assertIn("无轮报", se)

    def test_T5b_review_incomplete_then_complete(self):
        """T5b：轮报缺项 ⇒ exit 1；补齐六项 ⇒ 可进位。"""
        self.start_b()
        rc, _so, se = _run(_args(action="review", workspace=self.w,
                                 file=_write(os.path.join(self.w, "rr_bad.json"),
                                             {"只有一项": "x"})))
        self.assertEqual(rc, 1, f"轮报只 1 项竟通过：{se[:200]}")
        rc2, _so2, se2 = _run(_args(action="review", workspace=self.w,
                                    file=_write(os.path.join(self.w, "rr.json"),
                                                ROUND_REVIEW_6)))
        self.assertEqual(rc2, 0, f"六项齐全却未通过：{se2[:200]}")
        rc3, _so3, se3 = _run(_args(action="continue", workspace=self.w,
                                    decision="accept", confirmed=True))
        self.assertEqual(rc3, 0, f"有轮报却不能进位：{se3[:300]}")

    def test_T6a_baseline_fields_from_config(self):
        """T6a：缺 delta_gate.baseline_fields 里的字段 ⇒ 拒绝登记。"""
        self.start_b()
        fields = loop_contract.delta_gate_cfg(self.cfg)["baseline_fields"]
        partial = {fields[0]: 1}
        rc, so, se = _run(_args(action="baseline", workspace=self.w,
                                file=_write(os.path.join(self.w, "b.json"), partial)))
        self.assertEqual(rc, 1, f"基线只给 1 个字段竟通过：{se[:200]}")
        self.assertEqual(sorted(_jout(so)["missing"]), sorted(fields[1:]))

    def test_T6b_delta_blocks_new_defects(self):
        """T6b：自引入 P0 上升 ⇒ 增量门禁阻断（block_on_new_defects）。"""
        self.start_b()
        full = {f: (1 if f == "p0" else 0) for f in
                loop_contract.delta_gate_cfg(self.cfg)["baseline_fields"]}
        _run(_args(action="baseline", workspace=self.w,
                   file=_write(os.path.join(self.w, "base.json"), full)))
        rep = _write(os.path.join(self.w, "rep.json"),
                     {"gate": {"p0": 9, "p1": 0, "p2": 0},
                      "stats": {"file": self.deck}})
        lint = _write(os.path.join(self.w, "lint.json"),
                      {"summary": {"geo_new_overlap": 0}})
        rc, so, se = _run(_args(action="delta", workspace=self.w,
                                verify_json=rep, lint_json=lint))
        self.assertEqual(rc, 1, f"自引入 P0 上升竟放行：{se[:300]}")
        out = _jout(so)
        self.assertTrue(out["blocked"])
        self.assertEqual(out["increased"][0]["metric"], "p0")

    def test_T6c_delta_passes_and_renders_report(self):
        """T6c 正例：未引入新缺陷 + 有 lint 报告 ⇒ 放行，且报告行按 report_format 渲染。"""
        self.start_b()
        full = {f: (5 if f == "p0" else 0) for f in
                loop_contract.delta_gate_cfg(self.cfg)["baseline_fields"]}
        _run(_args(action="baseline", workspace=self.w,
                   file=_write(os.path.join(self.w, "base.json"), full)))
        rep = _write(os.path.join(self.w, "rep.json"),
                     {"gate": {"p0": 3, "p1": 0, "p2": 0},
                      "stats": {"file": self.deck}})
        lint = _write(os.path.join(self.w, "lint.json"),
                      {"summary": {"geo_new_overlap": 0}})
        rc, so, se = _run(_args(action="delta", workspace=self.w,
                                verify_json=rep, lint_json=lint))
        self.assertEqual(rc, 0, f"未引入新缺陷却被拦：{se[:300]}")
        out = _jout(so)
        self.assertTrue(out["reports"][0]["ok"], "报告行未按 report_format 渲染/守恒")
        self.assertIn("自引入 -2", out["reports"][0]["report"])

    def test_T6d_spatial_audit_without_lint_report_is_blocked(self):
        """T6d：insert_spatial_audit=true 却拿不出 lint 报告 ⇒ 按「未做」阻断。"""
        self.start_b()
        full = {f: (5 if f == "p0" else 0) for f in
                loop_contract.delta_gate_cfg(self.cfg)["baseline_fields"]}
        _run(_args(action="baseline", workspace=self.w,
                   file=_write(os.path.join(self.w, "base.json"), full)))
        rep = _write(os.path.join(self.w, "rep.json"),
                     {"gate": {"p0": 3, "p1": 0, "p2": 0},
                      "stats": {"file": self.deck}})
        rc, so, se = _run(_args(action="delta", workspace=self.w, verify_json=rep))
        self.assertEqual(rc, 1, f"无 lint 报告竟放行（审计等于没做）：{se[:300]}")
        self.assertIn("未做", se + so)


class TestDefaultsAndMakeGate(_TmpLoop):
    """T7–T8：默认档与制作前置门的新增两条。"""

    def test_T7_out_template_all_suggested(self):
        """T7：--out 产出的 intake 模板**必须全是 suggested**（防仓库默认值冒充确认）。"""
        out = os.path.join(self.w, "intake_tpl.json")
        rc, so, se = _run(_args(action="defaults", workspace=self.w, out=out))
        self.assertEqual(rc, 0, f"defaults --out 失败：{se[:300]}")
        tpl = json.load(open(out, encoding="utf-8"))
        for k in ("audience", "periods", "template", "scope", "acceptance"):
            self.assertEqual(tpl[k]["status"], "suggested",
                             f"{k} 的 status 不是 suggested——默认档会冒充用户确认")
        self.assertIn("suggested ≠ confirmed", se)

    def test_T7b_check_refs_detects_dangling(self):
        """T7b 反例：把默认档里某个 ref 改成不存在的文件 ⇒ --check-refs 必须 exit 1。"""
        self.cfg["loop_b"]["defaults"]["profile_ref"] = "references/__不存在的档案__.md"
        rc, _so, se = _run(_args(action="defaults", workspace=self.w, check_refs=True))
        self.assertEqual(rc, 1, f"引用悬空却未报：{se[:300]}")
        self.assertIn("缺失", se)

    def test_T8_make_gate_requires_geo_and_delta_baseline(self):
        """T8：geo_baseline_required / baseline_required 未登记 ⇒ make-gate 新增两条 reason。"""
        self.start_b()
        rc, so, se = _run(_args(action="make-gate", workspace=self.w))
        self.assertNotEqual(rc, 0)
        reasons = " ".join(_jout(so).get("reasons", []))
        self.assertIn("几何基线", reasons, "geo_baseline_required 未接进 make-gate")
        self.assertIn("增量基线", reasons, "baseline_required 未接进 make-gate")

    def test_T8b_registered_then_no_such_reason(self):
        """T8b 正例：登记齐两条基线后，这两条 reason 必须消失（守卫不得误杀）。"""
        self.start_b()
        with open(os.path.join(self.w, "i.json"), "w", encoding="utf-8") as f:
            json.dump({k: {"value": "v", "status": "confirmed"}
                       for k in harness.LOOP_INTAKE_A}, f)
        rc, so, se = _run(_args(action="intake", workspace=self.w,
                                file=os.path.join(self.w, "i.json")))
        self.assertEqual(rc, 0, f"intake 未通过：{so[:200]}{se[:200]}")
        _run(_args(action="geo-baseline", workspace=self.w, geo_baseline=self.deck))
        full = {f: 0 for f in loop_contract.delta_gate_cfg(self.cfg)["baseline_fields"]}
        _run(_args(action="baseline", workspace=self.w,
                   file=_write(os.path.join(self.w, "base.json"), full)))
        rc2, so2, _ = _run(_args(action="make-gate", workspace=self.w))
        reasons = " ".join(_jout(so2).get("reasons", []))
        self.assertNotIn("几何基线", reasons, "已登记几何基线却仍阻断")
        self.assertNotIn("增量基线", reasons, "已登记增量基线却仍阻断")
        self.assertEqual(rc2, 0, f"登记齐后仍阻断：{reasons}")


class TestDiscoverability(unittest.TestCase):
    """T9：新动作必须**可发现**（doctor 表里查得到）。"""

    def test_T9_new_actions_in_doctor(self):
        args = types.SimpleNamespace(workspace=tempfile.mkdtemp())
        so = io.StringIO()
        with contextlib.redirect_stdout(so):
            rc = harness.cmd_doctor(args)
        self.assertEqual(rc, 0)
        doc = json.loads(so.getvalue())
        actions = {a["action"] for a in doc.get("loop_actions", [])}
        for a in ("batch-open", "batch-close", "batch-status", "review",
                  "retrieval", "baseline", "delta", "geo-baseline", "defaults"):
            self.assertIn(a, actions, f"新动作 {a} 未出现在 doctor 表——对 LLM 冷启动不存在")
        # 每个动作都要能追溯到判据来源（否则又是"有动作、无判据"）
        for a in doc["loop_actions"]:
            self.assertTrue(a["judge_source"], f"{a['action']} 缺 judge_source")


if __name__ == "__main__":
    unittest.main(verbosity=2)

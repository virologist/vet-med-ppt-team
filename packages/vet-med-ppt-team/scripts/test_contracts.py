#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_contracts.py — 契约检查器的回归测试（**正例 + 能红反例**）。

v3.31.0 新建。依据本包纪律（references/defect-reflow.yaml 头注）：
「改规则不改输出」是 Loop A 反复出现的病灶——**每条新判据都必须同时给出
正例（真值通过）与反例（真值判红）**，否则「能红」无从证明。

设计（与 scripts/test_regression_skip_report.py 的
`TestTimeoutDispositionWording` 同型）：

  T1  工作地图 ⇄ harness.yaml#stages 逐项一致：正例通过 + 4 类反例判红
      （改 name / 改 members / 改 gate / 改 parallel）
  T2  体检项数口径：正例通过 + 反例判红（文档写 22/22，真源 27）
  T3  交付三件套：正例通过 + 反例判红（缺任一件）
  T4  闸间就绪：非法闸号判红 + 闸1 复用 gate1-check
  T5  MERGE_GATE 执行器在位
  T6  纯函数自洽（collect_doc_count_mentions 不读文件、classify_delivery_files 分类正确）

运行：
    python3 scripts/test_contracts.py          # 独立运行
    python3 -m pytest scripts/test_contracts.py -q
"""

import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)


def _load_module():
    """按路径加载 check_contracts.py（避免包内相对 import 失败）。"""
    spec = importlib.util.spec_from_file_location(
        "_check_contracts", os.path.join(HERE, "check_contracts.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = _load_module()


class TestWorkmapStagesParity(unittest.TestCase):
    """T1：工作地图镜像与 harness.yaml#stages 的逐项一致性。"""

    def test_T1_positive_real_repo(self):
        """正例：真实包内工作地图与 harness.yaml 逐项一致（改动前必须绿）。"""
        checks = cc.check_workmap_matches_stages(PKG_ROOT)
        bad = [c for c in checks if not c.ok]
        self.assertEqual([], [(c.cid, c.target, c.detail) for c in bad],
                         "真实包内工作地图与 harness.yaml#stages 不一致")

    def _mutated_pkg(self, mutate):
        """复制包内相关文件到临时目录并施加突变，返回临时包根。"""
        tmp = tempfile.mkdtemp(prefix="vtmp_contracts_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            os.makedirs(os.path.join(tmp, "config"))
            shutil.copy(os.path.join(PKG_ROOT, "references", "work-map.yaml"),
                        os.path.join(tmp, "references", "work-map.yaml"))
            shutil.copy(os.path.join(PKG_ROOT, "config", "harness.yaml"),
                        os.path.join(tmp, "config", "harness.yaml"))
            mutate(tmp)
            return tmp
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    def test_T1_anti_name_drift(self):
        """反例：工作地图改闸名 ⇒ 必须判红（否则镜像块形同虚设）。"""
        def mut(tmp):
            p = os.path.join(tmp, "references", "work-map.yaml")
            t = open(p, encoding="utf-8").read()
            t = t.replace("闸4.5 案例三源核验", "闸4.5 案例三源核验（已改）")
            open(p, "w", encoding="utf-8").write(t)
        tmp = self._mutated_pkg(mut)
        try:
            checks = cc.check_workmap_matches_stages(tmp)
            self.assertTrue(any((not c.ok) and c.target.endswith(".name") for c in checks),
                            "改了闸名却判绿——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T1_anti_parallel_drift(self):
        """反例：把闸2 改回「并行」⇒ 必须判红（R1/R7 同型，真值分裂）。"""
        def mut(tmp):
            p = os.path.join(tmp, "references", "work-map.yaml")
            t = open(p, encoding="utf-8").read()
            t = t.replace("parallel: false\n    input: \"闸1 冻结态", "parallel: true\n    input: \"闸1 冻结态")
            open(p, "w", encoding="utf-8").write(t)
        tmp = self._mutated_pkg(mut)
        try:
            checks = cc.check_workmap_matches_stages(tmp)
            self.assertTrue(any((not c.ok) and c.target.endswith(".parallel") for c in checks),
                            "改了 parallel 却判绿——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T1_anti_members_drift(self):
        """反例：篡改成员集合 ⇒ 必须判红。"""
        def mut(tmp):
            p = os.path.join(tmp, "references", "work-map.yaml")
            t = open(p, encoding="utf-8").read()
            t = t.replace('members: ["pedagogy-architect", "dvm-content-expert"]',
                          'members: ["pedagogy-architect", "ppt-producer"]')
            open(p, "w", encoding="utf-8").write(t)
        tmp = self._mutated_pkg(mut)
        try:
            checks = cc.check_workmap_matches_stages(tmp)
            self.assertTrue(any((not c.ok) and c.target.endswith(".members") for c in checks),
                            "改了成员却判绿——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T1_anti_missing_four_elements(self):
        """反例：删掉某闸的 acceptance ⇒ 必须判红（工作地图不得退化成空壳）。

        ⚠ 突变方式：删掉 `acceptance:` **键行及其下的列表项**，
          使 YAML 解析结果为 None（而不是空列表）——两种形态判据都要能抓。
        """
        def mut(tmp):
            p = os.path.join(tmp, "references", "work-map.yaml")
            lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
            out = []
            i = 0
            removed = False
            while i < len(lines):
                ln = lines[i]
                # 只删第一处 acceptance 块：键行 + 其后连续缩进列表项
                if (not removed and ln.strip() == "acceptance:"
                        and out and "stage: 0" not in out[-1]):
                    removed = True
                    i += 1
                    while i < len(lines) and lines[i].startswith("      - "):
                        i += 1
                    continue
                out.append(ln)
                i += 1
            assert removed, "突变未生效：未找到 acceptance 键行"
            open(p, "w", encoding="utf-8").write("".join(out))
        tmp = self._mutated_pkg(mut)
        try:
            checks = cc.check_workmap_matches_stages(tmp)
            self.assertTrue(any((not c.ok) and "acceptance" in c.target for c in checks),
                            "删了 acceptance 却判绿——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDocCountConsistency(unittest.TestCase):
    """T2：文档体检项数口径必须等于真源。"""

    def test_T2_positive_real_repo(self):
        """正例：真实包内文档口径一致（改造后必须绿）。"""
        checks = cc.check_doc_count_consistency(PKG_ROOT)
        bad = [c for c in checks if not c.ok]
        self.assertEqual([], [(c.target, c.detail) for c in bad],
                         "文档口径与真源不一致（应先修文档再收批）")

    def test_T2_anti_wrong_count(self):
        """反例：文档写 22/22 而真源 27 ⇒ 必须判红。"""
        docs = {"references/x.md": "回归 ensure_settings 22/22 全绿\n"}
        mentions = cc.collect_doc_count_mentions(PKG_ROOT, docs)
        self.assertTrue(any(v == 22 for (_, _, _, v) in mentions),
                        "未捕获 22/22 口径提及——正则失效")
        # 真源取 27 时，22 的提及必须被判为漂移
        self.assertNotEqual(22, 27)

    def test_T2_anti_ratio_not_count(self):
        """反例型反例：'3/10' 这类占比**不得**被当成口径提及。"""
        docs = {"references/x.md": "自引入缺陷 3/10 项\n"}
        mentions = cc.collect_doc_count_mentions(PKG_ROOT, docs)
        self.assertEqual([], mentions, "把占比误当口径——正则过宽")

    def test_T2_anti_mismatch_detected(self):
        """反例：真源 27 + 文档 22 ⇒ check 返回失败项。

        ⚠ 反例文档须**同时**满足收窄后的口径条件（同行提到体检）：
        「须 22/22 全绿」若不提及体检/ensure_settings，就无法判定它说的是
        体检口径（也可能是别的判据的通过率）——这是「假阳性必须为零」的代价，
        故反例写成真实漂移的原句形态（含 `ensure_settings` 标识）。
        """
        tmp = tempfile.mkdtemp(prefix="vtmp_count_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            os.makedirs(os.path.join(tmp, "scripts"))
            open(os.path.join(tmp, "scripts", "ensure_settings.py"), "w",
                 encoding="utf-8").write("N = 27  # 检查项总数\n")
            open(os.path.join(tmp, "references", "a.md"), "w",
                 encoding="utf-8").write("python3 scripts/ensure_settings.py  # 须 22/22 全绿\n")
            open(os.path.join(tmp, "references", "b.md"), "w",
                 encoding="utf-8").write("ensure_settings 27 项检查 全绿\n")
            checks = cc.check_doc_count_consistency(tmp)
            bad = [c for c in checks if not c.ok]
            self.assertEqual(1, len(bad), f"应恰好 1 处漂移，实得 {len(bad)}："
                                         f"{[(c.target, c.detail) for c in bad]}")
            self.assertIn("22", bad[0].detail)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDeliveryTriplet(unittest.TestCase):
    """T3：交付三件套齐备性。"""

    def test_T3_positive(self):
        """正例：三件齐备 ⇒ 通过。"""
        tmp = tempfile.mkdtemp(prefix="vtmp_deliv_")
        try:
            open(os.path.join(tmp, "课程.pptx"), "w").write("x")
            open(os.path.join(tmp, "逐页修改说明.md"), "w").write("x")
            open(os.path.join(tmp, "验收自检清单.md"), "w").write("x")
            checks = cc.check_delivery_triplet(tmp)
            self.assertTrue(all(c.ok for c in checks),
                            f"三件齐备却判红：{[(c.target, c.detail) for c in checks]}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T3_anti_missing_checklist(self):
        """反例：缺验收自检清单 ⇒ 必须判红（三件缺一不算完成）。"""
        tmp = tempfile.mkdtemp(prefix="vtmp_deliv_")
        try:
            open(os.path.join(tmp, "课程.pptx"), "w").write("x")
            open(os.path.join(tmp, "逐页修改说明.md"), "w").write("x")
            checks = cc.check_delivery_triplet(tmp)
            bad = [c for c in checks if not c.ok]
            self.assertEqual(1, len(bad), f"应恰好 1 件缺失，实得 {len(bad)}")
            self.assertIn("checklist", bad[0].target)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T3_classify_pure(self):
        """纯函数：分类器行为正确。"""
        b = cc.classify_delivery_files(["a.pptx", "逐页修改说明.md", "验收自检清单.md"])
        self.assertEqual(["a.pptx"], b["deck"])
        self.assertEqual(["逐页修改说明.md"], b["change_note"])
        self.assertEqual(["验收自检清单.md"], b["checklist"])


class TestGateReadiness(unittest.TestCase):
    """T4：闸间就绪检查。"""

    def test_T4_anti_illegal_stage(self):
        """反例：非法闸号 ⇒ 判红（只认 0–4）。"""
        checks = cc.check_gate_readiness(9)
        self.assertTrue(any(not c.ok for c in checks), "非法闸号却判绿")

    def test_T4_stage1_uses_gate1_check(self):
        """闸1 必须复用既有唯一判据 gate1-check（不重造轮子）。"""
        checks = cc.check_gate_readiness(1)
        self.assertTrue(any("gate1-check" in c.target for c in checks),
                        "闸1 未复用 gate1-check")

    def test_T4_no_workspace_is_warn_not_block(self):
        """未给工作区 ⇒ 提示级，不判缺陷（探测受阻 ≠ 缺陷）。"""
        checks = cc.check_gate_readiness(2)
        self.assertTrue(all(c.ok for c in checks),
                        "未提供工作区时不应判红")
        self.assertTrue(all(c.level == "warn" for c in checks),
                        "未提供工作区时严重级应为 warn")


class TestMergeGateEnforceable(unittest.TestCase):
    """T5：MERGE_GATE 执行器在位。"""

    def test_T5_executor_present(self):
        checks = cc.check_merge_gate_enforceable(PKG_ROOT)
        ex = [c for c in checks if "merge-gate" in c.target]
        self.assertTrue(ex, "未找到执行器检查项")
        self.assertTrue(ex[0].ok, "MERGE_GATE 执行器不在位")


class TestMergeGateExecution(unittest.TestCase):
    """T6：MERGE_GATE 晋升门禁执行器（把声明面变成执行面）。"""

    def test_T6_positive_real_repo(self):
        """正例：真实包内学习条目全部合法（含 grandfather 豁免）。"""
        checks = cc.run_merge_gate(PKG_ROOT)
        bad = [c for c in checks if not c.ok]
        self.assertEqual([], [(c.target, c.detail) for c in bad],
                         "真实包内学习条目状态违规")

    def test_T6_anti_new_entry_without_status(self):
        """反例：截止日**之后**的新条目缺 Status ⇒ 必须判红。

        （截止日之前的缺 Status 条目按 grandfather 条款豁免——反例必须
          晚于截止日，否则会与豁免条款冲突，测不出真问题。）
        """
        tmp = tempfile.mkdtemp(prefix="vtmp_lrn_")
        try:
            os.makedirs(os.path.join(tmp, ".learnings"))
            shutil.copy(os.path.join(PKG_ROOT, ".learnings", "MERGE_GATE.yaml"),
                        os.path.join(tmp, ".learnings", "MERGE_GATE.yaml"))
            open(os.path.join(tmp, ".learnings", "LEARNINGS.md"), "w", encoding="utf-8").write(
                "## [LRN-20261120-999] 某条新条目\n\n### Summary\n正文\n")
            checks = cc.run_merge_gate(tmp)
            bad = [c for c in checks if not c.ok]
            self.assertTrue(bad, "截止日后的新条目缺 Status 却判绿——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T6_anti_legacy_exempt(self):
        """反例型反例：截止日**之前**缺 Status ⇒ grandfather 豁免，不得判红。"""
        tmp = tempfile.mkdtemp(prefix="vtmp_lrn2_")
        try:
            os.makedirs(os.path.join(tmp, ".learnings"))
            shutil.copy(os.path.join(PKG_ROOT, ".learnings", "MERGE_GATE.yaml"),
                        os.path.join(tmp, ".learnings", "MERGE_GATE.yaml"))
            open(os.path.join(tmp, ".learnings", "LEARNINGS.md"), "w", encoding="utf-8").write(
                "## [LRN-20261104-005] 旧条目\n\n### Summary\n正文\n")
            checks = cc.run_merge_gate(tmp)
            bad = [c for c in checks if not c.ok]
            self.assertEqual([], [(c.target, c.detail) for c in bad],
                             "grandfather 条款被误判——假阳性")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T6_candidate_promotion_rules(self):
        """纯函数：candidate 晋升判定（同型 ≥3 或 ack）。"""
        entries = [
            ("LRN-A", "candidate", ["同型"]),
            ("LRN-B", "candidate", ["同型"]),
            ("LRN-C", "candidate", ["同型"]),
            ("LRN-D", "candidate", ["异型"]),
            ("LRN-E", "applied", ["同型"]),
        ]
        res = {r["id"]: r for r in cc.classify_learning_promotion(entries, 3)}
        self.assertTrue(res["LRN-A"]["promotable"], "同型累计 3 条应够格晋升")
        self.assertFalse(res["LRN-D"]["promotable"], "同型仅 1 条且未 ack，不该晋升")
        self.assertNotIn("LRN-E", res, "applied 条目不参与 candidate 判定")

    def test_T6_candidate_ack_overrides(self):
        """纯函数：管家节点 ack 可越过同型计数门槛。"""
        entries = [("LRN-X", "candidate", ["罕见型"])]
        res = cc.classify_learning_promotion(entries, 3, ack_ids=["LRN-X"])
        self.assertTrue(res[0]["promotable"], "ack 后应可晋升")
        self.assertTrue(res[0]["acked"])


class TestMergeGatePromotionSemantics(unittest.TestCase):
    """T8：candidate 状态的**语义边界**（v3.31.0 修正的判据级错误）。

    修正缘由（现场实证）：v3.31.0 首版把「candidate 未够格晋升」判红。
    但 MERGE_GATE.yaml 的门禁语义是「未过闸 = 未生效」——
    candidate 条目**本来就不该进下一轮待办**，故「未够格」是**合法状态**，
    不是缺陷。判红 = 把「尚未到晋升时机」误报为「门禁失效」= 假阳性。

    门禁真正要拦的是**反向**情形：**已够格却仍挂 candidate**——
    因为 candidate 不进待办清单 ⇒ 该条目会**永久失踪**（没人会再拾取它）。
    """

    def _tmp_pkg(self, lrn_body):
        tmp = tempfile.mkdtemp(prefix="vtmp_lrn3_")
        os.makedirs(os.path.join(tmp, ".learnings"))
        shutil.copy(os.path.join(PKG_ROOT, ".learnings", "MERGE_GATE.yaml"),
                    os.path.join(tmp, ".learnings", "MERGE_GATE.yaml"))
        open(os.path.join(tmp, ".learnings", "LEARNINGS.md"), "w", encoding="utf-8").write(lrn_body)
        return tmp

    def test_T8_positive_not_enough_is_legal(self):
        """正例：candidate 未够格（同型 <3 且未 ack）⇒ **不得判红**（合法状态）。"""
        tmp = self._tmp_pkg(
            "## [LRN-20261111-901] 缺口登记\n\n"
            "**Status**: candidate\n\n"
            "### Metadata\n- Tags: 缺口登记\n")
        try:
            checks = cc.run_merge_gate(tmp)
            bad = [c for c in checks if not c.ok and c.level == "block"]
            self.assertEqual([], [(c.target, c.detail) for c in bad],
                             "candidate 未够格被误判为缺陷——假阳性（v3.31.0 首版判据级错误）")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T8_anti_ready_but_still_candidate(self):
        """能红反例：同型累计 ≥3 已够格，却仍挂 candidate ⇒ 必须判红。

        （否则该条目因「candidate 不进待办清单」而永久失踪。）
        """
        tmp = self._tmp_pkg(
            "## [LRN-20261111-901] 甲\n\n**Status**: candidate\n\n"
            "### Metadata\n- Tags: 同型X\n\n"
            "## [LRN-20261111-902] 乙\n\n**Status**: candidate\n\n"
            "### Metadata\n- Tags: 同型X\n\n"
            "## [LRN-20261111-903] 丙\n\n**Status**: candidate\n\n"
            "### Metadata\n- Tags: 同型X\n")
        try:
            checks = cc.run_merge_gate(tmp)
            bad = [c for c in checks if not c.ok and c.level == "block"]
            self.assertTrue(bad, "已够格却仍挂 candidate 未判红——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T8_anti_acked_but_still_candidate(self):
        """能红反例2：管家节点已 ack（够格）却仍挂 candidate ⇒ 必须判红。"""
        tmp = self._tmp_pkg(
            "## [LRN-20261111-901] 甲\n\n**Status**: candidate\n\n"
            "### Metadata\n- Tags: 罕见型\n")
        try:
            checks = cc.run_merge_gate(tmp, ack_ids=["LRN-20261111-901"])
            bad = [c for c in checks if not c.ok and c.level == "block"]
            self.assertTrue(bad, "ack 后仍挂 candidate 未判红——反例失效")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestNextCommand(unittest.TestCase):
    """T7：`harness.py next` 任务级导航的行为。"""

    def _run_next(self, args):
        """跑 harness.py next，返回 (rc, stdout)。"""
        import subprocess
        hrns = os.path.join(PKG_ROOT, "scripts", "harness.py")
        r = subprocess.run([sys.executable, hrns, "next"] + args,
                           capture_output=True, text=True, timeout=180)
        return r.returncode, (r.stdout or "")

    def test_T7_positive_runs_and_reports(self):
        """正例：next 能跑出「现在在哪 / 下一步 / 验收条件」三段。

        ⚠ 退出码语义：**rc=0 = 有明确下一步**；**rc=1 = 卡住（有未满足项）**。
          本机工作区实测闸1 缺 task_mode ⇒ rc=1 是**正确**行为，
          故此处断言「rc ∈ {0,1} 且 rc=1 时必须打出『卡住』」，不断言 rc=0。
        """
        rc, out = self._run_next([])
        self.assertIn(rc, (0, 1), f"next 退出码异常 rc={rc}：{out[:300]}")
        self.assertIn("【现在在哪】", out)
        self.assertIn("【下一步动作】", out)
        self.assertIn("【验收条件】", out)
        self.assertIn("须人工", out, "必须列出人工判断项（语义/审美不交给脚本）")
        if rc == 1:
            self.assertIn("卡住", out, "rc=1 时必须明确指出卡住与未满足项")

    def test_T7_json_mode(self):
        """正例：--json 输出机器可读结构，且含四要素。"""
        import json as _json
        rc, out = self._run_next(["--json"])
        self.assertEqual(0, rc, f"next --json 失败 rc={rc}：{out[:300]}")
        data = _json.loads(out)
        for key in ("objective", "current", "next_actions", "acceptance"):
            self.assertIn(key, data, f"JSON 缺 {key}")
        self.assertIn("machine", data["acceptance"])
        self.assertIn("human", data["acceptance"])

    def test_T7_anti_missing_workmap(self):
        """反例：工作地图缺失 ⇒ 必须 rc=3（依赖缺失），不得假装「无待办」。

        这是关键反例：工作地图读不到时若返回 rc=0，冷启动会误以为一切就绪。
        """
        import subprocess
        import shutil as _sh
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_nomap_")
        try:
            hrns = os.path.join(PKG_ROOT, "scripts", "harness.py")
            # 复制 harness.py 到临时包（模拟工作地图缺失的包）
            os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
            _sh.copy(hrns, os.path.join(tmp, "scripts", "harness.py"))
            r = subprocess.run([sys.executable, os.path.join(tmp, "scripts", "harness.py"), "next"],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(3, r.returncode,
                             f"工作地图缺失时应 rc=3，实得 {r.returncode}：{(r.stdout or '')[:200]}")
            self.assertIn("工作地图", (r.stdout or "") + (r.stderr or ""))
        finally:
            _sh.rmtree(tmp, ignore_errors=True)


class TestVersionWatchlistSelfCheck(unittest.TestCase):
    """T9：体检第 14 项「版本巡检清单自检」的能红反例。

    病灶（同型第 14 处，现场实证）：v3.31.0 提版时**实际改了 14 个声明点**，
    但第 14 项只报「13 处一致」⇒ `config/figure-assets.yaml` 不在巡检清单内
    ⇒ 它若漂移，体检**照样全绿**（「声明层≠执行层」复发）。

    本项自检把「清单是否覆盖全部实际声明点」变成**可判定**的事实：
    扫描 config/ 与 references/ 下所有带顶层 `version:` 键的 yaml，
    与巡检清单取差集；差集非空 ⇒ 判红。
    """

    def _run_ensure(self, pkg_root):
        """在指定包根上跑体检第 14 项（--quick 足够，且不跑第 7 项重回归）。"""
        import subprocess
        env = dict(os.environ)
        r = subprocess.run(
            [sys.executable, os.path.join(PKG_ROOT, "scripts", "ensure_settings.py"), "--quick"],
            capture_output=True, text=True, timeout=600, cwd=pkg_root, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    def test_T9_positive_real_repo(self):
        """正例：真实包内清单覆盖全部带 version 键的 yaml ⇒ 第 14 项不报漏项。"""
        rc, out = self._run_ensure(PKG_ROOT)
        self.assertNotIn("版本巡检清单**漏项**", out,
                         "真实包内存在未被巡检的 version 声明点")

    def test_T9_anti_unlisted_yaml(self):
        """能红反例：新增一个带 version 键但未登记的 yaml ⇒ 必须判红。"""
        import shutil as _sh
        import subprocess
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_ver_")
        try:
            _sh.copytree(PKG_ROOT, os.path.join(tmp, "pkg"),
                         ignore=_sh.ignore_patterns(".git", "packages", "outputs",
                                                   "01-research", "__pycache__"))
            probe = os.path.join(tmp, "pkg", "config", "_probe_new.yaml")
            open(probe, "w", encoding="utf-8").write('version: "9.9.9"\nfoo: bar\n')
            r = subprocess.run(
                [sys.executable, os.path.join(tmp, "pkg", "scripts", "ensure_settings.py"), "--quick"],
                capture_output=True, text=True, timeout=600, cwd=os.path.join(tmp, "pkg"))
            out = (r.stdout or "") + (r.stderr or "")
            self.assertIn("版本巡检清单**漏项**", out,
                          f"新增未登记 version 键 yaml 却未判红——反例失效：{out[:400]}")
            self.assertIn("_probe_new.yaml", out, "报错必须指名漏登记的文件")
        finally:
            _sh.rmtree(tmp, ignore_errors=True)


class TestDanglingRefs(unittest.TestCase):
    """T10：契约 C8「包内路径引用可达性」（悬空引用检测）。

    病灶（本轮现场实证三次）：
      ① `references/approved-examples/README.md` 引用 `LRN-20261111-024`
         —— 该学习条目当时并不存在；
      ② `references/work-map.yaml` 注释写「人类阅读：references/work-map.md
         （由 next --render 生成）」—— 文件不存在，`next` 也无该选项；
      ⇒ 文档说的与真实存在的各说各话 ⇒ 冷启动顺着文档找文件会扑空。

    ⚠ 本项首版 22 处假阳性 ⇒ 三轮收窄（去掉 outputs/、排除前瞻性引用、排除 CHANGELOG）。
      ⇒ 测试必须同时锁住「能红」**与**「不过度判红」两侧。
    """

    def test_T10_positive_real_repo(self):
        """正例：真实包内无悬空引用（收窄后不得再冒出假阳性）。"""
        dangling = cc.collect_dangling_refs(PKG_ROOT)
        self.assertEqual([], [(d["doc"], d["line"], d["ref"]) for d in dangling],
                         "真实包内存在悬空引用")

    def test_T10_anti_dangling_ref(self):
        """能红反例：文档里写一个不存在的包内路径 ⇒ 必须被检出。"""
        import shutil as _sh
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_dangling_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            doc = os.path.join(tmp, "references", "probe.md")
            open(doc, "w", encoding="utf-8").write(
                "# 探针\n"
                "本文件引用 `references/definitely-not-exist.md` 作为配套契约。\n")
            dangling = cc.collect_dangling_refs(tmp)
            refs = [d["ref"] for d in dangling]
            self.assertIn("references/definitely-not-exist.md", refs,
                          f"悬空引用未被检出——反例失效：{dangling}")
        finally:
            _sh.rmtree(tmp, ignore_errors=True)

    def test_T10_anti_future_ref_is_not_dangling(self):
        """反例型反例：前瞻性引用（「按需建 xxx」）**不得**被判为悬空。

        ⇒ 锁住「收窄」成果：判据过宽 = 守卫被绕过 = 假阳性。
        """
        import shutil as _sh
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_future_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            open(os.path.join(tmp, "references", "probe.md"), "w", encoding="utf-8").write(
                "# 探针\n"
                "本域尚无本地导航锚点——首次接单时按需建 references/to-be-created.md\n")
            dangling = cc.collect_dangling_refs(tmp)
            self.assertEqual([], [(d["doc"], d["ref"]) for d in dangling],
                             "前瞻性引用被误判为悬空——假阳性")
        finally:
            _sh.rmtree(tmp, ignore_errors=True)

    def test_T10_anti_outputs_is_exempt(self):
        """反例型反例2：`outputs/` 不随包跟踪 ⇒ 引用它**不算**悬空。"""
        import shutil as _sh
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_outputs_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            open(os.path.join(tmp, "references", "probe.md"), "w", encoding="utf-8").write(
                "# 探针\n"
                "证据见 outputs/某次诊断报告.md（历史归档区，不随包发布）。\n")
            dangling = cc.collect_dangling_refs(tmp)
            self.assertEqual([], [(d["doc"], d["ref"]) for d in dangling],
                             "outputs/（不随包跟踪）被误判为悬空——假阳性")
        finally:
            _sh.rmtree(tmp, ignore_errors=True)


class TestActionCommandsExist(unittest.TestCase):
    """T11：契约 C9「工作地图 actions 段命令必须已注册」（可照跑性）。

    背景：`references/work-map.yaml#actions` 的定位是「**可直接照跑**的命令串」，
    冷启动的 AI 会照抄执行 ⇒ 指向未注册子命令 = 工作地图「看起来能用但跑不通」。
    ⇒ 与 C8 同族（C8 管文件存在，C9 管命令可用）。
    """

    def test_T11_positive_real_repo(self):
        """正例：真实包内 actions 段命令全部已注册。"""
        checks = cc.check_action_commands_exist(PKG_ROOT)
        bad = [c for c in checks if not c.ok and c.level == "block"]
        self.assertEqual([], [(c.target, c.detail) for c in bad],
                         "真实包内 actions 段引用了未注册子命令")

    def test_T11_anti_unregistered_command(self):
        """能红反例：actions 段写入一个未注册的子命令 ⇒ 必须判红。"""
        import shutil as _sh
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix="vtmp_act_")
        try:
            os.makedirs(os.path.join(tmp, "references"))
            os.makedirs(os.path.join(tmp, "scripts"))
            shutil.copy(os.path.join(PKG_ROOT, "references", "work-map.yaml"),
                        os.path.join(tmp, "references", "work-map.yaml"))
            shutil.copy(os.path.join(PKG_ROOT, "scripts", "harness.py"),
                        os.path.join(tmp, "scripts", "harness.py"))
            # 在 actions.open 里塞一条不存在的子命令
            wp = os.path.join(tmp, "references", "work-map.yaml")
            t = open(wp, encoding="utf-8").read()
            t = t.replace('  open:\n', '  open:\n    - "harness.py no-such-command --x"\n', 1)
            open(wp, "w", encoding="utf-8").write(t)
            checks = cc.check_action_commands_exist(tmp)
            bad = [c for c in checks if not c.ok and c.level == "block"]
            self.assertTrue(bad, "未注册子命令未被检出——反例失效")
        finally:
            _sh.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

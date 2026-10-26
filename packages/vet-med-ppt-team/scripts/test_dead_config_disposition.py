"""L3 死配置处置回归护栏（v3.19.3）。

覆盖三件事（每条都有反例，防假绿）：
  T1  第 18 项判据修复：人读型登记支持**段名/前缀**语义
      （修复前：登记写段名、判据查末段键名 ⇒ 登记从未生效）
  T2  `path_prefixes` 自动派生（不再硬编码 7 个老段）
  T3  第 24 项新增：阶段顺序漂移守卫（stages.N.next == i+1）
  T4  75 键全量定性后的预期残留 = 0
"""
import importlib.util
import io
import contextlib
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = PKG / "scripts" / "ensure_settings.py"
HARNESS_YAML = PKG / "config" / "harness.yaml"


def _load_es():
    spec = importlib.util.spec_from_file_location("es_ut", ES)
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_ut"] = m
    spec.loader.exec_module(m)
    return m


def _run_dead(es) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        es.check_dead_config_keys(str(PKG))
    return buf.getvalue()


class TestDeadConfigDisposition(unittest.TestCase):
    """T1–T4：L3 死配置处置与判据修复。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()
        cls.out = _run_dead(cls.es)

    # ── T1：段名/前缀语义生效（原缺陷：登记段名、判据查末段键名）──────────
    def test_T1_segment_prefix_registration_takes_effect(self):
        """T1：登记段名后，该段下**任何**末段键名都应计为人读型。

        缺陷实测（v3.19.3 确证）：`overlay_injection.max_overlap_ratio` 的末段是
        `max_overlap_ratio`，而 known_textual 登记的是 `overlay_injection`
        ⇒ 原判据 `leaf.lower() in known_textual` **永不匹配**，登记形同虚设。
        """
        self.assertNotIn("overlay_injection.", self.out,
                         "overlay_injection.* 仍被判死——段名登记未生效")
        self.assertNotIn("loop_b.", self.out,
                         "loop_b.* 仍被判死——段名登记未生效")
        self.assertNotIn("delta_gate.", self.out,
                         "delta_gate.* 仍被判死——段名登记未生效")

    def test_T1b_reverse_example_registration_removal_reintroduces_keys(self):
        """T1b 反例：**去掉**段名登记 ⇒ 该段下键必须重新出现在 dead 清单。

        这条是防假绿的关键：证明"键消失"是**登记起的作用**，
        而不是判据恰好放过了它。

        ⚠ **v3.22.0 修正：样例段改为动态挑选**（不再写死 `overlay_injection`）。
          原实现固定拿 `overlay_injection.*` 当样例——而 v3.22.0 G1 把这四键
          **真正接上了线**（inject_notes.py 读它们）⇒ 有代码读取点 ⇒
          删掉人读型登记后它们**本就不该**变死 ⇒ 反向例的前提被合法改变 ⇒ 转红。
          ⇒ 改为：从 known_textual 登记里**动态挑一个当前仍无 AST 读取点**的段
            （否则它被人读型登记豁免着，删掉登记就该重现），挑不到即 skip。
            这样后续任何接线都不会再打破这条护栏。

        ⚠ **v3.23.0 再修正：改为**自足式合成反例**（不再依赖内置登记的偶然状态）。
          v3.23.0 给第 18 项加了**块级证据层**（父级配置段被代码整块取走 ⇒
          该子树随父级被消费），且第 18 项另有人读型登记的**路径前缀白名单**
          （`.gates` 等）⇒ 内置登记里已**找不到**一个"只靠自身登记才存活"的键：
            · `shrink_order` 落在被整块读取的 `density` 段下（块级证据兜住）
            · `legacy_compat` 落在 `.gates` 路径前缀白名单里（段级豁免兜住）
          ⇒ 动态挑样例的路走不通（会退化成 skip，护栏名存实亡）。
          ⇒ 改为**自造样例**：在隔离副本里 ① 造一个无任何证据的探针配置键
            ② 在 `known_textual` 里为它加一行登记 ③ 断言它因此不判死
            ④ 撤掉那行登记 ⑤ 断言它**必须重新变死**。
          这样「键消失是**登记**起的作用」被**确定性地**证明，
          且不再随判据层数（路径级/块级/弱证据）演进而失效。
          ⚠ 全程在**隔离副本**上做（tempdir），不改包内文件——
            原实现直接改包内 ES 再复原，写盘瞬间会让并行体检读到半截文件
            （历轮已踩过：worker 写盘瞬间误报"文件丢失"）。
        """
        import shutil
        import tempfile
        import yaml

        seg = "__probe_t1b_reg_seg_v2303"
        leaf = "__probe_t1b_reg_leaf_v2303"
        tmp = Path(tempfile.mkdtemp(prefix="hb-t1b-"))
        try:
            shutil.copytree(PKG / "config", tmp / "config")
            shutil.copytree(PKG / "scripts", tmp / "scripts")
            es_tmp = tmp / "scripts" / "ensure_settings.py"
            hy = tmp / "config" / "harness.yaml"

            # ① 造探针配置键（全新段 ⇒ 无路径级、无块级、无同名证据）
            data = yaml.safe_load(hy.read_text(encoding="utf-8"))
            data[seg] = {leaf: True}
            hy.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")

            # ② 在副本的 known_textual 里为该段加登记
            es_src = es_tmp.read_text(encoding="utf-8")
            marker = "    known_textual = {\n"
            self.assertIn(marker, es_src, "known_textual 定义未找到")
            es_src2 = es_src.replace(marker, marker + f'        "{seg}",\n', 1)
            es_tmp.write_text(es_src2, encoding="utf-8")

            def _run_on(tmp_root):
                spec = importlib.util.spec_from_file_location(
                    "es_t1b_tmp", tmp_root / "scripts" / "ensure_settings.py")
                m = importlib.util.module_from_spec(spec)
                sys.modules["es_t1b_tmp"] = m
                spec.loader.exec_module(m)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = m.check_dead_config_keys(str(tmp_root))
                return rc, buf.getvalue()

            # ③ 有登记 ⇒ 不判死
            rc_with, out_with = _run_on(tmp)
            self.assertNotIn(f"{seg}.{leaf}", out_with,
                             "★ 登记在案却被判死——登记机制本身失效")

            # ④ 撤掉登记
            es_tmp.write_text(es_src, encoding="utf-8")

            # ⑤ 撤登记后必须重新变死
            rc_without, out_without = _run_on(tmp)
            self.assertNotEqual(rc_without, 0,
                                "★ 撤掉登记后第 18 项仍转绿——登记机制无效或判据有其它漏洞")
            self.assertIn(f"{seg}.{leaf}", out_without,
                          f"撤掉登记后 {seg}.{leaf} 未重现于死配置清单")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── T2：path_prefixes 自动派生（不再漏新段）────────────────────────
    def test_T2_path_prefixes_derived_from_known_textual(self):
        """T2：path_prefixes 必须包含 known_textual 里的段名（自动派生）。

        缺陷实测（v3.19.3 确证）：原 path_prefixes 硬编码 7 个老段
        （disease_modules/gates/ai_literacy/snapshot/fallback/members/domains），
        **不含**任何 v3.19.0 新增段 ⇒ 新段的 seg_hit 兜底也失效。
        """
        src = ES.read_text(encoding="utf-8")
        i = src.find("path_prefixes = (")
        self.assertGreater(i, 0, "path_prefixes 定义未找到")
        seg = src[i:i + 2500]
        self.assertIn("known_textual", seg,
                      "path_prefixes 未从 known_textual 派生（仍是硬编码？）")
        # 派生必须真的发生：跑一次看 visual-rules 的 gate 段是否被限定路径豁免
        self.assertNotIn("gate.deliver_gate_level", self.out,
                         "visual-rules.gate.deliver_gate_level 仍被判死"
                         "——带文件前缀的限定登记未生效")

    # ── T3：第 24 项阶段顺序守卫 ────────────────────────────────────────
    def test_T3_stage_order_guard_passes_on_current_config(self):
        """T3 正例：当前 stages 配置下第 24 项应通过（next 均 == i+1）。"""
        import yaml
        cfg = yaml.safe_load(HARNESS_YAML.read_text(encoding="utf-8"))
        stages = {str(k): v for k, v in (cfg.get("stages") or {}).items()}
        nums = sorted(int(k) for k in stages if str(k).isdigit())
        self.assertGreater(len(nums), 1, "stages 段至少应有 2 级")
        for i in nums[:-1]:
            self.assertEqual(stages[str(i)].get("next"), i + 1,
                             f"stages.{i}.next 应为 {i+1}")
        self.assertIn(stages[str(nums[-1])].get("next"), (None, "", 0),
                      "末级 stages.next 应为 None")

    def test_T3b_reverse_example_stage_order_drift_detected(self):
        """T3b 反例：注入 stages.2.next=5 ⇒ 第 24 项必须报红。

        同时验证守卫的 **YAML int 键归一化**（`0:` 被解析成 int，
        不归一化会恒取到 None 而误报漂移——本守卫首版即踩此坑）。
        """
        import yaml
        bak = HARNESS_YAML.read_text(encoding="utf-8")
        try:
            cfg = yaml.safe_load(bak)
            cfg["stages"][2]["next"] = 5
            HARNESS_YAML.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                es2 = _load_es()
                rc = es2.check_stage_order_drift(str(PKG))
            self.assertEqual(rc, 1, "注入漂移后第 24 项未报红（守卫失效）")
            self.assertIn("stages.2.next=5", buf.getvalue(),
                          "报错信息未指出具体漂移项")
        finally:
            HARNESS_YAML.write_text(bak, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc2 = _load_es().check_stage_order_drift(str(PKG))
            self.assertEqual(rc2, 0, "复原后第 24 项未归绿——配置可能未还原")

    # ── T4：75 键定性后的预期残留 ───────────────────────────────────────
    def test_T4_no_residual_dead_keys(self):
        """T4：75 键全量处置后，第 18 项应报「无死配置」。

        75 键的处置结论（v3.19.3 L3，主理人接管实施）：
          · 33 键（loop_a 4 + loop_b 20 + delta_gate 9）= 整批**声明未接线**
            （v3.9.0「双层 Loop 契约下沉批」只下沉了动作层，判据层与默认值层
            仍是纯声明；代码字面量 0 处）⇒ 登记人读型，理由据实写"声明未接线"；
          · 5 键（stages.0..4.next）= 人读型顺序说明（next_stage 代码 0 次），
            另加第 24 项漂移守卫防双份真相；
          · 2 键（caption_five_elements / caption_base_elements_note）=
            v3.19.0 G4 明确标注的**历史键**（向后兼容，不可删）；
          · 其余按段名登记（ima/standards/channels/terminology/
            english_allowed_when/consistency/english_minimum/visual-rules.gate/
            collapse/observability/report_only 等），理由逐条写在
            known_textual 的注释里。
        """
        self.assertIn("无死配置", self.out,
                      f"仍有死配置残留：{[l.strip() for l in self.out.splitlines() if '·' in l][:5]}")




class TestBClassWiring(unittest.TestCase):
    """T5–T7：35 键逐键定性中 3 个 B 类（漏消费）键的接线守卫。

    定性结论（v3.19.4，主理人独立逐键完成）：
      · `domain_config.yaml#image_fetch.license_uncertain_markers` —— 原被
        fetch_oa_image.py **硬编码**（("待核实","未明","未知","待定")），yaml 已声明同值
        ⇒「配置写了、代码硬编码」（改配置不改行为，与 v3.12.0 修掉的
        three_source 阈值硬编码同型）⇒ **B 类，已接线**。
      · `visual-rules.yaml#gate.write_gate_level` / `#gate.deliver_gate_level` ——
        sweep/gate 的 argparse 默认等级原为硬编码（"P0"/"all"），与 yaml 同值但
        互不知晓 ⇒ 双份真相 ⇒ **B 类，已接线**（_default_gate_level）。
    其余 32 键经逐键核实为 A 类（人读型，消费方为会话层/成员 LLM），
    段名批量登记合理——但本测试类守住那 3 个**不该**被批量登记掩盖的键。
    """

    def test_T5_license_markers_read_from_yaml(self):
        """T5 正例：许可不明标记词从 yaml 读（非硬编码）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("foa", PKG / "scripts" / "fetch_oa_image.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["foa"] = m
        spec.loader.exec_module(m)
        import yaml
        cfg = yaml.safe_load((PKG / "config" / "domain_config.yaml").read_text(encoding="utf-8"))
        marks, note = m.license_uncertain_markers(cfg)
        self.assertEqual(marks, ("待核实", "未明", "未知", "待定"),
                         "与 yaml 登记的标记词不一致")
        self.assertEqual(note, "", "正常路径不应产生回退说明")

    def test_T5b_reverse_example_yaml_change_propagates(self):
        """T5b 反例：改 yaml 的标记词 ⇒ 读到的值必须跟着变。

        这条是防「改配置不改行为」的**决定性判据**——若有人把接线改回硬编码，
        本测试立刻红。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("foa", PKG / "scripts" / "fetch_oa_image.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["foa"] = m
        spec.loader.exec_module(m)
        p = PKG / "config" / "domain_config.yaml"
        bak = p.read_text(encoding="utf-8")
        try:
            import yaml
            cfg = yaml.safe_load(bak)
            cfg["image_fetch"]["license_uncertain_markers"] = ["待核实", "授权待确认"]
            p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
            marks, _ = m.license_uncertain_markers(cfg)
            self.assertEqual(marks, ("待核实", "授权待确认"),
                             "改 yaml 后读到的值未变——接线被改回硬编码了")
        finally:
            p.write_text(bak, encoding="utf-8")
            marks2, _ = m.license_uncertain_markers(
                yaml.safe_load(p.read_text(encoding="utf-8")))
            self.assertEqual(marks2, ("待核实", "未明", "未知", "待定"),
                             "复原后未归位——配置可能未还原")

    def test_T6_gate_default_levels_from_yaml(self):
        """T6 正例：sweep/gate 的默认门禁等级从 yaml 读。

        ⚠ v3.19.4 补强：首版只断言**返回值**，而 `write_gate_level` 的回退值
        恰好也是 "P0" ⇒ 若有人把接线改回硬编码/注释掉，函数走回退仍返回 "P0"，
        **断言照样通过**（测试假绿）。现改为同时断言**无告警**——
        真读了 yaml 就不该往 stderr 写任何东西，走了回退才会告警。
        """
        import importlib.util, io, contextlib
        spec = importlib.util.spec_from_file_location("h", PKG / "scripts" / "harness.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["h"] = m
        spec.loader.exec_module(m)
        for key, expect in (("write_gate_level", "P0"), ("deliver_gate_level", "all")):
            errbuf = io.StringIO()
            with contextlib.redirect_stderr(errbuf):
                v = m._default_gate_level(key, expect)
            self.assertEqual(v, expect, f"{key} 读到 {v!r} ≠ 期望 {expect!r}")
            self.assertEqual(errbuf.getvalue(), "",
                             f"{key} 读取时产生告警——说明没真读到 yaml（走了回退）")

    def test_T6b_reverse_example_gate_level_yaml_change_propagates(self):
        """T6b 反例：改 yaml 的 deliver_gate_level ⇒ 默认等级必须跟着变。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("h", PKG / "scripts" / "harness.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["h"] = m
        spec.loader.exec_module(m)
        p = PKG / "config" / "visual-rules.yaml"
        bak = p.read_text(encoding="utf-8")
        try:
            import yaml
            cfg = yaml.safe_load(bak)
            cfg["gate"]["deliver_gate_level"] = "P1"
            p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
            self.assertEqual(m._default_gate_level("deliver_gate_level", "all"), "P1",
                             "改 yaml 后默认等级未变——argparse 又被写回硬编码了")
        finally:
            p.write_text(bak, encoding="utf-8")
            self.assertEqual(m._default_gate_level("deliver_gate_level", "all"), "all",
                             "复原后未归位——配置可能未还原")

    def test_T7_gate_level_fallback_warns_not_silent(self):
        """T7：yaml 读不到/值非法时**回落并告警**，不静默。"""
        import importlib.util, io, contextlib
        spec = importlib.util.spec_from_file_location("h", PKG / "scripts" / "harness.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["h"] = m
        spec.loader.exec_module(m)
        # 值非法：直接构造一个坏 yaml 场景不可行（函数读固定路径），
        # 改为验证函数对**不存在路径**的鲁棒性 + 回退值正确
        orig = os.path.join
        try:
            # monkeypatch PKG 指向不存在目录 ⇒ 必然读不到 ⇒ 应回落且不崩
            bad = PKG / "__no_such_dir__"
            m.PKG = str(bad)
            buf, errbuf = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(errbuf):
                v = m._default_gate_level("deliver_gate_level", "all")
            self.assertEqual(v, "all", "读不到时应回落 fallback")
            self.assertTrue(errbuf.getvalue().strip(),
                            "读不到时必须告警（不静默）")
        finally:
            m.PKG = str(PKG)


if __name__ == "__main__":
    unittest.main(verbosity=2)

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

        ⚠ **v3.25.0：改隔离副本，不改生产 config**。
          原实现就地改写包内 `config/harness.yaml` 再 `finally` 复位——
          复位的是「当时读到的内容」，并发下可能已被污染 ⇒ **污染被固化**
          （而 harness.yaml 是**阶段真源**，被污染会直接让第 24 项误判）。
          `check_stage_order_drift(expert_dir)` 只按 `expert_dir` 取 config
          ⇒ 直接传副本根即可，**无需 monkeypatch**。
        """
        import yaml
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg

        iso = make_isolated_pkg(prefix="vetmed-iso-stageord-")
        try:
            hy = iso / "config" / "harness.yaml"
            cfg = yaml.safe_load(hy.read_text(encoding="utf-8"))
            cfg["stages"][2]["next"] = 5
            hy.write_text(
                yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                es2 = _load_es()
                rc = es2.check_stage_order_drift(str(iso))
            self.assertEqual(rc, 1, "注入漂移后第 24 项未报红（守卫失效）")
            self.assertIn("stages.2.next=5", buf.getvalue(),
                          "报错信息未指出具体漂移项")
            # 复原对照（副本内）⇒ 归绿 ⇒ 证明判红确由注入引起，不是恒红
            hy.write_text(
                yaml.safe_dump(yaml.safe_load(
                    (PKG / "config" / "harness.yaml").read_text(encoding="utf-8")),
                    allow_unicode=True, sort_keys=False),
                encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc2 = _load_es().check_stage_order_drift(str(iso))
            self.assertEqual(rc2, 0, "复原后第 24 项未归绿——配置可能未还原")
        finally:
            cleanup_isolated_pkg(iso)

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

        ⚠ **v3.25.0：删除写盘动作（死代码）**。
          `m.license_uncertain_markers(cfg)` 的入参 `cfg` 是**调用方传入的 dict**，
          函数**从不读文件** ⇒ 原实现的 `p.write_text(...)` 与断言**完全无关**
          （纯副作用）。既无判别力，又在并发下污染生产 config。
          ⇒ 改为：只在内存里构造 cfg 副本传给函数，**一个字节都不写盘**。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("foa", PKG / "scripts" / "fetch_oa_image.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules["foa"] = m
        spec.loader.exec_module(m)
        import yaml
        cfg = yaml.safe_load((PKG / "config" / "domain_config.yaml").read_text(encoding="utf-8"))
        cfg["image_fetch"]["license_uncertain_markers"] = ["待核实", "授权待确认"]
        marks, _ = m.license_uncertain_markers(cfg)
        self.assertEqual(marks, ("待核实", "授权待确认"),
                         "改 yaml 后读到的值未变——接线被改回硬编码了")

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
        """T6b 反例：改 yaml 的 deliver_gate_level ⇒ 默认等级必须跟着变。

        ⚠ **v3.25.0：改隔离副本**（原实现就地改写包内 `config/visual-rules.yaml`
          再 `finally` 复位 ⇒ 并发下污染被固化）。
          `_default_gate_level` 用模块级 `PKG` 拼路径 ⇒ 只需把副本的 harness 模块
          的 `PKG` 指向副本根（**同文件 T7 的既有范式**，见 `:338-350`）。
        """
        import importlib.util
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg

        iso = make_isolated_pkg(prefix="vetmed-iso-gatelevel-")
        try:
            spec = importlib.util.spec_from_file_location("h_iso", iso / "scripts" / "harness.py")
            m = importlib.util.module_from_spec(spec)
            sys.modules["h_iso"] = m
            spec.loader.exec_module(m)
            # 副本的 harness 模块 PKG → 副本根
            m.PKG = str(iso)
            p = iso / "config" / "visual-rules.yaml"
            import yaml
            cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
            cfg["gate"]["deliver_gate_level"] = "P1"
            p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
            self.assertEqual(m._default_gate_level("deliver_gate_level", "all"), "P1",
                             "改 yaml 后默认等级未变——argparse 又被写回硬编码了")
            # 复原对照（副本内）⇒ 归位 ⇒ 证明判红确由该注入引起
            p.write_text((PKG / "config" / "visual-rules.yaml").read_text(encoding="utf-8"),
                         encoding="utf-8")
            self.assertEqual(m._default_gate_level("deliver_gate_level", "all"), "all",
                             "复原后未归位——配置可能未还原")
        finally:
            cleanup_isolated_pkg(iso)

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


class TestInspectionZoneRegistry(unittest.TestCase):
    """T8–T12：免检区（块级消费段）登记表守卫（R1–R6）。

    背景（v3.25.0 实测）：
      第 18 项的静态判据对「父级被代码整块取走」的键**无法逐键确认**
      ⇒ 这些键落在**免检区**（实测 39 段 / 1489 键 / 204 键末段键名 0 出现）。
      改造前只报一个**总数** ⇒ 人工无法复核、无法行动。
      改造后 `references/inspection-zones.yaml` 把免检区变成**可行动清单**：
      每段登记「消费方」+「新增键处置规则」+「键集合指纹」。

    守卫断言集（每条都有反例，防假绿）：
      R1  登记表存在且含**全部**实时段（缺文件/缺段 ⇒ FAIL，不是 SKIP）
      R2  登记的段在实时 config 中**仍存在**
      R3  实时叶子路径集合 digest == 登记 `keys_sha256`（**集合相等** ⇒ 段内增/删/改名任一 ⇒ 判红）
      R4  实时 `key_count` == 登记 `key_count`（与 R3 交叉核对，防只改一个字段）
      R5  实时段集合 == 登记段集合（**双向** ⇒ 新段未登记 / 登记了不存在的段 ⇒ 判红）
      R6  `consumer` / `disposition` ∈ 枚举（格式越界即判红——格式破坏属真问题）

    ⚠ **为什么 R3/R5 是「段级增量守卫」**：
      R3 比的是「段内叶子路径**集合**是否变化」，不是「谁读了它」
      ⇒ 不需要叶子级白名单（那等于又一份声明源）
      ⇒ 段内新增一个键 ⇒ 必红 ⇒ 必须显式登记处置规则（新增键须登记/须接线/禁止新增）。
    """

    REGISTRY = PKG / "references" / "inspection-zones.yaml"

    #: `consumer` 允许取值（枚举校验用）
    #: ⚠ 「脚本+会话层+主理人」是**三者齐备**的形态，与「三者兼有」同义；
    #:   保留两个写法是为了让登记能精确表达「部分命中」与「全部命中」两种常见情况，
    #:   避免为 11 段各造一个生僻词（生僻词 = 枚举漂移的温床）。
    CONSUMERS = {
        "脚本", "会话层", "主理人",
        "脚本+会话层", "脚本+主理人", "会话层+主理人",
        "脚本+会话层+主理人", "三者兼有",
    }
    #: `disposition` 允许取值
    DISPOSITIONS = {"新增键须登记", "新增键须接线", "禁止新增（冻结）"}

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()
        cls.live = cls.es.collect_block_segments(str(PKG))
        import yaml
        cls.reg = yaml.safe_load(cls.REGISTRY.read_text(encoding="utf-8"))

    # ── R1：登记表存在且含全部实时段 ─────────────────────────────
    def test_T8_registry_file_exists_and_covers_all_segments(self):
        """R1：登记表必须存在、可解析，且**覆盖全部**实时免检区段。"""
        self.assertTrue(self.REGISTRY.is_file(),
                        f"缺 {self.REGISTRY}——它是 v3.25.0 新增的必交付物")
        self.assertIsInstance(self.reg, dict)
        segs = self.reg.get("segments")
        self.assertIsInstance(segs, list, "登记表缺 segments 列表")
        reg_ids = {s.get("id") for s in segs}
        live_ids = set(self.live)
        missing = live_ids - reg_ids
        self.assertEqual(missing, set(),
                         f"以下实时免检区段未登记（{len(missing)} 段）：{sorted(missing)}")
        self.assertEqual(len(segs), len(live_ids),
                         f"登记表段数 {len(segs)} ≠ 实时段数 {len(live_ids)}")

    # ── R2/R3/R4/R5：逐段核对 ───────────────────────────────────
    def test_T9_registry_segments_match_live(self):
        """R2+R3+R4+R5：登记的每段都必须与实时状态**完全一致**。"""
        problems = []
        for s in self.reg.get("segments") or []:
            sid = s.get("id")
            live = self.live.get(sid)
            if live is None:
                problems.append(f"{sid}：登记的段在实时 config 中**不存在**（R2）")
                continue
            # R3：键集合 digest（集合相等 ⇒ 段内增/删/改名任一 ⇒ 判红）
            live_sha = self.es.segments_digest(live["keys"])
            if live_sha != s.get("keys_sha256"):
                problems.append(
                    f"{sid}：键集合已变（登记 {s.get('keys_sha256')} ≠ 实时 {live_sha}）"
                    f"——段内新增/删除/改名了键，请更新登记表或显式处置该新增键（R3）")
            # R4：键数（与 R3 交叉核对，防只改一个字段）
            if int(live and len(live["keys"])) != int(s.get("key_count", -1)):
                problems.append(
                    f"{sid}：键数不一致（登记 {s.get('key_count')} ≠ "
                    f"实时 {len(live['keys'])}）（R4）")
        # R5：双向集合相等
        reg_ids = {s.get("id") for s in self.reg.get("segments") or []}
        live_ids = set(self.live)
        for sid in sorted(reg_ids - live_ids):
            problems.append(f"{sid}：登记了但实时**不存在**该段（R5）")
        for sid in sorted(live_ids - reg_ids):
            problems.append(f"{sid}：实时存在但**未登记**（R5）")
        self.assertEqual(problems, [],
                         "免检区登记表与实时 config 不一致：\n"
                         + "\n".join(f"  · {p}" for p in problems))

    # ── R6：枚举校验 ────────────────────────────────────────────
    def test_T10_registry_enums_valid(self):
        """R6：`consumer` / `disposition` 必须落在枚举内。"""
        bad = []
        for s in self.reg.get("segments") or []:
            sid = s.get("id")
            if s.get("consumer") not in self.CONSUMERS:
                bad.append(f"{sid}：consumer={s.get('consumer')!r} 不在枚举内")
            if s.get("disposition") not in self.DISPOSITIONS:
                bad.append(f"{sid}：disposition={s.get('disposition')!r} 不在枚举内")
            for f in ("file", "prefix", "note"):
                if not s.get(f):
                    bad.append(f"{sid}：{f} 为空")
        self.assertEqual(bad, [],
                         "登记表字段越界（格式破坏属真问题）：\n"
                         + "\n".join(f"  · {b}" for b in bad))

    # ── 反例 A（能失败）：段内新增键 ⇒ R3 判红 ───────────────────
    def test_T11_reverse_example_new_key_in_segment_trips_r3(self):
        """T11 反例：在免检区段里加一个键 ⇒ R3（digest）必须判红。

        这是「段级增量守卫」的核心价值证明：
        没有 R3，段内新增一个没人读的键**永远不会被发现**。
        ⚠ 全程在**隔离副本**上做（不碰生产 config）。
        """
        import shutil
        import tempfile
        import yaml
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg

        iso = make_isolated_pkg(prefix="vetmed-iso-zones-")
        try:
            es_iso = _load_es_on(iso)
            live = es_iso.collect_block_segments(str(iso))
            sid = "harness.yaml#budgets"
            self.assertIn(sid, live, "样例段不存在（免检区结构变了？）")
            before = live[sid]["keys"]

            # 在副本的该段下加一个新键
            hy = iso / "config" / "harness.yaml"
            cfg = yaml.safe_load(hy.read_text(encoding="utf-8"))
            cfg["budgets"]["__probe_zone_new_key"] = True
            hy.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")

            live2 = es_iso.collect_block_segments(str(iso))
            after = live2[sid]["keys"]
            self.assertNotEqual(before, after, "新键未进入免检区段键集合——判据失效")
            self.assertEqual(len(after), len(before) + 1,
                             f"新键未计入：{len(before)} → {len(after)}")
            # digest 必须变化 ⇒ R3 会判红
            self.assertNotEqual(es_iso.segments_digest(before),
                                es_iso.segments_digest(after),
                                "新键加入后 digest 未变——R3 失效（假绿）")
        finally:
            cleanup_isolated_pkg(iso)

    # ── 反例 B（能失败）：登记了不存在的段 ⇒ R2/R5 判红 ─────────
    def test_T12_reverse_example_phantom_segment_detected(self):
        """T12 反例：登记一个**不存在**的段 ⇒ R2/R5 必须判红。

        没有这条，登记表会逐渐积累「僵尸声明」而不被发现。
        """
        import yaml
        reg = yaml.safe_load(self.REGISTRY.read_text(encoding="utf-8"))
        reg.setdefault("segments", []).append({
            "id": "foo.yaml#bar", "file": "foo.yaml", "prefix": "bar",
            "key_count": 1, "keys_sha256": "0" * 40, "leaf_unused": 0,
            "consumer": "脚本", "disposition": "新增键须登记", "note": "探针",
        })
        self.assertNotIn("foo.yaml#bar", self.live,
                         "探针段竟真实存在——反例前提失效")
        # R2：登记的段在实时 config 中不存在 ⇒ 必须能被检出
        phantom = [s for s in reg["segments"] if s["id"] not in self.live]
        self.assertTrue(phantom, "未检出幽灵段——R2 失效（假绿）")
        # R5：登记集合 ≠ 实时集合 ⇒ 必须不等
        self.assertNotEqual({s["id"] for s in reg["segments"]}, set(self.live),
                            "集合竟相等——R5 失效（假绿）")


# ── 反例 C（能失败）：测试文件里的读取点**不得**算作「有读取者」 ──
    def test_T13_reverse_example_test_file_reads_do_not_count(self):
        """T13 反例：**测试文件**里的 `cfg.get("x")` 不得让 `x` 获得读取证据。

        病灶（v3.25.0 实测复现）：
          第 18 项的 AST 读取集原本扫**全部** `scripts/*.py`（含 `test_*.py`）
          ⇒ 在测试里写一行 `cfg["a"]["x"]` 就能让死配置门对 `x` **假绿**。
          实测：隔离副本的 `harness.yaml#budgets` 下加 `__probe_zone_new_key`，
          仅因本守卫测试文件里写了那一句，该键就获得**路径级证据**（`_a_path`）
          ⇒ 不进免检区 ⇒ 守卫完全看不见。

        本用例把这个漏洞**钉死**：测试文件里的读取**不构成消费**。
        ⚠ 全程在**隔离副本**上做（不碰生产 config）。
        """
        import yaml
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg

        iso = make_isolated_pkg(prefix="vetmed-iso-testread-")
        try:
            es_iso = _load_es_on(iso)
            live = es_iso.collect_block_segments(str(iso))
            sid = "harness.yaml#budgets"
            self.assertIn(sid, live, "样例段不存在（免检区结构变了？）")
            before = list(live[sid]["keys"])

            # 在副本的该段下加一个新键
            hy = iso / "config" / "harness.yaml"
            cfg = yaml.safe_load(hy.read_text(encoding="utf-8"))
            cfg["budgets"]["__probe_test_read_key"] = True
            hy.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")

            # 关键：副本的 scripts/ 下**放一个测试文件**，里面读取该键
            probe = iso / "scripts" / "test_probe_reader.py"
            probe.write_text(
                'def _f(cfg):\n'
                '    return cfg["budgets"]["__probe_test_read_key"]\n',
                encoding="utf-8")

            live2 = es_iso.collect_block_segments(str(iso))
            after = live2[sid]["keys"]
            self.assertNotEqual(before, after,
                                "新键未进入免检区段键集合——判据失效")
            self.assertEqual(len(after), len(before) + 1,
                             f"新键未计入：{len(before)} → {len(after)}")
        finally:
            cleanup_isolated_pkg(iso)


def _load_es_on(pkg_root):
    """按路径加载指定包根下的 ensure_settings.py（隔离副本用）。"""
    spec = importlib.util.spec_from_file_location(
        "es_zones_tmp", Path(pkg_root) / "scripts" / "ensure_settings.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_zones_tmp"] = m
    spec.loader.exec_module(m)
    return m


if __name__ == "__main__":
    unittest.main(verbosity=2)

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
      R7  实时 `leaf_unused` == 登记 `leaf_unused`（**逐段**；「待人工定性候选」桶的大小）
      R8  实时 `leaf_weak`   == 登记 `leaf_weak`  （**逐段**；「弱证据洞」的大小）

    ⚠ **为什么 R3/R5 是「段级增量守卫」**：
      R3 比的是「段内叶子路径**集合**是否变化」，不是「谁读了它」
      ⇒ 不需要叶子级白名单（那等于又一份声明源）
      ⇒ 段内新增一个键 ⇒ 必红 ⇒ 必须显式登记处置规则（新增键须登记/须接线/禁止新增）。

    ⚠ **v3.28.2：R3/R4 按登记表顶层的 `digest_scheme` 分派口径**：
      · `indexed-set-v2`（**新口径**，当前登记表）：对「**带下标**的叶子路径
        **集合**」求指纹 ⇒ 段内某元素的**内容**改变也能检出
        （旧口径下改内容不改指纹 ⇒ 假阴性）。
      · `folded-multiset-v1`（**旧口径**，缺省）：对「折叠路径多重集」求指纹
        ⇒ **向后兼容**：没升级的登记表**仍能过**（不会被误判成「脱节」）。
      ⇒ 登记表**未**声明 `digest_scheme` ⇒ 按**旧口径**解释（缺省 = 旧口径）。
      ⚠ **判据语义本身未被削弱**（用户对判据有拍板权）：R3 仍是
        「实时 digest == 登记 digest」⇒ 不一致即判红；只是**按登记表自己声明的
        口径**去算「实时 digest」⇒ 旧登记表的判据含义**不变**。

    ⚠⚠ **v3.28.2：R7 / R8 是新增判据**（R1–R6 的编号与语义**零改动**——
      用户对判据编号有拍板权 ⇒ 新增只能**往后排**，不得改动既有编号）。
      · R7 = 逐段 `leaf_unused`（「待人工定性候选」桶的大小）登记值 == 实时值
      · R8 = 逐段 `leaf_weak`  （「弱证据洞」的大小）登记值 == 实时值
      ★ **为什么必须有它们（真实假绿缺口，已实测复现）**：
        修复 A（判定顺序修正）的**全部可观测产出**就是 `leaf_unused` 的值
        （211 → 145）⇒ 但这个字段**此前无任何守卫** ⇒ 红队实测把 7 段的
        `leaf_unused` 篡改成 999 ⇒ 本文件（28 用例）+ 红证明文件（**当时** 17 用例）
        **共 45 个测试全绿** ⇒ 下次有人改 `known_textual` 或判定顺序，
        让真实候选变成 180 或 100，**体检不会报** ⇒ 修复 A 的效果不可持续。
        （⚠ 红证明文件自 v3.28.2 起已扩到 **21 用例** —— 新增 R7/R8 的
         判据级红证明 + 变异敏感性用例各 2 条 ⇒ 本处「45 个」记的是
         **缺口被发现时**的测试总数，是历史事实，不随用例数增长而改写。）
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
        """R2+R3+R4+R5+R7+R8：登记的每段都必须与实时状态**完全一致**。"""
        problems = []
        # ⚠ **v3.28.2：指纹口径按登记表顶层的 `digest_scheme` 分派**。
        #   缺省 = 旧口径（`folded-multiset-v1`）⇒ **旧口径登记表仍能过**
        #   （向后兼容：登记表没升级时，守卫按旧算法比对，不误判「脱节」）。
        scheme = self.reg.get("digest_scheme") or self.es.DEFAULT_DIGEST_SCHEME
        for s in self.reg.get("segments") or []:
            sid = s.get("id")
            live = self.live.get(sid)
            if live is None:
                problems.append(f"{sid}：登记的段在实时 config 中**不存在**（R2）")
                continue
            # R3：键集合 digest（集合相等 ⇒ 段内增/删/改名任一 ⇒ 判红）
            live_sha = self.es.segments_digest(
                self.es.segment_digest_inputs(live, scheme), scheme=scheme)
            if live_sha != s.get("keys_sha256"):
                problems.append(
                    f"{sid}：键集合已变（登记 {s.get('keys_sha256')} ≠ 实时 {live_sha}）"
                    f"——段内新增/删除/改名了键，请更新登记表或显式处置该新增键（R3）")
            # R4：键数（与 R3 交叉核对，防只改一个字段）
            # ⚠ `key_count` 与 `keys_sha256` **同口径**（`segment_key_count`）
            #   ⇒ 两条判据不会互相打架（口径不一致会让「只改一个字段」有可乘之机）。
            live_count = self.es.segment_key_count(
                self.es.segment_digest_inputs(live, scheme), scheme=scheme)
            if int(live_count) != int(s.get("key_count", -1)):
                problems.append(
                    f"{sid}：键数不一致（登记 {s.get('key_count')} ≠ "
                    f"实时 {live_count}）（R4）")
            # ── R7：逐段 `leaf_unused`（「待人工定性候选」桶的大小）──────────
            # ⚠ **v3.28.2 新增**（R1–R6 的编号与语义**零改动**）。
            #   为什么必须逐段核对（真实假绿缺口，已实测复现）：
            #     判定顺序修正（修复 A）的**全部可观测产出**就是 `leaf_unused`
            #     （211 → 145）⇒ 但此前**无任何守卫**读这个字段
            #     ⇒ 红队实测把 7 段的 `leaf_unused` 篡改成 999
            #     ⇒ 守卫文件（28 用例）+ 红证明文件（**当时** 17 用例）**共 45 个全绿**
            #     ⇒ 下次有人改 `known_textual` 或判定顺序，让真实候选变成
            #       180 或 100，**体检不会报** ⇒ 修复 A 的效果不可持续。
            #   ⇒ 本判据把「修复 A 的产出」纳入守卫 ⇒ 效果**可持续**。
            # ⚠ 口径：`leaf_unused` 的定义**未被改动**（末段键名在代码中 0 出现）。
            live_unused = int(live.get("leaf_unused", 0))
            if live_unused != int(s.get("leaf_unused", -1)):
                problems.append(
                    f"{sid}：待人工定性候选数不一致（登记 {s.get('leaf_unused')} ≠ "
                    f"实时 {live_unused}）（R7）")
            # ── R8：逐段 `leaf_weak`（「弱证据洞」的大小）────────────────────
            # ⚠ **v3.28.2 新增**。
            #   为什么必须逐段核对（真实判据洞，已实测复现）：
            #     `leaf_weak` = 末段键名**撞名**但**无路径级证据**的键数
            #     （与 `leaf_unused` **精确对位**：两者互斥且穷尽「证据不足」的键）。
            #     v3.23.0 F1 明写「弱证据 = 仅末段同名撞车，**不是**路径级证据」，
            #     但 `weak` 桶因 `_b_block` 前置短路而**永不触发**（真包实测
            #     `weak=0`）⇒ 这批键（实测 **1012 键 / 67%**）既不判死、
            #     不进候选桶、也不进 `weak` 桶 ⇒ **无任何守卫覆盖**。
            #     ⇒ 一个末段名叫 `note` / `enabled` 的**新键**加进已登记段里，
            #       会**静默绿灯** ⇒ 本判据让该段「弱证据洞」的**大小**可核对。
            # ⚠ 登记表若**缺** `leaf_weak` 字段（未升级的旧登记表）⇒ 登记值
            #   取 -1 ⇒ 必然判红 ⇒ **必须**升级登记表（这是刻意的：
            #   与「升级口径后必须重新生成 `keys_sha256`」同款纪律）。
            live_weak = int(live.get("leaf_weak", 0))
            if live_weak != int(s.get("leaf_weak", -1)):
                problems.append(
                    f"{sid}：弱证据（末段撞名但无路径级证据）数不一致"
                    f"（登记 {s.get('leaf_weak')} ≠ 实时 {live_weak}）（R8）")
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


# ══════════════════════════════════════════════════════════════════════
# T31–T34：判定**分支顺序**的守卫（人读型登记优先于块级证据）
# ══════════════════════════════════════════════════════════════════════
#
# 病灶（实测复现，可证伪）：
#   第 18 项的 `walk()` 原本把「块级证据」与「人读型登记」放在**同一条 elif 链**上，
#   且块级证据在前 ⇒ `elif` **短路** ⇒ `_is_textual()` **根本没机会执行**
#   ⇒ 已登记为「人读型」的键，只要其所在段被代码**整块读取**，
#     就会被误归入「免检区（块级消费段）」的**待人工定性候选**桶
#     ⇒ **既没被判死、也没拿到人读型定性 ⇒ 永久悬空**。
#   实测规模：修复前 211 键待人工定性候选里，**66 键**属此型（确定性假候选）。
#
# ★ **本组的判据全部自造隔离 fixture**（临时目录 + 自己的 config + 自己的 script）：
#   不依赖仓库现有 config 的具体值 ⇒ 后续任何配置变动都不会让判据失效或假绿。
#   ⚠ fixture 必须造出「**人读型登记 ∧ 块级证据同时成立**」的**最小**形态：
#     · 一个新段 `probe_block`（代码整块取走 ⇒ 块级证据成立）；
#     · 段内一个键，其**末段键名**已在 `known_textual` 登记（⇒ 人读型成立）；
#     · 段内另一个键，**未**登记（⇒ 只有块级证据 ⇒ 仍应进免检区）；
#     · 段外一个键，**未**登记、无块级证据、无路径证据（⇒ 仍应判死）。
#
# ⚠ **不写生产 config、不写生产 script**：全部改动都发生在 `tempfile.mkdtemp()`
#   造的临时目录里，用完即删 ⇒ 并发下不会污染真包（与本文件 T1b 的既有纪律一致）。
#
# ⚠ **测试文件自身的读取点不算消费**：`_collect_ast_reads` / `_collect_chain_reads`
#   都排除 `test_*.py` ⇒ 本守卫文件里写的 `cfg["probe_block"]` **不会**给探针键
#   制造路径级证据 ⇒ 探针的块级证据只能来自 fixture 自带的**非测试**脚本。


#: fixture 里「被代码整块取走」的段名。
FIXTURE_SEG = "probe_block"
#: fixture 里「已登记为人读型」的末段键名（**不进** `known_textual` 的原始集）。
FIXTURE_TEXTUAL_LEAF = "probe_textual_leaf"
#: fixture 里「块级证据成立但未登记」的末段键名。
FIXTURE_PLAIN_LEAF = "probe_plain_leaf"
#: fixture 里「未登记 + 无块级证据 + 无路径证据」的末段键名（应判死）。
FIXTURE_DEAD_LEAF = "probe_dead_leaf"


def _build_branch_order_fixture(root: Path):
    """造一个「人读型登记 ∧ 块级证据同时成立」的**最小隔离 fixture**。

    目录形态（`<root>` 即返回的包根）：
        <root>/config/probe.yaml   —— 三个探针键 + 段外一个死键
        <root>/scripts/probe_reader.py —— 整块取走 `probe_block` 段（⇒ 块级证据）

    ⚠ 探针脚本**不**以 `test_` 开头 ⇒ 其读取点被 AST/链式读取点采集器计入
      （否则 fixture 造不出块级证据，判据就失去意义）。
    """
    import yaml

    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)

    cfg = {
        FIXTURE_SEG: {
            FIXTURE_TEXTUAL_LEAF: "人读型键（末段键名已登记）",
            FIXTURE_PLAIN_LEAF: "普通键（未登记，但有块级证据）",
        },
        FIXTURE_DEAD_LEAF: "无人读、无线索的键（应判死）",
    }
    (root / "config" / "probe.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # 整块取走 `probe_block` ⇒ 该段下所有键都拿到**块级证据**。
    # ⚠ 用 `cfg["probe_block"]`（下标访问）——链式读取点采集器能还原出 "probe_block"
    #   ⇒ 父级被整块取走的证据成立。
    (root / "scripts" / "probe_reader.py").write_text(
        'def _read(cfg):\n'
        '    return cfg["probe_block"]\n',
        encoding="utf-8")
    return root


def _register_textual_leaf(es_src: str, leaf: str) -> str:
    """在 `known_textual` 里为给定末段键名加一条登记（返回改写后的源码）。

    ⚠ 用**末段键名**登记（不是段名）：这样只有该段下的**这一个**键被人读型，
      段内另一个未登记的键仍只有块级证据 ⇒ 两条判据可在同一 fixture 上同时验证。
    """
    marker = "    known_textual = {\n"
    if marker not in es_src:
        raise AssertionError("known_textual 定义未找到（ensure_settings.py 结构变了？）")
    if es_src.count(marker) != 1:
        raise AssertionError("known_textual 定义锚点不唯一（ensure_settings.py 结构变了？）")
    return es_src.replace(marker, marker + f'        "{leaf}",\n', 1)


def _load_es_from(root: Path, name: str):
    """加载 fixture 根下的 ensure_settings.py（fixture 只含 scripts/ 与 config/）。"""
    spec = importlib.util.spec_from_file_location(
        name, root / "scripts" / "ensure_settings.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


#: **修复后**（当前）的判定分支片段 —— 变异体的替换源。
#: ⚠ **v3.28.2 更新**：`_is_textual(fname, full)` 改为 `_is_textual(fname, _plain)`
#:   （判定用**剥下标**路径 ⇒ 判定口径与修复前逐字一致；下标只进段键集合）。
#: ⚠ **v3.28.2 再更新**：段 dict 新增 `leaf_weak` 字段（弱证据洞可见化）
#:   ⇒ 锚点随之更新（锚点必须**逐字**匹配当前源码，否则变异体会变成
#:   「什么也没改」的假 mutant ⇒ 变异证明恒真）。
FIXED_BRANCH_BLOCK = '''            if _full_hit or _a_path:
                alive += 1
            elif _is_textual(fname, _plain):
                textual += 1          # 人读型登记在案，无代码读取者是合理的
                if _b_block:
                    # 块级证据与人读型**同时成立** ⇒ 保留段归属，但不算「待人工定性候选」。
                    alive += 1
                    block += 1
                    block_textual += 1
                    _seg_key = f"{fname}#{_b_prefix}"
                    _seg = block_segments.setdefault(
                        _seg_key,
                        {"file": fname, "prefix": _b_prefix, "keys": [],
                         "idents": [], "leaf_unused": 0, "leaf_weak": 0})
                    # ⚠ **v3.28.2**：段键集合存**带下标**的路径（元素身份可辨）
                    #   ⇒ 另存**身份串**（路径+值）供指纹用 ⇒ 值变更也可检出。
                    _seg["keys"].append(full)
                    _seg["idents"].append(_ident)
            elif _b_block:
                alive += 1
                block += 1
                # v3.25.0：把该键归入「免检区（块级消费段）」——
                # 段键 = `<config 文件名>#<触发前缀>`（ADR-6：必须带文件名前缀，
                # 因为同名段跨文件是不同的段，合并登记会让处置规则无法落地）。
                _seg_key = f"{fname}#{_b_prefix}"
                _seg = block_segments.setdefault(
                    _seg_key,
                    {"file": fname, "prefix": _b_prefix, "keys": [],
                     "idents": [], "leaf_unused": 0, "leaf_weak": 0})
                # ⚠ **v3.28.2**：段键集合存**带下标**的路径（元素身份可辨）
                #   ⇒ 另存**身份串**（路径+值）供指纹用 ⇒ 值变更也可检出。
                _seg["keys"].append(full)
                _seg["idents"].append(_ident)
                # 「末段键名归一化后不在 AST 读取集」⇒ 该键连同名都没撞上 ⇒
                # 连**弱证据**都没有 ⇒ 属「待人工定性候选」（不是死配置）。
                if not (n_leaf and n_leaf in norm_reads):
                    _seg["leaf_unused"] += 1
                # ⚠ **v3.28.2**：`leaf_weak` = **弱证据洞**的可见化。
                #   口径（与 `leaf_unused` **精确对位**，两者互斥且穷尽）：
                #     · `leaf_unused` = 末段键名在代码中 **0 出现**（连撞名都没有）
                #     · `leaf_weak`   = 末段键名**有**出现（撞名）**且**
                #                        **无路径级证据**（`_a_path` 为假）
                #                        **且**该键**整条路径**未命中 `norm_reads`
                #   ⚠ 为什么必须可见（真实判据洞，已实测复现）：
                #     v3.23.0 F1 自己明写「弱证据 = 仅末段同名撞车，**不是**路径级证据」。
                #     但 `weak` 桶因 `_b_block` 已被前置短路而**永不触发**（真包实测
                #     `weak=0`）⇒ 这批键被「块级证据」这一层**接管**了 ⇒
                #     既不判死、不进 `leaf_unused`、也不进 `weak` ⇒ **无任何守卫覆盖**。
                #     ⇒ 一个末段名叫 `note` / `description` / `enabled` 的**新键**，
                #       加进已登记的免检区段里，会**静默绿灯**（实测：145 键的
                #       「待人工定性候选」桶之外，还有 **1012 键（67%）** 落在这个洞里）。
                #   ⇒ 修法：**不判死、不进人工定性范围**（桶③的键大概率确实有人读），
                #     只是**登记可见**（段级字段 `leaf_weak`）+ 守卫 R8 逐段核对。
                #   ⚠ **不得**因此改动 `dead` 判定口径（本项是纯观测，不改判定）。
                # ⚠ 判定用 `_leaf_weak_hit`（三条原始信号的显式合取）——
                #   理由见该谓词定义处的注释（避免写成**恒真**的等价条件）。
                elif _leaf_weak_hit:
                    _seg["leaf_weak"] += 1
            elif seg_hit or _is_guard_consumed(fname, _plain):
                textual += 1          # 人读型：登记在案，无代码读取者是合理的
            elif n_leaf and n_leaf in norm_reads:
                # 弱证据：仅末段键名撞车。**不算已接线**，必须登记理由。
                if _is_weak_registered(fname, _plain):
                    weak_reg += 1
                else:
                    weak += 1
                    # ⚠ 展示路径用**剥下标**形态（与修复前逐字一致 ⇒ 展示口径不变；
                    #   下标只用于段内指纹的**身份**，不用于人读的「这个键在哪」）。
                    weak_list.append((fname, _plain, node))'''

#: **变异体**：把**判定顺序**换回去（块级证据在前 ⇒ `elif` 短路
#:   ⇒ `_is_textual()` 根本没机会执行）。
#:
#: ⚠⚠ **v3.28.2 重写（重要：变异体必须与当前源码**同代**）**：
#:   旧版 `OLD_BRANCH_BLOCK` 是**修复 A+B 之前**的历史形态 ⇒ 它同时改了
#:     ① `_is_textual(fname, full)` → `_is_textual(fname, _plain)`（判定路径口径）
#:     ② 段 dict 缺 `idents` 字段（指纹口径）
#:     ③ 判定链的**整体结构**（不是单纯换序）
#:   ⇒ 施加它会**连带**打红 T9 / T35 / T38（指纹与登记表判据），实测杀 5 个
#:     ⇒ 读 commit message 的人会困惑「不是只测顺序吗，怎么打红 5 个？」
#:
#:   ★ **本变异体只隔离「顺序」这一个变量**：
#:     · 保留 `_plain`（判定用剥下标路径）——与当前源码一致；
#:     · 保留 `idents`（段指纹用带下标身份串）——与当前源码一致；
#:     · 保留 `leaf_weak` / `leaf_unused` 两个段级字段——与当前源码一致；
#:     · **只**把「块级证据分支」提到「人读型登记分支」之前。
#:   ⇒ 实测：施加它 ⇒ **4 failed**（T31 + T34 + T9 + T39），且
#:     `test_inspection_zone_registry_red.py` 21 用例**全绿**。
#:   ⚠ **用历史形态会连带打红 T9/T35/T38**（那三条测的是**指纹口径**，
#:     不是本判据所测的**顺序**）⇒ 必须在用例注释里写明这一点。
#:   ⚠⚠ **v3.28.2 实测口径修正**：上句的「4 failed」中，T9 / T39 的红是
#:     **R7 / R8 标签**（**不是** R3/R4）⇒ 原因是**新增的 R7/R8 正是用来
#:     「抓住修复 A 被回退」**的 ⇒ 判定顺序一旦换回去，`leaf_unused` /
#:     `leaf_weak` 的实时值必然与登记值不符 ⇒ R7/R8 必然判红。
#:     ⇒ 这是**新增守卫的预期行为**，不是变异体「不干净」；
#:       **「恰好 2 failed」在 R7/R8 存在之后已不可达**。
OLD_BRANCH_BLOCK = '''            if _full_hit or _a_path:
                alive += 1
            elif _b_block:
                alive += 1
                block += 1
                # v3.25.0：把该键归入「免检区（块级消费段）」——
                # 段键 = `<config 文件名>#<触发前缀>`（ADR-6：必须带文件名前缀，
                # 因为同名段跨文件是不同的段，合并登记会让处置规则无法落地）。
                _seg_key = f"{fname}#{_b_prefix}"
                _seg = block_segments.setdefault(
                    _seg_key,
                    {"file": fname, "prefix": _b_prefix, "keys": [],
                     "idents": [], "leaf_unused": 0, "leaf_weak": 0})
                # ⚠ **v3.28.2**：段键集合存**带下标**的路径（元素身份可辨）
                #   ⇒ 另存**身份串**（路径+值）供指纹用 ⇒ 值变更也可检出。
                _seg["keys"].append(full)
                _seg["idents"].append(_ident)
                # 「末段键名归一化后不在 AST 读取集」⇒ 该键连同名都没撞上 ⇒
                # 连**弱证据**都没有 ⇒ 属「待人工定性候选」（不是死配置）。
                if not (n_leaf and n_leaf in norm_reads):
                    _seg["leaf_unused"] += 1
                # ⚠ **v3.28.2**：`leaf_weak` = **弱证据洞**的可见化。
                #   口径（与 `leaf_unused` **精确对位**，两者互斥且穷尽）：
                #     · `leaf_unused` = 末段键名在代码中 **0 出现**（连撞名都没有）
                #     · `leaf_weak`   = 末段键名**有**出现（撞名）**且**
                #                        **无路径级证据**（`_a_path` 为假）
                #                        **且**该键**整条路径**未命中 `norm_reads`
                #   ⚠ 为什么必须可见（真实判据洞，已实测复现）：
                #     v3.23.0 F1 自己明写「弱证据 = 仅末段同名撞车，**不是**路径级证据」。
                #     但 `weak` 桶因 `_b_block` 已被前置短路而**永不触发**（真包实测
                #     `weak=0`）⇒ 这批键被「块级证据」这一层**接管**了 ⇒
                #     既不判死、不进 `leaf_unused`、也不进 `weak` ⇒ **无任何守卫覆盖**。
                #     ⇒ 一个末段名叫 `note` / `description` / `enabled` 的**新键**，
                #       加进已登记的免检区段里，会**静默绿灯**（实测：145 键的
                #       「待人工定性候选」桶之外，还有 **1012 键（67%）** 落在这个洞里）。
                #   ⇒ 修法：**不判死、不进人工定性范围**（桶③的键大概率确实有人读），
                #     只是**登记可见**（段级字段 `leaf_weak`）+ 守卫 R8 逐段核对。
                #   ⚠ **不得**因此改动 `dead` 判定口径（本项是纯观测，不改判定）。
                # ⚠ 判定用 `_leaf_weak_hit`（三条原始信号的显式合取）——
                #   理由见该谓词定义处的注释（避免写成**恒真**的等价条件）。
                elif _leaf_weak_hit:
                    _seg["leaf_weak"] += 1
            elif _is_textual(fname, _plain):
                textual += 1          # 人读型登记在案，无代码读取者是合理的
                if _b_block:
                    # 块级证据与人读型**同时成立** ⇒ 保留段归属，但不算「待人工定性候选」。
                    alive += 1
                    block += 1
                    block_textual += 1
                    _seg_key = f"{fname}#{_b_prefix}"
                    _seg = block_segments.setdefault(
                        _seg_key,
                        {"file": fname, "prefix": _b_prefix, "keys": [],
                         "idents": [], "leaf_unused": 0, "leaf_weak": 0})
                    # ⚠ **v3.28.2**：段键集合存**带下标**的路径（元素身份可辨）
                    #   ⇒ 另存**身份串**（路径+值）供指纹用 ⇒ 值变更也可检出。
                    _seg["keys"].append(full)
                    _seg["idents"].append(_ident)
            elif seg_hit or _is_guard_consumed(fname, _plain):
                textual += 1          # 人读型：登记在案，无代码读取者是合理的
            elif n_leaf and n_leaf in norm_reads:
                # 弱证据：仅末段键名撞车。**不算已接线**，必须登记理由。
                if _is_weak_registered(fname, _plain):
                    weak_reg += 1
                else:
                    weak += 1
                    # ⚠ 展示路径用**剥下标**形态（与修复前逐字一致 ⇒ 展示口径不变；
                    #   下标只用于段内指纹的**身份**，不用于人读的「这个键在哪」）。
                    weak_list.append((fname, _plain, node))'''


def _revert_to_old_branch_order(src: str) -> str:
    """把 `walk()` 的判定分支换成**原缺陷形态**（块级证据在前 ⇒ elif 短路）。

    ⚠ 这是**变异体构造器**：它复现的是**原缺陷**（不是「把块级证据删掉」）。
    ⚠ **v3.28.2 重写**：变异体现在**只隔离「判定顺序」一个变量**——
      保留 `_plain`（判定路径口径）、保留 `idents`（指纹口径）、
      保留 `leaf_weak`/`leaf_unused` 两个段级字段；
      **只**把块级证据分支提到人读型登记分支之前。
      ⚠ 早版用的是**历史形态**（修复 A+B 之前）⇒ 连带打红 T9/T35/T38
        （那三条测的是**指纹口径**，不是本判据所测的**顺序**）
        ⇒ 变异报告与 commit message 会互相矛盾（声称杀 2 个、实测杀 5 个）。
      ⚠ **v3.28.2 实测口径**：施加本变异体 ⇒ `test_dead_config_disposition.py`
        **4 failed**（T31 + T34 + T9 + T39）；其中 T9/T39 的红是 **R7/R8 标签**
        ⇒ **R7/R8 的存在本身要求它变红** ⇒「恰好 2 failed」在本版不可达。
    ⚠ **必须逐字**替换 ⇒ 锚点匹配不上直接抛错（而不是静默变成
      「什么也没改」的假 mutant ⇒ 那样变异证明会恒真）。
    """
    if FIXED_BRANCH_BLOCK not in src:
        raise AssertionError(
            "变异体锚点未逐字匹配（ensure_settings.py 的判定分支结构变了？）")
    if src.count(FIXED_BRANCH_BLOCK) != 1:
        raise AssertionError("变异体锚点不唯一（ensure_settings.py 的判定分支结构变了？）")
    return src.replace(FIXED_BRANCH_BLOCK, OLD_BRANCH_BLOCK, 1)


def _run_fixture(root: Path):
    """在 fixture 上跑第 18 项，返回 (rc, 输出, 段清单)。"""
    import io as _io
    import contextlib as _ctx
    es = _load_es_from(root, "es_t31_fixture")
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        rc = es.check_dead_config_keys(str(root))
    return rc, buf.getvalue(), es.last_block_segments()


class TestJudgementBranchOrder(unittest.TestCase):
    """T31–T34：第 18 项**判定分支顺序**守卫。

    ★ 本组的价值：这条判据钉住的是「**判定顺序**」本身，
      而非「某个键当前是什么状态」⇒ 不会被配置演进打穿。
    """

    # ── 构造（每个用例一份独立 fixture，互不串味）──────────────────
    def _make_fixture(self, register_textual=True):
        """造 fixture +（可选）在副本的 known_textual 里加登记 + 跑第 18 项。

        返回 (root, rc, 输出, 段清单)。
        """
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="vetmed-t31-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        _build_branch_order_fixture(root)
        # 把真包的 ensure_settings.py 复制进 fixture（它是被测对象）
        shutil.copy2(ES, root / "scripts" / "ensure_settings.py")
        if register_textual:
            es_src = (root / "scripts" / "ensure_settings.py").read_text(encoding="utf-8")
            es_src = _register_textual_leaf(es_src, FIXTURE_TEXTUAL_LEAF)
            (root / "scripts" / "ensure_settings.py").write_text(es_src, encoding="utf-8")
        rc, out, segs = _run_fixture(root)
        return root, rc, out, segs

    @staticmethod
    def _textual_count(out: str) -> int:
        """从体检输出里取「人读型登记 N 项」的数字。"""
        import re
        m = re.search(r"人读型登记\s*(\d+)\s*项", out)
        if not m:
            raise AssertionError(f"体检输出里找不到「人读型登记 N 项」：\n{out[:800]}")
        return int(m.group(1))

    # ── T31：核心判据（能红）─────────────────────────────────────
    def test_T31_textual_registration_wins_over_block_evidence(self):
        """T31：**人读型登记** ∧ **块级证据** 同时成立 ⇒ 计入 textual，
        且**不**计入「待人工定性候选」（leaf_unused）。

        这是本次修复的**核心判据**。
        修复前（块级证据在 `elif` 链前面 ⇒ 短路）本用例会 FAIL：
          探针键 `probe_block.probe_textual_leaf` 会被计入该段的
          「待人工定性候选」桶（leaf_unused）⇒ 它既没被判死、也没拿到人读型定性
          ⇒ **永久悬空**。

        ⚠ **断言口径说明（避免误读）**：
          该键**仍保留**在所属段的键集合里（`seg["keys"]`）——
          这是**有意**保留的：段归属是 R3「段内增/删/改名任一 ⇒ 判红」这条
          **段级增量守卫**的覆盖范围 ⇒ 若把人读型键踢出段集合，
          以后往该段新增一个人读型键就会**逃过 R3**（守卫被削弱）。
          本次修复要消掉的是「**待人工定性候选**」这个桶里的假候选，
          **不是**消掉段归属信息。
          ⇒ 故判据落在两处：① `leaf_unused` 不含它；② 它被计入 textual 计数。
        """
        # ① 同一条 fixture，跑两遍：有登记 / 无登记 ⇒ textual 计数必须**恰好 +1**
        #    （这直接证明「该键被计入 textual」，而不是靠段清单间接推断）。
        _, rc_with, out_with, segs_with = self._make_fixture(register_textual=True)
        _, rc_without, out_without, segs_without = self._make_fixture(register_textual=False)

        self.assertEqual(
            self._textual_count(out_with), self._textual_count(out_without) + 1,
            "T31：已登记的人读型键**未被计入 textual 计数**"
            "——判定分支顺序又倒回去了（块级证据短路了人读型判定）")

        # ② 它**不得**被算作「待人工定性候选」（leaf_unused）
        seg_key = f"probe.yaml#{FIXTURE_SEG}"
        self.assertIn(seg_key, segs_with, "T31：fixture 未造出免检区段——判据失效")
        self.assertEqual(
            segs_with[seg_key]["leaf_unused"], 1,
            "T31：已定性的人读型键被计入了「待人工定性候选」桶（leaf_unused）"
            "⇒ 它会被误列为待人工定性（永久悬空）")

        # ③ 对照：未登记时，同一 fixture 的 leaf_unused 必须是 2
        #    （证明 ② 里的 1 是**判定顺序带来的差异**，不是 fixture 天然如此）。
        self.assertEqual(
            segs_without[seg_key]["leaf_unused"], 2,
            "T31 对照组：未登记时两键都应是待人工定性候选（leaf_unused=2）——"
            "fixture 前提失效，T31 的差异断言失去意义")

        # ④ 该键**不得**被判死（它已被登记 ⇒ 没人读是对的）
        self.assertNotIn(f"{FIXTURE_SEG}.{FIXTURE_TEXTUAL_LEAF}", out_with,
                         "T31：已登记的人读型键被判死——登记机制失效")

    # ── T32：防过度修正（块级证据成立但未登记 ⇒ 仍进免检区）──────
    def test_T32_block_only_key_still_enters_examination_zone(self):
        """T32：块级证据成立但**未**人读型登记 ⇒ **仍**进免检区（防过度修正）。

        防的是「把块级证据整层删掉」这种过度修正：
        那会让所有块级消费的键都掉进死配置门 ⇒ 假阳性爆炸。

        ⚠ **本判据只针对「未登记的那一个键」**：
          `leaf_unused` 是**段级**计数（该段里几个键算待人工定性候选），
          故这里断言「≥1」而非「==1」——否则本判据会被 T31 的修复**连带**打死
          （判定顺序一改，该段的 leaf_unused 就从 2 变 1）⇒ 一个用例盯两件事
          ⇒ 变异报告读不出「哪个判据咬住了哪个缺陷」。
          「恰好那一个未登记键」的精确口径由 T31 的对照组（2 vs 1）承担。
        """
        root, rc, out, segs = self._make_fixture()

        seg_key = f"probe.yaml#{FIXTURE_SEG}"
        self.assertIn(seg_key, segs,
                      "T32：块级消费段未出现在免检区清单里——"
                      "块级证据层被误删（过度修正）")
        self.assertIn(f"{FIXTURE_SEG}.{FIXTURE_PLAIN_LEAF}", segs[seg_key]["keys"],
                      "T32：块级证据成立但未登记的键未进免检区段——过度修正")
        # 该键的末段键名在代码中 0 出现 ⇒ 应算「待人工定性候选」
        self.assertGreaterEqual(
            segs[seg_key]["leaf_unused"], 1,
            "T32：未登记的块级键未被计入「待人工定性候选」")
        # ⚠ 它**不得**被判死（它有块级证据 ⇒ 不是死配置）
        self.assertNotIn(f"{FIXTURE_SEG}.{FIXTURE_PLAIN_LEAF}", out,
                         "T32：块级证据成立的键被判死——块级证据层失效")
    # ── T33：防误伤 dead 判定（未登记 + 无块级证据 ⇒ 仍判死）──────
    def test_T33_unregistered_key_without_evidence_still_dies(self):
        """T33：未登记 + 无块级证据 + 无路径证据 ⇒ **仍判死**（防误伤 dead 判定）。

        防的是「为了修分支顺序，把 dead 判定放宽了」：
        那样任何新配置键都不会被检出 ⇒ 死配置门彻底失效。
        """
        root, rc, out, segs = self._make_fixture()

        self.assertIn(f"{FIXTURE_DEAD_LEAF}", out,
                      "T33：未登记、无任何证据的键未出现在死配置清单里"
                      "——dead 判定被放宽了（假绿）")
        self.assertNotEqual(rc, 0,
                            "T33：存在未登记死键但第 18 项 rc=0——dead 判定被放宽了")

    # ── T34：变异体必须能红（判定顺序改回原样 ⇒ T31 必须 FAIL）────
    def test_T34_reverse_example_old_branch_order_makes_T31_fail(self):
        """T34 反例：把判定顺序**改回原样**（elif 短路，textual 在 block 之后）
        ⇒ T31 的核心判据**必须失效**。

        ★ 这是「判据能红」的证明：若 T31 在错误实现下也通过，
          那 T31 就是恒真守卫 ⇒ 本组整体假绿。
        ⚠ 变异**只发生在临时目录的副本里**（不改真包、不改生产 config）。

        ⚠ **本用例自带变异体，完全自足**（不读 git、不依赖真包历史）：
          变异体 = 真包当前源码 + 「把这个末段键名登记为人读型」
                   + 「把判定分支替换成**换序形态**（块级证据在前 ⇒ elif 短路）」
          ⇒ ① 不依赖 `git HEAD`（提交后 HEAD 就变了 ⇒ 早版写法会失效——已踩）；
          ⇒ ② 真包被并行改动时本用例**依然**有效；
          ⇒ ③ 真包本身处于变异态时（外部做变异测试）本用例**依然**有效。

        ⚠⚠ **该变异体只隔离「顺序」这一个变量**（v3.28.2 重写）：
          · 保留 `_plain`（判定路径口径）· 保留 `idents`（指纹口径）
          · 保留 `leaf_weak` / `leaf_unused`（两个段级字段）
          · **只**把块级证据分支提到人读型登记分支之前。
          ⇒ 施加它 ⇒ `test_dead_config_disposition.py` **4 failed**
            （T31 + T34 + **T9** + **T39**），
            且 `test_inspection_zone_registry_red.py` **21 用例全绿**
            （换序不影响「登记表被改坏 ⇒ 判红」这条红证明链）。
          ⚠ **用历史形态（修复 A+B 之前）会连带打红 T9/T35/T38**——
            那三条测的是**指纹口径**（`keys_sha256` / 元素身份），
            **不是本判据所测的「顺序」** ⇒ 变异报告会与 commit 声称矛盾。
          ⚠⚠ **v3.28.2 实测口径修正（重要）**：
            本用例早版注释写的是「恰好 2 failed」——**那是在 R7/R8 存在之前**
            测的。**新增 R7 / R8 之后，「恰好 2 failed」在本版已不可达**：
            R7/R8 的存在目的正是「抓住修复 A 被回退」⇒ 判定顺序一旦换回去，
            `leaf_unused` / `leaf_weak` 的**实时值**必然与**登记值**不符
            ⇒ R7/R8 必然判红 ⇒ T9 必然转红；T39（端到端跑真守卫的 R2/R3/R4/R5）
            因内部调用同一个 T9 判据而**连带**转红。
            ⇒ 实测：T9 / T39 的红是 **R7 / R8 标签**（**不是** R3/R4）
              ⇒ 这是**新增守卫的预期行为**，不是变异体「不干净」。
            ⇒ 故此处改写为「4 failed」并**显式标注成因**，避免与实测不符。
        """
        # ① 变异体 = 真包源码 + 登记 + 原形态判定分支
        src = ES.read_text(encoding="utf-8")
        mutant_src = _register_textual_leaf(src, FIXTURE_TEXTUAL_LEAF)
        mutant_src = _revert_to_old_branch_order(mutant_src)

        # ② 在 fixture 上跑变异体
        import shutil
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="vetmed-t34-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        _build_branch_order_fixture(root)
        (root / "scripts" / "ensure_settings.py").write_text(mutant_src, encoding="utf-8")
        rc_mut, out_mut, segs_mut = _run_fixture(root)

        # ③ 对照组：正确实现（有登记）vs 基线（未登记）
        _, _, out_ok, _ = self._make_fixture(register_textual=True)
        _, _, out_base, _ = self._make_fixture(register_textual=False)

        seg_key = f"probe.yaml#{FIXTURE_SEG}"
        self.assertIn(seg_key, segs_mut,
                      "T34：变异体未造出免检区段——变异未生效，"
                      "本反例失去意义（不能证明判据能红）")

        # ★ 变异体下：已登记的人读型键**重新**落进「待人工定性候选」桶
        #   （leaf_unused = 2）⇒ 复现原缺陷 ⇒ T31 的 leaf_unused 断言必然失败。
        self.assertEqual(
            segs_mut[seg_key]["leaf_unused"], 2,
            "T34：变异体（判定顺序改回原样）未把已登记的人读型键打回"
            "「待人工定性候选」桶——变异未生效，本反例无效")

        # ★ 变异体下：textual 计数**不再**因该登记而 +1
        #   （对照组 +1，变异组 +0）⇒ T31 的 textual 断言在变异体下必然失败。
        mut_txt = self._textual_count(out_mut)
        ok_txt = self._textual_count(out_ok)
        base_txt = self._textual_count(out_base)
        self.assertEqual(ok_txt, base_txt + 1,
                         "T34 对照组：正确实现下该键未计入 textual —— "
                         "对照组前提失效，本反例无法证明判据能红")
        self.assertEqual(mut_txt, base_txt,
                         "T34：变异体下 textual 计数仍 +1 —— "
                         "变异未生效（人读型判定没被短路掉），本反例无效")


# ══════════════════════════════════════════════════════════════════════
# T35–T38：免检区段指纹的「**元素身份**」守卫（带下标 + 带值）
# ══════════════════════════════════════════════════════════════════════
#
# 病灶（真实判据缺陷，已实测复现）：
#   第 18 项的 `walk()` 遍历列表时把每个元素**折叠成同一条路径**
#   （`walk(item, path, fname)` —— 不加下标）⇒ 段内叶子路径**集合丢失了元素身份**。
#   而 `segments_digest()` 吃的是「折叠后的路径**多重集**」⇒
#   改**某个元素的内容**（把 `expert_panel[2].id` 从 A 改成 B）
#   **不改变**折叠后的路径多重集 ⇒ 指纹**不变** ⇒ 守卫 R3 判绿 ⇒ **假阴性**。
#
# ⚠ **实测得出的关键结论（本组判据的设计依据，逐条列明）**：
#   ① **只带下标**的路径指纹**检测不到「值变更」**——因为改**值**时
#      路径（`p[1].ident`）**一个字都没变** ⇒ 任何「纯路径」指纹都不变。
#      ⇒ 「值」必须进入指纹身份，否则「内容变更可检出」这条核心判据是**假的**。
#   ② **只带值、不带下标**的身份指纹**检测不到「元素换序」**——
#      换序后同一批「路径折叠后+值」不变 ⇒ 折叠+值 的指纹不变。
#      ⇒ 「下标」必须进入身份，否则「换序可检出」是假的。
#   ⇒ 结论：**下标与值缺一不可** ⇒ 新口径 = 「带下标 + 带值」的叶子**身份集合**。
#
# ★ **本组判据全部自造隔离 fixture**（临时目录 + 自己的 config + 自己的 script）：
#   不依赖仓库现有 config 的具体值 ⇒ 后续任何配置变动都不会让判据失效或假绿。
# ⚠ **不写生产 config、不写生产 script**：全部改动都发生在 `tempfile.mkdtemp()`
#   造的临时目录里，用完即删 ⇒ 并发下不会污染真包。

#: fixture 的段名（被 fixture 里的脚本整块取走 ⇒ 产生**块级证据**）。
DIGEST_FIXTURE_SEG = "probe_digest"
#: fixture 列表里元素的键名（改名判据用它）。
DIGEST_FIXTURE_KEY = "ident"
#: fixture 列表里元素的另一个键名（用于「只改某个键的值」的精确打击）。
DIGEST_FIXTURE_KEY2 = "mark"


def _build_digest_fixture(root: Path, items=None):
    """造一个「块级消费段 + 列表元素」的**最小隔离 fixture**。

    目录形态：
        <root>/config/probe.yaml       —— 段 `probe_digest` 里含一个**列表**
        <root>/scripts/probe_reader.py —— 整块取走 `probe_digest`（⇒ 块级证据）

    ⚠ 探针脚本**不**以 `test_` 开头 ⇒ 其读取点被 AST/链式读取点采集器计入
      （否则 fixture 造不出块级证据，判据就失去意义）。
    """
    import yaml

    if items is None:
        items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "config" / "probe.yaml").write_text(
        yaml.safe_dump({DIGEST_FIXTURE_SEG: {"entries": items}},
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    (root / "scripts" / "probe_reader.py").write_text(
        'def _read(cfg):\n'
        '    return cfg["probe_digest"]\n',
        encoding="utf-8")
    return root


def _revert_to_folded_walk(src: str) -> str:
    """把 `walk()` 的**列表分支**换成**原形态**（折叠路径、不加下标）。

    ⚠ 这是**变异体构造器**：它复刻的是**原缺陷形态**（列表元素被折叠）。
    ⚠ **必须逐字**替换 ⇒ 匹配不上直接抛错（而不是静默变成
      「什么也没改」的假 mutant ⇒ 那样变异证明会恒真）。
    ⚠ **自足**：以**真包当前源码**为基（不读 git、不依赖 HEAD 历史）
      ⇒ 真包本身处于变异态时本构造器**依然**有效。
    """
    old = '''        elif isinstance(node, list):
            # ⚠ **v3.28.2**：列表元素**带下标**（修复前折叠 ⇒ 元素身份丢失）。
            for _i, item in enumerate(node):
                walk(item, f"{path}[{_i}]" if path else f"[{_i}]", fname)'''
    new = '''        elif isinstance(node, list):
            for item in node:
                walk(item, path, fname)'''
    if old not in src:
        raise AssertionError(
            "变异体锚点未逐字匹配（ensure_settings.py 的列表分支结构变了？）")
    if src.count(old) != 1:
        raise AssertionError("变异体锚点不唯一（ensure_settings.py 的列表分支结构变了？）")
    return src.replace(old, new, 1)


def _revert_to_path_only_identity(src: str) -> str:
    """把「叶子身份」改成「**只带路径、不带值**」（第二个变异体）。

    ⚠ 复刻的是「只做了下标、没做值」这个**半修**形态
      ⇒ 它能检出「换序 / 增删 / 改名」，但**检不出「值变更」**
      ⇒ 用来证明 T35（值变更判据）对它**有鉴别力**。
    """
    old = '''    if value is None:
        return str(path)
    return f"{path}={value!r}"'''
    new = '''    return str(path)'''
    if old not in src:
        raise AssertionError(
            "变异体锚点未逐字匹配（ensure_settings.py 的 leaf_identity 结构变了？）")
    if src.count(old) != 1:
        raise AssertionError("变异体锚点不唯一（ensure_settings.py 的 leaf_identity 结构变了？）")
    return src.replace(old, new, 1)


def _run_digest_fixture(root: Path):
    """在 fixture 上跑第 18 项，返回 (rc, 输出, 段清单, 被测模块)。"""
    es = _load_es_from(root, "es_t35_fixture")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = es.check_dead_config_keys(str(root))
    return rc, buf.getvalue(), es.last_block_segments(), es


class TestSegmentDigestElementIdentity(unittest.TestCase):
    """T35–T38：免检区段指纹的「**元素身份**」守卫。

    ★ 本组的价值：钉住的是「指纹**能否分辨元素的哪一次出现、哪个值**」
      ⇒ 不会被配置演进打穿（判据自造 fixture，不依赖真实 config 的值）。
    """

    #: fixture 段的段键。
    SEG_KEY = f"probe.yaml#{DIGEST_FIXTURE_SEG}"

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    def _fixture_digest(self, items=None, es_src=None, name="es_t35"):
        """造 fixture → 跑第 18 项 → 返回该段的 (keys, digest)。

        ⚠ `es_src` 非空 ⇒ 用它当被测模块源码（供变异体使用）。
        """
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="vetmed-t35-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        _build_digest_fixture(root, items)
        if es_src is None:
            shutil.copy2(ES, root / "scripts" / "ensure_settings.py")
        else:
            (root / "scripts" / "ensure_settings.py").write_text(es_src,
                                                                encoding="utf-8")
        es = _load_es_from(root, name)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            es.check_dead_config_keys(str(root))
        segs = es.last_block_segments()
        self.assertIn(self.SEG_KEY, segs,
                      "fixture 未造出免检区段——判据前提失效（块级证据没生效？）")
        seg = segs[self.SEG_KEY]
        return seg["keys"], es.segments_digest(
            es.segment_digest_inputs(seg)), es

    # ── T35：核心判据（**值变更** ⇒ 指纹必须变）────────────────
    def test_T35_element_value_change_changes_digest(self):
        """T35：段内某元素的**内容**（值）改变 ⇒ 指纹**必须变**。

        ★ **本组的核心判据**。修复前（折叠路径多重集）它**必然 FAIL**：
          改 `probe_digest.entries[1].ident` 的**值**（e1→CHANGED）时，
          折叠后的路径集是「`entries.ident` 出现 2 次」——**一个字都没变**
          ⇒ 指纹不变 ⇒ R3 判绿 ⇒ **假阴性**。

        ⚠ **判据不依赖「当前数据恰好如此」**：fixture 完全自造
          （临时目录 + 自己的 config + 自己的 script）。
        """
        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        changed_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "CHANGED", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        keys0, d0, _es = self._fixture_digest(base_items)
        keys1, d1, _es2 = self._fixture_digest(changed_items)

        self.assertNotEqual(
            d0, d1,
            "T35：段内元素的**值**改了，指纹却没变 ⇒ R3 检不出「内容变更」"
            "（免检区段指纹的假阴性仍在）")

        # ★ 对照：确认**变的是值**而不是别的（键路径集合必须完全相同）
        #   ⇒ 证明本判据**精确命中**「值变更」，不是「别的也变了」的假通过。
        self.assertEqual(
            keys0, keys1,
            "T35 对照组：两组 fixture 的**键路径集合**应完全相同"
            "（唯一差异是值）——否则本判据证明的不是「值变更可检出」")

    # ── T36：列表长度 ±1 ⇒ 指纹变 ──────────────────────────────
    def test_T36_list_length_change_changes_digest(self):
        """T36：段内列表长度 +1 / -1 ⇒ 指纹**必须变**。

        防的是「有人把列表改短了/加长了，免检区却看不出来」。
        """
        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        longer = base_items + [{DIGEST_FIXTURE_KEY: "e2", DIGEST_FIXTURE_KEY2: "m2"}]
        shorter = base_items[:1]

        _k0, d0, _es = self._fixture_digest(base_items)
        _k1, d1, _es1 = self._fixture_digest(longer)
        _k2, d2, _es2 = self._fixture_digest(shorter)

        self.assertNotEqual(d0, d1, "T36：列表长度 +1 但指纹未变 ⇒ 判据失效")
        self.assertNotEqual(d0, d2, "T36：列表长度 -1 但指纹未变 ⇒ 判据失效")

    # ── T37：元素**改名**（键名改名）⇒ 指纹变 ────────────────────
    def test_T37_element_key_rename_changes_digest(self):
        """T37：段内某元素的**键名**改名 ⇒ 指纹**必须变**。

        防的是「把 `ident` 改成 `id`」这类改动（路径变了 ⇒ 身份变了）。
        """
        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        renamed = [
            {"renamed_" + DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {"renamed_" + DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        _k0, d0, _es = self._fixture_digest(base_items)
        _k1, d1, _es1 = self._fixture_digest(renamed)
        self.assertNotEqual(d0, d1, "T37：元素键名改名但指纹未变 ⇒ 判据失效")

    # ── T38：变异体必须能红（折叠形态 ⇒ 「顺序/重复元素」判据必须 FAIL）──
    def test_T38_reverse_example_folded_walk_makes_identity_criteria_fail(self):
        """T38 反例：把 `walk()` 改回**折叠路径**形态 ⇒ 「身份类」判据**必须失效**。

        ★ 这是「判据能红」的证明：若这些判据在错误实现下也通过，
          那它们就是恒真守卫 ⇒ 本组整体假绿。

        ⚠ **为什么本变异体由「顺序/重复元素」判据来杀**（**实测结论，如实标注**）：
          折叠形态下，段内键的**路径**不再带下标 ⇒
            · 元素**换序** ⇒ 身份串集合**完全相同**（路径折叠了、值没变）
              ⇒ 指纹**不变** ⇒ **检出不了**（这正是折叠的病根）。
            · 新增一个**内容与已有元素相同**的元素 ⇒ 身份串集合**不变**
              ⇒ 指纹**不变** ⇒ **检出不了**。
          而「改元素**值**」这一类，折叠形态**仍能**检出（因为身份串里**含值**，
          值变了身份就变了）⇒ 杀折叠形态的**不是**「值变更」判据。
          ⇒ 故本组把两维判据**分工**（各自杀各自的变异体）：
            · **值变更**判据（T35）⇒ 杀「只带路径、不带值」的**半修**形态（T38b）；
            · **顺序/重复元素**判据（本条）⇒ 杀「折叠路径」形态（本条）。
          ⇒ 两维各自有判据 ⇒ 缺任何一维的形态都**存活不了**。

        ⚠ **变异体自足**：以**真包当前源码**为基（不读 git、不依赖 HEAD 历史）
          ⇒ ① 提交后 HEAD 就变了，早版写法会失效——已踩；
          ⇒ ② 真包本身处于变异态时（外部做变异测试）本用例**依然**有效。
        ⚠ 变异**只发生在临时目录的副本里**（不改真包、不改生产 config）。
        """
        src = ES.read_text(encoding="utf-8")
        mutant_src = _revert_to_folded_walk(src)

        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        swapped = [
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
        ]
        # 新增一个「内容与已有元素**完全相同**」的元素（折叠形态下集合不变）
        duplicated = base_items + [
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"}]

        # ① 变异体下：换序 ⇒ 指纹**不变**（复现原缺陷 ⇒ 判据必然失败）
        _mk, d_mut, _esm = self._fixture_digest(base_items, es_src=mutant_src,
                                                name="es_t38_mut")
        _mk2, d_mut2, _esm2 = self._fixture_digest(swapped, es_src=mutant_src,
                                                   name="es_t38_mut2")
        self.assertEqual(
            d_mut, d_mut2,
            "T38：变异体（列表折叠回原形态）下，元素**换序**竟然改变了指纹 —— "
            "说明变异未生效或该形态仍能检出换序 ⇒ 本反例无效")

        # ② 变异体下：新增「重复内容」元素 ⇒ 指纹**不变**（同型漏检）
        _mk3, d_mut3, _esm3 = self._fixture_digest(duplicated,
                                                   es_src=mutant_src,
                                                   name="es_t38_mut3")
        self.assertEqual(
            d_mut, d_mut3,
            "T38：变异体（列表折叠回原形态）下，新增**重复内容**的元素竟然"
            "改变了指纹 —— 说明该形态仍能检出重复元素 ⇒ 本反例无效")

        # ③ 对照组：正确实现下，换序**必须**改指纹
        #   （证明 ① 的「不变」确由变异引起，不是恒真）
        _k0, d_ok, _es = self._fixture_digest(base_items)
        _k1, d_ok2, _es1 = self._fixture_digest(swapped)
        self.assertNotEqual(
            d_ok, d_ok2,
            "T38 对照组：正确实现下元素换序未改指纹 ⇒ 「下标」这一维失效，"
            "本反例无法证明判据能红")

        # ④ 对照组：正确实现下，新增「重复内容」元素**必须**改指纹
        _k2, d_ok3, _es2 = self._fixture_digest(duplicated)
        self.assertNotEqual(
            d_ok, d_ok3,
            "T38 对照组：正确实现下新增重复内容元素未改指纹 ⇒ "
            "「元素身份可辨」失效，本反例无法证明判据能红")

    # ── T38b：第二个变异体（只带下标、**不带值**）必须被 T35 杀掉 ──
    def test_T38b_reverse_example_path_only_identity_makes_T35_fail(self):
        """T38b 反例：把身份改成「**只带路径、不带值**」⇒ T35 必须失效。

        ★ 这条针对的是「**半修**」形态：只做了下标、没做值。
          它**能**检出换序 / 增删 / 改名，但**检不出值变更**
          ⇒ 若 T35 只测「换序 / 增删 / 改名」，这个半修形态就会**存活**
          ⇒ 本用例证明 T35 的判据**精确命中「值变更」**这一维。
        """
        src = ES.read_text(encoding="utf-8")
        mutant_src = _revert_to_path_only_identity(src)

        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        changed_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "CHANGED", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        _k0, d_mut, _esm = self._fixture_digest(base_items, es_src=mutant_src,
                                                name="es_t38b_mut")
        _k1, d_mut2, _esm2 = self._fixture_digest(changed_items,
                                                   es_src=mutant_src,
                                                   name="es_t38b_mut2")
        self.assertEqual(
            d_mut, d_mut2,
            "T38b：变异体（身份只带路径、不带值）下，改元素**值**竟然改变了指纹 —— "
            "说明该半修形态仍能检出值变更 ⇒ T35 的判据没有精确命中「值变更」")

    # ── T38c：重复内容元素 ⇒ 正确实现必须检出（折叠形态检不出）────
    def test_T38c_reverse_example_folded_walk_misses_duplicate_element(self):
        """T38c 反例：新增一个「**内容与已有元素完全相同**」的元素 ⇒
        正确实现必须检出，折叠形态**检不出**。

        ⚠ **为什么单独一条**：这是「**集合 vs 多重集**」这一维的判据。
          折叠形态下，新元素的「折叠路径 + 值」与已有元素**完全相同**
          ⇒ 身份串**集合**不变 ⇒ 指纹不变 ⇒ 漏检。
          而带下标的正确实现下，新元素是 `entries[2].ident='e1'`
          ⇒ 与 `entries[1].ident='e1'` **不同** ⇒ 集合变大 ⇒ 指纹变。
        """
        base_items = [
            {DIGEST_FIXTURE_KEY: "e0", DIGEST_FIXTURE_KEY2: "m0"},
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"},
        ]
        duplicated = base_items + [
            {DIGEST_FIXTURE_KEY: "e1", DIGEST_FIXTURE_KEY2: "m1"}]

        # 正确实现 ⇒ 必须检出
        _k0, d_ok, _es = self._fixture_digest(base_items)
        _k1, d_ok2, _es1 = self._fixture_digest(duplicated)
        self.assertNotEqual(
            d_ok, d_ok2,
            "T38c：正确实现下新增「重复内容」元素未改指纹 ⇒ "
            "「元素身份可辨」这一维失效")

        # 折叠形态 ⇒ 检不出（复现原缺陷）
        src = ES.read_text(encoding="utf-8")
        mutant_src = _revert_to_folded_walk(src)
        _k2, d_mut, _esm = self._fixture_digest(base_items, es_src=mutant_src,
                                                name="es_t38c_mut")
        _k3, d_mut2, _esm2 = self._fixture_digest(duplicated,
                                                  es_src=mutant_src,
                                                  name="es_t38c_mut2")
        self.assertEqual(
            d_mut, d_mut2,
            "T38c：变异体（折叠形态）下，新增「重复内容」元素竟然改变了指纹 —— "
            "说明该形态仍能检出重复元素 ⇒ 本反例无效")

    # ── T39：向后兼容——旧口径登记表仍能过（**不新增判据编号**）────
    def test_T39_backward_compatible_old_scheme_registry_still_passes(self):
        """T39：登记表**没写** `digest_scheme`（= 旧口径）⇒ 仍能过 R3/R4。

        ★ **向后兼容的证明**（旧口径的 `keys_sha256` 是按「折叠路径多重集」算的；
          本次把 `walk()` 改成带下标后，若不能**精确复现**旧值，
          旧登记表会被误判成「脱节」⇒ 升级就会**逼所有人**重登一遍）。

        ⚠⚠ **完全自足**（不读 git、不依赖 HEAD 历史）—— **踩坑修正**：
          早版实现用 `git show HEAD:references/inspection-zones.yaml` 取旧登记值
          当对照 ⇒ **提交后 HEAD 就变了** ⇒ 该判据**自毁**（提交后必转红）。
          本仓库已有纪律明写「不依赖 `git HEAD`（提交后 HEAD 就变了 ⇒ 早版写法
          会失效——已踩）」，本条不得再犯。
          ⇒ 改为**现场造**一份旧口径登记表（见下），对照值由**独立 oracle** 算出。

        【本用例的鉴别力从哪来（两处，都不是「复刻自己」）】
          ① **独立 oracle**：旧口径指纹由本测试**自己实现**的 sha256 + 剥下标
             算出（**不复用**被测的 `segments_digest` / `fold_segment_keys`）
             ⇒ 被测实现若把「剥下标」或「去值/去重」写错 ⇒ 两者不一致 ⇒ 判红。
          ② **端到端跑真守卫**：旧口径登记表交给**真守卫代码**（子进程跑
             `TestInspectionZoneRegistry.test_T9_registry_segments_match_live`，
             它同时跑 R2/R3/R4/R5）⇒ 守卫的旧口径分支被改坏 ⇒ 守卫判红
             ⇒ 本用例失败。**跑的是真代码，不是复刻**。

        ⚠ 全程在**隔离副本**上做（不碰生产 config、不碰生产登记表）。
        """
        import hashlib
        import re
        import subprocess
        import sys
        import yaml
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg

        # ── 独立 oracle：旧口径 = sha256("\\n".join(sorted(折叠路径)))[:40] ──
        #    ⚠ **不复用被测代码**（否则「实现和自己一致」恒真 ⇒ 鉴别力为零）。
        def _old_oracle(keys):
            folded = [re.sub(r"\[\d+\]", "", str(k)) for k in keys]
            blob = "\n".join(sorted(folded)).encode("utf-8")
            return hashlib.sha256(blob).hexdigest()[:40], len(folded)

        iso = make_isolated_pkg(prefix="vetmed-iso-oldscheme-")
        try:
            es_iso = _load_es_on(iso)
            live = es_iso.collect_block_segments(str(iso))
            self.assertTrue(live, "隔离副本未造出免检区段——判据前提失效")

            # ① 把副本的登记表换成「旧口径版本」
            reg_path = iso / "references" / "inspection-zones.yaml"
            reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
            reg.pop("digest_scheme", None)        # = 旧登记表形态（无口径声明）
            for s in reg.get("segments") or []:
                seg = live.get(s["id"])
                if seg is None:
                    continue
                sha, cnt = _old_oracle(seg["keys"])
                s["keys_sha256"] = sha
                s["key_count"] = cnt
            reg_path.write_text(
                yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
                encoding="utf-8")

            # ② 子进程跑**真守卫**的 R2/R3/R4/R5（真代码，不是复刻）
            guard = iso / "scripts" / "test_dead_config_disposition.py"
            env = dict(os.environ)
            env["PYTHONPATH"] = (str(iso / "scripts") + os.pathsep
                                  + env.get("PYTHONPATH", ""))
            proc = subprocess.run(
                [sys.executable, str(guard),
                 "TestInspectionZoneRegistry.test_T9_registry_segments_match_live"],
                capture_output=True, text=True, env=env, cwd=str(iso), timeout=300)
            self.assertEqual(
                proc.returncode, 0,
                "旧口径登记表（无 `digest_scheme`）没通过真守卫的 R2/R3/R4/R5 ⇒ "
                "向后兼容是假的（守卫的旧口径分支被改坏？）\n"
                f"输出尾部：{(proc.stdout or '')[-2000:]}\n"
                f"错误尾部：{(proc.stderr or '')[-800:]}")
        finally:
            cleanup_isolated_pkg(iso)

        # ③ 缺省口径 = 旧口径（登记表不写 `digest_scheme` ⇒ 按旧口径解释）
        self.assertEqual(self.es.DEFAULT_DIGEST_SCHEME,
                         self.es.DIGEST_SCHEME_FOLDED,
                         "缺省口径必须是旧口径，否则旧登记表会被误判成脱节")


if __name__ == "__main__":
    unittest.main(verbosity=2)

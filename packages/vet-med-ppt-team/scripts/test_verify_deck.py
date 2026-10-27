#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_verify_deck.py — verify_deck.py 回归测试（v3.16.0 批次「口径与机器校验」）

T1  默认口径 = yaml page_caliber_default（"course"）；非法值不静默生效
T2  24 页 fixture：course 报「课时不达标」/ single-ppt 不报（证明开关真的接线，不是摆设）
T3  不加 caliber 与显式 course 结果逐字一致（历史复验不受影响）
T4  主框 180 字 → 「主框密度超标」计入 P1 且不在 P0；全页 <400 → 「文字墙」不触发
T5  主框 140 字 → 不报（同时反证标题/图注/页脚被正确排除）
T6  body_frame_chars 排除规则逐条验证（含"页脚区位但 >20 字不得排除"的反边界）
T7  red 的每个键都能在 severity 里找到（防新增问题类型静默掉出分级）
T8  未知问题类型不落 P0（改为不落任何级、进 P3 明示队列）
T9  rubric 建议级：默认关闭产 0 条；打开后出条目且**不影响 p0/p1/p2 与 issues**
T10 _FALLBACK 已同步双口径新键（与 ensure_settings 第 19 项互为双保险）

风格：unittest + tempfile 自造 fixture（与既有 scripts/test_*.py 一致），禁依赖网络与真实课件。
用法：
    python3 scripts/test_verify_deck.py
    python3 -m pytest scripts/test_verify_deck.py -q
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RULES_YAML = HERE.parent / "config" / "visual-rules.yaml"

try:
    import verify_deck as vd          # 与 verify_deck.py 同目录
    PPTX_AVAILABLE = True
except ImportError:                   # python-pptx 缺失时 import 会 SystemExit
    PPTX_AVAILABLE = False

from pptx import Presentation          # noqa: E402
from pptx.util import Inches, Pt       # noqa: E402

BODY_TEXT = ("病原经呼吸道侵入后在法氏囊内复制，导致淋巴滤泡坏死与出血，"
             "临床可见精神沉郁与白色水样下痢，剖检见胸腺与法氏囊点状出血，"
             "确诊需结合琼脂扩散试验与RT-PCR结果，防控以疫苗免疫与生物安全并重。")


def _page(prs, title, body, note=True):
    """建一页：标题占位符 + 正文占位符（单段落，避免 \\n 计入字数）。"""
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.placeholders[0].text_frame.text = title
    tf = s.placeholders[1].text_frame
    tf.text = body
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(18)      # 高于 12pt 字号红线
    if note:
        s.notes_slide.notes_text_frame.text = "讲稿要点：先结论，再机制，最后判读要点。"
    return s


def _make_deck(tmp, n_pages, toc=True, quiz=True):
    """n_pages 页合规小课件（含目录页/题页）。"""
    prs = Presentation()
    extra = 0
    if toc:
        _page(prs, "目录", "一 病原与流行病学\n二 临床症状\n三 剖检病变\n四 防控要点")
    for i in range(max(0, n_pages - int(toc) - int(quiz))):
        extra += 1
        _page(prs, f"知识点{extra}", BODY_TEXT[:40] + f"（要点{extra}）")
    if quiz:
        _page(prs, "思考题", "Q1：如何区分新城疫与禽流感的剖检差异？")
    assert len(prs.slides) == n_pages, (len(prs.slides), n_pages)
    p = os.path.join(tmp, f"deck{n_pages}.pptx")
    prs.save(p)
    return p


def _make_body_deck(tmp, n_chars, name):
    """含一页主框 n_chars 字 + 来源框 + 页脚框的课件（共 3 页）。"""
    prs = Presentation()
    _page(prs, "目录", "一 病原\n二 症状\n三 诊断\n四 防控")
    _page(prs, "思考题", "Q1：本病的示病性病变是什么？")
    body = (BODY_TEXT * 10)[:n_chars]
    assert len(body) == n_chars, (len(body), n_chars)
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.placeholders[0].text_frame.text = "主框密度测试页"
    tf = s.placeholders[1].text_frame
    tf.text = body
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(18)
    s.placeholders[1].height = Inches(4.0)     # 腾出不重叠空位给来源框
    tb = s.shapes.add_textbox(Inches(0.7), Inches(6.1), Inches(8.0), Inches(0.4))
    tb.text_frame.text = "来源：WOAH《陆生动物卫生法典》2023，PMCID PMC1234567"
    # 页脚区：top=7.05in ≥ 0.92×页高(7.5in)=6.9in，且文本 7 字 ≤20 → 应被排除
    ft = s.shapes.add_textbox(Inches(0.7), Inches(7.05), Inches(2.0), Inches(0.4))
    ft.text_frame.text = "12 / 23"
    s.notes_slide.notes_text_frame.text = "讲稿：先结论后机制。"
    p = os.path.join(tmp, name)
    prs.save(p)
    return p


def _make_rubric_deck(tmp):
    """前 3 页同版式 + 第 4 页标题外移 1.5in；全篇无图 → 触发连续纯文字。"""
    prs = Presentation()
    _page(prs, "目录", "一 病原\n二 症状\n三 诊断")
    _page(prs, "知识点一", BODY_TEXT[:40])
    s = _page(prs, "知识点二", BODY_TEXT[:40])
    s.placeholders[0].left = s.placeholders[0].left + Inches(1.5)
    _page(prs, "思考题", "Q1：简述本病防控要点。")
    p = os.path.join(tmp, "deck_rubric.pptx")
    prs.save(p)
    return p


@unittest.skipUnless(PPTX_AVAILABLE, "需要 python-pptx")
class TestCaliber(unittest.TestCase):
    """F1：页数双口径。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.deck = _make_deck(self.tmp.name, 24)

    def tearDown(self):
        self.tmp.cleanup()

    def test_t1_default_caliber_is_course(self):
        # 默认口径恒为 course：与 v3.16.0 之前同一张表，历史复验结论不得变
        self.assertEqual(vd._resolve_caliber(None), "course")
        self.assertEqual(vd._resolve_caliber("course"), "course")
        self.assertEqual(vd._resolve_caliber("single-ppt"), "single-ppt")
        self.assertEqual(vd._resolve_caliber("乱写的值"), "course")   # 非法值不静默生效
        self.assertEqual(vd.THRESHOLD["page_caliber_default"], "course")

    def test_t2_24_pages_opposite_results(self):
        a = vd.verify(self.deck, hours=2, caliber="course")
        b = vd.verify(self.deck, hours=2, caliber="single-ppt")
        types_a = [i["type"] for i in a["issues"]]
        types_b = [i["type"] for i in b["issues"]]
        self.assertIn("课时不达标", types_a, "24 页 ∉ 36-52 —— course 口径必须报")
        self.assertNotIn("课时不达标", types_b, "24 页 ∈ 22-32 —— single-ppt 口径不得报")
        self.assertEqual(a["stats"]["page_range"], [36, 52])
        self.assertEqual(b["stats"]["page_range"], [22, 32])
        self.assertEqual(a["stats"]["caliber"], "course")
        self.assertEqual(b["stats"]["caliber"], "single-ppt")

    def test_t3_default_equals_course(self):
        d = vd.verify(self.deck, hours=2)                      # 不显式给 caliber
        c = vd.verify(self.deck, hours=2, caliber="course")
        self.assertEqual(json.dumps(d["issues"], ensure_ascii=False, sort_keys=True),
                         json.dumps(c["issues"], ensure_ascii=False, sort_keys=True))
        self.assertEqual(d["stats"]["caliber"], "course")
        self.assertEqual(d["red"], c["red"])
        self.assertEqual(d["gate"], c["gate"])
        # 默认口径下 课时不达标 的 detail 字符串不得携带口径标签（与 v3.16.0 之前逐字一致）
        detail = [i["detail"] for i in d["issues"] if i["type"] == "课时不达标"][0]
        self.assertNotIn("［", detail, "默认口径不得在 detail 里追加口径标签")
        self.assertEqual(detail, f"可见24页，{d['stats']['hours']}课时标准(36-52页)")


    def test_t11_missing_tier_warns_and_is_not_pass(self):
        """口径 B 无 1.5 档：不得静默判通过，但也不许伪造 P0。"""
        r = vd.verify(self.deck, hours=1.5, caliber="single-ppt")
        self.assertTrue(r["stats"]["hours_standard_missing"])
        self.assertFalse(r["stats"]["hours_ok"], "缺档时 hours_ok 必须为 False（未判定≠达标）")
        self.assertIn("single-ppt", r["stats"]["hours_missing_detail"])
        self.assertIn("1.5", r["stats"]["hours_missing_detail"])
        self.assertEqual(r["gate"]["p3"], 1, "缺档必须进 P3 明示队列")
        self.assertNotIn("课时不达标", [i["type"] for i in r["issues"]],
                         "缺档不得伪造「课时不达标」这条 P0")
        self.assertEqual(r["gate"]["p0"], 0)
        # JSON 必须能看出未判定
        dumped = json.dumps(r, ensure_ascii=False)
        self.assertIn("hours_standard_missing", dumped)
        self.assertIn("未执行", dumped)

    def test_t12_course_1_5_unchanged(self):
        """course 口径有 1.5 档 → 与 v3.16.0 之前一致：24 页 ∉ 35-50 → 真 P0。"""
        r = vd.verify(self.deck, hours=1.5, caliber="course")
        self.assertFalse(r["stats"]["hours_standard_missing"])
        self.assertEqual(r["stats"]["page_range"], [35, 50])
        self.assertFalse(r["stats"]["hours_ok"])
        self.assertEqual(r["gate"]["p0"], 1)
        detail = [i["detail"] for i in r["issues"] if i["type"] == "课时不达标"][0]
        self.assertEqual(detail, f"可见24页，{r['stats']['hours']}课时标准(35-50页)")

    def test_t13_empty_table_warns(self):
        """yaml 结构异常导致整表为空 → 比缺档更严重，同样不许静默。"""
        saved = vd.THRESHOLD["hours_page_range_single_ppt"]
        try:
            vd.THRESHOLD["hours_page_range_single_ppt"] = {}
            r = vd.verify(self.deck, hours=2, caliber="single-ppt")
            self.assertTrue(r["stats"]["hours_standard_missing"])
            self.assertIn("为空", r["stats"]["hours_missing_detail"])
            self.assertFalse(r["stats"]["hours_ok"])
            self.assertEqual(r["gate"]["p3"], 1)
        finally:
            vd.THRESHOLD["hours_page_range_single_ppt"] = saved

    def test_t14_cli_missing_tier_prints_warning(self):
        """CLI 层：stderr 必须有告警，stdout 结论必须带限定语（否则会被读成通过）。"""
        import subprocess
        p = subprocess.run(
            [sys.executable, str(HERE / "verify_deck.py"), self.deck,
             "--hours", "1.5", "--caliber", "single-ppt"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, "缺档不阻断写回")
        self.assertIn("未定义 1.5 课时的页数标准", p.stderr)
        self.assertIn("课时匹配【未执行】", p.stdout)
        self.assertIn("本次结论不含课时判定", p.stdout)
        self.assertIn("⚠未判定", p.stdout)


@unittest.skipUnless(PPTX_AVAILABLE, "需要 python-pptx")
class TestBodyDensity(unittest.TestCase):
    """F4：单页主框字数落地为机器判据。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d180 = _make_body_deck(self.tmp.name, 180, "d180.pptx")
        self.d140 = _make_body_deck(self.tmp.name, 140, "d140.pptx")

    def tearDown(self):
        self.tmp.cleanup()

    def test_t4_180_chars_reported_as_p1(self):
        r = vd.verify(self.d180, hours=1, caliber="single-ppt")
        self.assertEqual(r["red"]["主框密度超标"], 1)
        self.assertEqual(r["stats"]["max_body_chars_seen"], 180)
        self.assertEqual(r["red"]["文字墙"], 0, "全页应 <400 字，不得误触发文字墙")
        self.assertIn("主框密度超标", [i["type"] for i in r["issues"]])
        self.assertEqual(vd._TYPE_LEVEL.get("主框密度超标"), "P1")
        self.assertEqual(vd._count_by_level({"主框密度超标": 1}), (0, 1),
                         "主框密度必须进 P1，不得被算成 P0")

    def test_t5_140_chars_not_reported(self):
        r = vd.verify(self.d140, hours=1, caliber="single-ppt")
        self.assertEqual(r["red"]["主框密度超标"], 0)
        self.assertEqual(r["stats"]["max_body_chars_seen"], 140,
                         "若来源46字/页脚7字未被排除则为 193，排除规则即失效")
        self.assertNotIn("主框密度超标", [i["type"] for i in r["issues"]])

    def test_t6_exclusion_rules(self):
        h = int(7.5 * vd.EMU_PER_INCH)          # 页高 7.5in → 页脚阈值 6.9in
        footer_top = int(7.05 * vd.EMU_PER_INCH)
        adapters = [
            {"has_tf": True, "text": "标题占位符", "is_title_ph": True, "rect": None},
            {"has_tf": True, "text": "来源：WOAH 2023", "is_title_ph": False, "rect": None},
            {"has_tf": True, "text": "12 / 23", "is_title_ph": False,
             "rect": (0, footer_top, 100, 100)},
            {"has_tf": True, "text": "这是真正要学生读的主框正文", "is_title_ph": False,
             "rect": (0, int(2 * vd.EMU_PER_INCH), 100, 100)},
            {"has_tf": True, "text": "", "is_title_ph": False, "rect": None},
        ]
        chars, frames = vd.body_frame_chars(adapters, h)
        self.assertEqual(chars, len("这是真正要学生读的主框正文"))
        self.assertEqual(frames, 1, "只应有 1 个框计入主框")

        # 反边界①：同样在页脚区位置，但 >20 字 → 不得按页脚排除（防"位置命中即排除"）
        long_footer = {"has_tf": True, "text": "本页补充说明：" + "延长" * 12,
                       "is_title_ph": False, "rect": (0, footer_top, 100, 100)}
        _, frames2 = vd.body_frame_chars([long_footer], h)
        self.assertEqual(frames2, 1, "页脚区但超 20 字 → 必须计入主框")

        # 反边界②：同样短文本，但不在页脚区 → 不得按页脚排除
        short_mid = {"has_tf": True, "text": "小结要点", "is_title_ph": False,
                     "rect": (0, int(3 * vd.EMU_PER_INCH), 100, 100)}
        _, frames3 = vd.body_frame_chars([short_mid], h)
        self.assertEqual(frames3, 1, "页中部短文本 → 必须计入主框")


@unittest.skipUnless(PPTX_AVAILABLE, "需要 python-pptx")
class TestSeverityWiring(unittest.TestCase):
    """分级接线：red 键必须有归宿；未知类型不得默认 P0。"""

    def test_t7_every_red_key_in_severity(self):
        tr = tempfile.TemporaryDirectory()
        try:
            deck = _make_deck(tr.name, 24)
            r = vd.verify(deck, hours=2)
            for k in r["red"]:
                self.assertIn(k.split("(")[0], vd._TYPE_LEVEL,
                              f"red 键 {k} 未在 severity 登记 → 会静默掉出分级统计")
            self.assertEqual(r["stats"]["unknown_red_keys"], [])
        finally:
            tr.cleanup()

    def test_t8_unknown_type_not_p0(self):
        unknown = []
        self.assertEqual(vd._count_by_level({"根本没登记的类型": 5}, unknown), (0, 0))
        self.assertEqual(unknown, ["根本没登记的类型"])
        # 已登记类型仍按既有级别计（不得因这次改动被弱化）
        self.assertEqual(vd._count_by_level({"课时不达标": 1, "文字墙": 2, "缺备注": 3}),
                         (1, 2))


@unittest.skipUnless(PPTX_AVAILABLE, "需要 python-pptx")
class TestRubricChecks(unittest.TestCase):
    """M5：V1/V5 落地为建议级，默认关闭、不计门禁。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.deck = _make_rubric_deck(self.tmp.name)
        self._saved = {k: dict(v) for k, v in vd.THRESHOLD["checks"].items()}

    def tearDown(self):
        vd.THRESHOLD["checks"] = {k: dict(v) for k, v in self._saved.items()}
        self.tmp.cleanup()

    def test_t9_default_off(self):
        r = vd.verify(self.deck, hours=1, caliber="single-ppt")
        self.assertIn("rubric", r)
        self.assertEqual(r["rubric"], [], "默认关闭时不得产出任何条目")
        self.assertEqual(r["gate"]["rubric_count"], 0)
        self.assertNotIn("title_position_consistency", [i["type"] for i in r["issues"]])
        self.assertNotIn("image_area_ratio", [i["type"] for i in r["issues"]])

    def test_t9b_enabled_shows_entries_and_changes_no_gate(self):
        before = vd.verify(self.deck, hours=1, caliber="single-ppt")
        vd.THRESHOLD["checks"]["title_position_consistency"]["enabled"] = True
        vd.THRESHOLD["checks"]["image_area_ratio"]["enabled"] = True
        after = vd.verify(self.deck, hours=1, caliber="single-ppt")

        ids = {e["check_id"] for e in after["rubric"]}
        self.assertIn("title_position_consistency", ids)
        self.assertIn("image_area_ratio", ids)
        for e in after["rubric"]:
            self.assertIn("slide", e)
            self.assertIn("detail", e)
        # 每条 rubric 必须能进 JSON 报告（验收项 3 的硬要求：可被序列化、可被读出）
        self.assertEqual(json.loads(json.dumps(after["rubric"], ensure_ascii=False)),
                         after["rubric"])
        # 建议级不得影响任何门禁计数
        self.assertEqual(before["gate"]["p0"], after["gate"]["p0"])
        self.assertEqual(before["gate"]["p1"], after["gate"]["p1"])
        self.assertEqual(before["gate"]["p2_block"], after["gate"]["p2_block"])
        self.assertEqual(before["issues"], after["issues"])

    def test_t9c_title_position_units(self):
        rows = [(1, (0, 0, 100000)), (2, (0, 0, 100000)), (3, (0, 0, 100000)),
                (4, (int(1.5 * vd.EMU_PER_INCH), 0, 100000))]
        out = vd._rubric_title_position(rows, {"enabled": True, "tolerance_in": 0.25})
        self.assertEqual([e["slide"] for e in out], [4], "只有偏离众数的那页出条目")
        self.assertEqual(vd._rubric_title_position(rows, {"enabled": False,
                                                          "tolerance_in": 0.25}), [])
        self.assertEqual(vd._rubric_title_position([(1, (0, 0, 1))],
                                                   {"enabled": True}), [],
                         "样本不足 2 页时众数无意义 → 不产条目（防逻辑性假阳性）")

    def test_t9d_image_area_units(self):
        # 连续纯文字：上限 3 → 第 4、5 页才报警
        rows = [(i, 0.0, False) for i in range(1, 6)]
        out = vd._rubric_image_area(rows, {"enabled": True, "min": 0.20, "max": 0.50,
                                           "max_consecutive_textonly": 3})
        self.assertEqual([e["slide"] for e in out], [4, 5])
        # 占比越界：10% < 20% 下限 → 报；30% 在区间内 → 不报；60% > 50% 上限 → 报
        rows2 = [(1, 0.10, True), (2, 0.30, True), (3, 0.60, True)]
        out2 = vd._rubric_image_area(rows2, {"enabled": True, "min": 0.20, "max": 0.50,
                                             "max_consecutive_textonly": 3})
        self.assertEqual([e["slide"] for e in out2], [1, 3])
        self.assertEqual(vd._rubric_image_area(rows2, {"enabled": False}), [])


class TestFallbackSync(unittest.TestCase):
    """T10：_FALLBACK 必须同步 v3.16.0 新键（与 ensure_settings 第 19 项互证）。"""

    def test_t10_fallback_has_new_keys(self):
        fb = vd._FALLBACK
        self.assertEqual(fb["page_caliber_default"], "course")
        self.assertEqual(fb["max_body_chars_per_slide"], 150)
        self.assertEqual(fb["hours_page_range_single_ppt"],
                         {1: (12, 18), 2: (22, 32), 3: (32, 45), 4: (42, 58)})
        self.assertIn("主框密度超标", fb["severity"]["P1"])
        self.assertFalse(fb["checks"]["title_position_consistency"]["enabled"])
        self.assertFalse(fb["checks"]["image_area_ratio"]["enabled"])
        self.assertEqual(fb["checks"]["title_position_consistency"]["tolerance_in"], 0.25)

    def test_t10b_yaml_sections_exist(self):
        import yaml
        rules = yaml.safe_load(open(RULES_YAML, encoding="utf-8"))
        self.assertEqual(list(rules["hours_page_range_single_ppt"].keys()),
                         [1, 2, 3, 4])
        self.assertEqual(rules["page_caliber_default"], "course")
        self.assertIn("主框密度超标", rules["severity"]["P1"])
        self.assertFalse(rules["checks"]["title_position_consistency"]["enabled"])


class TestChartLayoutW1(unittest.TestCase):
    """v3.23.1 W1：chart.unimplemented 三项中两项落地（轴标注字号 / 图例存在性）。

    背景：v3.22.0 G2 只实现"图区面积比"；轴字号 / 图例 / 表格布局登记为残留。
    本轮实证判据可确定性解析（chartSpace XML 内 catAx/valAx 段的 a:defRPr sz
    与 c:legend/legendPos、c:ser 计数），落地两项；table_layout 仍不实现。
    全部建议级（不登记 severity ⇒ 不阻断），缺省键 = 不判（向后兼容）。
    """

    BAD = ("<c:chartSpace><c:chart><c:plotArea>"
           "<c:barChart><c:ser/><c:ser/></c:barChart>"
           "<c:catAx><c:txPr><a:p><a:pPr><a:defRPr sz=\"900\"/></a:pPr></a:p></c:txPr></c:catAx>"
           "<c:valAx></c:valAx></c:plotArea></c:chart></c:chartSpace>")
    GOOD = ("<c:chartSpace><c:chart><c:plotArea>"
            "<c:barChart><c:ser/><c:ser/></c:barChart>"
            "<c:catAx><c:txPr><a:p><a:pPr><a:defRPr sz=\"1300\"/></a:pPr></a:p></c:txPr></c:catAx>"
            "<c:valAx><c:txPr><a:p><a:pPr><a:defRPr sz=\"1400\"/></a:pPr></a:p></c:txPr></c:valAx>"
            "</c:plotArea><c:legend><c:legendPos val=\"b\"/></c:legend></c:chart></c:chartSpace>")

    @staticmethod
    def _mk(cxml):
        class C:
            _chartSpace = type("CS", (), {"xml": cxml})
        class SH:
            has_chart = True
            shape_type = "CHART"
            width = 4000000
            height = 3000000
            name = "图表"
            chart = C()
        class S:
            shapes = [SH()]
        return S()

    RULES = {"enabled": True, "area_ratio": {"min": 0.15, "max": 0.60},
             "axis_label_min_pt": 12.0, "legend_required": True}

    def test_axis_label_below_min_is_flagged(self):
        out = vd.check_chart_layout(self._mk(self.BAD), 3, self.RULES, 10 ** 8)
        types = [o["type"] for o in out]
        self.assertIn("图表轴标注字号过小", types)

    def test_multi_series_without_legend_is_flagged(self):
        out = vd.check_chart_layout(self._mk(self.BAD), 3, self.RULES, 10 ** 8)
        types = [o["type"] for o in out]
        self.assertIn("图表缺图例", types)

    def test_compliant_chart_not_flagged(self):
        out = vd.check_chart_layout(self._mk(self.GOOD), 4, self.RULES, 10 ** 8)
        types = [o["type"] for o in out]
        self.assertNotIn("图表轴标注字号过小", types)
        self.assertNotIn("图表缺图例", types)

    def test_absent_keys_means_no_judgement(self):
        """缺省键 = 不判（向后兼容：旧配置文件不含这两个键时行为不变）。"""
        rules = {"enabled": True, "area_ratio": {"min": 0.15, "max": 0.60}}
        out = vd.check_chart_layout(self._mk(self.BAD), 5, rules, 10 ** 8)
        types = [o["type"] for o in out]
        self.assertNotIn("图表轴标注字号过小", types)
        self.assertNotIn("图表缺图例", types)

    def test_self_closing_ser_counted(self):
        """ser 计数须兼容自闭合 <c:ser/>（第三轮盘点实测踩过：<c:ser> 计数为 0 的漏检）。"""
        import re
        self.assertEqual(len(re.findall(r"<c:ser(?=[\s/>])[^>]*>", "<c:ser/><c:ser/>")), 2)
        self.assertEqual(len(re.findall(r"<c:ser(?=[\s/>])[^>]*>", "<c:serX>")), 0)


class TestKeyDataSourceC5(unittest.TestCase):
    """v3.24.0：C5「关键数据注明来源」判据护栏。

    背景：`.learnings/FEATURE_REQUESTS.md` 的 [缺口] C5 条目——长期「暂无机器实现」。
    本版落地，判据三层收敛（指标语境 → 量值 → 来源邻近）。
    ⚠ **护栏重点在假阳性**：本包铁律「假阳性必须为零，否则门禁会被绕过」。
    实测基线（4 份真实动医课件）：
      · 全页 1071 个数字 → 仅 7 个段落命中指标语境（收敛比约 1/150）
      · 裸 4 位数字会把指标数字本身误当年份（宽判 2/14 vs 紧判 0/14）⇒ 已收紧
    """

    CFG = {"enabled": True, "scope": "paragraph_then_page"}

    def _run(self, rows):
        return vd._rubric_key_data_source(rows, self.CFG)

    def test_disabled_produces_nothing(self):
        """关闭时不产出任何条目（默认关闭 ⇒ 旧行为不变）。"""
        rows = [(1, "死亡率可达90%～100%")]
        out = vd._rubric_key_data_source(rows, {"enabled": False})
        self.assertEqual(out, [])

    def test_metric_without_source_is_flagged(self):
        """关键指标 + 量值 + 无来源 ⇒ 判红。"""
        rows = [(31, "发病后急剧死亡，死亡率可达90%～100%。")]
        out = self._run(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["check_id"], "key_data_source")
        self.assertEqual(out[0]["slide"], 31)

    def test_non_metric_numbers_not_flagged(self):
        """非指标语境的数字（25日龄 / 3天 / 2023年）⇒ **不判**（防假阳性）。"""
        rows = [
            (1, "25日龄白羽肉鸡"),
            (2, "病程3天"),
            (3, "2023年新版指南"),
            (4, "共12页"),
        ]
        self.assertEqual(self._run(rows), [])

    def test_strain_id_not_treated_as_measure(self):
        """株型编号（H5N1 / H7N9）**不算量值** ⇒ 不判（它们不需要来源）。"""
        rows = [(5, "由H5N1亚型引起，H7N9亦可感染")]
        self.assertEqual(self._run(rows), [])

    def test_source_marker_in_paragraph_suppresses(self):
        """同段落有来源标记 ⇒ 不判。"""
        rows = [(7, "死亡率可达90%（来源：农业农村部，2023年）")]
        self.assertEqual(self._run(rows), [])

    def test_source_marker_on_page_suppresses(self):
        """同页另一形状有来源标记 ⇒ 不判（页级回退作用域）。"""
        rows = [
            (9, "死亡率可达90%"),
            (9, "来源：WHO, 2022年"),
        ]
        self.assertEqual(self._run(rows), [])

    def test_bare_four_digit_number_is_not_a_year(self):
        """裸 4 位数字**不**算年份（实测假阳性源：宽判 2/14 → 紧判 0/14）。

        取证口径：宽判（裸 `\\d{4}`）会把段落里的指标数字本身误当年份 ⇒ 假阳性。
        本例段落含真实量值（90%），但「2024」裸数字**不构成来源标记**
        ⇒ 仍应判红（证明年份未被误认）。
        """
        rows = [(11, "日龄越小发病率、死亡率越高，死亡率可达90%，2024")]
        out = self._run(rows)
        self.assertEqual(len(out), 1)
        # 反向对照：把「2024」换成「2024年」⇒ 应被认作来源标记 ⇒ 不判红
        rows_ok = [(11, "日龄越小发病率、死亡率越高，死亡率可达90%，2024年")]
        self.assertEqual(self._run(rows_ok), [])

    def test_one_entry_per_page(self):
        """同页多个未标源段落 ⇒ 只出一条（防刷屏）。"""
        rows = [
            (20, "死亡率可达90%"),
            (20, "保护率仅50%"),
            (20, "感染率30%"),
        ]
        out = self._run(rows)
        self.assertEqual(len(out), 1)

    def test_measure_display_excludes_strain_numbers(self):
        """展示的量值不应混入株型编号（H5N1 里的 5）。"""
        rows = [(31, "H5N1引起，发病后死亡率可达90%～100%。")]
        out = self._run(rows)
        self.assertEqual(len(out), 1)
        self.assertIn("90%", out[0]["detail"])
        self.assertNotIn("（5、", out[0]["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

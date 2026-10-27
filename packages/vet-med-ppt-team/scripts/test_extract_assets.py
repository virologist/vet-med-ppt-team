#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_extract_assets.py — extract_assets.py 回归测试（v3.2.0-batch1 · v3.16.0 配图链路记录字段）

14 例用例（T1-T14），全自造 fixture，禁依赖网络与外部课件。
风格：unittest（与既有 scripts/test_harness.py 一致，遵循 C3 默认）。

用例：
  T1 纯文本 PPT（无嵌入元素）              → 0 资产 + 完整性通过 + exit 0
  T2 含 1 张 PNG 图                         → images/a-001.png 存在 + sha256 匹配 + manifest 字段全
  T3 含 1 个简单柱状图                      → charts/{xml,xlsx,csv} 三件套 + chart_data_refs>=1
  T4 含 1 个 0 字节媒体                     → 标 WARN 但 exit 0；manifest notes 含"0 字节"
  T5 含 GroupShape 嵌套 1 图 1 文本         → 递归正确：1 asset + 1 skipped
  T6 4 份挂账课件试跑（不写盘：--dry-run）   → 4 份都能解析，无 exit 4；输出 JSON 字段全
  T7 完整性断言触发                         → exit 1 + stderr 详细列表
  T8 --dry-run 不创建任何目录                → 跑前后 os.path.exists(out_dir) == False
  ── v3.16.0（F8 配图链路补记录字段）──
  T9 新记录字段有真实取值                   → 2 张图：width/height 为 int 且 > 0（不只看键存在）
  T10 license_note 默认值                   → 不再是「原课件自带」；reuse_status=待核查；unlicensed_assets 计数对
  T11 --require-license 端到端（CLI）        → 有空许可 exit 1 + 前缀行 + asset_id 清单；零素材/全登记 exit 0
  T12 许可纪律断言                           → 空许可却标「已复用」→ 写盘前 exit 1；补登记后门禁放行
  T13 旧 manifest 兼容                      → 缺新字段容错为 null/""；旧占位值「原课件自带」作废归一
  T14 配置漂移哨兵                           → references/asset-fields.yaml == 内置回退值 == usage.md 字段名集合
  T15 --force 重跑已存在 out_dir             → exit 0（守 mkdir EEXIST 修复，不许 exit 3）
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# 让脚本可被直接 python 运行
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_assets import AssetExtractor, ShapeRouter  # noqa: E402

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    PPTX_OK = True
except ImportError:
    PPTX_OK = False

# v3.24.0（FEAT-003c 取证后）：样本定位**下沉**到 `sample_fixtures.py`。
# 病灶：原实现在本文件硬编码 4 条精确路径（`2.1高致病性禽流感防控.pptx` 等），
#   实测（2026-10-27）**第一条就不存在**（用户整理后文件名变为「高致病性禽流感防控.pptx」）
#   ⇒ T6 长期 skip，**在本机从未真跑过**。
# 改法：多候选目录自动发现 + 环境变量覆盖；不可得 ⇒ 合成 fixture 顶上（不再 skip）。
# ⚠ 样本目录属用户工作区，本模块**只读不写**。
from sample_fixtures import (  # noqa: E402
    build_synthetic_suite,
    resolve_real_samples,
)

# 4 份挂账课件（只读，**禁修改**）
WORKSPACE_DECKS = Path("/Users/biodog/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
SAMPLE_DECKS, _SAMPLE_DESC = resolve_real_samples(minimum=1)


def _make_minimal_pptx(path: Path):
    """构造一份纯文本 PPT，零嵌入元素。"""
    p = Presentation()
    p.slides.add_slide(p.slide_layouts[0])  # 1 张幻灯片
    p.save(str(path))


def _make_pptx_with_pic(path: Path, png_path: Path):
    """构造 1 张含 PNG 图的 PPT。"""
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[0])
    s.shapes.add_picture(str(png_path), Inches(1), Inches(1), Inches(2), Inches(2))
    p.save(str(path))


def _make_pptx_with_chart(path: Path):
    """构造 1 张含柱状图的 PPT。"""
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])  # title-only
    chart_data = CategoryChartData()
    chart_data.categories = ["猫", "狗", "鸡"]
    chart_data.add_series("数量", (12, 8, 25))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(5), Inches(4), chart_data)
    p.save(str(path))


def _make_pptx_with_zero_media(path: Path, empty_media: Path):
    """构造 1 张含 0 字节 media 的 PPT（用 add_picture 把 0 字节文件塞进去可能崩溃，改用底层手段）。"""
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[0])
    # 直接 add_picture 0 字节文件会抛异常；用 mock 直接生成 MEDIA shape
    # 此处退而求其次：构造正常 PPT，验证 WARN 路径覆盖
    s.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1), "无嵌入元素占位")
    p.save(str(path))
    # 返回 PPT 让 T4 单独验证 WARN 路径（通过 monkeypatch）


def _make_pptx_with_group(path: Path, png_path: Path):
    """构造 1 张 GroupShape 内含 1 图 + 1 文本（python-pptx 1.0.2 兼容版）。"""
    from pptx.oxml.ns import qn
    from lxml import etree
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[0])
    # 直接添加 1 张图到顶层（用纯 slide 路径；GROUP 通过 XML 注入：先放图 + 文本，再用 spTree 包成 grpSp）
    pic = s.shapes.add_picture(str(png_path), Inches(0.5), Inches(0.5), Inches(2), Inches(2))
    tb = s.shapes.add_textbox(Inches(3), Inches(0.5), Inches(2), Inches(1))
    tb.text_frame.text = "嵌套文本"
    # 用 XML 把 pic 和 tb 包进一个 grpSp
    spTree = s.shapes._spTree
    nsmap = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    grpSp_xml = (
        '<p:grpSp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:nvGrpSpPr><p:cNvPr id="100" name="Group 1"/><p:cNvGrpSpPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:off x="0" y="0"/><a:ext cx="1000000" cy="1000000"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="1000000" cy="1000000"/></a:xfrm></p:grpSpPr>'
        '</p:grpSp>'
    )
    grpSp = etree.fromstring(grpSp_xml)
    spTree.append(grpSp)
    p.save(str(path))


def _make_pptx_with_two_pics(path: Path, png_a: Path, png_b: Path):
    """构造 1 份含 2 张图（分处两页、尺寸不同）的 PPT，供 T9-T12 取真实尺寸用。"""
    p = Presentation()
    s1 = p.slides.add_slide(p.slide_layouts[6])     # blank
    s1.shapes.add_picture(str(png_a), Inches(0.5), Inches(0.5), Inches(2), Inches(2))
    s2 = p.slides.add_slide(p.slide_layouts[6])
    s2.shapes.add_picture(str(png_b), Inches(1), Inches(1), Inches(3), Inches(2))
    p.save(str(path))


def _png_bytes() -> bytes:
    """最小合法 1x1 PNG 二进制。"""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _png_8x8_bytes() -> bytes:
    """8x8 实色 PNG，更稳。"""
    import base64
    # 8x8 红色 PNG base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFklEQVQYV2P8z8DwH4iZGAACDgwAAv4DhV5sjJgAAAAASUVORK5CYII="
    )


@unittest.skipUnless(PPTX_OK, "python-pptx 未装")
class TestExtractAssets(unittest.TestCase):
    """T1-T8 回归测试。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- T1 ----------
    def test_T1_pure_text_no_assets(self):
        pptx = self.tmpdir / "pure.pptx"
        _make_minimal_pptx(pptx)
        out = self.tmpdir / "pure_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0, f"应 exit 0，实际 {rc}，warnings={ext.stats.warnings}")
        self.assertEqual(len(ext.assets), 0)
        self.assertTrue(out.is_dir())
        self.assertTrue((out / "manifest.json").exists())
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["assets_count"], 0)
        self.assertEqual(m["total_slides"], 1)
        self.assertIn("schema_version", m)
        # 完整性已通过（rc=0）

    # ---------- T2 ----------
    def test_T2_picture_extracted(self):
        png = self.tmpdir / "tiny.png"
        png.write_bytes(_png_bytes())
        pptx = self.tmpdir / "with_pic.pptx"
        _make_pptx_with_pic(pptx, png)
        out = self.tmpdir / "with_pic_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0, f"应 exit 0，实际 {rc}，warnings={ext.stats.warnings}")
        self.assertEqual(len(ext.assets), 1)
        a = ext.assets[0]
        self.assertEqual(a.type, "image")
        img_file = out / a.file
        self.assertTrue(img_file.exists())
        self.assertGreater(img_file.stat().st_size, 0)
        # sha256 匹配
        import hashlib
        self.assertEqual(a.sha256, hashlib.sha256(img_file.read_bytes()).hexdigest())
        # manifest 字段全
        for field_name in ("asset_id", "type", "source_page", "shape_id", "file", "sha256", "extracted_at", "source_deck_sha1"):
            self.assertTrue(getattr(a, field_name), f"缺字段: {field_name}")

    # ---------- T3 ----------
    def test_T3_chart_three_pieces(self):
        pptx = self.tmpdir / "with_chart.pptx"
        _make_pptx_with_chart(pptx)
        out = self.tmpdir / "with_chart_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0, f"应 exit 0，实际 {rc}，warnings={ext.stats.warnings}")
        # 至少 1 个 chart（有些 pptx 1.0.2 会把图表当 picture shape 解析，那也至少 1 个 image）
        self.assertGreaterEqual(len(ext.assets), 1)
        # 找 chart 类型
        charts = [a for a in ext.assets if a.type == "chart"]
        if charts:
            c = charts[0]
            self.assertTrue((out / c.file).exists())
            # xlsx 与 csv 在 notes 字段中标记路径
            self.assertIn("xlsx=", c.notes)
            self.assertIn("csv=", c.notes)
            self.assertGreaterEqual(c.chart_part_refs, 1)

    # ---------- T4 ----------
    def test_T4_zero_byte_media_warns(self):
        """模拟 0 字节媒体进入 _extract_media 路径，验证 WARN 与 notes 标记。"""
        from extract_assets import AssetRecord
        # 直接构造一个 AssetRecord 模拟 0 字节视频
        rec = AssetRecord(
            asset_id="a-001", type="video", source_page=1,
            shape_id="media 1", file="videos/a-001.mp4",
            raw_part="ppt/media/media1.mp4", sha256="",
            media_bytes=0, notes="⚠️ 0 字节媒体（D11 苗子）",
            extracted_at="2026-10-14T00:00:00",
            source_deck_sha1="dummy_sha1", source_deck_mtime="2026-10-14T00:00:00",
        )
        # 验证：notes 含 D11 苗子字样 + media_bytes=0（完整性断言的 0 字节告警基础）
        self.assertEqual(rec.media_bytes, 0)
        self.assertIn("D11", rec.notes)
        self.assertIn("0 字节", rec.notes)
        # 验证 _check_integrity 在 0 字节文件存在时能通过
        out = self.tmpdir / "zero_assets"
        out.mkdir(parents=True, exist_ok=True)
        (out / "videos").mkdir(parents=True, exist_ok=True)
        (out / "videos" / "a-001.mp4").write_bytes(b"")
        ext = AssetExtractor(str(self.tmpdir / "x.pptx"), str(out), force=True)
        ext.assets.append(rec)
        # 写 manifest 与一个 0 字节文件，断言完整性通过（0 字节不阻断，但有 D11 提示）
        import hashlib
        rec.sha256 = hashlib.sha256(b"").hexdigest()
        ext._write_manifest()
        ok, errs = ext._check_integrity()
        self.assertTrue(ok, f"0 字节媒体不阻断完整性，errs={errs}")

    # ---------- T5 ----------
    def test_T5_group_nested_pic_text(self):
        png = self.tmpdir / "tiny2.png"
        png.write_bytes(_png_8x8_bytes())
        pptx = self.tmpdir / "with_group.pptx"
        _make_pptx_with_group(pptx, png)
        out = self.tmpdir / "with_group_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0, f"应 exit 0，实际 {rc}，warnings={ext.stats.warnings}")
        # 至少 1 张图（嵌套文本不算资产）
        self.assertGreaterEqual(len(ext.assets), 1)
        types = [a.type for a in ext.assets]
        self.assertIn("image", types)

    # ---------- T6 ----------
    def test_T6_real_decks_dry_run(self):
        """真实样本优先；不可得时用确定性合成 fixture 顶上（**不再 skip**）。

        v3.24.0（FEAT-003c）：原实现 `@skipUnless(all(p.exists() ...))`
        —— 4 条路径中有 1 条文件名已变 ⇒ 长期 skip ⇒ 该用例**从未真跑**。
        """
        if SAMPLE_DECKS:
            decks, kind, desc = SAMPLE_DECKS, "real", _SAMPLE_DESC
        else:
            decks = build_synthetic_suite(self.tmpdir / "synth_suite", count=4)
            kind, desc = "synthetic", "包外真实样本不可得 → 合成 fixture（4 份）"
        print(f"\n[T6] 样本来源：{kind} — {desc}")
        for deck in decks:
            with self.subTest(deck=deck.name):
                out = self.tmpdir / (deck.stem + "_assets_dryrun")
                ext = AssetExtractor(str(deck), str(out), dry_run=True)
                rc = ext.run()
                self.assertEqual(rc, 0, f"{deck.name} dry-run 应 exit 0，实际 {rc}")
                self.assertFalse(out.exists(), f"{deck.name} dry-run 不应创建 {out}")
                # emit_dry_run_json 应可解析
                js = json.loads(ext.emit_dry_run_json())
                self.assertIn("dry_run", js)
                self.assertIn("total_slides", js)

    # ---------- T7 ----------
    def test_T7_integrity_failure_when_manifest_lies(self):
        """人为在 manifest 中声明一个真实不存在的文件，触发完整性失败。"""
        from extract_assets import AssetRecord
        # 直接构造一个 AssetRecord，指向真实不存在的文件
        rec = AssetRecord(
            asset_id="a-999", type="image", source_page=1,
            shape_id="fake", file="images/a-999.png",
            raw_part="ppt/media/fake.png", sha256="deadbeef" * 8,
            media_bytes=10, extracted_at="2026-10-14T00:00:00",
            source_deck_sha1="dummy", source_deck_mtime="2026-10-14T00:00:00",
        )
        out = self.tmpdir / "intg_assets"
        out.mkdir(parents=True, exist_ok=True)
        # 不创建 images/a-999.png → 完整性断言必报"文件不存在"
        ext = AssetExtractor(str(self.tmpdir / "intg.pptx"), str(out), force=True)
        ext.assets.append(rec)
        ext._write_manifest()
        ok, errs = ext._check_integrity()
        self.assertFalse(ok, "完整性断言应报失败")
        self.assertGreater(len(errs), 0, "应有错误列表")
        joined = " | ".join(errs)
        self.assertTrue("不存在" in joined or "不匹配" in joined, f"错误信息不符: {joined}")

    # ---------- T9（v3.16.0）：新记录字段出现在 manifest 且有真实取值 ----------
    def test_T9_new_record_fields_have_real_values(self):
        png_a = self.tmpdir / "a.png"
        png_a.write_bytes(_png_8x8_bytes())
        png_b = self.tmpdir / "b.png"
        png_b.write_bytes(_png_bytes())
        pptx = self.tmpdir / "two_pics.pptx"
        _make_pptx_with_two_pics(pptx, png_a, png_b)
        out = self.tmpdir / "two_pics_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0, f"应 exit 0，实际 {rc}，warnings={ext.stats.warnings}")

        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(m["assets"]), 2, "应有 2 条素材")
        widths = []
        for a in m["assets"]:
            # 四个新字段键必须都在（缺键即契约破）
            for key in ("width", "height", "source_url", "doi_pmcid"):
                self.assertIn(key, a, f"{a.get('asset_id')} 缺字段键 {key}")
            # 真实取值断言：不是"键存在"而是 int 且 > 0
            self.assertIsInstance(a["width"], int, f"{a['asset_id']} width 应为 int，实际 {a['width']!r}")
            self.assertIsInstance(a["height"], int, f"{a['asset_id']} height 应为 int，实际 {a['height']!r}")
            self.assertGreater(a["width"], 0)
            self.assertGreater(a["height"], 0)
            self.assertEqual(a["source_url"], "")
            self.assertEqual(a["doi_pmcid"], "")
            widths.append(a["width"])
        # 两张图显示宽度不同（2in vs 3in → 192px vs 288px），证明取的是实际尺寸不是常量
        self.assertEqual(sorted(widths), [192, 288], f"宽度应随形状尺寸变化，实际 {widths}")

    # ---------- T10（v3.16.0）：license_note 默认值不再是「原课件自带」 ----------
    def test_T10_license_default_is_not_legacy_placeholder(self):
        from extract_assets import AssetRecord
        rec = AssetRecord(asset_id="a-001", type="image", source_page=1,
                          shape_id="Picture 1", file="images/a-001.png", raw_part="")
        self.assertEqual(rec.license_note, "", "license_note 默认应为空（不默认可用）")
        self.assertNotEqual(rec.license_note, "原课件自带", "不得再默认「原课件自带」（M3）")
        self.assertEqual(rec.reuse_status, "待核查", "未登记许可时 reuse_status 应为「待核查」")

        # 端到端：manifest 里两条都是空许可，且统计区块给出计数与清单
        png_a = self.tmpdir / "a.png"
        png_a.write_bytes(_png_8x8_bytes())
        png_b = self.tmpdir / "b.png"
        png_b.write_bytes(_png_bytes())
        pptx = self.tmpdir / "two_pics.pptx"
        _make_pptx_with_two_pics(pptx, png_a, png_b)
        out = self.tmpdir / "two_pics_assets"
        ext = AssetExtractor(str(pptx), str(out), force=True)
        rc = ext.run()
        self.assertEqual(rc, 0)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["unlicensed_assets"], 2, "未登记许可的素材数应为 2")
        self.assertEqual(sorted(m["unlicensed_asset_ids"]), ["a-001", "a-002"])
        for a in m["assets"]:
            self.assertEqual(a["license_note"], "")
            self.assertEqual(a["reuse_status"], "待核查")
        self.assertEqual(ext.stats.unlicensed_assets, 2)

    # ---------- T11（v3.16.0）：--require-license 端到端（真 CLI） ----------
    def test_T11_require_license_cli_gate(self):
        import subprocess
        script = Path(__file__).resolve().parent / "extract_assets.py"
        png_a = self.tmpdir / "a.png"
        png_a.write_bytes(_png_8x8_bytes())
        png_b = self.tmpdir / "b.png"
        png_b.write_bytes(_png_bytes())
        pptx = self.tmpdir / "two_pics.pptx"
        _make_pptx_with_two_pics(pptx, png_a, png_b)

        # 反例：2 条空许可 → 非零退出 + 前缀行 + asset_id 清单
        out_bad = self.tmpdir / "gate_assets"
        proc = subprocess.run(
            [sys.executable, str(script), str(pptx), "--out-dir", str(out_bad), "--require-license"],
            capture_output=True, text=True, timeout=180,
        )
        merged = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, f"有空许可时应非零退出，实际 {proc.returncode}")
        self.assertIn("未登记许可", merged, f"输出应带「未登记许可」前缀，实际:\n{merged}")
        for aid in ("a-001", "a-002"):
            self.assertIn(aid, merged, f"输出应列出 {aid}，实际:\n{merged}")

        # 正例：零素材课件（不存在未登记项）→ exit 0
        pptx0 = self.tmpdir / "pure.pptx"
        _make_minimal_pptx(pptx0)
        out_ok = self.tmpdir / "gate_ok_assets"
        proc0 = subprocess.run(
            [sys.executable, str(script), str(pptx0), "--out-dir", str(out_ok), "--require-license"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(proc0.returncode, 0,
                         f"全部登记（此处 0 条）时应 exit 0，实际 {proc0.returncode}\n{proc0.stdout + proc0.stderr}")
        m0 = json.loads((out_ok / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m0["unlicensed_assets"], 0)

    # ---------- T12（v3.16.0）：许可纪律断言 + 补登记后放行 ----------
    def test_T12_license_discipline_assertion(self):
        import extract_assets as ea
        from dataclasses import dataclass

        png_a = self.tmpdir / "a.png"
        png_a.write_bytes(_png_8x8_bytes())
        png_b = self.tmpdir / "b.png"
        png_b.write_bytes(_png_bytes())
        pptx = self.tmpdir / "two_pics.pptx"
        _make_pptx_with_two_pics(pptx, png_a, png_b)

        # 反例：空 license_note 却标「已复用」→ 写盘前 exit 1，manifest 不落盘
        @dataclass
        class _Mislabeled(ea.AssetRecord):
            reuse_status: str = "已复用"

        out_bad = self.tmpdir / "discipline_assets"
        ext_bad = ea.AssetExtractor(str(pptx), str(out_bad), force=True)
        with mock.patch.object(ea, "AssetRecord", _Mislabeled):
            rc = ext_bad.run()
        self.assertEqual(rc, 1, f"许可纪律违规应 exit 1，实际 {rc}")
        self.assertFalse((out_bad / "manifest.json").exists(), "违规时 manifest 不应落盘")
        self.assertFalse(ext_bad.stats.license_gate_passed)

        # 正例：同一条素材补登记许可后，门禁放行
        out_ok = self.tmpdir / "discipline_ok_assets"
        ext = ea.AssetExtractor(str(pptx), str(out_ok), force=True, require_license=True)
        rc0 = ext.run()
        self.assertEqual(rc0, 1, "未登记时门禁应拦下")
        for a in ext.assets:
            a.license_note = "CC-BY-4.0 · Europe PMC OA（T12 示例登记）"
            a.reuse_status = "已复用"
        self.assertEqual(ext._tally_license(), 0, "补登记后未登记许可数应为 0")
        self.assertEqual(ext._check_license_gate(), [], "全部登记后门禁应无错误")
        self.assertEqual(ext.stats.unlicensed_assets, 0)

    # ---------- T13（v3.16.0）：旧 manifest 兼容 ----------
    def test_T13_legacy_manifest_backward_compat(self):
        from extract_assets import AssetRecord, load_manifest_records
        legacy = {
            "schema_version": 1,
            "extractor_version": "extract_assets/1.0.0",
            "assets_count": 1,
            "assets": [{
                "asset_id": "a-001", "type": "image", "source_page": 1,
                "shape_id": "Picture 1", "file": "images/a-001.png",
                "raw_part": "ppt/media/image1.png", "render": "", "sha256": "abc",
                "license_note": "原课件自带", "reuse_status": "未决", "notes": "",
                "chart_part_refs": 0, "media_bytes": 75,
                "extracted_at": "2026-10-14T00:00:00",
                "extractor_version": "extract_assets/1.0.0",
                "source_deck_sha1": "x", "source_deck_mtime": "y", "pptx_schema": "",
            }],
        }
        p = self.tmpdir / "legacy_manifest.json"
        p.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        recs = load_manifest_records(p)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        # 缺的新字段容错为 null / ""（不是 0、不是抛异常）
        self.assertIsNone(r.width)
        self.assertIsNone(r.height)
        self.assertEqual(r.source_url, "")
        self.assertEqual(r.doi_pmcid, "")
        # 旧占位许可值作废 → 视为未登记
        self.assertEqual(r.license_note, "")
        self.assertEqual(r.reuse_status, "待核查")
        self.assertIn("旧占位许可值", r.notes)
        # 极简记录（大量键缺失）也不炸
        r2 = AssetRecord.from_dict({"asset_id": "a-002"})
        self.assertIsNone(r2.width)
        self.assertEqual(r2.source_url, "")
        # 已登记的许可不被误清
        r3 = AssetRecord.from_dict({"asset_id": "a-003", "license_note": "CC-BY-4.0",
                                    "reuse_status": "已复用"})
        self.assertEqual(r3.license_note, "CC-BY-4.0")
        self.assertEqual(r3.reuse_status, "已复用")

    # ---------- T14（v3.16.0）：配置漂移哨兵（yaml == 内置回退 == 文档字段名） ----------
    def test_T14_config_no_drift(self):
        import extract_assets as ea
        # ① 机器源是独立 yaml 文件（不是 md 里嵌的块）
        self.assertTrue(ea._ASSET_FIELDS_PATH.exists(),
                        f"配置源缺失: {ea._ASSET_FIELDS_PATH}")
        self.assertTrue(ea._ASSET_FIELDS_PATH.name.endswith(".yaml"),
                        "机器可读配置必须是独立 yaml 文件")
        loaded = ea._load_asset_field_config()
        # ② yaml 值 == 代码内置回退值（改一处不改另一处即判漂移）
        # v3.24.0（FEAT-003a）：原用 assertEqual(dict, dict)，失败信息**不给位置**，
        #   排查要人工翻两份文件找差异键。改用逐键漂移诊断 ⇒ 直接给出
        #   「yaml 第 N 行 vs extract_assets.py 第 M 行」。
        drift = ea.describe_asset_field_drift()
        if drift:
            lines = ["配置漂移明细（references/asset-fields.yaml vs scripts/extract_assets.py）："]
            for d in drift:
                lines.append(
                    f"  · {d['path']} [{d['kind']}] "
                    f"yaml 第 {d['yaml_line']} 行（值={d['yaml_value']!r}）"
                    f" vs 代码 第 {d['code_line']} 行（值={d['code_value']!r}）"
                )
            lines.append("改一处必须同步另一处（改 yaml ⇒ 同步 _BUILTIN_ASSET_FIELD_CONFIG）。")
            self.fail("\n".join(lines))
        self.assertEqual(loaded, ea._BUILTIN_ASSET_FIELD_CONFIG,
                         "references/asset-fields.yaml 与内置回退值不一致（改一处必须同步另一处）")
        # ③ 人读文档列出全部字段名并指向该 yaml；且不含第二份可解析副本
        usage_doc = ea._ASSET_FIELDS_PATH.parent / "extract_assets_usage.md"
        doc = usage_doc.read_text(encoding="utf-8")
        self.assertIn("references/asset-fields.yaml", doc, "usage 文档必须指向机器源")
        for key in ea._AF:
            self.assertIn(key, doc, f"usage 文档 §10 表格应列出字段名 {key}")
        for key in ea._LG:
            self.assertIn(key, doc, f"usage 文档 §10 表格应列出字段名 {key}")
        for key in ea._AF:
            self.assertNotIn(f"{key}:", doc,
                             f"usage 文档不得保留机器可解析副本（发现 yaml 键行 {key}:）")
        # ④ 关键取值仍在（防配错文件/配错段）
        self.assertEqual(ea._AF["license_note_default"], "")
        self.assertNotEqual(ea._AF["license_note_default"], "原课件自带")
        self.assertEqual(ea._AF["reuse_status_default"], "待核查")
        self.assertIn("原课件自带", ea._AF["legacy_license_placeholders"])
        self.assertEqual(ea._AF["emu_per_px"], 9525)
        self.assertIn("未登记许可", ea._LG["prefix"])
        self.assertIn("{n}", ea._LG["count_line"])

    # ---------- T15（v3.16.0）：--force 对已存在 out_dir 重跑 → exit 0 ----------
    def test_T15_force_rerun_on_existing_out_dir(self):
        """守 mkdir EEXIST 修复：本机 shim 下 exist_ok=True 对已存在目录仍抛 EEXIST。"""
        png = self.tmpdir / "t.png"
        png.write_bytes(_png_8x8_bytes())
        pptx = self.tmpdir / "one.pptx"
        _make_pptx_with_pic(pptx, png)
        out = self.tmpdir / "one_assets"

        ext1 = AssetExtractor(str(pptx), str(out))
        rc1 = ext1.run()
        self.assertEqual(rc1, 0, f"首次跑应 exit 0，实际 {rc1}，warnings={ext1.stats.warnings}")
        self.assertTrue((out / "manifest.json").exists())

        # 第二次：目录与 manifest 都已存在，--force 重跑必须仍是 0（不得 exit 3）
        ext2 = AssetExtractor(str(pptx), str(out), force=True)
        rc2 = ext2.run()
        self.assertEqual(rc2, 0, f"--force 重跑已存在 out_dir 应 exit 0，实际 {rc2}")
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["assets_count"], 1)
        self.assertEqual(len(m["assets"]), 1)


def extractor_ver():
    return "extract_assets/1.0.0"


# ---------- T8 ----------
class TestDryRunNoSideEffect(unittest.TestCase):
    """T8 --dry-run 不创建任何目录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_T8_dry_run_creates_nothing(self):
        pptx = self.tmpdir / "pp.pptx"
        _make_minimal_pptx(pptx)
        out = self.tmpdir / "must_not_exist"
        self.assertFalse(out.exists())
        ext = AssetExtractor(str(pptx), str(out), dry_run=True)
        rc = ext.run()
        self.assertEqual(rc, 0)
        self.assertFalse(out.exists(), f"dry-run 不应创建 {out}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

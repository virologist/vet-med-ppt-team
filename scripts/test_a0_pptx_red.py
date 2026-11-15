#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# b2026111505 · A0-批2「PPTX 产物 / 路径过滤 / 同行多图」能红反例（v3.31.3 内整改）
#
# 本文件 6 条用例盯的是「报告说改了但产物没改」与「路径规则误杀整包」两类缺陷：
#   在修复前的旧代码上必须失败（能红），在修复后的新代码上必须全部通过。
#   - theme_fingerprint._active_deck：隐藏目录判定把扫描根自身的安装路径算进去，
#     包内所有 .pptx 被当归档排除（本包恰好装在 ~/.workbuddy/... 下）。
#   - deck_surgery.NORMID_RE：\b 在中文紧邻处不成立 ⇒「依据GB30000」漏检。
#   - deck_surgery.fix_normid：算出 new 只记报告、不写 run ⇒ 报告与产物不一致。
#   - deck_surgery.fix_superscript：lxml .get() 缺属性返回 None 不抛异常 ⇒ 恒 continue。
#   - fix_md_image_refs：rewrite[line_no] 直接覆盖 ⇒ 同一行多个图片引用只保留最后一个。
# 运行方式（在 scripts/ 目录下）：python3 -m unittest -v test_a0_pptx_red
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deck_surgery import NORMID_RE, fix_normid, fix_superscript  # noqa: E402
from fix_md_image_refs import fix_refs  # noqa: E402
from theme_fingerprint import _active_deck, batch_report  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DECK_SURGERY_PY = os.path.join(HERE, "deck_surgery.py")
PY = sys.executable


def _make_deck(path: Path, text: str) -> None:
    """造一页含单个文本框的最小 PPTX（不依赖包外课件）。"""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
    box.text_frame.text = text
    prs.save(str(path))


def _is_active(p, root):
    """兼容旧版单参签名，让反例在旧码上以「行为判红」而非 TypeError 判红。"""
    try:
        return _active_deck(p, root)
    except TypeError:
        return _active_deck(p)      # 旧实现：只有单参，按旧口径跑


def _runs(path_or_prs):
    prs = path_or_prs if not isinstance(path_or_prs, (str, Path)) else Presentation(str(path_or_prs))
    for slide in prs.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    yield run


class A0PptxRedTest(unittest.TestCase):
    """A0-批2 能红反例集合。"""

    def setUp(self):
        # 扫描根故意放在「. 开头隐藏目录」里，复现本包 ~/.workbuddy/... 安装形态
        self.tmp = Path(tempfile.mkdtemp(prefix=".hidden_pkg_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- T1：隐藏安装根不应误杀包内课件 ----------
    def test_T1_hidden_install_root_keeps_active_decks(self):
        live = self.tmp / "example_decks"
        live.mkdir()
        _make_deck(live / "lesson.pptx", "教学课件")
        p = live / "lesson.pptx"
        self.assertTrue(_is_active(p, self.tmp),
                        "扫描根之下无隐藏子目录，应判活跃（旧实现把安装路径的 . 开头段误杀）")
        rep = batch_report(self.tmp)
        self.assertGreaterEqual(rep["total_decks"], 1,
                                "batch_report 应统计到包内课件（旧实现恒 0 份）")

    # ---------- T2：快照 / 归档 / 临时文件仍须排除 ----------
    def test_T2_still_excludes_snapshots_trash_and_temp(self):
        for sub in (".snapshots", "_trash_old", "example_decks"):
            (self.tmp / sub).mkdir()
        _make_deck(self.tmp / ".snapshots" / "snap.pptx", "快照")
        _make_deck(self.tmp / "_trash_old" / "old.pptx", "归档")
        _make_deck(self.tmp / "example_decks" / "live.pptx", "活跃")
        _make_deck(self.tmp / "example_decks" / "~$tmp.pptx", "临时")
        self.assertFalse(_is_active(self.tmp / ".snapshots" / "snap.pptx", self.tmp))
        self.assertFalse(_is_active(self.tmp / "_trash_old" / "old.pptx", self.tmp))
        self.assertFalse(_is_active(self.tmp / "example_decks" / "~$tmp.pptx", self.tmp))
        self.assertEqual(batch_report(self.tmp)["total_decks"], 1,
                         "修复后仍须只统计 1 份活跃课件（不得放宽排除规则）")

    # ---------- T3：中文紧邻的国标编号必须命中，且不得误伤字母紧邻 ----------
    def test_T3_normid_regex_chinese_adjacent_no_false_positive(self):
        hits = [m.group(0) for m in NORMID_RE.finditer("依据GB30000与NY1234执行")]
        self.assertEqual(len(hits), 2, f"中文紧邻的 GB/NY 编号应命中 2 处，实际 {hits}")
        self.assertEqual([m.group(0) for m in NORMID_RE.finditer("XGB30000")], [],
                         "ASCII 字母紧邻的前缀不得被误判为国标编号")

    # ---------- T4：fix_normid 真实写回 run（端到端 --apply） ----------
    def test_T4_normid_cli_apply_really_writes_pptx(self):
        deck = self.tmp / "normid.pptx"
        _make_deck(deck, "依据GB30000与NY1234执行")
        res = subprocess.run(
            [PY, DECK_SURGERY_PY, "--deck", str(deck), "--fix", "normid", "--apply"],
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"CLI 应成功：stdout={res.stdout!r} stderr={res.stderr!r}")
        texts = [r.text for r in _runs(deck)]
        self.assertTrue(any("GB 30000" in t and "NY 1234" in t for t in texts),
                        f"--apply 后 PPTX 内文本应已规范化，实际 {texts}")

    # ---------- T5：上标候选应报告；显式 baseline 应跳过 ----------
    def test_T5_superscript_reports_then_skips_explicit_baseline(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
        box.text_frame.text = "剂量 12mL"
        stats, details = fix_superscript(prs, {})
        self.assertGreaterEqual(stats.get("reported", 0), 1,
                                "未设 baseline 的 12mL 应被报告（旧实现恒 continue ⇒ 0）")
        run = next(_runs(prs))
        rpr = getattr(run.font, "_rPr", None)
        self.assertIsNotNone(rpr, "python-pptx 应能取得 rPr")
        rpr.set("baseline", "30000")
        stats2, _ = fix_superscript(prs, {})
        self.assertEqual(stats2.get("reported", 0), 0,
                         "显式 baseline 已是上标，不应重复报告")

    # ---------- T6：同一行两个图片引用都要被重写 ----------
    def test_T6_same_line_two_refs_both_rewritten(self):
        md = self.tmp / "doc.md"
        md.write_text(
            "<!-- Slide number: 1 -->\n\n![a](x.jpg) ![a](x.jpg)\n",
            encoding="utf-8")
        assets = self.tmp / "_assets"
        (assets / "images").mkdir(parents=True)
        manifest = assets / "manifest.json"
        manifest.write_text(json.dumps({"assets": [
            {"asset_id": "a-001", "type": "image", "source_page": 1,
             "file": "images/a-001.png", "sha256": ""},
            {"asset_id": "a-002", "type": "image", "source_page": 1,
             "file": "images/a-002.png", "sha256": ""},
        ]}, ensure_ascii=False), encoding="utf-8")
        report, fixed_md = fix_refs(
            md, manifest, assets, self.tmp / "out.md",
            types=("image", "video"), link_mode="relative",
            deck_path=None, dry_run=True)
        self.assertEqual(report["counts"]["matched"], 2,
                         "两个引用都应匹配到资产")
        self.assertIn("a-001.png", fixed_md, "第 1 个引用被覆盖丢失")
        self.assertIn("a-002.png", fixed_md, "第 2 个引用应保留")

    # ---------- T7：fix_normid 函数级写回（不经 CLI） ----------
    def test_T7_normid_function_mutates_run(self):
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(2))
        box.text_frame.text = "依据GB30000执行"
        stats, details = fix_normid(prs, {})
        self.assertEqual(stats["changed"], 1, "应记 1 处变更")
        self.assertIn("GB 30000", next(_runs(prs)).text,
                      "run.text 必须真实写回（旧实现只记报告不改产物）")


if __name__ == "__main__":
    unittest.main(verbosity=2)

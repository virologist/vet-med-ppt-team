#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_fix_md_image_refs.py — fix_md_image_refs.py 回归测试（v3.8.2）

7 例用例（T1-T7），全自造 fixture，禁依赖网络与外部课件、禁依赖 markitdown 是否安装。
风格：unittest（与既有 scripts/test_extract_assets.py 一致）。

用例：
  T1 正常全匹配（页号+页内序号）        → 3/3 已解析 + 链接相对可解析 + exit 0
  T2 引用多于资产（缺图）               → missing_refs=1 + exit 1 + 原 ref 文本保留且带 REF-MISSING 标记
  T3 资产多于引用（孤立资产）           → orphan_assets=1 + exit 1
  T4 --out 与 --md 相同                 → exit 2（用法护栏，守"原始转换结果只读留存"）
  T5 绝对链接模式                       → new_link 为绝对路径
  T6 原始 md 不被改写                   → 修复前后原始 md 字节一致
  T7 sha256 证据优先                    → 磁盘 target 存在且哈希一致时 evidence=sha256
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SCRIPT = Path(__file__).resolve().parent / "fix_md_image_refs.py"
PY = sys.executable

try:                       # T8（GROUP 嵌套计数）依赖 python-pptx 造 deck
    from pptx import Presentation  # noqa: F401
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

# 与 markitdown 0.1.7 对 PPTX 的实测输出格式一致（见脚本头部实测基线）
MD_FIXTURE = """<!-- Slide number: 1 -->

![img1.png](Picture1.jpg)

<!-- Slide number: 2 -->

![img2.png](Picture1.jpg)

![img1.png](Picture2.jpg)
"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _asset(aid: str, page: int, fname: str, sha: str) -> dict:
    return {
        "asset_id": aid, "type": "image", "source_page": page,
        "shape_id": f"Picture {aid[-1]}", "file": fname,
        "raw_part": f"ppt/media/{Path(fname).name}", "sha256": sha,
    }


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fixrefs_test_"))
        self.assets = self.tmp / "_assets"
        (self.assets / "images").mkdir(parents=True)
        self.blobs = {}
        for aid, seed in (("a-001", b"R" * 32), ("a-002", b"B" * 32), ("a-003", b"R" * 32)):
            data = seed + aid.encode()
            self.blobs[aid] = data
            (self.assets / "images" / f"{aid}.png").write_bytes(data)
        self.manifest = self.assets / "manifest.json"
        self.manifest.write_text(json.dumps({
            "schema_version": 1,
            "source_deck": "/tmp/demo.pptx",
            "total_slides": 2,
            "assets": [
                _asset("a-001", 1, "images/a-001.png", _sha256_bytes(self.blobs["a-001"])),
                _asset("a-002", 2, "images/a-002.png", _sha256_bytes(self.blobs["a-002"])),
                _asset("a-003", 2, "images/a-003.png", _sha256_bytes(self.blobs["a-003"])),
            ],
        }, ensure_ascii=False), encoding="utf-8")
        self.md = self.tmp / "_raw" / "original.md"
        self.md.parent.mkdir(parents=True, exist_ok=True)
        self.md.write_text(MD_FIXTURE, encoding="utf-8")
        self.out = self.tmp / "_raw" / "original.refs.md"

    def _run(self, extra=None):
        cmd = [PY, str(SCRIPT), "--md", str(self.md), "--manifest", str(self.manifest),
               "--out", str(self.out)]
        if extra:
            cmd += extra
        proc = subprocess.run(cmd, capture_output=True, text=True)
        report_path = self.out.with_suffix(self.out.suffix + ".refs.json")
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
        return proc.returncode, report, proc.stdout + proc.stderr


class TestHappyPath(_Base):
    def test_t1_all_matched(self):
        rc, report, log = self._run()
        self.assertEqual(rc, 0, log)
        self.assertEqual(report["counts"]["refs_total"], 3)
        self.assertEqual(report["counts"]["matched"], 3)
        self.assertEqual(report["counts"]["missing_refs"], 0)
        # 链接相对输出文件可解析，且文件真实存在
        for m in report["matched"]:
            resolved = (self.out.parent / m["new_link"]).resolve()
            self.assertTrue(resolved.exists(), f"{m['new_link']} 解析后不存在")
        # alt 携带 asset_id，可回溯
        fixed = self.out.read_text(encoding="utf-8")
        self.assertIn("a-001", fixed)
        self.assertIn("a-003", fixed)
        self.assertNotIn("Picture1.jpg", fixed)

    def test_t5_absolute_link(self):
        rc, report, log = self._run(["--link-mode", "absolute"])
        self.assertEqual(rc, 0, log)
        for m in report["matched"]:
            self.assertTrue(os.path.isabs(m["new_link"]))
            self.assertTrue(Path(m["new_link"]).exists())


class TestNegative(_Base):
    def test_t2_missing_ref(self):
        # 第 1 页塞入第 2 条引用，而该页只有 1 个资产
        self.md.write_text(
            "<!-- Slide number: 1 -->\n\n![img1.png](Picture1.jpg)\n\n![ghost.png](Picture2.jpg)\n",
            encoding="utf-8")
        rc, report, log = self._run()
        self.assertEqual(rc, 1, log)
        self.assertEqual(report["counts"]["missing_refs"], 1)
        fixed = self.out.read_text(encoding="utf-8")
        self.assertIn("REF-MISSING", fixed)
        self.assertIn("ghost.png", fixed, "缺失引用必须保留原文本，不得留空链接或占位图")

    def test_t3_orphan_asset(self):
        # md 只引用第 1 页 1 张图 → 第 2 页两个资产成孤儿
        self.md.write_text("<!-- Slide number: 1 -->\n\n![img1.png](Picture1.jpg)\n", encoding="utf-8")
        rc, report, log = self._run()
        self.assertEqual(rc, 1, log)
        self.assertEqual(report["counts"]["orphan_assets"], 2)
        self.assertEqual({o["asset_id"] for o in report["orphan_assets"]}, {"a-002", "a-003"})

    def test_t4_out_equals_md(self):
        proc = subprocess.run(
            [PY, str(SCRIPT), "--md", str(self.md), "--manifest", str(self.manifest),
             "--out", str(self.md)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

    def test_t6_original_md_untouched(self):
        before = self.md.read_bytes()
        self._run()
        self.assertEqual(self.md.read_bytes(), before, "原始转换结果必须只读留存，不得被覆盖")


class TestEvidence(_Base):
    def test_t7_sha256_evidence(self):
        # 让 md 的 target 在磁盘真实存在且内容等于 a-001 → evidence 应为 sha256
        (self.md.parent / "Picture1.jpg").write_bytes(self.blobs["a-001"])
        rc, report, log = self._run()
        self.assertEqual(rc, 0, log)
        first = report["matched"][0]
        self.assertEqual(first["asset_id"], "a-001")
        self.assertEqual(first["evidence"], "sha256")


@unittest.skipUnless(PPTX_AVAILABLE, "python-pptx 未装，跳过 T8")
class TestNestedGroupCount(_Base):
    """T8（v3.10.1）：图片全在 GROUP 内时三方计数必须一致。

    真因记录：has_blip 用 `_element.iter()` 会把组合内子图片的 blip 算到组合头上，
    旧 walk() 又以 `has_blip(sh) is False` 作为递归前提 → 组合整体计 1 且不递归，
    deck=1 vs md/manifest=3 误报"计数不一致"。合成 fixture（顶层散图）测不出；
    **首次真实课件运行现形**（模板 slide1 三图全在组合内）。
    """

    def setUp(self):
        super().setUp()
        # 造一页 PPTX：三张图全部装进一个 GROUP（复刻真实模板 slide1 结构）
        from io import BytesIO
        from pptx import Presentation
        from pptx.util import Inches
        try:
            from PIL import Image
            buf = BytesIO()
            Image.new("RGB", (60, 40), (200, 30, 30)).save(buf, format="PNG")
            png_bytes = buf.getvalue()
        except ImportError:           # PIL 缺失时退化为最小合法 PNG（1×1 黑点）
            png_bytes = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
                         b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\n"
                         b"IDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
                         b"\x00\x00IEND\xaeB`\x82")
        tmp_png = self.tmp / "seed.png"
        tmp_png.write_bytes(png_bytes)
        prs = Presentation()
        # 页分布对齐 manifest：第 1 页 1 图（顶层），第 2 页 2 图（全部入组）
        s1 = prs.slides.add_slide(prs.slide_layouts[6])
        s1.shapes.add_picture(str(tmp_png), Inches(1), Inches(1), Inches(1), Inches(1))
        s2 = prs.slides.add_slide(prs.slide_layouts[6])
        grp = s2.shapes.add_group_shape()
        for i in range(2):
            grp.shapes.add_picture(str(tmp_png), Inches(1 + i), Inches(1), Inches(1), Inches(1))
        self.deck = self.tmp / "deck.pptx"
        prs.save(str(self.deck))

    def test_t8_group_nested_images_count(self):
        rc, report, log = self._run(extra=["--deck", str(self.deck)])
        self.assertEqual(rc, 0, log)
        self.assertEqual(report["counts"]["count_mismatches"], 0,
                         "组合内图片必须递归计数，三方应一致")
        mismatches = report.get("count_mismatches", [])
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

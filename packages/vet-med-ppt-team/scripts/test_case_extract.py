#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_case_extract.py — case_extract.py 回归测试 v3.2.0-batch4

T1  单页含"案例 1"被识别
T2  多页含"案例 1-5"被批量识别
T3  文本脱敏：人名/单位/地址
T4  病种映射：M4A1 → 禽流感
T5  同名去重：upsert_case 不重复
T6  三源核验：unverified 默认 True
T7  JSON 入库：save_library / load_library 往返一致
T8  --dry-run 不写文件
T9  注册后 audit 通过
T10 病种未识别（目录不在 M4-M7 范围）→ 返回空
T11 跨学科样本（测试脱敏但不映射）
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 注入 scripts 目录
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from case_extract import (  # noqa
    SCHEMA_VERSION, CaseDraft, audit_library, desensitize, extract_from_pptx,
    load_library, save_library, upsert_case, DISEASE_MAP,
)


# ─────────────────────── 脱敏测试（T3 / T11） ───────────────────────
class TestDesensitize(unittest.TestCase):
    def test_T3_desensitize(self):
        """人名+单位+地址全脱敏。"""
        src = "李老师 在 江苏泰州海陵区 的 王老板养殖场 看到病鸡"
        out = desensitize(src)
        self.assertNotIn("李老师", out)
        self.assertNotIn("王老板养殖场", out)
        self.assertNotIn("江苏泰州海陵区", out)
        self.assertIn("XX养殖场", out)
        self.assertIn("X省X市", out)

    def test_T11_cross_discipline(self):
        """跨学科样本：'XX 大学动物医院' 也命中（验证泛化）。"""
        src = "陈医生 在 XX大学动物医院 观察到异常"
        out = desensitize(src)
        self.assertNotIn("陈医生", out)


# ─────────────────────── 病种映射（T4 / T10） ───────────────────────
class TestDiseaseMap(unittest.TestCase):
    def test_T4_disease_map(self):
        self.assertEqual(DISEASE_MAP["M4A1"], "禽流感")
        self.assertEqual(DISEASE_MAP["M5A1"], "大肠杆菌病")
        self.assertEqual(DISEASE_MAP["M6A1"], "球虫")
        self.assertEqual(DISEASE_MAP["M7A"], "营养代谢病")

    def test_T10_unmapped_returns_empty(self):
        """非 M4-M7 目录名 → 提取返回空。"""
        with patch("pptx.Presentation") as mock_prs:
            mock_prs.return_value.slides = [MagicMock()]
            out = extract_from_pptx(Path("/tmp/random_dir/课件.pptx"))
            self.assertEqual(out, [])


# ─────────────────────── 提取测试（T1 / T2） ───────────────────────
def _mock_pptx_with_cases(slide_texts: list[str]):
    """造一个含 N 页文本的 mock Presentation。"""
    slides = []
    for text in slide_texts:
        slide = MagicMock()
        shape = MagicMock()
        run = MagicMock()
        run.text = text
        para = MagicMock()
        para.runs = [run]
        tf = MagicMock()
        tf.paragraphs = [para]
        shape.has_text_frame = True
        shape.text_frame = tf
        slide.shapes = [shape]
        slides.append(slide)
    prs = MagicMock()
    prs.slides = slides
    return prs


class TestExtractFromPptx(unittest.TestCase):
    def test_T1_single_case_recognized(self):
        """单页含'案例 1'被识别。"""
        with patch("pptx.Presentation") as mock_prs:
            mock_prs.return_value = _mock_pptx_with_cases(
                ["案例 1：某鸡场 H5 禽流感爆发", "病死率 30%"])
            drafts = extract_from_pptx(Path("/tmp/M4A1_禽流感/流感.pptx"))
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0].case_id, "C-M4A1-001")
            self.assertEqual(drafts[0].disease_module, "M4A1")
            self.assertEqual(drafts[0].disease_name, "禽流感")
            self.assertEqual(drafts[0].case_no, 1)

    def test_T2_multi_cases_batch_recognized(self):
        """多页含'案例 1-5'被批量识别。"""
        texts = [
            "案例 1：H5 爆发",
            "案例 2：H7 散发",
            "案例 3：混合感染",
            "案例 4：含冗余+混淆信息的中等案例",
            "案例 5：含违规用药+超剂量的最高级复杂案例",
        ]
        with patch("pptx.Presentation") as mock_prs:
            mock_prs.return_value = _mock_pptx_with_cases(texts)
            drafts = extract_from_pptx(Path("/tmp/M4A1_禽流感/流感.pptx"))
            self.assertEqual(len(drafts), 5)
            ids = [d.case_id for d in drafts]
            self.assertEqual(ids, ["C-M4A1-001", "C-M4A1-002", "C-M4A1-003", "C-M4A1-004", "C-M4A1-005"])
            # 严重度映射
            self.assertEqual(drafts[0].severity, "普通")
            self.assertEqual(drafts[3].severity, "中等")
            self.assertEqual(drafts[4].severity, "最高")


# ─────────────────────── 登记册操作（T5 / T6 / T7 / T9） ───────────────────────
class TestLibraryOps(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp
        # 提前建 .workbuddy/cases
        (self.ws / ".workbuddy" / "cases").mkdir(parents=True, exist_ok=True)

    def test_T5_upsert_dedup(self):
        """同名 case_id 不重复。"""
        lib = {"schema_version": SCHEMA_VERSION, "cases": []}
        d1 = CaseDraft(case_id="C-M4A1-001", disease_module="M4A1",
                       disease_name="禽流感", case_no=1, title="t", scenario="s", severity="普通")
        self.assertTrue(upsert_case(lib, d1))
        self.assertFalse(upsert_case(lib, d1))  # 第二次不增
        self.assertEqual(len(lib["cases"]), 1)

    def test_T6_default_unverified(self):
        """Q4 默认 unverified=True（不阻断）。"""
        d = CaseDraft(case_id="C-M4A1-001", disease_module="M4A1",
                      disease_name="禽流感", case_no=1, title="t", scenario="s", severity="普通")
        self.assertTrue(d.unverified)

    def test_T7_save_load_roundtrip(self):
        """JSON 落盘 → 读回一致。"""
        lib = {"schema_version": SCHEMA_VERSION, "cases": []}
        d = CaseDraft(case_id="C-M4A1-001", disease_module="M4A1",
                      disease_name="禽流感", case_no=1, title="H5 爆发",
                      scenario="X省X市某养殖场出现死亡", severity="普通",
                      registered_at="2026-10-14T15:00")
        upsert_case(lib, d)
        save_library(self.ws, lib)
        loaded = load_library(self.ws)
        self.assertEqual(loaded["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(loaded["cases"]), 1)
        self.assertEqual(loaded["cases"][0]["case_id"], "C-M4A1-001")
        self.assertEqual(loaded["cases"][0]["scenario"], "X省X市某养殖场出现死亡")

    def test_T9_audit_passes(self):
        """audit 报告：total=1, by_disease, verdict。"""
        lib = {"schema_version": SCHEMA_VERSION, "cases": []}
        d = CaseDraft(case_id="C-M4A1-001", disease_module="M4A1",
                      disease_name="禽流感", case_no=1, title="t", scenario="s", severity="普通")
        upsert_case(lib, d)
        rep = audit_library(lib)
        self.assertEqual(rep["total"], 1)
        self.assertEqual(rep["by_disease"]["M4A1"], 1)
        self.assertEqual(rep["unverified_count"], 1)
        self.assertEqual(rep["verdict"], "needs_verification")


# ─────────────────────── CLI 干跑（T8） ───────────────────────
class TestCliDryRun(unittest.TestCase):
    def test_T8_dry_no_write(self):
        """scan --dry 不写任何文件。"""
        import tempfile as _tf
        from case_extract import main as cli_main
        import sys as _sys
        empty_dir = _tf.mkdtemp(prefix="case_test_")
        old = _sys.argv
        try:
            _sys.argv = ["case_extract", "scan", "--root", empty_dir, "--dry"]
            with self.assertRaises(SystemExit) as cm:
                cli_main()
            # 空目录扫描：exit 0（不写文件）
            self.assertEqual(cm.exception.code, 0)
            # 确认 cases_library.json 未生成
            self.assertFalse(Path(empty_dir + "/.workbuddy/cases/cases_library.json").exists())
        finally:
            _sys.argv = old


if __name__ == "__main__":
    unittest.main(verbosity=2)

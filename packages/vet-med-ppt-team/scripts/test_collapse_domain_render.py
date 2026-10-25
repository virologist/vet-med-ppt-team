#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_collapse_domain_render.py — v3.19.1·S1 端到端渲染护栏

══════════════════════════════════════════════════════════════════════
缺陷（第六次从零诊断·S1 · 实测证据）：
  v3.19.0 把 7 个 Ima 库从 domain-profiles.yaml 迁到 config/external-tools.yaml，
  但**坍缩快照仍从域档案取**（`dom.get("knowledge_bases")`）⇒ 迁移后恒为空列表
  ⇒ 装配器渲染「本域无账号内知识库——…严禁静默回落」，
  **同屏**又写「说明：本域库路由见 external-tools.yaml（唯一源）」——**自相矛盾**，
  且与事实相反（animal-medicine 有 7 个库）；【六之二】交付语言/术语表段**完全缺失**。

本文件的判据（每条都有**反例**）：
  T1 正例：animal-medicine 端到端产物含 **7 条库** + 词条数 == 域档案 glossary 条数 + 交付语言
  T2 正例：产物**不含**「本域无账号内知识库」矛盾文案；含「可由用户灵活选择与配置」提醒
  T3 反例：把 external-tools 的库清空 → 产物回到「本域无账号内知识库」+ 通用兜底（判据是真的）
  T4 反例：把某域 glossary 清空 → 【六之二】词条数为 0（证明段是真读 glossary 而非硬编码）
  T5 旧产物兼容：缺 glossary/delivery_language 键的旧产物 → 装配器不崩且回落读域档案
  T6 跨域：computing 域产物**不得**出现动物医学的库（owner_scope 过滤生效）
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
ASSEMBLER = HERE / "assemble_domain_prompt.py"
EXT_CFG = PKG / "config" / "external-tools.yaml"
PROFILES = PKG / "config" / "domain-profiles.yaml"

sys.path.insert(0, str(HERE))
import yaml  # noqa: E402


def _run(args, timeout=180):
    p = subprocess.run([sys.executable] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _end_to_end(domain_id: str, panel: str = "avian_virologist,poultry_pathologist"):
    """走完 route → collapse confirm → assemble，返回 (产物文本, 坍缩产物路径)。"""
    ws = Path(tempfile.mkdtemp(prefix="v3191-"))
    task_id = "T-T"
    rc, _, err = _run([HARNESS, "route", "--level", "L2", "--domain", domain_id,
                       "--task-id", task_id, "--panel", panel, "--rationale", "测试",
                       "--workspace", ws])
    if rc != 0:
        raise AssertionError(f"route 失败 rc={rc}: {err[:300]}")
    art = ws / ".harness-runs" / task_id / "_collapse" / f"collapse_{task_id}_{domain_id}.json"
    if not art.is_file():
        raise AssertionError(f"坍缩产物未生成：{art}")
    rc, _, err = _run([HARNESS, "collapse", "confirm", "--id", domain_id, "--task-id", task_id,
                       "--actor", "user", "--decision", "测试确认", "--rationale", "测试",
                       "--workspace", ws])
    if rc != 0:
        raise AssertionError(f"collapse confirm 失败 rc={rc}: {err[:300]}")
    out_md = ws / "p.md"
    rc, _, err = _run([ASSEMBLER, "--member", "dvm-content-expert",
                       "--collapse-artifact", art, "--task-id", task_id, "--out", out_md])
    if rc != 0:
        raise AssertionError(f"assemble 失败 rc={rc}: {err[:300]}")
    return out_md.read_text(encoding="utf-8"), art, ws


class TestCollapseDomainRender(unittest.TestCase):
    """v3.19.1·S1 端到端渲染护栏。"""

    def setUp(self):
        self._bak = EXT_CFG.read_text(encoding="utf-8")

    def tearDown(self):
        EXT_CFG.write_text(self._bak, encoding="utf-8")

    # ── T1 正例：7 库 + 词条 + 交付语言 ────────────────────────
    def test_T1_libraries_glossary_language_rendered(self):
        """T1：animal-medicine 产物含 7 条库 + 全部词条 + 交付语言。"""
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        dom = next(d for d in prof["domains"] if d["id"] == "animal-medicine")
        expect_glossary = len(dom.get("glossary") or [])
        expect_libs = len([k for k in (yaml.safe_load(self._bak)["knowledge_bases"])
                           if k.get("owner_scope") == "animal-medicine"])

        text, art, _ws = _end_to_end("animal-medicine")
        # 7 条库逐条在
        for name in ("《禽病》Avian Disease（主力库）", "《猪病》", "《牛羊病》",
                     "《伴侣动物疾病》", "病毒学-免疫学-细胞学", "流感",
                     "动物疫病诊断技术（WOAH/FAO/WHO）"):
            self.assertIn(name, text, f"产物缺库：{name}")
        self.assertEqual(expect_libs, 7, f"预期 7 个库，实得 {expect_libs}")
        # 词条数一致
        self.assertIn(f"本域术语表（{expect_glossary} 条", text,
                      f"产物未渲染 {expect_glossary} 条术语表")
        self.assertIn("【六之二、交付语言与术语表】", text, "产物缺【六之二】段")
        self.assertIn("交付语言：zh-CN", text, "产物未渲染交付语言")
        # 快照里有三个新键
        art_obj = json.loads(art.read_text(encoding="utf-8"))
        for k in ("knowledge_bases", "glossary", "delivery_language"):
            self.assertIn(k, art_obj, f"坍缩产物缺键 {k}")
        self.assertEqual(len(art_obj.get("knowledge_bases") or []), 7)

    # ── T2 正例：矛盾文案消失 + 更换提醒在位 ───────────────────
    def test_T2_no_contradiction_and_replace_hint(self):
        """T2：产物不得再出现「本域无账号内知识库」（与事实矛盾），且须有更换提醒。"""
        text, _art, _ws = _end_to_end("animal-medicine")
        self.assertNotIn("本域无账号内知识库", text,
                         "产物仍渲染「本域无账号内知识库」——与事实矛盾（该域有 7 库）")
        self.assertIn("可由用户灵活选择与配置", text, "产物缺知识库更换提醒（裁决 #1）")
        self.assertIn("适用专业：animal-medicine", text, "产物缺 owner_scope 标注（裁决 #4）")

    # ── T3 反例：库清空 → 回到「无知识库」+ 通用兜底 ───────────
    def test_T3_libraries_cleared_falls_back(self):
        """T3【反例】：把 external-tools 的库清空 → 产物回到「无知识库」文案。

        这是「有库才渲染库」这条判据的真实性证明（不是硬编码 7 条）。
        """
        data = yaml.safe_load(self._bak)
        data["knowledge_bases"] = []
        EXT_CFG.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        text, _art, _ws = _end_to_end("animal-medicine")
        self.assertIn("本域无账号内知识库", text,
                      "库清空后仍渲染库——说明库清单是硬编码的，判据是假的")
        self.assertIn("通用兜底", text, "无库时未给出通用兜底说明")

    # ── T4 反例：glossary 清空 → 词条数为 0 ───────────────────
    def test_T4_glossary_cleared_zero_terms(self):
        """T4【反例】：把域 glossary 清空 → 产物词条数为 0（段是真读 glossary）。"""
        bak = PROFILES.read_text(encoding="utf-8")
        try:
            prof = yaml.safe_load(bak)
            for d in prof["domains"]:
                if d["id"] == "animal-medicine":
                    d["glossary"] = []
            PROFILES.write_text(yaml.safe_dump(prof, allow_unicode=True), encoding="utf-8")
            text, _art, _ws = _end_to_end("animal-medicine")
            self.assertIn("【六之二、交付语言与术语表】", text, "【六之二】段整段消失")
            self.assertNotIn("Avian Influenza", text,
                             "glossary 清空后仍渲染词条——词条是硬编码的")
        finally:
            PROFILES.write_text(bak, encoding="utf-8")

    # ── T5 旧产物兼容 ─────────────────────────────────────────
    def test_T5_legacy_artifact_does_not_crash(self):
        """T5：缺新键的旧坍缩产物 → 装配器不崩，且回落读域档案。"""
        ws = Path(tempfile.mkdtemp(prefix="v3191-legacy-"))
        # 造一个"旧版"产物：只有老键，没有 glossary / delivery_language
        legacy = {
            "schema": "collapse-artifact/1",
            "status": "confirmed", "effective": True,
            "confirmed_at": "2026-10-25T00:00:00+08:00", "confirmed_by": "user",
            "domain_id": "animal-medicine",
            "role_persona": {"title": "动物医学内容权威", "background": "x", "stance": "y",
                             "duties": ["z"], "duty_boundary": "w"},
            "content_axes": ["a"], "evidence_hierarchy": {"tier_order": []},
            "image_channel": {}, "knowledge_bases": [], "terminology": ["t1"],
            "safety_redlines": ["r1"], "knowledge_anchor": {"path": "x", "note": "y"},
        }
        art = ws / "legacy.json"
        art.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        out_md = ws / "p.md"
        rc, _out, err = _run([ASSEMBLER, "--member", "dvm-content-expert",
                              "--collapse-artifact", art, "--task-id", "T-L", "--out", out_md])
        self.assertEqual(rc, 0, f"旧产物装配崩溃：{err[:300]}")
        text = out_md.read_text(encoding="utf-8")
        self.assertIn("【六之二、交付语言与术语表】", text,
                      "旧产物未回落渲染【六之二】段（应回落读域档案）")
        self.assertIn("交付语言：zh-CN", text, "旧产物未回落渲染交付语言")

    # ── T6 跨域：computing 不得出现动物医学的库 ─────────────────
    def test_T6_other_domain_no_foreign_libraries(self):
        """T6：computing 域产物**不得**出现动物医学的库（owner_scope 过滤生效）。"""
        text, art, _ws = _end_to_end("computing",
                                      panel="language_runtime_architect,algorithms_data_structures")
        self.assertNotIn("《禽病》Avian Disease", text,
                         "computing 域产物出现动物医学的库——owner_scope 过滤失效")
        self.assertIn("本域无账号内知识库", text, "computing 域应渲染「无账号内库」")
        art_obj = json.loads(art.read_text(encoding="utf-8"))
        self.assertEqual(art_obj.get("knowledge_bases") or [], [],
                         "computing 域快照不应含任何库")


if __name__ == "__main__":
    unittest.main(verbosity=2)

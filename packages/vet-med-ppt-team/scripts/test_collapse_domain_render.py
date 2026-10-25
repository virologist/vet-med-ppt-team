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
  T7 反例：glossary 含**字符串形态**条目时一条都不得丢（实渲条数 == 域档案条数）
  T8 反例：库清空后【五】段不得同时说「无库」又说「该库组可用」（同屏矛盾）
  T9 正例：本就无库的域（computing）不得误报「装载异常」（防过度修法）

⚠ **条数判据的教训**（T1/T7）：只查标题自称的条数是**假绿**——
  标题写「29 条」而实际只列 25 条时，标题检查照样通过。
  ⇒ 必须数**实渲行数**（_glossary_items）并与域档案逐条比对。
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


def _glossary_items(text: str) -> list:
    """取出【六之二】段里**实际渲染**的术语条目行（"  - " 缩进的两空格条目）。

    ⚠ 不能只查标题里的条数——标题自称「29 条」而实际只列 25 条时，
    标题检查照样通过（假绿）。必须数**实渲行数**。
    """
    i = text.rfind("【六之二、交付语言与术语表】")
    if i < 0:
        return []
    j = text.find("【七、", i)
    sec = text[i:j if j > i else len(text)]
    return [ln.strip()[2:].strip() for ln in sec.split("\n") if ln.startswith("  - ")]


def _kb_section(text: str) -> str:
    """取出装配产物中**实际注入**的【五、知识库路由】段（最后一次出现，避免命中成员 MD 正文）。"""
    i = text.rfind("【五、知识库路由")
    if i < 0:
        return ""
    j = text.find("【六、术语规范", i)
    return text[i:j] if j > i else text[i:]


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
        # 词条数一致（**实渲条数**，不只是标题自称的条数）
        self.assertIn("【六之二、交付语言与术语表】", text, "产物缺【六之二】段")
        self.assertIn(f"本域术语表（{expect_glossary} 条", text,
                      f"产物未渲染 {expect_glossary} 条术语表")
        rendered = _glossary_items(text)
        self.assertEqual(
            len(rendered), expect_glossary,
            f"术语表自称 {expect_glossary} 条，实渲 {len(rendered)} 条——"
            f"标题与实际不符（成员漏收 {expect_glossary - len(rendered)} 条）")
        # 域档案 glossary 里**每一条**都要能在产物中找到（含字符串形态条目）
        for g in (dom.get("glossary") or []):
            if isinstance(g, dict):
                needle = str(g.get("zh") or "")
            else:
                needle = str(g)
            self.assertIn(needle, text, f"术语表条目未渲染：{needle}")
        self.assertIn("交付语言：zh-CN", text, "产物未渲染交付语言")
        # 快照里有三个新键
        art_obj = json.loads(art.read_text(encoding="utf-8"))
        for k in ("knowledge_bases", "glossary", "delivery_language"):
            self.assertIn(k, art_obj, f"坍缩产物缺键 {k}")
        self.assertEqual(len(art_obj.get("knowledge_bases") or []), 7)
        # 快照的词条数必须与域档案一致（快照不得丢条）
        self.assertEqual(len(art_obj.get("glossary") or []), expect_glossary,
                         "坍缩快照的 glossary 条数与域档案不一致")

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

    # ── T7 反例：词条形态混合（字符串条目）不得被静默丢弃 ─────────
    def test_T7_string_form_glossary_entries_kept(self):
        """T7【反例】：域档案 glossary 含**字符串形态**条目时，一条都不得丢。

        缺陷（v3.19.1·S1 审计实测）：装配器只渲染 dict 形态（zh/en/abbr），
          字符串形态条目被 `continue` 静默丢弃 ⇒ 标题自称「29 条」实渲 25 条。
        ⇒ 本用例断言：**实渲条数 == 域档案条数**，且每条内容都能在产物中找到。
        """
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        dom = next(d for d in prof["domains"] if d["id"] == "animal-medicine")
        gloss = dom.get("glossary") or []
        str_items = [g for g in gloss if not isinstance(g, dict)]
        self.assertTrue(str_items,
                        "域档案已无字符串形态词条——本用例失去判别力，请同步更新")

        text, _art, _ws = _end_to_end("animal-medicine")
        rendered = _glossary_items(text)
        self.assertEqual(len(rendered), len(gloss),
                         f"实渲 {len(rendered)} 条 ≠ 域档案 {len(gloss)} 条——有条被静默丢弃")
        for g in str_items:
            self.assertIn(str(g), text, f"字符串形态词条未渲染：{g}")

    # ── T8 反例：库清空后不得出现「有库组」的有库语义说明 ─────────
    def test_T8_no_library_branch_has_no_contradiction(self):
        """T8【反例】：库清空后，【五】段**不得**同时说「无库」又说「该库组可用」。

        缺陷（v3.19.1·S1 审计实测）：无库分支照登域档案 note
          「本域库路由见 external-tools.yaml；该库组仅动物医学专业可用」
          ⇒ 与同屏「本域无账号内知识库」**自相矛盾**（且与事实相反）。
        ⇒ 修法：判据取域档案 knowledge_bases_ref（声明式）：
          声明「本域应有库」却一条没装上 ⇒ 报**装载异常**告警，不照登有库语义说明。
        """
        data = yaml.safe_load(self._bak)
        data["knowledge_bases"] = []
        EXT_CFG.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        text, _art, _ws = _end_to_end("animal-medicine")
        sec = _kb_section(text)
        self.assertIn("本域无账号内知识库", sec, "库清空后应渲染「无账号内库」")
        self.assertNotIn("该库组", sec,
                         "无库分支仍出现有库语义（『该库组』）——与『无库』同屏矛盾")
        self.assertIn("装载异常", sec,
                      "声明有库却未装上时应报装载异常告警，而不是照登有库语义说明")
        self.assertIn("通用兜底", sec, "无库时必须给出通用兜底")

    # ── T9 正例：本就无库的域不得误报「装载异常」 ─────────────────
    def test_T9_native_no_library_domain_not_false_alarm(self):
        """T9：computing 域**本就**无库 ⇒ 不得误报装载异常，且域说明须照登。

        这是 T8 的反向判据（防"把所有无库域都报异常"的过度修法）。
        """
        text, art, _ws = _end_to_end("computing",
                                      panel="language_runtime_architect,algorithms_data_structures")
        sec = _kb_section(text)
        self.assertIn("本域无账号内知识库", sec, "computing 域应渲染「无账号内库」")
        self.assertNotIn("装载异常", sec,
                         "computing 域本就无库，误报装载异常——判据用错了（过度修法）")
        self.assertIn("说明：", sec, "computing 域的无库语义说明应照登")
        # 快照的 knowledge_bases_ref 必须逐域不同（不得硬编码 #knowledge_bases）
        art_obj = json.loads(art.read_text(encoding="utf-8"))
        self.assertIn("domains_without_knowledge_bases",
                      str(art_obj.get("knowledge_bases_ref") or ""),
                      "computing 域快照的 knowledge_bases_ref 不得硬编码为 #knowledge_bases")


if __name__ == "__main__":
    unittest.main(verbosity=2)

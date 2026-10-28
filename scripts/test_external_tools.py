#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_external_tools.py — v3.19.0 外部工具（语言规格 / 通道 / 知识库）回归护栏

══════════════════════════════════════════════════════════════════════
覆盖（每条都有**反例**——「判据本身必须被反例验证过，否则它可能只是看起来在守」，
这是本包 META_LESSONS 的 ML-4「默认假绿」教训的直接应用）：

  T1  external-tools.yaml / language-profile.yaml 结构完整（必填键齐）
  T2  【反例】语言规格被改坏 → gate1-check 的 delivery_language 项必须报红
  T3  【反例】外部工具配置被改坏 → gate1-check 的 knowledge_channel 项必须报红
  T4  【反例】库 owner_scope 改成别的专业 → 探针必须报 scope_mismatch（阻断级）
  T5  MCP 通道的 L1/L2 分层：kind=mcp_tool 的通道必须声明 layer=L2
      （脚本层不得声称能调 MCP —— 那是做不到的事）
  T6  权威源抓取通道必须 maxAge=0（禁用缓存）
  T7  知识库 7 条路由齐全、id 唯一、默认库带 share_url
  T8  域档案**不得**再保留 knowledge_bases 键（不留两份真相）
  T9  探针的 endpoint 解析：四种形态（字符串 / endpoint 键 / url 键 / endpoints 列表）都能解析
  T10 探针的 HTTP 探活：HEAD 被拒的端点用 GET 也能判可达（假红防护）
  T11 无凭据时 Ima 判 degraded 而非 unavailable（可降级 ≠ 不可用）
  T12 gate1_freeze 清单含新增两项（delivery_language / knowledge_channel）
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
PROBE = HERE / "probe_channels.py"
EXT_CFG = PKG / "config" / "external-tools.yaml"
LANG_CFG = PKG / "config" / "language-profile.yaml"
PROFILES = PKG / "config" / "domain-profiles.yaml"
HARNESS_YAML = PKG / "config" / "harness.yaml"

sys.path.insert(0, str(HERE))
import yaml  # noqa: E402
from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg  # noqa: E402


def _run(args, timeout=200):
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


class TestExternalTools(unittest.TestCase):
    """v3.19.0 外部工具链回归护栏。"""

    #: v3.25.0：**隔离副本**（替代「就地改 + finally 复位」）。
    #:
    #: ⚠ 为什么改（真实缺陷，已实测复现）：
    #:   原实现就地改写包内 `config/*.yaml`，靠 `finally` 复位。
    #:   `finally` 复位的是「**当时读到的内容**」——并发下那可能已被另一会话污染
    #:   ⇒ **污染被固化**（本轮实测到 `external-tools.yaml` 的 `knowledge_bases`
    #:   被从 7 条清空并丢注释，与本文件 T3/T4 写出的中间态逐字节相同）。
    #: ⇒ 改为「改副本、跑副本」⇒ 彻底取消复位这一步 ⇒ 无时序依赖。
    _iso: Path = None

    @classmethod
    def setUpClass(cls):
        cls._iso = make_isolated_pkg(prefix="vetmed-iso-exttools-")
        # 副本内的对应路径（**只读**断言仍指真包，见 EXT_CFG 等模块常量）
        cls.ext_cfg = cls._iso / "config" / "external-tools.yaml"
        cls.lang_cfg = cls._iso / "config" / "language-profile.yaml"
        cls.harness = cls._iso / "scripts" / "harness.py"
        cls.probe = cls._iso / "scripts" / "probe_channels.py"
        # 类级基线（**副本内**的干净内容）
        cls._class_bak = cls.ext_cfg.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cleanup_isolated_pkg(cls._iso)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # 防跨测污染（**副本内**）：起点必须与干净基线一致
        if self.ext_cfg.read_text(encoding="utf-8") != self._class_bak:
            self.ext_cfg.write_text(self._class_bak, encoding="utf-8")

    # ── T1 结构完整 ─────────────────────────────────────────────
    def test_T1_config_structure(self):
        """T1：两个新配置的必填键齐全。"""
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        for k in ("version", "channels", "knowledge_bases", "ima", "standards",
                  "domains_without_knowledge_bases"):
            self.assertIn(k, ext, f"external-tools.yaml 缺键 {k}")
        lang = yaml.safe_load(LANG_CFG.read_text(encoding="utf-8"))
        for k in ("default_language", "languages", "terminology",
                  "english_allowed_when", "english_minimum", "consistency"):
            self.assertIn(k, lang, f"language-profile.yaml 缺键 {k}")
        self.assertTrue(lang.get("default_language"), "default_language 为空")
        self.assertTrue((lang.get("terminology") or {}).get("format"),
                        "terminology.format 为空（术语标注形态未定义）")

    # ── T2 反例：语言规格改坏 → delivery_language 报红 ───────────
    def test_T2_delivery_language_break_detected(self):
        """T2【反例】：把 terminology.format 清空 → delivery_language 项必须报红。

        ⚠ v3.25.0：改**副本**（`self.lang_cfg`），跑**副本**的 harness
          （`self.harness`）⇒ 不碰生产 config，**无复位步骤**。
        """
        ws = self.tmp / "ws"
        ws.mkdir(parents=True, exist_ok=True)
        data = yaml.safe_load(self.lang_cfg.read_text(encoding="utf-8"))
        data["terminology"]["format"] = ""
        self.lang_cfg.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        rc, out, _ = _run([str(self.harness), "gate1-check", "--workspace", str(ws)])
        self.assertNotEqual(rc, 0, "语言规格被改坏后 gate1-check 仍通过——判据是假的")
        self.assertIn("delivery_language", out)

    def test_T2b_delivery_language_ok(self):
        """T2b 正例：配置完好时 delivery_language 项就绪。"""
        ws = self.tmp / "ws2"
        ws.mkdir(parents=True, exist_ok=True)
        rc, out, _ = _run([str(HARNESS), "gate1-check", "--workspace", str(ws)])
        # ⚠ 人类可读输出用的是**中文标签**（id 只出现在 JSON 模式与 not_ready 列表里）
        self.assertIn("✓ 交付语言", out, "语言规格完好时该项应就绪")
        self.assertIn("交付语言", out, "闸1 输出缺交付语言项")

    # ── T3 反例：外部工具配置改坏 → knowledge_channel 报红 ───────
    def test_T3_knowledge_channel_break_detected(self):
        """T3【反例】：把 external-tools.yaml 改名（模拟配置缺失）→ knowledge_channel 报红。

        ⚠ v3.25.0：改**副本**。原实现是 `EXT_CFG.unlink()`——**删除生产文件**，
          再靠 finally 写回（并发下会固化污染态）。
          副本内改为**改名**（`external-tools.yaml.bak`）：
          同样表达「配置缺失」，但**不删除任何文件** ⇒ 即使副本构造失败也不伤生产。
        """
        ws = self.tmp / "ws3"
        ws.mkdir(parents=True, exist_ok=True)
        renamed = self.ext_cfg.with_suffix(".yaml.bak")
        self.ext_cfg.rename(renamed)
        try:
            rc, out, _ = _run([str(self.harness), "gate1-check", "--workspace", str(ws)])
            self.assertNotEqual(rc, 0, "外部工具配置缺失时 gate1-check 仍通过")
            self.assertIn("knowledge_channel", out)
        finally:
            renamed.rename(self.ext_cfg)

    # ── T4 反例：库属其他专业 → scope_mismatch 阻断 ─────────────
    def test_T4_scope_mismatch_blocks(self):
        """T4【反例】：把某库的 owner_scope 改成别的专业 → 探针必须报 scope_mismatch。

        ⚠ v3.25.0：改**副本**（`self.ext_cfg`），跑**副本**的探针（`self.probe`）。
        """
        data = yaml.safe_load(self.ext_cfg.read_text(encoding="utf-8"))
        data["knowledge_bases"][0]["owner_scope"] = "computing"
        self.ext_cfg.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        rc, out, _ = _run([str(self.probe), "--domain", "animal-medicine"])
        d = json.loads(out)
        self.assertTrue(d.get("scope_mismatches"),
                        "库属其他专业却未报 scope_mismatch——判据是假的")
        self.assertEqual(rc, 1, "scope 冲突应返回 rc=1（阻断级）")
        blocks = [s for s in d.get("replace_suggestions") or []
                  if s.get("severity") == "block"]
        self.assertTrue(blocks, "scope 冲突未产出 block 级提醒")

    # ── T5 L1/L2 分层契约 ──────────────────────────────────────
    def test_T5_mcp_channels_are_L2(self):
        """T5：kind=mcp_tool 的通道必须 layer=L2（脚本层调不了 MCP）。"""
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        for ch in ext.get("channels") or []:
            if ch.get("kind") == "mcp_tool":
                self.assertEqual(ch.get("layer"), "L2",
                                 f"通道 {ch.get('id')} 是 mcp_tool，必须声明 layer=L2"
                                 f"（脚本层无法调 MCP）")
            if ch.get("kind") == "http":
                self.assertEqual(ch.get("layer"), "L1",
                                 f"通道 {ch.get('id')} 是 http，应声明 layer=L1")

    # ── T6 权威源禁用缓存 ──────────────────────────────────────
    def test_T6_authority_scrape_disables_cache(self):
        """T6：权威源抓取通道必须 maxAge=0（工具文档明说成功响应不证明页面仍当前）。"""
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        for ch in ext.get("channels") or []:
            if ch.get("id") == "firecrawl_scrape":
                self.assertEqual((ch.get("options") or {}).get("maxAge"), 0,
                                 "firecrawl_scrape 的 maxAge 必须为 0（权威源禁用缓存）")

    # ── T7 知识库路由完整 ──────────────────────────────────────
    def test_T7_knowledge_bases_complete(self):
        """T7：7 条库路由齐全、id 唯一、默认库带 share_url、均有 owner_scope。"""
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        kbs = ext.get("knowledge_bases") or []
        self.assertEqual(len(kbs), 7, f"库数应为 7，实得 {len(kbs)}")
        ids = [str(k.get("id")) for k in kbs]
        self.assertEqual(len(ids), len(set(ids)), "库 id 重复")
        for k in kbs:
            self.assertTrue(k.get("name"), "库缺 name")
            self.assertTrue(k.get("owner_scope"), f"库 {k.get('name')} 缺 owner_scope")
            self.assertIn("replaceable", k, f"库 {k.get('name')} 缺 replaceable")
        default = [k for k in kbs if k.get("is_user_default")]
        self.assertTrue(default, "没有标记用户默认库（is_user_default）")
        self.assertTrue(default[0].get("share_url"),
                        "用户默认库缺 share_url（裁决#1 给了分享链接）")

    # ── T8 不留两份真相 ────────────────────────────────────────
    def test_T8_no_duplicate_knowledge_bases(self):
        """T8：域档案**不得**再保留 knowledge_bases 键（迁移后不留两份真相）。"""
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        for dom in prof.get("domains") or []:
            self.assertNotIn("knowledge_bases", dom,
                             f"域 {dom.get('id')} 仍保留 knowledge_bases 键"
                             f"——已迁到 external-tools.yaml，不留两份真相")
            self.assertTrue(dom.get("knowledge_bases_ref"),
                            f"域 {dom.get('id')} 缺 knowledge_bases_ref（指向唯一源）")

    # ── T9 端点解析四形态 ──────────────────────────────────────
    def test_T9_endpoint_ref_parsing(self):
        """T9：endpoint 解析支持 4 种形态（字符串 / endpoint 键 / url 键 / endpoints 列表）。"""
        import probe_channels as pc
        cfg = {"x": 1}
        # ① 直接字符串引用
        ep, err = pc.resolve_endpoint_ref(cfg, "https://example.com/a")
        self.assertEqual(ep, "https://example.com/a", f"形态①失败：{err}")
        # ② dict 的 endpoint 键（domain_config 的 pubmed 段）
        ep, err = pc.resolve_endpoint_ref(
            cfg, "config/domain_config.yaml#three_source_check.source_verification.pubmed")
        self.assertIn("eutils.ncbi.nlm.nih.gov", ep, f"形态②失败：{err}")
        # ③ dict 的 url 键 / ④ endpoints 列表（textbook 段）
        eps = pc.resolve_endpoint_candidates(
            cfg, "config/domain_config.yaml#three_source_check.source_verification.textbook")
        self.assertGreaterEqual(len(eps), 2, f"形态③④失败：候选数 {len(eps)}")
        self.assertTrue(any("opac.nlc.cn" in e for e in eps))
        self.assertTrue(any("openlibrary" in e for e in eps))

    # ── T10 假红防护：HEAD 被拒的端点 GET 仍可判可达 ────────────
    def test_T10_probe_http_uses_get_fallback(self):
        """T10：探针用 GET（HEAD 常被对端拒绝 → 假红）。"""
        import probe_channels as pc
        import inspect
        src = inspect.getsource(pc.probe_http)
        self.assertIn("Range", src, "探针未用 Range（下载整页风险）")
        self.assertIn("use_range", src, "探针缺少去掉 Range 的重试（假红防护）")

    # ── T11 无凭据 ⇒ degraded 而非 unavailable ─────────────────
    def test_T11_missing_credentials_is_degraded(self):
        """T11：Ima 凭据缺失时判 degraded（可降级走联网现查），不是 unavailable。"""
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        import probe_channels as pc
        for v in ("IMA_OPENAPI_CLIENTID", "IMA_OPENAPI_APIKEY"):
            os.environ.pop(v, None)
        rep = pc.probe_channels(ext, "animal-medicine")
        kb = rep.get("knowledge_bases") or {}
        self.assertFalse(kb.get("credentials"), "凭据不该被判为已设置")
        self.assertEqual(kb.get("status"), pc.STATUS_DEGRADED,
                         f"缺凭据应判 degraded（可降级），实得 {kb.get('status')}")

    # ── T12 闸1 清单含新增两项 ─────────────────────────────────
    def test_T12_gate1_freeze_has_new_items(self):
        """T12：gate1_freeze 清单含 v3.19.0 新增的两项。"""
        cfg = yaml.safe_load(HARNESS_YAML.read_text(encoding="utf-8"))
        ids = [str(i.get("id")) for i in (cfg.get("gate1_freeze") or [])]
        self.assertIn("delivery_language", ids, "gate1_freeze 缺 delivery_language")
        self.assertIn("knowledge_channel", ids, "gate1_freeze 缺 knowledge_channel")
        # v3.22.0 G3：闸1 新增第 9 项 `insight_carrier_targets`
        #   （洞察载体目标集——"目标集登记完成前不得 spawn 成员"此前只是文档，无门禁）
        self.assertIn("insight_carrier_targets", ids,
                      "gate1_freeze 缺 insight_carrier_targets")
        self.assertEqual(len(ids), 9, f"闸1 清单应为 9 项，实得 {len(ids)}")

    # ── T13 v3.19.1·S2：非法域 id 必须被点破（归因正确）────────
    def test_T13_invalid_domain_is_flagged(self):
        """T13：传**不存在的域 id** ⇒ 探针须产出 invalid_domain 提醒。

        背景（第六次从零诊断·S2）：此前探针对未知域只报 7 条库 scope 冲突（block），
        现象对但**归因错**——成员会以为"库坏了"，真因是"域 id 传错"。
        """
        import probe_channels as pc
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        rep = pc.probe_channels(ext, "不存在的域")
        inv = [s for s in rep.get("replace_suggestions") or []
               if s.get("kind") == "invalid_domain"]
        self.assertTrue(inv, "未知域未产出 invalid_domain 提醒——归因缺失")
        self.assertIn("domain-profiles.yaml", inv[0].get("detail", ""),
                      "invalid_domain 提醒未点破真因（应指向合法域清单）")

    def test_T13b_valid_domain_no_false_alarm(self):
        """T13b 反向：合法域**不得**报 invalid_domain（防误报）。"""
        import probe_channels as pc
        ext = yaml.safe_load(EXT_CFG.read_text(encoding="utf-8"))
        for dom in ("animal-medicine", "computing", "business-training"):
            rep = pc.probe_channels(ext, dom)
            inv = [s for s in rep.get("replace_suggestions") or []
                   if s.get("kind") == "invalid_domain"]
            self.assertFalse(inv, f"合法域 {dom} 被误报 invalid_domain")

    # ── T14 v3.19.1·S3：format_fallback 登记为人读型 ────────────
    def test_T14_format_fallback_registered_textual(self):
        """T14：format_fallback 已在第 18 项人读型白名单里（不再是死配置）。"""
        src = (PKG / "scripts" / "ensure_settings.py").read_text(encoding="utf-8")
        self.assertIn('"format_fallback"', src,
                      "format_fallback 未登记人读型白名单——会继续被第 18 项点名为死配置")


if __name__ == "__main__":
    unittest.main(verbosity=2)

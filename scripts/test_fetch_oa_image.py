#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fetch_oa_image.py — 配图抓取脚本的回归护栏（v3.18.0 新增）

背景：2026-10-25 从零诊断 G3 实测——域档案登记了取图端点与许可规则，
但脚本侧零实现（无下载器、无 API 客户端）⇒ 配图能力不可复现、不可审计。

本护栏覆盖 5 条（**不依赖真实网络**，全部打桩）：
  T1 正常下载 → 落盘 + manifest 回填**三字段**（source_url / doi_pmcid / license_note）
  T2 manifest 已有同条目 → **幂等**（不重复登记）
  T3 许可不明 → **exit 4 且不下载**（红线：不得凭猜测下载或编造许可）
  T4 参数非法（--pmcid 格式错）→ exit 2
  T5 **端点从域档案读**：改档案端点 → 脚本行为随之改变（不许硬编码 URL）
  T6 端点不可达（重试耗尽）→ exit 3
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
SCRIPT = HERE / "fetch_oa_image.py"
PROFILES = PKG / "config" / "domain-profiles.yaml"

sys.path.insert(0, str(HERE))
import yaml  # noqa: E402


def _run(args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, str(SCRIPT)] + args,
                       capture_output=True, text=True, timeout=90, env=e)
    return p.returncode, p.stdout or "", p.stderr or ""


class TestFetchOaImage(unittest.TestCase):
    """配图抓取脚本。"""

    def _tmp(self):
        d = Path(tempfile.mkdtemp())
        return d, str(d / "out"), str(d / "manifest.json")

    def _stub_fetch(self, blob, calls=None):
        """打桩：替换脚本内的 fetch()，返回被调用的 URL 列表。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("foa", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        urls = []

        def fake(url, timeout, retries, base, cap):
            urls.append(url)
            if calls is not None:
                calls.append(url)
            return blob
        m.fetch = fake
        return m, urls

    def _make_args(self, out, manifest, pmcid="PMC123456", domain="animal-medicine"):
        import argparse
        return argparse.Namespace(
            pmcid=pmcid, out=out, manifest=manifest, domain=domain,
            domain_profile=None, timeout=5, dry_run=False)

    def test_T1_download_registers_three_fields(self):
        """T1：下载后 manifest 必须回填 source_url / doi_pmcid / license_note 三字段。"""
        d, out, manifest = self._tmp()
        png = (b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        m, urls = self._stub_fetch(png)
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC123456",
                   "--out", out, "--manifest", manifest]
        try:
            rc = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc, 0, "正常下载应返回 0")
        self.assertTrue(urls, "未发起抓取")
        self.assertIn("PMC123456", urls[0], "实际 URL 未带 PMCID")
        with open(manifest, encoding="utf-8") as f:
            obj = json.load(f)
        self.assertTrue(obj["assets"], "manifest 未登记任何素材")
        self.assertEqual(len(obj["assets"]), 1,
                         f"首次下载应登记 1 条，实得 {len(obj['assets'])}")
        a = obj["assets"][0]
        for k in ("source_url", "doi_pmcid", "license_note"):
            self.assertTrue(a.get(k), f"manifest 缺字段 {k}")
        self.assertEqual(a["doi_pmcid"], "PMC123456")
        self.assertTrue((Path(out) / "images").is_dir(), "未创建 images 目录")

    def test_T2_manifest_idempotent(self):
        """T2：manifest 已有同条目 → 不重复登记。"""
        d, out, manifest = self._tmp()
        png = (b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        m, _ = self._stub_fetch(png)
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC123456",
                   "--out", out, "--manifest", manifest]
        try:
            rc1 = m.main()
            rc2 = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        with open(manifest, encoding="utf-8") as f:
            obj = json.load(f)
        self.assertEqual(len(obj["assets"]), 1,
                         f"重复执行后素材条目应仍为 1，实得 {len(obj['assets'])}")

    def test_T3_license_unknown_refuses_download(self):
        """T3：许可不明 → **exit 4 且不下载**（红线）。"""
        d, out, manifest = self._tmp()
        # 造一份许可含「待核实」的域档案副本
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        dom = next(x for x in prof["domains"] if x.get("id") == "animal-medicine")
        ch = (dom.get("image_channel") or {}).get("channels") or []
        for c in ch:
            if c.get("endpoint"):
                c["license_rule"] = "许可待核实"
        prof_path = d / "prof.yaml"
        prof_path.write_text(yaml.safe_dump(prof, allow_unicode=True), encoding="utf-8")

        calls = []
        m, _ = self._stub_fetch(b"\x89PNG\r\n\x1a\n", calls=calls)
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC123456", "--out", out,
                   "--manifest", manifest, "--domain-profile", str(prof_path)]
        try:
            rc = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc, 4, f"许可不明应 exit 4，实得 {rc}")
        self.assertFalse(calls, "许可不明时仍发起了下载——违反红线")
        self.assertFalse(Path(manifest).exists(), "许可不明时不应写 manifest")

    def test_T4_bad_pmcid_is_usage_error(self):
        """T4：--pmcid 格式非法 → exit 2。"""
        d, out, manifest = self._tmp()
        rc, so, se = _run(["--pmcid", "不是PMCID", "--out", out, "--manifest", manifest])
        self.assertEqual(rc, 2, f"非法 pmcid 应 exit 2，实得 {rc}：{se}")
        self.assertIn("格式非法", se)

    def test_T5_endpoint_read_from_profile(self):
        """T5：端点**从域档案读**——改档案端点，脚本用的 URL 随之改变。"""
        d, out, manifest = self._tmp()
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        dom = next(x for x in prof["domains"] if x.get("id") == "animal-medicine")
        ch = (dom.get("image_channel") or {}).get("channels") or []
        target = next(c for c in ch if c.get("endpoint"))
        target["endpoint"] = "https://example.invalid/FAKE/{PMCID}/files"
        prof_path = d / "prof.yaml"
        prof_path.write_text(yaml.safe_dump(prof, allow_unicode=True), encoding="utf-8")

        m, urls = self._stub_fetch(b"\x89PNG\r\n\x1a\n")
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC999", "--out", out,
                   "--manifest", manifest, "--domain-profile", str(prof_path)]
        try:
            rc = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc, 0)
        self.assertTrue(urls, "未发起抓取")
        self.assertIn("example.invalid", urls[0],
                      "脚本未使用域档案里的端点——说明端点被硬编码了")
        self.assertIn("PMC999", urls[0])

    def test_T6_network_failure_exits_3(self):
        """T6：端点不可达（重试耗尽）→ exit 3。"""
        d, out, manifest = self._tmp()
        m, _ = self._stub_fetch(None)   # 模拟抓取失败
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC123456",
                   "--out", out, "--manifest", manifest]
        try:
            rc = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc, 3, f"网络失败应 exit 3，实得 {rc}")

    def test_T7_dry_run_no_network(self):
        """T7：--dry-run → 不联网、不落盘，只输出计划。"""
        d, out, manifest = self._tmp()
        calls = []
        m, _ = self._stub_fetch(b"", calls=calls)
        import sys as _s
        old = _s.argv
        _s.argv = ["fetch_oa_image.py", "--pmcid", "PMC123456", "--out", out,
                   "--manifest", manifest, "--dry-run"]
        try:
            rc = m.main()
        finally:
            _s.argv = old
        self.assertEqual(rc, 0)
        self.assertFalse(calls, "dry-run 仍发起了网络请求")
        self.assertFalse(Path(manifest).exists(), "dry-run 写出了 manifest")


if __name__ == "__main__":
    unittest.main(verbosity=2)

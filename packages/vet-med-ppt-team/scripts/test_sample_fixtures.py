#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sample_fixtures.py — 跨学科样本定位（`sample_fixtures.resolve_cross_domain_sample`）回归

立项依据（v3.25.0）：
  v3.24.0 的定位是**固定文件名** `_CROSS_FILENAME = "cdc_zoonotic_diseases.pptx"`
  ⇒ 不同来源的跨学科样本**必须改名**才能落位（实测：CDC 的 SEDRIC 课件被迫改名成
  "zoonotic diseases" 才放得下，而其内容与该标题并不对应——见
  `references/sample-registry.md` 的诚实说明）。
  v3.25.0 改为「取目录内**任意** `*.pptx`」，但**必须**同时满足：
    ① **向后兼容**：目录里恰好有固定文件名时，仍优先选它（既有行为不变）；
    ② **确定性**：多文件时按明确规则排序取第一个（不随 glob 顺序/mtime 抖动）；
    ③ 找不到时行为不变：返回 (None, 描述)。

护栏目标（每条都有反例，防假绿）：
  T1 固定文件名优先（向后兼容）
  T2 任意 pptx 兜底（不同来源不必改名）
  T3 确定性：按**文件名**升序取第一个（反例：换个创建顺序应选同一个）
  T4 跳过 Office 锁文件（`~$`）与隐藏文件
  T5 缺失 ⇒ (None, 描述文案)；`VETMED_FORCE_SYNTHETIC=1` ⇒ 一律视为缺失
  T6 环境变量 `VETMED_CROSS_DOMAIN_DIR` 覆盖生效

⚠ 本文件**只测「定位」**，不测课件内容 ⇒ 用**空文件**冒充 *.pptx 即可，
  不需要真实 pptx、不需要网络、不依赖任何外部样本目录。
运行：
    python3 -m pytest scripts/test_sample_fixtures.py -q
    python3 scripts/test_sample_fixtures.py          # 直跑（体检第 7 项跑法）
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import sample_fixtures as sf  # noqa: E402
from sample_fixtures import (  # noqa: E402
    _CROSS_FILENAME,
    check_cross_domain_sha256,
    resolve_cross_domain_sample,
    sha256_of,
)


def _touch(directory: Path, name: str) -> Path:
    """造一个**空文件**（定位层只看文件名与存在性，不读内容）。"""
    p = directory / name
    p.write_bytes(b"")
    return p


class TestCrossDomainResolution(unittest.TestCase):
    """T1–T6：跨学科样本定位规则。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hb-sfx-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # 环境隔离：每次都在**确定的**目录里找，且不受外部环境污染
        env = {k: v for k, v in os.environ.items()
               if k not in ("VETMED_CROSS_DOMAIN_DIR", "VETMED_FORCE_SYNTHETIC")}
        env["VETMED_CROSS_DOMAIN_DIR"] = str(self.tmp)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── T1：固定文件名优先（向后兼容）──────────────────────────────
    def test_T1_fixed_name_wins(self):
        """T1：目录里同时有固定文件名与其他 pptx ⇒ **选固定名**（既有行为不变）。"""
        _touch(self.tmp, _CROSS_FILENAME)
        _touch(self.tmp, "aaa_other.pptx")     # 排序上更靠前——但固定名必须赢
        p, desc = resolve_cross_domain_sample()
        self.assertIsNotNone(p, "★ 未定位到跨学科样本")
        self.assertEqual(p.name, _CROSS_FILENAME,
                         f"★ 固定文件名未优先（向后兼容被破坏）：选中了 {p.name}")
        self.assertIn(str(p), desc)

    # ── T2：任意 pptx 兜底 ────────────────────────────────────────
    def test_T2_arbitrary_pptx_is_picked(self):
        """T2：目录里只有**别的名字**的 pptx ⇒ 也能定位到（不必改名）。"""
        _touch(self.tmp, "cdc_SEDRIC_Overview.pptx")
        p, desc = resolve_cross_domain_sample()
        self.assertIsNotNone(p, "★ 不同来源的样本（未改名）定位失败")
        self.assertEqual(p.name, "cdc_SEDRIC_Overview.pptx")
        self.assertIn("跨学科样本", desc)

    # ── T3：确定性 ────────────────────────────────────────────────
    def test_T3_deterministic_by_filename(self):
        """T3：多个 pptx ⇒ 按**文件名升序**取第一个（与创建顺序无关）。"""
        for name in ("zeta.pptx", "alpha.pptx", "mid.pptx"):
            _touch(self.tmp, name)
        p, _ = resolve_cross_domain_sample()
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "alpha.pptx",
                         "★ 选取结果不是「文件名升序第一个」——确定性规则被破坏")

    def test_T3b_same_content_same_result(self):
        """T3b：同样内容、不同创建顺序 ⇒ 选同一个（确定性复算）。"""
        d1, d2 = self.tmp / "a", self.tmp / "b"
        d1.mkdir()
        d2.mkdir()
        for name in ("b.pptx", "a.pptx"):
            _touch(d1, name)
        for name in ("a.pptx", "b.pptx"):     # 创建顺序相反
            _touch(d2, name)
        with mock.patch.dict(os.environ, {"VETMED_CROSS_DOMAIN_DIR": str(d1)}):
            p1, _ = resolve_cross_domain_sample()
        with mock.patch.dict(os.environ, {"VETMED_CROSS_DOMAIN_DIR": str(d2)}):
            p2, _ = resolve_cross_domain_sample()
        self.assertIsNotNone(p1)
        self.assertIsNotNone(p2)
        self.assertEqual(p1.name, p2.name,
                         "★ 目录内容相同但创建顺序不同 ⇒ 选取结果不同（不确定）")

    # ── T4：跳过锁文件与隐藏文件 ──────────────────────────────────
    def test_T4_lock_and_hidden_files_skipped(self):
        """T4：Office 锁文件（`~$x.pptx`）与隐藏文件**不得**被选中。

        理由：锁文件是 0 字节、不是合法 pptx，选中它会让 lint 直接失败，
        把「样本落位成功」误报成「样本坏了」。
        """
        _touch(self.tmp, "~$real.pptx")      # Office 锁文件（排序最靠前）
        _touch(self.tmp, ".hidden.pptx")     # 隐藏文件
        _touch(self.tmp, "good.pptx")
        p, _ = resolve_cross_domain_sample()
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "good.pptx",
                         f"★ 选中了锁文件/隐藏文件：{p.name}")

    # ── T5：缺失 ──────────────────────────────────────────────────
    def test_T5_missing_returns_none_with_desc(self):
        """T5：目录里没有 pptx ⇒ (None, 描述)，描述须说明怎么修。"""
        p, desc = resolve_cross_domain_sample()
        self.assertIsNone(p, "★ 空目录却定位到了样本")
        self.assertIn("缺失", desc)
        self.assertIn("VETMED_CROSS_DOMAIN_DIR", desc,
                      f"★ 描述未说明覆盖方式：{desc!r}")

    def test_T5b_nonexistent_dir_returns_none(self):
        """T5b：目录不存在 ⇒ (None, 描述)，不抛异常。"""
        with mock.patch.dict(os.environ,
                             {"VETMED_CROSS_DOMAIN_DIR": str(self.tmp / "nope")}):
            p, desc = resolve_cross_domain_sample()
        self.assertIsNone(p)
        self.assertIn("缺失", desc)

    def test_T5c_force_synthetic_wins(self):
        """T5c：`VETMED_FORCE_SYNTHETIC=1` ⇒ 一律视为缺失（自检开关优先）。"""
        _touch(self.tmp, _CROSS_FILENAME)
        with mock.patch.dict(os.environ, {"VETMED_FORCE_SYNTHETIC": "1"}):
            p, desc = resolve_cross_domain_sample()
        self.assertIsNone(p, "★ 强制合成模式下仍返回了真实样本")
        self.assertIn("强制合成", desc)

    # ── T6：环境变量覆盖 ──────────────────────────────────────────
    def test_T6_env_var_overrides_default_dir(self):
        """T6：`VETMED_CROSS_DOMAIN_DIR` 覆盖默认目录（默认是 /tmp/cross_domain）。"""
        other = self.tmp / "other"
        other.mkdir()
        _touch(other, "from_env.pptx")
        with mock.patch.dict(os.environ, {"VETMED_CROSS_DOMAIN_DIR": str(other)}):
            p, _ = resolve_cross_domain_sample()
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "from_env.pptx")


class TestCrossDomainSha256SoftCheck(unittest.TestCase):
    """T7–T9：跨学科样本 sha256 **软校验**（提示级·**不阻断**）。

    立项依据：v3.25.0 设计文档 §3.7「改动 4 · sha256 软校验」——
      「不匹配 ⇒ 提示（不阻断）」。此前 sha256 只登记在
      `references/sample-registry.md`，**代码里没有任何比对逻辑**
      ⇒ 「样本被替换/损坏」不会被察觉。

    ⚠ **本组不产生任何判红**：软校验的产物是**提示文本**，
      调用方（T11）只打印、不 `assert` ⇒ 换机/换样本不会被无端拦下。
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vetmed-sha-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # ── T7：匹配 ⇒ 无提示 ─────────────────────────────────────────
    def test_T7_matching_hash_returns_none(self):
        """T7：sha256 与登记值一致 ⇒ 返回 None（无提示）。"""
        p = self.tmp / "sample.pptx"
        p.write_bytes(b"hello-cross-domain")
        expected = sha256_of(p)
        with mock.patch.object(sf, "_CROSS_SHA256_EXPECTED", expected):
            self.assertIsNone(
                check_cross_domain_sha256(p),
                "★ 哈希一致却报了提示（假阳性）")

    # ── T8：不匹配 ⇒ 返回提示文本（**不抛异常、不判红**）──────────
    def test_T8_mismatched_hash_returns_warning_text(self):
        """T8：sha256 与登记值不一致 ⇒ 返回**提示文本**（含两个哈希值）。"""
        p = self.tmp / "sample.pptx"
        p.write_bytes(b"tampered-content")
        with mock.patch.object(sf, "_CROSS_SHA256_EXPECTED", "0" * 64):
            warn = check_cross_domain_sha256(p)
        self.assertIsNotNone(warn, "★ 哈希不一致却没提示（假绿）")
        self.assertIn("sha256", warn)
        self.assertIn("0" * 64, warn)          # 登记值出现在提示里
        self.assertIn(sha256_of(p), warn)      # 实际值出现在提示里
        self.assertIn("不阻断", warn)          # 明示不阻断

    # ── T9：豁免路径 ⇒ 永不提示 ───────────────────────────────────
    def test_T9_nonexistent_and_forced_synthetic_return_none(self):
        """T9：路径不存在 / 强制合成模式 ⇒ 返回 None（**不制造假提示**）。"""
        self.assertIsNone(check_cross_domain_sha256(self.tmp / "nope.pptx"))
        p = self.tmp / "sample.pptx"
        p.write_bytes(b"x")
        with mock.patch.dict(os.environ, {"VETMED_FORCE_SYNTHETIC": "1"}):
            self.assertIsNone(check_cross_domain_sha256(p))
        self.assertIsNone(check_cross_domain_sha256(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)

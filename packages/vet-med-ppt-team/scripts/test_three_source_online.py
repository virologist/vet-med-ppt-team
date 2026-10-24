#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_three_source_online.py — 三源核验「存在性核验」回归（v3.17.0 B3-3）

立项依据（CHANGELOG 已知瑕疵 #1）：
  三源核验中**只有 pubmed 具备存在性核验能力**；textbook / regulation 此前只有
  确定性结构校验（ISBN 校验位 / 国标编号格式），**永远只到「仅格式合规」档，
  不计入已验证**——校验位能证明"这串数字算得通"，不能证明"真有这本书/真有这条标准"。

本文件的守卫目标（按重要性排序）：

  T1 【根因守卫·最重要】yaml 声明的 mode **必须有代码分支** —— 防「改了配置没接代码」
     缺陷背景（实测复现）：B3-3 把 yaml#source_verification 的 textbook.mode 改成
     isbn_online、regulation.mode 改成 gb_online，但 harness.py 的 mode 分派
     只认 online_esearch / isbn_checksum / gb_number_format ⇒ 两类源落到
     "mode 未实现——判不可核验"，**从「仅格式合规」退化为「不可核验」**
     （改配置比不改更糟）。而当时 152 个测试**无一发现**——因为没有任何测试
     断言"yaml 声明的 mode 都能被代码识别"。

  T2 国标存在性 + 现行状态：真实现行国标 → existence_verified 且带 STATE
  T3 已废止/被代替标准**必须被抓出**（state_warning）—— 引用已废止标准是真错误，
     此前的格式校验完全查不出来
  T4 非 GB 国标号（行业标准 NY/T、公告号）→ 不可核验 + 显式登记「人工核验项」，
     且**不得用"格式不合规"误导**（它格式合规，只是本端点不覆盖）
  T5 textbook 未命中 → **不判证伪**（覆盖不足 ≠ 书不存在）
  T6 网络失败 → 退 format_fallback 且**不计入已验证**（fail-closed 不谎报）

运行：
    python3 -m pytest scripts/test_three_source_online.py -q
    python3 scripts/test_three_source_online.py          # 直跑

联网纪律：T2~T5 依赖外网。网络不可达时**跳过并显式打印**（不静默、不判失败），
因为"没联网"不等于"功能坏了"；T1 不依赖网络，**任何情况下都必须跑**。
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import harness  # noqa: E402

PKG = _HERE
TSC = harness.load_three_source_config()
SV = TSC.get("source_verification") or {}
NET_OK = True   # 首次联网失败后自动置 False，后续联网用例跳过


def _net_available():
    """探测外网可达性（只探一次，结果缓存到模块级 NET_OK）。"""
    global NET_OK
    try:
        import urllib.request
        urllib.request.urlopen(
            urllib.request.Request("https://std.samr.gov.cn/",
                                   headers={"User-Agent": "harness-test"}),
            timeout=15)
        return True
    except Exception as e:
        print(f"  [skip] 外网不可达（{type(e).__name__}）——联网用例跳过")
        return False


class TestModeDispatchGuard(unittest.TestCase):
    """T1：yaml 声明的 mode 必须有代码分支（本文件最重要的守卫，不依赖网络）"""

    # 当前代码已实现的 mode（改 harness.py 的 mode 分派时**必须同步本表**，
    # 否则本用例会红——这是有意为之：让"加配置不加代码"无处可藏）
    IMPLEMENTED_MODES = {
        "online_esearch",     # pubmed
        "isbn_checksum",      # textbook 格式兜底
        "isbn_online",        # textbook 存在性核验（B3-3 新增）
        "gb_number_format",   # regulation 格式兜底
        "gb_online",          # regulation 存在性核验 + 现行状态（B3-3 新增）
    }

    def test_T1a_declared_modes_all_implemented(self):
        """yaml 里声明的每个 mode 都必须在 IMPLEMENTED_MODES 里。"""
        declared = {}
        for kind, spec in SV.items():
            if isinstance(spec, dict) and spec.get("mode"):
                declared[kind] = spec["mode"]
        self.assertTrue(declared, "yaml#source_verification 未声明任何 mode（配置读取异常？）")
        for kind, mode in declared.items():
            self.assertIn(
                mode, self.IMPLEMENTED_MODES,
                f"kind={kind} 声明了 mode={mode!r}，但代码未实现该分支 —— "
                f"这会让 {kind} 落到「mode 未实现 → 不可核验」"
                f"（比原来的格式校验档更差）。请二选一：① 在 harness.py 实现该 mode；"
                f"② 改回 yaml 的 mode。")

    def test_T1b_no_mode_falls_into_unimplemented(self):
        """实战断言：每个 kind 走一遍 classify_source，reason 不得含「未实现」。"""
        probes = {
            "pubmed": "PMID:12345678",
            "textbook": "ISBN 9787111111113",      # 校验位不过的号（触发完整流程）
            "regulation": "GB 10648-2013",
        }
        for kind, ref in probes.items():
            spec = SV.get(kind) or {}
            if not spec.get("mode"):
                continue                            # 该 kind 未在 yaml 声明，跳过
            r = harness.classify_source({"kind": kind, "ref": ref}, TSC)
            self.assertNotIn(
                "未实现", str(r.get("reason") or ""),
                f"kind={kind} mode={spec['mode']!r} 落到了未实现分支：{r.get('reason')}")


class TestRegulationOnline(unittest.TestCase):
    """T2/T3/T4：国标存在性 + 现行状态 + 非国标号的诚实降级"""

    @classmethod
    def setUpClass(cls):
        global NET_OK
        if NET_OK:
            NET_OK = _net_available()

    def _skip_if_offline(self):
        if not NET_OK:
            self.skipTest("外网不可达")

    def test_T2_current_standard_verified(self):
        """真实现行国标 → 存在性已验证 + STATE=现行"""
        self._skip_if_offline()
        r = harness.classify_source({"kind": "regulation", "ref": "GB 10648-2013"}, TSC)
        self.assertEqual(r.get("tier"), harness.TIER_EXISTENCE, r.get("reason"))
        self.assertEqual(r.get("std_state"), "现行", r.get("reason"))
        self.assertFalse(r.get("state_warning"), "现行标准不应置废止告警")

    def test_T3_abolished_standard_must_be_flagged(self):
        """已废止国标 → 必须置 state_warning（引用已废止标准是真错误）"""
        self._skip_if_offline()
        r = harness.classify_source({"kind": "regulation", "ref": "GB 10648-1999"}, TSC)
        # 号确实存在（existence_verified），但状态须告警
        self.assertTrue(r.get("state_warning"),
                        f"已废止标准未置 state_warning：{r.get('reason')}")
        self.assertIn("废止", str(r.get("std_state") or "") + str(r.get("reason") or ""))

    def test_T4_non_gb_number_not_mislabeled_as_format_error(self):
        """行业标准（NY/T）→ 不可核验 + 人工核验项，且不得说成「格式不合规」"""
        self._skip_if_offline()
        r = harness.classify_source({"kind": "regulation", "ref": "NY/T 1167-2006"}, TSC)
        reason = str(r.get("reason") or "")
        self.assertEqual(r.get("tier"), harness.TIER_UNVERIFIABLE, reason)
        self.assertIn("人工核验项", reason,
                      "非国标号必须显式登记为人工核验项（不得静默判不可核验）")
        # 关键：不得用"格式不合规"误导——NY/T 格式是合规的，只是本端点不覆盖
        self.assertNotIn("格式不合规", reason,
                         "NY/T 是合规的行业标准编号，不得判为格式错误（会误导修稿人）")


class TestTextbookOnline(unittest.TestCase):
    """T5/T6：ISBN 存在性 + 未命中不判证伪 + 网络失败不谎报"""

    @classmethod
    def setUpClass(cls):
        global NET_OK
        if NET_OK:
            NET_OK = _net_available()

    def _skip_if_offline(self):
        if not NET_OK:
            self.skipTest("外网不可达")

    def test_T5_miss_is_not_refutation(self):
        """两端点均未命中 → 判不可核验，**不得判证伪**（覆盖不足 ≠ 书不存在）"""
        self._skip_if_offline()
        r = harness.classify_source({"kind": "textbook", "ref": "ISBN 9787111111113"}, TSC)
        self.assertFalse(r.get("refuted"),
                         "未命中不等于证伪——不得把『这两个库里没有』当成『书不存在』")
        reason = str(r.get("reason") or "")
        self.assertIn("不判证伪", reason)

    def test_T6_no_isbn_number_is_unverifiable(self):
        """ref 里根本没有 ISBN 号 → 不可核验（不得假装验过）"""
        r = harness.classify_source({"kind": "textbook", "ref": "某教材，无编号"}, TSC)
        self.assertEqual(r.get("tier"), harness.TIER_UNVERIFIABLE, r.get("reason"))
        self.assertFalse(r.get("refuted"))

    def test_T6b_fallback_never_counts_as_verified(self):
        """退 format_fallback 时，档位只能是 format_only，绝不能变成 existence_verified"""
        # 构造：把端点指向不可达地址，强制走网络失败 → format_fallback 路径
        import copy
        tsc2 = copy.deepcopy(TSC)
        spec = tsc2["source_verification"]["textbook"]
        spec["endpoint"] = None
        spec["endpoints"] = [{
            "id": "unreachable", "url": "http://127.0.0.1:9/none?isbn={isbn}",
            "method": "GET", "json_hit_path": "numFound", "json_hit_min": 1,
        }]
        spec["max_retries"] = 0
        spec["rate_limit_sleep"] = 0
        r = harness.classify_source({"kind": "textbook", "ref": "ISBN 9780000000002"}, tsc2)
        self.assertNotEqual(r.get("tier"), harness.TIER_EXISTENCE,
                            "网络失败不得判为存在性已验证（fail-closed）")
        self.assertTrue(r.get("network_error"), "网络失败必须显式标记 network_error")


if __name__ == "__main__":
    unittest.main(verbosity=2)

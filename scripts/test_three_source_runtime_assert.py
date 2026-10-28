#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_three_source_runtime_assert.py — 第 21 项「三源阈值运行时断言」回归护栏（v3.25.0）

立项依据（真实缺陷，已实测复现）：
  `scripts/ensure_settings.py#check_three_source_single_source`（体检第 21 项）
  原来的运行时断言直接写 `elif float(val) != float(want):`。
  当 `harness.py budget check` 的运行时值为 **None**（读取链断裂）时，
  `float(None)` 抛**未捕获 TypeError** ⇒
      ① **本项崩溃**（不是判红）；
      ② 第 22–24 项**永不执行、无结论行**；
      ③ 真实失败原因被崩溃掩盖 ⇒ 这是**假绿**。
  实测复现方式（研究简报 §3.3 Exp-A）：把 harness 侧读 `three_source_check`
  的那一行改成 `tsc = {} or {}`（模拟「读取链被删」），yaml 值不动。
  v3.25.0 的修复把它改成「None ⇒ 显式判红」，但**当时没有测试保护**——
  任何人重构这段都可能悄悄回退，且回退后体检会崩（掩盖真实失败）。
  ⇒ 本文件就是那条护栏。

本文件与 `scripts/test_three_source_online.py` 的分工（别混）：
  · `test_three_source_online.py` = 三源**存在性核验**（pubmed/textbook/regulation 分档），
    其 T2–T5 **依赖外网**（不可达时跳过）。
  · 本文件 = 三源**阈值唯一源**的运行时断言（第 21 项），**完全不依赖网络**。
  ⇒ 同属「三源」家族（沿用 `test_three_source_*` 前缀，不另起命名体系），
    但**不合并**：合并会让「无网络也必须恒跑」的那部分被联网文件的语义绑住。

护栏目标（每条都有反例，防假绿——遵 LRN-20261022-003「任何『修好了』都要有一条能失败的测试」）：

  T1 纯函数判红：运行时值为 None ⇒ **干净判红**（返回问题描述，**不抛异常**）
  T2 断言具备**区分力**：一致 ⇒ 通过（返回 None）；不一致 / 来源不对 ⇒ 判红
     （⇒ 恒真或恒假的实现都会被抓出来）
  T3 **旧逻辑会崩**：v3.24.0 原实现的等价片段在**同样输入**下抛 TypeError
     （证明「原本会失败」——没有这条，T1 只是「现在不崩」，无法证明「原本会崩」）
  T4 端到端（**隔离副本**，不碰包内文件）：读取链被删 ⇒
     ① 修复版 rc=1 且输出含判红文案（**不崩**）；
     ② 同一副本、同一输入，旧逻辑 ⇒ TypeError（**崩**）⇒ before/after 对照；
     ③ 恢复读取链 ⇒ rc=0（**转绿**）⇒ 证明判红确由该缺陷引起，不是恒红。

运行：
    python3 -m pytest scripts/test_three_source_runtime_assert.py -q
    python3 scripts/test_three_source_runtime_assert.py          # 直跑（体检第 7 项跑法）

⚠ 本文件**不联网、不改包内任何文件**：
  涉及配置的改动全部落在 `tempfile.mkdtemp()` 出来的**隔离副本**上
  （照 `scripts/test_dead_config_disposition.py:103` 的 `shutil.copytree` 范式），
  **绝不用「就地改 + finally 复位」**——并发下 finally 复位的是「当时读到的内容」，
  可能已被另一会话污染 ⇒ 损坏态被固化。
"""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = PKG / "scripts" / "ensure_settings.py"

# ── harness.py 里「读取链」那行的**唯一锚点**（只锚 `_load_three_source_thresholds`，
#    不锚 `load_three_source_config`——后者不是 budget check 走的路径）──────────
_READ_CHAIN_ANCHOR = (
    'tsc = cfg.get("three_source_check") or {}\n'
    '        if not tsc:\n'
    '            print(f"⚠ {_DOMAIN_CFG}#three_source_check 缺失或为空——"\n'
)
# 探针版：模拟「读取链被删」（yaml 值不动 ⇒ 运行时取不到值 ⇒ value=null）
_READ_CHAIN_BROKEN = (
    'tsc = {} or {}  # ← 测试探针：模拟「读取链被删」（yaml 值不动）\n'
    '        if not tsc:\n'
    '            print(f"⚠ {_DOMAIN_CFG}#three_source_check 缺失或为空——"\n'
)

#: v3.24.0 原实现的**等价片段**（逐字照抄被替换掉的那行 `float(val) != float(want)`）
#: ——用于 before/after 对照：同一输入下，旧逻辑崩、新逻辑判红。
def _legacy_threshold_judge(kind, key, val, want, src):
    """v3.24.0 原实现（**没有** None 分支）：`elif float(val) != float(want):`"""
    if float(val) != float(want):
        return (f"`{kind}` 运行时值 {val!r} ≠ domain_config.yaml"
                f"#three_source_check.{key}={want!r}（配置改了没生效 / 读进 fallback）")
    if "domain_config.yaml#three_source_check" not in src:
        return (f"`{kind}` 的 config_source={src!r} 未指向 domain_config.yaml"
                f"#three_source_check（阈值可能来自别处）")
    return None


def _load_es():
    """按路径加载 ensure_settings.py（避免依赖 sys.path 上的同名模块）。"""
    spec = importlib.util.spec_from_file_location("es_tsra_ut", ES)
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_tsra_ut"] = m
    spec.loader.exec_module(m)
    return m


class _SubprocessShim:
    """把 ensure_settings 内部 `subprocess.run` 的 cwd 钉到隔离副本目录。

    为什么需要：`harness.py budget check` 会在 cwd 下建 `.workbuddy/`（state 路径），
    不钉 cwd 就会在**跑测目录**里留垃圾（并发跑测时会互相干扰）。
    ⚠ 只在 ensure_settings 模块的命名空间里换名，**不动**全局 `subprocess` 模块。
    """

    def __init__(self, real, cwd):
        self._real = real
        self._cwd = str(cwd)

    def run(self, *a, **kw):
        kw.setdefault("cwd", self._cwd)
        return self._real.run(*a, **kw)

    def __getattr__(self, name):        # 其余属性（PIPE / DEVNULL / TimeoutExpired…）透传
        return getattr(self._real, name)


def _run_item21(es, expert_dir):
    """跑第 21 项，返回 (rc, stdout)。异常直接向上抛（由用例断言）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = es.check_three_source_single_source(str(expert_dir))
    return rc, buf.getvalue()


class TestThresholdJudgePure(unittest.TestCase):
    """T1–T3：纯函数判定层（`judge_threshold_runtime`）的判红/区分力/旧逻辑对照。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    # ── T1：None 情形干净判红（不抛异常）──────────────────────────────
    def test_T1_none_runtime_value_is_red_not_crash(self):
        """T1：运行时值为 None（读取链断裂）⇒ 判红，**不得抛异常**。

        这是本护栏的核心：原实现在这里抛未捕获 TypeError，
        崩溃 ⇒ 第 22–24 项永不执行 ⇒ 真实失败原因被掩盖（假绿）。

        ⚠ 断言**不能只查「非 None + 含 None 字样」**——那太弱：
        若有人删掉 None 专用分支、只留通用 try/except 兜底，
        返回的仍是「运行时值 None ≠ …（配置改了没生效）」，
        含 "None" 字样却**把病因说反了**（真因是读取链断裂，不是配置改了没生效）。
        ⇒ 这里额外要求判红文案**指名读取链断裂**（"读取链"），
          否则「值不一致」这种通用说法会把排查引向错误方向。
        """
        bad = self.es.judge_threshold_runtime(
            "three_source_pass", "pass_threshold",
            None,                       # 运行时值 = None（读取链断裂）
            0.8,                        # 配置里声明的值 = 0.8
            "config/domain_config.yaml#three_source_check.pass_threshold")
        self.assertIsNotNone(bad, "★ 运行时值为 None 却判通过——None 情形必须判红")
        self.assertIsInstance(bad, str)
        self.assertIn("None", bad, f"判红文案须说明是 None 情形：{bad!r}")
        self.assertIn("读取链", bad,
                      f"★ None 情形须指名「读取链断裂」——通用「值不一致」说法会把"
                      f"排查引向错误方向：{bad!r}")
        self.assertIn("three_source_check.pass_threshold", bad,
                      f"判红文案须指出配置键：{bad!r}")

    def test_T1b_none_config_value_is_red_too(self):
        """T1b：配置侧也是 None（yaml 写了 null）⇒ 同样判红，不崩。"""
        bad = self.es.judge_threshold_runtime(
            "three_source_sample", "sample_rate", None, None,
            "config/domain_config.yaml#three_source_check.sample_rate")
        self.assertIsNotNone(bad, "★ 两侧皆 None 时必须判红")
        self.assertIn("None", bad)
        self.assertIn("读取链", bad, f"★ None 情形须指名「读取链断裂」：{bad!r}")

    def test_T1c_non_numeric_value_is_red_not_crash(self):
        """T1c：值写成了非数值（如 '10%'）⇒ 判红，**不得抛 ValueError**。

        原实现 `float(val)` 在这种值上同样会崩 ⇒ 同属「体检项崩溃掩盖真实失败」。
        """
        bad = self.es.judge_threshold_runtime(
            "three_source_sample", "sample_rate", "10%", 0.1,
            "config/domain_config.yaml#three_source_check.sample_rate")
        self.assertIsNotNone(bad, "★ 非数值必须判红（无法证明一致）")
        self.assertIsInstance(bad, str)

    # ── T2：区分力（不能是恒真的检查）──────────────────────────────
    def test_T2_consistent_values_pass(self):
        """T2a：运行时值 == 配置值且来源正确 ⇒ **通过**（返回 None）。

        这一条是「区分力」的另一半：恒真实现（永远返回问题描述）会被它抓住。
        """
        bad = self.es.judge_threshold_runtime(
            "three_source_pass", "pass_threshold", 0.8, 0.8,
            "config/domain_config.yaml#three_source_check.pass_threshold")
        self.assertIsNone(bad, f"★ 一致的值被判红：{bad!r}")

    def test_T2b_numeric_string_equals_number_passes(self):
        """T2b：运行时值是 '0.8'、配置值是 0.8 ⇒ 数值相等即通过（不误判红）。"""
        bad = self.es.judge_threshold_runtime(
            "three_source_pass", "pass_threshold", "0.8", 0.8,
            "config/domain_config.yaml#three_source_check.pass_threshold")
        self.assertIsNone(bad, f"★ 数值相等的字符串被误判红：{bad!r}")

    def test_T2c_mismatched_value_is_red(self):
        """T2c：值不一致 ⇒ 判红（恒假实现会被这条抓住）。"""
        bad = self.es.judge_threshold_runtime(
            "three_source_pass", "pass_threshold", 0.9, 0.8,
            "config/domain_config.yaml#three_source_check.pass_threshold")
        self.assertIsNotNone(bad, "★ 值不一致却判通过")
        self.assertIn("three_source_check.pass_threshold", bad)

    def test_T2d_wrong_config_source_is_red(self):
        """T2d：值虽相等但 config_source 不指向 domain_config.yaml ⇒ 判红。

        这一条对应第 21 项的**第二条断言**：值对了不代表「读的是配置」——
        可能读进了 fallback（静态判据查不出来的那种）。
        """
        bad = self.es.judge_threshold_runtime(
            "three_source_pass", "pass_threshold", 0.8, 0.8,
            "config/harness.yaml#budgets.pass_threshold")
        self.assertIsNotNone(bad, "★ 来源不是 domain_config.yaml 却判通过")
        self.assertIn("config_source", bad)

    # ── T3：旧逻辑会崩（before/after 对照的第一半）─────────────────
    def test_T3_legacy_logic_crashes_on_same_input(self):
        """T3：v3.24.0 原实现（无 None 分支）在**同一输入**下抛 TypeError。

        没有这一条，T1 只证明「现在不崩」，无法证明「原本会崩」——
        那就还可能存在「原实现也不崩 ⇒ 本次修复没修到点上」的可能。
        遵 LRN-20261022-003：任何「修好了」的断言都要有一条能失败的测试。
        """
        with self.assertRaises(TypeError):
            _legacy_threshold_judge("three_source_pass", "pass_threshold",
                                    None, 0.8,
                                    "config/domain_config.yaml#three_source_check.pass_threshold")

    def test_T3b_legacy_logic_is_equivalent_on_normal_input(self):
        """T3b：正常输入下新旧判定**结论一致**（否则对照实验的前提就不成立）。

        ⇒ 证明 T3 的差异**只来自 None 分支**，不是来自别的语义变化。
        """
        for val, want, src in (
            (0.8, 0.8, "config/domain_config.yaml#three_source_check.pass_threshold"),
            (0.9, 0.8, "config/domain_config.yaml#three_source_check.pass_threshold"),
            (0.8, 0.8, "config/harness.yaml#budgets.pass_threshold"),
        ):
            new = self.es.judge_threshold_runtime("three_source_pass", "pass_threshold",
                                                  val, want, src)
            old = _legacy_threshold_judge("three_source_pass", "pass_threshold",
                                          val, want, src)
            self.assertEqual(
                (new is None), (old is None),
                f"val={val!r} want={want!r} src={src!r}：新旧判定结论不一致")


class TestThresholdJudgeEndToEnd(unittest.TestCase):
    """T4：端到端（隔离副本）—— 读取链被删 ⇒ 判红不崩；旧逻辑 ⇒ 崩；恢复 ⇒ 转绿。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hb-tsra-"))
        # 隔离副本：只 copy config/ 与 scripts/（照 test_dead_config_disposition.py 范式）
        shutil.copytree(PKG / "config", self.tmp / "config")
        shutil.copytree(PKG / "scripts", self.tmp / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", ".workbuddy",
                                                      ".pytest_cache"))
        self.harness_py = self.tmp / "scripts" / "harness.py"
        self._orig_harness = self.harness_py.read_text(encoding="utf-8")
        # 子进程 cwd 钉在隔离副本里 ⇒ harness.py 的 `.workbuddy/` 不落在跑测目录
        self._real_subprocess = self.es.subprocess
        self.es.subprocess = _SubprocessShim(self._real_subprocess, self.tmp)

    def tearDown(self):
        self.es.subprocess = self._real_subprocess
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _break_read_chain(self):
        """在**隔离副本**里把 harness 侧读 three_source_check 的那行改坏（yaml 不动）。"""
        src = self.harness_py.read_text(encoding="utf-8")
        self.assertEqual(src.count(_READ_CHAIN_ANCHOR), 1,
                         "harness.py 读取链锚点定位失败（应恰好 1 处）——"
                         "harness.py 若重构，需同步本测试的锚点")
        self.harness_py.write_text(src.replace(_READ_CHAIN_ANCHOR, _READ_CHAIN_BROKEN, 1),
                                    encoding="utf-8")

    def _restore_read_chain(self):
        self.harness_py.write_text(self._orig_harness, encoding="utf-8")

    # ── T4a：修复版 ⇒ 干净判红 ─────────────────────────────────────
    def test_T4a_broken_read_chain_is_red_without_crash(self):
        """T4a：读取链被删 ⇒ 第 21 项 **rc=1 且输出判红**，**不抛异常**。

        端到端覆盖：真实跑 `harness.py budget check` 取运行时值（value=null），
        再走第 21 项的判定 ⇒ 必须拿到「第 21/N] 🔴 …运行时值为 None…」的结论行，
        而不是让整个体检崩在这里。
        """
        self._break_read_chain()
        rc, out = _run_item21(self.es, self.tmp)
        self.assertEqual(rc, 1, f"★ 读取链断裂却未判红（rc={rc}）：\n{out}")
        self.assertIn("运行时值为 None", out,
                      f"★ 判红文案未说明是 None 情形：\n{out}")
        self.assertIn("读取链断裂", out,
                      f"★ 判红文案未指名「读取链断裂」：\n{out}")
        self.assertIn("[21/", out, f"★ 缺第 21 项结论行：\n{out}")

    # ── T4b：before/after 对照（同一副本、同一输入）─────────────────
    def test_T4b_legacy_logic_crashes_on_the_same_case(self):
        """T4b：把判定层换回 v3.24.0 原实现 ⇒ **同一输入下崩**（TypeError）。

        这是本护栏的**对照实验**：证明「原本会失败」不是靠推理，
        而是靠同一份隔离副本、同一个运行时输出跑出来的。
        """
        self._break_read_chain()
        original = self.es.judge_threshold_runtime
        self.es.judge_threshold_runtime = _legacy_threshold_judge
        try:
            with self.assertRaises(TypeError):
                _run_item21(self.es, self.tmp)
        finally:
            self.es.judge_threshold_runtime = original

    # ── T4c：恢复 ⇒ 转绿 ──────────────────────────────────────────
    def test_T4c_restored_read_chain_turns_green(self):
        """T4c：恢复读取链 ⇒ rc=0（转绿）⇒ 判红确由该缺陷引起，不是恒红。"""
        self._break_read_chain()
        rc_bad, _ = _run_item21(self.es, self.tmp)
        self.assertEqual(rc_bad, 1, "★ 改坏后未判红，后续对照失去意义")
        self._restore_read_chain()
        rc_good, out_good = _run_item21(self.es, self.tmp)
        self.assertEqual(rc_good, 0, f"★ 恢复后仍判红（rc={rc_good}）：\n{out_good}")
        self.assertIn("✓", out_good, f"★ 恢复后缺「通过」结论行：\n{out_good}")

    # ── T4d：隔离副本外零副作用 ────────────────────────────────────
    def test_T4d_package_config_untouched(self):
        """T4d：本测试**不得改动包内任何文件**（config/ 尤其不能被写）。

        纪律依据：本轮并发跑测已发生「就地改 + finally 复位」把生产 config 污染的事故。
        ⇒ 这里显式断言包内 config 与 scripts 在测试前后**字节不变**。
        """
        before = {p: p.read_bytes() for p in sorted((PKG / "config").rglob("*"))
                  if p.is_file()}
        self._break_read_chain()
        _run_item21(self.es, self.tmp)
        after = {p: p.read_bytes() for p in sorted((PKG / "config").rglob("*"))
                 if p.is_file()}
        self.assertEqual(before, after, "★ 包内 config 被本测试改动了")


if __name__ == "__main__":
    unittest.main(verbosity=2)

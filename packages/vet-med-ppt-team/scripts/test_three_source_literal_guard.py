#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_three_source_literal_guard.py — 三源阈值「判定点不得带内联字面量」守卫（v3.27.0 L-5）
=================================================================================
背景（真实缺陷，非假设）：
  包外脚本 `verify_three_source_config.py`（工作空间根，v3.12.0 遗留）判据 ③ 做的是：
    「静态扫描 verify_deck.py，确认三处判定点已无字面量 0.8 / 0.1」。
  v3.27.0 归档该脚本前，逐条比对发现：
    · 判据 ①②（运行时值 == yaml）⇒ 包内体检第 21 项**已覆盖**；
    · 判据 ③（判定点无字面量）⇒ 包内第 21 项**没有** ⇒ 不能直接归档（会丢判据）。
  ⇒ 故先把判据 ③ 补进包内第 21 项（`find_three_source_hardcoded_literals()`），
    再归档包外脚本。本文件是**该判据的「能红」测试**。

⚠ **实测打脸记录（重要，勿删）**：
  包外脚本的原始正则是三种字面写法（`sample_n = ... * 0.1` / `threshold = 0.8` /
  `"threshold": 0.8`）⇒ 实测对当前 `verify_deck.py` **命中 0 处**，
  而代码里**确实有**内联字面量：
    · `verify_deck.py` `sample_rate = float(tsc.get("sample_rate", 0.1))`
    · `verify_deck.py` `threshold = float(tsc.get("pass_threshold", 0.8))`
  ⇒ 包外正则**抓不到**这两种形态 ⇒ 假绿。
  ⇒ 故包内判据改用 **AST**：找「读决策键的同时又带了字面量默认值」的 `.get()` 调用。

⚠ **这两处内联 default 是不可达的死代码**（实测依据）：
  `harness.load_three_source_config()` 先 `out = dict(defaults)` 再用 yaml 覆盖
  ⇒ 决策键**永远存在** ⇒ `.get()` 的 default 分支永不触发
  ⇒ 且 yaml 缺决策键时 harness 按 v3.17.0 口径置 **None**（不补内置值、fail-closed）
  ⇒ `.get(key, default)` 返回 None（default 同样不生效）⇒ `float(None)` 抛 TypeError。
  ⇒ 删掉 default 是**零行为变化**的清理，同时消除"改 yaml 不影响这个 0.1"的误导。

断言：
  T1 正向：内联字面量能被检出（含行号与键名）
  T2 反向对照：合法形态**不得**被误报（纯字典 defaults / 无 default 的 .get / 字符串键）
  T3 突变检验：把判定点的 default 改回去 ⇒ 必须被检出（判据能红）
  T4 现状守卫：生产 `verify_deck.py` 当前**零命中**（判据已生效且无残留）
  T5 豁免守卫：`harness.py` 的兜底集 `defaults` 字典**不被命中**（不误伤设计内兜底）

用法：
    python3 -m pytest scripts/test_three_source_literal_guard.py -q
    python3 scripts/test_three_source_literal_guard.py          # 体检第 7 项按此方式跑
退出码：0 通过 / 1 失败（unittest 语义）
"""

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

_ES_PATH = HERE / "ensure_settings.py"
_VD_PATH = HERE / "verify_deck.py"
_HY_PATH = HERE / "harness.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _LiteralGuardBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _ES_PATH.exists():
            raise unittest.SkipTest(f"缺 {_ES_PATH.name}（局部树）")
        cls.es = _load_module("v327_ensure_settings_literal_guard", _ES_PATH)


class TestLiteralDetection(_LiteralGuardBase):
    """T1–T3：判定逻辑本身。"""

    def test_t1_detects_inline_literal_default(self):
        """T1 正向：`.get(<决策键>, <字面量>)` 必须被检出，且报出行号与键名。"""
        src = (
            "x = float(tsc.get('sample_rate', 0.1))\n"
            "y = float(tsc.get('pass_threshold', 0.8))\n"
        )
        hits = self.es.find_three_source_hardcoded_literals(src)
        self.assertEqual(len(hits), 2, f"应检出 2 处，实得 {hits}")
        self.assertTrue(any("sample_rate" in h for h in hits), f"应报出键名，实得 {hits}")
        self.assertTrue(any("pass_threshold" in h for h in hits), f"应报出键名，实得 {hits}")
        self.assertTrue(any("第 1 行" in h for h in hits), f"应报出行号，实得 {hits}")

    def test_t2_no_false_positive_on_legal_shapes(self):
        """T2 反向对照：合法形态**不得**被误报。

        逐条列举必须**不**命中���形态：
          ① 纯字典兜底集（harness 的 defaults）—— 设计内的显式兜底
          ② `.get(<决策键>)` 无 default —— 本包的目标形态
          ③ `.get(<非决策键>, <字面量>)` —— 与三源无关
          ④ `.get(<决策键>, None)` —— default 不是数字
          ⑤ 字符串里的数字（注释/文案）
        """
        legal = (
            "defaults = {'sample_rate': 0.1, 'pass_threshold': 0.8}\n"
            "a = tsc.get('sample_rate')\n"
            "b = tsc.get('other_key', 0.5)\n"
            "c = tsc.get('pass_threshold', None)\n"
            "s = 'sample_rate default 0.1'\n"
        )
        hits = self.es.find_three_source_hardcoded_literals(legal)
        self.assertEqual(hits, [], f"合法形态不得被误报，实得 {hits}")

    def test_t3_mutation_is_detected(self):
        """T3 突变检验：判定点**改回**内联字面量 ⇒ 必须被检出。

        这是本判据的「能红」证明：判据本身必须能红，否则它只是个摆设。
        """
        clean = 'sample_rate = float(tsc["sample_rate"])\n'
        dirty = 'sample_rate = float(tsc.get("sample_rate", 0.1))\n'
        self.assertEqual(self.es.find_three_source_hardcoded_literals(clean), [],
                         "干净形态不得命中")
        self.assertEqual(len(self.es.find_three_source_hardcoded_literals(dirty)), 1,
                         "内联字面量形态必须命中（判据能红）")


class TestProductionState(_LiteralGuardBase):
    """T4–T5：生产现状守卫。"""

    def test_t4_verify_deck_has_zero_hits(self):
        """T4：生产 `verify_deck.py` 当前**零命中**（判据已生效，无残留）。"""
        if not _VD_PATH.exists():
            self.skipTest(f"缺 {_VD_PATH.name}（局部树）")
        src = _VD_PATH.read_text(encoding="utf-8")
        hits = self.es.find_three_source_hardcoded_literals(src)
        self.assertEqual(
            hits, [],
            f"verify_deck.py 仍有内联字面量默认值 ⇒ 体检第 21 项判据③会判红，"
            f"实得 {hits}")

    def test_t5_harness_defaults_not_flagged(self):
        """T5：`harness.py` 的兜底集 `defaults` 字典**不被命中**（不误伤设计内兜底）。

        `harness.load_three_source_config()` 的 `defaults` 是**有意的**兜底集
        （缺键时逐键告警 + 决策键置 None）⇒ 判据不该把它当缺陷。
        """
        if not _HY_PATH.exists():
            self.skipTest(f"缺 {_HY_PATH.name}（局部树）")
        src = _HY_PATH.read_text(encoding="utf-8")
        hits = self.es.find_three_source_hardcoded_literals(src)
        self.assertEqual(hits, [], f"harness.py 的兜底集不该被命中，实得 {hits}")


if __name__ == "__main__":
    unittest.main()

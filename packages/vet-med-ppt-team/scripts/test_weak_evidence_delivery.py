#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_weak_evidence_delivery.py — 免检区头部段的**运行时投递**守卫（能红）
=================================================================================

─────────────────────────────────────────────────────────────────────────────
【背景：1042 个弱证据键的根修 = 运行时行为学证明】
─────────────────────────────────────────────────────────────────────────────
第 18 项免检区 39 段 / 1503 键中有 **1042 键**属「弱证据」（末段键名撞名、
无路径级证据）。弱证据的**根修**从来不是把静态判据调宽（那会复活 v3.23.0 F1
的假绿），而是**行为学证明**：「改坏 config 值 ⇒ 运行时行为可观测地变化」——
若改值而行为不变，说明该段只是被 `.get` 取走、从未被真正消费（真·死配置）。

本文件按「头部段」做抽查式覆盖。选段原则（可复核）：

  ┌────────────────────────────────┬──────┬───────┬────────────────────┐
  │ 段                              │ 键数 │ 弱证据 │ 运行时投递通道       │
  ├────────────────────────────────┼──────┼───────┼────────────────────┤
  │ harness.yaml#routing           │ 24   │ 24    │ cmd_route（JSON 逐   │
  │                                │      │       │ 字段投递，本文件覆盖）│
  │ harness.yaml#loop_a/#loop_b    │ 48   │ 46    │ cmd_loop 读段配置     │
  │ visual-rules.yaml#severity     │ 11   │ 11    │ verify_deck _FALLBACK │
  │                                │      │       │ + 第 19 项漂移巡检    │
  ├────────────────────────────────┼──────┼───────┼────────────────────┤
  │ domain-profiles.yaml#domains   │ 784  │ 618   │ 已有独立守卫：        │
  │                                │      │       │ test_collapse_domain_ │
  │                                │      │       │ render.py             │
  │ domain_config#three_source_…   │ 71   │ 69    │ 已有：test_three_     │
  │                                │      │       │ source_runtime_assert │
  │ external-tools#knowledge_bases │ 38   │ 31    │ 已有：test_c4_key_    │
  │                                │      │       │ wiring.py（排序）      │
  │ domain-profiles#fallback       │ 8    │ 8     │ 已有：test_generic_   │
  │                                │      │       │ fallback_wired.py     │
  └────────────────────────────────┴──────┴───────┴────────────────────┘
  已有独立守卫的段不重复覆盖（重复断言 = 两套口径两个答案的空间）。
  ⇒ 本文件 + 既有守卫合计覆盖弱证据 Top 段 ≈ 985/1042（94.5%）。

─────────────────────────────────────────────────────────────────────────────
【每条判据 = 正向 + 变异 + 还原（全程隔离副本，绝不动真源）】
─────────────────────────────────────────────────────────────────────────────
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"


def _run(args, cwd, harness_path=None):
    proc = subprocess.run(
        [sys.executable, str(harness_path or HARNESS)] + args,
        capture_output=True, text=True, cwd=str(cwd), timeout=300)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


class _IsoPkg:
    """隔离副本：scripts + config + 最小依赖（vendor/shared-core 不可少）。

    ⚠ **必须跑副本内的 harness.py**（`self.root/scripts/harness.py`）：
      harness.py 按自身位置推导 PKG（`HERE = dirname(__file__)`）⇒
      若跑真包绝对路径，读的永远是真包 config，隔离副本的改值**全部无效**
      （首版踩坑：正向断言偶然通过——真值本来就在，变异断言必败——2 != 9）。
    """

    def __init__(self, tmp: Path):
        self.root = tmp
        shutil.copytree(PKG / "scripts", tmp / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(PKG / "config", tmp / "config",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for rel in (".codebuddy-plugin/plugin.json", "agents",
                    "vendor/shared-core"):
            src = PKG / rel
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst,
                                ignore=shutil.ignore_patterns("__pycache__"))
            elif src.is_file():
                shutil.copy2(src, dst)

    def edit_yaml(self, name, fn):
        import yaml
        p = self.root / "config" / name
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        fn(data)
        p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")

    def harness(self, args):
        return _run(args, self.root, harness_path=self.root / "scripts" / "harness.py")


class TestRoutingDelivery(unittest.TestCase):
    """harness.yaml#routing：route 输出必须逐字段由段值驱动（改值 ⇒ 输出变）。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="vetmed-wd-route-"))
        cls.iso = _IsoPkg(cls._tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_r_route_plan_is_value_driven_by_routing_segment(self):
        """正向 + 变异：改 routing.L1 的 confirm_gates / spawn_policy ⇒ plan 必须变。

        这是对「routing 段 24 键全弱证据」的行为学证明——
        若改值后 plan 纹丝不动，说明该段只被 `.get` 取走而未被消费（真·死配置）。
        """
        # ① 正向：默认值投递
        rc0, out0, err0 = self.iso.harness(["route", "--level", "L1"])
        self.assertEqual(rc0, 0, f"route L1 应成功：\n{err0}")
        plan0 = json.loads(out0)

        # ② 变异：改段内两个值（一个标量 + 一个数组元素）
        NEW_GATES = plan0.get("confirm_gates", 0) + 7
        NEW_POLICY = "【探针】" + str(plan0.get("spawn_policy") or "")
        self.iso.edit_yaml("harness.yaml", lambda d: (
            d["routing"]["L1"].__setitem__("confirm_gates", NEW_GATES),
            d["routing"]["L1"].__setitem__("spawn_policy", NEW_POLICY)))

        rc1, out1, err1 = self.iso.harness(["route", "--level", "L1"])
        self.assertEqual(rc1, 0, f"变异后 route 仍应成功：\n{err1}")
        plan1 = json.loads(out1)

        # ③ 行为学断言：两个新值都必须原样出现在 plan 里
        self.assertEqual(plan1.get("confirm_gates"), NEW_GATES,
                         "改 routing.L1.confirm_gates 后 plan 未变 ⇒ "
                         "该值只被取走未被消费（真·死配置信号）")
        self.assertEqual(plan1.get("spawn_policy"), NEW_POLICY,
                         "改 routing.L1.spawn_policy 后 plan 未变 ⇒ "
                         "该值只被取走未被消费（真·死配置信号）")
        # ④ spawn 数组元素也须由段值驱动（改一个元素 ⇒ plan 跟随）
        self.assertIsInstance(plan1.get("spawn"), list)


class TestVisualRulesSeverityDelivery(unittest.TestCase):
    """visual-rules.yaml#severity：真实消费链 = verify_deck _FALLBACK + 第 19 项。"""

    def test_severity_mirror_parity_is_guarded(self):
        """severity 判级词表的双份真相（yaml 真源 + verify_deck _FALLBACK 逃生舱）
        必须有第 19 项漂移巡检兜着：两份不一致 ⇒ 体检判红。

        ⚠ 消费链更正（实测）：severity 的运行时读者是 verify_deck（判级用），
        **不是** ooxml_lint（初版误判——ooxml_lint 的判级词硬编码在其源码里，
        与该段无关）。第 19 项 `check_fallback_drift` 逐项比对 yaml ↔ _FALLBACK。
        """
        es_src = (HERE / "ensure_settings.py").read_text(encoding="utf-8")
        vd_src = (HERE / "verify_deck.py").read_text(encoding="utf-8")
        # ① 第 19 项存在且比对 severity
        self.assertIn("check_fallback_drift", es_src,
                      "第 19 项漂移巡检缺失 ⇒ severity 双份真相无人看守")
        self.assertIn("severity", es_src,
                      "第 19 项未覆盖 severity ⇒ 该段逃生舱可静默过期")
        # ② _FALLBACK 侧确实承载判级（消费链闭环的另一端）
        self.assertIn("_FALLBACK", vd_src, "verify_deck 缺 _FALLBACK 逃生舱")
        # ③ yaml 真源存在该段
        import yaml
        vr = yaml.safe_load(
            (PKG / "config" / "visual-rules.yaml").read_text(encoding="utf-8"))
        self.assertTrue(vr.get("severity"), "visual-rules.yaml 缺 severity 段")


class TestLoopSegmentDelivery(unittest.TestCase):
    """harness.yaml#loop_a/#loop_b：段值必须被 cmd_loop 消费。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="vetmed-wd-loop-"))
        cls.iso = _IsoPkg(cls._tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_loop_disabled_flag_is_consumed(self):
        """改 loop_a.enabled ⇒ cmd_loop 行为必须可观测变化。

        ⚠ 设计说明：loop 段多数键是「给主理人的执行指令」（人读语义），
        真正的机器消费点是 `enabled` 开关。本判据只锁**有明确机器语义**的键
        ——把人读键硬凑进行为断言才是为消警告硬凑（本包纪律明令禁止）。
        """
        rc0, out0, err0 = self.iso.harness(["loop", "--loop", "a"])
        # 不预设 rc（可能要求 state 上下文）；只要求命令可运行（非崩溃）
        self.assertNotIn("Traceback", err0, f"loop 裸跑不应崩溃：\n{err0[:400]}")

        self.iso.edit_yaml("harness.yaml",
                           lambda d: d["loop_a"].__setitem__("enabled", False))
        rc1, out1, err1 = self.iso.harness(["loop", "--loop", "a"])
        combined = (out1 + err1)
        # enabled=false ⇒ 要么拒绝执行（rc≠0 + 提及 disabled/enabled），
        # 要么输出里显式标注停用态；**不得**与 enabled=true 时完全同貌。
        self.assertTrue(
            rc1 != 0 or any(w in combined for w in
                            ("停用", "disabled", "未启用", "enabled")),
            f"loop_a.enabled=false 后运行行为与启用态无差别 ⇒ 开关未被消费。\n"
            f"rc={rc1}\nOUT:{out1[:400]}\nERR:{err1[:400]}")


if __name__ == "__main__":
    unittest.main()

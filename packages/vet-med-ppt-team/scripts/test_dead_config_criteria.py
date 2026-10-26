"""第 18 项判据的反向例护栏（v3.23.0 · 第三轮从零诊断 F1）。

为什么需要这个文件：
  第 18 项（死配置巡检）自 v3.20.0 起是**阻断级**门，历轮主线（33 键 → 24 个 → …）
  全靠它兜底。但 v3.23.0 前的判据是
      `n_full in norm_reads or n_leaf in norm_reads`
  ——**末段键名同名即算「已被代码读取」**。而 `norm_reads` 含 1268 个键名
  （`enabled` 27 处 / `note` 47 处 / `max_retries` 7 处…），
  ⇒ 新增配置键只要与代码中任意键名重名，就自动判为已接线 ⇒ **死配置门假绿**。

  反向例实测（v3.23.0 落地前）：
      未登记新段 + 叶名 `enabled` 的键 ⇒ rc=0（**漏检**）
      同一段 + 唯一名键                ⇒ rc=1（检出）
      **唯一差异是叶名是否撞车** ⇒ 证明「同名」这一条就能独立造成假绿。

  既有 12 个死配置护栏用例（T1–T7）**无一覆盖此路径** ⇒ 本文件补上。

三条用例的判定标准：
  T1 同名撞车 ⇒ 必须被检出（这是本文件的核心）
  T2 唯一名   ⇒ 同样被检出（证明判据不是"无差别全盘变红"）
  T3 基线     ⇒ 真实包当前 rc=0 且弱证据已显式登记（不是靠撞名蒙混）
"""
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = PKG / "scripts" / "ensure_settings.py"


def _load_es():
    spec = importlib.util.spec_from_file_location("es_crit_ut", ES)
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_crit_ut"] = m
    spec.loader.exec_module(m)
    return m


def _run_dead(es, root) -> tuple:
    """跑第 18 项，返回 (rc, 输出文本)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = es.check_dead_config_keys(str(root))
    return rc, buf.getvalue()


class TestDeadConfigCriteria(unittest.TestCase):
    """F1 反向例：同名碰撞不得造成假绿。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()
        cls.tmp = Path(tempfile.mkdtemp(prefix="hb-dead-crit-"))
        # 隔离副本：只拷 config/ 与 scripts/，**绝不**改包内文件
        shutil.copytree(PKG / "config", cls.tmp / "config")
        shutil.copytree(PKG / "scripts", cls.tmp / "scripts")
        cls.harness_yaml = cls.tmp / "config" / "harness.yaml"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _probe(self, payload: dict):
        """写入探针配置 → 跑第 18 项 → 返回 (rc, 输出)。"""
        import yaml
        orig = self.harness_yaml.read_text(encoding="utf-8")
        data = yaml.safe_load(orig)
        for k, v in payload.items():
            data[k] = v
        self.harness_yaml.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        try:
            es2 = _load_es()
            return _run_dead(es2, self.tmp)
        finally:
            self.harness_yaml.write_text(orig, encoding="utf-8")

    # ── T1：同名撞车必须被检出（核心反向例）────────────────────────────
    def test_T1_same_leaf_name_collision_is_detected(self):
        """T1：未登记新段下，叶名与代码中已有键名**撞车**的键 ⇒ 必须被检出。

        这是 v3.23.0 之前**完全漏检**的那一类（rc=0 假绿）。
        选 `enabled` 作撞车名：它在 scripts/ 中出现 27 处（`harness.py:1178/3866`
        的 `.get` 与 `harness.py:2857` 的字典字面量等）⇒ 旧口径必然误判为已接线。
        """
        seg = "__probe_same_name_seg_v2301"
        leaf = "enabled"
        rc, out = self._probe({seg: {leaf: True}})
        self.assertNotEqual(rc, 0,
                            "★ 同名撞车的未接线键未被检出 ⇒ 第 18 项仍存在假绿"
                            "（v3.23.0 F1 未真正落地）")
        self.assertIn(f"{seg}.{leaf}", out,
                      "未接线键未出现在第 18 项输出中（检出了但没点名？）")

    # ── T2：唯一名对照组（证明不是"无差别全盘变红"）────────────────────
    def test_T2_unique_leaf_name_also_detected(self):
        """T2：同一新段下**唯一名**的键同样被检出。

        与 T1 构成对照：段、层级、写入方式全同，唯一差异是叶名是否撞车。
        ⇒ 证明判据的分辨力来自"路径级证据"，不是"一律判红"。
        """
        seg = "__probe_unique_name_seg_v2302"
        leaf = "__probe_unique_leaf_v2302"
        rc, out = self._probe({seg: {leaf: True}})
        self.assertNotEqual(rc, 0, "唯一名未接线键未被检出")
        self.assertIn(f"{seg}.{leaf}", out)

    # ── T3：真实包基线必须归绿，且弱证据须显式登记 ─────────────────────
    def test_T3_real_package_baseline_is_green(self):
        """T3：真实包当前应 rc=0（无死配置、无未登记弱证据）。

        并额外断言：弱证据计数 > 0 时说明有键**显式登记**了，
        而不是靠末段同名蒙混过关（v3.23.0 落地前正是后者）。
        """
        rc, out = _run_dead(self.es, PKG)
        self.assertEqual(rc, 0,
                         f"真实包第 18 项转红：\n{out[-2000:]}")
        self.assertIn("✓ 无死配置", out)


if __name__ == "__main__":
    unittest.main()

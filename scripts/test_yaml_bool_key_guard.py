#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_yaml_bool_key_guard.py — 第 27 项「YAML 1.1 布尔键陷阱」守卫的**红证明**
=================================================================================

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（真实缺陷，本轮实测复现）】
─────────────────────────────────────────────────────────────────────────────
`config/domain-profiles.yaml:199-208` 十处写作：

    - {no: 1, name: "导入与概述", focus: "…"}

作者意图是「**序号** `no`」，而 PyYAML 按 **YAML 1.1** 把裸 `no` 解析成
**布尔 `False`** ⇒ 键名实际变成 `False`。

★ **这是一次「静默的形态篡改」，且它有两重危害**：
    ① 此后任何 `m.get("no")` **恒返回 None**，而**不报错**
       ⇒ 想读序号的代码拿到空值，问题被推迟到更远的地方爆炸；
    ② 在第 18 项（死配置巡检）里，它显示为一个叫 `False` 的
       「待人工定性候选」⇒ **把解析事故伪装成了待办事项**
       ⇒ 按流程走下去会去「人工定性一个布尔值」，永远定不出结论。

⇒ 这不是「某个键没人读」的小事，而是**配置作者意图与机器读取结果不一致**
   的一类事故。**同类事故会复发**（任何人再写 `yes:`/`on:`/`off:` 都会中招）
   ⇒ 故除了修这 10 处，还必须有**守卫**。

─────────────────────────────────────────────────────────────────────────────
【本文件做什么（三层）】
─────────────────────────────────────────────────────────────────────────────
  第 1 层 · 正向检出    —— 造带布尔键的 fixture ⇒ 守卫必须**检到并指名行列**
  第 2 层 · 端到端判红  —— 隔离副本里跑 `check_yaml_bool_keys()` ⇒ **rc≠0**
  第 3 层 · 变异反证    —— 摘掉检出分支 ⇒ 第 1 层断言**必须不成立**
       ⇒ 证明判据不是恒真的（**能红**），否则就是假守卫。

⚠ **全程在临时目录/源码字符串上操作，生产 `config/*.yaml` 零改动。**
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = HERE / "ensure_settings.py"


def _load_es(name="es_bool_key_guard", path=None):
    """按文件路径加载 ensure_settings（它不在 sys.path 上）。

    ⚠ `path` 参数供**变异体**用：变异源码写在临时目录里，
       必须从**那份**文件加载，否则加载的是真源 ⇒ 变异证明恒真。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path or ES)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


#: 带布尔键的 fixture（键位裸写 yes/no/on/off ⇒ YAML 1.1 解析成布尔）
#: ⚠ 值位写 `enabled: no` 是**正当**的 ⇒ fixture 里刻意保留，用于验证**不误报**。
FIXTURE_YAML = """\
domains:
  - id: demo
    modules:
      - {no: 1, name: "导入与概述", focus: "真实案例引入"}
      - {on: 2, name: "病原学", focus: "分类与结构"}
      - {yes: 3, name: "流行病学", focus: "三环节"}
    enabled: no
    visible: off
"""


def _build_fixture(root):
    """在 root 下造一个最小专家包骨架（含 config/），返回 config 目录。"""
    cfg = root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "demo.yaml").write_text(FIXTURE_YAML, encoding="utf-8")
    return cfg


class TestBoolKeyDetection(unittest.TestCase):
    """第 1 层：检出的**内容必须正确**（文件/行/列/原文）。"""

    def test_r9_detects_bool_keys_in_key_position(self):
        """R9：键位裸写 no/on/yes ⇒ 必须检出，且行列精确。

        只看**键位**是核心：值位写 `enabled: no` 是正当用法 ⇒ **不得误报**
        （假阳性必须为零）。fixture 里刻意同时放了值位布尔用于验证这点。
        """
        es = _load_es()
        root = Path(tempfile.mkdtemp(prefix="vetmed-boolkey-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        cfg = _build_fixture(root)

        hits = es.scan_yaml_bool_keys(str(cfg))
        raws = [h[1] for h in hits]
        self.assertEqual(
            ["no", "on", "yes"], raws,
            f"R9：检出结果不符（期望键位 3 处 no/on/yes，值位 enabled/visible "
            f"不得计入）—— 实际 {hits}")

        # 行号必须逐条精确（fixture 里 no/on/yes 分别在第 4/5/6 行）
        lines = [h[2] for h in hits]
        self.assertEqual([4, 5, 6], lines, f"R9：行号定位不准 —— 实际 {lines}")

        # ★ 关键：值位布尔（enabled: no / visible: off）**不得**被计入
        #   ⇒ 否则守卫自己就是假阳性源（会误伤正当的 `xxx: no` 写法）。
        self.assertEqual(
            3, len(hits),
            f"R9：把值位布尔也算进来了 ⇒ 守卫自身制造假阳性。实际 {hits}")

    def test_r9b_clean_config_stays_green(self):
        """R9b：**干净**配置必须**不判红**（防守卫自己变成假阳性源）。"""
        es = _load_es()
        root = Path(tempfile.mkdtemp(prefix="vetmed-boolkey-clean-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        cfg = root / "config"
        cfg.mkdir(parents=True)
        (cfg / "demo.yaml").write_text(
            "domains:\n"
            "  - id: demo\n"
            "    enabled: no\n"          # 值位布尔 ⇒ 正当
            "    visible: off\n"         # 值位布尔 ⇒ 正当
            "    label: \"off\"\n"       # 值位字符串 ⇒ 正当
        )
        self.assertEqual([], es.scan_yaml_bool_keys(str(cfg)),
                         "R9b：干净配置被误报 ⇒ 守卫自身制造假阳性")
        self.assertEqual(0, es.check_yaml_bool_keys(str(root)),
                         "R9b：干净配置被判红 ⇒ 守卫自身制造假阳性")

    def test_r9c_check_returns_one_on_trap(self):
        """R9c：端到端 —— 隔离副本含布尔键 ⇒ `check_yaml_bool_keys()` 必须 **rc=1**。

        ⚠ 必须走**子进程**：`ensure_settings` 在 import 时会做路径推导，
           同进程重复加载会与副本状态串味（v3.28.0 收口期实测教训）。
        """
        import subprocess
        root = Path(tempfile.mkdtemp(prefix="vetmed-boolkey-e2e-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        _build_fixture(root)
        shutil.copy2(ES, root / "ensure_settings.py")

        code = (
            "import importlib.util,sys;"
            "spec=importlib.util.spec_from_file_location('es',"
            "'ensure_settings.py');"
            "m=importlib.util.module_from_spec(spec);"
            "sys.modules['es']=m;spec.loader.exec_module(m);"
            "print('RC=',m.check_yaml_bool_keys('.'))"
        )
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True,
                              cwd=str(root), timeout=120)
        out = (proc.stdout or "") + (proc.stderr or "")
        self.assertIn("RC= 1", out,
                      f"R9c：含布尔键的副本**未被判红** ⇒ 守卫是假绿。\n{out}")
        self.assertIn("27/27", out, f"R9c：检查项编号不对。\n{out}")


class TestBoolKeyMutantsAreKilled(unittest.TestCase):
    """第 3 层 · 变异反证：摘掉检出分支 ⇒ 正向判据必须失效。

    ★ 这一层是「判据能红」的**唯一硬证明**——
      没有它，一条判据即便恒真也永远显示绿灯（v3.28.0 收口期实测的假绿形态）。
    """

    #: 变异锚点：`scan_yaml_bool_keys` 里的**检出分支**（必须逐字匹配真实源码）
    _ANCHOR = '''                if (isinstance(k_node, _y.ScalarNode)
                        and k_node.tag == "tag:yaml.org,2002:bool"
                        and k_node.value.lower() in _YAML11_BOOL_WORDS):'''

    _REPLACEMENT = '''                if False:  # MUTANT: 布尔键检出分支被掏空'''

    def test_r9c_removing_detection_kills_r9(self):
        """R9c：摘掉检出分支 ⇒ R9 的正向断言**必须不成立**。

        ⚠ 全程在**临时副本**的源码字符串上做变异，**绝不**改仓库里的
          `ensure_settings.py` ⇒ 反向证明不得污染真源。
        """
        src = ES.read_text(encoding="utf-8")
        self.assertIn(self._ANCHOR, src,
                      "变异锚点缺失：ensure_settings.py 的检出分支结构变了？")
        self.assertEqual(1, src.count(self._ANCHOR),
                         "变异锚点不唯一 ⇒ 变异体不可靠")
        mutated = src.replace(self._ANCHOR, self._REPLACEMENT, 1)
        self.assertNotEqual(mutated, src, "变异体构造失败 ⇒ 证明会恒真")

        # 在临时目录里用**变异源码**跑同一套正向检出
        root = Path(tempfile.mkdtemp(prefix="vetmed-boolkey-mut-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        cfg = _build_fixture(root)
        (root / "es_mutant.py").write_text(mutated, encoding="utf-8")

        es_mut = _load_es("es_bool_key_mutant", root / "es_mutant.py")
        hits = es_mut.scan_yaml_bool_keys(str(cfg))
        self.assertEqual(
            [], hits,
            f"R9c：摘掉检出分支后**仍能检出** ⇒ 检出另有来源，"
            f"或变异体没真正生效 ⇒ R9 可能是恒真判据（假守卫）。实际 {hits}")


if __name__ == "__main__":
    unittest.main()

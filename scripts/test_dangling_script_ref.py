#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第 17 项（悬空脚本引用）的**双向护栏**（v3.25.0）

══════════════════════════════════════════════════════════════════════
为什么需要这个文件：
  v3.25.0 批 3 在 `INSTALL.md` 补了「包外跑测试的布局约定」，文中引用
  `shared-core/assemble_spawn_prompt.py` —— 那是**联邦共享件**里的文件
  （本包 `scripts/` 下只有同名 shim 转发过去），引用是**正确的**，
  但第 17 项判「相对包根是否存在」⇒ 判成悬空 ⇒ 体检红。

  修法两条：
    ① 把 `assemble_spawn_prompt.py` 登记进 `known_external` 白名单；
    ② 让**带路径**的引用也能命中白名单（按 basename 匹配）。

  ⚠ 第 ② 条是**放宽**判据 ⇒ **必须有反例钉死**，否则「白名单一登记就全放行」
    会让本项彻底失效（本包铁律：假阳性必须为零；反过来，漏检同样致命）。

两条用例的判定标准：
  D1 真悬空（未登记的裸名 + 未登记的带路径）⇒ 必须判红（白名单没放宽过头）
  D2 已登记的外部件（裸名 + 带路径两种形态）⇒ 不得判红（白名单确实生效）
"""

import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = PKG / "scripts" / "ensure_settings.py"


def _load_es():
    """按路径加载 ensure_settings 模块（不改包内文件）。"""
    spec = importlib.util.spec_from_file_location("es_dangling_ut", ES)
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_dangling_ut"] = m
    spec.loader.exec_module(m)
    return m


def _run_dangling(es, root) -> tuple:
    """跑第 17 项，返回 (rc, 输出文本)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = es.check_dangling_script_ref(str(root))
    return rc, buf.getvalue()


class TestDanglingScriptRefGuard(unittest.TestCase):
    """第 17 项白名单放宽的双向护栏。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()
        cls.tmp = Path(tempfile.mkdtemp(prefix="vetmed-dangling-"))
        # 隔离副本：只拷 agents/ references/ README.md INSTALL.md 与 scripts/
        # （第 17 项只扫这几处），**绝不**改包内文件
        dst = cls.tmp / "pkg"
        dst.mkdir(parents=True, exist_ok=True)
        for sub in ("agents", "references"):
            shutil.copytree(PKG / sub, dst / sub)
        shutil.copytree(PKG / "scripts", dst / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in ("README.md", "INSTALL.md"):
            shutil.copy2(PKG / f, dst / f)
        cls.pkg = dst

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _install_md(self):
        return self.pkg / "INSTALL.md"

    def test_D1_real_dangling_still_fails(self):
        """D1：真悬空引用（裸名 + 带路径）⇒ 必须判红。

        这是白名单放宽的**反例护栏**：若这条用例变绿，说明白名单把真悬空也放过了。
        """
        p = self._install_md()
        original = p.read_text(encoding="utf-8")
        try:
            p.write_text(
                original
                + "\n\n<!-- 护栏注入 -->\n"
                + "`no_such_real_script.py` 与 `scripts/ghost_module.py`\n",
                encoding="utf-8")
            rc, out = _run_dangling(self.es, self.pkg)
            self.assertNotEqual(rc, 0, "真悬空引用未被检出（D1 失效）")
            self.assertIn("no_such_real_script.py", out)
            self.assertIn("ghost_module.py", out)
        finally:
            p.write_text(original, encoding="utf-8")

    def test_D2_registered_external_passes(self):
        """D2：已登记的外部件（裸名 + 带路径两种形态）⇒ 不得判红。

        证明白名单**确实生效**（否则 D1 之外，外部依赖会永久刷红）。
        """
        p = self._install_md()
        original = p.read_text(encoding="utf-8")
        try:
            p.write_text(
                original
                + "\n\n<!-- 护栏注入 -->\n"
                + "`assemble_spawn_prompt.py` 与 `shared-core/assemble_spawn_prompt.py`\n",
                encoding="utf-8")
            rc, out = _run_dangling(self.es, self.pkg)
            self.assertEqual(rc, 0,
                             "已登记的外部依赖被判成悬空（D2 失效）：\n" + out[-1500:])
        finally:
            p.write_text(original, encoding="utf-8")

    def test_D3_baseline_real_pkg_is_clean(self):
        """D3 基线：真实包当前无悬空引用（不靠白名单蒙混）。"""
        rc, out = _run_dangling(self.es, PKG)
        self.assertEqual(rc, 0, "真实包存在悬空脚本引用：\n" + out[-1500:])


if __name__ == "__main__":
    unittest.main(verbosity=2)

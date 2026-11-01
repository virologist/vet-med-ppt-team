#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_probe_channels.py — IMA 凭据双通道判据的能红证明（2026-11-01 B12）

─────────────────────────────────────────────────────────────────────────────
【背景（本轮 Loop A 第二轮诊断 H1 定论）】
probe_channels.py 原只读环境变量（IMA_OPENAPI_CLIENTID/APIKEY）——
但 WorkBuddy Bash 进程不加载 ~/.zshrc ⇒ 探针进程里环境变量常缺失，
而 ~/.config/ima/{client_id,api_key} 明明已配置 ⇒ 探针报 degraded = 假阴性。
ima_api.cjs（外部 skill 侧）早已支持配置文件回落；本批让探针对齐同一口径：
环境变量 > ~/.config/ima/ 配置文件，任一齐备即 credentials=True。

本文件锁住双通道判据：
  T1 双通道齐备 → credentials=True 且 source 标 config_file（无环境变量时）
  T2 两通道全缺 → credentials=False + degraded（不得假绿）
  T3 环境变量齐备 → source 标 env（优先级口径）
  T4 配置文件存在但为空 → 不算齐备（防"空文件假绿"）
每条判据配变异证明非恒真。
⚠ 全程用 monkeypatch 隔离 HOME 与 os.environ，不碰真实凭据。
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
PKG = HERE.parent


def _load_pc():
    spec = importlib.util.spec_from_file_location(
        "probe_channels", HERE / "probe_channels.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["probe_channels"] = m
    spec.loader.exec_module(m)
    return m


# 假 skill 目录（probe_ima 还会查 skill 目录，缺失会置 unavailable 覆盖凭据态；
# 本文件只锁凭据判据 ⇒ 用真实存在的 HERE 目录填平 skill 环节）
_IMA_CFG = {
    "credentials_env": ["IMA_OPENAPI_CLIENTID", "IMA_OPENAPI_APIKEY"],
    "skill_dir_candidates": [str(HERE)],
}


def _make_home(files: dict) -> Path:
    """真实临时 HOME：按 files 写出 ~/.config/ima/<name>（缺键=不创建）。"""
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="ima-home-"))
    cfg = root / ".config" / "ima"
    cfg.mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        (cfg / name).write_text(content, encoding="utf-8")
    return root


def _run_probe(env_vars: dict, home_files: dict):
    pc = _load_pc()
    home = _make_home(home_files)
    with mock.patch.dict(os.environ, env_vars, clear=False):
        # 屏蔽真实 IMA 环境变量（若有）
        for k in _IMA_CFG["credentials_env"]:
            os.environ.pop(k, None)
        os.environ.update(env_vars)
        with mock.patch.object(pc.Path, "home", return_value=home):
            return pc.probe_ima(_IMA_CFG, domain_id="animal-medicine")


class TestImaCredentialDualChannel(unittest.TestCase):
    """双通道判据：能绿也能红。"""

    def test_T1_config_file_channel_fills_in(self):
        """T1 无环境变量 + 配置文件齐备 ⇒ credentials=True，source=config_file。"""
        r = _run_probe({}, {"client_id": "cid-abc", "api_key": "key-xyz"})
        self.assertTrue(r["credentials"], "配置文件齐备应算凭据齐备")
        self.assertEqual(r["credentials_source"], "config_file")
        self.assertNotIn("凭据缺失", r.get("detail") or "")

    def test_T2_both_missing_stays_degraded(self):
        """T2 两通道全缺 ⇒ credentials=False + degraded（防假绿）。"""
        r = _run_probe({}, {})
        self.assertFalse(r["credentials"])
        self.assertEqual(r["status"], "degraded")
        self.assertIn("无配置文件", r.get("detail") or "")
        self.assertIsNone(r["credentials_source"])

    def test_T3_env_takes_priority(self):
        """T3 环境变量齐备 ⇒ source=env（即便配置文件也在）。"""
        r = _run_probe({"IMA_OPENAPI_CLIENTID": "c", "IMA_OPENAPI_APIKEY": "k"},
                       {"client_id": "cid", "api_key": "key"})
        self.assertTrue(r["credentials"])
        self.assertEqual(r["credentials_source"], "env")

    def test_T4_empty_config_file_does_not_count(self):
        """T4 配置文件存在但内容为空白 ⇒ 不算齐备（防空文件假绿）。"""
        r = _run_probe({}, {"client_id": "  \n  ", "api_key": "key"})
        self.assertFalse(r["credentials"], "空白 client_id 不得算齐备")
        self.assertEqual(r["status"], "degraded")


class TestMutantsAreKilled(unittest.TestCase):
    """变异证明：掏空判据 ⇒ 测试必须变红（判据非恒真）。"""

    def _mutated_probe(self, old: str, new: str) -> None:
        src = (HERE / "probe_channels.py").read_text(encoding="utf-8")
        assert src.count(old) == 1, f"锚点出现 {src.count(old)} 次"
        mutated = src.replace(old, new, 1)
        mod = importlib.util.module_from_spec(
            importlib.util.spec_from_loader("pc_mut", None))
        mod.__dict__["__file__"] = str(HERE / "probe_channels.py")
        exec(compile(mutated, "probe_channels_mut", "exec"), mod.__dict__)
        return mod

    def test_mutant_drop_file_fallback_makes_T1_red(self):
        """变异：删掉配置文件回落 ⇒ T1 场景必须判 False（证明回落判据真实生效）。"""
        mod = self._mutated_probe(
            "        if file_ok:",
            "        if False:  # MUTANT: 回落被掏空")
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in _IMA_CFG["credentials_env"]:
                os.environ.pop(k, None)
            with mock.patch.object(mod.Path, "home",
                                   return_value=_make_home(
                                       {"client_id": "c", "api_key": "k"})):
                r = mod.probe_ima(_IMA_CFG, domain_id="animal-medicine")
        # 变异语义：掏空回落 ⇒ 配置文件场景必须翻松（判 False）。
        # 若变异体仍判 True，说明该场景根本不经过回落判据 ⇒ 本守卫空转。
        self.assertFalse(r["credentials"],
                         "变异体仍判 True ⇒ 回落判据没被这个测试覆盖（守卫空转）")

    def test_mutant_accept_empty_file_makes_T4_red(self):
        """变异：去掉 strip() 空白校验 ⇒ T4 场景须翻红（证明空白防线真实生效）。"""
        mod = self._mutated_probe(
            'read_text(\n                encoding="utf-8", errors="replace").strip()',
            'read_text(\n                encoding="utf-8", errors="replace")  # MUTANT')
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in _IMA_CFG["credentials_env"]:
                os.environ.pop(k, None)
            with mock.patch.object(mod.Path, "home",
                                   return_value=_make_home(
                                       {"client_id": " \n ", "api_key": "k"})):
                r = mod.probe_ima(_IMA_CFG, domain_id="animal-medicine")
        # 变异语义：去掉 strip ⇒ 空白文件场景必须翻松（判 True）。
        # 若变异体仍判 False，说明空白场景不经过 strip 判据 ⇒ T4 守卫空转。
        self.assertTrue(r["credentials"],
                        "变异体仍判 False ⇒ strip 判据没被这个测试覆盖（守卫空转）")


if __name__ == "__main__":
    unittest.main()

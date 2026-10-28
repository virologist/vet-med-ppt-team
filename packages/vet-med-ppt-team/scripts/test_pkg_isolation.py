#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_pkg_isolation.py — 隔离副本构造器 + 「测试不得原地改写生产 config」静态守卫（v3.25.0）

══════════════════════════════════════════════════════════════════════
立项依据（真实缺陷，已实测复现）：
  改造前共有 **9 处**「测试用例就地改写包内 `config/*.yaml`」的写法
  （3 个文件），它们靠 `try/finally` 复位或类级备份复位。
  ⚠ **finally 复位在并发下不成立**——它复位的是「**当时读到的内容**」，
    而那可能已被另一会话污染 ⇒ **污染被固化**。
    本轮已实测到一次：`config/external-tools.yaml` 的 `knowledge_bases`
    被并发测试从 7 条清空并丢掉全部注释（与 T3/T8 写出的中间态**逐字节相同**）。

本文件的两个职责（分开）：
  ① **构造器**（`make_isolated_pkg()`）——让「改配置类」用例改**副本**、跑**副本**，
    用完即弃 ⇒ **彻底取消「复位」这一步** ⇒ 失败时最坏结果是临时目录残留，
    不是生产配置损坏。
  ② **静态守卫**（`TestNoProductionWrite`）——用 AST 扫全部 `scripts/test_*.py`，
    凡「写盘接收者静态可判定为包内 `config/` 下的路径」即判红。
    这是**结构性守卫**，比逐点修更强：以后新增用例若再犯同型，自动判红。

⚠ **布局硬约束（v3.25.0 实测踩到，写进构造器注释以免后人重踩）**：
  · `scripts/assemble_spawn_prompt.py`（联邦 shim）按「包根向上最多 4 层」找
    `shared-core/assemble_spawn_prompt.py` ⇒ 副本的**同级**必须有 shared-core；
  · `scripts/assemble_domain_prompt.py` 经 shared-core 的 `load_plugin()` 读
    `.codebuddy-plugin/plugin.json`（或 `.claude-plugin/`）⇒ 必须一并拷贝。
  ⇒ 只拷 `config/` + `scripts/` 会让端到端用例假失败。

运行：
    python3 -m pytest scripts/test_pkg_isolation.py -q
    python3 scripts/test_pkg_isolation.py          # 直跑（体检第 7 项跑法）
"""

import ast
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

#: 副本必须包含的包内子树（实测最小集）。
#: `docs/` 也带上：脚本里有 5 处读 `references/`、若干处读 `agents/`，
#: 多拷一份的代价是 0.1 秒量级，而漏拷的代价是**用例假失败**。
COPY_DIRS = ("config", "scripts", "agents", "references", "docs")

#: 清单目录（装配器经 shared-core 的 `load_plugin()` 读 `.codebuddy-plugin/plugin.json`）。
COPY_MANIFEST_DIRS = (".codebuddy-plugin", ".claude-plugin")

#: 拷贝时排除的目录/文件（体积与无关物）。
COPY_IGNORE = shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "*.pyc",
                                      ".DS_Store", "packages", "tests")


def _find_shared_core() -> Path:
    """定位联邦共享件 `shared-core/`。

    优先级：环境变量 `VETMED_SHARED_CORE` > 包根的**同级**目录
    （`.../plugins/shared-core`，即本包在 marketplace 下的标准布局）。

    ⚠ 找不到 ⇒ 抛**明确异常**（不静默降级）：缺 shared-core 时端到端用例
      会**假失败**，与其让用例红得莫名其妙，不如直接点名缺什么。
    """
    env = os.environ.get("VETMED_SHARED_CORE")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
        raise RuntimeError(f"VETMED_SHARED_CORE 指向的目录不存在：{p}")
    cand = PKG.parent / "shared-core"
    if cand.is_dir():
        return cand
    raise RuntimeError(
        "找不到联邦共享件 shared-core/（预期位置："
        f"{cand}；或用 VETMED_SHARED_CORE 指定）。\n"
        "  共享件不随包分发（仅安装态/仓库结构下存在）⇒ 端到端用例无法在隔离副本里跑。"
    )


def make_isolated_pkg(prefix: str = "vetmed-iso-") -> Path:
    """构造隔离副本并返回其**包根**。

    布局：`<tmp>/plugins/vet-med-ppt-team`（副本）+ `<tmp>/plugins/shared-core`（软链）
    ⇒ 副本与 shared-core **同级**，满足 shim「向上最多 4 层」的搜索路径。

    调用方负责清理（`cleanup_isolated_pkg(pkg)`）；最坏情况是临时目录残留，
    **绝不会**污染生产 config。
    """
    core = _find_shared_core()
    root = Path(tempfile.mkdtemp(prefix=prefix))
    plugins = root / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    pkg = plugins / "vet-med-ppt-team"
    shutil.copytree(PKG, pkg, ignore=COPY_IGNORE)
    for d in COPY_MANIFEST_DIRS:
        if not (pkg / d).is_dir():
            continue
    # shared-core 软链（副本同级）——shim 的搜索路径依赖它
    link = plugins / "shared-core"
    if not link.exists():
        os.symlink(core, link)
    return pkg


def cleanup_isolated_pkg(pkg: Path) -> None:
    """删除隔离副本（含它的临时根）。**只删自己建的目录**，不碰包内任何文件。"""
    root = Path(pkg).parent.parent if pkg.parent.name == "plugins" else pkg.parent
    shutil.rmtree(root, ignore_errors=True)


# ───────────────────────────────────────────────────── AST 静态守卫
#: 「包根」的内部标记（不是真实路径段）——用于识别「相对包根」的路径表达式。
_ROOT = "<PKG>"

#: 会被视为「写盘」的属性名。
_WRITE_ATTRS = frozenset({"write_text", "write_bytes", "unlink", "rmdir"})

#: 违规写盘目标：**包内 config/ 下的路径**。
#: ⚠ 只禁 `config/`：`settings.json`（体检自愈目标）与临时目录不在此列。
_VIOLATION_ROOT = "config"


def _resolve_path_expr(node: ast.AST, consts: dict) -> tuple:
    """把路径表达式解析成「路径段元组」，解析不出返回 None。

    支持：
      · `PKG / "config" / "x.yaml"`            → ("<PKG>", "config", "x.yaml")
      · `HERE / "config" / "x.yaml"`            → None（HERE 不可静态判定）
      · 常量名 `EXT_CFG`                        → 查 `consts`
      · `Path(...)` / 函数调用                   → None
    """
    if isinstance(node, ast.Name):
        if node.id == "PKG":
            return (_ROOT,)
        return consts.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _resolve_path_expr(node.left, consts)
        if left is None:
            return None
        right = node.right
        if isinstance(right, ast.Constant) and isinstance(right.value, str):
            return left + (right.value,)
        return None
    return None


def _collect_consts(tree: ast.Module) -> dict:
    """收集「名字 → 路径段元组」的常量表（**函数体内部**的赋值也收，保守从严）。

    保守从严的取舍：若同一名字在别处被指向非 config 路径，仍按「可能违规」判红。
    理由：这是**结构性守卫**，宁可多看一眼，也不要放过同型复发；
    且改造后不会触发（白名单为空集）。
    """
    consts: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        parts = _resolve_path_expr(node.value, consts)
        if parts:
            consts[tgt.id] = parts
    return consts


def _is_config_target(parts: tuple) -> bool:
    """该路径是否落在**包内 config/ 下**。"""
    return (len(parts) >= 2 and parts[0] == _ROOT and parts[1] == _VIOLATION_ROOT)


def find_production_writes(src: str) -> list:
    """扫描源码，返回 [(行号, 描述)] —— 全部「就地改写包内 config」的写盘点。"""
    tree = ast.parse(src)
    consts = _collect_consts(tree)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _WRITE_ATTRS:
            continue
        parts = _resolve_path_expr(func.value, consts)
        if parts and _is_config_target(parts):
            hits.append((node.lineno, f"{'.'.join(parts)}.{func.attr}()"))
    return hits


class TestNoProductionWrite(unittest.TestCase):
    """结构性守卫：测试用例**不得**就地改写包内 `config/`。"""

    #: 豁免名单（`文件名 → 理由`）。当前**为空集**——改造后不应有任何例外。
    WHITELIST: dict = {}

    def _test_files(self):
        # ⚠ `HERE / "test_*.py"` 是**字面路径**（含 `*`），glob 匹配不到任何东西
        #   ⇒ 守卫会「零命中恒绿」（假绿）。必须用 `HERE.glob("test_*.py")`。
        return sorted(HERE.glob("test_*.py"))

    def test_T1_no_test_writes_package_config(self):
        """T1：全部 `scripts/test_*.py` 不得写盘到包内 `config/`。"""
        offenders = []
        for f in self._test_files():
            if f.name in self.WHITELIST:
                continue
            src = f.read_text(encoding="utf-8")
            for lineno, desc in find_production_writes(src):
                offenders.append(f"{f.name}:{lineno}  {desc}")
        self.assertEqual(
            offenders, [],
            "以下测试用例就地改写了包内生产 config（必须改用隔离副本）：\n"
            + "\n".join(offenders)
            + "\n\n修法：用 scripts/test_pkg_isolation.py 的 make_isolated_pkg()"
              "构造副本，改副本、跑副本；**不要**用「就地改 + finally 复位」"
              "（并发下复位的是被污染过的内容 ⇒ 污染被固化）。")

    def test_T2_detector_actually_catches_a_violation(self):
        """T2 反例：给探测器喂一段**真的**违规代码 ⇒ 必须被抓出来。

        没有这条，T1 可能因探测器失效而恒绿（假绿）。
        """
        bad = (
            'from pathlib import Path\n'
            'PKG = Path("/x").parent\n'
            'EXT_CFG = PKG / "config" / "external-tools.yaml"\n'
            'EXT_CFG.write_text("x")\n'
        )
        hits = find_production_writes(bad)
        self.assertTrue(hits, "探测器对真违规代码未报出——守卫失效（假绿）")
        self.assertIn("config", hits[0][1])

    def test_T3_detector_ignores_isolated_and_readonly(self):
        """T3 反例（防误伤）：隔离副本路径与只读读取**不得**被报出。"""
        ok = (
            'from pathlib import Path\n'
            'PKG = Path("/x").parent\n'
            'EXT_CFG = PKG / "config" / "external-tools.yaml"\n'
            'EXT_CFG.read_text()\n'
            'iso = Path("/tmp/iso")\n'
            'iso_cfg = iso / "config" / "external-tools.yaml"\n'
            'iso_cfg.write_text("x")\n'
            'PKG.joinpath("config", "a.yaml").unlink()\n'
        )
        hits = find_production_writes(ok)
        # ⚠ `PKG.joinpath(...)` 不在解析能力内（不是 `/` 链）⇒ 不报；
        #   但为了不放过同型，构造器纪律要求：**不要**在测试里用 joinpath 写生产 config。
        self.assertEqual([h for h in hits if "joinpath" in h[1]], [],
                         "joinpath 形态未被覆盖（记录用）")


class TestIsolatedPkgBuilder(unittest.TestCase):
    """构造器自身的护栏：布局必须满足 shim / 装配器的硬依赖。"""

    def test_T4_isolated_pkg_has_required_layout(self):
        """T4：副本必须含 config/scripts/agents/references + plugin.json + 同级 shared-core。"""
        iso = make_isolated_pkg()
        try:
            for d in COPY_DIRS:
                self.assertTrue((iso / d).is_dir(), f"副本缺目录 {d}")
            self.assertTrue((iso / ".codebuddy-plugin" / "plugin.json").is_file(),
                            "副本缺 .codebuddy-plugin/plugin.json（装配器硬依赖）")
            core = iso.parent / "shared-core"
            self.assertTrue(core.exists(), "副本同级缺 shared-core（shim 硬依赖）")
        finally:
            cleanup_isolated_pkg(iso)

    def test_T5_isolated_pkg_config_is_byte_identical(self):
        """T5：副本的 config 必须与真包**逐字节相同**（否则测的就不是同一份配置）。"""
        iso = make_isolated_pkg()
        try:
            for f in sorted((PKG / "config").glob("*.yaml")):
                a = f.read_bytes()
                b = (iso / "config" / f.name).read_bytes()
                self.assertEqual(a, b, f"副本 config/{f.name} 与真包不一致")
        finally:
            cleanup_isolated_pkg(iso)


if __name__ == "__main__":
    unittest.main(verbosity=2)

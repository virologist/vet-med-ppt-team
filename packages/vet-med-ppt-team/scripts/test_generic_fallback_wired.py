#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_generic_fallback_wired.py — 「通用兜底人设」链路的端到端守卫（能红）
=================================================================================

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（真实教训：调研误判「未接线」）】
─────────────────────────────────────────────────────────────────────────────
第 18 项死配置巡检曾把 `fallback.generic_persona` / `generic_evidence_hierarchy`
/ `generic_safety_redlines` 三键列为「零读取点」。调研也一度结论「链路整体未接线」。

★ **实测推翻**（2026-10-31 终验，可复现）：
  无坍缩装配（`--allow-unconfirmed`，rc=0）的产物里，三键内容**逐字投递**：
    【通用人设】称号/背景/立场/职责边界
    【通用证据轴】机构轴 + 文献轴
    【通用红线】两条底线
  真实链路（**跨函数局部变量传递**，AST 静态判据看不见）：
    main():1080  `fallback = _fallback_block(profiles)`
    main():1135  `build_domain_section(..., fallback, ...)`
    build():803/813/827  `_render_generic(fallback)`   ← 三键在此被逐键读取
    _render_generic():287/297/306  `fb.get("generic_persona")` 等

⇒ 教训（与本包既有标注一致）：**静态 AST 判据对「跨函数数据流」天然失明**，
  「0 读取点」≠「没接线」。**但**这不能只停留在口头教训——
  若日后有人删掉 `_render_generic`、改坏 `fallback` 传参、或删掉 config 三键，
  第 18 项**不会报**（三键本来就在弱证据桶）⇒ 链路会**静默断掉**。
  ⇒ 本文件就是那条**运行时守卫**：端到端跑装配器，断言三键内容真的到达产物。

─────────────────────────────────────────────────────────────────────────────
【判据设计（能红 + 防误伤）】
─────────────────────────────────────────────────────────────────────────────
  R1 端到端正向  —— 隔离副本跑真装配器（无坍缩态）⇒ 产物必须含三段通用兜底，
                    且内容与 config 真源**逐字一致**（不是「存在即可」，是「值对」）
  R2 变异①断链  —— 摘掉 `fallback = _fallback_block(profiles)` 赋值 ⇒ R1 必须红
  R3 变异②删消费 —— 摘掉 `_render_generic` 的 generic_persona 读取 ⇒ R1 必须红
  R4 config 缺键 —— 隔离副本删掉 config 的 generic_persona ⇒ 产物【通用人设】段
                    必须消失对应字段（守卫不得因「渲染器跳过空值」而假红）

⚠ 全程在**临时目录隔离副本**上变异，**绝不**改包内真源。
⚠ 跑装配器用子进程（`--allow-unconfirmed` 逃生口），与既有 test_c4_key_wiring 同范式。
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

#: 真源 config（供内容逐字比对）
TRUE_PROFILE = PKG / "config" / "domain-profiles.yaml"

#: 三个被守卫的键 + 各自产物中的锚点行（与 _render_generic 的渲染格式逐字对应）
EXPECTED_ANCHORS = (
    "【通用人设】（不含任何域专有信息）",
    "【通用证据轴】（两条独立轴）",
    "【通用红线】（任何域都成立的底线）",
)


def _load_yaml(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


#: 域上下文注入段的边界标记（与 assemble_domain_prompt.py 的 DOMAIN_BEGIN/END 逐字一致）
_DOMAIN_BEGIN = "==================== 域上下文（v3.17.0 坍缩产物注入） ===================="
_DOMAIN_END = "==================== 域上下文结束 ===================="


def _domain_section(full_text: str) -> str:
    """截取装配产物中的**域上下文注入段**。

    ⚠ 为什么不能全文搜：成员 MD 正文本身就会提到「内容权威」「证据等级」等词
    （角色描述与降级纪律的说明文字），全文断言会把「MD 里的字」误判成
    「渲染投递的值」⇒ 变异证明恒假（实测踩坑）。只断言注入段 = 只验真投递。
    """
    start = full_text.find(_DOMAIN_BEGIN)
    if start < 0:
        return ""
    end = full_text.find(_DOMAIN_END, start)
    return full_text[start:end if end > 0 else len(full_text)]


class _IsoPkg:
    """隔离副本专家包（最小骨架：装配器可跑 + config 可换）。"""

    def __init__(self, tmp_root: Path):
        self.root = tmp_root
        # 只复制装配器需要的部分（scripts + config + members 白名单来源）
        shutil.copytree(PKG / "scripts", tmp_root / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(PKG / "config", tmp_root / "config",
                        ignore=shutil.ignore_patterns("__pycache__"))
        # plugin.json / agents 是装配器白名单与成员 MD 的来源
        for rel in (".codebuddy-plugin/plugin.json", "agents"):
            src = PKG / rel
            dst = tmp_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst,
                                ignore=shutil.ignore_patterns("__pycache__"))
            elif src.is_file():
                shutil.copy2(src, dst)
        # ⚠ vendor/shared-core 是装配器 shim 的兜底联邦件（隔离副本无上游联邦层
        #   可向上查找 ⇒ 必须随副本分发，否则 shim 报「shared-core 缺失」exit 3）
        if (PKG / "vendor" / "shared-core").is_dir():
            shutil.copytree(PKG / "vendor" / "shared-core",
                            tmp_root / "vendor" / "shared-core")

    def config_path(self):
        return self.root / "config" / "domain-profiles.yaml"

    def assembler(self):
        return self.root / "scripts" / "assemble_domain_prompt.py"

    def run_assemble(self):
        """跑无坍缩装配（--allow-unconfirmed 逃生口），返回 (rc, 产物文本, stderr)。"""
        out = self.root / "out.md"
        proc = subprocess.run(
            [sys.executable, str(self.assembler()),
             "--member", "dvm-content-expert",
             "--allow-unconfirmed", "--out", str(out)],
            capture_output=True, text=True, cwd=str(self.root), timeout=180)
        text = out.read_text(encoding="utf-8") if out.exists() else ""
        return proc.returncode, text, (proc.stderr or "")


class TestGenericFallbackWired(unittest.TestCase):
    """R1：端到端——三键内容必须真的到达装配产物（值级断言，非存在级）。"""

    def test_r1_generic_fallback_reaches_output(self):
        iso = _IsoPkg(Path(tempfile.mkdtemp(prefix="vetmed-gfb-")))
        self.addCleanup(shutil.rmtree, iso.root, ignore_errors=True)

        rc, text, err = iso.run_assemble()
        self.assertEqual(rc, 0, f"装配器应成功（无坍缩走兜底路径）：\n{err}")

        seg = _domain_section(text)
        self.assertTrue(seg, "产物中未找到域上下文注入段")

        # ① 三段锚点必须在
        for anchor in EXPECTED_ANCHORS:
            self.assertIn(anchor, seg, f"注入段缺通用兜底段锚点：{anchor}")

        # ② **值级断言**：注入段内容必须与 config 真源逐字一致
        cfg = _load_yaml(iso.config_path())["fallback"]
        gp = cfg["generic_persona"]
        for field in ("title", "background", "stance", "duty_boundary"):
            self.assertIn(gp[field], seg,
                          f"通用人设.{field} 的值未到达注入段（链路断了？）：{gp[field]!r}")
        red = cfg["generic_safety_redlines"]
        for line in red:
            self.assertIn(line, seg, f"通用红线条目未到达注入段：{line!r}")
        gh = cfg["generic_evidence_hierarchy"]
        for axis in ("institutional", "literature"):
            for item in gh[axis]:
                self.assertIn(item, seg, f"通用证据轴.{axis} 条目未到达注入段：{item!r}")


class TestGenericFallbackMutants(unittest.TestCase):
    """R2/R3：变异证明——链路被改坏时 R1 **必须**变红（否则 R1 是恒真假守卫）。"""

    def _mutated_iso(self, anchor: str, replacement: str) -> _IsoPkg:
        """造一个「源码被改坏」的隔离副本；锚点不唯一/缺失 ⇒ 直接抛错（防假 mutant）。"""
        iso = _IsoPkg(Path(tempfile.mkdtemp(prefix="vetmed-gfb-mut-")))
        self.addCleanup(shutil.rmtree, iso.root, ignore_errors=True)
        p = iso.assembler()
        src = p.read_text(encoding="utf-8")
        self.assertEqual(1, src.count(anchor),
                         f"变异锚点不唯一（{src.count(anchor)} 处）⇒ mutant 不可靠：{anchor!r}")
        p.write_text(src.replace(anchor, replacement, 1), encoding="utf-8")
        return iso

    def test_r2_breaking_fallback_assignment_makes_r1_red(self):
        """R2：断链变异——摘掉 fallback 赋值 ⇒ R1 的**值级**断言必须不成立。

        ⚠ 实测教训（首版踩坑）：`_render_generic({})` 仍会输出三段**标题行**
        （`【通用人设】`等）⇒ 若只断言「标题不在」，断链变异体照样有标题
        ⇒ R2 恒假。**断言必须锁值级内容**（称号/红线原文），标题不可靠。
        """
        iso = self._mutated_iso(
            "        fallback = _fallback_block(profiles)",
            "        fallback = {}  # MUTANT: 链路被切断")
        rc, text, err = iso.run_assemble()
        seg = _domain_section(text)
        # 值级断言：config 真源里的具体值必须**全部**从注入段消失
        cfg = _load_yaml(iso.config_path())["fallback"]
        self.assertNotIn(cfg["generic_persona"]["title"], seg,
                         "断链后通用人设称号仍在注入段 ⇒ 渲染另有数据来源 ⇒ R1 恒真")
        for line in cfg["generic_safety_redlines"]:
            self.assertNotIn(line, seg,
                             f"断链后通用红线仍在注入段 ⇒ R1 恒真：{line!r}")
        for axis in ("institutional", "literature"):
            for item in cfg["generic_evidence_hierarchy"][axis]:
                self.assertNotIn(item, seg,
                                 f"断链后证据轴条目仍在注入段 ⇒ R1 恒真：{item!r}")

    def test_r3_removing_generic_persona_read_makes_r1_red(self):
        """R3：删消费变异——摘掉 _render_generic 的通用人设读取 ⇒ **值级**内容必须消失。

        ⚠ 与 R2 同理：标题行 `【通用人设】` 由无条件 `append` 产生，
        删掉读取后标题仍在 ⇒ 必须断言**字段值**消失（而非标题）。
        """
        iso = self._mutated_iso(
            '    gp = fb.get("generic_persona") or {}',
            '    gp = {}  # MUTANT: 消费点被删除')
        rc, text, err = iso.run_assemble()
        seg = _domain_section(text)
        gp = _load_yaml(iso.config_path())["fallback"]["generic_persona"]
        for field in ("title", "background", "stance", "duty_boundary"):
            self.assertNotIn(gp[field], seg,
                             f"删消费点后通用人设.{field} 仍在注入段 ⇒ 渲染另有来源 ⇒ R1 恒真")

    def test_r4_config_missing_key_renders_empty_not_crash(self):
        """R4：config 缺键 ⇒ 渲染器跳过空值（不崩、不出半截内容），守卫不得假红。

        ⚠ 这条是 R1 的**防误伤**配套：若日后 config 精简掉某键，
          本测试保证装配器**优雅降级**（渲染器 `or {}` 兜底），而不是崩溃。
        """
        iso = _IsoPkg(Path(tempfile.mkdtemp(prefix="vetmed-gfb-miss-")))
        self.addCleanup(shutil.rmtree, iso.root, ignore_errors=True)
        p = iso.config_path()
        cfg = _load_yaml(p)
        cfg["fallback"].pop("generic_persona")
        import yaml
        p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")

        rc, text, err = iso.run_assemble()
        self.assertEqual(rc, 0, f"缺键应优雅降级而非崩溃：\n{err}")
        seg = _domain_section(text)
        self.assertNotIn("【通用人设】", seg, "缺 generic_persona 时不得渲染空壳段")
        self.assertIn("【通用红线】", seg, "其余段应照常渲染")
        # 红线内容仍须逐字到达（该键未被删）
        for line in cfg["fallback"]["generic_safety_redlines"]:
            self.assertIn(line, seg)


if __name__ == "__main__":
    unittest.main()

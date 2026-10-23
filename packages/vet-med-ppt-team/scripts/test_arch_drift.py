#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_arch_drift.py — 文档↔yaml 架构防漂移守卫（v3.16.0 · W5 批次）
================================================================
背景（真实缺陷，非假设）：`docs/architecture.md` 在 v3.0.0（六阶段→四闸）、
v3.3.0（追加 stage 4 闸4.5）之后**仍描述六阶段流水线**，且「团队组成」表**漏掉 verifier**
（yaml#members 自 v3.0.0 起就有 5 名成员）。文档与真源之间无任何机器拦截 → 必然继续漂移。

守卫思路（廉价、可证伪）：
  architecture.md 内嵌一块**机器比对用的阶段镜像块**（sentinel 包裹的竖线分隔行），
  本脚本把它与 `config/harness.yaml#stages` 逐项比对；再比对成员表与 agents/ 目录。

断言：
  T1 阶段镜像块 == yaml#stages（stage 集合 / 名称 / 成员 / gate / 并行标记）
  T2 镜像块格式可解析（sentinel 存在、5 段、stage 编号连续自 0 起）
  T3 每个 stage 成员都登记在 yaml#members（单向子集：新增注册成员不误报）
  T4 architecture.md「团队组成」表的 Agent ID == {主理人} ∪ yaml#members 全键
  T5 agents/*.md（除 *-team-lead）文件名集合 == yaml#members 全键
  T6 「六阶段」只出现在「历史沿革」章节之后（旧口径复活检测）
  T7 每个成员的 MD 都把工具白名单指向 config/harness.yaml（不在 MD 另写清单）

为何不会假阳性（设计取舍，改动前请先读）：
  ① 只解析 sentinel 之间的结构化行与两张显式表格，**不扫散文**——散文里的阶段描述怎么改都不触发；
  ② yaml 侧做单向子集判定（stage 成员 ⊆ 成员注册表），yaml 新增成员不会误报；
  ③ `docs/architecture.md` / `config/harness.yaml` / `agents/` 任一缺失 → **SKIP 不 FAIL**
     （packages/ 副本等局部树不误报；真缺失由 ensure_settings 第 5/15 项兜底）；
  ④ T4/T5 用集合相等，是刻意选的"强判据"：成员表漏人（本次真实缺陷）或注册了没有 MD 的成员
     都属**真漂移**，宁可 FAIL 也不静默。

用法：
    python3 -m pytest scripts/test_arch_drift.py -q
    python3 scripts/test_arch_drift.py          # 体检第 7 项按此方式逐个跑
退出码：0 通过 / 1 失败（unittest 语义）
"""

import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ARCH_MD = PKG / "docs" / "architecture.md"
HARNESS_YAML = PKG / "config" / "harness.yaml"
AGENTS_DIR = PKG / "agents"

BEGIN = "<!-- STAGE_MIRROR_BEGIN -->"
END = "<!-- STAGE_MIRROR_END -->"
HISTORY_HEADING = "## 历史沿革"
LEGACY_TERM = "六阶段"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class _Base(unittest.TestCase):
    """公共装载：文件缺失一律 SKIP（不误报），yaml 解析失败才 FAIL。"""

    def setUp(self):
        missing = [str(p) for p in (ARCH_MD, HARNESS_YAML) if not p.is_file()]
        if missing:
            self.skipTest(f"缺少比对输入：{', '.join(missing)}（局部树，跳过防漂移比对）")
        try:
            import yaml
        except ImportError:  # pragma: no cover - 环境缺 PyYAML 时不明示失败
            self.skipTest("未安装 PyYAML，跳过防漂移比对")
            return
        with open(HARNESS_YAML, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.stages = self.cfg.get("stages") or {}
        self.members = self.cfg.get("members") or {}
        self.arch = _read(ARCH_MD)
        self.lines = self.arch.splitlines()

    # ── 解析辅助 ─────────────────────────────────────────────
    def mirror_rows(self):
        """取 sentinel 之间的镜像行；返回 [(原始行号, 行文本)]。"""
        start = next((i for i, l in enumerate(self.lines) if l.strip() == BEGIN), None)
        end = next((i for i, l in enumerate(self.lines) if l.strip() == END), None)
        if start is None or end is None or end <= start:
            self.fail(f"architecture.md 缺阶段镜像块（须含 {BEGIN} / {END} 两行 sentinel）")
        return [(i, self.lines[i]) for i in range(start + 1, end)
                if self.lines[i].strip()]

    @staticmethod
    def parse_row(text):
        """`stage 0 | 名称 | members: a, b | gate: g | parallel: yes` → dict。"""
        parts = [p.strip() for p in text.split("|")]
        if len(parts) != 5:
            raise ValueError(f"镜像行须为 5 段竖线分隔，实得 {len(parts)} 段：{text!r}")
        m = re.match(r"^stage\s+(\d+)$", parts[0], re.I)
        if not m:
            raise ValueError(f"第 1 段须形如 'stage <n>'：{parts[0]!r}")
        members_raw = parts[2].split(":", 1)[1].strip() if ":" in parts[2] else ""
        members = [] if members_raw in ("", "-") else \
            [x.strip() for x in members_raw.split(",") if x.strip()]
        gate = parts[3].split(":", 1)[1].strip() if ":" in parts[3] else ""
        parallel = parts[4].split(":", 1)[1].strip().lower() if ":" in parts[4] else ""
        return {"stage": int(m.group(1)), "name": parts[1], "members": members,
                "gate": gate, "parallel": parallel}


class TestStageMirror(_Base):
    def test_T2_mirror_block_parseable(self):
        rows = self.mirror_rows()
        parsed = []
        for lineno, text in rows:
            try:
                parsed.append(self.parse_row(text))
            except ValueError as e:
                self.fail(f"architecture.md:{lineno + 1} 镜像行不可解析 → {e}")
        self.assertTrue(parsed, "阶段镜像块为空")
        self.assertEqual([p["stage"] for p in parsed], list(range(len(parsed))),
                         "镜像块 stage 编号须自 0 起连续")

    def test_T1_mirror_matches_yaml_stages(self):
        parsed = {}
        for lineno, text in self.mirror_rows():
            try:
                row = self.parse_row(text)
            except ValueError as e:
                self.fail(f"architecture.md:{lineno + 1} → {e}")
            parsed[row["stage"]] = row
        self.assertEqual(set(parsed), set(int(k) for k in self.stages),
                         "镜像块 stage 集合与 config/harness.yaml#stages 不一致（改 yaml 须同步镜像块）")
        for sid, row in sorted(parsed.items()):
            y = self.stages.get(sid, {})
            self.assertEqual(row["name"], str(y.get("name", "")).strip(),
                             f"stage {sid} 名称与 yaml 不一致")
            self.assertEqual(sorted(row["members"]), sorted(y.get("members") or []),
                             f"stage {sid} 成员与 yaml 不一致")
            self.assertEqual(row["gate"], str(y.get("gate", "")).strip(),
                             f"stage {sid} gate 与 yaml 不一致")
            want = "yes" if len(y.get("members") or []) > 1 else "no"
            self.assertEqual(row["parallel"], want,
                             f"stage {sid} 并行标记与 yaml#members 数量不符（≥2 人才并行）")

    def test_T3_stage_members_registered(self):
        unknown = set()
        for sid, y in self.stages.items():
            for m in (y.get("members") or []):
                if m not in self.members:
                    unknown.add(f"stage {sid} → {m}")
        self.assertFalse(unknown, f"阶段调度了未注册的成员：{sorted(unknown)}")


class TestMemberTable(_Base):
    def _table_ids(self):
        """抽取「团队组成」章节表格首列的反引号 Agent ID。"""
        start = next((i for i, l in enumerate(self.lines)
                      if l.startswith("## 团队组成")), None)
        if start is None:
            self.fail("architecture.md 缺「## 团队组成」章节")
        end = next((i for i, l in enumerate(self.lines[start + 1:], start + 1)
                    if l.startswith("## ")), len(self.lines))
        ids = []
        for line in self.lines[start + 1:end]:
            if not line.strip().startswith("|"):
                continue
            cell = line.split("|")[1] if len(line.split("|")) > 1 else ""
            m = re.search(r"`([A-Za-z0-9._-]+)`", cell)
            if m:
                ids.append(m.group(1))
        return set(ids)

    def test_T4_member_table_matches_registry(self):
        if not AGENTS_DIR.is_dir():
            self.skipTest(f"缺少 {AGENTS_DIR}（局部树，跳过）")
        lead = [p.stem for p in AGENTS_DIR.glob("*.md") if p.stem.endswith("team-lead")]
        self.assertTrue(lead, "agents/ 下未找到 *-team-lead 的 MD")
        expect = set(self.members) | {lead[0]}
        self.assertEqual(self._table_ids(), expect,
                         "「团队组成」表与 config/harness.yaml#members 不一致（漏人或多出幽灵成员）")

    def test_T5_agent_files_match_registry(self):
        if not AGENTS_DIR.is_dir():
            self.skipTest(f"缺少 {AGENTS_DIR}（局部树，跳过）")
        md_ids = {p.stem for p in AGENTS_DIR.glob("*.md")
                  if not p.stem.endswith("team-lead")}
        self.assertEqual(md_ids, set(self.members),
                         "agents/*.md 与 config/harness.yaml#members 不一致"
                         "（有 MD 未注册，或注册了没有 MD 的成员）")


class TestLegacyWording(_Base):
    def test_T6_legacy_six_stage_only_in_history(self):
        hist = next((i for i, l in enumerate(self.lines)
                     if l.startswith(HISTORY_HEADING)), None)
        if hist is None:
            self.fail(f"architecture.md 缺「{HISTORY_HEADING}」章节：已废弃口径无处标注")
        strays = [i + 1 for i, l in enumerate(self.lines)
                  if LEGACY_TERM in l and i <= hist]
        self.assertFalse(strays,
                         f"{LEGACY_TERM}（已废弃口径）出现在历史沿革之前，行号：{strays}")


class TestToolWhitelistSingleSource(unittest.TestCase):
    def setUp(self):
        if not (HARNESS_YAML.is_file() and AGENTS_DIR.is_dir()):
            self.skipTest("缺少 config/harness.yaml 或 agents/（局部树，跳过）")
        import yaml
        with open(HARNESS_YAML, encoding="utf-8") as f:
            self.members = (yaml.safe_load(f) or {}).get("members") or {}

    def test_T7_each_member_md_points_to_yaml(self):
        bad = []
        for mid in sorted(self.members):
            p = AGENTS_DIR / f"{mid}.md"
            if not p.is_file():
                continue  # 缺 MD 由 T5 负责报错，此处不重复计
            text = _read(p)
            if "harness.yaml" not in text or "工具白名单" not in text:
                bad.append(mid)
        self.assertFalse(bad, f"下列成员 MD 未把工具白名单指向 config/harness.yaml：{bad}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

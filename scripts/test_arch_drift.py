#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_arch_drift.py — 文档↔yaml 架构防漂移守卫（v3.16.0 · W5 批次 / v3.17.0 扩面）
=================================================================================
背景（真实缺陷，非假设）：
  · `docs/architecture.md` 在 v3.0.0（六阶段→四闸）、v3.3.0（追加 stage 4 闸4.5）
    之后**仍描述六阶段流水线**，且「团队组成」表**漏掉 verifier**（yaml#members
    自 v3.0.0 起就有 5 名成员）。文档与真源之间无任何机器拦截 → 必然继续漂移。
  · v3.17.0 实测**同型漂移复发**：上一轮只修了 `docs/architecture.md`，同型的
    `references/sop-stages.md` 仍停在「四道闸 / 只认 0–3 / 无闸4.5 章节」——
    守卫覆盖面只有一个文件 → 同型文件无人拦。本版把覆盖面扩到**一组文档**
    （清单见 `config/guard.yaml#guarded_docs`），并补上"闸号/闸名 vs yaml 逐项一致"
    与"旧口径不得复活"两条断言。

守卫思路（廉价、可证伪）：
  architecture.md 与受守卫文档内嵌**机器比对用的阶段镜像块**
  （sentinel 包裹的竖线分隔行），本脚本把它与 `config/harness.yaml#stages` 逐项比对；
  再比对成员表与 agents/ 目录；最后把 `config/guard.yaml#cross_review_mapping`
  与三个 agent MD 的「你不做…」边界声明对照（取反校验）。

断言：
  T1 阶段镜像块 == yaml#stages（stage 集合 / 名称 / 成员 / gate / 并行标记）
  T2 镜像块格式可解析（sentinel 存在、5 段、stage 编号连续自 0 起）
  T3 每个 stage 成员都登记在 yaml#members（单向子集：新增注册成员不误报）
  T4 architecture.md「团队组成」表的 Agent ID == {主理人} ∪ yaml#members 全键
  T5 agents/*.md（除 *-team-lead）文件名集合 == yaml#members 全键
  T6 「六阶段」只出现在「历史沿革」章节之后（旧口径复活检测）
  T7 每个成员的 MD 都把工具白名单指向 config/harness.yaml（不在 MD 另写清单）
  T8 交叉复检映射 == 各 agent MD「你不做…」边界的**取反**（v3.17.0 新增）
  T9 受守卫文档的阶段镜像块 == yaml#stages（覆盖面从 1 个文件扩到一组，v3.17.0 新增）
  T10 受守卫文档正文不得出现旧口径词表（历史沿革区除外，v3.17.0 新增）
  G1–G5 门禁退出码镜像块 == yaml#gate_exit_codes（码集合双向 + 语义逐字，v3.25.0 新增）
  T4a「人读视图」表的 3 列 == yaml#stages（闸号 / 是否并行 / 门禁，v3.25.0 新增）
  T4b team-lead.md 的退出码唯一源指针存在性（v3.25.0 新增）

为何不会假阳性（设计取舍，改动前请先读）：
  ① 只解析 sentinel 之间的结构化行与两张显式表格，**不扫散文**——散文里的阶段描述怎么改都不触发；
  ② yaml 侧做单向子集判定（stage 成员 ⊆ 成员注册表），yaml 新增成员不会误报；
  ③ `docs/architecture.md` / `config/harness.yaml` / `agents/` 任一缺失 → **SKIP 不 FAIL**
     （packages/ 副本等局部树不误报；真缺失由 ensure_settings 第 5/15 项兜底）；
  ④ T4/T5 用集合相等，是刻意选的"强判据"：成员表漏人（本次真实缺陷）或注册了没有 MD 的成员
     都属**真漂移**，宁可 FAIL 也不静默；
  ⑤ T8/T10 的豁免区用**可判定标记**（`## 历史沿革` 章节 / `LEGACY_HISTORY` 哨兵块），
     不靠关键词猜测；旧口径词表来自 `config/guard.yaml#legacy_wording`（yaml 唯一源）。

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
GUARD_YAML = PKG / "config" / "guard.yaml"          # v3.17.0：防漂移守卫口径唯一源
AGENTS_DIR = PKG / "agents"
PROFILES_YAML = PKG / "config" / "domain-profiles.yaml"   # v3.18.0：域档案（专家面板源）
ASSEMBLER = PKG / "scripts" / "assemble_domain_prompt.py"  # v3.18.0：装配器（面板注入点）
HARNESS_PY = PKG / "scripts" / "harness.py"                # v3.18.0：编排内核（选人逻辑）
SOP_MD = PKG / "references" / "sop-stages.md"              # v3.18.0：主流程 SOP（坍缩步）
# v3.24.0（FEAT-003b）：1.5 课时缺档说明的**双向互指**两处（人读 md ↔ 机器 yaml）
COURSE_PROFILE_MD = PKG / "references" / "course-profile-defaults.md"
VISUAL_RULES_YAML = PKG / "config" / "visual-rules.yaml"
# v3.25.0（项 4/项 5/§3.6.1）：新增三处比对面
HARNESS_ENGINE_MD = PKG / "references" / "harness-engine.md"   # 门禁退出码镜像块
TEAM_LEAD_MD = PKG / "agents" / "vet-med-ppt-team-team-lead.md"  # 退出码唯一源指针

BEGIN = "<!-- STAGE_MIRROR_BEGIN -->"
END = "<!-- STAGE_MIRROR_END -->"
GATE_EXIT_BEGIN = "<!-- GATE_EXIT_MIRROR_BEGIN -->"
GATE_EXIT_END = "<!-- GATE_EXIT_MIRROR_END -->"
HISTORY_HEADING = "## 历史沿革"
LEGACY_BEGIN = "<!-- LEGACY_HISTORY_BEGIN -->"     # v3.17.0：历史区哨兵
LEGACY_END = "<!-- LEGACY_HISTORY_END -->"
LEGACY_TERM = "六阶段"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml(path: Path):
    """读 yaml（v3.18.0：T11 专家面板守卫用）。缺文件/解析失败 → None（SKIP 不 FAIL）。"""
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _ast_get_keys(path: Path) -> set:
    """采集文件里**真实读取**的配置键名集合（AST 级，非文本匹配）。

    形态覆盖（v3.18.0 实测教训：只判前两种会漏）：
      ① `X.get("key")`            —— Call 节点，func 是 Attribute(attr="get")
      ② `X["key"]`                —— Subscript 节点，slice 是字符串常量
      ③ 字典字面量里的 `"key":`   —— Dict 节点的 key（写侧，用于确认键名存在）

    ⚠ **为什么必须 AST 而非文本**：`if "institutional_endpoints" not in src`
       只证明「字符串出现过」，不证明「被读过」——反例：把读取改成
       `inst_eps = []` 而把字面量留在别处，文本判据照样通过（守卫是假的）。
    """
    try:
        import ast
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    keys = set()
    for node in ast.walk(tree):
        # ① X.get("key")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("get", "pop") and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                keys.add(a0.value)
        # ② X["key"]
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            keys.add(node.slice.value)
        # ③ {"key": ...} 字典字面量
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


def _squash(text: str) -> str:
    """去掉所有空白（比对文档写法时容忍空格差异）。"""
    return re.sub(r"\s+", "", text)


# ── 哨兵块通用解析（v3.25.0：GATE_EXIT_MIRROR 与人读视图表共用）──────
def _sentinel_rows(lines, begin, end, rel):
    """取 sentinel 之间的非空行；返回 [(原始行号, 行文本)]。缺 sentinel → AssertionError。

    与 `_mirror_rows` 同型，但 sentinel 名可配对（GATE_EXIT_MIRROR 独立命名）。
    """
    start = next((i for i, l in enumerate(lines) if l.strip() == begin), None)
    end_i = next((i for i, l in enumerate(lines) if l.strip() == end), None)
    if start is None or end_i is None or end_i <= start:
        raise AssertionError(f"{rel} 缺哨兵块（须含 {begin} / {end} 两行 sentinel）")
    return [(i, lines[i]) for i in range(start + 1, end_i) if lines[i].strip()]


def _parse_exit_row(text):
    """`exit 0 | 通过` → (0, "通过")。

    只接受 `exit <int> | <语义>` 两段式；语义里允许出现 `|`（用 maxsplit=1 保护）。
    """
    parts = text.split("|", 1)
    if len(parts) != 2:
        raise ValueError(f"退出码镜像行须为 `exit <n> | <语义>` 两段式，实得：{text!r}")
    m = re.match(r"^exit\s+(\d+)$", parts[0].strip(), re.I)
    if not m:
        raise ValueError(f"第 1 段须形如 'exit <n>'：{parts[0]!r}")
    return int(m.group(1)), parts[1].strip()


# ── 镜像块解析（模块级，供 T1 与 T9 共用）────────────────────────
def _mirror_rows(lines, rel):
    """取 sentinel 之间的镜像行；返回 [(原始行号, 行文本)]。缺 sentinel → AssertionError。"""
    start = next((i for i, l in enumerate(lines) if l.strip() == BEGIN), None)
    end = next((i for i, l in enumerate(lines) if l.strip() == END), None)
    if start is None or end is None or end <= start:
        raise AssertionError(f"{rel} 缺阶段镜像块（须含 {BEGIN} / {END} 两行 sentinel）")
    return [(i, lines[i]) for i in range(start + 1, end) if lines[i].strip()]


def _parse_row(text):
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


def _want_parallel(y):
    """stage 的并行标记期望值：**yaml 显式声明优先**，未声明才按成员数推导。

    v3.17.0 批次 B 修正：原判据恒为 `len(members) > 1 ? yes : no`——
    即"多人必并行"，这在语义上**否定了"多人串行"的合法性**，而闸2 恰恰是
    多人串行（蓝图依赖证据包的「易误解」标注，存在真实数据依赖，见
    config/harness.yaml#stages[1] 注释）。旧判据会让"如实声明为串行"变成测试失败，
    逼人去改事实而不是改声明——正是本包最忌的"声明服从推导"。

    改为：yaml#stages[n].parallel 是唯一源；缺该键时退回按成员数推导（向后兼容）。
    """
    # ⚠ 不可写 `y.get("parallel", "") or ""` —— YAML 的 `no` 解析成 Python False，
    #   `False or ""` 会得到空串，把显式声明误判成"未声明"（布尔陷阱）。
    raw = y.get("parallel")
    v = str(raw).strip().lower() if raw is not None else ""
    if v in ("yes", "no", "true", "false"):
        return "yes" if v in ("yes", "true") else "no"
    return "yes" if len(y.get("members") or []) > 1 else "no"


# ── 历史沿革豁免区（可判定标记，不靠关键词猜测）──────────────────
def _exempt_line_numbers(lines):
    """算出豁免行号集合。

    豁免区只有两种（都是**声明式标记**，不靠关键词猜测）：
      ① 标题行以「## 历史沿革」开头的章节 → 直到下一个一级/二级标题为止
         （其下的 ### 子标题仍在区内，避免章节子标题把正文重新拉回红线）
      ② `<!-- LEGACY_HISTORY_BEGIN --> … <!-- LEGACY_HISTORY_END -->` 哨兵块
    """
    exempt = set()
    i, n = 0, len(lines)
    while i < n:
        if lines[i].startswith(HISTORY_HEADING):
            j = i + 1
            while j < n and not re.match(r"^#{1,2}\s", lines[j]):
                exempt.add(j)
                j += 1
            i = j
            continue
        if lines[i].strip() == LEGACY_BEGIN:
            j = i
            while j < n:
                exempt.add(j)
                if lines[j].strip() == LEGACY_END:
                    break
                j += 1
            i = j + 1
            continue
        i += 1
    return exempt


# ── 成员显示名（与 ensure_settings.py#_agent_display_names 同实现）────
# 两个脚本各自独立实现（不互相 import，保证体检器可单独运行）；
# 改动时**两处必须同步**。
def _member_display_names(agents_dir: Path):
    """{agent_id: 显示名}。容错解析 frontmatter（实测 dvm 的 frontmatter 未在
    YAML 结束处闭合，yaml.safe_load 会抛错）→ 退化为正则 → 再退化为 H1 标题。"""
    names = {}
    if not agents_dir.is_dir():
        return names
    try:
        import yaml
    except ImportError:
        yaml = None
    for p in sorted(agents_dir.glob("*.md")):
        lines = _read(p).split("\n")
        name = None
        if lines and lines[0].strip() == "---":
            seps = [i for i, l in enumerate(lines) if l.strip() == "---"]
            if len(seps) >= 2:
                block = "\n".join(lines[1:seps[1]])
                if yaml is not None:
                    try:
                        data = yaml.safe_load(block) or {}
                        dn = data.get("displayName")
                        if isinstance(dn, dict):
                            name = dn.get("zh")
                        elif isinstance(dn, str):
                            name = dn
                    except Exception:
                        name = None
                if not name:
                    m = re.search(r"displayName:[\s\S]{0,200}?zh:\s*[\"']?([^\"'\n]+)", block)
                    if m:
                        name = m.group(1).strip()
        if not name:
            for l in lines:
                if l.startswith("# "):
                    m = re.search(r"-\s*(\S+)\s*$", l)
                    if m:
                        name = m.group(1)
                    break
        names[p.stem] = name or p.stem
    return names


# ── agent MD 的「你不做…」边界声明抽取（v3.17.0）──────────────────
_EXCL_VERBS = ("不做", "不回答", "不管")
_CLAUSE_SPLIT = re.compile(r"[、，,；;]")
_SENT_SPLIT = re.compile(r"[。\n；;]")


def _exclusion_clauses(text, names):
    """从 agent MD 里抽出 (领域词, 归属人) 记录。归属人可为 None（配不出人）。

    `names` = {agent_id: 显示名} 映射（归属人按**显示名**在句中的出现顺序配对）。

    抽取规则（结构化，**不猜语义**——语义由 `config/guard.yaml` 声明）：
      ① 按句号/分号/换行切句；句内出现 不做 / 不回答 / 不管 → 该句是「边界声明句」；
      ② 句内按 、，,；; 切子句，每个含上述动词的子句取动词之后的词作为**领域词**
         （遇到「（」或「——」即截断，避免把"那是…的事"吞进领域词）；
      ③ 该句里出现的成员显示名按出现顺序作为**归属人**；领域词与归属人按出现顺序
         一一对应（例：「你不做教学设计、不做版式设计——那是苏学法和屠明熙的事」
         → 2 个领域 + 2 个人 → 顺序配对）。

    ④ **数量对不上时的取舍（v3.17.0 明确标注，勿当缺陷）**
      典型触发：一名多归属的句子，如 ppt-producer.md 的
      「你不做内容决策（严真奥/苏学法）、不做版式设计（屠明熙）」——1 个领域挂了 2 个人，
      配不出唯一归属人。此时：
        · **归属人不产出**（owner=None）——宁可不判，避免把"其实可能指别人"判成矛盾
          （假阳性比漏判更坏：假阳性会让体检被绕过）；
        · **领域词照常产出**——因为"该成员声明自己不做某领域"这件事本身不需要配对归属人，
          T8 的「取反」判据（复检人自己的 MD 不得声明不做该领域）靠它成立。
      ⇒ 代价与兜底：**漏判方向集中在「归属证明」**（某领域归谁所有）——
        这类漏判由 T8 的 yaml 侧正向校验（规则①领域词级取反 + `config/guard.yaml`
        的登记值）与 `scripts/ensure_settings.py` 第 22 项（文档写法 == yaml 登记值）兜底。
    """
    display = sorted({v for v in names.values() if v})
    out = []
    for sent in _SENT_SPLIT.split(text):
        if not any(v in sent for v in _EXCL_VERBS):
            continue
        areas = []
        for cl in _CLAUSE_SPLIT.split(sent):
            for v in _EXCL_VERBS:
                idx = cl.find(v)
                if idx >= 0:
                    area = re.split(r"[（(——*]", cl[idx + len(v):])[0]
                    area = area.strip(" 　·—、,，.。;；：*")
                    if area:
                        areas.append(area)
                    break
        owners = [n for n in sorted(display,
                                    key=lambda x: sent.find(x) if x in sent else 10 ** 6)
                  if n in sent]
        if not areas:
            continue
        if len(areas) == len(owners):
            out.extend(zip(areas, owners))
        else:
            # 数量对不上 → 不产出归属人（宁可不判），领域词照常产出（供「取反」判据用）
            out.extend((a, None) for a in areas)
    return out


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
        try:
            return _mirror_rows(self.lines, "docs/architecture.md")
        except AssertionError as e:
            self.fail(str(e))

    @staticmethod
    def parse_row(text):
        """`stage 0 | 名称 | members: a, b | gate: g | parallel: yes` → dict。"""
        return _parse_row(text)


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
            want = _want_parallel(y)
            self.assertEqual(row["parallel"], want,
                             f"stage {sid} 并行标记与 yaml#stages[{sid}].parallel 不一致"
                             f"（yaml 未声明时按成员数推导：≥2 人才并行）")

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


# ── v3.17.0 新增：多文档覆盖 + 交叉复检映射守卫 ──────────────────────
class _GuardBase(unittest.TestCase):
    """装载 config/guard.yaml（防漂移守卫口径唯一源）与受守卫文档清单。"""

    def setUp(self):
        if not GUARD_YAML.is_file():
            self.skipTest("缺少 config/guard.yaml（守卫口径唯一源），跳过")
        if not HARNESS_YAML.is_file():
            self.skipTest("缺少 config/harness.yaml（阶段真源），跳过")
        try:
            import yaml
        except ImportError:  # pragma: no cover
            self.skipTest("未安装 PyYAML，跳过防漂移比对")
        self.guard = yaml.safe_load(_read(GUARD_YAML)) or {}
        self.docs = list(self.guard.get("guarded_docs") or [])
        self.stages = (yaml.safe_load(_read(HARNESS_YAML)) or {}).get("stages") or {}
        if not self.docs:
            self.fail("config/guard.yaml#guarded_docs 为空——守卫覆盖面为零等于没设防")

    def _doc_lines(self, rel):
        p = PKG / rel
        self.assertTrue(p.is_file(), f"受守卫文档缺失：{rel}")
        return _read(p).splitlines()


class TestGuardedDocs(_GuardBase):
    """T9 / T10：受守卫文档（清单来自 config/guard.yaml）与 yaml 逐项一致。"""

    def test_T9_guarded_docs_stage_mirror_matches_yaml(self):
        for rel in self.docs:
            lines = self._doc_lines(rel)
            try:
                rows = _mirror_rows(lines, rel)
            except AssertionError as e:
                self.fail(str(e))
            parsed = {}
            for lineno, text in rows:
                try:
                    row = _parse_row(text)
                except ValueError as e:
                    self.fail(f"{rel}:{lineno + 1} 镜像行不可解析 → {e}")
                parsed[row["stage"]] = row
            self.assertEqual(set(parsed), set(int(k) for k in self.stages),
                             f"{rel} 镜像块 stage 集合与 config/harness.yaml#stages 不一致"
                             f"（改 yaml#stages 必须同步该文档的镜像块）")
            for sid, row in sorted(parsed.items()):
                y = self.stages.get(sid, {})
                self.assertEqual(row["name"], str(y.get("name", "")).strip(),
                                 f"{rel} stage {sid} 名称与 yaml 不一致")
                self.assertEqual(sorted(row["members"]), sorted(y.get("members") or []),
                                 f"{rel} stage {sid} 成员与 yaml 不一致")
                self.assertEqual(row["gate"], str(y.get("gate", "")).strip(),
                                 f"{rel} stage {sid} gate 与 yaml 不一致")
                want = _want_parallel(y)
                self.assertEqual(row["parallel"], want,
                                 f"{rel} stage {sid} 并行标记与 yaml#stages[{sid}].parallel 不一致"
                                 f"（yaml 未声明时按成员数推导：≥2 人才并行）")

    def test_T10_no_legacy_wording_outside_history(self):
        terms = list(self.guard.get("legacy_wording") or [])
        self.assertTrue(terms, "config/guard.yaml#legacy_wording 为空——旧口径词表不能为空")
        hits = []
        for rel in self.docs:
            lines = self._doc_lines(rel)
            exempt = _exempt_line_numbers(lines)
            for i, line in enumerate(lines):
                if i in exempt:
                    continue
                for t in terms:
                    if t in line:
                        hits.append(f"{rel}:{i + 1} 旧口径「{t}」→ {line.strip()[:50]}")
        self.assertFalse(
            hits,
            "受守卫文档正文出现旧口径（当前口径只在正文；历史口径须放进「## 历史沿革」"
            "章节或 LEGACY_HISTORY 哨兵块）：\n     " + "\n     ".join(hits))

    def test_T6b_legacy_six_stage_only_after_history(self):
        """T6 扩面：所有受守卫文档的「六阶段」都必须出现在历史沿革章节之后。"""
        hits = []
        for rel in self.docs:
            lines = self._doc_lines(rel)
            exempt = _exempt_line_numbers(lines)
            hist = next((i for i, l in enumerate(lines)
                         if l.startswith(HISTORY_HEADING)), None)
            for i, line in enumerate(lines):
                if LEGACY_TERM not in line or i in exempt:
                    continue
                if hist is None or i < hist:
                    hits.append(f"{rel}:{i + 1} 「{LEGACY_TERM}」出现在历史沿革章节之前"
                                f" → {line.strip()[:50]}")
        self.assertFalse(hits, "\n     ".join(hits))


class TestCrossReviewMapping(_GuardBase):
    """T8：`config/guard.yaml#cross_review_mapping` 与 agent MD「你不做…」边界取反校验。

    真实缺陷背景：闸3 迭代回路的「跨模块改动 → 非作者交叉复检」映射曾三处全反，
    把把关人派给了各自 agent MD 明文「你不做…（那是别人的事）」的人 —— 把关被整体绕开。
    """

    def setUp(self):
        super().setUp()
        if not AGENTS_DIR.is_dir():
            self.skipTest(f"缺少 {AGENTS_DIR}（局部树，跳过）")
        self.mapping = self.guard.get("cross_review_mapping") or {}
        self.assertTrue(self.mapping, "config/guard.yaml#cross_review_mapping 为空"
                                        "——交叉复检映射必须登记在 yaml")
        self.names = _member_display_names(AGENTS_DIR)

    def test_T8_mapping_not_contradicted_by_agent_boundaries(self):
        problems = []
        reviewers = {spec.get("reviewer") for spec in self.mapping.values()
                     if isinstance(spec, dict)}
        for kind, spec in sorted(self.mapping.items()):
            self.assertIsInstance(spec, dict, f"cross_review_mapping.{kind} 须为映射")
            reviewer = spec.get("reviewer")
            terms = list(spec.get("md_area_terms") or [])
            self.assertTrue(reviewer, f"cross_review_mapping.{kind} 缺 reviewer（期望成员 id）")
            self.assertTrue(terms, f"cross_review_mapping.{kind} 缺 md_area_terms")
            name = self.names.get(reviewer)
            self.assertTrue(name, f"取不到 {reviewer} 的显示名（agents/{reviewer}.md）")
            # ① 取反：复检人自己的 MD 不得声明「不做」该领域
            own = _exclusion_clauses(_read(AGENTS_DIR / f"{reviewer}.md"), self.names)
            for area, _owner in own:
                if any(t in area for t in terms):
                    problems.append(
                        f"{kind} 派给 {name}，但其 agent MD 明文声明「不做{area}」")
            # ② 归属证明：必须有人声明该领域归复检人所有
            owners = set()
            for mid in sorted(m for m in reviewers if m):
                p = AGENTS_DIR / f"{mid}.md"
                if not p.is_file():
                    continue
                for area, owner in _exclusion_clauses(_read(p), self.names):
                    if owner and any(t in area for t in terms):
                        owners.add(owner)
            if name not in owners:
                problems.append(
                    f"{kind} 派给 {name}，但没有任何 agent MD 声明该领域归其所有"
                    f"（当前声明归属：{sorted(owners) or '无'}）")
        self.assertFalse(problems, "；".join(problems))


class TestExpertPanelWiring(unittest.TestCase):
    """T11（v3.18.0 新增）：专家面板的**声明↔执行**接线守卫。

    背景（2026-10-25 从零诊断 G1/D-1 实测）：本包长期存在「声明层≠执行层」——
      · 域档案声明了 `role_persona`（域人格），但坍缩产物**不产专家团**（只有 1 段人格）；
      · 域档案声明了 `institutional_endpoints`（6 条实测可达端点），
        但装配器渲染 evidence_hierarchy 时**只挑 5 个子键 → 端点全被丢弃**
        （实跑装配产物 grep：msdvetmanual/woah.org/fao.org 命中数 = 0）。
    本守卫把两条接线钉死，防止「加了字段但没接线」再次静默发生。
    """

    def test_T11a_panel_assets_wired_to_runtime(self):
        """T11a：域档案的 expert_panel / institutional_endpoints 必须被装配器**真的消费**。

        ⚠ 判据用 **AST 真实读取点**，不是字符串出现——
          v3.18.0 首版用 `if "institutional_endpoints" not in asm` 判"是否接线"，
          反例验证时把读取改成 `inst_eps = []`（字面量仍在文件里）→ **守卫没红**，
          说明字符串判据是假的。改为：解析 AST，收集所有
          `X.get("key")` / `X["key"]` 两种形态的**真实读取点**。
        """
        prof = _load_yaml(PROFILES_YAML) or {}
        domains = prof.get("domains") or []
        self.assertTrue(domains, "domain-profiles.yaml 无 domains")
        with_panel = [d for d in domains if isinstance(d, dict) and d.get("expert_panel")]
        self.assertTrue(with_panel, "没有任何域声明 expert_panel——多专家坍缩无从谈起")

        asm_reads = _ast_get_keys(ASSEMBLER)
        h_reads = _ast_get_keys(HARNESS_PY)
        h_text = _read(HARNESS_PY)
        problems = []
        # ① 装配器必须**真的取用** selected_experts（坍缩产物里已带）
        if "selected_experts" not in asm_reads:
            problems.append("装配器无 selected_experts 的真实读取点"
                            "——坍缩选中的专家不会被注入")
        # ② 装配器必须**真的取用** institutional_endpoints（机构端点实址）
        if "institutional_endpoints" not in asm_reads:
            problems.append("装配器无 institutional_endpoints 的真实读取点"
                            "——机构权威端点不会被注入")
        # ③ harness.py 必须支持选人（--panel）与选人合法性校验
        if '"--panel"' not in h_text:
            problems.append("harness.py 无 --panel 参数——无法指定本次上场的子专家")
        if "_select_experts" not in h_text:
            problems.append("harness.py 无 _select_experts——选人逻辑缺失")
        if "expert_panel" not in h_reads:
            problems.append("harness.py 无 expert_panel 的真实读取点"
                            "——域档案的专家池不会被装配进坍缩产物")
        self.assertFalse(problems, "；".join(problems))

    def test_T11b_sop_documents_collapse_step(self):
        """T11b：主流程 SOP 必须写明「选域→选人→输出对齐→确认」四步。"""
        sop = _read(SOP_MD)
        problems = []
        for token, desc in (("route --level", "路由命令"),
                            ("--panel", "选人参数"),
                            ("collapse confirm", "确认命令"),
                            ("gate1-check", "闸1 自检命令")):
            if token not in sop:
                problems.append(f"references/sop-stages.md 未写「{desc}」（缺 {token}）")
        self.assertFalse(problems, "；".join(problems))

    def test_T11c_every_domain_panel_ids_unique(self):
        """T11c：每个域的 expert_panel 条目 id 必须**域内唯一**且非空。"""
        prof = _load_yaml(PROFILES_YAML) or {}
        problems = []
        for d in prof.get("domains") or []:
            if not isinstance(d, dict):
                continue
            panel = d.get("expert_panel") or []
            ids = [e.get("id") for e in panel if isinstance(e, dict)]
            if len(ids) != len(set(ids)):
                problems.append(f"域 {d.get('id')} 的 expert_panel id 重复：{ids}")
            for e in panel:
                if not isinstance(e, dict):
                    continue
                for req in ("id", "title", "background", "stance", "duties", "duty_boundary"):
                    if not e.get(req):
                        problems.append(
                            f"域 {d.get('id')} 的专家 {e.get('id')} 缺必填字段 {req}")
        self.assertFalse(problems, "；".join(problems))

    def test_T11d_caption_single_skeleton_no_overlap(self):
        """T11d（G4）：图注要素 = **通用骨架 + 域扩展**，且二者**不得重复**。

        缺陷（2026-10-25 从零诊断 G4 实测）：图注要素**四套定义并存**——
          ① visual-rules.yaml#caption_five_elements（域口径 5 项）
          ② seven-dimension-rubric.md:107（域无关 5 项）
          ③ dvm-content-expert.md:262（3 项·域专属）
          ④ 各域 image_channel.caption_elements（computing 又不同）
        且 rubric:106-110 **自认冲突并声明"本文件不替 config 做决定"**——明知冲突而不调和。
        v3.18.0 统一为：骨架 = visual-rules.yaml#caption_base_elements（唯一源），
        域扩展 = 域档案 image_channel.caption_extra_elements（不得与骨架重叠）。
        """
        vr = _load_yaml(PKG / "config" / "visual-rules.yaml") or {}
        skeleton = (vr.get("caption_base_elements") or [])
        self.assertTrue(skeleton, "visual-rules.yaml 缺 caption_base_elements（通用骨架）")

        prof = _load_yaml(PROFILES_YAML) or {}
        problems = []
        for d in prof.get("domains") or []:
            if not isinstance(d, dict):
                continue
            ic = d.get("image_channel") or {}
            # ① 旧键不得再作为独立定义出现
            if ic.get("caption_elements"):
                problems.append(
                    f"域 {d.get('id')} 仍用 caption_elements（旧键）——"
                    f"应改用 caption_extra_elements（域扩展）")
            # ② 域扩展不得与骨架重复
            extra = ic.get("caption_extra_elements") or []
            sk_set = {str(x).strip() for x in skeleton}
            for x in extra:
                if str(x).strip() in sk_set:
                    problems.append(
                        f"域 {d.get('id')} 的 caption_extra_elements 含骨架重复项：{x!r}")
        self.assertFalse(problems, "；".join(problems))

    def test_T11e_no_third_caption_definition_in_docs(self):
        """T11e：包内不得再有**第三套独立的图注要素定义**。

        判据（精确到"只能在域档案里出现"）：
          · agent MD 不得出现「图注三要素 / 图注五要素」这类**独立清单式**表述——
            应改为引用唯一源（骨架 + 域扩展）；
          · rubric 里出现域专属词**允许**（那是解释"域扩展是什么"的正当举例），
            但**不得**再出现「图注三要素/图注五要素」式清单声明。
        """
        problems = []
        # ① agent MD 不得独立列图注要素清单（应只引用唯一源）
        for md in sorted(AGENTS_DIR.glob("*.md")):
            txt = _read(md)
            for phrase in ("图注三要素", "图注五要素"):
                if phrase in txt:
                    problems.append(
                        f"{md.name} 仍写「{phrase}」——应改为引用 "
                        f"visual-rules.yaml#caption_base_elements + 域档案 caption_extra_elements")
        # ② rubric 不得再声明独立清单（域专属词的正当举例不算）
        #   ⚠ 例外：**引述旧口径以说明"已统一"的历史句**是正当的
        #     （v3.18.0 的口径说明段里就引了"原写…是上游旧清单"），
        #     故只对**不含"原写/旧/历史/此前"等引述语境**的行判红。
        rub = _read(PKG / "references" / "seven-dimension-rubric.md")
        quote_ctx = ("原写", "旧", "历史", "此前", "上游", "已统一", "已并入", "deprecated")
        for i, line in enumerate(rub.splitlines(), 1):
            for phrase in ("图注三要素", "图注五要素"):
                if phrase in line and not any(k in line for k in quote_ctx):
                    problems.append(
                        f"references/seven-dimension-rubric.md:{i} 仍声明「{phrase}」"
                        f"——应改为引用 caption_base_elements + caption_extra_elements")
        self.assertFalse(problems, "；".join(problems))


class TestGateExitMirror(unittest.TestCase):
    """G1–G5（v3.25.0 · 项 5）：`references/harness-engine.md` 的 `GATE_EXIT_MIRROR` 块
    与 `config/harness.yaml#gate_exit_codes` 的**逐字**对账。

    缺陷背景（研究简报 §2.3.2②a 实测）：删掉 `config/harness.yaml#gate_exit_codes` 的
    `4:` 行 ⇒ 体检 rc=0、全量 pytest 0 failed，而 3 处 MD 仍在教成员
    「exit 4 = 运行错误」⇒ 退出码语义**静默退化**，无人察觉。
    本守卫把退化从「运行时静默」提前到「体检期判红」。

    断言：
      G1 镜像块存在且可解析（每行 `exit <int> | <语义>`，码不重复）
      G2 **码集合相等**（双向）—— 这正是「删键零检测」缺口
      G3 每码语义非空（yaml 侧与镜像侧都非空）
      G4 每码语义**逐字相等**（镜像行 == yaml 值，strip 后比较）
      G5 代码 `_FALLBACK["gate_exit_codes"]` 码集合 == yaml 码集合 —— **默认关闭**（见 ADR-7）

    ⚠ 为何 G4 可以逐字相等（而 STAGE_MIRROR 的 name 列不能）：
      yaml 侧 `gate_exit_codes` 的值是**标量**、无版本后缀、无括号补充说明 ⇒
      逐字相等无歧义。STAGE_MIRROR 的 `stages.4.name` 带了「（v3.3.0）」而人读表
      压缩掉了 ⇒ 那里只能比集合不比逐字（见 §3.4.1 的关键决策）。
    """

    # G5 开关：ADR-7「待裁决」项（yaml 0–4 vs 代码 fallback 0–5 的第二份真相）。
    #   裁决为 (b)（删 fallback 第 5 码）⇒ 可置 True；
    #   裁决为 (a)/(c) ⇒ 保持 False（否则开启即基线红）。
    ENABLE_FALLBACK_PARITY = False

    def setUp(self):
        missing = [str(p) for p in (HARNESS_ENGINE_MD, HARNESS_YAML)
                   if not p.is_file()]
        if missing:
            self.skipTest(f"缺少比对输入：{', '.join(missing)}（局部树，跳过）")
        try:
            import yaml
        except ImportError:  # pragma: no cover
            self.skipTest("未安装 PyYAML，跳过退出码对账")
        with open(HARNESS_YAML, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f) or {}
        self.yaml_codes = self.cfg.get("gate_exit_codes") or {}
        self.lines = _read(HARNESS_ENGINE_MD).splitlines()

    def _mirror(self):
        try:
            rows = _sentinel_rows(self.lines, GATE_EXIT_BEGIN, GATE_EXIT_END,
                                  "references/harness-engine.md")
        except AssertionError as e:
            self.fail(str(e))
        parsed = {}
        for lineno, text in rows:
            try:
                code, sem = _parse_exit_row(text)
            except ValueError as e:
                self.fail(f"references/harness-engine.md:{lineno + 1} → {e}")
            if code in parsed:
                self.fail(f"references/harness-engine.md:{lineno + 1} 退出码 {code} 重复")
            parsed[code] = sem
        self.assertTrue(parsed, "退出码镜像块为空")
        return parsed

    def test_G1_mirror_block_parseable(self):
        """G1：镜像块存在、每行可解析、码不重复。"""
        self._mirror()

    def test_G2_code_set_equal_both_directions(self):
        """G2：码集合相等（**双向**）——删任一码或加任一码都判红。"""
        mirror = self._mirror()
        self.assertEqual(set(mirror), set(self.yaml_codes),
                         "退出码镜像块的码集合与 config/harness.yaml#gate_exit_codes 不一致"
                         "（yaml 侧是唯一源，改 yaml 必须同步 references/harness-engine.md "
                         "的 GATE_EXIT_MIRROR 块）")

    def test_G3_semantics_non_empty(self):
        """G3：每个码的语义在两侧都非空。"""
        mirror = self._mirror()
        empty = [c for c, s in mirror.items() if not str(s).strip()]
        empty += [c for c, s in self.yaml_codes.items() if not str(s).strip()]
        self.assertFalse(empty, f"以下退出码的语义为空：{sorted(empty)}")

    def test_G4_semantics_verbatim_equal(self):
        """G4：每码语义**逐字相等**（yaml 值是标量 ⇒ 无归一化歧义）。"""
        mirror = self._mirror()
        for code in sorted(set(mirror) & set(self.yaml_codes)):
            self.assertEqual(mirror[code], str(self.yaml_codes[code]).strip(),
                             f"exit {code} 的语义与 config/harness.yaml#gate_exit_codes "
                             f"不一致（镜像：{mirror[code]!r}）")

    @unittest.skipUnless(ENABLE_FALLBACK_PARITY,
                         "G5 默认关闭：ADR-7 待裁决（yaml 0–4 vs 代码 fallback 0–5）")
    def test_G5_fallback_code_set_matches_yaml(self):
        """G5（默认关闭）：代码 `_FALLBACK["gate_exit_codes"]` 码集合 == yaml 码集合。

        ⚠ 开启前必须先裁决 ADR-7 并**同批**删除 fallback 的多余码 ——
          「守卫与被守卫数据必须同批落地」，否则一开启即基线红。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_harness_for_gate_exit", PKG / "scripts" / "harness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # ⚠ 键必须归一化为 str：yaml 的 `0:` 解析为 **int**，而代码副本是 **str**
        #   （`ensure_settings.py` 第 25 项同源判据已做此归一）⇒ 不归一则
        #   `set(int) != set(str)` ⇒ G5 一开启即**假红**（不是真缺陷）。
        fb = {str(k) for k in
              ((getattr(mod, "_FALLBACK", {}) or {}).get("gate_exit_codes") or {})}
        yk = {str(k) for k in self.yaml_codes}
        self.assertEqual(fb, yk,
                         "代码 fallback 的退出码集合与 yaml 不一致（第二份真相未收敛）")


class TestHumanReadStageTable(_Base):
    """项 4（v3.25.0）：`docs/architecture.md`「人读视图」表纳入守卫。

    缺陷背景：`docs/architecture.md` 的「人读视图」表长期停在 stage 1 = `**并行**`，
    而 `config/harness.yaml#stages[1].parallel` 自 v3.17.0 起已改为 `no`
    （伪并行修正）⇒ 文档在**直接教人做错的事**，且无机器拦截。

    只比 **3 列**（闸号 / 是否并行 / 门禁），理由见 §3.4.1：
      · 「名称」列**不比** —— yaml 的 `stages.4.name` 带「（v3.3.0）」而人读表压缩掉了，
        逐字比较必假阳性（铁律：假阳性必须为零）；
      · 「干活的人」列**不比** —— 显示名组合，无结构化对照源；
      · 「为什么要这么排」列**不比** —— 散文（遵 FEAT-20261022-001 教训）。
    """

    HEADER_CELLS = ("闸", "名称", "干活的人", "是否并行", "门禁", "为什么要这么排")

    def _table(self):
        """取「### 人读视图」标题之后的第一个 markdown 表 → (表头, 数据行列表)。"""
        start = next((i for i, l in enumerate(self.lines)
                      if l.strip().startswith("### 人读视图")), None)
        if start is None:
            self.fail("docs/architecture.md 缺「### 人读视图」章节")
        # 找表头行：第一个以 | 开头且含「闸」的行
        head_i = None
        for i in range(start + 1, len(self.lines)):
            line = self.lines[i]
            if line.strip().startswith("|") and "闸" in line:
                head_i = i
                break
            if line.startswith("## "):   # 越过本章节
                break
        if head_i is None:
            self.fail("docs/architecture.md 的「人读视图」章节下未找到表格")
        header = [c.strip() for c in self.lines[head_i].strip().strip("|").split("|")]
        rows = []
        for line in self.lines[head_i + 1:]:
            s = line.strip()
            if not s.startswith("|"):
                break
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue          # 分隔行
            rows.append((line, cells))
        return header, rows

    @staticmethod
    def _parallel_flag(cell: str) -> str:
        """「是否并行」列 → yes/no。只接受 3 个枚举值，其他 ⇒ 抛错（不猜语义）。"""
        v = cell.strip().replace("**", "").strip()
        if v in ("并行", "yes", "是"):
            return "yes"
        if v in ("串行", "no", "否"):
            return "no"
        if v in ("—", "-", "—", ""):
            return "no"
        raise ValueError(f"「是否并行」列取值 {cell!r} 不在枚举内（并行/串行/—）")

    def test_T4a_human_read_table_3cols_match_yaml(self):
        """表头 6 列固定 → 逐行比 3 列（闸号 / 是否并行 / 门禁）。"""
        header, rows = self._table()
        self.assertEqual(tuple(header), self.HEADER_CELLS,
                         "「人读视图」表头结构已变（须为 6 列固定表头）")

        yaml_ids = set(int(k) for k in self.stages)
        seen = []
        for text, cells in rows:
            if len(cells) < 5:
                self.fail(f"「人读视图」数据行列数不足 5：{text.strip()[:60]}")
            try:
                sid = int(cells[0].strip())
            except ValueError:
                self.fail(f"「人读视图」第 1 列须为闸号整数：{cells[0]!r}")
            try:
                par = self._parallel_flag(cells[3])
            except ValueError as e:
                self.fail(str(e))
            gate = _squash(cells[4].strip().strip("`"))
            seen.append(sid)

            y = self.stages.get(sid)
            self.assertIsNotNone(y, f"「人读视图」出现 yaml 中不存在的闸号 {sid}")
            self.assertEqual(par, _want_parallel(y),
                             f"「人读视图」闸 {sid} 的「是否并行」与 "
                             f"config/harness.yaml#stages[{sid}].parallel 不一致")
            self.assertEqual(gate, _squash(str(y.get("gate", "")).strip()),
                             f"「人读视图」闸 {sid} 的「门禁」与 "
                             f"config/harness.yaml#stages[{sid}].gate 不一致")

        self.assertEqual(len(seen), len(set(seen)),
                         "「人读视图」表闸号有重复")
        self.assertEqual(set(seen), yaml_ids,
                         "「人读视图」表的闸号集合与 config/harness.yaml#stages 不一致"
                         "（漏行 / 多行）")


class TestTeamLeadExitCodePointer(unittest.TestCase):
    """§3.6.1（v3.25.0）：`team-lead.md` 的退出码唯一源指针**存在性**守卫。

    病灶：`agents/vet-med-ppt-team-team-lead.md:79` 写「退出码语义唯一源
    `references/harness-engine.md#6`」——把**人读镜像**当成唯一源。
    真源是 `config/harness.yaml#gate_exit_codes`。

    判据是**字面锚点**（不是散文语义判定）⇒ 与 T11a/b 同型，零假阳性：
    只判一个字符串在不在文件里，正文怎么改措辞都不误报。
    """

    def setUp(self):
        if not TEAM_LEAD_MD.is_file():
            self.skipTest(f"缺少 {TEAM_LEAD_MD}（局部树，跳过）")

    def test_T4b_team_lead_points_to_yaml_source(self):
        txt = _read(TEAM_LEAD_MD)
        self.assertIn("config/harness.yaml#gate_exit_codes", txt,
                      "team-lead.md 必须把退出码语义的唯一源指向 "
                      "config/harness.yaml#gate_exit_codes"
                      "（references/harness-engine.md#6 是人读镜像块，不是唯一源）")


class TestGuardAntiExamples(unittest.TestCase):
    """批 3 守卫的**反例验证**（v3.25.0 · §3.4.4 / §3.5.3）。

    为何必须固化反例：一条「全绿」的守卫无法自证有效——它可能因
    探测器失效、路径写错、判据恒真而**假绿**（本包历史已踩多次：
    FEAT-20261022-001 的「删键零检测」、v3.18.0 的字符串判据假绿）。

    做法：在**隔离副本**里制造漂移，守卫必须判红；再确认「只改散文」
    这类合法改动**不**判红（防误伤）。副本由 `test_pkg_isolation` 提供，
    生产 config / 文档**零改动**。

    ⚠ 两条工程纪律（v3.25.0 实测踩到，勿删）：
      ① **每个用例用全新副本**——共用一个副本会让 mutation **累积**，
        后一个用例的判红原因可能是前一个留下的脏数据 ⇒ 断言失真。
      ② **子进程只跑守卫类，不跑反例类**——若子进程跑整个文件，
        反例会再次自举（子进程里的反例又起子进程…）⇒ 指数膨胀 + 死循环。
        故子进程用 unittest 的**类名选择**参数精确指定。
    """

    #: 子进程里要跑的守卫类（**不含**本反例类，防自举）
    GUARD_CLASSES = ("TestGateExitMirror", "TestHumanReadStageTable",
                     "TestTeamLeadExitCodePointer")

    def setUp(self):
        sys.path.insert(0, str(HERE))
        from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg
        self._iso = make_isolated_pkg(prefix="vetmed-iso-archdrift-")
        self._cleanup = cleanup_isolated_pkg
        self.addCleanup(self._cleanup, self._iso)

    def _run_guard(self, pkg_root: Path):
        """在副本里**只**跑守卫类，返回 (rc, 输出)。"""
        import subprocess
        script = pkg_root / "scripts" / "test_arch_drift.py"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(pkg_root / "scripts")
        proc = subprocess.run(
            [sys.executable, str(script)] + list(self.GUARD_CLASSES),
            capture_output=True, text=True, env=env, cwd=str(pkg_root),
            timeout=120)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def _fail_case(self, name, mutate, expect_in_output):
        """在**全新副本**里施加 mutation ⇒ 必须判红且输出含期望关键字。"""
        iso = self._iso
        mutate(iso)
        rc, out = self._run_guard(iso)
        self.assertNotEqual(rc, 0, f"{name}：期望判红，实际 rc=0（守卫假绿）")
        self.assertIn(expect_in_output, out,
                      f"{name}：判红了但输出未含期望关键字 {expect_in_output!r}")

    def _pass_case(self, name, mutate):
        """在**全新副本**里施加合法改动 ⇒ 必须**不**判红（防误伤）。"""
        iso = self._iso
        mutate(iso)
        rc, out = self._run_guard(iso)
        self.assertEqual(rc, 0,
                         f"{name}：合法改动被判红 ⇒ 守卫越界（假阳性）：\n" + out[-2000:])

    # ── 反例 A/B/C（人读视图表，§3.4.4）──────────────────────
    def test_anti_A_parallel_flag_regression(self):
        """反例 A：把 stage 1 的「是否并行」改回 `**并行**` ⇒ 必须判红。

        这是**已发生过的真实漂移**（yaml 自 v3.17.0 起 parallel: no，
        人读表一直写 `**并行**`）。
        """
        def mutate(pkg):
            p = pkg / "docs" / "architecture.md"
            t = p.read_text(encoding="utf-8")
            old = "| 1 | 闸2 设计（证据先行→蓝图·串行） | 苏学法 ∥ 严真奥 | **串行** |"
            new = "| 1 | 闸2 设计（证据先行→蓝图·串行） | 苏学法 ∥ 严真奥 | **并行** |"
            self.assertIn(old, t, "反例前提不成立：人读表 stage 1 行未按预期排版")
            p.write_text(t.replace(old, new), encoding="utf-8")
        self._fail_case("反例 A（并行标记漂移）", mutate, "是否并行")

    def test_anti_B_gate_column_wrong(self):
        """反例 B：把 stage 2 的门禁改成 `user_confirm` ⇒ 必须判红。"""
        def mutate(pkg):
            p = pkg / "docs" / "architecture.md"
            t = p.read_text(encoding="utf-8")
            old = "| 2 | 闸3 成稿（页表∥版式） | 苏学法 ∥ 屠明熙 | **并行** | `script_check` |"
            new = "| 2 | 闸3 成稿（页表∥版式） | 苏学法 ∥ 屠明熙 | **并行** | `user_confirm` |"
            self.assertIn(old, t, "反例前提不成立：人读表 stage 2 行未按预期排版")
            p.write_text(t.replace(old, new), encoding="utf-8")
        self._fail_case("反例 B（门禁列错）", mutate, "门禁")

    def test_anti_C_missing_row(self):
        """反例 C：删掉 stage 4 行 ⇒ 必须判红（行数 ≠ yaml 键数）。"""
        def mutate(pkg):
            p = pkg / "docs" / "architecture.md"
            lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
            out = [l for l in lines
                   if not l.startswith("| 4 | 闸4.5 案例三源核验 |")]
            self.assertEqual(len(out), len(lines) - 1, "反例前提不成立：未删掉 stage 4 行")
            p.write_text("".join(out), encoding="utf-8")
        self._fail_case("反例 C（漏行）", mutate, "闸号集合")

    def test_anti_D_prose_only_change_must_not_fail(self):
        """反例 D（**防误伤**）：只改「为什么要这么排」列的措辞 ⇒ **不得**判红。

        证明守卫**只比 3 列**，散文怎么改都不触发（FEAT-20261022-001 教训）。
        """
        def mutate(pkg):
            p = pkg / "docs" / "architecture.md"
            t = p.read_text(encoding="utf-8")
            old = "证据先行→蓝图：蓝图的二八难点清单依赖证据包的「易误解」标注，存在真实数据依赖 ⇒ 串行；并行会必然回问"
            new = "（散文措辞改写测试：语义不变，只是换了说法）证据先行→蓝图。"
            self.assertIn(old, t, "反例前提不成立：stage 1 理由列未按预期")
            p.write_text(t.replace(old, new), encoding="utf-8")
        self._pass_case("反例 D（只改散文）", mutate)

    # ── 反例 A–E（退出码镜像块，§3.5.3）──────────────────────
    def test_anti_E_yaml_code_deleted(self):
        """反例 A（退出码）：删掉 yaml 的 `4:` 码 ⇒ 必须判红（G2 + G4）。"""
        def mutate(pkg):
            p = pkg / "config" / "harness.yaml"
            lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
            out = [l for l in lines if not l.startswith("  4: \"运行错误")]
            self.assertEqual(len(out), len(lines) - 1, "反例前提不成立：未删掉 4 码")
            p.write_text("".join(out), encoding="utf-8")
        self._fail_case("反例 A（yaml 删码）", mutate, "gate_exit_codes")

    def test_anti_F_yaml_extra_code(self):
        """反例 B（退出码）：yaml 加码 6 ⇒ 必须判红（G2 双向）。"""
        def mutate(pkg):
            p = pkg / "config" / "harness.yaml"
            t = p.read_text(encoding="utf-8")
            anchor = "  4: \"运行错误"
            self.assertIn(anchor, t, "反例前提不成立：未找到 4 码锚点")
            t = t.replace(anchor, "  6: \"未定义码\"\n" + anchor, 1)
            p.write_text(t, encoding="utf-8")
        self._fail_case("反例 B（yaml 加码）", mutate, "gate_exit_codes")

    def test_anti_G_semantics_changed_one_char(self):
        """反例 C（退出码）：yaml 的 `4:` 语义改一个字 ⇒ 必须判红（G4 逐字）。"""
        def mutate(pkg):
            p = pkg / "config" / "harness.yaml"
            t = p.read_text(encoding="utf-8")
            old = "必须报 traceback 并走缺陷回流，不得当作红灯打回成员"
            new = "必须报 traceback 并走缺陷回流，不得当作红灯打回老师"
            self.assertIn(old, t, "反例前提不成立：未找到 4 码语义原文")
            p.write_text(t.replace(old, new), encoding="utf-8")
        self._fail_case("反例 C（语义改一字）", mutate, "exit 4")

    def test_anti_H_mirror_block_missing(self):
        """反例 D（退出码）：删掉 GATE_EXIT_MIRROR 块 ⇒ 必须判红（G1）。"""
        def mutate(pkg):
            p = pkg / "references" / "harness-engine.md"
            lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
            out, dropped = [], 0
            inside = False
            for l in lines:
                if l.strip() == GATE_EXIT_BEGIN:
                    inside = True
                    continue
                if l.strip() == GATE_EXIT_END:
                    inside = False
                    continue
                if inside:
                    dropped += 1
                    continue
                out.append(l)
            self.assertGreater(dropped, 0, "反例前提不成立：镜像块内无内容")
            p.write_text("".join(out), encoding="utf-8")
        self._fail_case("反例 D（镜像块缺失）", mutate, "哨兵块")

    def test_anti_I_prose_change_must_not_fail(self):
        """反例 E（**防误伤**）：改镜像块外的散文措辞 ⇒ **不得**判红。"""
        def mutate(pkg):
            p = pkg / "references" / "harness-engine.md"
            t = p.read_text(encoding="utf-8")
            old = "- 每次调用自动写 trace（退出码、耗时、stderr 尾部）"
            new = "- 每次调用自动写 trace（退出码、耗时、stderr 尾部记录）"
            self.assertIn(old, t, "反例前提不成立：未找到散文锚点")
            p.write_text(t.replace(old, new), encoding="utf-8")
        self._pass_case("反例 E（只改散文）", mutate)

    # ── 反例（team-lead 指针，§3.6.1）────────────────────────
    def test_anti_J_team_lead_pointer_removed(self):
        """反例：team-lead.md 删掉 yaml 指针 ⇒ 必须判红（锚点守卫）。"""
        def mutate(pkg):
            p = pkg / "agents" / "vet-med-ppt-team-team-lead.md"
            t = p.read_text(encoding="utf-8")
            old = "退出码语义唯一源 = `config/harness.yaml#gate_exit_codes`；"
            self.assertIn(old, t, "反例前提不成立：未找到指针原文")
            p.write_text(t.replace(old, "退出码语义唯一源 `references/harness-engine.md#6`；"),
                         encoding="utf-8")
        self._fail_case("反例 J（指针错位）", mutate, "gate_exit_codes")


class TestHoursCaliberCrossRef(unittest.TestCase):
    """T11 1.5 课时缺档说明的**双向互指**守卫（v3.24.0 · FEAT-003b）。

    病灶：`references/course-profile-defaults.md#2` 与
    `config/visual-rules.yaml#hours_page_range_single_ppt` 上方注释块
    **讲的是同一件事**（口径 B 无 1.5 档 ⇒ 缺档 ≠ 通过），但原先**互不指向**——
    任一处改动都不会被察觉 ⇒ 表述分裂（FEAT-003b 登记的诉求）。

    守卫思路：两处必须**各自含对方路径**，且同带一个**共同标记**
    （`FEAT-003b`）⇒ 单边删除任一侧的互指声明即判红。

    ⚠ 为何不做「散文正则比对」：本包已有教训（FEAT-20261022-001）——
    纯文本判据假阳性不可控。此处只判**明确锚点**（文件路径 + 标记串），
    不判散文措辞，故改动正文措辞不会误报。
    """

    MARK = "FEAT-003b"

    def setUp(self):
        missing = [str(p) for p in (COURSE_PROFILE_MD, VISUAL_RULES_YAML)
                   if not p.is_file()]
        if missing:
            self.skipTest(f"缺少比对输入：{', '.join(missing)}（局部树，跳过）")

    def test_T11a_md_points_to_yaml(self):
        """人读 md 必须指向 yaml 侧的口径说明书。"""
        txt = _read(COURSE_PROFILE_MD)
        self.assertIn("config/visual-rules.yaml#hours_page_range_single_ppt", txt,
                      "course-profile-defaults.md 必须指向 visual-rules.yaml 的 single_ppt 口径")
        self.assertIn(self.MARK, txt,
                      f"course-profile-defaults.md 缺互指标记「{self.MARK}」")

    def test_T11b_yaml_points_to_md(self):
        """机器 yaml 必须回指人读 md（单向互指 ⇒ 改一侧另一侧可知）。"""
        txt = _read(VISUAL_RULES_YAML)
        self.assertIn("references/course-profile-defaults.md", txt,
                      "visual-rules.yaml 必须回指 course-profile-defaults.md")
        self.assertIn(self.MARK, txt,
                      f"visual-rules.yaml 缺互指标记「{self.MARK}」")


if __name__ == "__main__":
    unittest.main(verbosity=2)

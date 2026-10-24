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

BEGIN = "<!-- STAGE_MIRROR_BEGIN -->"
END = "<!-- STAGE_MIRROR_END -->"
HISTORY_HEADING = "## 历史沿革"
LEGACY_BEGIN = "<!-- LEGACY_HISTORY_BEGIN -->"     # v3.17.0：历史区哨兵
LEGACY_END = "<!-- LEGACY_HISTORY_END -->"
LEGACY_TERM = "六阶段"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _squash(text: str) -> str:
    """去掉所有空白（比对文档写法时容忍空格差异）。"""
    return re.sub(r"\s+", "", text)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)

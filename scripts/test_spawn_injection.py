#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_spawn_injection.py — 装配链回归守卫（v3.17.0 批次 B 新建）

背景（2026-10-24 端到端实测，非假设）：
  v3.17.0 引入「专家团动态坍缩」机制，但端到端实测发现**坍缩产物从未进入成员 prompt**——
    ① `harness.py route --domain computing` 正确落盘 `_collapse/collapse_*.json`；
    ② `harness.py collapse confirm` 正确置 status=confirmed / effective=true；
    ③ 但装配产物中域人格关键词命中数 = **0**（"软件工程内容权威"/"事件循环"/"asyncio" 全 0）。
  根因：`scripts/assemble_spawn_prompt.py` 是 shim，转调 shared-core 的实现，
  后者只做 load_plugin + load_member_md + parse_frontmatter + 拼 task_payload，
  **从不读 `_collapse/` 目录、也不读 `config/domain-profiles.yaml`**。
  另有一处 frontmatter 撕裂：`shared-core` 的 `parse_frontmatter` 用
  `md_text.split("---", 2)` 切分，而成员 MD 的注释里含**行内**闭合符字面量，
  导致切分提前截断——装配产物里 frontmatter 只剩 name/maxTurns，正文混入半截注释。

守卫范围（每条断言都对应一个真实缺陷，不是形式主义）：
  T1  6 份成员 MD 经装配后，**正文与原文逐字节相等**（防 frontmatter 再次撕裂）
  T1b frontmatter 块内**不含**闭合符子串（撕裂的充分条件）
  T2  装配产物含 `name` / `description` / `maxTurns` 三键（core 会丢弃 description）
  T3  已确认坍缩产物时，产物含 role_persona.title 与该域 content_axes 首项
  T4  坍缩未确认时，**不注入**域人格且有显式警告
  T5  无坍缩产物 / 域档案缺失时，按 fallback 通用兜底并带标注
  T6  成员在该域为 domain_neutral 时不注入域人格

用法：
    python3 -m pytest scripts/test_spawn_injection.py -q
    python3 scripts/test_spawn_injection.py          # 直跑（ensure_settings 第 7 项用）
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ASSEMBLER = HERE / "assemble_domain_prompt.py"
HARNESS = HERE / "harness.py"
AGENTS_DIR = PKG / "agents"
PROFILE_YAML = PKG / "config" / "domain-profiles.yaml"
PY = sys.executable

ROLE_BEGIN = "==================== 角色定义（专家包成员 MD 全文） ===================="
ROLE_END = "==================== 角色定义结束 ===================="
DOMAIN_BEGIN = "==================== 域上下文（v3.17.0 坍缩产物注入） ===================="

MEMBER_IDS = ["dvm-content-expert", "pedagogy-architect", "visual-slide-designer",
              "ppt-producer", "verifier", "vet-med-ppt-team-team-lead"]


# ───────────────────────────────────────────────── 工具
def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def assemble(member: str, out_path: str, task_file: str | None = None,
             run_dir: str | None = None, collapse: str | None = None,
             profile: str | None = None, workspace: str | None = None,
             member_id: str | None = None) -> tuple[int, str, str]:
    """跑本包装配器，返回 (rc, stdout, stderr)。"""
    cmd = [PY, str(ASSEMBLER), "--member", member_id or member, "--out", out_path]
    if task_file:
        cmd += ["--task-file", task_file]
    if run_dir:
        cmd += ["--run-dir", run_dir]
    if collapse:
        cmd += ["--collapse-artifact", collapse]
    if profile:
        cmd += ["--domain-profile", profile]
    if workspace:
        cmd += ["--workspace", workspace]
    return _run(cmd)


def extract_body(prompt: str) -> str:
    """从装配产物中取出「角色定义」段的正文（frontmatter 之后的全部内容）。"""
    i = prompt.find(ROLE_BEGIN)
    j = prompt.find(ROLE_END)
    assert i >= 0 and j > i, "装配产物缺少角色定义段标记"
    seg = prompt[i + len(ROLE_BEGIN):j]
    lines = seg.split("\n")
    assert lines and lines[0] == "", "frontmatter 起始符前应为空行"
    assert lines[1].rstrip() == "---", "frontmatter 起始符缺失"
    k = 2
    while k < len(lines) and lines[k].rstrip() != "---":
        k += 1
    assert k < len(lines), "frontmatter 闭合符缺失"
    return "\n".join(lines[k + 1:]).strip("\n")


def extract_fm_block(prompt: str) -> str:
    """取出装配产物头部的 frontmatter **内容**（不含首尾两个分隔符）。"""
    i = prompt.find(ROLE_BEGIN)
    j = prompt.find(ROLE_END)
    seg = prompt[i + len(ROLE_BEGIN):j]
    lines = seg.split("\n")
    k = 2
    while k < len(lines) and lines[k].rstrip() != "---":
        k += 1
    assert k < len(lines), "frontmatter 闭合符缺失"
    return "\n".join(lines[2:k])


def domain_section(prompt: str) -> str:
    """取出**实际注入**的域上下文段（从角色定义结束之后的第一个标记起）。

    不能全文第一个命中——成员 MD 正文里也可能提到该标记字面量。
    """
    role_end = prompt.find(ROLE_END)
    start = prompt.find(DOMAIN_BEGIN, role_end)
    if start < 0:
        return ""
    end = prompt.find("==================== 域上下文结束", start)
    return prompt[start:end] if end > start else prompt[start:]


def source_body(md_text: str) -> tuple[str, str]:
    """返回 (frontmatter_raw, body)：body = 去掉 frontmatter 后的原文正文。"""
    if not md_text.startswith("---"):
        return "", md_text
    lines = md_text.split("\n")
    k = 1
    while k < len(lines) and lines[k].rstrip() != "---":
        k += 1
    if k >= len(lines):
        return "", md_text
    return "\n".join(lines[1:k]), "\n".join(lines[k + 1:]).lstrip("\n")


# ───────────────────────────────────────────────── 夹具
def make_artifact(domain_id: str = "computing", confirmed: bool = True) -> dict:
    """构造一份形态与 harness.py 落盘一致的坍缩产物。"""
    art = {
        "schema": "vet-med-ppt-team.collapse/1.0",
        "task_id": "adhoc",
        "domain_id": domain_id,
        "domain_display_name": "计算机与软件工程",
        "domain_profile_path": str(PROFILE_YAML),
        "status": "confirmed" if confirmed else "pending_confirmation",
        "effective": bool(confirmed),
        "role_persona": {
            "title": "软件工程内容权威",
            "background": "有生产工程实践与一线教学经验的工程师",
            "stance": "能复现的才算数——不编造 API 行为、不凭记忆写版本特性",
            "duties": ["供给经核验的工程知识，并标注版本适用性"],
            "duty_boundary": "只做内容核验、证据检索与分级、术语规范；不做教学设计、不做版式设计",
        },
        "role_persona_status": "effective" if confirmed else "pending",
        "content_axes": ["语言语义与类型系统", "算法与复杂度分析"],
        "evidence_hierarchy": {
            "institutional": ["语言与平台的**官方文档 / 语言规范 / 参考手册**（须现查对应版本）"],
            "literature": ["同行评议论文与预印本"],
        },
        "image_channel": {
            "channels": [{"name": "官方文档与官方图示", "role": "架构图 / 流程图 / 行为示意",
                          "status": "有效"}],
            "query_elements": ["技术栈 / 组件名"],
            "query_template": "<技术栈/组件> <版本> <场景或概念>",
        },
        "knowledge_bases": [],
        "terminology": ["API / 缩写首次出现给全称"],
        "safety_redlines": ["涉及认证授权、密钥、隐私的内容：只给高层原则与合规要求"],
        "knowledge_anchor": {"path": None, "note": "本域**无包内知识锚点**——需联网现查官方文档"},
    }
    if confirmed:
        art["confirmed_at"] = "2026-10-24T20:39:21+08:00"
        art["confirmed_by"] = "team-lead"
        art["selection_rationale"] = "测试选型理由"
        art["selection_rationale_status"] = "filled"
    return art


def write_artifact(path: Path, art: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


# ───────────────────────────────────────────────── T1 正文逐字节一致
class TestBodyIntegrity(unittest.TestCase):
    """T1：装配产物的正文必须与成员 MD 原文正文逐字节相等（防 frontmatter 撕裂）。"""

    def _assemble_all(self, tmp: Path) -> dict:
        out = {}
        for mid in MEMBER_IDS:
            op = tmp / f"spawn_{mid}.md"
            rc, so, se = assemble(mid, str(op))
            self.assertEqual(rc, 0, f"{mid} 装配失败 rc={rc}: {se}")
            out[mid] = op.read_text(encoding="utf-8")
        return out

    def test_T1_body_byte_identical_to_source(self):
        tmp = Path(tempfile.mkdtemp())
        assembled = self._assemble_all(tmp)
        for mid in MEMBER_IDS:
            md_text = (AGENTS_DIR / f"{mid}.md").read_text(encoding="utf-8")
            _, body = source_body(md_text)
            got = extract_body(assembled[mid])
            self.assertEqual(got, body.rstrip(),
                             f"{mid} 的装配正文与原文不一致（前 200 字：{got[:200]!r}）")

    def test_T1b_no_inline_closing_delimiter_in_frontmatter(self):
        """frontmatter 块内不得出现闭合符子串——这是撕裂的充分条件。"""
        for mid in MEMBER_IDS:
            md_text = (AGENTS_DIR / f"{mid}.md").read_text(encoding="utf-8")
            fm_raw, _ = source_body(md_text)
            self.assertNotIn("---", fm_raw,
                             f"{mid} 的 frontmatter 内含闭合符字面量（按子串切分会被提前截断）")

    def test_T1c_body_has_no_frontmatter_leakage(self):
        """装配正文不得混入 frontmatter 内容（撕裂的历史特征）。"""
        tmp = Path(tempfile.mkdtemp())
        assembled = self._assemble_all(tmp)
        for mid in MEMBER_IDS:
            body = extract_body(assembled[mid])
            for leak in ("误落在正文里", "导致整段 frontmatter 不可 YAML 解析"):
                self.assertNotIn(leak, body,
                                 f"{mid} 的装配正文混入了 frontmatter 注释片段：{leak!r}")
            md_text = (AGENTS_DIR / f"{mid}.md").read_text(encoding="utf-8")
            self.assertNotIn(md_text.split("\n")[0] + "\nname:", body,
                             f"{mid} 的装配正文开头疑似含 frontmatter")

    def test_T1d_core_and_strict_parse_agree(self):
        """本包严格切分与 shared-core 切分，在 6 份成员 MD 上正文必须完全一致。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("_shim", HERE / "assemble_spawn_prompt.py")
        shim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shim)
        core = shim._mod
        spec2 = importlib.util.spec_from_file_location("_dom", ASSEMBLER)
        dom = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(dom)
        for mid in MEMBER_IDS:
            md_text = (AGENTS_DIR / f"{mid}.md").read_text(encoding="utf-8")
            _, core_body = core.parse_frontmatter(md_text)
            _, strict_body = dom.parse_frontmatter_strict(md_text)
            self.assertEqual(core_body, strict_body,
                             f"{mid} 的正文在 core 切分与严格切分下不一致")


# ───────────────────────────────────────────────── T2 frontmatter 键
class TestFrontmatterKeys(unittest.TestCase):
    """T2：装配产物头部必须含 name / description / maxTurns 三键。"""

    def test_T2_assembly_has_three_keys(self):
        tmp = Path(tempfile.mkdtemp())
        for mid in MEMBER_IDS:
            op = tmp / f"spawn_{mid}.md"
            rc, _, se = assemble(mid, str(op))
            self.assertEqual(rc, 0, f"{mid} 装配失败: {se}")
            fm = extract_fm_block(op.read_text(encoding="utf-8"))
            self.assertIn(f"name: {mid}", fm, f"{mid} 装配产物缺 name 键")
            self.assertIn("description:", fm, f"{mid} 装配产物缺 description 键")
            self.assertIn("maxTurns:", fm, f"{mid} 装配产物缺 maxTurns 键")

    def test_T2b_description_and_profession_reflected(self):
        """description / profession 是成员定位声明，必须进装配产物。"""
        tmp = Path(tempfile.mkdtemp())
        op = tmp / "spawn_dvm.md"
        rc, _, se = assemble("dvm-content-expert", str(op))
        self.assertEqual(rc, 0, se)
        fm = extract_fm_block(op.read_text(encoding="utf-8"))
        md_text = (AGENTS_DIR / "dvm-content-expert.md").read_text(encoding="utf-8")
        fm_raw, _ = source_body(md_text)
        self.assertIn("profession:", fm, "装配产物缺 profession 键")
        self.assertIn("领域内容权威", fm, "profession.zh 未进装配产物")
        self.assertIn("内容权威（域无关）", fm, "description 未进装配产物")

    def test_T2c_frontmatter_block_is_valid_yaml(self):
        """装配产物头部的 frontmatter 块必须可被 YAML 解析（防止回填格式坏掉）。"""
        import yaml
        tmp = Path(tempfile.mkdtemp())
        for mid in MEMBER_IDS:
            op = tmp / f"spawn_{mid}.md"
            assemble(mid, str(op))
            fm = extract_fm_block(op.read_text(encoding="utf-8"))
            data = yaml.safe_load(fm)
            self.assertIsInstance(data, dict, f"{mid} 的 frontmatter 块不是 YAML 映射")
            self.assertEqual(data.get("name"), mid)


# ───────────────────────────────────────────────── T3 已确认 → 注入域人格
class TestConfirmedInjection(unittest.TestCase):
    """T3：已确认的坍缩产物必须真的进入装配产物。"""

    def test_T3_confirmed_artifact_injects_persona_and_axes(self):
        tmp = Path(tempfile.mkdtemp())
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=True))
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=art_path)
        self.assertEqual(rc, 0, se)
        text = op.read_text(encoding="utf-8")
        section = domain_section(text)
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertIn("软件工程内容权威", section, "域上下文段缺 role_persona.title")
        self.assertIn("语言语义与类型系统", section, "域上下文段缺 content_axes 首项")
        self.assertIn("域人格已生效", section, "域上下文段未标出生效状态")

    def test_T3b_injection_sits_between_role_and_task(self):
        """域上下文段必须落在「角色定义」之后、「任务包」之前。"""
        tmp = Path(tempfile.mkdtemp())
        task = tmp / "task.md"
        task.write_text("objective: x\noutput_format: y\nconstraints: []\ntask_boundary: z",
                        encoding="utf-8")
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=True))
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), task_file=str(task),
                             collapse=art_path)
        self.assertEqual(rc, 0, se)
        text = op.read_text(encoding="utf-8")
        role_end = text.find(ROLE_END)
        # 从「角色定义结束」之后开始找域上下文段——成员 MD 正文里也可能提到该标记字面量，
        # 不能全文第一个命中就是注入段（否则测的是文档提及而不是注入位置）。
        dom = text.find(DOMAIN_BEGIN, role_end)
        self.assertGreater(role_end, 0, "装配产物缺角色定义结束标记")
        self.assertGreater(dom, role_end, "域上下文段未落在角色定义之后")
        task_pos = text.find("==================== 任务包", dom)
        self.assertGreater(task_pos, dom, "域上下文段未落在任务包之前")


# ───────────────────────────────────────────────── T4 未确认 → 不注入
class TestUnconfirmedNoInjection(unittest.TestCase):
    """T4：坍缩未确认 → 不注入域人格 + 显式警告。"""

    def test_T4_unconfirmed_artifact_not_injected(self):
        tmp = Path(tempfile.mkdtemp())
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=False))
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=art_path)
        self.assertEqual(rc, 0, se)
        text = op.read_text(encoding="utf-8")
        section = domain_section(text)
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertNotIn("软件工程内容权威", section,
                         "未确认的坍缩产物仍被注入——违反安全语义")
        self.assertNotIn("语言语义与类型系统", section,
                         "未确认的坍缩产物仍被注入 content_axes")
        self.assertIn("域人格未生效（未确认）", section, "域上下文段缺显式警告")
        self.assertIn("域人格未生效（未确认）", se, "stderr 缺显式警告")

    def test_T4b_effective_false_also_blocks(self):
        """status=confirmed 但 effective=false → 同样视为未生效。"""
        tmp = Path(tempfile.mkdtemp())
        art = make_artifact(confirmed=True)
        art["effective"] = False
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json", art)
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=art_path)
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertNotIn("软件工程内容权威", section, "effective=false 仍被注入")
        self.assertIn("域人格未生效（未确认）", section)


# ───────────────────────────────────────────────── T5 兜底
class TestFallback(unittest.TestCase):
    """T5：无坍缩产物 / 域档案缺失 → 按 fallback 通用兜底并带标注。"""

    def test_T5_no_artifact_fallback(self):
        tmp = Path(tempfile.mkdtemp())
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertNotIn("软件工程内容权威", section, "无坍缩产物却注入了域人格")
        self.assertIn("未找到坍缩产物", section, "缺『未找到坍缩产物』提示")
        self.assertIn("通用兜底", section, "缺通用兜底标注")

    def test_T5b_profile_domain_missing_fallback(self):
        """域档案里没有该域 → 通用兜底 + 显式标注『本条按通用兜底处理』。"""
        tmp = Path(tempfile.mkdtemp())
        prof = tmp / "profile.yaml"
        prof.write_text(
            "fallback:\n"
            "  generic_persona:\n"
            "    title: \"内容权威\"\n"
            "    background: \"通用背景\"\n"
            "    stance: \"通用立场\"\n"
            "    duty_boundary: \"通用边界\"\n"
            "  generic_evidence_hierarchy:\n"
            "    institutional:\n"
            "      - \"通用机构源\"\n"
            "    literature:\n"
            "      - \"通用文献源\"\n"
            "  generic_safety_redlines:\n"
            "    - \"通用红线\"\n"
            "domains: []\n",
            encoding="utf-8")
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=True))
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=art_path,
                             profile=str(prof))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertIn("本条按通用兜底处理", section, "缺『本条按通用兜底处理』标注")
        self.assertNotIn("软件工程内容权威", section, "域档案缺失却注入了域人格")
        self.assertNotIn("动物医学", section, "缺域档案时不得回落 animal-medicine 域")
        self.assertIn("通用背景", section, "通用兜底内容未渲染")

    def test_T5c_unreadable_profile_falls_back_to_package_default(self):
        """域档案路径读不到 → 兜底内容取自包内默认档案，仍带标注。"""
        tmp = Path(tempfile.mkdtemp())
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=True))
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=art_path,
                             profile=str(tmp / "does_not_exist.yaml"))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertIn("本条按通用兜底处理", section, "缺『本条按通用兜底处理』标注")
        self.assertNotIn("软件工程内容权威", section, "域档案不可读却注入了域人格")
        self.assertNotIn("动物医学", section, "缺域档案时不得回落 animal-medicine 域")


# ───────────────────────────────────────────────── T6 domain_neutral 成员
class TestNeutralMember(unittest.TestCase):
    """T6：成员在该域为 domain_neutral 时不注入域人格。"""

    def test_T6_neutral_member_gets_no_persona(self):
        tmp = Path(tempfile.mkdtemp())
        art_path = write_artifact(tmp / "_collapse" / "collapse_adhoc_computing.json",
                                  make_artifact(confirmed=True))
        op = tmp / "spawn.md"
        rc, _, se = assemble("verifier", str(op), collapse=art_path)
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertNotIn("软件工程内容权威", section, "domain_neutral 成员被注入了域人格")
        self.assertIn("domain_neutral", section, "缺 domain_neutral 说明")


# ───────────────────────────────────────────────── T7 端到端（真实 harness 链路）
class TestEndToEnd(unittest.TestCase):
    """T7：真实 harness 链路 route → collapse confirm → 装配，域人格必须落地。"""

    def test_T7_real_harness_route_confirm_then_assemble(self):
        ws = Path(tempfile.mkdtemp())
        rc, so, se = _run([PY, str(HARNESS), "route", "--level", "L2",
                            "--domain", "computing", "--rationale", "回归测试",
                            "--workspace", str(ws)])
        self.assertEqual(rc, 0, f"route 失败: {se}")
        rc, so, se = _run([PY, str(HARNESS), "collapse", "confirm", "--id", "computing",
                            "--task-id", "adhoc", "--workspace", str(ws)])
        self.assertEqual(rc, 0, f"collapse confirm 失败: {se}")
        art = ws / ".harness-runs" / "adhoc" / "_collapse" / "collapse_adhoc_computing.json"
        self.assertTrue(art.is_file(), f"坍缩产物未落盘：{art}")
        obj = json.loads(art.read_text(encoding="utf-8"))
        self.assertEqual(obj.get("status"), "confirmed")
        self.assertTrue(obj.get("effective"))

        op = ws / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=str(art))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertIn("软件工程内容权威", section, "端到端装配产物缺域人格称号")
        self.assertIn("语言语义与类型系统", section, "端到端装配产物缺 content_axes 首项")
        self.assertEqual(section.count("软件工程内容权威"), 1,
                         "域人格称号在域上下文段中重复出现")

    def test_T7b_route_then_assemble_unconfirmed_is_blocked(self):
        """只 route（未 confirm）→ 装配产物必须拒绝注入域人格。"""
        ws = Path(tempfile.mkdtemp())
        rc, _, se = _run([PY, str(HARNESS), "route", "--level", "L2",
                          "--domain", "computing", "--rationale", "回归测试",
                          "--workspace", str(ws)])
        self.assertEqual(rc, 0, se)
        art = ws / ".harness-runs" / "adhoc" / "_collapse" / "collapse_adhoc_computing.json"
        self.assertTrue(art.is_file())
        op = ws / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op), collapse=str(art))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertNotIn("软件工程内容权威", section, "未确认却被注入域人格")
        self.assertIn("域人格未生效（未确认）", section, "缺未确认警告")


# ───────────────────────────────────────────────── T8 兜底内容与档案一致（防漂移）
class TestFallbackSourceSingle(unittest.TestCase):
    """T8：通用兜底内容必须来自 config/domain-profiles.yaml#fallback（唯一源）。"""

    def test_T8_fallback_matches_profile_yaml(self):
        import yaml
        prof = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8"))
        fb = prof.get("fallback") or {}
        gp = fb.get("generic_persona") or {}
        tmp = Path(tempfile.mkdtemp())
        op = tmp / "spawn.md"
        rc, _, se = assemble("dvm-content-expert", str(op))
        self.assertEqual(rc, 0, se)
        section = domain_section(op.read_text(encoding="utf-8"))
        self.assertTrue(section, "装配产物缺域上下文段")
        self.assertIn(gp.get("title", "内容权威"), section, "兜底称号与档案不一致")
        if gp.get("background"):
            self.assertIn(gp["background"], section, "兜底背景与档案不一致")
        for r in fb.get("generic_safety_redlines") or []:
            self.assertIn(r, section, "兜底红线与档案不一致")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ── 归属声明 ──────────────────────────────────────────────────────
# 所有者/执行者: 主理人 / 编排层（vet-med-ppt-team-team-lead 全课吉）
# 用途: spawn 前装配成员人设提示词（基础装配 + **域上下文注入** + frontmatter 键补偿）
# 何时被调用: 每次 spawn 成员的**强制第一步**（P0）——不跑装配直接 spawn 即违纪
# ─────────────────────────────────────────────────────────────────────
"""
assemble_domain_prompt.py — 成员 spawn 人设装配器（本包版 · 基础装配 + 域上下文注入）
=================================================================================
v3.17.0 批次 B 新建。本文件**不替代** `scripts/assemble_spawn_prompt.py`（联邦 shim），
而是**在其之上**补三件联邦共享件不做的事：

  ① **域上下文注入**（本轮核心修复）
     背景（2026-10-24 端到端实测，非假设）：
       `harness.py route --domain computing` 正确落盘 `_collapse/collapse_*.json`，
       `harness.py collapse confirm` 正确置 status=confirmed / effective=true，
       但装配产物中域人格关键词命中数 = **0**——
       因为 shared-core 的 `assemble_spawn_prompt.py` 只做
       `load_plugin + load_member_md + parse_frontmatter + 拼 task_payload`，
       **从不读 `_collapse/` 目录、也不读 `config/domain-profiles.yaml`**。
     修法（本文件）：读坍缩产物 → 校验生效状态 → 组织结构化「域上下文」段 →
       插入到「角色定义」段之后、「任务包」段之前。
     ⚠ **不修改 shared-core**（联邦共享件，影响另外 4 个包，需另案上提）。

  ② **frontmatter 键补偿**
     shared-core 的 `parse_frontmatter` 只取 `name` / `maxTurns` / `skills`，
     **丢弃** `description` / `profession` / `displayName`——
     而这三个键定义了成员定位与域无关声明，必须出现在装配产物里。
     补偿方式：本文件自行稳健切分 frontmatter（全键），装配后回填。

  ③ **frontmatter 撕裂防护**
     shared-core 的 `parse_frontmatter` 用 `md_text.split("---", 2)` 切分，
     而 `agents/dvm-content-expert.md` 的 v3.17.0 变更注释里**含行内 `---` 字面量**
     → 切分提前截断（frontmatter 只剩 name/maxTurns，正文混入半截注释）。
     本文件用「闭合符必须独占一行」的稳健切分，**行为不受行内 `---` 影响**。

安全语义（**不满足即不注入，绝不静默按已确认处理**）：
  · 坍缩产物 `status != "confirmed"` 或 `effective != true`
    → **不注入域人格**，装配产物内打印显式警告「域人格未生效（未确认）」。
  · 域档案（`config/domain-profiles.yaml`）读不到 / 找不到该域
    → 按 `config/domain-profiles.yaml#fallback` 的**通用兜底**渲染，
      并显式标注「本条按通用兜底处理」。
  · **严禁**在缺域档案时静默回落某个具体域（尤其 animal-medicine）——包内宪法。
  · 成员在该域的绑定为 `domain_neutral` 时**不注入域人格**（职责与域无关）。

用法：
    python3 scripts/assemble_domain_prompt.py --member dvm-content-expert \
        --task-file task.json --run-dir "$RUN_DIR" \
        --collapse-artifact "$RUN_DIR/_collapse/collapse_adhoc_computing.json" \
        --out "$RUN_DIR/spawn__dvm-content-expert.md"

退出码：
    0 = 成功；2 = 成员 ID 不在白名单；3 = 文件缺失（坍缩产物/域档案不可读）；4 = 任务包要素缺失
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SHIM = os.path.join(HERE, "assemble_spawn_prompt.py")

LOG_PREFIX = "[assemble_domain_prompt]"
DEFAULT_PROFILE_REL = "config/domain-profiles.yaml"

# shared-core 装配产物的段标记（用于定位插入点；core 侧结构固定，便于审计与 diff）
ROLE_BEGIN = "==================== 角色定义（专家包成员 MD 全文） ===================="
ROLE_END = "==================== 角色定义结束 ===================="
DOMAIN_BEGIN = "==================== 域上下文（v3.17.0 坍缩产物注入） ===================="
DOMAIN_END = "==================== 域上下文结束 ===================="


def log(msg: str) -> None:
    """统一日志输出到 stderr，避免污染 stdout 的 prompt 正文。"""
    print(f"{LOG_PREFIX} {msg}", file=sys.stderr)


# ───────────────────────────────────────────────── 加载 shared-core
def _load_core():
    """经本包 shim 加载 shared-core 实现（shim 负责 core 路径反推与缺失提示）。

    返回 core 模块对象；core 缺失时 shim 自己会退出（exit 3），此处兜底再抛。
    """
    if not os.path.isfile(SHIM):
        print(f"{LOG_PREFIX} ❌ 本包 shim 缺失：{SHIM}", file=sys.stderr)
        sys.exit(3)
    spec = importlib.util.spec_from_file_location("_vet_med_assemble_shim", SHIM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # shim 在 import 期加载 core 并置 EXPERT_DIR
    core = getattr(mod, "_mod", None)
    if core is None:
        print(f"{LOG_PREFIX} ❌ shim 未暴露 core 模块（core 缺失）", file=sys.stderr)
        sys.exit(3)
    return core


# ───────────────────────────────────────────────── frontmatter 稳健切分
_FM_BLOCK_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def parse_frontmatter_strict(md_text: str) -> tuple[str, str]:
    """稳健切分 frontmatter 与正文，返回 (frontmatter_raw, body)。

    与 shared-core 的 `md_text.split("---", 2)` 的关键差异：
      **闭合符必须独占一行**（行首 `---` + 行尾可选空白）。
    因此正文或注释里出现的行内 `---` 字面量**不会**造成提前截断——
    这正是 `agents/dvm-content-expert.md` v3.17.0 注释里踩过的坑。

    body 的处理与 core 逐字节一致：`成功切分 → lstrip("\\n")；失败 → 原样返回`。
    """
    if not md_text.startswith("---"):
        return "", md_text
    m = _FM_BLOCK_RE.match(md_text)
    if not m:
        return "", md_text
    return m.group(1), md_text[m.end():].lstrip("\n")


def parse_fm_mapping(fm_raw: str) -> dict:
    """把 frontmatter 原文解析成映射（优先 PyYAML，失败退化极简解析）。"""
    if not fm_raw.strip():
        return {}
    try:
        import yaml  # noqa
        data = yaml.safe_load(fm_raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    out: dict = {}
    for line in fm_raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def _skills_of(fm_map: dict) -> list:
    """取 frontmatter 的 skills（列表或 `[a, b]` 字符串两种写法）。"""
    sk = fm_map.get("skills")
    if isinstance(sk, list):
        return [str(x).strip() for x in sk if str(x).strip()]
    if isinstance(sk, str) and sk.strip():
        return [s.strip().strip('"') for s in sk.strip().strip("[]").split(",") if s.strip()]
    return []


# ───────────────────────────────────────────────── 域档案
def load_profile(path: str):
    """读域档案，返回 (data, err)；err 非 None = 不可用。"""
    try:
        import yaml  # noqa
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return None, f"域档案读取失败（{e}）：{path}"
    if not isinstance(data, dict):
        return None, f"域档案格式非法（顶层须是映射）：{path}"
    return data, None


def find_domain(profiles: dict, domain_id: str):
    """按 id 取域档案；取不到返回 None（**调用方必须显式标注兜底，不得静默回落**）。"""
    for d in (profiles or {}).get("domains") or []:
        if isinstance(d, dict) and str(d.get("id")) == str(domain_id):
            return d
    return None


def _fallback_block(profiles: dict) -> dict:
    return (profiles or {}).get("fallback") or {}


# ───────────────────────────────────────────────── 坍缩产物
def read_collapse_artifact(path: str):
    """读坍缩产物 JSON，返回 (obj, err)。"""
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except FileNotFoundError:
        return None, f"坍缩产物不存在：{path}"
    except Exception as e:
        return None, f"坍缩产物解析失败（{e}）：{path}"
    if not isinstance(obj, dict):
        return None, f"坍缩产物格式非法（顶层须是映射）：{path}"
    return obj, None


def _artifact_state(obj: dict) -> tuple[bool, str]:
    """坍缩产物是否已生效。返回 (effective, 说明)。

    契约：**status != confirmed 或 effective != true 一律视为未生效**，
    不得静默按已确认处理。
    """
    status = str(obj.get("status") or "")
    eff = obj.get("effective")
    if status == "confirmed" and eff is True:
        return True, f"status={status} / effective={eff}"
    return False, f"status={status or '(缺失)'} / effective={eff}"


def discover_collapse_artifacts(run_dir: str | None, workspace: str | None) -> list:
    """在 run-dir / workspace 下发现坍缩产物（返回路径列表，按修改时间倒序）。"""
    dirs: list[str] = []
    if run_dir:
        dirs.append(os.path.join(run_dir, "_collapse"))
    if workspace:
        root = os.path.join(os.path.abspath(workspace), ".harness-runs")
        if os.path.isdir(root):
            for tid in sorted(os.listdir(root)):
                dirs.append(os.path.join(root, tid, "_collapse"))
    found: list[str] = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.startswith("collapse_") and fn.endswith(".json"):
                found.append(os.path.join(d, fn))
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found


def pick_collapse_artifact(candidates: list):
    """从候选产物中挑一个：优先「已确认且生效」，其次最新（未确认，用于发警告）。"""
    confirmed = []
    for p in candidates:
        obj, err = read_collapse_artifact(p)
        if err:
            continue
        ok, _ = _artifact_state(obj)
        if ok:
            confirmed.append((p, obj))
    if confirmed:
        confirmed.sort(key=lambda t: str(t[1].get("confirmed_at") or ""), reverse=True)
        return confirmed[0][0], confirmed[0][1], None
    if candidates:
        p = candidates[0]
        obj, err = read_collapse_artifact(p)
        if err:
            return None, None, err
        return p, obj, None
    return None, None, None


# ───────────────────────────────────────────────── 域上下文渲染
def _bullets(items, indent: str = "- ") -> list:
    out = []
    for it in items or []:
        if it is None:
            continue
        if isinstance(it, dict):
            out.append(f"{indent}{it}")
        else:
            out.append(f"{indent}{it}")
    return out


def _render_generic(fb: dict) -> list:
    """渲染通用兜底段（不含任何域专有信息）。"""
    lines = []
    gp = fb.get("generic_persona") or {}
    lines.append("【通用人设】（不含任何域专有信息）")
    if gp.get("title"):
        lines.append(f"- 称号：{gp['title']}")
    if gp.get("background"):
        lines.append(f"- 背景：{gp['background']}")
    if gp.get("stance"):
        lines.append(f"- 立场：{gp['stance']}")
    if gp.get("duty_boundary"):
        lines.append(f"- 职责边界：{gp['duty_boundary']}")
    gh = fb.get("generic_evidence_hierarchy") or {}
    if gh.get("institutional") or gh.get("literature"):
        lines.append("【通用证据轴】（两条独立轴）")
        if gh.get("institutional"):
            lines.append("- 机构权威轴（谁说了算）：")
            lines += _bullets(gh.get("institutional"), "  - ")
        if gh.get("literature"):
            lines.append("- 文献权威轴（证据强度与时效）：")
            lines += _bullets(gh.get("literature"), "  - ")
    if fb.get("generic_safety_redlines"):
        lines.append("【通用红线】（任何域都成立的底线）")
        lines += _bullets(fb.get("generic_safety_redlines"))
    return lines


def _render_domain_context(artifact: dict, domain: dict, artifact_path: str) -> list:
    """渲染**已确认域**的上下文段（内容源 = 坍缩产物快照，档案补缺）。"""
    lines = []
    lines.append("【生效状态】✅ 域人格已生效（status=confirmed / effective=true）")
    dom_id = artifact.get("domain_id") or (domain or {}).get("id")
    dom_name = artifact.get("domain_display_name") or (domain or {}).get("display_name")
    if dom_id:
        lines.append(f"【所属域】{dom_id}" + (f"（{dom_name}）" if dom_name else ""))
    if artifact_path:
        lines.append(f"【坍缩产物】{artifact_path}")
    if artifact.get("confirmed_at"):
        lines.append(f"【确认时间】{artifact['confirmed_at']}"
                     + (f"　【确认人】{artifact['confirmed_by']}" if artifact.get("confirmed_by") else ""))
    if artifact.get("selection_rationale"):
        lines.append(f"【选型理由】{artifact['selection_rationale']}")

    def pick(key):
        v = artifact.get(key)
        if v in (None, [], {}, ""):
            v = (domain or {}).get(key)
        return v

    persona = pick("role_persona") or {}
    if persona:
        lines.append("【一、域人格】")
        if persona.get("title"):
            lines.append(f"- 称号：{persona['title']}")
        if persona.get("background"):
            lines.append(f"- 背景：{persona['background']}")
        if persona.get("stance"):
            lines.append(f"- 立场：{persona['stance']}")
        if persona.get("duties"):
            lines.append("- 职责：")
            lines += _bullets(persona.get("duties"), "  - ")
        if persona.get("duty_boundary"):
            lines.append(f"- 职责边界：{persona['duty_boundary']}")

    axes = pick("content_axes")
    if axes:
        lines.append("【二、内容轴（知识覆盖方向）】")
        lines += _bullets(axes)

    ev = pick("evidence_hierarchy") or {}
    if ev:
        lines.append("【三、证据层级（两条独立轴，不可合成平铺序数表）】")
        if ev.get("institutional"):
            lines.append("- 机构权威轴（谁说了算）：")
            lines += _bullets(ev.get("institutional"), "  - ")
        if ev.get("literature"):
            lines.append("- 文献权威轴（证据强度与时效）：")
            lines += _bullets(ev.get("literature"), "  - ")
        if ev.get("axes_note"):
            lines.append(f"- 轴说明：{ev['axes_note']}")
        if ev.get("time_layers"):
            lines.append("- 时限分层：")
            lines += _bullets(ev.get("time_layers"), "  - ")
        if ev.get("dual_source_rule"):
            lines.append(f"- 双源规则：{ev['dual_source_rule']}")

    ic = pick("image_channel") or {}
    if ic:
        lines.append("【四、取图通道与检索式】")
        chans = ic.get("channels") or []
        if chans:
            lines.append("- 通道（按稳定度排序）：")
            for c in chans:
                if not isinstance(c, dict):
                    lines.append(f"  - {c}")
                    continue
                parts = [str(c.get("name") or "")]
                if c.get("role"):
                    parts.append(str(c["role"]))
                if c.get("status"):
                    parts.append(str(c["status"]))
                lines.append("  - " + "｜".join(parts))
                if c.get("endpoint"):
                    lines.append(f"    - 端点：{c['endpoint']}")
                if c.get("license_rule"):
                    lines.append(f"    - 许可规则：{c['license_rule']}")
        if ic.get("query_elements"):
            lines.append("- 检索式要素：")
            lines += _bullets(ic.get("query_elements"), "  - ")
        if ic.get("query_template"):
            lines.append(f"- 检索式模板：{ic['query_template']}")
        if ic.get("examples"):
            lines.append("- 示例（骨架，具体以当次检索到的原文为准）：")
            for ex in ic.get("examples"):
                if not isinstance(ex, dict):
                    lines.append(f"  - {ex}")
                    continue
                lines.append(f"  - {ex.get('query') or ''}"
                             + (f" → 目标：{ex['target']}" if ex.get("target") else ""))
                if ex.get("caption_hint"):
                    lines.append(f"    - 图注提示：{ex['caption_hint']}")
        if ic.get("caption_elements"):
            lines.append("- 图注要素：")
            lines += _bullets(ic.get("caption_elements"), "  - ")
        if ic.get("forbidden_sources"):
            lines.append("- 禁止来源：")
            lines += _bullets(ic.get("forbidden_sources"), "  - ")
        if ic.get("knowledge_channel_ref"):
            lines.append(f"- 知识通道说明：{ic['knowledge_channel_ref']}")

    kb = pick("knowledge_bases")
    lines.append("【五、知识库路由（文本型，与取图通道并列）】")
    if kb:
        for k in kb:
            if isinstance(k, dict):
                nm = k.get("name") or ""
                kid = k.get("id") or ""
                when = k.get("when") or ""
                lines.append(f"- {nm}" + (f"（id: {kid}）" if kid else "")
                             + (f" —— 何时用：{when}" if when else ""))
            else:
                lines.append(f"- {k}")
    else:
        lines.append("- （本域无账号内知识库——按域档案给出的通道现查官方/制度原文；"
                     "**严禁**静默回落其它域的知识库）")
    if domain and domain.get("knowledge_bases_note"):
        lines.append(f"- 说明：{domain['knowledge_bases_note']}")

    term = pick("terminology")
    if term:
        lines.append("【六、术语规范】")
        lines += _bullets(term)

    red = pick("safety_redlines")
    if red:
        lines.append("【七、安全红线（拒收 / 高风险）】")
        lines += _bullets(red)

    ka = pick("knowledge_anchor")
    lines.append("【八、知识锚点】")
    if isinstance(ka, dict):
        p = ka.get("path")
        if p:
            lines.append(f"- 路径：{p}")
        else:
            lines.append("- 路径：（本域无包内知识锚点——需联网现查）")
        if ka.get("note"):
            lines.append(f"- 说明：{ka['note']}")
    elif isinstance(ka, str) and ka.strip():
        lines.append(f"- 路径：{ka}")
    else:
        lines.append("- 路径：（本域无包内知识锚点——需联网现查）")
    return lines


def _member_binding(domain: dict, member_id: str):
    """取成员在该域的绑定方式（persona_subject / domain_neutral）；取不到返回 None。"""
    for b in (domain or {}).get("member_bindings") or []:
        if isinstance(b, dict) and str(b.get("member")) == str(member_id):
            return str(b.get("binding") or "")
    return None


def build_domain_section(member_id: str,
                         artifact: dict | None,
                         artifact_path: str | None,
                         artifact_state_note: str,
                         domain: dict | None,
                         fallback: dict,
                         profile_err: str | None) -> tuple[str, str]:
    """构造「域上下文」段。返回 (段文本, 状态标记)。

    状态标记取值：effective / fallback_profile_missing / fallback_unconfirmed /
                  fallback_no_artifact / neutral_member
    """
    lines = []
    status = "effective"

    # ① 未确认 → 不注入域人格，显式警告
    if artifact is not None and not artifact_state_note.startswith("status=confirmed / effective=True"):
        status = "fallback_unconfirmed"
        lines.append(DOMAIN_BEGIN)
        lines.append("⚠️ 域人格未生效（未确认）——本次**不注入**域人格。")
        lines.append(f"【未生效原因】坍缩产物 {artifact_state_note}；"
                     "须经 `harness.py collapse confirm` 确认后方可注入。")
        lines.append("【以下仅为通用兜底人设，不得当作域人格使用】")
        lines += _render_generic(fallback)
        lines.append(DOMAIN_END)
        return "\n".join(lines), status

    # ② 无坍缩产物 → 不注入域人格，显式说明
    if artifact is None:
        status = "fallback_no_artifact"
        lines.append(DOMAIN_BEGIN)
        lines.append("⚠️ 未找到坍缩产物——本次**不注入**域人格。")
        lines.append("【以下仅为通用兜底人设，不得当作域人格使用】")
        lines += _render_generic(fallback)
        lines.append(DOMAIN_END)
        return "\n".join(lines), status

    # ③ 已确认，但域档案缺失 → 通用兜底 + 显式标注
    if domain is None:
        status = "fallback_profile_missing"
        reason = profile_err or (
            f"域档案中找不到域 id={artifact.get('domain_id')!r}"
            if artifact.get("domain_id") else "域档案中找不到对应域")
        lines.append(DOMAIN_BEGIN)
        lines.append("⚠️ 域档案不可用——**本条按通用兜底处理**。")
        lines.append(f"【兜底原因】{reason}")
        lines.append("【以下仅为通用兜底人设，不得当作域人格使用】")
        lines += _render_generic(fallback)
        lines.append(DOMAIN_END)
        return "\n".join(lines), status

    # ④ 已确认 + 域档案可用 → 域人格注入（成员绑定为 domain_neutral 则不注入）
    binding = _member_binding(domain, member_id)
    if binding == "domain_neutral":
        status = "neutral_member"
        lines.append(DOMAIN_BEGIN)
        lines.append(f"ℹ️ 域上下文：本成员（{member_id}）在本域的绑定为 `domain_neutral`"
                     "——职责与域无关，**不注入域人格**。")
        lines.append(DOMAIN_END)
        return "\n".join(lines), status

    lines.append(DOMAIN_BEGIN)
    lines += _render_domain_context(artifact, domain, artifact_path)
    lines.append(DOMAIN_END)
    return "\n".join(lines), status


# ───────────────────────────────────────────────── frontmatter 块回填
def _yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def _render_fm_block(fm_map: dict, core_fm: dict, member_id: str) -> str:
    """渲染装配产物头部的 frontmatter 块（含 core 丢弃的键）。"""
    lines = ["---"]
    name = fm_map.get("name") or core_fm.get("name") or member_id
    lines.append(f"name: {name}")
    if fm_map.get("description"):
        lines.append(f"description: {_yaml_scalar(fm_map['description'])}")
    for key in ("displayName", "profession"):
        val = fm_map.get(key)
        if isinstance(val, dict):
            lines.append(f"{key}:")
            for k2, v2 in val.items():
                lines.append(f"  {k2}: {_yaml_scalar(v2)}")
        elif val:
            lines.append(f"{key}: {_yaml_scalar(val)}")
    skills = _skills_of(fm_map)
    if skills:
        lines.append(f"skills: [{', '.join(skills)}]")
    if fm_map.get("maxTurns") is not None:
        lines.append(f"maxTurns: {fm_map.get('maxTurns')}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def enrich_frontmatter_block(prompt: str, fm_map: dict, core_fm: dict,
                              member_id: str) -> str:
    """把 core 装配产物的 frontmatter 块替换为**全键**版本（含 description/profession/displayName）。

    core 的块结构固定（`---\\nname: ...\\n[skills]\\n[maxTurns]\\n---`），
    按段标记定位后整块替换——只动这一块，正文逐字节不动。
    """
    idx = prompt.find(ROLE_BEGIN)
    if idx < 0:
        log("⚠️ 未在装配产物中定位到「角色定义」段标记——frontmatter 键补偿跳过")
        return prompt
    start = prompt.find("\n---\n", idx)
    if start < 0:
        log("⚠️ 未在装配产物中定位到 frontmatter 起始符——frontmatter 键补偿跳过")
        return prompt
    start += 1                                   # 指向 "---"
    close = prompt.find("\n---\n", start + 4)
    if close < 0:
        log("⚠️ 未在装配产物中定位到 frontmatter 闭合符——frontmatter 键补偿跳过")
        return prompt
    block_end = close + 4                        # 指向闭合 "---" 之后的换行符
    return prompt[:start] + _render_fm_block(fm_map, core_fm, member_id) + prompt[block_end:]


def insert_domain_section(prompt: str, domain_text: str) -> str:
    """把「域上下文」段插入到「角色定义」段之后、「任务包」段之前。"""
    pos = prompt.find(ROLE_END)
    if pos < 0:
        log("⚠️ 未在装配产物中定位到「角色定义结束」标记——域上下文追加到末尾")
        return prompt.rstrip("\n") + "\n\n" + domain_text.rstrip("\n") + "\n"
    at = pos + len(ROLE_END)
    # prompt[at] 是行尾换行；插入后格式：标记行 / 空行 / 域上下文 / 空行 / 下一段
    return (prompt[:at] + "\n\n" + domain_text.strip("\n") + "\n\n"
            + prompt[at + 1:].lstrip("\n"))


# ───────────────────────────────────────────────── CLI
def main() -> int:
    core = _load_core()
    ap = argparse.ArgumentParser(
        description="成员 spawn 人设装配器（本包版）：成员 MD + 域上下文 + 资源路径 + task_payload")
    ap.add_argument("--expert-dir", default=None, help="专家包根目录（默认：本包位置反推）")
    ap.add_argument("--member", help="成员 Agent ID（MD 文件名，不含 .md）")
    ap.add_argument("--task-file", help="任务包文本文件路径（推荐）")
    ap.add_argument("--phase", type=int, help="阶段号")
    ap.add_argument("--task-id", help="任务 ID")
    ap.add_argument("--out", help="输出到文件（默认 stdout）")
    ap.add_argument("--check-task-package", action="store_true",
                    help="校验任务包四要素齐全，缺则 exit 4")
    ap.add_argument("--run-dir", default=None,
                    help="本轮运行目录（产出落盘契约；同时用于自动发现 _collapse/ 产物）")
    ap.add_argument("--workspace", default=None,
                    help="工作区（用于自动发现 <workspace>/.harness-runs/*/_collapse/ 产物）")
    ap.add_argument("--collapse-artifact", default=None,
                    help="坍缩产物路径（显式指定；缺省时按 --run-dir / --workspace 自动发现）")
    ap.add_argument("--domain-profile", default=None,
                    help=f"域档案路径（默认：本包 {DEFAULT_PROFILE_REL}）")
    ap.add_argument("--list-members", action="store_true", help="列出白名单成员 ID 后退出")
    args = ap.parse_args()

    expert_dir = core.resolve_expert_dir(args.expert_dir)
    plugin = core.load_plugin(expert_dir)
    member_ids = core.load_member_ids(plugin)
    # 主理人（leadAgent）不在 memberAgents 白名单里，但它的成员 MD 同样有 frontmatter
    # 与正文——本包装配器**允许**装配主理人（用于自检/复盘），
    # 但**不放进**下发给成员的「合法成员白名单」段（该段内容与 core 保持一致）。
    lead_id = str((plugin.get("teamInfo") or {}).get("leadAgent") or "")
    allowed_ids = list(member_ids) + ([lead_id] if lead_id and lead_id not in member_ids else [])

    if args.list_members:
        print("\n".join(member_ids))
        return 0

    if not args.member:
        log("❌ 缺少 --member（或用 --list-members 查看白名单）")
        return 3
    if args.member not in allowed_ids:
        log(f"❌ 成员 ID 不在白名单：{args.member}")
        log(f"   白名单（来自 plugin.json teamInfo.memberAgents）：{member_ids}")
        return 2

    md_text = core.load_member_md(expert_dir, args.member)
    fm_raw, body = parse_frontmatter_strict(md_text)
    fm_map = parse_fm_mapping(fm_raw)
    core_fm = {
        "name": str(fm_map.get("name") or args.member),
        "maxTurns": fm_map.get("maxTurns"),
        "skills": _skills_of(fm_map),
    }
    if not fm_raw.strip():
        log("⚠️ 成员 MD 的 frontmatter 未成功切分——按无 frontmatter 处理")

    task_text = None
    if args.task_file:
        tf = Path(args.task_file).expanduser()
        if not tf.is_file():
            log(f"❌ 任务包文件不存在：{tf}")
            return 3
        task_text = tf.read_text(encoding="utf-8")
        if args.check_task_package:
            ok, missing = core.check_task_package(task_text)
            if not ok:
                log(f"❌ 任务包缺要素：{missing}（四要素：{core.TASK_PACKAGE_FIELDS}）")
                return 4
            log("✅ 任务包四要素齐全")

    run_dir = None
    if args.run_dir:
        rd = Path(args.run_dir).expanduser().resolve()
        rd.mkdir(parents=True, exist_ok=True)
        run_dir = str(rd)
        log(f"✅ 运行目录就绪：{run_dir}")

    # ── 域档案 ────────────────────────────────────────────────
    profile_path = args.domain_profile or os.path.join(PKG, DEFAULT_PROFILE_REL)
    profiles, profile_err = load_profile(profile_path)
    fallback = {}
    if profiles is not None:
        fallback = _fallback_block(profiles)
    else:
        # 显式尝试包内默认档案取 fallback 段（仍取不到 → 硬失败，不静默）
        default_path = os.path.join(PKG, DEFAULT_PROFILE_REL)
        if os.path.abspath(default_path) != os.path.abspath(profile_path):
            dprof, derr = load_profile(default_path)
            if derr is None:
                fallback = _fallback_block(dprof)
                log(f"⚠️ 域档案不可读（{profile_err}）——通用兜底内容取自包内默认档案 {default_path}#fallback")
            else:
                log(f"❌ 域档案不可读（{profile_err}）；包内默认档案亦不可读（{derr}）")
        else:
            log(f"❌ 域档案不可读（{profile_err}）")

    # ── 坍缩产物 ──────────────────────────────────────────────
    artifact = None
    artifact_path = None
    state_note = ""
    if args.collapse_artifact:
        artifact_path = os.path.abspath(args.collapse_artifact)
        if not os.path.isfile(artifact_path):
            log(f"❌ 坍缩产物不存在：{artifact_path}")
            return 3
        artifact, err = read_collapse_artifact(artifact_path)
        if err:
            log(f"❌ {err}")
            return 3
    else:
        cands = discover_collapse_artifacts(run_dir, args.workspace)
        if cands:
            artifact_path, artifact, err = pick_collapse_artifact(cands)
            if err:
                log(f"❌ {err}")
                return 3
            log(f"ℹ️ 自动发现坍缩产物：{artifact_path}（候选 {len(cands)} 个）")
        else:
            log("ℹ️ 未发现坍缩产物（--run-dir / --workspace 下无 _collapse/*.json）")

    if artifact is not None:
        ok, state_note = _artifact_state(artifact)
        if ok:
            log(f"✅ 坍缩产物已确认生效：{artifact_path}（{state_note}）")
        else:
            log(f"⚠️ 域人格未生效（未确认）：{artifact_path}（{state_note}）——不注入域人格")
    else:
        state_note = "无坍缩产物"

    # ── 域档案定位（供域人格注入用）───────────────────────────
    domain = None
    if artifact is not None and profiles is not None:
        dom_id = artifact.get("domain_id")
        domain = find_domain(profiles, dom_id) if dom_id else None
        if domain is None and dom_id:
            log(f"⚠️ 域档案中找不到域 id={dom_id!r}——本条按通用兜底处理（严禁静默回落其它域）")

    domain_text, domain_status = build_domain_section(
        args.member, artifact, artifact_path, state_note, domain, fallback, profile_err)
    if domain_status == "fallback_profile_missing":
        log("⚠️ 域档案缺失——本条按通用兜底处理")
    elif domain_status == "fallback_unconfirmed":
        log("⚠️ 域人格未生效（未确认）——本次装配**不含**任何域人格内容")
    elif domain_status == "fallback_no_artifact":
        log("⚠️ 无坍缩产物——本次装配**不含**任何域人格内容")
    elif domain_status == "neutral_member":
        log(f"ℹ️ 成员 {args.member} 在本域为 domain_neutral——不注入域人格")

    # ── 装配 + 后处理 ─────────────────────────────────────────
    prompt = core.assemble(expert_dir, args.member, core_fm, body,
                           task_text, args.phase, args.task_id, run_dir, member_ids)
    prompt = enrich_frontmatter_block(prompt, fm_map, core_fm, args.member)
    prompt = insert_domain_section(prompt, domain_text)

    if args.out:
        Path(args.out).expanduser().write_text(prompt, encoding="utf-8")
        log(f"✅ 已写入：{args.out}（{len(prompt)} 字符）")
    else:
        print(prompt)

    log(f"✅ 装配完成：member={args.member} | expert_dir={expert_dir} "
        f"| domain_context={domain_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

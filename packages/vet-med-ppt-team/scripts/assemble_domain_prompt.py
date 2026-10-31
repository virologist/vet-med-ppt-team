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
CARRIER_BEGIN = "==================== 洞察载体（v3.21.0 多专家单载体） ===================="
CARRIER_END = "==================== 洞察载体结束 ===================="


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
def _kb_is_user_default(k) -> bool:
    """`is_user_default` 的宽松布尔判定（YAML 三形态：true / "true" / 1）。

    ⚠ **双胞注意**：`harness.py::_is_user_default_kb` 是**同口径**的另一份实现
      （快照层排序用）。为什么复制而不 import：装配器与编排内核是两个 CLI 入口，
      相互 import 会把 7000 行的 CLI 模块拖进装配进程；
      本包的既有先例是「复制 + 用守卫盯漂移」（见 ensure_settings.py 的
      `_md_exclusion_clauses`，它与 test_arch_drift 的同名函数一样是复制件）。
      ⇒ 漂移由 `scripts/test_c4_key_wiring.py` 的一致性用例盯住。
    """
    v = (k or {}).get("is_user_default")
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "on", "1")
    return bool(v)


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
    """渲染通用兜底段（不含任何域专有信息）。

    ⚠ **v3.28.2 修正**：`generic_persona` 缺失时**不得输出空壳标题**——
      首版实现在读取 `gp` 之前就无条件 append 标题行 ⇒ config 精简掉该键时
      产物出现只有标题没有内容的空壳段（「看起来有、实际没有」的半截渲染，
      与本包「不得出现与『无库』并列的半句话」同一病灶族）。
      现改为：**任一子键有内容才渲染对应段**；全空 ⇒ 整段省略。
    """
    lines = []
    gp = fb.get("generic_persona") or {}
    if any(gp.get(k) for k in ("title", "background", "stance", "duty_boundary")):
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

    # ── v3.18.0：专家面板分段注入（坍缩出**多名**资深专家）────────────
    # 规格原文：「依据输入的 PPT 或指定主题/模块（如禽流感→禽流感病毒学家+禽病学家）
    #   **动态坍缩生成匹配的资深专家团队**」——此前只有单个 role_persona，
    #   「专家团」在注入层不存在。这里按**子专家**逐人一段，
    #   成员据此知道自己此刻扮演哪几位专家、各自负责哪块、边界在哪。
    # 向后兼容：selected_experts 为空时（本包自建域档案无面板）→ 本段不出现，
    #   装配产物与 v3.17.0 逐字节一致。
    experts = artifact.get("selected_experts") or []
    if experts:
        lines.append("")
        lines.append(f"【一之二、专家面板（本次坍缩选中的 {len(experts)} 位资深专家）】")
        lines.append("你此刻是以下几位专家的**合体**：各人分管一块，"
                     "遇跨专业的判断按各自职责边界协作，**不越界替他人下结论**。")
        for i, ex in enumerate(experts, 1):
            if not isinstance(ex, dict):
                continue
            lines.append("")
            lines.append(f"▍专家 {i}：{ex.get('title') or ex.get('id') or '未命名专家'}"
                         f"（id={ex.get('id') or '-'}）")
            if ex.get("background"):
                lines.append(f"  - 背景：{ex['background']}")
            if ex.get("stance"):
                lines.append(f"  - 立场：{ex['stance']}")
            if ex.get("duties"):
                lines.append("  - 职责：")
                lines += _bullets(ex.get("duties"), "    - ")
            if ex.get("duty_boundary"):
                lines.append(f"  - 职责边界：{ex['duty_boundary']}")
            if ex.get("coverage_axes"):
                lines.append("  - 覆盖知识轴："
                             + "、".join(str(x) for x in ex.get("coverage_axes")))

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
        # ── v3.18.0（D-1）：机构权威源**实端点**注入 ──────────────────
        # 缺陷（2026-10-25 从零诊断 D-1 实测）：此前渲染 evidence_hierarchy 时
        #   只挑 5 个子键（institutional/literature/axes_note/time_layers/dual_source_rule），
        #   `institutional_endpoints`（MSD 兽医手册 / WOAH 陆生法典与手册 / WOAH 疾病卡 /
        #   FAO 动物卫生 / WHO 人畜共患 等**实测可达端点**）**被丢弃**——
        #   实跑 grep 装配产物：msdvetmanual|woah.org|fao.org 命中数 = **0**。
        #   ⇒ 成员只拿到机构**名称**，只能盲搜网页，**恰好违反同文件
        #     institutional_endpoints_note 自立的纪律**（"机构轴 = 端点直达，不得盲搜网页"）。
        # 本段把端点逐条注入（并连带 note / license_rule / retrieval_patterns）。
        inst_eps = ev.get("institutional_endpoints") or []
        if inst_eps:
            lines.append("")
            lines.append("【三之二、机构权威源实端点（**端点直达，不得盲搜网页**）】")
            for ep in inst_eps:
                if not isinstance(ep, dict):
                    lines.append(f"  - {ep}")
                    continue
                lines.append(f"  - {ep.get('name') or '(未命名机构源)'}")
                if ep.get("role"):
                    lines.append(f"    - 定位：{ep['role']}")
                if ep.get("status"):
                    lines.append(f"    - 状态：{ep['status']}")
                if ep.get("endpoint"):
                    lines.append(f"    - 端点：{ep['endpoint']}")
                if ep.get("retrieval_patterns"):
                    lines.append("    - 检索式：")
                    lines += _bullets(ep.get("retrieval_patterns"), "      - ")
                if ep.get("note"):
                    lines.append(f"    - 说明：{ep['note']}")
                if ep.get("license_rule"):
                    lines.append(f"    - 许可规则：{ep['license_rule']}")
            if ev.get("institutional_endpoints_note"):
                lines.append(f"  - 纪律：{ev['institutional_endpoints_note']}")

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
        # ── v3.28.2·C1：补渲染「图片科学性归属」（此前配了未渲染）────────
        #   用途：划清「图片**内容**科学性由谁负责」与「标注/版式由谁负责」
        #   ⇒ 缺它 ⇒ 内容专家与视觉设计成员互相等对方兜底（责任真空）。
        if ic.get("image_science_ownership"):
            lines.append(f"- 科学性归属：{ic['image_science_ownership']}")
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
        # ── v3.18.0（G4）：图注要素 = 通用骨架 + 域扩展 ──────────────
        # 通用骨架（域无关·唯一源）= config/visual-rules.yaml#caption_base_elements
        # 域扩展（域专属）= 域档案 image_channel.caption_extra_elements
        # 缺陷（2026-10-25 从零诊断 G4）：图注要素此前**四套并存**且 rubric 自认冲突不调和
        #   ⇒ 成员拿到的判据随域而变，无统一底座。
        # 本段把骨架与扩展**同时**呈现，并显式标注二者角色，避免成员各写一套。
        if ic.get("caption_extra_elements"):
            lines.append("- 图注要素（**域扩展项**，通用骨架见 visual-rules.yaml#caption_base_elements）：")
            lines += _bullets(ic.get("caption_extra_elements"), "  - ")
        if ic.get("forbidden_sources"):
            lines.append("- 禁止来源：")
            lines += _bullets(ic.get("forbidden_sources"), "  - ")
        if ic.get("knowledge_channel_ref"):
            lines.append(f"- 知识通道说明：{ic['knowledge_channel_ref']}")

    # ── v3.19.1·S1：知识库路由渲染（修「本域无知识库」与「见 external-tools」同屏矛盾）──
    # 缺陷实测：v3.19.0 把库迁到 external-tools.yaml 后，坍缩快照仍从域档案取 ⇒ 恒空
    #   ⇒ 装配器渲染「本域无账号内知识库」，而同屏说明又写「见 external-tools.yaml」——
    #   **自相矛盾**，且与事实相反（animal-medicine 有 7 个库）。
    # 修复：快照层已改从唯一源取（harness.py::_domain_knowledge_bases），本段负责渲染，
    #   并把「无库」时的兜底说明改为**明确的通用兜底**（不再出现半句话）。
    kb = pick("knowledge_bases")
    # 本域库路由指针（**唯一源的哪个分节**）——驱动「有库/无库」两种说明的取舍：
    #   #knowledge_bases               ⇒ 本域**有**账号内库
    #   #domains_without_knowledge_bases ⇒ 本域**无**账号内库（声明即如此）
    _kb_ref = str(pick("knowledge_bases_ref") or "")
    _declares_no_kb = bool(_kb_ref) and "domains_without_knowledge_bases" in _kb_ref
    lines.append("【五、知识库路由（文本型，与取图通道并列）】")
    if kb:
        for k in kb:
            if isinstance(k, dict):
                nm = k.get("name") or ""
                kid = k.get("id") or ""
                when = k.get("when") or ""
                share = k.get("share_url") or ""
                scope = k.get("owner_scope") or ""
                line = f"- {nm}"
                # ── C4·键B-b 接线：标注「用户默认启用的库」─────────────────
                # 消费方：`external-tools.yaml#knowledge_bases[].is_user_default`
                #   （判定 helper 在 harness.py::_is_user_default_kb，快照层已按它
                #     稳定排序 = harness.py::_domain_knowledge_bases）。
                # 为什么渲染层还要再标一次（两个不同的可见性）：
                #   排序只决定"列在最前"，成员扫读时**看不出**那是默认库
                #   ⇒ 排序 ≠ 可见。标注紧跟库名，才让"默认"这件事**看得见**。
                # ⚠ 不做过滤：`owner_scope` 已独占过滤职责（harness.py 快照层），
                #   此处只做**标注**，不增删条目。
                if _kb_is_user_default(k):
                    line += " ★**用户默认启用的库**"
                line += (f"（id: {kid}）" if kid else "")
                line += (f" —— 何时用：{when}" if when else "")
                if scope:
                    line += f"；适用专业：{scope}"
                if share:
                    line += f"；导航：{share}"
                lines.append(line)
        # 更换提醒（口径与 external-tools.yaml#knowledge_bases[].replaceable 一致）
        if any(isinstance(k, dict) and k.get("replaceable") for k in kb):
            lines.append("- ⚠ 上述知识库**可由用户灵活选择与配置**（可替换/更新）——"
                         "若用户提供了自己的库，按用户指定的库检索，并**主动提示**替换与更新；"
                         "库路由唯一源：`config/external-tools.yaml#knowledge_bases`")
        # 有库时域说明可照登（它描述的正是"该库组仅某专业可用"，与有库同屏**不矛盾**）
        if domain and domain.get("knowledge_bases_note"):
            lines.append(f"- 说明：{domain['knowledge_bases_note']}")
    else:
        # 无库：必须说清**通用兜底**，不得再出现与「无库」并列的半句话
        _fallback = ""
        _reminder = ""          # ⚠ 必须先初始化：except 分支若走到则用不到，
        try:                    #   但未初始化会在异常路径触发 UnboundLocalError
            import yaml as _y
            _ext = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "config", "external-tools.yaml")
            with open(_ext, encoding="utf-8") as _f:
                _ed = _y.safe_load(_f) or {}
            for _d in (_ed.get("domains_without_knowledge_bases") or []):
                if isinstance(_d, dict) and _d.get("id") == (domain or {}).get("id"):
                    _fallback = str(_d.get("fallback") or "")
                    _reminder = str(_d.get("reminder") or "")
        except Exception:
            _fallback = ""
            _reminder = ""
        lines.append(f"- （本域无账号内知识库——通用兜底：{_fallback or '现查官方文档/制度原文'}；"
                     f"**严禁**静默回落其它域的知识库）")
        if _reminder:
            lines.append(f"- ⚠ {_reminder}")
        # ⚠ **同屏矛盾防护**（v3.19.1·S1 审计实测）：域说明（knowledge_bases_note）
        #   分两种语义——「该库组仅某专业可用」（**有库**语义）与
        #   「本域没有账号内知识库」（**无库**语义）。前者若与「本域无账号内知识库」
        #   同屏 ⇒ 成员看到"说没有库、又说有个库组"——**自相矛盾**。
        #   判据取域档案 knowledge_bases_ref（**声明式**，不靠字符串匹配）：
        #     · ref 指向 #domains_without_knowledge_bases ⇒ 本域**自述**无库
        #       ⇒ 其 note 正是无库语义，照登不矛盾；
        #     · ref 指向 #knowledge_bases（默认）⇒ 本域**应有**库却一条没装上
        #       ⇒ 这是**装载异常**，note 与「无库」同屏必矛盾 ⇒ 不照登，改为告警。
        if domain and domain.get("knowledge_bases_note"):
            if _declares_no_kb:
                lines.append(f"- 说明：{domain['knowledge_bases_note']}")
            else:
                lines.append("- ⚠ 装载异常：本域档案声明库路由来自 "
                             f"`{_kb_ref or 'config/external-tools.yaml#knowledge_bases'}`"
                             "（**本域应有账号内库**），但本次**一条库都没装上**——"
                             "请核对该唯一源的库清单与 owner_scope 归属；"
                             "在修复前按上方通用兜底执行，**严禁**静默回落其它域的库。")
    _kb_warn = pick("knowledge_bases_load_warning")
    if _kb_warn:
        lines.append(f"- ⚠ 装载告警：{_kb_warn}")

    # ── v3.21.1：深度出处 / 四层受众 / 模块模板 / 用户指定源策略 ────────
    # 这 4 段此前在 config/domain-profiles.yaml 里配了、但**从未进快照** ⇒
    # 装配产物里没有 ⇒ 成员拿不到"深度三档的出处"（= 该专业教学标准的要求用词，
    # 正是"用专业标准耦合 PPT 诊断"的落点）、四层受众差异、模块/页序模板、用户指定源策略。
    # 实测（AST）：这 4 个键在 scripts/ 里 0 处读取点。
    _dss = pick("depth_scale_source") or {}
    if isinstance(_dss, dict) and _dss:
        lines.append("【二之二、深度三档的出处（专业标准要求）】")
        if _dss.get("standard"):
            lines.append(f"- 专业标准：{_dss['standard']}")
        if _dss.get("core_course"):
            lines.append(f"- 核心课程：{_dss['core_course']}")
        if _dss.get("note"):
            lines.append(f"- 说明：{_dss['note']}")
        lines.append("- ⚠ 本页深度（了解/理解/掌握）**以此标准的用词为准**；"
                     "标准未覆盖处按通用三档，并显式标注「标准未覆盖」")

    _ap = pick("audience_profile") or {}
    if isinstance(_ap, dict) and _ap:
        lines.append("【二之三、受众分层（本域差异）】")
        for k in ("layer_notes", "data_requirements", "case_forms",
                  # ── v3.28.2·C1：补 interaction_forms（此前配了未渲染）──
                  "interaction_forms"):
            v = _ap.get(k)
            if isinstance(v, list) and v:
                lines.append(f"- {k}：")
                lines += _bullets(v)
        if _ap.get("job_context"):
            lines.append(f"- 岗位语境：{_ap['job_context']}")

    _cmt = pick("course_module_templates") or []
    if isinstance(_cmt, list) and _cmt:
        lines.append("【二之四、模块/页序模板（本域现成骨架）】")
        for tpl in _cmt:
            if not isinstance(tpl, dict):
                continue
            lines.append(f"- {tpl.get('title') or tpl.get('id')}"
                         + (f"（适用：{tpl['applies_to']}）" if tpl.get("applies_to") else ""))
            mods = tpl.get("modules") or []
            if mods:
                for m in mods:
                    if isinstance(m, dict):
                        lines.append(f"  · {m.get('name')}"
                                     + (f" —— {m.get('focus')}" if m.get("focus") else ""))
            if tpl.get("note"):
                lines.append(f"  ⚠ {tpl['note']}")
            # ── v3.28.2·C1：补渲染 sibling_architecture / trim_priority ──
            #   二者此前配了未渲染 ⇒ 成员拿不到「另一条课型架构」与「课时不足时
            #   先砍哪块」这两条裁剪判据 ⇒ 只能凭感觉砍，砍掉关键诊断链。
            if tpl.get("sibling_architecture"):
                lines.append(f"  · 并行课型架构：{tpl['sibling_architecture']}")
            if tpl.get("trim_priority"):
                lines.append(f"  · 裁剪优先级：{tpl['trim_priority']}")

    _uss = pick("user_supplied_sources") or {}
    if isinstance(_uss, dict) and _uss:
        lines.append("【二之五、用户指定源策略】")
        if _uss.get("intake_field"):
            lines.append(f"- 指定源登记处：{_uss['intake_field']}")
        for k, label in (("default_strategy", "优先级"),
                         ("conflict_rule", "冲突处置"),
                         ("traceability_rule", "可追溯要求"),
                         # ── v3.28.2·C1：补 inaccessible_rule（此前配了未渲染）──
                         #   它是**取不到源时怎么办**的唯一判据；缺它 ⇒ 成员可能
                         #   把取不到的内容**当成事实写进正式内容**（无据断言）。
                         ("inaccessible_rule", "取不到时")):
            if _uss.get(k):
                lines.append(f"- {label}：{_uss[k]}")

    term = pick("terminology")
    if term:
        lines.append("【六、术语规范】")
        lines += _bullets(term)

    # ── v3.19.1·S1：新增【六之二、交付语言与术语表】────────────────
    # 缺陷实测：v3.19.0 新增的 glossary（29/23/21 条）与 delivery_language
    #   **从未进快照、也从未被渲染** ⇒ 成员拿不到词条，"关键词汇首现补英文"落不了地。
    _gloss = pick("glossary") or []
    _lang = pick("delivery_language") or "zh-CN"
    # 语言规格唯一源指针：取坍缩快照的 language_profile_ref（**消费该键**，
    # 免得它成为"声明了却无人读"的死键）；旧产物缺该键 ⇒ 回落默认路径。
    _lp_ref = str(pick("language_profile_ref") or "config/language-profile.yaml")
    if _gloss or _lang:
        lines.append("【六之二、交付语言与术语表】")
        lines.append(f"- 交付语言：{_lang}"
                     + ("（PPT 默认中文）" if _lang == "zh-CN" else "（英语场景）"))
        lines.append(f"- 语言规格唯一源：`{_lp_ref}`"
                     "（英语场景判据、术语标注形态、英文场景中文保留项均在其中，**不在本文件复制**）")
        # ── v3.21.0 F4：把「英语场景判据」与「英文场景中文保留项」**真的注入** ──
        # 独立诊断实测（AST 读取点）：`english_allowed_when` / `english_minimum`
        #   此前 **0 处读取** —— 配置里有判据、装配器却没注入 ⇒ 成员看不到 ⇒
        #   "PPT 默认中文 / 关键词汇补英文 / 极少数场景做英语 PPT（留学生班）"
        #   这三条**只有配置声明、没有执行面**。
        # 这里从**唯一源** config/language-profile.yaml 读并渲染（不复制定义），
        # 判据的**执行**仍属会话层（成员按条款判断受众语言）——
        # 代码能做的是"确保成员看得见判据"，判据本身是语义判断。
        _lp_path = os.path.join(PKG, _lp_ref) if not os.path.isabs(_lp_ref) else _lp_ref
        try:
            import yaml as _yaml
            with open(_lp_path, encoding="utf-8") as _f:
                _lprof = _yaml.safe_load(_f) or {}
        except Exception as _e:
            _lprof = {}
            lines.append(f"- ⚠ 语言规格读取失败（{_e}）——英语场景判据**未注入**，"
                         "本轮按 zh-CN 默认中文执行（缺失即降级，不得静默当英语场景）")
        # ⚠ **判据单独成段**（v3.21.0 实测修的冲突）：
        #   【六之二、交付语言与术语表】段里以 `  - ` 缩进开头的行 = **术语词条**
        #   （scripts/test_collapse_domain_render.py#_glossary_items 按此数条目数，
        #   断言"实渲条数 == 域档案条数"）。若把判据也写成 `  - ` 放进该段，
        #   计数会多出几条 ⇒ **既有护栏失败**（实测 32 ≠ 29）。
        #   ⇒ 判据另起【六之三】段：既不污染词条段的口径，判据也照样注入。
        _eaw = _lprof.get("english_allowed_when")
        _emin = _lprof.get("english_minimum")
        if (isinstance(_eaw, list) and _eaw) or isinstance(_emin, dict):
            lines.append("【六之三、交付语言判据（英语场景）】")
        if isinstance(_eaw, list) and _eaw:
            lines.append("何时可做英语 PPT（仅此两种情形，其余一律中文）：")
            for _c in _eaw:
                if isinstance(_c, dict):
                    _fld = _c.get("field") or ""
                    _eq = _c.get("equals")
                    _tt = _c.get("truthy")
                    _cond = (f"{_fld} = {_eq}" if _eq is not None
                             else (f"{_fld} 为真" if _tt else str(_fld)))
                    lines.append(f"· 当 {_cond} → 允许英语 PPT"
                                 + (f"（{_c.get('note')}）" if _c.get("note") else ""))
        if isinstance(_emin, dict):
            _keep = _emin.get("keep_chinese_for")
            if isinstance(_keep, list) and _keep:
                lines.append("英语场景仍须保留中文锚点（不得只出英文）："
                             + "、".join(str(x) for x in _keep))
            if _emin.get("note"):
                lines.append(f"· 理由：{_emin['note']}")
        if _gloss:
            # ── 渲染**全部**词条：一条不可省（成员靠它标注术语）──────────
            # 缺陷（v3.19.1·S1 审计实测）：此前只渲染 dict 形态（zh/en/abbr），
            #   域档案 glossary 里的**字符串形态**条目被 `continue` 静默丢弃
            #   （animal-medicine 29 条里丢 4 条）⇒ 产物标题写「29 条」、
            #   实际只列 25 条——**自称条数与实渲条数不符**，与本批修的
            #   「自相矛盾」同属一类病。故此处：dict → 中英形态；字符串 → 原样列出。
            _items = []
            for _g in _gloss:
                if isinstance(_g, dict):
                    _zh = str(_g.get("zh") or "")
                    _en = str(_g.get("en") or "")
                    _abbr = str(_g.get("abbr") or "")
                    if not _zh and not _en:
                        # 两个名都缺 ⇒ 仍是**一条**内容，原样列出（不静默丢）
                        _items.append(f"  - {_g}")
                        continue
                    if not _en:
                        _form = _zh
                    elif not _zh:
                        _form = _en + (f"（{_abbr}）" if _abbr else "")
                    else:
                        # 规格形态：中文（English, Abbreviation）；abbr 为空则中文（English）
                        _form = f"{_zh}（{_en}" + (f", {_abbr}" if _abbr else "") + "）"
                    _items.append(f"  - {_form}")
                else:
                    # 字符串形态条目（域档案里的规范行）：原样列出，不丢
                    _items.append(f"  - {_g}")
            # 条数按**实渲**数写（不再自称一个与实际不符的数）
            lines.append(f"- 本域术语表（{len(_items)} 条，**首现补英文**，一条不可省）：")
            lines += _items

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


def _carrier_axis_for_member(member_id: str):
    """从 config/harness.yaml#insight_carrier.axes 反查本成员对应的轴。

    为什么反查而不是写死：轴↔成员映射是**编排参数**（唯一源 = harness.yaml），
    装配器硬编码成员名 = 第二份真相 ⇒ 改配置不改行为（本包反复治理的同型缺陷）。
    读不到 ⇒ 返回 None，并在注入段里显式说明"未登记本成员的轴"（不静默不注入）。
    """
    p = os.path.join(PKG, "config", "harness.yaml")
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        log(f"⚠️ 读 harness.yaml 失败（{e}）——无法反查成员轴")
        return None
    axes = ((cfg.get("insight_carrier") or {}).get("axes") or {})
    for axis, mem in axes.items():
        if str(mem) == str(member_id):
            return str(axis)
    return None


def _render_carrier_context(member_id: str, run_dir: str) -> str:
    """渲染「洞察载体」注入段（v3.21.0）。

    为什么必须注入（而不是只写进成员 MD）：**人设不注入，规范就不会被遵守**
    ——这是域人格注入的既有教训（v3.17.0：装配产物里域人格关键词命中数为 0）。
    载体写入契约若只存在于 MD 里，成员看不到就等于没有。
    """
    lines = [CARRIER_BEGIN]
    axis = _carrier_axis_for_member(member_id)
    if not axis:
        lines.append("ℹ️ 未在 `config/harness.yaml#insight_carrier.axes` 登记本成员的轴——"
                     "本次**不注入**载体写入契约（该成员不参与载体条目，或映射待登记）。")
        lines.append(CARRIER_END)
        return "\n".join(lines)
    run = run_dir or "<RUN_DIR>"
    lines.append(f"【本成员轴】{axis}（成员 {member_id}）")
    lines.append(f"【载体文件】{os.path.join(run, '_insights', 'carrier.json')}（**主理人合并后写，你不要直接改**）")
    lines.append(f"【你的分片】{os.path.join(run, '_insights', 'parts', f'{member_id}__{axis}.json')}")
    lines.append("【为什么要写】同一目标上的内容/教学/视觉建议原本散落三处 ⇒ 冲突无处显形、"
                 "合并丢信息、追溯断裂。载体是全程唯一事实源（轮报/冻结/验收都从它投影）。")
    lines.append("【分片结构】")
    lines.append('{"task_id":"...","member":"%s","axis":"%s","round":1,' % (member_id, axis))
    lines.append(' "entries":[{"insight_id":"<target>-<轴首字母>-<两位序号>","target_id":"<s12 或模块id>",')
    lines.append('   "target_kind":"page|module","axis":"%s","expert":"%s",' % (axis, member_id))
    lines.append('   "proposal":"……具体改什么（必填，可执行到动作级；禁"整体优化"这类无定位表述）",')
    lines.append('   "rationale":"……依据（必填）","severity":"P0|P1|P2","status":"proposed"%s}]}'
                 % (',"evidence":"PMID/DOI 或 文件:行号"' if axis == "content" else ""))
    lines.append("【必填字段】insight_id / target_id / target_kind / axis / expert / proposal / "
                 "rationale / severity / status"
                 + ("；**evidence 内容轴必填**（内容轴洞察必须可溯源）" if axis == "content" else ""))
    lines.append("【两条纪律】① **只写自己轴**：同一目标上其他轴的条目由别人写，"
                 "你不得改别人的分片，也不得直接改载体；同轴内不重复做（防重复劳动），"
                 "同一目标上多轴并存是正常的（合起来才是完整洞察）。")
    lines.append("② **专业产物照旧落盘**（你的证据包/蓝图/检索单）：载体是**洞察的汇入通道**，"
                 "不取代你的产物——产物=「我这轴做了什么」，载体=「我提了哪些条目」。")
    lines.append("【合并由主理人做】`harness.py insights add --part <你的分片>`；"
                 "若 insight_id 与已有条目重复 ⇒ 报错且**不静默覆盖**（两版都留痕等裁决）。")
    lines.append(CARRIER_END)
    return "\n".join(lines)


def insert_carrier_section(prompt: str, carrier_text: str) -> str:
    """把「洞察载体」段插入到「域上下文结束」标记之后。"""
    pos = prompt.find(DOMAIN_END)
    if pos < 0:
        log("⚠️ 未在装配产物中定位到「域上下文结束」标记——载体段追加到末尾")
        return prompt.rstrip("\n") + "\n\n" + carrier_text.rstrip("\n") + "\n"
    at = pos + len(DOMAIN_END)
    return (prompt[:at] + "\n\n" + carrier_text.strip("\n") + "\n\n"
            + prompt[at + 1:].lstrip("\n"))


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
    ap.add_argument("--require-confirmed", dest="require_confirmed",
                    action="store_true", default=True,
                    help="（默认开启）坍缩产物未确认时**拒绝装配并 exit 5**——"
                         "落实「坍缩结果须经用户确认后方可生效」")
    ap.add_argument("--allow-unconfirmed", dest="require_confirmed",
                    action="store_false",
                    help="逃生口：允许在未确认态装配（仅通用兜底人设，无域人格）。"
                         "输出会显式标注降级；生产流程禁用")
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

    # ── v3.18.0：未确认态**阻断装配**（落实「坍缩结果经确认后方可生效」）──
    # 缺陷（2026-10-25 从零诊断 G2，实测复现）：此前未确认只打警告、仍 `return 0`，
    #   装配器写出完整 spawn prompt（实测 24212 字符）⇒「未确认照样能 spawn」，
    #   且 `test_spawn_injection.py` 里名为 `..._is_blocked` 的用例实际断言 `rc == 0`。
    #   即规格「经用户确认后方可生效」在**执行层**没有任何强制点。
    # 本段把「不注入域人格」升级为「不产出装配产物」：
    #   · 阻断条件 = 坍缩产物存在但未确认（fallback_unconfirmed）
    #     ——无产物（fallback_no_artifact）不阻断：那是"尚未坍缩"，由主理人走 route/confirm 流程；
    #   · 逃生口 = `--allow-unconfirmed`（显式声明降级，输出带告警）；
    #   · 退出码 5 = 域未确认（与 harness.yaml#gate_exit_codes 的 0-4 语义不冲突，5 为新语义）。
    if args.require_confirmed and domain_status == "fallback_unconfirmed":
        print("", file=sys.stderr)
        print("⛔ 拒绝装配：坍缩产物未确认（域人格未生效）", file=sys.stderr)
        print(f"   产物：{artifact_path}", file=sys.stderr)
        print(f"   状态：{state_note}", file=sys.stderr)
        if artifact:
            print(f"   域 id：{artifact.get('domain_id')!r}"
                  f"｜域人格称号：{(artifact.get('role_persona') or {}).get('title')!r}",
                  file=sys.stderr)
        print("   → 规格要求「坍缩结果须先输出并与用户对齐、经确认后方可生效」。", file=sys.stderr)
        print("   → 处置：① `harness.py collapse show` 输出坍缩摘要给用户裁决；"
              "② 用户确认后 `harness.py collapse confirm --id <域id> --task-id <tid> --rationale \"...\"`；"
              "③ 重新装配。", file=sys.stderr)
        print("   → 确实需要先跑通用兜底（明知未确认仍要装）：加 `--allow-unconfirmed`（输出会标注降级）。",
              file=sys.stderr)
        return 5

    # ── 装配 + 后处理 ─────────────────────────────────────────
    prompt = core.assemble(expert_dir, args.member, core_fm, body,
                           task_text, args.phase, args.task_id, run_dir, member_ids)
    prompt = enrich_frontmatter_block(prompt, fm_map, core_fm, args.member)
    prompt = insert_domain_section(prompt, domain_text)
    # v3.21.0：洞察载体写入契约注入（载体段紧随域上下文段，人设不注入规范就不会被遵守）
    prompt = insert_carrier_section(prompt, _render_carrier_context(args.member, run_dir))

    # ── v3.22.0 G7：装配体量分段表 + 超阈值告警（不裁剪，决策归人）────────
    # 病灶（第二轮独立诊断 P7，实测）：装配产物实测 **71,543 字符**——
    #   `context.summary_max_chars: 800` 只管**回传摘要**，管不到**注入体量**；
    #   而注入是逐版叠加的（域上下文八段 + 载体段 + 语言判据 + 深度/受众/模块/指定源四段…）
    #   ⇒ 关键纪律有被中后段稀释的风险（成员对超长 prompt 的注意力衰减）。
    # ⇒ 这里**只报体量与分段占比**，并超阈值时告警——**不自动裁剪**：
    #   裁哪段是内容决策（哪段对本次任务更重要），归主理人。
    _segs = []
    for _name, _beg, _end in (("角色定义", ROLE_BEGIN, ROLE_END),
                              ("域上下文", DOMAIN_BEGIN, DOMAIN_END),
                              ("洞察载体", CARRIER_BEGIN, CARRIER_END)):
        _i = prompt.find(_beg)
        if _i < 0:
            continue
        _j = prompt.find(_end, _i)
        if _j < 0:
            continue
        _segs.append((_name, _j - _i))
    _other = len(prompt) - sum(x[1] for x in _segs)
    _segs.append(("其他（任务包/资源清单/域上下文各子段）", _other))
    _tot = len(prompt)
    _warn_at = 60000
    log("📏 装配体量分段（占总字符 %）：" + " · ".join(
        f"{n} {v/(_tot or 1)*100:.0f}%" for n, v in _segs))
    if _tot > _warn_at:
        print(f"⚠ 装配产物 {_tot} 字符，超过告警阈值 {_warn_at}——"
              f"注入体量逐版叠加，成员对超长 prompt 的注意力会衰减。"
              f"分段占比见上方 📏 行。\n"
              f"   → **本工具不自动裁剪**：裁哪段属内容决策（哪段对本次任务更重要），"
              f"请主理人按分段占比决定保留什么，或把该段下沉到 references/ 按需读取。",
              file=sys.stderr)

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

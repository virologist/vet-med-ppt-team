#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成员 spawn 人设装配器（确定性工程 · 联邦共享件 shared-core）
==================================================
⚠ shared-core 归属声明（v3.4.1 R9，2026-10-14）：
    本文件是 6 个专家包的公共实现真源（单一维护点）。
    4 个无差异包（vet-med-ppt-team / research-orchestration-team /
    smart-textbook-team / triz-invention-team）的 scripts/assemble_spawn_prompt.py
    已改为兼容 shim 转调本文件；viral-evo-lab 为定制版（公共版 + V1 数字核验增量），
    独立维护但头部注明来源。
    修改本文件 = 同时影响 4 包行为，改前先跑各包 --list-members 基线对比。
    维护纪律：改公共逻辑必须所有引用包同受益；包私有需求走各包增量，不回染本文件。

用途：把「成员 MD 人设 + 技能资源绝对路径 + task_payload + 输出契约」确定性地
拼装成一份可直接作为 Agent 工具 prompt 的 spawn 文案，供主理人下发。

为什么要这个脚本：
    WorkBuddy 平台在 TeamCreate + Agent(name=成员ID) 时**不会**自动把
    agents/<member>.md 注入被 spawn 的 teammate（实测：团队配置文件中
    agentType=general-purpose，prompt 仅含主理人下发内容）。
    因此「成员专业产出」必须由主理人显式注入人设。手工复制 MD 易漏、易旧，
    交给脚本做确定性装配 + 白名单校验。

边界（严格守）：
    本脚本只做「结构拼装 / 路径解析 / 白名单校验」这类确定性工作；
    「派谁 / 任务怎么写 / 产出是否合格」仍是 LLM 与人的判断，脚本不介入。

用法：
    # 1. 只装配人设骨架（主理人自己补任务段）
    python3 assemble_spawn_prompt.py --member contradiction-analyst

    # 2. 装配人设 + 任务段（推荐，一次成型）
    python3 assemble_spawn_prompt.py --member contradiction-analyst \
        --phase 2 --task-id T-20260929-001 --task-file /tmp/phase2_task.md

    # 3. 同时校验任务包四要素是否齐全
    python3 assemble_spawn_prompt.py --member contradiction-analyst \
        --task-file /tmp/phase2_task.md --check-task-package

    # 4. 列出本团队全部合法成员 ID（路由白名单）
    python3 assemble_spawn_prompt.py --list-members

    # 5. 写到文件（长 prompt 建议落盘后再由主理人粘贴/引用）
    python3 assemble_spawn_prompt.py --member contradiction-analyst --out /tmp/spawn.md

退出码：
    0 = 成功；2 = 成员 ID 不在白名单；3 = 文件缺失；4 = 任务包要素缺失
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

LOG_PREFIX = "[assemble_spawn_prompt]"

# 任务包四要素（Anthropic 委派协议；缺一即补齐再 spawn）
TASK_PACKAGE_FIELDS = ["objective", "output_format", "constraints", "task_boundary"]


def log(msg: str) -> None:
    """统一日志输出到 stderr，避免污染 stdout 的 prompt 正文。"""
    print(f"{LOG_PREFIX} {msg}", file=sys.stderr)


# ---------------------------------------------------------------- 路径与元数据

def resolve_expert_dir(explicit: str | None) -> Path:
    """
    解析专家包根目录。
    优先级：命令行显式传入 > 脚本文件位置反推（scripts/ 的上两级）> 环境变量。
    禁止猜测：三者都拿不到就报错退出，绝不用相对路径硬编码。
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            log(f"❌ 传入的专家包目录不存在：{p}")
            sys.exit(3)
        return p

    env = os.environ.get("EXPERT_DIR")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
        log(f"⚠️ 环境变量 EXPERT_DIR 指向的目录不存在，回退脚本位置反推：{env}")

    inferred = Path(__file__).resolve().parent.parent
    if (inferred / "agents").is_dir():
        return inferred

    log("❌ 无法解析专家包目录。请用 --expert-dir 显式传入。")
    sys.exit(3)


def load_plugin(expert_dir: Path) -> dict:
    """读取 plugin.json（权威元数据：成员白名单、技能清单）。"""
    candidates = [
        expert_dir / ".codebuddy-plugin" / "plugin.json",
        expert_dir / ".claude-plugin" / "plugin.json",
        expert_dir / "plugin.json",
    ]
    for c in candidates:
        if c.is_file():
            try:
                return json.loads(c.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log(f"❌ plugin.json 解析失败：{c} -> {e}")
                sys.exit(3)
    log(f"❌ 未找到 plugin.json， searched: {[str(c) for c in candidates]}")
    sys.exit(3)


def load_member_ids(plugin: dict) -> list[str]:
    """从 plugin.json 提取成员白名单（teamInfo.memberAgents 优先，回退 members）。"""
    team_info = plugin.get("teamInfo") or {}
    ids = list(team_info.get("memberAgents") or [])
    if not ids:
        ids = [m.get("id") for m in plugin.get("members", []) if m.get("id")]
    return [i for i in ids if i]


# ---------------------------------------------------------------- 动态成员层

def load_dynamic_members(work_root: str | None) -> dict[str, dict]:
    """读取 WORK_ROOT 级动态成员注册表（运行态/dynamic-members.yaml）。

    返回 {member_id: entry}；注册表不存在 → 空表（动态层是可选能力，缺失不是错误）。
    **闸门（安全关键）**：只收录 `confirmed_by_user: true` 的条目——
    未过用户闸门的提案成员绝不允许进入 spawn 白名单（team-generation skill §1）。
    解析顺序依赖安全：先判确认标志、后收成员（2026-10-30 首版状态机解析器有顺序 bug
    导致闸门失效，已改用「解析全量 + 按标志过滤」的确定性两段式）。
    """
    if not work_root:
        return {}
    reg = Path(work_root) / "运行态" / "dynamic-members.yaml"
    if not reg.is_file():
        return {}
    text = reg.read_text(encoding="utf-8")

    confirmed = False
    m = re.search(r"^confirmed_by_user\s*:\s*(\S+)", text, re.M)
    if m:
        confirmed = m.group(1).lower() in ("true", "yes", "1")
    if not confirmed:
        log("⛔ 动态成员注册表 confirmed_by_user 非 true —— 未过用户闸门，动态层不生效")
        return {}

    members: dict[str, dict] = {}
    try:
        import yaml  # PyYAML；缺失时降级为「拒收整个动态层」而不是半解析
        data = yaml.safe_load(text)
    except ImportError:
        log("⛔ PyYAML 不可用，无法安全解析动态成员注册表 —— 动态层不生效（宁可拒绝不猜）")
        return {}
    except Exception as e:
        log(f"⚠️ 动态成员注册表解析失败（按空表处理）：{e}")
        return {}

    if not isinstance(data, dict):
        log("⚠️ 注册表顶层不是映射，按空表处理")
        return {}
    for entry in data.get("members") or []:
        if not isinstance(entry, dict):
            continue
        mid = entry.get("member_id")
        if not mid or not re.fullmatch(r"[a-z0-9\-]+", str(mid)):
            log(f"⚠️ 跳过非法 member_id: {mid!r}（须 kebab-case）")
            continue
        members[str(mid)] = entry
    return members


def build_dynamic_member_md(entry: dict, member_id: str) -> str:
    """由注册表条目即时合成动态成员的「角色定义 MD」（人设注入主体）。

    动态成员没有 agents/*.md 静态文件——这正是「运行时真生成」的实现方式：
    通用专家骨架 + 注册表声明的 role_name/domain/examines 合成完整角色定义。
    """
    role_name = entry.get("role_name", member_id)
    domain = entry.get("domain", "通用")
    examines = entry.get("examines", [])
    ex_lines = "\n".join(f"  - {e}" for e in examines) or "  - 术语精确性"
    return f"""---
name: {member_id}
version: 1.0.0
description: "动态生成专家成员：{role_name}（{domain}）。来源：运行时团队生成（skills/team-generation）。"
displayName:
  zh: "{role_name}"
---

# {role_name}（动态成员）

> 你是本团队按本章主题**运行时生成**的领域专家成员，聚焦知识域「{domain}」。
> 与常驻成员同责同权：受 harness 协议全量约束（boundary filter / token budget /
> 收尾三件套 / 落盘契约），产出仅限你的职责边界。

## 职责（examines——你盯什么）
{ex_lines}

## 输出要求
1. 产出以「{domain}」领域专家视角审读与撰写，术语与本学科 profile 的权威源一致
2. 遵守任务包的 output_format / constraints / task_boundary，缺任一要素回问主理人
3. 结论附证据位置；不确定处标 [待核实]，禁止编造
4. 不代行其他成员职责（尤其不代 quality-examiner 审查——生成者与审查者分离）

## 收尾三件套（强制）
结束时依次：① patch 黑板 ② `python3 scripts/record_trace.py ...` ③ `python3 scripts/progress.py update ...`
三项缺一 = 任务未完成。
"""


# ---------------------------------------------------------------- 成员 MD 解析

def load_member_md(expert_dir: Path, member_id: str) -> str:
    """读取成员 MD 全文（人设注入的主体）。"""
    md = expert_dir / "agents" / f"{member_id}.md"
    if not md.is_file():
        log(f"❌ 成员 MD 不存在：{md}")
        sys.exit(3)
    return md.read_text(encoding="utf-8")


def parse_frontmatter(md_text: str) -> tuple[dict, str]:
    """
    拆分 frontmatter 与正文。
    返回 (frontmatter_dict, body)。解析失败时 frontmatter 为空字典（不阻断）。
    """
    if not md_text.startswith("---"):
        return {}, md_text
    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return {}, md_text
    fm_raw, body = parts[1], parts[2]
    fm = {}
    # 极简 YAML 解析：只取本脚本关心的 key（name/skills/maxTurns/profession/displayName）
    for key in ("name", "maxTurns"):
        m = re.search(rf"^{key}:\s*(.+)$", fm_raw, re.M)
        if m:
            fm[key] = m.group(1).strip().strip('"')
    m = re.search(r"^skills:\s*\[(.+?)\]", fm_raw, re.M)
    if m:
        fm["skills"] = [s.strip().strip('"') for s in m.group(1).split(",")]
    return fm, body.lstrip("\n")


def resolve_skill_paths(expert_dir: Path, skills: list[str] | None) -> list[str]:
    """
    把 skills 名称解析为 references/skill 的绝对路径清单。
    只做路径解析（确定性），不做「该不该加载」的语义判断——那归成员自己按需。
    """
    if not skills:
        return []
    paths: list[str] = []
    for sk in skills:
        # 技能目录可能在 skills/<name>/ 下
        base = expert_dir / "skills" / sk
        if base.is_dir():
            paths.append(str(base / "SKILL.md"))
            ref_dir = base / "references"
            if ref_dir.is_dir():
                for f in sorted(ref_dir.rglob("*.md")):
                    paths.append(str(f))
        else:
            # 退化为 skills 根目录同级扫描（兼容扁平布局）
            for f in sorted((expert_dir / "skills").rglob(f"{sk}.md")):
                paths.append(str(f))
    # 去重保序
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_shared_refs(expert_dir: Path) -> list[str]:
    """收集专家包级共享资源（references/ config/ scripts/），供成员按需取用。"""
    out: list[str] = []
    for sub in ("references", "config"):
        d = expert_dir / sub
        if d.is_dir():
            for f in sorted(d.rglob("*")):
                if f.is_file() and f.suffix in (".md", ".yaml", ".yml", ".json"):
                    out.append(str(f))
    s = expert_dir / "scripts"
    if s.is_dir():
        for f in sorted(s.glob("*.py")):
            out.append(str(f))
    return out


# ---------------------------------------------------------------- 任务包校验

def check_task_package(task_text: str) -> tuple[bool, list[str]]:
    """
    校验任务包四要素是否齐全（objective / output_format / constraints / task_boundary）。
    这是**结构性校验**（字段存在性），属确定性范畴；内容质量由主理人判断。
    """
    low = task_text.lower()
    missing = [f for f in TASK_PACKAGE_FIELDS if f not in low]
    return (not missing), missing


def resolve_body_skills(expert_dir: Path, body: str) -> list[str]:
    """从成员 MD 正文提取 skills/<name>/SKILL.md 相对路径并解析为绝对路径。

    背景（P2-5, 2026-10-15，e2e-p1 真实运行实证）：各包成员把技能预加载声明写在
    【正文】（如 subject-writer「额外预加载skills（前置门禁）」），而 frontmatter
    均未声明 skills → resolve_skill_paths 恒为空，装配产物中技能只有相对路径，
    成员 spawn 后 cwd=WORK_ROOT 不可达，「前置门禁」实际不可执行。
    本函数补上正文声明这一来源；仅收录真实存在的文件（防御性：路径写错不注入死链）。
    """
    out: list[str] = []
    for m in re.finditer(r"skills/[\w\-]+/SKILL\.md", body or ""):
        rel = m.group(0)
        p = expert_dir / rel
        if p.is_file() and str(p) not in out:
            out.append(str(p))
    return out


# ---------------------------------------------------------------- 装配

def assemble(expert_dir: Path, member_id: str, fm: dict, body: str,
             task_text: str | None, phase: int | None,
             task_id: str | None, run_dir: str | None,
             member_ids: list[str] | None = None) -> str:
    """拼装最终 spawn prompt。结构固定，便于审计与 diff。"""
    skills = fm.get("skills") or []
    skill_paths = resolve_skill_paths(expert_dir, skills)
    # P2-5: 正文声明的技能路径（相对）解析为绝对路径注入——否则「前置门禁」不可达
    body_skill_paths = resolve_body_skills(expert_dir, body)
    for p in body_skill_paths:
        if p not in skill_paths:
            skill_paths.append(p)
    shared = resolve_shared_refs(expert_dir)

    lines: list[str] = []
    lines.append(f"你是下面这份角色定义所描述的专家。请完整代入该角色，严格遵守其输出规范与接口契约。")
    lines.append("")
    lines.append("=" * 20 + " 角色定义（专家包成员 MD 全文） " + "=" * 20)
    lines.append(f"---\nname: {fm.get('name', member_id)}")
    if skills:
        lines.append(f"skills: [{', '.join(skills)}]")
    if fm.get("maxTurns"):
        lines.append(f"maxTurns: {fm['maxTurns']}")
    lines.append("---")
    lines.append("")
    lines.append(body.rstrip())
    lines.append("=" * 20 + " 角色定义结束 " + "=" * 20)
    lines.append("")

    lines.append("【专家包资源绝对路径】（按需 Read，禁止猜测路径）")
    for p in skill_paths:
        lines.append(f"- {p}")
    for p in shared:
        lines.append(f"- {p}")
    lines.append("")

    if task_id or phase is not None:
        lines.append("【任务标识】")
        if task_id:
            lines.append(f"- task_id: {task_id}")
        if phase is not None:
            lines.append(f"- phase: {phase}")
        lines.append("")

    if task_text:
        lines.append("=" * 20 + " 任务包（task_payload） " + "=" * 20)
        lines.append(task_text.strip())
        lines.append("=" * 20 + " 任务包结束 " + "=" * 20)
        lines.append("")
    else:
        lines.append("【任务包】（主理人请在下方补全四要素后下发）")
        lines.append("- objective: <一句话目标>")
        lines.append("- output_format: <输出结构 + 回传 schema>")
        lines.append("- constraints: [<边界与红线>]")
        lines.append("- task_boundary: <做什么/不做什么/输入是什么>")
        lines.append("")

    # 合法下游白名单：防止成员在 next_agent_hint 里编造不存在的成员
    # （实测出现成员建议 solution-architect / prior-art / ip-strategist 等本团没有的角色）
    lines.append("【本团合法成员白名单】（next_agent_hint 只能从这里取值，禁止自创成员名）")
    for m in member_ids:
        mark = " ← 你" if m == member_id else ""
        lines.append(f"- {m}{mark}")
    lines.append("")

    lines.append("【回传要求·双通道】")
    if run_dir:
        artifact = f"{run_dir}/{task_id or 'T-UNKNOWN'}__{member_id}.md"
        lines.append(f"通道1（主·必须）：把完整产出写入文件 `{artifact}`。"
                     f"优先用 Write 工具；若无 Write 权限，改用 Bash heredoc "
                     f"（`cat > \"{artifact}\" << 'ARTEOF' ... ARTEOF`）。"
                     f"这是主理人读取产出的可靠通道。")
        lines.append("通道2（辅）：写完后用 SendMessage 给 team-lead 回传「一句话摘要 + 上述文件绝对路径」。")
        lines.append("⚠️ 严禁只 SendMessage 不落盘：实测中仅靠消息回传存在丢失风险，"
                     "主理人将按文件为准；文件缺失视为该成员本轮未交付。")
    else:
        lines.append("完成后用 SendMessage 把完整产出回传给 team-lead；"
                     "回传正文最前必须附上你角色定义中规定的上行信封 JSON。")
        lines.append("（提示：建议主理人用 --run-dir 启用落盘契约，回传更可靠）")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(
        description="成员 spawn 人设装配器：把成员 MD + 技能路径 + task_payload 拼成 spawn prompt")
    ap.add_argument("--expert-dir", default=None,
                    help="专家包根目录（默认：本脚本位置反推）")
    ap.add_argument("--member", help="成员 Agent ID（MD 文件名，不含 .md）")
    ap.add_argument("--task-file", help="任务包文本文件路径（推荐）")
    ap.add_argument("--phase", type=int, help="阶段号")
    ap.add_argument("--task-id", help="任务 ID，如 T-20260929-001")
    ap.add_argument("--out", help="输出到文件（默认 stdout）")
    ap.add_argument("--check-task-package", action="store_true",
                    help="校验任务包四要素齐全，缺则 exit 4")
    ap.add_argument("--run-dir", default=None,
                    help="本轮运行目录；传入后会在 prompt 中注入「产出落盘契约」"
                         "（成员必须把产出写入 <run-dir>/<task_id>__<member-id>.md）")
    ap.add_argument("--list-members", action="store_true",
                    help="列出白名单成员 ID 后退出")
    ap.add_argument("--work-root", default=None,
                    help="任务工作根目录（含 运行态/dynamic-members.yaml 时启用动态层）")
    ap.add_argument("--allow-dynamic-members", action="store_true",
                    help="允许把已确认的动态成员并入白名单（默认关闭，显式开启防误用）")
    args = ap.parse_args()

    expert_dir = resolve_expert_dir(args.expert_dir)
    plugin = load_plugin(expert_dir)
    member_ids = load_member_ids(plugin)

    # 动态层（须显式开启 + 注册表 confirmed_by_user: true）
    dynamic: dict[str, dict] = {}
    if args.allow_dynamic_members:
        dynamic = load_dynamic_members(args.work_root)
        for did in dynamic:
            if did not in member_ids:
                member_ids.append(did)
        if dynamic:
            log(f"✅ 动态层并入白名单 {len(dynamic)} 个：{sorted(dynamic)}")

    if args.list_members:
        print("\n".join(member_ids))
        return 0

    if not args.member:
        log("❌ 缺少 --member（或用 --list-members 查看白名单）")
        return 3

    # 确定性路由白名单校验：非法成员 ID 直接拒绝，不进入 spawn
    if args.member not in member_ids:
        log(f"❌ 成员 ID 不在白名单：{args.member}")
        log(f"   静态白名单（plugin.json teamInfo.memberAgents）：{load_member_ids(plugin)}")
        if dynamic:
            log(f"   动态白名单（已确认）：{sorted(dynamic)}")
        else:
            log("   动态层未启用（需 --allow-dynamic-members + --work-root + 注册表 confirmed_by_user: true）")
        return 2

    # 成员 MD：静态层读文件；动态层由注册表条目即时合成
    if args.member in dynamic:
        md_text = build_dynamic_member_md(dynamic[args.member], args.member)
        log(f"✅ 动态成员「{args.member}」角色定义已由注册表合成")
    else:
        md_text = load_member_md(expert_dir, args.member)
    fm, body = parse_frontmatter(md_text)

    task_text = None
    if args.task_file:
        tf = Path(args.task_file).expanduser()
        if not tf.is_file():
            log(f"❌ 任务包文件不存在：{tf}")
            return 3
        task_text = tf.read_text(encoding="utf-8")

        if args.check_task_package:
            ok, missing = check_task_package(task_text)
            if not ok:
                log(f"❌ 任务包缺要素：{missing}（四要素：{TASK_PACKAGE_FIELDS}）")
                return 4
            log(f"✅ 任务包四要素齐全")

    run_dir = None
    if args.run_dir:
        rd = Path(args.run_dir).expanduser().resolve()
        rd.mkdir(parents=True, exist_ok=True)   # 幂等建目录，成员只需写文件
        run_dir = str(rd)
        log(f"✅ 运行目录就绪：{run_dir}")

    prompt = assemble(expert_dir, args.member, fm, body,
                      task_text, args.phase, args.task_id, run_dir, member_ids)

    if args.out:
        Path(args.out).expanduser().write_text(prompt, encoding="utf-8")
        log(f"✅ 已写入：{args.out}（{len(prompt)} 字符）")
    else:
        print(prompt)

    log(f"✅ 装配完成：member={args.member} | expert_dir={expert_dir} "
        f"| skills={fm.get('skills') or []}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

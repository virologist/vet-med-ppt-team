#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harness.py — vet-med-ppt-team 编排内核（确定性工程层）v3.9.0

为什么要有这个文件（2026-09-29 基线实测教训）：
  1. 苏学法（pedagogy-architect）连 spawn 三次全部 `not available`，而现行规则
     "Agent 不可用＝任务阻断" → 整条流水线在阶段 3 停摆。纪律越严，缺降级越致命。
  2. 严真奥被平台登记为 `agentType=general-purpose`（成员 MD 未注入），平台不报错，
     主理人完全不知情 → 静默降级。
  3. 全程无执行日志、无预算计数、无耗时统计，A/B 无法对比。

v3.4.0（2026-10-14 专家团治理批）：
  + R1 doctor 子命令——LLM 友好"可发现性表"，一次返回所有 9 子命令的 usage/examples
  + R2 修 budget check 矛盾（kind=None 路径返回 0 退出而非 exceeded=true）
  + R3 修 trace report 死值（event='event' 标 + stage_seconds 空字典注释 + 4 缺失成员提示）
  + R5 spawn 子命令——主理人/脚本可显式 spawn 某 agent 写 trace
  + R6 token 估算字段（input_chars/output_chars）入 trace

v3.4.1（2026-10-14 待办收尾）：
  + R11 stage 子命令——主理人编排循环在每个闸切换时显式发 stage_enter/stage_exit，
    让 trace report 的 stage_seconds 真正有数（此前无入口发事件，字段恒空）；
    带孤儿 exit 防护（同 stage 无未闭合 enter 时警告，防 stage_seconds 静默丢失）

v3.4.2（2026-10-15 P0-P3 全量执行）：
  + P0-3 verify-ref 子命令——cases_library.json 文献引用预检（假 PMID 黑名单
    + 缺 verified_at 时间戳红线 + 格式预检），不依赖 PubMed 联网实检
  + P0-1 sweep 子命令——从 CHANGELOG v3.1.0 失落的"闸外收编"能力落地：递归扫
    全量 pptx → gate 收编 deck_registry（judge_provenance 保留）
  + P1-1 stage 工具采用闭环——主理人 MD 收尾步强制 stage_seconds 贴交付物
  + P1-2 member_return/degrade 事件——成员回传与降级落 trace
  + P1-4 trace report 增 token 汇总（按 actor 聚合 + 预算使用率）

v3.4.3（2026-10-15 采用迁移批，裁决=稳健核心10项）：
  + A1 堵 --event 死值源（trace log 漏写/显式死值一律 exit 2，v3.4.0 R3 只清了已生数据）
  + A2 verify-ref 增 --online（PubMed esearch 联网核验）+ --write-back（受控写回：
    门禁→.bak 备份→写回→复检）——消除 v3.4.2 P0-2 "脚本直写绕过 verify-ref" 旁路
  + E6 doctor 首跑归档；A3 eval 周期化（外部 automation 承接，不在本文件）

v3.5.0（2026-10-17 实战经验治理批）：
  + 迭代四原则抽象（骨架冻结/方向裁决/增量门禁/检出≠判定）——规则落在
    references/adjudication-rules.md 与 config/harness.yaml#delta_gate，本文件未改逻辑
  + 页数三口径（物理/可见/导出）落在 sop-stages.md#闸1；重复指令对账协议同处

v3.6.0（2026-10-17 迭代实战治理批）：
  + 迭代四原则扩为六原则，新增"插入物避让"（v6 流程条 +8、v7 图注 +5 处自引入重叠）
    与"素材判读红线"（v7 识图发现 5 张低清新闻图 + 1 张无预设病变）
  + harness.yaml#delta_gate 扩 insert_spatial_audit / insert_font_at_creation /
    image_caption_requires_reading / caption_missing_element_policy
  + OOXML 病例 13–14（GEO-003 空间冲突 / API-001 属性名凭记忆猜测）——登记未实现

v3.7.0（2026-10-17 诊断颗粒度升级批）：
  + 七维精准诊断双路由（量规唯一源=下游 skill teaching-ppt-studio/
    references/seven-dimension-rubric.md，本团只引路径不复制——防双源漂移）
  + 三级修复路由（大修/中修/细节修，按侵入性）与既有 A/B/C 三轨（按手段）正交
  + config/domain_config.yaml#ai_literacy 落维⑦ AI 融合与数智素养
  ⚠ 本批未改本文件任何逻辑；v3.5–v3.7 的变更全部落在 references/ 与 config/。
  ⚠ 本版同时修 P-1 版本对齐：docstring 与 doctor 自报版本从 v3.4.3 补齐到 v3.7.0
    （实证：v3.5–v3.7 三版推进时只改了 config/ 与 references/，本文件的版本段与
    doctor 常量被漏掉；且 .claude-plugin/plugin.json 也漏在 3.4.4——四处版本号各说各话）。
  机器背书：ensure_settings 第 14 项 check_version_consistency（版本号一致性巡检）。

v3.9.0（2026-10-22 双层 Loop 契约下沉批）：
  + loop 子命令——v3.8.x 把 loop_a/loop_b 写进 config、把五条指令与终止五类写进
    references/dual-loop-governance.md，但本文件从未含 loop 子命令，"逐轮停等""部分
    接受只冻点名条目""sha256 漂移即失效""沉默不推进"全是 Markdown 纪律。本次把可判定
    部分下沉为代码：start/intake/add-item/status/resume/continue/rework/freeze/
    verify/make-gate/block/terminate/check-path 共 13 个动作。
  + check-path 实现 loop_a.forbidden_paths 与 loop_a.scope 的写前越界校验
    （此前 dual-loop-governance §8 第 3 项自认"非代码级强制"）。
  + 机器背书：scripts/test_loop_state.py（33 例）与 ensure_settings 第 7 项
    （v3.9.0 起跑全部 test_*.py，此前只跑 test_harness.py，新增套件挂了体检看不见）。
  ⚠ 诚实边界：本段不判定条目内容的专业对错，也拦不住成员的实际写文件动作（平台无
    hook）——它校验的是"路径是否越界"与"状态推进是否合规"，不是沙箱，不得对外宣称
    "两环隔离已由代码强制"。

本脚本把"提示词里的纪律"下沉为"代码里的约束"，全部参数读 config/harness.yaml（禁硬编码）。
它只做确定性事务（路径解析 / 状态校验 / 计数 / 日志 / 进程调用），
不做任何语义判断（识别、匹配、权衡仍归 LLM 与主理人）。

用法（推荐先跑 `python3 scripts/harness.py doctor` 看可发现性表）：
    python3 scripts/harness.py doctor     # 所有子命令的 usage/examples/exit_codes
    python3 scripts/harness.py preflight  [--team <团队名>] [--workspace <路径>]
    python3 scripts/harness.py route      --level L0|L1|L2|L3
    python3 scripts/harness.py state init|get|set|validate  [--workspace <路径>] [--stage N] [--key K --value V]
    python3 scripts/harness.py budget check|spend|reset --kind spawn|react|rework [--n 1] [--workspace <路径>]
    python3 scripts/harness.py trace log|report  [--event E] [--actor A] [--detail D] [--workspace <路径>]
    python3 scripts/harness.py spawn     --agent <成员名> --task-id <id> [--stage N] [--input-bytes N] [--output-bytes N] [--workspace <路径>]
    python3 scripts/harness.py stage     --action enter|exit --stage 0-4 [--task-id <id>] [--note <备注>] [--workspace <路径>]
    python3 scripts/harness.py gate --deck <课件.pptx> [--hours 2] [--level P0|P1|all] [--workspace <路径>]
    python3 scripts/harness.py template-audit --root <课件根目录> [--json <出>] [--require-registered] [--workspace <路径>]
    python3 scripts/harness.py loop start|intake|add-item|status|resume|continue|rework|freeze|verify|make-gate|block|terminate|check-path [--loop a|b] [--workspace <路径>]

退出码：0=正常  1=存在需处置项（降级/预算超/状态非法）  2=用法错误  3=依赖缺失
"""

import argparse
import hashlib    # v3.9.0：Loop B 冻结/失效判定与原件只读核验的 sha256 证据
import json
import os
import re         # v3.9.0：两环目录越界校验的通配匹配
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
HARNESS_YAML = os.path.join(PKG, "config", "harness.yaml")
AGENTS_DIR = os.path.join(PKG, "agents")
TEAMS_DIR = os.path.expanduser("~/.workbuddy/teams")

# yaml 缺失时的兜底（与 harness.yaml 同值；仅用于不阻断运行，且必须打印告警）
_FALLBACK = {
    "stages": {str(i): {"members": [], "gate": "user_confirm"} for i in range(6)},
    "members": {},
    "routing": {},
    "fallback": {"max_spawn_attempts": 2, "on_unavailable": "degrade"},
    "budgets": {"max_member_spawns": 8, "max_spawn_attempts_per_member": 2,
                "max_react_rounds_per_gap": 3, "max_react_rounds_total": 15,
                "max_rework_rounds_per_stage": 2, "max_stage_minutes": 20,
                "max_artifact_bytes": 60000,
                # v3.3.0：闸4.5 三源核验预算
                "three_source_sample_rate": 0.1, "three_source_pass_threshold": 0.8},
    "context": {"handoff_mode": "path_only", "summary_max_chars": 800,
                "state_max_bytes": 32768, "state_allowed_keys": []},
    "observability": {"trace_file": ".workbuddy/harness_trace.jsonl"},
    "gate_exit_codes": {"0": "通过", "1": "P0 硬阻断", "2": "P1 阻断", "3": "P2 阻断",
                        "4": "运行错误", "5": "闸4.5 三源核验未达标（v3.3.0）"},
}


# ─────────────────────────── 配置加载 ───────────────────────────
def load_cfg():
    """读 config/harness.yaml；失败时回退内置值并显式告警（不再静默）。"""
    try:
        import yaml  # noqa
        with open(HARNESS_YAML, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            raise ValueError("harness.yaml 解析结果不是映射")
        # YAML 里 stages 的键会被解析成 int，统一成 str 便于与命令行/JSON 对照
        if isinstance(cfg.get("stages"), dict):
            cfg["stages"] = {str(k): v for k, v in cfg["stages"].items()}
        # 退出码键同理（YAML 里写成 0/1/2/3/4 会被解析成 int）
        if isinstance(cfg.get("gate_exit_codes"), dict):
            cfg["gate_exit_codes"] = {str(k): v for k, v in cfg["gate_exit_codes"].items()}
        return cfg, True
    except Exception as e:
        print(f"⚠ harness.yaml 加载失败（{e}）→ 回退内置值。"
              f"编排护栏已降级，请修复后再继续。", file=sys.stderr)
        return dict(_FALLBACK), False


def now_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def wkspace(args):
    return os.path.abspath(args.workspace or os.getcwd())


def state_path(w):
    p = os.path.join(w, ".workbuddy")
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, "task_state.json")


def trace_path(w, cfg):
    rel = cfg.get("observability", {}).get("trace_file", ".workbuddy/harness_trace.jsonl")
    p = os.path.join(w, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_state(w):
    sp = state_path(w)
    if not os.path.exists(sp):
        return {}
    try:
        with open(sp, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ task_state.json 解析失败（{e}），按空状态处理", file=sys.stderr)
        return {}


def write_state(w, st):
    with open(state_path(w), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# ─────────────────────────── preflight ───────────────────────────
def cmd_preflight(args):
    """开工前成员可用性预检：把"静默降级"变成"显式告警"。"""
    cfg, ok = load_cfg()
    members = cfg.get("members", {})
    fb = cfg.get("fallback", {})
    report = {"ts": now_iso(), "team": args.team, "members": {}, "verdict": "ok"}

    reg = {}
    if args.team:
        tp = os.path.join(TEAMS_DIR, args.team, "config.json")
        if os.path.exists(tp):
            try:
                with open(tp, encoding="utf-8") as f:
                    reg = {m["name"]: m for m in json.load(f).get("members", [])}
            except Exception as e:
                print(f"⚠ 团队配置读取失败（{e}）", file=sys.stderr)
        else:
            print(f"⚠ 未找到团队 {args.team} 的 config.json（尚未 TeamCreate？）", file=sys.stderr)

    for mid, spec in members.items():
        md = os.path.join(AGENTS_DIR, f"{mid}.md")
        item = {"md_exists": os.path.exists(md), "registered": mid in reg,
                "agent_type": reg.get(mid, {}).get("agentType"), "fallback": spec.get("fallback")}
        if not item["md_exists"]:
            item["status"] = "missing_md"
        elif reg and item["agent_type"] and item["agent_type"] != mid:
            # 关键：平台把成员回落成通用子代理 = 成员人格/红线未注入
            item["status"] = "degraded"
        elif reg and not item["registered"]:
            item["status"] = "not_spawned_yet"
        else:
            item["status"] = "ok"
        report["members"][mid] = item

    bad = [m for m, v in report["members"].items() if v["status"] in ("missing_md", "degraded")]
    if bad:
        report["verdict"] = "degraded"
        report["advice"] = (f"成员 {bad} 不可用或已被静默降级。按 harness.yaml#fallback.on_unavailable="
                            f"{fb.get('on_unavailable')} 处置：spawn 通用子代理并在任务包开头注入该成员 MD 全文；"
                            f"同一成员最多尝试 {fb.get('max_spawn_attempts')} 次，超限即上报主理人，不得无限重试。")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if bad else 0


# ─────────────────────────── route ───────────────────────────
def cmd_route(args):
    """确定性路由：复杂度 → spawn 计划（不再靠主理人临场判断）。"""
    cfg, _ = load_cfg()
    r = cfg.get("routing", {}).get(args.level)
    if not r:
        print(f"用法错误：未知复杂度 {args.level}", file=sys.stderr)
        return 2
    plan = {"level": args.level, "team_create": r.get("team_create"),
            "spawn": r.get("spawn"), "confirm_gates": r.get("confirm_gates"),
            "red_team": r.get("red_team", False),
            "budgets": cfg.get("budgets", {}),
            "handoff_mode": cfg.get("context", {}).get("handoff_mode")}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


# ─────────────────────────── state ───────────────────────────
def cmd_state(args):
    cfg, _ = load_cfg()
    w = wkspace(args)
    allowed = cfg.get("context", {}).get("state_allowed_keys") or []
    stages = cfg.get("stages", {})

    if args.action == "init":
        st = {"task_id": f"t{int(time.time())}", "workflow": args.workflow or "WF-1",
              "current_stage": args.stage if args.stage is not None else 0,
              "stage_history": [], "user_confirmations_pending": [],
              "tool_probe_results": {}, "budget": {}, "next_action": "", "compaction": {}}
        write_state(w, st)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    st = read_state(w)
    if args.action == "get":
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    if args.action == "validate":
        errs = []
        cs = st.get("current_stage")
        # v3.3.0：双轨期 0-4 合法（4 闸→5 闸），旧任务 0-3 仍合法；只拒绝 5+ 整数
        if not isinstance(cs, int) or cs < 0 or cs > 4:
            errs.append(f"current_stage 非法：{cs!r}（v3.3.0 双轨期 0-4 整数，不接受 M5A2 之类的便签值）")
        if allowed:
            extra = [k for k in st if k not in allowed]
            if extra:
                errs.append(f"存在白名单外的键（状态文件膨胀源头）：{extra}")
        try:
            sz = os.path.getsize(state_path(w))
            if sz > int(cfg["context"].get("state_max_bytes", 32768)):
                errs.append(f"状态文件 {sz} bytes 超过上限，必须 compaction")
        except OSError:
            pass
        print(json.dumps({"ok": not errs, "errors": errs}, ensure_ascii=False, indent=2))
        return 0 if not errs else 1
    if args.action == "set":
        if args.stage is not None:
            # v3.3.0：双轨期 0-4 合法
            if not isinstance(args.stage, int) or args.stage < 0 or args.stage > 4:
                print(f"拒绝写入：阶段必须是 0-4 整数（v3.3.0 双轨期），收到 {args.stage!r}", file=sys.stderr)
                return 1
            st["current_stage"] = args.stage
            st.setdefault("stage_history", []).append(
                {"stage": args.stage, "status": "entered", "ts": now_iso(), "summary": args.detail or ""})
        if args.key:
            if allowed and args.key not in allowed:
                print(f"拒绝写入：{args.key} 不在 state_allowed_keys 白名单内", file=sys.stderr)
                return 1
            try:
                st[args.key] = json.loads(args.value)
            except Exception:
                st[args.key] = args.value
        write_state(w, st)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    return 2


# ─────────────────────────── budget ───────────────────────────
def cmd_budget(args):
    """任务级预算计数：spawn / react / rework 三类，超限即阻断（纪律变计数）。"""
    cfg, _ = load_cfg()
    b = cfg.get("budgets", {})
    limit_map = {"spawn": "max_member_spawns", "react": "max_react_rounds_total",
                 "rework": "max_rework_rounds_per_stage"}
    w = wkspace(args)
    st = read_state(w)
    bud = st.setdefault("budget", {})

    if args.action == "reset":
        st["budget"] = {}
        write_state(w, st)
        print(json.dumps(st["budget"], ensure_ascii=False))
        return 0

    if args.action == "check":
        # v3.4.0 R2 修：kind 缺省时不再返回"used=0 limit=0 exceeded=true"的矛盾状态
        if not args.kind:
            print(json.dumps({"kind": None, "used": 0, "limit": 0, "exceeded": False,
                              "remaining": 0, "hint": "指定 --kind spawn|react|rework"},
                             ensure_ascii=False))
            return 2  # 用法错误，提示重跑
        used = bud.get(args.kind, 0)
        lim = int(b.get(limit_map.get(args.kind, ""), 0))
        print(json.dumps({"kind": args.kind, "used": used, "limit": lim,
                          "exceeded": used >= lim, "remaining": max(lim - used, 0)}, ensure_ascii=False))
        return 0 if used < lim else 1

    if args.action == "spend":
        lim = int(b.get(limit_map.get(args.kind, ""), 0))
        used = bud.get(args.kind, 0)
        if used + args.n > lim:
            print(f"⛔ 预算阻断：{args.kind} 已用 {used}/{lim}，本次申请 {args.n}。"
                  f"按 harness.yaml 处置（上报主理人 / 走降级），不得硬冲。", file=sys.stderr)
            _trace(w, cfg, "budget_exceeded", args.actor or "main",
                   {"kind": args.kind, "used": used, "limit": lim, "n": args.n})
            return 1
        bud[args.kind] = used + args.n
        write_state(w, st)
        print(json.dumps(bud, ensure_ascii=False))
        return 0
    return 2


# ─────────────────────────── trace ───────────────────────────
def _trace(w, cfg, event, actor, detail):
    rec = {"ts": now_iso(), "event": event, "actor": actor, "detail": detail}
    with open(trace_path(w, cfg), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def cmd_trace(args):
    cfg, _ = load_cfg()
    w = wkspace(args)
    if args.action == "log":
        # v3.4.3 A1：死值防呆——漏写 --event（None）或显式传 "event" 都拒绝写入
        if not args.event or args.event == "event":
            sys.stderr.write(
                "[trace log] --event 必填且不得为死值 \"event\"（v3.4.3 A1）。\n"
                "  事件名请用语义名：gate/sweep/eval/template_audit/agent_spawn/"
                "stage_enter/stage_exit/verify_ref/doctor/preflight 等。\n")
            return 2
        try:
            d = json.loads(args.detail) if args.detail else {}
        except Exception:
            d = {"raw": args.detail}
        print(json.dumps(_trace(w, cfg, args.event, args.actor or "main", d), ensure_ascii=False))
        return 0
    if args.action == "report":
        p = trace_path(w, cfg)
        if not os.path.exists(p):
            print("（无 trace 记录）")
            return 0
        ev, by_event, by_actor, dead_event_count = [], {}, {}, 0
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                ev.append(r)
                # v3.4.0 R3-1：event='event' 是 trace log 漏写 --event 的死值
                if r.get("event") == "event":
                    dead_event_count += 1
                by_event[r.get("event")] = by_event.get(r.get("event"), 0) + 1
                by_actor[r.get("actor")] = by_actor.get(r.get("actor"), 0) + 1
        # v3.4.0 R3-3：已知 6 成员 vs 实际 actor 缺口
        expected_actors = {"vet-med-ppt-team-team-lead", "dvm-content-expert",
                           "pedagogy-architect", "visual-slide-designer",
                           "ppt-producer", "verifier"}
        seen = set(by_actor.keys())
        missing_actors = expected_actors - seen
        # 阶段耗时：stage_enter → stage_exit 配对
        spans, open_at = {}, {}
        for r in ev:
            d = r.get("detail") or {}
            s = d.get("stage")
            if r.get("event") == "stage_enter" and s is not None:
                open_at[s] = r["ts"]
            elif r.get("event") == "stage_exit" and s is not None and s in open_at:
                try:
                    t0 = datetime.fromisoformat(open_at[s])
                    t1 = datetime.fromisoformat(r["ts"])
                    spans.setdefault(s, []).append(round((t1 - t0).total_seconds(), 1))
                except Exception:
                    pass
        # v3.4.2 P1-4：按 actor 聚合 token 估算 + 预算使用率
        tokens_by_actor = {}
        for r in ev:
            d = r.get("detail") or {}
            t = d.get("approx_tokens")
            if isinstance(t, (int, float)):
                a = r.get("actor", "unknown")
                tokens_by_actor[a] = tokens_by_actor.get(a, 0) + int(t)
        # 预算（从 config/harness.yaml 读，无则用默认）
        budgets_cfg = cfg.get("budgets", {}) or {}
        max_spawns = budgets_cfg.get("max_member_spawns", 8)
        max_react = budgets_cfg.get("max_react_rounds_total", 15)
        spawn_count = sum(v for k, v in by_actor.items() if k)
        usage_pct = round(spawn_count / max_spawns * 100, 1) if max_spawns else 0
        out = {"events_total": len(ev), "by_event": by_event, "by_actor": by_actor,
               "stage_seconds": {k: v for k, v in spans.items()},
               "stage_seconds_status": "未启用 stage 追踪（需显式发 stage_enter/exit 事件）" if not spans else "ok",
               "dead_event_count": dead_event_count,
               "dead_event_hint": f"{dead_event_count} 条 event='event' 死值（trace log 漏写 --event）" if dead_event_count else "ok",
               "missing_actors": sorted(missing_actors),
               "missing_actors_hint": (f"未观测到 {len(missing_actors)} 成员事件，需 spawn 时显式 trace log"
                                       if missing_actors else "ok"),
               # v3.4.2 P1-4 成本可见性
               "tokens_by_actor": tokens_by_actor,
               "tokens_total": sum(tokens_by_actor.values()),
               "budget_usage": {
                   "spawn_used": spawn_count, "spawn_max": max_spawns,
                   "spawn_pct": usage_pct,
                   "react_max": max_react,
               },
               "first_ts": ev[0]["ts"] if ev else None, "last_ts": ev[-1]["ts"] if ev else None}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    return 2


# ─────────────────────────── gate ───────────────────────────
def cmd_gate(args):
    """包装 verify_deck：统一退出码语义 + 抓 traceback + 写入 trace。
    关键：exit 4（运行错误）必须与 exit 1（P0 阻断）分流处置——
    前者是脚本/文件问题，后者才是课件质量问题，混为一谈会导致"拿脚本 bug 当红灯打回成员"。

    v3.2.0-batch2：lint 前置——ooxml_lint ERROR→exit 1 阻断；snapshot 写回前自动打点。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    vd = os.path.join(HERE, "verify_deck.py")
    if not os.path.exists(vd):
        print(f"依赖缺失：{vd}", file=sys.stderr)
        return 3

    # v3.2.0-batch2：lint 前置（O1）
    lint = os.path.join(HERE, "ooxml_lint.py")
    if os.path.exists(lint):
        lint_cmd = [sys.executable, lint, args.deck]
        if getattr(args, "baseline", None):
            lint_cmd += ["--baseline", args.baseline]
        if getattr(args, "strict", False):
            lint_cmd += ["--strict"]
        t1 = time.time()
        lp = subprocess.run(lint_cmd, capture_output=True, text=True)
        lint_secs = round(time.time() - t1, 2)
        # 输出 lint 报告
        if lp.stdout:
            print(lp.stdout, end="")
        if lp.returncode == 1:
            # D11 苗子：lint ERROR 阻断
            _trace(w, cfg, "lint_blocked", args.actor or "ppt-producer",
                   {"deck": os.path.basename(args.deck), "exit": 1, "seconds": lint_secs,
                    "stderr_tail": (lp.stderr or "")[-300:]})
            print(f"\n[harness.gate] ooxml_lint ERROR 阻断（D11 苗子）耗时 {lint_secs}s —— "
                  f"请先修复 OOXML 兼容性问题再跑 verify_deck。")
            return 1
        if lp.returncode == 4:
            # lint 运行错误，不当红灯
            _trace(w, cfg, "lint_run_error", args.actor or "ppt-producer",
                   {"deck": os.path.basename(args.deck), "exit": 4, "seconds": lint_secs,
                    "stderr_tail": (lp.stderr or "")[-300:]})
            print(f"\n[harness.gate] ooxml_lint 脚本运行错误（exit 4）—— 走缺陷回流修脚本，"
                  f"不当课件红灯。", file=sys.stderr)
            return 4
        _trace(w, cfg, "lint_passed", args.actor or "ppt-producer",
               {"deck": os.path.basename(args.deck), "exit": lp.returncode, "seconds": lint_secs})

    # v3.2.0-batch2：snapshot 写回前自动打点（O2，可选）
    snap = os.path.join(HERE, "snapshot.py")
    if os.path.exists(snap) and not getattr(args, "no_snap", False):
        snap_cmd = [sys.executable, snap, "snap", args.deck,
                    "--workspace", w, "--trigger", "auto_pre_writeback",
                    "--gate-exit", "0"]
        if getattr(args, "tag", None):
            snap_cmd += ["--tag", args.tag]
        sp = subprocess.run(snap_cmd, capture_output=True, text=True)

    cmd = [sys.executable, vd, args.deck, "--hours", str(args.hours), "--level", args.level]
    if args.json:
        cmd += ["--json", args.json]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    secs = round(time.time() - t0, 2)
    meaning = cfg.get("gate_exit_codes", {}).get(str(p.returncode), "未知退出码")
    print(p.stdout, end="")
    if p.stderr:
        print(p.stderr, end="", file=sys.stderr)
    _trace(w, cfg, "gate", args.actor or "ppt-producer",
           {"deck": os.path.basename(args.deck), "level": args.level, "exit": p.returncode,
            "meaning": meaning, "seconds": secs,
            "stderr_tail": (p.stderr or "")[-300:]})
    print(f"\n[harness.gate] exit={p.returncode}（{meaning}） 耗时 {secs}s —— "
          f"已写入 trace；exit=4 属运行错误，走缺陷回流，不得当作课件红灯打回成员。")
    return p.returncode


# ─────────────────────── 产物真实性核验 ───────────────────────
def cmd_verify_artifact(args):
    """核验成员自报"已落盘"是否属实。

    实测依据（2026-09-29）：3 名成员中多人自报"已写入 XX.md"，主理人全盘检索后
    文件根本不存在；郅作基自报门禁数字（P0=13）与独立复验（P0=136）也差一个量级。
    「智能体无法准确评估自己的工作」——落盘与计数一律机器核验，自述不作交付依据。
    """
    import hashlib
    p = os.path.abspath(args.path)
    res = {"path": p, "exists": os.path.exists(p)}
    if not res["exists"]:
        res["verdict"] = "❌ 文件不存在——成员自报不实，按反自评失真处理，退回重做"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        _trace(args.workspace or os.getcwd(), load_cfg()[0], "self_report_false",
               args.actor or "member", {"path": p, "reason": "file not found"})
        return 1
    b = open(p, "rb").read()
    res.update({"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()[:16]})
    if len(b) == 0:
        res["verdict"] = "❌ 文件为空"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    if args.min_bytes and len(b) < args.min_bytes:
        res["verdict"] = f"⚠ 体积 {len(b)} < 期望 {args.min_bytes}，疑似内容不完整"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    if args.expect_bytes and abs(len(b) - args.expect_bytes) > max(200, args.expect_bytes * 0.2):
        res["verdict"] = (f"⚠ 体积 {len(b)} 与成员自报 {args.expect_bytes} 偏差过大，"
                          f"要求成员给出绝对路径与真实字节数")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    res["verdict"] = "✅ 落盘属实"
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


# ─────────────────── 文献引用预检（v3.4.2 P0-3：反假 PMID）────────────
# 背景：v3.4.2 诊断实测——cases_library 3 条 ok=true 全是 PMID:12345 假引用（假号复用 3 次）。
# dvm MD 规定"核验通过 = 三个来源至少两个命中"被击穿：ok 判定无实检无时间戳。
# 本子命令对 cases_library.json 做静态预检，发现假号模式直接拒，不依赖 PubMed 实检（联网见 P0-2 真正核验）。

import re as _re_ref
_PMID_RE = _re_ref.compile(r"^PMID:\s*(\d+)$", _re_ref.I)
_DOI_RE = _re_ref.compile(r"^(?:DOI:|https?://(?:dx\.)?doi\.org/)?\s*(10\.\d{4,}/\S+)$", _re_ref.I)
# 假号黑名单：占位号、明显测试号（按 PubMed 实测无有效对应）
_FAKE_PMIDS = {"12345", "00000", "99999", "11111", "012345"}
# 旧 cases_library "ok" 无 verified_at → 一律判 unverified 候选
_OK_NO_TS = _re_ref.compile(r"\"ok\"\s*:\s*true", _re_ref.I)


def _check_one_ref(src: dict) -> dict:
    """单条来源预检：返回 {verdict, reason, fix_hint}。
    v3.4.2 红线：ok=true 但无 verified_at → 假通过（最高优先级，先判）。
    真黑名单号（PMID:12345 等占位号）即使 ok=false 也报 fake，便于核验时挑出。
    """
    kind = (src.get("kind") or "").lower()
    ref = (src.get("ref") or "").strip()
    has_ts = bool(src.get("verified_at"))
    ok_flag = bool(src.get("ok"))
    if not kind or not ref:
        return {"verdict": "invalid", "reason": "缺 kind 或 ref",
                "fix_hint": "补 kind+ref，或改 unverified=true"}
    if ok_flag and not has_ts:
        return {"verdict": "stale_ok", "reason": "ok=true 但缺 verified_at 时间戳（v3.4.2 红线）",
                "fix_hint": "改为 ok=false + verified_at 留空，或联网实检后补 verified_at"}
    if kind == "pubmed":
        m = _PMID_RE.match(ref)
        if not m:
            return {"verdict": "format_err", "reason": f"PMID 格式不合规: {ref!r}",
                    "fix_hint": "应为 PMID:<数字>，如 PMID:12345678"}
        if m.group(1) in _FAKE_PMIDS:
            return {"verdict": "fake", "reason": f"PMID:{m.group(1)} 在黑名单（占位号/测试号）",
                    "fix_hint": ("降级 unverified=true（推荐保留历史但禁用）"
                                 if not ok_flag else "联网实检替换为真实 PMID")}
        if len(m.group(1)) < 6:
            return {"verdict": "suspicious", "reason": f"PMID 长度 < 6 位（{m.group(1)}）",
                    "fix_hint": "PubMed PMID 实际多 7-8 位，过短疑为占位"}
    if kind == "doi":
        if not _DOI_RE.match(ref):
            return {"verdict": "format_err", "reason": f"DOI 格式不合规: {ref!r}",
                    "fix_hint": "应为 10.xxxx/<suffix>，可带 DOI: 前缀或 doi.org URL"}
    return {"verdict": "ok", "reason": "通过预检", "fix_hint": ""}


def _static_ref_report(cases):
    """v3.4.3 A2：静态引用预检（自 cmd_verify_ref 抽出——--online 修复后需复跑同一逻辑）。"""
    report = {"total": len(cases), "fake": [], "stale_ok": [], "suspicious": [],
              "format_err": [], "ok": [], "fake_unverified": []}
    for c in cases:
        sid = c.get("case_id", c.get("title", "?"))
        for src in (c.get("sources") or []):
            r = _check_one_ref(src)
            v = r["verdict"]
            # 已 unverified 的黑名单号不阻断（仅标出便于核验时挑出）
            if v == "fake" and not src.get("ok"):
                report["fake_unverified"].append({"case_id": sid, "ref": src.get("ref"),
                                                   "reason": r["reason"]})
                continue
            report[v].append({"case_id": sid, "ref": src.get("ref"),
                              "reason": r["reason"]})
    return report


def _pmid_online_check(pmids):
    """v3.4.3 A2：PubMed esearch 联网确认 PMID 真实存在（反"假核验"闭环核心）。
    返回 {pmid: True/False/None}——True=存在 False=esearch 无记录 None=网络失败。
    请求间 sleep 0.4s（NCBI 无 key 限速 3/s）；None 不参与写回判定（防半核验落盘）。
    """
    import urllib.request as _u
    out = {}
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    for pmid in pmids:
        try:
            url = f"{base}?db=pubmed&term={pmid}%5Buid%5D&retmode=json"
            with _u.urlopen(url, timeout=15) as resp:
                j = json.loads(resp.read().decode("utf-8"))
            ids = (j.get("esearchresult") or {}).get("idlist") or []
            out[pmid] = str(pmid) in [str(x) for x in ids]
        except Exception:
            out[pmid] = None
        time.sleep(0.4)  # NCBI 限速（无 key 3 req/s）
    return out


def cmd_verify_ref(args):
    """v3.4.2 P0-3（v3.4.3 A2 增强）：cases_library.json 文献引用预检。
    默认：静态预检（假 PMID/格式错/缺时间戳红线），只读。
    --online：对未核验的 pubmed 来源联网 PubMed esearch 确认，命中补 ok+verified_at。
    --write-back：受控写回（静态门禁 → .bak 备份 → 写回 → 复检；net_err>0 拒写）。
    背景：v3.4.2 P0-2 曾用一次性脚本直写 cases_library.json 绕过本命令（诊断 3.1 实证）——
    A2 后「联网核验+写回」收编为本命令唯一受控路径，旁路消除。
    exit 0=全过；1=存在需处置项；2=文件错。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    p = os.path.abspath(args.path)
    if not os.path.isfile(p):
        print(f"❌ cases_library 不存在: {p}", file=sys.stderr)
        return 2
    try:
        d = json.loads(open(p, encoding="utf-8").read())
    except Exception as e:
        print(f"❌ 解析失败: {e}", file=sys.stderr)
        return 2
    cases = d.get("cases", d) if isinstance(d, dict) else d
    report = _static_ref_report(cases)

    # ── v3.4.3 A2：--online 联网核验（esearch 命中 → 补 ok+verified_at）──
    online_summary = None
    if getattr(args, "online", False):
        todo = {}
        for c in cases:
            for src in (c.get("sources") or []):
                if (src.get("kind") or "").lower() != "pubmed":
                    continue
                m = _PMID_RE.match((src.get("ref") or "").strip())
                if not m or m.group(1) in _FAKE_PMIDS:
                    continue
                if not (src.get("ok") and src.get("verified_at")):
                    todo[m.group(1)] = src
        online_summary = {"checked": len(todo), "hit": 0, "miss": 0, "net_err": 0}
        if todo:
            res = _pmid_online_check(sorted(todo))
            for pmid, verdict in res.items():
                src = todo[pmid]
                if verdict is True:
                    src["ok"] = True
                    src["verified_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    online_summary["hit"] += 1
                elif verdict is False:
                    online_summary["miss"] += 1
                else:
                    online_summary["net_err"] += 1
            # 联网修复后复跑静态预检（ok 补齐后 stale_ok 应清零）
            report = _static_ref_report(cases)
        print(f"🌐 online 核验：checked={online_summary['checked']} "
              f"hit={online_summary['hit']} miss={online_summary['miss']} "
              f"net_err={online_summary['net_err']}")

    # ── v3.4.3 A2：--write-back 受控写回（门禁 → 备份 → 写回 → 复检）──
    wrote_back = False
    if getattr(args, "write_back", False):
        blockers = (report["fake"] or report["stale_ok"] or report["suspicious"]
                    or report["format_err"])
        net_partial = bool(online_summary and online_summary.get("net_err", 0) > 0)
        if blockers:
            print("🚫 拒绝写回：静态预检存在需处置项（先处置再 --write-back）",
                  file=sys.stderr)
        elif net_partial:
            print("🚫 拒绝写回：--online 存在网络失败条目（防半核验状态落盘，"
                  "重跑至 net_err=0 再写）", file=sys.stderr)
        else:
            bak = p + ".bak"
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            report = _static_ref_report(cases)   # 写回后复检
            wrote_back = True
            print(f"💾 已写回 {p}（备份 {bak}）；复检 fake={len(report['fake'])} "
                  f"stale_ok={len(report['stale_ok'])} suspicious={len(report['suspicious'])}")
    summary = {
        "total": report["total"],
        "fake_count": len(report["fake"]),
        "stale_ok_count": len(report["stale_ok"]),
        "suspicious_count": len(report["suspicious"]),
        "format_err_count": len(report["format_err"]),
        "ok_count": len(report["ok"]),
        "fake_unverified_count": len(report["fake_unverified"]),
        "verdict": ("✅ 全过" if not (report["fake"] or report["stale_ok"]
                                       or report["suspicious"] or report["format_err"])
                     else "❌ 存在需处置项"),
        "details": {k: v for k, v in report.items() if k != "total" and v},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    _trace(w, cfg, "verify_ref", args.actor or "verifier",
           {"path": p, "fake": len(report["fake"]),
            "stale_ok": len(report["stale_ok"]), "suspicious": len(report["suspicious"]),
            "online": bool(getattr(args, "online", False)),
            "write_back": wrote_back,
            "online_summary": online_summary})
    if report["fake"] or report["stale_ok"] or report["suspicious"] or report["format_err"]:
        return 1
    return 0


# ─────────────────── 回传信封机器校验（B2）───────────────────
ENVELOPE_REQUIRED = ["agent_id", "task_id", "phase", "status", "confidence",
                     "deliverable_summary"]
ENVELOPE_STATUS = {"success", "partial", "failed", "blocked"}


def _extract_envelope(text):
    """从 markdown 文本里取出第一个 JSON 对象（优先 ```json 代码块）。"""
    import re as _re
    m = _re.search(r"```json\s*(\{.*?\})\s*```", text, _re.S)
    if m:
        return m.group(1)
    m = _re.search(r"\{.*\}", text, _re.S)
    return m.group(0) if m else None


def cmd_verify_envelope(args):
    """校验成员回传的 result_envelope（把约定变成代码）。

    缘由（2026-10-04）：result_envelope 由 commit 7013f87 引入，但只写在 MD 里，
    成员"自觉遵守"——实测自报失真 4/4 个版本复发，说明约定必须有执行者。
    """
    p = os.path.abspath(args.path)
    res = {"path": p, "exists": os.path.exists(p)}
    if not res["exists"]:
        res["verdict"] = "❌ 文件不存在"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    text = open(p, encoding="utf-8").read()
    blob = _extract_envelope(text)
    if not blob:
        res["verdict"] = "❌ 未找到 result_envelope JSON 块"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    try:
        env = json.loads(blob)
    except Exception as e:
        res["verdict"] = f"❌ result_envelope 不可解析：{e}"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    missing = [k for k in ENVELOPE_REQUIRED if k not in env or env.get(k) in (None, "")]
    res["envelope"] = env
    res["missing"] = missing
    if missing:
        res["verdict"] = f"❌ 信封缺字段：{missing}（判 partial，退回补充）"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    st = str(env.get("status", "")).lower()
    if st not in ENVELOPE_STATUS:
        res["verdict"] = f"❌ status 取值非法：{st!r}（应为 {'/'.join(sorted(ENVELOPE_STATUS))}）"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    # 产物路径真实性交叉核验（若有 artifact 字段）
    art = env.get("artifact") or env.get("deliverable") or ""
    if isinstance(art, str) and art.startswith("/") and not os.path.exists(art):
        res["verdict"] = f"⚠ 信封声明的产物不存在：{art}（疑自评失真，先落盘再放行）"
        res["verdict_ok"] = True          # 字段齐备，但需人工处理
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    res["verdict"] = "✅ 信封合规"
    res["verdict_ok"] = True
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


# ─────────────────── 模板审计（v3.2.0-batch3）───────────────────
def cmd_template_audit(args):
    """模板盘点 + 登记册审计一步跑（薄封装 theme_fingerprint.batch_report）。

    用途：批量迁移前的"先查册"闸门——未登记指纹的课件不许直接换模板
    （用户裁决 2：换模板前先查此册，复用先登记）。
    """
    sys.path.insert(0, HERE)
    try:
        from theme_fingerprint import batch_report
    except Exception as e:
        print(f"依赖缺失：theme_fingerprint 导入失败（{e}）", file=sys.stderr)
        return 3
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"用法错误：--root 不是目录：{root}", file=sys.stderr)
        return 2

    report = batch_report(Path(root))
    reg_p = os.path.join(wkspace(args), ".workbuddy", "templates", "template_registry.json")
    registered = set()
    if os.path.exists(reg_p):
        try:
            with open(reg_p, encoding="utf-8") as f:
                # 登记册结构：{"schema_version":…, "templates":[{…, "fingerprint":{"theme":…}}]}
                for e in json.load(f).get("templates", []):
                    fp = e.get("fingerprint", {})
                    theme = fp.get("theme") if isinstance(fp, dict) else fp
                    if theme:
                        registered.add(theme)
        except Exception as e:
            print(f"⚠ 登记册解析失败（{e}），按空册处理", file=sys.stderr)

    # 盘点分布：distribution=[{fingerprint,count,…}] → {fp: count}
    fps = {d["fingerprint"]: d["count"] for d in report.get("distribution", [])
           if isinstance(d, dict) and d.get("fingerprint")}
    matched = sorted(fps.keys() & registered)
    unregistered = sorted(fps.keys() - registered)
    out = {
        "ts": now_iso(), "root": root,
        "decks": report.get("total_decks"), "unique_fps": report.get("unique_fingerprints"),
        "registry_path": reg_p, "registry_size": len(registered),
        "registered_fps": matched, "unregistered_fps": unregistered,
        "verdict": "all_registered" if not unregistered else "has_unregistered",
    }
    if unregistered:
        out["advice"] = (f"指纹 {unregistered} 未登记。先 register 再迁移："
                         f"python template_migrate.py register <模板.pptx> --name <名> "
                         f"--use-case <场景> --domain <学科>")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    cfg, _ = load_cfg()
    _trace(wkspace(args), cfg, "template_audit", "main",
           {"root": root, "decks": out["decks"], "unregistered": len(unregistered)})
    return 1 if (unregistered and args.require_registered) else 0


# ─────────────────── 双层 Loop 状态机（v3.9.0：文档契约 → 代码约束） ───────────────────
# 背景（2026-10-22 核对实证）：v3.8.0/3.8.1 把 loop_a/loop_b 写进了 config/harness.yaml，
#   五条指令与终止五类写进了 references/dual-loop-governance.md，但 harness.py **从未含
#   loop 子命令**——"逐轮停等""部分接受只冻点名条目""sha256 漂移即失效""沉默不推进"
#   全是靠主理人自觉遵守的 Markdown 纪律，同一份治理文档 §8 第 3 项自认"非代码级强制"。
# 本段把其中**可确定性判定**的部分下沉为代码：状态读写、决策语义、预算触顶、冻结失效、
#   原件只读核验、制作前置门、两环目录越界校验。
# 诚实边界：本段**不判定**条目的专业内容对错（仍归成员与主理人），也不拦截成员的实际
#   写文件动作（平台层无 hook）——它校验"路径是否越界"与"状态推进是否合规"，不是沙箱。

LOOP_TERMINATIONS = ["成功完成", "等待用户", "能力或证据阻塞", "达到预算但未完成", "用户取消"]
LOOP_INTAKE_A = ["audience", "periods", "template", "scope", "acceptance"]  # A 类五项：缺一即停


def _sha256_file(path):
    """文件 sha256——冻结/失效判定与原件只读核验的唯一证据源（禁凭印象说话）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _loop_state_path(w, loop):
    p = os.path.join(w, ".workbuddy")
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, f"loop{loop.upper()}_state.json")


def _read_loop_state(w, loop):
    """读 Loop 状态；不存在返回 None（与 task_state.json 并存，不复用其路径）。"""
    sp = _loop_state_path(w, loop)
    if not os.path.exists(sp):
        return None
    try:
        with open(sp, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ loop{loop.upper()}_state.json 解析失败（{e}），按空状态处理", file=sys.stderr)
        return None


def _write_loop_state(w, loop, st):
    with open(_loop_state_path(w, loop), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def _loop_hist(st, action, detail):
    """追加一条不可删的流水——'每轮用户批准可追溯'（验收清单第 5 项）靠它落地。"""
    st.setdefault("history", []).append(
        {"ts": now_iso(), "action": action, "detail": detail})


def _loop_counts(st):
    items = st.get("items", {})
    frozen = [k for k, v in items.items() if v.get("status") == "frozen"]
    invalid = [k for k, v in items.items() if v.get("status") == "invalidated"]
    pending = [k for k, v in items.items() if v.get("status") not in ("frozen", "invalidated")]
    return {"frozen": frozen, "invalidated": invalid, "pending": pending}


def _resolve_placeholders(p, w):
    """把 harness.yaml 里的 <包> / <工作区> 占位符解析成真实绝对路径。"""
    return p.replace("<包>", PKG).replace("<工作区>", w)


def _glob_match(path, pattern):
    """通配匹配（fnmatch 不认 ** 的递归语义，此处自行转正则）。

    规则：`**/` → 任意层级目录；`**` → 任意字符；`*` → 单层非分隔符；`?` → 单字符。
    """
    out, i = "", 0
    pat = pattern.replace("\\", "/")
    while i < len(pat):
        if pat[i:i + 3] == "**/":
            out += "(?:.*/)?"     # 也匹配零层：<工作区>/**/*.pptx 命中工作区根下的 pptx
            i += 3
            continue
        if pat[i:i + 2] == "**":
            out += ".*"
            i += 2
            continue
        if pat[i] == "*":
            out += "[^/]*"
        elif pat[i] == "?":
            out += "[^/]"
        else:
            out += re.escape(pat[i])
        i += 1
    return re.match("^" + out + "$", path.replace("\\", "/")) is not None


def _parse_kv_list(s):
    """解析 'I-001,I-002' 或 'I-001=a.md,I-002=b.md' 形式的命令行参数。"""
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out.append((k.strip(), v.strip()))
        else:
            out.append((part, ""))
    return out


def cmd_loop(args):
    """双层 Loop 状态机（v3.9.0）：把 dual-loop-governance.md 的可判定条款下沉为代码。

    覆盖的硬约束（对应 round-review-sop.md 条款）：
      · 沉默/超时不构成确认 → continue 必须显式带 --decision，缺省即 exit 2
      · 部分接受只冻点名条目 → freeze 只改 --items 列出的项，其余保持 pending
      · 返修仍属当前轮 → rework 不改 current_round，只累加 rework_count
      · sha256 漂移即批准失效 → verify 重算哈希，不一致标记 invalidated 并 exit 1
      · 预算触顶只暂停不宣布通过 → continue 超 max_rounds 写「达到预算但未完成」并 exit 1
      · 原件只读 → verify/make-gate 比对启动时的 sha256+size+mtime
      · 两环目录隔离 → check-path 校验写入目标是否越界
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    loop = (args.loop or "b").lower()
    lb = cfg.get("loop_b", {}) or {}
    la = cfg.get("loop_a", {}) or {}
    budgets = dict(lb.get("budgets", {}) or {})

    # ── check-path：写前越界校验（Loop A 禁区 = 用户课件目录；Loop B 禁区 = 包目录与原件）
    if args.action == "check-path":
        target = os.path.abspath(args.path)
        if loop == "a":
            forb = [_resolve_placeholders(p, w) for p in (la.get("forbidden_paths") or [])]
            hits = [p for p in forb if _glob_match(target, p)]
            if hits:
                print(f"⛔ Loop A 越界：{target}\n   命中禁区 {hits}——"
                      f"Loop A 只许改专家团自身，不得触碰用户课件目录。", file=sys.stderr)
                return 1
            scope = [_resolve_placeholders(p, w) for p in (la.get("scope") or [])]
            # scope 写的是目录（<包>/scripts），须按"目录内"判定而非精确相等
            def _in_scope(t, ps):
                return any(t == p or t.startswith(p.rstrip("/") + "/") for p in ps)
            if scope and not _in_scope(target, scope):
                print(f"⛔ Loop A 越权：{target} 不在白名单 scope 内（{scope}）。", file=sys.stderr)
                return 1
            print(json.dumps({"ok": True, "loop": "A", "path": target}, ensure_ascii=False))
            return 0
        # Loop B
        if target.startswith(PKG):
            print(f"⛔ Loop B 越界：{target} 属于专家包目录——"
                  f"单课件诉求不得改全局规则（须在 Loop A 单独立项）。", file=sys.stderr)
            return 1
        st = _read_loop_state(w, "b")
        src = (st or {}).get("source_ppt", {}).get("path")
        if src and os.path.abspath(src) == target:
            print(f"⛔ Loop B 越界：{target} 是原件，只读；改动必须落在工作副本 "
                  f"{(st or {}).get('wip_dir')}。", file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "loop": "B", "path": target}, ensure_ascii=False))
        return 0

    # ── start：启动（建状态、存档原件指纹、建工作副本目录）
    if args.action == "start":
        if not args.deck:
            print("用法错误：start 必须带 --deck <原 PPTX>", file=sys.stderr)
            return 2
        deck = os.path.abspath(args.deck)
        if not os.path.isfile(deck):
            print(f"依赖缺失：原课件不存在 {deck}", file=sys.stderr)
            return 3
        if not deck.lower().endswith((".pptx", ".ppt")):
            print(f"用法错误：--deck 必须是 .pptx/.ppt，收到 {deck}", file=sys.stderr)
            return 2
        st = _read_loop_state(w, "b")
        if st and not st.get("termination") and not args.force:
            print(f"⛔ 已存在未结束的 Loop B 任务（第 {st.get('current_round')} 轮）。"
                  f"用 `loop resume` 恢复，或加 --force 重建（会丢失冻结记录）。", file=sys.stderr)
            return 1
        base = os.path.splitext(os.path.basename(deck))[0]
        wip = os.path.abspath(args.wip) if args.wip else os.path.join(os.path.dirname(deck), f"{base}_wip")
        stt = os.stat(deck)
        # 预算可确认参数：轮次上限允许任务级覆盖（dual-loop-governance 要求"提出为可确认参数"）
        eff_budgets = dict(budgets)
        if args.max_rounds:
            eff_budgets["max_rounds"] = args.max_rounds
        st = {
            "loop": "B", "task_id": args.task_id or f"b{int(time.time())}",
            "created_at": now_iso(),
            "source_ppt": {"path": deck, "sha256": _sha256_file(deck),
                           "size": stt.st_size, "mtime": datetime.fromtimestamp(
                               stt.st_mtime).astimezone().replace(microsecond=0).isoformat()},
            "wip_dir": wip,
            "intake": {k: None for k in LOOP_INTAKE_A} | {"confirmed": False},
            "current_round": 1, "items": {}, "budgets": eff_budgets,
            "blockers": [], "termination": None,
            "awaiting_user_confirm": True,   # 启动即待确认：未对齐九项不得开工
            "last_decision": None, "history": [],
        }
        os.makedirs(wip, exist_ok=True)
        _loop_hist(st, "start", {"deck": deck, "wip": wip})
        _write_loop_state(w, "b", st)
        _trace(w, cfg, "loop_start", "team-lead", {"task_id": st["task_id"], "deck": deck, "wip": wip})
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    st = _read_loop_state(w, "b")
    if st is None:
        print("依赖缺失：loopB_state.json 不存在，先跑 `loop start --deck <原PPTX>`", file=sys.stderr)
        return 3
    if st.get("termination") and args.action not in ("status", "resume", "terminate"):
        print(f"⛔ 任务已终止（{st['termination']}），不得再执行 {args.action}。", file=sys.stderr)
        return 1

    # ── intake：九项登记（A 类五项齐 + 非空才算 confirmed）
    if args.action == "intake":
        if not args.file:
            print("用法错误：intake 必须带 --file <九项JSON>", file=sys.stderr)
            return 2
        try:
            with open(args.file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"用法错误：--file 解析失败（{e}）", file=sys.stderr)
            return 2
        intake = st.setdefault("intake", {})
        for k, v in data.items():
            intake[k] = v
        missing = [k for k in LOOP_INTAKE_A if not intake.get(k)]
        intake["confirmed"] = not missing
        _loop_hist(st, "intake", {"filled": sorted(data.keys()), "missing": missing})
        _write_loop_state(w, "b", st)
        out = {"confirmed": intake["confirmed"], "missing_A": missing}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if not missing else 1

    # ── add-item：条目登记（八字段中的可判定部分落盘）
    if args.action == "add-item":
        if not args.item:
            print("用法错误：add-item 必须带 --item <item_id>", file=sys.stderr)
            return 2
        items = st.setdefault("items", {})
        if args.item in items and not args.force:
            print(f"⛔ 条目 {args.item} 已存在（状态 {items[args.item].get('status')}）。"
                  f"加 --force 覆盖。", file=sys.stderr)
            return 1
        fp = os.path.abspath(args.file) if args.file else ""
        items[args.item] = {
            "item_id": args.item, "page_id": args.page or "", "file": fp,
            "sha256": _sha256_file(fp) if fp and os.path.isfile(fp) else None,
            "status": "pending", "round": st.get("current_round", 1),
            "decision": None, "decided_at": None, "rework_count": 0,
            "severity": args.severity or "", "owner": args.owner or "",
        }
        _loop_hist(st, "add-item", {"item": args.item, "page": args.page, "file": fp})
        _write_loop_state(w, "b", st)
        print(json.dumps(items[args.item], ensure_ascii=False, indent=2))
        return 0

    # ── status：摘要（含原件是否被改动）
    if args.action == "status":
        c = _loop_counts(st)
        src = st.get("source_ppt", {})
        orig_ok = None
        if os.path.isfile(src.get("path", "")):
            orig_ok = (_sha256_file(src["path"]) == src.get("sha256"))
        print(json.dumps({
            "task_id": st.get("task_id"), "current_round": st.get("current_round"),
            "awaiting_user_confirm": st.get("awaiting_user_confirm"),
            "last_decision": st.get("last_decision"),
            "frozen": len(c["frozen"]), "pending": len(c["pending"]),
            "invalidated": len(c["invalidated"]),
            "blockers": st.get("blockers", []), "termination": st.get("termination"),
            "original_unchanged": orig_ok,
            "intake_confirmed": st.get("intake", {}).get("confirmed", False),
        }, ensure_ascii=False, indent=2))
        return 0 if orig_ok is not False else 1

    # ── resume：断线恢复（只报，不推进；必须等用户确认）
    if args.action == "resume":
        c = _loop_counts(st)
        st["awaiting_user_confirm"] = True      # 恢复后一律先等确认，禁止自动续跑
        _loop_hist(st, "resume", {"round": st.get("current_round"),
                                  "frozen": len(c["frozen"]), "pending": len(c["pending"])})
        _write_loop_state(w, "b", st)
        print(json.dumps({
            "message": (f"恢复到第 {st.get('current_round')} 轮，已冻结 {len(c['frozen'])} 条，"
                        f"待办 {len(c['pending'])} 条；已置 awaiting_user_confirm=true，"
                        f"等您确认后再继续。"),
            "current_round": st.get("current_round"),
            "awaiting_user_confirm": True,
            "frozen_items": c["frozen"], "pending_items": c["pending"],
            "blockers": st.get("blockers", []),
            "wip_dir": st.get("wip_dir"),
        }, ensure_ascii=False, indent=2))
        return 0

    # ── continue：进位（沉默不构成确认 → 必须显式 --decision）
    if args.action == "continue":
        if not args.decision:
            print("⛔ 拒绝进位：continue 必须显式带 --decision accept|partial_accept。"
                  "沉默、超时、成员自评均不构成用户确认（round-review-sop.md#4）。", file=sys.stderr)
            return 2
        if args.decision not in ("accept", "partial_accept"):
            print(f"⛔ {args.decision} 不进位：返修用 `loop rework`，暂停/终止用 `loop terminate`。",
                  file=sys.stderr)
            return 1
        c = _loop_counts(st)
        if args.decision == "partial_accept" and not c["pending"]:
            print("⚠ 声明 partial_accept 但无 pending 条目——按 accept 处理（进位）。",
                  file=sys.stderr)
        if st.get("awaiting_user_confirm") and not args.confirmed:
            print("⛔ 状态为等待用户确认；确认后加 --confirmed 再进位。", file=sys.stderr)
            return 1
        beff = dict(budgets)
        beff.update(st.get("budgets") or {})   # 任务级覆盖优先（用户在启动时确认的参数）
        maxr = int(beff.get("max_rounds", 8))
        nxt = int(st.get("current_round", 1)) + 1
        if nxt > maxr:
            st["termination"] = "达到预算但未完成"
            _loop_hist(st, "budget_exhausted", {"max_rounds": maxr, "attempted": nxt})
            _write_loop_state(w, "b", st)
            _trace(w, cfg, "budget_exceeded", "team-lead",
                   {"loop": "B", "kind": "rounds", "attempted": nxt, "limit": maxr})
            print(f"⛔ 轮次预算触顶（{maxr} 轮）：置终止态「达到预算但未完成」，"
                  f"**暂停并报告，不宣布通过**。如需继续须用户上调 max_rounds 并确认。",
                  file=sys.stderr)
            return 1
        st["current_round"] = nxt
        st["awaiting_user_confirm"] = False
        st["last_decision"] = args.decision
        _loop_hist(st, "continue", {"from": nxt - 1, "to": nxt, "decision": args.decision})
        _write_loop_state(w, "b", st)
        print(json.dumps({"current_round": nxt, "decision": args.decision,
                          "note": f"每轮最多处理 {budgets.get('max_items_per_round', 5)} 条"
                                  f"（loop_b.budgets.max_items_per_round）"},
                         ensure_ascii=False, indent=2))
        return 0

    # ── rework：返修（仍属当前轮，不进位；超单条目上限即挂阻塞）
    if args.action == "rework":
        if not args.item:
            print("用法错误：rework 必须带 --item <item_id>", file=sys.stderr)
            return 2
        items = st.setdefault("items", {})
        it = items.get(args.item)
        if not it:
            print(f"用法错误：条目 {args.item} 未登记（先 `loop add-item`）", file=sys.stderr)
            return 2
        rnd_before = st.get("current_round")
        it["rework_count"] = int(it.get("rework_count", 0)) + 1
        it["status"] = "pending"
        beff = dict(budgets)
        beff.update(st.get("budgets") or {})
        mx = int(beff.get("max_rework_per_item", 2))
        _loop_hist(st, "rework", {"item": args.item, "count": it["rework_count"],
                                  "round": rnd_before, "note": args.note or ""})
        if it["rework_count"] > mx:
            st.setdefault("blockers", []).append(
                {"kind": "rework_exhausted", "item": args.item,
                 "detail": f"单条目返修 {it['rework_count']} 次 > 上限 {mx}；"
                           f"方向层面问题应走「换方向」：该条目作废、新条目入 pending",
                 "ts": now_iso()})
            _write_loop_state(w, "b", st)
            print(f"⛔ 条目 {args.item} 返修 {it['rework_count']} 次超上限 {mx}，已挂阻塞；"
                  f"轮次保持 {rnd_before}（返修不进位）。", file=sys.stderr)
            return 1
        _write_loop_state(w, "b", st)
        print(json.dumps({"item": args.item, "rework_count": it["rework_count"],
                          "current_round": rnd_before, "round_unchanged": True},
                         ensure_ascii=False, indent=2))
        return 0

    # ── freeze：冻结（部分接受只冻点名条目；绑定 file + sha256 + round + decided_at）
    if args.action == "freeze":
        if not args.items:
            print("用法错误：freeze 必须带 --items I-001,I-002", file=sys.stderr)
            return 2
        if not args.decision:
            print("用法错误：freeze 必须带 --decision accept|partial_accept", file=sys.stderr)
            return 2
        items = st.setdefault("items", {})
        pairs = _parse_kv_list(args.items)
        rnd = st.get("current_round", 1)
        frozen, skipped = [], []
        for iid, fpath in pairs:
            it = items.get(iid)
            if not it:
                skipped.append({"item": iid, "reason": "未登记"})
                continue
            if fpath:
                fp = os.path.abspath(fpath)
                if not os.path.isfile(fp):
                    skipped.append({"item": iid, "reason": f"文件不存在 {fp}"})
                    continue
                it["file"] = fp
                it["sha256"] = _sha256_file(fp)
            it.update({"status": "frozen", "round": rnd, "decision": args.decision,
                       "decided_at": now_iso()})
            frozen.append(iid)
        st["last_decision"] = args.decision
        _loop_hist(st, "freeze", {"frozen": frozen, "skipped": skipped,
                                  "decision": args.decision, "round": rnd})
        _write_loop_state(w, "b", st)
        c = _loop_counts(st)
        print(json.dumps({"frozen_now": frozen, "skipped": skipped,
                          "frozen_total": len(c["frozen"]), "pending_total": len(c["pending"]),
                          "note": "部分接受：未点名条目保持 pending，不消耗轮次配额"},
                         ensure_ascii=False, indent=2))
        return 0 if not skipped else 1

    # ── verify：批准失效核验 + 原件未改动（验收清单第 1、5 项的机器背书）
    if args.action == "verify":
        problems = []
        src = st.get("source_ppt", {})
        if os.path.isfile(src.get("path", "")):
            cur = _sha256_file(src["path"])
            if cur != src.get("sha256"):
                problems.append({"kind": "original_modified", "path": src["path"],
                                 "detail": "原件 sha256 与启动时不一致——原件必须只读，立即停止并上报"})
        else:
            problems.append({"kind": "original_missing", "path": src.get("path"),
                             "detail": "原件不见了，立即停止并上报"})
        for iid, it in st.get("items", {}).items():
            if it.get("status") != "frozen":
                continue
            fp = it.get("file")
            if not fp or not os.path.isfile(fp):
                it["status"] = "invalidated"
                problems.append({"kind": "frozen_file_missing", "item": iid, "file": fp,
                                 "detail": "冻结内容文件缺失，批准失效"})
                continue
            if _sha256_file(fp) != it.get("sha256"):
                it["status"] = "invalidated"
                problems.append({"kind": "sha256_drift", "item": iid, "file": fp,
                                 "detail": "内容文件已改，该条目批准自动失效，必须重审"})
        if problems:
            _loop_hist(st, "verify_failed", {"problems": problems})
            _write_loop_state(w, "b", st)
            print(json.dumps({"ok": False, "problems": problems}, ensure_ascii=False, indent=2))
            return 1
        _loop_hist(st, "verify_ok", {"frozen": len(_loop_counts(st)["frozen"])})
        _write_loop_state(w, "b", st)
        print(json.dumps({"ok": True, "original_unchanged": True,
                          "frozen": len(_loop_counts(st)["frozen"])}, ensure_ascii=False, indent=2))
        return 0

    # ── make-gate：制作前置门（round-review-sop.md#8 三条 + 九项 A 类齐备）
    if args.action == "make-gate":
        c = _loop_counts(st)
        reasons = []
        intake = st.get("intake", {})
        if not intake.get("confirmed"):
            miss = [k for k in LOOP_INTAKE_A if not intake.get(k)]
            reasons.append(f"九项 A 类未齐（缺 {miss}）——不得用仓库默认值冒充")
        if c["pending"]:
            reasons.append(f"仍有 {len(c['pending'])} 条未冻结：{c['pending'][:10]}")
        if c["invalidated"]:
            reasons.append(f"{len(c['invalidated'])} 条批准已失效（sha256 漂移），须重审")
        if st.get("blockers"):
            reasons.append(f"存在 {len(st['blockers'])} 条未清阻塞")
        src = st.get("source_ppt", {})
        if os.path.isfile(src.get("path", "")) and _sha256_file(src["path"]) != src.get("sha256"):
            reasons.append("原件已被改动（只读纪律被破坏）")
        if reasons:
            _loop_hist(st, "make_gate_blocked", {"reasons": reasons})
            _write_loop_state(w, "b", st)
            print(json.dumps({"ok": False, "reasons": reasons}, ensure_ascii=False, indent=2))
            return 1
        _loop_hist(st, "make_gate_passed", {"frozen": len(c["frozen"])})
        _write_loop_state(w, "b", st)
        print(json.dumps({"ok": True, "frozen": len(c["frozen"]),
                          "note": "制作期遇内容问题须退回内容轮，不得擅自改写已批准内容"},
                         ensure_ascii=False, indent=2))
        return 0

    # ── block：登记能力/证据阻塞（不降级冒充，必须带核验方法）
    if args.action == "block":
        st.setdefault("blockers", []).append(
            {"kind": args.kind or "unspecified", "detail": args.note or "", "ts": now_iso()})
        _loop_hist(st, "block", {"kind": args.kind, "note": args.note})
        _write_loop_state(w, "b", st)
        print(json.dumps(st["blockers"], ensure_ascii=False, indent=2))
        return 1   # 有阻塞即非正常态

    # ── terminate：五类终止（穷举，不得自造）
    if args.action == "terminate":
        if args.reason not in LOOP_TERMINATIONS:
            print(f"用法错误：--reason 必须是五类之一 {LOOP_TERMINATIONS}", file=sys.stderr)
            return 2
        if args.reason == "成功完成" and not args.confirmed:
            c = _loop_counts(st)
            if c["pending"]:
                print(f"⛔ 仍有 {len(c['pending'])} 条未冻结，不得报「成功完成」。", file=sys.stderr)
                return 1
        st["termination"] = args.reason
        st["awaiting_user_confirm"] = (args.reason == "等待用户")
        _loop_hist(st, "terminate", {"reason": args.reason, "note": args.note or ""})
        _write_loop_state(w, "b", st)
        print(json.dumps({"termination": args.reason, "ts": now_iso(),
                          "state_kept": _loop_state_path(w, "b")}, ensure_ascii=False, indent=2))
        return 0

    return 2


# ─────────────────────────── main ───────────────────────────
def cmd_doctor(args):
    """v3.4.0 R1：LLM 友好"可发现性表"——一次返回所有子命令的 usage/examples/exit_codes。
    根因（2026-10-14 实测 6 步 3 步参数错位）：argparse 仅在运行时暴露错误，
    AI 冷启动/新会话无 README 可查，本子命令填补"可发现性"缺口。
    """
    table = [
        # (子命令, 一句话用途, 必填参数, 常用可选, 退出码, 示例)
        ("doctor",     "可发现性表（你正在看）",                     "无",      "无",          "0", "harness.py doctor"),
        ("preflight",  "开工前成员可用性预检",                        "--team",  "--workspace", "0/1", "harness.py preflight --team vet-med-ppt-team"),
        ("route",      "复杂度 L0-L3 → spawn 计划",                  "--level", "--workspace", "0/1", "harness.py route --level L2"),
        ("state",      "任务状态机读写（init/get/set/validate）",      "action",  "--stage/--key/--value", "0/1/2", "harness.py state set --stage 1 --key deliverable --value <path>"),
        ("budget",     "预算计数（spawn/react/rework）",             "action",  "--kind/--n",  "0/1/2", "harness.py budget check --kind spawn"),
        ("trace",      "执行日志 JSONL（log/report）",                "action",  "--event/--actor/--detail", "0/2", "harness.py trace report"),
        ("spawn",      "v3.4.0：显式记录某成员 spawn（带 token 估算）",  "--agent", "--task-id/--input-bytes/--output-bytes", "0/1/2", "harness.py spawn --agent dvm-content-expert --task-id t1 --input-bytes 1200 --output-bytes 800"),
        ("stage",      "v3.4.1：显式发 stage_enter/exit（填 stage_seconds）", "--action/--stage", "--task-id/--note", "0/2", "harness.py stage --action enter --stage 1"),
        ("gate",       "包装 verify_deck（lint+snap+gate 一体）",     "--deck",  "--hours/--level/--baseline/--tag", "0/1/2/3/4", "harness.py gate --deck x.pptx --hours 1"),
        ("verify-artifact", "核验成员自报落盘（反自评失真硬校验）",    "--path",  "--expect-bytes/--min-bytes", "0/1", "harness.py verify-artifact --path x.md --expect-bytes 1200"),
        ("verify-ref",     "v3.4.2 P0-3：cases_library 文献引用预检（假 PMID/格式错/缺时间戳）", "--path", "--online/--write-back", "0/1/2", "harness.py verify-ref --path cases_library.json --online --write-back"),
        ("sweep",         "v3.4.2 P0-1：递归扫全量 pptx → 收编 deck_registry（v3.1.0 失落的闸外能力）", "--root", "--hours/--level/--max-decks", "0/1/3/4", "harness.py sweep --root <工作区>"),
        ("eval",          "v3.4.2 P3-3：自动化演进环（基线 vs 当前 sweep diff）", "--root", "--reset-baseline", "0/1/2", "harness.py eval --root <工作区> --reset-baseline"),
        ("verify-envelope", "校验 result_envelope JSON 六字段",       "--path",  "无",          "0/1", "harness.py verify-envelope --path <成员产出.md>"),
        ("template-audit",  "模板指纹盘点 + 登记册审计",              "--root",  "--json/--require-registered", "0/1", "harness.py template-audit --root /Users/.../课程目录"),
        ("loop",  "v3.9.0：双层 Loop 状态机（启动/登记/恢复/进位/返修/冻结/核验/制作门/终止/越界）", "action", "--loop/--deck/--items/--decision/--reason", "0/1/2/3", "harness.py loop start --deck x.pptx"),
    ]
    out = {"version": "v3.9.0", "executable": __file__,
           "global_options": ["--workspace <工作空间>（可写在子命令前/后）"],
           "exit_codes": {
               "0": "正常通过",
               "1": "存在需处置项（降级/预算超/状态非法/P0 阻断）",
               "2": "用法错误（缺参数/参数非法）",
               "3": "依赖缺失（脚本/文件未找到）",
               "4": "运行错误（脚本 bug/IO 异常）",
               "5": "闸4.5 三源核验未达标"
           },
           "commands": [
               {"name": n, "purpose": p, "required": r, "optional": o,
                "exit": e, "example": x}
               for (n, p, r, o, e, x) in table
           ]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_spawn(args):
    """v3.4.0 R5：主理人/脚本可显式 spawn 某 agent 写 trace。
    解决：trace 之前只能在 gate/lint/template_audit 三处自动写，4 成员（dvm/pedagogy/
    visual/verifier）零事件。spawn 子命令让"主理人调了 dvm"这件事有 trace。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    members = cfg.get("members", {})
    if args.agent not in members:
        print(f"⚠ agent={args.agent!r} 不在 members 表（{list(members.keys())}）"
              f"——仍记录（可能是外部 agent）", file=sys.stderr)
    detail = {
        "task_id": args.task_id,
        "stage": getattr(args, "stage", None),
        "input_chars": getattr(args, "input_bytes", 0),
        "output_chars": getattr(args, "output_bytes", 0),
    }
    if detail["input_chars"] or detail["output_chars"]:
        detail["approx_tokens"] = round((detail["input_chars"] + detail["output_chars"]) / 4)
    rec = _trace(w, cfg, "agent_spawn", args.agent, detail)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def cmd_sweep(args):
    """v3.4.2 P0-1：闸外收编（v3.1.0 失落的"冷启动合法"基础能力终于落地）。

    背景：v3.4.2 诊断实测——CHANGELOG v3.1.0 自 v3.1.0 至 HEAD 声称"harness.py sweep 已实现+16/16 测试通过"，
    但 git 全历史确认 harness.py 从未含 sweep 子命令；deck_registry.json 的 generator 字段一直自称由它生成。
    连带：台账仅覆盖 4 份课件（3.7%），工作区 108 份 pptx 在监管外。本子命令一次性补救。

    行为：
      1. 递归扫 --root 下所有 .pptx（自动跳过 _trash_*、~ 临时文件、.snapshots 快照库）；
      2. 每份跑 verify_deck.py SSOT 门禁（--hours 默认 2，--level P0）；
      3. 收编到 <workspace>/.workbuddy/deck_registry.json：decks[<name>] = {p0/p1/p3/visible_pages/age_days/first_seen/judge_provenance}；
      4. 写 trace event=sweep；判定 exit 0=全过、1=部分阻断、3=依赖缺失、4=运行错误、2=用法错。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"用法错误：--root 不是目录：{root}", file=sys.stderr)
        return 2
    vd = os.path.join(HERE, "verify_deck.py")
    if not os.path.isfile(vd):
        print(f"依赖缺失：{vd}", file=sys.stderr)
        return 3
    hours = float(getattr(args, "hours", 2) or 2)
    level = getattr(args, "level", "P0") or "P0"
    max_decks = int(getattr(args, "max_decks", 0) or 0)  # 0=不限

    # 扫盘：递归 .pptx，过滤 _trash_/~/snapshots/.git
    skip_dirs = ("_trash_", "~", ".snapshots", ".git", "node_modules")
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if not fn.lower().endswith(".pptx"):
                continue
            if fn.startswith("~$"):
                continue
            found.append(os.path.join(dirpath, fn))
    if max_decks and len(found) > max_decks:
        print(f"⚠ 发现 {len(found)} 份，仅处理前 {max_decks} 份（其余由下次 sweep 补）")
        found = found[:max_decks]

    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    decks = {}
    p0_total = p1_total = p3_total = 0
    blocked = []
    errors = []
    t0 = time.time()
    for i, deck in enumerate(found, 1):
        name = os.path.basename(deck)
        # 用临时 JSON 文件收集门禁结果（避免 stdout 污染）
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            tmp_json = tf.name
        try:
            r = subprocess.run([sys.executable, vd, deck, "--hours", str(hours),
                                "--level", level, "--json", tmp_json],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 4:
                # 走缺陷回流（脚本问题，非课件质量）
                errors.append({"deck": name, "exit": 4,
                               "stderr_tail": (r.stderr or "")[-200:]})
                continue
            try:
                rep = json.loads(open(tmp_json, encoding="utf-8").read())
            except Exception as e:
                errors.append({"deck": name, "exit": 5, "reason": f"JSON 解析失败: {e}"})
                continue
            g = rep.get("gate", {})
            stats = rep.get("stats", {})
            jdg = rep.get("judge", {})
            p0 = g.get("p0", 0); p1 = g.get("p1", 0); p3 = g.get("p3", 0)
            p0_total += p0; p1_total += p1; p3_total += p3
            if p0 > 0:
                blocked.append(name)
            entry = {
                "deck_path": deck,
                "visible_pages": stats.get("visible_pages", stats.get("total_slides")),
                "total_slides": stats.get("total_slides"),
                "hours": hours,
                "first_seen": now_iso,
                "age_days": 0,
                "gate": {"P0": p0, "P1": p1, "P3": p3,
                          "note_coverage": g.get("note_coverage")},
                "judge_provenance": {
                    "SSOT": "vet-med-ppt-team/scripts/verify_deck.py",
                    "SSOT_version": jdg.get("version", "3.0.0"),
                    "thresholds": jdg.get("thresholds",
                                          "vet-med-ppt-team/config/visual-rules.yaml"),
                    "hours_caliber": f"sweep --hours {hours}（CSV 显式/默认）",
                    "level_arg": level,
                },
            }
            decks[name] = entry
            if i % 10 == 0 or i == len(found):
                print(f"  [{i}/{len(found)}] {name}  P0={p0} P1={p1} P3={p3}", file=sys.stderr)
        finally:
            try: os.unlink(tmp_json)
            except OSError: pass

    elapsed = round(time.time() - t0, 1)
    # 收编到 deck_registry.json
    reg_p = os.path.join(w, ".workbuddy", "deck_registry.json")
    os.makedirs(os.path.dirname(reg_p), exist_ok=True)
    reg = {
        "version": 8,
        "updated": now_iso,
        "generator": ("harness.py sweep v3.4.2（v3.1.0 CHANGELOG 声称的'闸外收编'能力实际于 v3.4.2 落地）"
                      "——递归扫 --root 全量 pptx → 逐份 SSOT 门禁 → 收编 deck_registry，不依赖 checkpoint"),
        "judge_provenance": {
            "SSOT": "vet-med-ppt-team/scripts/verify_deck.py",
            "SSOT_version": "3.0.0",
            "thresholds": "vet-med-ppt-team/config/visual-rules.yaml",
            "hours_caliber": f"sweep --hours {hours}（CSV 显式/默认，绝不按页数反推）",
        },
        "counters": {
            "decks": len(decks), "P0_total": p0_total, "P1_total": p1_total,
            "P3_total": p3_total, "P0_blocked_decks": len(blocked),
            "sweep_errors": len(errors), "elapsed_seconds": elapsed,
        },
        "P0_blocked_list": blocked,
        "decks": decks,
    }
    with open(reg_p, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    print(f"✅ sweep 完成：扫描 {len(found)} 份 → 收编 {len(decks)} 份 → P0阻断 {len(blocked)} 份"
          f"（耗时 {elapsed}s）→ 写入 {reg_p}")
    _trace(w, cfg, "sweep", "harness",
           {"root": root, "found": len(found), "admitted": len(decks),
            "P0_total": p0_total, "P1_total": p1_total, "P0_blocked": len(blocked),
            "errors": len(errors), "elapsed_seconds": elapsed, "hours": hours, "level": level})
    return 1 if (blocked or errors) else 0


def cmd_eval(args):
    """v3.4.2 P3-3：自动化演进环——同任务重跑 diff（A/B 演进基线）。

    用途：固化 v3.4.0/v3.4.1 重构时手写的"同任务重跑对比"工作流为代码子命令。
    工作流：
      1. 存当前 deck_registry 为 baseline（若无）；
      2. 跑 sweep 收编当前全量课件；
      3. diff 两次报告的 counters.P0_total / P1_total / P0_blocked_decks / errors；
      4. 输出 diff 报告，写 trace event=eval。

    退出码：0=无恶化、1=有 P0 恶化、2=参数错。
    """
    import shutil
    cfg, _ = load_cfg()
    w = wkspace(args)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"用法错误：--root 不是目录：{root}", file=sys.stderr)
        return 2
    reg_path = os.path.join(w, ".workbuddy", "deck_registry.json")
    baseline_path = os.path.join(w, ".workbuddy", "deck_registry.eval_baseline.json")
    sweep_args = type("A", (), {"root": root, "hours": float(getattr(args, "hours", 2) or 2),
                                  "level": "P0", "max_decks": 0, "actor": "harness",
                                  "workspace": w})()
    if not os.path.exists(reg_path):
        print(f"❌ 当前 deck_registry 不存在：{reg_path}（先跑 sweep 生成基线）", file=sys.stderr)
        return 2
    if getattr(args, "reset_baseline", False) or not os.path.exists(baseline_path):
        shutil.copyfile(reg_path, baseline_path)
        print(f"📌 已存基线：{baseline_path}")
        rc = cmd_sweep(sweep_args)
        print(f"   sweep exit={rc}")
        return 0 if rc == 0 else 1
    # 有基线：跑当前 sweep 然后 diff
    before = json.load(open(baseline_path, encoding="utf-8"))
    rc = cmd_sweep(sweep_args)
    after = json.load(open(reg_path, encoding="utf-8"))
    bc = before.get("counters", {})
    ac = after.get("counters", {})
    diff = {
        "decks": ac.get("decks", 0) - bc.get("decks", 0),
        "P0_total": ac.get("P0_total", 0) - bc.get("P0_total", 0),
        "P1_total": ac.get("P1_total", 0) - bc.get("P1_total", 0),
        "P0_blocked_decks": ac.get("P0_blocked_decks", 0) - bc.get("P0_blocked_decks", 0),
        "sweep_errors": ac.get("sweep_errors", 0) - bc.get("sweep_errors", 0),
        "elapsed_seconds": round(ac.get("elapsed_seconds", 0) - bc.get("elapsed_seconds", 0), 1),
    }
    print(f"\n=== A/B 演进 diff（基线 → 当前） ===")
    for k, v in diff.items():
        arrow = "↑" if v > 0 else ("↓" if v < 0 else "·")
        print(f"  {k:24s} {arrow} {v:+d}" if isinstance(v, int) else f"  {k:24s} {arrow} {v}")
    # 评价
    regress = []
    if diff["P0_total"] > 0:
        regress.append(f"P0_total 上升 {diff['P0_total']}")
    if diff["P0_blocked_decks"] > 0:
        regress.append(f"P0_blocked_decks 上升 {diff['P0_blocked_decks']}")
    if diff["sweep_errors"] > 0:
        regress.append(f"sweep_errors 上升 {diff['sweep_errors']}")
    if regress:
        print(f"\n⚠ 演进恶化: {'; '.join(regress)}")
    else:
        print("\n✅ 演进无恶化（P0/P1/errors 全部持平或下降）")
    # trace
    _trace(w, cfg, "eval", "harness", {"diff": diff, "regress": regress, "rc_sweep": rc})
    # 产物
    out = os.path.join(w, ".workbuddy", "artifacts", "v342_verify", "eval_diff.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"before": bc, "after": ac, "diff": diff, "regress": regress,
                   "ts": datetime.now().astimezone().isoformat(timespec="seconds")},
                  f, ensure_ascii=False, indent=2)
    print(f"  diff 报告: {out}")
    return 1 if regress else 0


def cmd_stage(args):
    """v3.4.1 R11：主理人编排循环在每个闸切换时显式发 stage_enter/stage_exit。

    背景：trace report 的 stage_seconds 配对逻辑（stage_enter → stage_exit 算 ts 差）
    自 v3.4.0 起就写好了，但**没有任何入口发这两个事件**——字段恒为空字典，
    report 只能标"未启用 stage 追踪"。本子命令补上入口。

    与 state set --stage 的分工：
      state 管任务状态机（task_state.json 持久，回答"现在在第几闸"）；
      stage 管执行轨迹（trace.jsonl 追加，回答"每闸实际花了多少秒"）。
      二者都写，互不替代。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    if args.action not in ("enter", "exit"):
        print(f"拒绝：--action 只接 enter|exit（收到 {args.action!r}）", file=sys.stderr)
        return 2
    if not isinstance(args.stage, int) or args.stage < 0 or args.stage > 4:
        print(f"拒绝：--stage 必须是 0-4 整数（v3.3.0 双轨期），收到 {args.stage!r}", file=sys.stderr)
        return 2
    # stage_name 从 harness.yaml#stages 读（禁硬编码闸名）
    stages = cfg.get("stages", {})
    stage_name = (stages.get(str(args.stage)) or {}).get("name", f"闸{args.stage}")
    detail = {"stage": args.stage, "stage_name": stage_name,
              "task_id": args.task_id, "note": args.note or ""}
    # 孤儿 exit 防护：report 配对要求同 stage 先有未闭合 enter（s in open_at），
    # 缺 enter 的 exit 会被静默跳过 → stage_seconds 少一段无人知晓。此处提前检查。
    if args.action == "exit":
        p = trace_path(w, cfg)
        open_cnt = 0
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    d = r.get("detail") or {}
                    if d.get("stage") != args.stage:
                        continue
                    if r.get("event") == "stage_enter":
                        open_cnt += 1
                    elif r.get("event") == "stage_exit":
                        open_cnt -= 1
        if open_cnt <= 0:
            print(f"⚠ stage={args.stage}（{stage_name}）无未闭合的 stage_enter——"
                  f"本次 exit 是孤儿事件，trace report 不会把它计入 stage_seconds", file=sys.stderr)
    rec = _trace(w, cfg, f"stage_{args.action}", args.actor or "vet-med-ppt-team-team-lead", detail)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="vet-med-ppt-team 编排内核（确定性工程层）v3.4.2")
    ap.add_argument("--workspace", help="工作空间路径（默认 cwd）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _ws(sp):  # 允许 --workspace 写在子命令之前或之后
        sp.add_argument("--workspace", default=argparse.SUPPRESS, help="同主命令的 --workspace")

    p = sub.add_parser("doctor", help="v3.4.0：可发现性表——所有子命令的 usage/examples/exit_codes")
    _ws(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("preflight", help="开工前成员可用性与静默降级预检")
    p.add_argument("--team", default="", help="团队名（读 ~/.workbuddy/teams/<team>/config.json）")
    _ws(p)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("route", help="复杂度 → spawn 计划")
    p.add_argument("--level", required=True, choices=["L0", "L1", "L2", "L3"])
    _ws(p)
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("state", help="状态机读写与校验")
    p.add_argument("action", choices=["init", "get", "set", "validate"])
    p.add_argument("--workflow", default="WF-1")
    p.add_argument("--stage", type=int)
    p.add_argument("--key"); p.add_argument("--value"); p.add_argument("--detail")
    _ws(p)
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("budget", help="任务级预算计数")
    p.add_argument("action", choices=["check", "spend", "reset"])
    p.add_argument("--kind", choices=["spawn", "react", "rework"])
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--actor", default="main")
    _ws(p)
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("trace", help="执行日志（JSONL）")
    p.add_argument("action", choices=["log", "report"])
    # v3.4.3 A1：堵死值源——v3.4.0 R3 只清了已生死值，default="event" 未堵会再生；
    # log 时必须显式传 --event，漏写或显式传 "event" 一律 exit 2
    p.add_argument("--event", default=None)
    p.add_argument("--actor", default="main")
    p.add_argument("--detail", default="{}")
    _ws(p)
    p.set_defaults(func=cmd_trace)

    # v3.4.0 R5：spawn 子命令——显式记录某成员 spawn 写 trace
    p = sub.add_parser("spawn", help="v3.4.0：显式记录某成员 spawn（带 token 估算）")
    p.add_argument("--agent", required=True, help="成员名（dvm-content-expert/pedagogy-architect/...）")
    p.add_argument("--task-id", required=True, help="任务 ID（state.task_id 锚定）")
    p.add_argument("--stage", type=int, default=None, help="当前闸号（0-4）")
    p.add_argument("--input-bytes", type=int, default=0, help="输入 token 估算（按 1 token ≈ 4 chars）")
    p.add_argument("--output-bytes", type=int, default=0, help="输出 token 估算（按 1 token ≈ 4 chars）")
    _ws(p)
    p.set_defaults(func=cmd_spawn)

    # v3.4.1 R11：stage 子命令——编排循环显式发 stage_enter/exit，填补 stage_seconds
    p = sub.add_parser("stage", help="v3.4.1：显式发 stage_enter/stage_exit（填 trace report 的 stage_seconds）")
    p.add_argument("--action", required=True, choices=["enter", "exit"], help="进入闸 / 离开闸")
    p.add_argument("--stage", type=int, required=True,
                   help="闸号 0-4（0=闸1冻结 1=闸2设计 2=闸3成稿 3=闸4交付 4=闸4.5三源核验）")
    p.add_argument("--actor", default="vet-med-ppt-team-team-lead")
    p.add_argument("--task-id", default="", help="任务 ID（可选，建议与 state.task_id 一致）")
    p.add_argument("--note", default="", help="人读备注（如：闸2 设计确认通过）")
    _ws(p)
    p.set_defaults(func=cmd_stage)

    # v3.4.2 P0-1：sweep 子命令——CHANGELOG v3.1.0 失落的闸外收编能力终于落地
    p = sub.add_parser("sweep", help="v3.4.2 P0-1：递归扫全量 .pptx → SSOT 门禁 → 收编 deck_registry")
    p.add_argument("--root", required=True, help="课件根目录（递归扫 .pptx，自动跳过 _trash_/~/snapshots）")
    p.add_argument("--hours", type=float, default=2, help="课时口径（默认 2，禁止按页数反推）")
    p.add_argument("--level", choices=["P0", "P1", "all"], default="P0", help="门禁等级")
    p.add_argument("--max-decks", type=int, default=0, help="0=不限；>0 时仅处理前 N 份（分批 sweeP 用）")
    p.add_argument("--actor", default="harness")
    _ws(p)
    p.set_defaults(func=cmd_sweep)

    # v3.4.2 P3-3：eval 子命令——自动化演进环（A/B 重跑 diff）
    p = sub.add_parser("eval", help="v3.4.2 P3-3：自动化演进环（基线 vs 当前 sweep diff）")
    p.add_argument("--root", required=True, help="课件根目录（同 sweep）")
    p.add_argument("--hours", type=float, default=2)
    p.add_argument("--reset-baseline", action="store_true",
                   help="存当前 deck_registry 为新基线（首次跑或主动重置）")
    _ws(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("gate", help="包装 verify_deck，统一退出码语义并落 trace")
    p.add_argument("--deck", required=True)
    p.add_argument("--hours", type=float, default=2)
    p.add_argument("--level", default="all", choices=["P0", "P1", "all"])
    p.add_argument("--json", dest="json", default="")
    p.add_argument("--actor", default="ppt-producer")
    # v3.2.0-batch2：lint/snap 集成参数
    p.add_argument("--baseline", default=None, help="ooxml_lint 基线对照（original 副本）")
    p.add_argument("--strict", action="store_true", help="lint 强模式")
    p.add_argument("--no-snap", action="store_true", help="跳过 snapshot 写回前打点")
    p.add_argument("--tag", default=None, help="snapshot 里程碑标签")
    _ws(p)
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("verify-artifact", help="核验成员自报落盘是否属实（反自评失真硬校验）")
    p.add_argument("--path", required=True)
    p.add_argument("--expect-bytes", type=int, default=0, help="成员自报的字节数（允许 ±20%）")
    p.add_argument("--min-bytes", type=int, default=0)
    p.add_argument("--actor", default="member")
    _ws(p)
    p.set_defaults(func=cmd_verify_artifact)

    # v3.4.2 P0-3：文献引用预检（反假 PMID 机器防御）；v3.4.3 A2 增联网核验+受控写回
    p = sub.add_parser("verify-ref", help="v3.4.2 P0-3：cases_library.json 文献引用预检（假 PMID/格式错/缺时间戳；A2 增 --online 联网核验 + --write-back 受控写回）")
    p.add_argument("--path", required=True, help="cases_library.json 绝对路径")
    p.add_argument("--online", action="store_true",
                   help="v3.4.3 A2：PubMed esearch 联网核验未 verified 的 PMID，命中补 ok+verified_at")
    p.add_argument("--write-back", dest="write_back", action="store_true",
                   help="v3.4.3 A2：受控写回（静态门禁→.bak 备份→写回→复检；net_err>0 拒写）")
    p.add_argument("--actor", default="verifier")
    _ws(p)
    p.set_defaults(func=cmd_verify_ref)

    p = sub.add_parser("verify-envelope", help="校验成员回传 result_envelope 六字段（约定→代码）")
    p.add_argument("--path", required=True)
    _ws(p)
    p.set_defaults(func=cmd_verify_envelope)

    p = sub.add_parser("template-audit", help="模板指纹盘点 + 登记册审计（换模板前先查册）")
    p.add_argument("--root", required=True, help="课件根目录（递归盘点）")
    p.add_argument("--json", dest="json", default="", help="审计结果落盘路径")
    p.add_argument("--require-registered", action="store_true",
                   help="存在未登记指纹时 exit 1（批量迁移前闸门）")
    _ws(p)
    p.set_defaults(func=cmd_template_audit)

    # v3.9.0：双层 Loop 状态机——把 dual-loop-governance.md 的可判定条款下沉为代码
    p = sub.add_parser("loop", help="v3.9.0：双层 Loop 状态机（启动/登记/恢复/进位/返修/冻结/核验/制作门/终止/越界校验）")
    p.add_argument("action", choices=["start", "intake", "add-item", "status", "resume",
                                      "continue", "rework", "freeze", "verify",
                                      "make-gate", "block", "terminate", "check-path"])
    p.add_argument("--loop", choices=["a", "b"], default="b", help="A=专家团工程进化 / B=旧课件逐轮优化")
    p.add_argument("--deck", help="start：原 PPTX 绝对路径（只读，存档 sha256/size/mtime）")
    p.add_argument("--wip", help="start：工作副本目录（默认 <课件名>_wip/）")
    p.add_argument("--task-id", dest="task_id", default="", help="start：任务 ID")
    p.add_argument("--max-rounds", dest="max_rounds", type=int, default=0,
                   help="start：任务级轮次上限（覆盖 harness.yaml#loop_b.budgets.max_rounds，须经用户确认）")
    p.add_argument("--file", help="intake：九项 JSON 路径 / add-item：条目内容文件路径")
    p.add_argument("--items", help="freeze：条目 ID 列表，形如 I-001,I-002 或 I-001=a.md,I-002=b.md")
    p.add_argument("--item", help="rework：条目 ID")
    p.add_argument("--page", help="add-item：稳定页面 ID（如 s12）")
    p.add_argument("--severity", default="", help="add-item：P0/P1/P2")
    p.add_argument("--owner", default="", help="add-item：dvm/pedagogy/visual")
    p.add_argument("--decision", choices=["accept", "partial_accept", "rework", "pause"],
                   help="continue/freeze：用户裁决（不传即拒绝进位——沉默不构成确认）")
    p.add_argument("--confirmed", action="store_true", help="continue/terminate：已获用户确认")
    p.add_argument("--reason", help="terminate：五类终止之一")
    p.add_argument("--kind", default="", help="block：阻塞类型（capability/evidence/...）")
    p.add_argument("--note", default="", help="人读备注")
    p.add_argument("--path", help="check-path：待写入的目标路径（越界校验）")
    p.add_argument("--force", action="store_true", help="start/add-item：允许覆盖既有记录")
    _ws(p)
    p.set_defaults(func=cmd_loop)

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()

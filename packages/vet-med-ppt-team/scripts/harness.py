#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harness.py — vet-med-ppt-team 编排内核（确定性工程层）v3.4.0

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

退出码：0=正常  1=存在需处置项（降级/预算超/状态非法）  2=用法错误  3=依赖缺失
"""

import argparse
import json
import os
import subprocess
import sys
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
        out = {"events_total": len(ev), "by_event": by_event, "by_actor": by_actor,
               "stage_seconds": {k: v for k, v in spans.items()},
               "stage_seconds_status": "未启用 stage 追踪（需显式发 stage_enter/exit 事件）" if not spans else "ok",
               "dead_event_count": dead_event_count,
               "dead_event_hint": f"{dead_event_count} 条 event='event' 死值（trace log 漏写 --event）" if dead_event_count else "ok",
               "missing_actors": sorted(missing_actors),
               "missing_actors_hint": (f"未观测到 {len(missing_actors)} 成员事件，需 spawn 时显式 trace log"
                                       if missing_actors else "ok"),
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
        ("verify-envelope", "校验 result_envelope JSON 六字段",       "--path",  "无",          "0/1", "harness.py verify-envelope --path <成员产出.md>"),
        ("template-audit",  "模板指纹盘点 + 登记册审计",              "--root",  "--json/--require-registered", "0/1", "harness.py template-audit --root /Users/.../课程目录"),
    ]
    out = {"version": "v3.4.1", "executable": __file__,
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
    ap = argparse.ArgumentParser(description="vet-med-ppt-team 编排内核（确定性工程层）v3.4.1")
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
    p.add_argument("--event", default="event")
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

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()

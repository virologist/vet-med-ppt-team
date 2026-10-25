#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harness.py — vet-med-ppt-team 编排内核（确定性工程层）v3.19.1

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
  + 七维精准诊断双路由（**历史记录**：当时量规唯一源=下游 skill teaching-ppt-studio/
    references/seven-dimension-rubric.md，本团只引路径不复制——防双源漂移。
    ⚠ 该口径已于 v3.17.0 作废，量规已内化进本包，见下方 v3.17.0 段）
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

v3.17.0（单一数据源 / 裁判规则落地 / 质量收敛批）：
  + F2 删重复声明源：harness.yaml#budgets 的 three_source_sample_rate /
    three_source_pass_threshold 删除（与 domain_config.yaml#three_source_check 重复声明，
    而 verify_deck.py 只读后者 → 改前者静默失效）。`budget --kind three_source_*`
    改读 domain_config.yaml，输出明示 config_source 与真实执行者；缺值只告警不补内置值。
  + F3 内容判据落地：verify-envelope 不再只判"字段存在且非空"，改按
    references/result-envelope.yaml#validation.content_rules 判 confidence 裸标签、
    deliverable_summary 裸表述、status/issues 一致性、metrics 键子集——
    词表/正则/阈值全在 yaml，代码只执行；规则无执行器时显式告警。
  + F6 质量收敛判据：loop continue 落 quality_history（**报告优先**：
    --verify-json <verify_deck 报告> > --p0/--p1/--p2 手工自报；来源写进快照的
    source 字段与 trace，报告缺字段即报错不静默取 0）；
    连续 no_progress_threshold 轮 P0+P1+P2 合计未下降 → exit 1 + trace 事件 no_progress +
    终止建议（v3.17.0 B3-4：P2 已纳入——否则"只补备注覆盖率"这一有效推进会被误杀）。
    终止原因改读 harness.yaml#loop_b.termination（唯一源）。
  + 七维量规唯一源**收敛到包内**（治双副本漂移）：唯一执行源=包内
    references/seven-dimension-rubric.md；下游 skill teaching-ppt-studio 的同名副本
    **仅作上游对照源**，不一致时**一律以包内为准**。下游副本**不删除**（不在本包管辖范围，
    删除会造成引用方悬空）——收敛靠「声明 + 指向」实现。逐行 diff 结论见该文件顶部
    「差异摘要」段（下游 148 行 → 包内 208 行，本包为超集）。

本脚本把"提示词里的纪律"下沉为"代码里的约束"，全部参数读 config/harness.yaml（禁硬编码）。
它只做确定性事务（路径解析 / 状态校验 / 计数 / 日志 / 进程调用），
不做任何语义判断（识别、匹配、权衡仍归 LLM 与主理人）。

用法（推荐先跑 `python3 scripts/harness.py doctor` 看可发现性表）：
    python3 scripts/harness.py doctor     # 所有子命令的 usage/examples/exit_codes
    python3 scripts/harness.py preflight  [--team <团队名>] [--workspace <路径>]
    python3 scripts/harness.py route      --level L0|L1|L2|L3 [--domain <域id>] [--task-id <id>] [--rationale "<选型理由>"]
    python3 scripts/harness.py domain list|show [--id <域id>] [--workspace <路径>]      # v3.17.0：域档案菜单（给 LLM 选域用）
    python3 scripts/harness.py collapse list|show|confirm --id <域id> [--task-id <id>] [--rationale "<选型理由>"]  # v3.17.0：坍缩产物确认
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
import urllib.request    # v3.17.0 B3-3：textbook/regulation 存在性核验的联网通道
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
                # v3.17.0：删掉 three_source_sample_rate / three_source_pass_threshold——
                # 它们在 harness.yaml 里是"第二份声明"，真正被消费的是
                # config/domain_config.yaml#three_source_check（见 _load_three_source_thresholds）。
                "max_artifact_bytes": 60000},
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


# v3.17.0：三源阈值的**唯一源** = config/domain_config.yaml#three_source_check。
# 与 verify_deck.py#_load_three_source_thresholds 同源同责（那里是执行者，这里是查询者），
# 差异只在缺值策略：本函数**不静默补内置值**——缺键即告警并返回 None，
# 由 `budget check` 按"护栏缺失"如实返回 exit 1（配了 0/null 同样视为不存在）。
# 若在此补 0.1/0.8，改配置的人会以为生效而实际没生效，正是本批要根治的"静默失效"。
_DOMAIN_CFG = os.path.join(PKG, "config", "domain_config.yaml")


def _load_three_source_thresholds():
    """读 domain_config.yaml#three_source_check 的 sample_rate / pass_threshold。

    返回 {"sample_rate": x|None, "pass_threshold": y|None}；缺值不补默认值，只告警。
    ⚠ 有意**不做缓存**：本批治的正是"改配置不生效"，进程内缓存会让长驻进程读到过期阈值，
      与 load_envelope_schema 的缓存取舍不同（schema 每次启动读一次、且变化需重启）。
    """
    out = {"sample_rate": None, "pass_threshold": None}
    try:
        import yaml
        with open(_DOMAIN_CFG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        tsc = cfg.get("three_source_check") or {}
        if not tsc:
            print(f"⚠ {_DOMAIN_CFG}#three_source_check 缺失或为空——"
                  f"三源阈值无唯一源，harness 不补内置值（改配置请改这里）。", file=sys.stderr)
        for k in ("sample_rate", "pass_threshold"):
            v = tsc.get(k)
            if v is None:
                print(f"⚠ {_DOMAIN_CFG}#three_source_check.{k} 未配置——"
                      f"该护栏实际不存在，harness 不补内置值。", file=sys.stderr)
            else:
                out[k] = float(v)
    except Exception as e:
        print(f"⚠ domain_config.yaml#three_source_check 读取失败（{e}）——"
              f"三源阈值不可知，harness 不补内置值。", file=sys.stderr)
    return out


def load_term_reasons(cfg):
    """v3.17.0：终止原因读 harness.yaml#loop_b.termination（不再与代码里另立一份）。

    此前 LOOP_TERMINATIONS 是 harness.py 里的硬编码常量，yaml 里又写一份——
    在 yaml 加终止原因不会生效，属同型"双声明"缺陷。本函数为唯一取值口，
    yaml 不可读/为空时退回内置五类（并告警），保证不因配置缺失而整链不可用。
    """
    lb = (cfg or {}).get("loop_b") or {}
    reasons = [str(x) for x in (lb.get("termination") or []) if str(x).strip()]
    if reasons:
        return reasons
    print("⚠ harness.yaml#loop_b.termination 缺失或为空 → 退回内置终止原因清单，"
          "在 yaml 里新增的终止原因不会生效。", file=sys.stderr)
    return list(_FALLBACK_TERMINATIONS)


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


def read_state(w, strict=False):
    """读 task_state.json。

    v3.17.0：**解析失败不再一律"按空状态处理"**。
      · strict=True（写入路径必须用）：抛 _StateCorrupt —— 在损坏状态上重建会把
        stage_history / task_id 全部丢掉，比读不到更危险（丢历史会被读成"从未推进"）。
      · strict=False（只读路径）：保持旧行为（打印告警 + 返回 {}），但仍**显式告警**。
    """
    sp = state_path(w)
    if not os.path.exists(sp):
        return {}
    try:
        with open(sp, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        msg = f"task_state.json 解析失败（{e}）：{sp}"
        if strict:
            raise _StateCorrupt(msg)
        print(f"⚠ {msg}，按空状态处理", file=sys.stderr)
        return {}


class _StateCorrupt(Exception):
    """task_state.json 损坏：写入路径必须拒绝（保留损坏文件供人工修）。"""


class _TaskIdConflict(Exception):
    """task_id 比对不一致：立即停止推进 + 显式报警（不得静默接受他人 task_id）。"""


def _atomic_write_json(path, obj):
    """原子写 JSON：同目录临时文件 → fsync → os.replace 覆盖。

    为什么必须原子：裸 open(path,"w") 先截断文件，进程被杀 / 磁盘满 / 并发读到
    中间态时，磁盘上留下半截 JSON → 解析失败 → 状态被当空状态处理（= 静默重置）。
    os.replace 在同一文件系统内是原子的，读者要么看到旧版要么看到新版。
    （与 Loop B 侧 _write_loop_state 同一实现，两处不再各写一套。）
    """
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".taskstate.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())      # 落盘缓冲，避免 replace 后仍丢数据
        os.replace(tmp, path)        # 同目录 → 原子替换
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def _task_id_ledger_path(w):
    """task_id 台账（旁挂）：<workspace>/.workbuddy/task_state.taskid。

    为什么需要台账（v3.17.0）：文档承诺"写入前原子比对 task_id"，但状态文件里的
    task_id **本身可被手改**——只跟磁盘里的自己比，比的是"改过之后的自己"。
    实测：把文件里的 task_id 改成 t-DIFFERENT-PROCESS 后 `state set --stage 2`
    无告警、exit 0、直接推进。台账在首次写入时落盘、之后只读，成为 task_id 的
    **不随状态文件一起被改写**的锚点。
    ⚠ 诚实边界：台账挡的是"手改状态文件里的 task_id"，**不是**有写权限的恶意攻击者
    （同时改掉台账仍可绕过）——本项是防误操作与并发串台，不是防攻击者。
    """
    return os.path.join(os.path.dirname(state_path(w)), "task_state.taskid")


def _read_task_id_ledger(w):
    """读 task_id 台账；不存在返回 None，**损坏则抛错**（fail-closed，不得静默失效）。"""
    p = _task_id_ledger_path(w)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return (d or {}).get("task_id")
    except Exception as e:
        raise _TaskIdConflict(
            f"task_id 台账损坏（{e}）：{p}——无法确认任务归属，拒绝写入"
            f"（fail-closed：台账读不到就不能保证 task_id 比对有效）")


def _assert_task_id(w, new_state, expect_task_id=None, reset_ledger=False):
    """写入前的 **task_id 原子比对**（文档承诺的并发防护，v3.17.0 真正落地）。

    比对三处：台账锚点 / 磁盘上的 task_state.json / 本次操作携带的 task_id。
    任一不一致 → 抛 _TaskIdConflict：调用方必须立即停止推进 + 显式报警 + 非 0 退出。
    """
    path = state_path(w)
    if reset_ledger:
        # `state init` = 显式重建任务：新 task_id 取代旧锚点（台账随之重置）。
        # 此时不做任何比对——否则"重建任务"反而会被上一轮任务的台账挡住。
        # ⚠ 调用方（cmd_state init）负责先把损坏的旧状态文件备份留证。
        return {"ledger": None, "disk_task_id": None, "new_task_id":
                (new_state or {}).get("task_id"), "reset": True}
    ledger = _read_task_id_ledger(w)          # 损坏 → 抛错（fail-closed）
    disk = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                disk = json.load(f)
        except Exception as e:
            raise _StateCorrupt(f"task_state.json 解析失败（{e}）：{path}")
    disk_tid = disk.get("task_id") if isinstance(disk, dict) else None
    new_tid = (new_state or {}).get("task_id") if isinstance(new_state, dict) else None
    if expect_task_id and disk_tid and str(expect_task_id) != str(disk_tid):
        raise _TaskIdConflict(
            f"本次操作携带的 task_id={expect_task_id!r} 与状态文件里的 {disk_tid!r} "
            f"不一致——可能是在操作别人的任务，拒绝推进")
    if ledger and disk_tid and str(ledger) != str(disk_tid):
        raise _TaskIdConflict(
            f"状态文件里的 task_id={disk_tid!r} 与台账锚点 {ledger!r} 不一致——"
            f"task_state.json 的 task_id 被改写（并发防护命中），拒绝推进")
    if ledger and new_tid and str(ledger) != str(new_tid):
        raise _TaskIdConflict(
            f"本次写入的 task_id={new_tid!r} 与台账锚点 {ledger!r} 不一致——"
            f"不得改写 task_id（除非 `state init` 显式重建任务）")
    if not ledger and disk_tid:
        print(f"⚠ task_id 台账缺失（老版本遗留？）——以状态文件现有 task_id={disk_tid!r} "
              f"为锚点落台账；此后 task_id 被改写即会被拦下", file=sys.stderr)
    return {"ledger": ledger, "disk_task_id": disk_tid, "new_task_id": new_tid}


def write_state(w, st, locked=False, expect_task_id=None, reset_ledger=False):
    """写 task_state.json：原子写 + 文件锁 + task_id 原子比对（v3.17.0）。

    v3.17.0 前是裸 open(path,"w")：无临时文件、无 fsync、无 os.replace、无 task_id
    比对、无锁——而文档（agents/vet-med-ppt-team-team-lead.md:218、
    references/sop-stages.md:153）明确承诺"写入前原子比对 task_id，不一致立即停止
    推进并报警"。**同一份代码里两套标准**（Loop B 侧的 _write_loop_state 早就做了
    原子写 + _StateLock）。现在统一到同一套标准。

    ⚠ 失败一律**抛异常**（_TaskIdConflict / _StateCorrupt），由调用方转成
      "显式报警 + 非 0 退出"——绝不允许"写不下去就当没这回事"。
    """
    path = state_path(w)

    def _do():
        info = _assert_task_id(w, st, expect_task_id=expect_task_id,
                               reset_ledger=reset_ledger)
        _atomic_write_json(path, st)
        # 台账：首次写入 / 显式重建任务时落盘（锚点只认第一次或重建）
        if st.get("task_id") and (info.get("ledger") is None or info.get("reset")):
            _atomic_write_json(_task_id_ledger_path(w),
                               {"task_id": st["task_id"], "written_at": now_iso()})

    if locked:
        _do()
    else:
        with _StateLock(w, None, path=path + ".lock"):
            _do()


# ─────────────────────────── preflight ───────────────────────────
def cmd_preflight(args):
    """开工前成员可用性预检：把"静默降级"变成"显式告警"。"""
    cfg, ok = load_cfg()
    members = cfg.get("members", {})
    fb = cfg.get("fallback", {})
    w = wkspace(args)
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
    # v3.17.0 B3-2：preflight 事件（此前 yaml 声明了它却零产出）+ 对**已发生的降级**
    #   逐个补 degrade 事件——"成员被平台回落成 general-purpose"就是静默降级的本体，
    #   preflight 是机器唯一能抓到它的时点（抓到即留痕，不靠人自觉申报）。
    _trace(w, cfg, "preflight", "team-lead",
           {"team": args.team, "verdict": report["verdict"],
            "members": {m: v.get("status") for m, v in report["members"].items()},
            "degraded": bad})
    for mid in bad:
        spec = members.get(mid) or {}
        item = report["members"][mid]
        _trace(w, cfg, "degrade", mid,
               {"member_id": mid, "degrade_channel": spec.get("fallback"),
                "reason": ("成员 MD 缺失" if item.get("status") == "missing_md"
                           else f"平台登记 agentType={item.get('agent_type')!r} ≠ 成员 id"
                                f"（成员人格/红线未注入 = 静默降级）"),
                "detected_by": "preflight", "task_id": getattr(args, "task_id", "") or "",
                "disclosure_required": bool(fb.get("require_disclosure", True))})

    # ── v3.19.0：外部通道探针（维度 10/11/13）────────────────────
    # 此前 preflight **只查成员**（agentType 是否被平台回落），**不查任何外部通道**
    #   ⇒ Ima 凭据缺失、库不可达、MCP 未登记等状态**无人报告**（静默降级的老毛病）。
    # 探针异常**不崩 preflight**（preflight 是开工前预检，不能因探针挂了就开不了工）：
    #   探针失败 ⇒ verdict 标 degraded + 告警，按降级路径处置。
    if getattr(args, "probe_channels", False):
        report["channels"] = {"status": "skipped"}
        try:
            sys.path.insert(0, HERE)
            import probe_channels as _pc
            _cfg, _err = _pc._load_yaml(_pc.PKG / "config" / "external-tools.yaml")
            if _err:
                report["channels"] = {"status": "unavailable", "detail": _err}
                report["verdict"] = "degraded"
                print(f"⚠ 外部通道探针不可用：{_err}", file=sys.stderr)
            else:
                _probe = _pc.probe_channels(_cfg, getattr(args, "domain", "") or "")
                report["channels"] = _probe
                # 落 task_state.json#tool_probe_results（该键已在 state_allowed_keys 白名单内）
                try:
                    sp = os.path.join(os.path.abspath(w), ".workbuddy", "task_state.json")
                    os.makedirs(os.path.dirname(sp), exist_ok=True)
                    st = {}
                    if os.path.isfile(sp):
                        with open(sp, encoding="utf-8") as f:
                            st = json.load(f)
                    if not isinstance(st, dict):
                        st = {}
                    st.setdefault("task_id", getattr(args, "task_id", "") or "adhoc")
                    st.setdefault("workflow", "WF-1")
                    st.setdefault("current_stage", 0)
                    st["tool_probe_results"] = _probe
                    tmp = sp + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(st, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, sp)
                except Exception as e:
                    print(f"⚠ 探针结果落盘失败（{e}）——不影响 preflight 结论", file=sys.stderr)
                if _probe.get("scope_mismatches"):
                    report["verdict"] = "degraded"
                _sugg = _probe.get("replace_suggestions") or []
                if _sugg:
                    print("", file=sys.stderr)
                    print("── 外部通道主动提醒（可配置/可更换）──", file=sys.stderr)
                    for s in _sugg:
                        print(f"  [{s.get('severity')}] {s.get('target')}：{s.get('detail')}",
                              file=sys.stderr)
        except Exception as e:
            report["channels"] = {"status": "error", "detail": str(e)[:200]}
            report["verdict"] = "degraded"
            print(f"⚠ 外部通道探针异常（{e}）——按降级路径处置，不得静默",
                  file=sys.stderr)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if bad else 0


# ─────────────────────────── route ───────────────────────────
def cmd_route(args):
    """确定性路由：复杂度 → spawn 计划（不再靠主理人临场判断）。

    v3.17.0：新增 `--domain <域id>` —— 追加**域坍缩**字段并落盘坍缩产物。
      ⚠ **除新增 `spawn_policy` 键外默认行为零变化**：不传 --domain 时，
        追加字段全部在 `if domain_id:` 分支内，plan 的键序不变。
        （`spawn_policy` 是 v3.17.0 批次 B Task#7 的增量，见下。）
      ⚠ **选哪个域是语义判断**——脚本不做关键词选域；域由主理人（LLM）读
        `domain list` 菜单后显式指定。传了不存在的域 id → **显式报错**，
        绝不静默回落默认域（动物医学）。

    v3.17.0 批次 B（Task#7）：**spawn 伪 ID 防线**。
      缘由：`config/harness.yaml#routing.L1/L3` 的 `spawn` 曾是含中文括号的
      说明字符串（如 "pedagogy-architect|dvm-content-expert（按需1-2名）"），
      不是成员 ID 数组——下游若按成员 ID 遍历 spawn 计划，拿到的是**无法解析的伪 ID**。
      修法（三处同时生效，缺一即复发）：
        ① 配置层：spawn 元素改为真 ID 数组；说明语义移到同级 `spawn_policy` 键；
        ② **本函数（执行层）**：spawn 元素逐一对照 `members` 注册表校验，
           命中伪 ID → **显式报错退出（exit 2）**，绝不静默透传；
        ③ 回归层：scripts/test_harness.py 断言四档 spawn 元素全是合法成员 ID。
      ⚠ `spawn_policy` 一并输出到 plan——它是**人读语义**，主理人据此决定
        「按需 1-2 名」到底取哪几个；不输出等于把语义丢在 yaml 里没人看。
    """
    cfg, _ = load_cfg()
    r = cfg.get("routing", {}).get(args.level)
    if not r:
        print(f"用法错误：未知复杂度 {args.level}", file=sys.stderr)
        return 2
    # ── spawn 成员 ID 校验（Task#7：伪 ID 不得静默透传）──────────────
    valid_ids = set((cfg.get("members") or {}).keys())
    spawn = r.get("spawn") or []
    bad = [s for s in spawn if s not in valid_ids]
    if bad:
        print(f"⛔ {args.level}.spawn 含非法成员 ID：{bad}\n"
              f"   合法成员 ID（config/harness.yaml#members 的键）：{sorted(valid_ids)}\n"
              f"   → spawn 元素**只能是成员 ID 本身**；说明性文字请放同级 `spawn_policy` 键"
              f"（如「按需1-2名」），不得塞进 spawn 数组元素。", file=sys.stderr)
        return 2
    plan = {"level": args.level, "team_create": r.get("team_create"),
            "spawn": spawn, "spawn_policy": r.get("spawn_policy"),
            "confirm_gates": r.get("confirm_gates"),
            "red_team": r.get("red_team", False),
            "budgets": cfg.get("budgets", {}),
            "handoff_mode": cfg.get("context", {}).get("handoff_mode")}
    # ── v3.19.0：闸的**并行/串行**语义进 plan（此前 parallel 字段**零消费者**）──
    # 缺陷（第五次从零诊断·维度 2 实测）：`config/harness.yaml#stages` 每闸都声明了
    #   `parallel: yes|no`，但**全包无任何代码读它** ⇒ 该字段是纯声明，
    #   主理人无法从 route 输出看出「本闸成员该同时派还是排队」，
    #   而 stage 1 已因伪并行被改过（v3.17.0 批次 B）——正说明这字段有用却没人用。
    # 处置：把**本次 route 对应的闸**的 parallel 与成员清单写进 plan（消费方 = 主理人）。
    #   ⚠ L0/L1 走 routing 段（不经过 stages 闸），此时 parallel 无意义 → 不输出该键。
    _stages = cfg.get("stages") or {}
    _stage_no = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}.get(str(args.level))
    if _stage_no is not None and str(_stage_no) in _stages:
        _st = _stages[str(_stage_no)] or {}
        plan["stage"] = _stage_no
        plan["stage_name"] = _st.get("name")
        plan["parallel"] = bool(_st.get("parallel", False))
        plan["parallel_members"] = list(_st.get("members") or [])
        plan["parallel_policy"] = (
            "本闸成员**并行**派发（互相无数据依赖）" if _st.get("parallel")
            else "本闸成员**串行**派发（有数据依赖，按 stages 顺序）")
    domain_id = (getattr(args, "domain", None) or "").strip()
    if domain_id:
        # ── v3.17.0：域坍缩（追加域字段 + 落盘坍缩产物）─────────────────
        profiles, err = load_domain_profiles(cfg)
        if err:
            print(f"⛔ {err}\n   域档案不可用时**不得**回落任何域（含默认域）——"
                  f"请修复 {config/domain-profiles.yaml} 或去掉 --domain。", file=sys.stderr)
            return 3
        dom = find_domain(profiles, domain_id)
        if not dom:
            ids = ", ".join(str(x.get("id")) for x in (profiles.get("domains") or [])
                             if isinstance(x, dict))
            print(f"⛔ 未知域 id：{domain_id!r}\n"
                  f"   可用域：{ids}\n"
                  f"   → **不回落任何域**（尤其不回落默认域）：域的选择是语义判断，"
                  f"由主理人读 `domain list` 菜单后显式指定。", file=sys.stderr)
            return 2
        # ── v3.18.0：panel 选人合法性**先于落盘**校验（不落半成品）──
        _sel, _sel_status, _sel_err = _select_experts(dom, getattr(args, "panel", "") or "")
        if _sel_err:
            print(f"⛔ {_sel_err}\n"
                  f"   → 专家 id 必须是该域 expert_panel 里的真 id；"
                  f"脚本**不按关键词自动选人**（选谁是语义判断，属主理人职责）。",
                  file=sys.stderr)
            return 2
        path, payload, _created = _write_collapse_artifact(cfg, dom, args)
        status = payload.get("status")
        c = _collapse_cfg(cfg)
        pending = c.get("pending_status") or "pending_confirmation"
        confirmed = c.get("confirmed_status") or "confirmed"
        effective = bool(payload.get("effective")) and status == confirmed
        plan["domain"] = dom.get("id")
        plan["domain_profile_path"] = _domain_profiles_path(cfg)
        plan["role_persona"] = dom.get("role_persona")
        # ── v3.18.0：专家面板进 plan（供主理人输出给用户对齐）──────────
        panel_pool = payload.get("expert_panel") or []
        selected = payload.get("selected_experts") or []
        plan["expert_panel_pool"] = [
            {"id": e.get("id"), "title": e.get("title"),
             "coverage_axes": e.get("coverage_axes") or []}
            for e in panel_pool if isinstance(e, dict)
        ]
        plan["selected_experts"] = [
            {"id": e.get("id"), "title": e.get("title"),
             "duty_boundary": e.get("duty_boundary")}
            for e in selected if isinstance(e, dict)
        ]
        # 选人状态：explicit=已指定；pending_selection=该域有面板但尚未选人（待用户裁决）
        plan["expert_selection_status"] = (
            "explicit" if selected else
            ("pending_selection" if panel_pool else "no_pool"))
        if panel_pool and not selected:
            plan["expert_selection_note"] = (
                f"该域有 {len(panel_pool)} 位可选子专家，**尚未选人**——"
                f"请按主题从下列 id 中挑选后执行 "
                f"`route --level {args.level} --domain {domain_id} --panel <id1,id2>`；"
                f"**未选人时不得进入确认流程**（确认的必须是具体的人选配置）。")
        plan["collapse_artifact"] = path
        plan["collapse_status"] = status
        plan["collapse_effective"] = effective
        plan["collapse_note"] = ("已确认，已生效" if effective
                                 else "待确认，未生效（须经 `collapse confirm` 确认后域人格方可生效）")
        plan["collapse_confirmation_required"] = bool(c.get("require_user_confirmation", True))
        plan["selection_rationale_status"] = payload.get("selection_rationale_status")
    # v3.17.0 B3-2：team_create 事件（yaml 声明了它却零产出）。
    #   路由判出"本任务要建队"是建队的**决策时点**——机器唯一知道
    #   "这次任务是否真的建队、派了哪些人"的地方。L0 不建队 → 不写事件
    #   （写了就是假事件：声明了却没建队，正是本任务要治的病）。
    if r.get("team_create"):
        _trace(wkspace(args), cfg, "team_create", "team-lead",
               {"level": args.level, "spawn": spawn,
                "spawn_policy": r.get("spawn_policy"),
                "confirm_gates": r.get("confirm_gates"),
                "red_team": bool(r.get("red_team", False)),
                "task_id": getattr(args, "task_id", "") or "",
                "domain": plan.get("domain")})
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


# ───────────────────── 域档案 / 坍缩（v3.17.0）────────────────────
# 域档案唯一数据源 = config/domain-profiles.yaml（路径取自 harness.yaml#collapse.profile_file）。
#
# 分工宪法（**最重要的一条**）：
#   · **选哪个域 = 语义判断** → 由主理人（LLM）读 `domain list` 菜单后显式指定；
#     本文件**严禁**用 match_hints / 关键词 / 正则 / 打分自动选域（那是规则匹配偏见）。
#   · 脚本只做确定性事务：读档案、组装、落盘、校验状态——**不猜、不判断语义**。
_DOMAIN_PROFILES_REL = "config/domain-profiles.yaml"
_EXTERNAL_TOOLS_REL = "config/external-tools.yaml"   # v3.19.1：外部工具唯一源


def _external_tools_path(cfg=None):
    """外部工具配置路径（**唯一源**：config/external-tools.yaml）。

    与 _domain_profiles_path 同模式：路径可由 yaml 覆盖（默认固定相对路径）。
    """
    rel = ((cfg or {}).get("collapse") or {}).get("external_tools_file") \
        or _EXTERNAL_TOOLS_REL
    return os.path.join(PKG, rel)


def _domain_knowledge_bases(cfg, domain_id):
    """取**归属该域**的 Ima 知识库路由（v3.19.1·S1）。

    缺陷（第六次从零诊断·S1 · 实测证据）：
      v3.19.0 把 7 个 Ima 库从 domain-profiles.yaml 迁到 config/external-tools.yaml，
      但**坍缩快照仍从域档案取**（`dom.get("knowledge_bases")`）⇒ 迁移后恒为空列表
      ⇒ 装配器渲染「本域无账号内知识库」——**与事实相反**（animal-medicine 有 7 个库），
      且与同屏的「见 external-tools.yaml」说明自相矛盾。
      ⇒ 快照层必须改从唯一源 external-tools.yaml 取，并**按 owner_scope 过滤**到本域。

    返回 (库列表, 说明字符串)：
      · 库列表 = owner_scope == domain_id 的库（无匹配则空列表——**正确**：
        computing / business-training 本就没有账号内库）
      · 说明 = 读取失败/未找到域时的告警文案（空串表示正常）
    """
    path = _external_tools_path(cfg)
    if not os.path.isfile(path):
        return [], f"外部工具配置缺失：{path}——知识库路由无法装载"
    try:
        import yaml as _yaml
        with open(path, encoding="utf-8") as f:
            data = _yaml.safe_load(f)
    except Exception as e:
        return [], f"外部工具配置读取失败：{e}——知识库路由无法装载"
    if not isinstance(data, dict):
        return [], "外部工具配置格式异常——知识库路由无法装载"
    kbs = data.get("knowledge_bases") or []
    mine = []
    for kb in kbs:
        if not isinstance(kb, dict):
            continue
        scope = str(kb.get("owner_scope") or "")
        if not scope or scope == domain_id:
            mine.append(kb)
    return mine, ""


def _domain_profiles_path(cfg=None):
    rel = ((cfg or {}).get("collapse") or {}).get("profile_file") or _DOMAIN_PROFILES_REL
    return os.path.join(PKG, rel)


def load_domain_profiles(cfg=None):
    """读域档案。返回 (data, err)；err 非 None = 不可用。

    失败一律**显式报错**，不回落任何域（尤其不得静默回落动物医学域）——
    "显式失败"优于"静默跑偏"。域 id 缺失/重复也判非法（否则选域会指向歧义目标）。
    """
    path = _domain_profiles_path(cfg)
    try:
        import yaml  # noqa
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return None, f"域档案读取失败（{e}）：{path}"
    if not isinstance(data, dict):
        return None, f"域档案格式非法（顶层须是映射）：{path}"
    doms = data.get("domains")
    if not isinstance(doms, list) or not doms:
        return None, f"域档案格式非法（domains 须是非空列表）：{path}"
    ids = []
    for d in doms:
        if not isinstance(d, dict) or not str(d.get("id") or "").strip():
            return None, f"域档案格式非法（有域缺 id）：{path}"
        ids.append(str(d.get("id")))
    if len(set(ids)) != len(ids):
        return None, f"域档案格式非法（域 id 重复：{ids}）：{path}"
    return data, None


def find_domain(profiles, domain_id):
    """按 id 取域档案；取不到返回 None（**调用方必须显式报错，不得回落**）。"""
    for d in (profiles or {}).get("domains") or []:
        if isinstance(d, dict) and str(d.get("id")) == str(domain_id):
            return d
    return None


def _collapse_cfg(cfg):
    return (cfg or {}).get("collapse") or {}


def cmd_domain(args):
    """v3.17.0：域档案菜单（list）与详情（show）——**给主理人（LLM）看的选域入口**。

    ⚠ 本命令**不做任何自动匹配**：`match_hints` 是给人读的线索菜单，
      脚本不据此选域（分工宪法：面向内容语义的判断归 LLM）。
    """
    cfg, _ = load_cfg()
    profiles, err = load_domain_profiles(cfg)
    if err:
        print(f"⛔ {err}", file=sys.stderr)
        return 3
    ppath = _domain_profiles_path(cfg)
    if args.action == "list":
        items = []
        for d in profiles.get("domains") or []:
            ka = d.get("knowledge_anchor")
            ka_path = ka.get("path") if isinstance(ka, dict) else ka
            items.append({
                "id": d.get("id"),
                "display_name": d.get("display_name"),
                "match_hints": d.get("match_hints") or [],
                "knowledge_anchor": ka_path,
                "knowledge_anchor_present": bool(ka_path),
                "knowledge_anchor_note": (ka.get("note") if isinstance(ka, dict) else None),
            })
        print(json.dumps({
            "profile_file": ppath,
            "default_domain": profiles.get("default_domain"),
            "usage": "这是**给主理人（LLM）看的选域菜单**——脚本不自动选域；"
                     "选定后用 `route --level <L> --domain <id>` 落盘坍缩产物，"
                     "并须经 `collapse confirm` 确认后域人格方可生效。",
            "domains": items,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.action == "show":
        d = find_domain(profiles, args.id)
        if not d:
            ids = ", ".join(str(x.get("id")) for x in (profiles.get("domains") or [])
                             if isinstance(x, dict))
            print(f"⛔ 未知域 id：{args.id!r}。可用域：{ids}", file=sys.stderr)
            return 2
        print(json.dumps({"profile_file": ppath, "domain": d,
                          "fallback": profiles.get("fallback") or {}},
                         ensure_ascii=False, indent=2))
        return 0
    return 2


def _run_dir(workspace, task_id):
    """RUN_DIR 约定 = <workspace>/.harness-runs/<task_id>（见 references/spawn-protocol.md#二）。

    坍缩产物与成员检索单（`_search_requests/`）同在 RUN_DIR 下、同级分目录，
    保证"一次任务的所有中间产物"在一处、且不散落进用户课件目录。
    """
    return os.path.join(os.path.abspath(workspace), ".harness-runs", str(task_id))


def _collapse_artifact_path(cfg, workspace, task_id, domain_id):
    c = _collapse_cfg(cfg)
    d = os.path.join(_run_dir(workspace, task_id), c.get("artifact_dir") or "_collapse")
    tpl = c.get("artifact_name_template") or "collapse_{task_id}_{domain_id}.json"
    return os.path.join(d, tpl.format(task_id=task_id, domain_id=domain_id))


def _resolve_task_id(args, workspace):
    """task_id 取值顺序：--task-id > task_state.json 的 task_id > adhoc。"""
    tid = (getattr(args, "task_id", "") or "").strip()
    if tid:
        return tid
    try:
        st = read_state(workspace, strict=False)
        if isinstance(st, dict) and st.get("task_id"):
            return str(st["task_id"])
    except Exception:
        pass
    return "adhoc"


def _select_experts(dom, panel_arg):
    """按主理人指定的 id 列表，从域档案的 expert_panel 池里挑出本次坍缩的子专家。

    ⚠ **分工宪法**：脚本**只装配/校验**，不按关键词/activation_hints 自动选人
      （选谁是语义判断，属主理人职责）——因此：
      · 传了 ids → 按 id 精确取（取不到就报错，由 cmd_route 拦截）
      · 没传 ids → **不自动选**：返回空列表 + 状态 "pending_selection"，
        交由主理人裁决后用 `--panel` 重跑 route（避免"脚本替用户做专家选型"）。

    返回 (selected, status, error)：
      selected = 选中的专家条目列表（完整字段，供装配器注入）
      status   = "explicit" | "pending_selection" | "no_pool"
      error    = 非法 id 时的说明（None 表示无错）
    """
    pool = [e for e in (dom.get("expert_panel") or []) if isinstance(e, dict)]
    ids = [s.strip() for s in str(panel_arg or "").replace("，", ",").split(",") if s.strip()]
    if not pool:
        # 该域没有专家池 → 保持 v3.17.0 行为（单人格）
        return [], "no_pool", None
    if not ids:
        return [], "pending_selection", None
    by_id = {str(e.get("id")): e for e in pool if e.get("id")}
    bad = [i for i in ids if i not in by_id]
    if bad:
        return [], "invalid_selection", (
            f"未在域档案 expert_panel 中找到专家 id：{bad}；"
            f"该域可用 id：{sorted(by_id)}")
    selected = [by_id[i] for i in ids]
    return selected, "explicit", None


def _collapse_artifact_payload(cfg, dom, task_id, rationale, artifact_path, panel_arg=""):
    """组装坍缩产物（**只组装，不判断**）。

    · 选型理由由主理人（LLM）填（--rationale）；未填 → null + 状态"待补"，
      **脚本不猜**（猜出来的理由等于没对齐）。
    · 各成员的域匹配说明取自域档案的 member_bindings（**声明式**，不是脚本推断）；
      主理人的补充说明留 confirmed_note 待确认时补写。
    """
    c = _collapse_cfg(cfg)
    members = cfg.get("members") or {}
    bindings = {}
    for b in (dom.get("member_bindings") or []):
        if isinstance(b, dict) and b.get("member"):
            bindings[str(b.get("member"))] = b
    mm = []
    for mid, spec in members.items():
        b = bindings.get(str(mid)) or {}
        mm.append({
            "member": mid,
            "duty": (spec or {}).get("duty"),
            "binding": b.get("binding") or "unspecified",
            "domain_match_note": b.get("note"),
            "confirmed_note": None,      # 主理人确认时补写
        })
    for mid, b in bindings.items():
        if mid not in members:
            mm.append({"member": mid, "duty": None,
                       "binding": b.get("binding"),
                       "domain_match_note": b.get("note"),
                       "confirmed_note": None,
                       "warning": "该成员 id 未登记在 config/harness.yaml#members"})
    _kb_list, _kb_warn = _domain_knowledge_bases(cfg, dom.get("id"))
    return {
        "schema": "collapse-artifact/1",
        "created_at": now_iso(),
        "task_id": task_id,
        "domain_id": dom.get("id"),
        "domain_display_name": dom.get("display_name"),
        "domain_profile_path": _domain_profiles_path(cfg),
        "status": c.get("pending_status") or "pending_confirmation",
        "effective": False,
        "confirmed_at": None,
        "confirmed_by": None,
        "selection_rationale": rationale,
        "selection_rationale_status": "filled" if rationale else "pending_team_lead",
        "role_persona": dom.get("role_persona"),
        "role_persona_status": "proposed_pending_confirmation",
        # ── v3.18.0：专家面板（坍缩出**多名**资深专家）────────────────
        # 缘由（2026-10-25 从零诊断 G1）：规格要求「按主题/模块（如禽流感→禽流感病毒学家
        #   +禽病学家）**动态坍缩生成匹配的资深专家团队**」，
        #   但此前坍缩产物只带**单个** role_persona，成员集恒为同一批 5 人
        #   ⇒「坍缩出专家团」在数据结构与代码路径上都不存在。
        # 语义分工：
        #   · expert_panel          = 该域**可选的子专家池**（声明式，取自域档案）
        #   · selected_experts      = 本次坍缩**实际选中的子专家**（主理人指定）
        #   · role_persona          = 域级**底座人格**（保留：上场者共守的底线与风格）
        # 向后兼容：域档案无 expert_panel 时，expert_panel=[]、selected_experts=[]，
        #   装配行为与 v3.17.0 完全一致（单人格）。
        "expert_panel": dom.get("expert_panel") or [],
        "selected_experts": _select_experts(dom, panel_arg)[0],
        "content_axes": dom.get("content_axes") or [],
        "evidence_hierarchy": dom.get("evidence_hierarchy") or {},
        "image_channel": dom.get("image_channel") or {},
        # v3.19.1·S1：知识库路由改从**唯一源** external-tools.yaml 取并按域过滤
        #   （此前从域档案取，v3.19.0 迁移后恒为空 ⇒ 装配器误渲染「本域无知识库」）
        "knowledge_bases": _kb_list,
        # ⚠ v3.19.1·S1 审计修正：**不得**硬编码为 #knowledge_bases——
        #   computing / business-training 的库路由指针本就是 #domains_without_knowledge_bases
        #   （域档案 knowledge_bases_ref 逐域不同）。硬编码会让装配器把
        #   「本域本就无库」误判成「本域应有库却没装上」⇒ 报假警。
        #   ⇒ 取域档案自己的指针（域语义，**唯一源**仍指 external-tools.yaml）。
        "knowledge_bases_ref": dom.get("knowledge_bases_ref")
                               or "config/external-tools.yaml#knowledge_bases",
        # ⚠ **不覆盖**域档案的 knowledge_bases_note（那是域语义说明）——
        #   装载告警另存独立键，避免两个来源互相覆盖（本项目核心忌讳：一份口径两处写）
        "knowledge_bases_load_warning": _kb_warn or None,
        # v3.19.1·S1：交付语言 + 域级术语表（v3.19.0 新增，此前未进快照 ⇒ 成员拿不到词条）
        "glossary": dom.get("glossary") or [],
        "delivery_language": dom.get("delivery_language") or "zh-CN",
        "language_profile_ref": "config/language-profile.yaml",
        "terminology": dom.get("terminology") or [],
        "safety_redlines": dom.get("safety_redlines") or [],
        "knowledge_anchor": dom.get("knowledge_anchor"),
        "member_domain_match": mm,
        "gate1_freeze_item": "collapsed_team_config",
        "confirm_command": c.get("confirm_command")
                          or "python3 scripts/harness.py collapse confirm --id <域id> --task-id <task_id>",
        "notes": [
            "本产物为**待确认态**：域人格（role_persona）**尚未生效**。",
            "确认命令见 confirm_command；**沉默不构成确认**，须由主理人显式执行。",
            "选型理由（selection_rationale）由主理人填写，脚本不猜。",
        ],
    }


def _write_collapse_artifact(cfg, dom, args):
    """落盘坍缩产物；返回 (path, payload, created)。

    已确认的产物**不覆盖**：确认是用户裁决，不能被再次 route 悄悄打回待确认态。
    """
    c = _collapse_cfg(cfg)
    w = wkspace(args)
    tid = _resolve_task_id(args, w)
    path = _collapse_artifact_path(cfg, w, tid, dom.get("id"))
    rationale = (getattr(args, "rationale", "") or "").strip()
    confirmed_status = c.get("confirmed_status") or "confirmed"
    old = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = None
    if isinstance(old, dict) and old.get("status") == confirmed_status:
        return path, old, False
    payload = _collapse_artifact_payload(cfg, dom, tid, rationale, path,
                                        getattr(args, "panel", "") or "")
    if isinstance(old, dict):
        # 沿用此前已填的选型理由（本次未显式提供时不抹掉）
        if not rationale and old.get("selection_rationale"):
            payload["selection_rationale"] = old["selection_rationale"]
            payload["selection_rationale_status"] = (old.get("selection_rationale_status")
                                                      or "filled")
        payload["created_at"] = old.get("created_at") or payload["created_at"]
        payload["updated_at"] = now_iso()
    _atomic_write_json(path, payload)
    return path, payload, True


def cmd_collapse(args):
    """v3.17.0：坍缩产物的落盘查询与**用户确认**（确认前域人格不生效）。

    契约（规格原文：「坍缩结果须主动输出并与我对齐、**经确认后生效**」）：
      · `route --domain <id>` 落盘**待确认**产物；
      · `collapse confirm --id <id> --task-id <tid>` 才把状态改为 confirmed / effective=true；
      · 确认**要求已填选型理由**（脚本不猜理由；没有理由的确认等于没对齐）。
    """
    cfg, _ = load_cfg()
    c = _collapse_cfg(cfg)
    w = wkspace(args)
    if not c.get("enabled", True):
        print("ℹ 坍缩已禁用（config/harness.yaml#collapse.enabled=false），跳过")
        return 0

    if args.action == "list":
        root = os.path.join(os.path.abspath(w), ".harness-runs")
        items = []
        if os.path.isdir(root):
            for tid in sorted(os.listdir(root)):
                d = os.path.join(root, tid, c.get("artifact_dir") or "_collapse")
                if not os.path.isdir(d):
                    continue
                for fn in sorted(os.listdir(d)):
                    if not fn.endswith(".json"):
                        continue
                    fp = os.path.join(d, fn)
                    try:
                        with open(fp, encoding="utf-8") as f:
                            obj = json.load(f)
                    except Exception:
                        continue
                    items.append({
                        "domain_id": obj.get("domain_id"),
                        "task_id": obj.get("task_id") or tid,
                        "status": obj.get("status"),
                        "effective": bool(obj.get("effective")),
                        "selection_rationale_status": obj.get("selection_rationale_status"),
                        "path": fp,
                    })
        print(json.dumps({"root": root, "count": len(items), "artifacts": items},
                         ensure_ascii=False, indent=2))
        return 0

    if args.action == "show":
        tid = _resolve_task_id(args, w)
        profiles, err = load_domain_profiles(cfg)
        if err:
            print(f"⛔ {err}", file=sys.stderr)
            return 3
        dom = find_domain(profiles, args.id)
        if not dom:
            print(f"⛔ 未知域 id：{args.id!r}", file=sys.stderr)
            return 2
        path = _collapse_artifact_path(cfg, w, tid, dom.get("id"))
        if not os.path.exists(path):
            print(f"⛔ 未找到坍缩产物：{path}\n"
                  f"   → 先执行 `route --level <L> --domain {dom.get('id')} --task-id {tid}` 生成待确认产物。",
                  file=sys.stderr)
            return 1
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        # ── v3.18.0：输出**用户对齐摘要**（"谁上场、各管哪块、为什么是他"）──
        # 规格：「坍缩结果须**先输出**并与我对齐」——只 dump 原始 JSON 不够，
        #   主理人需要一份可直接念给用户听的摘要（含未选人提示）。
        sel = obj.get("selected_experts") or []
        pool = obj.get("expert_panel") or []
        summary = {
            "domain_id": obj.get("domain_id"),
            "domain_display_name": obj.get("domain_display_name"),
            "status": obj.get("status"),
            "effective": obj.get("effective"),
            "selected_experts": [
                {"id": e.get("id"), "title": e.get("title"),
                 "coverage_axes": e.get("coverage_axes") or [],
                 "duty_boundary": e.get("duty_boundary")}
                for e in sel if isinstance(e, dict)
            ],
            "expert_panel_pool": [
                {"id": e.get("id"), "title": e.get("title")}
                for e in pool if isinstance(e, dict)
            ],
            "selection_rationale": obj.get("selection_rationale"),
            "confirmed_by": obj.get("confirmed_by"),
            "confirmed_decision": obj.get("confirmed_decision"),
            "confirmed_at": obj.get("confirmed_at"),
        }
        print("── 坍缩结果摘要（供与用户对齐）──")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if pool and not sel:
            print("\n⚠️ 该域有专家面板但**尚未选人**——本次坍缩未指定谁上场。")
            print(f"   可选 id：{[e.get('id') for e in pool if isinstance(e, dict)]}")
            print("   → 选人后重跑 `route --level <L> --domain <id> --panel <id1,id2>`；"
                  "未选人不得进入确认流程。")
        print("\n── 坍缩产物全文 ──")
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return 0

    if args.action == "confirm":
        tid = _resolve_task_id(args, w)
        profiles, err = load_domain_profiles(cfg)
        if err:
            print(f"⛔ {err}", file=sys.stderr)
            return 3
        dom = find_domain(profiles, args.id)
        if not dom:
            print(f"⛔ 未知域 id：{args.id!r}", file=sys.stderr)
            return 2
        path = _collapse_artifact_path(cfg, w, tid, dom.get("id"))
        if not os.path.exists(path):
            print(f"⛔ 未找到待确认的坍缩产物：{path}\n"
                  f"   → 先执行 `route --level <L> --domain {dom.get('id')} --task-id {tid}`。",
                  file=sys.stderr)
            return 1
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        rationale = (getattr(args, "rationale", "") or "").strip() or (obj.get("selection_rationale") or "")
        if not rationale:
            print("⛔ 拒绝确认：选型理由（selection_rationale）为空。\n"
                  "   理由由**主理人**提供（脚本不猜）——请用 `--rationale \"<理由>\"` 重新执行。",
                  file=sys.stderr)
            return 1
        # ── v3.18.0：确认必须带**用户裁决语义**（--decision）+ 确认人不得是执行方自己 ──
        # 缺陷（2026-10-25 从零诊断 G2 实测）：此前 `--actor` 默认 "team-lead"，
        #   即「主理人自己确认自己」在代码层畅通无阻，且无任何"用户已阅"字段
        #   ⇒ 事后无法区分「人确认」与「自确认」，规格「经用户确认」无处落地。
        # 对照：Loop B 的 `loop continue` 缺 `--decision` 即 exit 2（沉默不构成确认）——
        #   说明本包别处做得到「强制裁决」，坍缩这条此前没做。
        decision = (getattr(args, "decision", "") or "").strip()
        if not decision:
            print("⛔ 拒绝确认：缺少 `--decision`（用户裁决语义）。\n"
                  "   规格要求「坍缩结果须先输出并与我对齐、**经确认后生效**」——"
                  "沉默不构成确认（与 `loop continue --decision` 同一纪律）。\n"
                  "   → 用 `--decision <裁决>` 重新执行，例："
                  "`--decision \"用户已阅并确认该专家团配置\"`。",
                  file=sys.stderr)
            return 2
        actor = (getattr(args, "actor", "") or "").strip()
        if not actor:
            print("⛔ 拒绝确认：未指定确认人（`--actor` 为空）。\n"
                  "   → 请显式传 `--actor user`（或真实裁决人标识）。\n"
                  "   理由：确认人不可缺省，否则事后无法区分「人确认」与「自确认」。",
                  file=sys.stderr)
            return 2
        if actor == "team-lead":
            print("⛔ 拒绝确认：`--actor team-lead` 是执行方自己，不构成「用户确认」。\n"
                  "   → 请用 `--actor user`（或真实裁决人标识）重新执行。\n"
                  "   理由：确认人是执行方 ⇒ 事后无法区分「人确认」与「自确认」。",
                  file=sys.stderr)
            return 2
        # ── v3.18.0：该域有专家池但**尚未选人** → 不得确认 ──────────
        # 规格：「坍缩出**匹配的资深专家团队**」——确认的必须是**具体的人选配置**，
        #   而不是"确认了一个域"。未选人就确认 = 确认了一个空配置。
        _pool = obj.get("expert_panel") or []
        _sel = obj.get("selected_experts") or []
        if _pool and not _sel:
            ids = [e.get("id") for e in _pool if isinstance(e, dict) and e.get("id")]
            print("⛔ 拒绝确认：该域有专家面板但**尚未选人**（selected_experts 为空）。\n"
                  f"   可选专家 id：{ids}\n"
                  "   → 先按主题选人并重新落盘："
                  f"`route --level <L> --domain {dom.get('id')} --task-id {tid} "
                  f"--panel <id1,id2>`\n"
                  "   → 理由：确认的必须是**具体的人选配置**，"
                  "「确认了一个域但没定谁上场」等于没对齐。",
                  file=sys.stderr)
            return 1
        confirmed_status = c.get("confirmed_status") or "confirmed"
        obj["status"] = confirmed_status
        obj["effective"] = True
        obj["confirmed_at"] = now_iso()
        obj["confirmed_by"] = actor
        obj["confirmed_decision"] = decision
        obj["selection_rationale"] = rationale
        obj["selection_rationale_status"] = "filled"
        obj["role_persona_status"] = "effective"
        obj.setdefault("notes", []).append(
            f"已由 {obj['confirmed_by']} 于 {obj['confirmed_at']} 确认：域人格生效。")
        _atomic_write_json(path, obj)
        # 镜像进 task_state.json（白名单键 collapse；不在白名单会被静默拒绝）
        # ⚠ 仅当状态文件**已存在**时才镜像：状态文件不存在说明本任务还没 `state init`，
        #   此时凭空造一个只含 collapse 的残状态文件，会让下游 `state validate` 判非法
        #   （缺 task_id / current_stage）——宁可只留产物（产物本身就是生效依据）。
        mirrored = False
        sp = state_path(w)
        if os.path.exists(sp):
            try:
                st = read_state(w, strict=True)
                if isinstance(st, dict):
                    st["collapse"] = {
                        "domain_id": obj.get("domain_id"),
                        "task_id": obj.get("task_id"),
                        "role_persona": obj.get("role_persona"),
                        "selection_rationale": obj.get("selection_rationale"),
                        "status": obj.get("status"),
                        "effective": True,
                        "confirmed_at": obj.get("confirmed_at"),
                        "artifact": path,
                    }
                    write_state(w, st)
                    mirrored = True
            except Exception as e:
                print(f"⚠ 未能镜像进 task_state.json（{e}）——坍缩产物本身已是生效依据。",
                      file=sys.stderr)
        else:
            print(f"ℹ 未发现 task_state.json（{sp}）——本次不镜像状态；"
                  f"坍缩产物本身即生效依据。", file=sys.stderr)
        print(json.dumps({
            "ok": True,
            "domain_id": obj.get("domain_id"),
            "status": obj.get("status"),
            "effective": True,
            "confirmed_at": obj.get("confirmed_at"),
            "artifact": path,
            "state_mirrored": mirrored,
            "gate1_freeze_item": obj.get("gate1_freeze_item"),
        }, ensure_ascii=False, indent=2))
        return 0
    return 2


# ─────────────────────── gate1 冻结清单校验 ───────────────────────
def _language_profile():
    """读 config/language-profile.yaml（PPT 交付语言唯一源）。

    读不到 → 回退**内置最小集**（zh-CN + 术语标注形态），并显式告警
    （不静默：静默回退等于"声明层≠执行层"的老毛病）。
    """
    p = os.path.join(PKG, "config", "language-profile.yaml")
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and data:
            return data, ""
    except Exception as e:
        return ({"default_language": "zh-CN",
                 "terminology": {"format": "中文（English, Abbreviation）"}},
                f"语言规格读取失败（{e}）——已回退内置最小集")
    return ({"default_language": "zh-CN",
             "terminology": {"format": "中文（English, Abbreviation）"}},
            "语言规格为空——已回退内置最小集")


def _delivery_language_state(intake):
    """闸1 第 7 项：交付语言就绪度（维度 6）。

    判据（v3.19.0）：
      ① 语言规格文件可读（有 default_language）；
      ② 交付语言与受众语言**一致性**检查——受众 zh-CN 而交付 en 时报不一致。
         级别取 language-profile.yaml#consistency.mismatch_policy（默认 warn，
         即不阻断：允许给中国学生出英文课件）。
    返回 (ready, detail)。
    """
    spec, warn = _language_profile()
    if warn:
        return False, warn
    default_lang = str(spec.get("default_language") or "zh-CN")
    term = spec.get("terminology") or {}
    fmt = str(term.get("format") or "")
    if not fmt:
        return False, "语言规格缺 terminology.format（术语标注形态未定义）"

    # 受众语言：intake.audience.language（可缺省 → 不判不一致）
    aud = (intake or {}).get("audience") or {}
    aud_lang = ""
    if isinstance(aud, dict):
        aud_lang = str(aud.get("language") or "").strip()
    elif isinstance(aud, str):
        aud_lang = aud.strip()

    cons = spec.get("consistency") or {}
    policy = str(cons.get("mismatch_policy") or "warn")
    detail = f"默认交付语言 {default_lang}；术语标注形态「{fmt}」"
    if aud_lang and aud_lang.lower() != default_lang.lower():
        detail += f"；⚠ 受众语言为 {aud_lang}，与默认交付语言不一致（策略 {policy}）"
        if policy == "block":
            return False, detail
    return True, detail


def _knowledge_channel_state(w):
    """闸1 第 8 项：知识库路由就绪度（维度 10/13）。

    判据（v3.19.0）：
      ① 外部工具配置可读；
      ② 若工作区有探针结果（task_state.json#tool_probe_results）⇒ 读它；
         无探针结果时**不做阻断**（探针是可选的开工前检查，不是闸1 必过项），
         只报"未探测"提示；
      ③ 探针结果里若存在 **scope_mismatch**（库属其他专业）⇒ **阻断**
         （管家节点裁决 #4：不得静默使用其他专业的库）。
    返回 (ready, detail)。
    """
    p = os.path.join(PKG, "config", "external-tools.yaml")
    if not os.path.isfile(p):
        return False, f"外部工具配置缺失：{p}"
    probe = {}
    sp = os.path.join(os.path.abspath(w), ".workbuddy", "task_state.json")
    if os.path.isfile(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                st = json.load(f)
            if isinstance(st, dict) and isinstance(st.get("tool_probe_results"), dict):
                probe = st["tool_probe_results"]
        except Exception:
            probe = {}
    if not probe:
        return True, ("外部工具配置就位；**尚未探测**通道"
                      "（建议开工前跑 `preflight --probe-channels`）")
    mism = probe.get("scope_mismatches") or []
    if mism:
        names = "、".join(str(m.get("library_name") or m.get("library_id")) for m in mism)
        return False, (f"⛔ 知识库属其他专业（{names}）——**不得静默使用**；"
                       f"须提醒用户更换/更新为其所在专业的库")
    unavailable = probe.get("unavailable_channels") or []
    if unavailable:
        return True, (f"外部通道探测：{len(unavailable)} 条不可用"
                      f"（{', '.join(unavailable)}）——须按降级路径处置并向用户声明")
    return True, "外部通道探测全部可用；知识库归属无冲突"


def cmd_gate1_check(args):
    """闸1 冻结清单的**机器校验**（v3.18.0 新增）。

    缺陷（2026-10-25 从零诊断 G2 实测）：`config/harness.yaml#gate1_freeze`
    声明了 6 项必须由用户逐条确认的冻结项，但**全包无任何代码读它**——
    即"该确认的到底确认了没有"完全靠主理人自觉。
    本子命令把该清单变成可校验的判据：
      · audience / hours / template / scope / acceptance —— 取自 Loop B 的 intake；
      · collapsed_team_config —— 取自坍缩产物的确认态（须 confirmed 且 effective）。

    判据来源：config/harness.yaml#gate1_freeze（**唯一源**），本函数只执行不重定义。

    退出码：0=全部就绪可进闸2；1=有未就绪项（阻断）；2=用法错误。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    items = cfg.get("gate1_freeze") or []
    if not items:
        print("⚠ config/harness.yaml#gate1_freeze 为空——闸1 无冻结清单可校验", file=sys.stderr)
        return 2

    # ── 收集各冻结项的就绪状态 ────────────────────────────────────
    # intake 来源：优先 Loop B 状态文件（intake 字段），其次 task_state.json
    intake = {}
    lpath = os.path.join(os.path.abspath(w), ".workbuddy", "loopB_state.json")
    if os.path.isfile(lpath):
        try:
            with open(lpath, encoding="utf-8") as f:
                lb = json.load(f)
            if isinstance(lb, dict) and isinstance(lb.get("intake"), dict):
                intake = lb["intake"]
        except Exception:
            intake = {}
    if not intake:
        tpath = os.path.join(os.path.abspath(w), ".workbuddy", "task_state.json")
        if os.path.isfile(tpath):
            try:
                with open(tpath, encoding="utf-8") as f:
                    ts = json.load(f)
                if isinstance(ts, dict) and isinstance(ts.get("intake"), dict):
                    intake = ts["intake"]
            except Exception:
                intake = {}

    def _intake_ready(key):
        v = intake.get(key)
        if v in (None, [], {}, ""):
            return False, "未登记"
        if isinstance(v, dict):
            st = str(v.get("status") or "")
            if st != "confirmed":
                return False, f"状态为 {st or '未标'}（须 confirmed）"
            return True, "已确认"
        return True, "已登记"

    # 模板：包内不预置具体模板（v3.18.0 G5）—— 查工作区模板登记册
    template_state = None
    reg_p = os.path.join(os.path.abspath(w), ".workbuddy", "templates", "template_registry.json")
    if os.path.isfile(reg_p):
        try:
            with open(reg_p, encoding="utf-8") as f:
                reg = json.load(f)
            n = len(reg.get("templates") or [])
            template_state = {"ready": n > 0, "detail": f"工作区模板登记册 {n} 份"}
        except Exception as e:
            template_state = {"ready": False, "detail": f"模板登记册解析失败：{e}"}
    else:
        template_state = {"ready": False,
                          "detail": "无工作区模板登记册（<workspace>/.workbuddy/templates/"
                                    "template_registry.json）——包内不预置任何模板文件，"
                                    "请用 template_migrate.py register 登记后再进闸2"}

    # 坍缩确认态
    collapse_state = {"ready": False, "detail": "未找到坍缩产物（先 route --domain ...）"}
    cdir = os.path.join(os.path.abspath(w), ".harness-runs")
    if os.path.isdir(cdir):
        for tid in sorted(os.listdir(cdir)):
            sub = os.path.join(cdir, tid, "_collapse")
            if not os.path.isdir(sub):
                continue
            for fn in sorted(os.listdir(sub)):
                if not (fn.startswith("collapse_") and fn.endswith(".json")):
                    continue
                fp = os.path.join(sub, fn)
                try:
                    with open(fp, encoding="utf-8") as f:
                        o = json.load(f)
                except Exception:
                    continue
                if o.get("status") == "confirmed" and o.get("effective") is True:
                    sel = o.get("selected_experts") or []
                    collapse_state = {
                        "ready": True,
                        "detail": f"已确认（域 {o.get('domain_id')}，"
                                  f"选中专家 {len(sel)} 位）",
                        "artifact": fp,
                    }
                    break
            if collapse_state.get("ready"):
                break

    checks = {
        "audience": _intake_ready("audience"),
        "hours": _intake_ready("periods"),
        "scope": _intake_ready("scope"),
        "acceptance": _intake_ready("acceptance"),
        "template": (template_state["ready"], template_state["detail"]),
        "collapsed_team_config": (collapse_state["ready"], collapse_state["detail"]),
        # ── v3.19.0 新增第 7 项：交付语言（维度 6）────────────────
        "delivery_language": _delivery_language_state(intake),
        # ── v3.19.0 新增第 8 项：知识库路由就绪度（维度 10/13）────
        "knowledge_channel": _knowledge_channel_state(w),
    }

    rows, not_ready = [], []
    for it in items:
        iid = str(it.get("id") or "")
        label = str(it.get("label") or iid)
        required = bool(it.get("required", True))
        ok, detail = checks.get(iid, (False, "无校验实现（判据缺失）"))
        rows.append({"id": iid, "label": label, "required": required,
                     "ready": ok, "detail": detail})
        if required and not ok:
            not_ready.append(iid)

    out = {
        "ok": not not_ready,
        "total": len(rows),
        "not_ready": not_ready,
        "items": rows,
    }
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            flag = "✓" if r["ready"] else ("⚠" if not r["required"] else "✗")
            req = "" if r["required"] else "（非必填）"
            print(f"  {flag} {r['label']}{req}：{r['detail']}")
        if not_ready:
            print(f"\n⛔ 闸1 未就绪 {len(not_ready)}/{len(rows)} 项：{not_ready}")
            print("   → 未就绪项须补齐并经用户确认后方可进入闸2（闸1 是 user_confirm 门）。")
        else:
            print(f"\n✅ 闸1 全部就绪（{len(rows)}/{len(rows)}）——可进入闸2。")
    return 0 if not not_ready else 1


# ─────────────────────────── state ───────────────────────────
def cmd_state(args):
    cfg, _ = load_cfg()
    w = wkspace(args)
    allowed = cfg.get("context", {}).get("state_allowed_keys") or []
    stages = cfg.get("stages", {})

    if args.action == "init":
        # v3.17.0：原状态文件损坏时**先保留证据再重建**（不静默覆盖）
        sp = state_path(w)
        if os.path.exists(sp):
            try:
                with open(sp, encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                bak = sp + ".corrupt"
                try:
                    os.replace(sp, bak)
                except OSError as e2:
                    print(f"❌ 原 task_state.json 损坏（{e}）且无法备份（{e2}）：{sp}"
                          f"——拒绝重建（不覆盖损坏文件）", file=sys.stderr)
                    return 1
                print(f"⚠ 原 task_state.json 损坏（{e}），已保留为 {bak} 后重建"
                      f"（请人工核查其内容）", file=sys.stderr)
        st = {"task_id": args.task_id or f"t{int(time.time())}", "workflow": args.workflow or "WF-1",
              "current_stage": args.stage if args.stage is not None else 0,
              "stage_history": [], "user_confirmations_pending": [],
              "tool_probe_results": {}, "budget": {}, "next_action": "", "compaction": {}}
        try:
            write_state(w, st, reset_ledger=True)
        except (_TaskIdConflict, _StateCorrupt) as e:
            print(f"⛔ 拒绝写入：{e}", file=sys.stderr)
            return 1
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    # v3.17.0：非 init 动作一律**严格读**——损坏状态不得被读成"空状态"（那是静默重置）
    try:
        st = read_state(w, strict=True)
    except _StateCorrupt as e:
        print(f"⛔ 拒绝操作：{e}\n"
              f"   损坏文件已原样保留（**不覆盖、不重建**）——请人工修复，"
              f"或确认作废后删除再 `state init` 重建。", file=sys.stderr)
        return 1
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
        # v3.17.0：读-改-写整段在锁内（避免并发写丢更新），写前做 task_id 比对
        with _StateLock(w, None, path=state_path(w) + ".lock"):
            try:
                st = read_state(w, strict=True)
            except _StateCorrupt as e:
                print(f"⛔ 拒绝写入：{e}\n"
                      f"   损坏文件已原样保留（**不覆盖、不重建**）——请人工修复。",
                      file=sys.stderr)
                return 1
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
                except Exception as e:
                    # v3.17.0：**不再静默存字符串**。旧实现在 JSON 解析失败时
                    # `st[key] = args.value`，于是 quality_history 变成字符串，
                    # 下游 isinstance(h, dict) 过滤掉 → 收敛判据 streak 恒 0（静默失效）。
                    print(f"拒绝写入：--value 不是合法 JSON（{e}）：{args.value!r}\n"
                          f"   用法：--value 的内容必须是合法 JSON。\n"
                          f"     字符串 → 显式加引号：--value '\"abc\"'（例：--value '\"gate2_spawn\"'）\n"
                          f"     数字   → --value '3'\n"
                          f"     数组   → --value '[1,2]'\n"
                          f"     对象   → --value '{{\"k\":1}}'\n"
                          f"   不做隐式字符串回落（静默存字符串会让 quality_history 之类结构化键"
                          f"变成字符串 → 下游按 dict 过滤掉 → 判据静默失效）。", file=sys.stderr)
                    return 2
            try:
                write_state(w, st, locked=True, expect_task_id=getattr(args, "task_id", "") or None)
            except _TaskIdConflict as e:
                print(f"⛔ 拒绝写入：{e}", file=sys.stderr)
                return 1
            except _StateCorrupt as e:
                print(f"⛔ 拒绝写入：{e}\n"
                      f"   损坏文件已原样保留（**不覆盖、不重建**）。", file=sys.stderr)
                return 1
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    if args.action == "compact":
        # v3.18.0 G6：把 `state validate` 报的那句「必须 compaction」变成**可执行的命令**。
        # 此前全包无任何 compaction 实现（grep compact 在 scripts/ 下只有 init 置 {} 与报错文案），
        #   超限后只能人工手改状态文件——而手改会绕过 task_id 台账比对、并可能写坏 JSON。
        # 压缩是**有损**操作，故必须留下账本：compaction 键记录压前字节/压后字节/丢了什么。
        with _StateLock(w, None, path=state_path(w) + ".lock"):
            try:
                st = read_state(w, strict=True)
            except _StateCorrupt as e:
                print(f"⛔ 拒绝压缩：{e}\n"
                      f"   损坏文件已原样保留（**不覆盖、不重建**）——请人工修复。",
                      file=sys.stderr)
                return 1
            if not st:
                print(f"⛔ 无状态文件可压缩：{state_path(w)}\n"
                      f"   → 先跑 `state init` 建状态，再执行 `state compact`。",
                      file=sys.stderr)
                return 1
            try:
                before = os.path.getsize(state_path(w))
            except OSError:
                before = 0
            new_st, meta = _compact_state(st, cfg)
            meta["bytes_before"] = before
            # 压后字节数必须反映**最终落盘文件**的大小，而落盘内容里含 meta 本身
            #   → 存在自指。这里用与 _atomic_write_json 完全一致的序列化方式
            #     （json.dumps(..., ensure_ascii=False, indent=2)）迭代收敛：
            #     按当前 meta 估一次 → 把估值写回 meta → 再估，直至稳定（至多 5 轮）。
            for _ in range(5):
                est = len(json.dumps(new_st, ensure_ascii=False, indent=2).encode("utf-8"))
                if est == meta.get("bytes_after"):
                    break
                meta["bytes_after"] = est
            # 原子写（复用 write_state：同目录临时文件 → fsync → os.replace）
            try:
                write_state(w, new_st, locked=True,
                            expect_task_id=getattr(args, "task_id", "") or None)
            except (_TaskIdConflict, _StateCorrupt) as e:
                print(f"⛔ 拒绝压缩写入：{e}\n"
                      f"   原状态文件已原样保留（**未改动**）。", file=sys.stderr)
                return 1
            try:
                after = os.path.getsize(state_path(w))
            except OSError:
                after = 0
            meta["bytes_after"] = after
            _trace(w, cfg, "compaction", "main",
                   {"task_id": new_st.get("task_id"),
                    "bytes_before": before, "bytes_after": after,
                    "dropped_count": sum(d.get("dropped_count", 0) for d in meta["dropped"]),
                    "dropped_keys": [d.get("key") for d in meta["dropped"]]})
            print(json.dumps({
                "ok": True,
                "bytes_before": before,
                "bytes_after": after,
                "saved_bytes": before - after,
                "max_bytes": int((cfg.get("context") or {}).get("state_max_bytes", 32768)),
                "within_limit": after <= int((cfg.get("context") or {}).get("state_max_bytes", 32768)),
                "kept": sorted(new_st.keys()),
                "must_keep": list(COMPACT_MUST_KEEP),
                "dropped": meta["dropped"],
                "dropped_count": sum(d.get("dropped_count", 0) for d in meta["dropped"]),
                "state_path": state_path(w),
            }, ensure_ascii=False, indent=2))
            return 0
    return 2


# ─────────────────────── 状态压缩（compaction）───────────────────────
# 缺陷（v3.18.0 G6 实测）：`cmd_state validate` 会报「状态文件 N bytes 超过上限，
#   必须 compaction」，但**全包没有任何 compaction 实现**——超限后只能人工手改状态文件，
#   而手改会绕过 task_id 台账比对（v3.17.0 建的并发防护）并可能写坏 JSON。
#   本段把"必须 compaction"这句报错变成**可执行的命令**。

# 必保最小集：压缩时**绝不丢弃**的键（依据 references/sop-stages.md「Compaction 最小集策略」：
#   ① task_id + workflow ② current_stage + next_action ③ 关键决策摘要 ④ 文件路径清单）。
#   tool_probe_results / budget 同属"跨会话必须知道的事实"，一并必保。
COMPACT_MUST_KEEP = ["task_id", "workflow", "current_stage", "next_action",
                     "budget", "tool_probe_results"]

# 可选白名单键：压缩后**仍超上限**时才丢弃，按此顺序（先丢可再生的）。
#   quality_history 是 loopB_state.json 的**镜像**，真源在 Loop B 侧 → 先丢它；
#   collapse 是域坍缩产物镜像、体量小 → 最后丢。
COMPACT_DROP_ORDER = ["quality_history", "collapse"]


def _compact_confirmations_pending(items):
    """只保留**未决**的确认项；已确认的从历史里剥离。

    判定：条目是 dict 且 status 属于已确认集合（confirmed/done/resolved/approved/accepted）
    → 视为已决，剥离。非 dict（字符串等）**一律保留**——无法判定时保留是安全方向
    （误丢一个待确认项 = 丢掉用户没拍板的事，比多留一条严重）。
    """
    done_status = {"confirmed", "done", "resolved", "approved", "accepted"}
    kept = []
    for it in items or []:
        if isinstance(it, dict):
            s = str(it.get("status") or it.get("state") or "").strip().lower()
            if s in done_status:
                continue
        kept.append(it)
    return kept


def _compact_stage_history(hist, keep_n):
    """只保留最近 keep_n 条 stage_history（列表尾部 = 最新）。

    返回 (保留后的列表, 被丢弃的条数)。
    """
    h = list(hist or [])
    if not isinstance(keep_n, int) or keep_n < 0 or len(h) <= keep_n:
        return h, 0
    return h[-keep_n:], len(h) - keep_n


def _compact_state(st, cfg):
    """把膨胀的状态文件裁剪回「必保最小集 + 最近 N 条历史 + 未决确认项」。

    策略（每条都有出处，不靠"感觉"裁剪）：
      ① 必保最小集（COMPACT_MUST_KEEP）——一个字节都不丢；
      ② stage_history —— 只留最近 N 条（N = config/harness.yaml#context.state_history_keep，
         默认 10）：它是状态文件**唯一无上限增长**的键（每次 `state set --stage` 追加一条），
         也是历史上撑爆状态文件的元凶；
      ③ user_confirmations_pending —— 只留未决项：已确认的确认项留在历史里没价值，
         却让每次冷启动都要重读一遍；
      ④ 其余**白名单内**的键（quality_history / collapse）默认保留；
         只有在 ①②③ 做完**仍超上限**时，才按 COMPACT_DROP_ORDER 依次丢弃
         （丢弃动作全部记进 compaction.dropped，不静默）；
      ⑤ 白名单**外**的键——按既有「拒绝写入」逻辑处理：压缩不写它们
         （`state set` 的白名单检查不因此放宽；压缩不是绕过白名单的后门）。

    返回 (新状态, 压缩元信息)。
    """
    ctx = (cfg or {}).get("context") or {}
    allowed = list(ctx.get("state_allowed_keys") or [])
    try:
        keep_n = int(ctx.get("state_history_keep", 10))
    except (TypeError, ValueError):
        keep_n = 10
    max_bytes = int(ctx.get("state_max_bytes", 32768))

    st = st if isinstance(st, dict) else {}
    dropped = []

    # ④ 白名单外的键：压缩不写（记录下来，让操作者知道有东西被拒了）
    #    ⚠ allowed 为空（配置缺失）时**不做任何判定**——宁可全留也不误删。
    unknown = [k for k in st if allowed and k not in allowed]
    for k in unknown:
        dropped.append({"key": k, "dropped_count": 1,
                        "reason": "白名单外的键——压缩不写（`state set` 的白名单检查不放宽）"})

    new = {}
    # ① 必保最小集（逐个保留原值；缺失就缺，不伪造）
    for k in COMPACT_MUST_KEEP:
        if k in st:
            new[k] = st[k]
    # ② stage_history：只留最近 N 条
    hist, n_hist = _compact_stage_history(st.get("stage_history"), keep_n)
    if "stage_history" in st or hist:
        new["stage_history"] = hist
    if n_hist:
        dropped.append({"key": "stage_history", "dropped_count": n_hist,
                        "reason": f"只保留最近 {keep_n} 条（其余是历史噪声）"})
    # ③ user_confirmations_pending：只留未决项
    if "user_confirmations_pending" in st:
        orig = st.get("user_confirmations_pending") or []
        pend = _compact_confirmations_pending(orig)
        new["user_confirmations_pending"] = pend
        if len(pend) != len(orig):
            dropped.append({"key": "user_confirmations_pending",
                            "dropped_count": len(orig) - len(pend),
                            "reason": "已确认的确认项从历史里剥离（只留未决项）"})
    # ④ 其余白名单内的键：默认保留（allowed 为空 ⇒ 原样保留全部其余键）
    if allowed:
        for k in allowed:
            if k in st and k not in new and k != "compaction":
                new[k] = st[k]
    else:
        for k, v in st.items():
            if k not in new and k != "compaction":
                new[k] = v

    # 压缩元信息（compaction 键本身必保——它是"压过没有/丢了什么"的账本）
    def _size_of(obj):
        return len(json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))

    # ①②③ 做完仍超上限 → 按 COMPACT_DROP_ORDER 依次丢弃可选键
    guard = 0
    while _size_of(new) > max_bytes and guard < len(COMPACT_DROP_ORDER):
        guard += 1
        key = COMPACT_DROP_ORDER[guard - 1]
        if key not in new:
            continue
        val = new.pop(key)
        dropped.append({"key": key,
                        "dropped_count": len(val) if isinstance(val, (list, dict)) else 1,
                        "reason": f"压缩后仍超 {max_bytes} bytes 上限，按优先级丢弃该可选键"})
    new["compaction"] = {
        "must_keep": list(COMPACT_MUST_KEEP),
        "dropped": dropped,
        "bytes_before": None,     # 由调用方填（需要磁盘上的原始大小）
        "bytes_after": None,
        "compacted_at": now_iso(),
        "state_history_keep": keep_n,
        "max_bytes": max_bytes,
    }
    return new, new["compaction"]


# ─────────────────────────── budget ───────────────────────────
def cmd_budget(args):
    """任务级预算计数：超限即阻断（纪律变计数）。

    v3.12.0：补齐 6 项此前「配了但从不读取」的死配置。
    根因：limit_map 只映射 spawn/react/rework 三项，而 harness.yaml#budgets 里
    还有 6 项（max_spawn_attempts_per_member / max_react_rounds_per_gap /
    max_stage_minutes / max_artifact_bytes / three_source_sample_rate /
    three_source_pass_threshold）只在 _FALLBACK 兜底字典里出现，代码从不读——
    配置写了、文档也引用了（如 sop-stages.md 引用 max_stage_minutes），
    但**没有任何执行者**，等于"看起来有护栏、实际不设防"。
    v3.17.0：后两项（three_source_*）已从 harness.yaml 删除——它们与
    domain_config.yaml#three_source_check 重复声明，而 verify_deck.py 只读后者，
    改 harness.yaml 静默无效。现 three_source_sample / three_source_pass 两个 kind
    改读 domain_config.yaml（见 threshold_map 的第三项"配置源"），
    并在输出里明示 config_source 与真实执行者。

    修法分两类，不混为一谈：
      ① 计数型（可由 harness 自己判断用没用超）→ 补进 limit_map，可 --kind check/spend
      ② 阈值型（含义属于其它脚本的判定规则，harness 不该替它执行）
        → 注册到 THRESHOLD_BUDGETS，供 `budget --kind xxx` 查询"当前配置值是什么"，
          并在输出里标明"阈值型：由 <哪个脚本> 执行，harness 只查不做"。
    两类都不再"静默失效"：要么能查，要么明确说明谁执行。
    """
    cfg, _ = load_cfg()
    b = cfg.get("budgets", {})
    limit_map = {"spawn": "max_member_spawns", "react": "max_react_rounds_total",
                 "rework": "max_rework_rounds_per_stage"}
    # v3.12.0：阈值型预算——harness 不代执行，只做「配置查得到 + 标明执行者」
    # v3.17.0：三元组第三项是**配置源**：
    #   "budgets"            → 读 config/harness.yaml#budgets.<key>
    #   "domain_three_source"→ 读 config/domain_config.yaml#three_source_check.<key>
    # 背景：three_source_* 曾在 harness.yaml 与 domain_config.yaml 两处同值声明，
    #   而 verify_deck.py 只读后者 → 改 harness.yaml 静默无效。现 harness.yaml 已删这两键，
    #   executed_by 也更正为真实执行者（verify_deck.py#_load_three_source_thresholds）。
    threshold_map = {
        "attempts": ("max_spawn_attempts_per_member",
                     "spawn-protocol.md#工具/通道不可用回退（主理人判定，不自动计数）",
                     "budgets"),
        "react_gap": ("max_react_rounds_per_gap",
                      "dvm-content-expert.md#联网检索循环（成员自评，harness 不代判）",
                      "budgets"),
        "stage_minutes": ("max_stage_minutes",
                          "sop-stages.md#超时降级（trace 侧可比对，非阻断）",
                          "budgets"),
        "artifact_bytes": ("max_artifact_bytes",
                           "harness-engine.md#产物压缩策略（成员侧自律）",
                           "budgets"),
        "three_source_sample": ("sample_rate",
                                "verify_deck.py#_load_three_source_thresholds()（three_source_check() "
                                "按 sample_rate 抽检）",
                                "domain_three_source"),
        "three_source_pass": ("pass_threshold",
                              "verify_deck.py#_load_three_source_thresholds()（three_source_check() "
                              "按 pass_threshold 判定达标）",
                              "domain_three_source"),
    }

    def _threshold_value(key, source):
        """按配置源取阈值：domain_three_source 走 domain_config.yaml，其余走 budgets。"""
        if source == "domain_three_source":
            return _load_three_source_thresholds().get(key)
        return b.get(key)

    def _threshold_source(key, source):
        if source == "domain_three_source":
            return f"config/domain_config.yaml#three_source_check.{key}"
        return f"config/harness.yaml#budgets.{key}"

    all_kinds = set(limit_map) | set(threshold_map)
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
            print(json.dumps({
                "kind": None, "used": 0, "limit": 0, "exceeded": False, "remaining": 0,
                "counter_kinds": sorted(limit_map),
                "threshold_kinds": sorted(threshold_map),
                "hint": "指定 --kind <见 counter_kinds|threshold_kinds>；"
                        "不带 --list 可列全部配置值",
            }, ensure_ascii=False))
            return 2  # 用法错误，提示重跑
        # 阈值型：查得到值，但不做 spent/exceeded 判定（执行者是别的脚本）
        if args.kind in threshold_map:
            key, owner, source = threshold_map[args.kind]
            val = _threshold_value(key, source)
            print(json.dumps({
                "kind": args.kind, "type": "threshold", "config_key": key,
                "config_source": _threshold_source(key, source),
                "value": val, "executed_by": owner,
                "note": ("阈值型预算：harness 只查配置，不计数不阻断——由执行者判定。"
                         "配成 0/null 即该护栏实际不存在，勿当已有。"
                         + ("配置源=domain_config.yaml#three_source_check.%s；"
                            "harness.yaml 不再提供此键（v3.17.0 已删 three_source_* 重复声明）。"
                            % key if source == "domain_three_source" else "")),
            }, ensure_ascii=False))
            if val in (None, 0):
                return 1      # 没配值 = 护栏缺失，如实暴露而非静默通过
            return 0
        used = bud.get(args.kind, 0)
        lim = int(b.get(limit_map.get(args.kind, ""), 0))
        print(json.dumps({"kind": args.kind, "used": used, "limit": lim,
                          "exceeded": used >= lim, "remaining": max(lim - used, 0)},
                         ensure_ascii=False))
        return 0 if used < lim else 1

    if args.action == "list":
        out = {"counter": {}, "threshold": {}}
        for k, key in sorted(limit_map.items()):
            out["counter"][k] = {"config_key": key, "limit": b.get(key),
                                 "used": bud.get(k, 0)}
        for k, (key, owner, source) in sorted(threshold_map.items()):
            out["threshold"][k] = {"config_key": key,
                                   "config_source": _threshold_source(key, source),
                                   "value": _threshold_value(key, source),
                                   "executed_by": owner}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        missing = [v["config_key"] for v in list(out["counter"].values())
                   + list(out["threshold"].values()) if v.get("limit") is None
                   and v.get("value") is None]
        if missing:
            print(f"⚠ {len(missing)} 项预算未配置：{missing}", file=sys.stderr)
            return 1
        return 0

    if args.action == "spend":
        if args.kind not in limit_map:
            print(f"用法错误：--kind {args.kind!r} 不是计数型预算；"
                  f"计数型为 {sorted(limit_map)}（阈值型不可 spend）", file=sys.stderr)
            return 2
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


# ── v3.17.0 B3-2：声明层≠执行层的 trace 事件补产 ──────────────────────
# 立项理由（不是"锦上添花"）：config/harness.yaml#observability.trace_events 声明了
# 12 个事件，实测只有 5 个有代码产出（gate / stage_enter / stage_exit /
# budget_exceeded / no_progress），另外 7 个是**纯声明**。
# 后果是立项级的：harness.yaml#fallback.require_disclosure=true 写着"降级必须在
# 交付物与 trace 中显式声明"，而 degrade 事件**没有任何代码产出**——
# ⇒ 降级是否发生、是否被声明，在 trace 里根本查不到。
# 这恰恰是 v2.2.0 建立整个 harness 层的原始理由（"静默降级无人察觉"）被自己重犯。
#
# 处置原则：**事件名沿用 yaml 声明的原名**（不改声明去迁就代码），写入点沿用
# 既有 `_trace()` 风格（追加式 JSONL，一行一事件），不另起一套日志。
#
# 各事件的产出点（谁在什么时候知道这件事）：
#   spawn        ← cmd_spawn（spawn 成功时）
#   spawn_failed ← cmd_spawn --failed（spawn 失败/不可用时）
#   degrade      ← cmd_spawn --failed（降级到 fallback 通道时）+ cmd_preflight
#                  （检出成员已被平台回落成通用子代理时——这正是"静默降级"本体）
#   member_return← cmd_member_return（成员回传登记）
#   preflight    ← cmd_preflight（开工前可用性预检）
#   team_create  ← cmd_route（路由判出需要建队时）
#   error        ← 各命令的异常出口（_trace_error）

# trace 事件名 → yaml 声明的全集（用于自检：声明了却没产出点 = 仍是纯声明）
TRACE_EVENTS_DECLARED = ("team_create", "preflight", "spawn", "spawn_failed", "degrade",
                         "member_return", "gate", "stage_enter", "stage_exit",
                         "budget_exceeded", "error", "no_progress")


def _trace_error(w, cfg, event, actor, detail):
    """写一条 error 事件——**运行期异常的统一出口**。

    为什么单列：此前 harness 的异常一律向上抛（栈打到 stderr 就没了），
    trace 里查不到"哪一步炸了"。error 事件是 yaml 声明了 12 个事件之一，
    此前同样零产出。
    """
    return _trace(w, cfg, event or "error", actor, detail)


def _fallback_channels(cfg):
    """取 fallback.degrade_modes 的通道名（general-purpose+persona / script_pipeline）。"""
    modes = (cfg.get("fallback") or {}).get("degrade_modes") or {}
    return list(modes.keys())


def cmd_member_return(args):
    """登记成员回传（写 trace 事件 member_return）。

    v3.17.0 B3-2 新增。此前回传**零 trace 产出**——成员交了什么、在哪个阶段、
    产物落在哪，全都只存在于主理人的对话里，事后不可审计。
    本命令把回传落成结构化事件：成员 id / task_id / status / 产物路径。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    members = cfg.get("members") or {}
    if args.agent not in members:
        print(f"⚠ agent={args.agent!r} 不在 members 表（{list(members.keys())}）"
              f"——仍记录（可能是外部 agent）", file=sys.stderr)
    detail = {
        "task_id": args.task_id,
        "stage": getattr(args, "stage", None),
        "status": args.status,
        "artifact": args.artifact or "",
        "phase": getattr(args, "phase", "") or "",
    }
    if args.issues:
        detail["issues"] = args.issues
    if args.warnings:
        detail["warnings"] = args.warnings
    rec = _trace(w, cfg, "member_return", args.agent, detail)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def cmd_spawn_failed(args):
    """登记 spawn 失败（写 trace 事件 spawn_failed，可选连带 degrade）。

    v3.17.0 B3-2 新增。spawn 失败此前只有主理人一句口头说明，trace 里查不到
    "试了几次、为什么不行、最后走了哪条降级通道"。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    fb = cfg.get("fallback") or {}
    max_attempts = int(fb.get("max_spawn_attempts", 2))
    attempt = int(getattr(args, "attempt", 1) or 1)
    detail = {
        "task_id": args.task_id,
        "stage": getattr(args, "stage", None),
        "attempt": attempt,
        "max_attempts": max_attempts,
        "reason": args.reason or "",
        "exhausted": attempt >= max_attempts,
    }
    rec = _trace(w, cfg, "spawn_failed", args.agent, detail)
    if attempt >= max_attempts:
        print(f"⚠ 该成员已尝试 {attempt}/{max_attempts} 次——按 harness.yaml#fallback."
              f"max_spawn_attempts 处置（降级或上报主理人），不得无限重试。", file=sys.stderr)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def cmd_degrade(args):
    """登记成员降级（写 trace 事件 degrade：成员 id / 降级通道 / 原因）。

    v3.17.0 B3-2 新增。**这是 fallback.require_disclosure 的执行者**——
    此前该声明的消费者只有人（靠自觉在交付物里写"已降级"），机器无从查证。
    """
    cfg, _ = load_cfg()
    w = wkspace(args)
    fb = cfg.get("fallback") or {}
    modes = (fb.get("degrade_modes") or {})
    channel = args.channel or ""
    if channel and channel not in modes:
        print(f"⚠ 降级通道 {channel!r} 不在 harness.yaml#fallback.degrade_modes "
              f"（{list(modes.keys())}）——仍记录（便于事后发现自造通道）", file=sys.stderr)
    detail = {
        "task_id": args.task_id,
        "stage": getattr(args, "stage", None),
        "member_id": args.agent,
        "degrade_channel": channel,
        "reason": args.reason or "",
        "disclosure_required": bool(fb.get("require_disclosure", True)),
        "fallback_on_unavailable": fb.get("on_unavailable"),
    }
    rec = _trace(w, cfg, "degrade", args.agent, detail)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


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
        # v3.17.0 B3-2：**声明的事件 vs 实际产出**（治"声明层≠执行层"）
        #   yaml#observability.trace_events 声明了哪些事件、trace 里实际出现了哪些，
        #   两者的差集就是"声明了却没发生"——这个差集此前**没有任何机器视图**，
        #   只能靠人读 CHANGELOG 的已知瑕疵 #5 才知道 7 个事件零产出。
        declared = list((cfg.get("observability") or {}).get("trace_events") or [])
        observed = set(by_event.keys())
        declared_missing = [e for e in declared if e not in observed]
        out = {"events_total": len(ev), "by_event": by_event, "by_actor": by_actor,
               "stage_seconds": {k: v for k, v in spans.items()},
               "stage_seconds_status": "未启用 stage 追踪（需显式发 stage_enter/exit 事件）" if not spans else "ok",
               "declared_events": declared,
               "declared_events_observed": [e for e in declared if e in observed],
               "declared_events_missing": declared_missing,
               "declared_events_missing_hint": (
                   f"声明了但本次 trace 未出现 {len(declared_missing)} 个事件：{declared_missing}"
                   if declared_missing else "ok（声明的事件全部有产出）"),
               "undeclared_events": sorted(observed - set(declared)),
               "undeclared_events_hint": (
                   "trace 里出现了未在 yaml#observability.trace_events 声明的事件"
                   f"（{sorted(observed - set(declared))}）——要么补登记，要么删产出点"),
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
        # v3.19.0：subprocess 加 timeout（此前三处全部裸跑——子进程挂死 ⇒ gate 永久阻塞；
        #   上限取 harness.yaml#budgets.max_stage_minutes ×60，语义同源）
        _stage_timeout = int((cfg.get("budgets") or {}).get("max_stage_minutes", 20)) * 60
        try:
            lp = subprocess.run(lint_cmd, capture_output=True, text=True,
                                timeout=_stage_timeout)
        except subprocess.TimeoutExpired:
            _trace(w, cfg, "lint_run_error", args.actor or "ppt-producer",
                   {"deck": os.path.basename(args.deck), "exit": 4,
                    "seconds": _stage_timeout, "stderr_tail": f"timeout>{_stage_timeout}s"})
            print(f"\n[harness.gate] ooxml_lint 超时（>{_stage_timeout}s）——按运行错误（exit 4）"
                  f"走缺陷回流，不当课件红灯。", file=sys.stderr)
            return 4
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
        # v3.19.0：加 timeout + **补 returncode 检查**——此前 snapshot 失败会被
        #   **静默跳过**（不查 sp.returncode ⇒ 快照没打上也继续跑门禁，
        #   "写回前自动打点"这个安全网形同虚设）
        try:
            sp = subprocess.run(snap_cmd, capture_output=True, text=True,
                                timeout=_stage_timeout)
        except subprocess.TimeoutExpired:
            _trace(w, cfg, "snapshot_run_error", args.actor or "ppt-producer",
                   {"deck": os.path.basename(args.deck), "seconds": _stage_timeout,
                    "stderr_tail": f"timeout>{_stage_timeout}s"})
            print(f"\n[harness.gate] snapshot 超时（>{_stage_timeout}s）——按运行错误（exit 4）。"
                  f"写回前打点失败**不得**静默继续。", file=sys.stderr)
            return 4
        if sp.returncode != 0:
            _trace(w, cfg, "snapshot_run_error", args.actor or "ppt-producer",
                   {"deck": os.path.basename(args.deck), "exit": sp.returncode,
                    "stderr_tail": (sp.stderr or "")[-300:]})
            print(f"\n[harness.gate] snapshot 失败（exit {sp.returncode}）——写回前自动打点"
                  f"未完成，按运行错误（exit 4）走缺陷回流，**不得静默继续**。",
                  file=sys.stderr)
            if sp.stderr:
                print(sp.stderr, end="", file=sys.stderr)
            return 4

    cmd = [sys.executable, vd, args.deck, "--hours", str(args.hours), "--level", args.level]
    if args.json:
        cmd += ["--json", args.json]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=_stage_timeout)
    except subprocess.TimeoutExpired:
        _trace(w, cfg, "gate", args.actor or "ppt-producer",
               {"deck": os.path.basename(args.deck), "level": args.level, "exit": 4,
                "meaning": "运行错误——verify_deck 超时", "seconds": _stage_timeout,
                "stderr_tail": f"timeout>{_stage_timeout}s"})
        print(f"\n[harness.gate] verify_deck 超时（>{_stage_timeout}s）——按运行错误（exit 4）"
              f"走缺陷回流，不当课件红灯。", file=sys.stderr)
        return 4
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


def _check_one_ref(src: dict, pmid_rx=None) -> dict:
    """单条来源预检：返回 {verdict, reason, fix_hint}。
    v3.4.2 红线：ok=true 但无 verified_at → 假通过（最高优先级，先判）。
    真黑名单号（PMID:12345 等占位号）即使 ok=false 也报 fake，便于核验时挑出。
    v3.17.0：PMID 格式正则改由 yaml 提供（pmid_rx），内置正则仅作缺配置时的受控兜底。
    """
    kind = (src.get("kind") or "").lower()
    ref = (src.get("ref") or "").strip()
    has_ts = bool(src.get("verified_at"))
    ok_flag = bool(src.get("ok"))
    rx = pmid_rx or _PMID_RE
    if not kind or not ref:
        return {"verdict": "invalid", "reason": "缺 kind 或 ref",
                "fix_hint": "补 kind+ref，或改 unverified=true"}
    if ok_flag and not has_ts:
        return {"verdict": "stale_ok", "reason": "ok=true 但缺 verified_at 时间戳（v3.4.2 红线）",
                "fix_hint": "改为 ok=false + verified_at 留空，或联网实检后补 verified_at"}
    if kind == "pubmed":
        m = rx.match(ref)
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


def _static_ref_report(cases, pmid_rx=None):
    """v3.4.3 A2：静态引用预检（自 cmd_verify_ref 抽出——--online 修复后需复跑同一逻辑）。"""
    report = {"total": len(cases), "fake": [], "stale_ok": [], "suspicious": [],
              "format_err": [], "ok": [], "fake_unverified": []}
    for c in cases:
        sid = c.get("case_id", c.get("title", "?"))
        for src in (c.get("sources") or []):
            r = _check_one_ref(src, pmid_rx)
            v = r["verdict"]
            # 已 unverified 的黑名单号不阻断（仅标出便于核验时挑出）
            if v == "fake" and not src.get("ok"):
                report["fake_unverified"].append({"case_id": sid, "ref": src.get("ref"),
                                                   "reason": r["reason"]})
                continue
            report[v].append({"case_id": sid, "ref": src.get("ref"),
                              "reason": r["reason"]})
    return report


def _esearch_url(base, db, pmid, api_key=None):
    """拼 esearch URL（api_key 非空时附加 &api_key=...）。"""
    url = f"{base}?db={db}&term={pmid}%5Buid%5D&retmode=json"
    if api_key:
        url += f"&api_key={api_key}"
    return url


def _classify_net_error(exc):
    """把网络异常分成两类：rate_limit（明确的速率限制/封禁）/ network（其它）。

    NCBI 封禁的两种表现：HTTP 403（Access Denied 页面）或 HTTP 429（Too Many
    Requests）——都是明确的速率限制信号；部分网络路径下同一封禁表现为 SSL EOF
    （URLError），那类无法单次判定，靠"连续失败次数"阈值来怀疑（见 suspect_threshold）。
    """
    code = getattr(exc, "code", None)
    if code in (403, 429):
        return "rate_limit"
    return "network"


def pmid_existence_check(pmids, endpoint=None, db="pubmed", timeout=15, sleep=0.4,
                         api_key=None, max_retries=3, backoff_base=2.0,
                         backoff_cap=30.0, suspect_threshold=2, on_alarm=None,
                         abort_batch_on_rate_limit=True):
    """PubMed esearch 联网确认 PMID 是否**真实存在**（v3.17.0：参数化 + 退避）。

    返回 {pmid: True/False/None}——True=存在 False=esearch 无记录 None=网络失败。
    **False 与 None 必须分开计数**：False=证伪（该号根本不存在，是数据错）；
    None=没查到（网络故障/被封禁，是环境问题）。二者都**不得**被当作"已验证"，
    但处置不同，故返回值保留三态而不是布尔。

    v3.17.0 收尾（治 NCBI abuse 封禁）：
      · api_key：有 key 时请求带 &api_key=（NCBI 限速 3→10 req/s）。
        ⚠ **key 真值只从环境变量读**（调用方解析 yaml#…pubmed.api_key_env 得到变量名），
          本函数只接收已取到的值，**绝不**把 key 写进任何日志/报告/URL 输出。
      · 退避：遇 403/429（明确的速率限制）或连续失败达 suspect_threshold
        （疑似封禁，如 SSL EOF）→ **指数退避重试**，且**每次退避都显式告警**
        （on_alarm 回调；默认打印到 stderr）——**不静默重试到超时**。
      · 退避耗尽 → 该 PMID 记 None（网络失败），由上层计入 network_error 并阻断。
      · 熔断（abort_batch_on_rate_limit=True，默认开）：**某个 PMID 因速率限制
        重试耗尽 = 端点/限速对整批都不可用**，此时**中止本批剩余 PMID 的实查**
        （不再发请求，剩余全部记 None）——否则封禁时每条 PMID 都要赔上
        2+4+8 秒退避，整批清单会拖到无法忍受。被中止的条数**显式告警**，
        上层按 network_error 计数 → fail-closed，不静默。

    请求间 sleep（限速，NCBI 无 key 3 req/s）；None 不参与写回判定（防半核验落盘）。
    """
    import urllib.request as _u
    out = {}
    base = endpoint or "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    def _alarm(msg):
        if on_alarm:
            on_alarm(msg)
        else:
            print(msg, file=sys.stderr)

    consecutive_fail = 0
    aborted = False
    pmids = list(pmids)
    for idx, pmid in enumerate(pmids):
        if aborted:
            out[pmid] = None
            continue
        attempt = 0
        while True:
            try:
                url = _esearch_url(base, db, pmid, api_key)
                with _u.urlopen(url, timeout=timeout) as resp:
                    j = json.loads(resp.read().decode("utf-8"))
                ids = (j.get("esearchresult") or {}).get("idlist") or []
                out[pmid] = str(pmid) in [str(x) for x in ids]
                consecutive_fail = 0
                break
            except Exception as e:
                kind = _classify_net_error(e)
                consecutive_fail += 1
                suspected = (kind == "network"
                             and consecutive_fail >= max(1, int(suspect_threshold)))
                if kind == "rate_limit" or suspected:
                    reason = ("HTTP %s（NCBI 速率限制/封禁）" % getattr(e, "code", "?")
                              if kind == "rate_limit"
                              else "连续 %d 次连接失败（疑似触发 NCBI 速率限制）" % consecutive_fail)
                    if attempt < max_retries:
                        delay = min(backoff_base * (2 ** attempt), backoff_cap)
                        _alarm(f"⚠ 疑似触发 NCBI 速率限制（{reason}）：PMID:{pmid} "
                               f"第 {attempt + 1} 次请求失败，{delay:.1f}s 后指数退避重试"
                               f"（退避期间**不算已验证**；退避耗尽即记网络失败）")
                        time.sleep(delay)
                        attempt += 1
                        continue
                    _alarm(f"⛔ PMID:{pmid} 因速率限制连续失败 {attempt + 1} 次，退避重试耗尽"
                           f"（{reason}）——记为网络失败，**不计入已验证**；"
                           f"建议配 NCBI_API_KEY 环境变量或放慢节奏重跑")
                    out[pmid] = None
                    if abort_batch_on_rate_limit:
                        aborted = True
                        rest = len(pmids) - idx - 1
                        if rest:
                            _alarm(f"⛔ 已因速率限制中止本批剩余 {rest} 条 PMID 的实查"
                                   f"（不再发请求，全部记为网络失败）——"
                                   f"端点/限速对整批不可用，继续跑只会把每条都赔上退避时间")
                    break
                out[pmid] = None
                break
        if sleep and not aborted:
            time.sleep(sleep)  # NCBI 限速（无 key 3 req/s / 有 key 10 req/s）
    return out


def _resolve_api_key(tsc=None, alarms=None):
    """按 yaml 指定的**环境变量名**取 NCBI API key（真值只从环境读，绝不落盘）。

    yaml 里只放变量名（source_verification.pubmed.api_key_env），本函数读
    os.environ。**返回的 key 不得写进任何日志/报告**——调用方只把它交给
    pmid_existence_check 拼 URL。

    返回 (key, 说明文字)：说明文字供调用方显式告警"用没用 key"（没 key 是
    **已知环境约束**，必须让使用者知道，否则批量清单跑不完会被当成 bug）。
    """
    spec = ((tsc or {}).get("source_verification") or {}).get("pubmed") or {}
    env_name = str(spec.get("api_key_env") or "").strip()
    if not env_name:
        return "", ("ℹ 未配置 NCBI API key（yaml 未设 api_key_env）——按匿名限速 3 req/s 跑，"
                    "批量清单易触发 NCBI 封禁，建议分批+批间留间隔")
    key = os.environ.get(env_name, "").strip()
    if not key:
        return "", (f"ℹ 未取到 NCBI API key（环境变量 {env_name} 未设置）——按匿名限速 3 req/s 跑，"
                    f"批量清单易触发 NCBI 封禁，建议分批+批间留间隔")
    return key, f"ℹ 已启用 NCBI API key（取自环境变量 {env_name}，限速 10 req/s）"


def _pmid_online_check(pmids):
    """v3.4.3 A2：PubMed esearch 联网确认 PMID 真实存在（反"假核验"闭环核心）。

    v3.17.0：改为薄封装，参数化实现见 pmid_existence_check()（端点/时限/限速落 yaml）。
    返回 {pmid: True/False/None}——True=存在 False=esearch 无记录 None=网络失败。
    """
    return pmid_existence_check(pmids)


# ══════════════ v3.17.0 三源核验内核（存在性 / 格式 三档判定）══════════════
# 唯一实现点：verify_deck.py#three_source_check（裁判侧执行）与
#   harness.py#cmd_verify_ref（编排侧查询/写回）共用，避免同型逻辑两处各写一份
#   （"同一判据两处各写"是本包反复出现的缺陷类型）。
#
# 为什么必须重做判定口径（v3.17.0 独立诊断组实跑攻击复现）：
#   原判据 = `any(src.get("ok") is True for src in sources)` —— **自报布尔值**，
#   零存在性校验。攻击：造 3 条来源（不存在的 PMID + 不存在的 ISBN + 不存在的 GB），
#   把 ok 写成 true → 闸4.5 输出 pass_rate=1.0 / verdict=pass / exit 0；
#   交叉核验该 PMID 在 PubMed esearch count=0（根本不存在）。
#   ⇒ 判据必须从"自报"改为"实查"，且**查得到才算通过，查不到更不算通过**。
#
# 三档语义（唯一源 = config/domain_config.yaml#three_source_check.tiers）：
#   existence_verified 存在性已验证 —— 联网实查命中（当前仅 pubmed 具备该能力）
#   format_only        仅格式合规   —— 校验位/编号格式通过，**未验证存在性**
#   unverifiable       不可核验     —— 无核验器 / 格式不过 / 联网失败
# 硬约束：判定**不读 src.ok / src.verified_at**——自报布尔值不构成证据。

TIER_EXISTENCE = "existence_verified"    # 存在性已验证
TIER_FORMAT = "format_only"              # 仅格式合规（未验证存在性）
TIER_UNVERIFIABLE = "unverifiable"       # 不可核验
# 档位排序：同一 kind 下取"档位最高"的一条作为该类来源的代表
_TIER_RANK = {"existence_verified": 4, "format_only": 3, "unverifiable": 2}


# v3.17.0 收尾：**决策键**（缺了就不能继续判）vs 装饰键（缺了只影响显示）
#   口径与包内既有查询者 _load_three_source_thresholds() 一致：「缺值不补内置值」。
_DECISION_KEYS = ("sample_rate", "pass_threshold", "required_kinds",
                  "required_existence_verified", "network_failure_policy")


def load_three_source_config():
    """读 config/domain_config.yaml#three_source_check **全段**（v3.17.0）。

    缺键策略：逐键退回内置最小集并**显式告警**（不静默）。
    ⚠ 本函数**不做进程内缓存**：本包反复吃过"改配置不生效"的亏（进程内缓存会让
      长驻进程读到过期阈值），故每次调用都重新读盘。
    ⚠ **yaml 的键全量覆盖**（不只兜底集里那几个）：否则本版新增的子键
      （如 sources[].label、source_verification.pubmed.api_key_env）会被兜底集
      静默丢掉——"配了但代码读不到" = 同型静默失效。
    """
    defaults = {
        "enabled": True,
        "sample_rate": 0.1,
        "pass_threshold": 0.8,
        "sample_seed": None,
        "sources": [],
        "tiers": {"existence_verified": "存在性已验证",
                  "format_only": "仅格式合规",
                  "unverifiable": "不可核验"},
        "required_kinds": ["pubmed", "textbook", "regulation"],
        "required_existence_verified": 1,
        "network_failure_policy": "block",
        "source_verification": {},
        "format_rules": {},
    }
    out = dict(defaults)
    try:
        import yaml
        with open(_DOMAIN_CFG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        tsc = cfg.get("three_source_check") or {}
        if not tsc:
            print(f"⚠ {_DOMAIN_CFG}#three_source_check 缺失或为空——退回内置三档判定集"
                  f"（改配置不会生效）", file=sys.stderr)
            return out
        # yaml 全量覆盖（新增子键不会被兜底集吞掉）
        for k, v in tsc.items():
            out[k] = v
        # v3.17.0 收尾（同 guard.yaml 的"缺键即红"标准 + 与包内既有查询者口径对齐）：
        #   **决策键缺失不再补内置值**——补了 = yaml 那份成装饰品（检查照跑、没消费配置）。
        #   决策键缺 → 置 None + 显式告警，由闸4.5 判"护栏缺失"并 fail-closed；
        #   纯装饰键（tiers 中文名等）保留兜底，不影响判定。
        for k in defaults:
            if k in tsc:
                continue
            if k in _DECISION_KEYS:
                out[k] = None
                print(f"⛔ {_DOMAIN_CFG}#three_source_check.{k} 未配置——该护栏实际不存在，"
                      f"**不补内置值**（补了 yaml 就成装饰品：检查照跑、但没消费配置）。"
                      f"闸4.5 将判「护栏缺失」并阻断，请补齐该键。", file=sys.stderr)
            else:
                print(f"⚠ {_DOMAIN_CFG}#three_source_check.{k} 未配置——退回内置值 "
                      f"{defaults[k]!r}（仅影响显示文案，不影响判定）", file=sys.stderr)
        return out
    except Exception as e:
        print(f"⚠ {_DOMAIN_CFG}#three_source_check 读取失败（{e}）——退回内置三档判定集"
              f"（改配置不会生效）", file=sys.stderr)
        return out


def _esearch_params(tsc=None):
    """从 yaml 取 esearch 调用参数（端点/库/时限/限速/退避），两个调用方共用。

    v3.17.0 收尾：有 NCBI key 时用更快的限速（10 req/s 上限内），无 key 用
    匿名限速（3 req/s 上限内，默认 0.4s **不调慢**）。
    """
    spec = ((tsc or {}).get("source_verification") or {}).get("pubmed") or {}
    key, note = _resolve_api_key(tsc)
    sleep = float(spec.get("rate_limit_sleep_with_key") or 0.11) if key \
        else float(spec.get("rate_limit_sleep") or 0.4)
    return {
        "endpoint": spec.get("endpoint"),
        "db": spec.get("db") or "pubmed",
        "timeout": float(spec.get("timeout_seconds") or 15),
        "sleep": sleep,
        "api_key": key,
        "max_retries": int(spec.get("max_retries", 3)),
        "backoff_base": float(spec.get("backoff_base", 2.0)),
        "backoff_cap": float(spec.get("backoff_cap", 30.0)),
        "suspect_threshold": int(spec.get("suspect_threshold", 2)),
        "abort_batch_on_rate_limit": bool(spec.get("abort_batch_on_rate_limit", True)),
        "note": note,
    }


def _source_labels(tsc=None):
    """kind → 来源类型显示名（读 yaml#three_source_check.sources[*].label）。

    v3.17.0 收尾：这三个 label 此前是"配了无人读"的死配置键（体检第 18 项 INFO）。
    现由报告真正消费——来源定档时带上显示名，报告里直接显示
    「PubMed 检索（PMID）」而不是裸 kind。改 label 会真实改变报告输出。
    """
    out = {}
    for s in ((tsc or {}).get("sources") or []):
        if isinstance(s, dict) and s.get("kind"):
            out[str(s["kind"])] = str(s.get("label") or s["kind"])
    return out


def _pmid_regex(tsc=None):
    """取 PMID 格式正则（唯一源 = yaml#three_source_check.format_rules.pmid）。

    yaml 未配该项时退回既有内置正则 `_PMID_RE` 并**显式告警**（受控逃生舱），
    不用"猜一个"的新正则——两份正则并存 = 同型双声明缺陷。
    """
    rules = ((tsc or {}).get("format_rules") or {})
    pat = rules.get("pmid")
    if not pat:
        return _PMID_RE
    try:
        return _re_ref.compile(pat)
    except Exception as e:
        print(f"⚠ yaml#three_source_check.format_rules.pmid 非法（{e}）——退回内置正则",
              file=sys.stderr)
        return _PMID_RE


def isbn_checksum_ok(code):
    """ISBN 校验位算法（ISBN-10 / ISBN-13）——**确定性结构校验**，不是存在性验证。

    ISBN-10：前 9 位权重 10..2，末位校验位权重 1（X 表示 10），和 % 11 == 0
    ISBN-13：权重 1/3 交替，和 % 10 == 0
    长度不受支持或含非数字 → False（不猜、不折算）。
    """
    c = re.sub(r"[^0-9Xx]", "", (code or ""))
    if len(c) == 10:
        if not c[:9].isdigit():
            return False
        s = sum((10 - i) * int(ch) for i, ch in enumerate(c[:9]))
        chk = 10 if c[9] == "X" else (int(c[9]) if c[9].isdigit() else -1)
        return chk >= 0 and (s + chk) % 11 == 0
    if len(c) == 13:
        if not c.isdigit():
            return False
        s = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(c))
        return s % 10 == 0
    return False


def _compile_rule(pattern, key):
    """编译 yaml 规则表里的正则；缺失/非法 → (None, 原因)。

    刻意**不内置正则兜底**：内置兜底 = 又一份"看起来生效其实没生效"的声明，
    且 yaml 与代码两份正则会漂移。缺规则 → 该 kind 判「不可核验」并显式告警。

    ⚠ 传入的是**已取出的规则字符串**（调用点用 rules.get("<键>") 取），
      这样"该规则有代码读取者"能被体检第 18 项的 AST 判据真实识别到。
    """
    if not pattern:
        return None, f"未配置 {key} 规则"
    try:
        return _re_ref.compile(pattern), ""
    except Exception as e:
        return None, f"{key} 规则非法（{e}）"


def collect_pending_pmids(cases, tsc=None):
    """收集需要联网实查的 PMID 列表（去重、保序）。

    只收 kind=pubmed、PMID 格式可解析、且不在静态黑名单（占位号/测试号）里的号。
    黑名单号静态即可判"假"，不必浪费一次网络请求。
    """
    rx = _pmid_regex(tsc)
    out, seen = [], set()
    for c in (cases or []):
        for src in ((c or {}).get("sources") or []):
            if str((src or {}).get("kind") or "").strip().lower() != "pubmed":
                continue
            m = rx.match(str((src or {}).get("ref") or "").strip())
            if not m:
                continue
            pmid = m.group(1)
            if pmid in _FAKE_PMIDS or pmid in seen:
                continue
            seen.add(pmid)
            out.append(pmid)
    return out


def _net_fetch(url, spec, want_json=False):
    """带重试/退避/限速的联网抓取（v3.17.0 B3-3：textbook/regulation 存在性核验用）。

    纪律（与 pubmed 通道一致）：
      · 超时 / 重试次数 / 退避基数 / 限速间隔**全部从 yaml 读**，代码不内置 —— 内置兜底
        = 又一份"看起来生效其实没生效"的声明（本包宪法）。
      · 失败**不静默**：返回 (None, 错误串)，由调用方决定退 format_fallback 还是
        判 network_error（fail-closed），绝不假装"没查到 = 不存在"（未命中 ≠ 证伪）。

    Args:
        url: 完整 URL（已由调用方按 yaml 模板拼好）
        spec: yaml#source_verification.<kind> 全段（取 timeout/retry/backoff/rate_limit）
        want_json: True = 解析为 JSON 返回 dict；False = 返回原始 bytes

    Returns:
        (data, err)：成功时 err=None；失败时 data=None 且 err 为可读原因
    """
    import time as _t
    import json as _json

    timeout = float(spec.get("timeout_seconds") or 25)
    max_retries = int(spec.get("max_retries") or 2)
    backoff_base = float(spec.get("backoff_base") or 3.0)
    backoff_cap = float(spec.get("backoff_cap") or 20.0)
    rate_sleep = float(spec.get("rate_limit_sleep") or 0)

    last_err = None
    for attempt in range(max_retries + 1):
        if rate_sleep and attempt > 0:
            _t.sleep(rate_sleep)          # 实测 opac.nlc.cn 连发即被限速 ⇒ 请求间必须睡
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (harness-three-source-verify)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            if want_json:
                return _json.loads(raw.decode("utf-8", "replace")), None
            return raw, None
        except Exception as e:            # 网络类失败：退避后重试，不做语义判定
            last_err = f"{type(e).__name__}: {e}"
            if attempt < max_retries:
                _t.sleep(min(backoff_base * (2 ** attempt), backoff_cap))
    return None, last_err


def _verify_isbn_checksum(ref, res, rules, tiers):
    """ISBN 校验位（确定性结构校验）——**仅格式合规**，不代表书存在。"""
    rx, err = _compile_rule(rules.get("isbn_candidate"), "isbn_candidate")
    if rx is None:
        res["reason"] = f"ISBN 校验不可用：{err}"
        return res
    norm = re.sub(r"[^0-9Xx]", "", ref)
    m = rx.search(norm)
    if not m:
        res["reason"] = f"未找到 ISBN 号：{ref!r}"
        return res
    code = m.group(0)
    if isbn_checksum_ok(code):
        res["tier"] = TIER_FORMAT
        res["tier_label"] = tiers.get(TIER_FORMAT) or "仅格式合规"
        res["reason"] = f"ISBN 校验位通过：{code}（**仅格式合规，未验证存在性**）"
    else:
        res["reason"] = f"ISBN 校验位不通过：{code}"
    return res


def _verify_gb_number_format(ref, res, rules, tiers):
    """国标/公告编号格式（确定性结构校验）——**仅格式合规**，不代表标准存在。"""
    rx, err = _compile_rule(rules.get("gb_number"), "gb_number")
    rx2, err2 = _compile_rule(rules.get("announcement_no"), "announcement_no")
    if rx is None and rx2 is None:
        res["reason"] = f"国标编号校验不可用：{err or err2}"
        return res
    if (rx and rx.search(ref)) or (rx2 and rx2.search(ref)):
        res["tier"] = TIER_FORMAT
        res["tier_label"] = tiers.get(TIER_FORMAT) or "仅格式合规"
        res["reason"] = f"编号格式合规：{ref!r}（**仅格式合规，未验证存在性**）"
    else:
        res["reason"] = f"国标/公告编号格式不合规：{ref!r}"
    return res


def _verify_isbn_online(ref, res, spec, rules, tiers, tsc):
    """textbook 存在性核验（v3.17.0 B3-3 实现）：按 yaml 的 endpoints 逐个实查。

    判定纪律（**不能核验的字段不得计入已验证**）：
      · 任一端点**命中** → 存在性已验证（该 ISBN 在该书目库中存在）
      · 两端点**均未命中** → 判「不可核验」+ 显式告警，**不判证伪**
        （未命中只说明"这两个库覆盖里没有"，不等于"这本书不存在"——
         实测 OpenLibrary 对中文教材覆盖稀疏，国图才覆盖中文书目）
      · 网络失败 → 退 format_fallback（校验位），仍不计入已验证 + 显式告警
    """
    rx, err = _compile_rule(rules.get("isbn_candidate"), "isbn_candidate")
    if rx is None:
        res["reason"] = f"ISBN 候选正则不可用：{err}"
        return res
    norm = re.sub(r"[^0-9Xx]", "", ref)
    m = rx.search(norm)
    if not m:
        res["reason"] = f"未找到 ISBN 号：{ref!r}（无法联网核验）"
        return res
    code = m.group(0)

    endpoints = spec.get("endpoints") or []
    if not endpoints:
        res["reason"] = "yaml#source_verification.textbook.endpoints 为空（无法联网核验）"
        return _verify_isbn_checksum(ref, res, rules, tiers)

    hits, misses, neterr = [], [], []
    for ep in endpoints:
        url_tpl = ep.get("url") or ""
        if "{isbn}" not in url_tpl:
            misses.append(f"{ep.get('id')}: url 模板缺 {{isbn}} 占位")
            continue
        url = url_tpl.replace("{isbn}", code)
        if str(ep.get("method") or "GET").upper() != "GET":
            misses.append(f"{ep.get('id')}: 暂只支持 GET")
            continue
        want_json = bool(ep.get("json_hit_path"))
        data, e = _net_fetch(url, spec, want_json=want_json)
        if e is not None:
            neterr.append(f"{ep.get('id')}: {e}")
            continue
        # 命中判据：JSON 端点看 json_hit_path 数值；HTML 端点看"未命中固定文案"
        if want_json:
            path = str(ep.get("json_hit_path") or "")
            cur = data
            for part in path.split("."):
                cur = (cur or {}).get(part) if isinstance(cur, dict) else None
            try:
                val = float(cur or 0)
            except (TypeError, ValueError):
                val = 0.0
            if val >= float(ep.get("json_hit_min") or 1):
                hits.append(ep.get("id"))
            else:
                misses.append(ep.get("id"))
        else:
            blob = data or b""
            absent = str(ep.get("absent_marker") or "")
            min_bytes = int(ep.get("min_hit_bytes") or 0)
            text = blob.decode("utf-8", "replace")
            # 二级判据（实测）：命中页显著大于未命中页；未命中页含固定文案
            if absent and absent not in text and len(blob) >= min_bytes:
                hits.append(ep.get("id"))
            else:
                misses.append(ep.get("id"))

    if hits:
        res["tier"] = TIER_EXISTENCE
        res["tier_label"] = tiers.get(TIER_EXISTENCE) or "存在性已验证"
        res["verified_by"] = hits
        res["reason"] = (f"ISBN:{code} 联网实查命中端点 {hits}（存在性已验证；"
                         f"未命中端点 {misses or '无'}）")
        return res

    if neterr and not misses:
        # 全部端点网络失败 → 退格式校验（仍不计入已验证），fail-closed 不谎报
        res["network_error"] = True
        out = _verify_isbn_checksum(ref, res, rules, tiers)
        out["reason"] = (f"联网核验失败（{'; '.join(neterr)}）——退回格式校验；"
                         f"**不计入已验证**")
        return out

    # 均未命中：不判证伪（覆盖不足 ≠ 书不存在）
    res["tier"] = TIER_UNVERIFIABLE
    res["tier_label"] = tiers.get(TIER_UNVERIFIABLE) or "不可核验"
    res["reason"] = (f"ISBN:{code} 在 {misses} 均未命中——**不判证伪**"
                     f"（未命中只说明这些库覆盖里没有，不等于书不存在）"
                     f"；网络异常：{'; '.join(neterr) or '无'}")
    return res


def _verify_gb_online(ref, res, spec, rules, tiers, tsc):
    """regulation 存在性核验（v3.17.0 B3-3 实现）：查全国标准信息公共服务平台。

    实测语义（**必须按实测实现，不得想当然**）：
      · 检索按**标准号前缀**匹配，不是"号-年"精确匹配：查「GB 10648」会同时返回
        GB 10648-1999[废止] 与 GB 10648-2013[现行]
      · 返回的 C_STD_CODE 夹 `<sacinfo>` 标记，比对前须剥
      · 只覆盖国家标准（GB/GB-T）；行业标准（NY/T 等）与公告号实测 total=0
        ⇒ 非国标号不走此端点，退格式校验并显式登记为「人工核验项」

    判定：
      · 命中且号+年份完全一致 → 存在性已验证（附 STATE/发布日期/实施日期）
      · 命中但只同号不同年 → 仅格式合规 + 告警（该号存在，但此年份版本未登记）
      · STATE 为废止/被代替 → 仍判存在，但置 state_warning（引用已废止标准是真错误）
      · 网络失败 / 非国标 → 退 gb_number_format（不计入已验证）
    """
    endpoint = spec.get("endpoint") or ""
    if not endpoint:
        res["reason"] = "yaml#source_verification.regulation.endpoint 缺失"
        return _verify_gb_number_format(ref, res, rules, tiers)

    rx, err = _compile_rule(rules.get("gb_number"), "gb_number")
    if rx is None:
        res["reason"] = f"国标编号正则不可用：{err}"
        return res
    m = rx.search(ref)
    if not m:
        # 非 GB 国标号（行业标准 NY/T、SN/T，或公告号）→ 该端点**不覆盖**（实测 total=0），
        # 判「不可核验」并显式登记为人工核验项；不得拿"格式不合规"误导——
        # 它格式是合规的，只是本端点查不到（实测特性，非编号错误）。
        out = _verify_gb_number_format(ref, res, rules, tiers)
        ann_rx, _ = _compile_rule(rules.get("announcement_no"), "announcement_no")
        is_ann = bool(ann_rx and ann_rx.search(ref))
        note = "公告号" if is_ann else "非 GB 国标号（行业标准/其它编号体系）"
        if out.get("tier") == TIER_FORMAT:
            out["reason"] += (f"；⚠ {note}——国标平台不覆盖，"
                              f"**列入人工核验项**（不等于编号错误）")
        else:
            out["tier"] = TIER_UNVERIFIABLE
            out["tier_label"] = tiers.get(TIER_UNVERIFIABLE) or "不可核验"
            out["reason"] = (f"{note}：{ref!r}——国标平台不覆盖（实测 total=0），"
                             f"**列入人工核验项**")
        return out
    std_no = m.group(0)

    import urllib.parse as _up
    q = _up.quote(std_no)
    url = f"{endpoint}?{spec.get('query_param') or 'searchText'}={q}" \
          f"&current=1&size={int(spec.get('page_size') or 10)}"
    data, e = _net_fetch(url, spec, want_json=True)
    if e is not None:
        res["network_error"] = True
        out = _verify_gb_number_format(ref, res, rules, tiers)
        out["reason"] = (f"国标平台联网失败（{e}）——退回格式校验；**不计入已验证**")
        return out

    rows = (data or {}).get("rows") or []
    try:
        total = float((data or {}).get("total") or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total < float(spec.get("json_hit_min") or 1) or not rows:
        out = _verify_gb_number_format(ref, res, rules, tiers)
        if out.get("tier") == TIER_FORMAT:
            out["reason"] += f"；国标平台未登记 {std_no}（人工核验项）"
        return out

    # 剥 <sacinfo> 标记后比对"号+年份完全一致"
    strip_rx = spec.get("strip_markers") or "<sacinfo>|</sacinfo>"
    def _norm_code(s):
        s = re.sub(strip_rx, "", str(s or ""))
        return re.sub(r"[\s\-—]", "", s).upper()

    want = _norm_code(std_no)
    exact = None
    for r in rows:
        if _norm_code(r.get(spec.get("field_code") or "C_STD_CODE")) == want:
            exact = r
            break

    if exact is None:
        res["tier"] = TIER_FORMAT
        res["tier_label"] = tiers.get(TIER_FORMAT) or "仅格式合规"
        codes = [_norm_code(r.get(spec.get("field_code") or "C_STD_CODE")) for r in rows]
        res["reason"] = (f"国标平台命中同号不同年：{std_no} 未完全匹配，命中 {codes}"
                         f"——**仅格式合规**（该号存在，此年份版本未登记）")
        return res

    state = str(exact.get(spec.get("field_state") or "STATE") or "").strip()
    res["tier"] = TIER_EXISTENCE
    res["tier_label"] = tiers.get(TIER_EXISTENCE) or "存在性已验证"
    res["verified_by"] = ["std_samr_gov_cn"]
    res["std_state"] = state
    res["std_name"] = exact.get(spec.get("field_name") or "C_C_NAME")
    res["std_issue_date"] = exact.get(spec.get("field_issue_date") or "ISSUE_DATE")
    res["std_act_date"] = exact.get(spec.get("field_act_date") or "ACT_DATE")
    res["reason"] = (f"国标平台命中 {std_no}（STATE={state}｜"
                     f"{res['std_name']}｜实施 {res['std_act_date']}）")
    if state and state not in ("现行", "即将实施"):
        # 引用已废止/被代替标准是真错误——此前格式校验完全查不出来
        res["state_warning"] = True
        res["reason"] += f"；⚠ **该标准已 {state}——引用它是真错误**"
    return res


def classify_source(src, tsc=None, online=None):
    """给**单条来源**定档 → {kind, ref, tier, tier_label, reason, refuted, network_error}。

    ⚠ 判定**不读 src.ok / src.verified_at**：那是自报值，v3.17.0 实测可被纯编造骗过。
      · existence_verified 只能由**联网实查命中**得到；
      · format_only 由确定性结构校验得到（ISBN 校验位 / 国标编号格式），**不代表存在**；
      · 联网失败（None）既不是"已验证"也不是"证伪"，单列 network_error 并告警。
    """
    online = online or {}
    src = src or {}
    kind = str(src.get("kind") or "").strip().lower()
    ref = str(src.get("ref") or "").strip()
    tsc = tsc or {}
    sv = (tsc.get("source_verification") or {})
    rules = (tsc.get("format_rules") or {})
    tiers = (tsc.get("tiers") or {})
    labels = _source_labels(tsc)
    res = {"kind": kind, "label": labels.get(kind) or kind, "ref": ref,
           "tier": TIER_UNVERIFIABLE,
           "tier_label": tiers.get(TIER_UNVERIFIABLE) or "不可核验",
           "reason": "", "refuted": False, "network_error": False}
    if not kind or not ref:
        res["reason"] = "缺 kind 或 ref"
        return res
    spec = (sv.get(kind) or {})
    mode = spec.get("mode")
    if not mode:
        res["reason"] = f"kind={kind} 无核验器（yaml#source_verification 未配该 kind）"
        return res

    if mode == "online_esearch":
        rx = _pmid_regex(tsc)
        m = rx.match(ref)
        if not m:
            res["reason"] = f"PMID 格式不合规：{ref!r}"
            return res
        pmid = m.group(1)
        if pmid in _FAKE_PMIDS:
            res["reason"] = f"PMID:{pmid} 在静态黑名单（占位号/测试号）"
            return res
        if pmid not in online:
            res["reason"] = f"PMID:{pmid} 未纳入本批联网核验（无实查结论）"
            return res
        verdict = online[pmid]
        if verdict is True:
            res["tier"] = TIER_EXISTENCE
            res["tier_label"] = tiers.get(TIER_EXISTENCE) or "存在性已验证"
            res["reason"] = f"PubMed esearch 命中 PMID:{pmid}（实查存在）"
        elif verdict is False:
            res["refuted"] = True
            res["reason"] = f"PubMed esearch 无此记录：PMID:{pmid}（实查**不存在**）"
        else:
            res["network_error"] = True
            res["reason"] = f"PMID:{pmid} 联网核验失败（网络/端点异常，未取得结论）"
        return res

    if mode == "isbn_online":
        # v3.17.0 B3-3：由"仅格式合规"升级为"可实查存在性"；失败退 format_fallback
        return _verify_isbn_online(ref, res, spec, rules, tiers, tsc)

    if mode == "gb_online":
        # v3.17.0 B3-3：由"仅格式合规"升级为"可实查存在性 + 现行状态"；失败退 format_fallback
        return _verify_gb_online(ref, res, spec, rules, tiers, tsc)

    if mode == "isbn_checksum":
        return _verify_isbn_checksum(ref, res, rules, tiers)

    if mode == "gb_number_format":
        return _verify_gb_number_format(ref, res, rules, tiers)

    res["reason"] = f"kind={kind} 的核验方式 mode={mode!r} 未实现——判「不可核验」"
    return res


def verify_three_source_case(case, tsc=None, online=None):
    """给**单案例**定档 → 案例级判定（口径见下，唯一源 = yaml#three_source_check）。

    判定口径：
      ① required_kinds 里每一类都须有 1 条达到「存在性已验证」或「仅格式合规」的来源
         （格式不过 / 无核验器 / 联网失败都不算该类已提供）——堵死"只留 1 条来源也能过"；
      ② 其中至少 required_existence_verified 条达到「存在性已验证」（"仅格式合规"不计入）；
      ③ 被实查**证伪**的来源若承担该类职责 → 案例判否（明示原因，不静默）；
      ④ 联网核验**失败** → 案例判「未取得结论」，不得计为已验证。
    """
    tsc = tsc or {}
    online = online or {}
    case = case or {}
    sources = case.get("sources") or []
    per_src = [classify_source(s, tsc, online) for s in sources]
    kinds_cfg = tsc.get("required_kinds") or []
    try:
        need_exist = int(tsc.get("required_existence_verified", 1))
    except Exception:
        need_exist = 1
    kind_status = {}
    for k in kinds_cfg:
        cands = [r for r in per_src if r["kind"] == k]
        if not cands:
            kind_status[k] = {"status": "missing", "reason": f"无 {k} 类来源",
                              "label": _source_labels(tsc).get(k) or k,
                              "ref": "", "refuted": False, "network_error": False}
            continue
        best = max(cands, key=lambda r: _TIER_RANK.get(r["tier"], 0))
        st = {"status": best["tier"], "reason": best["reason"], "ref": best["ref"],
              "label": best.get("label") or k,
              "refuted": best["refuted"], "network_error": best["network_error"]}
        if best["refuted"]:
            st["status"] = "refuted"
        elif best["network_error"]:
            st["status"] = "network_error"
        kind_status[k] = st
    exist_count = sum(1 for r in per_src if r["tier"] == TIER_EXISTENCE)
    refuted_all = [r for r in per_src if r["refuted"]]
    net_err_all = [r for r in per_src if r["network_error"]]
    bad_kinds = [k for k, v in kind_status.items()
                 if v["status"] in ("missing", TIER_UNVERIFIABLE, "refuted", "network_error")]
    if net_err_all:
        verdict = "network_incomplete"
    elif any(v["status"] == "refuted" for v in kind_status.values()):
        verdict = "refuted"
    elif bad_kinds:
        verdict = "insufficient_sources"
    elif exist_count < need_exist:
        verdict = "not_existence_verified"
    else:
        verdict = "pass"
    return {
        "case_id": case.get("case_id"),
        "title": case.get("title"),
        "deck_path": case.get("deck_path"),
        "verdict": verdict,
        "existence_verified": exist_count,
        "format_only": sum(1 for r in per_src if r["tier"] == TIER_FORMAT),
        "unverifiable": sum(1 for r in per_src if r["tier"] == TIER_UNVERIFIABLE),
        "refuted": len(refuted_all),
        "network_error": len(net_err_all),
        "kind_status": kind_status,
        "sources": per_src,
    }


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
    tsc = load_three_source_config()          # v3.17.0：PMID 格式正则与联网参数的唯一源
    pmid_rx = _pmid_regex(tsc)
    report = _static_ref_report(cases, pmid_rx)

    # ── v3.4.3 A2：--online 联网核验（esearch 命中 → 补 ok+verified_at）──
    # v3.17.0 关键修复：原实现只核验"缺 ok / 缺 verified_at"的来源——
    #   于是**编造**的来源只要把 ok=true + verified_at 写上，就**永远不会被实查**，
    #   静态预检也查不出（不在 5 个占位号黑名单里）→ 假核验闭环。
    #   现改为：**所有**格式可解析的 pubmed 来源一律实查；实查证伪的来源写回时
    #   强制降级 ok=false（自报"已核验"与实查结论冲突时，以实查为准）。
    #   ⚠ 溯源声明（主理人 2026-10-24 裁决批准保留）：**本行为 v3.17.0 越出
    #   闸4.5 范围**，因属**同一缺陷根因**（"自报 ok=true 的编造来源永不被实查"
    #   在 verify-ref 与闸4.5 是同一个出口）——治本需要两处同改，不是无关改动。
    online_summary = None
    if getattr(args, "online", False):
        todo = {}
        for c in cases:
            for src in (c.get("sources") or []):
                if (src.get("kind") or "").lower() != "pubmed":
                    continue
                m = pmid_rx.match((str(src.get("ref") or "").strip()))
                if not m or m.group(1) in _FAKE_PMIDS:
                    continue
                todo.setdefault(m.group(1), []).append(src)
        online_summary = {"checked": len(todo), "hit": 0, "miss": 0, "net_err": 0,
                          "refuted_pmids": []}
        if todo:
            # v3.17.0 收尾：api_key（真值只从环境变量读）+ 可配限速 + 遇速率限制指数退避
            ep = _esearch_params(tsc)
            print(ep["note"], file=sys.stderr)
            res = pmid_existence_check(sorted(todo), **{
                k: ep[k] for k in ("endpoint", "db", "timeout", "sleep", "api_key",
                                   "max_retries", "backoff_base", "backoff_cap",
                                   "suspect_threshold", "abort_batch_on_rate_limit")})
            for pmid, verdict in res.items():
                if verdict is True:
                    for src in todo[pmid]:
                        src["ok"] = True
                        src["verified_at"] = datetime.now().astimezone().isoformat(
                            timespec="seconds")
                    online_summary["hit"] += 1
                elif verdict is False:
                    for src in todo[pmid]:
                        # 实查证伪 → 自报的 ok=true 必须降级（否则假核验继续存活）
                        src["ok"] = False
                        src["verified_at"] = ""
                    online_summary["miss"] += 1
                    online_summary["refuted_pmids"].append(pmid)
                else:
                    online_summary["net_err"] += 1
            # 联网修复后复跑静态预检（ok 补齐后 stale_ok 应清零）
            report = _static_ref_report(cases, pmid_rx)
        print(f"🌐 online 核验：checked={online_summary['checked']} "
              f"hit={online_summary['hit']} miss={online_summary['miss']} "
              f"net_err={online_summary['net_err']}")
        if online_summary["refuted_pmids"]:
            print(f"⚠ 实查证伪（PubMed 无此记录，来源 ok 已降级为 false）："
                  f"{online_summary['refuted_pmids'][:20]}"
                  f"{' …' if len(online_summary['refuted_pmids']) > 20 else ''}",
                  file=sys.stderr)

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
            report = _static_ref_report(cases, pmid_rx)   # 写回后复检
            wrote_back = True
            print(f"💾 已写回 {p}（备份 {bak}）；复检 fake={len(report['fake'])} "
                  f"stale_ok={len(report['stale_ok'])} suspicious={len(report['suspicious'])}")
    # v3.17.0：结论必须区分"静态预检通过"与"存在性已实查"——
    #   旧版无论是否实查都打「✅ 全过」，实测把编造的 PMID 判成全过（自报 ok=true 即可）。
    #   现在：实查证伪 / 网络失败（未取得结论）一律非 0，且结论原文写明核验层级。
    static_bad = bool(report["fake"] or report["stale_ok"]
                      or report["suspicious"] or report["format_err"])
    refuted = list((online_summary or {}).get("refuted_pmids") or [])
    net_err = int((online_summary or {}).get("net_err", 0) or 0)
    if static_bad:
        verdict = "❌ 存在需处置项（静态预检）"
        rc = 1
    elif refuted:
        verdict = f"❌ 实查证伪 {len(refuted)} 条来源（引用在 PubMed 不存在）"
        rc = 1
    elif net_err:
        verdict = (f"⚠ 核验未完成（网络失败 {net_err} 条，未取得结论）"
                   f"——**不得读作「已通过」**")
        rc = 1
    elif online_summary:
        verdict = "✅ 全过（静态预检 + PubMed 联网实查）"
        rc = 0
    else:
        verdict = ("✅ 静态预检全过（**未验证存在性**——存在性须 --online 实查，"
                   "静态预检判不了「像真的但不存在」的引用）")
        rc = 0
    summary = {
        "total": report["total"],
        "fake_count": len(report["fake"]),
        "stale_ok_count": len(report["stale_ok"]),
        "suspicious_count": len(report["suspicious"]),
        "format_err_count": len(report["format_err"]),
        "ok_count": len(report["ok"]),
        "fake_unverified_count": len(report["fake_unverified"]),
        "verdict": verdict,
        "details": {k: v for k, v in report.items() if k != "total" and v},
        # v3.17.0：静态预检**只判格式与占位号**，判不了"像真的但不存在"——
        #   实查结论单列，避免结论被读成"引用都真实存在"。
        "existence_check": {
            "performed": bool(getattr(args, "online", False)),
            "note": "静态预检不验证存在性；存在性结论以 --online 实查为准",
            "online_summary": online_summary,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    _trace(w, cfg, "verify_ref", args.actor or "verifier",
           {"path": p, "fake": len(report["fake"]),
            "stale_ok": len(report["stale_ok"]), "suspicious": len(report["suspicious"]),
            "online": bool(getattr(args, "online", False)),
            "write_back": wrote_back,
            "online_summary": online_summary})
    return rc


# ─────────────────── 回传信封机器校验（B2）───────────────────
# v3.12.0：字段定义改为**读 references/result-envelope.yaml**（单一数据源）。
# 缘由：v3.11.0 及之前包内有三套互斥 schema（spawn-protocol.md 自称唯一权威源要求
# {from,stage,artifact,warnings,evidence_used,next_recommendation}，本文件校验
# {agent_id,task_id,phase,status,confidence,deliverable_summary}，agent MD 又一套），
# 按前者产出的**合规**信封会被本校验器判缺字段——自相矛盾，根因是"多处各自定义"。
# 现在：yaml 定义 → 本校验器读取 → agent MD 引用，三者同源。
_ENVELOPE_SCHEMA_CACHE = None


def load_envelope_schema(pkg_dir=None):
    """加载 references/result-envelope.yaml；失败回退内置常量（受控逃生舱）。

    不用内置常量当默认路径——那正是本缺陷的成因（代码里另立一套定义）。
    """
    global _ENVELOPE_SCHEMA_CACHE
    if _ENVELOPE_SCHEMA_CACHE is not None:
        return _ENVELOPE_SCHEMA_CACHE
    base = pkg_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "references", "result-envelope.yaml")
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            sc = yaml.safe_load(f)
        if not isinstance(sc, dict) or not sc.get("required"):
            raise ValueError("schema 缺 required 字段")
        _ENVELOPE_SCHEMA_CACHE = sc
        return sc
    except Exception as e:
        print(f"⚠ 回传信封 schema 读取失败（{e}），回退内置常量", file=sys.stderr)
        _ENVELOPE_SCHEMA_CACHE = {
            "required": ["agent_id", "task_id", "phase", "status",
                         "confidence", "deliverable_summary"],
            "status_enum": ["success", "partial", "failed", "blocked"],
            "legacy_aliases": {"from": "agent_id", "stage": "phase",
                               "artifact": "deliverable_summary",
                               "warnings": "issues",
                               "evidence_used": "evidence",
                               "next_recommendation": "next_agent_hint"},
            "validation": {"reject_legacy_keys": True, "strict_status_enum": True,
                           "normalize_before_check": True},
        }
        return _ENVELOPE_SCHEMA_CACHE


def _envelope_required():
    return load_envelope_schema()["required"]


def _envelope_status_set():
    return set(load_envelope_schema()["status_enum"])


def _normalize_envelope(env, schema=None):
    """把旧字段名归一化为新名（from→agent_id 等）。

    为什么要归一而不是直接判失败：既有 trace 里存着旧 schema 的信封，
    硬判失败会让历史回溯全线变红。归一后在报告里标注 normalized_keys，
    做到"能读旧、能写新、旧名不再被新产出使用"。
    """
    sc = schema or load_envelope_schema()
    aliases = sc.get("legacy_aliases") or {}
    if not aliases:
        return env, []
    renamed = {}
    for old, new in aliases.items():
        if old in env and new not in env:
            env[new] = env.pop(old)
            renamed[old] = new
    return env, renamed


def _extract_envelope(text):
    """从 markdown 文本里取出第一个 JSON 对象（优先 ```json 代码块）。"""
    import re as _re
    m = _re.search(r"```json\s*(\{.*?\})\s*```", text, _re.S)
    if m:
        return m.group(1)
    m = _re.search(r"\{.*\}", text, _re.S)
    return m.group(0) if m else None


# ── v3.17.0：内容判据执行器 ───────────────────────────────────────────
# 为什么单独成段：fields.*.rule 写了语义（confidence 禁裸标签、deliverable_summary
# 禁裸表述），但校验器只判"字段存在且非空"，规则与校验器是两套。
# 设计约束（与 result-envelope.yaml#validation.content_rules 配套）：
#   · 词表 / 正则 / 阈值 / 严重度**全部来自 yaml**，本段只做执行，不自带任何词表；
#   · 规则 id 与执行器一一对应；yaml 声明了规则但这里没注册执行器 → 显式告警
#     （防止又出现"规则写了没人执行"的同型缺陷）。
def _rule_has_evidence(s, patterns):
    """按 yaml 给的正则列表判断字符串里有没有"可复核依据"（任一命中即有）。"""
    import re as _re2
    for p in patterns or []:
        pat = p.get("pattern") if isinstance(p, dict) else p
        if not pat:
            continue
        try:
            if _re2.search(pat, s):
                return True, p.get("id") if isinstance(p, dict) else str(pat)
        except Exception as e:
            print(f"⚠ content_rules 正则不可编译（{pat!r}）：{e}——该证据项按未命中处理",
                  file=sys.stderr)
    return False, None


def _rule_confidence_not_bare(env, rule):
    """confidence 不得是裸标签：命中裸值集合，或过短且不含任何证据。"""
    fld = rule.get("field") or "confidence"
    s = str(env.get(fld, "") or "").strip()
    bares = [str(x).strip().lower() for x in (rule.get("bare_values") or [])]
    if s.lower() in bares:
        return False, f"{fld}={s!r} 命中裸值集合 {sorted(set(bares))}"
    ok, _ = _rule_has_evidence(s, rule.get("evidence_patterns"))
    if not ok and len(s) < int(rule.get("max_bare_length", 20)):
        return False, (f"{fld}={s!r} 长度 {len(s)} < {rule.get('max_bare_length', 20)} "
                       f"且不含任何依据（数字计数/文件路径/命令或工具名）")
    return True, ""


def _rule_deliverable_summary_verifiable(env, rule):
    """deliverable_summary 不得是裸表述：命中裸词集且无可验证计数，或过短且无可验证计数。

    ⚠ 关键细节（v3.17.0 实测修正）：命中裸词后要把**裸词本身从文本里剔除**再判
    "有没有可验证计数"（开关：evidence_check_excludes_bare_terms）。原因：
    "问题已修复归零" 里的"归零"含汉字数字"零"，会被证据正则当成"有计数"而漏网——
    裸表述自己给自己提供了计数，判据就废了。
    """
    fld = rule.get("field") or "deliverable_summary"
    s = str(env.get(fld, "") or "").strip()
    minlen = int(rule.get("min_verifiable_length", 24))
    # ① 先判裸词：命中则"剔除裸词后"再看有没有可验证计数（顺序不能反，
    #    否则裸词里的汉字数字会先被当成计数，判据直接失灵）
    hits = [t for t in (rule.get("bare_terms") or []) if str(t) in s]
    if hits:
        residue = s
        for t in hits:
            residue = residue.replace(str(t), "")
        if rule.get("evidence_check_excludes_bare_terms", True):
            ok2, _ = _rule_has_evidence(residue, rule.get("evidence_patterns"))
            if ok2:
                # 剔除裸词后仍有落盘路径/计数 → 只是措辞瑕疵，不是自评失真
                return True, ""
        return False, (f"{fld}={s!r} 命中裸词集 {hits}，且剔除裸词后的剩余文本"
                       f"{residue.strip()!r} 不含可验证计数（数字/路径）")
    # ② 未命中裸词：有过短且无可验证计数 → 判失败
    ok, _ = _rule_has_evidence(s, rule.get("evidence_patterns"))
    if not ok and len(s) < minlen:
        return False, (f"{fld}={s!r} 长度 {len(s)} < {minlen} 且不含可验证计数"
                       f"（数字/路径）——须写明落盘路径与原始 P0/P1/P2 计数")
    return True, ""


def _rule_status_issues_consistency(env, rule):
    """status 与 fields.status.criteria 的一致性：success 时 issues 必须为空。"""
    stt = str(env.get("status", "") or "").strip().lower()
    issues = env.get("issues")
    non_empty = bool(issues) if isinstance(issues, (list, dict, str)) else issues not in (None, "", 0)
    if stt == "success" and non_empty:
        return False, (f"status=success 但 issues 非空（{issues!r}）——按 "
                       f"fields.status.criteria 应为 partial/failed/blocked")
    return True, ""


def _rule_metrics_keys_subset(env, rule):
    """metrics 的键应是 fields.metrics.known_keys 的子集；越界键只告警（severity=warn）。

    v3.17.0：yaml 侧把 `keys`（硬限）改名为 `known_keys`（已知键白名单）。
    改名原因：硬限 2 键会把成员逼到「删指标」或「谎报键名」，比不登记更糟。
    兼容：若 yaml 仍是旧键 `keys`（老包/老配置），继续读它——但这是**显式的
    版本兼容**，不是"缺键补内置值"的静默兜底。
    """
    sc = load_envelope_schema()
    mf = (sc.get("fields") or {}).get("metrics") or {}
    allowed = set(mf.get("known_keys") or mf.get("keys") or [])
    m = env.get("metrics")
    if not isinstance(m, dict):
        return True, ""
    extra = sorted(set(m.keys()) - allowed)
    if extra:
        return False, f"metrics 含未登记键 {extra}；已登记键 {sorted(allowed)}"
    return True, ""


def _load_domain_ids():
    """读 config/domain-profiles.yaml 的域 id 集合（信封 domain 字段的枚举源）。

    v3.17.0 新增。**缺键即红**——domain 的枚举源读不到就不能校验 domain，
    静默放行等于让 domain 字段变成装饰品（与第 21/22 项同型盲区）。
    """
    import os as _os
    p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                      "..", "config", "domain-profiles.yaml")
    try:
        import yaml as _y
        with open(p, encoding="utf-8") as f:
            d = _y.safe_load(f) or {}
        doms = d.get("domains") or []
        ids = [x.get("id") for x in doms if isinstance(x, dict) and x.get("id")]
        return ids, None
    except Exception as e:
        return [], f"读 config/domain-profiles.yaml 失败（{e}）——域枚举源不可用，域字段无法校验"


def _rule_domain_in_profile(env, rule):
    """domain 必须在 config/domain-profiles.yaml 的域 id 集合内。

    v3.17.0 新增。通用化后信封必须能自证「这批产出属于哪个域」；
    域 id 写错会让 trace 与台账按域聚合时归错桶，故判失败（severity=fail）。
    """
    v = env.get("domain")
    if v in (None, ""):
        return True, ""                       # 未坍缩/未标域 → 不判失败
    if not isinstance(v, str):
        return False, f"domain 必须是字符串，收到 {type(v).__name__}：{v!r}"
    ids, err = _load_domain_ids()
    if err:
        return False, f"域枚举源不可用——{err}（不得静默放行，否则 domain 字段形同装饰品）"
    if v not in ids:
        return False, f"domain={v!r} 不在 config/domain-profiles.yaml 的域 id 集合内；合法值：{ids}"
    return True, ""


def _rule_routing_structure(env, rule):
    """routing 若提供，必须含 level / members / collapse_artifact 三个子键。

    v3.17.0 新增。它把「本次产出属于哪次路由与哪次坍缩」钉死在信封里，
    是通用化后可追溯性的最小保证。
    """
    r = env.get("routing")
    if r in (None, ""):
        return True, ""
    if not isinstance(r, dict):
        return False, f"routing 必须是对象，收到 {type(r).__name__}：{r!r}"
    need = ["level", "members", "collapse_artifact"]
    miss = [k for k in need if k not in r]
    if miss:
        return False, f"routing 缺子键 {miss}；结构见 references/result-envelope.yaml#fields.routing"
    if not isinstance(r.get("members"), list):
        return False, f"routing.members 必须是数组，收到 {type(r.get('members')).__name__}"
    return True, ""


# 规则 id → 执行器（新增 yaml 规则必须在此登记，否则校验器会告警"无执行者"）
_CONTENT_RULE_EXECUTORS = {
    "confidence_not_bare": _rule_confidence_not_bare,
    "deliverable_summary_verifiable": _rule_deliverable_summary_verifiable,
    "status_issues_consistency": _rule_status_issues_consistency,
    "metrics_keys_subset": _rule_metrics_keys_subset,
    "domain_in_profile": _rule_domain_in_profile,
    "routing_structure": _rule_routing_structure,
}


def _eval_content_rules(env, sc):
    """按 yaml#validation.content_rules 逐条执行内容判据。

    返回 (violations, warnings, disabled, unimplemented)，元素形如
    {"id":..., "severity":..., "rule_ref":..., "detail":..., "message":...}。
    """
    rules = ((sc.get("validation") or {}).get("content_rules") or [])
    violations, warnings, disabled, unimplemented = [], [], [], []
    for r in rules:
        if not isinstance(r, dict):
            continue
        rid = r.get("id") or "<无名规则>"
        if not r.get("enabled", True):
            disabled.append({"id": rid, "reason": r.get("disabled_reason", "").strip()})
            continue
        fn = _CONTENT_RULE_EXECUTORS.get(rid)
        if fn is None:
            unimplemented.append({"id": rid, "rule_ref": r.get("rule_ref", "")})
            continue
        ok, detail = fn(env, r)
        if ok:
            continue
        item = {"id": rid, "severity": r.get("severity", "fail"),
                "field": r.get("field", ""), "rule_ref": r.get("rule_ref", ""),
                "detail": detail, "message": r.get("message", ""),
                "defined_at": "references/result-envelope.yaml#validation.content_rules.%s" % rid}
        (violations if item["severity"] == "fail" else warnings).append(item)
    return violations, warnings, disabled, unimplemented


def cmd_verify_envelope(args):
    """校验成员回传的 result_envelope（把约定变成代码）。

    缘由（2026-10-04）：result_envelope 由 commit 7013f87 引入，但只写在 MD 里，
    成员"自觉遵守"——实测自报失真 4/4 个版本复发，说明约定必须有执行者。
    v3.12.0：字段改读 references/result-envelope.yaml，消除多套 schema 互斥。
    v3.17.0：新增**内容判据**——此前只判字段存在且非空，`confidence:"高"` 能过；
    现在按 yaml#validation.content_rules 逐条判裸标签/裸表述/status-issues 一致性/
    metrics 键子集，规则与词表全在 yaml（改 yaml 即改校验器）。
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

    sc = load_envelope_schema()
    vcfg = sc.get("validation") or {}
    # 旧字段名检测（在归一之前，先看清对方给了什么）
    aliases = sc.get("legacy_aliases") or {}
    legacy_hit = [k for k in env if k in aliases]
    if vcfg.get("normalize_before_check", True):
        env, renamed = _normalize_envelope(env, sc)
        if renamed:
            res["normalized_keys"] = renamed
    if vcfg.get("reject_legacy_keys", True) and legacy_hit and not res.get("normalized_keys"):
        res["verdict"] = (f"❌ 使用旧版字段名：{legacy_hit}；现行字段见 "
                          f"references/result-envelope.yaml，请改用新名")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    required = sc["required"]
    missing = [k for k in required if k not in env or env.get(k) in (None, "")]
    res["envelope"] = env
    res["missing"] = missing
    if missing:
        res["verdict"] = (f"❌ 信封缺字段：{missing}（判 partial，退回补充；"
                          f"字段定义见 references/result-envelope.yaml）")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    st = str(env.get("status", "")).lower()
    allowed = _envelope_status_set()
    if st not in allowed:
        res["verdict"] = f"❌ status 取值非法：{st!r}（应为 {'/'.join(sorted(allowed))}）"
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1

    # v3.17.0：内容判据（只判存在性拦不住 confidence:"高" 这类自评失真）
    violations, warns, disabled, unimpl = _eval_content_rules(env, sc)
    res["content_rules"] = {
        "checked": len(((sc.get("validation") or {}).get("content_rules") or [])),
        "violations": violations, "warnings": warns,
        "disabled": [{"id": d["id"], "reason": d["reason"]} for d in disabled],
    }
    if unimpl:
        # 规则已声明但无执行者 = 又一套"写了不执行"，必须显式暴露
        print(f"⚠ {len(unimpl)} 条 content_rules 已启用但 harness.py 无对应执行器："
              f"{[u['id'] for u in unimpl]}——规则当前未生效，请补注册。", file=sys.stderr)
        res["content_rules"]["unimplemented"] = unimpl
    if violations:
        refs = "；".join(f"{v['rule_ref']}（{v['defined_at']}）" for v in violations)
        res["verdict"] = (f"❌ 信封内容不合规：{len(violations)} 条——"
                          + " | ".join(f"[{v['id']}] {v['detail']}" for v in violations)
                          + f"（判据见 {refs}）")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1
    if warns:
        res["content_warnings"] = warns
        for w in warns:
            print(f"⚠ [{w['id']}] {w['detail']}——{w['message']}"
                  f"（判据见 {w['rule_ref']}，{w['defined_at']}）", file=sys.stderr)
    # 产物路径真实性交叉核验（若有 artifact/deliverable 字段）
    art = env.get("deliverable") or env.get("artifact_path") or ""
    if isinstance(art, str) and art.startswith("/") and not os.path.exists(art):
        res["verdict"] = f"⚠ 信封声明的产物不存在：{art}（疑自评失真，先落盘再放行）"
        res["verdict_ok"] = True          # 字段齐备，但需人工处理
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    res["verdict"] = "✅ 信封合规" + (f"（含 {len(warns)} 条告警，见 content_warnings）" if warns else "")
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

# v3.17.0：终止原因的唯一源改为 harness.yaml#loop_b.termination（见 load_term_reasons）。
#   本常量降级为**兜底**：仅当 yaml 缺失/为空时启用，且启用时打印告警。
#   ⚠ 不要在这里新增终止原因——加了也不会生效（这正是本批要修的"双声明静默失效"）。
_FALLBACK_TERMINATIONS = ["成功完成", "等待用户", "能力或证据阻塞", "达到预算但未完成", "用户取消"]
LOOP_TERMINATIONS = _FALLBACK_TERMINATIONS   # 兼容旧引用；实际判定一律走 load_term_reasons(cfg)
LOOP_INTAKE_A = ["audience", "periods", "template", "scope", "acceptance"]  # A 类五项：缺一即停


def _intake_item_state(v):
    """判定一个 A 类 intake 项的**就绪态**。返回 (state, detail)。

    state 取值：
      "missing"    —— 未登记 / 空值
      "unconfirmed"—— 已登记但**未确认**（dict 且 status != "confirmed"）
      "confirmed"  —— 已确认

    ⚠ v3.18.0 新增「unconfirmed」态（缺陷 D2，2026-10-25 从零诊断实测复现）：
      此前 intake 校验只判 `not intake.get(k)`，于是 A 类五项若值为
      `{"value": "...", "status": "suggested"}`（**已填但未确认**），
      `intake.get(k)` 为真 → 直接判 confirmed 并放行，与
      `references/task-intake-checklist.md` 的「存在 suggested 即不得进入制作」矛盾。
      ⇒ 未确认 ≠ 已确认，必须分开判。

    兼容性：
      · 纯标量 / 字符串 → 保持旧行为（非空即算已确认），不破坏既有纯标量用法；
      · list           → 非空即算已登记（list 元素若为 dict 且含 status，
                          则要求至少一个 status == "confirmed"）；
      · dict           → 必须 status == "confirmed"。
    """
    if v in (None, [], {}, ""):
        return "missing", "未登记"
    if isinstance(v, dict):
        st = str(v.get("status") or "").strip()
        if st == "confirmed":
            return "confirmed", "已确认"
        if st:
            return "unconfirmed", f"已登记但状态为 {st}（须 confirmed）"
        return "unconfirmed", "已登记但未标 status（须 confirmed）"
    if isinstance(v, list):
        dicts = [x for x in v if isinstance(x, dict)]
        if dicts:
            if any(str(x.get("status") or "").strip() == "confirmed" for x in dicts):
                return "confirmed", "已确认"
            return "unconfirmed", "已登记但无 confirmed 条目"
        return "confirmed", "已登记"
    return "confirmed", "已登记"


def _intake_item_confirmed(v):
    """判定 A 类五项中的一项是否**已确认**（不只是"非空"）。布尔版（供简洁调用）。

    背景（D2 实测复现）：此前 `cmd_loop intake` 与 `cmd_loop make-gate` 都只判
    `not intake.get(k)`——而 A 类五项的登记格式是 dict
    （见 references/task-intake-checklist.md:134）：
        {"value": "高职大二", "status": "confirmed|suggested"}
    一个 `status="suggested"`（**未确认**）的 dict 是非空的 ⇒ `intake.get(k)` 为真
    ⇒ 被判为已确认 ⇒ 直接放行进制作。这与
    references/task-intake-checklist.md:158-159 的硬要求
    「A 类 5 项 status 必须全为 confirmed——存在 suggested 即不得进入制作阶段」
    **直接矛盾**，且是"文档说要拦、代码不拦"的典型双声明失效。

    ⚠ v3.18.0：核心判据统一在 `_intake_item_state()`（三态：missing / unconfirmed /
      confirmed）；本函数只是它的布尔薄封装，供不需要区分"缺失 vs 未确认"的调用方使用。
      两者**必须同源**——曾并存两份实现，正是本项目「同一口径两处漂移」的典型病灶。
    """
    state, _detail = _intake_item_state(v)
    return state == "confirmed"


def _intake_a_gaps(intake):
    """把 A 类五项分成两组：**缺失**（没登记）与**未确认**（登记了但 status 非 confirmed）。

    返回 (missing, unconfirmed) 两个列表，二者元素均为 A 类键名。
    · missing     —— 键不存在，或值为空（None / "" / 空 list / 空 dict）
    · unconfirmed —— 值非空但 `_intake_item_state(v)` 判为 "unconfirmed"

    为什么必须区分这两组：两者对主理人的**处置动作不同**——
      缺失 → "还没问，去问"；未确认 → "问过了但用户没拍板，去追认"。
    混在一个 missing_A 里等于把"未确认"伪装成"缺失"，用户会以为没登记过，
    从而绕过"追认"这一步直接重填——那正是 D2 缺陷得以放行的心理路径。
    """
    intake = intake if isinstance(intake, dict) else {}
    missing, unconfirmed = [], []
    for k in LOOP_INTAKE_A:
        state, _detail = _intake_item_state(intake.get(k))
        if state == "missing":
            missing.append(k)
        elif state == "unconfirmed":
            unconfirmed.append(k)
    return missing, unconfirmed


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


def _state_lock_path(w, loop):
    return _loop_state_path(w, loop) + ".lock"


class _StateLock:
    """状态文件的跨进程文件锁（v3.12.0；v3.17.0 泛化到 task_state.json）。

    为什么需要：`_write_loop_state` 全包 20 处调用，且都是「读 JSON → 改内存 → 写回」的
    读-改-写模式。两个 harness 进程并发跑（如主理人一边 freeze 一边 verify）会：
      ① 后写者覆盖先写者 → 丢条目（lost update）
      ② 裸 open(w) 截断后崩溃 → 文件半截，JSON 解析失败 → 状态被当空状态处理（更糟：静默重置）
    两者都不会产生「schema 字段对不上」那种症状，故与信封互斥是两回事——
    信封互斥的根因是"多处各自定义 schema"（见 references/result-envelope.yaml），
    本锁解决的是并发写的丢更新与半写问题。

    实现：fcntl.flock 排他锁，跨进程有效（Windows 无 fcntl 时退化为进程内互斥并告警）。
    用法：with _StateLock(w, loop): st = _read_loop_state(...); ... ; _write_loop_state(...)

    v3.17.0：新增 path 参数——task_state.json 不是 Loop 状态文件（路径不同），
      但**并发写丢更新/半写**是同一个问题，故复用同一把锁的实现（不再各写一套）。
      ⚠ flock 绑定在 open file description 上：**同一进程重复加锁会自死锁**，
        故调用方需用 write_state(..., locked=True) 表达"我已持锁"。
    """

    def __init__(self, w, loop=None, timeout=5.0, path=None):
        self.path = path if path else _state_lock_path(w, loop)
        self.timeout = timeout
        self._fh = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            import fcntl
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            # Windows / 无 fcntl：退化为进程内锁（只防线程，不防跨进程），显式告警
            print("⚠ 无 fcntl，Loop 状态锁退化为进程内（跨进程并发写仍需串行调度）",
                  file=sys.stderr)
        except OSError as e:
            print(f"⚠ 取 Loop 状态锁失败：{e}（继续，可能有并发写风险）", file=sys.stderr)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
        return False   # 不吞异常


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
    """原子写：先写同目录临时文件 → fsync → os.replace 覆盖。

    为什么必须原子（v3.12.0）：原实现裸 open(path,"w") 会先截断文件。若此刻进程被杀 /
    磁盘满 / 并发读到中间态，磁盘上留下半截 JSON；`_read_loop_state` 解析失败会
    「按空状态处理」——等于静默把整个 Loop 状态重置，比丢几条更严重。
    os.replace 在同一文件系统内是原子的，读者要么看到旧版要么看到新版，不存在半截态。

    v3.17.0：实现下沉到 _atomic_write_json()，与 task_state.json 共用同一份原子写
    （此前同文件里两套标准：Loop B 侧有原子写，task_state 侧裸写）。
    """
    path = _loop_state_path(w, loop)
    _atomic_write_json(path, st)


def _loop_quality_snapshot(st, rnd, p0, p1, p2, source="", extra=None):
    """记录一轮结束时的质量快照（P0/P1/P2 计数），供"有无进展"判定。

    v3.17.0：loop_b.budgets.no_progress_threshold 此前零命中——配了阈值但没有任何
    执行者，缺陷数不再下降这件事机器检不出来。本函数是它的落点。
    同一轮重复记录按"后者覆盖前者"处理（返修后复测值应为最新值）。

    source（v3.17.0 F6 补）：数据从哪来——"verify_json|<报告路径>"（verify_deck 机器复算，
    优先）或 "manual"（成员/主理人自报，未经交叉核验）。**必须写进快照**：
    只知道数字不知道来源，就等于无法判断这个数能不能信（本包"工具自报不算数"纪律）。
    """
    # v3.17.0 B3-4：p0p1p2 与 p0p1 并存 —— 收敛判据改看三者合计（见
    #   _loop_no_progress_streak）；保留 p0p1 供既有报表/旧快照兼容消费。
    snap = {"round": int(rnd), "p0": int(p0), "p1": int(p1), "p2": int(p2),
            "p0p1": int(p0) + int(p1),
            "p0p1p2": int(p0) + int(p1) + int(p2), "ts": now_iso()}
    if source:
        snap["source"] = source
    if extra:
        snap.update(extra)
    hist = [h for h in (st.get("quality_history") or []) if int(h.get("round", -1)) != int(rnd)]
    hist.append(snap)
    hist.sort(key=lambda h: int(h.get("round", 0)))
    st["quality_history"] = hist
    return snap


class _QualityReportError(Exception):
    """--verify-json 取数失败：code=3 报告不存在，code=2 不可解析/缺字段/课件不匹配。"""

    def __init__(self, msg, code=2):
        super().__init__(msg)
        self.code = code


def _deck_binding_targets(st):
    """本轮 loop 的「目标课件」集合：原件 + 工作副本目录。

    v3.17.0 B2-2：--verify-json 报告必须绑定到本轮课件。此前只校验报告**结构**，
    从不校验它对应哪份 pptx（课件路径只在 stats.file，代码不读它）——
    实测把**另一份完全不同的课件**的报告喂进来，照单全收并参与收敛判定。
    """
    out = []
    src = (st or {}).get("source_ppt") or {}
    if src.get("path"):
        out.append(("原件", os.path.realpath(os.path.abspath(src["path"]))))
    wip = (st or {}).get("wip_dir")
    if wip:
        out.append(("工作副本目录", os.path.realpath(os.path.abspath(wip))))
    return out


def _report_deck_matches(rfile, targets):
    """报告的 stats.file 是否落在本轮目标课件内 → (是否匹配, 命中标签)。

    比较用 realpath（macOS 的 /var → /private/var 软链会让 abspath 失配）。
    """
    rp = os.path.realpath(os.path.abspath(rfile))
    for label, t in targets or []:
        if rp == t:
            return True, label
        if os.path.isdir(t) and rp.startswith(t.rstrip(os.sep) + os.sep):
            return True, label
    return False, ""


def _load_quality_from_verify_json(path, expect_deck=None):
    """从 `verify_deck.py --json` 报告里取本轮 P0/P1/P2（**报告优先**于手工自报）。

    为什么必须有这条路（v3.17.0 F6）：`--p0/--p1/--p2` 手工值理论上可注水，而
    verify_deck 早就有 `--json` 报告——机器复算的结果必须是第一数据源，人手填的只能
    当"没有报告时的次选"，并且要在输出里标明未核验。

    失败策略（铁律：不静默）：
      · 文件不存在 → code 3（依赖缺失）
      · 顶层不是对象 / 缺 gate 段 / gate 缺 p0|p1 / 既无 p2 也无 p2_block → code 2
      · **v3.17.0 B2-2**：缺 stats 段 / 缺 stats.file / 报告对应**别的课件** → code 2
    两种都不退回手工值、**也不按 0 处理**——静默取 0 会造出"本轮缺陷为 0"的假象，
    比不取数更危险（会让 no_progress 判据反向失灵）。
    """
    p = os.path.abspath(path)
    if not os.path.isfile(p):
        raise _QualityReportError(
            f"报告不存在：{p}（先用 `verify_deck.py <课件> --hours N --level all "
            f"--json <路径>` 产出再进位）", 3)
    try:
        with open(p, encoding="utf-8") as f:
            rep = json.load(f)
    except Exception as e:
        raise _QualityReportError(f"报告不可解析：{p}（{e}）", 2)
    if not isinstance(rep, dict):
        raise _QualityReportError(f"报告顶层不是对象：{p}（{type(rep).__name__}）", 2)

    # ── v3.17.0 B2-2：报告与本轮课件的绑定校验（此前**只校验结构，不校验归属**）──
    stats = rep.get("stats")
    if not isinstance(stats, dict):
        raise _QualityReportError(
            f"报告缺 stats 段：{p}（顶层键 {sorted(rep)}）——无法确认这份报告对应哪份课件，"
            f"拒绝采用（宁可无数据，不拿错课件的数据算收敛）", 2)
    rfile = stats.get("file")
    if not rfile or not isinstance(rfile, str):
        raise _QualityReportError(
            f"报告 stats.file 缺失或非法：{p}（stats 键 {sorted(stats)}）——"
            f"无法确认这份报告对应哪份课件，拒绝采用", 2)
    if expect_deck:
        ok, label = _report_deck_matches(rfile, expect_deck)
        if not ok:
            targets = "；".join(f"{lab}={t}" for lab, t in expect_deck)
            raise _QualityReportError(
                f"报告对应的是**另一份课件**：stats.file={rfile!r}，"
                f"本轮目标课件（{targets}）——拒绝采用"
                f"（拿别处课件的报告喂收敛判据 = 拿别人的成绩单算自己的进度）", 2)

    gate = rep.get("gate")
    if not isinstance(gate, dict):
        raise _QualityReportError(
            f"报告缺 gate 段：{p}（顶层键 {sorted(rep)}）——确认这是 verify_deck --json 的产物？", 2)

    def _req_int(k):
        if k not in gate:
            raise _QualityReportError(
                f"报告 gate 缺 {k}：{p}（gate 键 {sorted(gate)}）——不按 0 处理，先修报告", 2)
        v = gate[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _QualityReportError(
                f"报告 gate.{k} 不是数值：{v!r}（{type(v).__name__}）——不猜、不折算", 2)
        return int(v)

    p0, p1 = _req_int("p0"), _req_int("p1")
    # P2：报告给的是 p2_block(布尔) + note_coverage，没有 p2 计数；
    #   有 gate.p2 数值就用数值，否则按 p2_block 折算 1/0，并把折算口径写进快照（可追溯）
    if isinstance(gate.get("p2"), int) and not isinstance(gate.get("p2"), bool):
        p2, p2_basis = int(gate["p2"]), "gate.p2"
    elif "p2_block" in gate:
        p2, p2_basis = (1 if bool(gate["p2_block"]) else 0), "gate.p2_block(bool→1/0)"
    else:
        raise _QualityReportError(
            f"报告 gate 既无 p2 也无 p2_block：{p}（gate 键 {sorted(gate)}）——不按 0 处理", 2)
    return {"p0": p0, "p1": p1, "p2": p2, "p2_basis": p2_basis,
            "note_coverage": gate.get("note_coverage"), "path": p}


def _loop_no_progress_streak(hist):
    """连续多少轮 P0+P1+P2 合计「未下降」（相邻两轮逐一比较，遇下降即归零）。

    语义：比较次数 = len(hist)-1；连续 N 次"没变好"即触发（N 取自 no_progress_threshold）。
    只有 1 条快照时无从比较 → 返回 0（宁可不判，也不凭空触发）。

    v3.17.0 B3-4：**P2 纳入判据**（此前只比 p0p1）。
      缺陷场景（实测可构造）：一轮只把「备注覆盖率」补达标（P2 阻断解除，
      p2: 1 → 0），P0/P1 一个没动 ⇒ 旧判据看 p0p1 持平 → 判「无进展」并终止，
      而**质量实际在推进**（P2 门禁从阻断变通过）。这是把"有效推进"误杀为"空转"。
      方向说明（**不可搞反**）：P0/P1/P2 在本包口径里**同向**——都是"缺陷/
      阻断计数"，**越少越好**；P2 阻断的语义是「备注覆盖率**未达标**」
      （1=未达标/阻断，0=达标），不是"覆盖率百分比"本身，故可直接相加。
      若将来把 p2 改成"覆盖率百分比（越高越好）"，本函数必须同步改向，
      不能简单相加。

    向后兼容：旧快照可能没有 p0p1p2 键 → 用 p0p1 + p2 现算（p2 缺失按 0）。
    """
    hist = [h for h in (hist or []) if isinstance(h, dict)]
    if len(hist) < 2:
        return 0

    def _total(h):
        if h.get("p0p1p2") is not None:
            return int(h["p0p1p2"])
        return int(h.get("p0p1", 0)) + int(h.get("p2", 0) or 0)

    streak = 0
    for prev, cur in zip(hist, hist[1:]):
        if _total(cur) >= _total(prev):
            streak += 1
        else:
            streak = 0
    return streak


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
            # v3.17.0：质量快照序列（每轮 continue 带 --p0/--p1/--p2 追加一条；
            # 供 no_progress_threshold 收敛判据消费）
            "quality_history": [],
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

    # ── v3.12.0：状态事务加锁 ────────────────────────────────────────
    # 上面这次 _read_loop_state 与下面 10+ 分支里的 _write_loop_state 构成一个
    # 「读-改-写」事务。两个 harness 进程并发跑（主理人一边 freeze 一边 verify、
    # 或自动化脚本并发调 add-item）会丢更新（后写者用旧快照覆盖先写者的改动）。
    # 这里把锁提到「读完状态」之前，持有到函数结束，保证事务内不被他人插入。
    # 只读动作（status/resume/terminate）也加锁——它们不写，但可能读到写了一半的状态；
    # 原子写已保证不会读到半截 JSON，加锁额外保证读到的是"某个已提交版本"而非中间态。
    _lock = _StateLock(w, "b")
    _lock.__enter__()
    try:
        st = _read_loop_state(w, "b")   # 持锁后重读，确保用的是最新快照
        return _loop_dispatch(args, cfg, w, loop, st, budgets)
    finally:
        _lock.__exit__()


def _loop_dispatch(args, cfg, w, loop, st, budgets):
    """loop 状态机各动作分派（v3.12.0 从 cmd_loop 抽出，以便整体包在锁内）。

    注意：函数体原样承接 cmd_loop 的后续分支，调用方已持锁并已读完最新状态。
    """
    lb = cfg.get("loop_b", {}) or {}
    la = cfg.get("loop_a", {}) or {}
    # ── intake：九项登记（A 类五项齐 + **全部 confirmed** 才算 confirmed）
    # v3.18.0 D2：此前只判 `not intake.get(k)`（非空即算确认），导致 A 类五项以
    #   {"status": "suggested"}（未确认）登记时被判为已确认并放行进制作——
    #   与 references/task-intake-checklist.md:158-159「存在 suggested 即不得进入制作」
    #   直接矛盾。现统一走 _intake_a_gaps()：区分「缺失」与「未确认」两组。
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
        if getattr(args, "replace", False):
            # ── v3.18.0：--replace 整体替换 ──────────────────────
            # 缺陷（实测发现）：intake 此前是**增量合并**——本次文件里删掉的键
            #   在状态文件里**永远删不掉**（旧值仍在）⇒ 用户/主理人"撤回某一项"
            #   在系统里无法表达，缺失项会一直显示为已登记。
            #   ⇒ 提供显式 --replace：本次文件即完整快照（未出现的键视为未登记）。
            #   默认仍是合并（**向后兼容**既有递进式登记流程）。
            intake.clear()
        for k, v in data.items():
            intake[k] = v
        missing, unconfirmed = _intake_a_gaps(intake)
        # ⚠ intake["confirmed"] 的语义与类型**不变**（仍是 bool），保持向后兼容：
        #   它现在的含义从"五项非空"收紧为"五项齐且全部 confirmed"。
        intake["confirmed"] = not (missing or unconfirmed)
        _loop_hist(st, "intake", {"filled": sorted(data.keys()),
                                  "missing": missing, "unconfirmed": unconfirmed})
        _write_loop_state(w, "b", st)
        # missing_A 字段名保留（兼容既有消费方）；新增 unconfirmed_A 区分"未确认"。
        out = {"confirmed": intake["confirmed"], "missing_A": missing,
               "unconfirmed_A": unconfirmed}
        if unconfirmed:
            out["note"] = (f"A 类五项中有 {len(unconfirmed)} 项登记了但 status 不是 confirmed"
                           f"（{unconfirmed}）——须先在轮报中请用户追认，"
                           f"存在 suggested 即不得进入制作")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if not (missing or unconfirmed) else 1

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
            # v3.17.0：质量收敛判据的可观测面（no_progress_threshold 此前零命中，
            # 现在每轮 continue 带 --p0/--p1/--p2 即落 quality_history）
            "quality_history": st.get("quality_history", []),
            "no_progress_streak": _loop_no_progress_streak(st.get("quality_history") or []),
            "no_progress_threshold": (st.get("budgets") or {}).get(
                "no_progress_threshold", (lb.get("budgets") or {}).get("no_progress_threshold", 2)),
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
        # v3.17.0 F6：质量收敛判据——每轮结束（进位时）记该轮 P0/P1/P2 快照。
        # 为什么挂在 continue：一轮的产出在此刻定稿，是唯一能拿到"本轮真实缺陷数"的时点；
        # 而 loop_b.budgets.no_progress_threshold 此前**零命中**（配了无执行者），
        # 五类终止条件全是工作量/交互维度，机器检不出"缺陷数已不再下降"。
        rnd_end = int(st.get("current_round", 1))
        snap = None
        vjson = getattr(args, "verify_json", "") or ""
        manual_given = args.p0 is not None or args.p1 is not None or args.p2 is not None
        allow_unverified = bool(getattr(args, "allow_unverified", False))

        # ── v3.17.0 B2-2：手工填数受限（治"递减假数序列"绕过）────────────
        # 攻击实测：手工 --p0 逐轮递减（9→7→5→3）能让每轮都判"有进展"，
        #   真实情况该课件 P0 恒为 3、从未变好，收敛判据永不触发。
        # 规则：一旦 quality_history 里已出现**非 verify_json 来源**的条目，
        #   后续轮次**强制**要求 --verify-json；逃生口 --allow-unverified 须留痕
        #   （写 blockers + trace 事件 + 快照 source=manual_unverified）。
        prior_hist = st.get("quality_history") or []
        prior_manual = [(h.get("round"), h.get("source")) for h in prior_hist
                        if not str(h.get("source") or "").startswith("verify_json|")]
        if manual_given and not vjson and prior_manual and not allow_unverified:
            print(f"⛔ 拒绝进位：quality_history 已存在**非机器复算来源**的质量快照 "
                  f"{prior_manual[:5]}——手工 --p0/--p1/--p2 理论可注水，"
                  f"历史轮已用手工值则后续轮次必须改用 --verify-json <verify_deck 报告>。\n"
                  f"   确无报告可显式声明 --allow-unverified（会登记 blocker 事件、"
                  f"快照标 source=manual_unverified，且 make-gate 会阻断）。", file=sys.stderr)
            return 2

        if vjson:
            # 报告优先：verify_deck 机器复算 > 手工自报（自报理论可注水）
            try:
                q = _load_quality_from_verify_json(vjson, expect_deck=_deck_binding_targets(st))
            except _QualityReportError as e:
                print(f"⛔ 质量取数失败（--verify-json {vjson}）：{e}——"
                      f"不静默退回手工值、也不按 0 处理。请产出有效报告后重试；"
                      f"确无报告请去掉 --verify-json 改用 --p0/--p1/--p2"
                      f"（输出会标 source=manual 未核验）。", file=sys.stderr)
                return e.code
            src = f"verify_json|{q['path']}"
            extra = {"p2_basis": q["p2_basis"], "note_coverage": q["note_coverage"],
                     "report_path": q["path"]}
            if manual_given and (args.p0, args.p1, args.p2) != (q["p0"], q["p1"], q["p2"]):
                extra["manual_ignored"] = {"p0": args.p0, "p1": args.p1, "p2": args.p2}
                print(f"⚠ 手工 --p0/--p1/--p2（{args.p0}/{args.p1}/{args.p2}）与报告"
                      f"（{q['p0']}/{q['p1']}/{q['p2']}）冲突：**以报告为准**"
                      f"（工具自报不算数），手工值仅存证不采用。", file=sys.stderr)
            snap = _loop_quality_snapshot(st, rnd_end, q["p0"], q["p1"], q["p2"],
                                          source=src, extra=extra)
            _loop_hist(st, "quality_snapshot", snap)
        elif manual_given:
            # v3.17.0：source 区分 "manual"（首轮自报）与 "manual_unverified"
            #   （已用过自报值后又用 --allow-unverified 强行自报）——后者留痕更重。
            src = "manual_unverified" if (prior_manual or allow_unverified) else "manual"
            extra = {"unverified": "自报值，未经 --verify-json 交叉核验"}
            if allow_unverified:
                extra["allow_unverified"] = True
                extra["reason"] = ("显式逃生口：已声明本轮质量数无机器复算报告可依"
                                   "（降级为未核验自报）")
                st.setdefault("blockers", []).append(
                    {"kind": "unverified_quality_source",
                     "detail": f"第 {rnd_end} 轮质量数来自手工自报（--allow-unverified）："
                               f"p0={args.p0 or 0} p1={args.p1 or 0} p2={args.p2 or 0}；"
                               f"未经 verify_deck 报告交叉核验，不得据此宣布达标",
                     "ts": now_iso()})
                _loop_hist(st, "quality_source_unverified",
                           {"round": rnd_end, "p0": args.p0 or 0, "p1": args.p1 or 0,
                            "p2": args.p2 or 0})
                _trace(w, cfg, "quality_source_unverified", "team-lead",
                       {"loop": "B", "round": rnd_end, "p0": args.p0 or 0,
                        "p1": args.p1 or 0, "p2": args.p2 or 0,
                        "note": "手工自报（--allow-unverified）——非机器复算"})
                print(f"⚠ 本轮质量数取自手工 --p0/--p1/--p2 且带 --allow-unverified："
                      f"已登记 blocker 事件（kind=unverified_quality_source），"
                      f"快照 source={src}，make-gate 会因此阻断。", file=sys.stderr)
            snap = _loop_quality_snapshot(st, rnd_end, args.p0 or 0, args.p1 or 0, args.p2 or 0,
                                          source=src, extra=extra)
            _loop_hist(st, "quality_snapshot", snap)
            if not allow_unverified:
                print("⚠ 本轮质量数取自手工 --p0/--p1/--p2（source=manual）："
                      "自报值未经 verify_deck 报告交叉核验，可信度低于 --verify-json。",
                      file=sys.stderr)
        st["current_round"] = nxt
        st["awaiting_user_confirm"] = False
        st["last_decision"] = args.decision
        _loop_hist(st, "continue", {"from": nxt - 1, "to": nxt, "decision": args.decision})
        _write_loop_state(w, "b", st)

        # 收敛判定：连续 N 轮 P0+P1 合计未下降 → 触发终止建议（不自动终止：
        # 终止需用户裁决，代码只给结论与证据）
        nthr = int(beff.get("no_progress_threshold", 2))
        streak = _loop_no_progress_streak(st.get("quality_history") or [])
        if streak >= nthr:
            hist = st.get("quality_history") or []
            detail = {"loop": "B", "round": rnd_end, "next_round": nxt,
                      "threshold": nthr, "streak": streak,
                      "p0p1_series": [h.get("p0p1") for h in hist],
                      "quality_history": hist,
                      "quality_sources": [h.get("source") for h in hist],
                      "suggested_termination": "连续 N 轮无质量进展"}
            _loop_hist(st, "no_progress", detail)
            _write_loop_state(w, "b", st)
            _trace(w, cfg, "no_progress", "team-lead", detail)
            msg = (f"连续 {streak} 轮无质量进展（阈值 no_progress_threshold={nthr}，"
                   f"取自 harness.yaml#loop_b.budgets）：P0+P1 序列 "
                   f"{detail['p0p1_series']} 未下降 → 触发终止建议"
                   f"「连续 N 轮无质量进展」。继续硬做不再减少缺陷，"
                   f"请改方向或请用户裁决（`loop terminate --reason 连续 N 轮无质量进展`）。")
            print(json.dumps({"current_round": nxt, "decision": args.decision,
                              "no_progress": True, "threshold": nthr, "streak": streak,
                              "p0p1_series": detail["p0p1_series"],
                              "quality_sources": detail["quality_sources"],
                              "suggested_termination": "连续 N 轮无质量进展",
                              "message": msg}, ensure_ascii=False, indent=2))
            print(f"⛔ {msg}", file=sys.stderr)
            return 1
        print(json.dumps({"current_round": nxt, "decision": args.decision,
                          "no_progress": False,
                          "quality_snapshot": snap,
                          "quality_source": (snap or {}).get("source"),
                          "no_progress_streak": streak,
                          "no_progress_threshold": nthr,
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
            # v3.18.0 D2：与 cmd_loop intake 走**同一个**判定函数 _intake_a_gaps()，
            #   理由里必须写明是"未确认"还是"缺失"——两者的处置动作不同：
            #   缺失 = 还没问；未确认 = 问过了但用户没拍板（须追认）。
            miss, unconf = _intake_a_gaps(intake)
            if miss:
                reasons.append(f"九项 A 类未齐（缺 {miss}）——不得用仓库默认值冒充")
            if unconf:
                reasons.append(
                    f"九项 A 类有 {len(unconf)} 项**未确认**（{unconf}）："
                    f"登记了但 status 不是 confirmed——存在 suggested 即不得进入制作，"
                    f"须先在轮报中请用户追认")
            if not miss and not unconf:
                # A 类五项其实都齐且都 confirmed，但 confirmed 标记为 false——
                #   说明标记与实际不一致（可能被人手改过），必须显式暴露而不是放行。
                reasons.append("intake.confirmed 标记为 false，但 A 类五项实际齐备且均已确认——"
                               "标记与内容不一致，请重跑 `loop intake` 同步后再进制作")
        if c["pending"]:
            reasons.append(f"仍有 {len(c['pending'])} 条未冻结：{c['pending'][:10]}")
        if c["invalidated"]:
            reasons.append(f"{len(c['invalidated'])} 条批准已失效（sha256 漂移），须重审")
        if st.get("blockers"):
            reasons.append(f"存在 {len(st['blockers'])} 条未清阻塞")
        src = st.get("source_ppt", {})
        if os.path.isfile(src.get("path", "")) and _sha256_file(src["path"]) != src.get("sha256"):
            reasons.append("原件已被改动（只读纪律被破坏）")
        # ── v3.17.0 B2-2：quality_history 来源合规性（让 manual 来源**可被下游发现**）──
        # 此前 quality_history[].source 只被 `loop status` 打印，**无任何下游消费者**
        # 读它做门禁 → 手工填的数能一路走到制作门而不被发现。现 make-gate 是消费者：
        #   · 已进位（current_round > 1）却没有质量快照 → 无收敛数据，不得放行；
        #   · 存在非 verify_json 来源的快照 → 未经机器复算，不得据此宣布达标。
        # ⚠ "已进位却无快照"只在**真的走过轮次**时判定：从未 continue 过的 Loop
        #   （current_round == 1）本就无快照，不是质量问题，不阻断。
        rounds_done = int(st.get("current_round", 1)) - 1
        qhist = st.get("quality_history") or []
        if rounds_done > 0:
            if not qhist:
                reasons.append(f"已进位 {rounds_done} 轮但 quality_history 为空——"
                               f"收敛判据无数据，须用 --verify-json 报告补记质量快照")
            else:
                bad_src = [(h.get("round"), h.get("source")) for h in qhist
                           if not str(h.get("source") or "").startswith("verify_json|")]
                if bad_src:
                    reasons.append(f"quality_history 含 {len(bad_src)} 条**非机器复算来源**"
                                   f"的质量快照（须为 verify_json|...）：{bad_src[:5]}")
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
        # v3.17.0：终止原因读 harness.yaml#loop_b.termination（唯一源），
        # 不再用代码里另立的常量——否则在 yaml 加原因不生效（同型双声明缺陷）
        reasons = load_term_reasons(cfg)
        if args.reason not in reasons:
            print(f"用法错误：--reason 必须是已登记终止原因之一 {reasons}"
                  f"（源：harness.yaml#loop_b.termination）", file=sys.stderr)
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
def _read_json_readonly(path):
    """只读读 JSON；文件不存在或解析失败返回 None（**不创建、不修改任何文件**）。

    为什么不用 `read_state` / `_read_loop_state`：那两个都会经 `os.makedirs` 顺带
    建出 `.workbuddy/` 目录，且 `read_state` 在解析失败时会打印告警并按空状态处理。
    doctor 是**纯只读**的探针（iron-rules.md:73 定为"冷启动/任何新会话首查"），
    它跑一次不该在工作空间里留下任何痕迹，故自己走一条纯读路径。
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ {os.path.basename(path)} 解析失败（{e}），按无此状态处理", file=sys.stderr)
        return None


def _pending_work(w):
    """扫工作空间里的**未完成任务**，产出冷启动可执行的恢复指引。

    背景（D3 实测缺陷）：`cmd_doctor` 此前**完全不读** `loopB_state.json` /
    `task_state.json`——会话中断后"是否恢复、从哪恢复"完全靠主理人（LLM）的记忆，
    而 references/iron-rules.md:73 把 doctor 定为「冷启动/任何新会话首查」。
    记忆不可靠 ⇒ 会话一断，"第 2 轮还有 3 条待冻结"这种事实就查不到了。

    判定口径：
      · loopB_state.json 存在且 `termination` 为空 → 未结束 → 报 kind="loopB"
        （termination 非空 = 已终止，属历史，无需恢复）
      · task_state.json 存在且 `current_stage` 不为 0 → 未完成 → 报 kind="task"
        （current_stage == 0 = 任务刚初始化、尚未开工，无需恢复）

    返回值：
      · 无任何未完成项 → `None`（doctor 输出里为 null，**不输出空壳**）
      · 有一项 → 该项字典（顶层带 `kind`，字段即 spec 要求的那几个）
      · 有多项 → 以**优先级最高**的那项为主（顶层 `kind` + 该项字段），
        其余放进 `also_pending` 列表（不丢信息）。

    优先级：loopB > task。理由：loopB 处在"逐轮冻结/制作门"链条上，
    恢复它需要逐条追认（动作更重、更不可逆），先报它更安全。
    """
    entries = []

    # ── Loop B：未终止即未完成 ────────────────────────────────
    lb = _read_json_readonly(os.path.join(w, ".workbuddy", "loopB_state.json"))
    if isinstance(lb, dict) and not lb.get("termination"):
        c = _loop_counts(lb)
        hist = lb.get("history") or []
        last_ts = hist[-1].get("ts") if hist and isinstance(hist[-1], dict) else None
        entries.append({
            "kind": "loopB",
            "current_round": lb.get("current_round"),
            "pending_items": c["pending"],
            "frozen_items": c["frozen"],
            "last_action_ts": last_ts or lb.get("created_at"),
            # resume_hint 必须是**可直接执行**的命令串（不是散文描述）：
            # `loop resume` 只报不推进并置 awaiting_user_confirm=true（等用户确认）。
            "resume_hint": f"python3 scripts/harness.py loop resume --workspace {w}",
        })

    # ── task：current_stage != 0 即已开工未完成 ───────────────
    ts = _read_json_readonly(os.path.join(w, ".workbuddy", "task_state.json"))
    if isinstance(ts, dict) and ts.get("current_stage") not in (None, 0):
        entries.append({
            "kind": "task",
            "current_stage": ts.get("current_stage"),
            "next_action": ts.get("next_action", ""),
            # 冷启动恢复入口 = 读状态最小集（references/sop-stages.md:207 的
            # "Read task_state.json 最小集"），next_action 指明读完之后该干什么。
            "resume_hint": f"python3 scripts/harness.py state get --workspace {w}",
        })

    if not entries:
        return None
    primary = entries[0]
    if len(entries) > 1:
        primary = dict(primary)
        primary["also_pending"] = entries[1:]
    return primary


def cmd_doctor(args):
    """v3.4.0 R1：LLM 友好"可发现性表"——一次返回所有子命令的 usage/examples/exit_codes。
    根因（2026-10-14 实测 6 步 3 步参数错位）：argparse 仅在运行时暴露错误，
    AI 冷启动/新会话无 README 可查，本子命令填补"可发现性"缺口。

    v3.18.0 D3：新增顶层 `pending_work` 段——冷启动**自动发现**未完成任务
      （扫 loopB_state.json / task_state.json，见 `_pending_work`）。
      无未完成项时该段为 null（不输出空壳）。本命令**只读**，不写任何状态文件。
    """
    table = [
        # (子命令, 一句话用途, 必填参数, 常用可选, 退出码, 示例)
        ("doctor",     "可发现性表（你正在看）",                     "无",      "无",          "0", "harness.py doctor"),
        ("preflight",  "开工前成员可用性预检",                        "--team",  "--workspace", "0/1", "harness.py preflight --team vet-med-ppt-team"),
        ("route",      "复杂度 L0-L3 → spawn 计划",                  "--level", "--workspace", "0/1", "harness.py route --level L2"),
        ("state",      "任务状态机读写（init/get/set/validate/compact）", "action",  "--stage/--key/--value", "0/1/2", "harness.py state set --stage 1 --key deliverable --value <path>"),
        ("budget",     "预算计数（spawn/react/rework）",             "action",  "--kind/--n",  "0/1/2", "harness.py budget check --kind spawn"),
        ("trace",      "执行日志 JSONL（log/report）",                "action",  "--event/--actor/--detail", "0/2", "harness.py trace report"),
        ("spawn",      "v3.4.0：显式记录某成员 spawn（带 token 估算）",  "--agent", "--task-id/--input-bytes/--output-bytes", "0/1/2", "harness.py spawn --agent dvm-content-expert --task-id t1 --input-bytes 1200 --output-bytes 800"),
        ("member-return", "v3.17.0 B3-2：登记成员回传（写 trace member_return）", "--agent", "--task-id/--stage/--status/--artifact", "0", "harness.py member-return --agent dvm-content-expert --task-id t1 --stage 2 --status success --artifact out/blueprint.md"),
        ("spawn-failed", "v3.17.0 B3-2：登记 spawn 失败（写 trace spawn_failed）", "--agent", "--task-id/--attempt/--reason", "0", "harness.py spawn-failed --agent pedagogy-architect --task-id t1 --attempt 1 --reason '平台返回 not available'"),
        ("degrade",    "v3.17.0 B3-2：登记成员降级（写 trace degrade）", "--agent", "--task-id/--channel/--reason", "0", "harness.py degrade --agent pedagogy-architect --task-id t1 --channel general-purpose+persona --reason 'spawn 2 次均 not available'"),
        ("stage",      "v3.4.1：显式发 stage_enter/exit（填 stage_seconds）", "--action/--stage", "--task-id/--note", "0/2", "harness.py stage --action enter --stage 1"),
        ("gate",       "包装 verify_deck（lint+snap+gate 一体）",     "--deck",  "--hours/--level/--baseline/--tag", "0/1/2/3/4", "harness.py gate --deck x.pptx --hours 1"),
        ("verify-artifact", "核验成员自报落盘（反自评失真硬校验）",    "--path",  "--expect-bytes/--min-bytes", "0/1", "harness.py verify-artifact --path x.md --expect-bytes 1200"),
        ("verify-ref",     "v3.4.2 P0-3：cases_library 文献引用预检（假 PMID/格式错/缺时间戳）", "--path", "--online/--write-back", "0/1/2", "harness.py verify-ref --path cases_library.json --online --write-back"),
        ("sweep",         "v3.4.2 P0-1：递归扫全量 pptx → 收编 deck_registry（v3.1.0 失落的闸外能力）", "--root", "--hours/--level/--max-decks", "0/1/3/4", "harness.py sweep --root <工作区>"),
        ("eval",          "v3.4.2 P3-3：自动化演进环（基线 vs 当前 sweep diff）", "--root", "--reset-baseline", "0/1/2", "harness.py eval --root <工作区> --reset-baseline"),
        ("verify-envelope", "校验 result_envelope JSON 六字段",       "--path",  "无",          "0/1", "harness.py verify-envelope --path <成员产出.md>"),
        ("template-audit",  "模板指纹盘点 + 登记册审计",              "--root",  "--json/--require-registered", "0/1", "harness.py template-audit --root /Users/.../课程目录"),
        ("loop",  "v3.9.0：双层 Loop 状态机（启动/登记/恢复/进位/返修/冻结/核验/制作门/终止/越界）", "action", "--loop/--deck/--items/--decision/--reason/--verify-json/--p0/--p1/--p2/--allow-unverified", "0/1/2/3", "harness.py loop continue --decision accept --confirmed --verify-json <verify_deck报告.json>（报告优先于手工 --p0/--p1/--p2；v3.17.0：报告须对应本轮课件）"),
        ("domain", "v3.17.0：内容域档案菜单与详情（**给 LLM 看的选域菜单**，脚本不自动匹配）", "action", "--id", "0/2/3", "harness.py domain list"),
        ("collapse", "v3.17.0：坍缩产物查询与确认（**确认前域人格不生效**）", "action", "--id/--task-id/--rationale/--actor", "0/1/2/3", "harness.py collapse confirm --id computing --task-id T-1 --rationale \"用户主题为 Python 入门\"（须先 route --domain 落盘待确认产物）"),
    ]
    out = {"version": "v3.19.1", "executable": __file__,
           "global_options": ["--workspace <工作空间>（可写在子命令前/后）"],
           # v3.18.0 D3：冷启动自动发现未完成任务；无未完成项时为 null（不输出空壳）。
           "pending_work": _pending_work(wkspace(args)),
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

    v3.17.0 B3-2：补写 yaml 声明的 `spawn` 事件。
      此前本命令只写 `agent_spawn`——而 harness.yaml#observability.trace_events 声明的
      12 个事件里**没有** agent_spawn、有的却是 `spawn` ⇒ 声明层与执行层错位
      （同一型病：声明了却没产出点 / 产出了却没声明）。
      处置：写两条——
        · `spawn`      = **yaml 声明的事件名**，detail 含成员 id / 任务 id / 阶段
                         （新增断言据此判定"声明的事件真有产出"）；
        · `agent_spawn` = 保留给既有文档与既有 trace（references/iron-rules.md#B3、
                         agents/…-team-lead.md 的闸动作序列都点名它），**不删**
                         ——删事件名会让既有文档立刻变成假引用。
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
    rec = _trace(w, cfg, "spawn", args.agent, detail)
    _trace(w, cfg, "agent_spawn", args.agent, detail)      # 兼容既有文档/既有 trace
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
    ap = argparse.ArgumentParser(description="vet-med-ppt-team 编排内核（确定性工程层）v3.19.1")
    ap.add_argument("--workspace", help="工作空间路径（默认 cwd）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _ws(sp):  # 允许 --workspace 写在子命令之前或之后
        sp.add_argument("--workspace", default=argparse.SUPPRESS, help="同主命令的 --workspace")

    p = sub.add_parser("doctor", help="v3.4.0：可发现性表——所有子命令的 usage/examples/exit_codes")
    _ws(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("preflight", help="开工前成员可用性与静默降级预检")
    p.add_argument("--team", default="", help="团队名（读 ~/.workbuddy/teams/<team>/config.json）")
    p.add_argument("--task-id", dest="task_id", default="",
                   help="任务 id（写入 preflight / degrade 事件，便于事后对账）")
    # v3.19.0：外部通道探针（维度 10/11/13）——此前 preflight 只查成员，不查通道
    p.add_argument("--probe-channels", dest="probe_channels", action="store_true",
                   help="同时探测外部 skill/MCP 通道（Ima 库 / PubMed / fetch / 机构端点），"
                        "结果落 task_state.json#tool_probe_results，并输出**主动更换提醒**")
    p.add_argument("--domain", default="",
                   help="配合 --probe-channels：当前任务域 id（用于知识库归属核对）")
    _ws(p)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("route", help="复杂度 → spawn 计划")
    p.add_argument("--level", required=True, choices=["L0", "L1", "L2", "L3"])
    # v3.17.0：域坍缩——追加域字段并落盘坍缩产物（未确认不生效）
    p.add_argument("--domain", default="",
                   help="内容域 id（见 `domain list` 菜单）；不传则**输出与改造前逐字节一致**。"
                        "域由主理人显式指定，脚本不做关键词自动匹配")
    p.add_argument("--task-id", dest="task_id", default="",
                   help="任务 ID（坍缩产物落盘用；不传则读 task_state.json 的 task_id）")
    p.add_argument("--rationale", default="",
                   help="选型理由（**主理人填**，脚本不猜）；不填则坍缩产物标记为待补")
    # v3.18.0：专家面板选人——逗号分隔的 expert_panel id
    p.add_argument("--panel", default="",
                   help="坍缩选中的子专家 id（逗号分隔，取自该域 expert_panel）。"
                        "**主理人显式指定**——脚本不按关键词自动选人")
    _ws(p)
    p.set_defaults(func=cmd_route)

    # v3.17.0：域档案菜单（给主理人/LLM 看的选域入口；脚本不自动匹配）
    p = sub.add_parser("domain", help="v3.17.0：内容域档案菜单与详情（list / show）")
    p.add_argument("action", choices=["list", "show"])
    p.add_argument("--id", default="", help="show：域 id（kebab-case）")
    _ws(p)
    p.set_defaults(func=cmd_domain)

    # v3.17.0：坍缩产物查询与用户确认（确认前域人格不生效）
    p = sub.add_parser("collapse", help="v3.17.0：坍缩产物查询与确认（list / show / confirm）")
    p.add_argument("action", choices=["list", "show", "confirm"])
    p.add_argument("--id", default="", help="域 id")
    p.add_argument("--task-id", dest="task_id", default="", help="任务 ID")
    p.add_argument("--rationale", default="",
                   help="confirm：选型理由（主理人填；为空则拒绝确认）")
    # v3.18.0：--decision 改为**必填语义**（缺失即 exit 2，沉默不构成确认）
    p.add_argument("--decision", default="",
                   help="confirm：**用户裁决语义**（必填；缺失即拒绝确认）。"
                        "例：\"用户已阅并确认该专家团配置\"")
    # v3.18.0：--actor 默认值由 "team-lead" 改为空 —— 执行方自己不算「用户确认」；
    #   留空时按「未指定确认人」拒绝（须显式传 user 或真实裁决人标识）
    p.add_argument("--actor", default="",
                   help="confirm：确认人标识（**不得**填 team-lead——执行方自己不构成用户确认；"
                        "例：user / 用户本人标识）")
    _ws(p)
    p.set_defaults(func=cmd_collapse)

    # v3.18.0：闸1 冻结清单的机器校验（gate1_freeze 六项）
    p = sub.add_parser("gate1-check", help="闸1 冻结清单就绪度校验（六项；未就绪 exit 1 阻断）")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    _ws(p)
    p.set_defaults(func=cmd_gate1_check)

    p = sub.add_parser("state", help="状态机读写与校验")
    # v3.18.0 G6：新增 compact——`state validate` 报「必须 compaction」时，
    #   给的是一条**可执行命令**而不是一句没有下文的报错。
    p.add_argument("action", choices=["init", "get", "set", "validate", "compact"])
    p.add_argument("--workflow", default="WF-1")
    p.add_argument("--stage", type=int)
    # v3.17.0：task_id 原子比对的显式入口——带上它才能验证"本次操作属于这个任务"
    p.add_argument("--task-id", dest="task_id", default="",
                   help="state init/set：本任务 ID（init 时用于指定；set 时用于比对——"
                        "与状态文件里的 task_id 不一致即拒绝推进）")
    p.add_argument("--key"); p.add_argument("--detail")
    # v3.17.0：--value 只接受合法 JSON（旧的"解析失败就存字符串"会让
    # quality_history 之类结构化键变字符串 → 下游按 dict 过滤 → 判据静默失效）
    p.add_argument("--value",
                   help="set：值必须是**合法 JSON**；字符串须显式加引号，"
                        "例如 --value '\"gate2_spawn\"'（不带引号会被拒绝并报错，"
                        "不再静默存成字符串）")
    _ws(p)
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("budget", help="任务级预算计数")
    # v3.12.0：新增 list 动作（列出全部预算及其执行者）；--kind 不再硬编码 choices，
    # 否则 argparse 会在 cmd_budget 之前就拒掉新增的阈值型 kind。
    p.add_argument("action", choices=["check", "spend", "reset", "list"])
    p.add_argument("--kind", default="",
                   help="计数型 spawn|react|rework；阈值型 attempts|react_gap|"
                        "stage_minutes|artifact_bytes|three_source_sample|three_source_pass"
                        "（v3.17.0：three_source_* 改读 config/domain_config.yaml#three_source_check）")
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

    # ── v3.17.0 B3-2：补齐 yaml 声明却无产出点的 trace 事件入口 ────────
    # 立项理由：config/harness.yaml#observability.trace_events 声明 12 个事件，
    #   实测 7 个零产出（含 degrade / member_return / spawn_failed / error）——
    #   其中 degrade 是 fallback.require_disclosure 的唯一执行者，缺它 =
    #   "降级是否发生、是否声明"在 trace 里查不到（v2.2.0 建 harness 的原始理由被自己重犯）。
    p = sub.add_parser("member-return",
                       help="v3.17.0 B3-2：登记成员回传（写 trace 事件 member_return）")
    p.add_argument("--agent", required=True, help="回传成员 id")
    p.add_argument("--task-id", dest="task_id", default="", help="任务 id")
    p.add_argument("--stage", type=int, default=None, help="阶段号（0-4）")
    p.add_argument("--status", default="", help="回传状态（success/partial/failed/blocked）")
    p.add_argument("--artifact", default="", help="产物落盘路径")
    p.add_argument("--phase", default="", help="阶段标识")
    p.add_argument("--issues", default="", help="阻塞/缺口摘要")
    p.add_argument("--warnings", default="", help="警告摘要")
    _ws(p)
    p.set_defaults(func=cmd_member_return)

    p = sub.add_parser("spawn-failed",
                       help="v3.17.0 B3-2：登记 spawn 失败（写 trace 事件 spawn_failed）")
    p.add_argument("--agent", required=True, help="成员 id")
    p.add_argument("--task-id", dest="task_id", default="", help="任务 id")
    p.add_argument("--stage", type=int, default=None, help="阶段号（0-4）")
    p.add_argument("--attempt", type=int, default=1, help="第几次尝试（对照 fallback.max_spawn_attempts）")
    p.add_argument("--reason", default="", help="失败原因（必填语义：不可用/平台回落/超时…）")
    _ws(p)
    p.set_defaults(func=cmd_spawn_failed)

    p = sub.add_parser("degrade",
                       help="v3.17.0 B3-2：登记成员降级（写 trace 事件 degrade——"
                            "fallback.require_disclosure 的执行者）")
    p.add_argument("--agent", required=True, help="被降级的成员 id")
    p.add_argument("--task-id", dest="task_id", default="", help="任务 id")
    p.add_argument("--stage", type=int, default=None, help="阶段号（0-4）")
    p.add_argument("--channel", default="",
                   help="降级通道（general-purpose+persona / script_pipeline，"
                        "取自 harness.yaml#fallback.degrade_modes）")
    p.add_argument("--reason", default="", help="降级原因（必填语义）")
    _ws(p)
    p.set_defaults(func=cmd_degrade)

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
    p.add_argument("--replace", action="store_true",
                   help="intake：本次文件即**完整快照**（未出现的键视为未登记）。"
                        "默认是增量合并（向后兼容递进式登记）")
    p.add_argument("--items", help="freeze：条目 ID 列表，形如 I-001,I-002 或 I-001=a.md,I-002=b.md")
    p.add_argument("--item", help="rework：条目 ID")
    p.add_argument("--page", help="add-item：稳定页面 ID（如 s12）")
    p.add_argument("--severity", default="", help="add-item：P0/P1/P2")
    p.add_argument("--owner", default="", help="add-item：dvm/pedagogy/visual")
    p.add_argument("--decision", choices=["accept", "partial_accept", "rework", "pause"],
                   help="continue/freeze：用户裁决（不传即拒绝进位——沉默不构成确认）")
    p.add_argument("--confirmed", action="store_true", help="continue/terminate：已获用户确认")
    p.add_argument("--reason", help="terminate：已登记终止原因之一（harness.yaml#loop_b.termination）")
    # v3.17.0 F6：continue 带本轮 P0/P1/P2 计数 → 落 quality_history，
    # 供 loop_b.budgets.no_progress_threshold 的"连续 N 轮无质量进展"判据消费
    p.add_argument("--p0", type=int, default=None, help="continue：本轮结束时的 P0 缺陷数")
    p.add_argument("--p1", type=int, default=None, help="continue：本轮结束时的 P1 缺陷数")
    p.add_argument("--p2", type=int, default=None, help="continue：本轮结束时的 P2 缺陷数")
    p.add_argument("--verify-json", dest="verify_json", default="",
                   help="continue：verify_deck.py --json 产出的报告路径（**优先于** --p0/--p1/--p2："
                        "机器复算 > 手工自报；缺字段/不可解析/对应别的课件即报错，不静默取 0）")
    # v3.17.0 B2-2：手工填数的显式逃生口——留痕（blocker 事件 + trace + 快照 source），
    #   不得成为默认；用了它 make-gate 会阻断。
    p.add_argument("--allow-unverified", dest="allow_unverified", action="store_true",
                   help="continue：**逃生口**——允许在已有手工自报历史后继续用手工 "
                        "--p0/--p1/--p2（会登记 blocker 事件、快照标 source=manual_unverified，"
                        "make-gate 阻断；默认不允许）")
    p.add_argument("--kind", default="", help="block：阻塞类型（capability/evidence/...）")
    p.add_argument("--note", default="", help="人读备注")
    p.add_argument("--path", help="check-path：待写入的目标路径（越界校验）")
    p.add_argument("--force", action="store_true", help="start/add-item：允许覆盖既有记录")
    _ws(p)
    p.set_defaults(func=cmd_loop)

    a = ap.parse_args()
    sys.exit(run_command(a))


def run_command(a):
    """执行子命令并统一处理运行期异常 → 写 trace 事件 error。

    v3.17.0 B3-2 新增（**error 事件**是 yaml 声明的 12 个事件里最后一个零产出的）。
      此前 harness 抛异常 = 栈打到 stderr 就没了，trace 里查不到"哪一步炸了"
      ⇒ 编排现场无法复盘。现在统一在此捕获：写一条 error 事件（带子命令名、
      argv、异常类型与消息），再按既有语义返回退出码 4（运行错误——非课件质量，
      不得当作红灯打回成员，见 harness.yaml#gate_exit_codes）。

    抽成独立函数（而不是内联在 main 里）的原因：**可测**——
    异常路径若只在 __main__ 里，就没有任何测试能覆盖它（这正是本包反复吃亏的
    "不可达路径"型缺陷）。
    """
    try:
        return a.func(a)
    except SystemExit:
        raise
    except BaseException as e:
        try:
            cfg, _ = load_cfg()
            w = wkspace(a)
            fn = getattr(a, "func", None)
            _trace_error(w, cfg, "error", "harness",
                         {"command": getattr(fn, "__name__", "?") if fn else "?",
                          "argv": sys.argv[1:], "exception": type(e).__name__,
                          "message": str(e)[:500]})
        except Exception:
            pass    # trace 写失败不得掩盖原始异常
        import traceback as _tb
        print(f"⛔ harness 运行异常：{type(e).__name__}: {e}", file=sys.stderr)
        _tb.print_exc()
        return 4


if __name__ == "__main__":
    main()

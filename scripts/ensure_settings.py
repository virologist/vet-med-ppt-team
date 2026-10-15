#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensure_settings.py — vet-med-ppt-team 专家包 体检 + 自愈器（doctor）

背景（2026-09-17 → 2026-10-04 实证）：
  ① 本专家包的 settings.json 已丢失 5 次。规律：每次修改专家包内文件后，WorkBuddy
     热重载会吞掉 settings.json。故保留自愈。
  ② .claude-plugin/plugin.json 版本曾长期落后 .codebuddy-plugin/plugin.json，
     而 validate_expert.py 只校验后者 —— 单靠官方校验发现不了。
  ③ **2026-10-04 新增两项致命体检**（第二轮诊断 B1/B2）：
     - 安装目录被整仓克隆后，根级 scripts/ 只剩 1 个文件，6 个核心脚本缺失
       （verify_deck/harness/surgery_deck/inject_notes/ensure_settings/test_harness）
       → 分级门禁在真实使用路径上根本跑不起来。
     - 根级包与 packages/vet-med-ppt-team/ 双份并存且已内容漂移。
     - 同名 verify_deck.py 在包内出现多份 → "唯一裁判"失效，结论不可比。

因此本脚本从 4 项扩到 7 项（v3.1.0），v3.2.0-batch2 再 +3 项治理自检 = 10 项：
  1 settings.json 存在且 agent 名与清单一致        → 缺失/损坏则重建【自愈】
  2 两侧清单版本号一致                            → 漂移则告警【只读】
  3 清单声明的 agent 文件全部存在                 → 缺失则告警【只读】
  4 权威门禁 verify_deck.py 存在                 → 缺失则告警【只读】
  5 全脚本完整性（9 个脚本，v3.2.0 +extract_assets/ooxml_lint/snapshot）  → 缺失则告警【只读】★扩
  6 双份与多裁判检测（同名 verify_deck.py 计数） → 告警【只读】★新
  7 回归测试自跑（test_harness.py）              → 失败则告警【只读】★新
  ★ v3.2.0-batch2 新增 3 项治理自检：
  8 活跃目录文件数超限（D12 备份膨胀）            → 告警【只读】
  9 scratch 超期（D12 备份膨胀）                  → 告警【只读】
  10 快照库超容（D12 备份膨胀）                   → 告警【只读】

用法：
    python3 scripts/ensure_settings.py [专家包路径]     # 0=全通过  1=有告警
    python3 scripts/ensure_settings.py <路径> --quick    # 跳过第 7 项（耗时项）
    python3 scripts/ensure_settings.py <路径> --no-governance  # 跳过 8/9/10（治理项）

默认路径：~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
退出码：0 = 全部通过（可发布）  1 = 存在需人工处理的告警
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team"
)

# 两侧清单：WorkBuddy 读 codebuddy，Claude Code 读 claude
MANIFESTS = [
    (".codebuddy-plugin", "WorkBuddy"),
    (".claude-plugin", "ClaudeCode"),
]

# 权威门禁：唯一裁判（SSOT）。同名多份 = 裁判失效，见检查 6。
JUDGE = "verify_deck.py"

# 全脚本清单（检查 5）。v3.2.0-batch4 新增 2 个：case_extract / test_case_extract
REQUIRED_SCRIPTS = [
    "verify_deck.py",            # 权威门禁（分级 + 退出码语义 + traceback + v3.3.0 三源核验）
    "harness.py",                # 编排内核（preflight/route/state/budget/trace/gate/verify-artifact/verify-envelope/template-audit）
    "surgery_deck.py",           # 批量版面外科
    "inject_notes.py",           # 讲稿注入
    "ensure_settings.py",        # 本体检器（自指）
    "test_harness.py",           # 回归测试
    "assemble_spawn_prompt.py",  # 人设装配器
    # v3.2.0-batch2 新增
    "extract_assets.py",         # 资产化转换（Batch 1）
    "ooxml_lint.py",             # OOXML 兼容性检查（Batch 2）
    "snapshot.py",               # 快照库（Batch 2）
    # v3.2.0-batch3 新增
    "theme_fingerprint.py",      # 主题指纹 + 批量盘点（Batch 3）
    "template_migrate.py",       # 三档模板迁移 + 登记册（Batch 3）
    # v3.2.0-batch4 新增
    "case_extract.py",           # 病例库登记册（Batch 4）
    "test_case_extract.py",      # 病例库回归测试（Batch 4）
    # v3.2.0-batch5 新增
    "test_five_gates.py",        # 5 闸扩展回归测试（Batch 5）
]

N = 13  # 检查项总数（v3.2.0-batch2：7→10；v3.3.1 治理批：10→11；v3.4.2 P2-4：12；v3.4.3 B3：13 联邦巡检）


# ── 8. 活跃目录文件数超限（D12）─────────────────────────────
def check_active_dir_files(expert_dir):
    """扫描课程工作区活跃课件目录，文件数超 20 报警。
    排除项：4 类常驻（.pptx / .original_YYYYMMDD.pptx / _diagnosis/ / _assets/） + .snapshots/ + .scratch/
    """
    # 简单实现：找工作区（heuristic：用户工作区可能不在 expert_dir 路径下；
    # 实际可由环境变量或主理人指定，本批仅做 best-effort 提示）
    ws = os.environ.get("VET_WS") or os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
    if not os.path.exists(ws):
        print(f"[8/{N}] – 未找到工作区（VET_WS 或默认路径）")
        return 0
    over_limit = []
    for d in os.listdir(ws):
        full = os.path.join(ws, d)
        if not os.path.isdir(full):
            continue
        if d.startswith("."):
            continue
        # 数文件（不含子目录）
        files = [f for f in os.listdir(full) if os.path.isfile(os.path.join(full, f))]
        # 排除 _assets/ _diagnosis/ 等常驻
        kept = [f for f in files if not f.endswith("_assets") and "_diagnosis" not in f]
        if len(kept) > 20:
            over_limit.append((d, len(kept)))
    if over_limit:
        print(f"[8/{N}] ⚠ 活跃目录文件数超限（D12 备份膨胀）: {len(over_limit)} 个目录")
        for d, n in over_limit[:5]:
            print(f"     {d}: {n} 个文件")
        if len(over_limit) > 5:
            print(f"     ... 还有 {len(over_limit) - 5} 个")
        print(f"     → 启用 snapshot.py gc 与 scratch 清理")
        return 1
    print(f"[8/{N}] ✓ 活跃目录文件数正常（无 >20 文件目录）")
    return 0


# ── 9. scratch 超期（D12）────────────────────────────────────
def check_scratch_expiry(expert_dir):
    """<workspace>/.scratch/<task_id>/ mtime > 7 天报警。"""
    ws = os.environ.get("VET_WS") or os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
    scratch_root = os.path.join(ws, ".scratch")
    if not os.path.exists(scratch_root):
        print(f"[9/{N}] ✓ scratch 目录不存在（无累积）")
        return 0
    over = []
    now = time.time()
    for d in os.listdir(scratch_root):
        full = os.path.join(scratch_root, d)
        if not os.path.isdir(full):
            continue
        mtime = os.path.getmtime(full)
        age_days = (now - mtime) / 86400
        if age_days > 7:
            over.append((d, round(age_days, 1)))
    if over:
        print(f"[9/{N}] ⚠ scratch 超期（>7 天）: {len(over)} 个 task")
        for d, age in over[:5]:
            print(f"     {d}: {age} 天前")
        if len(over) > 5:
            print(f"     ... 还有 {len(over) - 5} 个")
        print(f"     → 手动 `rm -rf {scratch_root}/<task_id>` 清理")
        return 1
    print(f"[9/{N}] ✓ scratch 无超期 task")
    return 0


# ── 10. 快照库超容（D12）────────────────────────────────────
def check_snapshot_size(expert_dir):
    """<workspace>/.snapshots/ 总大小 > 500MB 报警。"""
    ws = os.environ.get("VET_WS") or os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
    snap_root = os.path.join(ws, ".snapshots")
    if not os.path.exists(snap_root):
        print(f"[10/{N}] ✓ 快照库未初始化（无 .snapshots/）")
        return 0
    total = 0
    for dp, dn, fn in os.walk(snap_root):
        for f in fn:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    total_mb = total / (1024 * 1024)
    if total_mb > 500:
        print(f"[10/{N}] ⚠ 快照库超容（D12 备份膨胀）: {total_mb:.0f} MB > 500 MB")
        print(f"     → 跑 `python3 scripts/snapshot.py gc --workspace {ws}`")
        return 1
    print(f"[10/{N}] ✓ 快照库容量正常（{total_mb:.0f} MB）")
    return 0


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 1. settings.json（自愈）────────────────────────────────
def heal_settings(expert_dir, agent_name):
    target = os.path.join(expert_dir, "settings.json")
    want = {"agent": agent_name}
    if os.path.exists(target):
        try:
            with open(target, encoding="utf-8") as f:
                if json.load(f) == want:
                    print(f"[1/{N}] ✓ settings.json 已正确存在（agent={agent_name}）")
                    return 0
        except Exception:
            pass  # 内容损坏 → 重建
    with open(target, "w", encoding="utf-8") as f:
        json.dump(want, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[1/{N}] ✚ settings.json 已恢复（agent={agent_name}）—— 第 N 次丢失，宿主热重载所致")
    return 0


# ── 2. 两侧清单版本一致 ─────────────────────────────────────
def check_version_parity(expert_dir):
    seen = {}
    for sub, label in MANIFESTS:
        p = os.path.join(expert_dir, sub, "plugin.json")
        if not os.path.exists(p):
            print(f"[2/{N}] ⚠ {label} 清单缺失：{p}")
            return 1
        try:
            seen[label] = _load(p).get("version", "?")
        except Exception as e:
            print(f"[2/{N}] ⚠ {label} 清单解析失败：{e}")
            return 1
    vals = list(seen.values())
    desc = " / ".join(f"{k}={v}" for k, v in seen.items())
    if len(set(vals)) == 1:
        print(f"[2/{N}] ✓ 两侧清单版本一致（{desc}）")
        return 0
    print(f"[2/{N}] ⚠ 版本漂移：{desc} —— 需手动同步（validate_expert.py 查不出此项）")
    return 1


# ── 3. agent 文件齐全 ───────────────────────────────────────
def check_agents(expert_dir):
    p = os.path.join(expert_dir, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(p):
        print(f"[3/{N}] ⚠ 无法校验：主清单缺失")
        return 1
    try:
        plugin = _load(p)
    except Exception as e:
        print(f"[3/{N}] ⚠ 主清单解析失败：{e}")
        return 1
    agents = plugin.get("agents", [])
    missing = [a for a in agents if not os.path.exists(os.path.join(expert_dir, a))]
    if not missing:
        print(f"[3/{N}] ✓ {len(agents)} 个 agent 文件齐全")
        return 0
    for m in missing:
        print(f"[3/{N}] ⚠ 缺失 agent 文件：{m}")
    return 1


# ── 4. 权威门禁存在 ─────────────────────────────────────────
def check_judge(expert_dir):
    p = os.path.join(expert_dir, "scripts", JUDGE)
    if os.path.exists(p):
        print(f"[4/{N}] ✓ 权威门禁就位（scripts/{JUDGE}）")
        return 0
    print(f"[4/{N}] 🔴 缺失权威门禁 scripts/{JUDGE} —— 分级门禁不可执行，"
          f"所有 MD 里的门禁命令都会 FileNotFoundError")
    return 1


# ── 5. 全脚本完整性 ★新 ─────────────────────────────────────
def check_all_scripts(expert_dir):
    sdir = os.path.join(expert_dir, "scripts")
    missing = [s for s in REQUIRED_SCRIPTS if not os.path.exists(os.path.join(sdir, s))]
    if not missing:
        print(f"[5/{N}] ✓ 全脚本齐全（{len(REQUIRED_SCRIPTS)} 个）")
        return 0
    print(f"[5/{N}] 🔴 缺失 {len(missing)} 个脚本：{', '.join(missing)}")
    print(f"      —— 典型成因：安装目录被整仓克隆，根级 scripts/ 只保留了部分文件")
    print(f"      —— 修法：把 packages/vet-med-ppt-team/ 的内容同步到包根（rsync），"
          f"并检查 .gitignore 是否误伤")
    return 1


# ── 6. 双份与多裁判检测 ★新 ────────────────────────────────
def check_single_judge(expert_dir):
    """同名 verify_deck.py 出现多份 = 唯一裁判失效（2026-10-04 B0 致命问题）。
    统计范围：本包内（不含嵌套 packages/ 的对照，那会在下一项单独报）。"""
    found = []
    for root, dirs, files in os.walk(expert_dir):
        # 不进入 .git 与嵌套包（嵌套是"源"，单列一项报）
        dirs[:] = [d for d in dirs if d not in (".git", "packages")]
        if JUDGE in files:
            found.append(os.path.relpath(os.path.join(root, JUDGE), expert_dir))
    if len(found) == 1:
        print(f"[6/{N}] ✓ 唯一裁判（包根级仅 1 份 {JUDGE}）")
    else:
        print(f"[6/{N}] 🔴 包内出现 {len(found)} 份 {JUDGE}：{found}")
        print("      —— 多份门禁 = 结论不可比（B0）。请指定唯一权威源，其余删除或明确标注为非门禁工具。")
    return 0 if len(found) == 1 else 1


# ── 7. 回归测试自跑 ★新 ─────────────────────────────────────
def check_regression(expert_dir):
    t = os.path.join(expert_dir, "scripts", "test_harness.py")
    if not os.path.exists(t):
        print(f"[7/{N}] ⚠ 回归测试脚本缺失，跳过")
        return 1
    try:
        p = subprocess.run([sys.executable, t], capture_output=True, text=True,
                           timeout=180)
    except subprocess.TimeoutExpired:
        print(f"[7/{N}] ⚠ 回归测试超时（>180s），未能判定")
        return 1
    last = [l for l in (p.stdout or "").strip().splitlines() if l.strip()]
    tail = last[-1] if last else ""
    if p.returncode == 0:
        print(f"[7/{N}] ✓ 回归测试通过（{tail}）")
        return 0
    print(f"[7/{N}] 🔴 回归测试失败（{tail}）")
    return 1


# ── 11. 工作区旁路版本检查（v3.3.1 治理批）──────────────────
def check_bypass_versions(expert_dir):
    """扫课程工作区一级目录的旁路版本文件（写回纪律违纪信号）。
    模式：_v<数字> / 副本 / 优化版 / (1)(2) 序号括号，扩展名 .pptx/.ppt。
    依据：主理人 MD#写回纪律（v3.3.1）——AI 修改必须原地写回，禁旁路新文件。
    """
    import re
    ws = os.environ.get("VET_WS") or os.path.expanduser(
        "~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治"
    )
    if not os.path.exists(ws):
        print(f"[11/{N}] – 未找到工作区（VET_WS 或默认路径）")
        return 0
    pat = re.compile(r"(_v\d|副本|优化版|\(\d\))\.(pptx?|ppt)$")
    hits = []
    for d in os.listdir(ws):
        full = os.path.join(ws, d)
        if not os.path.isdir(full) or d.startswith((".", "_")):
            continue
        for f in os.listdir(full):
            if pat.search(f):
                hits.append(f"{d}/{f}")
    if hits:
        print(f"[11/{N}] ⚠ 旁路版本文件 {len(hits)} 个（写回纪律违纪，见主理人 MD#写回纪律）")
        for h in hits[:5]:
            print(f"     {h}")
        if len(hits) > 5:
            print(f"     ... 还有 {len(hits) - 5} 个")
        print(f"     → 处置：合并内容后原地写回，旁路文件移 _trash_<date>/")
        return 1
    print(f"[11/{N}] ✓ 工作区无旁路版本文件（写回纪律达标）")
    return 0


def check_doc_implementation_drift(expert_dir):
    """v3.4.2 P2-4：CHANGELOG 声称子命令 vs argparse 实际注册表交叉核验。

    背景（2026-10-15 五维诊断发现）：CHANGELOG v3.1.0 声称"harness.py sweep 已实现+16/16 测试通过"，
    git 全历史确认 harness.py 从未含 sweep 子命令。ensure_settings 此前 11 项体检无一项能发现——
    因为没有检查问"CHANGELOG 声称的能力是否存在"。

    方法：
      1. 扫 CHANGELOG.md，提取 `**`...**子命令**` 的提及（或更简单的：匹配 `harness.py <cmd>` 字样）；
      2. 对每个声称的子命令，运行 `harness.py --help` 或 `harness.py <cmd> --help`（用 exit 2/usage 判存在）；
      3. 声称但不可执行的 → exit 1 挂账。

    设计取舍：CHANGELOG 表述多样（"`harness.py sweep`（P0-1 闸外收编）"），正则匹配
    抓 `harness.py <command>` 形式（命令在 2-30 字符之间），覆盖最常见声明。
    """
    import re, subprocess, sys
    chlog = os.path.join(expert_dir, "CHANGELOG.md")
    hrns = os.path.join(expert_dir, "scripts", "harness.py")
    if not os.path.exists(chlog) or not os.path.exists(hrns):
        print(f"[12/{N}] – CHANGELOG/harness.py 不存在，跳过")
        return 0
    # 1) 扫 CHANGELOG 声称的子命令
    chlog_text = open(chlog, encoding="utf-8").read()
    # 匹配 `harness.py <command>` 形式（命令在 2-30 字符之间）
    # 排除：`harness.py --help` / `harness.py <cmd>` 子命令 / `harness.py 描述` 中的 cmd 等
    pat = re.compile(r"harness\.py\s+([a-z][a-z0-9-]{2,30})", re.I)
    claimed = sorted(set(pat.findall(chlog_text)))
    # 过滤：`cmd` 是 argparse 主命令的占位词，doctor/stage/trace 等都是子命令但个别不是
    # 已知子命令白名单（v3.4.2 共 14 个），只保留在此白名单里的——更稳的"声称必须是真子命令"
    SUB_WHITELIST = {"doctor", "preflight", "route", "state", "budget", "trace",
                     "spawn", "stage", "gate", "verify-artifact", "verify-envelope",
                     "verify-ref", "sweep", "template-audit", "eval"}
    claimed = [c for c in claimed if c in SUB_WHITELIST]
    if not claimed:
        print(f"[12/{N}] ✓ CHANGELOG 无 harness.py 子命令声称（无漂移风险）")
        return 0
    # 2) 跑 harness.py <cmd> --help 判存在
    # 改：--help 可能因 argparse 顺序报非 0/2；改用更稳的判据：argv 含未知子命令必 exit 2
    # 真存在：运行 <cmd> 时 exit 在 {0,1,2,3,4,5}（命令处理了），exit 2=用法错（命令存在但不接 --help）
    # 不存在：main argparse 直接报 invalid choice → exit 2 + "invalid choice: '<cmd>'" 在 stderr
    missing = []
    checked = 0
    for cmd in claimed:
        checked += 1
        try:
            r = subprocess.run([sys.executable, hrns, "--help"],
                               capture_output=True, text=True, timeout=10)
            # 从主 --help 输出提取已注册子命令
            out = (r.stdout or "") + (r.stderr or "")
            # 解析 argparse 实际注册表
            registered = set()
            for line in out.splitlines():
                m = re.search(r"\{[\"']?([a-z][a-z0-9-]*)[\"']?\s*[,}]", line)
                # argparse 子命令的 help 格式："{doctor,preflight,...}" 或 "{doctor, ...}"
                pass
            # 简单方法：再跑一次 harness 抽 doctor 的输出（doctor 列出所有子命令）
            r2 = subprocess.run([sys.executable, hrns, "doctor"],
                                capture_output=True, text=True, timeout=10)
            try:
                docd = json.loads(r2.stdout)
                reg_names = {c.get("name") for c in docd.get("commands", [])}
            except Exception:
                reg_names = set()
            if cmd not in reg_names:
                missing.append((cmd, f"doctor 列出 {len(reg_names)} 个子命令，无 {cmd}"))
        except Exception as e:
            missing.append((cmd, "exception", str(e)[:80]))
    if missing:
        print(f"[12/{N}] ❌ 文档-实现漂移：CHANGELOG 声称 {len(claimed)} 个子命令，其中 {len(missing)} 个未在 doctor 表中")
        for cmd, info in missing:
            print(f"     {cmd}  → {info[:100]}")
        print(f"     → 处置：①实现缺失子命令（最常见：只改 CHANGELOG 未落 harness.py）；②或从 CHANGELOG 删除声称（补勘误）")
        return 1
    print(f"[12/{N}] ✓ 文档-实现一致：CHANGELOG 声称 {len(claimed)} 个子命令，全部在 doctor 表中")
    return 0


def check_federation_sync(expert_dir):
    """v3.4.3 B3：联邦 shim 巡检——各包 shim 版本声明一致性 + vendor 副本哈希比对。

    背景（2026-10-15 五维诊断 2.1 实证）：v3.4.2 P0-1 升级了 smart-textbook-team 的
    shim（60 行 R9 → 102 行 P0-1，vendor 兜底），research-orchestration-team /
    triz-invention-team 停留 v3.4.1 R9 未跟升——此前 12 项体检无一项问
    "联邦各包的 shim 是否还在同一版本"（R2 联邦断层直到独立诊断才暴露）。

    方法：
      1. 扫联邦 plugins/ 下各包 scripts/assemble_spawn_prompt.py 头部 40 行，
         提取最新版本声明（"v3.4.2 P0-1" 为当前标准；"v3.4.1 R9" = 未跟升 ⚠）；
      2. 包内有 vendor/shared-core/ 副本时，比对 sha256 == 联邦真源（防漂移）；
      3. viral-evo-lab（独立定制版）与 shared-core 自身跳过。
    判据从"行数"改为"声明标准"：行数会随实现微调，声明字符串才是版本契约。
    """
    import hashlib
    plugins_root = os.path.dirname(os.path.abspath(expert_dir))
    core = os.path.join(plugins_root, "shared-core", "assemble_spawn_prompt.py")
    if not os.path.isdir(plugins_root) or not os.path.isfile(core):
        print(f"[13/{N}] – 联邦 plugins/shared-core 不存在（非安装态），跳过")
        return 0
    core_sha = hashlib.sha256(open(core, "rb").read()).hexdigest()
    STANDARD = "v3.4.2 P0-1"
    LAGACY = "v3.4.1 R9"
    skip = {"shared-core", "viral-evo-lab", expert_dir and os.path.basename(expert_dir)}
    rows, stale, drift = [], [], []
    for name in sorted(os.listdir(plugins_root)):
        pkg = os.path.join(plugins_root, name)
        shim = os.path.join(pkg, "scripts", "assemble_spawn_prompt.py")
        if not os.path.isdir(pkg) or name in skip or not os.path.isfile(shim):
            continue
        head = "".join(open(shim, encoding="utf-8", errors="replace").readlines()[:40])
        if STANDARD in head:
            ver = "P0-1 ✅"
        elif LAGACY in head:
            ver = "R9 ⚠ 未跟升"
            stale.append(name)
        else:
            ver = "无标准声明（独立版/待审）"
        # vendor 副本哈希比对（存在才查）
        vend = os.path.join(pkg, "vendor", "shared-core", "assemble_spawn_prompt.py")
        if os.path.isfile(vend):
            vsha = hashlib.sha256(open(vend, "rb").read()).hexdigest()
            if vsha != core_sha:
                ver += " | vendor漂移❌"
                drift.append(name)
        rows.append((name, ver))
    if stale or drift:
        print(f"[13/{N}] ⚠ 联邦同步有缺口：{len(stale)} 包 shim 未跟升 {STANDARD}、{len(drift)} 包 vendor 漂移")
        for n, v in rows:
            print(f"     {n:32s} {v}")
        print(f"     → 处置：未跟升包按 smart-textbook-team 先例升级（shim+vendor+test 三件套）；"
              f"vendor 漂移包 cp 联邦 core 后更新 VENDOR.json")
        return 1
    print(f"[13/{N}] ✓ 联邦同步一致：{len(rows)} 包 shim 均达 {STANDARD}，vendor 哈希无漂移")
    for n, v in rows:
        print(f"     {n:32s} {v}")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quick = "--quick" in sys.argv
    path = args[0] if args else DEFAULT
    if not os.path.isdir(path):
        print(f"✗ 专家包目录不存在：{path}", file=sys.stderr)
        return 1

    print(f"体检目标：{path}\n")
    mpath = os.path.join(path, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(mpath):
        print(f"✗ 找不到主清单：{mpath}", file=sys.stderr)
        return 1
    try:
        plugin = _load(mpath)
    except Exception as e:
        print(f"✗ 主清单解析失败：{e}", file=sys.stderr)
        return 1
    agent_name = plugin.get("agentName") or plugin.get("name")
    if not agent_name:
        print("✗ plugin.json 缺少 agentName", file=sys.stderr)
        return 1

    rc = 0
    rc |= heal_settings(path, agent_name)
    rc |= check_version_parity(path)
    rc |= check_agents(path)
    rc |= check_judge(path)
    rc |= check_all_scripts(path)
    rc |= check_single_judge(path)
    if not quick:
        rc |= check_regression(path)
    else:
        print(f"[7/{N}] – 已按 --quick 跳过回归测试")
    # v3.2.0-batch2：3 项治理自检（D12 备份膨胀）
    no_governance = "--no-governance" in sys.argv
    if not no_governance:
        rc |= check_active_dir_files(path)
        rc |= check_scratch_expiry(path)
        rc |= check_snapshot_size(path)
        rc |= check_bypass_versions(path)
    else:
        print(f"[8/{N}] – 已按 --no-governance 跳过")
    # v3.4.2 P2-4：文档-实现一致性（无论 quick/no-governance 均跑）
    rc |= check_doc_implementation_drift(path)
    # v3.4.3 B3：联邦 shim 巡检（无论 quick/no-governance 均跑）
    rc |= check_federation_sync(path)

    print()
    if rc == 0:
        print("结论：✅ 全部通过，可发布 / 可运行 validate_expert.py")
    else:
        print("结论：⚠️ 存在告警，处理后再发布（settings.json 已自愈）")
    return rc


if __name__ == "__main__":
    sys.exit(main())

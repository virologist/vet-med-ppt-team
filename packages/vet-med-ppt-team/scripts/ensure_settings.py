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
  5 全脚本完整性（清单内脚本数，v3.9.0 为 18 个）                        → 缺失则告警【只读】★扩
  6 双份与多裁判检测（同名 verify_deck.py 计数） → 告警【只读】★新
  7 回归测试自跑（scripts/ 下**全部** test_*.py）  → 失败则告警【只读】★新★扩(v3.9.0)
  ★ v3.2.0-batch2 新增 3 项治理自检：
  8 活跃目录备份膨胀（D12，只数备份/旁路模式文件 ≥3） → 告警【只读】
  9 scratch 超期（D12 备份膨胀）                  → 告警【只读】
  10 快照库超容（D12 备份膨胀）                   → 告警【只读】
  11 工作区旁路版本文件（写回纪律）               → 告警【只读】
  12 文档-实现一致性（CHANGELOG 子命令 vs doctor）→ 告警【只读】★新
  13 联邦 shim 同步（各包声明 + vendor 哈希）     → 告警【只读】★新
  14 版本号四处一致（codebuddy/claude/yaml/py）  → 不一致则告警【只读】★新
  15 agent frontmatter 闭合（双平台解析兼容）   → 未闭合则告警【只读】★新
  16 受众分层单一数据源（v3.11.0）             → 层数/深度档/时间结构/唯一默认/旧层名残留【只读】★新
  17 悬空脚本引用（v3.12.0）                       → MD 引用了 scripts/ 里没有的 .py【只读】★new
  18 死配置巡检（v3.12.0）                            → config/ 里的键在 scripts/ 中无读取者【提示·不阻断】
  19 回退阈值漂移巡检（v3.14.0）                      → _FALLBACK 与 visual-rules.yaml 不一致【只读】★新
  20 跨成员交接落盘契约巡检（v3.14.0）                → 交接指令未给载体（issues/落盘/中转/禁直连）【只读】★新

用法：
    python3 scripts/ensure_settings.py [专家包路径]     # 0=全通过  1=有告警
    python3 scripts/ensure_settings.py <路径> --quick    # 跳过第 7 项（耗时项）
    python3 scripts/ensure_settings.py <路径> --no-governance  # 跳过 8/9/10（治理项）

默认路径：~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
退出码：0 = 全部通过（可发布）  1 = 存在需人工处理的告警
"""

import json
import os
import re
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
    # v3.8.2 新增（补 round-review-sop §2.1 悬空的"图片引用修复"能力）
    "fix_md_image_refs.py",      # Markdown 图片引用修复（markitdown 悬空链接 → _assets 实际路径）
    "test_fix_md_image_refs.py", # 引用修复回归测试（7 例）
    # v3.9.0 新增（双层 Loop 契约下沉为代码）
    "test_loop_state.py",        # 双层 Loop 状态机回归测试（33 例：停等/部分冻结/sha256 失效/预算触顶/越界）
]

N = 20  # 检查项总数（...；v3.12.0：17 悬空脚本引用）（v3.2.0-batch2：7→10；v3.3.1：10→11；v3.4.2 P2-4：12；v3.4.3 B3：13 联邦巡检；v3.8.0 P-2：14 版本号一致性；v3.8.0：15 frontmatter 闭合；v3.11.0：16 受众分层单一数据源）


# ── 8. 活跃目录备份膨胀（D12）─────────────────────────────
# v3.4.3 遗留批口径修复：原实现按"目录文件总数 >20"报警，把合法教学内容目录
# （任务课件 27 份/企业环控资料/教学视频，无一备份）误报为膨胀——检测语义对齐
# 告警名"备份膨胀"：只统计备份/旁路模式文件，≥3 个报警。与写回纪律一致
# （team-lead MD：禁 _v2/副本/优化版旁路文件）。
_BACKUP_PAT = re.compile(
    r"[（(]\s*\d+\s*[)）]\.\w{3,5}$"   # "xxx (1).ppt" 括号数字后缀（半/全角）
    r"|-副本|_副本|副本\.|优化版|修改版|旧版|backup"  # 中文旁路命名
    r"|_v\d+\.|-v\d+\.|\.bak$"          # 版本后缀 / .bak
)


def check_active_dir_files(expert_dir):
    """扫描课程工作区活跃目录的备份/旁路文件堆积（D12 备份膨胀）。"""
    ws = os.environ.get("VET_WS") or os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
    if not os.path.exists(ws):
        print(f"[8/{N}] – 未找到工作区（VET_WS 或默认路径）")
        return 0
    over_limit = []
    for d in sorted(os.listdir(ws)):
        full = os.path.join(ws, d)
        if not os.path.isdir(full) or d.startswith(".") or d.startswith("_trash"):
            continue  # 隐藏目录与 _trash 归档区不计
        hits = [f for f in os.listdir(full)
                if os.path.isfile(os.path.join(full, f))
                and not f.startswith("~$")           # Office 锁文件是临时态
                and _BACKUP_PAT.search(f)]
        if len(hits) >= 3:
            over_limit.append((d, len(hits), hits[:3]))
    if over_limit:
        print(f"[8/{N}] ⚠ 活跃目录备份膨胀（D12）: {len(over_limit)} 个目录含 ≥3 个备份/旁路文件")
        for d, n, ex in over_limit[:5]:
            print(f"     {d}: {n} 个，如 {ex}")
        print(f"     → 旁路文件按写回纪律归并 _trash 区；版本史交 snapshot 库")
        return 1
    print(f"[8/{N}] ✓ 活跃目录无备份膨胀（各目录备份/旁路文件均 <3）")
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
    """<workspace>/.snapshots/ 总大小 > max_mb 报警。
    v3.4.3 C3：上限改从 harness.yaml snapshot.max_mb 读取（原硬编码 500 与配置脱节——
    5.5G 基线是 v3.4.2 P2-3 的"基线永久"有意决策，体检器却按写死 500 持续误报）。"""
    ws = os.environ.get("VET_WS") or os.path.expanduser("~/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治")
    snap_root = os.path.join(ws, ".snapshots")
    max_mb = 500  # 兜底默认（yaml 不可读时）
    yaml_path = os.path.join(expert_dir, "config", "harness.yaml")
    try:
        in_snap = False
        for line in open(yaml_path, encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("snapshot:"):
                in_snap = True
                continue
            if in_snap:
                if not s.startswith(("max_mb:", "enabled:", "keep:", "auto_snap",
                                     "milestone", "first_snap", "#")) and s[0].isalpha():
                    break  # 离开 snapshot 段
                if s.startswith("max_mb:"):
                    val = s.split("#", 1)[0].split(":", 1)[1].strip()
                    max_mb = int(float(val))
                    break
    except Exception:
        pass
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
    if total_mb > max_mb:
        print(f"[10/{N}] ⚠ 快照库超容（D12 备份膨胀）: {total_mb:.0f} MB > {max_mb} MB"
              f"（harness.yaml snapshot.max_mb）")
        print(f"     → 跑 `python3 scripts/snapshot.py gc --workspace {ws}`，"
              f"或确认水位后调 harness.yaml max_mb")
        return 1
    print(f"[10/{N}] ✓ 快照库容量正常（{total_mb:.0f} MB ≤ {max_mb} MB，上限与 harness.yaml 对齐）")
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
    """v3.9.0 扩：此前只跑 test_harness.py，新增套件（如 v3.8.2 的 test_fix_md_image_refs、
    v3.9.0 的 test_loop_state）失败**体检完全看不见**——第 7 项形同虚设。
    现改为跑 scripts/ 下全部 test_*.py，逐个报码，任一失败即告警。
    """
    import glob as _glob
    suites = sorted(_glob.glob(os.path.join(expert_dir, "scripts", "test_*.py")))
    if not suites:
        print(f"[7/{N}] ⚠ 未找到任何 test_*.py，跳过")
        return 1
    failed, tails = [], []
    for t in suites:
        name = os.path.basename(t)
        try:
            p = subprocess.run([sys.executable, t], capture_output=True, text=True,
                               timeout=180)
        except subprocess.TimeoutExpired:
            failed.append((name, "超时 >180s"))
            continue
        last = [l for l in (p.stdout or "").strip().splitlines() if l.strip()]
        # 部分套件（如 test_snapshot）不打印总结行，回退显示退出码，避免输出空槽
        tail = last[-1] if last else f"rc={p.returncode}"
        tails.append(f"{name}={tail[:20]}")
        if p.returncode != 0:
            failed.append((name, tail))
    if failed:
        print(f"[7/{N}] 🔴 回归测试失败：{len(failed)}/{len(suites)} 个套件不通过")
        for name, tail in failed:
            print(f"     {name}  → {tail[:120]}")
        print(f"     → 处置：先修失败套件再发布；单套件调试：python3 scripts/<套件>.py")
        return 1
    print(f"[7/{N}] ✓ 回归测试通过（{len(suites)}/{len(suites)} 套件：{' '.join(tails)}）")
    return 0


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
                     "verify-ref", "sweep", "template-audit", "eval",
                     "loop"}   # v3.9.0：双层 Loop 状态机
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


def check_version_consistency(expert_dir):
    """v3.8.0 P-2：版本号四处一致性巡检（补 [12] 的覆盖盲区）。

    背景（2026-10-21 Loop A 基线核对实证）：v3.5.0/v3.6.0/v3.7.0 三版推进
    只改了 config/ 与 references/，漏掉三处：
      ① .claude-plugin/plugin.json 停在 3.4.4（只改了 .codebuddy 侧）
      ② scripts/harness.py 的 doctor 自报常量停在 v3.4.3
      ③ harness.py 文件头 docstring 停在 v3.4.0
    而 [12] 只校验"CHANGELOG 声称的子命令是否都在 doctor 表中"，
    不覆盖版本号——四处各说各话，没有任何一项体检能发现。

    判据：四处版本号必须互等（harness.py 常量带 "v" 前缀，比较时归一）。
    权威序：.codebuddy-plugin/plugin.json 为主，其余三处须与之一致。
    """
    import re as _re
    rows, main_ver = [], None

    def _norm(v):
        return (v or "").lstrip("v").strip()

    # ① 主清单（权威）
    mpath = os.path.join(expert_dir, ".codebuddy-plugin", "plugin.json")
    if not os.path.isfile(mpath):
        print(f"[14/{N}] – 缺主清单，跳过")
        return 0
    main_ver = _norm(str(_load(mpath).get("version", "")))
    rows.append((".codebuddy-plugin/plugin.json", main_ver or "<空>"))

    # ② ClaudeCode 侧清单
    cpath = os.path.join(expert_dir, ".claude-plugin", "plugin.json")
    if os.path.isfile(cpath):
        cv = _norm(str(_load(cpath).get("version", "")))
        rows.append((".claude-plugin/plugin.json", cv or "<空>"))

    #③ harness.yaml（全文扫描：version 行在长注释块之后，不能只读文件头）
    ypath = os.path.join(expert_dir, "config", "harness.yaml")
    if os.path.isfile(ypath):
        ytxt = open(ypath, encoding="utf-8", errors="replace").read()
        m = _re.search(r'^version:\s*"?v?([0-9.]+)"?\s*$', ytxt, _re.M)
        rows.append(("config/harness.yaml", _norm(m.group(1)) if m else "<无 version 段>"))

    # ④ harness.py doctor 自报常量
    hpath = os.path.join(expert_dir, "scripts", "harness.py")
    if os.path.isfile(hpath):
        htxt = open(hpath, encoding="utf-8", errors="replace").read()
        m = _re.search(r'"version":\s*"(v[0-9.]+)"', htxt)
        rows.append(("scripts/harness.py doctor 常量", _norm(m.group(1)) if m else "<无 version 常量>"))

    if not main_ver:
        print(f"[14/{N}] ⚠ 主清单无 version 字段，无法做一致性巡检")
        return 1
    bad = [(src, v) for src, v in rows if v != main_ver]
    if bad:
        print(f"[14/{N}] ⚠ 版本号不一致（主清单={main_ver}）：{len(bad)}/{len(rows)} 处偏离")
        for src, v in bad:
            print(f"     {src:34s} {v}≠ {main_ver}")
        print(f"     → 处置：以 .codebuddy-plugin/plugin.json 为权威，同步其余各处"
              f"（.claude-plugin/plugin.json / config/harness.yaml / scripts/harness.py 常量+文件头）")
        return 1
    print(f"[14/{N}] ✓ 版本号四处一致：{main_ver}")
    for src, v in rows:
        print(f"     {src:34s} {v}")
    return 0


def check_agent_frontmatter(expert_dir):
    """v3.8.0：agent frontmatter 闭合巡检（2026-10-21 双平台核验发现的真实缺陷）。

    背景：verifier.md 与 vet-med-ppt-team-team-lead.md 的 frontmatter 只有开头
    一个 `---`、**无闭合符**。WorkBuddy 平台解析器宽容（体检"6 个 agent 齐全"
    照常通过），但 Claude Code 官方规范明确规定：frontmatter 未正确闭合时
    文件会被当作普通文档处理——即 name/description/maxTurns 全部失效，
    极端情况下直接跳过该 agent（含主理人）。双平台行为不一致的隐性缺陷。

    判据：文件首行为 `---` **且** 存在第二个 `---` 终止行；否则不合规。
    """
    import re as _re
    agents_dir = os.path.join(expert_dir, "agents")
    if not os.path.isdir(agents_dir):
        print(f"[15/{N}] – 无 agents/ 目录，跳过")
        return 0
    bad = []
    checked = 0
    for name in sorted(os.listdir(agents_dir)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(agents_dir, name)
        try:
            lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
        except OSError:
            continue
        checked += 1
        seps = [i for i, l in enumerate(lines) if l.strip() == "---"]
        if not lines or lines[0].strip() != "---":
            bad.append((name, "首行不是 ---"))
        elif len(seps) < 2:
            bad.append((name, "frontmatter 未闭合（只有一个 ---）"))
        else:
            fm = "\n".join(lines[1:seps[1]])
            m = _re.search(r"^name:\s*(.+)$", fm, _re.M)
            if not m:
                bad.append((name, "frontmatter 内无 name 字段"))
    if bad:
        print(f"[15/{N}] ⚠ agent frontmatter 不合规：{len(bad)}/{checked} 个文件")
        for n, why in bad:
            print(f"     {n:34s} {why}")
        print(f"     → 处置：在 frontmatter 末尾补一行 `---`；未闭合会导致 Claude Code"
              f"侧按无 frontmatter 处理（name/description/maxTurns 全部失效）")
        return 1
    print(f"[15/{N}] ✓ agent frontmatter 全部合规（{checked} 个文件均闭合且含 name）")
    return 0


def check_audience_profile(expert_dir):
    """v3.11.0：受众分层单一数据源巡检（第 16 项）。

    背景（真实缺陷，非假设）：受众分层此前是「单点定义 + 11 处文件各自引用」，
    无机器校验。v3.10.0 已发生过同类事故——「终审 10 项」改成 11 项后，
    dual-loop-governance / loop-master-prompt / team-lead 三处仍写 10。
    本项把「受众层数 / 深度档位 / 时间结构 / 唯一默认 / 旧层名残留」变成可执行断言，
    下次再加层或改层，漏改会当场报出。

    判据：
      ① schema 存在且可解析
      ② 层数 == schema.validation.expect_audience_count（当前 4）
      ③ 深度档位键 == expect_depth_scale_keys（了解/理解/掌握）
      ④ 讲授+案例+互动 == 100
      ⑤ 有且仅有一个默认层
      ⑥ 引用文件不得出现 drift_guard 里的旧层名残留
    """
    schema_path = os.path.join(expert_dir, "references", "audience-profile-schema.yaml")
    if not os.path.exists(schema_path):
        print(f"[16/{N}] ⚠ 受众 schema 缺失：references/audience-profile-schema.yaml")
        print(f"     → 处置：受众分层无单一数据源，各文件各自定义必然漂移；"
              f"先落 schema 再改引用方")
        return 1
    try:
        import yaml
        with open(schema_path, encoding="utf-8") as f:
            sc = yaml.safe_load(f)
    except Exception as e:
        print(f"[16/{N}] ⚠ 受众 schema 解析失败：{e}")
        return 1

    bad = []
    val = sc.get("validation", {}) or {}
    audiences = sc.get("audiences", []) or []

    # ② 层数
    exp_n = val.get("expect_audience_count", 4)
    if len(audiences) != exp_n:
        bad.append(f"受众层数 {len(audiences)} ≠ 期望 {exp_n}")
    # ③ 深度档位
    exp_scale = val.get("expect_depth_scale_keys", ["了解", "理解", "掌握"])
    got_scale = list((sc.get("depth_scale") or {}).keys())
    if got_scale != exp_scale:
        bad.append(f"深度档位 {got_scale} ≠ 期望 {exp_scale}")
    # ④ 时间结构合计
    ts = sc.get("time_structure", {}) or {}
    ssum = ts.get("lecture_pct", 0) + ts.get("case_pct", 0) + ts.get("interaction_pct", 0)
    if ssum != val.get("time_structure_sum_must_equal", 100):
        bad.append(f"课内时间结构合计 {ssum} ≠ 100")
    # ⑤ 唯一默认层
    defaults = [a.get("id") for a in audiences if a.get("is_default")]
    if val.get("default_audience_must_be_one", True) and len(defaults) != 1:
        bad.append(f"默认层数 {len(defaults)}（应为 1）：{defaults}")
    # 每层必备键
    req = val.get("each_audience_required_keys", []) or []
    for a in audiences:
        miss = [k for k in req if k not in a]
        if miss:
            bad.append(f"层 {a.get('name', a.get('id'))} 缺键 {miss}")

    if bad:
        print(f"[16/{N}] ⚠ 受众分层定义不合规（{len(bad)} 项）")
        for b in bad:
            print(f"     {b}")
        print(f"     → 处置：以 references/audience-profile-schema.yaml 为唯一源修正；"
              f"各引用文件不得自行另立定义")
        return 1

    # ⑥ 旧层名残留扫描
    drift = val.get("drift_guard", {}) or {}
    stale = drift.get("forbidden_definitions_in_references", []) or []
    hits = []
    for sub in ("references", "agents"):
        d = os.path.join(expert_dir, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith((".md", ".yaml", ".yml")):
                continue
            if name == "audience-profile-schema.yaml":
                continue      # schema 自身含 forbidden 字面量（自检用），跳过
            fp = os.path.join(d, name)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for pat in stale:
                if pat in txt:
                    hits.append(f"{sub}/{name} 含旧层名「{pat}」")
    if hits:
        print(f"[16/{N}] ⚠ 旧层名残留 {len(hits)} 处（受众已改四层，引用未同步）")
        for h in hits:
            print(f"     {h}")
        print(f"     → 处置：这些文件仍用 v3.10.0 旧受众层；改为引用 schema，勿各自定义")
        return 1

    print(f"[16/{N}] ✓ 受众分层合规（{len(audiences)} 层 · 深度档 {'/'.join(got_scale)} · "
          f"时间 {ts.get('lecture_pct')}/{ts.get('case_pct')}/{ts.get('interaction_pct')} · "
          f"默认层 {defaults[0] if defaults else '无'}）")
    return 0


def check_dangling_script_ref(expert_dir):
    """v3.12.0：悬空脚本引用巡检（第 17 项）。

    背景（真实缺陷）：agent MD 引用 `registry_rebuild.py` / `repair_p0_v200.py`
    作为"职责已被承接"的论据，但两者**均不在本包 scripts/ 内**（属课程工作区）。
    拿包外脚本当包内论据 = 悬空引用：工作区一换，论据自动失效且无人察觉。

    判据：扫描 agents/ 与 references/ 中形如 `<name>.py` 的反引号引用，
         若不在 scripts/ 且不在"已知外部脚本"白名单里 → 告警。
    白名单是显式的：新增外部依赖必须登记，不靠"忘了就没人管"。
    """
    scripts_dir = os.path.join(expert_dir, "scripts")
    if not os.path.isdir(scripts_dir):
        print(f"[17/{N}] – 无 scripts/ 目录，跳过")
        return 0
    local = {f for f in os.listdir(scripts_dir) if f.endswith(".py")}
    # 显式登记的外部脚本（课程工作区等），登记即"承认这是外部依赖"
    known_external = {"registry_rebuild.py", "repair_p0_v200.py"}

    import re as _re
    pat = _re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.py)`")
    dangling = []
    for sub in ("agents", "references"):
        d = os.path.join(expert_dir, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith((".md", ".yaml", ".yml")):
                continue
            fp = os.path.join(d, name)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for m in set(pat.findall(txt)):
                if m in local or m in known_external:
                    continue
                dangling.append(f"{sub}/{name} 引用 `{m}`（包内 scripts/ 无此文件）")

    if dangling:
        print(f"[17/{N}] ⚠ 悬空脚本引用 {len(dangling)} 处")
        for x in dangling:
            print(f"     {x}")
        print("     → 处置：① 若确为本包脚本，补进 scripts/；"
              "② 若属外部依赖，在本检查的 known_external 白名单登记并在 MD 标注来源；"
              "③ 若已废弃，删除该引用——悬空论据会让「职责已被承接」的判断失效")
        return 1
    print(f"[17/{N}] ✓ 无悬空脚本引用（本地 {len(local)} 个 .py；"
          f"外部白名单 {len(known_external)} 个已标注来源）")
    return 0


def check_dead_config_keys(expert_dir):
    """v3.12.0：死配置巡检（第 18 项）——「配了但没人读」的配置键。

    背景（真实缺陷，且已连续三轮复发同型问题）：
      · v3.12.0 `harness.yaml#budgets` 9 项中 6 项只在 `_FALLBACK` 出现、代码从不读，
        而 `sop-stages.md` 等文档仍当生效约束引用 → "看起来有护栏、实际不设防"
      · v3.12.0 `verify_deck.py` 三源阈值 0.8/0.1 三处硬编码，
        而 `harness.yaml` 与 `domain_config.yaml` 都配了同值 → 改配置不改行为
      · v3.11.0 受众层、v3.12.0 回传信封，均为"多处各自定义"导致漂移

    根因相同：**配置写了、文档引用了，但没有任何代码读取者**。
    本项一次性把 config/ 下所有叶子键与 scripts/ 全量文本做交叉比对——
    某个键若在 scripts/ 里找不到任何提及，即判为死配置。

    误报豁免：① 键名在代码里以点号路径或下划线变体出现（做归一化后再查）
              ② 显式登记的 known_textual（由文档层解释性引用、无需代码消费）
    判据不追求"绝对无提及"，而追求"**必须有人解释它为什么不被代码读**"。
    """
    cfg_dir = os.path.join(expert_dir, "config")
    scripts_dir = os.path.join(expert_dir, "scripts")
    if not os.path.isdir(cfg_dir) or not os.path.isdir(scripts_dir):
        print(f"[18/{N}] – 无 config/ 或 scripts/ 目录，跳过")
        return 0

    try:
        import yaml
    except ImportError:
        print(f"[18/{N}] – 无 yaml 模块，跳过")
        return 0

    # 代码全文（scripts/*.py，含注释与文档字符串——有文档说明也算"有人管"）
    code_text = ""
    for f in sorted(os.listdir(scripts_dir)):
        if f.endswith(".py"):
            try:
                code_text += open(os.path.join(scripts_dir, f),
                                  encoding="utf-8", errors="replace").read()
            except OSError:
                pass

    def norm(s):
        """归一化：去掉非字母数字与下划线，便于 'three-source' / 'three_source' 同查。"""
        return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == "_")

    code_norm = norm(code_text)

    # ── 人读型字段白名单（当前无代码读取者，但本就不该由代码消费）────────
    # 判据设计的关键教训：首版把"无代码读取者"一律判死配置，首跑 80 项里
    # 绝大多数是 `writes_allowed`（成员写权限声明）、`duty`（职责描述）这类
    # **给人看/给主理人判断**的字段——它们本就不该有代码读取者。
    # 故改为：人读型显式登记（登记=承认"这个没人读是对的"），
    # 只有既非人读、又不被代码消费的配置键才算死配置。
    known_textual = {
        # 元数据/说明
        "description", "version", "name", "note", "comment", "duty",
        # 域标签与命名规范（展示元数据）
        "label_zh", "label_en",
        "default_disease_module_prefix", "case_id_prefix",
        # 成员能力声明：供主理人 spawn 前判断，不由脚本消费
        "writes_allowed",
        # 降级通道的说明文本与披露要求：主理人按条款执行，无脚本判定
        "general-purpose+persona", "script_pipeline", "require_disclosure",
        "degrade_modes",
        # 闸的兼容标记：历史遗留，仅作说明
        "legacy_compat",
    }

    # ── 人读型路径段白名单（按前缀豁免，比逐个键名更抗漂移）────────
    path_prefixes = (
        ".disease_modules.",     # 课程目录内容，按域整体读取
        ".gates.",               # 五闸人读判据（机器判据在 verify_deck）
        ".ai_literacy.",         # AI 素养判据（主理人消费）
        ".snapshot.",            # 快照策略（snapshot.py 按部分键消费）
        ".fallback.",            # 降级通道说明（主理人按条款执行）
        ".members.",             # 成员能力/权限声明（供 spawn 前判断）
        ".domains.",             # 域标签与命名规范（展示元数据）
    )

    dead, alive, textual = [], 0, 0

    def walk(node, path, fname):
        """递归收集叶子键。

        判据用**整条路径**而非末段键名——因为代码里常见的读取形式是
        `cfg["domains"]["animal-medicine"]["label_zh"]`，末段 `label_zh`
        在别的分支下也可能出现，只查末段会误报；反过来，只查整条路径会漏报
        「代码读了同名字段但走的是另一条分支」，故**两段都查，任一命中即算有读取者**。
        """
        nonlocal alive, textual
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k), fname)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    walk(item, path, fname)
                else:
                    walk(item, path, fname)
        else:
            full = str(path)
            leaf = full.split(".")[-1]
            # 去掉数组下标（YAML 里不会有，这里防御性处理）
            leaf = leaf.split("[")[0]
            n_full, n_leaf = norm(full), norm(leaf)
            # 路径段命中：`.members.a.b` → 检查 `.a.b`、`.a`、`.members`
            segs = full.split(".")
            seg_hit = any("." + ".".join(segs[i:]) in path_prefixes
                          for i in range(len(segs)))
            if n_full and n_full in code_norm:
                alive += 1
            elif seg_hit or leaf.lower() in known_textual:
                textual += 1          # 人读型：登记在案，无代码读取者是合理的
            elif n_leaf and n_leaf in code_norm:
                alive += 1
            else:
                dead.append((fname, full, node))

    cfg_files = [f for f in sorted(os.listdir(cfg_dir))
                 if f.endswith((".yaml", ".yml"))]
    for cf in cfg_files:
        fp = os.path.join(cfg_dir, cf)
        try:
            data = yaml.safe_load(open(fp, encoding="utf-8"))
        except Exception as e:
            print(f"[18/{N}] ⚠ {cf} 解析失败：{e}")
            return 1
        walk(data, "", cf)

    # ── 最终设计决策（v3.12.0，含一次失败的教训）──────────────────
    # 首版把"无代码读取者"一律判死配置 → 首跑 80 项；放宽到路径段白名单仍 100 项。
    # 根本问题：**「谁该被代码读」无法自动判定**——`tools_whitelist`（成员工具权限）、
    # `pass_rule`（AI 素养判据）、`snapshot.*`（快照策略）都是有意义的配置，
    # 但它们本就该由**主理人/流程**消费而非脚本。继续调白名单只会变成
    # 「为了让检查变绿而往白名单里塞」的活——那是自欺。
    #
    # 故正式降级为 **INFO 提示，不阻断、不计入 rc**：
    #   • 价值：把「配了但确认无人读」这件事**显式列出来**，供人工复核；
    #   • 代价：不阻断。这是有意的取舍——**假阳性必须为零，否则体检会被绕过**。
    # 真正会阻断的判死配置已由更精确的专项检查覆盖：
    #   第 16 项（受众分层唯一源）、第 17 项（悬空脚本引用）、budget list（死配置可视化）。
    #
    # ⚠️ **已知局限（反例实测，如实标注）**：本检查是**纯文本包含匹配**，无法判断
    # 「代码里提到这个键名」与「代码真的读了这个值」的区别。反例：把 verify_deck 里
    # `cfg.get("three_source_check")` 改成 `{}`（真读行为已破坏）后，本项统计**不变**——
    # 因为该键名在其它脚本/注释/docstring 中仍出现，仍被判定为"有读取者"。
    # 故本项**只能发现"完全无人提及"的键**，发现不了"提到但没用"的键。
    # 要覆盖后者，需静态数据流分析（远超本项定位），或用 `verify_three_source_config.py`
    # 这类**逐键断言运行时值 == 配置值**的专项验证（本次已配套提供）。

    if dead:
        print(f"[18/{N}] ℹ 提示：{len(dead)} 个配置键在 scripts/ 中无读取者"
              f"（代码读取 {alive} 项 · 人读型登记 {textual} 项）")
        for fname, path, val in dead[:12]:
            print(f"     · {fname}#{path} = {val!r}")
        if len(dead) > 12:
            print(f"     · … 还有 {len(dead) - 12} 项")
        print("     → 本项为**提示不阻断**（人工复核用）：多数是主理人/流程消费的人读型配置，"
              "如成员工具权限、快照策略、AI 素养判据。")
        print("     → 若确认某个键**本该被脚本消费**却无人读（如本次修掉的 three_source 阈值），"
              "按「① 删掉 ② 实现读取 ③ 登记白名单」三选一处置。")
    else:
        print(f"[18/{N}] ✓ 无死配置（{len(cfg_files)} 个 config 文件："
              f"代码读取 {alive} 项 · 人读型登记 {textual} 项）")
    return 0   # 恒不阻断


def check_fallback_drift(expert_dir):
    """v3.14.0：`_FALLBACK` 回退阈值 vs `visual-rules.yaml` 漂移巡检（第 19 项）。

    背景：`_FALLBACK` 是 verify_deck 在 yaml 不可读时的**受控逃生舱**
    （须显式设 `VERIFY_ALLOW_FALLBACK=1` 才启用）。它的风险不在"当前值错"
    ——实测当前 7 项阈值与 yaml **完全一致**；风险在于**改了 yaml 忘了改 _FALLBACK**：
    yaml 加载失败时门禁会拿过期阈值继续判，且**完全静默**——比无护栏更危险
    （人以为在用新红线，实际是老红线）。

    本项把 _FALLBACK 与 yaml 逐项比对：漂移即告警并指出**该同步哪一项**。
    这与第 18 项的区别：18 项查"配置有没有人读"，本项查"**两份同源数据是否一致**"——
    后者判据确定（等值即可比）、假阳性为零，故本项**阻断**。
    """
    vd = os.path.join(expert_dir, "scripts", "verify_deck.py")
    rules_p = os.path.join(expert_dir, "config", "visual-rules.yaml")
    if not os.path.exists(vd) or not os.path.exists(rules_p):
        print(f"[19/{N}] – 缺 verify_deck.py 或 visual-rules.yaml，跳过")
        return 0
    try:
        import yaml
        src = open(vd, encoding="utf-8", errors="replace").read()
        rules = yaml.safe_load(open(rules_p, encoding="utf-8"))
    except Exception as e:
        print(f"[19/{N}] ⚠ 读取失败：{e}")
        return 1

    # 从 _FALLBACK 字面量里解析出各阈值（用 AST 避免正则误抓）
    import ast
    try:
        tree = ast.parse(src)
        fb = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_FALLBACK" for t in node.targets):
                fb = ast.literal_eval(node.value)
                break
        if fb is None:
            print(f"[19/{N}] – verify_deck.py 中未找到 _FALLBACK 字面量，跳过")
            return 0
    except Exception as e:
        print(f"[19/{N}] ⚠ 解析 _FALLBACK 失败：{e}")
        return 1

    # yaml 侧对应值（键名映射：fallback 键 → yaml 取值路径）
    def yget(path, default=None):
        cur = rules
        for seg in path:
            if not isinstance(cur, dict) or seg not in cur:
                return default
            cur = cur[seg]
        return cur

    pairs = [
        ("body_min_pt", yget(("font", "body_min_pt")), "font.body_min_pt"),
        ("note_min_pt", yget(("font", "note_min_pt")), "font.note_min_pt"),
        ("max_colors_per_slide", yget(("density", "max_colors_per_slide")), "density.max_colors_per_slide"),
        ("max_chars_per_slide", yget(("density", "max_chars_per_slide")), "density.max_chars_per_slide"),
        ("overlap_ratio", yget(("geometry", "overlap_ratio")), "geometry.overlap_ratio"),
        ("p2_note_coverage", yget(("gate", "p2_note_coverage")), "gate.p2_note_coverage"),
    ]
    drift = []
    for fk, yv, ypath in pairs:
        if yv is None:
            continue          # yaml 未配该项（如 gate 缺省），不判漂移
        fv = fb.get(fk)
        if fv is None:
            drift.append(f"{fk}: _FALLBACK 缺该项（yaml={yv} @ {ypath}）")
            continue
        try:
            same = abs(float(fv) - float(yv)) < 1e-9
        except (TypeError, ValueError):
            same = fv == yv
        if not same:
            drift.append(f"{fk}: _FALLBACK={fv!r} ≠ yaml={yv!r}（{ypath}）")

    # hours_page_range 单独比
    y_hpr = rules.get("hours_page_range")
    f_hpr = fb.get("hours_page_range")
    if isinstance(y_hpr, dict) and isinstance(f_hpr, dict):
        for k, v in y_hpr.items():
            fv = f_hpr.get(k, f_hpr.get(float(k)))
            if fv is None or list(fv) != list(v):
                drift.append(f"hours_page_range[{k}]: _FALLBACK={fv!r} ≠ yaml={v!r}")

    if drift:
        print(f"[19/{N}] ⚠ 回退阈值与 yaml 漂移 {len(drift)} 项"
              f"——yaml 加载失败时门禁会拿过期阈值继续判，且静默")
        for d in drift:
            print(f"     {d}")
        print("     → 处置：同步 verify_deck.py 的 `_FALLBACK`（受控逃生舱，"
              "仅 VERIFY_ALLOW_FALLBACK=1 时启用）；勿只改 yaml 不改回退值")
        return 1
    n = len(pairs) + (len(y_hpr) if isinstance(y_hpr, dict) else 0)
    print(f"[19/{N}] ✓ 回退阈值无漂移（_FALLBACK 与 visual-rules.yaml 逐项一致，"
          f"核对 {n} 项）")
    return 0


def check_handoff_paths(expert_dir):
    """v3.14.0：跨成员交接指令的落盘契约巡检（第 20 项）。

    背景：包内 4 处禁令禁止成员横向直连（平台无 agent-to-agent 通道），
    但历史上有 3 处业务指令写成「交严真奥补查」「进入苏学法的候选」——
    **交接路径未定义**，成员可能干等或私聊。v3.13.0 已把那 3 处改写为
    落盘契约/信封字段，但**新写或改写文档时极易复现**（这是文风问题，不是一次性问题）。

    本项扫 agents/ 与 references/ 中形如「交/找/通知/传给 + 某成员」的交接表述，
    检查同一句（或紧邻段落）是否给出了合规载体：
      ① 信封 `issues` 字段  ② 落盘路径（`/…` 或 `.md` 文件名）
      ③ 明示「经主理人」  ④ 明示「不得直接联系 / 禁止 SendMessage」
    四者皆无 = 悬空交接 → 告警。

    判据确定（有无载体即可判）故**阻断**；误报面通过要求"同一行或下两行内出现载体"收敛。
    """
    import re as _re
    # 交接动词：交…补查 / 找…/ 通知… / 传给… / 交由…
    pat = _re.compile(
        r"(交[给被]?\s*[\u4e00-\u9fa5]{2,3}(补查|核查|补|处理|确认|答复)"
        r"|通知\s*[\u4e00-\u9fa5]{2,3}"
        r"|传给\s*[\u4e00-\u9fa5]{2,3}"
        r"|找\s*[\u4e00-\u9fa5]{2,3}(补查|核查|确认|处理))")
    # 合规载体信号
    carriers = (
        "issues",             # 信封字段
        ".md", "/",           # 落盘路径或文件名
        "落盘", "写入", "文件",
        "主理人",             # 明示中转
        "不得直接", "禁止", "❌",
    )
    members = {"严真奥", "苏学法", "屠明熙", "郅作基", "验收员"}

    dangling = []
    for sub in ("agents", "references"):
        d = os.path.join(expert_dir, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            fp = os.path.join(d, name)
            try:
                lines = open(fp, encoding="utf-8", errors="replace").read().split("\n")
            except OSError:
                continue
            for i, ln in enumerate(lines):
                if not pat.search(ln):
                    continue
                if not any(m in ln for m in members):
                    continue      # 不是指向具体成员的交接
                # 上下文窗口：本行 + 下两行（跨行的补充说明也算给了载体）
                window = "\n".join(lines[i:i + 3])
                if any(c in window for c in carriers):
                    continue
                snippet = ln.strip()[:60]
                dangling.append(f"{sub}/{name}:{i + 1} 「{snippet}」")

    if dangling:
        print(f"[20/{N}] ⚠ 悬空跨成员交接 {len(dangling)} 处（说了要交给谁，但没给交接载体）")
        for x in dangling[:12]:
            print(f"     {x}")
        if len(dangling) > 12:
            print(f"     … 还有 {len(dangling) - 12} 处")
        print("     → 处置：每处须补①信封 `issues` 字段 ②落盘路径 ③明示经主理人中转 "
              "④明示不得直接联系（四者之一即可）；否则成员只能干等或私聊")
        return 1
    print(f"[20/{N}] ✓ 跨成员交接均有载体（扫 agents/ 与 references/，"
          f"未发现悬空交接）")
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
    # v3.8.0 P-2：版本号四处一致性巡检（无论 quick/no-governance 均跑；补 [12] 盲区）
    rc |= check_version_consistency(path)
    # v3.8.0：agent frontmatter 闭合巡检（无论 quick/no-governance 均跑）
    rc |= check_agent_frontmatter(path)
    # v3.11.0：受众分层单一数据源巡检（防 11 处引用各自漂移）
    rc |= check_audience_profile(path)
    # v3.12.0：悬空脚本引用巡检（防拿包外脚本当包内论据）
    rc |= check_dangling_script_ref(path)
    # v3.12.0：死配置巡检（防「配了没人读」；提示不阻断）
    rc |= check_dead_config_keys(path)
    # v3.14.0：回退阈值漂移巡检（防 yaml 改了忘改 _FALLBACK）
    rc |= check_fallback_drift(path)
    # v3.14.0：跨成员交接落盘契约巡检（防「交XX」不写路径复现）
    rc |= check_handoff_paths(path)

    print()
    if rc == 0:
        print("结论：✅ 全部通过，可发布 / 可运行 validate_expert.py")
    else:
        print("结论：⚠️ 存在告警，处理后再发布（settings.json 已自愈）")
    return rc


if __name__ == "__main__":
    sys.exit(main())

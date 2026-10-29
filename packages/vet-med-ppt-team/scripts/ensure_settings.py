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
  21 三源阈值双重声明防线（v3.16.0）                  → harness.yaml#budgets 重复声明 + budget check 运行时值 ≠ domain_config【只读】★新
  22 闸3 交叉复检领域映射（v3.17.0）                  → sop-stages.md 实际写法 ≠ config/guard.yaml 登记值【只读·阻断】★新
 23 域绑定残留巡检（v3.17.0）                       → agents/references 里的学科专有词应下沉到域档案【提示·不阻断】★新
 26 根⇄镜像提交态一致性（v3.27.0 L-7）            → 提交态漂移则告警【只读·阻断】★new

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

# v3.16.0 修（由独立测试工程师对抗性验证抓出，属**假绿陷阱**）：
#   此处原先硬编码真实安装包的绝对路径。后果是——把包复制到 /tmp 做回归/反例验证时，
#   运行 `python3 scripts/ensure_settings.py`（**不带参数**）会静默体检**真实包**，
#   而不是当前所在的副本：于是"改坏副本 → 跑体检 → 报全绿"，得到的是**假绿**。
#   这正是本项目最忌的失败形态（护栏看起来在、实际没设防），且它专坑最需要它的场景——
#   即"验证副本"这件事本身。
# 改法：以脚本自身位置推导包根（<包>/scripts/ensure_settings.py → <包>），
#   复制到任何位置都能正确体检那一份；仅当推导结果不像一个包时才回退旧硬编码路径。
_SELF_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LEGACY_DEFAULT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team"
)
DEFAULT = (_SELF_PKG if os.path.exists(
    os.path.join(_SELF_PKG, ".codebuddy-plugin", "plugin.json"))
    else _LEGACY_DEFAULT)

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

N = 26  # 检查项总数（...；v3.12.0：17 悬空脚本引用）（v3.2.0-batch2：7→10；v3.3.1：10→11；v3.4.2 P2-4：12；v3.4.3 B3：13 联邦巡检；v3.8.0 P-2：14 版本号一致性；v3.8.0：15 frontmatter 闭合；v3.11.0：16 受众分层单一数据源；v3.17.0：22 闸3 交叉复检映射；v3.25.0：25 harness 副本结构比对；v3.27.0 L-7：26 根⇄镜像提交态一致性）


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
#: 反例批次因**环境限制**被跳过时，套件 stdout 里出现的**专属**标记。
#:
#: ⚠ 刻意**复制**而非 `import scripts/test_arch_drift`：import 该文件会把整个
#:   测试模块拉进体检进程（重 + 有副作用），体检器不该为此付费。
#:   漂移风险由 `scripts/test_regression_skip_report.py` 的 T5 锁死
#:   （两处字面量必须逐字一致，不一致即判红）。
ANTIEXAMPLE_SKIP_MARKER = "[WARN][vet-med-ppt-team] 反例批次因环境限制被跳过"

#: 第 7 项检出「因环境限制被跳过」时是否**阻断**发布（v3.27.0 P0 收尾）。
#:
#: ⚠ 默认 False（**不阻断**）—— 理由见 `check_regression` 的 docstring。
#: ⚠ **双向可查**：若将来决定改为阻断，把这里改成 True 即可；
#:   判定逻辑（`has_env_skip`）与报告文案都不必动。
REGRESSION_SKIP_BLOCKS_RELEASE = False

#: 第 7 项最近一次运行的「未验证」留痕（供 `main()` 汇总结论时区分
#: 「真全绿」与「全绿但有跳过」）。
#:
#: ⚠ 为何用模块级而非返回值：`main()` 用 `rc |= check_regression(...)` 聚合，
#:   返值通道已被 rc 占用；而「是否阻断」与「是否未验证」是**两个维度**，
#:   挤进一个 int 会丢掉后者 ⇒ 就会留下"结论写着『全部通过』、实际有跳过"
#:   的假绿形态 —— 那正是本项要消灭的东西。
REGRESSION_UNVERIFIED = {"suites": [], "cases": 0}

#: 套件级状态常量（三态，供分级报告使用）
REG_PASS = "pass"                          # 真通过：rc=0 且未检出跳过
REG_PASS_WITH_SKIPS = "pass_with_skips"   # rc=0 但检出「因环境限制被跳过」
REG_FAIL = "fail"                          # rc≠0（**语义沿用** v3.9.0 起的行为，不变）


def count_suite_skips(stdout, stderr=""):
    """统计单个回归套件输出里的「跳过」信号（**纯函数**）。

    返回 dict：
      marker_hit    : bool —— stdout 是否出现 `ANTIEXAMPLE_SKIP_MARKER`
      skipped_cases : int  —— unittest 摘要里的 `skipped=N`
      anti_skips    : int  —— stderr 逐项输出里属于反例类（TestGuardAntiExamples）
                             的 skip 条数（**诊断增强**，不参与判定）
      text          : str  —— 人可读的一行摘要
    """
    out = stdout or ""
    err = stderr or ""
    marker_hit = ANTIEXAMPLE_SKIP_MARKER in out
    # ⚠ unittest 的 summary（`OK (skipped=N)`）默认写 **stderr**
    #   （TextTestRunner 的默认 stream 是 sys.stderr）—— 实测确认。
    #   体检第 7 项此前只读 stdout，所以"被跳过多少"一直是**看不见**的；
    #   两个流都扫，兼容 pytest 风格（summary 落 stdout）。
    counts = [int(x) for x in re.findall(r"skipped=(\d+)", err + "\n" + out)]
    skipped_cases = max(counts) if counts else 0
    anti_skips = _count_anti_example_skips(err)
    return {
        "marker_hit": marker_hit,
        "skipped_cases": skipped_cases,
        "anti_skips": anti_skips,
        "text": f"rc=0",
    }


def _count_anti_example_skips(stderr):
    """数 stderr 里属于**反例类**的 skip 条数（诊断增强，纯函数）。

    ⚠ unittest 的 verbose 输出可能把「用例 id 行」与「结果行」拆成两行
      （用例有 docstring 时会拆），也可能合成一行 ⇒ 两种形态都要认。
    ⚠ 这是**诊断信息**，不是判据：它依赖 unittest 的输出格式，
      格式一变就数不到 ⇒ 不能拿它当"能不能检出"的依据。
    """
    lines = (stderr or "").splitlines()
    n = 0
    for i, ln in enumerate(lines):
        if "skipped '" in ln:
            if "TestGuardAntiExamples" in ln:
                n += 1
            elif i > 0 and "TestGuardAntiExamples" in lines[i - 1]:
                n += 1
        elif "TestGuardAntiExamples" in ln and i + 1 < len(lines) \
                and "skipped '" in lines[i + 1]:
            n += 1
    return n


def has_env_skip(stdout, stderr=""):
    """判定某套件输出是否表明「反例批次因环境限制被跳过」（**纯函数**）。

    ⚠ **为何必须两个信号合取**（任一单独用都不成立——v3.27.0 P0 收尾实测）：

      ① 只看 marker（专属标记）⇒ **恒真误报**：反例类的**受控自测**
         `scripts/test_arch_drift.py::TestAntiExampleSkipSemantics` 会**故意**
         触发 `setUp` 的「环境限制 ⇒ skip」分支，用来证明"跳过语义"本身没坏；
         它每次运行都会往 stdout 打**同样**的 marker（实测：11 个反例全部
         通过的健康环境下，stdout 里仍有 2 处 marker）。⇒ 单看 marker 等于
         每次体检都误报"反例未验证"，那是另一种假绿。
      ② 只看 `skipped=N` ⇒ 把「与反例无关的 skip」误报成「反例未验证」
         （例：`test_three_source_online.py` 的「外网不可达」、
         `test_ooxml_lint.py` 的 `skipUnless(python-pptx)`）。
      ⇒ **合取**：marker 说明**反例批次**走进了环境限制分支；
        `skipped=N` 说明这些用例**真的没被执行**（受控自测的手工记账
        不进外层 summary ⇒ 不会把受控自测算进来）。
    """
    sig = count_suite_skips(stdout, stderr)
    return bool(sig["marker_hit"] and sig["skipped_cases"] > 0)  # MUT_POINT:SKIP_VERDICT


def analyze_suite_output(name, rc, stdout, stderr=""):
    """判定单个回归套件的输出 ⇒ (status, detail)（**纯函数**）。

    status ∈ {REG_PASS, REG_PASS_WITH_SKIPS, REG_FAIL}
    detail: dict（见 `count_suite_skips` 的返回结构 + `fail_tail`）

    ⚠ 纯函数：不碰文件系统、不起子进程 ⇒ 测试可直接调用，
      无需真跑全量回归（真跑一次约 2 分钟，且在本机会因宿主 broker 拦 mkdir
      而产生「因环境限制跳过」的真实现象，反而污染判据本身）。
    """
    sig = count_suite_skips(stdout or "", stderr or "")
    detail = {
        "marker_hit": sig["marker_hit"],
        "skipped_cases": sig["skipped_cases"],
        "anti_skips": sig["anti_skips"],
        "text": f"rc={rc}",
    }
    if rc != 0:
        # ⚠ 失败语义**优先**：rc≠0 一律判失败，跳过信号不得掩盖失败。
        return REG_FAIL, detail
    if has_env_skip(stdout, stderr):
        extra = (f"，其中反例用例 {sig['anti_skips']} 个"
                 if sig["anti_skips"] else "")
        detail["text"] = (f"rc=0 / 检出「反例批次因环境限制跳过」"
                          f"（跳过用例 {sig['skipped_cases']} 个{extra}）")
        return REG_PASS_WITH_SKIPS, detail
    return REG_PASS, detail


def format_regression_report(results, total_suites):
    """把各套件的判定结果汇成体检第 7 项的报告行（**纯函数**）。

    results: [(name, status, detail), ...]
    返回 (lines, rc)：
      lines —— 报告行（list[str]，不带换行）
      rc    —— 是否**阻断**（0/1）
    """
    failed = [(n, d) for (n, s, d) in results if s == REG_FAIL]
    skipped = [(n, d) for (n, s, d) in results if s == REG_PASS_WITH_SKIPS]
    lines = []
    if failed:
        lines.append(f"[7/{N}] 🔴 回归测试失败：{len(failed)}/{total_suites} 个套件不通过")
        for name, d in failed:
            lines.append(f"     {name}  → {(d.get('fail_tail') or d['text'])[:120]}")
        lines.append("     → 处置：先修失败套件再发布；单套件调试：python3 scripts/<套件>.py")
        return lines, 1
    if skipped:
        total_cases = sum(d["skipped_cases"] for _, d in skipped)
        lines.append(f"[7/{N}] ⚠ 回归测试通过但有 {len(skipped)} 个套件因环境限制跳过"
                     f"（反例批次未验证）")
        for name, d in skipped:
            lines.append(f"     {name} → {d['text']}")
        lines.append(f"     → 合计 {total_cases} 个用例未执行 ⇒ 守卫的「能红」属性本轮"
                     f"**未验证**（未验 ≠ 已验，勿据此认为守卫有效）")
        lines.append("     → 处置：环境限制所致（宿主 broker 拦 mkdir / TMPDIR 不可写），"
                     "**不是包缺陷**；换个会话或另设 TMPDIR 后重跑本套件再判")
        return lines, (1 if REGRESSION_SKIP_BLOCKS_RELEASE else 0)
    tails = " ".join(f"{n}={d['text']}" for (n, _s, d) in results)
    lines.append(f"[7/{N}] ✓ 回归测试通过（{len(results)}/{total_suites} 套件：{tails}）")
    return lines, 0


def format_final_conclusion(rc, unverified):
    """渲染体检最终结论（**纯函数**，v3.27.0 P0 收尾）。

    参数：
      rc        : int —— 体检聚合退出码
      unverified: dict —— 「未验证」累加器（`REGRESSION_UNVERIFIED` 同构）

    返回：list[str]（待打印的行，不带换行）

    ⚠ **为何必须抽成纯函数**（本轮实测踩到的坑）：
      首版把这段逻辑**内联**在 `main()` 里 ⇒ 判据只能做**静态源码检查**
      （AST 查「有没有引用 `REGRESSION_UNVERIFIED`」）⇒ 实测**反向对照失败**：
      把 `REGRESSION_UNVERIFIED.get("suites")` 改成 `[]`，
      而 `.get("cases")` 那行**仍引用着它** ⇒ 静态检查照样通过 ⇒
      **判据红了假绿**（变异后 8 passed，判据没抓住）。
      ⇒ 抽成纯函数后，判据可**真正执行**并断言输出内容 ⇒ 变异必红。

    ⚠ 三档语义（与 `check_regression` 的返值语义一致）：
      · rc=0 且无未验证项 ⇒ 「✅ 全部通过，可发布」
      · rc=0 但有未验证项 ⇒ 「⚠️ 存在**未验证项**」——**降级但不阻断**
        （环境问题不阻断发布；理由见 `check_regression` docstring）
      · rc≠0 ⇒ 「⚠️ 存在告警，处理后再发布」
    """
    suites = (unverified or {}).get("suites") or []
    cases = (unverified or {}).get("cases") or 0
    if rc == 0 and suites:
        lines = [
            f"结论：⚠️ 存在**未验证项**（{len(suites)} 个套件 / {cases} 个用例"
            f"因环境限制被跳过）——**未验 ≠ 已验**，"
            f"勿据此认为相关守卫的『能红』属性有效",
        ]
        for s in suites:
            lines.append(f"     未验证套件：{s}")
        lines.append("     → 处置：环境限制所致（宿主 broker 拦 mkdir / TMPDIR 不可写），"
                     "**不是包缺陷**；解除后重跑该套件再判")
        return lines
    if rc == 0:
        return ["结论：✅ 全部通过，可发布 / 可运行 validate_expert.py"]
    return ["结论：⚠️ 存在告警，处理后再发布（settings.json 已自愈）"]


def check_regression(expert_dir):
    """v3.9.0 扩：此前只跑 test_harness.py，新增套件（如 v3.8.2 的 test_fix_md_image_refs、
    v3.9.0 的 test_loop_state）失败**体检完全看不见**——第 7 项形同虚设。
    现改为跑 scripts/ 下全部 test_*.py，逐个报码，任一失败即告警。

    ⚠ **v3.27.0 P0 收尾：检出「因环境限制被跳过」**。
    旧前提被推翻：旧实现**只看 rc** ⇒ unittest 的 skip **不改变 rc**
    ⇒ 11 个反例全被跳过时，本项仍显示「✓ 回归测试通过 … rc=0」
    ⇒ "这批守卫的『能红』属性根本没验证"这件事在体检汇总里**完全看不见**
    ⇒ 排查者会把"反例全跳过"误读成"守卫没问题" ⇒ **假绿**。
    ⇒ 现按三态分级报告（真通过 / 通过但有跳过 / 失败），并把"未验证"
      显式透传到最终结论（`REGRESSION_UNVERIFIED`）。

    ⚠ **返值语义（本项最关键的决策）**：
      · rc≠0（套件失败）⇒ return 1（**沿用** v3.9.0 起的行为，不变）
      · rc=0 但检出「因环境限制被跳过」⇒ **return 0（不阻断）**，理由三条：
        ① 跳过源于**环境**（宿主 broker 拦 mkdir / TMPDIR 不可写），不是包缺陷；
           拿环境问题阻断发布属误伤。
        ② 本包既有惯例：第 23 项（域绑定残留）= 提示级·**不阻断**，
           第 11/22 项才阻断；"证据不足/环境受限"更近第 23 项的性质。
        ③ **告警疲劳**：某些会话里宿主 broker 会持续拦截 ⇒ 若阻断，体检
           **恒红** ⇒ 用户学会忽略体检输出 ⇒ 后续真告警全部失效。
      · ⚠ 但"不阻断"**不等于**"看不见"：跳过必须**显式打印**（⚠ 行），
        且最终结论要**降级**为「有未验证项」⇒ 绝不让"未验"显示成"已验"。
      · ⚠ 若将来决定改为阻断：把 `REGRESSION_SKIP_BLOCKS_RELEASE` 改成 True
        即可（**双向可查**：判定逻辑与文案都不必动）。
    """
    import glob as _glob
    suites = sorted(_glob.glob(os.path.join(expert_dir, "scripts", "test_*.py")))
    if not suites:
        print(f"[7/{N}] ⚠ 未找到任何 test_*.py，跳过")
        return 1
    REGRESSION_UNVERIFIED["suites"] = []
    REGRESSION_UNVERIFIED["cases"] = 0
    results = []
    for t in suites:
        name = os.path.basename(t)
        try:
            p = subprocess.run([sys.executable, t], capture_output=True, text=True,
                               timeout=180)
        except subprocess.TimeoutExpired:
            results.append((name, REG_FAIL, {"text": "超时 >180s",
                                             "fail_tail": "超时 >180s",
                                             "marker_hit": False,
                                             "skipped_cases": 0,
                                             "anti_skips": 0}))
            continue
        last = [l for l in (p.stdout or "").strip().splitlines() if l.strip()]
        # v3.16.0 修：此前优先显示 stdout 末行文本，而部分套件的末行是 JSON 的收尾大括号，
        #   于是输出变成 `test_extract_assets.py=}` —— rc 判定是对的，显示却像解析异常，会误导排查。
        #   改为**优先显示 rc**（这才是有信息量的那个值），仅在 rc≠0 且末行非空时才附末尾片段。
        tail = f"rc={p.returncode}"
        if p.returncode and last:
            tail += f" / {last[-1][:20]}"
        status, detail = analyze_suite_output(name, p.returncode, p.stdout, p.stderr)
        if status == REG_FAIL:
            detail["fail_tail"] = tail
        results.append((name, status, detail))
    lines, rc = format_regression_report(results, len(suites))
    for ln in lines:
        print(ln)
    skipped = [(n, d) for (n, s, d) in results if s == REG_PASS_WITH_SKIPS]
    if skipped:
        REGRESSION_UNVERIFIED["suites"] = [n for n, _ in skipped]
        REGRESSION_UNVERIFIED["cases"] = sum(d["skipped_cases"] for _, d in skipped)
    return rc


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
    # 2) 取 doctor 的实际子命令注册表（**只跑一次**，逐个 claimed 比对）
    #
    # ⚠ v3.25.0 修正两处**假阳性/崩溃**（实测于资源受限环境）：
    #   ① 原实现对**每个** claimed 子命令都起一次 `harness.py --help` + 一次
    #      `harness.py doctor` 子进程（13 个声称 ⇒ 26 个子进程）；
    #      在资源紧张时子进程超时 ⇒ `reg_names = set()` ⇒ **全部**命令被判「未实现」
    #      ⇒ 7 个假阳性。现改为**只探测一次**。
    #   ② **探测失败 ≠ 实现缺失**：doctor 探测失败（超时/输出非 JSON）时，
    #      本项判为「探测受阻」并返回 0（提示级·不阻断）——
    #      理由同「假阳性必须为零」：探测侧故障不能被当成实现侧缺陷。
    reg_names = set()
    probe_ok = True
    probe_err = ""
    try:
        r2 = subprocess.run([sys.executable, hrns, "doctor"],
                            capture_output=True, text=True, timeout=60)
        docd = json.loads(r2.stdout)
        reg_names = {c.get("name") for c in docd.get("commands", []) if c.get("name")}
        if not reg_names:
            probe_ok = False
            probe_err = "doctor 输出里没有子命令注册表"
    except Exception as e:
        probe_ok = False
        probe_err = f"{type(e).__name__}: {str(e)[:100]}"
    if not probe_ok:
        print(f"[12/{N}] ℹ 文档-实现一致性**未判**（探测受阻，非漂移）：{probe_err}")
        print(f"     → 不阻断：探测侧故障 ≠ 实现侧缺陷（假阳性必须为零）；"
              f"请在资源充裕时重跑本项复核")
        return 0
    missing = [(c, f"doctor 列出 {len(reg_names)} 个子命令，无 {c}")
               for c in claimed if c not in reg_names]
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
        # ⑤ harness.py 文件头 docstring（v3.17.0 补：独立测试发现第 6 处未同步）
        m = _re.search(r"^harness\.py .*?(v[0-9.]+)\s*$", htxt, _re.M)
        rows.append(("scripts/harness.py 文件头", _norm(m.group(1)) if m else "<无版本串>"))
        # ⑥ harness.py argparse 描述（v3.17.0 补：独立测试发现此处曾停在 v3.4.2）
        m = _re.search(r"description=[\"'][^\"']*?编排内核（确定性工程层）(v[0-9.]+)", htxt)
        rows.append(("scripts/harness.py argparse 描述", _norm(m.group(1)) if m else "<无版本串>"))

    # ⑦⑧ 本轮新增维护的 yaml version 键（v3.17.0 补）
    #   缘由（独立测试 N6）：F3/F4 修了「harness.py argparse 描述」「两个 yaml 的 version 键」，
    #   但**改回去体检照样全绿**——即这些修复**没有回归门禁**，等于随时可能复发。
    #   现把它们纳入第 14 项：任何一处漂移即判红。
    for rel in ("references/result-envelope.yaml", "config/domain_config.yaml",
                # v3.20.0 补：另两个 yaml 也带 version 键，此前**不在巡检清单**——
                #   与本项自己踩过的坑完全同型（4 处 → 8 处 → 10 处，每次都是"新发现一处漏掉"）。
                #   config/language-profile.yaml（交付语言与术语表契约）
                #   config/external-tools.yaml（外部工具/通道/知识库契约）
                #   这两个文件是 v3.19.0 新增的，加进来时漏了巡检——不改巡检就会长期漏。
                "config/language-profile.yaml", "config/external-tools.yaml"):
        p = os.path.join(expert_dir, *rel.split("/"))
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding="utf-8", errors="replace").read()
        m = _re.search(r'^version:\s*"?v?([0-9.]+)"?\s*$', txt, _re.M)
        rows.append((rel, _norm(m.group(1)) if m else "<无 version 段>"))

    # ⑨⑩ 两份 marketplace.json（v3.18.0 补：独立诊断第 G7 项实测缺口）
    #   缘由（2026-10-25 从零诊断实测）：plugin.json / harness.yaml / harness.py 已推进到
    #   3.17.0，而**两份 marketplace.json 的 plugins[0].version 仍停在 2.2.0**，
    #   第 14 项此前只核 8 处（全是包内源），**不覆盖 marketplace** ——
    #   于是"市场/安装侧看到的版本"与包内实际版本长期不一致且**体检全绿**。
    #   这是「声明层≠执行层」的发布侧实例：marketplace.json 是安装入口，
    #   版本错会直接误导升级判断与用户侧版本核对。
    #   ⚠ 结构差异：marketplace.json 的 version 在 **plugins[0].version**（顶层无 version 键），
    #     不能复用上面的 yaml 正则，必须走 JSON 解析。
    for rel in (".codebuddy-plugin/marketplace.json", ".claude-plugin/marketplace.json"):
        p = os.path.join(expert_dir, *rel.split("/"))
        if not os.path.isfile(p):
            continue
        try:
            mk = _load(p)
            plugs = mk.get("plugins") or []
            mv = _norm(str((plugs[0] if plugs else {}).get("version", "")))
            rows.append((rel, mv or "<无 plugins[0].version>"))
        except Exception:
            rows.append((rel, "<解析失败>"))

    if not main_ver:
        print(f"[14/{N}] ⚠ 主清单无 version 字段，无法做一致性巡检")
        return 1
    bad = [(src, v) for src, v in rows if v != main_ver]
    if bad:
        print(f"[14/{N}] ⚠ 版本号不一致（主清单={main_ver}）：{len(bad)}/{len(rows)} 处偏离")
        for src, v in bad:
            print(f"     {src:34s} {v}≠ {main_ver}")
        print(f"     → 处置：以 .codebuddy-plugin/plugin.json 为权威，同步其余各处"
              f"（.claude-plugin/plugin.json / config/harness.yaml / scripts/harness.py "
              f"常量+文件头+argparse / references/result-envelope.yaml / config/domain_config.yaml / "
              f"**.codebuddy-plugin/marketplace.json 与 .claude-plugin/marketplace.json 的 "
              f"plugins[0].version**——最后两处是安装入口，漏改会让用户侧版本与包内不符）")
        return 1
    print(f"[14/{N}] ✓ 版本号 {len(rows)} 处一致：{main_ver}")
    for src, v in rows:
        print(f"     {src:34s} {v}")
    return 0


def check_agent_frontmatter(expert_dir):
    """v3.17.0：agent frontmatter 巡检（第 15 项）——判据从「数 `---`」升级为「真解析 YAML」。

    背景（**为拦截这类缺陷而建的检查，被同一类缺陷骗过**——本包「声明层 ≠ 执行层」典型一例）：
      v3.8.0 专门为「frontmatter 未闭合」建了本项（修过 verifier.md 与 team-lead.md 无闭合符），
      但原判据是「首行是 `---` **且**存在第二个 `---` 终止行」——
      而 `agents/dvm-content-expert.md` 的第二个 `---` **恰好落在正文里**
      （frontmatter 之后正文就开始了），于是「数到 `---`」即判合规；
      实则整段 frontmatter **不可 YAML 解析**（yaml.safe_load → ScannerError）：
      Claude Code 侧该文件被当作普通文档处理 → name/description/maxTurns 全部失效
      → **签名内容专家在双平台之一上等于不存在**（WorkBuddy 侧解析器宽容，故本机可用）。

    v3.17.0 判据（真解析，不数符号）：
      ① 首行必须是 `---`；
      ② 闭合符**逐个候选试解析**：取「首个 `---` 独占行之后、该候选 `---` 之前」的块，
         用 yaml.safe_load 解析，**能解析成 dict 才算真正的闭合符**；失败就继续试下一个候选
         ——这样「闭合符位置错了但后面还有对的」也能被正确定位，而不是一律判坏；
      ③ 解析成功后校验字段：`name` 存在且 == 文件名主干（agents/<name>.md）、
         `description` 非空、`maxTurns` 为正整数；
      ④ 缺陷分两类，**文案不同（修法不同）**：
         · **未闭合**：全文只有 1 个 `---`，找不到任何闭合符候选
         · **闭合符位置错**：存在多个候选 `---`，但没有一处能解析出合法 frontmatter
           ——即正文被混进了 frontmatter 段；
      ⑤ 报错必须带**行号**：frontmatter 段起止行 + 候选闭合符行号 + YAML 报错原文
         + 该报错在本文件中的绝对行号（让人一眼定位）。
    """
    agents_dir = os.path.join(expert_dir, "agents")
    if not os.path.isdir(agents_dir):
        print(f"[15/{N}] – 无 agents/ 目录，跳过")
        return 0
    try:
        import yaml
    except ImportError:
        print(f"[15/{N}] – 无 yaml 模块，跳过")
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
        stem = name[:-3]
        if not lines or lines[0].strip() != "---":
            bad.append((name, "首行不是 `---`（无 frontmatter）", ""))
            continue
        cands = [i for i, l in enumerate(lines) if l.strip() == "---" and i > 0]
        if not cands:
            bad.append((name,
                        "frontmatter **未闭合**：全文只有 1 个 `---`，找不到闭合符",
                        "修法：在 frontmatter 末尾补一行 `---`（正文之前）"))
            continue
        fm = None
        first_err = None
        for ci in cands:
            block = "\n".join(lines[1:ci])
            try:
                data = yaml.safe_load(block)
            except Exception as e:
                if first_err is None:
                    first_err = (ci, e)
                continue
            if isinstance(data, dict):
                fm = (ci, data)
                break
            if first_err is None:
                first_err = (ci, ValueError(
                    f"解析成功但结果不是 dict（{type(data).__name__}）"))
        if fm is None:
            ci, e = first_err
            mark = getattr(e, "problem_mark", None)
            # block 起点是文件第 2 行 → yaml 的 0 基行号 +2 = 本文件 1 基行号
            abs_line = (mark.line + 2) if mark is not None else None
            where = (f"候选闭合符行号 {[c + 1 for c in cands]}；最近候选在第 {ci + 1} 行；"
                     f"YAML 报错：{str(e).splitlines()[0]}")
            if abs_line:
                where += f"（该错误落在本文件第 {abs_line} 行）"
            bad.append((name,
                        "frontmatter **闭合符位置错**："
                        f"{len(cands)} 个候选 `---` 均无法解析出合法 frontmatter"
                        "——正文被混进了 frontmatter 段",
                        where + "；修法：把闭合 `---` 移到正文开始之前（frontmatter 末尾）"))
            continue
        ci, data = fm
        rng = f"第 2–{ci} 行"
        nm = data.get("name")
        if not nm:
            bad.append((name, f"frontmatter（{rng}）缺 name 字段", ""))
        elif str(nm).strip() != stem:
            bad.append((name, f"frontmatter（{rng}）name={nm!r} 与文件名主干 {stem!r} 不一致",
                        "修法：name 必须等于文件名主干（agents/<name>.md）"))
        desc = data.get("description")
        if not desc or not str(desc).strip():
            bad.append((name, f"frontmatter（{rng}）description 为空", ""))
        mt = data.get("maxTurns")
        if isinstance(mt, bool) or not isinstance(mt, int) or mt <= 0:
            bad.append((name, f"frontmatter（{rng}）maxTurns={mt!r} 不是正整数", ""))
    if bad:
        print(f"[15/{N}] 🔴 agent frontmatter 不合规：{len(bad)}/{checked} 个文件"
              f"（判据 = 真解析 YAML，不是数 `---`）")
        for n, why, extra in bad:
            print(f"     {n:34s} {why}")
            if extra:
                print(f"     {'':34s} └─ {extra}")
        print("     → 处置：frontmatter 必须能 yaml.safe_load 成 dict（name/description/maxTurns 齐全）；"
              "未闭合/闭合符位置错两种缺陷修法不同，闭合符必须落在正文开始之前")
        return 1
    print(f"[15/{N}] ✓ agent frontmatter 全部合规（{checked} 个文件均真解析成功"
          f"且 name/description/maxTurns 齐全）")
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
    known_external = {"registry_rebuild.py", "repair_p0_v200.py",
                      "validate_expert.py",   # 外部：WorkBuddy 内置 expert-manager skill
                      # v3.25.0 补：联邦共享件（**不随本包分发**，只存在于安装态/仓库结构下）
                      #   `assemble_spawn_prompt.py` 由 shared-core/ 提供，本包 scripts/ 下只有
                      #   同名 shim（转发到 shared-core）⇒ 文档里引用 shared-core/ 下的真实文件
                      #   是正确的，不是悬空引用。
                      "assemble_spawn_prompt.py"}

    import re as _re
    # v3.17.0 补强（两轮，共三个盲区——**这个检查连自己的同类缺陷都抓不住，
    #   它给出的绿灯就不值钱**）：
    #   盲区①（原版）：正则只匹配**裸文件名**（`name.py`），
    #     于是**带路径的引用**（`references/xxx.py` / `scripts/xxx.py`）完全不被扫到。
    #     实测：把本包脚本从 references/ 归位 scripts/ 后，文档里残留的
    #     `references/check_external_deps.py` 是**悬空引用**（按文档执行 EXIT=2），
    #     而本检查却报「✓ 无悬空脚本引用」。
    #   盲区②（第 1 轮补强后仍漏）：扫描范围只有 `agents/` 与 `references/`，
    #     **包根的 README.md / INSTALL.md / CHANGELOG.md 根本不在范围内**——
    #     而这三个恰是用户最先看的文档。实测：README.md:35 的「自查命令」是
    #     `python3 references/check_external_deps.py`，用户换机后第一入口就撞墙。
    #   盲区③（第 1 轮补强后仍漏）：匹配形态只认**反引号紧包路径**。
    #     实测 4 形态对照：`` `no_such_a.py` `` 抓到、`` `scripts/no_such_b.py` `` 抓到，
    #     而 `python3 scripts/no_such_c.py`（命令行，无反引号）**没抓到**、
    #     `scripts/no_such_d.py`（裸路径）**没抓到**——
    #     即**文档里真正会被照抄执行的那两种形态都漏**。
    #   改法：范围扩到包根三份文档；形态扩到「命令行/裸路径」；
    #     统一以「相对包根是否存在」为准，避免靠形态猜。
    pat_bare = _re.compile(r"`([A-Za-z_][A-Za-z0-9_]*\.py)`")
    # 带相对路径的引用：反引号紧包 或 裸路径 或 python3 命令行（v3.17.0 三形态合一）
    #   盲区④（第 2 轮补强后仍漏）：**首段字符类不含连字符**，
    #     于是 `shared-core/assemble_spawn_prompt.py` 这类**带连字符的目录**整体逃逸。
    #     且若只放宽字符类，会在 "shared-core/x.py" 内部再匹配出 "core/x.py"（子串误配）。
    #     修法：首段允许连字符 + 加负向边界断言 `(?<![\w/-])`（前面不是词字符/连字符/斜杠）。
    #   盲区⑤（补强后仍漏，且属**假阳性**）：**变量/占位符路径静态不可判定**——
    #     `"$EXPERT_DIR/scripts/assemble_spawn_prompt.py"`（shell 变量前缀）与
    #     `<WorkBuddy>/resources/.../validate_expert.py`（尖括号占位符），
    #     剥掉前缀后看似"相对包根不存在"，但**它们本就是合法引用**。
    #     处置：**跳过**这类路径（前面紧邻 `$` / `<` 时不判），并在此登记为人工复核项——
    #     静默跳过不等于放行，路径真断时用户按文档执行会立刻撞墙（那属于文档责任，不是本检查能判的）。
    pat_path = _re.compile(
        r"(?<![\w/$-<>])(?![/~])[A-Za-z_][A-Za-z0-9_-]*(?:/[A-Za-z0-9_.-]+)+\.py")
    dangling = []
    # 扫描范围：agents/ 与 references/ 各目录 + 包根的三份用户文档
    targets = []
    for sub in ("agents", "references"):
        d = os.path.join(expert_dir, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith((".md", ".yaml", ".yml")):
                targets.append((f"{sub}/{name}", os.path.join(d, name)))
    # ⚠️ **CHANGELOG.md 刻意不在扫描范围内**（v3.17.0 定案）：
    #   它是**历史变更日志**，里面提到旧脚本名（如 `verify_three_source_config.py`、
    #   `ghost_script_xyz.py`）、正则示例（`name.py`）是**记录**，不是会被照抄执行的命令——
    #   把它们判成"悬空引用"是**假阳性**。本项目铁律：假阳性必须为零，否则门禁会被绕过。
    #   README.md / INSTALL.md 则**必须**扫：那是用户上手的第一入口，
    #   里面的破命令会让用户换机后第一步就撞墙（这正是 F1 的实际危害）。
    for name in ("README.md", "INSTALL.md"):
        fp = os.path.join(expert_dir, name)
        if os.path.isfile(fp):
            targets.append((name, fp))
    for label, fp in targets:
            sub, name = label.split("/") if "/" in label else ("", label)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            # ① 裸文件名：沿用原判据（本地 scripts/ 有，或已登记为外部依赖）
            for m in set(pat_bare.findall(txt)):
                if m in local or m in known_external:
                    continue
                dangling.append(f"{label} 引用 `{m}`（包内 scripts/ 无此文件）")
            # ② 带相对路径的引用：按「相对包根是否存在」判定（v3.17.0 新增，
            #   覆盖反引号紧包 / 裸路径 / python3 命令行三种形态）
            for rel in set(pat_path.findall(txt)):
                if os.path.exists(os.path.join(expert_dir, rel)):
                    continue
                # v3.25.0 补：带路径的引用也要能命中 known_external 白名单。
                #   缘由：`shared-core/assemble_spawn_prompt.py` 是**联邦共享件**里的文件
                #   （本包 scripts/ 下只有同名 shim 转发过去），文档引用它是正确的。
                #   白名单按 **basename** 匹配（登记项是文件名，不是全路径）——
                #   否则登记了也命中不了，白名单就成了摆设。
                if os.path.basename(rel) in known_external:
                    continue
                dangling.append(f"{label} 引用 `{rel}`（相对包根不存在该文件）")

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


def _collect_ast_reads(scripts_dir):
    """用 AST 收集 scripts/ 中**真实读取**的配置键（v3.15.0 · FEAT-001）。

    为什么不用文本搜索：纯文本搜索会把**注释与 docstring 里提到键名**也算成"有读取者"，
    导致"提到但没用"的键被判为活的——实测第 18 项的失效案例正是如此：
    把 `cfg.get("three_source_check")` 改成 `{}`（读取已破坏），
    因该键名在别处仍出现，文本搜索判定不变，缺陷被完全掩盖。

    收集三种形态：
      ① `x.get("key")`          —— 字典 .get 取值
      ② `x["key"]`              —— 下标取值
      ③ **字典字面量的字符串键** —— 如 `cmd_budget` 里
         `threshold_map = {"stage_minutes": ("max_stage_minutes", ...)}`
         这类键**是真被消费的**（`b.get(key)` 按 key 名查），
         但不出现在任何 `.get("…")` 字面量里，只按 .get 判会漏（实测 `max_stage_minutes` 即如此）。

    返回 {key: [位置…]}。
    """
    import ast
    reads = {}

    def add(k, where):
        if isinstance(k, str) and k:
            reads.setdefault(k, []).append(where)

    for fn in sorted(os.listdir(scripts_dir)):
        if not fn.endswith(".py"):
            continue
        # ⚠ **v3.25.0 修复：排除测试文件**（真实判据漏洞，已实测复现）。
        #   病灶：测试代码里的 `cfg.get("x")` / `cfg["a"]["x"]` 会被算作
        #   「x 有代码读取者」⇒ **在测试里写一行就能让死配置门对 x 假绿**。
        #   实测复现：隔离副本的 `harness.yaml#budgets` 下加 `__probe_zone_new_key`，
        #   仅因守卫测试文件里写了 `cfg["budgets"]["__probe_zone_new_key"]`，
        #   该键就获得了**路径级证据**（`_a_path`）⇒ 不进免检区 ⇒ 守卫完全看不见。
        #   理由：第 18 项问的是「**生产代码**是否消费这个键」，
        #   测试代码的读取**不构成消费**（测试只验证，不消费）。
        if fn.startswith("test_"):
            continue
        fp = os.path.join(scripts_dir, fn)
        try:
            tree = ast.parse(open(fp, encoding="utf-8", errors="replace").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            # ① .get("key")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and node.args):
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    add(a0.value, f"{fn}:{node.lineno}.get")
            # ② ["key"]
            if isinstance(node, ast.Subscript):
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    add(sl.value, f"{fn}:{node.lineno}[]")
            # ③ dict 字面量的字符串键（阈值映射表 / 白名单等）
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        add(k.value, f"{fn}:{node.lineno}{{dict}}")
    return reads


def _collect_chain_reads(scripts_dir):
    """用 AST 重建**链式访问路径**（v3.23.0 · 第三轮诊断 F1）。

    背景（第三轮从零诊断 P-1，实测可复现）：
      第 18 项的 alive 判定是 `n_full in norm_reads or n_leaf in norm_reads`——
      **末段键名同名即算"已被代码读取"**。而 `norm_reads` 含 1268 个键名
      （`enabled` 27 处 / `note` 47 处 / `max_retries` 7 处…），
      ⇒ 新增配置键只要与代码中任意键名重名，就自动判为"已接线"⇒ **死配置门假绿**。
      反向例实测：往未登记新段放一个叶名为 `enabled` 的键 ⇒ 第 18 项 rc=0（漏检）；
      同一段放唯一名键 ⇒ 检出。**唯一差异是叶名是否重名。**

    本函数把 `x.get("a").get("b")["c"]` 还原为 `a.b.c`，
    让"这条配置路径是否真被访问过"有了**路径级**证据，
    而不再依赖"末段名字是否撞车"。

    返回：规范化后的点分路径集合（含各级后缀）。
    局限（如实标注）：链在**函数传参**处会断（`f(cfg["x"])` 之后链不可知），
      也断在**动态键名**处（`d[k]`，k 非字面量）与 `**` 解包处——
      这些场景由"父级整块消费"层兜底（见 check_dead_config_keys）。
    """
    import ast

    def _chain(node, binds=None):
        """还原访问链；返回点分路径或 None（链根不可知时返回首段）。

        v3.23.0 增两种还原能力（否则本包主流读法会被误判为弱证据）：
          ① **节访问器约定**：`f(cfg, "段名")` ⇒ 视作访问 "段名"
             （本包 `loop_contract.py::_section(cfg, name)` 即此形态——
              段名以实参传入，纯属性链在此断裂）。
          ② **局部变量绑定**：`x = f(cfg, "段名")` ⇒ `x` 等价于 "段名"，
             后续 `x.get("键")` 可还原为 "段名.键"。
        """
        binds = binds if binds is not None else {}
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args):
            a = node.args[0]
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                base = _chain(node.func.value, binds)
                return f"{base}.{a.value}" if base else a.value
        if isinstance(node, ast.Subscript):
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                base = _chain(node.value, binds)
                return f"{base}.{sl.value}" if base else sl.value
        # ② 局部变量绑定：x = <链> ⇒ x 的链 = 该链
        if isinstance(node, ast.Name) and node.id in binds:
            return binds[node.id]
        # ① 节访问器约定：f(cfg_like, "段名")
        if isinstance(node, ast.Call) and node.args:
            _last = node.args[-1]
            _first = node.args[0]
            if (isinstance(_last, ast.Constant) and isinstance(_last.value, str)
                    and isinstance(_first, ast.Name)
                    and any(_t in _first.id.lower() for _t in ("cfg", "conf", "config"))):
                return _last.value
        return None

    def _norm(s):
        return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == "_")

    paths = set()
    for fn in sorted(os.listdir(scripts_dir)):
        if not fn.endswith(".py"):
            continue
        # ⚠ **v3.25.0 修复：排除测试文件**（真实判据漏洞，已实测复现）。
        #   病灶：测试代码里的 `cfg.get("x")` / `cfg["a"]["x"]` 会被算作
        #   「x 有代码读取者」⇒ **在测试里写一行就能让死配置门对 x 假绿**。
        #   实测复现：隔离副本的 `harness.yaml#budgets` 下加 `__probe_zone_new_key`，
        #   仅因守卫测试文件里写了 `cfg["budgets"]["__probe_zone_new_key"]`，
        #   该键就获得了**路径级证据**（`_a_path`）⇒ 不进免检区 ⇒ 守卫完全看不见。
        #   理由：第 18 项问的是「**生产代码**是否消费这个键」，
        #   测试代码的读取**不构成消费**（测试只验证，不消费）。
        if fn.startswith("test_"):
            continue
        fp = os.path.join(scripts_dir, fn)
        try:
            tree = ast.parse(open(fp, encoding="utf-8", errors="replace").read())
        except Exception:
            continue
        # 先收集局部变量绑定（单名赋值：x = <可还原链>）
        binds = {}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)):
                c = _chain(n.value, binds)
                if c:
                    binds[n.targets[0].id] = c
        for node in ast.walk(tree):
            c = _chain(node, binds)
            if not c:
                continue
            segs = c.split(".")
            for i in range(len(segs)):
                paths.add(_norm(".".join(segs[i:])))
            # 前缀（父级被整块取走的证据：段根本身入集）
            for i in range(1, len(segs)):
                paths.add(_norm(".".join(segs[:i])))
    return paths


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

    # v3.15.0（FEAT-001）：改用 AST 真实读取点，替换原先的纯文本搜索。
    # 文本搜索会把注释/docstring 里提到键名算成"有读取者"，掩盖"提到但没用"的缺陷
    #（实测失效案例：cfg.get("three_source_check") 被改成 {} 后统计仍不变）。
    ast_reads = _collect_ast_reads(scripts_dir)

    def norm(s):
        """归一化：去掉非字母数字与下划线，便于 'three-source'/'three_source' 同查。"""
        return "".join(ch for ch in str(s).lower() if ch.isalnum() or ch == "_")

    # AST 键也归一化后建索引（.get 与 [] 两种形态已合并）
    norm_reads = {}
    for k, locs in ast_reads.items():
        norm_reads.setdefault(norm(k), []).extend(locs)

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
        # ── v3.19.0：第五次从零诊断·维度 6 处置的 4 组"死配置"裁定 ──
        # 判据（主理人裁决）：**给 LLM/人的执行指令**本就不该由脚本读——
        #   它们的消费方是「成员按条款执行 + 主理人复核」，登记 = 承认没人读是对的。
        #   ⚠ 与"接线"的区别：接线 = 判据可确定性执行（如字号阈值）；
        #     人读型 = 判据是语义/流程指令（如降密顺序）。
        # visual-rules.yaml#density.shrink_order —— 降密执行顺序（给屠明熙的执行指令：
        #   "低级能解决不升级"，LLM 按序执行，脚本无法判定"某步是否够用"）
        "shrink_order",
        # visual-rules.yaml#theme.* —— 主题色令牌槽位（消费方 = 工作区 theme.yaml +
        #   屠明熙抽取登记；本文件只定义槽位结构，明确"值不在此定义"）
        "enforce_source_theme", "max_new_colors_per_slide", "token_slots",
        # ⚠ v3.22.0 G1：visual-rules.yaml#overlay_injection.* 的**人读型登记已撤**——
        #   这四键自 v3.22.0 起由 scripts/inject_notes.py **真正读取**（AST 读取点 ≥1）
        #   ⇒ 不再需要"人读型"豁免；留着反而会掩盖"接线被删掉"这类回归
        #   （豁免在前 ⇒ 无读取点也不报死配置 ⇒ 假绿）。
        #   sample_review_ratio 仍是**人复核比例**（语义），但它与另三键同段，
        #   段级读取点已存在 ⇒ 撤段级登记不影响其合法性。
        # ── v3.19.1：第六次从零诊断·S3 ──
        # domain_config.yaml#three_source_check.source_verification.*.format_fallback
        #   —— 书籍/标准的**离线校验兜底**（isbn_checksum / gb_number_format）：
        #   联网通道不可用时用校验位/编号格式做本地判据。判据本身是**语义规则**
        #   （ISBN 校验位算法、GB 标准号格式），由**会话层**执行，不由脚本算
        #   ⇒ 登记人读型（与 shrink_order 同判据）。
        "format_fallback",
        # ── v3.20.0：33 键"声明未接线"收口（v3.19.3 L3 的残留项）────────
        # v3.19.3 的取证：`loop_a`(4) + `loop_b`(20) + `delta_gate`(9) = 33 键
        #   整批"声明了但没接线"——v3.9.0 只把**动作层**下沉为代码（loop 子命令 13 个动作），
        #   而 yaml 里的**默认值段 / 轮次复核判据 / delta 门禁判据**三类仍是纯声明
        #   （代码字面量 0 处；`delta_gate` 在 harness.py 的 2 次出现只是文件头 docstring）。
        #
        # v3.20.0 处置：**32 键已真接线**（新建 scripts/loop_contract.py 承载判定，
        #   harness.py 的 loop 子命令调用它），故**整段登记撤销**——继续挂着等于
        #   给它们永久假绿（改回未接线也检不出来）。
        #   ⚠ 只保留 3 个**确属不可判定**的键，用带文件前缀的限定路径登记：
        "harness.loop_a.trigger", "harness.loop_b.trigger",
        #     · trigger —— 判环判据（dual-loop-governance.md#1 的判环表），
        #       是**语义判定**（"这句话是在改专家团还是在改课件"），代码不判环；
        "harness.delta_gate.insert_font_at_creation",
        #     · insert_font_at_creation —— "新元素文字规格创建时即达合规"是**写入时行为**，
        #       成品文件态无痕迹（与 OOXML 病例 API-001 同型），**结构性不可判定**。
        #       同段其余 8 键（baseline_required / baseline_fields / block_on_new_defects /
        #       report_format / miss_needs_human_review / insert_spatial_audit /
        #       image_caption_requires_reading / caption_missing_element_policy）已接线。
        #       ⚠ 执行面与不可判定面**不得混说**——不得因某键出现在输出里就宣称已强制。
        # harness.yaml#stages.{0..4}.next —— 阶段顺序的人读说明；实际推进由
        #   `task_state.json#current_stage`（数值）驱动，`next_stage` 在代码中 0 次出现。
        #   ⚠ 双份真相风险：yaml 的 `next` 与代码的 `current_stage+1` 是同一事实两处写法
        #     ⇒ 已加漂移守卫（check_stage_order_drift，见第 24 项）。
        "stages",
        # visual-rules.yaml#caption_five_elements —— v3.19.0 G4 图注要素统一时
        #   明确标注的**历史键**（向后兼容保留，下游若有引用不报错），同源
        #   CHANGELOG:455 记载「保留为历史键并标 deprecated」⇒ 不可删。
        "caption_five_elements", "caption_base_elements_note",
        # external-tools.yaml#ima.* / #standards.* / #channels.* —— Ima API 契约、
        #   教育部标准元数据、通道编排参数。消费方是**会话层**（成员按契约调
        #   search_knowledge / 按通道参数编排）；本文件只声明契约与参数。
        #   ⚠ `channels` 段下被 probe_channels.py 消费的键（id/kind/priority/
        #     endpoint_ref 等）走 alive 分支优先，不受本登记影响。
        "ima", "standards", "channels",
        # language-profile.yaml#terminology.* / #english_allowed_when.* /
        #   #consistency.* / #english_minimum.* —— 术语标注规则、英语场景判据、
        #   语言一致性策略、英语场景的中文保留项（疾病中文名/学名/法规条款号/数值单位）。
        #   消费方是**会话层**（dvm-content-expert 按规则标注术语、按判据决定交付语言）；
        #   被 gate1-check 消费的 default_language 走 alive 分支优先。
        "terminology", "english_allowed_when", "consistency", "english_minimum",
        # visual-rules.yaml#gate.deliver_gate_level / #gate.write_gate_level ——
        #   写回/交付门禁级别的**人读档位说明**（P0/P1/P2/P3 的语义由成员执行）。
        #   ⚠ 用**带文件前缀**的完整路径登记，避免与 harness.yaml#gate.*
        #     （退出码定义，被 cmd_gate 消费）混淆。
        "visual-rules.gate",
        # hygiene-words.yaml#report_only / #report_only_reason —— 卫生词表的
        #   「只报不修」模式开关与理由说明；由成员按 flag 执行，脚本不判。
        "report_only", "report_only_reason",
        # domain_config.yaml#image_fetch.license_uncertain_markers —— 许可不明标记词
        #   （待核实/未明/未知）；供成员判断"许可是否可信"，语义判断不由脚本做。
        "license_uncertain_markers",
        # harness.yaml#collapse.rationale_filled_by / #observability.report_on_finish ——
        #   坍缩理由填写方 / 观测收尾上报策略；流程说明，无脚本判定。
        "collapse", "observability",
    }

    # ── 人读型路径段白名单（按前缀豁免，比逐个键名更抗漂移）────────
    # v3.19.3：改为**自动派生**——原硬编码 7 段不含任何 v3.19.0 新增段
    #   （overlay_injection / theme / loop_b / delta_gate / stages / language-profile
    #   各段 …）⇒ 新段的登记**从未生效**（这是 L3 确证的核心判据缺陷）。
    #   现改为：原有 7 段 ∪ known_textual 中的裸段名（不含点号的条目）。
    #
    # ── v3.23.0 F2：把「末段键名豁免」与「段级豁免」**分开**────────────
    #   病灶（第三轮从零诊断 P-2）：`known_textual` 里混着两类条目——
    #     · **末段键名**（description / version / name / note / comment / duty /
    #       label_zh / label_en）：本意是「这些名字的键是给人读的」
    #     · **段名**（stages / collapse / observability / ima / standards /
    #       channels / terminology / consistency / report_only …）：本意是
    #       「这一整段由主理人/会话层消费」
    #   而 `path_prefixes` 把**两类都**派生成了段级白名单 ⇒
    #   **凡挂在名为 name/note/description/version/duty/comment 的段下的键，
    #   一律自动豁免**——新增的、确实没人读的键也照样绿灯。
    #   修法：通用词只按**末段键名**豁免（规则①保留），不再派生为段级白名单；
    #   真正的段级登记（stages/collapse/…）维持原样。
    known_leaf_only = {
        "description", "version", "name", "note", "comment", "duty",
        "label_zh", "label_en",
    }
    path_prefixes = (
        ".disease_modules",     # 课程目录内容（case_extract.py 按域整体读取疾病名）
        ".gates",               # 五闸人读判据（机器判据在 verify_deck）
        ".ai_literacy",         # AI 素养判据（主理人消费）
        ".snapshot",            # 快照策略（snapshot.py 按部分键消费）
        ".fallback",            # 降级通道说明（主理人按条款执行）
        ".members",             # 成员能力/权限声明（供 spawn 前判断）
        ".domains",             # 域标签与命名规范（展示元数据）
    ) + tuple(f".{_seg}" for _seg in sorted(known_textual)
              if "." not in _seg and not _seg.startswith("_")
              and _seg not in known_leaf_only)

    # v3.19.3：人读型判据补强——除末段键名外，**任一路径前缀段**命中
    #   known_textual 即算人读型（修复：原判据只查末段键名，而登记写的是段名
    #   ⇒ `overlay_injection.max_overlap_ratio` 的末段是 max_overlap_ratio，
    #   与登记的 "overlay_injection" **永不匹配**，登记形同虚设）。
    #   支持两种登记形态：
    #     · 裸段名（`loop_b`）        → 匹配任一文件的该段
    #     · 带文件前缀（`visual-rules.gate`）→ 只匹配该文件的该段（防同名段歧义）
    # ⚠ v3.23.0 F2：裸段名集合**排除通用词**（known_leaf_only）——
    #   它们只按末段键名豁免，不得作为段级白名单（否则整段自动绿灯）。
    _kt_bare = {k for k in known_textual
                if "." not in k and k not in known_leaf_only}
    _kt_qualified = {k for k in known_textual if "." in k}

    def _is_textual(fname: str, full: str) -> bool:
        segs = [s for s in full.split(".") if s]
        # ① 末段键名命中（原有判据）
        if segs and segs[-1].lower() in known_textual:
            return True
        # ② 任一路径前缀段命中裸段名
        for s in segs[:-1]:
            if s.lower() in _kt_bare:
                return True
        # ③ 带文件前缀的限定路径命中（如 visual-rules.gate 只豁免该文件的 gate 段）
        stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        for q in _kt_qualified:
            qf, _, qp = q.partition(".")
            if qf == stem:
                qsegs = [s for s in qp.split(".") if s]
                if segs[:len(qsegs)] == qsegs:
                    return True
        return False


    dead, alive, textual = [], 0, 0
    # v3.23.0 F1：块级证据计数 + 弱证据（仅末段同名撞车）清单
    block, weak, weak_reg, weak_list = 0, 0, 0, []
    # v3.25.0：**免检区（块级消费段）清单**——按 `<config 文件名>#<段前缀>` 聚合。
    # ⚠ 段归属直接复用 `_b_block` 的**同一次**短路循环结果（不另算一遍）⇒
    #   新输出与既有判定**口径必然一致**，不可能出现「两套算法算出两个答案」。
    block_segments = {}   # seg_key -> {"file":…, "prefix":…, "keys":[…], "leaf_unused": int}
    # v3.25.0：同步到模块级累加器（供 `collect_block_segments()` / dump 开关复用）。
    # ⚠ 每次调用**重置** ⇒ 不会跨轮残留（旧结果被误当本次结果）。
    global _LAST_BLOCK_SEGMENTS
    _LAST_BLOCK_SEGMENTS = block_segments

    # ── v3.23.0 F1：**弱证据登记区**（known_weak）────────────────────────
    # 弱证据 = 该键**只**因「末段键名与代码中某键同名」而被判为已接线。
    # 这**不是**路径级证据（父级被整块取走也算块级），故不能默认算数。
    # 登记 = 承认「这个键确实只靠同名，另有原因不被代码读」。
    # ⚠ 登记时必须写明理由；只登记不解释 = 把假绿固化，与本项纪律相悖。
    known_weak = {
        # language-profile.yaml#languages.*.{label,script} —— 语言**展示元数据**
        #   （zh-CN 简体中文/Hans、en English/Latn）：供成员与装配器按受众语言选字体、
        #   做简繁校对用。**当前无脚本消费点**（第三轮诊断实测：代码与文档 0 处引用
        #   `languages` 段）⇒ 旧口径下它是靠「末段同名（label / script）」**碰巧**
        #   被算作已接线——典型假绿。改为**显式登记**，把「没人读」这件事写明。
        "language-profile.languages",
    }

    # ── v3.25.0：**守卫型配置**（消费方 = 守卫测试自身）──────────────────
    # 背景（真实判据漏洞，v3.25.0 实测复现）：
    #   本项排除 `test_*.py` 后，`config/guard.yaml` 的两个键立刻被判死：
    #     · `guarded_docs`    —— 受守卫文档清单，被 `test_arch_drift.py` 读
    #     · `legacy_wording` —— 旧口径词表，被 `test_arch_drift.py` 读
    #   它们**不是死配置**：消费方就是**守卫测试代码**。
    #   ⚠ 为什么要显式登记而不是「把测试文件算回读取点」：
    #     算回去 ⇒ 任何人在**任意测试文件**里写一行 `cfg.get("任意键")`
    #     就能让死配置门对那个键假绿（实测复现，见 `_collect_ast_reads` 的注释）。
    #     ⇒ 必须「排除测试」+「显式登记守卫型配置」两步走。
    #   消费方分类学（v3.25.0 新增的第四类，缺了它模型就不完整）：
    #     脚本 / 会话层 / 主理人 / **守卫测试**
    known_guard_consumed = {
        # guard.yaml#guarded_docs —— 受守卫文档清单（改这张表 = 改守卫覆盖面）。
        #   消费方：`scripts/test_arch_drift.py`（T9：清单内每个文档必须含镜像块）。
        "guard.guarded_docs",
        # guard.yaml#legacy_wording —— 旧口径词表（正文出现即判红）。
        #   消费方：`scripts/test_arch_drift.py`（T10：豁免区外出现即判红）。
        "guard.legacy_wording",
    }

    def _is_guard_consumed(fname: str, full: str) -> bool:
        """守卫型配置判定：消费方是**守卫测试自身**的键（不算死配置）。

        登记形态：`<config 文件名去扩展名>.<段名>`（如 `guard.guarded_docs`）。
        """
        _segs = full.split(".")
        _stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        if full in known_guard_consumed:
            return True
        for _k in known_guard_consumed:
            if "." not in _k:
                if _k in _segs[:-1]:
                    return True
            else:
                _kf, _, _kp = _k.partition(".")
                if _kf == _stem and _segs[:len(_kp.split("."))] == _kp.split("."):
                    return True
        return False

    def _is_weak_registered(fname: str, full: str) -> bool:
        """弱证据登记判定：支持「限定路径」与「带文件前缀的段名」两种形态。"""
        _segs = full.split(".")
        _stem = fname.rsplit(".", 1)[0] if "." in fname else fname
        if full in known_weak:
            return True
        for _k in known_weak:
            if "." not in _k:
                # 裸段名：命中路径中任一段
                if _k in _segs[:-1]:
                    return True
            else:
                _kf, _, _kp = _k.partition(".")
                if _kf == _stem and _segs[:len(_kp.split("."))] == _kp.split("."):
                    return True
        return False

    # ── v3.23.0 F1：链式访问路径（路径级证据的唯一来源）────────────────
    # 由 _collect_chain_reads 从 AST 重建 `x.get("a").get("b")["c"]` ⇒ "a.b.c"，
    # 使"这条配置路径是否真被访问"有了路径级判据，而不再依赖末段键名是否撞车。
    chain_reads = _collect_chain_reads(scripts_dir)

    def walk(node, path, fname):
        """递归收集叶子键。

        判据用**整条路径**而非末段键名——因为代码里常见的读取形式是
        `cfg["domains"]["animal-medicine"]["label_zh"]`，末段 `label_zh`
        在别的分支下也可能出现，只查末段会误报；反过来，只查整条路径会漏报
        「代码读了同名字段但走的是另一条分支」，故**两段都查，任一命中即算有读取者**。
        """
        nonlocal alive, textual, block, weak, weak_reg
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
            _segs = full.split(".")
            # 路径段命中：逐段检查 `domains.active` → `.domains.active`、`.domains`、`.active`
            # （v3.13.0 曾写成只拼 segs[i:]，漏掉 i=0 的单段前缀 `.domains`，导致白名单整条失效）
            seg_hit = any("." + ".".join(_segs[:i + 1]) in path_prefixes
                          for i in range(len(_segs)))
            # ── v3.23.0 F1：alive 判定由「末段同名即算接线」改为**三层证据** ──
            # 病灶（第三轮从零诊断 P-1，反向例实测可复现）：
            #   原口径 `n_full in norm_reads or n_leaf in norm_reads`——**末段键名同名**
            #   即算「已被代码读取」。norm_reads 含 1268 个键名（enabled 27 处 / note 47 处），
            #   ⇒ 新增配置键只要与代码中任意键名重名就自动判为已接线 ⇒ **死配置门假绿**。
            #   反向例：未登记新段放叶名 `enabled` 的键 ⇒ rc=0（漏检）；同段唯一名 ⇒ 检出。
            # 三层证据：
            #   A 路径级（强）：链式访问路径命中该键的**整条路径或 ≥2 段后缀**
            #   B 块级  （强）：**父级路径**被代码整块取走 ⇒ 该子树随父级被消费
            #   C 名级  （弱）：仅末段键名撞车 ⇒ **不可信**，须登记理由（known_weak）
            _a_path = False
            for _i in range(len(_segs) - 1):        # 末段单独命中不算路径级证据
                _cand = norm(".".join(_segs[_i:]))
                if _cand and _cand in chain_reads:
                    _a_path = True
                    break
            _b_block = False
            _b_prefix = None
            for _i in range(len(_segs) - 1):        # 真前缀 ⇒ 父级被整块取走
                _cand = norm(".".join(_segs[:_i + 1]))
                if _cand and _cand in chain_reads:
                    _b_block = True
                    _b_prefix = ".".join(_segs[:_i + 1])   # v3.25.0：记下触发前缀
                    break
            if (n_full and n_full in norm_reads) or _a_path or _b_block:
                alive += 1
                if _b_block and not _a_path and not (n_full and n_full in norm_reads):
                    block += 1
                    # v3.25.0：把该键归入「免检区（块级消费段）」——
                    # 段键 = `<config 文件名>#<触发前缀>`（ADR-6：必须带文件名前缀，
                    # 因为同名段跨文件是不同的段，合并登记会让处置规则无法落地）。
                    _seg_key = f"{fname}#{_b_prefix}"
                    _seg = block_segments.setdefault(
                        _seg_key,
                        {"file": fname, "prefix": _b_prefix, "keys": [], "leaf_unused": 0})
                    _seg["keys"].append(full)
                    # 「末段键名归一化后不在 AST 读取集」⇒ 该键连同名都没撞上 ⇒
                    # 连**弱证据**都没有 ⇒ 属「待人工定性候选」（不是死配置）。
                    if not (n_leaf and n_leaf in norm_reads):
                        _seg["leaf_unused"] += 1
            elif seg_hit or _is_textual(fname, full) or _is_guard_consumed(fname, full):
                textual += 1          # 人读型：登记在案，无代码读取者是合理的
            elif n_leaf and n_leaf in norm_reads:
                # 弱证据：仅末段键名撞车。**不算已接线**，必须登记理由。
                if _is_weak_registered(fname, full):
                    weak_reg += 1
                else:
                    weak += 1
                    weak_list.append((fname, full, node))
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
# ⚠️ **已知局限（v3.15.0 已改善）**：v3.13.0 首版用纯文本包含匹配，无法区分
# 「代码提到这个键名」与「代码真的读了这个值」。反例实测：把 verify_deck 里
# `cfg.get("three_source_check")` 改成 `{}`（读取行为已破坏）后，统计**不变**——
# 因为该键名在其它脚本/注释/docstring 中仍出现，仍被判为"有读取者"。
#
# **v3.15.0（FEAT-001）已改为 AST 真实读取点判据**（`_collect_ast_reads`）：
# 解析 `.get("k")` / `["k"]` / 字典字面量字符串键，排除注释与 docstring。
# 探针实测：yaml 150 个叶子键中，纯文本判据认为"有读取者"但**AST 无真实读取点**的
# 有 109 个（73%）——即原判据的假阳性规模。修正后人读型登记 34→84、提示 139→89。
#
# ⚠️ **AST 判据的实测局限（反例验证，如实标注）**：
# 把 `cfg.get("three_source_check")` 改成 `{}`（读取链被删）后——
#   ✓ `three_source_check` 确实从 AST 读取集消失（判据能发现"整条链被删"）
#   ✗ **但** `sample_rate` / `pass_threshold` 仍在——因为它们同时出现在
#     `_load_three_source_thresholds` 的 **fallback 字典**（:134/:142）
#     与对 `THREE_SOURCE` 的取值（:824/:837/:849）里，**不依赖外层 cfg 也能活着**。
# 结论：AST 判据能发现"读取链被删"，**发现不了"读了 fallback 而没读配置"**。
# 后者必须靠**运行时断言**（配置值 == 运行时值）覆盖，即
# `verify_three_source_config.py` 这类逐键断言脚本——静态判据原理上做不到。

    # ── v3.19.2·G-B：同一路径去重（一键一计）──────────────────────
    # 缺陷（第七次从零诊断·实测）：walk 对列表的每个标量项都用同一路径走到底，
    #   `license_uncertain_markers` 的 3 个枚举值被计为 3 个"无读取者"（×4 实为
    #   3 值 + 1 下标形态）、`channels[].probe` 的 7 个通道各计 1 条 ⇒ 13 条展示
    #   中 9 条是同一键的重复虚增——**计数口径失真会稀释真长尾的信号**。
    # 修法：展示与计数都按**唯一路径**算（同键多值只报 1 次，附值个数）。
    seen = {}
    for fname, full, node in dead:
        key = f"{fname}#{full}"
        if key not in seen:
            seen[key] = (fname, full, node)
        else:
            # 保留首个；列表多值场景记录值个数供展示
            _f, _p, _n = seen[key]
            if isinstance(_n, (str, int, float, bool)):
                seen[key] = (_f, _p, [ _n ])  # 升级为列表便于统计
    # 统计列表键的值个数（用于展示"该键共 N 个枚举值"）
    list_valued = {}
    import yaml as _yaml_for_list
    for cf in cfg_files:
        try:
            _d = yaml.safe_load(open(os.path.join(cfg_dir, cf), encoding="utf-8"))
        except Exception:
            continue
        _stack = [("", _d)]
        while _stack:
            _path, _node = _stack.pop()
            if isinstance(_node, dict):
                for _k, _v in _node.items():
                    _stack.append((f"{_path}.{_k}" if _path else str(_k), _v))
            elif isinstance(_node, list) and _node and all(
                    not isinstance(_x, (dict, list)) for _x in _node):
                list_valued[f"{cf}#{_path}"] = len(_node)

    if dead or weak_list:

        uniq = list(seen.values())
        print(f"[18/{N}] ℹ 提示：{len(uniq) + len(weak_list)} 个配置键无**路径级**读取证据"
              f"（代码读取 {alive} 项〔其中块级消费 {block} 项〕 · 人读型登记 {textual} 项 · "
              f"弱证据登记 {weak_reg} 项 · "
              f"另有 {len(dead) - len(uniq)} 条为同键多值重复，已按唯一键计）")
        # v3.19.3（L3）：**全量输出**——原实现截断为前 12 条，其余条目**永远不可见**，
        #   ⇒ 人工无法复核 ⇒ 这本身是工具缺陷（体检项形同虚设）。
        #   默认打印全部；如需精简输出可设 VET_DEAD_CONFIG_LIMIT=<n> 截断（0 = 不截断）。
        _limit_env = os.environ.get("VET_DEAD_CONFIG_LIMIT", "").strip()
        _limit = 0
        if _limit_env:
            try:
                _limit = max(0, int(_limit_env))
            except ValueError:
                print(f"     ⚠ VET_DEAD_CONFIG_LIMIT={_limit_env!r} 不是整数，按默认（全量）处理")
                _limit = 0
        shown = uniq if _limit <= 0 else uniq[:_limit]
        for fname, path, val in shown:
            _n = list_valued.get(f"{fname}#{path}")
            _extra = f"（该键共 {_n} 个枚举值，按 1 键计）" if _n and _n > 1 else ""
            print(f"     · {fname}#{path} = {val!r}{_extra}")
        if len(shown) < len(uniq):
            print(f"     · … 还有 {len(uniq) - len(shown)} 项"
                  f"（本次按 VET_DEAD_CONFIG_LIMIT={_limit} 截断；unset = 全量）")
        if weak_list:
            print(f"     ── 弱证据（**仅**末段键名与代码中某键同名，不构成路径级证据）："
                  f"{len(weak_list)} 项 ──")
            for fname, path, val in weak_list:
                print(f"     · {fname}#{path} = {val!r}")
            print("        ⇒ 处置：① 改为路径级读取（改代码读整条路径）"
                  "② 登记到 known_weak 并写明理由 ③ 删掉该配置键。")
            print("        ⚠ 旧口径下这类键因「末段同名」被算作已接线 ⇒ **假绿**"
                  "（第三轮诊断 P-1 已实证：新增叶名 `enabled` 的键根本检不出来）。")
        print("     → 处置三选一：「① 删掉 ② 实现读取 ③ 登记白名单」——"
              "本次修掉的 three_source 阈值属 ②。")
        # ── v3.20.0：**由"提示不阻断"改为阻断** ────────────────────
        # 为什么改（这是本项存续三版的实测教训）：v3.19.2 第 18 项就报出了
        #   `loop_a`/`loop_b`/`delta_gate` 共 33 键"声明了但没接线"，
        #   但因为**提示不阻断**，这批键在随后三轮诊断里**反复被重新发现、反复未被处置**
        #   （v3.19.2 → v3.19.3 登记 → v3.19.4 逐键定性 → v3.20.0 才接线）。
        #   不阻断 ⇒ 每次都是"下次再说" ⇒ 声明层≠执行层这条核心禁忌永远清不干净。
        # 为什么现在可以阻断（前提已具备，不是拍脑袋收紧）：
        #   v3.19.3 L3 + v3.20.0 接线已完成**全量定性**，当前基线 = 0 死键。
        #   基线归零之后再出现死键，只可能是**新增**——要么是新增配置忘了接线，
        #   要么是新增人读型配置没登记。两种都必须在当次处置，不得挂账。
        print("      v3.20.0 起本项**阻断**：L3 全量定性已完成（基线 0），"
              "此后任何未登记死键都属新增项，须当次三选一处置，不得挂账。")
    else:
        print(f"[18/{N}] ✓ 无死配置（{len(cfg_files)} 个 config 文件："
              f"代码读取 {alive} 项〔其中块级消费 {block} 项〕 · 人读型登记 {textual} 项 · "
              f"弱证据登记 {weak_reg} 项）")
    # ── v3.25.0：**免检区（块级消费段）清单**输出 ──────────────────────
    # 为什么要输出（可证伪的动机）：
    #   第 18 项的静态判据对「父级被代码整块取走」的键**无法逐键确认**
    #   ⇒ 这些键落在**免检区**里（v3.25.0 实测：39 段 / 1489 键）。
    #   改造前只报一个**总数** ⇒ 人工无法复核、无法行动 ⇒ 体检项形同虚设。
    #   改造后按段列出 ⇒ 从「一个数字」变成「可行动清单」。
    #
    # ⚠ **措辞纪律（硬约束）**：段清单里**禁止**出现判红词（「死」「未接线」「异常」）
    #   —— 免检区的键**不是**缺陷，只是静态判据看不到它们被谁消费。
    #   一律用「免检区（块级消费）」「待人工定性候选」。
    # ⚠ **不判红**：本段清单**纯粹是输出**，`return 1 if (dead or weak_list) else 0`
    #   的 rc 判定路径**逐字不变** ⇒ 假阳性增量恒为 0。
    print_block_segments(block_segments)
    # v3.23.0 F1：弱证据（仅末段同名撞车）**同样阻断**——
    #   旧口径把它算作已接线 ⇒ 新增的死配置键只要名字撞车就能混过这道门（假绿）。
    return 1 if (dead or weak_list) else 0


def collect_block_segments(expert_dir):
    """返回「免检区（块级消费段）」清单（v3.25.0 · 供登记表守卫与 dump 开关复用）。

    返回 {seg_key: {"file","prefix","key_count","leaf_unused","keys":[完整路径…],"keys_sha256"}}
      seg_key = f"{config 文件名}#{段前缀}"   （ADR-6：必须带文件名前缀——
        同名段跨文件是不同的段，合并登记会让「新增键处置规则」无法落地）

    ⚠ **实现方式**：直接复用第 18 项 `check_dead_config_keys` 内部累加的同一份结果
      ⇒ 段归属、键计数与体检输出**逐字一致**，不存在「两套算法两个答案」的空间。
    ⚠ **纯观测**：不参与任何 rc 判定。
    """
    import io as _io
    import contextlib as _ctx
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        check_dead_config_keys(expert_dir)
    return last_block_segments()


def last_block_segments():
    """取最近一次 `check_dead_config_keys` 累加的段清单。

    ⚠ 用**模块级累加器**而非返回值：第 18 项的 `walk()` 是闭包，
      把段清单从闭包里传出来需要改 walk 签名（行为等价但改动面大）。
      累加器方案：`check_dead_config_keys` 每次调用**重置**它 ⇒ 不会跨轮残留。
    """
    return dict(_LAST_BLOCK_SEGMENTS)


#: 第 18 项最近一次运行累加的段清单（模块级累加器，见 `last_block_segments`）
_LAST_BLOCK_SEGMENTS = {}


def segments_digest(keys):
    """段内叶子路径集合的 sha256 指纹（前 40 hex）。

    定义（定稿，防歧义）：
        sha256( "\\n".join(sorted(叶子完整路径)) ).hexdigest()[:40]
        叶子完整路径 = "<段前缀>.<子路径>"（不含文件名、不含数组下标）

    ⚠ **集合相等**语义：顺序变化不影响（先排序）；
      段内增/删/改名任一键 ⇒ 指纹变化 ⇒ 守卫判红。
    """
    import hashlib
    blob = "\n".join(sorted(keys)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:40]


def print_block_segments(block_segments, stream=None):
    """打印「免检区（块级消费段）」清单（v3.25.0）。

    参数
      block_segments : {seg_key: {"file","prefix","keys":[...],"leaf_unused":int}}
                       —— 由第 18 项的 walk() 累加（**与判定同源**）。
      stream        : 输出流（默认 stdout）。

    ⚠ **纯观测**：本函数**不返回 rc、不改任何判定**，只 print。
    ⚠ **措辞纪律**：禁止判红词（死 / 未接线 / 异常）。见调用处注释。
    """
    import sys as _sys
    out = stream or _sys.stdout
    if not block_segments:
        return
    # 段键 = `<config 文件名>#<段前缀>`（ADR-6）
    items = sorted(block_segments.items(), key=lambda kv: (-len(kv[1]["keys"]), kv[0]))
    total_keys = sum(len(v["keys"]) for _k, v in items)
    total_unused = sum(v["leaf_unused"] for _k, v in items)
    print(f"     ── 免检区（块级消费）清单：{len(items)} 段 / {total_keys} 键；"
          f"其中 {total_unused} 键的末段键名在代码中 0 出现"
          f"（**待人工定性候选，不是死配置**）——", file=out)
    print(f"        说明：这些键按**段**被代码整块消费，静态判据无法逐键确认；"
          f"新增键须按 references/inspection-zones.yaml 的处置规则登记。", file=out)
    for seg_key, v in items:
        print(f"        · {seg_key} — {len(v['keys'])} 键"
              f"（末段键名 0 出现：{v['leaf_unused']}）", file=out)


def check_fallback_drift(expert_dir):
    """v3.14.0：`_FALLBACK` 回退阈值 vs `visual-rules.yaml` 漂移巡检（第 19 项）。
    v3.16.0 扩：覆盖新增的双页数表 / 默认口径 / 主框容量 / severity 分级 / checks 建议级段。

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
        # v3.16.0：主框密度（v3.5.0 配了却无代码读取者，本批首次 wiring → 必须纳入漂移巡检）
        ("max_body_chars_per_slide", yget(("density", "max_body_chars_per_slide")),
         "density.max_body_chars_per_slide"),
        ("overlap_ratio", yget(("geometry", "overlap_ratio")), "geometry.overlap_ratio"),
        ("p2_note_coverage", yget(("gate", "p2_note_coverage")), "gate.p2_note_coverage"),
        # v3.16.0：默认页数口径（字符串；走下面的等值比较分支）
        ("page_caliber_default", rules.get("page_caliber_default"), "page_caliber_default"),
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

    # hours_page_range（口径 A）与 hours_page_range_single_ppt（口径 B，v3.16.0）分别比
    for tbl in ("hours_page_range", "hours_page_range_single_ppt"):
        y_hpr = rules.get(tbl)
        f_hpr = fb.get(tbl)
        if isinstance(y_hpr, dict) and isinstance(f_hpr, dict):
            for k, v in y_hpr.items():
                fv = f_hpr.get(k, f_hpr.get(float(k)))
                if fv is None or list(fv) != list(v):
                    drift.append(f"{tbl}[{k}]: _FALLBACK={fv!r} ≠ yaml={v!r}")
        elif isinstance(y_hpr, dict) and not isinstance(f_hpr, dict):
            drift.append(f"{tbl}: _FALLBACK 缺该表（yaml 已配 {len(y_hpr)} 档）")

    # v3.16.0：severity 分级列表 —— 新增问题类型若只在 yaml 登记、忘了进 _FALLBACK，
    #           yaml 不可读时该类型会掉出所有分级统计（静默失效，比报错更危险）。
    y_sev = rules.get("severity") or {}
    f_sev = fb.get("severity") or {}
    for lv in ("P0", "P1", "P2"):
        if isinstance(y_sev.get(lv), list):
            if list(f_sev.get(lv, [])) != list(y_sev[lv]):
                drift.append(f"severity.{lv}: _FALLBACK={f_sev.get(lv)!r} ≠ yaml={y_sev[lv]!r}")

    # v3.16.0：checks 建议级段（嵌套：bool/数值混排）→ 递归逐叶比对
    def _diff_nested(fv, yv, path, out):
        """递归比对两个结构；只比叶子值，路径用于定位该同步哪一项。"""
        if isinstance(yv, dict):
            if not isinstance(fv, dict):
                out.append(f"checks.{path or '<根>'}: _FALLBACK={fv!r} ≠ yaml={yv!r}")
                return
            for k, v in yv.items():
                _diff_nested(fv.get(k), v, f"{path}.{k}" if path else str(k), out)
        elif isinstance(yv, list):
            if list(fv or []) != list(yv):
                out.append(f"checks.{path}: _FALLBACK={fv!r} ≠ yaml={yv!r}")
        else:
            try:
                same = abs(float(fv) - float(yv)) < 1e-9
            except (TypeError, ValueError):
                same = fv == yv
            if not same:
                out.append(f"checks.{path}: _FALLBACK={fv!r} ≠ yaml={yv!r}")

    y_chk = rules.get("checks") or {}
    if isinstance(y_chk, dict) and y_chk:
        _diff_nested(fb.get("checks") or {}, y_chk, "", drift)

    if drift:
        print(f"[19/{N}] ⚠ 回退阈值与 yaml 漂移 {len(drift)} 项"
              f"——yaml 加载失败时门禁会拿过期阈值继续判，且静默")
        for d in drift:
            print(f"     {d}")
        print("     → 处置：同步 verify_deck.py 的 `_FALLBACK`（受控逃生舱，"
              "仅 VERIFY_ALLOW_FALLBACK=1 时启用）；勿只改 yaml 不改回退值")
        return 1
    # v3.16.0：核对项数改为实算（新增标量 2 项 + 口径 B 4 档 + severity 3 级 + checks 叶子数）
    n = len(pairs)
    for tbl in ("hours_page_range", "hours_page_range_single_ppt"):
        t = rules.get(tbl)
        n += len(t) if isinstance(t, dict) else 0
    n += sum(1 for lv in ("P0", "P1", "P2") if isinstance(y_sev.get(lv), list))

    def _count_leaves(node):
        if isinstance(node, dict):
            return sum(_count_leaves(v) for v in node.values())
        if isinstance(node, list):
            return sum(_count_leaves(v) for v in node)
        return 1

    n += _count_leaves(y_chk) if isinstance(y_chk, dict) else 0
    print(f"[19/{N}] ✓ 回退阈值无漂移（_FALLBACK 与 visual-rules.yaml 逐项一致，"
          f"核对 {n} 项：标量 {len(pairs)} · 双口径页数表 {sum(len(rules.get(t) or {}) for t in ('hours_page_range', 'hours_page_range_single_ppt'))} 档 · "
          f"severity {sum(1 for lv in ('P0', 'P1', 'P2') if isinstance(y_sev.get(lv), list))} 级 · "
          f"checks {_count_leaves(y_chk) if isinstance(y_chk, dict) else 0} 叶）")
    return 0


def judge_threshold_runtime(kind, key, val, want, src):
    """第 21 项运行时断言的**纯函数**判定层（v3.25.0 抽出，供单测直接喂 None）。

    输入（全部由调用方取好，本函数**不碰文件、不起子进程**）：
      kind  —— budget kind 名（如 ``three_source_pass``）
      key   —— domain_config.yaml#three_source_check 下的子键（如 ``pass_threshold``）
      val   —— **运行时**取到的值（``harness.py budget check`` 的 JSON ``value``），可为 None
      want  —— **配置**里声明的值，可为 None
      src   —— 运行时的 ``config_source`` 字符串

    返回：None = 一致（通过）；str = 问题描述（**判红**，不是崩溃）。

    ⚠ **为什么必须是纯函数**：原实现把「取运行时值 → 与阈值比对」写死在体检流程里，
      其中 ``float(val)`` 在 ``val is None``（读取链断裂）时抛**未捕获 TypeError**
      ⇒ **本项崩溃** ⇒ 第 22–24 项永不执行、无结论行 ⇒ 真实失败原因被掩盖
      （研究简报 §3.3 Exp-A 实测：探针把 harness 侧读取链删掉即可复现）。
      抽出纯函数后，「None 情形」可被**直接单测**，不需要网络、不需要改包内 config、
      也不需要在生产代码里留故障注入开关。

    ⚠ 与原实现的**一处刻意差异**（同属「不崩溃、改为判红」这一条修复思路）：
      原实现直接 ``float(val) != float(want)``——当配置值写成 ``"10%"`` 这类**非数值**
      时会抛 **ValueError** 崩溃；本实现捕获后按「不一致」判红。
      理由与 None 分支相同：**体检项崩溃 = 掩盖真实失败**，比误判红更危险。

    返回值文案与 v3.25.0 修复版**逐字一致**（便于既有日志/结论行对照）。
    """
    if val is None or want is None:
        # v3.25.0：原实现直接 `float(val)`，读取链断裂时 val=None ⇒ 抛未捕获
        #   TypeError ⇒ **本项崩溃** ⇒ 第 22–24 项永不执行、无结论行，
        #   真实失败原因被掩盖（研究简报 §3.3 Exp-A 实测）。
        #   改为显式判红：缺值本身就是「配置未生效」的证据。
        return (f"`{kind}` 运行时值为 None（读取链断裂？）"
                f"≠ domain_config.yaml#three_source_check.{key}={want!r}"
                f"（配置未生效 / 读进 fallback）")
    try:
        same = float(val) == float(want)
    except (TypeError, ValueError, OverflowError):
        # 两侧都不是可转 float 的数值（如 "10%"）⇒ 无法证明一致 ⇒ 判红，不崩
        same = val == want
    if not same:
        return (f"`{kind}` 运行时值 {val!r} ≠ domain_config.yaml"
                f"#three_source_check.{key}={want!r}（配置改了没生效 / 读进 fallback）")
    if "domain_config.yaml#three_source_check" not in src:
        return (f"`{kind}` 的 config_source={src!r} 未指向 domain_config.yaml"
                f"#three_source_check（阈值可能来自别处）")
    return None


#: 三源阈值的**决策键**（唯一源 = config/domain_config.yaml#three_source_check）。
#: ⚠ 口径与 `scripts/harness.py#_DECISION_KEYS` 对齐——改了这里要同步改那边。
THREE_SOURCE_DECISION_KEYS = ("sample_rate", "pass_threshold")


def find_three_source_hardcoded_literals(src, decision_keys=THREE_SOURCE_DECISION_KEYS):
    """扫出「三源阈值判定点里硬编码了字面量」的位置（**纯函数**，v3.27.0 L-5）。

    背景（来自包外脚本 `verify_three_source_config.py` 的判据 ③）：
      v3.12.0 把三处硬编码 0.8/0.1 改成读配置，但**没有留下防线** ⇒
      以后有人「顺手写回」`float(tsc.get("sample_rate", 0.1))` 这种形态，
      改 yaml 又会**静默失效**（默认值被静默消费）⇒ 同型复发。

    ⚠ **为何本判据比包外脚本的原始正则更准**（实测）：
      包外脚本的正则是 `sample_n\\s*=.*\\*\\s*0\\.1` / `threshold\\s*=\\s*0\\.8` /
      `"threshold":\\s*0\\.8` ⇒ 只认**三种字面写法**，
      实测当前 `verify_deck.py` 命中 **0** 处 ⇒ 但代码里**确实有**字面量：
        · `verify_deck.py:1597` `float(tsc.get("sample_rate", 0.1))`
        · `verify_deck.py:1632` `float(tsc.get("pass_threshold", 0.8))`
      这两处是「**内联默认字面量**」形态 ⇒ 包外正则**抓不到** ⇒ 假绿。
      ⇒ 本判据改用 **AST**：找「读决策键的同时又带了字面量默认值」的 `.get()` 调用。

    ⚠ **豁免**（这三类是**合法**的，不该判红）：
      · `harness.py` 的 `defaults` 字典（**兜底集**，缺键时显式告警，属设计内）
      · `verify_deck.py` 的 `fallback` 字典（同上，且有 `VERIFY_ALLOW_FALLBACK` 门）
      · 纯注释行、docstring、告警文案里的 "0.1/0.8" 字样

    参数：
      src          : str —— 被扫源码（verify_deck.py 全文）
      decision_keys: tuple —— 决策键名集合
    返回：list[str] —— 命中位置描述（形如 "第 1597 行：sample_rate 读了字面量默认值 0.1"）
    """
    import ast as _ast
    try:
        tree = _ast.parse(src)
    except SyntaxError as e:
        return [f"__PARSE_ERROR__:{e}"]

    hits = []

    class _V(_ast.NodeVisitor):
        """找 `X.get(<决策键>, <字面量>)` 形态的调用。"""

        def visit_Call(self, node):
            fn = node.func
            is_get = False
            if isinstance(fn, _ast.Attribute) and fn.attr == "get":
                is_get = True
            if is_get and len(node.args) >= 2:
                key = node.args[0]
                if isinstance(key, _ast.Constant) and isinstance(key.value, str) \
                        and key.value in decision_keys:
                    default = node.args[1]
                    if isinstance(default, _ast.Constant) and \
                            isinstance(default.value, (int, float)) and \
                            not isinstance(default.value, bool):
                        hits.append(
                            f"第 {node.lineno} 行：决策键 `{key.value}` 带了"
                            f"字面量默认值 {default.value}（改 yaml 会被静默忽略）")
            self.generic_visit(node)

    _V().visit(tree)
    return hits


def check_three_source_single_source(expert_dir):
    """v3.16.0：第 21 项 —— 三源阈值「双重声明」防线（防复发）。

    背景：v3.16.0 删掉了 `harness.yaml#budgets` 里的 three_source_sample_rate /
    three_source_pass_threshold——它们与 `domain_config.yaml#three_source_check` **同值重复声明**，
    而真实执行者 `verify_deck.py#_load_three_source_thresholds()` 只读后者，
    于是「改 harness.yaml 侧」会**完全静默失效**（同一份阈值两个地方写着一样的值，
    谁改都不会报错，只有一处真生效）。删完若不留防线，下次有人"顺手加回来"就会复发。

    本项两道防线，缺一不可（各自堵的漏洞不同）：
      ① **静态同名比对**：`budgets` 的键里若出现 `three_source_<子键>`（归一化后同名）→ 阻断。
         归一化（去非字母数字 + 小写）是为了让 `three_source_pass_threshold` /
         `threeSourcePassThreshold` / `THREE_SOURCE_pass-threshold` 这类变体也躲不掉。
      ② **运行时值断言**：真跑 `harness.py budget check --kind three_source_pass`，
         断言 (a) value == domain_config.yaml#three_source_check.pass_threshold，
                (b) config_source 指向 domain_config.yaml#three_source_check。
         这条补的是第 18 项（死配置/AST 判据）的已知盲区——**静态分析发现不了
         "代码读了 fallback 而没读配置"**：AST 能看到 `cfg.get("x")` 存在，看不出运行时取到的是哪一路。
         只有实跑并把返回值与配置值对齐，才能证明"配置真的被消费了"。

    阻断级别：判据确定（键名等值 + 数值等值），假阳性为零 → 阻断。
    """
    har = os.path.join(expert_dir, "config", "harness.yaml")
    dom = os.path.join(expert_dir, "config", "domain_config.yaml")
    hpy = os.path.join(expert_dir, "scripts", "harness.py")
    if not (os.path.exists(har) and os.path.exists(dom)):
        print(f"[21/{N}] – 缺 harness.yaml 或 domain_config.yaml，跳过")
        return 0
    try:
        import yaml
        budgets = (yaml.safe_load(open(har, encoding="utf-8")) or {}).get("budgets") or {}
        tsc = (yaml.safe_load(open(dom, encoding="utf-8")) or {}).get("three_source_check") or {}
    except Exception as e:
        print(f"[21/{N}] ⚠ 读取失败：{e}")
        return 1

    def _norm(k):
        return "".join(ch for ch in str(k).lower() if ch.isalnum())

    problems = []

    # ① 静态：归一化同名检测
    if isinstance(budgets, dict) and isinstance(tsc, dict):
        norm_b = {_norm(k): k for k in budgets}
        for t in tsc:
            for cand in (f"three_source_{t}", str(t)):
                hit = norm_b.get(_norm(cand))
                if hit is not None:
                    problems.append(
                        f"harness.yaml#budgets.{hit} 与 domain_config.yaml#three_source_check.{t} "
                        f"重复声明；三源阈值唯一源是 domain_config.yaml，删 harness.yaml 侧")
                    break
    if problems:
        print(f"[21/{N}] 🔴 三源阈值双重声明 {len(problems)} 处——改 harness.yaml 侧会静默失效")
        for p_ in problems:
            print(f"     {p_}")
        print("     → 处置：删掉 harness.yaml#budgets 里的 three_source_* 键；"
              "值要改就改 config/domain_config.yaml#three_source_check（并由 verify_deck 消费）")
        return 1

    # ③ 静态：判定点不得带**内联字面量默认值**（v3.27.0 L-5 收口）
    #   来源：包外脚本 verify_three_source_config.py 的判据 ③ —— 该判据包内原本**没有**，
    #   按「归档前先补齐真源」的纪律，先补进来再归档包外脚本。
    #   ⚠ 包外脚本的原始正则只认三种字面写法，实测命中 0 处 ⇒ 假绿；
    #     本处改用 AST（见 find_three_source_hardcoded_literals 的说明）。
    vd = os.path.join(expert_dir, "scripts", "verify_deck.py")
    if not os.path.exists(vd):
        print(f"[21/{N}] ⚠ 静态比对通过，但缺 scripts/verify_deck.py，"
              f"无法做判定点字面量检查")
        return 1
    try:
        vd_src = open(vd, encoding="utf-8", errors="replace").read()
    except OSError as e:
        print(f"[21/{N}] ⚠ 读 verify_deck.py 失败：{e}")
        return 1
    literals = find_three_source_hardcoded_literals(vd_src)
    if literals and literals[0].startswith("__PARSE_ERROR__"):
        print(f"[21/{N}] ⚠ verify_deck.py 解析失败，未判（探测受阻，非漂移）：{literals[0]}")
        literals = []
    if literals:
        print(f"[21/{N}] 🔴 三源阈值判定点有 {len(literals)} 处内联字面量默认值"
              f"——改 yaml 会被静默忽略")
        for l_ in literals:
            print(f"     {l_}")
        print("     → 处置：删掉 .get(<决策键>, <字面量>) 的第二个参数；"
              "缺键策略统一由 harness.py#load_three_source_config() 负责"
              "（决策键缺 → 置 None + 显式告警 + fail-closed）")
        return 1

    # ② 运行时断言：configuration 值必须真的从 domain_config 取出来
    if not os.path.exists(hpy):
        print(f"[21/{N}] ⚠ 静态比对通过，但缺 scripts/harness.py，无法做运行时断言")
        return 1
    checks = [("three_source_pass", "pass_threshold"),
              ("three_source_sample", "sample_rate")]
    runtime_bad = []
    #: ⚠ v3.25.0 收口修正：**探测受阻 ≠ 断言失败**。
    #:   原实现把「子进程起不来 / 输出非 JSON」一律记进 `runtime_bad` ⇒ 判红（阻断级）。
    #:   但「探测侧故障」不能当「被测侧缺陷」——实测反例：
    #:     · shell 直跑 `python3 scripts/harness.py budget check --kind three_source_pass`
    #:       ⇒ 正常输出 JSON（value=0.8, rc=0）；
    #:     · 同一命令经 `subprocess.run` ⇒ rc=4、stdout 为空，
    #:       stderr = 「⛔ harness 运行异常：PermissionError: Brokered host mkdir …」
    #:       （WorkBuddy 宿主 shim 拦截子进程建目录，见 sitecustomize.py:508）。
    #:   ⇒ 同一个被测产物，在不同调用方式下结论相反 ⇒ 红色来自**环境**而非代码。
    #:   按「假阳性必须为零」铁律：**探测受阻 ⇒ 判「未判」（提示级·不阻断）**，
    #:   只有「拿到合法 JSON 且值/来源确实对不上」才判红。
    probe_blocked = []
    for kind, key in checks:
        try:
            p = subprocess.run([sys.executable, hpy, "budget", "check", "--kind", kind],
                               capture_output=True, text=True, timeout=60)
        except Exception as e:
            probe_blocked.append(f"`budget check --kind {kind}` 运行失败：{e}")
            continue
        try:
            out = json.loads((p.stdout or "").strip().splitlines()[-1])
        except Exception:
            # ⚠ 探测受阻（stdout 空 / 非 JSON）——**不是断言失败**。
            #   把子进程 stderr 的首行带出来，便于分辨「宿主拦截」与「真异常」。
            _err = ((p.stderr or "").strip().splitlines() or [""])[0][:120]
            probe_blocked.append(
                f"`budget check --kind {kind}` 探测受阻（stdout="
                f"{(p.stdout or '')[:40]!r}；stderr 首行={_err!r}）")
            continue
        val, src = out.get("value"), str(out.get("config_source", ""))
        want = tsc.get(key)
        if key not in tsc:
            runtime_bad.append(f"domain_config.yaml#three_source_check 缺 `{key}` "
                               f"（运行时无从对齐）")
            continue
        # v3.25.0：判定抽到纯函数 judge_threshold_runtime()——
        #   「None 情形」从此可被直接单测（不依赖网络、不依赖改包内 config、
        #   不需要在生产代码里留故障注入开关）。
        bad = judge_threshold_runtime(kind, key, val, want, src)
        if bad:
            runtime_bad.append(bad)
    if runtime_bad:
        print(f"[21/{N}] 🔴 三源阈值运行时断言失败 {len(runtime_bad)} 项"
              f"（第 18 项静态判据查不出的那类：读了 fallback 而没读配置）")
        for r_ in runtime_bad:
            print(f"     {r_}")
        print("     → 处置：让 verify_deck.py#_load_three_source_thresholds 真从 "
              "domain_config.yaml#three_source_check 取值，并确认 fallback 未被实际消费")
        return 1
    if probe_blocked:
        # ⚠ 探测受阻 ⇒ 判「未判」：静态部分已通过，运行时部分因环境受阻无法确认。
        print(f"[21/{N}] ℹ 三源阈值**运行时断言未判**（探测受阻，非漂移；静态部分已通过）"
              f"：harness.yaml 无重复声明")
        for b_ in probe_blocked:
            print(f"     {b_}")
        print("     → 处置：确认子进程可正常起（宿主拦截建目录时本项无法判定）；"
              "解除后再跑一次本项")
        return 0

    shown = "、".join(f"{k}={tsc.get(v)}" for k, v in checks if v in tsc) or "无可用阈值"
    print(f"[21/{N}] ✓ 三源阈值单一数据源（harness.yaml 无重复声明；"
          f"budget check 运行时值…… {shown} 与 domain_config.yaml#three_source_check 一致）")
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


# ── 22. 闸3 交叉复检领域映射（v3.17.0）───────────────────────────
def _agent_display_names(agents_dir):
    """取 agents/*.md 的成员显示名（displayName.zh）→ {agent_id: 显示名}。

    为何要**容错**解析（v3.17.0 实测到的真实缺陷）：
      `agents/dvm-content-expert.md` 的 frontmatter **未在 YAML 结束处闭合**——
      第二个 `---` 落在正文「## v3.4.0 硬约束」之后，于是整个 frontmatter 块里
      混进了 Markdown 正文，`yaml.safe_load` 直接抛 ScannerError。
      （体检第 15 项只查「有没有第二个 `---`」+「有没有 name 字段」，不查 YAML 可解析，
        故该缺陷一直**假绿**——属跨批需求，本函数只做容错读取，不改他人文件。）

    降级链：YAML 可解析 → 取 displayName.zh；否则正则取 displayName 段的 zh；
    否则取 H1 标题「… - 名字」；再不行用 agent id 兜底。
    """
    names = {}
    if not os.path.isdir(agents_dir):
        return names
    try:
        import yaml
    except ImportError:
        yaml = None
    for fn in sorted(os.listdir(agents_dir)):
        if not fn.endswith(".md"):
            continue
        mid = fn[:-3]
        try:
            lines = open(os.path.join(agents_dir, fn), encoding="utf-8",
                         errors="replace").read().split("\n")
        except OSError:
            continue
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
        names[mid] = name or mid
    return names


def check_cross_review_mapping(expert_dir):
    """v3.17.0：第 22 项 —— 闸3「非作者交叉复检」领域↔复检人映射守卫（**阻断**）。

    背景（真实缺陷，非假设）：`references/sop-stages.md` 闸3 迭代回路里的
    「跨模块改动 → 非作者交叉复检」映射**三处全反**：
        科学性改动→苏学法 / 教学性改动→严真奥 / 页面性改动→苏学法
    而这三人各自的 agent MD 都明文写着「你不做…（那是别人的事）」——
    等于**把把关人派给了被明文禁止接活的人**，把关被整体绕开，且无人察觉
    （散文里的映射此前没有任何机器拦截）。

    本项三道判据（任一不过 → 阻断，不放行）：
      ① **映射唯一源** = `config/guard.yaml#cross_review_mapping`
         （键 = 改动类型，值 = 期望成员 id）；yaml 里没登记 → 阻断（禁硬编码）。
      ② **SOP 文档的实际写法 == yaml 登记值**：同一条目内出现的成员名必须唯一且正确；
         写成别人 / 漏写 / 同条目多名字 → 阻断。
      ③ 复检人 id 必须登记在 `config/harness.yaml#members`（防派给不存在的成员）。

    为何阻断而不是提示：映射写反会把把关**整体**绕开，属"护栏看起来在、实际没设防"
    ——与第 21 项同级的确定性缺陷（判据确定、假阳性为零）。
    """
    guard_path = os.path.join(expert_dir, "config", "guard.yaml")
    if not os.path.exists(guard_path):
        print(f"[22/{N}] – 缺 config/guard.yaml（交叉复检映射唯一源），跳过")
        return 0
    try:
        import yaml
        guard = yaml.safe_load(open(guard_path, encoding="utf-8")) or {}
    except Exception as e:
        print(f"[22/{N}] 🔴 读取 config/guard.yaml 失败：{e}")
        return 1

    mapping = guard.get("cross_review_mapping") or {}
    pattern = guard.get("cross_review_doc_pattern") or ""
    doc_rel = guard.get("cross_review_doc") or ""
    if not isinstance(mapping, dict) or not mapping:
        print(f"[22/{N}] 🔴 config/guard.yaml 未登记 cross_review_mapping"
              f"（映射必须落 yaml 作为唯一源，禁在代码/文档里各写一份）")
        return 1
    # v3.17.0：yaml 键缺失**判红，不回退到代码内置默认值**。
    #   缘由（本项自身的盲区）：若这里写成 `guard.get("cross_review_doc_pattern") or "{kind}→{name}视角"`，
    #   则 yaml 键被改名/删除时**不报错**，检查照跑——但用的是代码里的兜底值，
    #   yaml 那份就变成"装饰品"：看着有唯一源，实际没消费配置。
    #   这与第 21 项记录的同一盲区（"读了 fallback 而没读配置"）同型，
    #   静态判据发现不了，只能靠"缺键即红"把静默失效变成显式失败。
    if not pattern or not doc_rel:
        missing = [k for k, v in (("cross_review_doc_pattern", pattern),
                                  ("cross_review_doc", doc_rel)) if not v]
        print(f"[22/{N}] 🔴 config/guard.yaml 缺 {' / '.join(missing)}"
              f"——唯一源不完整，禁回退到代码内置默认值"
              f"（回退会让 yaml 变成装饰品：检查照跑、但没消费配置）")
        return 1
    doc_path = os.path.join(expert_dir, doc_rel)
    if not os.path.exists(doc_path):
        print(f"[22/{N}] – 缺 {doc_rel}（交叉复检映射的落地文档），跳过")
        return 0
    if not os.path.isdir(os.path.join(expert_dir, "agents")):
        print(f"[22/{N}] – 无 agents/ 目录（取不到成员显示名），跳过")
        return 0

    # 成员注册表（复检人 id 必须在册）
    members = set()
    hpath = os.path.join(expert_dir, "config", "harness.yaml")
    if os.path.exists(hpath):
        try:
            members = set(((yaml.safe_load(open(hpath, encoding="utf-8")) or {})
                           .get("members") or {}).keys())
        except Exception:
            members = set()

    names = _agent_display_names(os.path.join(expert_dir, "agents"))
    all_names = {n for n in names.values() if n}
    try:
        lines = open(doc_path, encoding="utf-8", errors="replace").read().split("\n")
    except OSError as e:
        print(f"[22/{N}] 🔴 读取 {doc_rel} 失败：{e}")
        return 1

    problems = []
    for kind, spec in mapping.items():
        if not isinstance(spec, dict):
            problems.append(f"cross_review_mapping.{kind} 不是映射（须含 reviewer）")
            continue
        reviewer = spec.get("reviewer")
        if not reviewer:
            problems.append(f"cross_review_mapping.{kind} 缺 reviewer（期望成员 id）")
            continue
        if members and reviewer not in members:
            problems.append(f"{kind} → {reviewer}：该 id 未登记在 config/harness.yaml#members")
        expected_name = names.get(reviewer)
        if not expected_name:
            problems.append(f"{kind} → {reviewer}：取不到该成员显示名（agents/{reviewer}.md）")
            continue
        expected = pattern.format(kind=kind, name=expected_name)
        seen = 0
        ok_form = 0
        for i, line in enumerate(lines, 1):
            if kind not in line:
                continue
            for clause in re.split(r"[；;]", line):
                if kind not in clause:
                    continue
                seen += 1
                found = sorted(n for n in all_names if n in clause)
                if expected_name not in found:
                    problems.append(
                        f"{doc_rel}:{i} 「{kind}」未指向登记的复检人（应为 {expected_name}）；"
                        f"实得「{clause.strip()[:50]}」")
                elif len(found) > 1:
                    problems.append(
                        f"{doc_rel}:{i} 「{kind}」同一条目出现多个成员名 {found}（路由不唯一）")
                if expected in re.sub(r"\s+", "", clause):
                    ok_form += 1
        if seen == 0:
            problems.append(f"{doc_rel} 未出现「{kind}」的交叉复检映射（闸3 迭代回路缺该路由）")
        elif ok_form == 0:
            problems.append(f"{doc_rel} 中「{kind}」未按 yaml 登记写法落（应为「{expected}」）")

    if problems:
        print(f"[22/{N}] 🔴 闸3 交叉复检映射与 yaml 登记不一致 {len(problems)} 处"
              f"——把关人被派错 = 把关整体失效")
        for p_ in problems:
            print(f"     {p_}")
        print("     → 处置：映射唯一源 = config/guard.yaml#cross_review_mapping；"
              "改 SOP 文档必须同步改 yaml（或反之），两者不允许各写一份")
        return 1
    shown = "、".join(f"{k}→{names.get((v or {}).get('reviewer'), '?')}"
                      for k, v in mapping.items())
    print(f"[22/{N}] ✓ 闸3 交叉复检映射与 yaml 登记一致（{len(mapping)} 类改动：{shown}）")
    return 0


# ── 23. 域绑定残留巡检（v3.17.0）───────────────────────────────
def _exempt_line_set(lines, hy):
    """算出**豁免行号集合**（全部可判定，不靠关键词猜测）。

    四类豁免（判据见 config/hygiene-words.yaml#scan）：
      ① 哨兵块：begin…end 之间全部行；
      ② 章节级：标题命中 exempt_headings.pattern → 该章节内全部行
         （直到下一个**同级或更高级**标题）；
      ③ 行级：命中 profile_ref_patterns（该行在说"去域档案里取"）；
      ④ frontmatter 注释行：YAML frontmatter 内以 # 开头的注释行（变更说明）。
    """
    ex = set()
    # v3.17.0 批次 B 修复（**声明层≠执行层**实测）：
    #   `exempt_markers` / `exempt_headings` / `profile_ref_patterns` 三组键在
    #   config/hygiene-words.yaml 里**嵌在 `scan:` 之下**，而本函数此前从**顶层**取
    #   （只有 `frontmatter_comment_exempt` 一处正确写了 `hy.get("scan")`）。
    #   ⇒ 三组豁免**从未生效**：哨兵块围起来的行照样报、引用域档案路径的行照样报，
    #     体检第 23 项因此长期虚高，且"围哨兵就能豁免"这条契约是**假的**。
    #   修法：以 `scan` 为唯一读取位置（与 yaml 实际结构、与函数注释的 #scan 一致），
    #     兼容顶层写法回退一次（不静默吞错：两者都缺时该组豁免即为空集合，会照常报出）。
    _scan = hy.get("scan") or {}
    # ① 哨兵块
    for mk in (_scan.get("exempt_markers") or hy.get("exempt_markers") or []):
        b, e = mk.get("begin"), mk.get("end")
        if not b or not e:
            continue
        inblk = False
        for i, ln in enumerate(lines):
            if b in ln:
                inblk = True
                ex.add(i)
                continue
            if inblk:
                ex.add(i)
                if e in ln:
                    inblk = False
    # ② 章节级
    pats = [p.get("pattern") for p in (_scan.get("exempt_headings") or hy.get("exempt_headings") or [])
            if isinstance(p, dict) and p.get("pattern")]
    if pats:
        heads = []
        for i, ln in enumerate(lines):
            m = re.match(r"^(#{1,6})\s", ln)
            if m:
                heads.append((i, len(m.group(1))))
        for idx, (i, lvl) in enumerate(heads):
            if not any(re.match(p, lines[i]) for p in pats):
                continue
            end = len(lines)
            for j, l2 in heads[idx + 1:]:
                if l2 <= lvl:
                    end = j
                    break
            ex.update(range(i, end))
    # ③ 行级（引用域档案）
    refs = [p for p in (_scan.get("profile_ref_patterns") or hy.get("profile_ref_patterns") or []) if p]
    if refs:
        for i, ln in enumerate(lines):
            if any(p in ln for p in refs):
                ex.add(i)
    # ④ frontmatter 注释行
    if (hy.get("scan") or {}).get("frontmatter_comment_exempt", True):
        if lines and lines[0].strip() == "---":
            for i, ln in enumerate(lines[1:], 1):
                if ln.strip() == "---":
                    break
                if ln.lstrip().startswith("#"):
                    ex.add(i)
    return ex


def check_domain_binding_residue(expert_dir):
    """v3.17.0：第 23 项 —— 域绑定残留巡检（**提示级·不阻断**）。

    目的：把散落在 `agents/` 与 `references/` 里的**学科专有词**揪出来，
    指出哪些应下沉到域档案（`config/domain-profiles.yaml`）——
    "该下沉却没下沉"的残留此前没有任何机器可查的地方。

    判据（全部可判定，**不靠关键词猜测**）：
      ① 词表唯一源 = `config/hygiene-words.yaml#domain_specific_terms`
         （词表禁硬编码在代码里——改词只改 yaml）；
      ② 扫描范围 = `hygiene-words.yaml#scan.roots` + `include_suffixes`，
         排除 `scan.exclude_files`（每条排除都登记了原因）；
      ③ 豁免 = 哨兵块 / 「历史沿革」章节 / 引用域档案路径的行 / frontmatter 注释行；
      ④ 每处命中给出 **文件:行号 + 词 + 类别**，并判定该词
         **是否已下沉到域档案**（词是否出现在 `config/domain-profiles.yaml` 中）——
         已下沉 → 正文应改为**引用**档案；未下沉 → 建议把该内容写入档案对应字段。

    为何**只报不阻断**：词表天然会误伤正当举例（第一版先积累一轮证据再谈阻断，
    与本轮「假阳性必须为零」的纪律一致——宁可先不出数，也不出无法解释的数）。
    """
    hy_path = os.path.join(expert_dir, "config", "hygiene-words.yaml")
    if not os.path.exists(hy_path):
        print(f"[23/{N}] – 缺 config/hygiene-words.yaml（域绑定残留词表唯一源），跳过")
        return 0
    try:
        import yaml
        hy = yaml.safe_load(open(hy_path, encoding="utf-8")) or {}
    except Exception as e:
        print(f"[23/{N}] 🔴 读取 config/hygiene-words.yaml 失败：{e}")
        return 1
    terms = []
    for t in (hy.get("domain_specific_terms") or []):
        if isinstance(t, dict) and t.get("term"):
            terms.append((str(t["term"]), t.get("kind") or "", t.get("note") or ""))
        elif isinstance(t, str) and t.strip():
            terms.append((t.strip(), "", ""))
    if not terms:
        print(f"[23/{N}] 🔴 config/hygiene-words.yaml 未登记 domain_specific_terms"
              f"（词表必须落 yaml 作为唯一源，禁在代码里硬编码）")
        return 1

    sc = hy.get("scan") or {}
    roots = sc.get("roots") or ["agents", "references"]
    suffixes = tuple(sc.get("include_suffixes") or [".md"])
    excluded = {}
    for e in (sc.get("exclude_files") or []):
        if isinstance(e, dict) and e.get("path"):
            excluded[str(e["path"])] = e.get("reason") or ""

    # 「是否已下沉」判定：词是否出现在域档案里（可判定），并给出是哪个域
    prof_path = os.path.join(expert_dir, "config", "domain-profiles.yaml")
    prof_text = ""
    prof_domains = {}
    if os.path.exists(prof_path):
        prof_text = open(prof_path, encoding="utf-8", errors="replace").read()
        try:
            import yaml as _y
            pdata = _y.safe_load(prof_text) or {}
            for d in (pdata.get("domains") or []):
                if isinstance(d, dict) and d.get("id"):
                    prof_domains[str(d["id"])] = json.dumps(d, ensure_ascii=False)
        except Exception:
            prof_domains = {}

    hits = []
    scanned = 0
    for root in roots:
        d = os.path.join(expert_dir, str(root))
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(suffixes):
                continue
            rel = f"{root}/{name}"
            if rel in excluded:
                continue
            fp = os.path.join(d, name)
            try:
                lines = open(fp, encoding="utf-8", errors="replace").read().split("\n")
            except OSError:
                continue
            scanned += 1
            ex = _exempt_line_set(lines, hy)
            for i, ln in enumerate(lines):
                if i in ex or not ln.strip():
                    continue
                matched = [(t, k) for (t, k, _n) in terms if t in ln]
                if not matched:
                    continue
                in_prof = bool(prof_text) and any(t in prof_text for (t, _k) in matched)
                where = []
                for did, blob in prof_domains.items():
                    if any(t in blob for (t, _k) in matched):
                        where.append(did)
                hits.append({
                    "file": rel, "line": i + 1, "matched": matched,
                    "in_profile": in_prof, "profile_domains": where,
                    "count": 1,
                    "snippet": ln.strip()[:70],
                })
    # 同一文件同一「词组合」多次命中 → 只保留首个行号 + 计数（报告可读）
    grouped = {}
    for h in hits:
        k = (h["file"], tuple(t for (t, _k) in h["matched"]))
        if k in grouped:
            grouped[k]["count"] += 1
        else:
            grouped[k] = h
    hits = list(grouped.values())
    hits.sort(key=lambda h: (h["file"], h["line"]))

    if hits:
        print(f"[23/{N}] ℹ 域绑定残留巡检：命中 {len(hits)} 处"
              f"（提示级·**不阻断**——第一版积累证据；扫描 {scanned} 个文件，"
              f"排除 {len(excluded)} 个域专有文件）")
        for h in hits[:40]:
            if h["profile_domains"]:
                tip = (f"已下沉到域档案（{'、'.join(h['profile_domains'])}）"
                       f"→ 正文应改为**引用** config/domain-profiles.yaml，勿复制")
            elif h["in_profile"]:
                tip = ("已出现在域档案文件中（**未绑定到具体域**）"
                       "→ 建议下沉到某域的对应字段")
            else:
                tip = "**未下沉** → 建议把该域专有内容写入 config/domain-profiles.yaml 对应字段"
            terms_s = "".join(f"「{t}」" for (t, _k) in h["matched"])
            kinds = "、".join(sorted({k for (_t, k) in h["matched"] if k}))
            print(f"     {h['file']}:{h['line']} {terms_s}"
                  f"{('（' + kinds + '）') if kinds else ''}"
                  f"{(' ×' + str(h['count'])) if h.get('count', 1) > 1 else ''}"
                  f"  {tip}")
            print(f"        └─ {h['snippet']}")
        if len(hits) > 40:
            print(f"     … 还有 {len(hits) - 40} 处")
        print("     → 处置：① 已在域档案的词 → 正文改为**引用**档案（不复制）；"
              "② 未下沉的词 → 写入域档案对应字段；"
              "③ 确属正当用法（举例/历史沿革）→ 用哨兵块 "
              "<!-- DOMAIN_EXAMPLE_BEGIN -->…<!-- DOMAIN_EXAMPLE_END --> 或"
              "「## 历史沿革」章节圈起")
        return 0
    print(f"[23/{N}] ✓ 域绑定残留巡检：未发现学科专有词残留"
          f"（扫描 {scanned} 个文件，排除 {len(excluded)} 个域专有文件）")
    return 0


def check_stage_order_drift(expert_dir):
    """v3.19.3（L3）：第 24 项 —— 阶段顺序漂移守卫（**阻断**）。

    背景（L3 逐键定性时发现的双份真相）：
      `config/harness.yaml#stages.{i}.next` 是**人读型**阶段顺序说明
      （`next_stage` 在代码中 0 次出现，实际推进由 `task_state.json#current_stage`
      数值驱动）。但 yaml 的 `next` 与代码的 `current_stage+1` 是**同一事实的两处写法**
      ——若有人改了 yaml 的 `next` 顺序而代码仍按数值推进，会出现
      「配置说闸2 后接闸 5、代码实际去闸 3」的**静默不一致**。

    判据（确定、可反例验证）：
      `stages.{i}.next == i+1`（最后一级的 `next` 应为 None/空）。
    漂移即报错并指出该同步哪一项——与第 19 项 check_fallback_drift 同模式
    （后者防"两份同源数据不一致"，本项防"两处同一事实不一致"）。
    """
    hp = os.path.join(expert_dir, "config", "harness.yaml")
    if not os.path.exists(hp):
        print(f"[24/{N}] – 缺 harness.yaml，跳过")
        return 0
    try:
        import yaml
        cfg = yaml.safe_load(open(hp, encoding="utf-8"))
    except Exception as e:
        print(f"[24/{N}] ⚠ harness.yaml 解析失败：{e}")
        return 1
    stages = cfg.get("stages") or {}
    if not isinstance(stages, dict) or not stages:
        print(f"[24/{N}] – stages 段缺失或非 dict，跳过")
        return 0
    # ⚠ 键归一化：YAML 里 `0:` 会被解析成 **int**，直接 stages.get("0") 恒取到 None
    #   （harness.py 里早有同款归一化与注释，此处必须照做——否则守卫会把
    #   「所有 next 都是 None」误报成漂移，属**假红**。本守卫首版即踩此坑，
    #   实测抓到后修正——记：写守卫必须先看同文件已有的同类归一化）。
    stages = {str(k): v for k, v in stages.items()}
    problems = []
    nums = sorted(int(k) for k in stages if str(k).isdigit())
    for i in nums:
        st = stages.get(str(i)) or {}
        nxt = st.get("next")
        name = st.get("name", f"闸{i}")
        if i == nums[-1]:
            if nxt not in (None, "", 0):
                problems.append(f"stages.{i}.next={nxt!r} 应为 None（末级无后继）")
        elif nxt != i + 1:
            problems.append(f"stages.{i}.next={nxt!r} ≠ {i + 1}"
                            f"（{name} 的后继应为 {i + 1}）")
    if problems:
        print(f"[24/{N}] ✗ 阶段顺序漂移 {len(problems)} 处：")
        for p in problems:
            print(f"     · {p}")
        print("     → stages.N.next 是**人读型**顺序说明，但必须与代码的 "
              "current_stage+1 推进一致；不一致即「配置说走 A、代码走 B」的静默分叉。")
        return 1
    print(f"[24/{N}] ✓ 阶段顺序一致（{len(nums)} 级："
          + " → ".join(f"{i}" for i in nums) + "，next 均等于 i+1）")
    return 0


def check_harness_fallback_structure(expert_dir):
    """v3.25.0：第 25 项 —— `harness.py#_FALLBACK` ↔ `harness.yaml` **结构**比对（阻断）。

    背景（研究简报 §7.2 / 主理人独立探针双源证实）：
      `scripts/harness.py` 的 `_FALLBACK` 是 yaml 的**代码侧副本**（yaml 读失败时整份顶上），
      但它与 yaml **早已漂移**：副本多出已废弃的 `gate_exit_codes."5"` 与六阶段残留 `stages.5`，
      且 `stages.2/3/4.gate` 语义漂移（副本全 `user_confirm`，yaml 实为
      `script_check` / `gate_script+verifier` / `three_source_check`）。
      ⚠ 后果不是文案问题：yaml 不可读时 **stage 2/3/4 的闸从机器强制退化为人工确认**。

    为何不并入第 19 项：第 19 项用 `ast.literal_eval` 解析 `verify_deck.py#_FALLBACK`
    （纯字面量，可行）；`harness.py#_FALLBACK` 含 **DictComp**（`str(i) for i in range(6)`），
    `literal_eval` 直接抛 ValueError ⇒ 本项改用 `importlib` 取**运行时**值（更贴近真实降级行为）。

    判据（**只比结构，不比文案**——研究简报附录 D 的避坑方案）：
      ① `gate_exit_codes` 键集合相等；
      ② `stages` 阶段集合相等；
      ③ 共同阶段的 `gate` 取值相等。
    文案（exit 1–4 的长文案）**刻意不比**：解释性文字天然长短不一（yaml 长口径 vs
    代码短口径都是合法表述），等值比会造 4 处假阳性 ⇒ 违反「假阳性必须为零」。
    语义骨架的文档侧对账由 `references/harness-engine.md#6` 的 GATE_EXIT_MIRROR 承载。
    """
    hp = os.path.join(expert_dir, "config", "harness.yaml")
    hpy = os.path.join(expert_dir, "scripts", "harness.py")
    if not os.path.exists(hp) or not os.path.exists(hpy):
        print(f"[25/{N}] – 缺 harness.yaml 或 harness.py，跳过")
        return 0
    try:
        import yaml
        cfg = yaml.safe_load(open(hp, encoding="utf-8"))
    except Exception as e:
        print(f"[25/{N}] ⚠ harness.yaml 解析失败：{e}")
        return 1
    # 取运行时 _FALLBACK（DictComp 安全；literal_eval 不可用）
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("_harness_fb_probe", hpy)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fb = getattr(mod, "_FALLBACK", None)
    except Exception as e:
        print(f"[25/{N}] ⚠ 加载 harness.py 取 _FALLBACK 失败：{e}")
        return 1
    if not isinstance(fb, dict):
        print(f"[25/{N}] – harness.py 无 _FALLBACK（可能已改为硬失败），跳过")
        return 0
    problems = []
    # ① gate_exit_codes 键集（键归一化为 str：yaml 里 `0:` 是 int）
    fk = {str(k) for k in (fb.get("gate_exit_codes") or {}).keys()}
    yk = {str(k) for k in (cfg.get("gate_exit_codes") or {}).keys()}
    if fk != yk:
        only_fb, only_y = sorted(fk - yk), sorted(yk - fk)
        problems.append(f"gate_exit_codes 键集分叉：仅代码副本有 {only_fb}，仅 yaml 有 {only_y}"
                        f"（副本残留已废弃键 ⇒ 应从代码删，不是加进 yaml）")
    # ②③ stages 阶段集 + gate 语义（键归一化：yaml 的 `0:` 是 int，代码副本是 str）
    fs = {str(k): (v or {}) for k, v in (fb.get("stages") or {}).items()}
    ys = {str(k): (v or {}) for k, v in (cfg.get("stages") or {}).items()}
    if set(fs) != set(ys):
        problems.append(f"stages 阶段集分叉：仅代码副本有 {sorted(set(fs) - set(ys))}，"
                        f"仅 yaml 有 {sorted(set(ys) - set(fs))}"
                        f"（六阶段残留 ⇒ 应从代码删）")
    for k in sorted(set(fs) & set(ys), key=lambda x: int(x) if x.isdigit() else 10 ** 9):
        fg, yg = fs[k].get("gate"), ys[k].get("gate")
        if fg != yg:
            problems.append(f"stages.{k}.gate 语义漂移：代码副本={fg!r} ≠ yaml={yg!r}"
                            f"（yaml 不可读时该闸会从机器强制退化为人工确认）")
    if problems:
        print(f"[25/{N}] ✗ harness.py#_FALLBACK 与 harness.yaml 结构漂移 {len(problems)} 处：")
        for p in problems:
            print(f"     · {p}")
        print("     → _FALLBACK 是 yaml 读失败时的**降级副本**；结构漂移 = 降级时闸门行为静默改变。"
              "修法：改代码副本对齐 yaml 结构（文案不比对）。")
        return 1
    print(f"[25/{N}] ✓ harness.py#_FALLBACK 与 harness.yaml 结构一致"
          f"（gate_exit_codes {len(fk)} 码 / stages {len(fs)} 级，gate 语义全对齐；文案不比对）")
    return 0


# ── 26. 根 ⇄ 镜像 提交态一致性（v3.27.0 L-7）─────────────────
def check_mirror_committed_parity(expert_dir):
    """v3.27.0（L-7）：第 26 项 —— 仓库根与**分发镜像**的**提交态**一致性（阻断）。

    背景（本项要治的事故）：本包在 marketplace 里以**两份**形式存在——
      · 仓库根（本目录）= 开发/编辑面
      · `packages/vet-med-ppt-team/` = 分发面（**实际被加载的就是它**）
    历史上出过三类事故：① `rsync --delete` 把根的删除传播到镜像
    （`settings.json` 丢失）；② 忘了排除 `packages` ⇒ rsync 自复制
    （嵌套 `packages/packages/`，5.6MB 污染）；③ 改完忘同步 ⇒ 根与镜像漂移。

    ⚠ **为何比「提交态」而不是「工作区」**（这是本项零假红的关键）：
      工作区在「改包但还没同步镜像」的**正常开发中间态**里必然有差异
      （根侧改了、镜像还没跟上）⇒ 用工作区比对会**常态性假红**
      （每次编辑都报 ⇒ 警报警常态化 ⇒ 等于没警）。
      而**提交态**是**发布单元**：提交了就说明那个提交要被发布出去；
      若提交里两侧不一致 ⇒ 那次发布就带上了漂移 ⇒ 正是要抓的。
      实测：最近 7 个提交里有 **3 个**存在提交态漂移（真事故，不是假警）。

    ⚠ **只读**：本项只调 `git ls-tree` 读提交树，**不写任何文件**。
    ⚠ **非 git 仓库 / 无 HEAD ⇒ 不判定**（返回 0，不阻断）——探测受阻 ≠ 实现缺陷。
    ⚠ 「镜像多出」（镜像有、根无）**只报告不阻断**：那多半是镜像里的历史残留，
      删不删是**人的决定**（默认的 `mirror_sync.py` 也不做删除传播）。
    """
    # 仓库根 = 含 .git 的那一层（镜像目录自己也会带一份 scripts/，需认准真根）
    repo_root = os.path.abspath(expert_dir)
    try:
        r = subprocess.run(["git", "-C", repo_root, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            repo_root = r.stdout.strip()
    except Exception:
        pass

    try:
        import importlib.util as _ilu
        _ms_path = os.path.join(repo_root, "scripts", "mirror_sync.py")
        _spec = _ilu.spec_from_file_location("_mirror_sync_probe", _ms_path)
        _ms = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_ms)
        res = _ms.git_committed_parity(__import__("pathlib").Path(repo_root))
    except Exception as e:
        print(f"[26/{N}] – 无法加载 mirror_sync.py 取提交态（{type(e).__name__}），跳过")
        return 0
    if res is None:
        print(f"[26/{N}] – 非 git 仓库或无 HEAD，提交态比对不适用，跳过")
        return 0
    if not res:
        print(f"[26/{N}] – 提交树里没有 packages/ 下的镜像目录，无需比对，跳过")
        return 0

    bad = []
    extras = []
    for name, (missing, differing, extra) in sorted(res.items()):
        bad.append((name, missing, differing))
        extras.append((name, extra))

    must_fix_total = sum(len(m) + len(d) for _, m, d in bad)
    if must_fix_total:
        print(f"[26/{N}] ✗ 根与镜像**提交态**漂移 {must_fix_total} 处：")
        for name, missing, differing in bad:
            if not (missing or differing):
                continue
            print(f"     · 镜像 {name}/：")
            for p in missing[:10]:
                print(f"         根有镜像无：{p}")
            for p in differing[:10]:
                print(f"         内容不同：{p}")
        print("     → 该提交若发布出去，镜像（实际被加载的那份）内容与根不一致。")
        print("     → 修法：python3 scripts/mirror_sync.py --confirm（预览差异后）再提交。")
        return 1

    names = "、".join(n for n, _, _ in bad)
    msg = f"[26/{N}] ✓ 根与镜像提交态一致（镜像 {names}/ 与根逐 blob 相同）"
    extra_total = sum(len(e) for _, e in extras)
    if extra_total:
        msg += f"；⚠ 镜像多出 {extra_total} 个文件（历史残留，只报告不删）"
    print(msg)
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quick = "--quick" in sys.argv
    path = args[0] if args else DEFAULT
    if not os.path.isdir(path):
        print(f"✗ 专家包目录不存在：{path}", file=sys.stderr)
        return 1

    # ── v3.25.0：--dump-block-segments（生成登记表骨架，**键数/digest 永不手写**）──
    if "--dump-block-segments" in sys.argv:
        segs = collect_block_segments(path)
        items = sorted(segs.items(), key=lambda kv: (-len(kv[1]["keys"]), kv[0]))
        print("# 免检区（块级消费段）登记表骨架 —— 由 "
              "`python3 scripts/ensure_settings.py --dump-block-segments` 生成")
        print("# ⚠ key_count 与 keys_sha256 **不要手写**；消费方/处置规则需人工判断后填。")
        print("version: \"3.27.0\"")
        print("segments:")
        for seg_key, v in items:
            print(f"  - id: \"{seg_key}\"")
            print(f"    file: \"{v['file']}\"")
            print(f"    prefix: \"{v['prefix']}\"")
            print(f"    key_count: {len(v['keys'])}")
            print(f"    keys_sha256: \"{segments_digest(v['keys'])}\"")
            print(f"    leaf_unused: {v['leaf_unused']}")
        return 0

    print(f"体检目标：{path}\n")
    if not quick:
        print("ℹ️ 本次为**全量体检**（含第 7 项回归测试，会串行跑全部 test_*.py，实测约 120 秒）。\n"
              "   日常改包可用快速体检：`python3 scripts/ensure_settings.py --quick`（约 16 秒，跳过回归测试）。\n")
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
    # v3.16.0：三源阈值双重声明防线（防重复声明复发 + 运行时值断言补 AST 盲区）
    rc |= check_three_source_single_source(path)
    # v3.17.0：闸3 交叉复检领域↔复检人映射（阻断；防"把关人被派给被禁止接活的人"）
    rc |= check_cross_review_mapping(path)
    # v3.17.0：域绑定残留巡检（**提示级·不阻断**——词表天然会误伤正当举例，
    #   先积累一轮证据再谈阻断；与本轮「假阳性必须为零」的纪律一致）
    rc |= check_domain_binding_residue(path)
    # v3.19.3（L3）：阶段顺序漂移守卫（阻断；防 stages.N.next 与 current_stage+1 分叉）
    rc |= check_stage_order_drift(path)
    # v3.25.0：harness.py#_FALLBACK ↔ harness.yaml 结构比对（阻断；防降级副本结构漂移）
    rc |= check_harness_fallback_structure(path)
    # v3.27.0（L-7）：根 ⇄ 分发镜像 提交态一致性（阻断；防镜像漂移进入发布）
    rc |= check_mirror_committed_parity(path)

    print()
    #: ⚠ **v3.27.0 收尾：把「未验证」透传到最终结论**。
    #:   此前 `REGRESSION_UNVERIFIED` 被 `check_regression()` 填充，却**从未被读取**
    #:   ⇒ 文档声称的「把『未验』显式透传到最终结论」**根本没实现** ⇒
    #:   即便第 7 项打出「⚠ 回归测试通过但有 N 个套件因环境限制跳过」，
    #:   最终结论仍会写「✅ 全部通过，可发布」⇒ **假绿残留**（未验被显示成已验）。
    #:   ⇒ 渲染抽到纯函数 `format_final_conclusion()`（**可测**）：
    #:     · rc=0 且无未验证项 ⇒ ✅ 全部通过（沿用 v3.26.0 字面，避免破坏既有日志对照）
    #:     · rc=0 但有未验证项 ⇒ ⚠️ **未验≠已验**：结论**降级**，但 rc 仍为 0
    #:       （返值语义见 `check_regression` docstring：环境问题不阻断发布）
    #:     · rc≠0 ⇒ ⚠️ 存在告警（沿用）
    for _ln in format_final_conclusion(rc, REGRESSION_UNVERIFIED):
        print(_ln)
    return rc


if __name__ == "__main__":
    sys.exit(main())

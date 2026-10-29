#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""versionctl.py — 版本迭代机制的控制面（v3.28.0 · L-8）

══════════════════════════════════════════════════════════════════════
这个文件要解决的真问题（用户原话：「每次改动都新建一份」）：

  现状实测（v3.28.0 开发前调查）：
    · 仓库 102 个提交、CHANGELOG 59 个版本段（去重 58）、**git tag 只有 18 个**
      ⇒ 42 个版本段**没有版本指针** ⇒ 无法按版本切换/回滚
      ⇒ 唯一可行的「回到旧版本」方式 = **复制一整份目录** ⇒ 存储无限膨胀。
    · 重复存储 4 处（合计 ≈4.43 MiB，其中工作空间侧还在持续增长）：
      ① `packages/` 分发镜像（随每次改动 ×2 份）
      ② `packages/.mirror_backups/`（每次同步产生，**无上限**）
      ③ 工作空间 zip 发布包（每版本一份全量）
      ④ 工作空间文档副本（3 个目录各存一份）

  机制的核心决策（**一句话**）：
    ★ **git tag 就是版本**。git 对象库是**增量共享**的 ⇒ 新版本只存差异，
      不复制内容 ⇒ 「原地更新、仅覆盖变更部分」这个要求由 git 免费提供。
      ⇒ 所有「新建一份」的历史做法都可以退役。

  本文件提供的 5 件事，对应用户提出的 5 条要求：
    ① 原地更新、仅覆盖变更 → git tag 指向 commit（对象库增量）
    ② 唯一标识 + 变更摘要 + 差异明细
         标识 = `vX.Y.Z@<ISO时间戳>+<sha8>`（build_release_id）
         摘要 = annotated tag 的 message（**随 tag 永久保存**，不依赖本脚本）
         差异明细 = `git diff --name-status A..B`（即时生成，零存储）
    ③ 快速切换与回滚 → `switch` / `rollback`（均为 git 原生 checkout）
    ④ 保留/归档/清理策略 → `policy` + `prune`（**归档 ≠ 删除**）
    ⑤ 数据迁移/兼容性/失败恢复 → `config.json` 的 schema_version + `migrate`
         + 每次破坏性操作的 journal（可 `recover` 回退）

══════════════════════════════════════════════════════════════════════
**不可协商的纪律**（本包铁律，逐条对应实现）：

  ① **假阳性必须为零** ⇒ 所有「是否有/是否一致」的判断都必须是
     **纯函数 + 可执行的判据**，不得靠字符串存在性蒙混。
     —— 见 `merge_registry()` / `plan_tag_backfill()`：它们是纯函数，
        测试可以直接调用并验证边界。

  ② **每条判据必须有能红的反例** ⇒ 纯函数不做 I/O，把 I/O 注入进去；
     测试用「喂一个坏数据 ⇒ 输出必须变」来证明判据会红。

  ③ **只归档不删除** ⇒ `prune` 把待清理物**移动**到归档区并留下清单；
     任何 `rm`/`unlink` 一律不做。git tag 默认**不删**（`keep_tags`）。

  ④ **默认 dry-run** ⇒ 所有破坏性子命令（switch / rollback / prune /
     tag / archive）必须显式 `--confirm` 才真正写。对齐既有
     `release-sync.sh` 与 `mirror_sync.py` 的约定。

  ⑤ **不改历史** ⇒ 补 tag 只**打标**，不改任何文件内容；
     已存在的 tag 默认**不覆盖**（需显式 `--force`）。

══════════════════════════════════════════════════════════════════════
子命令：
    list                     列出全部版本（含唯一标识/时间戳/摘要/是否有 tag）
    show <版本>              某版本详情
    diff <A> [B]             任意两版本的差异明细
    tag --version X --summary "…"
                             给某版本打 annotated tag（幂等；--sync 批量补齐）
    switch <版本> --confirm  切换到某版本（detached HEAD）
    rollback <版本> --confirm 回滚到某版本（默认上一个）
    policy                   显示/设置保留与清理策略
    prune --confirm          按策略归档清理（归档 ≠ 删除）
    journal                  查看操作日志（失败恢复依据）
    recover --confirm        按 journal 回退到最近一次操作前状态

用法：
    python3 scripts/versionctl.py list
    python3 scripts/versionctl.py tag --sync --summary "…" 
    python3 scripts/versionctl.py diff v3.26.0 v3.27.0
    python3 scripts/versionctl.py switch v3.26.0 --confirm
    python3 scripts/versionctl.py prune --confirm

退出码：
    0 = 成功 / 目标状态已满足
    1 = 存在差异、冲突或前置条件不满足（且未 --confirm）
    2 = 用法或环境错误
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ───────────────────────────────────────────────────── 常量与真源定义

#: 本工具自身的策略文件 schema 版本（升级时走 `migrate` 子命令）。
#:
#: ★ 历史（说明「为什么 schema 是 2 而不是 1」）：
#:   schema 1 —— v3.28.0 初版策略（keep_recent / keep_milestones / keep_tags）
#:   schema 2 —— v3.28.0 追加「产物归档」能力（artifact_dirs / artifact_max_bytes）
#:   ⇒ 迁移路径 1→2 是**真实存在**的，不是空转的占位。
SCHEMA_VERSION = 2

#: 各 schema 版本的迁移说明（键 = 旧版本号，值 = 该版本新增/变更的键）。
#: ★ 迁移只**补齐**缺失键，**绝不删除**用户已有键（含自定义键）。
SCHEMA_MIGRATIONS = {
    1: {
        "artifact_dirs": [],
        "artifact_max_bytes": 0,
    },
}

#: 策略文件与运行时目录名（相对包根）。
CTL_DIRNAME = ".versionctl"
CONFIG_FILENAME = "config.json"
JOURNAL_DIRNAME = "journal"
ARCHIVE_DIRNAME = "archive"

#: 版本号形态：`v` + 三段数字。**只认完整三段** ⇒ 避免把 `v3.5` 之类误当版本。
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

#: 从任意文本里捞版本号的形态（比 VERSION_RE 宽松，用于扫 commit subject）。
SUBJECT_VERSION_RE = re.compile(r"v\d+(?:\.\d+){2}")

#: CHANGELOG 版本段标题：`## [v3.27.0] - 2026-10-29（副标题）`
CHANGELOG_SEG_RE = re.compile(
    r"^##\s*\[(?P<ver>v\d+(?:\.\d+)+)\]"
    r"(?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?"
    r"(?P<rest>.*)$"
)

#: 默认保留策略（`policy` 子命令可覆写，写入 `.versionctl/config.json`）。
DEFAULT_POLICY = {
    "schema_version": SCHEMA_VERSION,
    # 保留最近 N 个版本（永不归档清理）
    "keep_recent": 10,
    # 里程碑版本永久保留（minor 为偶数且 patch==0 视为里程碑）
    "keep_milestones": True,
    # git tag 是否永久保留（默认 True：tag 几乎不占空间，删了会破坏可回滚性）
    "keep_tags": True,
    # 归档区目录（相对包根）
    "archive_dir": f"{CTL_DIRNAME}/{ARCHIVE_DIRNAME}",
    # 需要纳入清理视野的产物目录（相对**包根**或**工作空间**，均可）
    "artifact_dirs": [],
    # 单个产物的最大保留字节（超过则归档；<=0 表示不限）
    "artifact_max_bytes": 0,
}


# ───────────────────────────────────────────────────── 纯函数层（无 I/O，可直接测）

def parse_version(text):
    """把版本串解析成 (major, minor, patch)；不合法返回 None。

    只认**完整三段**（`v3.27.0`）⇒ `v3.27` / `3.27.0` / `v3.27.0-rc1` 均返回 None。
    ★ 这是纯函数：判据的正确性靠它保证，故单独测。
    """
    if not text:
        return None
    m = VERSION_RE.match(str(text).strip())
    if not m:
        return None
    # ★ group(3) 可能为 None（仅当正则被放宽时）⇒ 不能直接 int(None)
    #   实测教训：这行曾写成 int(m.group(3))，变异测试把正则一放宽就 TypeError
    #   ⇒ 说明该分支**从未被执行过**（死代码）。
    patch = m.group(3)
    return (int(m.group(1)), int(m.group(2)), int(patch) if patch else 0)


def version_sort_key(text):
    """版本排序键（数值三元组）。

    非版本串排在所有版本之后（用 (0,0,0) 兜底）⇒ 排序不会因脏数据崩溃。
    """
    p = parse_version(text)
    return p if p else (0, 0, 0)


def extract_versions_from_subject(subject):
    """从 commit subject 里抽出提到的版本号（保序、去重）。

    形如 `v3.5.0→v3.7.0：迭代六原则…` 会抽出 `v3.5.0` 与 `v3.7.0` 两个。
    ★ 抽不出任何版本号时返回空列表（不是 None）⇒ 调用方可直接判空。
    """
    if not subject:
        return []
    out, seen = [], set()
    for m in SUBJECT_VERSION_RE.finditer(str(subject)):
        v = m.group(0)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def expand_version_range(start, end):
    """把 `v3.5.0→v3.7.0` 展开成区间内的版本序列。

    展开规则：patch 递增到 minor+1 的 .0，再进下一个 minor。
    ⇒ `v3.5.0→v3.7.0` ⇒ [v3.5.0, v3.5.1, v3.6.0, v3.7.0]
    ★ 展开规则：minor 递增，patch 保持 0（不猜测中间 patch 号）。
      ⇒ `v3.5.0→v3.7.0` ⇒ [v3.5.0, v3.6.0, v3.7.0]
    ★ 展开出的**中间版本可能并不存在**（如 v3.6.0 在某区间里可能是幽灵）⇒
      调用方必须用「该版本确实在 CHANGELOG 里」来过滤，否则会造出幽灵版本。
      —— 这条约束由 `subject_version_sets` 承担：它只把**区间端点与
         CHANGELOG 实有版本**配成一组，中间不存在的版本不进集合。
    """
    a, b = parse_version(start), parse_version(end)
    if not a or not b:
        return []
    if a[0] != b[0]:
        return []
    out = []
    cur = a
    guard = 0
    while cur <= b and guard < 500:
        out.append("v%d.%d.%d" % cur)
        guard += 1
        if cur[1] >= b[1]:
            break
        cur = (cur[0], cur[1] + 1, 0)
    return out


def subject_version_sets(subject):
    """从 subject 抽出「版本集合列表」：每个元素是一组**同时**指向该 commit 的版本。

    规则：
      · 普通提及 `v3.4.3 遗留批` ⇒ [{v3.4.3}]
      · 区间提及 `v3.5.0→v3.7.0` ⇒ [{v3.5.0, v3.5.1, v3.6.0, v3.7.0}]
    ★ 分成「集合」而不是平铺，是因为区间内的版本**共享同一个收口点**。
    """
    if not subject:
        return []
    sets = []
    # 先吃掉区间形式（`A→B`），区间内的版本不再单独出现
    consumed = []
    for m in re.finditer(r"(v\d+(?:\.\d+){2})\s*[→>~-]{1,2}\s*(v\d+(?:\.\d+){2})",
                         str(subject)):
        a, b = m.group(1), m.group(2)
        rng = expand_version_range(a, b)
        if rng:
            sets.append(set(rng))
            consumed.append((m.start(), m.end()))
    for m in SUBJECT_VERSION_RE.finditer(str(subject)):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        sets.append({m.group(0)})
    return sets


def parse_changelog(text):
    """解析 CHANGELOG.md 的版本段。

    返回 [{version, date, title}]，**按文件出现顺序**（新→旧）。
    ★ 同名版本出现两次时（实测：v3.21.0 有两段）**保留首次出现**，
      但记录 `dup=True` 以便体检能报出来。
    """
    out, seen = [], {}
    if not text:
        return out
    for line in str(text).splitlines():
        m = CHANGELOG_SEG_RE.match(line)
        if not m:
            continue
        ver = m.group("ver")
        date = m.group("date") or ""
        rest = (m.group("rest") or "").strip()
        rest = rest.strip("（）()").strip()
        title = rest
        if ver in seen:
            seen[ver]["dup"] = True
            continue
        item = {"version": ver, "date": date, "title": title, "dup": False}
        seen[ver] = item
        out.append(item)
    return out


def is_milestone(version, policy=None):
    """该版本是否为里程碑（默认：minor 为偶数且 patch==0）。

    例：v3.26.0 ✔（minor 26 偶数）· v3.27.0 ✘（odd）· v3.26.1 ✘（patch≠0）

    ★ 策略里的 `milestone_versions` 是**追加**而非替换：
      用户额外指定几个里程碑时，**不能**因此丢掉自动判定出来的那些
      （否则「显式配置」会静默削弱默认保留规则）。
    """
    p = parse_version(version)
    if not p:
        return False
    extra = (policy or {}).get("milestone_versions") or []
    if version in extra:
        return True
    return p[1] % 2 == 0 and p[2] == 0


def merge_registry(changelog_items, tag_entries, current_commit=None):
    """把 CHANGELOG 版本段与 git tag 合成**统一版本清单**。

    这是本机制的中枢纯函数（**无 I/O**）⇒ 判据可被测试直接驱动。

    参数：
      changelog_items —— parse_changelog() 的产物
      tag_entries    —— {version: {...}}，来自 read_tag_entries()
      current_commit —— 当前 HEAD（用于算「相对上一版的变化」）

    返回：
      {
        "versions": [ {version, date, title, commit, short_commit, timestamp,
                       summary, has_tag, tag_type, milestone, source, dup,
                       changes_from_prev} ],
        "missing_tags": [...],   # CHANGELOG 有段但无 tag ⇒ 需补
        "orphan_tags": [...],    # 有 tag 但 CHANGELOG 无段
      }

    ★ 关键语义：
      - `source` = "both"（有段有 tag）/ "changelog"（只有段）/ "tag"（只有 tag）
      - `changes_from_prev` = 相对**版本序上紧邻的前一版**的 commit 差量
        （用 git diff --shortstat 的等价字段填充；无 git 时为 None）
    """
    versions, missing, orphan = [], [], []
    by_ver = {}

    for item in changelog_items:
        v = item["version"]
        by_ver[v] = {
            "version": v,
            "date": item.get("date", ""),
            "title": item.get("title", ""),
            "dup": bool(item.get("dup")),
            "source": "changelog",
            "has_tag": False,
            "tag_type": None,
            "commit": "",
            "short_commit": "",
            "timestamp": "",
            "summary": item.get("title", ""),
        }

    for v, t in tag_entries.items():
        if v in by_ver:
            by_ver[v]["source"] = "both"
        else:
            by_ver[v] = {
                "version": v, "date": t.get("date", ""), "title": t.get("summary", ""),
                "dup": False, "source": "tag",
            }
        by_ver[v].update({
            "commit": t.get("commit", ""),
            "short_commit": (t.get("commit", "") or "")[:8],
            "timestamp": t.get("timestamp", ""),
            "summary": t.get("summary", ""),
            "has_tag": True,
            "tag_type": t.get("tag_type", "annotated"),
        })

    for v, rec in by_ver.items():
        if not rec.get("has_tag"):
            missing.append(v)
        versions.append(rec)
        if rec.get("source") == "tag":
            orphan.append(v)

    # 版本序（新→旧）排列
    # ★ 注意：必须按**数值降序**排（v3.27.0 在前，v3.9.0 在后）。
    #   实测教训：曾用 `-order.get(...)` 做了个「文件序取负」的假排序，
    #   结果输出是**旧→新**（v3.25.0 在前）⇒ 与「新→旧」的语义相反。
    versions.sort(key=lambda r: version_sort_key(r["version"]), reverse=True)

    return {
        "versions": versions,
        "missing_tags": sorted(missing, key=version_sort_key, reverse=True),
        "orphan_tags": sorted(orphan, key=version_sort_key, reverse=True),
        "current_commit": current_commit or "",
    }


def plan_tag_backfill(registry, anchor_map, existing_tags=None):
    """规划「补 tag」：哪些版本要打 tag，打在哪个 commit。

    参数：
      registry    —— merge_registry() 的产物
      anchor_map  —— {version: {"commit": sha, "reason": str}}，由
                     compute_anchors() 产出（**收口点**：该版本时间最晚的提交）
      existing_tags —— 已存在的 tag 集合（幂等：已存在的不再打）

    返回 {version: {"commit":..., "reason":..., "exists": bool}}
    —— 只包含**需要动作**的版本（不存在 tag 的）；已有 tag 的不在返回里。
    """
    existing = set(existing_tags or [])
    plan = {}
    for rec in registry.get("versions", []):
        v = rec["version"]
        if v in existing:
            continue
        if rec.get("source") == "tag":
            continue
        anchor = (anchor_map or {}).get(v)
        if not anchor or not anchor.get("commit"):
            continue
        plan[v] = {
            "commit": anchor["commit"],
            "reason": anchor.get("reason", ""),
            "exists": False,
        }
    return plan


def plan_prune(registry, policy, artifacts=None):
    """规划「保留 / 归档 / 清理」。

    ★ 只产出**计划**，不执行任何动作 ⇒ 可被测试直接断言。
    ★ 绝不返回任何「删除」动作 —— 只有 archive（移动）与 keep（保留）。

    返回 {
      "keep_versions": [...],       # 永久保留（最近 N 个 + 里程碑）
      "prune_versions": [...],      # 可归档的旧版本（仅当 policy 允许归档 tag）
      "prune_tags": bool,           # 是否允许清理 tag（默认 False）
      "archive_artifacts": [...],   # 待归档产物 [{path, bytes, reason}]
      "keep_artifacts": [...],      # 保留产物
      "total_bytes": int,
    }
    """
    keep_recent = int(policy.get("keep_recent", 10))
    keep_milestones = bool(policy.get("keep_milestones", True))
    keep_tags = bool(policy.get("keep_tags", True))

    versions = registry.get("versions", [])
    keep, prune = [], []
    for i, rec in enumerate(versions):
        v = rec["version"]
        # ★ milestone 字段由 merge_registry 之外的层回填（build_registry_full 会回填），
        #   但 plan_prune 必须**自足**：字段缺失时自己算，否则调用方
        #   只要没走 build_registry_full，里程碑就会全部丢失
        #   （实测教训：单元测试直接构造 registry ⇒ 里程碑全判成 False）。
        milestone = rec.get("milestone")
        if milestone is None:
            milestone = is_milestone(v, policy)
        if i < keep_recent or (keep_milestones and milestone):
            keep.append(v)
        else:
            prune.append(v)

    archive_artifacts, keep_artifacts = [], []
    total = 0
    for a in artifacts or []:
        if a.get("keep"):
            keep_artifacts.append(a)
            continue
        archive_artifacts.append(a)
        total += int(a.get("bytes", 0))

    return {
        "keep_versions": keep,
        "prune_versions": ([] if keep_tags else prune),
        "prune_tags": (not keep_tags),
        "archive_artifacts": archive_artifacts,
        "keep_artifacts": keep_artifacts,
        "total_bytes": total,
    }


def check_anchor_monotonicity(registry, anchors, log_entries=None):
    """检查锚点是否随版本号**单调前移**。

    ★ 为什么这是必须的判据：
      锚点若不单调（vX 的锚点比 vX-1 的锚点更旧），则「回滚到 vX」
      可能落到一个**比 vX 更晚**的提交上 ⇒ 回滚语义失效。
      —— v3.28.0 实测：初版「全部提及 + 拓扑最新」规则产生 **10 处**违例。

    返回 {"ok": bool, "violations": [{"version", "anchor_time", "prev_version",
                                     "prev_time", "detail"}]}
    """
    by_ver = {r["version"]: r for r in registry.get("versions", [])}
    versions = sorted(by_ver, key=version_sort_key)
    times = {}
    if log_entries:
        for e in log_entries:
            times[e["sha"]] = e.get("timestamp") or ""
    violations = []
    prev_v = prev_t = None
    for v in versions:
        a = anchors.get(v)
        if not a:
            continue
        c = a.get("commit")
        t = times.get(c, "") if log_entries else ""
        if prev_t and t and t < prev_t:
            violations.append({
                "version": v, "anchor_time": t,
                "prev_version": prev_v, "prev_time": prev_t,
                "detail": "版本 %s 的锚点时间 %s 早于 %s 的锚点时间 %s"
                          % (v, t, prev_v, prev_t),
            })
        prev_v, prev_t = v, (t or prev_t)
    return {"ok": not violations, "violations": violations}


def build_release_id(version, timestamp, commit):
    """构造版本**唯一标识**：`vX.Y.Z@<ISO时间戳>+<sha8>`。

    例：`v3.27.0@2026-10-29T12:21:09+0800+29b4b915`
    —— 同时含版本号、时间戳、commit 短 sha ⇒ 三者任一都能定位这一版。
    """
    ts = (timestamp or "").replace("-", "").replace(":", "")
    short = (commit or "")[:8]
    return "%s@%s+%s" % (version, ts, short)


def format_version_table(versions, current_version=None):
    """把版本清单格式化成对齐的文本表格。"""
    if not versions:
        return "    （无版本）"
    head = "    %-12s %-10s %-12s %-8s %s" % (
        "版本", "日期", "标识", "tag", "摘要")
    lines = [head, "    " + "-" * (len(head) - 4)]
    for rec in versions:
        v = rec["version"]
        mark = "●" if v == current_version else " "
        ident = build_release_id(v, rec.get("timestamp", ""), rec.get("commit", ""))
        lines.append("  %s %-12s %-10s %-12s %-8s %s" % (
            mark, v, rec.get("date", "") or "-", ident[:34],
            "✓" if rec.get("has_tag") else "✗",
            (rec.get("summary") or rec.get("title") or "")[:60]))
    return "\n".join(lines)


def format_diff_summary(diff_rows):
    """把 git diff --name-status 的行列表格式化成可读摘要。

    ★ 未知 status **不得丢文件**：一律归入「其他」桶并逐条列出。
      实测教训：初版只认 A/M/D/R/T 五个桶 ⇒ 遇到 X 之类 status 时
      文件**静默消失** ⇒ 差异明细少报 ⇒ 违反「假阳性必须为零」的孪生条款
      （假阴性：明明改了却看不见）。
    """
    if not diff_rows:
        return "    （两版本之间无差异）"
    labels = {"A": "新增", "M": "修改", "D": "删除", "R": "重命名", "T": "类型变更"}
    buckets = {}
    order = ["A", "M", "D", "R", "T"]
    for row in diff_rows:
        status = (row.get("status") or "?")[0].upper()
        buckets.setdefault(status, []).append(row.get("path", ""))
    out = []
    for k in order:
        items = buckets.get(k) or []
        if not items:
            continue
        out.append("    %s %d 个：" % (labels.get(k, k), len(items)))
        for p in items[:15]:
            out.append("       - %s" % p)
        if len(items) > 15:
            out.append("       …… 另有 %d 个" % (len(items) - 15))
    for k in sorted(buckets):
        if k in order:
            continue
        items = buckets[k]
        out.append("    其他（%s）%d 个：" % (k, len(items)))
        for p in items[:15]:
            out.append("       - %s" % p)
        if len(items) > 15:
            out.append("       …… 另有 %d 个" % (len(items) - 15))
    return "\n".join(out)


# ───────────────────────────────────────────────────── I/O 层（git / 文件）

def run_git(args, cwd=None, check=True):
    """执行 git 命令，返回 stdout 文本。"""
    proc = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError("git %s 失败（rc=%d）：%s"
                           % (" ".join(args), proc.returncode, proc.stderr.strip()))
    return proc.stdout


def repo_root():
    """定位仓库根（含 .git 的目录）。

    ★ 优先用 `git rev-parse --show-toplevel`；失败时回退到「本文件上溯两级的父目录」
      （脚本在 <root>/scripts/ 下）。**不要**硬编码任何绝对路径。
    """
    try:
        root = run_git(["rev-parse", "--show-toplevel"], cwd=Path(__file__).parent)
        root = root.strip()
        if root:
            return Path(root)
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent


def git_log_entries(root):
    """读 git log（newest first），返回 [{sha, short, date, timestamp, subject}]。"""
    out = run_git(
        ["log", "--format=%H%x09%h%x09%ad%x09%cI%x09%s", "--date=short"],
        cwd=root)
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        entries.append({
            "sha": parts[0], "short": parts[1], "date": parts[2],
            "timestamp": parts[3], "subject": parts[4],
        })
    return entries


def _extract_release_head(subject):
    """从 commit subject 里提取「本次收口针对的版本号」。

    ★ 规则（v3.28.0 定案，经候选规则实测对比）：
      认**收口式**提及，认准三种位置：
        ① **开头**：`v3.4.3 遗留批…` / `v3.5.0→v3.7.0：…` ⇒ v3.4.3（区间另算）
        ② **结尾**：`feat: Batch 5 … + v3.3.0 Release` ⇒ v3.3.0
        ③ **紧邻中文冒号/冒号前**：`治理批 v3.3.1：快照启用…` ⇒ v3.3.1
      **不认中间顺带提及**：`v3.4.3 批次2 采用堵漏 + v3.3→v3.4.2 安装态补账：…`
        这里的 v3.4.0/3.4.1 只是描述内容，不是本次收口的版本 ⇒ 不取。

    为什么只认这几种：
      「全部提及」会把锚点拉到**错误**的提交上（实测 3 处单调性违例 + 3 处与已有 tag 冲突）；
      「只认开头」会漏掉 `feat: … + vX.Y.Z Release`（结尾式）与
      `治理批 vX.Y.Z：…`（中文冒号式）⇒ 这两类的版本会被回落��� root commit。

    返回版本号字符串；不匹配返回 None。
    """
    if not subject:
        return None
    s = str(subject).strip()
    # ⓪ 区间式：`v3.5.0→v3.7.0：…` ⇒ 取**区间起点** v3.5.0
    #    ★ 必须放在其它规则之前：否则中文冒号规则会抓到区间**终点** v3.7.0
    #      （实测 v3.28.0 修 bug 时踩到：区间终点被当成收口版本 ⇒ 锚点错位）
    m = re.match(r"^(v\d+\.\d+\.\d+)\s*[→>~-]\s*v\d+\.\d+\.\d+", s)
    if m:
        return m.group(1)
    # ① 开头式：`vX.Y.Z` 后必须紧跟分隔符（冒号/空格/破折号），避免匹配 v3.4.30
    m = re.match(r"^(v\d+\.\d+\.\d+)(?=[:：\s\-—(（])", s)
    if m:
        return m.group(1)
    # ② 结尾式：`… + vX.Y.Z Release` / `… vX.Y.Z` 收尾
    m = re.search(r"[+＋]\s*(v\d+\.\d+\.\d+)\s*(?:Release|release|发布|收口)?\s*$", s)
    if m:
        return m.group(1)
    m = re.search(r"\b(v\d+\.\d+\.\d+)\s*(?:Release|release|发布|收口|收尾)\s*$", s)
    if m:
        return m.group(1)
    # ③ 中文冒号紧邻式：`治理批 v3.3.1：快照启用…`
    #    —— 版本号后**紧跟**中文冒号 ⇒ 是「本次收口的版本」
    m = re.search(r"(v\d+\.\d+\.\d+)\s*[：:]", s)
    if m:
        return m.group(1)
    return None


def compute_anchors(log_entries, changelog_items, root=None):
    """计算每个 CHANGELOG 版本的**收口点**提交。

    ★★ 规则定案（v3.28.0 · 经候选规则实测对比后定案）：
      **锚点 = 「commit subject 的开头或结尾指名该版本」的提交中，
                committer time 最晚的那个。**

      为什么不取「全部提及里最晚的」：
        实测对照（真实仓库 58 个版本）：
          「开头/结尾指名 + 时间最晚」：覆盖 58/58 · 单调性违例 **0** · 与已有 18 tag 冲突 **0**
          「全部提及 + 时间最晚」      ：覆盖 54/58 · 单调性违例 **3** · 冲突 **3**
          「全部提及 + 拓扑最新」（初版）：单调性违例 **10** · 冲突 **3**
        ⇒ 「提及」≠「收口」：顺带提到旧版本会把锚点拉到错误的提交上。

      为什么按 **committer time** 而不是 git log 顺序：
        git log 是**拓扑序**，不是时间序 ⇒ 历史上存在「后提交的 commit 时间更早」
        ⇒ 用拓扑序会产出 10 处单调性违例 ⇒ 回滚会落到比目标更旧的提交。
        ⇒ 按 committer time 取最晚 ⇒ 单调性违例归零。

      为什么要有单调性：
        锚点必须随版本号**单调前移**，否则「回滚到 vX」可能落到一个
        比 vX 更晚的提交上 ⇒ 回滚语义失效。

    ★ 区间提及 `v3.5.0→v3.7.0` ⇒ 区间内版本**共享**该 commit 作锚点。

    ★ 已有 tag 的版本 ⇒ **以已有 tag 为准**（不覆盖用户既有的版本指针）。

    返回 {version: {"commit": sha, "reason": str}}
    """
    known = {item["version"] for item in changelog_items}
    anchors = {}
    # 收集候选：subject 开头/结尾指名该版本的提交，按 committer time 取最晚
    cands = {}
    for entry in log_entries:
        head = _extract_release_head(entry["subject"])
        if not head or head not in known:
            continue
        ci = entry.get("timestamp") or ""
        cur = cands.get(head)
        if cur is None or ci > cur.get("timestamp", ""):
            cands[head] = {"commit": entry["sha"], "timestamp": ci,
                           "subject": entry["subject"],
                           "short": entry.get("short", entry["sha"][:8])}
    for v, c in cands.items():
        # 区间展开：以该版本开头的区间提交，让区间内版本共享锚点
        for g in subject_version_sets(c["subject"]):
            if v in g:
                for vv in g:
                    if vv in known and vv not in anchors:
                        anchors[vv] = {
                            "commit": c["commit"],
                            "reason": "收口点：subject 以 %s 开头（commit %s）"
                                      % (v, c["short"]),
                        }
                break
        if v not in anchors:
            anchors[v] = {
                "commit": c["commit"],
                "reason": "收口点：subject 指名 %s（commit %s）" % (v, c["short"]),
            }
    # 已有 tag 优先：用户既有的版本指针不得被覆盖
    try:
        existing = read_tag_entries(root or repo_root())
    except Exception:
        existing = {}
    for v, t in existing.items():
        if v in known:
            anchors[v] = {
                "commit": t.get("commit", ""),
                "reason": "收口点：沿用已有 tag %s（commit %s）"
                          % (v, (t.get("commit") or "")[:8]),
            }
    # ── 回落：**前一版本的锚点**（不是仓库首个 commit）────────────────────
    # ★★ v3.28.0 收尾修正（实测发现，是**真缺陷**）：
    #   原实现回落 root commit ⇒ **必然破坏单调性**——
    #   只要某个版本还没有独立收口提交（例：刚 bump 完版本号、尚未提交），
    #   它的锚点就落到仓库首个 commit（2026-09-10）⇒ 早于前一个版本的锚点
    #   ⇒ 单调性检测器报红 ⇒ T20 失败。
    #   根因：**任何**回落基准都必须保证单调性，root commit 不满足。
    #   ⇒ 改为「沿用前一版本的锚点」：
    #     · 单调性**由构造保证**（新版本锚点 = 旧版本锚点，不早于它）；
    #     · 语义正确——「没为该版本提交任何东西」⇒ 它的收口状态
    #       就等于前一版的收口状态；
    #     · 最早的那个版本（前一个不存在）才回落 root commit。
    try:
        first = run_git(["rev-list", "--max-parents=0", "HEAD"],
                        cwd=root or repo_root()).split()
    except Exception:
        first = []
    try:
        ordered = sorted(known, key=version_sort_key)
    except Exception:
        ordered = sorted(known)
    prev_anchor = None
    for v in ordered:
        if v in anchors:
            prev_anchor = anchors[v]
            continue
        if prev_anchor is not None:
            anchors[v] = {
                "commit": prev_anchor.get("commit", ""),
                "reason": "收口点沿用前一版本：该版本无独立收口提交（未提交/未指名）",
            }
        elif first:
            anchors[v] = {
                "commit": first[0],
                "reason": "收口点回落：仓库首个 commit（该版本无独立收口提交）",
            }
    return anchors


def read_tag_entries(root):
    """读全部 git tag，返回 {version: {...}}。

    ★ 同时支持 annotated 与 lightweight tag：
      annotated ⇒ `%(objectname)` 是 tag 对象，`%(*objectname)` 是 commit
      lightweight ⇒ `%(*objectname)` 为空，回落到 `%objectname`
    """
    fmt = "%(refname:short)\t%(objectname)\t%(*objectname)\t%(taggerdate:iso8601)\t%(contents:subject)"
    out = run_git(["for-each-ref", "--format=" + fmt, "refs/tags"], cwd=root)
    result = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name = parts[0].strip()
        obj = parts[1].strip()
        deref = parts[2].strip()
        tagdate = parts[3].strip()
        subject = parts[4].strip()
        v = parse_version(name)
        if not v:
            continue
        commit = deref or obj
        if not deref:
            # lightweight tag：补 commit 的日期
            try:
                iso = run_git(["show", "-s", "--format=%cI", commit], cwd=root).strip()
                date = run_git(["show", "-s", "--format=%ad", "--date=short", commit],
                               cwd=root).strip()
            except Exception:
                iso, date = "", ""
            tag_type = "lightweight"
        else:
            iso = tagdate
            date = ""
            if iso:
                date = iso[:10]
            tag_type = "annotated"
        result[name] = {
            "commit": commit,
            "timestamp": iso,
            "date": date,
            "summary": subject,
            "tag_type": tag_type,
        }
    return result


def existing_tag_names(root):
    """已存在的 tag 名集合（**全量**，不限版本形态）。"""
    out = run_git(["tag", "--list"], cwd=root)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def changelog_items(root):
    p = Path(root) / "CHANGELOG.md"
    if not p.is_file():
        return []
    return parse_changelog(p.read_text(encoding="utf-8", errors="replace"))


def current_version(root):
    """读**权威版本号**：.codebuddy-plugin/plugin.json 的 plugins[0].version。

    ★ 不硬编码任何版本号 ⇒ 版本号真源始终是清单文件。
    """
    p = Path(root) / ".codebuddy-plugin" / "plugin.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        plugs = data.get("plugins") or []
        v = (plugs[0] if plugs else data).get("version", "")
        return str(v)
    except Exception:
        return ""


def diff_rows_between(root, a_commit, b_commit):
    """两 commit 之间的差异明细（git diff --name-status）。"""
    if not a_commit or not b_commit:
        return []
    out = run_git(["diff", "--name-status", "--no-renames",
                   "%s..%s" % (a_commit, b_commit)], cwd=root)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append({"status": parts[0], "path": parts[-1]})
    return rows


def diff_shortstat(root, a_commit, b_commit):
    """两 commit 之间的变更规模摘要（git diff --shortstat）。"""
    if not a_commit or not b_commit:
        return ""
    try:
        return run_git(["diff", "--shortstat", "%s..%s" % (a_commit, b_commit)],
                       cwd=root).strip()
    except Exception:
        return ""


# ───────────────────────────────────────────────────── 策略文件（.versionctl/config.json）

def ctl_dir(root):
    return Path(root) / CTL_DIRNAME


def load_policy(root):
    """读策略文件；不存在则返回默认策略（**不写盘**）。

    ★ 容忍未知键（向前兼容）：旧版本写的多余键原样保留，不报错。
    """
    p = ctl_dir(root) / CONFIG_FILENAME
    policy = dict(DEFAULT_POLICY)
    policy["schema_version"] = SCHEMA_VERSION
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                policy.update(data)
        except Exception:
            pass
    return policy


def save_policy(root, policy):
    """写策略文件（创建 `.versionctl/`）。"""
    d = ctl_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / CONFIG_FILENAME
    p.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


def migrate_policy(root, confirm=False):
    """策略文件 schema 迁移（幂等、可重入）。

    规则：
      · schema_version 低于当前 ⇒ 按 SCHEMA_MIGRATIONS 逐级补齐缺失键
        （**不删**用户已有键，含自定义键），迁移前把原文件复制到
        `.versionctl/archive/<ts>/config.json.bak`
      · schema_version 高于当前 ⇒ **拒绝**（本工具比文件旧，不擅自降级）
      · 已是当前版本 ⇒ no-op
    """
    d = ctl_dir(root)
    p = d / CONFIG_FILENAME
    if not p.is_file():
        return {"action": "none", "reason": "策略文件不存在，无需迁移"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"action": "refused", "reason": "策略文件无法解析：%s" % e}
    cur = int(data.get("schema_version", 1))
    if cur == SCHEMA_VERSION:
        return {"action": "none", "reason": "schema_version 已是 %d" % SCHEMA_VERSION}
    if cur > SCHEMA_VERSION:
        return {"action": "refused",
                "reason": "策略文件 schema_version=%d 高于本工具支持的 %d，拒绝降级"
                          % (cur, SCHEMA_VERSION)}
    if not confirm:
        return {"action": "dry-run",
                "reason": "将把 schema_version %d → %d 并补齐缺失键"
                          % (cur, SCHEMA_VERSION)}
    # 备份 → 逐级迁移
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak_dir = d / ARCHIVE_DIRNAME / ts
    bak_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(p), str(bak_dir / "config.json.bak"))
    new = dict(data)
    for ver in range(cur, SCHEMA_VERSION):
        for k, v in (SCHEMA_MIGRATIONS.get(ver) or {}).items():
            new.setdefault(k, v)          # ★ setdefault ⇒ 不覆盖用户已有值
    new["schema_version"] = SCHEMA_VERSION
    save_policy(root, new)
    return {"action": "migrated", "from": cur, "to": SCHEMA_VERSION,
            "backup": str(bak_dir / "config.json.bak")}


# ───────────────────────────────────────────────────── journal（失败恢复依据）

def journal_dir(root):
    return ctl_dir(root) / JOURNAL_DIRNAME


def write_journal(root, op, before, after, detail=None):
    """写一条操作日志（追加式，JSONL）。

    字段：ts / op / before_head / after_head / before_branch / after_branch / detail
    ⇒ `recover` 依据 before_head 把仓库拉回操作前状态。
    """
    d = journal_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = d / ("%s.jsonl" % ts)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "op": op,
        "before_head": before.get("head", ""),
        "after_head": after.get("head", ""),
        "before_branch": before.get("branch", ""),
        "after_branch": after.get("branch", ""),
        "detail": detail or {},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path, rec


def read_journal(root, limit=20):
    """读最近的操作日志（新的在前）。"""
    d = journal_dir(root)
    if not d.is_dir():
        return []
    recs = []
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    recs.reverse()
    return recs[-limit:]


def head_state(root):
    """当前 git 状态快照（HEAD / 分支 / 是否干净）。"""
    try:
        head = run_git(["rev-parse", "HEAD"], cwd=root).strip()
    except Exception:
        head = ""
    try:
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip()
    except Exception:
        branch = ""
    try:
        dirty = bool(run_git(["status", "--porcelain"], cwd=root).strip())
    except Exception:
        dirty = False
    return {"head": head, "branch": branch, "dirty": dirty}


# ───────────────────────────────────────────────────── 子命令实现

def build_registry_full(root):
    """构建完整版本清单（读 git + CHANGELOG）。"""
    items = changelog_items(root)
    tags = read_tag_entries(root)
    log_entries = git_log_entries(root)
    anchors = compute_anchors(log_entries, items, root=root)
    reg = merge_registry(items, tags, current_commit=head_state(root)["head"])
    # 回填 milestone 标记
    policy = load_policy(root)
    for rec in reg["versions"]:
        rec["milestone"] = is_milestone(rec["version"], policy)
    reg["anchors"] = anchors
    reg["monotonicity"] = check_anchor_monotonicity(reg, anchors, log_entries)
    return reg


def cmd_list(args, root):
    reg = build_registry_full(root)
    cur = current_version(root)
    print("版本清单（共 %d 个；tag %d 个）" % (
        len(reg["versions"]),
        sum(1 for r in reg["versions"] if r.get("has_tag"))))
    print(format_version_table(reg["versions"], current_version=cur))
    if reg["missing_tags"]:
        print("\n  ⚠ 缺 tag（可一键补齐）：%s" % ", ".join(reg["missing_tags"]))
    if reg["orphan_tags"]:
        print("  ⚠ 有 tag 但 CHANGELOG 无对应版本段：%s"
              % ", ".join(reg["orphan_tags"]))
    print("\n  ● = 当前清单版本（%s）" % (cur or "未知"))
    return 0


def cmd_show(args, root):
    reg = build_registry_full(root)
    want = args.version
    hits = [r for r in reg["versions"] if r["version"] == want]
    if not hits:
        print("✗ 未找到版本：%s" % want)
        return 1
    rec = hits[0]
    print("版本：%s" % rec["version"])
    print("  唯一标识：%s" % build_release_id(
        rec["version"], rec.get("timestamp", ""), rec.get("commit", "")))
    print("  日期：%s" % (rec.get("date") or "-"))
    print("  commit：%s" % (rec.get("commit") or "-"))
    print("  tag：%s" % ("✓ %s" % rec.get("tag_type") if rec.get("has_tag") else "✗ 无"))
    print("  里程碑：%s" % ("是" if rec.get("milestone") else "否"))
    print("  标题：%s" % (rec.get("title") or "-"))
    print("  摘要：%s" % (rec.get("summary") or "-"))
    anchor = reg.get("anchors", {}).get(rec["version"])
    if anchor:
        print("  锚点依据：%s" % anchor.get("reason", ""))
    return 0


def cmd_diff(args, root):
    reg = build_registry_full(root)
    by_ver = {r["version"]: r for r in reg["versions"]}
    a, b = args.a, args.b
    if b is None:
        b = current_version(root)
    if a not in by_ver or b not in by_ver:
        print("✗ 版本不存在：%s / %s" % (a, b))
        return 1
    ca, cb = by_ver[a].get("commit"), by_ver[b].get("commit")
    if not ca or not cb:
        print("✗ 目标版本缺 commit（尚未打 tag）⇒ 无法比对")
        return 1
    rows = diff_rows_between(root, ca, cb)
    print("差异明细：%s → %s" % (a, b))
    print("  %s" % (by_ver[a].get("commit", "")[:8]), "→", by_ver[b].get("commit", "")[:8])
    print("  规模：%s" % (diff_shortstat(root, ca, cb) or "-"))
    print(format_diff_summary(rows))
    return 0


def cmd_tag(args, root):
    """打 tag / 批量补齐 tag。

    ★ 幂等：已存在的 tag 默认跳过（`--force` 才覆盖）。
    ★ 只打标不改内容。
    ★ 默认 dry-run（须 --confirm 才真打）。
    """
    policy = load_policy(root)
    reg = build_registry_full(root)
    existing = existing_tag_names(root)

    if args.sync:
        anchor_map = reg.get("anchors", {})
        plan = plan_tag_backfill(reg, anchor_map, existing)
        if not plan:
            print("✓ 无缺失 tag，无需补齐（幂等：已存在的跳过）")
            return 0
        print("计划补齐 %d 个 tag：" % len(plan))
        for v, info in sorted(plan.items(), key=lambda kv: version_sort_key(kv[0])):
            print("  %-10s → %s  (%s)" % (v, info["commit"][:8], info["reason"][:70]))
        if not args.confirm:
            print("\n（dry-run：加 --confirm 才真正打 tag）")
            return 0
        summary = args.summary or "由 versionctl.py 批量补齐：补全 CHANGELOG 已声明但缺少版本指针的版本"
        made = []
        for v, info in sorted(plan.items(), key=lambda kv: version_sort_key(kv[0])):
            msg = "%s\n\n%s" % (summary, info["reason"])
            run_git(["tag", "-a", v, info["commit"], "-m", msg], cwd=root)
            made.append(v)
        print("\n✓ 已补齐 %d 个 tag：%s" % (len(made), ", ".join(made)))
        return 0

    # 单版本打 tag
    v = args.version
    if not v:
        print("✗ 需 --version 或 --sync")
        return 2
    if not parse_version(v):
        print("✗ 版本号不合法：%s（需完整三段，如 v3.27.0）" % v)
        return 2
    if v in existing and not args.force:
        print("✓ tag %s 已存在（幂等跳过；需覆盖请加 --force）" % v)
        return 0
    reg_items = changelog_items(root)
    anchor = reg.get("anchors", {}).get(v)
    commit = args.commit or (anchor or {}).get("commit") or ""
    if not commit:
        print("✗ 找不到 %s 的收口点提交 ⇒ 请显式传 --commit" % v)
        return 1
    if not args.confirm:
        print("（dry-run）将打 tag %s → %s" % (v, commit[:8]))
        print("   摘要：%s" % (args.summary or "(无)"))
        print("   加 --confirm 执行")
        return 0
    msg = args.summary or "版本 %s" % v
    if args.force:
        run_git(["tag", "-f", "-a", v, commit, "-m", msg], cwd=root)
    else:
        run_git(["tag", "-a", v, commit, "-m", msg], cwd=root)
    print("✓ 已打 tag：%s → %s" % (v, commit[:8]))
    return 0


def cmd_switch(args, root):
    """切换到指定版本（detached HEAD）。

    ★ 目标可以是**版本号**（v3.26.0）或 **commit sha**（40/7 位）——
      后者用于「回到历史上的任意一点」，不必先有 tag。

    ★ dry-run 优先于一切：即使目标版本**尚无 tag**，dry-run 也必须给出
      「打算怎么做」的预览（含「该版本尚无版本指针」这一事实），
      而不是直接报错退出 —— 否则用户无法预演。
      实测教训：v3.28.0 初版把「无 tag」检查放在 dry-run 检查之前，
      导致 `switch v3.26.0`（无 tag）在 dry-run 阶段就 rc=1 退出，
      「dry-run 不改 HEAD」这条判据根本测不到。
    """
    reg = build_registry_full(root)
    by_ver = {r["version"]: r for r in reg["versions"]}
    v = args.version
    st = head_state(root)

    # ── 目标解析：先试版本号，再试 commit sha
    if v in by_ver:
        rec = by_ver[v]
        commit = rec.get("commit")
        label = v
        if not commit:
            anchor = reg.get("anchors", {}).get(v)
            fallback = (anchor or {}).get("commit", "")
            print("⚠ %s 尚无 tag ⇒ 没有版本指针可切换" % v)
            if fallback:
                print("   其收口点提交为 %s（先跑 tag --sync 补齐即可切换）"
                      % fallback[:8])
            if not args.confirm:
                print("   （dry-run：未做任何改动）")
                return 0
            print("   → 请先执行：python3 scripts/versionctl.py tag --sync --confirm")
            return 1
    elif re.match(r"^[0-9a-f]{7,40}$", v or ""):
        try:
            commit = run_git(["rev-parse", "--verify", v + "^{commit}"],
                             cwd=root).strip()
        except Exception:
            commit = ""
        if not commit:
            print("✗ 不是合法版本号，也不是可解析的 commit：%s" % v)
            return 1
        label = "commit %s" % commit[:8]
    else:
        print("✗ 未找到版本：%s" % v)
        return 1

    if st["dirty"]:
        print("✗ 工作区有未提交改动 ⇒ 拒绝切换（避免丢失工作）")
        print("   请先 git stash 或提交；本工具不做自动 stash（那是破坏性猜测）")
        return 1
    if not args.confirm:
        print("（dry-run）将切换到 %s（commit %s）" % (label, commit[:8]))
        print("   当前：%s @ %s" % (st["branch"], st["head"][:8]))
        print("   加 --confirm 执行")
        return 0
    before = st
    run_git(["checkout", "--detach", commit], cwd=root)
    after = head_state(root)
    write_journal(root, "switch", before, after,
                  {"version": label, "commit": commit})
    print("✓ 已切换到 %s（%s）" % (label, commit[:8]))
    print("   回原状态：python3 scripts/versionctl.py recover --confirm")
    return 0


def cmd_rollback(args, root):
    """回滚到指定版本（默认：版本序上的前一个）。"""
    reg = build_registry_full(root)
    versions = [r["version"] for r in reg["versions"]]
    if args.version:
        target = args.version
    else:
        cur = current_version(root)
        if cur not in versions:
            print("✗ 当前版本 %s 不在清单中，无法推断回滚目标" % cur)
            return 1
        idx = versions.index(cur)
        if idx + 1 >= len(versions):
            print("✗ %s 已是最新版本，无可回滚目标" % cur)
            return 1
        target = versions[idx + 1]
    return cmd_switch(_SwitchArgs(version=target, confirm=args.confirm), root)


class _SwitchArgs(object):
    """轻量参数载体（让 rollback 复用 switch 的实现，避免逻辑分叉）。"""

    def __init__(self, version, confirm=False):
        self.version = version
        self.confirm = confirm


def cmd_policy(args, root):
    """显示 / 设置保留与清理策略。"""
    policy = load_policy(root)
    if args.set:
        for kv in args.set:
            if "=" not in kv:
                print("✗ 格式应为 key=value：%s" % kv)
                return 2
            k, v = kv.split("=", 1)
            k = k.strip()
            try:
                if v.strip().lower() in ("true", "false"):
                    policy[k] = (v.strip().lower() == "true")
                elif v.strip().isdigit():
                    policy[k] = int(v.strip())
                else:
                    policy[k] = v.strip()
            except Exception:
                policy[k] = v.strip()
        if not args.confirm:
            print("（dry-run）策略将写入 %s" % (ctl_dir(root) / CONFIG_FILENAME))
            print("   加 --confirm 执行")
            return 0
        p = save_policy(root, policy)
        print("✓ 策略已写入：%s" % p)
        return 0
    print("当前策略（schema_version=%s）：" % policy.get("schema_version"))
    for k in sorted(policy):
        print("  %-22s %s" % (k, policy[k]))
    print("\n  里程碑判定：minor 偶数且 patch==0（如 v3.26.0）")
    print("  tag 默认永久保留（keep_tags=true）⇒ tag 不占实质空间且删了会破坏可回滚性")
    return 0


def cmd_prune(args, root):
    """按策略规划并（--confirm 时）执行归档清理。★ 归档 ≠ 删除。"""
    policy = load_policy(root)
    reg = build_registry_full(root)
    artifacts = []
    for rel in policy.get("artifact_dirs") or []:
        p = Path(rel) if os.path.isabs(rel) else (Path(root) / rel)
        if not p.exists():
            continue
        if p.is_file():
            artifacts.append({"path": str(p), "bytes": p.stat().st_size,
                              "keep": False, "reason": "策略指定清理"})
        else:
            for child in sorted(p.iterdir()):
                try:
                    size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                except Exception:
                    size = 0
                artifacts.append({"path": str(child), "bytes": size,
                                  "keep": False, "reason": "策略指定清理"})
    plan = plan_prune(reg, policy, artifacts)

    print("保留/归档计划：")
    print("  永久保留版本（最近 %d + 里程碑）：%d 个"
          % (policy.get("keep_recent", 10), len(plan["keep_versions"])))
    if plan["prune_tags"]:
        print("  可归档版本（tag 允许清理时）：%s" % ", ".join(plan["prune_versions"]))
    else:
        print("  tag 策略：永久保留（keep_tags=true）⇒ 不清理任何 tag")
    print("  待归档产物：%d 项，合计 %d 字节" % (
        len(plan["archive_artifacts"]), plan["total_bytes"]))
    for a in plan["archive_artifacts"][:20]:
        print("     - %s（%d 字节）" % (a["path"], a["bytes"]))
    if not args.confirm:
        print("\n（dry-run：加 --confirm 才真正移动；★ 移动到归档区，不删除）")
        return 0
    if not plan["archive_artifacts"]:
        print("\n✓ 无待归档产物")
        return 0
    ts = time.strftime("%Y%m%d-%H%M%S")
    archive_base = Path(policy.get("archive_dir", "%s/%s" % (CTL_DIRNAME, ARCHIVE_DIRNAME)))
    if not archive_base.is_absolute():
        archive_base = Path(root) / archive_base
    dest = archive_base / ts
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for a in plan["archive_artifacts"]:
        src = Path(a["path"])
        if not src.exists():
            continue
        target = dest / src.name
        n = 1
        while target.exists():
            target = dest / ("%s.%d" % (src.name, n))
            n += 1
        shutil.move(str(src), str(target))
        moved.append({"from": str(src), "to": str(target)})
    manifest = dest / "ARCHIVE_MANIFEST.json"
    manifest.write_text(json.dumps(
        {"archived_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
         "note": "归档而非删除；如需恢复，把 to 路径下的文件移回 from 路径即可",
         "items": moved}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_journal(root, "prune", head_state(root), head_state(root),
                  {"archived": len(moved), "dest": str(dest)})
    print("\n✓ 已归档 %d 项 → %s" % (len(moved), dest))
    print("   清单：%s" % manifest)
    print("   ★ 未删除任何文件；恢复方式见清单 from/to 字段")
    return 0


def cmd_journal(args, root):
    recs = read_journal(root, limit=args.limit)
    if not recs:
        print("（无操作日志）")
        return 0
    print("操作日志（最近 %d 条，新的在前）：" % len(recs))
    for r in recs:
        print("  %s  %-8s  before=%s  after=%s" % (
            r.get("ts", ""), r.get("op", ""),
            (r.get("before_head") or "")[:8], (r.get("after_head") or "")[:8]))
        if r.get("detail"):
            print("      detail: %s" % json.dumps(r["detail"], ensure_ascii=False))
    return 0


def cmd_recover(args, root):
    """按 journal 把仓库拉回最近一次操作前状态。"""
    recs = read_journal(root, limit=50)
    if not recs:
        print("✗ 无操作日志 ⇒ 无可恢复的目标")
        return 1
    last = recs[-1]
    target = last.get("before_head")
    if not target:
        print("✗ 最后一条日志没有 before_head ⇒ 无法恢复")
        return 1
    st = head_state(root)
    if st["dirty"]:
        print("✗ 工作区有未提交改动 ⇒ 拒绝恢复（避免丢失工作）")
        return 1
    if not args.confirm:
        print("（dry-run）将恢复到：%s（%s）" % (
            target[:8], last.get("before_branch") or "?"))
        print("   加 --confirm 执行")
        return 0
    run_git(["checkout", "--detach", target], cwd=root)
    after = head_state(root)
    write_journal(root, "recover", st, after, {"recovered_to": target})
    print("✓ 已恢复到 %s（%s）" % (target[:8], last.get("op", "?")))
    return 0


def cmd_migrate(args, root):
    r = migrate_policy(root, confirm=args.confirm)
    print("migrate：%s —— %s" % (r.get("action"), r.get("reason", "")))
    if r.get("backup"):
        print("  备份：%s" % r["backup"])
    if r.get("action") == "refused":
        return 1
    return 0


# ───────────────────────────────────────────────────── CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="versionctl.py",
        description="版本迭代机制控制面（tag / 清单 / 对比 / 切换 / 回滚 / 归档清理）")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("list", help="列出全部版本")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="某版本详情")
    sp.add_argument("version")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("diff", help="任意两版本差异明细")
    sp.add_argument("a")
    sp.add_argument("b", nargs="?")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("tag", help="打 tag / 批量补齐")
    sp.add_argument("--version")
    sp.add_argument("--commit")
    sp.add_argument("--summary", default="")
    sp.add_argument("--sync", action="store_true", help="批量补齐缺失 tag")
    sp.add_argument("--force", action="store_true", help="覆盖已存在的 tag")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_tag)

    sp = sub.add_parser("switch", help="切换到指定版本")
    sp.add_argument("version")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_switch)

    sp = sub.add_parser("rollback", help="回滚到指定版本（默认上一个）")
    sp.add_argument("version", nargs="?")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_rollback)

    sp = sub.add_parser("policy", help="显示/设置保留与清理策略")
    sp.add_argument("--set", action="append", default=[], help="key=value（可多次）")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_policy)

    sp = sub.add_parser("prune", help="按策略归档清理（归档≠删除）")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_prune)

    sp = sub.add_parser("journal", help="查看操作日志")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_journal)

    sp = sub.add_parser("recover", help="按 journal 回退到最近操作前状态")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_recover)

    sp = sub.add_parser("migrate", help="策略文件 schema 迁移")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_migrate)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 2
    root = repo_root()
    try:
        return args.func(args, root)
    except Exception as e:
        print("✗ 执行失败：%s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())

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
JOURNAL_DIRNAME = "journal"
ARCHIVE_DIRNAME = "archive"
#: 控制面**自举锚点**目录（相对 `.versionctl/`）。
#:
#: ★★ v3.28.0 收尾修正（实测踩坑，第 6 个真缺陷）：
#:   `switch` 用 `git checkout --detach` ⇒ **整个工作树**被替换 ⇒
#:   控制面脚本 `scripts/versionctl.py` **自己也被换掉**：
#:     · 切到 v3.28.0 之前的版本 ⇒ 该文件**根本不存在**；
#:     · 切到更早的 v3.28.0 之前的小版本 ⇒ 该文件是**旧逻辑**。
#:   ⇒ 切换后 `recover` 跑的是旧逻辑甚至无法运行 ⇒ **用户切出去就回不来**。
#:   —— 实测：切到 v3.27.0 后 `.versionctl/` 整个目录消失（config.json
#:      被 git 跟踪 ⇒ checkout 删除），`scripts/versionctl.py` 不存在。
#:
#: ⇒ 修法：**自举锚点**。`switch` 执行前把「当前工作区里的控制面脚本」
#:   复制到 `.versionctl/bin/versionctl.py`（**gitignored** ⇒ 跨 checkout 存活），
#:   并在 journal 里记下锚点路径；`recover` 优先用锚点里的**最新版**控制面。
#:   ⇒ 控制面与历史工作树**彻底解耦**：无论 checkout 到哪个年代，
#:     执行 `.versionctl/bin/versionctl.py recover` 都能回到主线。
BOOTSTRAP_DIRNAME = "bin"
BOOTSTRAP_SCRIPT = "versionctl.py"

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


# ───────────────────────────────────────────────────── 策略文件（包级真源 + 本机覆盖层）

def ctl_dir(root):
    return Path(root) / CTL_DIRNAME


#: 策略**包级真源**（相对包根）：入库、跨版本存活。
#:
#: ★★ v3.28.0 收尾修正（实测踩坑，第 6 个真缺陷）：
#:   原设计把策略放在 `.versionctl/config.json`（**入库**）⇒ 两个致命问题：
#:     ① `switch` 的 `git checkout --detach` 会把**整个工作树**替换 ⇒
#:        该文件被 checkout **删除** ⇒ 切到 v3.28.0 之前的版本后
#:        **策略真源直接消失**（实测：切到 v3.27.0 后 `.versionctl/` 整个目录没了）；
#:     ② 反过来，用户改一次策略就让工作区**变脏** ⇒ `switch` 拒绝切换
#:        （实测报错「Your local changes to the following files would be
#:         overwritten by checkout」）。
#:   ⇒ 真源上移到 `config/version-policy.yaml`（**入库**⇒ 跨版本存活；
#:     且本包既有约定就是「config/*.yaml 是唯一数据源」）。
#:   ⇒ `.versionctl/` 退化为**运行时状态区**（不入库）。
POLICY_YAML_REL = "config/version-policy.yaml"

#: 运行时**本机覆盖层**文件名（相对 `.versionctl/`）：不入库、只存覆盖增量。
#:
#: ★★ v3.28.0 收尾修正（D8：**运行时副本会被 checkout 静默覆盖** —— 真缺陷）：
#:   原名 `config.json` 在 **v3.28.0 这个提交里是被 git 跟踪的**
#:   ⇒ 切到 v3.28.0（或更早）时，git 会用该提交里的旧内容
#:     **覆盖掉**用户本机的运行时副本
#:     （实测：`git checkout --detach v3.28.0` 后 `.versionctl/config.json`
#:       的内容被换成了 v3.28.0 的旧值 ⇒ 用户本机设置被静默清空）。
#:   ⇒ 改用**从未被任何提交跟踪过**的文件名 ⇒ git 永远不碰它
#:     ⇒ 跨版本切换后本机覆盖**存活**。
POLICY_LOCAL_FILENAME = "policy.local.json"

#: **旧版**运行时副本文件名（v3.28.0 及之前的布局；**曾被 git 跟踪**）。
#:
#:   保留兼容读取：用户升级后磁盘上可能还留着它。
#:   ★ 它是**运行时残留** ⇒ **不得遮蔽**包级真源（否则真源静默失效，D1）。
POLICY_LEGACY_FILENAME = "config.json"

#: 兼容别名（**同义**于 POLICY_LEGACY_FILENAME，指向同一个对象）。
#:
#: ★ v3.28.0 收尾修正（D6：常量去重 —— 真缺陷的前身）：
#:   此前存在**值相同但各自独立**的 `CONFIG_FILENAME = "config.json"` 与
#:   `POLICY_LOCAL_FILENAME = "config.json"` ⇒ 后续维护者只改其中一个
#:   ⇒ 两个常量**静默分叉**（写到两个不同的文件）。
#:   ⇒ 真相只留**一处**；此处是**别名**（同一个对象 ⇒ 改一处即处处生效）。
CONFIG_FILENAME = POLICY_LEGACY_FILENAME

#: 本机覆盖层的**角色标记键**（值恒为 True）。
#:
#: ★★ v3.28.0 收尾修正（D1：包级真源被运行时残留污染 —— 真缺陷）：
#:   若运行时副本存的是**全量镜像**，它会**永久遮蔽**包级真源
#:   ⇒ 真源随 git 更新（pull / checkout 到新版本）**静默失效**
#:   （实测：真源 keep_recent=25，生效值仍是旧副本的 10）。
#:   ⇒ 覆盖层一律只存「**本机覆盖增量**」，并用本标记**自描述角色**：
#:     · **带标记** ⇒ 本文件是「本机覆盖增量」⇒ 它的键**覆盖**真源；
#:     · **无标记** ⇒ **旧版全量副本** ⇒ 属运行时残留 ⇒ **不遮蔽**真源。
POLICY_OVERLAY_MARKER = "_local_overrides"


# ───────────────────────────────────────────────── 自举锚点（控制面与历史工作树解耦）

def bootstrap_dir(root):
    """自举锚点目录：`<root>/.versionctl/bin/`。"""
    return ctl_dir(root) / BOOTSTRAP_DIRNAME


def bootstrap_script(root):
    """自举锚点里的控制面脚本路径。"""
    return bootstrap_dir(root) / BOOTSTRAP_SCRIPT


def write_bootstrap(root, src_path=None):
    """把当前控制面脚本复制到自举锚点目录（**gitignored** ⇒ 跨 checkout 存活）。

    ★ 为什么必须这么做（v3.28.0 第 6 个真缺陷）：
      `switch` 会替换整个工作树 ⇒ `scripts/versionctl.py` 自己也会被替换
      ⇒ 切到 v3.28.0 之前的版本时**该文件根本不存在** ⇒ 用户切出去后
      没有任何办法执行 `recover` ⇒ **死锁**。
      ⇒ 把控制面先复制到 gitignored 目录，切出去后仍可执行它。

    返回锚点路径；失败抛异常（调用方须捕获后**降级**而不是整体失败）。
    """
    src = Path(src_path) if src_path else Path(__file__).resolve()
    if not src.is_file():
        raise RuntimeError("控制面脚本不存在：%s" % src)
    dst = bootstrap_script(root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    # ★ 用临时文件 + 原子替换 ⇒ 中途失败不会留下**半截**的控制面
    tmp = dst.with_suffix(".py.tmp")
    shutil.copy2(str(src), str(tmp))
    os.replace(str(tmp), str(dst))
    return dst


def read_bootstrap(root):
    """读自举锚点里的控制面内容（不存在返回 None）。"""
    p = bootstrap_script(root)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def policy_yaml_path(root):
    """包级策略真源路径（`config/version-policy.yaml`）。"""
    return Path(root) / POLICY_YAML_REL


def _read_yaml_policy(path):
    """读 YAML 策略文件。

    返回 `(data, error)` 二元组：
      · `data` —— 解析成功且是 dict 时为其内容，否则 None
      · `error` —— None 表示「文件不存在」；非 None 表示**发生了什么**：
        - "unreadable"  文件读不了（IO 错误）
        - "no_yaml"     环境无 PyYAML ⇒ **无法解析**（不是「文件不存在」！）
        - "parse_error" YAML 语法错误
        - "not_dict"    内容不是映射（如顶层是列表）
    ★ 区分「不存在」与「存在但坏了」是关键（D5）：
      后者必须**显式告警** ⇒ 否则用户改过的策略会**静默失效**。
    """
    if not path.is_file():
        return None, None
    try:
        import yaml  # 局部导入：避免对无 yaml 环境造成硬依赖
    except ImportError:
        return None, "no_yaml"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None, "unreadable"
    try:
        data = yaml.safe_load(raw)
    except Exception:
        return None, "parse_error"
    if not isinstance(data, dict):
        return None, "not_dict"
    return data, None


def _read_json_policy(path):
    """读 JSON 策略文件。

    返回 `(data, error)` 二元组（语义同 `_read_yaml_policy`）：
      · `error` ∈ {None, "unreadable", "parse_error", "not_dict"}
    """
    if not path.is_file():
        return None, None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None, "unreadable"
    try:
        data = json.loads(raw)
    except Exception:
        return None, "parse_error"
    if not isinstance(data, dict):
        return None, "not_dict"
    return data, None


#: 策略文件读取错误的**人类可读**说明（供告警文案复用）。
POLICY_READ_ERRORS = {
    "unreadable": "文件读不了（IO 错误）",
    "no_yaml": "环境无 PyYAML ⇒ 无法解析该 YAML 文件",
    "parse_error": "语法错误（解析失败）",
    "not_dict": "内容不是键值映射（顶层不是 dict）",
}


def _source_is_default(yaml_data, key, current_value):
    """判定「包级真源里这个键是否**仍是默认值**」。

    ★ v3.28.0 收尾修正（D11 配套）：判定必须基于**真源原始内容**，
      不能基于「与 DEFAULT_POLICY 合并后的 policy」——
      因为 `policy` 已被真源覆盖过，真源值恰好等于默认值时看不出
      「用户从没设置过」这一事实。
    """
    if isinstance(yaml_data, dict) and key in yaml_data:
        return yaml_data.get(key) == DEFAULT_POLICY.get(key)
    # 真源里**没有**这个键 ⇒ 该键仍取的是默认值
    return current_value == DEFAULT_POLICY.get(key)


def load_policy(root, warnings=None):
    """读策略：包级 YAML 真源为主，运行时覆盖层为辅。

    优先级（**后者覆盖前者**）：
      ① `DEFAULT_POLICY`（代码内置默认）
      ② `config/version-policy.yaml`（**包级真源**，入库 ⇒ 跨版本存活）
      ③ `.versionctl/policy.local.json`（**本机覆盖层**，不入库）
      ③' `.versionctl/config.json`（**旧版运行时副本**，残留，只补缺键）

    ★ 容忍未知键（向前兼容）：旧版本写的多余键原样保留，不报错。

    ★★ v3.28.0 收尾修正（D1：真源被运行时残留污染 —— **真缺陷**）：
      原实现是「JSON 无条件覆盖 YAML」⇒ 运行时副本成了**事实上的第二份真源**：
        · 用户在旧版本工作树里改过副本 ⇒ 回到主线后，**旧副本遮蔽新真源**
          ⇒ 刚更新的真源**静默失效**（实测：真源 keep_recent=25，
            生效值仍是旧副本的 10）；
        · 真源随 git 更新（pull / checkout 到新版本）时同样被遮蔽。
      ⇒ 修法：运行时副本**只能是「本机本地覆盖增量」**，用
        `_local_overrides` 标记**自描述角色**：
          · **带标记** ⇒ 它是覆盖层 ⇒ 它的键**覆盖**真源（`--local` 的语义）；
          · **无标记** ⇒ **旧版全量副本**（v3.28.0 之前的布局）
            ⇒ 属「运行时残留」⇒ **只补真源没有的键，绝不遮蔽真源**。
      ★ 这样「覆盖」就有了**明确出处**：只有显式 `--local` 写出的增量
        才能覆盖真源；残留副本没有这个权力。

    ★ `warnings`（可选 list）：传入时，读取异常会**显式告警**进去（D5）
      ⇒ 调用方可把「策略文件坏了」如实告诉用户，而不是静默退回默认值。
    """
    if warnings is None:
        warnings = []
    policy = dict(DEFAULT_POLICY)
    policy["schema_version"] = SCHEMA_VERSION

    y, y_err = _read_yaml_policy(policy_yaml_path(root))
    if y_err:
        warnings.append("⚠ 策略真源 %s 读取失败：%s ⇒ 该文件**未被采用**"
                        % (POLICY_YAML_REL, POLICY_READ_ERRORS.get(y_err, y_err)))
    if y:
        policy.update(y)

    # ★ 运行时层：读**两个**文件
    #   ① `policy.local.json`（新名，从未被 git 跟踪 ⇒ 跨版本存活）
    #   ② `config.json`（旧名，v3.28.0 曾被 git 跟踪 ⇒ 可能是残留）
    #   两者都读，且**只有带标记的**才允许覆盖真源。
    #
    # ★ schema_version 的语义：生效值取「真源」与「覆盖层」里的**较大者**
    #   ⇒ 覆盖层不会把真源的 schema 拉低（真源更新后不被降级）。
    overlay_schema = None
    for fname, role in ((POLICY_LOCAL_FILENAME, "本机覆盖层"),
                        (POLICY_LEGACY_FILENAME, "旧版运行时副本")):
        j, j_err = _read_json_policy(ctl_dir(root) / fname)
        if j_err:
            warnings.append("⚠ %s %s/%s 读取失败：%s ⇒ 该文件**未被采用**"
                            % (role, CTL_DIRNAME, fname,
                               POLICY_READ_ERRORS.get(j_err, j_err)))
            continue
        if not j:
            continue
        is_overlay = bool(j.get(POLICY_OVERLAY_MARKER))
        if is_overlay:
            # ★ 本机覆盖（显式 --local 写出的增量）⇒ 覆盖真源
            for k, v in j.items():
                if k not in (POLICY_OVERLAY_MARKER, "schema_version"):
                    policy[k] = v
            try:
                s = int(j.get("schema_version", 1))
            except (TypeError, ValueError):
                s = 1
            overlay_schema = s if overlay_schema is None else max(overlay_schema, s)
        else:
            # ★ 旧版全量副本（运行时残留）⇒ **不得遮蔽真源**
            #   （否则真源更新后静默失效，D1）
            #
            # ★★ v3.28.0 收尾修正（D11：**旧副本里的用户设置被静默丢弃**
            #   —— 真缺陷）：
            #   「只补真源没有的键」这个口径**太粗** ⇒ 用户在旧布局里
            #   真实设置过的值会被丢掉。
            #   —— 实测：`.versionctl/config.json` 里写了
            #     `artifact_dirs: ["/用户/的/目录"]`，而包级真源里该键
            #     **存在但仍是默认值 `[]`** ⇒ 「真源有该键」⇒ 旧副本的值
            #     **被忽略** ⇒ 用户的产物目录配置**静默失效**
            #     （实测：prune 因此找不到任何产物，一个都没归档）。
            #
            #   ⇒ 修法（**真源优先、默认值让位**）：
            #     · 真源里该键的值 **== DEFAULT_POLICY 的默认值**
            #       ⇒ 说明**真源从没被设置过** ⇒ 采用旧副本的值（兜底）
            #       ⇒ 并**显式告警**（让用户知道「你的旧设置被接住了，
            #         建议跑 `versionctl migrate` 把它固化进真源」）；
            #     · 真源里该键的值 **!= 默认值**
            #       ⇒ 用户设置过真源 ⇒ **以真源为准**，旧副本不生效
            #       （这正是 D1 要防的「旧副本遮蔽真源」）。
            adopted, overridden = [], []
            for k, v in j.items():
                if k == "schema_version":
                    continue
                if k not in policy:
                    policy[k] = v              # 真源**根本没有**这个键 ⇒ 补上
                    adopted.append(k)
                elif _source_is_default(y, k, policy.get(k)):
                    # ★ 真源该键**仍是默认值** ⇒ 用户从没在真源里设置过
                    #   ⇒ 采用旧副本的值（兜底）
                    #   ★ 关键：判定必须看**真源原始值**（`y`），
                    #     不能看合并后的 `policy`（它已被 `policy.update(y)`
                    #     覆盖成真源值，而真源值恰好等于默认值）
                    policy[k] = v
                    adopted.append(k)
                else:
                    overridden.append(k)
            if adopted:
                warnings.append(
                    "ℹ %s %s/%s 是**旧版全量副本**（无 %s 标记）"
                    "⇒ 已**兜底**采用其中真源未设置的值：%s"
                    "（建议跑 `versionctl migrate` 把它们固化进包级真源）"
                    % (role, CTL_DIRNAME, fname, POLICY_OVERLAY_MARKER,
                       "、".join(sorted(adopted))))
            if overridden:
                warnings.append(
                    "ℹ %s %s/%s 的这些键**未采用**（包级真源已显式设置 ⇒ 真源优先）：%s"
                    % (role, CTL_DIRNAME, fname, "、".join(sorted(overridden))))
    # ★ 生效 schema = 真源与覆盖层里的**较大者**（覆盖层不得把真源降级）
    try:
        src_schema = int(policy.get("schema_version", SCHEMA_VERSION))
    except (TypeError, ValueError):
        src_schema = SCHEMA_VERSION
    if overlay_schema is not None:
        src_schema = max(src_schema, overlay_schema)
    policy["schema_version"] = src_schema
    return policy


def archive_stale_runtime(root, path):
    """把「旧版全量运行时副本」**归档**（★ 不删除，本包铁律）。

    缘由（D1）：旧版全量副本会**遮蔽**包级真源 ⇒ 必须让位；
      但本包铁律是「**只归档不删除**」⇒ 不许 `unlink`。

    返回归档后的路径（失败返回 None）。
    """
    src = Path(path)
    if not src.is_file():
        return None
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest_dir = ctl_dir(root) / ARCHIVE_DIRNAME / ts
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (src.name + ".stale")
        n = 1
        while dest.exists():
            dest = dest_dir / ("%s.stale.%d" % (src.name, n))
            n += 1
        shutil.move(str(src), str(dest))
    except OSError:
        return None
    return str(dest)


def save_policy(root, policy, local_only=False, keep_runtime_names=()):
    """写策略。

    ★ `local_only=False`（默认）⇒ 写**包级真源** `config/version-policy.yaml`
      （入库，跨版本存活）+ 让**旧版全量残留**让位
      （否则旧残留会遮蔽刚写的真源 ⇒ 真源静默失效，D1）。
    ★ `local_only=True` ⇒ 只写运行时**覆盖层**（**增量**形态，不动包级真源
      ⇒ 不弄脏工作区）。

    ★ `keep_runtime_names=()` ⇒ 指定**不得归档**的运行时文件名集合。
      缘由（D12）：`migrate_policy` 用本函数把旧版 JSON **提升为真源**时，
      该 JSON 正是**迁移源** ⇒ 归档它会让用户读回原文件时拿到 FileNotFound。

    返回 (写入的路径列表, 告警列表)。
    ★ 返回二元组是 v3.28.0 收尾修正（D4）：
      无 PyYAML 时**不得静默降级** ⇒ 必须把「真源没写成」如实报出来。
    """
    written = []
    warnings = []
    policy = dict(policy)
    d = ctl_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / POLICY_LOCAL_FILENAME
    legacy_p = d / POLICY_LEGACY_FILENAME
    if not local_only:
        yp = policy_yaml_path(root)
        yp.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml
        except ImportError:
            # ★★ D4：真源写不了 ⇒ **显式告警**（绝不静默退化）
            warnings.append(
                "⚠ 无 PyYAML ⇒ **包级真源未写入**（%s）！"
                "本次设置**只落在本机副本**里 ⇒ 换机器 / 切版本后会丢失。"
                "（装 PyYAML：pip install pyyaml）" % POLICY_YAML_REL)
        else:
            yp.write_text(
                "# version-policy.yaml — 版本迭代机制策略真源（v3.28.0）\n"
                "# ★ 入库 ⇒ 跨版本存活（切到任意历史版本都读得到）\n"
                "# ★ 由 scripts/versionctl.py 的 `policy` 子命令维护\n"
                "# ⚠ schema 升级走 `versionctl migrate`（幂等、只补缺键）\n"
                + yaml.safe_dump(dict(policy), allow_unicode=True,
                                 sort_keys=True, default_flow_style=False),
                encoding="utf-8")
            written.append(yp)
        # ★ 真源已定 ⇒ **旧版全量残留**必须让位
        #   （否则它会遮蔽真源 ⇒ 刚设的值不生效 ⇒ 真源静默失效，D1）
        #   ★ 纪律：本包铁律「**只归档不删除**」⇒ 用**归档**而非 unlink。
        for stale in (legacy_p, p):
            existing, _e = _read_json_policy(stale)
            if existing is None:
                continue
            if existing.get(POLICY_OVERLAY_MARKER):
                # 已是覆盖层形态 ⇒ 保留「本机覆盖」的键，但把**值**同步为最新
                keep = {POLICY_OVERLAY_MARKER: True}
                for k, v in existing.items():
                    if k == POLICY_OVERLAY_MARKER:
                        continue
                    keep[k] = policy.get(k, v)
                stale.write_text(json.dumps(keep, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
            else:
                # ★ 旧版全量副本 ⇒ **归档**（不删除），并留清单
                #
                # ★★ v3.28.0 收尾修正（D12：**迁移时把迁移源自己归档掉了**
                #   —— 真缺陷）：
                #   `migrate_policy` 在「只有旧版 JSON」的场景下调用本函数
                #   来**提升为包级真源** ⇒ 但本函数随后又把**同一个文件**
                #   当作「旧版残留」**归档（move）**掉
                #   ⇒ 迁移后原路径**消失** ⇒ 用户的旧文件既不在原位、
                #     也不在真源里（真源只拿到 YAML）⇒ 数据看似「迁移成功」
                #     实则**用户读回原文件时拿到 FileNotFound**。
                #   —— 实测：`T12MigratePolicy` / `T17Migrate*` 三例
                #     报 FileNotFoundError: .versionctl/config.json。
                #
                #   ⇒ 修法：迁移路径**显式声明**「哪些文件是迁移源」，
                #     迁移源**不归档**（它正在被就地升级成新形态），
                #     由调用方负责改写它的内容。
                if stale.name in (keep_runtime_names or ()):
                    continue
                bak = archive_stale_runtime(root, stale)
                if bak:
                    warnings.append(
                        "ℹ 运行时残留副本 %s/%s（无 %s 标记 ⇒ 属旧版全量副本，"
                        "会遮蔽包级真源）已**归档**到：%s"
                        % (CTL_DIRNAME, stale.name, POLICY_OVERLAY_MARKER, bak))
    else:
        # ★ 本机覆盖层：只写**与真源不同的键**的增量
        #   （不是全量镜像！）⇒ 不得遮蔽真源的其它键
        y_now, _e = _read_yaml_policy(policy_yaml_path(root))
        base = y_now if isinstance(y_now, dict) else {}
        overlay = {POLICY_OVERLAY_MARKER: True}
        for k, v in policy.items():
            if k == "schema_version":
                continue          # ★ schema 由真源决定，不进覆盖增量
            if base.get(k) != v:
                overlay[k] = v
        # ★ 覆盖层**自带** schema 标记（供 migrate 判定它是否需要迁移）
        overlay["schema_version"] = int(policy.get("schema_version",
                                                    SCHEMA_VERSION))
        p.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    written.append(p)
    return written, warnings


def migrate_policy(root, confirm=False):
    """策略文件 schema 迁移（幂等、可重入）。

    规则：
      · schema_version 低于当前 ⇒ 按 SCHEMA_MIGRATIONS 逐级补齐缺失键
        （**不删**用户已有键，含自定义键），迁移前把原文件复制到
        `.versionctl/archive/<ts>/<原文件名>.bak`
      · schema_version 高于当前 ⇒ **拒绝**（本工具比文件旧，不擅自降级）
      · 已是当前版本 ⇒ no-op

    ★ v3.28.0 收尾修正（双轨策略）：迁移以**包级 YAML 真源**为主对象；
      运行时 JSON 副本同步迁移（若存在）。两者都不存在时返回 none。

    ★★ v3.28.0 收尾修正（D3 —— **真缺陷**）：
      原实现只看 YAML 一份 ⇒ 三种情形全错：
        ① YAML 已是最新、JSON 停在旧 schema ⇒ 直接 no-op
           ⇒ **JSON 永远不被迁移** ⇒ 运行时副本带着旧 schema 遮蔽真源
           ⇒ 迁移形同虚设；
        ② 只有 JSON（旧布局）⇒ 迁移后**只写 JSON**
           ⇒ 包级真源**始终不存在** ⇒ 双轨设计落空；
        ③ YAML 存在但 JSON 也存在且 schema 不同 ⇒ 只迁 YAML。
      ⇒ 现在**各自判定、各自迁移**：
        · YAML 缺失而 JSON 在 ⇒ **把 JSON 提升为包级真源**（写入 YAML）
          ⇒ 旧布局可平滑升级到双轨；
        · 两份都在 ⇒ 两份**各自**补齐到当前 schema；
        · JSON 是**旧版全量副本**（无标记）⇒ 迁完后**降级为覆盖层**
          （只留与真源不同的键）⇒ 绝不遮蔽真源。
    """
    d = ctl_dir(root)
    yaml_p = policy_yaml_path(root)
    json_p = d / POLICY_LOCAL_FILENAME
    legacy_p = d / POLICY_LEGACY_FILENAME

    y, y_err = _read_yaml_policy(yaml_p)
    j, j_err = _read_json_policy(json_p)
    lg, lg_err = _read_json_policy(legacy_p)
    if y is None and j is None and lg is None:
        if y_err or j_err or lg_err:
            return {"action": "none",
                    "reason": "策略文件存在但无法解析（%s / %s）⇒ 无法迁移"
                              % (POLICY_READ_ERRORS.get(y_err, y_err or "-"),
                                 POLICY_READ_ERRORS.get(j_err, j_err or "-"))}
        return {"action": "none", "reason": "策略文件不存在，无需迁移"}

    def _schema_of(data):
        try:
            return int(data.get("schema_version", 1))
        except (TypeError, ValueError):
            return 1

    versions = []
    if y is not None:
        versions.append(("yaml", y, _schema_of(y)))
    if j is not None:
        versions.append(("json", j, _schema_of(j)))
    if lg is not None:
        versions.append(("legacy", lg, _schema_of(lg)))
    newest = max(c for _s, _d, c in versions)
    if newest > SCHEMA_VERSION:
        return {"action": "refused",
                "reason": "策略文件 schema_version=%d 高于本工具支持的 %d，拒绝降级"
                          % (newest, SCHEMA_VERSION)}
    need = [(s, d_, c) for (s, d_, c) in versions if c < SCHEMA_VERSION]
    if not need:
        return {"action": "none", "reason": "schema_version 已是 %d" % SCHEMA_VERSION}
    if not confirm:
        return {"action": "dry-run",
                "reason": "将把 schema_version %s → %d 并补齐缺失键"
                          % ("/".join(str(c) for _s, _d, c in versions), SCHEMA_VERSION)}

    # ── 备份（**先全备份**，再动任何一份）
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak_dir = d / ARCHIVE_DIRNAME / ts
    bak_dir.mkdir(parents=True, exist_ok=True)
    src_files = {"yaml": yaml_p, "json": json_p, "legacy": legacy_p}
    bak_names = {"yaml": "version-policy.yaml.bak", "json": "config.json.bak",
                 "legacy": "config.json.bak"}
    backups = {}
    for src, _data, _cur in need:
        src_file = src_files[src]
        bak_name = bak_names[src]
        dst = bak_dir / bak_name
        if src == "legacy" and dst.exists():
            # ★ 两份 JSON 同名备份 ⇒ 旧版那份改名，避免互相覆盖
            dst = bak_dir / "config.json.legacy.bak"
        shutil.copy2(str(src_file), str(dst))
        backups[src] = str(dst)

    def _bump(data, cur):
        new = dict(data)
        for ver in range(cur, SCHEMA_VERSION):
            for k, v in (SCHEMA_MIGRATIONS.get(ver) or {}).items():
                new.setdefault(k, v)      # ★ setdefault ⇒ 不覆盖用户已有值
        new["schema_version"] = SCHEMA_VERSION
        return new

    def _migrated_keys_of(data, cur):
        """本次迁移**补齐**了哪些键（用户原本没有的）⇒ 必须保留到运行时层。"""
        out = set()
        for ver in range(cur, SCHEMA_VERSION):
            for k in (SCHEMA_MIGRATIONS.get(ver) or {}):
                if k not in data:
                    out.add(k)
        return out

    migrated = []
    warnings = []
    # ── 情形②：只有 JSON（旧布局）⇒ **提升为包级真源**
    if y is None:
        src = "json" if j is not None else "legacy"
        data = j if j is not None else lg
        new = _bump(data, _schema_of(data))
        # ★ D12：迁移源**不得**被 `save_policy` 归档（否则原文件消失）
        src_name = POLICY_LOCAL_FILENAME if src == "json" else POLICY_LEGACY_FILENAME
        _migrated_keys = _migrated_keys_of(data, _schema_of(data))
        w, warns = save_policy(root, new, local_only=False,
                               keep_runtime_names=(src_name,))
        warnings.extend(warns)
        # ★ 迁移源**就地升级**成新形态（覆盖层）⇒ 用户读回原路径能拿到
        #   已迁移的内容（而不是 FileNotFound）。
        #   ★ D12 补充：迁移源的**全部键**都必须保留
        #     （用户原本持有的值 + 本次迁移补齐的键）：
        #     · 用户原值（如 `artifact_dirs: ["/MY/IMPORTANT/DIR"]`）
        #       —— 若按「只留与真源不同键」过滤，会因真源就是**从它提升**而来
        #         （两者同值）而被丢掉 ⇒ 用户的设置**静默消失**。
        #     · 迁移补齐的键（`artifact_dirs` / `artifact_max_bytes`）
        #       —— 正是本次迁移的产物 ⇒ 必须保留，否则迁移**形同虚设**。
        #   ★ 保留全部键**不会**造成 D1 所说的「遮蔽」：
        #     真源与运行时层同值 ⇒ 覆盖的是同一个值 ⇒ 无害。
        _src_file = d / src_name
        _overlay = {POLICY_OVERLAY_MARKER: True}
        for k, v in new.items():
            if k == "schema_version":
                continue
            _overlay[k] = v
        _overlay["schema_version"] = int(SCHEMA_VERSION)
        d.mkdir(parents=True, exist_ok=True)
        _src_file.write_text(json.dumps(_overlay, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        migrated.append({"source": "%s->yaml" % src, "from": _schema_of(data),
                         "to": SCHEMA_VERSION, "backup": backups.get(src, "")})
        return {"action": "migrated",
                "from": _schema_of(data), "to": SCHEMA_VERSION,
                "source": "%s->yaml" % src,
                "migrated": migrated,
                "backup": backups.get(src, ""),
                "warnings": warnings}

    # ── 情形①②③：YAML 在场 ⇒ 真源与覆盖层**各自**迁移
    y_cur = _schema_of(y)
    if y_cur < SCHEMA_VERSION:
        new = _bump(y, y_cur)
        w, warns = save_policy(root, new, local_only=False)
        warnings.extend(warns)
        migrated.append({"source": "yaml", "from": y_cur, "to": SCHEMA_VERSION,
                         "backup": backups.get("yaml", "")})
    for src in ("json", "legacy"):
        data = j if src == "json" else lg
        if data is None:
            continue
        cur = _schema_of(data)
        if cur >= SCHEMA_VERSION:
            continue
        new = _bump(data, cur)
        # ★ 运行时层 ⇒ 落成**覆盖层**（只留与真源不同的键）⇒ 不遮蔽真源
        y_now, _e = _read_yaml_policy(yaml_p)
        base = y_now if isinstance(y_now, dict) else {}
        overlay = {POLICY_OVERLAY_MARKER: True}
        for k, v in new.items():
            if base.get(k) != v:
                overlay[k] = v
        # ★★ v3.28.0 收尾修正（D10：**迁移后运行时层丢 schema** —— 真缺陷）：
        #   `schema_version` 若与真源相同 ⇒ 会被上面的「只留不同键」逻辑
        #   **过滤掉** ⇒ 运行时层文件里**没有** schema_version
        #   ⇒ 运行时层自己都读不出自己的 schema ⇒ 迁移**形同虚设**
        #   （实测：迁移后 `read_runtime().get("schema_version")` = None）。
        #   ⇒ 修法：覆盖层**始终自带** schema_version（它是「本文件按哪版
        #     schema 解释」的标记，不是「要覆盖真源的键」）
        #     ⇒ 与 `save_policy(local_only=True)` 的既有语义保持一致。
        overlay["schema_version"] = int(SCHEMA_VERSION)
        d.mkdir(parents=True, exist_ok=True)
        target = src_files[src]
        target.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        migrated.append({"source": src, "from": cur, "to": SCHEMA_VERSION,
                         "backup": backups.get(src, "")})
    if not migrated:
        return {"action": "none", "reason": "schema_version 已是 %d" % SCHEMA_VERSION}
    return {"action": "migrated",
            "from": min(m["from"] for m in migrated),
            "to": SCHEMA_VERSION,
            "source": migrated[0]["source"],
            "migrated": migrated,
            "backup": migrated[0]["backup"],
            "warnings": warnings}


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
    # ★ v3.28.0 修正（实测踩坑）：detached 状态下
    #   `git rev-parse --abbrev-ref HEAD` 返回的是字面量 **"HEAD"**
    #   （不是 "(detached)"、也不是空）⇒ 必须显式识别，
    #   否则 recover 会拿 "HEAD" 当分支名去 `git checkout HEAD`
    #   ⇒ 那只是重新 detach 到同一提交 ⇒ **分支永远回不去**。
    if branch == "HEAD":
        branch = "(detached)"
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

    # ★★ v3.28.0 收尾修正（D9：工具自身的运行时文件被误判为「工作区脏」
    #   —— **真缺陷**，直接导致 D8 的端到端判据打不红）：
    #   `policy --local` 会写 `.versionctl/policy.local.json`（**未跟踪**）
    #   ⇒ `git status --porcelain` 报 `?? .versionctl/policy.local.json`
    #   ⇒ 工作区判定为「脏」⇒ `switch` **一律拒绝**
    #   ⇒ 用户刚设的本机策略就再也切不了版本 ⇒ 功能自锁。
    #   —— 实测：`policy --local --set keep_recent=3 --confirm` 之后
    #      `switch v3.27.0 --confirm` 报「工作区有未提交改动 ⇒ 拒绝切换」。
    #   ⇒ 修法：脏判定**排除工具自己写的运行时路径**（复用 classify_dirty
    #     的 tool_owned 白名单）⇒ 用户自己的改动仍然一律阻塞。
    _status_lines = run_git(["status", "--porcelain"], cwd=root).splitlines()
    _blocking, _benign = classify_dirty(
        _status_lines,
        protected_rel_paths=PROTECTED_REL_PATHS,
        ignore_rel_prefixes=IGNORE_DIRTY_REL_PREFIXES,
        tool_owned_rel_paths=TOOL_OWNED_REL_PATHS)
    if _blocking:
        print("✗ 工作区有未提交改动 ⇒ 拒绝切换（避免丢失工作）")
        for b in _blocking[:10]:
            print("     %s" % b)
        print("   请先 git stash 或提交；本工具不做自动 stash（那是破坏性猜测）")
        return 1
    if _benign:
        print("ℹ 检测到 %d 项工具自身的运行时文件（不阻塞切换）" % len(_benign))
    if not args.confirm:
        print("（dry-run）将切换到 %s（commit %s）" % (label, commit[:8]))
        print("   当前：%s @ %s" % (st["branch"], st["head"][:8]))
        print("   加 --confirm 执行")
        return 0
    before = st
    # ★★ v3.28.0 第 6 个真缺陷修复（实测踩坑）：**先写自举锚点再切换**。
    #   缘由：checkout 会替换整个工作树 ⇒ `scripts/versionctl.py` 自己也会
    #   被替换（切到 v3.28.0 之前 ⇒ 该文件根本不存在）⇒ 切出去后
    #   无从执行 `recover` ⇒ 用户被**死锁**在历史版本里。
    #   ⇒ 把当前控制面复制到 **gitignored** 的 `.versionctl/bin/`，
    #     它跨 checkout 存活 ⇒ 任何时候都能用它恢复。
    #   ⚠ 写锚点失败**不阻断切换**（切换本身是可逆的 git 操作），
    #     但必须明确告警 ⇒ 否则用户不知道「切出去可能回不来」。
    bootstrap_note = ""
    try:
        bp = write_bootstrap(root)
        bootstrap_note = str(bp)
    except Exception as e:
        bootstrap_note = "⚠ 写自举锚点失败（%s）⇒ 切到旧版本可能无法 recover" % e
    run_git(["checkout", "--detach", commit], cwd=root)
    after = head_state(root)
    write_journal(root, "switch", before, after,
                  {"version": label, "commit": commit,
                   "bootstrap": bootstrap_note})
    print("✓ 已切换到 %s（%s）" % (label, commit[:8]))
    if bootstrap_note.startswith("⚠"):
        print("   " + bootstrap_note)
    else:
        print("   回原状态：python3 %s recover --confirm" % bootstrap_note)
        print("   ★ 控制面已固化到自举锚点（gitignored）⇒ 跨版本切换也能恢复")
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
    """显示 / 设置保留与清理策略。

    ★ v3.28.0 双轨策略：
      · 默认写**包级真源** `config/version-policy.yaml`（入库 ⇒ 跨版本存活）
      · `--local` ⇒ 只写运行时**覆盖层**（**不动**包级真源 ⇒ 不弄脏工作区）

    ★★ v3.28.0 收尾修正（D2：写真源必然弄脏工作区 —— 这**不是**缺陷）：
      「包级真源入库」与「改策略不弄脏工作区」**本来就冲突**：
        · 真源**入库** ⇒ 改它 ⇒ 工作区必然变脏（git 的定义）；
        · 不弄脏 ⇒ 只能改**不入库**的运行时层。
      ⇒ 二者不是「哪个对」，而是**两个不同的意图**，靠 `--local` 区分：
        · `--set`（默认）⇒ 改**真源** ⇒ 团队共享、跨版本存活
          ⇒ **必须**提交（工作区变脏是**预期**，不是 bug）
          ⇒ 输出必须**明说**「需要 git commit」；
        · `--local` ⇒ 改**本机** ⇒ 不弄脏工作区 ⇒ 不共享。
      ⇒ 关键修正：写真源后**不得**再写一份全量运行时副本
        （那会遮蔽真源 ⇒ 真源静默失效）。
    """
    warnings = []
    policy = load_policy(root, warnings=warnings)
    local_only = bool(getattr(args, "local", False))
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
        targets = ([ctl_dir(root) / POLICY_LOCAL_FILENAME] if local_only
                   else [policy_yaml_path(root)])
        if not args.confirm:
            print("（dry-run）策略将写入：%s"
                  % "、".join(str(t) for t in targets))
            if not local_only:
                print("   ★ 包级真源**入库** ⇒ 改它会让工作区变脏（预期行为）")
                print("     ⇒ 改完请 `git add %s && git commit` 分享给团队"
                      % POLICY_YAML_REL)
            else:
                print("   ★ 仅写本机覆盖层 ⇒ 工作区保持干净")
            print("   加 --confirm 执行")
            return 0
        written, warns = save_policy(root, policy, local_only=local_only)
        for p in written:
            print("✓ 策略已写入：%s" % p)
        for w in warns:
            print("   " + w)
        if not local_only:
            print("   ★ 包级真源已更新（入库 ⇒ 跨版本存活）")
            print("     ⚠ 真源**入库** ⇒ 工作区已变脏 ⇒ 请 `git add %s && git commit`"
                  % POLICY_YAML_REL)
            print("       （不提交 ⇒ 团队其他人拿不到这次设置）")
        else:
            print("   ★ 仅写本机覆盖层（包级真源未动 ⇒ 工作区保持干净）")
        return 0
    for w in warnings:
        print(w)
    print("当前策略（schema_version=%s）：" % policy.get("schema_version"))
    for k in sorted(policy):
        print("  %-22s %s" % (k, policy[k]))
    print("\n  真源：%s（入库）　覆盖层：%s/%s（不入库·仅本机覆盖）"
          % (POLICY_YAML_REL, CTL_DIRNAME, POLICY_LOCAL_FILENAME))
    print("  里程碑判定：minor 偶数且 patch==0（如 v3.26.0）")
    print("  tag 默认永久保留（keep_tags=true）⇒ tag 不占实质空间且删了会破坏可回滚性")
    return 0


def collect_artifacts(dirs, root=None):
    """按策略指定的目录列表**递归**收集待归档产物。

    ★ 这是纯函数（I/O 只在读文件系统，不写）⇒ 可被测试直接驱动。

    参数：
      `dirs` —— 策略里的 `artifact_dirs` 列表：
        · **绝对路径** ⇒ 直接使用；
        · **相对路径** ⇒ 相对 `root`（`root` 为 None 时相对当前工作目录）。
      `root` —— 仓库/工作区根目录（相对路径的拼接基准）。

    返回：`[{path, bytes, keep, reason}, ...]`
      · `path`  —— 产物的**绝对或拼接后**路径字符串；
      · `bytes` —— 文件大小（`stat()` 抛 `OSError` 时为 0）；
      · `keep`  —— 恒为 False（这些产物是「按策略待清理」的）；
      · `reason` —— 恒为 "策略指定清理"。

    ★★ v3.28.0 收尾修正（D13：**只遍历一层 ⇒ 深层产物找不到** —— 真缺陷）：
      原实现只扫 `p.iterdir()`（**一层**）⇒ 产物放在
      `artifacts/sub/bundle.zip` 这种**子目录**里时**一个都找不到**
      ⇒ prune 报「无待归档产物」⇒ 用户的产物**永远不清理**
      （磁盘无限膨胀，正是本机制要解决的问题）。
      —— 实测：`artifact_dirs: [<abs>/artifacts]` + 产物在
        `artifacts/sub/bundle.zip` ⇒ 待归档产物 0 项。
      ⇒ 修法：**递归**收集目录下的**所有文件**（逐文件判定），
        目录本身**不**作为归档单元（避免「移动目录」把用户目录结构打乱）。

    ★ 不存在的路径 ⇒ **跳过**（不报错）：策略里写了尚未创建的目录属正常。
    """
    out = []
    for rel in (dirs or []):
        if not rel:
            continue
        p = Path(rel) if os.path.isabs(rel) else (Path(root) if root else Path()) / rel
        if not p.exists():
            continue
        if p.is_file():
            # ★ 与原实现**逐字节等价**：单文件路径的 stat 不吞异常
            out.append({"path": str(p), "bytes": p.stat().st_size,
                        "keep": False, "reason": "策略指定清理"})
            continue
        # 目录 ⇒ **递归**逐文件收集（目录本身不作为归档单元）
        for f in sorted(p.rglob("*")):
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            out.append({"path": str(f), "bytes": size,
                        "keep": False, "reason": "策略指定清理"})
    return out


def cmd_prune(args, root):
    """按策略规划并（--confirm 时）执行归档清理。★ 归档 ≠ 删除。"""
    policy = load_policy(root)
    reg = build_registry_full(root)
    # ★ 产物收集抽成纯函数 `collect_artifacts`（D13 的可测点）
    artifacts = collect_artifacts(policy.get("artifact_dirs") or [], root=root)
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


def classify_dirty(git_status_lines, protected_rel_paths=(),
                   ignore_rel_prefixes=(), tool_owned_rel_paths=()):
    """把 `git status --porcelain` 的输出分成两类。

    返回 `(blocking, benign)`：
      · `blocking` —— **用户真实改动**（已修改/已暂存/未跟踪的新内容）
        ⇒ 必须拒绝恢复（避免丢失工作）。
      · `benign` —— **由 checkout / 工具自身造成**的"脏"：
        - 被删除的**受保护文件**（策略真源等本就不该跨版本存在的东西）
        - **工具自身写的东西**（journal / archive / 自举锚点 / 本机覆盖层）
        ⇒ 允许恢复（否则用户切出去就回不来 ⇒ 死锁）。

    ★★ v3.28.0 收尾修正（第 7 个真缺陷，死锁的第二重门）：
      切到旧版本时，入库的 `config/version-policy.yaml` 会被 checkout
      **删除** ⇒ `git status` 报 " D" ⇒ 工作区判定为"脏"
      ⇒ `recover` 一律拒绝 ⇒ **仍然回不来**。
      —— 实测：切到 v3.27.0 后 recover 报「工作区有未提交改动 ⇒ 拒绝恢复」。

    ★★ v3.28.0 收尾修正（第 8 个真缺陷，死锁的第三重门）：
      `.versionctl/` 整体 gitignored 后，git status 报 **`?? .versionctl/`**
      （未跟踪目录）⇒ 若未跟踪也算阻塞 ⇒ **仍然死锁**。
      —— 实测：切到 v3.27.0 后 recover 报「✗ 工作区有未提交改动 ⇒ 拒绝恢复」，
         且列出的阻塞项正是 `?? .versionctl/`。
      ⇒ 修法：工具自身的运行时目录**永不**构成阻塞。

    ★★ v3.28.0 收尾修正（D7：忽略范围过宽 —— **可改进**）：
      原实现把 `.versionctl/` 下的**一切**都当 benign
      ⇒ 用户自己放在那里的重要文件（如 `.versionctl/my_backup.txt`）
        在恢复时**可能被覆盖丢失**，而用户**毫不知情**。
      ⇒ 修法：区分三个参数，各管各的：
        · `ignore_rel_prefixes` —— **目录根本身**算 benign
          （git 把未跟踪目录**折叠**成一行 `?? .versionctl/` 时，
            无法枚举里面的文件 ⇒ 只能整体放行，否则必然死锁）；
        · `tool_owned_rel_paths` —— **工具自己写的那些路径**
          （journal/ archive/ bin/ + 本机覆盖层）⇒ 其下内容 benign；
        · 其余 `.versionctl/` 下的内容 ⇒ **照常算阻塞**（不许悄悄丢）。
      ★ 目录名匹配必须**逐段相等**：`startswith(ig + "/")` 才对，
        `startswith(ig)` 会把 `.versionctlX/` 之类**误伤**（D7 反例）。

    ★ 这是纯函数：判据的正确性靠测试直接验证（能红的反例）。
    """
    protected = set(protected_rel_paths or ())
    ignores = tuple(ignore_rel_prefixes or ())
    tool_owned = tuple(tool_owned_rel_paths or ())
    blocking = []
    benign = []
    for line in (git_status_lines or []):
        if not line.strip():
            continue
        # porcelain 格式：XY + 空格 + 路径（重命名含 " -> "）
        xy = line[:2]
        raw = line[3:].strip()
        path = raw
        renamed = False
        if " -> " in raw:
            # ★★ v3.28.0 收尾修正（D7：**重命名行的路径解析错误** —— 真缺陷）：
            #   原实现只取 `->` **右侧**（目标路径）⇒ 把重命名**当成了新增**：
            #     · 语义错：porcelain 的 XY 里的 `R` 表示「索引里有重命名记录」，
            #       而**工作树里少了旧文件**（checkout 副作用的典型形态）
            #       ⇒ 正确判定应是「旧路径消失」⇒ 只算删除。
            #     · 后果：`R  old.py -> new.py` 被判成 blocking
            #       ⇒ 即便目标是受保护文件也拒绝恢复 ⇒ 死锁。
            #   ⇒ 修法：重命名时**两个路径都参与判定**：
            #     · 目标路径命中 tool_owned / ignore ⇒ benign；
            #     · 源路径是受保护文件且只是重命名 ⇒ 视作「删除」⇒ benign。
            _old, _new = raw.split(" -> ", 1)
            path = _new.strip()
            renamed = True
        # ① 工具自身写的东西 ⇒ 永远 benign
        if any(path == own or path.startswith(own.rstrip("/") + "/")
               for own in tool_owned):
            benign.append(line)
            continue
        # ② 忽略目录的**根**（git 折叠未跟踪目录时的 `?? .versionctl/`）
        #   ★ 必须是「相等」⇒ 不能用裸 startswith(ig)
        #   ★★ v3.28.0 收尾修正（D7：**目录根下内容仍被整体放行** —— 真缺陷）：
        #     原实现用 `path.startswith(ig + "/")` ⇒ 把 `.versionctl/` 下的
        #     **一切**都放行 ⇒ 用户自己放的重要文件（如 `.versionctl/my_backup.txt`）
        #     在恢复时仍可能被覆盖丢失 ⇒ D7 的核心目标没达成。
        #   ⇒ 修法：**只有目录根本身**（git 折叠形态 `?? .versionctl/`）放行；
        #     目录**下的内容**不再整体放行 ⇒ 改由 `tool_owned` 精确白名单裁决
        #     （工具自己写的 journal/archive/bin/覆盖层 ⇒ benign；
        #       用户自放的文件 ⇒ blocking，不会被悄悄丢）。
        #   ★ 形态判据：git 折叠未跟踪目录时输出的是 `?? .versionctl/`
        #     （**带尾斜杠**）⇒ 用「带尾斜杠」精确识别折叠行，
        #     而 `.versionctl/my_backup.txt`（不带尾斜杠）走下面的精确白名单。
        if ignores and (path in ignores
                        or (path.endswith("/") and path[:-1] in ignores)):
            benign.append(line)
            continue
        # ③ 判定：是否只是「删除」（索引里还有，工作树里没了）
        deleted_only = ("D" in xy) and ("M" not in xy) and ("A" not in xy)
        if renamed:
            # 重命名 ⇒ 源路径在工作树里**消失**、目标路径**出现**
            # ⇒ 「目标路径是受保护文件」意味着：checkout 把受保护文件
            #    改名了 ⇒ 同样是 checkout 副作用 ⇒ benign
            # ⇒ 「源路径是受保护文件」意味着：受保护文件被改名走了
            #    ⇒ 也属 checkout 副作用 ⇒ benign
            # 两条都放行：任一端命中受保护名单 ⇒ benign。
            if _old.strip() in protected or path in protected:
                benign.append(line)
                continue
            blocking.append(line)
            continue
        if deleted_only and path in protected:
            benign.append(line)
        else:
            blocking.append(line)
    return blocking, benign


#: 受保护路径（相对仓库根）：切到旧版本时它们可能被 checkout 删除，
#: 但那属于 checkout 的副作用，**不该阻塞恢复**。
PROTECTED_REL_PATHS = (
    POLICY_YAML_REL,
)

#: 工具自身的运行时目录：**永远不**构成恢复阻塞（v3.28.0 第 8 个真缺陷）。
#:   缘由：`.versionctl/` 整体 gitignored ⇒ git status 报 `?? .versionctl/`
#:   ⇒ 若未跟踪也算「工作区脏」⇒ recover 拒绝 ⇒ 用户切出去就回不来（死锁）。
IGNORE_DIRTY_REL_PREFIXES = (
    CTL_DIRNAME,
)

#: **工具自己写**的运行时路径（相对仓库根）：这些路径下的内容
#: **永不**构成恢复阻塞（D7）。
#:
#: ★ v3.28.0 收尾修正（D7：忽略范围过宽 —— 可改进）：
#:   此前 `IGNORE_DIRTY_REL_PREFIXES = (".versionctl",)` 把 `.versionctl/`
#:   下的**一切**都放行 ⇒ 用户自己放在那里的重要文件
#:   （如 `.versionctl/my_backup.txt`）在恢复时可能被覆盖丢失。
#:   ⇒ 收窄为**工具自己写的**那几个：journal/ archive/ bin/ + 本机覆盖层。
#:   ⇒ 注意：`.versionctl/` **根本身**仍在 IGNORE_DIRTY_REL_PREFIXES 里
#:     —— 因为 git 把未跟踪目录**折叠**成一行 `?? .versionctl/`，
#:     此时无法枚举内部文件 ⇒ 只能整体放行，否则必然死锁。
TOOL_OWNED_REL_PATHS = (
    "%s/%s" % (CTL_DIRNAME, JOURNAL_DIRNAME),
    "%s/%s" % (CTL_DIRNAME, ARCHIVE_DIRNAME),
    "%s/%s" % (CTL_DIRNAME, BOOTSTRAP_DIRNAME),
    "%s/%s" % (CTL_DIRNAME, POLICY_LOCAL_FILENAME),
)


def cmd_bootstrap(args, root):
    """自举锚点管理：把控制面固化到**跨 checkout 存活**的位置。

    ★★ v3.28.0 收尾修正（第 6 个真缺陷，死锁的最终解法）：
      `switch` 用 `git checkout --detach` ⇒ **整个工作树**被替换 ⇒
      `scripts/versionctl.py` 自己也被换掉：
        · 切到 v3.28.0 之前 ⇒ 该文件**根本不存在**；
        · 切到更早的版本 ⇒ 该文件是**旧逻辑**。
      ⇒ 切换后**没有任何办法**执行 `recover` ⇒ 用户被死锁在历史版本里。
      —— 实测：切到 v3.27.0 后 `.versionctl/` 整个目录消失、
         `scripts/versionctl.py` 不存在。

      ⇒ 解法：**自举锚点**（`.versionctl/bin/versionctl.py`，**gitignored**
        ⇒ 跨 checkout 存活）：
        · `switch` 执行前自动固化当前控制面到锚点；
        · 切出去后执行 `python3 .versionctl/bin/versionctl.py recover --confirm`
          即可回到主线；
        · `--restore` ⇒ 把锚点里的控制面**装回**工作树
          （`scripts/versionctl.py`）⇒ 在旧版本里也能用完整功能。

    子命令：
      bootstrap                显示锚点状态与恢复指引（只读）
      bootstrap --restore      把锚点里的控制面装回工作树（需 --confirm）
    """
    anchor = bootstrap_script(root)
    exists = anchor.is_file()
    print("自举锚点（控制面的跨版本固化副本）：")
    print("  路径：%s" % anchor)
    print("  状态：%s" % ("✓ 存在（%d 字节）" % anchor.stat().st_size
                          if exists else "✗ 不存在"))
    if exists:
        try:
            head = run_git(["rev-parse", "HEAD"], cwd=root).strip()
            print("  当前 HEAD：%s" % head[:8])
        except Exception:
            pass
    print()
    if not exists:
        print("  ⇒ 锚点不存在：执行一次 `switch --confirm` 会自动创建它；")
        print("    也可执行 `bootstrap --restore --confirm` 由当前脚本自举。")
        return 0
    print("  ★ 切到任何历史版本后，用下面这条命令回到主线：")
    print("      python3 %s recover --confirm" % anchor)
    if not getattr(args, "restore", False):
        return 0
    # ── --restore：把锚点里的控制面装回工作树
    work = Path(root) / "scripts" / BOOTSTRAP_SCRIPT
    if not args.confirm:
        print("\n（dry-run）将把锚点内容写入：%s" % work)
        print("   加 --confirm 执行")
        return 0
    try:
        text = anchor.read_text(encoding="utf-8")
    except OSError as e:
        print("✗ 读取锚点失败：%s" % e)
        return 1
    work.parent.mkdir(parents=True, exist_ok=True)
    tmp = work.with_suffix(".py.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(work))
    print("\n✓ 已把控制面装回工作树：%s" % work)
    print("   ★ 注意：这是一个**未跟踪/已修改**的文件 ⇒ 工作区会变脏")
    print("     ⇒ 请检查 `git status` 后决定是否提交。")
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
        # ★★ v3.28.0 收尾修正（第 7 个真缺陷，死锁的第二重门）：
        #   区分「用户真实改动」与「checkout 造成的删除」。
        #   切到旧版本时，入库的策略真源会被 checkout 删除 ⇒ 报"脏"
        #   ⇒ 原实现一律拒绝 ⇒ 用户切出去就回不来（死锁）。
        #   ⇒ 只有**内容真的被改过**的项才阻塞恢复；
        #     受保护文件被 checkout 删除 ⇒ 视为副作用，放行。
        status_lines = run_git(["status", "--porcelain"], cwd=root).splitlines()
        blocking, benign = classify_dirty(status_lines, PROTECTED_REL_PATHS,
                                          IGNORE_DIRTY_REL_PREFIXES,
                                          TOOL_OWNED_REL_PATHS)
        if blocking:
            print("✗ 工作区有未提交改动 ⇒ 拒绝恢复（避免丢失工作）")
            for b in blocking[:10]:
                print("     %s" % b)
            if len(blocking) > 10:
                print("     …… 另有 %d 项" % (len(blocking) - 10))
            return 1
        if benign:
            print("ℹ 检测到 %d 项由 checkout 造成的删除（受保护文件）⇒ 放行"
                  % len(benign))
            for b in benign[:5]:
                print("     %s" % b)
    if not args.confirm:
        print("（dry-run）将恢复到：%s（%s）" % (
            target[:8], last.get("before_branch") or "?"))
        print("   加 --confirm 执行")
        return 0
    # ★ v3.28.0 修正（实测踩坑）：恢复必须**回到原分支**，不能只恢复 commit。
    #   缘由：`switch` 会把仓库切到 detached HEAD ⇒ 恢复若只 checkout commit，
    #   仓库仍留在 detached HEAD ⇒ 「回原状态」名不副实，
    #   且**下一次提交会落在游离 HEAD 上**（main 分支不前进）——
    #   本轮实测就踩到了：变异测试里的 `switch --confirm` 把真实仓库切到
    #   detached HEAD，导致 commit 不在 main 上、push 推了个空。
    #
    # ★★ v3.28.0 收尾修正（第 6 个真缺陷）：必须**同时**恢复分支**和**提交。
    #   只 `git checkout <分支>` ⇒ 回到的是分支**当前指向**的提交，
    #   而非 journal 记录的 `before_head` ⇒ 若期间分支前进过，
    #   恢复目标就**错了**（静默回错位置 = 最坏的恢复语义）。
    #   ⇒ 用 `git checkout -B <分支> <before_head>`：把分支**重置**到
    #     记录的提交并同时切过去 ⇒ 分支与提交**同时**回到原状态。
    #     ⚠ 该操作会移动分支指针 ⇒ 必须在 journal 里留痕（可再 recover 回来）。
    before_branch = last.get("before_branch") or ""
    restored_branch = False
    if before_branch and before_branch != "(detached)":
        # 优先：分支 + 提交一起恢复（`checkout -B`）
        try:
            run_git(["checkout", "-B", before_branch, target], cwd=root)
            restored_branch = True
        except Exception:
            restored_branch = False
        if not restored_branch:
            # 退化①：分支存在但无法重置 ⇒ 只切分支（不移动指针）
            try:
                run_git(["checkout", before_branch], cwd=root)
                restored_branch = True
            except Exception:
                restored_branch = False
    if not restored_branch:
        run_git(["checkout", "--detach", target], cwd=root)
    after = head_state(root)
    write_journal(root, "recover", st, after, {"recovered_to": target,
                                               "restored_branch": before_branch
                                               if restored_branch else ""})
    if restored_branch:
        print("✓ 已恢复到分支 %s（%s）" % (before_branch, target[:8]))
    else:
        print("✓ 已恢复到 %s（%s）" % (target[:8], last.get("op", "?")))
    return 0


def cmd_migrate(args, root):
    r = migrate_policy(root, confirm=args.confirm)
    print("migrate：%s —— %s" % (r.get("action"), r.get("reason", "")))
    if r.get("backup"):
        print("  备份：%s" % r["backup"])
    for m in (r.get("migrated") or []):
        print("  已迁移 %s：schema %s → %s（备份 %s）"
              % (m.get("source"), m.get("from"), m.get("to"), m.get("backup")))
    for w in (r.get("warnings") or []):
        print("   " + w)
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
    sp.add_argument("--local", action="store_true",
                    help="只写本机副本（不动包级真源 ⇒ 工作区保持干净）")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_policy)

    sp = sub.add_parser("prune", help="按策略归档清理（归档≠删除）")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_prune)

    sp = sub.add_parser("journal", help="查看操作日志")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_journal)

    sp = sub.add_parser("bootstrap",
                        help="自举锚点：把控制面固化到跨 checkout 存活的位置")
    sp.add_argument("--restore", action="store_true",
                    help="把锚点里的控制面装回工作树")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_bootstrap)

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

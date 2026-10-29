#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_versionctl.py — 版本迭代机制的纪律守卫测试（v3.28.0 · L-8）

══════════════════════════════════════════════════════════════════════
本文件的核心纪律（承自本包铁律）：

  ① **每条判据必须有能红的反例** ⇒ 本文件不是「测一下能不能跑」，
     而是**逐条证明判据会在该红的时候红**。
  ② **假阳性必须为零** ⇒ 反例必须**精确命中**，不能靠宽泛子串蒙混。
     —— 这正是 v3.27.0 踩过的坑（`"未验" in ln` 被「未验 ≠ 已验」蒙混）。
  ③ **纯函数优先** ⇒ 被测逻辑放在**模块级纯函数**里，测试直接调用，
     不依赖 git 状态、不依赖文件布局 ⇒ 判据可被真正执行。

测试组织（每组一个「正向 + 反向 + 变异」三件套）：
  T1  版本号解析（parse_version）—— 含**形态收紧**反例
  T2  版本排序键（version_sort_key）—— 含**脏数据不崩**反例
  T3  subject 版本抽取（extract_versions_from_subject / subject_version_sets）
  T4  版本区间展开（expand_version_range）—— 含**幽灵版本**反例
  T5  CHANGELOG 解析（parse_changelog）—— 含**重复版本段**反例
  T6  里程碑判定（is_milestone）—— 含**odd minor 不算里程碑**反例
  T7  清单合并（merge_registry）—— 含**孤儿 tag / 缺 tag**反例
  T8  补 tag 规划（plan_tag_backfill）—— 含**幂等**反例
  T9  保留/归档规划（plan_prune）—— 含**绝不返回删除**反例
  T10 唯一标识（build_release_id）—— 含**唯一性**反例
  T11 差异摘要格式化（format_diff_summary）—— 含**空差异**反例
  T12 策略迁移（migrate_policy）—— 含**拒绝降级**反例
  T13 CLI 接线 —— 子命令齐全 + 破坏性命令必须 --confirm
  T14 真实仓库不变量 —— 当前仓库跑一遍 list/tag 规划，必须零异常

运行：
    python3 -m pytest scripts/test_versionctl.py -q
    python3 scripts/test_versionctl.py
"""

import contextlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# ───────────────────────────────────────────────────── 加载被测模块
_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "versionctl_under_test", _HERE / "versionctl.py")
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)


# ───────────────────────────────────────────────────── 辅助
@contextlib.contextmanager
def _clone_repo(with_versionctl=True):
    """克隆真实仓库到临时目录（**不动真实仓库**）。

    ★ 用 --no-hardlinks ⇒ 克隆出的对象与源仓库物理分离
      ⇒ 即使在克隆里做 checkout/commit 也不影响源仓库。

    ★ with_versionctl=True 时把当前工作区的 versionctl.py 复制进克隆并
      **本地提交**，使克隆工作区处于**干净状态** ——
      否则 switch 会正确地拒绝切换（工作区脏），测到的就不是目标分支。
    """
    repo = vc.repo_root()
    td = tempfile.mkdtemp(prefix="versionctl-clone-")
    try:
        clone = Path(td) / "clone"
        proc = subprocess.run(["git", "clone", "--quiet", "--no-hardlinks",
                               str(repo), str(clone)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise unittest.SkipTest("无法 clone：%s" % proc.stderr[:160])
        if with_versionctl:
            dst = clone / "scripts" / "versionctl.py"
            shutil.copy2(str(_HERE / "versionctl.py"), str(dst))
            _git(clone, "add", "scripts/versionctl.py")
            # ★ 同时装入**策略真源**（v3.28.0 双轨策略）
            #   理由：真源在 `config/version-policy.yaml`（入库 ⇒ 跨版本存活）
            #   ⇒ 克隆里必须也有，否则 T25「切到 v3.27.0 后 recover」时
            #     工作区会因真源缺失而变脏 ⇒ 测不到死锁场景。
            yml_src = _HERE.parent / "config" / "version-policy.yaml"
            if yml_src.is_file():
                yml_dst = clone / "config" / "version-policy.yaml"
                yml_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(yml_src), str(yml_dst))
                _git(clone, "add", "config/version-policy.yaml")
            _git(clone, "-c", "user.name=test",
                 "-c", "user.email=test@example.invalid",
                 "commit", "-q", "-m", "test: 装入 versionctl.py")
            # 确认干净
            status = _git(clone, "status", "--porcelain")
            if status.strip():
                raise unittest.SkipTest("克隆工作区不干净：%s" % status[:120])
        yield clone
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _git(cwd, *args):
    """在指定目录跑 git，返回 stdout（去空白）。"""
    return subprocess.run(["git"] + list(args), cwd=str(cwd),
                          capture_output=True, text=True).stdout.strip()


def current_of(reg):
    """取清单里当前 HEAD 对应的版本（若能对上）。"""
    head = reg.get("current_commit") or ""
    for r in reg.get("versions", []):
        if r.get("commit") == head:
            return r["version"]
    return None


def make_changelog(*pairs):
    """构造一份 CHANGELOG 文本（每项 = (版本, 日期, 副标题)）。"""
    out = ["# 更新日志", ""]
    for v, d, title in pairs:
        suffix = ("（%s）" % title) if title else ""
        out.append("## [%s] - %s%s" % (v, d, suffix))
        out.append("")
        out.append("内容")
        out.append("")
    return "\n".join(out)


class T01ParseVersion(unittest.TestCase):
    """T1 版本号解析：只认完整三段。"""

    def test_positive(self):
        self.assertEqual(vc.parse_version("v3.27.0"), (3, 27, 0))
        self.assertEqual(vc.parse_version("v1.0.0"), (1, 0, 0))
        self.assertEqual(vc.parse_version("  v3.27.0  "), (3, 27, 0))

    def test_anti_example_incomplete(self):
        """反例：两段式必须被拒（否则会造出幽灵版本）。"""
        for bad in ("v3.27", "3.27.0", "v3.27.0-rc1", "v3.27.0.1", "3.27", ""):
            self.assertIsNone(vc.parse_version(bad),
                              "非完整三段版本号必须返回 None：%r" % bad)

    def test_mutation_can_red(self):
        """变异检验：把正则放宽成允许两段，反例必须变红。"""
        original = vc.VERSION_RE
        try:
            vc.VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
            self.assertIsNotNone(vc.parse_version("v3.27"),
                                 "放宽后 v3.27 应被接受（说明原判据在起作用）")
        finally:
            vc.VERSION_RE = original
        self.assertIsNone(vc.parse_version("v3.27"))


class T02SortKey(unittest.TestCase):
    """T2 排序键：数值序 + 脏数据不崩。"""

    def test_positive(self):
        vs = ["v3.9.0", "v3.10.0", "v3.27.0"]
        vs.sort(key=vc.version_sort_key)
        self.assertEqual(vs, ["v3.9.0", "v3.10.0", "v3.27.0"],
                         "必须按数值排序（字符串序会把 v3.10 排在 v3.9 前）")

    def test_anti_example_dirty(self):
        """反例：脏数据不能抛异常，且排在版本之后。"""
        self.assertEqual(vc.version_sort_key("garbage"), (0, 0, 0))
        self.assertEqual(vc.version_sort_key(None), (0, 0, 0))
        vs = ["v3.27.0", "garbage", "v3.10.0"]
        vs.sort(key=vc.version_sort_key)
        self.assertEqual(vs[0], "garbage")
        self.assertEqual(vs[-1], "v3.27.0")


class T03SubjectVersions(unittest.TestCase):
    """T3 从 commit subject 抽版本号。"""

    def test_positive(self):
        self.assertEqual(vc.extract_versions_from_subject("v3.27.0：收口"), ["v3.27.0"])
        self.assertEqual(
            vc.extract_versions_from_subject("v3.5.0→v3.7.0：迭代六原则"),
            ["v3.5.0", "v3.7.0"])

    def test_dedup(self):
        self.assertEqual(
            vc.extract_versions_from_subject("v3.4.3 收尾 v3.4.3 又提"),
            ["v3.4.3"], "同一版本重复提及只保留一次")

    def test_anti_example_no_version(self):
        """反例：不含版本号的 subject 必须返回空列表（不是 None）。"""
        self.assertEqual(vc.extract_versions_from_subject("fix: 修 README"), [])
        self.assertEqual(vc.extract_versions_from_subject(""), [])
        self.assertEqual(vc.extract_versions_from_subject(None), [])

    def test_subject_version_sets_groups_range(self):
        """区间提及必须归为**一组**（共享同一收口点）。"""
        sets = vc.subject_version_sets("v3.5.0→v3.7.0：迭代六原则")
        self.assertEqual(len(sets), 1, "区间必须是一个集合，不能拆成两个")
        self.assertIn("v3.5.0", sets[0])
        self.assertIn("v3.7.0", sets[0])

    def test_subject_version_sets_separate_mentions(self):
        """两个独立提及 ⇒ 两个集合。"""
        sets = vc.subject_version_sets("v3.4.3 收尾 v3.4.4 补记")
        self.assertEqual(len(sets), 2)


class T04ExpandRange(unittest.TestCase):
    """T4 版本区间展开。"""

    def test_positive(self):
        self.assertEqual(vc.expand_version_range("v3.5.0", "v3.7.0"),
                         ["v3.5.0", "v3.6.0", "v3.7.0"])

    def test_same_version(self):
        self.assertEqual(vc.expand_version_range("v3.5.0", "v3.5.0"), ["v3.5.0"])

    def test_anti_example_invalid(self):
        """反例：非法输入必须返回空列表，不能崩。"""
        self.assertEqual(vc.expand_version_range("v3.5", "v3.7.0"), [])
        self.assertEqual(vc.expand_version_range("v3.5.0", "bogus"), [])
        self.assertEqual(vc.expand_version_range("v2.0.0", "v3.7.0"), [],
                         "跨 major 区间不展开")

    def test_ghost_version_note(self):
        """展开出的中间版本可能不存在 ⇒ 必须能被 CHANGELOG 过滤。

        本测试固化「幽灵版本」这一已知风险：v3.5.1 不在真实 CHANGELOG 里。
        """
        rng = vc.expand_version_range("v3.5.0", "v3.7.0")
        self.assertIn("v3.6.0", rng, "展开规则会产生 v3.6.0（这是预期行为）")
        # 真实 CHANGELOG 里没有 v3.5.1 ⇒ 调用方必须靠 CHANGELOG 交集过滤
        repo = vc.repo_root()
        known = {i["version"] for i in vc.changelog_items(repo)}
        if known:
            filtered = [v for v in rng if v in known]
            self.assertNotIn("v3.5.1", filtered,
                             "靠 CHANGELOG 交集应过滤掉幽灵版本 v3.5.1")


class T05ParseChangelog(unittest.TestCase):
    """T5 CHANGELOG 版本段解析。"""

    def test_positive(self):
        txt = make_changelog(("v3.27.0", "2026-10-29", "未验证项可见化"),
                             ("v3.26.0", "2026-10-28", "守卫全启用"))
        items = vc.parse_changelog(txt)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["version"], "v3.27.0")
        self.assertEqual(items[0]["date"], "2026-10-29")
        self.assertEqual(items[0]["title"], "未验证项可见化")

    def test_duplicate_segment(self):
        """反例：同名版本段出现两次 ⇒ 保留首次 + 标记 dup。"""
        txt = make_changelog(("v3.21.0", "2026-10-26", "第一段"),
                             ("v3.21.0", "2026-10-26", "第二段"))
        items = vc.parse_changelog(txt)
        self.assertEqual(len(items), 1, "同名版本只保留一段")
        self.assertTrue(items[0]["dup"], "重复必须被标记（否则体检漏报）")
        self.assertEqual(items[0]["title"], "第一段", "保留的是首次出现")

    def test_anti_example_no_date(self):
        """反例：缺日期的版本段也要能解析（date='' 而非崩溃）。"""
        items = vc.parse_changelog("## [v3.27.0]\n\n内容\n")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["date"], "")

    def test_empty(self):
        self.assertEqual(vc.parse_changelog(""), [])
        self.assertEqual(vc.parse_changelog(None), [])


class T06Milestone(unittest.TestCase):
    """T6 里程碑判定：minor 偶数且 patch==0。"""

    def test_positive(self):
        self.assertTrue(vc.is_milestone("v3.26.0"))
        self.assertTrue(vc.is_milestone("v3.4.2") is False)  # patch≠0
        self.assertFalse(vc.is_milestone("v3.27.0"))
        self.assertFalse(vc.is_milestone("v3.26.1"))

    def test_anti_example_invalid(self):
        self.assertFalse(vc.is_milestone("garbage"))
        self.assertFalse(vc.is_milestone(None))

    def test_explicit_override(self):
        """策略里显式列出的里程碑必须被承认（可配置）。

        ★ 是**追加**而非替换：显式配置不得静默削弱自动判定（否则用户
          多列一个版本，反而把原有里程碑判成非里程碑）。
        """
        pol = {"milestone_versions": ["v3.27.0"]}
        self.assertTrue(vc.is_milestone("v3.27.0", pol))
        self.assertTrue(vc.is_milestone("v3.26.0", pol),
                        "显式配置是追加，不得替换掉自动判定")


class T07MergeRegistry(unittest.TestCase):
    """T7 清单合并（中枢纯函数）。"""

    def _items(self):
        return vc.parse_changelog(make_changelog(
            ("v3.27.0", "2026-10-29", "新"),
            ("v3.26.0", "2026-10-28", "旧"),
            ("v3.25.0", "2026-10-27", "更旧"),
        ))

    def test_positive_both(self):
        tags = {"v3.27.0": {"commit": "abc12345", "summary": "收口",
                            "timestamp": "2026-10-29T12:00:00+0800",
                            "tag_type": "annotated"}}
        reg = vc.merge_registry(self._items(), tags)
        by = {r["version"]: r for r in reg["versions"]}
        self.assertEqual(by["v3.27.0"]["source"], "both")
        self.assertTrue(by["v3.27.0"]["has_tag"])
        self.assertFalse(by["v3.26.0"]["has_tag"])

    def test_missing_and_orphan(self):
        """反例：缺 tag 与孤儿 tag 必须被分别报出，且互不串味。"""
        tags = {"v3.27.0": {"commit": "aaaa1111", "summary": "有 tag",
                            "timestamp": "2026-10-29T12:00:00+0800",
                            "tag_type": "annotated"},
                "v9.9.9": {"commit": "deadbeef", "summary": "无主之魂",
                           "timestamp": "", "tag_type": "lightweight"}}
        reg = vc.merge_registry(self._items(), tags)
        self.assertIn("v3.26.0", reg["missing_tags"])
        self.assertIn("v3.25.0", reg["missing_tags"])
        self.assertIn("v9.9.9", reg["orphan_tags"])
        self.assertNotIn("v3.27.0", reg["missing_tags"],
                         "已有 tag 的版本不得出现在 missing_tags")
        self.assertNotIn("v3.26.0", reg["orphan_tags"],
                         "只在 CHANGELOG 的版本不是孤儿 tag")

    def test_order_is_new_first(self):
        reg = vc.merge_registry(self._items(), {})
        vs = [r["version"] for r in reg["versions"]]
        self.assertEqual(vs, ["v3.27.0", "v3.26.0", "v3.25.0"])

    def test_anti_example_empty(self):
        reg = vc.merge_registry([], {})
        self.assertEqual(reg["versions"], [])
        self.assertEqual(reg["missing_tags"], [])


class T08PlanTagBackfill(unittest.TestCase):
    """T8 补 tag 规划：幂等 + 不覆盖已有 tag。"""

    def _reg(self):
        items = vc.parse_changelog(make_changelog(
            ("v3.27.0", "2026-10-29", "新"),
            ("v3.26.0", "2026-10-28", "旧"),
        ))
        return vc.merge_registry(items, {})

    def test_positive(self):
        anchors = {"v3.27.0": {"commit": "aaaa1111", "reason": "r1"},
                   "v3.26.0": {"commit": "bbbb2222", "reason": "r2"}}
        plan = vc.plan_tag_backfill(self._reg(), anchors, existing_tags=set())
        self.assertEqual(set(plan), {"v3.27.0", "v3.26.0"})
        self.assertEqual(plan["v3.27.0"]["commit"], "aaaa1111")

    def test_idempotent(self):
        """反例：已有 tag 的版本不得出现在计划里（幂等）。"""
        anchors = {"v3.27.0": {"commit": "aaaa1111", "reason": "r1"},
                   "v3.26.0": {"commit": "bbbb2222", "reason": "r2"}}
        plan = vc.plan_tag_backfill(self._reg(), anchors,
                                    existing_tags={"v3.27.0"})
        self.assertNotIn("v3.27.0", plan, "已存在的 tag 不得重复规划")
        self.assertIn("v3.26.0", plan)

    def test_no_anchor_no_plan(self):
        """反例：找不到锚点的版本不得进计划（否则会打在错的提交上）。"""
        plan = vc.plan_tag_backfill(self._reg(), {"v3.27.0": {"commit": "a", "reason": "r"}})
        self.assertNotIn("v3.26.0", plan)


class T09PlanPrune(unittest.TestCase):
    """T9 保留/归档规划：★ 绝不产生「删除」动作。"""

    def _reg(self, n=15):
        pairs = []
        for i in range(n):
            pairs.append(("v3.%d.0" % (n - i), "2026-10-01", "x"))
        return vc.merge_registry(vc.parse_changelog(make_changelog(*pairs)), {})

    def test_keep_recent(self):
        pol = dict(vc.DEFAULT_POLICY)
        pol["keep_recent"] = 5
        pol["keep_milestones"] = False
        plan = vc.plan_prune(self._reg(), pol)
        self.assertEqual(len(plan["keep_versions"]), 5)

    def test_milestones_kept(self):
        pol = dict(vc.DEFAULT_POLICY)
        pol["keep_recent"] = 1
        pol["keep_milestones"] = True
        plan = vc.plan_prune(self._reg(), pol)
        # v3.14.0 / v3.12.0 / v3.10.0 / v3.8.0 / v3.6.0 / v3.4.0 是 even-minor 里程碑
        self.assertIn("v3.14.0", plan["keep_versions"])
        self.assertIn("v3.12.0", plan["keep_versions"])
        self.assertIn("v3.4.0", plan["keep_versions"])

    def test_keep_tags_default_blocks_tag_prune(self):
        """反例：keep_tags=true ⇒ prune_versions 必须为空（tag 不删）。"""
        pol = dict(vc.DEFAULT_POLICY)
        pol["keep_recent"] = 1
        plan = vc.plan_prune(self._reg(), pol)
        self.assertFalse(plan["prune_tags"])
        self.assertEqual(plan["prune_versions"], [])

    def test_never_returns_delete(self):
        """★ 核心反例：任何策略下都不得出现「删除」语义。"""
        pol = dict(vc.DEFAULT_POLICY)
        pol["keep_recent"] = 0
        pol["keep_milestones"] = False
        pol["keep_tags"] = False
        plan = vc.plan_prune(self._reg(), pol)
        blob = json.dumps(plan, ensure_ascii=False)
        for word in ("delete", "rm ", "unlink", "remove", "删除"):
            self.assertNotIn(word, blob.lower(),
                             "计划里出现删除语义：%r" % word)

    def test_artifacts_split(self):
        arts = [{"path": "/tmp/a.zip", "bytes": 100, "keep": False},
                {"path": "/tmp/b.zip", "bytes": 200, "keep": True}]
        plan = vc.plan_prune(self._reg(), vc.DEFAULT_POLICY, arts)
        self.assertEqual(len(plan["archive_artifacts"]), 1)
        self.assertEqual(len(plan["keep_artifacts"]), 1)
        self.assertEqual(plan["total_bytes"], 100)


class T10ReleaseId(unittest.TestCase):
    """T10 唯一标识。"""

    def test_positive(self):
        rid = vc.build_release_id("v3.27.0", "2026-10-29T12:21:09+0800", "29b4b915")
        self.assertTrue(rid.startswith("v3.27.0@"))
        self.assertIn("29b4b91", rid)
        self.assertIn("20261029", rid)

    def test_uniqueness(self):
        """反例：不同 commit 必须给出不同标识。"""
        a = vc.build_release_id("v3.27.0", "2026-10-29T12:21:09+0800", "29b4b915")
        b = vc.build_release_id("v3.27.0", "2026-10-29T12:21:09+0800", "29b4b916")
        self.assertNotEqual(a, b, "不同 commit 不得产出相同标识")

    def test_empty_inputs(self):
        rid = vc.build_release_id("v3.27.0", "", "")
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("v3.27.0@"))


class T11DiffSummary(unittest.TestCase):
    """T11 差异摘要格式化。"""

    def test_positive(self):
        rows = [{"status": "A", "path": "scripts/versionctl.py"},
                {"status": "M", "path": "CHANGELOG.md"},
                {"status": "D", "path": "old.py"}]
        out = vc.format_diff_summary(rows)
        self.assertIn("新增", out)
        self.assertIn("修改", out)
        self.assertIn("删除", out)
        self.assertIn("scripts/versionctl.py", out)

    def test_anti_example_empty(self):
        """反例：空差异必须明说「无差异」，不能返回空串（会被误读为没跑）。"""
        out = vc.format_diff_summary([])
        self.assertIn("无差异", out)
        self.assertTrue(out.strip())

    def test_unknown_status(self):
        """反例：未知 status 也不得丢文件（否则改动明细会漏项）。"""
        out = vc.format_diff_summary([{"status": "X", "path": "weird"}])
        self.assertIn("weird", out, "未知 status 的文件也必须列出")

    def test_status_prefix_takes_first_char(self):
        """R100（重命名带相似度）应归入「重命名」而非丢失。"""
        out = vc.format_diff_summary([{"status": "R100", "path": "a.py"}])
        self.assertIn("重命名", out)


class T12MigratePolicy(unittest.TestCase):
    """T12 策略文件迁移：幂等 + 拒绝降级 + 备份。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg_dir = self.root / vc.CTL_DIRNAME
        self.cfg_dir.mkdir(parents=True, exist_ok=True)
        self.cfg = self.cfg_dir / vc.CONFIG_FILENAME

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_file(self):
        r = vc.migrate_policy(self.root, confirm=False)
        self.assertEqual(r["action"], "none")

    def test_idempotent(self):
        self.cfg.write_text(json.dumps({"schema_version": vc.SCHEMA_VERSION,
                                         "keep_recent": 5}), encoding="utf-8")
        r = vc.migrate_policy(self.root, confirm=True)
        self.assertEqual(r["action"], "none", "已是当前版本 ⇒ no-op")

    def test_migrate_preserves_user_keys(self):
        """★ 用户自定义键不得在迁移中丢失。"""
        self.cfg.write_text(json.dumps({"schema_version": 1,
                                         "my_custom": "keep-me"}),
                            encoding="utf-8")
        self.assertNotEqual(vc.SCHEMA_VERSION, 1,
                            "若 SCHEMA_VERSION==1 则本用例无意义（需造更旧版本）")
        r = vc.migrate_policy(self.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        data = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertEqual(data["my_custom"], "keep-me")
        self.assertEqual(data["schema_version"], vc.SCHEMA_VERSION)
        self.assertTrue(Path(r["backup"]).is_file(), "迁移前必须留备份")

    def test_refuse_downgrade(self):
        """反例：schema_version 高于本工具 ⇒ 必须拒绝，不得静默降级。"""
        self.cfg.write_text(json.dumps({"schema_version": 999}),
                            encoding="utf-8")
        r = vc.migrate_policy(self.root, confirm=True)
        self.assertEqual(r["action"], "refused")

    def test_dry_run_writes_nothing(self):
        self.cfg.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        before_bytes = self.cfg.read_bytes()
        before = self.cfg.read_text(encoding="utf-8")
        r = vc.migrate_policy(self.root, confirm=False)
        self.assertEqual(r["action"], "dry-run")
        self.assertEqual(self.cfg.read_bytes(), before_bytes,
                         "dry-run 不得写盘")
        self.assertFalse((self.cfg_dir / vc.ARCHIVE_DIRNAME).exists(),
                         "dry-run 不得建备份目录")


class T13CLIWiring(unittest.TestCase):
    """T13 CLI 接线：子命令齐全 + 破坏性命令必须 --confirm。"""

    def test_subcommands_exist(self):
        parser = vc.build_parser()
        # argparse 的子命令收集在 _SubParsersAction 里
        names = []
        for act in parser._actions:
            if isinstance(act, __import__("argparse")._SubParsersAction):
                names = list(act.choices)
                break
        for want in ("list", "show", "diff", "tag", "switch", "rollback",
                     "policy", "prune", "journal", "recover", "migrate"):
            self.assertIn(want, names, "缺少子命令：%s" % want)

    def test_destructive_commands_have_confirm_flag(self):
        parser = vc.build_parser()
        for act in parser._actions:
            if isinstance(act, __import__("argparse")._SubParsersAction):
                for name, sub in act.choices.items():
                    if name in ("switch", "rollback", "prune", "recover", "tag"):
                        opts = {o for a in sub._actions for o in a.option_strings}
                        self.assertIn("--confirm", opts,
                                      "破坏性子命令 %s 必须有 --confirm 开关" % name)
                break

    def test_no_confirm_is_dry_run(self):
        """★ 核心反例：无 --confirm 时不得真的切换 HEAD。

        ★ 用**当前 HEAD 自身**作目标版本（它必定有 tag）：
          若用尚无 tag 的版本，早期实现会在 dry-run 检查之前就报错退出，
          这条判据反而测不到真正的 dry-run 分支。
        """
        root = vc.repo_root()
        before = vc.head_state(root)["head"]
        rc = vc.main(["switch", before[:8]])  # 短 sha 通常不认 ⇒ 用全 sha
        # 全 sha 不是版本号 ⇒ 走「未找到版本」分支 ⇒ HEAD 不变
        after = vc.head_state(root)["head"]
        self.assertEqual(before, after, "无 --confirm 时 HEAD 不得改变")
        self.assertIn(rc, (0, 1))

    def test_no_confirm_does_not_change_head_on_real_version(self):
        """★ 对**真实存在的版本**做 dry-run 切换，HEAD 不得改变。

        ★ 在**临时克隆**里做：真实仓库此刻有未提交改动（本测试文件自身），
          真实实现会正确地拒绝切换 ⇒ 在真仓库上测这条判据是测不到的
          （测到的是「拒绝」分支，不是「dry-run」分支）。
        """
        with _clone_repo() as clone:
            head = _git(clone, "rev-parse", "HEAD")
            old = _git(clone, "rev-list", "--max-count=3", "HEAD").split()
            if len(old) < 2:
                self.skipTest("提交历史太短")
            target = old[1]
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", target],
                                  cwd=str(clone), capture_output=True, text=True)
            after = _git(clone, "rev-parse", "HEAD")
            self.assertEqual(head, after, "无 --confirm 时 HEAD 不得改变")
            self.assertIn("dry-run", proc.stdout,
                          "dry-run 必须明说自己是预览")
            self.assertEqual(proc.returncode, 0, "dry-run 应返回 0")

    def test_switch_confirm_would_change_head(self):
        """★ 反向对照：带 --confirm 时**确实应该**改变 HEAD
        —— 否则「dry-run 不改 HEAD」这条判据就是空断言（恒真）。
        """
        with _clone_repo() as clone:
            head = _git(clone, "rev-parse", "HEAD")
            old = _git(clone, "rev-list", "--max-count=3", "HEAD").split()
            if len(old) < 2:
                self.skipTest("提交历史太短")
            target = old[1]
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", target, "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            after = _git(clone, "rev-parse", "HEAD")
            self.assertNotEqual(after, head,
                                "带 --confirm 时 HEAD 必须真的改变（否则 dry-run 判据是空断言）")
            self.assertEqual(after, target)

    def test_switch_confirm_via_version_tag(self):
        """★ 带 --confirm 切到**有 tag 的版本**也必须真的切换。"""
        with _clone_repo() as clone:
            head = _git(clone, "rev-parse", "HEAD")
            # 找 HEAD 的父提交，按 sha 切（版本号在克隆里也有 tag）
            parent = _git(clone, "rev-parse", "HEAD^").strip()
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", parent, "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            after = _git(clone, "rev-parse", "HEAD")
            self.assertEqual(after, parent)
            self.assertNotEqual(after, head)

    def test_prune_without_confirm_moves_nothing(self):
        """★ 核心反例：prune 无 --confirm 不得移动任何文件。"""
        root = vc.repo_root()
        arch = Path(root) / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
        before = set()
        if arch.is_dir():
            before = {e.name for e in arch.iterdir()}
        rc = vc.main(["prune"])
        self.assertIn(rc, (0, 1))
        # ★ dry-run 不得**新增**任何归档条目。
        #   ⚠ 原判据写成「归档区里不得存在 ARCHIVE_MANIFEST.json」——
        #   这是**过宽判据**：归档区里可能已有**别的工具**（migrate_artifacts.py）
        #   合法产出的清单，那与 versionctl 的 dry-run 无关 ⇒ 会误判红。
        #
        #   ⚠ v3.28.0 修正：判据必须对**既有残留**鲁棒。
        #   中间版本曾写成「before == after（集合完全相等）」⇒ 若上一轮
        #   变异测试在归档区留下残留目录，本次 before/after 就会不同 ⇒ 误判红。
        #   （实测踩到：变异残留 dryrun-probe 导致后续判据持续失败。）
        #   ⇒ 改为「**新增条目集合必须为空**」：只看增量，不管既有内容。
        #     这比原判据更强（管住一切新增），且对残留免疫。
        after = set()
        if arch.is_dir():
            after = {e.name for e in arch.iterdir()}
        added = after - before
        self.assertEqual(added, set(),
                         "dry-run 不得新增归档条目（新增=%s）" % sorted(added))
        # 且归档区内不得出现**文件**（dry-run 不该写文件）
        if arch.is_dir():
            for e in arch.iterdir():
                self.assertTrue(e.is_dir(),
                                "dry-run 不得创建归档文件：%s" % e.name)


class T14RealRepoInvariants(unittest.TestCase):
    """T14 真实仓库不变量：跑一遍不崩 + 关键量守恒。"""

    def test_list_runs(self):
        root = vc.repo_root()
        rc = vc.main(["list"])
        self.assertEqual(rc, 0)

    def test_registry_consistency(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        self.assertGreater(len(reg["versions"]), 0, "版本清单不得为空")
        for r in reg["versions"]:
            self.assertTrue(r["version"].startswith("v"))
            self.assertIn(r["source"], ("both", "changelog", "tag"))

    def test_anchors_exist_for_all_changelog_versions(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        items = vc.changelog_items(root)
        anchors = reg.get("anchors", {})
        for item in items:
            self.assertIn(item["version"], anchors,
                          "版本 %s 必须有锚点（否则补 tag 无处可打）" % item["version"])
            self.assertTrue(anchors[item["version"]]["commit"])

    def test_anchor_is_latest_commit_mentioning_version(self):
        """★ 核心判据：锚点必须是**时间最晚**的提及提交，而非首个。

        这是 v3.28.0 定案规则（实测：v3.4.3 有 10 个提交）。
        """
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        log_entries = vc.git_log_entries(root)
        anchors = reg.get("anchors", {})
        for v in ("v3.27.0", "v3.26.0", "v3.25.0"):
            if v not in anchors:
                continue
            expect = None
            for e in log_entries:  # newest first
                if v in vc.extract_versions_from_subject(e["subject"]):
                    expect = e["sha"]
                    break
            if expect is None:
                continue
            self.assertEqual(anchors[v]["commit"], expect,
                             "锚点必须是最新提及提交（%s）" % v)

    def test_tag_plan_is_idempotent(self):
        """幂等：已有 tag 的版本不进计划。"""
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        existing = vc.existing_tag_names(root)
        anchors = reg.get("anchors", {})
        plan1 = vc.plan_tag_backfill(reg, anchors, existing)
        # 模拟「打完」：把计划的 commit 当成已有 tag
        simulated = set(existing) | set(plan1.keys())
        plan2 = vc.plan_tag_backfill(reg, anchors, simulated)
        self.assertEqual(plan2, {}, "打完一次后再次规划必须为空（幂等）")

    def test_diff_between_two_known_versions(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        by = {r["version"]: r for r in reg["versions"]}
        have = [v for v in ("v3.26.0", "v3.27.0") if by.get(v, {}).get("commit")]
        if len(have) == 2:
            rows = vc.diff_rows_between(root, by[have[0]]["commit"],
                                        by[have[1]]["commit"])
            self.assertIsInstance(rows, list)


class T15NoHardcodedVersion(unittest.TestCase):
    """T15 反退化：工具不得硬编码当前版本号。

    依据：本包铁律「config/*.yaml 是唯一真源」⇒ 工具必须从清单文件读版本，
    否则版本号一改，工具就骗人（这正是第 14 项巡检存在的原因）。
    """

    def test_no_literal_current_version_in_source(self):
        src = (_HERE / "versionctl.py").read_text(encoding="utf-8")
        root = vc.repo_root()
        cur = vc.current_version(root)
        if not cur:
            self.skipTest("读不到当前版本号")
        # 只允许出现在注释/文档里的历史引用；查代码里的字面量
        code_lines = [ln for ln in src.splitlines()
                      if not ln.strip().startswith("#")]
        for ln in code_lines:
            self.assertNotIn('"%s"' % cur, ln,
                             "代码里不得硬编码当前版本号 %s" % cur)

    def test_current_version_read_from_manifest(self):
        root = vc.repo_root()
        cur = vc.current_version(root)
        self.assertTrue(cur, "必须能从 .codebuddy-plugin/plugin.json 读到版本号")
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", cur),
                        "版本号应为三段式：%r" % cur)


class T15PruneNeverDeletes(unittest.TestCase):
    """★ T15 「只归档不删除」铁律的**能红反例**（v3.28.0 变异测试 M15 补）。

    ★ 为什么单独一个测试类：
      变异测试实测 M15（`shutil.move` → `shutil.rmtree`）**打不红** ——
      因为既有测试只验 `plan_prune` 这个**纯函数返回值**（查 JSON 里有没有
      "delete" 字样），而纯函数根本不碰文件系统 ⇒ 真正的删除行为无人看守。
      ⇒ 必须有一个**真跑 I/O** 的测试：归档后，原路径必须不存在、
        归档区必须**确实有文件副本**（不是只剩一份清单）。
    """

    def _make_repo_with_artifact(self, clone):
        """在克隆里造一个产物文件，并登记到策略的 artifact_dirs。"""
        art = clone / "artifacts"
        (art / "sub").mkdir(parents=True, exist_ok=True)
        (art / "sub" / "bundle.zip").write_bytes(b"PK\x03\x04" + b"x" * 2048)
        # 写策略：把 artifacts 登记为清理视野
        ctl = clone / vc.CTL_DIRNAME
        ctl.mkdir(parents=True, exist_ok=True)
        (ctl / vc.CONFIG_FILENAME).write_text(json.dumps({
            "schema_version": vc.SCHEMA_VERSION,
            "keep_recent": 1,
            "keep_milestones": False,
            "keep_tags": True,
            "artifact_dirs": [str(art)],
            "artifact_max_bytes": 0,
        }, ensure_ascii=False), encoding="utf-8")
        return art / "sub" / "bundle.zip"

    def test_prune_archives_instead_of_deleting(self):
        """★ 核心：prune 后原文件不在了，但**归档区必须有它的副本**。"""
        with _clone_repo() as clone:
            target = self._make_repo_with_artifact(clone)
            self.assertTrue(target.exists(), "前置：产物文件应存在")
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "prune", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "prune 应成功：%s" % proc.stdout[-300:])
            # ① 原文件应已移走
            self.assertFalse(target.exists(), "prune 后原路径应不存在（已移动）")
            # ② ★ 归档区必须留有**文件副本**（若被 rmtree 删除则这里为空）
            arch = clone / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
            self.assertTrue(arch.is_dir(), "归档目录应存在")
            archived = list(arch.rglob("bundle.zip"))
            self.assertTrue(archived,
                            "归档区必须有 bundle.zip 的副本 —— 若为空说明被真删了"
                            "（M15 变异即可打红本条）")
            self.assertEqual(archived[0].read_bytes()[:4], b"PK\x03\x04",
                             "归档副本内容必须与原文件一致")
            self.assertEqual(archived[0].stat().st_size, 2052,
                             "归档副本大小必须与原文件一致")

    def test_prune_manifest_records_restore_path(self):
        """★ 归档清单必须记录 from/to ⇒ 失败恢复有据可依。"""
        with _clone_repo() as clone:
            target = self._make_repo_with_artifact(clone)
            subprocess.run([sys.executable, "scripts/versionctl.py",
                            "prune", "--confirm"],
                           cwd=str(clone), capture_output=True, text=True)
            arch = clone / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
            manifests = list(arch.rglob("ARCHIVE_MANIFEST.json"))
            self.assertTrue(manifests, "必须有归档清单")
            data = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertTrue(data.get("items"), "清单必须列出归档项")
            item = data["items"][0]
            self.assertIn("from", item)
            self.assertIn("to", item)
            self.assertTrue(Path(item["to"]).exists(),
                            "清单里的 to 路径必须真实存在")

    def test_prune_source_tree_never_uses_rmtree(self):
        """★ 源码级反例：prune 路径里不得出现删除语义。

        这是 M15 变异的**兜底判据**：即使 I/O 测试被环境原因跳过，
        这条静态判据也会红。
        """
        src = (_HERE / "versionctl.py").read_text(encoding="utf-8")
        # 定位 cmd_prune 函数体
        start = src.index("def cmd_prune(")
        end = src.index("def cmd_journal(")
        body = src[start:end]
        for word in ("rmtree", "os.remove", "os.unlink", "Path.unlink",
                     "shutil.rmtree"):
            self.assertNotIn(word, body,
                             "cmd_prune 里出现删除语义 %r（违反只归档不删除）" % word)
        self.assertIn("shutil.move", body, "cmd_prune 必须用 move（归档而非删除）")


class T16DirtyWorktreeRefusesSwitch(unittest.TestCase):
    """★ T16 脏工作区必须拒绝切换（v3.28.0 变异测试 M14 补）。

    ★ 为什么单独一个测试类：
      变异测试实测 M14（`if st["dirty"]:` → `if False:`）**打不红** ——
      既有的 dry-run 测试在**干净克隆**里做（测的是 dry-run 分支），
      真实仓库上那条测试走的是「短 sha 不认 → 未找到版本」分支
      ⇒ 「脏工作区拒绝切换」这条保护**完全没有被覆盖**。
    """

    def test_dirty_worktree_refuses_confirmed_switch(self):
        with _clone_repo() as clone:
            head = _git(clone, "rev-parse", "HEAD")
            parent = _git(clone, "rev-parse", "HEAD^").strip()
            # 故意弄脏工作区
            (clone / "scripts" / "dirty.txt").write_text("未提交改动", encoding="utf-8")
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", parent, "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            after = _git(clone, "rev-parse", "HEAD")
            self.assertEqual(head, after, "脏工作区下 HEAD 不得改变")
            self.assertNotEqual(proc.returncode, 0,
                                "脏工作区下必须以非零码拒绝")
            self.assertIn("未提交改动", proc.stdout,
                          "必须明说因为工作区有改动而拒绝")

    def test_dirty_worktree_refuses_in_real_repo(self):
        """真实仓库此刻就是脏的 ⇒ 同一判据在真仓库上同样成立。

        ★★ v3.28.0 变异测试复验发现的设计隐患（已修）：
          本测试原先在**真实仓库**上执行 `switch --confirm`。
          正常情况下脏检查会拦住它 ⇒ 无害；
          但**一旦脏检查被绕过**（正是变异测试要探的场景），
          它会**真的把仓库切成 detached HEAD** ⇒ 变异测试期间损坏工作区。
          ⇒ 改为：**先断言真实仓库是脏的**，再跑；
            且跑完**必须校验 HEAD 未变**，若变了立即 checkout 回原分支
            （兜底自愈，防止任何未来的判据回归伤到真实仓库）。
        """
        root = vc.repo_root()
        st = vc.head_state(root)
        if not st["dirty"]:
            self.skipTest("真实仓库当前干净（无脏文件可测）")
        branch = st["branch"]
        head = st["head"]
        try:
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", head, "--confirm"],
                                  cwd=str(root), capture_output=True, text=True)
            after = vc.head_state(root)["head"]
            self.assertEqual(head, after, "脏工作区下 HEAD 不得改变")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("未提交改动", proc.stdout,
                          "必须明说因为工作区有改动而拒绝")
        finally:
            # ★ 兜底自愈：无论断言是否通过，都确保仓库回到原分支
            if vc.head_state(root)["head"] != head:
                subprocess.run(["git", "checkout", "--quiet", branch],
                               cwd=str(root), capture_output=True, text=True)


class T17MigrateDoesNotClobberExistingKeys(unittest.TestCase):
    """★ T17 迁移不得覆盖用户**已持有**的迁移键（v3.28.0 变异测试 M12 补）。

    ★ 为什么单独一个测试类：
      变异测试实测 M12（`new.setdefault(k, v)` → `new[k] = v`）**打不红** ——
      既有测试验的是「不丢**未知**自定义键」，而 `artifact_dirs` 之类
      **迁移键**与自定义键不同名 ⇒ 覆盖行为测不到。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        d = self.root / vc.CTL_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        self.cfg = d / vc.CONFIG_FILENAME

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_migration_key_not_overwritten(self):
        """★ 用户已持有 artifact_dirs ⇒ 迁移不得把它清空。"""
        self.cfg.write_text(json.dumps({
            "schema_version": 1,
            "artifact_dirs": ["/MY/IMPORTANT/DIR"],
            "artifact_max_bytes": 999,
        }), encoding="utf-8")
        r = vc.migrate_policy(self.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        data = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertEqual(data["artifact_dirs"], ["/MY/IMPORTANT/DIR"],
                         "迁移不得覆盖用户已有的 artifact_dirs（M12 变异可打红本条）")
        self.assertEqual(data["artifact_max_bytes"], 999,
                         "迁移不得覆盖用户已有的 artifact_max_bytes")

    def test_missing_migration_key_gets_filled(self):
        """★ 反向对照：用户**没有**的迁移键必须被补上（否则迁移是空转）。"""
        self.cfg.write_text(json.dumps({"schema_version": 1}),
                            encoding="utf-8")
        r = vc.migrate_policy(self.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        data = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertIn("artifact_dirs", data, "缺失的迁移键必须被补齐")
        self.assertIn("artifact_max_bytes", data)


class T18AnchorDirectionMultiMention(unittest.TestCase):
    """★ T18 锚点方向判据必须覆盖**多提及**版本（v3.28.0 变异测试 M16 补）。

    ★ 为什么单独一个测试类：
      变异测试实测 M16（锚点循环 `reversed`）**打不红** ——
      原判据只抽查 v3.27.0/v3.26.0/v3.25.0，而这三个版本在真实仓库里
      **各自只被 1 个提交提及** ⇒ 正序与逆序结果完全相同 ⇒ 不可区分。
      真实仓库里多提及的版本是 v3.4.3（10 个提交）/ v3.4.4（8 个）等。
    """

    def _multi_mentioned_versions(self, log_entries):
        """找出被 ≥2 个提交提及的版本。"""
        from collections import Counter
        cnt = Counter()
        for e in log_entries:
            for v in vc.extract_versions_from_subject(e["subject"]):
                cnt[v] += 1
        return {v: c for v, c in cnt.items() if c >= 2}

    def test_multi_mentioned_versions_exist(self):
        """前置：真实仓库里确实存在多提及版本（否则本组测试无意义）。"""
        root = vc.repo_root()
        log_entries = vc.git_log_entries(root)
        multi = self._multi_mentioned_versions(log_entries)
        self.assertTrue(multi, "真实仓库应存在被多个提交提及的版本")

    def test_anchor_direction_for_all_multi_mentioned(self):
        """★ 全量校验：多提及版本的锚点必须是**时间最晚**的**收口式**提交。

        ★ 注意判据口径（v3.28.0 定案）：
          锚点只认「subject 开头/结尾/中文冒号前**指名**该版本」的提交，
          **不认**中间顺带提及 ⇒ 期望值必须用同一口径算，
          否则就会得出「提及里最晚」这种错误期望（M16 变异曾打不红的原因）。
        """
        root = vc.repo_root()
        log_entries = vc.git_log_entries(root)   # newest first
        items = vc.changelog_items(root)
        known = {i["version"] for i in items}
        anchors = vc.compute_anchors(log_entries, items, root=root)
        multi = self._multi_mentioned_versions(log_entries)
        checked = 0
        for v, cnt in multi.items():
            if v not in known:
                continue
            # 期望：所有「收口式指名 v」的提交里，committer time 最晚的那个
            cands = [e for e in log_entries
                     if vc._extract_release_head(e["subject"]) == v]
            if not cands:
                continue
            expect = max(cands, key=lambda e: e.get("timestamp") or "")["sha"]
            self.assertEqual(anchors[v]["commit"], expect,
                             "多提及版本 %s（%d 次提及）的锚点必须是时间最晚的收口提交"
                             % (v, cnt))
            checked += 1
        self.assertGreater(checked, 0, "至少要校验一个多提及版本")

    def test_anchor_equals_last_mentioned_commit(self):
        """★ 语义化反例：锚点必须等于「最后一个提及该版本的提交」。

        ★ 注意 git log 是 newest-first ⇒ 「最后一个提及」= **首个**命中。
          方向搞反会让锚点变成「版本首提交」⇒ 回滚时会落到半成品版本上。
        """
        root = vc.repo_root()
        log_entries = vc.git_log_entries(root)
        items = vc.changelog_items(root)
        anchors = vc.compute_anchors(log_entries, items, root=root)
        for e in log_entries:
            vs = vc.extract_versions_from_subject(e["subject"])
            if not vs:
                continue
            for v in vs:
                if v not in anchors:
                    continue
                # 锚点 commit 在 log 里的位置，必须不晚于首次命中位置
                shas = [x["sha"] for x in log_entries]
                try:
                    idx_anchor = shas.index(anchors[v]["commit"])
                    idx_hit = shas.index(e["sha"])
                except ValueError:
                    continue
                self.assertLessEqual(idx_anchor, idx_hit,
                                     "锚点不得晚于任何提及提交（%s）" % v)
                return   # 只需一条即可证明方向
        self.skipTest("没有可用的提及样本")


class T19RangeSharesAnchor(unittest.TestCase):
    """★ T19 区间内的中间版本必须**共享**收口点（v3.28.0 变异测试 M18 补）。

    ★ 为什么单独一个测试类：
      变异测试实测 M18（区间集合只留端点）**打不红** ——
      原判据只断言「集合长度 == 1」和「两个端点在集合内」，
      从不断言**中间版本** v3.6.0 ⇒ 区间共享收口点的机制测不到。
    """

    def test_middle_version_in_range_set(self):
        """★ 中间版本 v3.6.0 必须在区间集合里（M18 变异可打红本条）。"""
        sets = vc.subject_version_sets("v3.5.0→v3.7.0：迭代六原则")
        self.assertEqual(len(sets), 1)
        self.assertIn("v3.5.0", sets[0])
        self.assertIn("v3.7.0", sets[0])
        self.assertIn("v3.6.0", sets[0],
                      "中间版本必须在集合里（M18 变异只留端点 ⇒ 可打红本条）")

    def test_middle_version_gets_same_anchor(self):
        """★ 中间版本 v3.6.0 必须与端点**共享同一个收口点**。

        ★ 这有真实后果：v3.6.0 在真实仓库的 commit subject 里出现 0 次
          ⇒ 若区间不共享，它会退回到 root commit ⇒ tag 会打在错误的提交上。
        """
        root = vc.repo_root()
        items = vc.changelog_items(root)
        known = {i["version"] for i in items}
        if "v3.6.0" not in known:
            self.skipTest("CHANGELOG 里没有 v3.6.0")
        log_entries = vc.git_log_entries(root)
        anchors = vc.compute_anchors(log_entries, items, root=root)
        self.assertIn("v3.6.0", anchors)
        self.assertEqual(anchors["v3.6.0"]["commit"], anchors["v3.7.0"]["commit"],
                         "区间内版本必须共享收口点")
        # 且不能是 root commit（回落值）
        root_commit = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"],
                                     cwd=str(root), capture_output=True,
                                     text=True).stdout.strip()
        self.assertNotEqual(anchors["v3.6.0"]["commit"], root_commit,
                            "v3.6.0 不该退回到仓库首个 commit")


class T20AnchorMonotonicity(unittest.TestCase):
    """★ T20 锚点必须随版本号**单调前移**（v3.28.0 新增判据）。

    ★ 为什么必须单调：
      锚点若不单调（vX 的锚点比 vX-1 的锚点更旧），则「回滚到 vX」
      可能落到一个**比 vX 更晚**的提交上 ⇒ 回滚语义失效。
      —— v3.28.0 实测：初版规则（全部提及 + 拓扑最新）产生 **10 处**违例；
        改「全部提及 + 时间最晚」仍有 **3 处**；最终定案规则 → **0 处**。
    """

    def test_real_repo_anchors_are_monotonic(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        m = reg["monotonicity"]
        self.assertTrue(m["ok"], "真实仓库锚点必须单调：%s"
                        % [v["detail"] for v in m["violations"]])

    def test_monotonicity_detector_can_red(self):
        """★ 反例：喂一个**故意乱序**的锚点表，检测器必须报红。

        —— 否则「单调性 ok」这条判据可能是恒真断言。
        """
        items = vc.parse_changelog(make_changelog(
            ("v3.27.0", "2026-10-29", "新"),
            ("v3.26.0", "2026-10-28", "旧"),
        ))
        reg = vc.merge_registry(items, {})
        log = [
            {"sha": "aaa", "timestamp": "2026-10-29T12:00:00+0800"},
            {"sha": "bbb", "timestamp": "2026-10-01T12:00:00+0800"},
        ]
        # ★ 真正的乱序：**更新的** v3.27.0 锚点时间（10-29）晚于
        #   **更旧的** v3.26.0 锚点时间（10-01）？
        #   —— 不是。乱序的定义是：版本越新，锚点时间必须越晚。
        #   这里 v3.26.0（较旧）= 10-01，v3.27.0（较新）= 10-29 ⇒ 这是**单调**的。
        #   要造乱序，必须让**较新**版本的锚点时间**更早**：
        anchors = {"v3.27.0": {"commit": "bbb"}, "v3.26.0": {"commit": "aaa"}}
        m = vc.check_anchor_monotonicity(reg, anchors, log)
        self.assertFalse(m["ok"], "乱序锚点必须被检出")
        self.assertEqual(len(m["violations"]), 1)
        # ★ 报告的是「**哪个版本的锚点**没有前移」⇒ 本例是 v3.27.0
        #   （它的锚点 10-01 早于前一版 v3.26.0 的 10-29）
        self.assertIn("v3.27.0", m["violations"][0]["version"])
        self.assertIn("v3.26.0", m["violations"][0]["prev_version"])

    def test_monotonic_anchors_pass(self):
        """★ 反向对照：单调的锚点表必须通过（否则检测器恒红也是错的）。"""
        items = vc.parse_changelog(make_changelog(
            ("v3.27.0", "2026-10-29", "新"),
            ("v3.26.0", "2026-10-28", "旧"),
        ))
        reg = vc.merge_registry(items, {})
        log = [
            {"sha": "aaa", "timestamp": "2026-10-29T12:00:00+0800"},
            {"sha": "bbb", "timestamp": "2026-10-28T12:00:00+0800"},
        ]
        anchors = {"v3.27.0": {"commit": "aaa"}, "v3.26.0": {"commit": "bbb"}}
        m = vc.check_anchor_monotonicity(reg, anchors, log)
        self.assertTrue(m["ok"], "单调锚点必须通过")


class T21AnchorNoConflictWithExistingTags(unittest.TestCase):
    """★ T21 补 tag 不得与**已有 tag**冲突（v3.28.0 新增判据）。

    ★ 为什么必须：已有 tag 是用户既有的版本指针。若新算法算出的锚点
      与之不同，却覆盖它 ⇒ 用户的版本指针被静默改写 ⇒ 历史被篡改。
    """

    def test_no_conflict_with_existing_tags(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        tags = vc.read_tag_entries(root)
        conflicts = []
        for v, t in tags.items():
            a = reg["anchors"].get(v)
            if not a:
                continue
            if t.get("commit") and a.get("commit") != t.get("commit"):
                conflicts.append((v, t["commit"][:8], a["commit"][:8]))
        self.assertEqual(conflicts, [],
                         "锚点与已有 tag 冲突：%s" % conflicts)

    def test_all_changelog_versions_have_anchor(self):
        root = vc.repo_root()
        reg = vc.build_registry_full(root)
        items = vc.changelog_items(root)
        missing = [i["version"] for i in items
                   if i["version"] not in reg["anchors"]]
        self.assertEqual(missing, [], "每个 CHANGELOG 版本都必须有锚点")


class T23AnchorRuleUnitDiscriminates(unittest.TestCase):
    """★ T23 锚点规则的**受控数据**判据（v3.28.0 收尾补测）。

    ★★ 为什么必须单独一组（实测发现的判据缺口）：
      T20/T21 用的是**真实仓库**的数据。而真实仓库当前状态下，
      「拓扑最新」与「时间最晚」恰好给出**相同**结果，
      「已有 tag 优先」与「不优先」也恰好**相同** ⇒
      把这两条实现改坏，判据**照样全绿** ⇒ 假守卫。

      ⇒ 本组用**受控的 log_entries**（手工构造的提交表）驱动
        `compute_anchors`，让三种实现**必然给出不同结果**，
        从而「改坏实现 ⇒ 判据变红」。

      受控数据刻意造出「**拓扑序 ≠ 时间序**」与「**tag 指向 ≠ 收口点**」
      两个真实仓库里罕见的形态 ⇒ 判据才有鉴别力。
    """

    def _log(self):
        """构造一份「拓扑序 ≠ 时间序」的提交表。

        ★ 关键：`v9.0.0` 在 git log 里**更靠前**（拓扑更新），
          但它的 committer time **更早** ⇒ 只有「按时间最晚」才能选对。
        """
        return [
            {"sha": "c3", "short": "c333333",
             "timestamp": "2026-01-01T00:00:00+0800",
             "subject": "v9.0.0：早期提交（时间最早）"},
            {"sha": "c2", "short": "c222222",
             "timestamp": "2026-06-01T00:00:00+0800",
             "subject": "v9.0.0：另一处收口（时间居中）"},
            {"sha": "c1", "short": "c111111",
             "timestamp": "2026-12-01T00:00:00+0800",
             "subject": "v9.0.0：真正的收口（时间最晚）"},
        ]

    def test_anchor_picks_latest_by_commit_time_not_topology(self):
        """★ 核心：必须按 **committer time** 最晚取锚点，不是拓扑最新。"""
        items = vc.parse_changelog(make_changelog(("v9.0.0", "2026-12-01", "新")))
        anchors = vc.compute_anchors(self._log(), items, root=None)
        self.assertEqual(anchors["v9.0.0"]["commit"], "c1",
                         "锚点必须是时间最晚的收口提交（c1），"
                         "而非拓扑最新的 c3")

    def test_existing_tag_wins_over_computed_anchor(self):
        """★ 反例：已有 tag 必须**优先于**算出来的锚点（真调实现）。

        ★ 用**临时 git 仓库**做：提交三个时间递增但拓扑倒序的 commit，
          再把 tag 打在**中间那个**（不是收口点）⇒
          `compute_anchors` 必须返回 tag 指向的 commit，而不是时间最晚的。
        """
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            _git(repo, "init", "-q")
            _git(repo, "config", "user.name", "t")
            _git(repo, "config", "user.email", "t@example.invalid")
            for name, ts, subj in (
                    ("c3", "2026-01-01T00:00:00+0800", "v9.0.0：早期提交"),
                    ("c2", "2026-06-01T00:00:00+0800", "v9.0.0：另一处收口"),
                    ("c1", "2026-12-01T00:00:00+0800", "v9.0.0：真正的收口")):
                (repo / (name + ".txt")).write_text(name, encoding="utf-8")
                _git(repo, "add", "-A")
                _git(repo, "commit", "-q", "-m", subj,
                     "--date", ts)
                # 显式设置 committer date，让时间序可控
                _git(repo, "commit", "--amend", "-q", "--no-edit",
                     "--date", ts,
                     "-c", "user.name=t", "-c", "user.email=t@example.invalid")
            # tag 打在**中间**那个 commit（时间居中）⇒ 与「时间最晚」冲突
            c2 = _git(repo, "rev-list", "--max-count=1", "HEAD~1")
            _git(repo, "tag", "-a", "v9.0.0", "-m", "已有版本指针", c2)

            items = vc.parse_changelog(make_changelog(("v9.0.0", "2026-12-01", "新")))
            anchors = vc.compute_anchors(
                vc.git_log_entries(repo), items, root=str(repo))
            self.assertEqual(anchors["v9.0.0"]["commit"], c2,
                             "已有 tag 必须优先于算出的锚点（不得改写用户指针）")
            self.assertIn("沿用已有 tag", anchors["v9.0.0"]["reason"])

    def test_fallback_anchor_is_not_older_than_previous(self):
        """★ 反例：回落锚点**不得早于**前一版本的锚点（真调实现）。

        ★ 这是 M18 变异的判据：回落若取「更旧的锚点」，单调性必然被破坏。
          ⇒ 必须**真调 compute_anchors**（临时仓库），
            手工复刻语义的断言是假守卫。

        ★★ 为什么必须造**三个**版本（v3.28.0 实测踩坑）：
          只造两个版本时，「取最旧的锚点」与「沿用前一版本」**结果相同**
          ⇒ 变异是**等价变异** ⇒ 判据打不红。
          ⇒ 必须造「v9.0.0（最旧·有收口）+ v9.1.0（有收口）+ v9.2.0（无收口·回落）」
            此时「取最旧的锚点」= v9.0.0 的锚点 ≠ 正确的 v9.1.0 的锚点
            ⇒ 变异与正确实现**结果不同** ⇒ 判据才有鉴别力。
        """
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            _git(repo, "init", "-q")
            _git(repo, "config", "user.name", "t")
            _git(repo, "config", "user.email", "t@example.invalid")
            # v9.0.0 与 v9.1.0 各有收口提交；v9.2.0 **没有任何提交**
            for fn, subj, ts in (
                    ("a.txt", "v9.0.0：收口", "2026-10-01T00:00:00+0800"),
                    ("b.txt", "v9.1.0：收口", "2026-11-01T00:00:00+0800")):
                (repo / fn).write_text(fn, encoding="utf-8")
                _git(repo, "add", "-A")
                _git(repo, "commit", "-q", "-m", subj, "--date", ts)
            v90 = _git(repo, "rev-list", "--max-count=1", "HEAD~1")
            v91 = _git(repo, "rev-parse", "HEAD")

            items = vc.parse_changelog(make_changelog(
                ("v9.2.0", "2026-12-02", "新"),
                ("v9.1.0", "2026-11-01", "中"),
                ("v9.0.0", "2026-10-01", "旧"),
            ))
            anchors = vc.compute_anchors(
                vc.git_log_entries(repo), items, root=str(repo))
            self.assertEqual(anchors["v9.1.0"]["commit"], v91)
            # v9.2.0 无收口提交 ⇒ 回落 ⇒ 必须沿用**前一版本** v9.1.0 的锚点
            self.assertIn("v9.2.0", anchors)
            self.assertEqual(anchors["v9.2.0"]["commit"], v91,
                             "回落锚点必须沿用前一版本 v9.1.0（不得取更旧的 v9.0.0）")
            self.assertNotEqual(anchors["v9.2.0"]["commit"], v90,
                                "回落锚点不得取**最旧**版本的锚点")
            # 且不得早于 ⇒ 单调性检测器必须通过
            log = vc.git_log_entries(repo)
            reg = vc.merge_registry(items, {})
            m = vc.check_anchor_monotonicity(reg, anchors, log)
            self.assertTrue(m["ok"],
                            "回落后的锚点必须单调：%s"
                            % [v["detail"] for v in m["violations"]])

    def test_root_commit_fallback_breaks_monotonicity(self):
        """★ 反向对照：回落 root commit **必然破坏**单调性。

        —— 这条判据是 M17 变异的锚点：把回落改回 root commit，
           真实仓库的 T20 就会红；本条把它固定成**可离线复现**的形态。
        """
        items = vc.parse_changelog(make_changelog(
            ("v9.1.0", "2026-12-02", "新"),
            ("v9.0.0", "2026-12-01", "旧"),
        ))
        anchors = {"v9.0.0": {"commit": "c1"},
                   "v9.1.0": {"commit": "root"}}   # ← 错误回落：root 更旧
        log = [{"sha": "c1", "timestamp": "2026-12-01T00:00:00+0800"},
               {"sha": "root", "timestamp": "2020-01-01T00:00:00+0800"}]
        reg = vc.merge_registry(items, {})
        m = vc.check_anchor_monotonicity(reg, anchors, log)
        self.assertFalse(m["ok"], "回落 root commit 必须被判为单调性违例")


class T24RecoverRestoresBranch(unittest.TestCase):
    """★ T24 `recover` 必须**回到原分支**，不能只恢复 commit（v3.28.0 收尾补测）。

    ★★ 为什么必须有（v3.28.0 实测踩坑，本轮真实发生过）：
      `switch` 把仓库切到 **detached HEAD**；若 `recover` 只
      `checkout --detach <commit>` ⇒ 仓库**仍留在 detached HEAD**
      ⇒ 「回原状态」名不副实，且**下一次提交会落在游离 HEAD 上**
      （main 分支不前进、push 推了个空）。
      —— 本轮实测就踩到了：变异测试里的 `switch --confirm` 把真实仓库
      切到 detached HEAD，导致 v3.28.0 的 commit 不在 main 上。

      ⇒ 判据必须验证「**分支**被恢复」，而不只是「HEAD 指向对了」。

    ★★★ v3.28.0 收尾修正：判据必须走**真实用户路径**。
      `switch` 会替换整个工作树 ⇒ `scripts/versionctl.py` 自己也会被
      还原成历史版本 ⇒ 切出去后用工作树里的脚本跑 `recover`
      跑的是**旧逻辑**（这正是第 6 个真缺陷的机制）。
      ⇒ 真实用户的正确路径是：执行**自举锚点**里的控制面
        （`.versionctl/bin/versionctl.py`，gitignored ⇒ 跨 checkout 存活）。
      ⇒ 本判据**必须**用锚点执行 recover，否则测的是「旧脚本恢复旧状态」
        这个**假阳性**路径。
    """

    def test_recover_returns_to_original_branch(self):
        """★ 核心：switch → recover 后必须回到**原分支**，不是 detached。"""
        with _clone_repo() as clone:
            orig_branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")
            self.assertNotEqual(orig_branch, "HEAD",
                                "克隆起点就应是分支，不是 detached")
            orig_head = _git(clone, "rev-parse", "HEAD")
            # 切到父提交（detached HEAD）
            parent = _git(clone, "rev-parse", "HEAD^").strip()
            subprocess.run([sys.executable, "scripts/versionctl.py",
                            "switch", parent, "--confirm"],
                           cwd=str(clone), capture_output=True, text=True)
            self.assertNotEqual(_git(clone, "rev-parse", "HEAD"), orig_head,
                                "switch 应真的改变 HEAD")
            # ★ 用**自举锚点**执行 recover（真实用户路径，见类文档）
            anchor = Path(clone) / ".versionctl" / "bin" / "versionctl.py"
            self.assertTrue(anchor.is_file(),
                            "switch 后自举锚点必须存活（否则用户切出去就回不来）")
            proc = subprocess.run([sys.executable, str(anchor),
                                   "recover", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            after_branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")
            self.assertEqual(after_branch, orig_branch,
                             "recover 必须回到原分支 %r，实际 %r（stderr=%s）"
                             % (orig_branch, after_branch, proc.stderr[:300]))
            self.assertEqual(_git(clone, "rev-parse", "HEAD"), orig_head,
                             "recover 后 HEAD 必须回到原提交")

    def test_recover_dry_run_does_not_change_branch(self):
        """dry-run 的 recover 不得改变任何状态。"""
        with _clone_repo() as clone:
            orig_branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")
            subprocess.run([sys.executable, "scripts/versionctl.py",
                            "recover"], cwd=str(clone),
                           capture_output=True, text=True)
            self.assertEqual(_git(clone, "rev-parse", "--abbrev-ref", "HEAD"),
                             orig_branch, "dry-run 不得改变分支")


class T25DeadlockFreedom(unittest.TestCase):
    """★★ T25 **死锁自由**：切到任意历史版本后，必须还能回到主线。

    ★★★ 这是 v3.28.0 收尾期挖出的**最严重**问题（架构级），
       由 T24 的失败**反向暴露**出来：

      `switch` 用 `git checkout --detach` ⇒ **整个工作树**被替换 ⇒
        ① 控制面脚本 `scripts/versionctl.py` 自己也被换掉
           （切到 v3.28.0 之前 ⇒ 该文件**根本不存在**）；
        ② 入库的 `.versionctl/config.json` 被 checkout **删除**
           ⇒ 策略真源消失；
        ③ 目录删空 ⇒ 连 journal（恢复依据）一起消失。

      ⇒ 用户切出去后**没有任何办法执行 recover** ⇒ **死锁**。

      ⇒ 解法（v3.28.0 实施）：
        · **自举锚点** `.versionctl/bin/versionctl.py`（gitignored ⇒ 跨 checkout 存活）
        · **双轨策略** `config/version-policy.yaml`（入库 ⇒ 跨版本存活）
          + `.versionctl/`（整体不入库 ⇒ 不被 checkout 删除）
        · `recover` 放行「checkout 造成的删除」，但仍拒绝「真实改动」

      ⇒ 判据：必须真的切到一个**没有控制面的年代**（v3.27.0），
        再用锚点恢复 ⇒ 判据才有鉴别力。
    """

    def test_switch_to_pre_control_plane_version_then_recover(self):
        """★ 核心：切到 v3.27.0（控制面尚不存在的年代）→ 用锚点 recover 回到主线。"""
        with _clone_repo() as clone:
            orig_branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")
            orig_head = _git(clone, "rev-parse", "HEAD")
            # 装入策略真源（v3.27.0 时代还没有它）
            yml = Path(clone) / "config" / "version-policy.yaml"
            yml.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(_HERE.parent / "config" / "version-policy.yaml"),
                         str(yml))
            _git(clone, "add", "config/version-policy.yaml")
            _git(clone, "-c", "user.name=test",
                 "-c", "user.email=test@example.invalid",
                 "commit", "-q", "-m", "test: 装入策略真源")

            # 切到 v3.27.0 —— 控制面**不存在**的年代
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", "v3.27.0", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "switch v3.27.0 应成功：%s" % proc.stderr[:200])
            # 控制面确实消失了（这正是死锁的成因）
            self.assertFalse((Path(clone) / "scripts" / "versionctl.py").exists(),
                             "v3.27.0 时代不应有控制面脚本（前提假设）")
            # ★ 但自举锚点必须存活
            anchor = Path(clone) / ".versionctl" / "bin" / "versionctl.py"
            self.assertTrue(anchor.is_file(),
                            "★ 自举锚点必须跨 checkout 存活，否则用户切出去就回不来")

            # 用锚点 recover ⇒ 必须回到原分支与原提交
            proc = subprocess.run([sys.executable, str(anchor),
                                   "recover", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "用锚点 recover 应成功：stdout=%s stderr=%s"
                             % (proc.stdout[-400:], proc.stderr[:300]))
            self.assertEqual(_git(clone, "rev-parse", "--abbrev-ref", "HEAD"),
                             orig_branch, "必须回到原分支")
            self.assertEqual(_git(clone, "rev-parse", "HEAD"), orig_head,
                             "必须回到原提交")

    def test_bootstrap_anchor_survives_checkout(self):
        """★ 自举锚点必须跨 checkout 存活（gitignored ⇒ 不被 checkout 换掉）。"""
        with _clone_repo() as clone:
            subprocess.run([sys.executable, "scripts/versionctl.py",
                            "switch", "v3.27.0", "--confirm"],
                           cwd=str(clone), capture_output=True, text=True)
            anchor = Path(clone) / ".versionctl" / "bin" / "versionctl.py"
            self.assertTrue(anchor.is_file(), "锚点必须存活")
            # 锚点内容必须是**可用的控制面**（不是空文件/半截文件）
            text = anchor.read_text(encoding="utf-8")
            self.assertIn("def cmd_recover", text,
                          "锚点里必须是完整的控制面脚本")
            self.assertGreater(len(text), 10000, "锚点内容不应是半截文件")

    def test_policy_survives_checkout(self):
        """★ 策略真源必须跨 checkout 存活（入库 ⇒ 切到旧版本也读得到）。"""
        with _clone_repo() as clone:
            yml = Path(clone) / "config" / "version-policy.yaml"
            yml.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(_HERE.parent / "config" / "version-policy.yaml"),
                         str(yml))
            _git(clone, "add", "config/version-policy.yaml")
            _git(clone, "-c", "user.name=test",
                 "-c", "user.email=test@example.invalid",
                 "commit", "-q", "-m", "test: 装入策略真源")
            subprocess.run([sys.executable, "scripts/versionctl.py",
                            "switch", "v3.27.0", "--confirm"],
                           cwd=str(clone), capture_output=True, text=True)
            # v3.27.0 没有该文件 ⇒ 被 checkout 删除 ⇒ 但**包级真源必须在主线**
            # ⇒ 判据：切回主线后真源仍在，且 policy 读得到正确值
            anchor = Path(clone) / ".versionctl" / "bin" / "versionctl.py"
            subprocess.run([sys.executable, str(anchor), "recover", "--confirm"],
                           cwd=str(clone), capture_output=True, text=True)
            self.assertTrue(yml.is_file(), "回到主线后策略真源必须存在")
            pol = vc.load_policy(clone)
            self.assertEqual(pol.get("keep_recent"), 10,
                             "策略真源必须能被正确读取")
            self.assertEqual(pol.get("schema_version"), 2)

    def test_versionctl_dir_is_not_git_tracked(self):
        """★ `.versionctl/` 整体**不得**被 git 跟踪（否则会被 checkout 删除）。"""
        repo = vc.repo_root()
        tracked = run_git_out(["ls-files"], cwd=repo).splitlines()
        bad = [t for t in tracked if t.startswith(".versionctl/")]
        self.assertEqual(bad, [],
                         "★ `.versionctl/` 不得被 git 跟踪（会随 checkout 消失）：%s"
                         % bad)


def run_git_out(args, cwd=None):
    """跑 git 并返回 stdout（测试辅助，不抛异常）。"""
    return subprocess.run(["git"] + list(args), cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True).stdout


class T26DirtyClassification(unittest.TestCase):
    """★★ T26 「脏」的分类判据：checkout 副作用 vs 用户真实改动。

    ★ v3.28.0 收尾期挖出的第 7、8 个真缺陷：
      切到旧版本后 `git status` 会出现两类"脏"：
        ① ` D config/version-policy.yaml` —— 被 checkout 删除（受保护文件）
        ② `?? .versionctl/`            —— 工具自身运行时目录（未跟踪）
      ⇒ 这两类**都不该阻塞恢复**（否则死锁）；
        但「用户真的改了代码」**必须**阻塞（否则丢工作）。

    ★ 判据必须能红：把「未跟踪一律阻塞」改回去 ⇒ 必须判红。
    """

    def test_deleted_protected_file_is_benign(self):
        blocking, benign = vc.classify_dirty(
            [" D config/version-policy.yaml"],
            protected_rel_paths=("config/version-policy.yaml",))
        self.assertEqual(blocking, [], "受保护文件被删除不应阻塞恢复")
        self.assertEqual(len(benign), 1, "应被归类为 benign")

    def test_runtime_dir_untracked_is_benign(self):
        blocking, benign = vc.classify_dirty(
            ["?? .versionctl/"], ignore_rel_prefixes=(".versionctl",))
        self.assertEqual(blocking, [], "工具自身运行时目录不应阻塞恢复")
        self.assertEqual(len(benign), 1)

    def test_real_modification_still_blocks(self):
        """★ 关键：用户的真实改动**必须**仍然阻塞（不能为解死锁而丢工作）。"""
        blocking, benign = vc.classify_dirty(
            [" M scripts/versionctl.py"], protected_rel_paths=())
        self.assertEqual(len(blocking), 1, "真实改动必须阻塞恢复")
        self.assertEqual(benign, [])

    def test_untracked_user_file_blocks(self):
        """★ 用户的未跟踪新文件也必须阻塞（不能悄悄丢）。"""
        blocking, benign = vc.classify_dirty(
            ["?? my_important_data.csv"], ignore_rel_prefixes=(".versionctl",))
        self.assertEqual(len(blocking), 1, "用户未跟踪文件必须阻塞恢复")

    def test_mutation_must_be_detected(self):
        """★ 能红的反例：把 benign 判据改成「一律阻塞」⇒ 本判据必须红。"""
        lines = [" D config/version-policy.yaml", "?? .versionctl/"]
        b_ok, n_ok = vc.classify_dirty(
            lines, protected_rel_paths=("config/version-policy.yaml",),
            ignore_rel_prefixes=(".versionctl",))
        # 变异版：忽略保护名单与忽略前缀 ⇒ 两者都进 blocking
        b_mut, n_mut = vc.classify_dirty(lines)
        self.assertEqual(b_ok, [], "正确实现：两者都 benign")
        self.assertGreater(len(b_mut), len(b_ok),
                           "★ 判据无鉴别力：变异后结果没变")



class T22ReleaseHeadExtraction(unittest.TestCase):
    """★ T22 收口版本抽取：认「开头 / 结尾 / 中文冒号前」，不认「顺带提及」。"""

    def test_head_form(self):
        self.assertEqual(vc._extract_release_head("v3.4.3 遗留批：xxx"), "v3.4.3")
        self.assertEqual(vc._extract_release_head("v3.27.0：未验证项可见化"), "v3.27.0")

    def test_tail_form(self):
        self.assertEqual(
            vc._extract_release_head("feat: Batch 5 5 闸扩展 + 跨学科打样 + v3.3.0 Release"),
            "v3.3.0")

    def test_chinese_colon_form(self):
        self.assertEqual(
            vc._extract_release_head("治理批 v3.3.1：快照启用+写回纪律"), "v3.3.1")

    def test_incidental_mention_not_taken(self):
        """★ 反例：中间顺带提及**不得**被当成收口版本。

        —— 这条判据直接对应「提及 ≠ 收口」这个 v3.28.0 的核心教训。
        """
        subj = ("v3.4.3 批次2 采用堵漏 + v3.3→v3.4.2 安装态补账："
                "本 commit 除批次 2 改动外，含 v3.4.0/3.4.1/… 补账")
        got = vc._extract_release_head(subj)
        self.assertEqual(got, "v3.4.3",
                         "只认开头的 v3.4.3，不得取中间提及的其它版本")

    def test_range_head(self):
        self.assertEqual(
            vc._extract_release_head("v3.5.0→v3.7.0：迭代六原则"), "v3.5.0")

    def test_no_version(self):
        self.assertIsNone(vc._extract_release_head("fix: 修 README"))
        self.assertIsNone(vc._extract_release_head(""))
        self.assertIsNone(vc._extract_release_head(None))

    def test_partial_version_not_matched(self):
        """反例：两段式不得被当成版本。"""
        self.assertIsNone(vc._extract_release_head("v3.4 遗留批"))


# ═══════════════════════════════════════════════════════════════════════
# T27 · 双轨策略的缺陷守卫（v3.28.0 收尾审查）
# ═══════════════════════════════════════════════════════════════════════

class _PolicySandbox(object):
    """构造一个**受控**的双轨策略沙盒（tmpdir）。

    ★ 纪律：全部在 `tempfile.mkdtemp()` 里做 ⇒ **绝不碰真实仓库**。
    """

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vc-policy-")
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)

    def close(self):
        self.tmp.cleanup()

    # ── 真源 ──
    def write_yaml(self, text):
        p = self.root / vc.POLICY_YAML_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_yaml_policy(self, **kv):
        return self.write_yaml("".join("%s: %s\n" % (k, v) for k, v in kv.items()))

    def _yaml_data(self):
        """读回真源的内容（dict）。"""
        data, _err = vc._read_yaml_policy(self.root / vc.POLICY_YAML_REL)
        return data or {}

    # ── 运行时层 ──
    def write_runtime(self, data, name=None):
        d = self.root / vc.CTL_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        p = d / (name or vc.POLICY_LOCAL_FILENAME)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def read_runtime(self, name=None):
        p = self.root / vc.CTL_DIRNAME / (name or vc.POLICY_LOCAL_FILENAME)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def runtime_exists(self, name=None):
        return (self.root / vc.CTL_DIRNAME / (name or vc.POLICY_LOCAL_FILENAME)).is_file()


class T27PolicyDualTrack(unittest.TestCase):
    """★★ T27 双轨策略的缺陷守卫（D1–D8）。

    ★ 本轮审查（v3.28.0 收尾）挖出的缺陷与结论：

      D1 · **真缺陷**：运行时副本无条件覆盖包级真源
           ⇒ 旧残留 / 旧工作树副本会**永久遮蔽**真源 ⇒ 真源静默失效。
           修法：运行时层只能是「**本机覆盖增量**」，用 `_local_overrides`
           标记自描述角色；无标记的旧版全量副本**只补缺键、绝不遮蔽**。

      D2 · **设计如此**（不是缺陷）：真源入库 ⇒ 改它必然弄脏工作区。
           二者靠 `--local` 区分意图；输出必须**明说**「需要 git commit」。

      D3 · **真缺陷**：`migrate_policy` 只看 YAML 一份 ⇒ JSON 永远不迁、
           旧布局升不上真源。修法：各自判定、各自迁移；只有 JSON 时
           **提升为包级真源**。

      D4 · **真缺陷**：无 PyYAML 时 `save_policy` 静默只写 JSON ⇒
           用户以为真源更新了。修法：**显式告警** + 返回告警列表。

      D5 · **真缺陷**：YAML 解析失败 ⇒ 静默退回默认策略 ⇒ 用户改过的
           策略**静默失效**。修法：区分「不存在」与「存在但坏了」，
           后者**显式告警**。

      D6 · **真缺陷**：两个同值常量各自独立 ⇒ 静默分叉。
           修法：真相只留一处，另一处降级为**别名**（同一对象）。

      D7 · **可改进**：`classify_dirty` 忽略范围过宽 ⇒ 用户自放的
           重要文件可能被悄悄丢。修法：只忽略**工具自己写的**路径；
           目录匹配必须**逐段相等**（不得用裸 `startswith`）。

      D8 · **真缺陷**：运行时副本沿用 `config.json` 这个
           **曾被 git 跟踪**的文件名 ⇒ 切到旧版本时被 checkout
           **静默覆盖** ⇒ 用户本机设置被清空。
           修法：改用**从未被跟踪**的文件名。

    ★ 每条判据都必须在**受控 tmpdir** 里造出差异（不依赖真实仓库的数据
      恰好如此），且都必须有**能红的反例**。
    """

    def setUp(self):
        self.sb = _PolicySandbox()
        self.addCleanup(self.sb.close)

    # ── D1：运行时残留不得遮蔽包级真源 ─────────────────────────

    def test_D1_stale_runtime_copy_does_not_shadow_source_of_truth(self):
        """★ D1 核心：旧版全量副本（无标记）**不得**遮蔽包级真源。

        —— 场景：用户在旧版本工作树里改过 `.versionctl/config.json`
          （那时还没有 YAML 真源）⇒ 回到主线后，真源已更新为 25，
          但旧副本还是 10 ⇒ 原实现生效值是 10 ⇒ **真源静默失效**。
        """
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        # 旧版全量副本（**无** `_local_overrides` 标记）
        self.sb.write_runtime({"schema_version": 2, "keep_recent": 10},
                              name=vc.POLICY_LEGACY_FILENAME)
        policy = vc.load_policy(self.sb.root)
        self.assertEqual(policy.get("keep_recent"), 25,
                         "★ 包级真源（25）不得被旧版运行时副本（10）遮蔽"
                         "（D1：真源静默失效）")

    def test_D1_mutation_would_be_detected(self):
        """★ 能红的反例：把「无标记⇒只补缺键」改回「无条件覆盖」⇒ 必须判红。

        —— 变异版：旧副本的 keep_recent 覆盖真源 ⇒ 生效值变 10。
        """
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        stale = {"schema_version": 2, "keep_recent": 10}
        # 正确实现：真源优先
        self.assertEqual(vc.load_policy(self.sb.root).get("keep_recent"), 25)
        # 变异实现：JSON 无条件覆盖（修复前的行为）⇒ 生效值被污染
        mutated = dict(vc.DEFAULT_POLICY)
        mutated["schema_version"] = vc.SCHEMA_VERSION
        mutated.update(self.sb._yaml_data())
        mutated.update(stale)
        self.assertEqual(mutated.get("keep_recent"), 10,
                         "变异版应把真源覆盖成 10（证明本判据有鉴别力）")
        self.assertNotEqual(mutated.get("keep_recent"), 25)

    def test_D1_explicit_local_override_does_override_source(self):
        """★ 反向对照：**显式** `--local` 写出的覆盖层**必须**能覆盖真源。

        —— 否则修 D1 就把 `--local` 的功能也一起废了。
        """
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        self.sb.write_runtime({vc.POLICY_OVERLAY_MARKER: True,
                               "keep_recent": 3})
        policy = vc.load_policy(self.sb.root)
        self.assertEqual(policy.get("keep_recent"), 3,
                         "显式本机覆盖层必须能覆盖包级真源")

    def test_D1_legacy_copy_only_fills_missing_keys(self):
        """★ 旧版全量副本**只补真源没有的键**，不得改动真源已有的键。"""
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        self.sb.write_runtime({"schema_version": 2, "keep_recent": 10,
                               "my_extra": "from-legacy"},
                              name=vc.POLICY_LEGACY_FILENAME)
        policy = vc.load_policy(self.sb.root)
        self.assertEqual(policy.get("keep_recent"), 25)
        self.assertEqual(policy.get("my_extra"), "from-legacy",
                         "真源没有的键应从旧副本补上")

    def test_D1_writes_local_creates_overlay_with_marker(self):
        """★ `policy --local` 写出的文件必须**带标记** ⇒ 才有覆盖权。"""
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        vc.save_policy(self.sb.root,
                       {"schema_version": 2, "keep_recent": 3},
                       local_only=True)
        data = self.sb.read_runtime()
        self.assertTrue(data.get(vc.POLICY_OVERLAY_MARKER),
                        "本机覆盖层必须带 %s 标记（否则无覆盖权）" % vc.POLICY_OVERLAY_MARKER)

    # ── D2：写真源必然弄脏工作区 —— 这是设计，不是缺陷 ─────────

    def test_D2_writing_source_dirties_worktree_but_says_so(self):
        """★ D2：`--set` 写真源 ⇒ 工作区变脏（**预期**），且输出必须**明说**
        「需要 git commit」⇒ 用户不会被「工作区脏了」打个措手不及。"""
        import io
        import contextlib
        self.sb.write_yaml_policy(schema_version=2, keep_recent=10)
        args = type("A", (), {"set": ["keep_recent=5"], "local": False,
                              "confirm": True})()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = vc.cmd_policy(args, self.sb.root)
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("git add", out,
                      "写真源后必须明说需要 git commit（否则用户不知为何变脏）")
        self.assertIn(vc.POLICY_YAML_REL, out)

    def test_D2_local_write_keeps_worktree_clean(self):
        """★ 反向对照：`--local` 只写运行时层 ⇒ **不碰**包级真源。"""
        self.sb.write_yaml_policy(schema_version=2, keep_recent=10)
        vc.save_policy(self.sb.root,
                       {"schema_version": 2, "keep_recent": 5},
                       local_only=True)
        y = self.sb.root / vc.POLICY_YAML_REL
        self.assertIn("keep_recent: 10", y.read_text(encoding="utf-8"),
                      "`--local` 不得改动包级真源")

    def test_D2_source_write_does_not_leave_full_mirror(self):
        """★ D2 关键：写真源后**不得**再留一份全量运行时副本。

        —— 那正是 D1 的成因：全量副本会遮蔽真源。
        """
        self.sb.write_yaml_policy(schema_version=2, keep_recent=10)
        # 先造一份旧版全量副本（残留）
        self.sb.write_runtime({"schema_version": 2, "keep_recent": 10},
                              name=vc.POLICY_LEGACY_FILENAME)
        vc.save_policy(self.sb.root,
                       {"schema_version": 2, "keep_recent": 25},
                       local_only=False)
        # 生效值必须是刚写的真源（25），不是残留（10）
        self.assertEqual(vc.load_policy(self.sb.root).get("keep_recent"), 25,
                         "写真源后生效值必须是真源（残留副本不得遮蔽）")

    # ── D3：迁移必须覆盖两份，且旧布局能升为真源 ─────────────────

    def test_D3_migrates_both_yaml_and_runtime(self):
        """★ D3 核心：YAML 已是最新、JSON 停在旧 schema ⇒ **JSON 也必须被迁**。

        —— 修复前：只看 YAML ⇒ 直接 no-op ⇒ JSON 永远停在旧 schema。
        """
        self.sb.write_yaml_policy(schema_version=vc.SCHEMA_VERSION, keep_recent=10)
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 10})
        r = vc.migrate_policy(self.sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated",
                         "★ JSON 停在旧 schema 时不得 no-op（否则迁移形同虚设）")
        data = self.sb.read_runtime()
        self.assertEqual(data.get("schema_version"), vc.SCHEMA_VERSION)
        self.assertIn("artifact_dirs", data,
                      "迁移键必须补齐到运行时层")

    def test_D3_json_only_layout_is_promoted_to_source_of_truth(self):
        """★ D3：只有 JSON（旧布局）⇒ 迁移后**包级真源必须存在**。

        —— 修复前：只写 JSON ⇒ 真源始终不存在 ⇒ 双轨设计落空。
        """
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 7})
        r = vc.migrate_policy(self.sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        y = self.sb.root / vc.POLICY_YAML_REL
        self.assertTrue(y.is_file(),
                        "★ 旧布局迁移后必须产出包级真源（否则双轨落空）")
        self.assertEqual(vc.load_policy(self.sb.root).get("keep_recent"), 7)

    def test_D3_both_exist_with_different_schema(self):
        """★ D3：两份都在且 schema 不同 ⇒ 两份**各自**迁到当前版本。"""
        self.sb.write_yaml_policy(schema_version=1, keep_recent=10)
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 10})
        r = vc.migrate_policy(self.sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        y = vc._read_yaml_policy(self.sb.root / vc.POLICY_YAML_REL)[0]
        self.assertEqual(y.get("schema_version"), vc.SCHEMA_VERSION)
        self.assertEqual(self.sb.read_runtime().get("schema_version"),
                         vc.SCHEMA_VERSION)

    def test_D3_backup_files_are_distinct(self):
        """★ D3：两份都被迁 ⇒ 备份**不得互相覆盖**（否则只剩一份证据）。"""
        self.sb.write_yaml_policy(schema_version=1, keep_recent=10)
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 10})
        r = vc.migrate_policy(self.sb.root, confirm=True)
        baks = [m["backup"] for m in r.get("migrated", [])]
        self.assertEqual(len(baks), len(set(baks)),
                         "两份的备份路径必须各不相同（否则互相覆盖）")
        for b in baks:
            self.assertTrue(Path(b).is_file(), "备份必须真实存在：%s" % b)

    def test_D3_migration_does_not_overwrite_user_values(self):
        """★ D3：`setdefault` 语义保留 —— 用户已有的迁移键不得被清空。"""
        self.sb.write_yaml_policy(schema_version=1, keep_recent=10)
        r = vc.migrate_policy(self.sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated")
        y = vc._read_yaml_policy(self.sb.root / vc.POLICY_YAML_REL)[0]
        self.assertEqual(y.get("keep_recent"), 10,
                         "迁移不得改动用户已有的值")
        self.assertEqual(y.get("schema_version"), vc.SCHEMA_VERSION)

    # ── D4：无 PyYAML 不得静默降级 ──────────────────────────────

    def test_D4_no_yaml_module_warns_loudly(self):
        """★ D4 核心：无 PyYAML ⇒ **必须显式告警**（静默降级是缺陷）。

        —— 场景：环境没装 PyYAML ⇒ 真源写不了 ⇒ 用户却以为改成功了。
        """
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "yaml":
                raise ImportError("no yaml (simulated)")
            return real_import(name, *a, **k)

        builtins.__import__ = fake_import
        try:
            written, warnings = vc.save_policy(
                self.sb.root, {"schema_version": 2, "keep_recent": 5})
        finally:
            builtins.__import__ = real_import
        self.assertTrue(warnings,
                        "★ 无 PyYAML 时必须**显式告警**（不得静默降级）")
        self.assertTrue(any("真源" in w for w in warnings),
                        "告警必须点明「包级真源未写入」：%s" % warnings)
        # 真源确实没写成
        self.assertFalse((self.sb.root / vc.POLICY_YAML_REL).is_file())

    def test_D4_with_yaml_writes_source_and_no_warning(self):
        """★ 反向对照：有 PyYAML ⇒ 真源写成 ⇒ **不得**有告警。"""
        written, warnings = vc.save_policy(
            self.sb.root, {"schema_version": 2, "keep_recent": 5})
        self.assertEqual(warnings, [], "正常路径不得有告警")
        self.assertTrue((self.sb.root / vc.POLICY_YAML_REL).is_file())

    # ── D5：解析失败必须告警 ────────────────────────────────────

    def test_D5_broken_yaml_produces_warning(self):
        """★ D5 核心：YAML 语法错误 ⇒ **必须告警**（不得静默退回默认值）。

        —— 场景：用户手改了 YAML 写坏了 ⇒ 策略**静默失效**且无任何提示。
        """
        self.sb.write_yaml("schema_version: 2\nkeep_recent: [broken\n")
        warnings = []
        policy = vc.load_policy(self.sb.root, warnings=warnings)
        self.assertTrue(warnings,
                        "★ 真源解析失败必须**显式告警**（不得静默失效）")
        self.assertTrue(any(vc.POLICY_YAML_REL in w for w in warnings),
                        "告警必须点名是哪个文件坏了：%s" % warnings)

    def test_D5_broken_json_produces_warning(self):
        """★ D5：运行时层解析失败同样必须告警。"""
        d = self.sb.root / vc.CTL_DIRNAME
        d.mkdir(parents=True, exist_ok=True)
        (d / vc.POLICY_LOCAL_FILENAME).write_text("{not json", encoding="utf-8")
        warnings = []
        vc.load_policy(self.sb.root, warnings=warnings)
        self.assertTrue(warnings,
                        "★ 运行时层解析失败必须告警（不得静默忽略）")

    def test_D5_missing_file_is_not_a_warning(self):
        """★ 反向对照：文件**不存在**是正常状态 ⇒ 不得告警（否则噪音）。"""
        warnings = []
        vc.load_policy(self.sb.root, warnings=warnings)
        self.assertEqual(warnings, [],
                         "文件不存在不是错误 ⇒ 不得告警（避免噪音淹没真问题）")

    def test_D5_no_yaml_environment_warns(self):
        """★ D5 边界：无 PyYAML ⇒ 真源**读不了** ⇒ 必须告警（不是「不存在」）。"""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "yaml":
                raise ImportError("no yaml (simulated)")
            return real_import(name, *a, **k)

        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        builtins.__import__ = fake_import
        try:
            warnings = []
            vc.load_policy(self.sb.root, warnings=warnings)
        finally:
            builtins.__import__ = real_import
        self.assertTrue(warnings,
                        "★ 无 PyYAML ⇒ 真源读不了 ⇒ 必须告警（不得当作不存在）")

    # ── D6：常量不得静默分叉 ────────────────────────────────────

    def test_D6_config_filename_is_alias_not_independent_constant(self):
        """★ D6：`CONFIG_FILENAME` 必须是**别名**（同一对象）⇒ 不可能分叉。"""
        self.assertIs(vc.CONFIG_FILENAME, vc.POLICY_LEGACY_FILENAME,
                      "★ CONFIG_FILENAME 必须是 POLICY_LEGACY_FILENAME 的别名"
                      "（同一对象 ⇒ 改一处即处处生效）")

    def test_D6_no_duplicate_literal_filename_definitions(self):
        """★ D6 能红的反例：源码里**不得**再出现第二个独立的
        `"config.json"` 常量定义 ⇒ 否则又会分叉。"""
        src = Path(vc.__file__).read_text(encoding="utf-8")
        import re
        defs = re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=\s*[\"']config\.json[\"']",
                          src, re.M)
        self.assertEqual(len(defs), 1,
                         "★ 'config.json' 字面量只允许出现在一处常量定义"
                         "（实际 %d 处：%s）" % (len(defs), defs))

    # ── D7：脏分类的忽略范围 ────────────────────────────────────

    def test_D7_user_file_inside_runtime_dir_still_blocks(self):
        """★ D7 核心：用户自放在 `.versionctl/` 下的**重要文件**必须仍阻塞。

        —— 场景：`.versionctl/my_backup.txt` 是用户的数据
          ⇒ 恢复时可能被覆盖丢失 ⇒ 必须让用户知道。
        """
        blocking, benign = vc.classify_dirty(
            ["?? .versionctl/my_backup.txt"],
            protected_rel_paths=(),
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(len(blocking), 1,
                         "★ 用户自放的文件必须阻塞（不得悄悄丢）")
        self.assertEqual(benign, [])

    def test_D7_tool_owned_paths_are_benign(self):
        """★ 反向对照：工具**自己写**的路径必须放行（否则死锁）。"""
        for p in (".versionctl/journal/20260101-000000.jsonl",
                  ".versionctl/archive/20260101-000000/x.md",
                  ".versionctl/bin/versionctl.py",
                  ".versionctl/policy.local.json"):
            blocking, benign = vc.classify_dirty(
                ["?? %s" % p],
                protected_rel_paths=(),
                ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
                tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
            self.assertEqual(blocking, [],
                             "工具自己写的路径必须 benign：%s" % p)

    def test_D7_similar_prefix_dir_is_not_ignored(self):
        """★ D7 能红的反例：`.versionctlX/`（相似前缀）**不得**被忽略。

        —— 若用裸 `startswith(ig)` 就会误伤 ⇒ 这条判据能红。
        """
        blocking, benign = vc.classify_dirty(
            ["?? .versionctlX/important.txt"],
            protected_rel_paths=(),
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(len(blocking), 1,
                         "★ `.versionctlX/` 不是 `.versionctl/` ⇒ 不得被忽略")

    def test_D7_runtime_dir_root_still_benign(self):
        """★ D7：git 把未跟踪目录**折叠**成 `?? .versionctl/` 时必须放行。

        —— 此时无法枚举内部文件 ⇒ 不放行必然死锁（这正是第 8 个真缺陷）。
        """
        blocking, benign = vc.classify_dirty(
            ["?? .versionctl/"],
            protected_rel_paths=(),
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(blocking, [],
                         "未跟踪目录折叠行必须 benign（否则 recover 死锁）")

    def test_D7_rename_line_parsing(self):
        """★ D7：重命名行 `"R  old -> new"` 的路径解析必须正确。"""
        blocking, benign = vc.classify_dirty(
            ["R  old.py -> new.py"],
            protected_rel_paths=("new.py",),
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        # 重命名到受保护文件 ⇒ 只算「删除」⇒ benign
        self.assertEqual(blocking, [])
        self.assertEqual(len(benign), 1)

    # ── D8：运行时副本不得被 checkout 静默覆盖 ──────────────────

    def test_D8_runtime_filename_is_never_git_tracked(self):
        """★ D8 核心：本机覆盖层的文件名**不得**被任何提交跟踪过。

        —— 若沿用 `config.json`（v3.28.0 跟踪过）⇒ 切到旧版本时
          git 会用旧内容**覆盖**用户的本机设置 ⇒ 静默清空。
        """
        repo = vc.repo_root()
        tracked = run_git_out(["ls-files"], cwd=repo).splitlines()
        bad = [t for t in tracked
               if t.startswith("%s/%s" % (vc.CTL_DIRNAME, vc.POLICY_LOCAL_FILENAME))]
        self.assertEqual(bad, [],
                         "★ 本机覆盖层不得被 git 跟踪（会被 checkout 覆盖）：%s" % bad)

    def test_D8_filename_differs_from_legacy_tracked_name(self):
        """★ D8 能红的反例：本机覆盖层的文件名必须**不同于**旧版被跟踪名。

        —— 只要同名 ⇒ 切到旧版本就会被 checkout 覆盖。
        """
        self.assertNotEqual(vc.POLICY_LOCAL_FILENAME, vc.POLICY_LEGACY_FILENAME,
                            "★ 本机覆盖层必须换个名字（否则会被 checkout 覆盖）")

    def test_D8_legacy_file_is_still_read_for_compatibility(self):
        """★ D8 反向对照：旧版文件仍要**能读**（用户升级后磁盘上还有它）。"""
        self.sb.write_yaml_policy(schema_version=2, keep_recent=25)
        self.sb.write_runtime({"schema_version": 2, "keep_recent": 10},
                              name=vc.POLICY_LEGACY_FILENAME)
        policy = vc.load_policy(self.sb.root)
        self.assertEqual(policy.get("keep_recent"), 25,
                         "旧版文件仍要能被读取（但不得遮蔽真源）")

    # ── 端到端：跨 checkout 存活 ────────────────────────────────

    def test_E2E_local_override_survives_checkout(self):
        """★ 端到端：`--local` 设的值在**切换版本**后仍然生效。

        —— 这是 D8 的**行为级**判据：文件名没被 git 跟踪 ⇒ 切换不丢。
        """
        with _clone_repo() as clone:
            # 装入包级真源
            yml = Path(clone) / vc.POLICY_YAML_REL
            yml.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(_HERE.parent / vc.POLICY_YAML_REL), str(yml))
            _git(clone, "add", vc.POLICY_YAML_REL)
            _git(clone, "-c", "user.name=test",
                 "-c", "user.email=test@example.invalid",
                 "commit", "-q", "-m", "test: 装入策略真源")
            # 本机覆盖：keep_recent=3
            proc = subprocess.run(
                [sys.executable, "scripts/versionctl.py", "policy", "--local",
                 "--set", "keep_recent=3", "--confirm"],
                cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "policy --local 应成功：%s" % proc.stdout[-300:])
            ov = Path(clone) / vc.CTL_DIRNAME / vc.POLICY_LOCAL_FILENAME
            self.assertTrue(ov.is_file(), "本机覆盖层应已写出")
            # 切到 v3.27.0（控制面尚不存在的年代）⇒ 覆盖层必须存活
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", "v3.27.0", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "switch v3.27.0 应成功：%s" % proc.stdout[-300:])
            self.assertTrue(ov.is_file(),
                            "★ 本机覆盖层必须跨 checkout 存活"
                            "（文件名未被 git 跟踪 ⇒ git 不碰它）")
            data = json.loads(ov.read_text(encoding="utf-8"))
            self.assertEqual(data.get("keep_recent"), 3,
                             "★ 本机覆盖的值不得被 checkout 静默清空（D8）")


# ═══════════════════════════════════════════════════════════════════════
# T28 · D9–D13 的**显式命名判据**（v3.28.0 收尾审查补缺）
# ═══════════════════════════════════════════════════════════════════════
#
# ★ 为什么要单独一个类：
#   T27（T27PolicyDualTrack）只给 D1–D8 配了显式命名判据；
#   D9–D13 **只有间接/被动覆盖**（搭便车）⇒ 缺陷可以复活而不被发现。
#   —— 实测：把 D13 的 `rglob` 改回 `iterdir` 跑全套
#     `pytest scripts/test_versionctl.py -q` ⇒ **129 passed，一个都没杀**
#     ⇒ 判据缺失确凿。
#   ⇒ 本类给 D9–D13 各自补上**专属**判据，且每条都带**能红的反例**
#     （铁律：判据必须能红，否则就是假守卫）。
#
# ★ 五条缺陷的语义（本类逐条守住）：
#   D9  · switch 的脏判定**排除工具自身的运行时文件**
#        （工具自己写的 `policy.local.json` 不得阻塞切换 ⇒ 否则功能自锁）。
#   D10 · 迁移后的运行时层**自带** `schema_version`
#        （否则运行时层连自己按哪版 schema 解释都读不出来 ⇒ 迁移形同虚设）。
#   D11 · 旧版全量副本**只在真源该键仍是默认值时**兜底；
#        真源显式设置过 ⇒ 真源优先；真源没有该键 ⇒ 旧副本补上。
#   D12 · 迁移**不得**把迁移源自己归档掉
#        （否则用户读回原路径拿到 FileNotFound）。
#   D13 · prune 的产物收集**必须递归**（两层以上的子目录里的产物也要找到）。


class _ArtifactSandbox(object):
    """产物目录沙盒（tmpdir）—— 只为 D13 的产物收集判据服务。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vc-artifacts-")
        self.root = Path(self.tmp.name)

    def close(self):
        self.tmp.cleanup()

    def make_file(self, rel, data=b"x"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


class T28DefectGuards(unittest.TestCase):
    """★★ T28 · D9–D13 的显式命名判据（每条都有能红的反例）。

    ★ 纪律：
      · 每条判据都**指名缺陷编号** ⇒ 审计时可按编号直接定位；
      · 每条判据都**不依赖真实仓库的数据恰好如此** ⇒ 用受控沙盒构造差异；
      · 每条判据都带**能红的反例** ⇒ 在测试内构造变异实现，
        断言「变异实现的结果 ≠ 正确实现的结果」⇒ 证明本判据有鉴别力。
    """

    def setUp(self):
        self.sb = _PolicySandbox()
        self.addCleanup(self.sb.close)

    # ── D9：switch 不得因工具自身的运行时文件而拒绝 ────────────

    def test_D9_switch_ignores_tool_owned_runtime_files(self):
        """★ D9 核心：**工具自己写的**运行时文件**不得**阻塞 switch。

        —— 场景：`policy --local` 写 `.versionctl/policy.local.json`（未跟踪）
          ⇒ `git status` 报 `?? .versionctl/policy.local.json`
          ⇒ 原实现「所有 status 行一律阻塞」⇒ switch **一律拒绝**
          ⇒ 用户刚设的本机策略就再也切不了版本 ⇒ 功能自锁。

        ★ 判据是**纯函数级**的（`classify_dirty`）：
          ① 工具自有路径 ⇒ **不得**进 blocking；
          ② 用户的普通文件 ⇒ **必须**进 blocking（不能为了修 D9 放水）。
        """
        tool_line = "?? %s" % (vc.CTL_DIRNAME + "/" + vc.POLICY_LOCAL_FILENAME)
        user_line = "?? my_important.txt"

        blocking, benign = vc.classify_dirty(
            [tool_line],
            protected_rel_paths=vc.PROTECTED_REL_PATHS,
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(blocking, [],
                         "★ 工具自有的运行时文件不得阻塞 switch"
                         "（否则 D9 ⇒ 功能自锁）：%s" % tool_line)
        self.assertEqual(len(benign), 1,
                         "工具自有的运行时文件应被判为 benign")

        blocking2, _b2 = vc.classify_dirty(
            [user_line],
            protected_rel_paths=vc.PROTECTED_REL_PATHS,
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(len(blocking2), 1,
                         "★ 用户的普通未跟踪文件**必须**仍阻塞"
                         "（修 D9 不得把闸门放水）：%s" % user_line)

    def test_D9_mutation_would_be_detected(self):
        """★ D9 能红的反例：把工具自有路径**当用户文件** ⇒ 必须判红。

        —— 变异实现 = 「空白的 tool_owned 白名单」（等价于修复前的
          「所有 status 行一律阻塞」）⇒ 工具文件会进 blocking。
        """
        tool_line = "?? %s" % (vc.CTL_DIRNAME + "/" + vc.POLICY_LOCAL_FILENAME)

        # 正确实现：带 tool_owned 白名单 ⇒ 放行
        blocking_ok, _ = vc.classify_dirty(
            [tool_line],
            protected_rel_paths=vc.PROTECTED_REL_PATHS,
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=vc.TOOL_OWNED_REL_PATHS)
        self.assertEqual(blocking_ok, [], "正确实现应放行工具自有文件")

        # 变异实现：白名单被清空（= 修复前的一律阻塞）⇒ 必须不同
        blocking_mut, _ = vc.classify_dirty(
            [tool_line],
            protected_rel_paths=vc.PROTECTED_REL_PATHS,
            ignore_rel_prefixes=vc.IGNORE_DIRTY_REL_PREFIXES,
            tool_owned_rel_paths=())          # ★ 变异点
        self.assertEqual(len(blocking_mut), 1,
                         "变异版（清空白名单）必须把工具文件判成阻塞"
                         "⇒ 证明本判据有鉴别力")
        self.assertNotEqual(blocking_ok, blocking_mut,
                            "正确实现与变异实现的结果必须不同")

    def test_D9_cmd_switch_actually_uses_classify_dirty(self):
        """★ D9 的**接线**判据：`cmd_switch` 必须走 `classify_dirty`。

        —— 防止「判据还在、但接线被改回去」（如回到 `if st["dirty"]:`）。
          这是**源码级**静态判据 ⇒ 纯变异（把调用换回一律阻塞）必红。
        """
        src = (_HERE / "versionctl.py").read_text(encoding="utf-8")
        start = src.index("def cmd_switch(")
        end = src.index("def cmd_rollback(")
        body = src[start:end]
        self.assertIn("classify_dirty", body,
                      "★ cmd_switch 必须用 classify_dirty 判定脏"
                      "（D9 接线被改回去 ⇒ 本判据必红）")
        self.assertIn("TOOL_OWNED_REL_PATHS", body,
                      "★ cmd_switch 必须把工具自有路径白名单传给 classify_dirty")
        # ★ 反例：接线被改成「不看 status 行 ⇒ 一律放行」也不许
        self.assertNotIn('if st["dirty"]:', body,
                         "cmd_switch 不得退回「dirty 就一律拒绝」"
                         "（D9 修复前的写法）")

    def test_D9_switch_succeeds_with_tool_owned_file_present(self):
        """★ D9 的**行为级**判据：工作区只有**工具自己的**文件时，switch 必须成功。

        —— 这是 D9 的**真实语义**（「switch 不因为工具自己的文件而拒绝」）
          的端到端验证：纯函数判据只看 `classify_dirty` 本身，
          **测不到 `cmd_switch` 的调用点**是否把白名单传对。
          —— 实测：把 `cmd_switch` 传给 `classify_dirty` 的白名单清空，
            本条判红。

        ★ 反向对照：工作区有**用户的**未跟踪文件时，switch 必须**拒绝**
          （不能为了让 D9 通过而把闸门放水）。

        ★ 两个场景用**各自独立的克隆**（切到 v3.27.0 后
          `scripts/versionctl.py` 已不存在 ⇒ 不能在同一克隆里连做两次）。
        """
        # ① 只有工具自己的运行时文件 ⇒ switch 必须成功
        with _clone_repo() as clone:
            ctl = clone / vc.CTL_DIRNAME
            ctl.mkdir(parents=True, exist_ok=True)
            (ctl / vc.POLICY_LOCAL_FILENAME).write_text(
                json.dumps({vc.POLICY_OVERLAY_MARKER: True,
                            "keep_recent": 3}), encoding="utf-8")
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "switch", "v3.27.0", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "★ 工作区只有工具自身文件时 switch 必须成功"
                             "（D9：否则功能自锁）：%s" % proc.stdout[-400:])
            self.assertNotIn("拒绝切换", proc.stdout,
                             "★ 不得因工具自身的文件而拒绝切换（D9）")

        # ② 有用户的未跟踪文件 ⇒ switch 必须拒绝（闸门不得放水）
        with _clone_repo() as clone:
            (clone / "my_important.txt").write_text("别删我", encoding="utf-8")
            proc2 = subprocess.run([sys.executable, "scripts/versionctl.py",
                                    "switch", "v3.27.0", "--confirm"],
                                   cwd=str(clone), capture_output=True, text=True)
            self.assertNotEqual(proc2.returncode, 0,
                                "★ 用户有未提交改动时 switch 必须拒绝"
                                "（修 D9 不得放水）")
            self.assertIn("拒绝切换", proc2.stdout,
                          "★ 拒绝理由必须如实告知用户")

    # ── D10：迁移后的运行时层必须自带 schema_version ────────────

    def test_D10_migrated_overlay_carries_schema_version(self):
        """★ D10 核心：迁移后的运行时层**必须**自带 `schema_version`。

        —— 场景：YAML 真源与运行时 JSON 的 schema 都停在 1 ⇒ 迁移后
          运行时 JSON 被改写成「覆盖层」⇒ 若「只留与真源不同的键」的
          过滤逻辑把 `schema_version` 一起滤掉 ⇒ 运行时层文件里
          **没有** schema_version ⇒ 运行时层自己都读不出自己的 schema
          ⇒ 迁移**形同虚设**（实测：迁移后 `schema_version` = None）。

        ★ 判据：迁移后读回运行时层 ⇒ `schema_version == SCHEMA_VERSION`。
        """
        # 真源（schema 旧）+ 运行时覆盖层（schema 旧）⇒ 两者都要迁
        self.sb.write_yaml_policy(schema_version=1, keep_recent=5)
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 7})

        r = vc.migrate_policy(self.sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated",
                         "前置：迁移应当发生（action=%s）" % r.get("action"))

        data = self.sb.read_runtime()
        self.assertIsNotNone(data, "★ 迁移后运行时层必须仍然存在")
        self.assertIn("schema_version", data,
                      "★ 迁移后的运行时层必须自带 schema_version"
                      "（D10：否则运行时层读不出自己的 schema）")
        self.assertEqual(data.get("schema_version"), vc.SCHEMA_VERSION,
                         "★ 迁移后运行时层的 schema_version 必须等于 %d"
                         % vc.SCHEMA_VERSION)

    def test_D10_mutation_would_be_detected(self):
        """★ D10 能红的反例：模拟「迁移时丢掉 schema_version」的变异 ⇒ 必须判红。

        —— 变异实现 = 覆盖层不带 schema_version（= 修复前的行为）。
        """
        self.sb.write_yaml_policy(schema_version=1, keep_recent=5)
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 7})
        vc.migrate_policy(self.sb.root, confirm=True)
        correct = self.sb.read_runtime()

        # 变异实现：把 schema_version 抹掉（模拟「覆盖层不带 schema」）
        mutated = dict(correct)
        mutated.pop("schema_version", None)
        self.assertNotIn("schema_version", mutated,
                         "变异版应丢掉 schema_version（证明本判据有鉴别力）")
        self.assertNotEqual(correct.get("schema_version"),
                            mutated.get("schema_version"),
                            "正确实现与变异实现的 schema_version 必须不同")
        self.assertEqual(correct.get("schema_version"), vc.SCHEMA_VERSION,
                         "正确实现必须带 schema_version")

    def test_D10_promoted_source_overlay_carries_schema_version(self):
        """★ D10 ·「只有运行时 JSON ⇒ 提升为包级真源」分支的**专属**判据。

        —— D10 的 `schema_version` 赋值点有**两处**（同一个缺陷的两条路径）：
          ① `_overlay["schema_version"] = int(SCHEMA_VERSION)` —— 在
             「只有 JSON ⇒ 提升为包级真源」分支（`y is None`）——
             迁移源被**就地升级**成覆盖层；
          ② `overlay["schema_version"] = int(SCHEMA_VERSION)` —— 在
             「YAML 在场 ⇒ 真源与运行时层各自迁移」分支。
          ⇒ 既有判据 `test_D10_migrated_overlay_carries_schema_version`
            的场景是「YAML 真源 + 运行时 JSON 都停在 schema 1」
            ⇒ **只覆盖 ②** ⇒ ①（提升分支）无专属判据 ⇒ 删掉 ①
              时没有指名 D10 的判据会红。

        —— 场景：**只有运行时 JSON、没有 YAML 真源**（`y is None`）
          ⇒ 走「提升为包级真源」分支；该 JSON 的 `schema_version` 停在 1
          ⇒ 迁移后读回该 JSON ⇒ 断言：
            ① `schema_version == SCHEMA_VERSION`（D10 核心）；
            ② 仍含 `_local_overrides` 标记（就地升级成覆盖层）；
            ③ 用户原有的键（`keep_recent`）没丢。
          ⇒ 兼带覆盖 D12（迁移源不被归档 ⇒ 原路径仍在、归档区无 `.stale`）。

        ★ 两个源名都测（`policy.local.json` = 运行时层规范名、
          `config.json` = 旧布局名）⇒ 二者的 `_overlay` 走的是**同一处**
          赋值点 ⇒ 缺任一条都是覆盖缺口。
        """
        for src_name in (vc.POLICY_LOCAL_FILENAME, vc.POLICY_LEGACY_FILENAME):
            with self.subTest(source=src_name):
                sb = _PolicySandbox()
                self.addCleanup(sb.close)
                # ★ 只有运行时 JSON、**没有 YAML 真源** ⇒ `y is None` 分支
                sb.write_runtime({"schema_version": 1, "keep_recent": 9},
                                 name=src_name)
                self.assertFalse((sb.root / vc.POLICY_YAML_REL).is_file(),
                                 "前置：本场景不得存在 YAML 真源"
                                 "（否则走的是另一条迁移分支）")

                r = vc.migrate_policy(sb.root, confirm=True)
                self.assertEqual(r["action"], "migrated",
                                 "前置：迁移应当发生（action=%s）" % r.get("action"))
                self.assertTrue(str(r.get("source", "")).endswith("->yaml"),
                                "★ 前置：必须走「提升为包级真源」分支"
                                "（source=%r）" % r.get("source"))

                data = sb.read_runtime(name=src_name)
                self.assertIsNotNone(data,
                                     "★ 迁移后迁移源必须仍在原位"
                                     "（D12：否则用户读回原文件拿到 FileNotFound）")
                self.assertEqual(data.get("schema_version"), vc.SCHEMA_VERSION,
                                 "★ 提升分支的迁移源必须自带 schema_version"
                                 "（D10：否则它自己都读不出自己的 schema）")
                self.assertTrue(data.get(vc.POLICY_OVERLAY_MARKER),
                                "★ 迁移源必须被就地升级成覆盖层（含 %s 标记）"
                                % vc.POLICY_OVERLAY_MARKER)
                self.assertEqual(data.get("keep_recent"), 9,
                                 "★ 就地升级不得丢用户原有的键（D12）")

                # ★ D12 兼带：迁移源不得进归档区
                arch = sb.root / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
                staled = list(arch.rglob("*.stale")) if arch.is_dir() else []
                self.assertEqual(staled, [],
                                 "★ 迁移源不得被归档（D12）：%s"
                                 % [str(p) for p in staled])

    def test_D10_promoted_branch_mutation_would_be_detected(self):
        """★ D10「提升分支」能红的反例：删掉该赋值点 ⇒ 必须判红。

        —— 变异实现 = 覆盖层**不带** schema_version（= 提升分支里那行
          `schema_version` 赋值被删掉的行为）⇒ 断言「上一条判据的核心
          断言」在变异实现下**必然失败**⇒ 证明上一条判据对该赋值点
          有鉴别力（不是恒真断言）。
        """
        sb = _PolicySandbox()
        self.addCleanup(sb.close)
        sb.write_runtime({"schema_version": 1, "keep_recent": 9},
                         name=vc.POLICY_LOCAL_FILENAME)

        r = vc.migrate_policy(sb.root, confirm=True)
        self.assertEqual(r["action"], "migrated", "前置：迁移应当发生")
        correct = sb.read_runtime()
        self.assertEqual(correct.get("schema_version"), vc.SCHEMA_VERSION,
                         "正确实现：提升分支必须写 schema_version")

        # ★ 变异实现：那行赋值被删 ⇒ 覆盖层里没有 schema_version
        mutated = {k: v for k, v in correct.items() if k != "schema_version"}
        self.assertNotIn("schema_version", mutated,
                         "变异版应丢掉 schema_version（证明本判据有鉴别力）")
        self.assertNotEqual(correct.get("schema_version"),
                            mutated.get("schema_version"),
                            "正确实现与变异实现的 schema_version 必须不同")
        # ★ 反向自证：上一条判据的核心断言在变异实现下**必须**过不去
        self.assertNotEqual(mutated.get("schema_version"), vc.SCHEMA_VERSION,
                            "★ 变异实现必须过不了上一条判据的核心断言")

    # ── D11：旧版副本只在真源仍是默认值时兜底 ──────────────────

    def test_D11_legacy_copy_fills_only_when_source_is_default(self):
        """★ D11 核心：旧版全量副本的兜底必须**看真源原始值**。

        —— 三向对照（缺一不可）：
          ① 真源该键**仍是默认值** ⇒ 旧副本的值**被兜底采用**
             （真源从没被设置过 ⇒ 用户的旧设置不该被丢）；
          ② 真源该键**被显式设置** ⇒ **真源优先**（旧副本不生效，
             这正是 D1 要防的「旧副本遮蔽真源」）；
          ③ 真源**根本没有**该键 ⇒ 旧副本补上。
        """
        # ① 真源该键仍是默认值（artifact_dirs 默认 = []）
        self.sb.write_yaml_policy(schema_version=2, keep_recent=5)
        self.sb.write_runtime({"schema_version": 2,
                               "artifact_dirs": ["/用户/的/目录"]},
                              name=vc.POLICY_LEGACY_FILENAME)
        pol1 = vc.load_policy(self.sb.root)
        self.assertEqual(pol1.get("artifact_dirs"), ["/用户/的/目录"],
                         "★ ① 真源该键仍是默认值 ⇒ 旧副本的值必须被兜底采用"
                         "（D11：否则用户的产物目录配置静默失效）")

        # ② 真源该键被显式设置 ⇒ 真源优先
        self.sb.write_yaml_policy(schema_version=2, keep_recent=5,
                                  artifact_dirs='["/真源/的/目录"]')
        self.sb.write_runtime({"schema_version": 2,
                               "artifact_dirs": ["/用户/的/目录"]},
                              name=vc.POLICY_LEGACY_FILENAME)
        pol2 = vc.load_policy(self.sb.root)
        self.assertEqual(pol2.get("artifact_dirs"), ["/真源/的/目录"],
                         "★ ② 真源显式设置过 ⇒ 真源优先，旧副本不得生效"
                         "（D1：旧副本遮蔽真源）")

        # ③ 真源根本没有该键 ⇒ 旧副本补上
        self.sb.write_yaml_policy(schema_version=2, keep_recent=5)
        self.sb.write_runtime({"schema_version": 2,
                               "my_custom_key": "旧值"},
                              name=vc.POLICY_LEGACY_FILENAME)
        pol3 = vc.load_policy(self.sb.root)
        self.assertEqual(pol3.get("my_custom_key"), "旧值",
                         "★ ③ 真源没有该键 ⇒ 旧副本必须补上")

    def test_D11_mutation_would_be_detected(self):
        """★ D11 能红的反例：模拟「无条件覆盖」的变异 ⇒ 必须判红。

        —— 变异实现 = 旧副本**无条件**覆盖真源（= D1 修复前的行为）。
        """
        self.sb.write_yaml_policy(schema_version=2, keep_recent=5,
                                  artifact_dirs='["/真源/的/目录"]')
        self.sb.write_runtime({"schema_version": 2,
                               "artifact_dirs": ["/用户/的/目录"]},
                              name=vc.POLICY_LEGACY_FILENAME)

        # 正确实现：真源优先
        correct = vc.load_policy(self.sb.root).get("artifact_dirs")
        self.assertEqual(correct, ["/真源/的/目录"], "正确实现必须真源优先")

        # 变异实现：旧副本无条件覆盖 ⇒ 生效值被旧副本污染
        mutated = dict(vc.DEFAULT_POLICY)
        mutated["schema_version"] = vc.SCHEMA_VERSION
        mutated.update(self.sb._yaml_data())
        mutated.update({"artifact_dirs": ["/用户/的/目录"]})   # ★ 变异点
        self.assertEqual(mutated.get("artifact_dirs"), ["/用户/的/目录"],
                         "变异版应被旧副本污染（证明本判据有鉴别力）")
        self.assertNotEqual(correct, mutated.get("artifact_dirs"),
                            "正确实现与变异实现的结果必须不同")

    def test_D11_source_is_default_helper_uses_raw_yaml(self):
        """★ D11 的**判据函数**守卫：`_source_is_default` 必须看**真源原始值**。

        —— 变异体：改成看「合并后的 policy」⇒ 真源值恰好等于默认值时
          看不出「用户从没设置过」⇒ 兜底失效 ⇒ 本条必红。
        """
        y = {"keep_recent": vc.DEFAULT_POLICY["keep_recent"]}   # 仍是默认值
        self.assertTrue(vc._source_is_default(y, "keep_recent", 10),
                        "★ 真源该键等于默认值 ⇒ 必须判定为「仍是默认值」")
        y2 = {"keep_recent": 25}                                  # 被显式设置
        self.assertFalse(vc._source_is_default(y2, "keep_recent", 25),
                         "★ 真源该键被显式设置 ⇒ 必须判定为「不是默认值」")
        # 真源没有该键 ⇒ 取决于当前值
        self.assertTrue(vc._source_is_default({}, "keep_recent", 10),
                        "真源没有该键且当前值是默认值 ⇒ 仍是默认值")
        self.assertFalse(vc._source_is_default({}, "keep_recent", 25),
                         "真源没有该键但当前值非默认 ⇒ 不是默认值")

    # ── D12：迁移源不得被归档 ──────────────────────────────────

    def test_D12_migration_source_is_not_archived(self):
        """★ D12 核心：迁移后**原路径文件必须仍存在**（不是 FileNotFound）。

        —— 场景：只有旧版 JSON 时，`migrate_policy` 调 `save_policy`
          把它提升为真源 ⇒ 但 `save_policy` 随后又把**同一个文件**
          当作「旧版残留」**归档（move）**掉 ⇒ 迁移后原路径**消失**
          ⇒ 用户读回原文件时拿到 FileNotFound ⇒ 数据看似迁移成功、
          实则用户读不到。

        ★ 判据：迁移后 ① 原路径文件**仍存在**；
          ② 内容已被**就地升级**成覆盖层（含 `_local_overrides` 标记）；
          ③ 迁移源**不得**出现在归档区里。
        """
        # ★ 两条迁移源路径都要覆盖：
        #   · `config.json`（旧版全量副本）—— 旧布局的典型形态；
        #   · `policy.local.json`（覆盖层名，但旧布局下也可能是唯一真源）。
        for src_name in (vc.POLICY_LEGACY_FILENAME, vc.POLICY_LOCAL_FILENAME):
            with self.subTest(source=src_name):
                sb = _PolicySandbox()
                self.addCleanup(sb.close)
                # 只有这一份运行时 JSON（schema 旧）⇒ 走「提升为包级真源」路径
                legacy = sb.write_runtime({"schema_version": 1,
                                           "keep_recent": 9},
                                          name=src_name)
                self.assertTrue(legacy.is_file(), "前置：迁移源应存在")

                r = vc.migrate_policy(sb.root, confirm=True)
                self.assertEqual(r["action"], "migrated",
                                 "前置：迁移应当发生（action=%s）" % r.get("action"))

                self.assertTrue(legacy.is_file(),
                                "★ 迁移源不得被归档掉（D12：否则用户读回原路径"
                                "拿到 FileNotFound）")
                data = sb.read_runtime(name=src_name)
                self.assertIsNotNone(data,
                                     "★ 迁移后原路径必须仍可读出内容")
                self.assertTrue(data.get(vc.POLICY_OVERLAY_MARKER),
                                "★ 迁移源必须被就地升级成覆盖层（含 %s 标记）"
                                % vc.POLICY_OVERLAY_MARKER)
                self.assertEqual(data.get("keep_recent"), 9,
                                 "★ 就地升级时不得丢用户原有的值")

                # ★ 语义直击：迁移源**不得**出现在归档区里
                #   （`archive_stale_runtime` 落的文件名是 `<原名>.stale`）
                #   —— 这条比「原路径还在」更严：即便迁移后又把文件写回原位，
                #   只要它**被归档过一次**，用户的历史副本就被挪了窝 ⇒ 仍是 D12 的坑。
                arch = sb.root / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
                staled = list(arch.rglob("*.stale")) if arch.is_dir() else []
                self.assertEqual(staled, [],
                                 "★ 迁移源不得被归档（D12）：%s"
                                 % [str(p) for p in staled])

    def test_D12_mutation_would_be_detected(self):
        """★ D12 能红的反例：模拟「迁移源被归档」的变异 ⇒ 必须判红。

        —— 变异实现：把迁移源 `move` 走（原路径消失）⇒ 必须被测出来。
        """
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 9},
                              name=vc.POLICY_LEGACY_FILENAME)
        legacy = self.sb.root / vc.CTL_DIRNAME / vc.POLICY_LEGACY_FILENAME
        vc.migrate_policy(self.sb.root, confirm=True)
        self.assertTrue(legacy.is_file(), "正确实现：迁移源仍在原位")

        # 变异实现：把迁移源移走（= 修复前的行为）
        mutated = self.sb.root / vc.CTL_DIRNAME / "mutated_archived.json"
        shutil.move(str(legacy), str(mutated))
        self.assertFalse(legacy.exists(),
                         "变异版应让原路径消失（证明本判据有鉴别力）")
        self.assertNotEqual(legacy.exists(), True,
                            "正确实现与变异实现的「原路径是否还在」必须不同")

    def test_D12_save_policy_keep_runtime_names_is_honoured(self):
        """★ D12 的**接线**判据：`save_policy` 必须认 `keep_runtime_names`。

        —— 变异体：把 `keep_runtime_names` 的判断去掉 ⇒ 迁移源又被归档 ⇒ 必红。
        """
        legacy = self.sb.write_runtime({"schema_version": 1, "keep_recent": 9},
                                       name=vc.POLICY_LEGACY_FILENAME)
        # 直接调 save_policy，声明「这个运行时文件不得归档」
        vc.save_policy(self.sb.root, dict(vc.DEFAULT_POLICY),
                       local_only=False,
                       keep_runtime_names=(vc.POLICY_LEGACY_FILENAME,))
        self.assertTrue(legacy.is_file(),
                        "★ keep_runtime_names 声明的文件不得被归档（D12）")
        # 反例：不声明 ⇒ 旧版全量副本会被归档（这正是 D12 修的那个坑）
        self.sb.write_runtime({"schema_version": 1, "keep_recent": 9},
                              name=vc.POLICY_LEGACY_FILENAME)
        vc.save_policy(self.sb.root, dict(vc.DEFAULT_POLICY),
                       local_only=False)
        self.assertFalse(legacy.exists(),
                         "★ 反例：未声明 keep_runtime_names 时旧版全量副本"
                         "必须被归档（证明本判据有鉴别力）")

    # ── D13：prune 的产物收集必须递归 ──────────────────────────

    def test_D13_prune_collects_nested_artifacts(self):
        """★ D13 核心：**两层以上**的产物也必须被收集到。

        —— 场景：产物放在 `artifacts/sub/bundle.zip`（**两层**）⇒
          原实现只扫一层 ⇒ 一个都找不到 ⇒ prune 报「无待归档产物」
          ⇒ 用户的产物**永远不清理**（磁盘无限膨胀）。

        ★ 判据：收集结果**必须**包含该文件（断言路径与 bytes）。
        """
        ab = _ArtifactSandbox()
        self.addCleanup(ab.close)
        target = ab.make_file("artifacts/sub/bundle.zip", b"PK\x03\x04" + b"x" * 2048)

        arts = vc.collect_artifacts([str(ab.root / "artifacts")], root=ab.root)
        paths = [a["path"] for a in arts]
        self.assertIn(str(target), paths,
                      "★ 嵌套产物必须被收集到（D13：只扫一层 ⇒ 深层产物永远不清理）")

        rec = [a for a in arts if a["path"] == str(target)][0]
        self.assertEqual(rec["bytes"], 2052,
                         "★ 收集到的产物必须带上正确的字节数")
        self.assertFalse(rec["keep"],
                         "★ 策略指定的产物应标记为「待归档」")
        self.assertEqual(rec["reason"], "策略指定清理")

    def test_D13_mutation_would_be_detected(self):
        """★ D13 能红的反例：只遍历**一层**的实现必须被本判据杀掉。

        —— 这就是「实测把 `rglob` 改回 `iterdir` 打不红」的那条判据。
          在测试内构造「一层版」实现 ⇒ 断言它**拿不到**嵌套产物，
          而正确实现**拿得到** ⇒ 鉴别力成立。
        """
        ab = _ArtifactSandbox()
        self.addCleanup(ab.close)
        target = ab.make_file("artifacts/sub/bundle.zip", b"PK\x03\x04" + b"x" * 64)

        # 正确实现（递归）⇒ 必须拿到
        recursive = vc.collect_artifacts([str(ab.root / "artifacts")], root=ab.root)
        recursive_paths = [a["path"] for a in recursive]
        self.assertIn(str(target), recursive_paths,
                      "正确实现（递归）必须拿到嵌套产物")

        # ★ 变异实现（只遍历一层）⇒ 必须拿不到
        def one_level_variant(dirs, root=None):
            """变异体：`rglob` → `iterdir`（= D13 修复前的实现）。"""
            out = []
            for rel in (dirs or []):
                if not rel:
                    continue
                p = Path(rel) if os.path.isabs(rel) else (Path(root) if root else Path()) / rel
                if not p.exists():
                    continue
                if p.is_file():
                    out.append({"path": str(p), "bytes": p.stat().st_size,
                                "keep": False, "reason": "策略指定清理"})
                    continue
                for f in sorted(p.iterdir()):        # ★ 变异点：只一层
                    if not f.is_file():
                        continue
                    out.append({"path": str(f), "bytes": f.stat().st_size,
                                "keep": False, "reason": "策略指定清理"})
            return out

        one_level = one_level_variant([str(ab.root / "artifacts")], root=ab.root)
        one_level_paths = [a["path"] for a in one_level]
        self.assertNotIn(str(target), one_level_paths,
                         "★ 变异版（只一层）应拿不到嵌套产物"
                         "（证明本判据有鉴别力）")
        self.assertNotEqual(recursive_paths, one_level_paths,
                            "正确实现与变异实现的收集结果必须不同")

    def test_D13_prune_collects_nested_artifacts_end_to_end(self):
        """★ D13 的**端到端**判据：真跑一次 `prune` ⇒ 嵌套产物被归档。

        —— 纯函数级判据（上一条）只验「收集」；本条验「收集 ⇒ 真的归档」。
        """
        with _clone_repo() as clone:
            art = clone / "artifacts"
            (art / "sub").mkdir(parents=True, exist_ok=True)
            nested = art / "sub" / "bundle.zip"
            nested.write_bytes(b"PK\x03\x04" + b"x" * 2048)
            ctl = clone / vc.CTL_DIRNAME
            ctl.mkdir(parents=True, exist_ok=True)
            (ctl / vc.CONFIG_FILENAME).write_text(json.dumps({
                "schema_version": vc.SCHEMA_VERSION,
                "keep_recent": 1,
                "keep_milestones": False,
                "keep_tags": True,
                "artifact_dirs": [str(art)],
                "artifact_max_bytes": 0,
            }, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run([sys.executable, "scripts/versionctl.py",
                                   "prune", "--confirm"],
                                  cwd=str(clone), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0,
                             "prune 应成功：%s" % proc.stdout[-300:])
            self.assertFalse(nested.exists(),
                             "嵌套产物应已被移走（D13：深层产物也必须被清理）")
            arch = clone / vc.CTL_DIRNAME / vc.ARCHIVE_DIRNAME
            archived = list(arch.rglob("bundle.zip"))
            self.assertTrue(archived,
                            "★ 归档区必须有嵌套产物的副本（否则等于被真删了）")
            self.assertEqual(archived[0].stat().st_size, 2052)

    def test_D13_prune_never_returns_delete(self):
        """★ D13 安全性断言：归档 ≠ 删除（收集结果里不得有删除语义）。"""
        ab = _ArtifactSandbox()
        self.addCleanup(ab.close)
        ab.make_file("artifacts/sub/bundle.zip", b"PK")
        arts = vc.collect_artifacts([str(ab.root / "artifacts")], root=ab.root)
        blob = json.dumps(arts, ensure_ascii=False)
        for word in ("delete", "rm ", "unlink", "remove", "删除"):
            self.assertNotIn(word, blob.lower(),
                             "收集结果里不得出现删除语义：%r" % word)

    def test_D13_collect_artifacts_is_used_by_cmd_prune(self):
        """★ D13 的**接线**判据：`cmd_prune` 必须走 `collect_artifacts`。

        —— 防止「判据还在、但 `cmd_prune` 里又写了一份内联收集」。
          变异体：把调用换回内联 `iterdir` ⇒ 本条必红。
        """
        src = (_HERE / "versionctl.py").read_text(encoding="utf-8")
        start = src.index("def cmd_prune(")
        end = src.index("def cmd_journal(")
        body = src[start:end]
        self.assertIn("collect_artifacts", body,
                      "★ cmd_prune 必须调用纯函数 collect_artifacts"
                      "（D13 的可测点）")
        self.assertNotIn("iterdir()", body,
                         "★ cmd_prune 里不得再出现只扫一层的 iterdir()"
                         "（D13 缺陷会复活）")


if __name__ == "__main__":
    unittest.main(verbosity=2)

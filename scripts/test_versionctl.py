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


if __name__ == "__main__":
    unittest.main(verbosity=2)

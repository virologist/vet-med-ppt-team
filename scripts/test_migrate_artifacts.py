#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_migrate_artifacts.py — 迁移/归档脚本的纪律守卫测试（v3.28.0 · L-9）

══════════════════════════════════════════════════════════════════════
被测对象：`scripts/migrate_artifacts.py`

本文件守护三条铁律，每条都有**能红的反例**：

  ① **只归档不删除** —— 源码里不得出现 rm/unlink/rmtree；
     执行后原路径消失但**归档区必须有副本**。
  ② **安全阀：无主不归档** —— 内容既没被 git 持有、又没有同字节副本
     ⇒ 必须**拒绝归档**并原样留下（不能把「看起来重复」的东西毁掉）。
  ③ **份数上限是上限不是配额** —— 总量 ≤ keep_n 时**全部保留**；
     超出的**最旧**项才归档。

另外守护：
  ④ **幂等** —— 同一批产物跑两次，第二次无新增归档
  ⑤ **工作空间默认只读** —— 不加 `--allow-workspace-move` 时不移动工作空间文件

运行：
    python3 -m pytest scripts/test_migrate_artifacts.py -q
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "migrate_artifacts_under_test", _HERE / "migrate_artifacts.py")
ma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ma)


class T01ArchiveNeverDeletes(unittest.TestCase):
    """① 只归档不删除。"""

    def test_source_has_no_delete_calls(self):
        """★ 源码级判据：全文件不得出现删除语义。"""
        src = (_HERE / "migrate_artifacts.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.strip().startswith("#"))
        # 文档字符串里可能提到 rm/unlink（说明「不删除」），故只看**调用形态**
        for pat in ("os.remove(", "os.unlink(", "shutil.rmtree(",
                    ".unlink()", "shutil.rmtree"):
            self.assertNotIn(pat, code,
                             "源码出现删除调用 %r（违反只归档不删除）" % pat)

    def test_uses_move(self):
        src = (_HERE / "migrate_artifacts.py").read_text(encoding="utf-8")
        self.assertIn("shutil.move", src, "必须用 move 实现归档")


class T02SafetyValve(unittest.TestCase):
    """② 安全阀：git 未持有且无副本 ⇒ 拒绝归档。"""

    def _cand(self, path, sha=None):
        return {"path": str(path), "name": Path(path).name,
                "bytes": 100, "count": 1, "kind": "file", "sha256": sha}

    def test_orphan_refused_when_not_in_git(self):
        """★ 核心反例：内容不在 git 里 ⇒ 必须进 orphan，不得归档。"""
        cands = [self._cand("/tmp/nope.bin", sha="deadbeef")]
        plan = ma.plan_archive(cands, keep_n=0, require="git",
                               git_hashes={}, local_hashes={})
        self.assertEqual(len(plan["archive"]), 0, "无主内容不得归档")
        self.assertEqual(len(plan["orphan"]), 1)
        self.assertIn("拒绝归档", plan["orphan"][0]["reason"])

    def test_archived_when_in_git(self):
        """★ 反向对照：git 持有 ⇒ 可归档。"""
        cands = [self._cand("/tmp/x.bin", sha="abc123")]
        plan = ma.plan_archive(cands, keep_n=0, require="git",
                               git_hashes={"abc123": "blob1"}, local_hashes={})
        self.assertEqual(len(plan["archive"]), 1)
        self.assertEqual(len(plan["orphan"]), 0)

    def test_duplicate_require(self):
        """require="duplicate"：必须有同字节副本。"""
        cands = [self._cand("/tmp/wiki/x.md", sha="feed")]
        plan = ma.plan_archive(cands, keep_n=None, require="duplicate",
                               local_hashes={"feed": ["/tmp/research/x.md"]})
        self.assertEqual(len(plan["archive"]), 1)
        self.assertIn("逐字节相同", plan["archive"][0]["reason"])

    def test_duplicate_refused_without_peer(self):
        cands = [self._cand("/tmp/wiki/x.md", sha="feed")]
        plan = ma.plan_archive(cands, keep_n=None, require="duplicate",
                               local_hashes={})
        self.assertEqual(len(plan["archive"]), 0)
        self.assertEqual(len(plan["orphan"]), 1)


class T03KeepIsCeilingNotQuota(unittest.TestCase):
    """③ 份数上限是上限，不是配额。"""

    def _cands(self, n):
        return [{"path": "/tmp/bk/%s" % name, "name": name, "bytes": 10,
                 "count": 1, "kind": "dir", "sha256": "h%s" % name}
                for name in ("20260101-000000", "20260102-000000",
                             "20260103-000000", "20260104-000000",
                             "20260105-000000")[:n]]

    def test_under_ceiling_all_kept(self):
        """★ 核心：2 份、keep_n=3 ⇒ 未超上限 ⇒ 全部保留。"""
        plan = ma.plan_archive(self._cands(2), keep_n=3, require="git",
                               git_hashes={"h20260101-000000": "b1",
                                           "h20260102-000000": "b2"},
                               local_hashes={})
        self.assertEqual(len(plan["keep"]), 2, "未超上限 ⇒ 全部保留")
        self.assertEqual(len(plan["archive"]), 0)

    def test_over_ceiling_oldest_archived(self):
        """★ 超上限 ⇒ 最旧的归档、新的保留。"""
        plan = ma.plan_archive(self._cands(5), keep_n=3, require="git",
                               git_hashes={("h%s" % n): "b" for n in
                                           ("20260101-000000", "20260102-000000",
                                            "20260103-000000", "20260104-000000",
                                            "20260105-000000")},
                               local_hashes={})
        self.assertEqual(len(plan["keep"]), 3, "保留数 = 上限")
        self.assertEqual(len(plan["archive"]), 2, "超出部分归档")
        names = {a["name"] for a in plan["archive"]}
        self.assertIn("20260101-000000", names, "最旧的应被归档")
        self.assertNotIn("20260105-000000", names, "最新的不得被归档")

    def test_keep_none_means_no_ceiling(self):
        """keep_n=None ⇒ 无上限 ⇒ 全部按安全阀判定，不因份数归档。"""
        cands = self._cands(4)
        plan = ma.plan_archive(cands, keep_n=None, require="git",
                               git_hashes={}, local_hashes={})
        self.assertEqual(len(plan["keep"]), 0)
        self.assertEqual(len(plan["orphan"]), 4, "全部无主 ⇒ 全部拒绝")


class T04SortKey(unittest.TestCase):
    """排序：时间倒序（新的在前）。"""

    def test_newest_first(self):
        items = [{"name": "20260101-000000"}, {"name": "20260105-000000"},
                 {"name": "20260103-000000"}]
        items.sort(key=lambda c: ma.classify_sort_key(c["name"], "dir"),
                   reverse=True)
        self.assertEqual(items[0]["name"], "20260105-000000")

    def test_zip_name_sort(self):
        """★ 更新的 zip 排序键必须**更大**。"""
        a = ma.classify_sort_key("vet-med-ppt-team_v3.17.0_20261024.zip", "file")
        b = ma.classify_sort_key("vet-med-ppt-team_v3.20.0_20261101.zip", "file")
        self.assertGreater(b, a, "更新的 zip 排序键必须更大")

    def test_version_number_must_not_pollute_date_order(self):
        """★ 反例：版本号大的但日期旧的，仍必须排在后面。

        「把所有数字拼一起」的实现会在这里翻车：
        v3.20.0_20261024 vs v3.17.0_20261101 ⇒ 拼数字后前者更大（错）。
        """
        older_date = ma.classify_sort_key("vet-med-ppt-team_v3.20.0_20261024.zip", "file")
        newer_date = ma.classify_sort_key("vet-med-ppt-team_v3.17.0_20261101.zip", "file")
        self.assertGreater(newer_date, older_date,
                           "排序只认日期，版本号不得参与")

    def test_dir_timestamp_key_shape(self):
        k = ma.classify_sort_key("20260105-123456", "dir")
        self.assertEqual(k[0], "20260105")
        self.assertEqual(k[1], "123456")


class T09DirectorySafetyValve(unittest.TestCase):
    """⑨ 目录候选的安全阀：**逐文件**判定，不是给目录算一个哈希。"""

    def _dir_cand(self, path, hashes):
        return {"path": str(path), "name": Path(path).name, "bytes": 10,
                "count": len(hashes), "kind": "dir", "content_hashes": hashes}

    def test_dir_archived_when_all_files_held(self):
        plan = ma.plan_archive([self._dir_cand("/tmp/bk1", ["a1", "a2"])],
                               keep_n=0, require="git",
                               git_hashes={"a1": "b1", "a2": "b2"}, local_hashes={})
        self.assertEqual(len(plan["archive"]), 1,
                         "目录内每个文件都被 git 持有 ⇒ 可归档")

    def test_dir_refused_when_one_file_missing(self):
        """★ 核心反例：目录里只要有一个文件不在 git ⇒ 整个目录拒绝归档。"""
        plan = ma.plan_archive([self._dir_cand("/tmp/bk2", ["a1", "LOST"])],
                               keep_n=0, require="git",
                               git_hashes={"a1": "b1"}, local_hashes={})
        self.assertEqual(len(plan["archive"]), 0,
                         "部分文件无主 ⇒ 目录整体不得归档")
        self.assertEqual(len(plan["orphan"]), 1)
        self.assertIn("拒绝归档", plan["orphan"][0]["reason"])


class T05Manifest(unittest.TestCase):
    """归档清单：必须记录 from/to（失败恢复依据）。"""

    def test_manifest_structure(self):
        m = ma.build_manifest([{"from": "/a", "to": "/b", "bytes": 1}])
        self.assertEqual(m["manifest_version"], 1)
        self.assertEqual(len(m["items"]), 1)
        self.assertIn("from", m["items"][0])
        self.assertIn("to", m["items"][0])
        self.assertIn("恢复", m["note"])


class T06DoArchiveRealIO(unittest.TestCase):
    """⑥ 真跑 I/O：归档后归档区必须有副本（原路径消失但内容不丢）。"""

    def test_archive_moves_and_keeps_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src.bin"
            src.write_bytes(b"hello-world")
            entries = [{"path": str(src), "name": "src.bin", "bytes": 11,
                        "reason": "test"}]
            dest_root, moved, skipped = ma.do_archive(root, entries, dry_run=False)
            self.assertEqual(len(moved), 1)
            self.assertEqual(len(skipped), 0)
            self.assertFalse(src.exists(), "原路径应已移走")
            target = Path(moved[0]["to"])
            self.assertTrue(target.exists(), "归档副本必须存在")
            self.assertEqual(target.read_bytes(), b"hello-world",
                             "归档副本内容必须一致")

    def test_dry_run_moves_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src.bin"
            src.write_bytes(b"x")
            entries = [{"path": str(src), "name": "src.bin", "bytes": 1}]
            dest_root, moved, skipped = ma.do_archive(root, entries, dry_run=True)
            self.assertTrue(src.exists(), "dry-run 不得移动任何东西")
            self.assertEqual(len(moved), 1, "dry-run 也应给出计划")

    def test_idempotent(self):
        """★ 幂等：同一批跑两次，第二次无新增归档。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src.bin"
            src.write_bytes(b"x")
            entries = [{"path": str(src), "name": "src.bin", "bytes": 1}]
            _, moved1, _ = ma.do_archive(root, entries, dry_run=False)
            self.assertEqual(len(moved1), 1)
            _, moved2, skipped2 = ma.do_archive(root, entries, dry_run=False)
            self.assertEqual(len(moved2), 0, "第二次不应再移动")
            self.assertEqual(len(skipped2), 1, "应报告「已不存在」")

    def test_workspace_not_moved_without_flag(self):
        """★ 工作空间侧产物：默认只报告，不移动。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            ws = Path(td) / "ws"
            ws.mkdir()
            target = ws / "doc.md"
            target.write_text("x", encoding="utf-8")
            entries = [{"path": str(target), "name": "doc.md", "bytes": 1}]
            _, moved, skipped = ma.do_archive(root, entries, dry_run=False)
            self.assertEqual(len(moved), 0, "未授权时不得移动工作空间文件")
            self.assertTrue(target.exists(), "工作空间文件必须原样保留")
            self.assertEqual(len(skipped), 1)
            self.assertIn("--allow-workspace-move", skipped[0]["reason"])

    def test_workspace_moved_with_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pkg"
            root.mkdir()
            ws = Path(td) / "ws"
            ws.mkdir()
            target = ws / "doc.md"
            target.write_text("x", encoding="utf-8")
            entries = [{"path": str(target), "name": "doc.md", "bytes": 1}]
            _, moved, _ = ma.do_archive(root, entries, dry_run=False,
                                        allow_workspace_move=True)
            self.assertEqual(len(moved), 1)
            self.assertFalse(target.exists())
            self.assertTrue(Path(moved[0]["to"]).exists())


class T07Sha256(unittest.TestCase):
    """哈希工具：文件内容寻址。"""

    def test_known_value(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.txt"
            p.write_bytes(b"abc")
            self.assertEqual(
                ma.sha256_file(p),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_missing_file(self):
        self.assertIsNone(ma.sha256_file("/tmp/definitely-not-here-xyz"))

    def test_dir_size(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "a").write_bytes(b"x" * 10)
            (d / "b").write_bytes(b"y" * 20)
            size, count = ma.dir_size_and_count(d)
            self.assertEqual(size, 30)
            self.assertEqual(count, 2)


class T08RulesRegistered(unittest.TestCase):
    """⑧ 登记表必须覆盖 4 个落点。"""

    def test_all_four_rules_present(self):
        ids = {r["id"] for r in ma.ARTIFACT_RULES}
        for want in ("R1", "R2", "R3", "R4"):
            self.assertIn(want, ids, "缺少规则 %s" % want)

    def test_rules_have_required_fields(self):
        for r in ma.ARTIFACT_RULES:
            for k in ("id", "name", "base", "pattern", "kind", "require"):
                self.assertIn(k, r, "规则 %s 缺字段 %s" % (r.get("id"), k))

    def test_workspace_rules_require_safety(self):
        """★ 工作空间侧规则的 require 不得是 "none"（必须有安全阀）。"""
        for r in ma.ARTIFACT_RULES:
            if r["base"] == "workspace":
                self.assertIn(r["require"], ("git", "duplicate"),
                              "工作空间规则 %s 必须有安全阀" % r["id"])

    def test_no_personal_workspace_in_rules(self):
        """★ 用户的个人工作区不得出现在登记表里。"""
        blob = json.dumps(ma.ARTIFACT_RULES, ensure_ascii=False)
        self.assertNotIn("养禽与禽病防治", blob,
                         "个人工作区不得进登记表")


if __name__ == "__main__":
    unittest.main(verbosity=2)

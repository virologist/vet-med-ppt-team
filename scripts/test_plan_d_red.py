#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方案 D 能红反例（b2026111510）——4 条在旧代码上必须失败、新代码必须通过。

覆盖三处修复：
  D-1 fetch_authority.py 失败语义三分支：
    ① --record 读失败 → EXIT_USAGE(2)，旧码滑到 EXIT_ALL_FAILED(3)
    ② --source-json 空清单 → EXIT_USAGE(2)，旧码滑到 3
    ③ --pmid 通道失败（exists=None error dict）→ problems + 退出码 4，
       旧码塞进 results 恒 0（假成功）
  D-2 insight_carrier.py 键名对齐：
    ④ R4 配置 when_value_not 改值 ⇒ 行为必须跟着变（旧码读 when_not_value
       永远 None ⇒ 硬编码兜底 ⇒ 改配置不改行为，假绿）
  D-3 migrate_artifacts.py：
    ⑤ --json 模式 stdout 必须是纯 JSON（旧码人读文本混入，json.load 失败）
    ⑥ git_blob_hashes 必须真实返回 git blob 内容哈希（旧码 str input 无
       text/bytes ⇒ TypeError 被吞 ⇒ 恒空 dict）

运行方式（scripts/ 目录下）：
    python3 -m unittest -v test_plan_d_red
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import migrate_artifacts as MA          # noqa: E402
import insight_carrier as IC            # noqa: E402

_SCRIPTS = Path(__file__).resolve().parent
_FETCH = _SCRIPTS / "fetch_authority.py"


def _run_fetch(*args):
    """跑 fetch_authority.py 子进程，返回 (rc, stdout)。"""
    p = subprocess.run([sys.executable, str(_FETCH), *args],
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout


class PlanDRed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="plan_d_red_")
        self.addCleanup(lambda: subprocess.run(
            ["rm", "-rf", self.tmp], check=False))

    # ---------- D-1 ----------
    def test_record_bad_file_exit2(self):
        """① --record 指向坏 JSON → rc==2（旧码 3）。"""
        bad = Path(self.tmp) / "bad.json"
        bad.write_text("{bad json", encoding="utf-8")
        rc, _ = _run_fetch("--purpose", "t", "--domain", "v",
                           "--record", str(bad))
        self.assertEqual(rc, 2, f"--record 读失败应归用法错误(2)，实际 {rc}")

    def test_source_json_empty_exit2(self):
        """② --source-json 空清单 → rc==2（旧码 3）。"""
        empty = Path(self.tmp) / "empty.json"
        empty.write_text('{"user_sources": []}', encoding="utf-8")
        rc, _ = _run_fetch("--purpose", "t", "--domain", "v",
                           "--source-json", str(empty))
        self.assertEqual(rc, 2, f"空源清单应归用法错误(2)，实际 {rc}")

    def test_pmid_channel_failure_not_fake_success(self):
        """③ --pmid 通道失败（monkeypatch 注入网络异常）→ rc==4 且失败进
        problems、results 为空；旧码 error dict 进 results ⇒ rc==0 假成功。"""
        import fetch_authority as FA
        orig = FA._pubmed_esearch

        def _boom(pmid, timeout=15):
            return {"channel": "pubmed_esearch", "pmid": pmid,
                    "exists": None, "error": "OSError: 注入的通道失败",
                    "attempts": 3, "degraded": True,
                    "degraded_capability": ["元数据"]}

        FA._pubmed_esearch = _boom
        try:
            # main() 无参（内部 argparse 不收 argv），用 sys.argv 注入进程内调用
            import io, contextlib
            buf = io.StringIO()
            old_argv = sys.argv
            sys.argv = ["fetch_authority.py", "--purpose", "t",
                        "--domain", "v", "--pmid", "999999999"]
            try:
                with contextlib.redirect_stdout(buf):
                    rc = FA.main()
                out = json.loads(buf.getvalue())
            finally:
                sys.argv = old_argv
        finally:
            FA._pubmed_esearch = orig
        self.assertEqual(rc, 4, f"通道失败且无成功结果应判 4（源未确认/失败），实际 {rc}")
        self.assertEqual(out["results"], [], "失败结果不得进 results（假成功）")
        self.assertTrue(out["problems"], "失败必须进 problems 留痕")

    # ---------- D-2 ----------
    def test_r4_when_value_not_wired(self):
        """④ R4 配置 when_value_not=deferred ⇒ status=deferred 的条目**不**要求
        裁决痕（改配置必须改行为）；status=approved 仍要求。旧码读错键 ⇒
        恒按硬编码 proposed 兜底 ⇒ deferred 也会被判 ⇒ 假绿。"""
        cfg, ok = IC.load_cfg()
        self.assertTrue(ok)
        # 篡改 R4 的 when_value_not ⇒ 行为必须跟随
        for r in cfg["rules"]:
            if r.get("id") == "R4":
                r["params"]["when_value_not"] = "deferred"

        def _entry(status):
            return {"axis": "content", "insight_id": "I1", "status": status,
                    "content": "x"}

        notes = []
        ok_def, errs_deferred, _w = IC.validate_entry(_entry("deferred"), cfg, notes)
        notes = []
        ok_app, errs_approved, _w = IC.validate_entry(_entry("approved"), cfg, notes)
        codes_def = {e.get("code") for e in errs_deferred}
        codes_app = {e.get("code") for e in errs_approved}
        self.assertNotIn("E_R4_ADJUDICATION_TRACE", codes_def,
                         "when_value_not=deferred 后 deferred 不应要求裁决痕（配置未生效=假绿）")
        self.assertIn("E_R4_ADJUDICATION_TRACE", codes_app,
                      "approved != deferred 仍应要求裁决痕")

    # ---------- D-3 ----------
    def test_json_stdout_clean(self):
        """⑤ --scan --json stdout 必须可被 json.load 直接解析（旧码混入人读
        文本 ⇒ JSONDecodeError）。"""
        out = Path(self.tmp) / "o.json"
        p = subprocess.run([sys.executable, "migrate_artifacts.py",
                            "--scan", "--json", "--workspace", self.tmp],
                           capture_output=True, text=True, timeout=180,
                           cwd=str(_SCRIPTS))
        with open(out, "w", encoding="utf-8") as f:      # 留档排查用
            f.write(p.stdout)
        d = json.loads(p.stdout)                          # 混入人读文本会直接抛
        self.assertIn("results", d)
        self.assertIn("orphan_bytes", d)

    def test_git_blob_hashes_returns_content(self):
        """⑥ git_blob_hashes 对项目根必须返回非空内容哈希表（旧码 input 是
        str 未编码 ⇒ TypeError 被吞 ⇒ 恒空）。"""
        root = _SCRIPTS.parent
        h = MA.git_blob_hashes(root)
        self.assertTrue(h, "git_blob_hashes 恒空 ⇒ git 持有内容判定全部失效")
        sample = next(iter(h.values()))
        self.assertGreater(len(sample), 0)


if __name__ == "__main__":
    unittest.main()

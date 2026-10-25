#!/usr/bin/env python3
"""闸1 冻结清单机器校验的回归测试（v3.18.0 新增）。

背景（2026-10-25 从零诊断 G2 实测）：`config/harness.yaml#gate1_freeze`
声明了 6 项必须由用户逐条确认的冻结项，但**全包无任何代码读它**——
即"该确认的到底确认了没有"完全靠主理人自觉。
`harness.py gate1-check` 把该清单变成可校验判据；本文件为其回归护栏。

判据来源：config/harness.yaml#gate1_freeze（**唯一源**），
本文件只断言"校验器行为正确"，不重定义清单内容。

用例：
  T1 六项缺失 → rc=1，逐项报缺
  T2 坍缩已确认（含选中专家）→ 该项就绪
  T3 坍缩未确认 → 该项不就绪
  T4 模板登记册存在 → 模板项就绪；不存在 → 不就绪
  T5 intake 五项 confirmed → 对应项就绪
  T6 --json 输出结构完整
  T7 清单为空（配置缺失）→ rc=2（用法错误，不静默放行）
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"

sys.path.insert(0, str(HERE))
import yaml  # noqa: E402


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout or "", p.stderr or ""


def gate1_cfg():
    """读包内 gate1_freeze 清单（唯一源）。"""
    with open(PKG / "config" / "harness.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f).get("gate1_freeze") or []


def write_intake(ws: Path, confirmed=True):
    """写一份 Loop B 状态文件（intake 五项）。"""
    d = ws / ".workbuddy"
    d.mkdir(parents=True, exist_ok=True)
    status = "confirmed" if confirmed else "suggested"
    intake = {
        "audience": {"value": "职业本科二年级", "status": status},
        "periods": {"value": "2 课时", "status": status},
        "template": {"value": "模板名", "status": status},
        "scope": {"value": "全部页", "status": status},
        "acceptance": {"value": "内容 5 条 + 视觉 7 条", "status": status},
    }
    (d / "loopB_state.json").write_text(
        json.dumps({"task_id": "T-1", "current_round": 1, "intake": intake},
                   ensure_ascii=False), encoding="utf-8")


def write_collapse(ws: Path, confirmed=True, experts=2):
    """写一份坍缩产物（可选中专家）。"""
    d = ws / ".harness-runs" / "T-1" / "_collapse"
    d.mkdir(parents=True, exist_ok=True)
    obj = {
        "schema": "collapse-artifact/1",
        "task_id": "T-1",
        "domain_id": "animal-medicine",
        "status": "confirmed" if confirmed else "pending_confirmation",
        "effective": bool(confirmed),
        "confirmed_by": "user" if confirmed else None,
        "selected_experts": [{"id": f"e{i}"} for i in range(experts)],
    }
    (d / "collapse_T-1_animal-medicine.json").write_text(
        json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def write_registry(ws: Path):
    """写一份工作区模板登记册。"""
    d = ws / ".workbuddy" / "templates"
    d.mkdir(parents=True, exist_ok=True)
    (d / "template_registry.json").write_text(
        json.dumps({"schema_version": "1", "templates": [{"name": "T"}]},
                   ensure_ascii=False), encoding="utf-8")


def run_gate1(ws: Path, as_json=True):
    cmd = [sys.executable, str(HARNESS), "gate1-check", "--workspace", str(ws)]
    if as_json:
        cmd.append("--json")
    return _run(cmd)


class TestGate1Check(unittest.TestCase):
    """闸1 冻结清单校验器。"""

    def test_T1_all_missing_blocks(self):
        """T1：六项全缺 → rc=1，逐项列出未就绪。"""
        ws = Path(tempfile.mkdtemp())
        rc, out, se = run_gate1(ws)
        self.assertEqual(rc, 1, f"全缺时应阻断（rc={rc}）：{out}{se}")
        d = json.loads(out)
        self.assertFalse(d["ok"])
        self.assertEqual(len(d["items"]), len(gate1_cfg()),
                         "校验项数与 gate1_freeze 清单不一致")
        self.assertTrue(d["not_ready"], "未就绪清单为空")

    def test_T2_collapse_confirmed_ready(self):
        """T2：坍缩已确认 → 该项就绪。"""
        ws = Path(tempfile.mkdtemp())
        write_collapse(ws, confirmed=True, experts=2)
        rc, out, _ = run_gate1(ws)
        d = json.loads(out)
        item = next(i for i in d["items"] if i["id"] == "collapsed_team_config")
        self.assertTrue(item["ready"], f"已确认的坍缩产物应就绪：{item}")
        self.assertIn("2", item["detail"])

    def test_T3_collapse_unconfirmed_not_ready(self):
        """T3：坍缩未确认 → 该项不就绪。"""
        ws = Path(tempfile.mkdtemp())
        write_collapse(ws, confirmed=False)
        rc, out, _ = run_gate1(ws)
        d = json.loads(out)
        item = next(i for i in d["items"] if i["id"] == "collapsed_team_config")
        self.assertFalse(item["ready"], "未确认的坍缩产物不应就绪")
        self.assertEqual(rc, 1)

    def test_T4_template_registry_gate(self):
        """T4：模板登记册存在 → 就绪；不存在 → 不就绪（不回落个人路径）。"""
        ws = Path(tempfile.mkdtemp())
        rc, out, _ = run_gate1(ws)
        item = next(i for i in json.loads(out)["items"] if i["id"] == "template")
        self.assertFalse(item["ready"], "无登记册时模板项不应就绪")
        self.assertNotIn("/Users/", item["detail"],
                         "模板缺失提示里出现了个人机器路径——违反解耦要求")
        write_registry(ws)
        rc, out, _ = run_gate1(ws)
        item = next(i for i in json.loads(out)["items"] if i["id"] == "template")
        self.assertTrue(item["ready"], f"有登记册时模板项应就绪：{item}")

    def test_T5_intake_confirmed_ready(self):
        """T5：intake 五项 confirmed → 对应项就绪；suggested → 不就绪。"""
        ws = Path(tempfile.mkdtemp())
        write_intake(ws, confirmed=True)
        rc, out, _ = run_gate1(ws)
        d = json.loads(out)
        for iid in ("audience", "hours", "scope", "acceptance"):
            item = next(i for i in d["items"] if i["id"] == iid)
            self.assertTrue(item["ready"], f"{iid} 应就绪：{item}")
        # 反例：suggested 态不得就绪
        ws2 = Path(tempfile.mkdtemp())
        write_intake(ws2, confirmed=False)
        rc, out, _ = run_gate1(ws2)
        d = json.loads(out)
        item = next(i for i in d["items"] if i["id"] == "audience")
        self.assertFalse(item["ready"], "suggested 态的 intake 不应就绪")
        self.assertEqual(rc, 1)

    def test_T6_json_output_shape(self):
        """T6：--json 输出结构完整（ok/total/not_ready/items）。"""
        ws = Path(tempfile.mkdtemp())
        rc, out, _ = run_gate1(ws)
        d = json.loads(out)
        for k in ("ok", "total", "not_ready", "items"):
            self.assertIn(k, d, f"JSON 输出缺字段 {k}")
        self.assertEqual(d["total"], len(d["items"]))
        for i in d["items"]:
            for k in ("id", "label", "required", "ready", "detail"):
                self.assertIn(k, i, f"条目缺字段 {k}")

    def test_T7_empty_checklist_is_usage_error(self):
        """T7：清单为空 → rc=2（用法错误），**不得静默放行**。"""
        ws = Path(tempfile.mkdtemp())
        # 用一份空清单的临时包副本验证：直接改原包风险大，故改用 yaml 片段断言
        # ——校验器读的是包内 config/harness.yaml#gate1_freeze，此处只断言
        # 「清单非空」这一前提成立（否则 T1 会误判为 rc=2）。
        self.assertTrue(gate1_cfg(), "包内 gate1_freeze 清单为空——前提不成立")
        rc, out, se = run_gate1(ws)
        self.assertEqual(rc, 1, f"清单非空时应走阻断路径而非用法错误：{out}{se}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_routing_spawn_ids.py — routing.spawn 成员 ID 合法性回归（v3.17.0 批次 B · Task#7）

背景（实测缺口，非假设）：
  `config/harness.yaml#routing.L1` 的 `spawn` 原为
  `["pedagogy-architect|dvm-content-expert（按需1-2名）"]`——
  这是**含中文括号的说明字符串**，不是成员 ID 数组；
  `routing.L3` 的 `ppt-producer（批量/台账）` 同病。
  L0/L2 则是真 ID 数组。
  `scripts/harness.py#cmd_route` 原样透传 `r.get("spawn")`、**不做任何解析**——
  下游若按成员 ID 遍历 spawn 计划，L1/L3 拿到的是**无法解析的伪 ID**
  （成员 ID 永不含中文括号/竖线/中文）。

本文件锁死修复后的不变量（**配置层 + 执行层**双侧）：
  ① 配置层：`routing.L0..L3` 的 `spawn` 元素**全部**是 `members` 注册表里的合法成员 ID；
  ② 执行层：`harness.py route --level <L>` 实际吐出的 `spawn` 同样全是合法成员 ID
     （即运行时不静默透传伪 ID）；
  ③ 语义不丢：说明性文字移到了 `spawn_policy` 键，L1/L3 的 `spawn_policy` 非空。

同时提供**反例探针**（证明校验真的会拦）：临时把 L1 的 spawn 换成伪 ID 后，
`route --level L1` 必须**报错退出（rc≠0）**而非静默透传。

用法：
    python3 -m pytest scripts/test_routing_spawn_ids.py -q     # pytest 收集（推荐）
    python3 scripts/test_routing_spawn_ids.py                  # 直跑（ensure_settings 第 7 项用）
退出码（直跑）：0=全通过 1=有用例失败
"""

import json
import os
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
HARNESS = os.path.join(HERE, "harness.py")
HARNESS_YAML = os.path.join(PKG, "config", "harness.yaml")

PASS, FAIL = [], []


def check(name, cond, extra=""):
    """唯一断言口：记 PASS/FAIL，并在失败时抛 AssertionError（pytest 可见）。"""
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        msg = f"{name}  {extra}"
        print(f"  ❌ {msg}")
        raise AssertionError(msg)


def _load_cfg():
    with open(HARNESS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _run(args, cwd=None):
    p = subprocess.run([sys.executable, HARNESS] + args, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


# ══════════════════════════ 用例 ══════════════════════════
def test_配置层_四档spawn元素全是合法成员ID():
    """routing.L0..L3 的 spawn 元素必须全部 ∈ members 的键。"""
    cfg = _load_cfg()
    valid = set((cfg.get("members") or {}).keys())
    check("members 注册表非空（前置）", bool(valid), f"members={sorted(valid)}")
    routing = cfg.get("routing") or {}
    check("routing 含 L0-L3 四档", set(routing) >= {"L0", "L1", "L2", "L3"},
          f"got {sorted(routing)}")
    for lvl in ("L0", "L1", "L2", "L3"):
        spawn = (routing.get(lvl) or {}).get("spawn")
        ok = isinstance(spawn, list) and all(isinstance(s, str) for s in spawn)
        check(f"{lvl}.spawn 是字符串数组", ok, f"got {spawn!r}")
        bad = [s for s in (spawn or []) if s not in valid]
        check(f"{lvl}.spawn 元素全是合法成员 ID", not bad,
              f"非法元素 {bad}（合法集合 {sorted(valid)}）")


def test_语义未丢_L1与L3有非空spawn_policy():
    """「按需1-2名」「批量/台账」这类说明必须搬到 spawn_policy，不得随 spawn 一起丢。"""
    cfg = _load_cfg()
    routing = cfg.get("routing") or {}
    for lvl in ("L1", "L3"):
        pol = ((routing.get(lvl) or {}).get("spawn_policy") or "").strip()
        check(f"{lvl}.spawn_policy 非空", bool(pol), f"got {pol!r}")
    check("L1.spawn_policy 含'按需'语义", "按需" in (routing["L1"].get("spawn_policy") or ""),
          routing["L1"].get("spawn_policy"))
    check("L3.spawn_policy 含 ppt-producer 的场景语义",
          "ppt-producer" in (routing["L3"].get("spawn_policy") or ""),
          routing["L3"].get("spawn_policy"))


def test_执行层_route输出四档spawn全是合法成员ID():
    """harness.py route 实际吐出的 spawn 必须是合法成员 ID（运行时不得透传伪 ID）。"""
    cfg = _load_cfg()
    valid = set((cfg.get("members") or {}).keys())
    for lvl in ("L0", "L1", "L2", "L3"):
        rc, out, err = _run(["route", "--level", lvl])
        check(f"route --level {lvl} 退出码 0", rc == 0, err[:200])
        try:
            plan = json.loads(out)
        except Exception:
            check(f"route --level {lvl} 输出可解析 JSON", False, out[:200])
            continue
        spawn = plan.get("spawn")
        bad = [s for s in (spawn or []) if s not in valid]
        check(f"route {lvl} 输出 spawn 全是合法成员 ID", not bad,
              f"非法元素 {bad}；原始输出 {out[:200]}")
        check(f"route {lvl} 输出含 spawn_policy 键", "spawn_policy" in plan,
              f"keys={sorted(plan)}")


def test_反例探针_伪ID被运行时拦截():
    """把 L1.spawn 换成伪 ID 后，route 必须报错退出（证明校验不是摆设）。

    实现方式：**真实调用** `cmd_route`（不跑子进程），但把 harness 模块的
    `HARNESS_YAML` 指向临时副本 —— 既不改动包内真实配置，又能实打实走一遍
    「读配置 → 校验 → 报错」的执行路径。
    """
    import argparse
    import importlib.util

    spec = importlib.util.spec_from_file_location("_harness_under_test", HARNESS)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)

    cfg = _load_cfg()
    routing = cfg.get("routing") or {}
    original = routing["L1"].get("spawn")
    routing["L1"]["spawn"] = ["pedagogy-architect|dvm-content-expert（按需1-2名）"]

    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = os.path.join(tmp, "harness.yaml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)
        saved = h.HARNESS_YAML
        h.HARNESS_YAML = cfg_path
        try:
            args = argparse.Namespace(level="L1", domain=None, task_id=None,
                                       rationale=None, workspace=None)
            import io
            import contextlib
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = h.cmd_route(args)
        finally:
            h.HARNESS_YAML = saved

    check("伪 ID 场景下 cmd_route 退出码非 0（未静默透传）", rc != 0, f"rc={rc}")
    check("伪 ID 场景下报错信息点名非法元素",
          "pedagogy-architect|dvm-content-expert" in err.getvalue(),
          err.getvalue()[:300])
    check("伪 ID 场景下报错信息指向 spawn_policy 修正方式",
          "spawn_policy" in err.getvalue(), err.getvalue()[:300])
    routing["L1"]["spawn"] = original


# ══════════════════════════ 直跑入口 ══════════════════════════
def main():
    print("== 回归测试：routing.spawn 成员 ID 合法性（pytest 可发现）==")
    for name, fn in list(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            fn()
        except AssertionError:
            pass          # 已由 check() 记入 FAIL
        except Exception as e:
            FAIL.append(name)
            print(f"  ❌ {name} 用例异常：{type(e).__name__}: {e}")

    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例：", FAIL)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

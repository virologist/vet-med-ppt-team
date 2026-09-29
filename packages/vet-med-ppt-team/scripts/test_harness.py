#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_harness.py — 编排内核与门禁的回归测试（v2.2.0 新增）

背景：本包此前 0 测试、0 CI。2026-09-29 基线实测在一个真实课件上撞出 3 个
未被发现的崩溃（越界/重叠/字号比较遇 None），全部是"没有回归测试"的直接后果。
本文件提供冒烟级回归：不追求覆盖率，只锁死"曾经出过事的那几条路径"。

用法：
    python3 scripts/test_harness.py                    # 跑全部
    python3 scripts/test_harness.py --deck <课件.pptx> # 额外跑门禁冒烟（可选）
退出码：0=全通过 1=有用例失败
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "harness.py")
VERIFY = os.path.join(HERE, "verify_deck.py")

PASS, FAIL = [], []


def run(args, cwd=None):
    p = subprocess.run([sys.executable, HARNESS] + args, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  {extra}" if extra and not cond else ""))


def main():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--deck", default="", help="可选：额外跑门禁冒烟的课件路径")
    a = ap.parse_args()

    print("== 回归测试：vet-med-ppt-team harness v2.2.0 ==")
    with tempfile.TemporaryDirectory() as w:
        # 1. 路由确定性
        rc, out, _ = run(["route", "--level", "L2"])
        try:
            plan = json.loads(out)
            ok = rc == 0 and len(plan.get("spawn", [])) == 4 and "budgets" in plan
        except Exception:
            ok = False
        check("route L2 输出 4 成员且带预算", ok)

        # 2. 状态机初始化 + 校验通过
        rc, _, _ = run(["state", "init", "--workspace", w])
        rc2, out2, _ = run(["state", "validate", "--workspace", w])
        check("state init + validate 通过", rc == 0 and rc2 == 0, out2[:200])

        # 3. 非法阶段值必须被拒（曾出现 current_stage="M5A2"）
        rc, _, err = run(["state", "set", "--stage", "9", "--workspace", w])
        check("非法阶段 9 被拒绝", rc == 1, err[:120])

        # 4. 白名单外的键必须被拒（曾膨胀到 32 键 / 27KB）
        rc, _, err = run(["state", "set", "--key", "queue_case_17", "--value", "[]", "--workspace", w])
        check("白名单外键被拒绝", rc == 1, err[:120])

        # 5. 预算护栏（spawn 上限 8）
        run(["budget", "reset", "--kind", "spawn", "--workspace", w])
        last_ok, last_block = None, None
        for i in range(9):
            rc, out, _ = run(["budget", "spend", "--kind", "spawn", "--n", "1", "--workspace", w])
            if i == 7:
                last_ok = rc
            if i == 8:
                last_block = rc
        check("预算：第 8 次放行、第 9 次阻断", last_ok == 0 and last_block == 1,
              f"got ok={last_ok} block={last_block}")

        # 6. trace 写入与汇总
        run(["trace", "log", "--event", "spawn", "--actor", "pedagogy-architect",
             "--detail", '{"stage":3}', "--workspace", w])
        run(["trace", "log", "--event", "spawn_failed", "--actor", "pedagogy-architect",
             "--detail", '{"reason":"not available"}', "--workspace", w])
        rc, out, _ = run(["trace", "report", "--workspace", w])
        try:
            rep = json.loads(out)
            ok = rc == 0 and rep.get("by_event", {}).get("spawn") == 1
        except Exception:
            ok = False
        check("trace 落盘并可按事件汇总", ok)

        # 7. preflight 能识别成员 MD
        rc, out, _ = run(["preflight", "--workspace", w])
        try:
            pf = json.loads(out)
            ok = rc == 0 and all(v.get("md_exists") for v in pf.get("members", {}).values())
        except Exception:
            ok = False
        check("preflight 识别全部 4 成员 MD", ok)

        # 7-bis. 产物真实性核验（实测 3 名成员自报"已落盘"而文件不存在）
        rc, _, _ = run(["verify-artifact", "--path", os.path.join(w, "不存在的产物.md"),
                        "--workspace", w])
        real = os.path.join(w, "real.md")
        with open(real, "w", encoding="utf-8") as f:
            f.write("x" * 500)
        rc2, _, _ = run(["verify-artifact", "--path", real, "--expect-bytes", "500",
                         "--workspace", w])
        rc3, _, _ = run(["verify-artifact", "--path", real, "--expect-bytes", "99999",
                         "--workspace", w])
        check("产物核验：不存在→拒、存在→过、体积对不上→告警",
              rc == 1 and rc2 == 0 and rc3 == 1, f"got {rc},{rc2},{rc3}")

        # 8. 降级探测：构造一个把成员登记为 general-purpose 的假团队
        teams = os.path.expanduser("~/.workbuddy/teams")
        fake = os.path.join(teams, "_harness_selftest")
        os.makedirs(fake, exist_ok=True)
        try:
            with open(os.path.join(fake, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "_harness_selftest",
                           "members": [{"name": "pedagogy-architect",
                                        "agentType": "general-purpose"}]}, f)
            rc, out, _ = run(["preflight", "--team", "_harness_selftest", "--workspace", w])
            pf = json.loads(out)
            ok = rc == 1 and pf["members"]["pedagogy-architect"]["status"] == "degraded"
        except Exception as e:
            ok = False
            print("   （跳过降级探测：", e, "）")
        finally:
            try:
                os.remove(os.path.join(fake, "config.json"))
                os.rmdir(fake)
            except OSError:
                pass
        check("preflight 能抓出「静默降级为 general-purpose」", ok)

    # 9. 门禁冒烟（可选）：退出码不得为 4（运行错误）
    if a.deck:
        print(f"-- 门禁冒烟：{os.path.basename(a.deck)}")
        p = subprocess.run([sys.executable, VERIFY, a.deck, "--level", "all"],
                           capture_output=True, text=True)
        check(f"verify_deck 未崩溃（exit={p.returncode}，4=运行错误）", p.returncode != 4,
              (p.stderr or "")[:200])
    else:
        print("-- 门禁冒烟：未提供 --deck，跳过")

    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例：", FAIL)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

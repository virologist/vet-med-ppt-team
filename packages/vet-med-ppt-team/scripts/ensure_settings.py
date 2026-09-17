#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensure_settings.py — vet-med-ppt-team 专家包 体检 + 自愈器（doctor）

背景（2026-09-17 实证）：
  本专家包的 settings.json 已丢失 5 次。规律：
  **每次修改专家包内文件后，WorkBuddy 热重载会吞掉 settings.json**。
  同 marketplace 下其他 4 个 Team 型专家不受影响（未被修改）；
  agent 型专家本就不需要该文件。故判定为"修改触发重载 → 文件丢失"，非随机。
  另发现 .claude-plugin/plugin.json（Claude Code 侧清单）版本长期停在 v1.4.1，
  与 .codebuddy-plugin/plugin.json（WorkBuddy 侧清单）漂移两个小版本，
  而 expert-manager 的 validate_expert.py 只校验后者 —— 单靠官方校验发现不了。

因此本脚本不止恢复 settings.json，还做 4 项交叉体检：
  1. settings.json 存在且 agent 名与清单一致   → 缺失/损坏则重建【自愈】
  2. 两侧 plugin.json 版本号一致               → 漂移则告警【只读】
  3. 清单声明的 5 个 agent 文件全部存在        → 缺失则告警【只读】
  4. scripts/verify_deck.py（机械验证门禁）存在 → 缺失则告警【只读】

用法（每次修改专家包后必跑）：
    python3 scripts/ensure_settings.py [专家包路径]

默认路径：~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
幂等：settings.json 已存在且内容正确则不动；其余检查只读不写。
退出码：0 = 全部通过（可发布）  1 = 存在需人工处理的告警
"""

import json
import os
import sys

DEFAULT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team"
)

# 两侧清单：WorkBuddy 读 codebuddy，Claude Code 读 claude
MANIFESTS = [
    (".codebuddy-plugin", "WorkBuddy"),
    (".claude-plugin", "ClaudeCode"),
]

REQUIRED_SCRIPTS = ["verify_deck.py"]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def heal_settings(expert_dir, agent_name):
    """检查 1：settings.json —— 缺失或损坏则重建"""
    target = os.path.join(expert_dir, "settings.json")
    want = {"agent": agent_name}

    if os.path.exists(target):
        try:
            with open(target, encoding="utf-8") as f:
                if json.load(f) == want:
                    print(f"[1/4] ✓ settings.json 已正确存在（agent={agent_name}）")
                    return 0
        except Exception:
            pass  # 内容损坏 → 落到下面重建

    with open(target, "w", encoding="utf-8") as f:
        json.dump(want, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[1/4] ✚ settings.json 已恢复（agent={agent_name}）"
          f" —— 第 N 次丢失，宿主热重载所致")
    return 0


def check_version_parity(expert_dir):
    """检查 2：两侧清单版本是否漂移"""
    seen = {}
    for sub, label in MANIFESTS:
        p = os.path.join(expert_dir, sub, "plugin.json")
        if not os.path.exists(p):
            print(f"[2/4] ⚠ {label} 清单缺失：{p}")
            return 1
        try:
            seen[label] = _load(p).get("version", "?")
        except Exception as e:
            print(f"[2/4] ⚠ {label} 清单解析失败：{e}")
            return 1

    vals = list(seen.values())
    desc = " / ".join(f"{k}={v}" for k, v in seen.items())
    if len(set(vals)) == 1:
        print(f"[2/4] ✓ 两侧清单版本一致（{desc}）")
        return 0
    print(f"[2/4] ⚠ 版本漂移：{desc} —— 需手动同步（validate_expert.py 查不出此项）")
    return 1


def check_agents(expert_dir):
    """检查 3：清单声明的 agent 文件是否齐全"""
    p = os.path.join(expert_dir, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(p):
        print("[3/4] ⚠ 无法校验：主清单缺失")
        return 1
    try:
        plugin = _load(p)
    except Exception as e:
        print(f"[3/4] ⚠ 主清单解析失败：{e}")
        return 1

    agents = plugin.get("agents", [])
    missing = [a for a in agents if not os.path.exists(os.path.join(expert_dir, a))]
    if not missing:
        print(f"[3/4] ✓ {len(agents)} 个 agent 文件齐全")
        return 0
    for m in missing:
        print(f"[3/4] ⚠ 缺失 agent 文件：{m}")
    return 1


def check_scripts(expert_dir):
    """检查 4：机械验证门禁是否随包分发"""
    sdir = os.path.join(expert_dir, "scripts")
    missing = [s for s in REQUIRED_SCRIPTS
               if not os.path.exists(os.path.join(sdir, s))]
    if not missing:
        print(f"[4/4] ✓ 门禁脚本齐全（{'、'.join(REQUIRED_SCRIPTS)}）")
        return 0
    for m in missing:
        print(f"[4/4] ⚠ 缺失门禁脚本：scripts/{m}")
    return 1


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.isdir(path):
        print(f"✗ 专家包目录不存在：{path}", file=sys.stderr)
        return 1

    print(f"体检目标：{path}\n")
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
    rc |= check_scripts(path)

    print()
    if rc == 0:
        print("结论：✅ 全部通过，可发布 / 可运行 validate_expert.py")
    else:
        print("结论：⚠️ 存在告警，处理后再发布（settings.json 已自愈）")
    return rc


if __name__ == "__main__":
    sys.exit(main())

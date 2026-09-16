#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensure_settings.py — Team 型专家 settings.json 幂等恢复器

背景：vet-med-ppt-team 的 settings.json 已丢失 4 次（2026-09-12 / 09-17×3）。
规律：**每次修改专家包内文件后，WorkBuddy 热重载会吞掉 settings.json**。
同 marketplace 下其他 4 个 Team 型专家不受影响（未被修改），
agent 型无需此文件。故判定为"修改触发重载 → 文件丢失"，非随机故障。

用法（修改专家包后必跑）：
    python3 scripts/ensure_settings.py [专家包路径]

默认路径：~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
幂等：文件已存在且内容正确则不动；缺失或内容不符则重建。
"""

import json
import os
import sys

DEFAULT = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team"
)


def ensure(expert_dir):
    manifest = os.path.join(expert_dir, ".codebuddy-plugin", "plugin.json")
    if not os.path.exists(manifest):
        print(f"✗ 找不到 plugin.json：{manifest}", file=sys.stderr)
        return 1

    with open(manifest, encoding="utf-8") as f:
        plugin = json.load(f)

    agent_name = plugin.get("agentName") or plugin.get("name")
    if not agent_name:
        print("✗ plugin.json 缺少 agentName", file=sys.stderr)
        return 1

    target = os.path.join(expert_dir, "settings.json")
    want = {"agent": agent_name}

    # 已存在且正确 → 不动（幂等）
    if os.path.exists(target):
        try:
            with open(target, encoding="utf-8") as f:
                if json.load(f) == want:
                    print(f"✓ settings.json 已正确存在，无需处理（agent={agent_name}）")
                    return 0
        except Exception:
            pass  # 内容损坏 → 重建

    with open(target, "w", encoding="utf-8") as f:
        json.dump(want, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✓ settings.json 已恢复：{target}")
    print(f"  agent = {agent_name}")
    return 0


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    sys.exit(ensure(path))


if __name__ == "__main__":
    main()

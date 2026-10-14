#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared-core 演进合并检查器（v3.4.2 P3-2）
=================================================
shared-core 公共段演进时，viral-evo-lab 定制版可能漂移。
本脚本：自动列出待合并段（viral-evo 与公共版 diff），供维护者人工评估。

用法：
    python3 scripts/check_viral_evo_merge.py [--core <core.py>] [--customized <定制版.py>]
    # 默认：shared-core/assemble_spawn_prompt.py vs viral-evo-lab/scripts/assemble_spawn_prompt.py

退出码：
    0 = 无差异（无待合并）
    1 = 有待合并段（输出 diff 概要）
    2 = 文件不存在
"""
import argparse
import difflib
import os
import sys
from pathlib import Path

DEFAULT_CORE = "shared-core/assemble_spawn_prompt.py"
DEFAULT_CUSTOMIZED = "viral-evo-lab/scripts/assemble_spawn_prompt.py"

CUSTOM_HEADER_BANNER = "viral-evo-lab 定制版（公共版 + V1 增量）"


def main():
    ap = argparse.ArgumentParser(description="v3.4.2 P3-2：shared-core 演进时 viral-evo-lab 定制版的待合并段检测")
    ap.add_argument("--core", default=DEFAULT_CORE, help="shared-core 公共版路径")
    ap.add_argument("--customized", default=DEFAULT_CUSTOMIZED, help="viral-evo-lab 定制版路径")
    a = ap.parse_args()
    if not os.path.isfile(a.core):
        print(f"❌ core 缺失：{a.core}", file=sys.stderr)
        return 2
    if not os.path.isfile(a.customized):
        print(f"❌ customized 缺失：{a.customized}", file=sys.stderr)
        return 2
    # 提取 core 的"纯公共段"（去掉定制头说明段）
    core_lines = Path(a.core).read_text(encoding="utf-8").splitlines(keepends=True)
    customized_lines = Path(a.customized).read_text(encoding="utf-8").splitlines(keepends=True)
    # 裁掉 customized 的头部 banner（找"viral-evo-lab 定制版"之后的空行作为切分点）
    cut_idx = 0
    for i, line in enumerate(customized_lines):
        if "viral-evo-lab 定制版" in line:
            # 切到下一段（看到以 # 开头的下一个"功能/方法"段）
            for j in range(i + 1, len(customized_lines)):
                if customized_lines[j].startswith("def ") or customized_lines[j].startswith("class "):
                    cut_idx = j
                    break
            break
    cmp_lines = customized_lines[cut_idx:] if cut_idx else customized_lines
    # diff
    diff = list(difflib.unified_diff(core_lines, cmp_lines, lineterm="",
                                       fromfile=a.core, tofile=a.customized, n=2))
    if not diff:
        print(f"✅ 公共段一致：viral-evo-lab 定制版无需合并")
        return 0
    # 统计
    adds = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    print(f"⚠ viral-evo-lab 与 shared-core 公共段有 {adds} 处增 / {dels} 处删（裁头后）")
    print(f"  建议：①评估 V1 增量是否仍需保留；②如保留，定制版独立维护；③若公共段真演进，需合并公共变更")
    print(f"  同步纪律见定制版头部 banner 与 shared-core/README.md")
    # 输出一段 diff 摘要（前 30 行）
    for line in diff[:30]:
        print(f"  {line.rstrip()}")
    if len(diff) > 30:
        print(f"  ... 共 {len(diff)} 行 diff")
    return 1


if __name__ == "__main__":
    sys.exit(main())

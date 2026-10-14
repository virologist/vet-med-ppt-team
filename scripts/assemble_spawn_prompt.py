#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容 shim（v3.4.1 R9 shared-core 下沉，2026-10-14）
================================================
本包的实现已下沉至联邦共享件：my-experts/plugins/shared-core/assemble_spawn_prompt.py
（4 个无差异包共用同一份真源，消除 369 行 x 4 的拷贝漂移）。
本文件保留入口兼容——sop-stages.md / 各成员 MD 均引用 scripts/assemble_spawn_prompt.py。

转调机制：
  1. 以本文件位置反推「调用方专家包根」与「plugins 根」；
  2. 经 EXPERT_DIR 环境变量把专家包根显式传给 core——
     core 自身按脚本位置反推，在 shim 场景会指向 shared-core/，必须覆盖；
  3. 动态加载 core 并转调其 main()，stdout/stderr/退出码原样透传。
core 缺失时报错含获取指引（git 仓库结构下 core 不随包分发，仅安装态部署）。
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)                                  # 调用方专家包根


def _find_core() -> str | None:
    """从调用方包根逐级向上找 shared-core/assemble_spawn_prompt.py（最多 4 层）。
    不写死层数——安装态路径随 marketplace 嵌套深度变化（.../marketplaces/my-experts/plugins/<pkg>）。
    """
    d = _PKG
    for _ in range(4):
        cand = os.path.join(d, "shared-core", "assemble_spawn_prompt.py")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


_CORE = _find_core()

if _CORE is None:
    sys.stderr.write(
        "[assemble_spawn_prompt shim] shared-core 缺失（自 %s 向上 4 层未找到）\n"
        "  本包实现已下沉至联邦共享件。请确认安装态 .../plugins/shared-core/ 存在；\n"
        "  若在 git 仓库结构中运行，core 不随包分发——请改用安装态，或从\n"
        "  vet-med-ppt-team 仓库的 shared-core/ 取回。\n" % _PKG)
    sys.exit(3)

# 专家包根显式传给 core（core 内优先级：--expert-dir > EXPERT_DIR > 位置反推）
os.environ.setdefault("EXPERT_DIR", _PKG)

_spec = importlib.util.spec_from_file_location("_shared_core_assemble_spawn_prompt", _CORE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

if __name__ == "__main__":
    sys.exit(_mod.main())

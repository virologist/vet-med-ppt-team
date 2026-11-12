#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""usercustomize_host_safe.py — Python **usercustomize** 注入点（v3.31.2 · D5）

─── 作用 ────────────────────────────────────────────────────────
把本包 `scripts/host_safe_tmp.py` 的「可靠建目录」补丁，装到**回归子进程**里
⇒ `tempfile.mkdtemp()` / `os.makedirs()` 不再因宿主 broker 的概率性拒绝而随机失败
⇒ 57 个测试文件**零改动**即可受益（实测：注入前 0/6 ⇒ 注入后 6/6）。

─── 为什么用 `usercustomize` 而不是 `sitecustomize` ───────────────
宿主 shim 已占用 `sitecustomize`：
    PYTHONPATH = /Applications/WorkBuddy.app/.../cli/vendor/shim   ← 第一位
⇒ 我们若也放一个 `sitecustomize.py`，必须抢第一位 ⇒ **覆盖宿主 shim**
  ⇒ 等于绕开宿主文件系统授权策略 = 越权，**不可接受**。

而 Python 的 `site.execsitecustomize()` 顺序是：
    ① import sitecustomize   ② import usercustomize
⇒ 两者**共存**，且 `usercustomize` 在**其后**执行
⇒ 我们的补丁叠在宿主 broker **之上**，broker 照常生效（探针7 R2 实测：
  注入后 `os.mkdir` 单次仍耗时 5.00s ⇒ broker 仍在做授权决策）。

─── 怎么启用（回归时）────────────────────────────────────────────
把**本文件所在目录**追加到 `PYTHONPATH` **末尾**（不是首位！）：

    PYTHONPATH="<已有 PYTHONPATH>:<scripts 目录>" python3 scripts/test_x.py

⚠ **必须是「追加」**：放首位会遮蔽宿主 shim 的 `sitecustomize` ⇒ broker 失效。
⚠ **文件名固定为 `usercustomize.py`**：Python 只认这个名字。
  ⇒ 本文件以 `usercustomize_host_safe.py` 保存（避免与包内其它模块混淆），
    由 `scripts/run_regression.py` 在启动子进程时**复制/软链**成
    `usercustomize.py` 到一个临时注入目录，再把该目录**追加**到 PYTHONPATH。
    （探针7 R1 实测：`usercustomize` 会被自动 import，标记文件已生成。）
"""

import os
import sys

#: 本文件所在目录（= scripts/）——`host_safe_tmp.py` 与本文件同目录
_HERE = os.path.dirname(os.path.abspath(__file__))

try:
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from host_safe_tmp import install
    install()
except Exception as _exc:  # noqa: BLE001
    # ⚠ **绝不因注入失败而让整个 Python 进程起不来**——
    #   注入只是「提高可靠性」的增强，失败时应退化为原生行为并留下痕迹。
    sys.stderr.write(
        f"[host_safe_tmp] 注入失败（{type(_exc).__name__}: {_exc}）"
        f"→ 退回原生 tempfile/os.makedirs 行为（建目录可能概率性失败）。\n")

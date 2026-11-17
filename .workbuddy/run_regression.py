#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_regression.py — v3.31.3 逐套件回归器 + 证据 JSON 生成器

═══ 当前实现（v3.31.3 口径，与文件头旧描述不同，以本节为准）═══════════

每个套件用 `subprocess.run([sys.executable, scripts/test_<name>.py])` **直跑脚本**，
用**退出码**判定（与 `ensure_settings.check_regression` 口径一致）。

⚠ **为什么不用 `unittest.TestLoader`**：包内套件有**两种风格**并存 ——
  · pytest 风格（模块级 `def test_*()`，如 `test_harness.py`）
  · unittest 风格（`class TestX(unittest.TestCase)`，如 `test_five_gates.py`）
  ⇒ `loadTestsFromName` 对前者**收集到 0 条** ⇒ 会报 "NO TESTS RAN"
  ⇒ **rc=0 但一条没跑** = 最毒的一类假绿（实测踩过）。

⚠ **为什么逐套件子进程而不是同进程**：套件会改写模块级全局态
  （`host_safe_tmp.install()` / `mock.patch` / `sys.modules` 注入），
  同进程跑会跨套件串扰 ⇒ 隔离子进程是**正确性**要求，不是性能偏好。

⚠ **v3.31.3 证据纪律**：
  ① 每个套件的**完整输出**落盘到 `.workbuddy/_logs/suite_<name>.log`
     （旧版只保留最后一行 ⇒ 失败时拿不到 traceback，无法定位）；
  ② 证据 JSON 收**全部实跑项**（7 必跑 + D5），与收批 `--regression` 名单双向相等。

⚠ **注入 `usercustomize` 提高建目录可靠性**：
  宿主 broker 对 mkdir 的**放行是概率性的**（实测 `tempfile.mkdtemp()` 0/6）
  ⇒ 套件随机挂在 setUp ⇒ 回归结论不可信。
  ⇒ 本脚本把注入目录**追加**到 PYTHONPATH **末尾**
  （⚠ **必须追加**：放首位会遮蔽宿主 shim 的 `sitecustomize` ⇒ broker 失效）。

证据格式（`batch-close --regression-evidence` 要求）：
    {"suites": [{"suite": "<名>", "rc": 0, "duration_s": 12.3}, ...]}
"""

import contextlib
import importlib
import io
import json
import os
import shutil
import sys
import time
import unittest

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PKG, "scripts")
OUT = os.path.join(PKG, ".workbuddy", "regression_evidence.json")
PARTIAL = os.path.join(PKG, ".workbuddy", "regression_partial.json")
INJECT_DIR = os.path.join(PKG, ".workbuddy", "_inject")

#: Loop A 要求的 7 套件（真源：config/harness.yaml#loop_a.regression_required）
#: ⚠ **顺序**：`ensure_settings` 放**最后** —— 它是体检脚本，内部 28 项检查
#:   在本宿主会触发 broker 慢路径（实测可达 30+ 分钟）⇒ 放最后可让
#:   其余套件先跑完并**逐个落盘**（中途被打断也不丢已完成结果）。
SUITES = [
    "test_harness",
    "test_five_gates",
    "test_dead_config_disposition",
    "test_inspection_zone_registry_red",
    "test_arch_drift",
    "test_domain_pack",
]

#: 体检脚本（慢，放最后；rc 单独看，不混入 7 套件结论）
BODY_CHECK = "ensure_settings"

#: D5 能红套件（v3.31.3 起已纳入 harness.yaml#loop_a.regression_required）
D5_SUITE = "test_host_broker_resilience"


def prepare_inject_dir():
    """建注入目录：`usercustomize.py` → 转发到 `host_safe_tmp.install()`。"""
    os.makedirs(INJECT_DIR, exist_ok=True)
    with open(os.path.join(INJECT_DIR, "usercustomize.py"), "w",
              encoding="utf-8") as f:
        f.write(
            "# 自动生成（run_regression.py）——转发到 host_safe_tmp.install()\n"
            "import os, sys\n"
            f"_S = {SCRIPTS!r}\n"
            "if _S not in sys.path:\n"
            "    sys.path.insert(0, _S)\n"
            "try:\n"
            "    from host_safe_tmp import install\n"
            "    install()\n"
            "except Exception as _e:\n"
            "    sys.stderr.write('[host_safe_tmp] inject failed: %r\\n' % (_e,))\n"
        )
    return INJECT_DIR


def child_env():
    """构造子进程环境：把注入目录**追加**到 PYTHONPATH **末尾**。

    ⚠ **这是本脚本能否成立的关键**（2026-11-11 实测修正）：
      `install()` 改写的是**当前解释器进程**的全局 ⇒ **subprocess 起的
      子进程是全新解释器，不继承任何 monkey-patch** ⇒ 只在父进程 install()
      是**无效**的（实测：子进程照样抛
      `PermissionError: Brokered host mkdir requires an available runtime file rule`
      ⇒ 12 个用例失败）。
      ⇒ 必须让子进程**自己**装补丁 ⇒ 靠 `usercustomize`（解释器启动时
        自动 import）⇒ 把注入目录**追加**到 PYTHONPATH **末尾**。
      ⚠ **必须追加**（不能放首位）：首位会遮蔽宿主 shim 的 `sitecustomize`
        ⇒ broker 失效 ⇒ 变成「绕开宿主授权策略」= 越权。
    """
    env = dict(os.environ)
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pp + os.pathsep + INJECT_DIR) if pp else INJECT_DIR
    return env


def _run_unittest_suite(name):
    """跑一个测试套件，返回 (rc, duration_s, tail)。

    ⚠ **口径与 `ensure_settings.check_regression` 完全一致**（真源在那边）：
      `subprocess.run([sys.executable, <scripts/test_*.py>])` **直跑脚本**，
      用**退出码**判定。
      ⇒ 为何不用 `unittest.TestLoader`：包内套件有**两种风格**并存 ——
        · pytest 风格（模块级 `def test_*()`，如 `test_harness.py`）
        · unittest 风格（`class TestX(unittest.TestCase)`，如 `test_five_gates.py`）
      ⇒ `loadTestsFromName` 对前者**收集到 0 条** ⇒ 会报 "NO TESTS RAN"
        ⇒ **rc=0 但一条没跑** = 最毒的一类假绿。
      ⇒ 直跑脚本则**两种风格都覆盖**（脚本自带 `main()` 汇总）。

    ⚠ **子进程必须带 `env=child_env()`**：否则子进程没有 broker 补丁
      ⇒ 建目录随机被 broker 拒 ⇒ 12 个用例假失败（实测已复现）。
    """
    t = time.time()
    import subprocess
    script = os.path.join(SCRIPTS, name + ".py")
    args = [sys.executable, script]
    if name == "ensure_settings":
        # ⚠ 体检脚本：传包根；`--quick` 跳过第 7 项（回归由本脚本统一跑，
        #   否则**同一批套件跑两遍** ⇒ 耗时翻倍）
        args.append(PKG)
        args.append("--quick")
    try:
        p = subprocess.run(args, cwd=PKG, env=child_env(),
                           capture_output=True, text=True, timeout=2400)
        rc = p.returncode
        out = (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, round(time.time() - t, 1), "TIMEOUT after 2400s"
    dur = round(time.time() - t, 1)
    # ⚠ **v3.31.3：每个套件保留完整输出**（不是只留最后一行）。
    #   上一轮教训：`test_five_gates` 报 "FAILED (errors=2)"，但回归器只截了
    #   最后一行 ⇒ **没有 traceback** ⇒ 无法判断是超时、断言还是环境瞬态，
    #   只能靠重跑猜。⇒ 「结果可验证」要求失败可定位到具体用例与栈。
    try:
        log_dir = os.path.join(PKG, ".workbuddy", "_logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "suite_%s.log" % name), "w",
                  encoding="utf-8") as f:
            f.write(out)
    except OSError:
        pass
    tail = [l for l in out.strip().splitlines() if l.strip()]
    return rc, dur, (tail[-1][:200] if tail else "")

def main():
    # v3.31.4 方案A（B1.2）：收批次归属（可选；收批时证据必须带，否则被
    # _regression_evidence_verdict 以 evidence_missing_batch_binding 拒收）。
    _args = sys.argv[1:]
    _batch_id = ""
    _start_commit = ""
    if "--batch" in _args:
        _i = _args.index("--batch")
        _batch_id = _args[_i + 1] if _i + 1 < len(_args) else ""
    if "--start-commit" in _args:
        _i = _args.index("--start-commit")
        _start_commit = _args[_i + 1] if _i + 1 < len(_args) else ""
    prepare_inject_dir()
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    os.chdir(PKG)

    # ⚠ **进程内直接装补丁**（`usercustomize` 只在解释器启动时生效，
    #   而本脚本是**解释器本身** ⇒ 必须在 main() 里显式 install()）。
    #   ⚠ 装的是**我们自己的** host_safe_tmp 补丁（叠在 broker 之外层）
    #     ⇒ broker 的授权决策照常进行（不绕开宿主策略）。
    try:
        from host_safe_tmp import install as _install
        _install()
        print("[inject] host_safe_tmp.install() 已在进程内装上", flush=True)
    except Exception as _e:
        print(f"[inject] 装 host_safe_tmp 失败（{_e!r}）——退回原生行为", flush=True)

    results = []
    all_suites = list(SUITES) + [D5_SUITE, BODY_CHECK]
    log_path = os.path.join(PKG, ".workbuddy", "regression.log")
    try:
        logf = open(log_path, "w", encoding="utf-8")
    except OSError as _e:
        logf = None

    def _log(line):
        print(line, flush=True)
        if logf is not None:
            try:
                logf.write(line + "\n")
                logf.flush()
            except OSError:
                pass

    for i, name in enumerate(all_suites, 1):
        rc, dur, tail = _run_unittest_suite(name)
        rec = {"suite": name, "rc": rc, "duration_s": dur}
        results.append(rec)
        # 逐个落盘 ⇒ 中途被打断也不丢已完成结果
        # ⚠ 落盘失败**不得**中断回归（OneDrive/限流下写文件可能失败）
        try:
            with open(PARTIAL, "w", encoding="utf-8") as f:
                json.dump({"suites": results}, f, ensure_ascii=False, indent=2)
        except OSError as _e:
            print(f"⚠ partial 落盘失败（{_e!r}）——继续跑", flush=True)
        _log(f"[{i}/{len(all_suites)}] {name}: rc={rc} {dur}s | {tail[:90]}")
    if logf is not None:
        logf.close()

    # ⚠ **v3.31.3 修正：证据收全部 8 项（含 `ensure_settings`）**。
    #   旧版把体检排除在证据外，理由是「体检不是回归套件」——但
    #   `config/harness.yaml#loop_a.regression_required` **明确把 `ensure_settings`
    #   列为 7 项必跑之一** ⇒ 收批时 `--regression` 必须含它，而
    #   `_regression_evidence_verdict` 要求「证据集合 == --regression 集合」（双向相等）
    #   ⇒ 旧证据必然报 `evidence_suite_mismatch`（缺 ensure_settings / 多 D5）。
    #   ⇒ 改为：证据含全部实跑项（7 必跑 + D5 新增能红套件），
    #     收批时 `--regression` 传同一份名单；`regression_check` 只拒绝缺项、
    #     **允许多跑**（见 `loop_contract.regression_check`：extra 仅记录不阻断）。
    evidence_suites = results
    payload = {"suites": evidence_suites,
               "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "pkgs_root": PKG,
               # v3.31.4 方案A（B1.2）：批次归属——收批裁决据此拒绝「旧批证据收新批」
               "batch_id": _batch_id,
               "start_commit": _start_commit}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    bad = [r for r in evidence_suites if r["rc"] != 0]
    print(f"\n=== 证据已写入 {OUT} ===")
    print(f"实跑套件通过 {len(evidence_suites) - len(bad)}/{len(evidence_suites)}")
    for r in bad:
        log = os.path.join(PKG, ".workbuddy", "_logs", "suite_%s.log" % r["suite"])
        print(f"  ✗ {r['suite']} rc={r['rc']}  完整输出：{log}")
    print("收批用 --regression 名单（与证据完全一致）：", flush=True)
    print(",".join(r["suite"] for r in evidence_suites), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared-core 分发与防漂移门禁（v3.4.2 P0-1 配套，2026-10-15 适配至本包）
=====================================================================
目的：修复「R9 联邦下沉后 git clone 直跑 shim 退出码 3」的可安装性回归，
      同时用哈希比对防止 vendor 兜底副本与联邦真源产生漂移。
适配：自 smart-textbook-team/tests/test_vendor_core.py 复制，仅改
      _PKG_NAME / MEMBER_IDS / V6 临时目录名三处包耦合。
      ★ v3.4.2 P0-1 适配至本包：_PKG_NAME 原为 "triz-invention-team"
        （从 triz 包复制过来忘了改）⇒ _INSTALL_DIR 指向**别的包**
        ⇒ V4 防漂移比对的是别人的 vendor 副本 ⇒ 本包漂移**永远发现不了**。

检查项：
  V1  vendor/shared-core/assemble_spawn_prompt.py 存在
  V2  VENDOR.json 存在且可解析
  V3  vendor 副本 sha256 == VENDOR.json.sha256（清单自洽，任何场景都查）
  V4  联邦真源存在时 vendor == 联邦（防漂移；联邦缺失 → SKIP，git/CI 场景不误报）
  V5  冒烟：python3 scripts/assemble_spawn_prompt.py --list-members 退出码 0
      且输出含全部成员 ID（真执行，非静态断言）
  V6  冒烟：联邦缺失模拟（SHIM 隔离目录）——把包拷到临时目录跑，仍须退出码 0
      （证明 git clone 态开箱可用；这是 P0-1 的验收核心）

用法：
  python3 tests/test_vendor_core.py [--expert-dir 路径] [--json]
退出码：0 全通过 | 1 有失败项
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

#: ★ 包名（本包，非 triz）——原先从 triz 包复制过来忘了改，导致 _INSTALL_DIR
#:   指向别的包 ⇒ V4 防漂移比对的是**别人的** vendor 副本。
_PKG_NAME = "vet-med-ppt-team"
_INSTALL_DIR = os.path.expanduser(
    "~/.workbuddy/plugins/marketplaces/my-experts/plugins/" + _PKG_NAME
)
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 与包内主测试同策略：CI/纯 clone 态回落到仓库自身
DEFAULT_EXPERT_DIR = (
    _REPO_DIR
    if os.path.exists(os.path.join(_REPO_DIR, ".codebuddy-plugin", "plugin.json"))
    else _INSTALL_DIR
)
CORE_REL = os.path.join("vendor", "shared-core", "assemble_spawn_prompt.py")
MANIFEST_REL = os.path.join("vendor", "shared-core", "VENDOR.json")
MEMBER_IDS = [
    "dvm-content-expert",
    "pedagogy-architect",
    "visual-slide-designer",
    "ppt-producer",
    "verifier",
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_federal(pkg_root, max_up=4):
    """与 shim 同逻辑：从包根父目录起向上找联邦 shared-core/。"""
    d = os.path.dirname(pkg_root)
    for _ in range(max_up):
        cand = os.path.join(d, "shared-core", "assemble_spawn_prompt.py")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


class Result:
    def __init__(self):
        self.items = []          # (id, desc, status, detail) status: PASS/FAIL/SKIP

    def add(self, cid, desc, status, detail=""):
        self.items.append((cid, desc, status, detail))

    @property
    def failed(self):
        return [i for i in self.items if i[2] == "FAIL"]


def run_checks(expert_dir):
    r = Result()
    core_path = os.path.join(expert_dir, CORE_REL)
    manifest_path = os.path.join(expert_dir, MANIFEST_REL)

    # V1 vendor 副本存在
    if not os.path.isfile(core_path):
        r.add("V1", "vendor/shared-core/assemble_spawn_prompt.py 存在", "FAIL", core_path)
        r.add("V2", "VENDOR.json 存在且可解析", "SKIP", "V1 失败，跳过")
        r.add("V3", "vendor sha256 == VENDOR.json.sha256", "SKIP", "V1 失败，跳过")
        r.add("V4", "vendor == 联邦真源（防漂移）", "SKIP", "V1 失败，跳过")
    else:
        r.add("V1", "vendor/shared-core/assemble_spawn_prompt.py 存在", "PASS")
        vendor_sha = sha256(core_path)

        # V2 清单可解析
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            r.add("V2", "VENDOR.json 存在且可解析", "PASS")
        except (OSError, json.JSONDecodeError) as e:
            manifest = {}
            r.add("V2", "VENDOR.json 存在且可解析", "FAIL", str(e))

        # V3 清单自洽
        want = manifest.get("sha256", "")
        r.add("V3", "vendor sha256 == VENDOR.json.sha256",
              "PASS" if want == vendor_sha else "FAIL",
              "" if want == vendor_sha else f"清单 {want[:12]}… vs 实际 {vendor_sha[:12]}…")

        # V4 防漂移（联邦存在才比对）
        fed = find_federal(expert_dir)
        if fed is None:
            r.add("V4", "vendor == 联邦真源（防漂移）", "SKIP",
                  "联邦 core 缺失（git/CI 态），按设计跳过")
        else:
            fed_sha = sha256(fed)
            r.add("V4", "vendor == 联邦真源（防漂移）",
                  "PASS" if fed_sha == vendor_sha else "FAIL",
                  "" if fed_sha == vendor_sha else
                  f"漂移！联邦 {fed_sha[:12]}… vs vendor {vendor_sha[:12]}…；"
                  f"同步: cp {fed} {core_path} 并更新 VENDOR.json")

    # V5 安装态冒烟（走联邦真源）
    script = os.path.join(expert_dir, "scripts", "assemble_spawn_prompt.py")
    try:
        p = subprocess.run([sys.executable, script, "--list-members"],
                           capture_output=True, text=True, timeout=60)
        out = p.stdout + p.stderr
        missing = [m for m in MEMBER_IDS if m not in out]
        ok = p.returncode == 0 and not missing
        r.add("V5", "安装态冒烟 --list-members 退出码 0 且含全部成员",
              "PASS" if ok else "FAIL",
              "" if ok else f"exit={p.returncode} 缺失成员={missing} out={out[:200]}")
    except (OSError, subprocess.SubprocessError) as e:
        r.add("V5", "安装态冒烟 --list-members 退出码 0 且含全部成员", "FAIL", str(e))

    # V6 git-clone 态冒烟：拷到临时目录（其父目录无 shared-core）→ 必须走 vendor 兜底
    tmp_root = tempfile.mkdtemp(prefix="vetmed-clone-sim-")
    try:
        tmp_pkg = os.path.join(tmp_root, _PKG_NAME)
        shutil.copytree(expert_dir, tmp_pkg,
                        ignore=shutil.ignore_patterns(".git"))
        if find_federal(tmp_pkg) is not None:
            r.add("V6", "git-clone 态冒烟（隔离目录走 vendor 兜底）", "SKIP",
                  "临时目录意外命中联邦 core，无法隔离")
        else:
            env = dict(os.environ, SHIM_DEBUG="1")
            p = subprocess.run(
                [sys.executable, os.path.join(tmp_pkg, "scripts", "assemble_spawn_prompt.py"),
                 "--list-members"],
                capture_output=True, text=True, timeout=60, env=env)
            out = p.stdout + p.stderr
            missing = [m for m in MEMBER_IDS if m not in out]
            used_vendor = "来源: vendor" in out
            ok = p.returncode == 0 and not missing and used_vendor
            r.add("V6", "git-clone 态冒烟（隔离目录走 vendor 兜底，退出码 0）",
                  "PASS" if ok else "FAIL",
                  "" if ok else f"exit={p.returncode} 缺失={missing} 走vendor={used_vendor} out={out[:250]}")
    except (OSError, subprocess.SubprocessError) as e:
        r.add("V6", "git-clone 态冒烟（隔离目录走 vendor 兜底）", "FAIL", str(e))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expert-dir", default=DEFAULT_EXPERT_DIR)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    r = run_checks(args.expert_dir)
    failed = r.failed

    if args.json:
        print(json.dumps({"passed": len(r.items) - len(failed),
                          "total": len(r.items),
                          "items": [{"id": i[0], "desc": i[1], "status": i[2],
                                     "detail": i[3]} for i in r.items]},
                         ensure_ascii=False, indent=2))
    else:
        print("=" * 62)
        print("shared-core 分发与防漂移门禁（vet-med-ppt-team）")
        print("=" * 62)
        for cid, desc, status, detail in r.items:
            mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "-"}[status]
            print(f"  {mark} [{cid}] {status:<4} {desc}")
            if detail:
                print(f"          → {detail}")
        n_pass = sum(1 for i in r.items if i[2] == "PASS")
        print("-" * 62)
        print(f"检查项 {len(r.items)} | 通过 {n_pass} | 失败 {len(failed)}")
        print("=" * 62)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

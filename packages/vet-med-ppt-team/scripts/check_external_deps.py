#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 外部依赖缺失的可执行检查（v3.17.0 新建）
#
# 目的：把「外部 skill 缺失」从**静默失效**变成**显式可见**。
# 背景：七维量规原执行源在包外用户级 skill teaching-ppt-studio，而 plugin.json
#       无依赖声明字段（见 references/dependency-manifest.yaml#platform_fact）。
#       v3.17.0 已把量规**内化**进本包，故本检查**只提示、不阻断**：
#       缺失时明确告知「以包内版本为准」，而不是让流程静默退化。
#
# 归属：外部依赖登记表的消费方；登记表 = references/dependency-manifest.yaml（SSOT）
# 用法：
#   python3 references/check_external_deps.py            # 默认不阻断，缺失 exit 0
#   python3 references/check_external_deps.py --strict   # 严格模式：缺失 exit 1
#   python3 references/check_external_deps.py --json     # 机器可读输出
#   VETPPT_SKILLS_ROOT=/tmp/empty python3 references/check_external_deps.py   # 覆盖探针根（反例测试用）
#
# 注意：本脚本刻意**不放在 scripts/**——scripts/ 由另一批次维护，本批不改他文件。
#       待体检第 23 项落地后，可由 ensure_settings.py 调用本模块（跨批需求，见
#       references/dependency-manifest.yaml#checker.integration_status）。

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# v3.17.0：本脚本原置于 references/，已归位到 scripts/（包内惯例：scripts/ 放可执行脚本，
#   references/ 放文档；且 references/ 下的 .py 会被体检第 17 项「悬空脚本引用」漏扫、
#   回归套件也未必收录）。归位后清单仍在 references/，故路径改走父目录。
MANIFEST = HERE.parent / "references" / "dependency-manifest.yaml"


def _load_manifest():
    """读登记表；登记表缺失即视为「无外部依赖登记」，不报错（自包含包应能独立运行）。"""
    if not MANIFEST.is_file():
        return None
    try:
        import yaml
    except ImportError:  # pragma: no cover - 环境缺 pyyaml 时降级为「读不到登记」
        return None
    try:
        with MANIFEST.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001 - 登记表损坏属环境问题，不应阻断使用
        print(f"⚠ 外部依赖登记表解析失败（{MANIFEST}）：{exc}", file=sys.stderr)
        return None


def _expand(root: str, skills_root: str | None) -> Path:
    """把登记表里的探针路径展开成绝对路径。

    skills_root 覆盖：探针根目录被替换为该值下的同名目录（用于反例测试 / 多安装布局）。
    """
    p = Path(os.path.expanduser(root))
    if skills_root:
        p = Path(os.path.expanduser(skills_root)) / p.name
    return p


def probe(dep: dict, skills_root: str | None) -> tuple[bool, str]:
    """探测一个外部依赖是否真的装上了。

    判据（确定性，不靠猜）：探针根目录**存在**且**至少含一个 probe_files**。
    只看目录存在是不够的——空目录/半安装目录同样算「未装好」。
    """
    probe_files = dep.get("probe_files") or []
    for root in dep.get("probe_roots") or []:
        base = _expand(root, skills_root)
        if not base.is_dir():
            continue
        if not probe_files:
            return True, str(base)
        if any((base / f).exists() for f in probe_files):
            return True, str(base)
    return False, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="外部依赖缺失检查（不阻断，仅显式化）")
    ap.add_argument("--strict", action="store_true",
                    help="外部依赖缺失时 exit 1（默认不阻断）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--skills-root", default=os.environ.get("VETPPT_SKILLS_ROOT"),
                    help="覆盖技能安装根目录（默认取环境变量 VETPPT_SKILLS_ROOT）")
    args = ap.parse_args(argv)

    manifest = _load_manifest()
    deps = ((manifest or {}).get("dependencies") or []) if manifest else []

    if not manifest:
        print("ℹ 未读到 references/dependency-manifest.yaml（视为无外部依赖登记）")
        return 0

    results = []
    missing = 0
    for dep in deps:
        ok, path = probe(dep, args.skills_root)
        msgs = dep.get("messages") or {}
        fallback = (dep.get("internal_fallback") or {}).get("path") or ""
        if ok:
            text = (msgs.get("found") or "外部依赖 {id} 已安装（{path}）").format(
                id=dep.get("id"), path=path)
            status = "found"
        else:
            missing += 1
            text = (msgs.get("missing")
                    or "外部 skill {id} 未安装 → 本包已内化 {fb}，以包内版本为准").format(
                        id=dep.get("id"), fb=fallback)
            status = "missing"
        results.append({
            "id": dep.get("id"),
            "status": status,
            "path": path or None,
            "blocking": bool(dep.get("blocking")),
            "internal_fallback": fallback,
            "message": text,
        })

    if args.json:
        print(json.dumps({
            "checker": "references/check_external_deps.py",
            "dependencies": results,
            "missing_count": missing,
            "blocking": False,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "✓" if r["status"] == "found" else "⚠"
            print(f"{mark} {r['message']}")
        if missing:
            print(f"→ 外部依赖缺失 {missing} 项：**不阻断**本包使用"
                  f"（量规等能力已内化进本包，缺失只影响「与上游比对更新」）。")
        else:
            print("→ 全部外部依赖均已安装；量规执行源仍以包内版本为准。")

    if missing and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

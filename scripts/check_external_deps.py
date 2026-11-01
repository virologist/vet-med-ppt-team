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
#   python3 scripts/check_external_deps.py            # 默认不阻断，缺失 exit 0
#   python3 scripts/check_external_deps.py --strict   # 严格模式：缺失 exit 1
#   python3 scripts/check_external_deps.py --json     # 机器可读输出
#   VETPPT_SKILLS_ROOT=/tmp/empty python3 scripts/check_external_deps.py   # 覆盖探针根（反例测试用）
#
# v3.17.0：本脚本**已归位 scripts/**（原置于 references/，会漏出体检第 17 项与回归套件的扫描范围）。
#       **未并入体检**——请按 `python3 scripts/check_external_deps.py` 手动调用或由 CI 调用。
#       ⚠️ 不要再写「待体检第 23 项落地后…」这类失效承诺：
#         dependency-manifest.yaml#checker.integration_status 已明令「勿再写待并入第 23 项」
#         （第 23 项现为域绑定残留巡检，与依赖检查无关），此处若留同一句话就是同一个错误漏一处。

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


def validate_contract(manifest: dict) -> tuple[bool, list, dict]:
    """校验「外部 skill 接入契约」（v3.28.2 B4 · D13③④ 立规）。

    缺口（本轮十三维度诊断实测）：D13①② 已落地（登记面结构支持五要素 /
    「以包内为准」成文），但 ③「PPT 美化类 skill 与 visual-slide-designer /
    visual-rules.yaml 的职责边界」与 ④「外部标准类 skill 与包内 standards 的归口」
    **均无成文规则** ⇒ 未来接入时无裁决依据，必然双源漂移。

    判据（全部可判定，语义内容不判）：
      ① `skill_contract.required_fields` 列出的九项，每条 dependencies[] 都非空；
      ② 解耦判据：required=false 且 blocking=false ⇒ 移除后不降级（记录，不判红）；
      ③ `beautify_boundary` 必含 decision_authority / executor / allowed / forbidden / dedupe_rule，
         且 decision_authority **必须**指向 config/visual-rules.yaml（判据唯一源不得旁落）；
      ④ `standard_authority` 必含 registry / rule / on_conflict / anti_dual_source，
         且 registry **必须**指向 config/external-tools.yaml#standards（不得双源）。

    返回 (ok, problems, summary)。
    """
    problems = []
    manifest = manifest if isinstance(manifest, dict) else {}
    deps = manifest.get("dependencies") or []
    sc = manifest.get("skill_contract")
    if not isinstance(sc, dict) or not sc:
        if deps:
            problems.append({"code": "E_NO_CONTRACT",
                             "detail": "有外部依赖登记但缺 skill_contract 段"
                                       "（五要素/美化边界/标准归口无判据源）"})
        return (not problems), problems, {"deps": len(deps), "contract": False}

    req = [str(x) for x in (sc.get("required_fields") or [])]
    if not req:
        problems.append({"code": "E_NO_REQUIRED_FIELDS",
                         "detail": "skill_contract.required_fields 为空——五要素无判据"})
    decoupled = []
    for i, dep in enumerate(deps):
        if not isinstance(dep, dict):
            problems.append({"code": "E_DEP_NOT_MAPPING", "detail": f"dependencies[{i}] 不是映射"})
            continue
        tag = f"dependencies[{i}]({dep.get('id') or '?'})"
        for f in req:
            v = dep.get(f)
            if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
                problems.append({"code": "E_DEP_MISSING_FIELD",
                                 "detail": f"{tag} 缺五要素字段 {f!r}"
                                           f"（判据源 dependency-manifest.yaml#skill_contract）"})
        if dep.get("required") is False and dep.get("blocking") is False:
            decoupled.append(dep.get("id"))

    bb = sc.get("beautify_boundary")
    if not isinstance(bb, dict):
        problems.append({"code": "E_NO_BEAUTIFY_BOUNDARY",
                         "detail": "缺 beautify_boundary（③ 美化类 skill 职责边界未立规）"})
    else:
        for f in ("decision_authority", "executor", "allowed", "forbidden", "dedupe_rule"):
            if not bb.get(f):
                problems.append({"code": "E_BEAUTIFY_FIELD_MISSING",
                                 "detail": f"beautify_boundary 缺 {f!r}"})
        da = str(bb.get("decision_authority") or "")
        if da and "visual-rules.yaml" not in da:
            problems.append({"code": "E_BEAUTIFY_AUTHORITY_DRIFT",
                             "detail": f"beautify_boundary.decision_authority={da!r} "
                                       f"必须指向 config/visual-rules.yaml（判据唯一源）"})

    sa = sc.get("standard_authority")
    if not isinstance(sa, dict):
        problems.append({"code": "E_NO_STANDARD_AUTHORITY",
                         "detail": "缺 standard_authority（④ 外部标准归口未立规）"})
    else:
        for f in ("registry", "rule", "on_conflict", "anti_dual_source"):
            if not sa.get(f):
                problems.append({"code": "E_STANDARD_FIELD_MISSING",
                                 "detail": f"standard_authority 缺 {f!r}"})
        reg = str(sa.get("registry") or "")
        if reg and "external-tools.yaml#standards" not in reg:
            problems.append({"code": "E_STANDARD_REGISTRY_DRIFT",
                             "detail": f"standard_authority.registry={reg!r} "
                                       f"必须指向 config/external-tools.yaml#standards"})
    return (not problems), problems, {
        "deps": len(deps),
        "contract": True,
        "required_field_count": len(req),
        "decoupled_deps": decoupled,
    }


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

    # ── v3.28.2 B4：接入契约校验（D13③④；与"装没装"是两件事）──────────
    #   ⚠ 本段判的是**登记是否合规**（五要素齐 / 美化边界成文 / 标准归口唯一），
    #     不判"外部 skill 好不好用"。
    c_ok, c_problems, c_summary = validate_contract(manifest)

    if args.json:
        print(json.dumps({
            "checker": "scripts/check_external_deps.py",
            "dependencies": results,
            "missing_count": missing,
            "blocking": False,
            "contract": {"ok": c_ok, "problems": c_problems, "summary": c_summary},
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
        # 契约结果单列（与上面"装没装"分开说，避免混为一谈）
        if c_ok:
            print(f"✓ 接入契约合规（{c_summary.get('deps', 0)} 条依赖 / "
                  f"五要素 {c_summary.get('required_field_count', 0)} 项；"
                  f"可解耦：{c_summary.get('decoupled_deps') or '无'}）")
        else:
            print(f"⚠ 接入契约 {len(c_problems)} 处不合规：")
            for p in c_problems:
                print(f"    · [{p.get('code')}] {p.get('detail')}")

    if args.strict and (missing or not c_ok):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

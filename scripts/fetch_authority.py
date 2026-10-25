#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_authority.py — 联网权威资源统一编排层（v3.19.0 新增）

══════════════════════════════════════════════════════════════════════
立项依据（2026-10-25 第五次从零诊断·维度 13 实测）：
  此前包内联网是「每个用途各写各的」：
    · harness.py 自建 PubMed esearch（`_esearch_url` / `_pubmed_exists`）+ 国图 + 国标；
    · fetch_oa_image.py 自建 Europe PMC 通道；
    · MCP 侧（pubmed / firecrawl / fetch）**零引用**。
  ⇒ **无统一入口、无优先级、无冗余降级**——任一通道失败只有该用途失败，
    无自动切换；且「权威源该实时抓还是用缓存」无人管。

★ L1/L2 分层契约（**本脚本最重要的纪律**，不可省）：
  MCP 工具是**宿主会话级**工具（主理人/成员在会话里用 ToolSearch + DeferExecuteTool
  调），**不是 scripts/*.py 能 import 的库** ⇒ 本脚本**不可能**在脚本内调 MCP。
  故分两层：
    · **L1 脚本层（确定性）**：本脚本执行 `kind: http` 的通道
      （PubMed esearch / 国图 / 国标 / Europe PMC），并输出**编排决策**
      （该走哪条链、各链状态、失败后的降级建议）。
    · **L2 会话层（语义/工具）**：`kind: mcp_tool` 的通道由主理人/成员在会话内执行，
      本脚本**只判定与记账**（把执行结果落进通道状态与证据账本）。
  这不是缺陷，是分工宪法的必然：「谁来调」是语义问题 → LLM；
  「调什么 / 失败了怎么办」是确定性问题 → 脚本。

用法：
  # ① 只出编排决策（不联网）——供主理人/成员据此决定调哪条链
  python3 scripts/fetch_authority.py --plan --purpose "禽流感 HA 糖基化位点"

  # ② 执行 L1 HTTP 通道（PubMed esearch 存在性核验）
  python3 scripts/fetch_authority.py --pmid 12345678

  # ③ 按用户指定源取（URL / 本地 PDF），用户源**优先于**域默认通道
  python3 scripts/fetch_authority.py --source-json sources.json

退出码：
  0 = 成功（至少一条通道拿到结果）
  2 = 用法错误
  3 = 全部通道失败
  4 = 用户指定源未确认（access != confirmed）——**阻断**，不静默跳过
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
EXT_CFG = PKG / "config" / "external-tools.yaml"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ALL_FAILED = 3
EXIT_SOURCE_UNCONFIRMED = 4


def log(msg: str) -> None:
    print(f"[fetch_authority] {msg}", file=sys.stderr)


def _load_yaml(path: Path):
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except Exception as e:
        return None, str(e)


def _load_cfg():
    cfg, err = _load_yaml(EXT_CFG)
    if err:
        return None, f"外部工具配置读取失败：{err}"
    return cfg, ""


def build_plan(cfg: dict, purpose: str = "", domain_id: str = "") -> dict:
    """产出**编排决策**（不联网）。

    决策规则（确定性，可复核）：
      ① 通道按 `priority` 升序；
      ② `fallback_for` 声明的通道排在被替代者之后（冗余链）；
      ③ L1（脚本可执行）与 L2（会话层）分开列出——调用方据此知道**谁来调**。
    """
    channels = cfg.get("channels") or []
    rows = []
    for ch in channels:
        rows.append({
            "id": ch.get("id"),
            "kind": ch.get("kind"),
            "layer": ch.get("layer"),
            "priority": ch.get("priority", 99),
            "capability": ch.get("capability") or [],
            "fallback_for": ch.get("fallback_for"),
            "degraded_capability": ch.get("degraded_capability") or [],
            "tool": ch.get("tool"),
            "endpoint_ref": ch.get("endpoint_ref"),
            "executor": "脚本（本脚本可直接执行）" if ch.get("layer") == "L1"
                        else "会话层（主理人/成员用 ToolSearch 实调）",
        })
    rows.sort(key=lambda r: (r["priority"], r["id"]))

    # 冗余链：按 fallback_for 分组
    chains = {}
    for r in rows:
        fb = r.get("fallback_for")
        if fb:
            chains.setdefault(fb, []).append(r["id"])

    plan = {
        "purpose": purpose,
        "domain_id": domain_id,
        "L1_script_layer": [r["id"] for r in rows if r["layer"] == "L1"],
        "L2_session_layer": [r["id"] for r in rows if r["layer"] == "L2"],
        "ordered_channels": rows,
        "fallback_chains": chains,
        "note": ("MCP 通道（L2）**不可**由脚本调用——本脚本只出决策与记账；"
                 "调用方在会话内用 ToolSearch + DeferExecuteTool 执行 L2 通道后，"
                 "用 --record 把结果回填。"),
    }
    return plan


def _pubmed_esearch(pmid: str, timeout: int = 15) -> dict:
    """L1：PubMed esearch 存在性核验（复用包内既有口径：只判存在性，无元数据）。"""
    import urllib.request
    import urllib.error
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    url = f"{base}?db=pubmed&retmode=json&term={pmid}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vet-med-ppt-team/3.19.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode("utf-8"))
        ids = (j.get("esearchresult") or {}).get("idlist") or []
        return {"channel": "pubmed_esearch", "pmid": pmid,
                "exists": bool(ids), "matched_ids": ids,
                "capability": ["PMID 存在性核验"],
                "degraded": True,  # 相对 MCP 版能力降级
                "degraded_capability": ["元数据", "全文", "相关文献", "按引文反查"]}
    except urllib.error.HTTPError as e:
        return {"channel": "pubmed_esearch", "pmid": pmid, "exists": None,
                "error": f"HTTP {e.code}", "degraded": True,
                "degraded_capability": ["元数据", "全文", "相关文献", "按引文反查"]}
    except Exception as e:
        return {"channel": "pubmed_esearch", "pmid": pmid, "exists": None,
                "error": f"{type(e).__name__}: {str(e)[:80]}", "degraded": True,
                "degraded_capability": ["元数据", "全文", "相关文献", "按引文反查"]}


def _validate_user_sources(sources: list) -> tuple[list, list]:
    """校验用户指定源（intake.user_sources）。

    返回 (confirmed_sources, problems)：
      · type ∈ {pdf, url, local_file}；path/url 二选一；
      · access ∈ {confirmed, pending, unavailable}
      · **access != confirmed ⇒ 不静默跳过**，列入 problems（阻断级）。
    """
    ok, problems = [], []
    for i, s in enumerate(sources or []):
        if not isinstance(s, dict):
            problems.append({"index": i, "reason": "源条目不是映射"})
            continue
        st = str(s.get("type") or "").strip()
        if st not in ("pdf", "url", "local_file"):
            problems.append({"index": i, "reason": f"type 非法：{st!r}"
                             "（应为 pdf / url / local_file）"})
            continue
        if st == "url" and not s.get("url"):
            problems.append({"index": i, "reason": "type=url 但缺 url"})
            continue
        if st in ("pdf", "local_file") and not s.get("path"):
            problems.append({"index": i, "reason": f"type={st} 但缺 path"})
            continue
        acc = str(s.get("access") or "pending").strip()
        if acc != "confirmed":
            problems.append({"index": i, "reason": f"源未确认（access={acc}）",
                             "severity": "block"})
            continue
        ok.append(s)
    return ok, problems


def main() -> int:
    ap = argparse.ArgumentParser(
        description="联网权威资源统一编排（编排决策 + L1 通道执行 + L2 记账）")
    ap.add_argument("--plan", action="store_true", help="只出编排决策，不联网")
    ap.add_argument("--purpose", default="", help="检索目的（进 plan 便于对账）")
    ap.add_argument("--domain", default="", help="当前任务域 id")
    ap.add_argument("--pmid", default="", help="PMID（走 pubmed_esearch L1 通道）")
    ap.add_argument("--source-json", default="",
                    help="用户指定源 JSON 文件（intake.user_sources 形态）")
    ap.add_argument("--record", default="",
                    help="L2 通道执行结果回填 JSON（会话层调用后回填记账）")
    ap.add_argument("--out", default="", help="结果写入 JSON 文件")
    args = ap.parse_args()

    cfg, err = _load_cfg()
    if err:
        log(f"⛔ {err}")
        return EXIT_USAGE

    out = {"plan": build_plan(cfg, args.purpose, args.domain), "results": [],
           "problems": []}

    # ① 用户指定源：**优先于**域默认通道（用户明确指定的源不被默认覆盖）
    if args.source_json:
        p = Path(args.source_json).expanduser()
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            srcs = data.get("sources") if isinstance(data, dict) else data
        except Exception as e:
            log(f"⛔ 用户指定源读取失败：{e}")
            return EXIT_USAGE
        ok, problems = _validate_user_sources(srcs)
        out["problems"] += problems
        blocking = [x for x in problems if x.get("severity") == "block"]
        if blocking:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            log("⛔ 用户指定源未确认——**阻断**，不静默跳过"
                "（确认后再执行，或由主理人改用其它通道并声明）")
            return EXIT_SOURCE_UNCONFIRMED
        for s in ok:
            out["results"].append({
                "channel": "user_source",
                "type": s.get("type"),
                "target": s.get("url") or s.get("path"),
                "status": "accepted",
                "priority": 0,   # 0 = 高于一切默认通道
                "note": "用户指定源**优先于**域档案默认通道",
            })

    # ② L1 通道执行（脚本可直接执行的）
    if args.pmid:
        out["results"].append(_pubmed_esearch(args.pmid))

    # ③ L2 通道记账（会话层执行后回填）
    if args.record:
        p = Path(args.record).expanduser()
        try:
            with open(p, encoding="utf-8") as f:
                rec = json.load(f)
            out["results"].append({"channel": "L2_recorded", **rec})
        except Exception as e:
            log(f"⚠ L2 回填读取失败：{e}")

    # ④ 编排决策（plan 模式直接输出）
    if args.plan and not args.pmid and not args.source_json and not args.record:
        print(json.dumps(out["plan"], ensure_ascii=False, indent=2))
        if args.out:
            Path(args.out).expanduser().write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return EXIT_OK

    if args.out:
        Path(args.out).expanduser().write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # 退出码：有结果 → 0；无结果且有源未确认 → 4；全通道失败 → 3
    if out["results"]:
        return EXIT_OK
    if out["problems"]:
        return EXIT_SOURCE_UNCONFIRMED
    return EXIT_ALL_FAILED


if __name__ == "__main__":
    sys.exit(main())

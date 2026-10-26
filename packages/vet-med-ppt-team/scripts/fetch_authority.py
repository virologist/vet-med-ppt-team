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
import time          # v3.21.0：L1 通道重试的指数退避需要 sleep
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


# ─────────────────── L1 HTTP 重试（v3.21.0 · 维度 11/13）───────────────────
# 背景（独立诊断实测）：scripts/fetch_authority.py 的 urlopen 是**单次**调用
#   （无 retry / attempt）⇒ 网络抖动时该次抓取直接失败。
#   同包其他通道有**跨通道**降级链（pubmed_mcp → pubmed_esearch），
#   但**同一条通道内部**没有重试 ⇒ 冗余编排缺一环（单点故障）。
# 参数唯一源 = config/external-tools.yaml#channels[pubmed_esearch].retry
#   （禁硬编码；缺配置时回落内置值并**显式告警**——静默回落 = 不设防）。

_RETRY_FALLBACK = {"max_attempts": 3, "backoff_base_sec": 1.0}


def _retry_spec(cfg=None):
    """取某通道的重试参数（**从 external-tools.yaml 读**，缺则回落并告警）。"""
    path = None
    try:
        import yaml as _yaml
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "config", "external-tools.yaml")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                data = _yaml.safe_load(f) or {}
            for ch in (data.get("channels") or []):
                if isinstance(ch, dict) and ch.get("id") == "pubmed_esearch":
                    r = ch.get("retry")
                    if isinstance(r, dict) and r:
                        return (int(r.get("max_attempts", 3) or 3),
                                float(r.get("backoff_base_sec", 1.0) or 1.0))
    except Exception as e:
        print(f"⚠ 读重试配置失败（{e}）→ 回落内置值 {_RETRY_FALLBACK}",
              file=sys.stderr)
    print(f"⚠ 未读到 pubmed_esearch.retry 配置 → 回落内置值 {_RETRY_FALLBACK}",
          file=sys.stderr)
    return (_RETRY_FALLBACK["max_attempts"], _RETRY_FALLBACK["backoff_base_sec"])


def _http_get_with_retry(url, timeout=15, headers=None, cfg=None):
    """带指数退避重试的 HTTP GET。返回 (响应字节, 尝试次数)；全失败抛最后一个异常。

    重试策略（**只重试值得重试的**）：
      · 可重试：urllib.error.URLError（含 socket.timeout / ConnectionError）、
        HTTPError 且 code ∈ {429, 5xx}
      · 不可重试：HTTPError 且 code 是其它 4xx（404/403 等——重试也不会成功）、
        以及其它异常（解析错误等，重试无意义）
    ⚠ 每次重试都往 **stderr** 留一行（降级必须可见），且不污染 stdout 的 JSON 输出。
    """
    import urllib.error
    import urllib.request
    max_attempts, backoff = _retry_spec(cfg)
    last_exc = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), attempt
        except urllib.error.HTTPError as e:
            last_exc = e
            retryable = (e.code == 429) or (500 <= e.code < 600)
            if not retryable or attempt >= max_attempts:
                # 挂上**实际尝试次数**——错误报文要用它，不能用配置值
                # （否则 404（只试 1 次）会报"重试 3 次后仍失败"，与事实不符）
                try:
                    e.attempts = attempt
                except Exception:
                    pass
                raise
            wait = backoff * (2 ** (attempt - 1))
            print(f"⚠ 第 {attempt} 次尝试失败（HTTP {e.code}）→ {wait:.1f}s 后重试"
                  f"（{attempt}/{max_attempts}）", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, OSError) as e:
            last_exc = e
            if attempt >= max_attempts:
                try:
                    e.attempts = attempt
                except Exception:
                    pass
                raise
            wait = backoff * (2 ** (attempt - 1))
            print(f"⚠ 第 {attempt} 次尝试失败（{type(e).__name__}: {str(e)[:60]}）"
                  f"→ {wait:.1f}s 后重试（{attempt}/{max_attempts}）", file=sys.stderr)
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError("重试耗尽且无异常记录——不应发生")


def _pubmed_esearch(pmid: str, timeout: int = 15) -> dict:
    """L1：PubMed esearch 存在性核验（复用包内既有口径：只判存在性，无元数据）。"""
    import urllib.request
    import urllib.error
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    url = f"{base}?db=pubmed&retmode=json&term={pmid}"
    try:
        # v3.21.0：改走带重试的取数（此前是单次 urlopen，网络抖动直接失败）
        raw, attempts = _http_get_with_retry(
            url, timeout=timeout,
            headers={"User-Agent": "vet-med-ppt-team/3.21.0"})
        j = json.loads(raw.decode("utf-8"))
        ids = (j.get("esearchresult") or {}).get("idlist") or []
        return {"channel": "pubmed_esearch", "pmid": pmid,
                "exists": bool(ids), "matched_ids": ids,
                "attempts": attempts,
                "capability": ["PMID 存在性核验"],
                "degraded": True,  # 相对 MCP 版能力降级
                "degraded_capability": ["元数据", "全文", "相关文献", "按引文反查"]}
    except urllib.error.HTTPError as e:
        # v3.21.0：错误信息带**实际尝试次数**（不是配置值）——
        #   404 这类不可重试的错误只试 1 次，报"重试 3 次"与事实不符。
        _att = getattr(e, "attempts", None)
        _tail = f"（尝试 {_att} 次后失败）" if _att else ""
        return {"channel": "pubmed_esearch", "pmid": pmid, "exists": None,
                "error": f"HTTP {e.code}{_tail}", "attempts": _att,
                "degraded": True,
                "degraded_capability": ["元数据", "全文", "相关文献", "按引文反查"]}
    except Exception as e:
        _att = getattr(e, "attempts", None)
        _tail = f"（尝试 {_att} 次后失败）" if _att else ""
        return {"channel": "pubmed_esearch", "pmid": pmid, "exists": None,
                "error": f"{type(e).__name__}: {str(e)[:80]}{_tail}",
                "attempts": _att,
                "degraded": True,
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

    # ── v3.23.0 F6：未给任何可执行通道输入 ⇒ **用法错误**，不是「全通道失败」────
    # 病灶（第三轮从零诊断 P-6，实测可复现）：
    #   `fetch_authority.py --purpose "..." --domain "..."`（脚本自述的常规用法）
    #   ⇒ results=[] / problems=[] / 退出码 **3（EXIT_ALL_FAILED）**，
    #   但**一个通道都没尝试过**（本脚本只在给了 --pmid / --source-json / --record
    #   时才真正执行）。⇒ 报「全通道失败」是**假失败**：与「网络故障」不可区分，
    #   会把人引向错误的排查方向（去查网络，而不是查用法）。
    if not args.pmid and not args.source_json and not args.record:
        if args.out:
            Path(args.out).expanduser().write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        log("⛔ 未给任何可执行通道的输入（--pmid / --source-json / --record 都没有）——"
            "这是**用法错误**，**不是**「全通道失败」。\n"
            "   → 只想看编排决策：加 --plan\n"
            "   → 想核验 PMID 存在性：加 --pmid <PMID>\n"
            "   → 想核验用户指定源：加 --source-json <文件>\n"
            "   → 会话层已执行的 L2 通道要回填：加 --record <文件>")
        return EXIT_USAGE

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

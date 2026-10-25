#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_channels.py — 外部 skill / MCP 通道可用性探针（v3.19.0 新增）

══════════════════════════════════════════════════════════════════════
立项依据（2026-10-25 第五次从零诊断·维度 10/11/13 实测）：
  · 包内 `preflight` **只查成员**（agentType 是否被平台回落），**不查任何外部通道**；
  · 包内对 `ima-mcp` / `mcp__pubmed` / `firecrawl` / `mcp__fetch` 的引用
    **全包 0 命中**——外部通道全是「文档里写过」，无一条代码路径能调；
  · Ima 凭据 `IMA_OPENAPI_CLIENTID` / `IMA_OPENAPI_APIKEY` 本机**未设置**
    ⇒ 域档案里 7 个库 ID 是**死数据**，且无任何检测会报出来。

本脚本的职责（**只判定与记账，不执行业务语义**）：
  ① 探测每条通道的可用性 → 三态（available / degraded / unavailable）；
  ② 探测 Ima 凭据与库可达性；
  ③ 产出 `replace_suggestions`（**主动提醒用户更换/更新**，管家节点裁决 #1）；
  ④ 产出 `scope_mismatches`（库/标准属其他专业 → 提醒更换，裁决 #4）。

★ 分层契约：MCP 工具是**宿主会话级**工具，脚本**无法**调用它们。
  故 MCP 通道的探针是「**声明式可达性检查**」：
    · 校验 tool 名符合 `mcp__<server>__<tool>` 形态；
    · 校验该 server 在本机 `~/.workbuddy/mcp.json` 中已登记（**只读**）；
    · 真实可用性由**会话层**（主理人/成员用 ToolSearch 实探）确认后回填。
  脚本**不得**伪造「已调用成功」。

退出码：
  0 = 全部通道可用 / 仅有降级（有 required 通道不可用时为 1）
  1 = 有 required 通道不可用，或有 scope 不匹配（阻断级）
  2 = 用法错误
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

STATUS_AVAILABLE = "available"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"

# MCP 工具名形态：mcp__<server>__<tool>
_MCP_TOOL_RE = re.compile(r"^mcp__([A-Za-z0-9_\-]+)__([A-Za-z0-9_\-]+)$")


def log(msg: str) -> None:
    """统一日志出口（stderr）。"""
    print(f"[probe_channels] {msg}", file=sys.stderr)


def _load_yaml(path: Path):
    """读 yaml；失败返回 (None, 错误说明)。"""
    try:
        import yaml
    except ImportError as e:
        return None, f"缺 PyYAML 依赖：{e}"
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f), None
    except FileNotFoundError:
        return None, f"文件不存在：{path}"
    except Exception as e:
        return None, f"yaml 解析失败：{e}"


def _mcp_servers() -> set:
    """读本机已登记的 MCP server 名（**只读**，不写不改）。"""
    p = Path(os.path.expanduser("~/.workbuddy/mcp.json"))
    if not p.is_file():
        return set()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return set()
    node = d.get("mcpServers")
    if not isinstance(node, dict):
        node = d if isinstance(d, dict) else {}
    return set(str(k) for k in node.keys())


def probe_http(endpoint: str, timeout: int = 8, method: str = "GET",
               use_range: bool = True) -> tuple[bool, str]:
    """HTTP 端点探针（只做可达性判断，不解析业务内容）。

    ⚠ **为什么默认 GET 而不是 HEAD**（实测 2026-10-25）：
      国图 OPAC 端点 `opac.nlc.cn/F/?func=find-b&...` 用 HEAD 请求返回
      `HTTP 000`（连接被对端直接关闭），而 GET 返回 `HTTP 200`（66KB）。
      ⇒ 用 HEAD 探活会把**可用端点误判为不可用**（假红与假绿同样有害）。

    ⚠ **Range 头的坑**（实测 2026-10-25）：
      OpenLibrary Search API 在带 `Range: bytes=0-1023` 时返回
      `URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING]>`，
      而**不带 Range** 完全正常（HTTP 200）⇒ Range 会让部分端点假失败。
      故：先带 Range 试，失败则**去掉 Range 重试一次**（两次都失败才判不可用）。
    """
    if not endpoint:
        return False, "端点为空"
    import urllib.request
    import urllib.error
    attempts = [True, False] if (method.upper() == "GET" and use_range) else [False]
    last_err = ""
    for with_range in attempts:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; vet-med-ppt-team/3.19.0)"}
            if with_range:
                headers["Range"] = "bytes=0-1023"
            req = urllib.request.Request(endpoint, method=method.upper(), headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return True, f"HTTP {r.status}（{method.upper()} 端点可达）"
        except urllib.error.HTTPError as e:
            # 4xx/5xx 都说明**端点可达**（只是本次请求不成功）
            return True, f"HTTP {e.code}（端点可达）"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            continue
    return False, f"不可达：{last_err}"


def resolve_endpoint_ref(cfg: dict, ref: str, domain_id: str = "") -> tuple[str, str]:
    """解析 endpoint_ref（点路径）→ (实际端点, 错误说明)。

    支持的形态：
      · `文件相对路径#点路径` —— 如 `config/domain_config.yaml#three_source_check.source_verification.pubmed`
        · 点路径末段若解析出 **dict**，自动取其 `endpoint` 子键
          （实测：domain_config.yaml 的 `...verification.pubmed` 段是 dict，端点在其 `endpoint` 键）
      · `文件相对路径#列表通配.子路径` —— 如 `config/domain-profiles.yaml#domains[].image_channel.channels[].endpoint`
        · `[]` 表示"遍历列表，对每项解析子路径"；
        · **传了 `domain_id` 时，优先取列表中 `id == domain_id` 的那一项**（逐域端点）；
          没有匹配则回落到"第一个能解析出端点的项"。

    返回 (端点字符串, 错误说明)。
    """
    if not ref:
        return "", "endpoint_ref 为空"
    if "#" not in ref:
        return ref, ""
    rel, path = ref.split("#", 1)
    f = PKG / rel
    if not f.is_file():
        return "", f"引用文件不存在：{rel}"
    data, err = _load_yaml(f)
    if err:
        return "", err

    def _walk(node, segs, errs):
        """在 node 上按 segs 逐段下降；遇 list 通配则遍历收集。"""
        if not segs:
            return [node]
        seg = segs[0]
        rest = segs[1:]
        # 列表通配：seg 形如 "domains[]" 或 "domains"
        if seg.endswith("[]"):
            key = seg[:-2]
            if isinstance(node, dict) and isinstance(node.get(key), list):
                out = []
                for item in node[key]:
                    out += _walk(item, rest, errs)
                return out
            errs.append(f"引用路径未命中列表：{key}")
            return []
        if isinstance(node, list):
            # 形如 "items.id" 的列表：取 id 匹配项
            if len(rest) >= 1 and rest[0] in ("id", "name"):
                hit = next((x for x in node if isinstance(x, dict) and x.get(rest[0]) == seg), None)
                if hit is None:
                    errs.append(f"引用路径未命中列表项：{seg}")
                    return []
                return _walk(hit, rest[1:], errs)
            errs.append(f"引用路径不支持列表直取：{seg}")
            return []
        if isinstance(node, dict):
            if seg not in node:
                errs.append(f"引用路径未命中：{seg}")
                return []
            return _walk(node[seg], rest, errs)
        errs.append(f"引用路径类型不支持：{seg}")
        return []

    errs = []
    segs = [s for s in path.split(".") if s]
    results = _walk(data, segs, errs)
    if not results:
        return "", "；".join(errs) or f"引用路径未解析：{path}"

    def _to_endpoint(r):
        """把一个解析结果转成端点字符串。

        覆盖 4 种形态（实测自本包真实配置）：
          ① 字符串本身
          ② dict 的 `endpoint` 键        —— domain_config.yaml 的 `...verification.pubmed`
          ③ dict 的 `url` 键            —— 同上 `textbook.endpoints[]` 里的条目
          ④ dict 的 `endpoints` 列表 → 取其中第一个含 url/endpoint 的条目
        """
        if isinstance(r, str) and r:
            return r
        if isinstance(r, dict):
            for k in ("endpoint", "url"):
                if isinstance(r.get(k), str) and r[k]:
                    return r[k]
            eps = r.get("endpoints")
            if isinstance(eps, list):
                for e in eps:
                    ep = _to_endpoint(e)
                    if ep:
                        return ep
        return ""

    def _all_endpoints(r):
        """收集一个解析结果里的**全部**候选端点（多端点择可用时用）。"""
        out = []
        if isinstance(r, str) and r:
            out.append(r)
        elif isinstance(r, dict):
            for k in ("endpoint", "url"):
                if isinstance(r.get(k), str) and r[k]:
                    out.append(r[k])
            eps = r.get("endpoints")
            if isinstance(eps, list):
                for e in eps:
                    out += _all_endpoints(e)
        return out

    # ① 按域优先：列表通配时若某项的 id == domain_id，优先用它的端点
    if domain_id and len(results) > 1:
        for r in results:
            if isinstance(r, dict) and str(r.get("id") or "") == domain_id:
                ep = _to_endpoint(r)
                if ep:
                    return ep, ""
    # ② 取第一个能变成端点字符串的
    for r in results:
        ep = _to_endpoint(r)
        if ep:
            return ep, ""
    return "", (f"引用路径未解析出端点字符串：{path}"
                + (f"（命中 {len(results)} 项但均无 endpoint）" if len(results) > 1 else ""))


def resolve_endpoint_candidates(cfg: dict, ref: str, domain_id: str = "") -> list:
    """解析出**全部**候选端点（多端点择可用时用）。

    实测背景：domain_config.yaml 的 `textbook.endpoints[]` 有两个端点——
      ① 国图 OPAC（`opac.nlc.cn`）——**不稳定**：2026-10-25 实测同一 URL
         第一次 GET 200(66KB)、第二次 RemoteDisconnected、curl 也 000；
      ② OpenLibrary Search API——**稳定 200**。
    ⇒ 探针必须**逐个试**，取第一个可达的，而不是固定取第一个。
    """
    if not ref or "#" not in ref:
        return [ref] if ref else []
    rel, path = ref.split("#", 1)
    f = PKG / rel
    if not f.is_file():
        return []
    data, err = _load_yaml(f)
    if err:
        return []
    segs = [s for s in path.split(".") if s]
    errs = []

    def _walk(node, rest, errs):
        if not rest:
            return [node]
        seg, tail = rest[0], rest[1:]
        if seg.endswith("[]"):
            key = seg[:-2]
            if isinstance(node, dict) and isinstance(node.get(key), list):
                out = []
                for item in node[key]:
                    out += _walk(item, tail, errs)
                return out
            errs.append(f"未命中列表：{key}")
            return []
        if isinstance(node, list):
            if tail and tail[0] in ("id", "name"):
                hit = next((x for x in node if isinstance(x, dict) and x.get(tail[0]) == seg), None)
                return _walk(hit, tail[1:], errs) if hit is not None else []
            return []
        if isinstance(node, dict):
            if seg not in node:
                errs.append(f"未命中：{seg}")
                return []
            return _walk(node[seg], tail, errs)
        return []

    results = _walk(data, segs, errs)

    def _all(r):
        out = []
        if isinstance(r, str) and r:
            out.append(r)
        elif isinstance(r, dict):
            for k in ("endpoint", "url"):
                if isinstance(r.get(k), str) and r[k]:
                    out.append(r[k])
            eps = r.get("endpoints")
            if isinstance(eps, list):
                for e in eps:
                    out += _all(e)
        return out

    cands = []
    for r in results:
        cands += _all(r)
    return cands


def probe_ima(ima_cfg: dict, domain_id: str) -> dict:
    """探测 Ima 通道：凭据 + skill 目录 + 库归属。"""
    out = {"status": STATUS_AVAILABLE, "detail": "", "credentials": False,
           "skill_found": None, "libraries": {}, "scope_mismatches": []}

    # ① 凭据（真值只从环境变量读）
    envs = ima_cfg.get("credentials_env") or []
    missing = [e for e in envs if not os.environ.get(e)]
    out["credentials"] = not missing
    if missing:
        out["detail"] = (f"凭据缺失（{', '.join(missing)}）——降级走联网现查机构权威源"
                         f"，**降级须向用户声明**")
        out["status"] = STATUS_DEGRADED

    # ② skill 目录（Ima 是 skill 形态，不是 MCP）
    found = None
    for cand in (ima_cfg.get("skill_dir_candidates") or []):
        p = Path(os.path.expanduser(cand))
        if p.is_dir():
            found = str(p)
            break
    out["skill_found"] = found
    if not found:
        out["status"] = STATUS_UNAVAILABLE
        out["detail"] = (out["detail"] + "；" if out["detail"] else "") + \
            "未找到 Ima skill 目录（候选：" + \
            ", ".join(ima_cfg.get("skill_dir_candidates") or []) + "）"

    # ③ 库归属核对（裁决 #4：仅动物医学专业；其他域必须提醒更换）
    kbs = ima_cfg.get("_knowledge_bases") or []
    for kb in kbs:
        kid = str(kb.get("id") or "")
        scope = str(kb.get("owner_scope") or "")
        if scope and domain_id and scope != domain_id:
            out["scope_mismatches"].append({
                "library_id": kid, "library_name": kb.get("name"),
                "owner_scope": scope, "current_domain": domain_id,
                "reason": f"库「{kb.get('name')}」属 {scope} 专业，当前任务域为 {domain_id}",
            })
    return out


def probe_channels(cfg: dict, domain_id: str = "") -> dict:
    """探测全部通道 + 产出主动提醒。返回结构见模块 docstring。"""
    channels = cfg.get("channels") or []
    servers = _mcp_servers()
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "domain_id": domain_id,
        "verdict": "ok",
        "channels": {},
        "knowledge_bases": {},
        "replace_suggestions": [],
        "scope_mismatches": [],
    }

    for ch in channels:
        cid = str(ch.get("id") or "")
        kind = ch.get("kind")
        item = {"kind": kind, "layer": ch.get("layer"),
                "priority": ch.get("priority", 99),
                "capability": ch.get("capability") or [],
                "status": STATUS_UNAVAILABLE, "detail": ""}
        if kind == "mcp_tool":
            tool = str(ch.get("tool") or "")
            m = _MCP_TOOL_RE.match(tool)
            if not m:
                item["detail"] = f"工具名不合形态（应为 mcp__<server>__<tool>）：{tool!r}"
            elif m.group(1) not in servers:
                item["detail"] = (f"MCP server {m.group(1)!r} 未在本机 mcp.json 登记"
                                  f"——通道不可用")
            else:
                # 声明式可达：server 已登记 + 工具名合法
                item["status"] = STATUS_AVAILABLE
                item["detail"] = (f"server {m.group(1)!r} 已登记；"
                                  f"**真实可用性待会话层 ToolSearch 实探确认**")
                item["probe_mode"] = "declarative"
        elif kind == "http":
            cands = resolve_endpoint_candidates(cfg, str(ch.get("endpoint_ref") or ""),
                                                domain_id=domain_id)
            if not cands:
                item["detail"] = (f"引用未解析出任何端点：{ch.get('endpoint_ref')!r}")
            else:
                # 端点模板含占位符（如 {PMCID}/{isbn}）⇒ 探针用 probe_value 替换后判可达性
                ph = str(ch.get("endpoint_placeholder") or "")
                pv = str(ch.get("probe_value") or "")
                method = str(ch.get("method") or "GET")
                tried = []
                ok = False
                detail = ""
                used = ""
                for cand in cands:
                    probe_ep = cand.replace(ph, pv) if ph else cand
                    o, d = probe_http(probe_ep, method=method)
                    tried.append({"endpoint": cand, "ok": o, "detail": d})
                    if o:
                        ok, detail, used = True, d, cand
                        break
                    detail = d
                item["candidates_tried"] = tried
                if ok:
                    item["status"] = STATUS_AVAILABLE
                    item["detail"] = detail + (f"（共试 {len(tried)} 个候选端点）"
                                               if len(tried) > 1 else "")
                    item["endpoint"] = used
                    item["probe_endpoint"] = used.replace(ph, pv) if ph else used
                    if len(tried) > 1:
                        item["fallback_used"] = True
                        item["degraded"] = True
                else:
                    item["status"] = STATUS_UNAVAILABLE
                    item["detail"] = f"全部 {len(tried)} 个候选端点不可达；最后错误：{detail}"
                item["probe_mode"] = "http"
        else:
            item["detail"] = f"未知通道 kind：{kind!r}"
        report["channels"][cid] = item

    # ── Ima 通道 ──────────────────────────────────────────────
    ima_cfg = cfg.get("ima") or {}
    if ima_cfg:
        # 把 knowledge_bases 挂进 ima_cfg 便于统一处理（不写回 yaml）
        ima_cfg = dict(ima_cfg)
        ima_cfg["_knowledge_bases"] = cfg.get("knowledge_bases") or []
        ima_report = probe_ima(ima_cfg, domain_id)
        report["knowledge_bases"] = ima_report
        report["scope_mismatches"] = ima_report.get("scope_mismatches") or []
        if ima_report["status"] == STATUS_UNAVAILABLE:
            report["channels"]["ima"] = {
                "kind": "skill", "layer": "L2", "priority": 1,
                "capability": ["知识库检索"], "status": STATUS_UNAVAILABLE,
                "detail": ima_report.get("detail", ""),
            }

    # ── 主动提醒（管家节点裁决 #1：可灵活选择与配置，主动提醒更换/更新）──
    # ① 库属其他专业（裁决 #4）
    for m in report["scope_mismatches"]:
        report["replace_suggestions"].append({
            "kind": "scope_mismatch",
            "severity": "block",
            "target": m.get("library_name"),
            "detail": (f"{m.get('reason')}——请更换/更新为你所在专业的知识库"
                       f"（**不得静默使用其他专业的库**）"),
        })
    # ② 域无账号内知识库 → 提醒换库
    for d in (cfg.get("domains_without_knowledge_bases") or []):
        if domain_id and d.get("id") == domain_id:
            report["replace_suggestions"].append({
                "kind": "domain_without_knowledge_bases",
                "severity": "warn",
                "target": d.get("id"),
                "detail": f"{d.get('reminder')}（本域通用兜底：{d.get('fallback')}）",
            })
    # ③ 凭据缺失 → 提示可降级
    if (report.get("knowledge_bases") or {}).get("credentials") is False:
        report["replace_suggestions"].append({
            "kind": "credentials_missing",
            "severity": "warn",
            "target": "ima",
            "detail": ("Ima 凭据未设置——知识库检索通道降级（改走联网现查机构权威源）；"
                       "如需恢复库检索请配置 " + ", ".join(ima_cfg.get("credentials_env") or [])),
        })
    # ④ 用户可更换的库（常驻提示）
    for kb in (cfg.get("knowledge_bases") or []):
        if kb.get("replaceable"):
            report["replace_suggestions"].append({
                "kind": "replaceable",
                "severity": "info",
                "target": kb.get("name"),
                "detail": ("该库可由用户替换/更新"
                           + (f"（当前：{kb.get('update_policy')}）" if kb.get("update_policy") else "")
                           + (f"｜导航：{kb.get('share_url')}" if kb.get("share_url") else "")),
            })

    # ── 判据：required 通道不可用 或 scope 不匹配 → 阻断级 ──
    blocking = [c for c, v in report["channels"].items() if v.get("status") == STATUS_UNAVAILABLE]
    if blocking or report["scope_mismatches"]:
        report["verdict"] = "degraded"
    elif any(v.get("status") == STATUS_DEGRADED for v in report["channels"].values()):
        report["verdict"] = "degraded"
    report["unavailable_channels"] = blocking
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description="外部 skill / MCP 通道可用性探针 + 主动提醒更换")
    ap.add_argument("--config", default=str(PKG / "config" / "external-tools.yaml"),
                    help="外部工具配置路径（默认：包内 config/external-tools.yaml）")
    ap.add_argument("--domain", default="", help="当前任务域 id（用于库归属核对）")
    ap.add_argument("--json", default="", help="结果写入 JSON 文件路径")
    ap.add_argument("--quiet", action="store_true", help="不打印人类可读摘要")
    args = ap.parse_args()

    cfg, err = _load_yaml(Path(args.config).expanduser())
    if err:
        log(f"⛔ {err}")
        return 2
    report = probe_channels(cfg or {}, args.domain)

    if args.json:
        p = Path(args.json).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)

    if not args.quiet:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sugg = report.get("replace_suggestions") or []
        if sugg:
            print("", file=sys.stderr)
            print("── 主动提醒（可配置/可更换）──", file=sys.stderr)
            for s in sugg:
                print(f"  [{s.get('severity')}] {s.get('target')}：{s.get('detail')}",
                      file=sys.stderr)

    # 退出码：有 required 通道不可用 或 scope 不匹配 → 1
    if report.get("unavailable_channels") or report.get("scope_mismatches"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

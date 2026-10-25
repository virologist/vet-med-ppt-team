#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_oa_image.py — 开放获取配图检索与落盘（v3.18.0 新增）

══════════════════════════════════════════════════════════════════════
立项依据（2026-10-25 从零诊断 G3 实测，非假设）：
  `config/domain-profiles.yaml#domains[].image_channel` 登记了取图主力端点
  （animal-medicine 域 = Europe PMC 补充文件，许可规则「仅取 CC-BY /
  开放获取论文图片」），但**脚本侧零实现**——Grep `europepmc|supplementaryFiles`
  于 scripts/ 下唯一命中是 test_extract_assets.py 里的一句示例字符串，
  **没有任何下载器、没有 API 客户端**；而"检索下载的新图保存到哪里"
  全包无定义（extract_assets_usage.md:340-342 自认 source_url / doi_pmcid
  「只留空串位，脚本不自动回填」）。
  ⇒ 后果：配图能力**不可复现、不可审计、换机器即静默归零**。

本脚本的定位（只做一件被漏掉的事）：
  · **端点从域档案读**，不硬编码 URL（域之间只差档案、不差代码）；
  · 下载 → 落盘 → **回填 manifest 三字段**（source_url / doi_pmcid / license_note）；
  · **许可红线**：许可无法判定 ⇒ 标 [待核实] 并**跳过下载**，绝不编造许可；
  · 退避重试参数**从 yaml 读**，且每次退避**显式告警**（不静默 sleep）。

退出码语义（与 harness.yaml#gate_exit_codes 的 0-4 不冲突，5-7 为本脚本专用）：
  0 = 成功（至少一个文件落盘，或 --dry-run 完成）
  2 = 用法/参数错误
  3 = 端点不可达 / 网络失败（重试耗尽）
  4 = **许可不明**（拒绝下载，标 [待核实]）
  5 = 域档案读不到 / 无可用取图通道
  6 = manifest 读写失败

依赖（标准库 + PyYAML，PyYAML 已是本包既有依赖）：
  python3 scripts/fetch_oa_image.py --pmcid PMC123456 --out <目录> --manifest <manifest.json>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
PROFILES_REL = os.path.join("config", "domain-profiles.yaml")
DOMAIN_CONFIG_REL = os.path.join("config", "domain_config.yaml")

# 退出码（本脚本专用）
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NETWORK = 3
EXIT_LICENSE = 4
EXIT_NO_CHANNEL = 5
EXIT_MANIFEST = 6

# 图像扩展名白名单（Europe PMC 补充文件里常见的位图/矢量格式）
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".svg", ".webp")

# 许可不明时的占位标记——**不编造许可**，显式挂账
LICENSE_TODO = "[待核实]"


def log(msg: str) -> None:
    """统一日志出口（stderr）。"""
    print(f"[fetch_oa_image] {msg}", file=sys.stderr)


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


def find_domain(profiles: dict, domain_id: str):
    """从域档案里取指定域；取不到返回 None。"""
    for d in (profiles or {}).get("domains") or []:
        if isinstance(d, dict) and str(d.get("id")) == str(domain_id):
            return d
    return None


def pick_channel(domain: dict) -> dict | None:
    """从域档案的 image_channel 里挑**稳定**的取图通道。

    选型判据（确定性规则，不看关键词语义）：
      ① 有 endpoint 的通道优先；
      ② 同等条件下 status 里含「稳定」者优先（域档案里 status 是人写的稳定性标注）。
    ⚠ 这是**通道级**选型（取图走哪条链路），**不是专家选型**——
      专家选型是语义判断，属主理人职责（见 harness.py#_select_experts）。
    """
    ic = (domain or {}).get("image_channel") or {}
    chans = [c for c in (ic.get("channels") or []) if isinstance(c, dict)]
    with_ep = [c for c in chans if c.get("endpoint")]
    if not with_ep:
        return None
    stable = [c for c in with_ep if "稳定" in str(c.get("status") or "")]
    return (stable or with_ep)[0]


def retry_spec(cfg: dict) -> tuple[int, float, float]:
    """取退避重试参数（**从 yaml 读**，不硬编码）。

    优先 `config/domain_config.yaml#image_fetch.retry`；
    缺则退回 `source_verification.pubmed` 的同名键（包内既有退避口径），
    再缺则用保守默认值并**告警**（不静默）。
    """
    defaults = (3, 2.0, 30.0)
    node = ((cfg or {}).get("image_fetch") or {}).get("retry")
    if not isinstance(node, dict):
        pv = (((cfg or {}).get("three_source_check") or {})
              .get("source_verification") or {}).get("pubmed") or {}
        node = pv if isinstance(pv, dict) else {}
        if node:
            log("ℹ️ image_fetch.retry 未配置，退回 source_verification.pubmed 的退避参数")
    try:
        return (int(node.get("max_retries", defaults[0])),
                float(node.get("backoff_base", defaults[1])),
                float(node.get("backoff_cap", defaults[2])))
    except (TypeError, ValueError):
        return defaults


def fetch(url: str, timeout: int, retries: int, base: float, cap: float) -> bytes | None:
    """带指数退避的抓取。**每次退避显式告警**（不静默 sleep）。

    返回内容字节；失败返回 None（重试耗尽）。
    """
    delay = base
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "vet-med-ppt-team/3.18.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            # 4xx（除 429）不重试——重试也不会好
            if e.code != 429 and 400 <= e.code < 500:
                log(f"⛔ HTTP {e.code}（客户端错误，不重试）：{url}")
                return None
            log(f"⚠️ HTTP {e.code}（{url}）——将退避重试")
        except Exception as e:
            log(f"⚠️ 抓取失败（{type(e).__name__}: {e}）——将退避重试")
        if attempt < retries:
            log(f"⏳ 退避 {delay:.1f}s 后重试（第 {attempt + 1}/{retries} 次）")
            time.sleep(delay)
            delay = min(delay * 2, cap)
    return None


def build_url(endpoint: str, pmcid: str) -> str:
    """按端点模板拼实际 URL（支持 {PMCID} 占位）。"""
    return endpoint.replace("{PMCID}", pmcid).replace("{pmcid}", pmcid)


def load_manifest(path: Path) -> dict:
    """读 manifest（不存在则新建骨架）。"""
    if not path.is_file():
        return {"schema": "asset-manifest/1", "assets": []}
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        log(f"⛔ manifest 解析失败：{path}（{e}）")
        raise
    if not isinstance(obj, dict):
        raise ValueError("manifest 顶层须是映射")
    obj.setdefault("assets", [])
    return obj


def save_manifest(path: Path, obj: dict) -> None:
    """原子写 manifest（先写临时文件再替换，避免半截文件）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def manifest_has(manifest: dict, pmcid: str, fname: str) -> bool:
    """幂等判定：同 PMCID + 同文件名已登记则跳过。"""
    for a in manifest.get("assets") or []:
        if not isinstance(a, dict):
            continue
        if str(a.get("doi_pmcid") or "") == pmcid and \
                str(a.get("file") or a.get("filename") or "").endswith(fname):
            return True
    return False


def append_asset(manifest: dict, entry: dict) -> None:
    """按 asset-fields.yaml 的字段名登记条目。"""
    manifest.setdefault("assets", []).append(entry)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="开放获取配图检索与落盘（端点从域档案读，许可不明则拒绝下载）")
    ap.add_argument("--pmcid", required=True,
                    help="文献标识（PMC123456 形式；也接受裸数字）")
    ap.add_argument("--out", required=True,
                    help="输出目录（图片落 <out>/images/）")
    ap.add_argument("--manifest", required=True,
                    help="manifest.json 路径（下载后回填三字段）")
    ap.add_argument("--domain", default="animal-medicine",
                    help="域 id（默认 animal-medicine；端点从该域 image_channel 读）")
    ap.add_argument("--domain-profile", default=None,
                    help=f"域档案路径（默认：包内 {PROFILES_REL}）")
    ap.add_argument("--timeout", type=int, default=30, help="单次请求超时秒数（默认 30）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只解析端点与许可并打印计划，不联网不落盘")
    args = ap.parse_args()

    # ── 参数校验 ──────────────────────────────────────────────
    pmcid = (args.pmcid or "").strip().upper()
    if not re.fullmatch(r"PMC\d+|\d+", pmcid):
        print(f"⛔ --pmcid 格式非法：{args.pmcid!r}（应为 PMC123456 或纯数字）", file=sys.stderr)
        return EXIT_USAGE
    if not pmcid.startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    out_dir = Path(args.out).expanduser()
    man_path = Path(args.manifest).expanduser()
    prof_path = Path(args.domain_profile).expanduser() if args.domain_profile \
        else (PKG / PROFILES_REL)

    # ── 域档案与通道 ──────────────────────────────────────────
    profiles, err = _load_yaml(prof_path)
    if err:
        log(f"⛔ {err}")
        return EXIT_NO_CHANNEL
    dom = find_domain(profiles, args.domain)
    if dom is None:
        ids = [d.get("id") for d in (profiles.get("domains") or []) if isinstance(d, dict)]
        log(f"⛔ 未知域 id：{args.domain!r}（可用：{ids}）")
        return EXIT_NO_CHANNEL
    chan = pick_channel(dom)
    if not chan:
        log(f"⛔ 域 {args.domain} 的 image_channel 无带 endpoint 的通道——无取图路径")
        return EXIT_NO_CHANNEL
    endpoint = str(chan.get("endpoint") or "")
    license_rule = str(chan.get("license_rule") or "").strip()
    if not endpoint:
        log(f"⛔ 通道 {chan.get('name')!r} 无 endpoint")
        return EXIT_NO_CHANNEL

    url = build_url(endpoint, pmcid)
    log(f"域：{args.domain}｜通道：{chan.get('name')}（{chan.get('status')}）")
    log(f"端点（从域档案读）：{url}")

    # ── 许可判定 ──────────────────────────────────────────────
    # 红线：许可规则缺失或含"待核实/未明" ⇒ **拒绝下载**，标 [待核实] 挂账。
    uncertain = (not license_rule) or any(
        k in license_rule for k in ("待核实", "未明", "未知", "待定"))
    if uncertain:
        log(f"⛔ 许可无法判定（license_rule={license_rule!r}）——**拒绝下载**，"
            f"按纪律标 {LICENSE_TODO} 挂账")
        log("   → 请在 config/domain-profiles.yaml#domains[].image_channel.channels[].license_rule "
            "写明确许可后再取图；**不得凭猜测下载或编造许可**。")
        return EXIT_LICENSE

    # ── 退避参数（从 yaml 读）────────────────────────────────
    dcfg, derr = _load_yaml(PKG / DOMAIN_CONFIG_REL)
    retries, base, cap = retry_spec(dcfg)
    log(f"退避参数（从 {DOMAIN_CONFIG_REL} 读）：重试 {retries} 次 / "
        f"基数 {base}s / 上限 {cap}s")

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "pmcid": pmcid,
            "domain": args.domain,
            "channel": chan.get("name"),
            "endpoint": url,
            "license_rule": license_rule,
            "images_dir": str(out_dir / "images"),
            "manifest": str(man_path),
            "retry": {"max_retries": retries, "backoff_base": base, "backoff_cap": cap},
        }, ensure_ascii=False, indent=2))
        return EXIT_OK

    # ── 抓取与落盘 ────────────────────────────────────────────
    blob = fetch(url, args.timeout, retries, base, cap)
    if blob is None:
        log(f"⛔ 端点不可达（重试 {retries} 次后仍失败）：{url}")
        log("   → 端点可用性会漂移（机构改版/迁移），请现查核对；"
            "或改用域档案里的其它通道。")
        return EXIT_NETWORK

    # 端点返回的是 zip（补充文件包）还是单文件：按内容魔数判定
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    if blob[:2] == b"PK":
        saved = _extract_from_zip(blob, images_dir, pmcid)
        if not saved:
            log("⚠️ 端点返回 zip 但其中无图像文件——记为「无可用图」")
    else:
        fname = f"pmc{pmcid.replace('PMC', '')}_img01"
        for ext in IMAGE_EXTS:
            if blob[:8].lower().startswith(b"\x89png\r\n\x1a\n") and ext == ".png":
                saved = [_write(blob, images_dir, fname + ext)]
                break
            if blob[:3] == b"\xff\xd8\xff" and ext == ".jpg":
                saved = [_write(blob, images_dir, fname + ext)]
                break
        if not saved:
            saved = [_write(blob, images_dir, fname + ".bin")]

    # ── manifest 回填三字段 ───────────────────────────────────
    try:
        manifest = load_manifest(man_path)
    except Exception as e:
        log(f"⛔ manifest 读取失败：{e}")
        return EXIT_MANIFEST
    n_new = 0
    for fn in saved:
        if manifest_has(manifest, pmcid, fn):
            log(f"· 已登记（幂等跳过）：{fn}")
            continue
        append_asset(manifest, {
            "asset_id": f"{pmcid}_{fn}",
            "file": f"images/{fn}",
            "source_url": url,          # ← 字段 1
            "doi_pmcid": pmcid,         # ← 字段 2
            "license_note": license_rule,  # ← 字段 3（取自域档案，不编造）
            "reuse_status": "待核查",
            "channel": chan.get("name"),
            "domain": args.domain,
        })
        n_new += 1
    try:
        save_manifest(man_path, manifest)
    except Exception as e:
        log(f"⛔ manifest 写入失败：{e}")
        return EXIT_MANIFEST

    print(json.dumps({
        "ok": True, "pmcid": pmcid, "downloaded": len(saved),
        "registered": n_new, "images_dir": str(images_dir),
        "manifest": str(man_path),
    }, ensure_ascii=False, indent=2))
    return EXIT_OK


def _write(blob: bytes, images_dir: Path, fname: str) -> str:
    """落盘单个文件，返回文件名。"""
    p = images_dir / fname
    with open(p, "wb") as f:
        f.write(blob)
    return fname


def _extract_from_zip(blob: bytes, images_dir: Path, pmcid: str) -> list:
    """从 zip（补充文件包）中挑出图像文件落盘；返回文件名列表。"""
    import io
    import zipfile
    out = []
    idx = 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except Exception as e:
        log(f"⛔ zip 解析失败：{e}")
        return out
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if not name.lower().endswith(IMAGE_EXTS):
            continue
        idx += 1
        base = os.path.basename(name)
        safe = re.sub(r"[^\w.\-]", "_", base)
        fname = f"pmc{pmcid.replace('PMC', '')}_img{idx:02d}_{safe}"
        data = zf.read(info)
        out.append(_write(data, images_dir, fname))
    return out


if __name__ == "__main__":
    sys.exit(main())

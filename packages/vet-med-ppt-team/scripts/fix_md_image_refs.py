#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_md_image_refs.py — Markdown 图片引用修复器（v3.8.2 新增）

> 立项目的：`references/round-review-sop.md#2.1` 要求"markitdown 输出的图片链接需重写为
>   <wip>/_assets/ 下的实际路径；无法对应的图显式列为'引用缺失'，不得留空链接或用占位图"，
>   但 extract_assets.py 无此参数、仓库内也无对应实现——协议要求的能力长期悬空。本脚本补齐该能力。

实测基线（2026-10-22，合成样本 demo.pptx：2 页 3 图，markitdown 0.1.7）：
  - markitdown 0.1.7 对 PPTX 的输出形如：
        <!-- Slide number: 1 -->
        ![img1.png](Picture1.jpg)
    即 ① 有页号注释可定位归属页；② 链接 target 是**不存在的文件**（形如 Picture1.jpg，
    页内重新编号，跨页会重名），alt 为原始文件名。
  - extract_assets manifest 的 assets 数组按 (source_page, 页内形状顺序) 排列，
    与 markitdown 逐页顺序一致 → 可用「页号 + 页内序号」精确配对。
  - 上述两点均为本脚本的配对依据；**未实测的格式请按未匹配处理并显式上报，不猜测**。

配对策略（按可信度降序）：
  1. sha256：当 md 中的 target 文件在磁盘上真实存在时，取其 sha256 与候选资产比对——命中即为最强证据
  2. 页号+页内序号：默认策略，依据上面的实测基线
  3. 无法配对 → 显式列入 missing（引用缺失），**保留原 ref 文本并加标记**，绝不留空链接或占位图

三方计数核验（可选 --deck）：逐页比对「原 PPTX 图片形状数 / md 引用数 / manifest 资产数」，
  不一致即记入 mismatches——用于发现 markitdown 漏出图或 extract_assets 漏抽图。

退出码（与 harness.py 统一）：
  0 全部引用已解析，无孤立资产，无计数不一致
  1 存在未决项（引用缺失 / 孤立资产 / 三方计数不一致）——须人工处置，不得当作通过
  2 用法错误（--out 与 --md 相同 / 缺参数 / 参数非法）
  3 文件读取失败（md / manifest / assets 不存在）
  4 运行错误（脚本 bug / 依赖缺失）

CLI：
  python3 fix_md_image_refs.py --md <original.md> --manifest <manifest.json>
       --out <original.refs.md> [--assets-dir DIR] [--deck <原.pptx>]
       [--types image,video] [--link-mode relative|absolute]
       [--report <report.json>] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ============== 日志（INFO/ERROR 双级，不 silent）==============
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fix_md_image_refs")

# md 图片引用：`![alt](target)`（允许带 title）
RE_IMG = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# HTML 兜底：<img src="...">
RE_HTML_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
# markitdown 页号注释：`<!-- Slide number: 1 -->`
RE_SLIDE = re.compile(r"<!--\s*Slide number:\s*(\d+)\s*-->")

SCHEMA_VERSION = "fix_md_image_refs/1.0.0"
DEFAULT_TYPES = ("image", "video")
MISSING_MARK = "引用缺失"


# ============== 数据结构 ==============
class Ref:
    """md 中的一条图片引用。"""

    __slots__ = ("line_no", "page", "index_in_page", "alt", "target", "raw")

    def __init__(self, line_no, page, index_in_page, alt, target, raw):
        self.line_no = line_no
        self.page = page
        self.index_in_page = index_in_page
        self.alt = alt
        self.target = target
        self.raw = raw

    def to_dict(self):
        return {
            "line_no": self.line_no,
            "page": self.page,
            "index_in_page": self.index_in_page,
            "alt": self.alt,
            "target": self.target,
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ============== 解析：md → 引用清单（带页归属）==============
def parse_md_refs(md_text: str) -> tuple[list[Ref], list[str]]:
    """解析 md，返回（引用清单，解析告警）。页号来自 markitdown 的 Slide number 注释。"""
    refs: list[Ref] = []
    warns: list[str] = []
    page = 0              # 0 = 首个页号注释之前（未归属）
    per_page_counter: dict[int, int] = {}

    for line_no, line in enumerate(md_text.splitlines(), start=1):
        m_slide = RE_SLIDE.search(line)
        if m_slide:
            page = int(m_slide.group(1))
            continue

        targets: list[tuple[str, str]] = []  # (alt, target)
        for m in RE_IMG.finditer(line):
            targets.append((m.group(1), m.group(2)))
        for m in RE_HTML_IMG.finditer(line):
            targets.append(("", m.group(1)))

        for alt, target in targets:
            idx = per_page_counter.get(page, 0)
            per_page_counter[page] = idx + 1
            refs.append(Ref(line_no, page, idx, alt, target, line))
            if page == 0:
                warns.append(
                    f"第 {line_no} 行的引用出现在首个 Slide number 注释之前，无法归属页号"
                )
    if not refs:
        warns.append("md 中未解析到任何图片引用（确认是否用了 markitdown 的 PPTX 转换通道）")
    return refs, warns


# ============== 装载：manifest → 按页分组的可视资产 ==============
def load_manifest_assets(manifest_path: Path, types: tuple[str, ...]) -> tuple[dict, dict]:
    """返回 (按页分组的资产列表, manifest 元信息)。页内顺序沿用 manifest 数组顺序。"""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    by_page: dict[int, list[dict]] = {}
    for a in manifest.get("assets", []):
        if a.get("type") not in types:
            continue
        if not a.get("file"):
            continue
        by_page.setdefault(int(a.get("source_page", 0)), []).append(a)
    meta = {
        "source_deck": manifest.get("source_deck", ""),
        "source_deck_sha1": manifest.get("source_deck_sha1", ""),
        "extractor_version": manifest.get("extractor_version", ""),
        "total_slides": manifest.get("total_slides"),
    }
    return by_page, meta


# ============== 可选：原 PPTX 逐页图片形状计数（三方核验）==============
def count_deck_images_by_page(deck_path: Path) -> dict:
    """逐页统计 PPTX 中含 blip 的形状数（含 GROUP 递归）。依赖 python-pptx，缺失则返回空。"""
    out: dict[int, int] = {}
    try:
        from pptx import Presentation
    except ImportError:
        log.warning("未装 python-pptx，跳过三方计数核验（--deck 失效）")
        return {}
    try:
        prs = Presentation(str(deck_path))
    except Exception as e:
        log.warning("打开 PPTX 失败，跳过三方计数核验: %s", e)
        return {}

    def has_blip(shape) -> bool:
        try:
            for tag in shape._element.iter():
                if tag.tag.endswith("}blip"):
                    return True
        except Exception:
            pass
        return False

    def walk(shapes, page: int):
        for sh in shapes:
            try:
                if sh.shape_type is not None and getattr(sh, "shapes", None) is not None and has_blip(sh) is False:
                    # GROUP：递归
                    try:
                        from pptx.enum.shapes import MSO_SHAPE_TYPE
                        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                            walk(sh.shapes, page)
                            continue
                    except Exception:
                        pass
            except Exception:
                pass
            if has_blip(sh):
                out[page] = out.get(page, 0) + 1

    for idx, slide in enumerate(prs.slides, start=1):
        walk(slide.shapes, idx)
    return out


# ============== 主流程 ==============
def fix_refs(
    md_path: Path,
    manifest_path: Path,
    assets_dir: Path,
    out_path: Path,
    types: tuple[str, ...],
    link_mode: str,
    deck_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict, str]:
    """返回（报告 dict，修复后 md 文本）。"""
    md_text = md_path.read_text(encoding="utf-8")
    refs, parse_warns = parse_md_refs(md_text)
    by_page, meta = load_manifest_assets(manifest_path, types)

    matched, missing, orphan_assets = [], [], []
    used_assets: set[str] = set()
    lines = md_text.splitlines()
    rewrite: dict[int, str] = {}   # line_no → 新行

    for r in refs:
        cands = by_page.get(r.page, [])
        if r.index_in_page < len(cands):
            asset = cands[r.index_in_page]
            asset_abs = assets_dir / asset["file"]
            # 二次核验：若 md 原 target 在磁盘存在，用 sha256 比对
            evidence = "page_order"
            note = ""
            ref_disk = None
            try:
                cand_target = (md_path.parent / r.target)
                if not r.target.startswith(("http://", "https://", "data:")) and cand_target.exists():
                    ref_disk = sha256_file(cand_target)
            except OSError:
                ref_disk = None
            if ref_disk and asset.get("sha256"):
                if ref_disk == asset["sha256"]:
                    evidence = "sha256"
                else:
                    evidence = "page_order_conflict"
                    note = "磁盘文件 sha256 与候选资产不一致（疑似错配，需人工看渲染图确认）"

            if link_mode == "absolute":
                link = str(asset_abs)
            else:
                link = os.path.relpath(str(asset_abs), str(out_path.parent))
            new_alt = f"{asset['asset_id']}｜{r.alt}" if r.alt else asset["asset_id"]
            if note:
                new_alt = f"{new_alt}｜{note}"
            new_line = lines[r.line_no - 1].replace(
                f"![{r.alt}]({r.target})", f"![{new_alt}]({link})"
            )
            if new_line == lines[r.line_no - 1]:  # 非标准写法（HTML img 等）→ 退化为行尾追加标记
                new_line = lines[r.line_no - 1] + f"  <!-- 引用已解析: {asset['asset_id']} → {link} -->"
            rewrite[r.line_no] = new_line
            used_assets.add(asset["asset_id"])
            matched.append({
                **r.to_dict(),
                "asset_id": asset["asset_id"],
                "asset_file": asset["file"],
                "new_link": link,
                "evidence": evidence,
                "note": note,
                "asset_exists": asset_abs.exists(),
            })
        else:
            mark = f"<!-- REF-MISSING: 第{r.page}页资产不足（引用序号 {r.index_in_page + 1} > 资产数 {len(cands)}）-->"
            rewrite[r.line_no] = mark + "\n" + lines[r.line_no - 1]
            missing.append({**r.to_dict(), "reason": f"第{r.page}页无第{r.index_in_page + 1}个可视资产"})

    # 孤立资产：manifest 有、md 未引用
    for page, assets in sorted(by_page.items()):
        for idx, a in enumerate(assets):
            if a["asset_id"] not in used_assets:
                orphan_assets.append({
                    "asset_id": a["asset_id"], "page": page, "index_in_page": idx,
                    "file": a["file"],
                    "reason": "manifest 有此资产但 md 未出现对应引用（可能 markitdown 漏出图，需对照渲染图人工确认）",
                })

    # 三方计数核验
    mismatches = []
    if deck_path and deck_path.exists():
        deck_counts = count_deck_images_by_page(deck_path)
        md_counts: dict[int, int] = {}
        for r in refs:
            md_counts[r.page] = md_counts.get(r.page, 0) + 1
        man_counts = {p: len(v) for p, v in by_page.items()}
        for page in sorted(set(deck_counts) | set(md_counts) | set(man_counts)):
            triple = {
                "page": page,
                "deck": deck_counts.get(page, 0),
                "md": md_counts.get(page, 0),
                "manifest": man_counts.get(page, 0),
            }
            if len({triple["deck"], triple["md"], triple["manifest"]}) > 1:
                mismatches.append(triple)
    elif deck_path:
        log.warning("--deck 路径不存在，跳过三方计数核验: %s", deck_path)

    for ln, new_line in rewrite.items():
        lines[ln - 1] = new_line
    fixed_md = "\n".join(lines)

    n_unresolved = len(missing) + len(orphan_assets) + len(mismatches)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "md": str(md_path),
            "manifest": str(manifest_path),
            "assets_dir": str(assets_dir),
            "deck": str(deck_path) if deck_path else "",
            "types": list(types),
            "link_mode": link_mode,
        },
        "manifest_meta": meta,
        "counts": {
            "refs_total": len(refs),
            "matched": len(matched),
            "missing_refs": len(missing),
            "orphan_assets": len(orphan_assets),
            "count_mismatches": len(mismatches),
        },
        "matched": matched,
        "missing_refs": missing,
        "orphan_assets": orphan_assets,
        "count_mismatches": mismatches,
        "parse_warnings": parse_warns,
        "dry_run": dry_run,
        "exit_code": 1 if n_unresolved else 0,
    }

    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(fixed_md, encoding="utf-8")
        log.info("已写出修复稿: %s", out_path)
    return report, fixed_md


# ============== CLI ==============
def main():
    ap = argparse.ArgumentParser(
        description="Markdown 图片引用修复器（v3.8.2）：把 markitdown 的悬空图片链接重写为 _assets 实际路径",
    )
    ap.add_argument("--md", required=True, help="markitdown 原始 Markdown（只读，不覆盖）")
    ap.add_argument("--manifest", required=True, help="extract_assets.py 产出的 manifest.json")
    ap.add_argument("--out", required=True, help="修复稿输出路径（不得与 --md 相同）")
    ap.add_argument("--assets-dir", default=None, help="资产目录（默认 manifest 所在目录）")
    ap.add_argument("--deck", default=None, help="原 PPTX（可选，用于三方计数核验）")
    ap.add_argument("--types", default=",".join(DEFAULT_TYPES), help="参与配对的可视资产类型，逗号分隔")
    ap.add_argument("--link-mode", choices=["relative", "absolute"], default="relative", help="链接写法（默认 relative）")
    ap.add_argument("--report", default=None, help="JSON 报告路径（默认 <out>.refs.json）")
    ap.add_argument("--dry-run", action="store_true", help="只出报告不写修复稿")
    ap.add_argument("--json", action="store_true", help="把报告打到 stdout")
    args = ap.parse_args()

    md_path = Path(args.md).resolve()
    manifest_path = Path(args.manifest).resolve()
    out_path = Path(args.out).resolve()

    # 用法护栏
    if md_path == out_path:
        log.error("⛔ --out 不得与 --md 相同（SOP：原始转换结果只读留存，后续改写不得覆盖）")
        sys.exit(2)
    for p, label in ((md_path, "--md"), (manifest_path, "--manifest")):
        if not p.exists():
            log.error("⛔ %s 文件不存在: %s", label, p)
            sys.exit(3)

    assets_dir = Path(args.assets_dir).resolve() if args.assets_dir else manifest_path.parent
    if not assets_dir.is_dir():
        log.error("⛔ 资产目录不存在: %s", assets_dir)
        sys.exit(3)

    types = tuple(t.strip() for t in args.types.split(",") if t.strip())
    if not types:
        log.error("⛔ --types 解析后为空")
        sys.exit(2)
    deck_path = Path(args.deck).resolve() if args.deck else None

    try:
        report, _ = fix_refs(
            md_path=md_path, manifest_path=manifest_path, assets_dir=assets_dir,
            out_path=out_path, types=types, link_mode=args.link_mode,
            deck_path=deck_path, dry_run=args.dry_run,
        )
    except (OSError, json.JSONDecodeError) as e:
        log.error("⛔ 读取/解析失败: %s", e)
        sys.exit(3)
    except Exception as e:
        import traceback
        log.error("⛔ 运行错误: %s\n%s", e, traceback.format_exc())
        sys.exit(4)

    report_path = Path(args.report).resolve() if args.report else out_path.with_suffix(out_path.suffix + ".refs.json")
    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("报告已写出: %s", report_path)

    c = report["counts"]
    log.info(
        "引用 %d 条：已解析 %d / 缺失 %d / 孤立资产 %d / 计数不一致 %d",
        c["refs_total"], c["matched"], c["missing_refs"], c["orphan_assets"], c["count_mismatches"],
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    rc = report["exit_code"]
    if rc == 0:
        log.info("✓ 全部引用已解析且三方一致")
    else:
        log.error("✗ 存在未决项（%d 类），须人工处置，不得当作通过", c["missing_refs"] + c["orphan_assets"] + c["count_mismatches"])
    sys.exit(rc)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ── 归属声明（v3.16.0 补：本脚本此前无任何 agent 归属声明）────────────
# 所有者: visual-slide-designer（屠明熙，主题色令牌与模板指纹的登记人）｜批量执行者: ppt-producer（郅作基）
# 用途: 抽取 PPTX 模板指纹 sha256(c14n(clrScheme)+c14n(fontScheme))[:8]，供模板登记与一致性核查
# 何时被调用: ① 新模板入库登记 `register`；② 批量施工前确认源课件主题是否已登记指纹（未登记先登记再施工）
# ─────────────────────────────────────────────────────────────────────
"""
theme_fingerprint.py — PPTX 模板指纹工具（v3.2.0-batch3）

> 适用场景：WF-2R 难题③「统一更换整套模板」的基础设施。
> 指纹算法（确定性，可比，Q5 裁决：只取 clrScheme + fontScheme）：
>   theme_fingerprint = sha256(c14n(clrScheme) + c14n(fontScheme))[:8]
>   归一化用 W3C XML Canonicalization（lxml c14n），去声明头/空白/属性顺序影响。
>   不含 fmtScheme（效果样式跨 Office 版本差异大，与"风格/字体/配色一致性"无关）。

CLI：
  python3 theme_fingerprint.py <deck.pptx>              # 单份
  python3 theme_fingerprint.py <dir/> --recursive       # 目录批量 + 统一性报告
  python3 theme_fingerprint.py <deck.pptx> --json       # 机器可读输出

退出码（与 harness.py 统一）：0 通过 / 1 批量模式下发现不统一 / 2 zip 损坏 / 3 文件缺失 / 4 运行错误
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from lxml import etree
except ImportError as e:
    print(f"⛔ 缺少 lxml 依赖（{e}）", file=sys.stderr)
    sys.exit(4)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("theme_fingerprint")

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

SCHEMA_VERSION = "theme_fingerprint/1.0.0"


@dataclass
class DeckFingerprint:
    """单份课件的模板指纹。"""
    deck: str                    # 文件名（不含路径）
    theme_fingerprint: str       # sha256(c14n(clrScheme)+c14n(fontScheme))[:8]
    theme_count: int             # ppt/theme/ part 数
    master_count: int            # slideMaster 数
    layout_count: int            # slideLayout 数
    layout_names: list = field(default_factory=list)  # layout name 属性（sorted）
    fonts: list = field(default_factory=list)          # fontScheme 主字体（latin/ea）
    colors: dict = field(default_factory=dict)         # clrScheme 12 色摘要


def _c14n(element) -> bytes:
    """W3C 规范化序列化（去属性顺序/空白差异，保证指纹可比）。"""
    return etree.tostring(element, method="c14n", exclusive=False)


def _extract_fingerprint_from_theme_xml(theme_xml_bytes: bytes) -> Optional[tuple]:
    """从 theme XML 抽取 (clrScheme, fontScheme) 的 c14n 字节。失败返回 None。"""
    try:
        root = etree.fromstring(theme_xml_bytes)
    except etree.XMLSyntaxError:
        return None
    clr = root.find(f"{{{A_NS}}}themeElements/{{{A_NS}}}clrScheme")
    font = root.find(f"{{{A_NS}}}themeElements/{{{A_NS}}}fontScheme")
    if clr is None or font is None:
        return None
    return _c14n(clr), _c14n(font), root, clr, font


def fingerprint_deck(deck_path: Path) -> DeckFingerprint:
    """算单份课件指纹（只读 zip + theme1.xml，不解析全部 slide）。"""
    with zipfile.ZipFile(str(deck_path), "r") as z:
        names = z.namelist()
        themes = sorted(n for n in names if n.startswith("ppt/theme/") and n.endswith(".xml"))
        masters = [n for n in names if n.startswith("ppt/slideMasters/") and n.endswith(".xml")]
        layouts = sorted(n for n in names if n.startswith("ppt/slideLayouts/") and n.endswith(".xml"))

        # theme1.xml 为主指纹源（Office 惯例：theme1 挂 master1）
        primary_theme = "ppt/theme/theme1.xml"
        if primary_theme not in themes:
            primary_theme = themes[0] if themes else None

        fp = "NONE"
        fonts: list = []
        colors: dict = {}
        if primary_theme:
            extracted = _extract_fingerprint_from_theme_xml(z.read(primary_theme))
            if extracted:
                clr_c14n, font_c14n, root, clr_el, font_el = extracted
                h = hashlib.sha256()
                h.update(clr_c14n)
                h.update(font_c14n)
                fp = h.hexdigest()[:8]
                # 摘要：主字体（latin + ea）
                for tag in ("majorFont", "minorFont"):
                    for sub in ("latin", "ea"):
                        el = font_el.find(f"{{{A_NS}}}{tag}/{{{A_NS}}}{sub}")
                        if el is not None and el.get("typeface"):
                            fonts.append(f"{tag[:5]}.{sub}:{el.get('typeface')}")
                # 摘要：12 色名 → srgbClr/(sysClr val)
                for child in clr_el:
                    name = child.tag.split("}")[-1]
                    srgb = child.find(f"{{{A_NS}}}srgbClr")
                    sysc = child.find(f"{{{A_NS}}}sysClr")
                    if srgb is not None and srgb.get("val"):
                        colors[name] = f"#{srgb.get('val')}"
                    elif sysc is not None and sysc.get("lastClr"):
                        colors[name] = f"sys:{sysc.get('lastClr')}"

        # layout names（读 cSld name 属性；容忍解析失败）
        layout_names = []
        for ln in layouts[:80]:  # 上限防超大
            try:
                r = etree.fromstring(z.read(ln))
                nm = r.get("name") or r.find(f"{{{A_NS.replace('drawingml','presentationml')}}}cSld")
                if r.get("name"):
                    layout_names.append(r.get("name"))
            except Exception:
                continue
        layout_names = sorted(set(layout_names))

    return DeckFingerprint(
        deck=deck_path.name,
        theme_fingerprint=fp,
        theme_count=len(themes),
        master_count=len(masters),
        layout_count=len(layouts),
        layout_names=layout_names[:20],
        fonts=fonts[:6],
        colors=colors,
    )


def _active_deck(p: Path) -> bool:
    """v3.4.3 C2 口径修复：只统计活跃课件——跳过 .snapshots 快照库 / _trash_ 归档 /
    . 开头隐藏目录 / ~ 临时文件，与 harness sweep 纪律对齐（sweep 注释"自动跳过
    _trash_*、~ 临时文件、.snapshots 快照库"）。
    背景：此前 batch_report 无过滤，238 总数混入约百份快照副本，覆盖统计失真
    （example_decks 全是 hash 命名快照，直接 register 会把快照当模板登记）。"""
    if p.name.startswith("~"):
        return False
    for part in p.parts[1:-1]:      # 跳过根自身与文件名，只查中间目录
        if part == ".snapshots" or part.startswith("_trash_") or part.startswith("."):
            return False
    return True


def batch_report(root_dir: Path) -> dict:
    """目录批量扫描 + 统一性报告（v3.4.3 C2：仅活跃 deck，跳过 .snapshots/_trash_/~）。"""
    decks = sorted(p for p in root_dir.rglob("*.pptx") if _active_deck(p))
    fps: list[DeckFingerprint] = []
    errors = 0
    for d in decks:
        try:
            fps.append(fingerprint_deck(d))
        except (zipfile.BadZipFile, OSError) as e:
            log.warning("跳过损坏文件: %s (%s)", d.name, e)
            errors += 1
    counter = Counter(f.theme_fingerprint for f in fps)
    majority_fp, majority_count = (counter.most_common(1)[0] if counter else ("NONE", 0))
    return {
        "schema_version": SCHEMA_VERSION,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "root_dir": str(root_dir),
        "total_decks": len(fps),
        "skipped_errors": errors,
        "unique_fingerprints": len(counter),
        "majority": {"fingerprint": majority_fp, "count": majority_count,
                     "pct": round(majority_count / max(len(fps), 1) * 100, 1)},
        "distribution": [
            {"fingerprint": fp, "count": c,
             "layout_range": _layout_range(fps, fp),
             "example_decks": _examples(fps, fp)}
            for fp, c in counter.most_common()
        ],
        "decks": [asdict(f) for f in fps],
    }


def _layout_range(fps: list, fp: str) -> str:
    ls = [f.layout_count for f in fps if f.theme_fingerprint == fp]
    return f"{min(ls)}-{max(ls)}" if ls else "?"


def _examples(fps: list, fp: str, n: int = 3) -> list:
    return [f.deck for f in fps if f.theme_fingerprint == fp][:n]


def main():
    ap = argparse.ArgumentParser(description="PPTX 模板指纹工具（v3.2.0-batch3）")
    ap.add_argument("target", help="课件 .pptx 或目录")
    ap.add_argument("--recursive", action="store_true", help="目录递归扫描")
    ap.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        log.error("目标不存在: %s", target)
        sys.exit(3)

    # 单文件模式
    if target.is_file():
        try:
            fp = fingerprint_deck(target)
        except zipfile.BadZipFile:
            log.error("zip 损坏")
            sys.exit(2)
        if args.json:
            print(json.dumps(asdict(fp), ensure_ascii=False, indent=2))
        else:
            print(f"deck: {fp.deck}")
            print(f"theme_fingerprint: {fp.theme_fingerprint}")
            print(f"themes={fp.theme_count} masters={fp.master_count} layouts={fp.layout_count}")
            print(f"fonts: {', '.join(fp.fonts) if fp.fonts else '(未取到)'}")
            print(f"colors: {json.dumps(fp.colors, ensure_ascii=False)}")
        sys.exit(0)

    # 目录批量模式
    report = batch_report(target)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"== 模板指纹盘点 ==")
        print(f"总课件: {report['total_decks']} 件（跳过损坏 {report['skipped_errors']}）")
        print(f"唯一指纹数: {report['unique_fingerprints']} 个")
        print()
        bar_max = 30
        for d in report["distribution"]:
            bar = "█" * max(1, int(d["count"] / max(report["total_decks"], 1) * bar_max))
            print(f"  {d['fingerprint']}  {bar} {d['count']} 件  layouts={d['layout_range']}  例: {', '.join(d['example_decks'][:2])}")
        m = report["majority"]
        print()
        print(f"模板统一度: {m['count']}/{report['total_decks']} = {m['pct']}% 使用多数派 {m['fingerprint']}")
        if report["unique_fingerprints"] > 1:
            minority = report["total_decks"] - m["count"]
            print(f"建议：若要统一，少数派 {minority} 件走 T2/T3 迁移（多数派作 T1 目标模板）")
    sys.exit(0)


if __name__ == "__main__":
    main()

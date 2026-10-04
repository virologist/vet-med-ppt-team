#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
surgery_deck.py — 批量版面外科工具（v2.1.0 · 屠明熙出判据 / 郅作基执行）

依据：references/batch-surgery-sop.md（修复顺序：缩小→移动→拆页→删冗余）。
本工具实现"移动"级：P1 元素重叠的卡位迁移 + P0 文字越界的画布内微调。

范围与克制（不可违反）：
  ① 阈值只读 config/visual-rules.yaml（geometry.overlap_ratio / offcanvas_tolerance_in）
  ② 修改前强制备份（偏好 C：<原名>_备份_YYYYMMDD_HHMM.pptx 同目录）
  ③ 迁移优先级：注入型卡片（❓/✅/【任务/【A轨/【B轨/【口径统一 等标记开头）> 面积较小一方
  ④ 空位检测：候选位置与页内全部其他文本框交面积/较小面积 ≤ overlap_ratio；
     尽量避开图片（与图交面积/卡片面积 > 30% 的候选位弃用，除非整页无图位可选）
  ⑤ 找不到空位 → 不动，记 unresolved（诚实原则，禁止硬塞制造新问题）
  ⑥ 文字墙 = 拆页 = 内容决策，不在本工具范围（如实记录，走苏学法工作流）

用法：
  python3 surgery_deck.py --base <课程根目录> [--decks file|a,b,c] [--dry-run] [--report out.json]
  decks 文件每行一条相对路径；缺省读 <base>/.workbuddy/deck_registry.json 的全部键。
"""

import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_YAML = os.path.join(HERE, "..", "config", "visual-rules.yaml")

from pptx import Presentation  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402

EMU_IN = 914400

# 注入型卡片标记（A轨叠加层/B轨倒序产物——迁移的优先对象）
OVERLAY_MARKERS = ("❓", "✅", "【任务", "【A轨", "【B轨", "【口径统一", "想一想", "随堂")


def load_rules():
    """阈值只读 yaml（单一数据源），失败回退内置值并告警"""
    import yaml
    try:
        with open(RULES_YAML, encoding="utf-8") as f:
            r = yaml.safe_load(f)
        return (float(r["geometry"]["overlap_ratio"]),
                float(r["geometry"]["offcanvas_tolerance_in"]),
                float(r.get("gate", {}).get("p2_note_coverage", 0.8)))
    except Exception as e:
        print(f"⚠ visual-rules.yaml 加载失败（{e}），回退内置阈值", file=sys.stderr)
        return 0.15, 0.25, 0.8


def inter_ratio(a, b):
    """两矩形交面积 / 较小矩形面积；无交返回 0"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    smaller = min(aw * ah, bw * bh)
    return inter / smaller if smaller > 0 else 0.0


def cover_ratio(fix, box):
    """box 被 fix 覆盖面积 / box 面积（用于避图判定）"""
    fx, fy, fw, fh = fix
    bx, by, bw, bh = box
    x1, y1 = max(fx, bx), max(fy, by)
    x2, y2 = min(fx + fw, bx + bw), min(fy + fh, by + bh)
    if x2 <= x1 or y2 <= y1 or bw * bh <= 0:
        return 0.0
    return (x2 - x1) * (y2 - y1) / (bw * bh)


def collect_slide_geometry(slide):
    """收集一页的文本框/图片矩形与 shape 引用（顶层，与 verify_deck 主路径口径一致）"""
    texts, pics = [], []
    for shape in slide.shapes:
        try:
            if shape.shape_type == 13:  # PICTURE
                rect = (shape.left, shape.top, shape.width, shape.height)
                if all(v is not None for v in rect):
                    pics.append(rect)
                continue
            if not shape.has_text_frame or not shape.text_frame.text.strip():
                continue
            rect = (shape.left, shape.top, shape.width, shape.height)
            if any(v is None for v in rect):
                continue
            texts.append({"shape": shape, "rect": rect,
                          "text": shape.text_frame.text.strip()})
        except Exception:
            continue  # 与裁判口径一致：解析不了的形状跳过
    return texts, pics


def find_free_slot(mover_rect, others, pics, sw, sh, tol, orate):
    """网格搜索空位：与文本框交≤orate、与图覆盖≤30%、画布内；按离原位距离升序取第一个"""
    mx, my, mw, mh = mover_rect
    step = int(0.30 * EMU_IN)
    cands = []
    x = int(0.05 * EMU_IN)
    while x + mw <= sw - tol and x - mx < sw:  # 覆盖整页横带
        y = int(0.05 * EMU_IN)
        while y + mh <= sh - tol:
            cands.append((x, y))
            y += step
        x += step
    cands.sort(key=lambda p: (p[0] - mx) ** 2 + (p[1] - my) ** 2)
    fallback = None  # 无图位可选时的次选缓存
    for (cx, cy) in cands[:4000]:
        cand = (cx, cy, mw, mh)
        if any(inter_ratio(cand, o["rect"]) > orate for o in others):
            continue
        pic_cover = max((cover_ratio(cand, p) for p in pics), default=0.0)
        if pic_cover > 0.30:
            if fallback is None and pic_cover <= 0.60:
                fallback = (cx, cy, pic_cover)
            continue
        return (cx, cy), "clean"
    if fallback:
        return (fallback[0], fallback[1]), f"pic_overlap_{fallback[2]:.0%}"
    return None, None


def surgery_deck(path, orate, tol_in, dry_run):
    """单课件版面外科；返回统计 dict。
    ⚠ tol_in 单位=英寸（来自 yaml offcanvas_tolerance_in）；内部一律先转 EMU 再比较。
    （v2.1.0 修复：首版把英寸容差直接当 EMU 比较，容差≈0，把装饰性微出血误判为越界）"""
    tol = int(tol_in * EMU_IN)  # 英寸 → EMU，全函数统一用此值
    prs = Presentation(path)
    sw, sh = prs.slide_width, prs.slide_height
    moved = offcanvas_fixed = skipped = 0
    details = []

    for idx, slide in enumerate(prs.slides, 1):
        if slide._element.get("show") == "0":
            continue
        texts, pics = collect_slide_geometry(slide)

        # ── P1 元素重叠：卡位迁移（需 ≥2 文本框才有意义；单文本框页直接跳过本段，
        #    但不得跳过下方越界检测——v2.1.0 修复：原守卫把单文本框页整页跳过，
        #    导致"标题标签+大图"型页面的越界漏检，M4C1 P3 实测复现）──
        if len(texts) >= 2:
            pairs = []
            for i in range(len(texts)):
                for j in range(i + 1, len(texts)):
                    r = inter_ratio(texts[i]["rect"], texts[j]["rect"])
                    if r > orate:
                        pairs.append((r, i, j))
            pairs.sort(reverse=True)
            moved_flags = set()
            for ratio, i, j in pairs:
                a, b = texts[i], texts[j]
                # 防重复迁移：两端现势矩形已不重叠的配对跳过（前次迁移可能已顺带解决）
                if inter_ratio(a["rect"], b["rect"]) <= orate:
                    continue
                # 选迁移对象：注入标记优先 → 面积小者优先；已被迁移过的允许再迁
                a_m = a["text"].startswith(OVERLAY_MARKERS)
                b_m = b["text"].startswith(OVERLAY_MARKERS)
                if a_m != b_m:
                    mover, anchor = (a, b) if a_m else (b, a)
                else:
                    mover, anchor = (a, b) if a["rect"][2] * a["rect"][3] <= b["rect"][2] * b["rect"][3] else (b, a)
                others = [t for t in texts if t["shape"] is not mover["shape"]]
                slot, quality = find_free_slot(mover["rect"], others, pics, sw, sh, tol, orate)
                if slot is None:
                    skipped += 1
                    details.append({"slide": idx, "type": "overlap_unresolved",
                                    "ratio": round(ratio, 2), "snippet": mover["text"][:20]})
                    continue
                if not dry_run:
                    mover["shape"].left, mover["shape"].top = slot
                mover["rect"] = (slot[0], slot[1], mover["rect"][2], mover["rect"][3])
                moved += 1
                details.append({"slide": idx, "type": "overlap_moved",
                                "ratio": round(ratio, 2), "quality": quality,
                                "mover": mover["text"][:20]})
                moved_flags.add(id(mover["shape"]))

        # ── P0 文字越界：画布内微调（平移回画布，改后重测不新增重叠才提交）──
        for t in texts:
            x, y, w, h = t["rect"]
            if x < -tol or y < -tol or x + w > sw + tol or y + h > sh + tol:
                nx = min(max(x, int(0.05 * EMU_IN)), int(sw - w - 0.05 * EMU_IN))
                ny = min(max(y, int(0.05 * EMU_IN)), int(sh - h - 0.05 * EMU_IN))
                cand = (nx, ny, w, h)
                if any(inter_ratio(cand, o["rect"]) > orate for o in texts if o["shape"] is not t["shape"]):
                    skipped += 1
                    details.append({"slide": idx, "type": "offcanvas_unresolved",
                                    "snippet": t["text"][:20]})
                    continue
                if not dry_run:
                    t["shape"].left, t["shape"].top = nx, ny
                t["rect"] = cand
                offcanvas_fixed += 1
                details.append({"slide": idx, "type": "offcanvas_fixed", "snippet": t["text"][:20]})

    # ── 写回磁盘（v2.1.0 修复：首版漏 save 导致空转，verify_deck 复验当场逮住）──
    if not dry_run:
        prs.save(path)

    return {"moved": moved, "offcanvas_fixed": offcanvas_fixed, "unresolved": skipped,
            "details": details}


def md5_of(path, buf=1 << 20):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(buf):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="批量版面外科工具（v2.1.0）")
    ap.add_argument("--base", required=True, help="课程根目录")
    ap.add_argument("--decks", help="相对路径清单文件（每行一条），缺省用 deck_registry.json 全部键")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="JSON 报告输出路径")
    a = ap.parse_args()

    orate, tol, _ = load_rules()
    base = a.base

    if a.decks:
        with open(a.decks, encoding="utf-8") as f:
            rels = [ln.strip() for ln in f if ln.strip()]
    else:
        reg = os.path.join(base, ".workbuddy", "deck_registry.json")
        with open(reg, encoding="utf-8") as f:
            rels = list(json.load(f)["decks"].keys())

    print(f"版面外科（dry_run={a.dry_run}）：overlap_ratio={orate} / 越界容差={tol}in / 课件 {len(rels)} 份")
    report = {"version": "2.1.0", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "dry_run": a.dry_run, "decks": {}}

    for rel in rels:
        path = os.path.join(base, rel)
        if not os.path.exists(path):
            report["decks"][rel] = {"error": "文件不存在"}
            continue
        if not a.dry_run:
            stem, ext = os.path.splitext(path)
            backup = f"{stem}_备份_{time.strftime('%Y%m%d_%H%M')}{ext}"
            shutil.copy2(path, backup)
        else:
            backup = None
        r = surgery_deck(path, orate, tol, a.dry_run)
        r["backup"] = os.path.basename(backup) if backup else None
        r["md5"] = md5_of(path)
        report["decks"][rel] = r
        print(f"  {rel}: 迁移 {r['moved']} / 越界修复 {r['offcanvas_fixed']} / 未解 {r['unresolved']}")

    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已存：{a.report}")


if __name__ == "__main__":
    main()

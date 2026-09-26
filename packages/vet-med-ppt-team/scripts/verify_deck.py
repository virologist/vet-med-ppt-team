#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_deck.py — 教学课件机械验证器（70% 机械验证的裁判）

设计原则：以"教学PPT为第一性原理、学生利益最大化"反向设阈值。
所有判定必须是机器可执行、可复现、可 diff 的，禁止模型自评。

检查项（8 项）：
  1. 字号红线      —— 正文 <12pt、图注/来源 <9pt 违规
  2. 越界          —— 元素超画布
  3. 元素重叠      —— 文字框相互遮挡（学生看不见 = 零价值）
  4. 配色混乱      —— 单页颜色数超阈值（视觉噪音）
  5. 文字墙        —— 单页字符数超限（认知负荷过载）
  6. 空白页        —— 无内容页
  7. 课时匹配      —— 页数 vs 课时标准
  8. 结构性完备    —— 目录页 / 题页 / 备注覆盖

用法：
  python3 verify_deck.py <课件.pptx> [--hours 3] [--json out.json] [--strict]

退出码：0=全绿 / 1=有红灯 / 2=运行错误

依赖：pip install python-pptx
"""

import argparse
import json
import sys
from collections import Counter

try:
    from pptx import Presentation
    from pptx.util import Emu
except ImportError:
    print("缺少依赖：pip install python-pptx", file=sys.stderr)
    sys.exit(2)

# ============ 阈值（单一数据源：config/visual-rules.yaml；回退=内置值）============
# v1.9.0：红线参数化——批量脚本与本脚本共用同一配置，改红线只改 yaml（防 R18 两张皮事故）
import os

_FALLBACK = {
    "body_min_pt": 12.0,
    "note_min_pt": 9.0,
    "max_colors_per_slide": 5,
    "max_chars_per_slide": 400,
    "overlap_ratio": 0.15,
    "hours_page_range": {
        1: (18, 28),
        1.5: (35, 50),
        2: (36, 52),
        3: (55, 78),
        4: (72, 104),
    },
}

_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "config", "visual-rules.yaml")

def _load_threshold():
    """优先读 config/visual-rules.yaml；失败回退内置值并告警（不中断裁判）。"""
    try:
        import yaml
        with open(_RULES_PATH, encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        hpr = {float(k): tuple(v) for k, v in rules["hours_page_range"].items()}
        return {
            "body_min_pt": float(rules["font"]["body_min_pt"]),
            "note_min_pt": float(rules["font"]["note_min_pt"]),
            "max_colors_per_slide": int(rules["density"]["max_colors_per_slide"]),
            "max_chars_per_slide": int(rules["density"]["max_chars_per_slide"]),
            "overlap_ratio": float(rules["geometry"]["overlap_ratio"]),
            "hours_page_range": hpr,
        }
    except Exception as e:
        print(f"⚠ visual-rules.yaml 加载失败（{e}），使用内置回退阈值", file=sys.stderr)
        return dict(_FALLBACK)

THRESHOLD = _load_threshold()

EMU_PER_INCH = 914400


def _pt(size):
    """EMU/pt 统一转为 pt；None 返回 None（表示继承，由调用方处理）"""
    if size is None:
        return None
    return round(size.pt, 1) if hasattr(size, "pt") else round(size / 12700.0, 1)


def _shape_font_size(shape):
    """尽力取字号：run → paragraph → 主题继承（拿不到返回 None）"""
    sizes = []
    if not shape.has_text_frame:
        return sizes
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            s = run.font.size
            if s is None and para.font.size is not None:
                s = para.font.size
            pt = _pt(s)
            if pt is not None:
                sizes.append(pt)
    return sizes


def _is_note_candidate(text):
    """图注/来源判定：短文本 + 含来源关键词 → 按低阈值"""
    keys = ("来源", "Source", "图注", "PMC", "CC-BY", "参考文献", "数据来", "引自", "http")
    return (len(text) <= 40) and any(k in text for k in keys)


def _shape_colors(shape):
    """收集该形状用到的颜色（填充 + 字体色）"""
    colors = set()
    try:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    c = run.font.color
                    if c is not None and c.type is not None and c.rgb is not None:
                        colors.add(str(c.rgb))
    except Exception:
        pass
    try:
        f = shape.fill
        if f.type is not None and f.type != 5:  # 5 = background/none
            fc = f.fore_color
            if fc.type is not None and fc.rgb is not None:
                colors.add(str(fc.rgb))
    except Exception:
        pass
    return colors


def _rect(shape):
    try:
        return (shape.left, shape.top, shape.width, shape.height)
    except Exception:
        return None


def _overlap_area(a, b):
    """两矩形相交面积"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0, 0
    return (x2 - x1) * (y2 - y1), min(aw * ah, bw * bh)


def verify(path, hours=3, strict=False):
    prs = Presentation(path)
    sw, sh = prs.slide_width, prs.slide_height
    issues = []
    stats = {
        "file": path,
        "total_slides": len(prs.slides),
        "visible_slides": 0,
        "hours": hours,
        "small_body": 0, "small_note": 0, "offcanvas": 0,
        "overlap": 0, "color_chaos": 0, "text_wall": 0,
        "empty_slides": 0, "no_notes": 0, "unknown_font": 0, "bleed_decor": 0,
    }

    visible = []
    for idx, slide in enumerate(prs.slides, 1):
        # 隐藏页跳过（R7 起用隐藏而非删除保留内容）
        if slide._element.get("show") == "0":
            continue
        visible.append((idx, slide))
    stats["visible_slides"] = len(visible)

    has_toc = False          # 目录页
    has_quiz = False         # 题页
    for idx, slide in visible:
        # ---------- 文本收集 ----------
        text_shapes = []
        all_text = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                text_shapes.append(shape)
                all_text.append(shape.text_frame.text.strip())

        page_text = " ".join(all_text)

        # 结构性识别
        if any(k in page_text for k in ("目录", "CONTENTS", "内容导航")):
            has_toc = True
        if any(k in page_text for k in ("思考题", "练习题", "课堂提问", "随堂测", "Q1", "答案")):
            has_quiz = True

        # ---------- 1. 字号 ----------
        for shape in text_shapes:
            sizes = _shape_font_size(shape)
            if not sizes:
                stats["unknown_font"] += 1
                continue
            min_s = min(sizes)
            txt = shape.text_frame.text.strip()
            limit = THRESHOLD["note_min_pt"] if _is_note_candidate(txt) else THRESHOLD["body_min_pt"]
            if min_s < limit:
                if _is_note_candidate(txt):
                    stats["small_note"] += 1
                else:
                    stats["small_body"] += 1
                issues.append({
                    "slide": idx, "type": "字号过小",
                    "detail": f"{min_s}pt < {limit}pt（{'图注/来源' if _is_note_candidate(txt) else '正文'}）",
                    "snippet": txt[:30],
                })

        # ---------- 2. 越界（只判有文本的元素；无文本装饰按"出血设计"放行）----------
        # 说明：教学课件常见贴边色带/页眉故意超出画布（bleed），属合法设计；
        #       但**文字**越界=学生看不见，必须红灯。容差 0.25in 吸收浮点与轻微出血。
        for shape in slide.shapes:
            r = _rect(shape)
            if r is None:
                continue
            has_txt = shape.has_text_frame and shape.text_frame.text.strip()
            x, y, w, h = r
            tol = EMU_PER_INCH * 0.25
            if (x is not None and (x < -tol or y < -tol
                                   or x + w > sw + tol
                                   or y + h > sh + tol)):
                if not has_txt:
                    stats["bleed_decor"] += 1   # 装饰性出血，不计违规
                    continue
                stats["offcanvas"] += 1
                issues.append({
                    "slide": idx, "type": "文字越界",
                    "detail": f"位置({round(x/EMU_PER_INCH,2)},{round(y/EMU_PER_INCH,2)})in "
                              f"尺寸({round(w/EMU_PER_INCH,2)}x{round(h/EMU_PER_INCH,2)})in "
                              f"画布({round(sw/EMU_PER_INCH,2)}x{round(sh/EMU_PER_INCH,2)})in",
                    "snippet": shape.text_frame.text[:30],
                })

        # ---------- 3. 元素重叠（学生看不见 = 零价值）----------
        for i in range(len(text_shapes)):
            for j in range(i + 1, len(text_shapes)):
                ra, rb = _rect(text_shapes[i]), _rect(text_shapes[j])
                if ra is None or rb is None:
                    continue
                inter, smaller = _overlap_area(ra, rb)
                if smaller > 0 and inter / smaller > THRESHOLD["overlap_ratio"]:
                    stats["overlap"] += 1
                    issues.append({
                        "slide": idx, "type": "元素重叠",
                        "detail": f"两文本框重叠 {round(inter/smaller*100)}%",
                        "snippet": text_shapes[i].text_frame.text[:20] + " ✕ " + text_shapes[j].text_frame.text[:20],
                    })

        # ---------- 4. 配色混乱 ----------
        page_colors = set()
        for shape in slide.shapes:
            page_colors |= _shape_colors(shape)
        if len(page_colors) > THRESHOLD["max_colors_per_slide"]:
            stats["color_chaos"] += 1
            issues.append({
                "slide": idx, "type": "配色混乱",
                "detail": f"单页 {len(page_colors)} 种颜色 > {THRESHOLD['max_colors_per_slide']} 种",
                "snippet": ",".join(sorted(page_colors)[:4]),
            })

        # ---------- 5. 文字墙 ----------
        if len(page_text) > THRESHOLD["max_chars_per_slide"]:
            stats["text_wall"] += 1
            issues.append({
                "slide": idx, "type": "文字墙",
                "detail": f"单页 {len(page_text)} 字 > {THRESHOLD['max_chars_per_slide']} 字",
                "snippet": page_text[:40],
            })

        # ---------- 6. 空白页 ----------
        has_pic = any(s.shape_type == 13 for s in slide.shapes)  # 13 = PICTURE
        if not text_shapes and not has_pic:
            stats["empty_slides"] += 1
            issues.append({"slide": idx, "type": "空白页", "detail": "无文本无图片", "snippet": ""})

        # ---------- 8. 备注 ----------
        if not (slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()):
            stats["no_notes"] += 1
            issues.append({"slide": idx, "type": "缺备注", "detail": "该页无讲稿备注", "snippet": ""})

    # ---------- 7. 课时匹配 ----------
    lo, hi = THRESHOLD["hours_page_range"].get(hours, (0, 9999))
    n = stats["visible_slides"]
    hours_ok = lo <= n <= hi
    if not hours_ok:
        issues.append({"slide": 0, "type": "课时不达标",
                       "detail": f"可见{n}页，{hours}课时标准({lo}-{hi}页)", "snippet": ""})

    stats["has_toc"] = has_toc
    stats["has_quiz"] = has_quiz
    stats["hours_ok"] = hours_ok

    # ---------- 红绿灯汇总 ----------
    red = {
        "字号过小(正文)": stats["small_body"],
        "字号过小(图注)": stats["small_note"],
        "文字越界": stats["offcanvas"],
        "元素重叠": stats["overlap"],
        "配色混乱": stats["color_chaos"],
        "文字墙": stats["text_wall"],
        "空白页": stats["empty_slides"],
        "缺备注": stats["no_notes"],
        "课时不达标": 0 if hours_ok else 1,
        "缺目录页": 0 if has_toc else 1,
        "缺题页": 0 if has_quiz else 1,
    }
    green = all(v == 0 for v in red.values())
    if strict:
        green = green and stats["unknown_font"] == 0

    return {"stats": stats, "red": red, "green": green, "issues": issues}


def main():
    ap = argparse.ArgumentParser(description="教学课件机械验证器")
    ap.add_argument("deck", help="课件路径 .pptx")
    ap.add_argument("--hours", type=float, default=3, help="课时数（默认3；1.5=1小时教学单元60min档，v1.6.0）")
    ap.add_argument("--json", help="输出 JSON 报告路径")
    ap.add_argument("--strict", action="store_true", help="严格模式：继承字号也算违规")
    ap.add_argument("--limit", type=int, default=25, help="终端最多打印多少条问题")
    a = ap.parse_args()

    try:
        r = verify(a.deck, a.hours, a.strict)
    except Exception as e:
        print(f"运行错误：{e}", file=sys.stderr)
        sys.exit(2)

    s = r["stats"]
    print(f"\n{'='*62}\n课件验证报告：{s['file']}")
    print(f"总页 {s['total_slides']} / 可见 {s['visible_slides']} / 课时 {s['hours']}")
    print(f"目录页:{'✓' if s['has_toc'] else '✗'}  题页:{'✓' if s['has_quiz'] else '✗'}  课时匹配:{'✓' if s['hours_ok'] else '✗'}")
    print(f"{'='*62}")
    print("红绿灯：")
    for k, v in r["red"].items():
        flag = "🟢" if v == 0 else "🔴"
        print(f"  {flag} {k:16s} {v}")
    if s["bleed_decor"]:
        print(f"  ⚪ 装饰出血(合法设计)   {s['bleed_decor']}  ← 非违规")
    if s["unknown_font"]:
        print(f"  ⚪ 字号继承(未取到)     {s['unknown_font']}  ← 非违规，需人工抽检")
    print(f"\n{'='*62}")
    print(f"结论：{'✅ 全绿' if r['green'] else '❌ 有红灯，禁止宣布完成'}")
    if r["issues"]:
        print(f"\n问题明细（前 {a.limit} 条，共 {len(r['issues'])} 条）：")
        for i in r["issues"][:a.limit]:
            print(f"  P{i['slide']:<3} [{i['type']}] {i['detail']}  {i['snippet']}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告已存：{a.json}")

    sys.exit(0 if r["green"] else 1)


if __name__ == "__main__":
    main()

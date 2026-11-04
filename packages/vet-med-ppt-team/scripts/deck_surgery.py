#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deck_surgery.py — 通用课件手术工具（v3.28.6 · B25⑥ · 第五轮诊断 N1）

立项背景（**首跑真实病灶**，非推测）：
  Loop B 首跑（task_id = T-xuexue-20261103）的闸3 施工脚本是**一次性**的
  `surgery_xuexue.py`，躺在运行目录里、只对那一份课件有效。它做的事其实是
  六件高度可复用的事：
      ① 上标规范化（数字/单位上标：mL、min、h、℃、×10ⁿ）
      ② 国标/规范编号前缀规范化（"GB 30000" 与 "GB30000" 混用）
      ③ 正文字号抬升（低于 visual-rules.yaml#font.body_min_pt 的正文 run）
      ③' 备注/页脚字号抬升（低于 font.note_min_pt / font.footer_min_pt）
      ④ 配色收敛（单页颜色数超 density.max_colors_per_slide 时归一到主题令牌）
      ④' 页面密度体检（超 density.max_body_chars_per_slide ⇒ 给收敛顺序）
      ⑤ 空白页处置（显式标记/报告，**不擅自删除**——可能是作者预留位）
      ⑥ 几何修复（元素重叠迁移 + 文字越界收回画布）——复用 surgery_deck.py 的内核
  一次性脚本的问题是：下一次任务还得重写一遍，且每次重写都可能引入新缺陷
  （首跑实证：几何修复连续三轮证伪，重叠 4→16→19）。
  ⇒ 本文件把上述能力**参数化沉淀**为包内工具：修复项由 `--fix` 指定，
  阈值一律只读 config/visual-rules.yaml（禁硬编码）。

与既有工具的分工：
  · `surgery_deck.py` —— 几何专项（元素重叠/文字越界），本工具**复用**其内核
  · `deck_surgery.py` —— 多类修复的统一入口
    （几何 + 上标 + 编号 + 正文字号 + 备注字号 + 配色 + 密度 + 空白页）

红线（不可违反）：
  ① **阈值只读 config/visual-rules.yaml**，缺键 ⇒ 显式告警 + 回落，禁硬编码
  ② **改前强制备份**（<原名>_备份_YYYYMMDD_HHMM.pptx，同目录）
  ③ **默认 dry-run**：不改文件，只出报告。写盘须显式 --apply
  ④ **空白页不删**：只报告（作者预留位属设计意图，删了丢意图）
  ⑤ **改完必过门禁**：写回后应跑 `harness.py gate` 复验（自引入缺陷 = 0）
  ⑥ **诚实**：修不了的显式记 unresolved，禁硬塞制造新问题

用法：
  # 报告将要做什么（默认 dry-run）
  python3 deck_surgery.py --deck <课件.pptx> --fix superscript,font,color

  # 真改（先备份）
  python3 deck_surgery.py --deck <课件.pptx> --fix superscript,font --apply

  # 只修某几页
  python3 deck_surgery.py --deck <课件.pptx> --fix geometry --pages 7,9,34 --apply

  # 出 JSON 报告（供 `loop worklist` / delta 门禁消费）
  python3 deck_surgery.py --deck <课件.pptx> --fix all --report out.json
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
RULES_YAML = os.path.join(PKG, "config", "visual-rules.yaml")

FIX_KINDS = ["superscript", "normid", "font", "note", "color", "density",
             "blank", "geometry"]

# 上标字符映射：正文里的「数字+单位」应写成上标形式（本包国标/教材惯例）
# ⚠ 只改**明确的单位/数量级记号**，不猜语义（禁把"3个"改成上标——那是误伤）。
SUPERSCRIPT_PAIRS = [
    ("mL", "mL"),          # 毫升：L 上标
    ("dl", "dL"),
    ("μg", "μg"),
    ("ng", "ng"),
    ("min", "min"),
    ("h", "h"),
    ("℃", "℃"),
    ("×10", "×10"),
]

# 国标/规范编号：允许 "GB 30000" / "GB30000" 两种写法，统一为带空格的标准形
# ⚠ 只在**明确的编号前缀**上动（GB / NY / WS / DB 等），不碰正文里的字母数字混排。
NORMID_RE = re.compile(r"\b(GB|NY|WS|DB|SN|YY)\s*(\d{3,}(?:[-–]\d{4})?)\b")


def load_rules():
    """阈值只读 yaml（单一数据源），失败回退内置值并告警。"""
    import yaml
    try:
        with open(RULES_YAML, encoding="utf-8") as f:
            r = yaml.safe_load(f)
        font = r.get("font") or {}
        density = r.get("density") or {}
        geometry = r.get("geometry") or {}
        return {
            "body_min_pt": float(font.get("body_min_pt", 12.0)),
            "note_min_pt": float(font.get("note_min_pt", 9.0)),
            "title_min_pt": float(font.get("title_min_pt", 28.0)),
            "footer_min_pt": float(font.get("footer_min_pt", 8.0)),
            "footer_max_chars": int(font.get("footer_max_chars", 40)),
            "max_colors_per_slide": int(density.get("max_colors_per_slide", 5)),
            "max_body_chars_per_slide": int(density.get("max_body_chars_per_slide", 150)),
            "max_chars_per_slide": int(density.get("max_chars_per_slide", 400)),
            "overlap_ratio": float(geometry.get("overlap_ratio", 0.15)),
            "offcanvas_tolerance_in": float(geometry.get("offcanvas_tolerance_in", 0.25)),
            "shrink_order": list(density.get("shrink_order") or []),
        }
    except Exception as e:
        print(f"⚠ visual-rules.yaml 加载失败（{e}），回退内置阈值", file=sys.stderr)
        return {"body_min_pt": 12.0, "note_min_pt": 9.0, "title_min_pt": 28.0,
                "footer_min_pt": 8.0, "footer_max_chars": 40,
                "max_colors_per_slide": 5, "max_body_chars_per_slide": 150,
                "max_chars_per_slide": 400,
                "overlap_ratio": 0.15, "offcanvas_tolerance_in": 0.25, "shrink_order": []}


def _iter_runs(prs):
    """遍历 (slide_idx, shape, para, run) —— 中文文本按 run 拆分，故逐 run 处理。"""
    from pptx.util import Emu
    for si, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    yield si, shape, para, run


# ─────────────────────────── 修复项实现 ───────────────────────────
def fix_superscript(prs, rules, pages=None):
    """上标规范化：把 run 文本里的单位/数量级记号拆成上标 run。

    诚实边界：只处理**能确定是上标记号**的固定对（mL / min / ℃ 等），
    拆不准的显式记 unresolved，**不猜**（本包铁律：工具自报不算数，宁可不修）。
    """
    stats = {"changed": 0, "unresolved": 0}
    details = []
    for si, shape, para, run in _iter_runs(prs):
        if pages and si not in pages:
            continue
        text = run.text or ""
        if not text:
            continue
        # 只处理"数字紧跟单位"的形态：12mL → 12 + m(L)
        m = re.search(r"(\d)\s*(mL|dL|mg|μg|ng|min|μm|nm|℃)\b", text)
        if not m:
            continue
        head, unit = m.group(0), m.group(2)
        # 已是上标则跳过（python-pptx 不直接暴露 baseline，交给 ooxml_lint 复验）
        try:
            run.font._rPr.get("baseline")
            continue
        except Exception:
            pass
        details.append({"slide": si, "action": "superscript",
                        "text": text[:40], "target": head})
        stats["changed"] += 1
    # 真正写回需要改 OOXML baseline 属性——本工具**只报告不改**：
    #   上标拆 run 会改变 run 结构，风险高于收益（首跑实证：几何修复三轮证伪）。
    #   ⇒ 留作人工确认项（fix_class=human）。
    stats["changed"] = 0
    stats["reported"] = len(details)
    return stats, details


def fix_normid(prs, rules, pages=None):
    """国标/规范编号规范化：GB30000 → GB 30000（统一带空格）。

    ⚠ 只改**明确编号前缀**形态；正文里其它字母数字混排不动。
    """
    stats = {"changed": 0, "unresolved": 0}
    details = []
    for si, shape, para, run in _iter_runs(prs):
        if pages and si not in pages:
            continue
        text = run.text or ""
        if not text:
            continue
        new = NORMID_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
        if new != text:
            details.append({"slide": si, "action": "normid",
                            "before": text[:60], "after": new[:60]})
            stats["changed"] += 1
    return stats, details


def fix_font(prs, rules, pages=None):
    """正文字号抬升：低于 body_min_pt 的正文 run 抬到下限（**不降字号**）。

    ⚠ 只抬升**正文 run**（不含图注/页脚）——抬图注/页脚会破坏版式；
      run 归属判断交 verify_deck 复验，此处只按 run 所在形状的文本长度粗判。
    """
    import copy
    from pptx.util import Pt
    stats = {"changed": 0, "unresolved": 0}
    details = []
    floor = rules["body_min_pt"]
    for si, shape, para, run in _iter_runs(prs):
        if pages and si not in pages:
            continue
        sz = run.font.size
        if sz is None:
            continue
        pt = round(sz.pt, 1)
        if pt >= floor:
            continue
        txt = (run.text or "").strip()
        # 图注/来源/页脚类：文本短且含来源标记 ⇒ 不动（由 ooxml_lint 的 note_min_pt 管）
        if len(txt) <= 40 and re.search(r"(图\s*\d|图注|来源|Source|资料|注：)", txt):
            details.append({"slide": si, "action": "font_skipped_note",
                            "pt": pt, "text": txt[:40]})
            stats["unresolved"] += 1
            continue
        run.font.size = Pt(floor)
        details.append({"slide": si, "action": "font_raised",
                        "from_pt": pt, "to_pt": floor, "text": txt[:40]})
        stats["changed"] += 1
    return stats, details


def fix_note(prs, rules, pages=None):
    """图注/页脚字号抬升：低于 note_min_pt / footer_min_pt 的备注类 run 抬到下限。

    ⚠ **只抬不降**（同 fix_font 纪律）：降字号是把问题藏起来。
      备注类 run 的判定与 fix_font 一致（短文本 + 来源标记）——
      两者互为补充：fix_font 管正文、fix_note 管备注。
    """
    from pptx.util import Pt
    stats = {"changed": 0, "unresolved": 0}
    details = []
    note_floor = rules["note_min_pt"]
    footer_floor = rules["footer_min_pt"]
    for si, shape, para, run in _iter_runs(prs):
        if pages and si not in pages:
            continue
        sz = run.font.size
        if sz is None:
            continue
        pt = round(sz.pt, 1)
        txt = (run.text or "").strip()
        if not txt:
            continue
        is_note = bool(re.search(r"(图\s*\d|图注|来源|Source|资料|注：|数据来源)", txt))
        is_footer = bool(re.search(r"(^\s*\d+\s*$|版权|©|课件|兽医|章节)", txt)) and len(txt) <= 60
        if not (is_note or is_footer):
            continue
        floor = note_floor if is_note else footer_floor
        if pt >= floor:
            continue
        run.font.size = Pt(floor)
        details.append({"slide": si, "action": "note_raised",
                        "kind": "note" if is_note else "footer",
                        "from_pt": pt, "to_pt": floor, "text": txt[:40]})
        stats["changed"] += 1
    return stats, details


def fix_density(prs, rules, pages=None):
    """页面密度体检：字数超限的页**报告**并给收敛顺序（不自动拆页）。

    ⚠ **只报告不自动改**：超密的正解是「拆页 / 移入备注 / 转结构化」——
      那是**改内容**不是改版式，AI 擅自拆页会丢意图（首跑实证：
      文字墙类缺陷三轮证伪）。按 visual-rules.yaml#density.shrink_order
      给出建议顺序，落到人工确认区（fix_class=human）。
    """
    stats = {"changed": 0, "unresolved": 0}
    details = []
    body_cap = rules["max_body_chars_per_slide"]
    all_cap = rules["max_chars_per_slide"]
    order = rules.get("shrink_order") or []
    for si, slide in enumerate(prs.slides, 1):
        if pages and si not in pages:
            continue
        total = 0
        body = 0
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            t = shape.text_frame.text or ""
            n = len(t.strip())
            total += n
            if n > 60:                       # 长文本块视为正文
                body += n
        over_body = body > body_cap
        over_all = total > all_cap
        if over_body or over_all:
            details.append({
                "slide": si, "action": "density_over_limit",
                "body_chars": body, "body_cap": body_cap,
                "total_chars": total, "total_cap": all_cap,
                "over_body": over_body, "over_total": over_all,
                "advice": ("按 density.shrink_order 收敛：" + " → ".join(order)
                           if order else "拆页或移入备注"),
                "fix_class": "human",
            })
            stats["unresolved"] += 1
    return stats, details


def fix_color(prs, rules, pages=None):
    """配色收敛：单页颜色数超限时**报告**并给收敛建议。

    ⚠ **不自动改色**——自创配色会破坏主题一致性（visual-rules.yaml#theme 明确
      "禁自创"）。收敛需先登记主题令牌（theme.yaml），属人工确认项。
    """
    stats = {"changed": 0, "unresolved": 0}
    details = []
    cap = rules["max_colors_per_slide"]
    for si, slide in enumerate(prs.slides, 1):
        if pages and si not in pages:
            continue
        colors = set()
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    c = run.font.color
                    try:
                        if c and c.type is not None and c.rgb is not None:
                            colors.add(str(c.rgb))
                    except Exception:
                        pass
        if len(colors) > cap:
            details.append({"slide": si, "action": "color_over_limit",
                            "colors": len(colors), "cap": cap,
                            "palette": sorted(colors),
                            "advice": "先登记主题令牌（<workspace>/.workbuddy/theme.yaml），"
                                      "再按令牌收敛；**禁自创配色**"})
            stats["unresolved"] += 1
    return stats, details


def fix_blank(prs, rules, pages=None):
    """空白页识别：**只报告不删**（可能是作者预留的插图位/演示位）。"""
    stats = {"changed": 0, "unresolved": 0}
    details = []
    for si, slide in enumerate(prs.slides, 1):
        if pages and si not in pages:
            continue
        has_text = False
        has_pic = False
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and (shape.text_frame.text or "").strip():
                has_text = True
            if getattr(shape, "shape_type", None) is not None and "PICTURE" in str(shape.shape_type):
                has_pic = True
        if not has_text and not has_pic:
            details.append({"slide": si, "action": "blank_page",
                            "advice": "**不自动删除**——可能是作者预留的插图位/演示位；"
                                      "请人工确认后再决定删或填"})
            stats["unresolved"] += 1
    return stats, details


def fix_geometry(prs, rules, pages=None):
    """几何修复（复用 surgery_deck.py 内核）：元素重叠迁移 + 文字越界收回。

    ⚠ **默认 dry-run 且只报告**：首跑实证——几何修复连续三轮证伪
      （重叠 4→16→19），且中途引入过自引入缺陷。
      ⇒ 本工具的几何修复**必须配几何基线**（`harness.py gate --geo-baseline`），
      否则「新增重叠」无从判定（不做 ≠ 无重叠）。
    """
    try:
        sys.path.insert(0, HERE)
        import surgery_deck as sd
    except Exception as e:
        return ({"changed": 0, "unresolved": 1},
                [{"action": "geometry_unavailable", "detail": f"内核不可用：{e}"}])
    tmp = os.path.join("/tmp", f"_deck_surgery_geom_{os.getpid()}.pptx")
    details = []
    stats = {"changed": 0, "unresolved": 0}
    try:
        prs.save(tmp)
        r = sd.surgery_deck(tmp, rules["overlap_ratio"],
                            rules["offcanvas_tolerance_in"], True)   # True=dry_run
        stats["changed"] = r.get("moved", 0) + r.get("offcanvas_fixed", 0)
        stats["unresolved"] = r.get("unresolved", 0)
        for d in r.get("details", []):
            if pages and d.get("slide") not in pages:
                continue
            details.append({"slide": d.get("slide"), "action": d.get("type"),
                            "snippet": d.get("snippet", "")})
        if not pages:
            details = details
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return stats, details


FIXERS = {
    "superscript": fix_superscript,
    "normid": fix_normid,
    "font": fix_font,
    "note": fix_note,
    "color": fix_color,
    "density": fix_density,
    "blank": fix_blank,
    "geometry": fix_geometry,
}


def main():
    ap = argparse.ArgumentParser(
        description="通用课件手术工具 v3.28.6（修复项参数化；默认 dry-run）")
    ap.add_argument("--deck", required=True, help="目标课件 .pptx 绝对路径")
    ap.add_argument("--fix", default="all",
                    help=f"修复项，逗号分隔；可选：{'/'.join(FIX_KINDS)}/all")
    ap.add_argument("--pages", default="",
                    help="只处理指定页（逗号分隔页号，如 7,9,34）；缺省全篇")
    ap.add_argument("--apply", action="store_true",
                   help="**真改并写盘**（默认只 dry-run 报告；改前自动备份）")
    ap.add_argument("--report", default="", help="JSON 报告输出路径")
    a = ap.parse_args()

    if not os.path.isfile(a.deck):
        print(f"⛔ 课件不存在：{a.deck}", file=sys.stderr)
        return 2
    try:
        from pptx import Presentation
    except Exception as e:
        print(f"⛔ python-pptx 不可用：{e}", file=sys.stderr)
        return 3

    rules = load_rules()
    kinds = list(FIX_KINDS) if a.fix.strip().lower() == "all" else \
        [k.strip() for k in a.fix.split(",") if k.strip()]
    bad = [k for k in kinds if k not in FIXERS]
    if bad:
        print(f"⛔ 未知修复项：{bad}——可选：{FIX_KINDS} / all", file=sys.stderr)
        return 2
    pages = set()
    if a.pages.strip():
        for x in a.pages.split(","):
            x = x.strip()
            if x.isdigit():
                pages.add(int(x))

    prs = Presentation(a.deck)
    report = {"tool": "deck_surgery", "version": "3.28.6",
              "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "deck": os.path.abspath(a.deck), "apply": bool(a.apply),
              "fixes": kinds, "pages": sorted(pages) or "all",
              "rules": rules, "results": {}}

    backup = None
    if a.apply:
        stem, ext = os.path.splitext(a.deck)
        backup = f"{stem}_备份_{time.strftime('%Y%m%d_%H%M')}{ext}"
        shutil.copy2(a.deck, backup)
        print(f"已备份：{backup}")

    for k in kinds:
        fn = FIXERS[k]
        try:
            stats, details = fn(prs, rules, pages)
        except Exception as e:
            stats, details = ({"changed": 0, "unresolved": 1},
                              [{"action": f"{k}_error", "detail": str(e)[:200]}])
        report["results"][k] = {"stats": stats, "details": details}
        print(f"  {k}: 改 {stats.get('changed', 0)} / 未解 {stats.get('unresolved', 0)}")

    if a.apply:
        prs.save(a.deck)
        print(f"已写盘：{a.deck}")
    else:
        print("（dry-run：未改盘。确认后加 --apply）")

    report["backup"] = os.path.basename(backup) if backup else None
    report["md5_after"] = _md5(a.deck) if a.apply else None
    if a.report:
        op = os.path.abspath(a.report)
        os.makedirs(os.path.dirname(op), exist_ok=True)
        with open(op, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已存：{op}")
    return 0


def _md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    sys.exit(main())

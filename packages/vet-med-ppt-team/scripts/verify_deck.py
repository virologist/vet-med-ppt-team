#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_deck.py — 教学课件机械验证器（70% 机械验证的裁判）

设计原则：以"教学PPT为第一性原理、学生利益最大化"反向设阈值。
所有判定必须是机器可执行、可复现、可 diff 的，禁止模型自评。

检查项（8 项 + 分级门禁 v2.0.0）：
  1. 字号红线      —— 正文 <12pt、图注/来源 <9pt 违规        [P0]
  2. 越界          —— 文字元素超画布                        [P0]
  3. 元素重叠      —— 文字框相互遮挡（学生看不见 = 零价值）  [P1]
  4. 配色混乱      —— 单页颜色数超阈值（视觉噪音）          [P0]
  5. 文字墙        —— 单页字符数超限（认知负荷过载）        [P1]
  6. 空白页        —— 无内容页                              [P0]
  7. 课时匹配      —— 页数 vs 课时标准                      [P0]
  8. 结构性完备    —— 目录页/题页 [P0]；备注覆盖率 [P2]

分级门禁（v2.0.0，防"全清不可达→门禁必被绕过"）：
  P0 硬阻断：写回磁盘前必须为 0（任何 level 下都阻断）
  P1 必清  ：允许中途写盘（须带修复计划），交付前必须为 0
  P2 指标  ：备注覆盖率 ≥ gate.p2_note_coverage（默认 80%），交付级阻断
  P3 明示  ：继承字号未取到 / 判定异常 / 装饰出血——不阻断，必须明示

用法：
  python3 verify_deck.py <课件.pptx> [--hours 3] [--level P0|P1|all] [--json out.json] [--strict]

  --level P0   写回门禁：仅 P0 阻断
  --level P1   中检门禁：P0+P1 阻断
  --level all  交付门禁（默认）：P0+P1+P2(覆盖率) 阻断

退出码：0=通过(所请求 level) / 1=P0阻断 / 2=P1阻断 / 3=P2阻断 / 4=运行错误
v2.0.0 起：单页/单形状解析异常不再崩溃退出（XML 兜底继续判，异常计入 P3 明示）。

依赖：pip install python-pptx pyyaml
"""

import argparse
import json
import sys
from collections import Counter

try:
    from pptx import Presentation
    from pptx.util import Emu
    from pptx.oxml.ns import qn
except ImportError:
    print("缺少依赖：pip install python-pptx", file=sys.stderr)
    sys.exit(4)

# ============ 阈值与分级（单一数据源：config/visual-rules.yaml；回退=内置值）============
# v1.9.0：红线参数化。v2.0.0：分级映射与 P2 覆盖率同样参数化。
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
    "p2_note_coverage": 0.80,
    "severity": {
        "P0": ["字号过小", "文字越界", "配色混乱", "空白页", "课时不达标", "缺目录页", "缺题页"],
        "P1": ["元素重叠", "文字墙"],
        "P2": ["缺备注"],
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
        th = {
            "body_min_pt": float(rules["font"]["body_min_pt"]),
            "note_min_pt": float(rules["font"]["note_min_pt"]),
            "max_colors_per_slide": int(rules["density"]["max_colors_per_slide"]),
            "max_chars_per_slide": int(rules["density"]["max_chars_per_slide"]),
            "overlap_ratio": float(rules["geometry"]["overlap_ratio"]),
            "hours_page_range": hpr,
            "p2_note_coverage": 0.80,
            "severity": dict(_FALLBACK["severity"]),
        }
        gate = rules.get("gate") or {}
        if "p2_note_coverage" in gate:
            th["p2_note_coverage"] = float(gate["p2_note_coverage"])
        sev = rules.get("severity") or {}
        for lv in ("P0", "P1", "P2"):
            if lv in sev:
                th["severity"][lv] = list(sev[lv])
        return th
    except Exception as e:
        # v2.2.0：yaml 是红线唯一数据源，读不到 = 裁判失去准星。
        # 静默回退会让"门禁通过"建立在未授权阈值上（护栏可绕过），故改为硬失败，
        # 仅当显式设置环境变量 VERIFY_ALLOW_FALLBACK=1 才允许回退（并醒目告警）。
        msg = (f"⛔ visual-rules.yaml 加载失败（{e}）——红线唯一数据源不可用，"
               f"拒绝使用内置回退阈值继续裁判。")
        if os.environ.get("VERIFY_ALLOW_FALLBACK") == "1":
            print(msg + "（已显式开启 VERIFY_ALLOW_FALLBACK=1，按内置阈值继续，结果仅供参考）",
                  file=sys.stderr)
            return dict(_FALLBACK)
        print(msg + " 修复 yaml 后重跑；确需临时放行请设 VERIFY_ALLOW_FALLBACK=1。", file=sys.stderr)
        raise

THRESHOLD = _load_threshold()

# v3.0.0：机器草稿标记（与 inject_notes.py 注入的标记一致）。
# 裁决④：机器草稿**计入** P2 覆盖率，但必须单独统计占比并在交付物明示。
_MACHINE_NOTE_MARK = "AI草稿"

# 问题类型 → 分级（从 yaml severity 反转生成）
_TYPE_LEVEL = {}
for _lv in ("P0", "P1", "P2"):
    for _t in THRESHOLD["severity"].get(_lv, []):
        _TYPE_LEVEL[_t] = _lv

EMU_PER_INCH = 914400

# XML 兜底命名空间（抗崩溃：python-pptx 不认识的 shape 包装层，如 mc:AlternateContent）
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _pt(size):
    """EMU/pt 统一转为 pt；None 返回 None（表示继承，由调用方处理）"""
    if size is None:
        return None
    return round(size.pt, 1) if hasattr(size, "pt") else round(size / 12700.0, 1)


# ============ 字号继承解析（v2.0.0：消"字号继承(未取到)"盲区）============

def _sz_from_defrpr(elmgiving):
    """从 a:defRPr 元素取 sz（百磅分之 pt → pt）；无则 None"""
    if elmgiving is None:
        return None
    d = elmgiving.find(qn("a:defRPr"))
    if d is not None and d.get("sz"):
        try:
            return int(d.get("sz")) / 100.0
        except Exception:
            return None
    return None


def _lvl1_sz(styles_elm):
    """从 txStyles 节点取 lvl1pPr/defRPr 的 sz"""
    if styles_elm is None:
        return None
    lvl1 = styles_elm.find(qn("a:lvl1pPr"))
    return _sz_from_defrpr(lvl1)


def _master_style_sz(slide, ph_type):
    """母版 txStyles 兜底：标题类→titleStyle，正文类→bodyStyle，其余→otherStyle"""
    try:
        from pptx.enum.shapes import PP_PLACEHOLDER
        master = slide.slide_layout.slide_master
        txs = master.element.find(qn("p:txStyles"))
        if txs is None:
            return None
        if ph_type in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
            return _lvl1_sz(txs.find(qn("p:titleStyle")))
        if ph_type in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.VERTICAL_BODY, PP_PLACEHOLDER.SUBTITLE):
            return _lvl1_sz(txs.find(qn("p:bodyStyle")))
        return _lvl1_sz(txs.find(qn("p:otherStyle")))
    except Exception:
        return None


def _layout_ph_sz(slide, shape):
    """版式同名占位符的 lstStyle / 段落 defRPr 兜底"""
    try:
        idx = shape.placeholder_format.idx
        for lph in slide.slide_layout.placeholders:
            if lph.placeholder_format.idx != idx:
                continue
            txBody = lph._element.find(qn("p:txBody"))
            if txBody is None:
                continue
            lst = txBody.find(qn("a:lstStyle"))
            s = _lvl1_sz(lst)
            if s is not None:
                return s
            for p in txBody.findall(qn("a:p")):
                pPr = p.find(qn("a:pPr"))
                s = _sz_from_defrpr(pPr)
                if s is not None:
                    return s
        return None
    except Exception:
        return None


def _resolve_run_sz(para, run, shape, slide):
    """run 字号解析链：run.rPr → 段落 defRPr → 版式占位符 → 母版 txStyles；全空返回 None"""
    s = run.font.size
    if s is not None:
        return _pt(s)
    # 段落级 defRPr
    try:
        pPr = para._p.find(qn("a:pPr"))
        s = _sz_from_defrpr(pPr)
        if s is not None:
            return s
    except Exception:
        pass
    # 占位符链（仅占位符形状值得走，普通文本框母版一般无字号语义）
    try:
        if shape.is_placeholder:
            ph_type = shape.placeholder_format.type
            s = _layout_ph_sz(slide, shape)
            if s is not None:
                return s
            s = _master_style_sz(slide, ph_type)
            if s is not None:
                return s
    except Exception:
        pass
    return None


def _shape_font_sizes(shape, slide):
    """尽力取字号：run → 段落 → 版式 → 母版继承。返回 (sizes, unresolved_runs)"""
    sizes = []
    unresolved = 0
    if not shape.has_text_frame:
        return sizes, unresolved
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            try:
                pt = _resolve_run_sz(para, run, shape, slide)
            except Exception:
                pt = None
            if pt is not None:
                sizes.append(pt)
            else:
                unresolved += 1
    return sizes, unresolved


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


# ============ 形状适配器（v2.0.0 抗崩溃：主路径失败 → XML 兜底）============

def _extract_shape(shape, slide):
    """把 python-pptx shape 归一化为只读适配器；任何异常都截获，不让裁判崩。"""
    a = {
        "ok": True, "err": None,
        "text": "", "has_tf": False,
        "rect": None, "sizes": [], "unresolved_runs": 0,
        "colors": set(), "is_pic": False,
    }
    try:
        if shape.shape_type == 13:  # PICTURE
            a["is_pic"] = True
    except Exception as e:
        a["ok"] = False
        a["err"] = f"shape_type: {e}"
        return a
    try:
        if shape.has_text_frame:
            a["has_tf"] = True
            a["text"] = shape.text_frame.text.strip()
    except Exception as e:
        a["ok"] = False
        a["err"] = f"text_frame: {e}"
        return a
    try:
        a["rect"] = _rect(shape)
    except Exception:
        a["rect"] = None
    if a["has_tf"]:
        try:
            a["sizes"], a["unresolved_runs"] = _shape_font_sizes(shape, slide)
        except Exception as e:
            a["ok"] = False
            a["err"] = f"font: {e}"
            return a
        try:
            a["colors"] = _shape_colors(shape)
        except Exception:
            a["colors"] = set()
    return a


def _xml_sz(rpr):
    """XML 兜底：从 rPr/defRPr 元素取 sz 属性（百分之一 pt）"""
    if rpr is None:
        return None
    sz = rpr.get("sz")
    if sz:
        try:
            return int(sz) / 100.0
        except Exception:
            return None
    return None


def _extract_sp_xml(elm):
    """XML 兜底解析 p:sp（python-pptx 工厂不认识的包装层里的形状）"""
    a = {"ok": True, "err": None, "text": "", "has_tf": False,
         "rect": None, "sizes": [], "unresolved_runs": 0,
         "colors": set(), "is_pic": False}
    try:
        a["has_tf"] = elm.find(qn("p:txBody")) is not None
        texts = [t.text or "" for t in elm.findall(".//" + qn("a:t"))]
        a["text"] = " ".join(texts).strip()
        xfrm = elm.find(".//" + qn("a:xfrm"))
        if xfrm is not None:
            off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
            if off is not None and ext is not None:
                a["rect"] = (int(off.get("x", 0)), int(off.get("y", 0)),
                             int(ext.get("cx", 0)), int(ext.get("cy", 0)))
        for rpr in elm.findall(".//" + qn("a:rPr")):
            s = _xml_sz(rpr)
            if s is not None:
                a["sizes"].append(s)
        for d in elm.findall(".//" + qn("a:defRPr")):
            s = _xml_sz(d)
            if s is not None:
                a["sizes"].append(s)
        if not a["sizes"] and a["text"]:
            a["unresolved_runs"] = 1
        for c in elm.findall(".//" + qn("a:srgbClr")):
            v = c.get("val")
            if v:
                a["colors"].add(v.upper())
    except Exception as e:
        a["ok"] = False
        a["err"] = str(e)
    return a


def _slide_shape_adapters(slide, stats):
    """逐页形状适配器列表；主路径崩溃时 XML 兜底，异常全部计数进 P3 明示。"""
    adapters = []
    try:
        it = list(slide.shapes)
    except Exception:
        # 主路径整页失败（如 mc:AlternateContent 包装）→ XML 兜底
        try:
            spTree = slide.shapes._spTree
        except Exception as e:
            stats["parse_errors"] += 1
            return adapters, f"spTree不可达：{e}"
        n_pic = 0
        for tag in ("p:sp", "p:pic"):
            for elm in spTree.findall(".//" + qn(tag)):
                if tag == "p:pic":
                    n_pic += 1
                    continue
                ad = _extract_sp_xml(elm)
                if not ad["ok"]:
                    stats["parse_errors"] += 1
                adapters.append(ad)
        stats["xml_fallback_slides"] += 1
        return adapters, None
    # 主路径：逐 shape 归一化，单个失败不断页
    for shape in it:
        try:
            if getattr(shape, "shape_type", None) == 13:
                adapters.append({"ok": True, "err": None, "text": "", "has_tf": False,
                                 "rect": None, "sizes": [], "unresolved_runs": 0,
                                 "colors": set(), "is_pic": True})
                continue
        except Exception:
            pass
        ad = _extract_shape(shape, slide)
        if not ad["ok"]:
            stats["parse_errors"] += 1
        adapters.append(ad)
    return adapters, None


def verify(path, hours=3, strict=False):
    prs = Presentation(path)
    sw, sh = prs.slide_width, prs.slide_height
    issues = []
    stats = {
        "file": path,
        "total_slides": len(prs.slides),
        "visible_slides": 0,
        "hidden_slides": 0,
        "hours": hours,
        "small_body": 0, "small_note": 0, "offcanvas": 0,
        "overlap": 0, "color_chaos": 0, "text_wall": 0,
        "empty_slides": 0, "no_notes": 0, "unknown_font": 0,
        "bleed_decor": 0, "parse_errors": 0, "xml_fallback_slides": 0,
        "machine_notes": 0,
    }

    visible = []
    for idx, slide in enumerate(prs.slides, 1):
        # 隐藏页跳过（R7 起用隐藏而非删除保留内容）；数量单独统计（v2.0.0 纳管）
        if slide._element.get("show") == "0":
            stats["hidden_slides"] += 1
            continue
        visible.append((idx, slide))
    stats["visible_slides"] = len(visible)

    has_toc = False          # 目录页
    has_quiz = False         # 题页
    for idx, slide in visible:
        adapters, fb_err = _slide_shape_adapters(slide, stats)

        text_adapters = [a for a in adapters if a["has_tf"] and a["text"]]
        page_text = " ".join(a["text"] for a in text_adapters)

        # 结构性识别
        if any(k in page_text for k in ("目录", "CONTENTS", "内容导航")):
            has_toc = True
        if any(k in page_text for k in ("思考题", "练习题", "课堂提问", "随堂测", "Q1", "答案")):
            has_quiz = True

        # ---------- 1. 字号 ----------
        for a in text_adapters:
            if not a["sizes"]:
                if a["unresolved_runs"]:
                    stats["unknown_font"] += 1
                continue
            # v2.2.0 修复：sizes 可能含 None（部分 run 字号解析失败），
            # min() 会返回 None，随后与阈值比较抛 TypeError → 整个门禁崩溃（exit 4）。
            _sizes = [s for s in a["sizes"] if s is not None]
            if not _sizes:
                # 一个有效字号都没解析出来 → 记 P3「未知」，不参与 P0 判定
                stats["unknown_font"] += 1
                continue
            min_s = min(_sizes)
            txt = a["text"]
            is_note = _is_note_candidate(txt)
            limit = THRESHOLD["note_min_pt"] if is_note else THRESHOLD["body_min_pt"]
            if min_s < limit:
                if is_note:
                    stats["small_note"] += 1
                else:
                    stats["small_body"] += 1
                issues.append({
                    "slide": idx, "type": "字号过小",
                    "detail": f"{min_s}pt < {limit}pt（{'图注/来源' if is_note else '正文'}）",
                    "snippet": txt[:30],
                })
            elif strict and a["unresolved_runs"]:
                # 严格模式：仍有 run 解析不出字号 → 视为 P0 违规
                stats["unknown_font"] += 1
                issues.append({
                    "slide": idx, "type": "字号过小",
                    "detail": f"{min_s}pt 且 {a['unresolved_runs']} 个 run 字号未解析（strict）",
                    "snippet": txt[:30],
                })

        # ---------- 2. 越界（只判有文本的元素；无文本装饰按"出血设计"放行）----------
        tol = EMU_PER_INCH * 0.25
        for a in adapters:
            r = a["rect"]
            if r is None or not a["text"]:
                continue
            # v2.2.0 修复：rect 四元组可能含 None（部分形状几何取不到，XML 兜底也失败），
            # 直接参与比较会抛 TypeError 使整个门禁崩溃。取不到几何 = 该形状无法判定，
            # 记 parse_errors（P3 明示），绝不因此让整份课件失去裁判。
            if any(v is None for v in r):
                stats["parse_errors"] += 1
                continue
            x, y, w, h = r
            if (x < -tol or y < -tol or x + w > sw + tol or y + h > sh + tol):
                stats["offcanvas"] += 1
                issues.append({
                    "slide": idx, "type": "文字越界",
                    "detail": f"位置({round(x/EMU_PER_INCH,2)},{round(y/EMU_PER_INCH,2)})in "
                              f"尺寸({round(w/EMU_PER_INCH,2)}x{round(h/EMU_PER_INCH,2)})in "
                              f"画布({round(sw/EMU_PER_INCH,2)}x{round(sh/EMU_PER_INCH,2)})in",
                    "snippet": a["text"][:30],
                })
        # 无文本越界 = 装饰出血（合法设计）
        for a in adapters:
            r = a["rect"]
            if r is None or a["text"] or a["is_pic"]:
                continue
            if any(v is None for v in r):      # v2.2.0：同上，几何取不到不参与比较
                stats["parse_errors"] += 1
                continue
            x, y, w, h = r
            if (x < -tol or y < -tol or x + w > sw + tol or y + h > sh + tol):
                stats["bleed_decor"] += 1

        # ---------- 3. 元素重叠（学生看不见 = 零价值）----------
        for i in range(len(text_adapters)):
            for j in range(i + 1, len(text_adapters)):
                ra, rb = text_adapters[i]["rect"], text_adapters[j]["rect"]
                # v2.2.0：rect 为 None 已挡，但四元组内部元素仍可能是 None（几何取不到），
                # 会把 None 传进 _overlap_area 做 max()/min() 比较而崩溃。
                if (ra is None or rb is None
                        or any(v is None for v in ra) or any(v is None for v in rb)):
                    continue
                inter, smaller = _overlap_area(ra, rb)
                if smaller > 0 and inter / smaller > THRESHOLD["overlap_ratio"]:
                    stats["overlap"] += 1
                    issues.append({
                        "slide": idx, "type": "元素重叠",
                        "detail": f"两文本框重叠 {round(inter/smaller*100)}%",
                        "snippet": text_adapters[i]["text"][:20] + " ✕ " + text_adapters[j]["text"][:20],
                    })

        # ---------- 4. 配色混乱 ----------
        page_colors = set()
        for a in adapters:
            page_colors |= a["colors"]
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
        has_pic = any(a["is_pic"] for a in adapters)
        if not text_adapters and not has_pic:
            stats["empty_slides"] += 1
            issues.append({"slide": idx, "type": "空白页", "detail": "无文本无图片", "snippet": ""})

        # ---------- 8. 备注 ----------
        try:
            note_text = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        except Exception:
            note_text = ""
        has_note = bool(note_text)
        # v3.0.0：机器草稿单独计数（裁决④：机器草稿计入覆盖率，但必须单独统计占比并在交付物明示）
        if has_note and _MACHINE_NOTE_MARK in note_text:
            stats["machine_notes"] += 1
        if not has_note:
            stats["no_notes"] += 1
            issues.append({"slide": idx, "type": "缺备注", "detail": "该页无讲稿备注", "snippet": ""})

    # ---------- 7. 课时匹配 ----------
    lo, hi = THRESHOLD["hours_page_range"].get(hours, (0, 9999))
    n = stats["visible_slides"]
    hours_ok = lo <= n <= hi
    if not hours_ok:
        issues.append({"slide": 0, "type": "课时不达标",
                       "detail": f"可见{n}页，{hours}课时标准({lo}-{hi}页)", "snippet": ""})
    if not has_toc:
        issues.append({"slide": 0, "type": "缺目录页", "detail": "未识别到目录页", "snippet": ""})
    if not has_quiz:
        issues.append({"slide": 0, "type": "缺题页", "detail": "未识别到题页", "snippet": ""})

    stats["has_toc"] = has_toc
    stats["has_quiz"] = has_quiz
    stats["hours_ok"] = hours_ok

    # ---------- 分级计数（v2.0.0）----------
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
    p0 = sum(v for k, v in red.items() if _TYPE_LEVEL.get(k.split("(")[0], "P0") == "P0")
    p1 = sum(v for k, v in red.items() if _TYPE_LEVEL.get(k.split("(")[0], "P1") == "P1")

    note_cov = 1.0 if n == 0 else round((n - stats["no_notes"]) / n, 3)
    p2_block = note_cov < THRESHOLD["p2_note_coverage"]
    # 机器草稿占比（裁决④）：计入覆盖率，但必须单独报出，供交付物明示
    noted = n - stats["no_notes"]
    machine_ratio = round(stats["machine_notes"] / noted, 3) if noted else 0.0

    p3 = stats["unknown_font"] + stats["parse_errors"] + stats["bleed_decor"]

    stats["note_coverage"] = note_cov
    stats["machine_note_pages"] = stats["machine_notes"]
    stats["machine_note_ratio"] = machine_ratio

    return {"stats": stats, "red": red, "issues": issues,
            "gate": {"p0": p0, "p1": p1, "note_coverage": note_cov,
                     "p2_threshold": THRESHOLD["p2_note_coverage"],
                     "p2_block": p2_block, "p3": p3,
                     "machine_note_ratio": machine_ratio,
                     "machine_note_pages": stats["machine_notes"]}}


def gate_decision(gate, level):
    """按请求 level 返回 (blocked_by, exit_code)。blocked_by ∈ {None,'P0','P1','P2'}"""
    if gate["p0"] > 0:
        return "P0", 1
    if level in ("P1", "all") and gate["p1"] > 0:
        return "P1", 2
    if level == "all" and gate["p2_block"]:
        return "P2", 3
    return None, 0


# ─────────────────────── 闸4.5 三源核验（v3.3.0）───────────────────
def three_source_check(workspace: str, deck: str) -> dict:
    """闸4.5：抽 10% unverified=true 案例，查 sources 字段，输出通过率。

    Args:
        workspace: 课程工作区根（含 .workbuddy/cases/cases_library.json）
        deck: 当前 deck 路径（仅用于过滤"此 deck 的案例"——非全库）

    Returns:
        dict: {total, sampled, unverified_sampled, verified_sampled, pass_rate, threshold, verdict, samples}
        verdict: "pass" (≥80%) / "needs_more_verification" (<80%)
    """
    import json
    import random
    from pathlib import Path

    # 1. 读 cases_library
    cases_p = Path(workspace) / ".workbuddy" / "cases" / "cases_library.json"
    if not cases_p.exists():
        return {"verdict": "no_library", "error": f"未找到 {cases_p}",
                "pass_rate": 0.0, "threshold": 0.8, "total": 0, "sampled": 0}

    with open(cases_p, encoding="utf-8") as f:
        lib = json.load(f)
    cases = lib.get("cases", [])

    # 2. 过滤：当前 deck 的案例（按 deck_path 后缀匹配）
    deck_name = Path(deck).name
    deck_cases = [c for c in cases if Path(c.get("deck_path", "")).name == deck_name]
    unverified = [c for c in deck_cases if c.get("unverified", True)]

    # 3. 抽 10%（domain_config.yaml 默认 sample_rate=0.1）
    sample_n = max(1, int(len(unverified) * 0.1))
    sampled = random.sample(unverified, min(sample_n, len(unverified)))

    # 4. 验 sources：每个样本检查 sources 列表是否至少 1 条 ok=true
    verified = 0
    for s in sampled:
        sources = s.get("sources", [])
        if any(src.get("ok") is True for src in sources):
            verified += 1

    pass_rate = verified / max(len(sampled), 1)
    threshold = 0.8
    return {
        "deck": deck_name,
        "total_in_deck": len(deck_cases),
        "unverified_in_deck": len(unverified),
        "sampled": len(sampled),
        "verified": verified,
        "pass_rate": round(pass_rate, 3),
        "threshold": threshold,
        "verdict": "pass" if pass_rate >= threshold else "needs_more_verification",
        "samples": [{"case_id": s.get("case_id"), "title": s.get("title"),
                     "sources_count": len(s.get("sources", [])),
                     "verified": any(src.get("ok") is True for src in s.get("sources", []))}
                    for s in sampled[:5]],  # 仅展示前 5
    }


def main():
    ap = argparse.ArgumentParser(description="教学课件机械验证器（分级门禁 v2.0.0 + v3.3.0 三源核验）")
    ap.add_argument("deck", help="课件路径 .pptx")
    ap.add_argument("--hours", type=float, required=True,
                    help="课时数（v3.0.0 起必填：1 / 1.5 / 2 / 3 / 4。"
                         "不再默认 3——默认值会凭空判出「课时不达标」，是 B0 口径混乱的源头之一。"
                         "1.5=1小时教学单元60min档；扩展阅读页不计入可见页，由阶段0 冻结口径")
    ap.add_argument("--level", choices=["P0", "P1", "all"], default="all",
                    help="门禁级别：P0=写回门禁 / P1=中检门禁 / all=交付门禁（默认）")
    ap.add_argument("--json", help="输出 JSON 报告路径")
    ap.add_argument("--strict", action="store_true", help="严格模式：未解析字号也判 P0")
    ap.add_argument("--limit", type=int, default=25, help="终端最多打印多少条问题")
    # v3.3.0：闸4.5 案例三源核验模式
    ap.add_argument("--three-source-check", action="store_true",
                    help="闸4.5：读 <workspace>/.workbuddy/cases/cases_library.json，"
                         "抽 10% unverified=true 案例检查 sources 字段，输出核验通过率；"
                         "≥80% 达标（domain_config.yaml#three_source_check.pass_threshold）")
    ap.add_argument("--workspace", default="",
                    help="--three-source-check 必填：课程工作区根（含 .workbuddy/cases/）")
    a = ap.parse_args()

    # v3.3.0 短路：--three-source-check 模式只跑三源核验，不跑主门禁
    if a.three_source_check:
        try:
            r = three_source_check(a.workspace, a.deck)
        except Exception as e:
            import traceback
            print(f"运行错误（三源核验）：{e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(4)
        import json as _json
        print(_json.dumps(r, ensure_ascii=False, indent=2))
        if a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                _json.dump(r, f, ensure_ascii=False, indent=2)
        # 退出码：1=未达标 / 0=达标
        sys.exit(0 if r.get("verdict") == "pass" else 1)

    try:
        r = verify(a.deck, a.hours, a.strict)
    except Exception as e:
        # v2.0.0：致命错误退出码 4（不再与 P1 的 2 混淆）
        # v2.2.0：必须打印 traceback —— 只打一行信息时，主理人无法区分
        #         "课件有问题" 与 "脚本有 bug"，曾导致崩溃被当成红灯打回成员。
        import traceback
        print(f"运行错误：{e}", file=sys.stderr)
        print(f"错误类型：{type(e).__name__}", file=sys.stderr)
        print("堆栈（用于缺陷回流，请附在 issue/CHANGELOG）：", file=sys.stderr)
        traceback.print_exc()
        print("\n处置指引：exit=4 属【运行错误】而非课件质量问题——"
              "① 先确认文件是 .pptx（.ppt 老格式会报 Package not found）；"
              "② 若是脚本异常，走缺陷回流修脚本，不得当作红灯打回成员；"
              "③ 完整上下文见 scripts/harness.py gate 写入的 trace。", file=sys.stderr)
        sys.exit(4)

    s = r["stats"]
    g = r["gate"]
    blocked_by, code = gate_decision(g, a.level)

    print(f"\n{'='*62}\n课件验证报告：{s['file']}")
    print(f"裁判：SSOT verify_deck.py（分级门禁 v3.0.0）｜阈值源 config/visual-rules.yaml"
          f"｜等级 {a.level}｜课时口径 {a.hours}（显式声明）")
    print(f"总页 {s['total_slides']} / 可见 {s['visible_slides']} / 隐藏 {s['hidden_slides']} / 课时 {s['hours']}")
    print(f"目录页:{'✓' if s['has_toc'] else '✗'}  题页:{'✓' if s['has_quiz'] else '✗'}  课时匹配:{'✓' if s['hours_ok'] else '✗'}")
    print(f"{'='*62}")

    print("分级门禁（v3.0.0）：")
    print(f"  {'🔴' if g['p0'] else '🟢'} P0 硬阻断（写回前必须=0）      {g['p0']}")
    print(f"  {'🔴' if g['p1'] else '🟢'} P1 必清（交付前必须=0）        {g['p1']}")
    cov = f"{g['note_coverage']*100:.1f}%"
    print(f"  {'🔴' if g['p2_block'] else '🟢'} P2 备注覆盖率（阈值 {g['p2_threshold']*100:.0f}%）  {cov}")
    if g.get("machine_note_pages"):
        print(f"    ├ 其中机器草稿【AI草稿·待教师复核】：{g['machine_note_pages']} 页"
              f"（占已备注文 {g['machine_note_ratio']*100:.0f}%）——计入覆盖率，"
              f"但交付物必须明示并经教师复核后转正")
    else:
        print(f"    └ 机器草稿 0 页（备注均为人工/AI-协作产出）")
    print(f"  ⚪ P3 明示（继承未取到/解析异常/装饰出血）  {g['p3']}")
    if s["xml_fallback_slides"]:
        print(f"  ⚠ XML 兜底解析页数：{s['xml_fallback_slides']}（该页部分形状经原始XML判定）")
    if s["parse_errors"]:
        print(f"  ⚠ 解析异常形状：{s['parse_errors']}（已跳过不崩溃，人工抽检）")

    print("红绿灯明细：")
    for k, v in r["red"].items():
        flag = "🟢" if v == 0 else "🔴"
        print(f"  {flag} {k:16s} {v}")

    verdict = {None: "✅ 通过（level=" + a.level + "）",
               "P0": "❌ P0 硬阻断——写回磁盘禁止，先清 P0",
               "P1": "❌ P1 阻断——可带修复计划写回，交付前必须清零",
               "P2": "❌ P2 阻断——备注覆盖率未达标"}[blocked_by]
    print(f"\n{'='*62}")
    print(f"结论：{verdict}")
    if r["issues"]:
        print(f"\n问题明细（前 {a.limit} 条，共 {len(r['issues'])} 条）：")
        for i in r["issues"][:a.limit]:
            print(f"  P{i['slide']:<3} [{i['type']}] {i['detail']}  {i['snippet']}")

    if a.json:
        r["exit_code"] = code
        r["level"] = a.level
        # v3.0.0：裁判溯源信息随报告落盘——台账据此判断这条结论出自哪份脚本
        r["judge"] = {
            "script": os.path.abspath(__file__),
            "role": "SSOT",
            "version": "3.0.0",
            "level_arg": a.level,
            "hours_arg": a.hours,
            "thresholds": os.path.abspath(_RULES_PATH),
        }
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告已存：{a.json}")

    sys.exit(code)


if __name__ == "__main__":
    main()

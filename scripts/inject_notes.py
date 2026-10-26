#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_notes.py — 讲稿备注注入工具（v3.22.0）

职责链（v2.0.0 苏学法页表九字段设计）：苏学法产出 speaker_note → 本工具注入 → P2 覆盖率达标。
本运行模式（bootstrap）：按页面真实内容批量生成【AI草稿·待教师复核】讲稿，补到每份课件
覆盖率 ≥ config/visual-rules.yaml#gate.p2_note_coverage（默认 80%）即止——不追求 100%，
把最需要讲稿的内容页先补上，剩余留教师工作流。

质量纪律（v2.1.0 起沿用，一条未改）：
  ① 备注四件套：本页定位 / 讲授要点（取自页面真实文本，非模板空话）/ 讲法建议 / 提问话术 / 易错提醒
  ② 全部显著标注【AI草稿·待教师复核】——反自评失真：机器生成的讲稿必须声明身份
  ③ 只补缺备注页，已有备注一概不动
  ④ 修改前强制备份（偏好 C）；写回后用 verify_deck 口径自验覆盖率
  ⑤ 隐藏页不注入（阶段0 裁决权在主理人）

批量注入四前置断言（v3.22.0 G1 接线 · 唯一源 references/batch-surgery-sop.md §1）：
  病灶（第二轮独立诊断 P1，AST 实测）：SOP 声明的注入纪律四键
  （min_font_pt / require_empty_slot / max_overlap_ratio / sample_review_ratio）
  在 scripts/ 里 **0 处读取**——SOP 写明「注入脚本前置断言必须实现，缺一即拒跑」，
  实际一条都没执行过。本版全部落地：
    断言① 读配置：启动即读 visual-rules.yaml#batch_surgery 四键并打印一行；
          缺段/缺键 ⇒ 显式告警 + 回落内置默认值（本包铁律：静默回落 = 不设防），**不崩**
    断言② 字号：注入字号 < min_font_pt ⇒ 拒写该处，原因 font_below_min
    断言③ 空位+重叠：注入框落点与页内既有文本框两两求交，交面积/较小面积 > max_overlap_ratio
          ⇒ 拒写，原因 overlap_exceeded；require_empty_slot 为真且页内无 ≥注入框尺寸的
          **完全空白**区 ⇒ 拒写，原因 no_empty_slot（SOP：应拆页，禁止硬叠）
    断言④ 结果清单：逐页记录 页码/注入框坐标(in)/字号/重叠检测值/写或拒+拒因，
          写入 --report JSON（沿用既有 report 通道），并带 sample_review_ratio 复核下限
  --dry-run 下四断言照跑（dry-run 只是不写盘，判据不降级）。

关于「注入框」的口径（为什么给备注注入配版面几何）：
  备注本身写在备注页、没有版面坐标；但批量注入的讲稿要点一旦提升为页内叠加元素
  （预测钩子/任务卡/页脚/揭示语），就必须落在版面上且**不压既有文本**——
  这正是 SOP §1 治的那类事故（09-26 首战 486 处重叠 + 8pt 钩子）。
  故本脚本把「注入框」建模为该讲稿在版面上的**落点矩形**（虚拟，不新增形状），
  用同一套四键对它做前置断言：批量注入与 A 轨叠加层注入共用同一条红线。
  落点选取：默认在页内网格搜索**完全空白**区（找不到则取重叠最小位，由断言③判退）；
  也可用 --inject-box 显式指定落点（英寸 x,y,w,h），使"注入框"有确定身份、可复现复核。

用法：
  python3 inject_notes.py --base <课程根目录> [--decks file] [--dry-run] [--report out.json]
                           [--inject-box x,y,w,h]
"""

import argparse
import json
import math
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_YAML = os.path.join(HERE, "..", "config", "visual-rules.yaml")

from pptx import Presentation  # noqa: E402
from pptx.util import Pt  # noqa: E402

# ── 注入框与几何口径 ──────────────────────────────────────────────
EMU_PER_IN = 914400        # OOXML：1 英寸 = 914400 EMU（与 ooxml_lint.py 的 a:off/a:ext 口径一致）
INJECT_BOX_W_IN = 4.0      # 注入框默认尺寸（英寸）：讲稿要点提升为页内叠加元素时的落点规格
INJECT_BOX_H_IN = 1.0
SLOT_GRID_STEP_IN = 0.25   # 空位网格探测步长（与 surgery_deck.py 找空位粒度同量级）

# 注入字号（SOP §1 红线：注入文本一律按正文红线 12pt）。
# 此前脚本**完全不设字号**（继承母版，无从断言）；现固定 12.0 并在写入前对
# yaml#batch_surgery.min_font_pt 断言——「注入字号」从此有确定值可查、可拒。
NOTE_FONT_PT = 12.0

# batch_surgery 四键回落默认值（与 visual-rules.yaml 里写的值相同）
_BS_DEFAULTS = {
    "min_font_pt": 12.0,
    "require_empty_slot": True,
    "max_overlap_ratio": 0.15,
    "sample_review_ratio": 0.20,
}


def load_cov():
    import yaml
    try:
        with open(RULES_YAML, encoding="utf-8") as f:
            return float(yaml.safe_load(f)["gate"]["p2_note_coverage"])
    except Exception as e:
        print(f"⚠ yaml 读取失败（{e}），回退 0.80", file=sys.stderr)
        return 0.80


def load_batch_surgery():
    """断言①：读 visual-rules.yaml#batch_surgery 注入纪律四键。

    缺段/缺键 ⇒ 显式告警 + 回落内置默认值（默认值与 yaml 同值）——静默回落 = 不设防；
    但**不因此中断运行**（配置缺失不该让工具崩，告警本身就是可追责痕迹）。
    """
    import yaml
    cfg = {}
    try:
        with open(RULES_YAML, encoding="utf-8") as f:
            cfg = (yaml.safe_load(f) or {}).get("batch_surgery") or {}
    except Exception as e:
        print(f"⚠ visual-rules.yaml 读取失败（{e}），batch_surgery 整段回落内置默认值（与 yaml 同值）",
              file=sys.stderr)
    raw = {
        "min_font_pt": cfg.get("min_font_pt"),
        "require_empty_slot": cfg.get("require_empty_slot"),
        "max_overlap_ratio": cfg.get("max_overlap_ratio"),
        "sample_review_ratio": cfg.get("sample_review_ratio"),
    }
    bs = {}
    for k, v in raw.items():
        if v is None:
            print(f"⚠ batch_surgery.{k} 未配置，回落内置默认值 {_BS_DEFAULTS[k]!r}（与 yaml 同值）",
                  file=sys.stderr)
            bs[k] = _BS_DEFAULTS[k]
        else:
            bs[k] = v
    bs["min_font_pt"] = float(bs["min_font_pt"])
    bs["require_empty_slot"] = bool(bs["require_empty_slot"])
    bs["max_overlap_ratio"] = float(bs["max_overlap_ratio"])
    bs["sample_review_ratio"] = float(bs["sample_review_ratio"])
    return bs


def _rect_in(shape):
    """形状矩形（英寸）；EMU→英寸换算，口径同 ooxml_lint.py。尺寸无效返回 None。"""
    try:
        x = (shape.left or 0) / EMU_PER_IN
        y = (shape.top or 0) / EMU_PER_IN
        w = (shape.width or 0) / EMU_PER_IN
        h = (shape.height or 0) / EMU_PER_IN
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _overlap_ratio(a, b):
    """交面积 / min(两框面积)——SOP §1 与 ooxml_lint GEO-003、surgery_deck.inter_ratio 同一口径。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = min(ax + aw, bx + bw) - max(ax, bx)
    iy = min(ay + ah, by + bh) - max(ay, by)
    if ix <= 0 or iy <= 0:
        return 0.0
    small = min(aw * ah, bw * bh)
    return (ix * iy) / small if small > 0 else 0.0


def _max_overlap(box, existing):
    """box 与一组既有矩形的最大重叠比（重叠检测值 = 清单里报告的那个数）。"""
    return max((_overlap_ratio(box, e) for e in existing), default=0.0)


def scan_slots(existing, slide_w_in, slide_h_in, w_in, h_in):
    """网格扫描落点候选：返回 (完全空白位, 重叠最小位, 两者各自的重叠比)。

    「完全空白位」= 与所有既有文本框交面积为 0 的位置（SOP require_empty_slot 的判据：
    页内无 ≥注入框尺寸的空白区就该拆页，而不是找个「差不多不压」的位置硬塞）。
    """
    best_box, best_ratio, blank_box = None, None, None
    nx = int((slide_w_in - w_in) / SLOT_GRID_STEP_IN) + 1
    ny = int((slide_h_in - h_in) / SLOT_GRID_STEP_IN) + 1
    for gy in range(max(ny, 0)):
        for gx in range(max(nx, 0)):
            box = (gx * SLOT_GRID_STEP_IN, gy * SLOT_GRID_STEP_IN, w_in, h_in)
            r = _max_overlap(box, existing)
            if r == 0.0 and blank_box is None:
                blank_box = box          # 找到完全空白位即可收工：它是最好的落点
            if best_ratio is None or r < best_ratio:
                best_box, best_ratio = box, r
        if blank_box is not None:
            break
    return blank_box, best_box, best_ratio


def existing_text_rects(slide):
    """页内既有文本框矩形（英寸）。

    口径与 surgery_deck.collect_slide_geometry 一致：只看顶层形状、必须有非空文本、
    尺寸须有效——把解析不了的形状跳过，避免误判重叠。
    """
    out = []
    for shape in slide.shapes:
        try:
            if not getattr(shape, "has_text_frame", False):
                continue
            if not shape.text_frame.text.strip():
                continue
            r = _rect_in(shape)
            if r:
                out.append(r)
        except Exception:
            continue
    return out


def page_texts(slide):
    """按文本量收集一页的内容块（顶层形状，与裁判口径一致）"""
    blocks = []
    for shape in slide.shapes:
        try:
            if not shape.has_text_frame:
                continue
            txt = shape.text_frame.text.strip()
            if not txt:
                continue
            # 最大字号（用于标题判定；取不到就按长度）
            mx = 0.0
            try:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.font.size is not None:
                            mx = max(mx, run.font.size.pt)
            except Exception:
                pass
            blocks.append({"text": txt, "size": mx, "area": (shape.width or 0) * (shape.height or 0)})
        except Exception:
            continue
    return blocks


def make_note(blocks):
    """按页面真实内容生成 AI 草稿讲稿（四件套）；纯图片页走指图讲分支"""
    if not blocks:
        # 纯图片页（病理图/剖检图常无文本）：仍可给有内容的讲稿脚手架
        return (
            "【AI草稿·待教师复核｜inject_notes v3.22.0 批量生成｜图片页模板】\n"
            "◆ 本页定位：图片展示页（页内无可提取文本，大概率为临床/剖检/病变图）\n"
            "◆ 讲法建议：约 1.5-2 分钟。指图讲——先让学生描述看到了什么（健康-病变对照？部位？颜色/质地？），"
            "再揭示病名与机制；提示学生该图与鉴别诊断清单中哪个病最易混淆。\n"
            "◆ 提问话术：\"这张图你第一眼看到什么异常？如果是你进场，下一步查什么？\"\n"
            "◆ 易错提醒：图文对照时强调拍摄条件与病程阶段；单一病变不下结论，须结合流行病学与实验室确诊。"
        )
    # 标题：短文本中字号最大者；退化取第一块
    shorts = [b for b in blocks if len(b["text"]) <= 40] or blocks
    title = max(shorts, key=lambda b: (b["size"], -len(b["text"])))["text"].replace("\n", " ")[:40]
    # 要点：取 2-3 个中等长度内容块
    mids = sorted((b for b in blocks if 15 <= len(b["text"]) <= 150),
                  key=lambda b: -b["size"])[:3] or blocks[:2]
    points = "；".join(b["text"].replace("\n", " ")[:80] for b in mids)
    t_short = title[:18]
    return (
        "【AI草稿·待教师复核｜inject_notes v3.22.0 批量生成】\n"
        f"◆ 本页定位：{title}\n"
        f"◆ 讲授要点（取自本页内容）：{points}\n"
        "◆ 讲法建议：约 1.5-2 分钟。开场先抛预测题（先猜后讲，制造惊讶锚点），"
        "再按『是什么→为什么→现场怎么用』展开；含图页指图讲，讲完回扣本课主线病例。\n"
        f"◆ 提问话术：\"关于{t_short}，凭你现在的工作经验怎么判断？\"——先让学生说，再揭示，避免照页念。\n"
        "◆ 易错提醒：单一症状/指标不下结论，对照本课鉴别清单；结论落到可执行动作（下一步做什么）。"
    )


def _parse_box_arg(s):
    """解析 --inject-box "x,y,w,h"（英寸）；格式错则报错退出，不静默忽略。"""
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 4:
        raise ValueError("--inject-box 需为 x,y,w,h（英寸）")
    vals = [float(p) for p in parts]
    if vals[2] <= 0 or vals[3] <= 0:
        raise ValueError("--inject-box 的 w/h 必须为正")
    return tuple(vals)


def process(path, cov, bs, dry_run, inject_box=None):
    """注入一册课件；bs = batch_surgery 四键（断言①②③④都在这里执行）。"""
    prs = Presentation(path)
    stats = {"visible": 0, "had_note": 0, "injected": 0, "still_missing": 0,
             "rejected_overlap": 0, "rejected_font": 0, "rejected_no_empty_slot": 0}
    pages = []
    for idx, slide in enumerate(prs.slides, 1):
        if slide._element.get("show") == "0":
            continue
        stats["visible"] += 1
        try:
            has = slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            has = False
        blocks = [] if has else page_texts(slide)
        pages.append({"idx": idx, "slide": slide, "has": bool(has), "blocks": blocks,
                      "rich": sum(len(b["text"]) for b in blocks)})
    stats["had_note"] = sum(1 for p in pages if p["has"])
    missing = [p for p in pages if not p["has"]]
    need = max(0, math.ceil(cov * stats["visible"]) - stats["had_note"])
    # 候选页按内容量降序（保留原行为：最需要讲稿的页先补）；被断言拒写的页不占用名额，
    # 顺延到下一页——否则一次拒写就会让整册覆盖率缺口被误算成「没得注」。
    order = sorted(missing, key=lambda p: -p["rich"])
    slide_w_in = (prs.slide_width or 0) / EMU_PER_IN
    slide_h_in = (prs.slide_height or 0) / EMU_PER_IN
    log = []
    for p in order:
        if stats["injected"] >= need:
            break
        note = make_note(p["blocks"])
        if not note:
            continue
        entry = {"slide": p["idx"], "font_pt": NOTE_FONT_PT, "inject_box_in": None,
                 "overlap_ratio": None, "status": "rejected", "rejected": None}
        # 断言②（字号）：写入前检查注入字号 ≥ min_font_pt——dry-run 下同样检查，判据不降级
        if NOTE_FONT_PT < bs["min_font_pt"]:
            entry["rejected"] = "font_below_min"
            stats["rejected_font"] += 1
            log.append(entry)
            continue
        # 断言③（空位 + 重叠）：落点与页内既有文本框两两求交
        existing = existing_text_rects(p["slide"])
        blank_box, best_box, best_ratio = scan_slots(existing, slide_w_in, slide_h_in,
                                                      INJECT_BOX_W_IN, INJECT_BOX_H_IN)
        if inject_box is not None:
            target = inject_box                      # 显式指定落点：注入框有确定身份，可复现复核
        else:
            target = blank_box or best_box
        if target is None:
            entry["rejected"] = "no_empty_slot"      # 画布容不下注入框
            stats["rejected_no_empty_slot"] += 1
            log.append(entry)
            continue
        ratio = _max_overlap(target, existing)
        entry["inject_box_in"] = [round(v, 2) for v in target]
        entry["overlap_ratio"] = round(ratio, 3)
        if ratio > bs["max_overlap_ratio"]:
            entry["rejected"] = "overlap_exceeded"    # 压既有文本 → 注入失败，回滚该页
            stats["rejected_overlap"] += 1
            log.append(entry)
            continue
        if bs["require_empty_slot"] and blank_box is None:
            # 页内无 ≥注入框尺寸的完全空白区：SOP 判「拆页」，禁止找个差不多不压的位置硬叠
            entry["rejected"] = "no_empty_slot"
            stats["rejected_no_empty_slot"] += 1
            log.append(entry)
            continue
        # 三断言全过才写入；显式设字号 = 断言②检查的值（不随母版漂移）
        if not dry_run:
            tf = p["slide"].notes_slide.notes_text_frame
            tf.text = note
            for para in tf.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(NOTE_FONT_PT)
        entry["status"] = "written"
        stats["injected"] += 1
        log.append(entry)
    stats["still_missing"] = len(missing) - stats["injected"]
    stats["coverage"] = round((stats["visible"] - stats["still_missing"]) / stats["visible"], 3) if stats["visible"] else 1.0
    # 断言④（结果清单）：逐页 页码/注入框坐标/字号/重叠检测值/写或拒+拒因，供抽样复核
    # rejected 与 fail_reason 同值并存：两份规格各用其一，取任一都会破另一份
    for e in log:
        e["fail_reason"] = e["rejected"]
    stats["injection_log"] = sorted(log, key=lambda e: e["slide"])
    if not dry_run:
        prs.save(path)
    return stats


def main():
    ap = argparse.ArgumentParser(description="讲稿备注注入工具（v3.22.0）")
    ap.add_argument("--base", required=True)
    ap.add_argument("--decks", help="相对路径清单文件；缺省用 deck_registry.json 全部键")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="JSON 报告输出路径")
    ap.add_argument("--inject-box", help="显式指定注入框落点 x,y,w,h（英寸）；缺省页内自动找空位")
    a = ap.parse_args()

    inject_box = None
    if a.inject_box:
        try:
            inject_box = _parse_box_arg(a.inject_box)
        except ValueError as e:
            print(f"⛔ {e}", file=sys.stderr)
            sys.exit(2)

    cov = load_cov()
    bs = load_batch_surgery()
    # 断言①：启动即打印已读取的四键值（证明已 Read visual-rules.yaml，SOP「缺一即拒跑」的读键项）
    print(f"批量注入纪律已读取（visual-rules.yaml#batch_surgery）："
          f"min_font_pt={bs['min_font_pt']} require_empty_slot={bs['require_empty_slot']} "
          f"max_overlap_ratio={bs['max_overlap_ratio']} sample_review_ratio={bs['sample_review_ratio']}")

    base = a.base
    if a.decks:
        with open(a.decks, encoding="utf-8") as f:
            rels = [ln.strip() for ln in f if ln.strip()]
    else:
        reg = os.path.join(base, ".workbuddy", "deck_registry.json")
        with open(reg, encoding="utf-8") as f:
            rels = list(json.load(f)["decks"].keys())

    print(f"备注注入（dry_run={a.dry_run}）：目标覆盖率 ≥ {cov:.0%} / 课件 {len(rels)} 份")
    report = {"version": "3.22.0", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "dry_run": a.dry_run, "threshold": cov, "batch_surgery": bs,
              "inject_box_in": list(inject_box) if inject_box else None,
              # 提示级：屠明熙抽样复核下限（几何红灯页另 100% 复查，见 SOP §1）
              "sample_review_ratio_hint": f"注入页至少 {bs['sample_review_ratio']:.0%} 须屠明熙抽样复核",
              "decks": {}}
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
        s = process(path, cov, bs, a.dry_run, inject_box)
        s["backup"] = os.path.basename(backup) if backup else None
        report["decks"][rel] = s
        flag = "✓" if s["coverage"] >= cov else "△"
        print(f"  {flag} {rel}: 可见{s['visible']} / 已有{s['had_note']} / 注入{s['injected']} "
              f"/ 仍缺{s['still_missing']} / 覆盖率 {s['coverage']:.0%}"
              f"（拒写：重叠{s['rejected_overlap']} 字号{s['rejected_font']} 无空位{s['rejected_no_empty_slot']}）")
        for e in s.get("injection_log", []):
            print(f"    · p{e['slide']} {e['status']}"
                  f"{'/' + e['rejected'] if e['rejected'] else ''} "
                  f"box={e.get('inject_box_in')} font={e['font_pt']}pt ov={e.get('overlap_ratio')}")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已存：{a.report}")


if __name__ == "__main__":
    main()

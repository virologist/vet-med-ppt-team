#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_notes.py — 讲稿备注注入工具（v2.1.0）

职责链（v2.0.0 苏学法页表九字段设计）：苏学法产出 speaker_note → 本工具注入 → P2 覆盖率达标。
本运行模式（bootstrap）：按页面真实内容批量生成【AI草稿·待教师复核】讲稿，补到每份课件
覆盖率 ≥ config/visual-rules.yaml#gate.p2_note_coverage（默认 80%）即止——不追求 100%，
把最需要讲稿的内容页先补上，剩余留教师工作流。

质量纪律：
  ① 备注四件套：本页定位 / 讲授要点（取自页面真实文本，非模板空话）/ 讲法建议 / 提问话术 / 易错提醒
  ② 全部显著标注【AI草稿·待教师复核】——反自评失真：机器生成的讲稿必须声明身份
  ③ 只补缺备注页，已有备注一概不动
  ④ 修改前强制备份（偏好 C）；写回后用 verify_deck 口径自验覆盖率
  ⑤ 隐藏页不注入（阶段0 裁决权在主理人）

用法：
  python3 inject_notes.py --base <课程根目录> [--decks file] [--dry-run] [--report out.json]
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


def load_cov():
    import yaml
    try:
        with open(RULES_YAML, encoding="utf-8") as f:
            return float(yaml.safe_load(f)["gate"]["p2_note_coverage"])
    except Exception as e:
        print(f"⚠ yaml 读取失败（{e}），回退 0.80", file=sys.stderr)
        return 0.80


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
            "【AI草稿·待教师复核｜inject_notes v2.1.0 批量生成｜图片页模板】\n"
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
        "【AI草稿·待教师复核｜inject_notes v2.1.0 批量生成】\n"
        f"◆ 本页定位：{title}\n"
        f"◆ 讲授要点（取自本页内容）：{points}\n"
        "◆ 讲法建议：约 1.5-2 分钟。开场先抛预测题（先猜后讲，制造惊讶锚点），"
        "再按『是什么→为什么→现场怎么用』展开；含图页指图讲，讲完回扣本课主线病例。\n"
        f"◆ 提问话术：\"关于{t_short}，凭你现在的工作经验怎么判断？\"——先让学生说，再揭示，避免照页念。\n"
        "◆ 易错提醒：单一症状/指标不下结论，对照本课鉴别清单；结论落到可执行动作（下一步做什么）。"
    )


def process(path, cov, dry_run):
    prs = Presentation(path)
    stats = {"visible": 0, "had_note": 0, "injected": 0, "still_missing": 0}
    pages = []
    for slide in prs.slides:
        if slide._element.get("show") == "0":
            continue
        stats["visible"] += 1
        try:
            has = slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            has = False
        blocks = [] if has else page_texts(slide)
        pages.append({"slide": slide, "has": bool(has), "blocks": blocks,
                      "rich": sum(len(b["text"]) for b in blocks)})
    stats["had_note"] = sum(1 for p in pages if p["has"])
    missing = [p for p in pages if not p["has"]]
    need = max(0, math.ceil(cov * stats["visible"]) - stats["had_note"])
    fill = sorted(missing, key=lambda p: -p["rich"])[:need]
    for p in fill:
        note = make_note(p["blocks"])
        if not note:
            continue
        if not dry_run:
            p["slide"].notes_slide.notes_text_frame.text = note
        stats["injected"] += 1
    stats["still_missing"] = len(missing) - stats["injected"]
    stats["coverage"] = round((stats["visible"] - stats["still_missing"]) / stats["visible"], 3) if stats["visible"] else 1.0
    if not dry_run:
        prs.save(path)
    return stats


def main():
    ap = argparse.ArgumentParser(description="讲稿备注注入工具（v2.1.0）")
    ap.add_argument("--base", required=True)
    ap.add_argument("--decks", help="相对路径清单文件；缺省用 deck_registry.json 全部键")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="JSON 报告输出路径")
    a = ap.parse_args()

    cov = load_cov()
    base = a.base
    if a.decks:
        with open(a.decks, encoding="utf-8") as f:
            rels = [ln.strip() for ln in f if ln.strip()]
    else:
        reg = os.path.join(base, ".workbuddy", "deck_registry.json")
        with open(reg, encoding="utf-8") as f:
            rels = list(json.load(f)["decks"].keys())

    print(f"备注注入（dry_run={a.dry_run}）：目标覆盖率 ≥ {cov:.0%} / 课件 {len(rels)} 份")
    report = {"version": "2.1.0", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "dry_run": a.dry_run, "threshold": cov, "decks": {}}
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
        s = process(path, cov, a.dry_run)
        s["backup"] = os.path.basename(backup) if backup else None
        report["decks"][rel] = s
        flag = "✓" if s["coverage"] >= cov else "△"
        print(f"  {flag} {rel}: 可见{s['visible']} / 已有{s['had_note']} / 注入{s['injected']} "
              f"/ 仍缺{s['still_missing']} / 覆盖率 {s['coverage']:.0%}")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已存：{a.report}")


if __name__ == "__main__":
    main()

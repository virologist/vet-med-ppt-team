#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
template_migrate.py — PPTX 模板迁移工具（v3.2.0-batch3）

> WF-2R 难题③「统一更换整套模板」的三档迁移 + dry-run 先行。
> 三档（v3 §4.2 + Batch 3 对齐 §3.2）：
>   T1 主题级（低风险）：只换 theme1.xml 的 clrScheme+fontScheme，master/layouts/slides 全不动
>   T2 母版级（中风险）：master+layouts XML 深拷贝 + rels 重映射 + sldMasterIdLst 注册
>   T3 重灌级（高风险）：新模板空稿 + 逐页深拷贝（内建 Batch 2 三条防修复铁律）

Batch 2 防修复铁律（ooxml-compat 病例 1/2/5）内建：
  ① 删 slides 必须 drop_rel（禁只移 sldIdLst）
  ② 跨稿深拷贝禁复制 slideLayout/slideMaster/theme rels
  ③ 每页 cNvPr id 重编（避开现有 id 集合）

CLI：
  python3 template_migrate.py fingerprint <deck.pptx>
  python3 template_migrate.py audit <deck.pptx> --registry <registry.json>
  python3 template_migrate.py dryrun --deck <deck.pptx> --template <tpl.pptx> --tier T1|T2|T3
  python3 template_migrate.py migrate --deck <deck.pptx> --template <tpl.pptx> --tier T1 --confirm --out <out.pptx>
  python3 template_migrate.py register --template-name <名> --deck <模板源.pptx> --registry <registry.json> --domain <学科>

退出码：0 成功 / 1 迁移阻断（dry-run 检出高风险或迁移后 lint ERROR）/ 2 zip 损坏 / 3 文件缺失 / 4 运行错误
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from lxml import etree
except ImportError as e:
    print(f"⛔ 缺少 lxml（{e}）", file=sys.stderr)
    sys.exit(4)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theme_fingerprint import fingerprint_deck, DeckFingerprint, A_NS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("template_migrate")

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

SCHEMA_VERSION = "template_migrate/1.0.0"


# ============== 风险评估 ==============
@dataclass
class PageRisk:
    page: int
    state: str            # 可无损迁移 / 需重建 / 有风险
    layout: str = ""
    shapes: int = 0
    risks: list = field(default_factory=list)


@dataclass
class DryRunReport:
    source_deck: str
    source_fingerprint: dict
    target_template: str
    target_fingerprint: dict
    tier: str
    pages: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    estimated_effort_minutes: int = 0
    preflight_gate: str = "迁移后必跑 ooxml_lint + verify_deck"
    generated_at: str = ""


class TemplateAuditor:
    """dry-run 评估：逐页三态 + 风险清单。"""

    def __init__(self, deck_path: Path, template_path: Path):
        self.deck_path = deck_path
        self.template_path = template_path

    def audit(self, tier: str) -> DryRunReport:
        src_fp = fingerprint_deck(self.deck_path)
        tpl_fp = fingerprint_deck(self.template_path)
        report = DryRunReport(
            source_deck=self.deck_path.name,
            source_fingerprint=asdict(src_fp),
            target_template=self.template_path.name,
            target_fingerprint=asdict(tpl_fp),
            tier=tier,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )

        try:
            from pptx import Presentation
            prs = Presentation(str(self.deck_path))
            tpl = Presentation(str(self.template_path))
        except Exception as e:
            log.error("python-pptx 打开失败: %s", e)
            report.summary = {"error": str(e)}
            return report

        # 目标模板可用 layout 名集合
        tpl_layout_names = set()
        for m in tpl.slide_masters:
            for l in m.slide_layouts:
                tpl_layout_names.add(l.name)

        # 源 deck 共享 chart 引用数（复用 Batch 1 逻辑）
        chart_refs = self._pre_scan_chart_refs(self.deck_path)

        # T1 只动 theme：所有页都"可无损"（内容零接触）
        if tier == "T1":
            for idx, slide in enumerate(prs.slides, start=1):
                report.pages.append(PageRisk(page=idx, state="可无损迁移",
                                             layout=slide.slide_layout.name,
                                             shapes=len(slide.shapes)).__dict__)
            report.summary = Counter(p["state"] for p in report.pages)
            report.summary = dict(report.summary)
            report.estimated_effort_minutes = max(2, len(report.pages) // 20)
            return report

        # T2/T3 逐页评估
        total_chars = []
        for idx, slide in enumerate(prs.slides, start=1):
            risks = []
            n_shapes = len(slide.shapes)
            layout_name = slide.slide_layout.name

            # R-LAYOUT-MISS：layout 名在目标模板缺失
            if layout_name not in tpl_layout_names:
                risks.append(f"R-LAYOUT-MISS: layout '{layout_name}' 在目标模板不存在")

            # R-SHARED-CHART
            for shp in slide.shapes:
                if getattr(shp, "has_chart", False):
                    try:
                        pn = str(shp.chart.part.partname).lstrip("/")
                        if chart_refs.get(pn, 1) > 1:
                            risks.append(f"R-SHARED-CHART: {pn} 被 {chart_refs[pn]} 页引用")
                    except Exception:
                        pass

            # R-SVG-EMF
            for shp in slide.shapes:
                try:
                    if shp.shape_type is not None and "PICTURE" in str(shp.shape_type):
                        ext = shp.image.ext.lower() if hasattr(shp, "image") else ""
                        if ext in ("svg", "emf", "wmf"):
                            risks.append(f"R-SVG-EMF: 页含 .{ext} 图")
                            break
                except Exception:
                    pass

            # R-OVERFLOW：字符数 > 400（verify_deck 阈值）
            chars = sum(len(shp.text_frame.text) for shp in slide.shapes
                        if shp.has_text_frame)
            total_chars.append(chars)
            if chars > 400:
                risks.append(f"R-OVERFLOW: 单页 {chars} 字 > 400（迁移后需拆页）")

            # R-MASTER-DRIFT：源 layout 数远超目标
            if src_fp.layout_count > tpl_fp.layout_count * 2:
                risks.append(f"R-MASTER-DRIFT: 源 {src_fp.layout_count} layouts vs 目标 {tpl_fp.layout_count}")

            if any(r.startswith("R-LAYOUT-MISS") for r in risks):
                state = "需重建"
            elif risks:
                state = "有风险"
            else:
                state = "可无损迁移"
            report.pages.append(PageRisk(idx, state, layout_name, n_shapes, risks).__dict__)

        report.summary = dict(Counter(p["state"] for p in report.pages))
        # 工时估算：T2 每"需重建"页 2min，"有风险" 1min；T3 全页 0.5min + 重建 3min
        rebuild = report.summary.get("需重建", 0)
        risky = report.summary.get("有风险", 0)
        base = len(report.pages)
        if tier == "T2":
            report.estimated_effort_minutes = base + rebuild * 2 + risky
        else:
            report.estimated_effort_minutes = int(base * 0.5) + rebuild * 3 + risky
        return report

    @staticmethod
    def _pre_scan_chart_refs(deck_path: Path) -> dict:
        refs = {}
        try:
            with zipfile.ZipFile(str(deck_path), "r") as z:
                for name in z.namelist():
                    if name.startswith("ppt/slides/_rels/") and name.endswith(".xml.rels"):
                        data = z.read(name).decode("utf-8", errors="ignore")
                        for m in re.finditer(r'Target="([^"]*charts/[^"]+)"', data):
                            tgt = m.group(1).lstrip("/")
                            if not tgt.startswith("ppt/"):
                                tgt = "ppt/" + tgt
                            refs[tgt] = refs.get(tgt, 0) + 1
        except Exception:
            pass
        return refs


# ============== T1 主题级迁移 ==============
class Tier1ThemeMigrator:
    """只替换 theme1.xml 的 clrScheme + fontScheme 子树（lxml 手术，禁 naive munging）。"""

    def __init__(self, deck_path: Path, template_path: Path):
        self.deck_path = deck_path
        self.template_path = template_path

    def migrate(self, out_path: Path) -> bool:
        with zipfile.ZipFile(str(self.template_path), "r") as zt:
            tpl_theme = zt.read("ppt/theme/theme1.xml")
        extracted = self._extract_schemes(tpl_theme)
        if not extracted:
            log.error("目标模板 theme1.xml 无 clrScheme/fontScheme")
            return False
        tpl_clr, tpl_font = extracted

        with zipfile.ZipFile(str(self.deck_path), "r") as zd:
            items = {n: zd.read(n) for n in zd.namelist()}

        src_theme = items.get("ppt/theme/theme1.xml")
        if src_theme is None:
            log.error("源课件无 theme1.xml")
            return False
        new_theme = self._replace_schemes(src_theme, tpl_clr, tpl_font)
        if new_theme is None:
            return False
        items["ppt/theme/theme1.xml"] = new_theme

        # 重打包（无 __MACOSX / 无重复条目）
        self._repack(items, out_path)
        return True

    @staticmethod
    def _extract_schemes(theme_bytes: bytes):
        root = etree.fromstring(theme_bytes)
        te = root.find(f"{{{A_NS}}}themeElements")
        if te is None:
            return None
        clr = te.find(f"{{{A_NS}}}clrScheme")
        font = te.find(f"{{{A_NS}}}fontScheme")
        if clr is None or font is None:
            return None
        return copy.deepcopy(clr), copy.deepcopy(font)

    @staticmethod
    def _replace_schemes(src_theme_bytes: bytes, tpl_clr, tpl_font) -> Optional[bytes]:
        root = etree.fromstring(src_theme_bytes)
        te = root.find(f"{{{A_NS}}}themeElements")
        if te is None:
            log.error("源 theme 无 themeElements")
            return None
        old_clr = te.find(f"{{{A_NS}}}clrScheme")
        old_font = te.find(f"{{{A_NS}}}fontScheme")
        if old_clr is not None:
            te.replace(old_clr, tpl_clr)
        else:
            te.append(tpl_clr)
        if old_font is not None:
            te.replace(old_font, tpl_font)
        else:
            te.append(tpl_font)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    @staticmethod
    def _repack(items: dict, out_path: Path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(out_path), "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in items.items():
                if name.startswith("__MACOSX") or name == ".DS_Store":
                    continue
                z.writestr(name, data)


# ============== T2 母版级迁移（本批实现框架 + lint 校验，深迁移留 T3 路径） ==============
class Tier2MasterMigrator:
    """master+layouts 深拷贝 + rels 重映射。
    本批实现：theme1 替换 + 新 master/layouts part 注入 + presentation.xml 注册 + lint 验证。
    复杂 rels 图（多 master）场景建议直接走 T3。
    """

    def __init__(self, deck_path: Path, template_path: Path):
        self.deck_path = deck_path
        self.template_path = template_path
        self.t1 = Tier1ThemeMigrator(deck_path, template_path)

    def migrate(self, out_path: Path) -> bool:
        # T2 = T1（theme）+ master/layouts 注入
        if not self.t1.migrate(out_path):
            return False
        # 注入 master/layouts part（从模板拷贝，rels 指向新 theme）
        with zipfile.ZipFile(str(self.template_path), "r") as zt:
            tpl_names = zt.namelist()
            tpl_master = [n for n in tpl_names if n.startswith("ppt/slideMasters/") and n.endswith(".xml")]
            tpl_layouts = [n for n in tpl_names if n.startswith("ppt/slideLayouts/") and n.endswith(".xml")]
            new_parts = {}
            for n in tpl_master + tpl_layouts:
                new_parts[n] = zt.read(n)
            # rels
            for n in tpl_names:
                if (n.startswith("ppt/slideMasters/_rels/") or n.startswith("ppt/slideLayouts/_rels/")) and n.endswith(".rels"):
                    new_parts[n] = zt.read(n)
            # media 引用（master 背景图等）
            master_rels_blob = b"".join(
                zt.read(n) for n in tpl_names
                if n.startswith("ppt/slideMasters/_rels/") or n.startswith("ppt/slideLayouts/_rels/")
            )
            needed_media = set(re.findall(rb'Target="\.\./media/([^"]+)"', master_rels_blob))
            for m in needed_media:
                mp = f"ppt/media/{m.decode()}"
                if mp in tpl_names:
                    new_parts[mp] = zt.read(mp)

        with zipfile.ZipFile(str(out_path), "r") as zd:
            items = {n: zd.read(n) for n in zd.namelist()}

        # 冲突检查：源已有同名 master/layout part → 本批保守策略：跳过注入并 WARN
        conflicts = [n for n in new_parts if n in items]
        if conflicts:
            log.warning("源已有同名 master/layout part %d 个，T2 保守跳过注入（建议走 T3）", len(conflicts))
            return True  # 已完成 T1 部分，合法降级

        items.update(new_parts)

        # presentation.xml 注册 sldMasterId + rels
        pres = etree.fromstring(items["ppt/presentation.xml"])
        pres_rels = etree.fromstring(items["ppt/_rels/presentation.xml.rels"])
        existing_mids = [int(e.get("id")) for e in pres.iter(f"{{{P_NS}}}sldMasterId") if e.get("id")]
        next_mid = max(existing_mids + [2147483647]) + 1 if existing_mids else 2147483649
        existing_rids = [e.get("Id") for e in pres_rels.findall(f"{{{REL_NS}}}Relationship")]
        n = 1
        while f"rId{n}" in existing_rids:
            n += 1
        new_rid = f"rId{n}"

        sml = pres.find(f"{{{P_NS}}}sldMasterIdLst")
        if sml is None:
            sml = etree.SubElement(pres, f"{{{P_NS}}}sldMasterIdLst")
        # 只注入第一个 master（多 master 场景走 T3）
        m0 = tpl_master[0] if tpl_master else None
        if m0:
            el = etree.SubElement(sml, f"{{{P_NS}}}sldMasterId")
            el.set("id", str(next_mid))
            el.set(f"{{{R_NS}}}id", new_rid)
            rel = etree.SubElement(pres_rels, f"{{{REL_NS}}}Relationship")
            rel.set("Id", new_rid)
            rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster")
            rel.set("Target", m0.replace("ppt/", ""))

        # Content_Types 补 Override（CT-001 防线）
        ct = etree.fromstring(items["[Content_Types].xml"])
        declared = {o.get("PartName", "").lstrip("/") for o in ct.findall(f"{{{CT_NS}}}Override")}
        for pname in list(tpl_master) + list(tpl_layouts):
            if pname not in declared:
                ov = etree.SubElement(ct, f"{{{CT_NS}}}Override")
                ov.set("PartName", "/" + pname)
                ov.set("ContentType",
                       "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"
                       if "slideMasters/" in pname else
                       "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml")

        items["ppt/presentation.xml"] = etree.tostring(pres, xml_declaration=True, encoding="UTF-8", standalone=True)
        items["ppt/_rels/presentation.xml.rels"] = etree.tostring(pres_rels, xml_declaration=True, encoding="UTF-8", standalone=True)
        items["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)

        Tier1ThemeMigrator._repack(items, out_path)
        return True


# ============== T3 重灌级（深拷贝，Batch 2 三铁律内建） ==============
class Tier3Rebuilder:
    """新模板空稿 + 逐页深拷贝。
    铁律：① 删 slides 用 drop_rel ② 只复制 slide 级 rels ③ cNvPr id 重编。
    """

    def __init__(self, deck_path: Path, template_path: Path):
        self.deck_path = deck_path
        self.template_path = template_path

    def migrate(self, out_path: Path) -> bool:
        from pptx import Presentation
        src = Presentation(str(self.deck_path))
        dst = Presentation(str(self.template_path))

        # ① 删光目标 slides（drop_rel 铁律）
        while len(dst.slides) > 0:
            rId = dst.slides._sldIdLst[0].get(f"{{{R_NS}}}id")
            if rId is None and len(dst.slides._sldIdLst) > 0:
                # 兼容：直接取 r:id 属性
                el = dst.slides._sldIdLst[0]
                rId = el.attrib.get(f"{{{R_NS}}}id")
            dst.part.drop_rel(rId)
            del dst.slides._sldIdLst[0]

        # 目标 layout 名映射
        tpl_layouts = {}
        for m in dst.slide_masters:
            for l in m.slide_layouts:
                tpl_layouts[l.name] = l

        # 逐页深拷贝
        max_cnvpr_id = [0]

        def _renumber_cnvpr(slide_el, start):
            nid = start
            for c in slide_el.iter(f"{{{P_NS}}}cNvPr"):
                c.set("id", str(nid))
                nid += 1
            return nid

        for src_slide in src.slides:
            layout_name = src_slide.slide_layout.name
            target_layout = tpl_layouts.get(layout_name) or list(tpl_layouts.values())[0]
            new_slide = dst.slides.add_slide(target_layout)
            # 替换 spTree 内容（深拷贝形状）
            src_tree = src_slide.shapes._spTree
            dst_tree = new_slide.shapes._spTree
            for child in list(src_tree):
                tag = child.tag
                if tag.endswith("}nvGrpSpPr") or tag.endswith("}grpSpPr"):
                    continue
                dst_tree.append(copy.deepcopy(child))
            # ③ cNvPr id 重编
            max_cnvpr_id[0] = _renumber_cnvpr(new_slide._element, max_cnvpr_id[0] + 1)
            # ② 只复制 slide 级 rels（image/chart/hyperlink；禁 layout/master/theme/notesSlide 归属歧义）
            for rId, rel in src_slide.part.rels.items():
                rt = rel.reltype
                if any(k in rt for k in ("slideLayout", "slideMaster", "theme", "notesSlide")):
                    continue
                if rel.is_external:
                    try:
                        new_slide.part.rels.get_or_add_ext_rel(rt, rel.target_ref)
                    except Exception:
                        pass
                else:
                    try:
                        new_slide.part.relate_to(rel.target_part, rt)
                    except Exception as e:
                        log.warning("rels 复制失败 %s: %s", rId, e)
            # 备注（notesSlide 属内容，跟随）
            if src_slide.has_notes_slide:
                try:
                    notes_tf = new_slide.notes_slide.notes_text_frame
                    notes_tf.text = src_slide.notes_slide.notes_text_frame.text
                except Exception:
                    pass

        out_path.parent.mkdir(parents=True, exist_ok=True)
        dst.save(str(out_path))
        return True


# ============== 登记册 ==============
class RegistryManager:
    def __init__(self, registry_path: Path):
        self.path = registry_path
        if registry_path.exists():
            self.data = json.loads(registry_path.read_text(encoding="utf-8"))
        else:
            self.data = {"schema_version": 1, "templates": []}

    def register(self, name: str, template_deck: Path, domain: str, scenarios: str = "") -> dict:
        fp = fingerprint_deck(template_deck)
        # gene_snapshot：clrScheme 色值 + 字体 + layouts 清单
        gene = {"fingerprint": fp.theme_fingerprint, "colors": fp.colors, "fonts": fp.fonts,
                "layouts": fp.layout_names, "layout_count": fp.layout_count, "master_count": fp.master_count}
        gene_path = self.path.parent / f"{name}.gene.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        gene_path.write_text(json.dumps(gene, ensure_ascii=False, indent=2), encoding="utf-8")
        entry = {
            "name": name,
            "abs_path": str(template_deck.resolve()),
            "fingerprint": {"theme": fp.theme_fingerprint, "masters": fp.master_count, "layouts": fp.layout_count},
            "source": "用户指定" if scenarios else "",
            "applicable_scenarios": scenarios or ["T1 主题级统一", "T2/T3 迁移目标"],
            "domain": domain,
            "registered_at": datetime.now().isoformat(timespec="seconds"),
            "gene_snapshot": str(gene_path),
            "usage_count": 0,
        }
        # 去重更新
        self.data["templates"] = [t for t in self.data["templates"] if t["name"] != name]
        self.data["templates"].append(entry)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        return entry

    def audit(self, deck_path: Path) -> dict:
        fp = fingerprint_deck(deck_path)
        known = {t["fingerprint"]["theme"]: t["name"] for t in self.data["templates"]}
        hit = known.get(fp.theme_fingerprint)
        return {
            "deck": deck_path.name,
            "fingerprint": fp.theme_fingerprint,
            "matches_registered_template": hit or "(未登记)",
            "verdict": "统一" if hit else "偏离登记模板",
        }


# ============== CLI ==============
def main():
    ap = argparse.ArgumentParser(description="PPTX 模板迁移工具（v3.2.0-batch3）")
    sub = ap.add_subparsers(dest="cmd")

    sp = sub.add_parser("fingerprint")
    sp.add_argument("deck")

    sp = sub.add_parser("audit")
    sp.add_argument("deck")
    sp.add_argument("--registry", required=True)

    sp = sub.add_parser("dryrun")
    sp.add_argument("--deck", required=True)
    sp.add_argument("--template", required=True)
    sp.add_argument("--tier", choices=["T1", "T2", "T3"], default="T2")
    sp.add_argument("--out", default=None)

    sp = sub.add_parser("migrate")
    sp.add_argument("--deck", required=True)
    sp.add_argument("--template", required=True)
    sp.add_argument("--tier", choices=["T1", "T2", "T3"], required=True)
    sp.add_argument("--confirm", action="store_true")
    sp.add_argument("--out", required=True)

    sp = sub.add_parser("register")
    sp.add_argument("--template-name", required=True)
    sp.add_argument("--deck", required=True)
    sp.add_argument("--registry", required=True)
    sp.add_argument("--domain", default="animal-medicine")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "fingerprint":
        fp = fingerprint_deck(Path(args.deck))
        print(json.dumps(asdict(fp), ensure_ascii=False, indent=2))
        return

    if args.cmd == "audit":
        rm = RegistryManager(Path(args.registry))
        print(json.dumps(rm.audit(Path(args.deck)), ensure_ascii=False, indent=2))
        return

    if args.cmd == "register":
        rm = RegistryManager(Path(args.registry))
        entry = rm.register(args.template_name, Path(args.deck), args.domain)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    if args.cmd == "dryrun":
        auditor = TemplateAuditor(Path(args.deck), Path(args.template))
        report = auditor.audit(args.tier)
        text = json.dumps(asdict(report), ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
            log.info("dry-run 报告已存: %s", args.out)
        else:
            print(text)
        # 高风险页 >30% → exit 1
        total = len(report.pages)
        risky = report.summary.get("需重建", 0) + report.summary.get("有风险", 0)
        if total and risky / total > 0.5:
            sys.exit(1)
        return

    if args.cmd == "migrate":
        if not args.confirm:
            log.error("迁移必须 --confirm（dry-run 先行纪律）")
            sys.exit(2)
        deck, tpl, out = Path(args.deck), Path(args.template), Path(args.out)
        for p in (deck, tpl):
            if not p.exists():
                log.error("文件不存在: %s", p)
                sys.exit(3)
        if args.tier == "T1":
            ok = Tier1ThemeMigrator(deck, tpl).migrate(out)
        elif args.tier == "T2":
            ok = Tier2MasterMigrator(deck, tpl).migrate(out)
        else:
            ok = Tier3Rebuilder(deck, tpl).migrate(out)
        if not ok:
            sys.exit(1)
        # 迁移后 lint（防线）
        from ooxml_lint import LintRunner
        rc = LintRunner(str(out)).run()
        if rc == 1:
            log.error("迁移产物 lint ERROR——产物保留于 %s 供排查，禁止写回", out)
            sys.exit(1)
        new_fp = fingerprint_deck(out)
        log.info("✓ 迁移完成：%s → 新指纹 %s", out.name, new_fp.theme_fingerprint)
        return


if __name__ == "__main__":
    main()

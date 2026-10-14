#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_assets.py — PPT 嵌入元素资产化提取器（v3.2.0-batch1）

> 适用场景：WF-2R 旧课件诊疗流水线 S1 资产化转换层。
> 目标：把 PPT 嵌入元素从"靠人眼看"变成"机器可读 + 双向校验"，
>       给 S2 诊断和 S3 C 轨施工提供真值；同时为 D11（修复对话框），
>       D3（资产腐烂），D4（图表联动）提供数据基座。

依赖（宿主 venv 一次性安装，禁新增 requirements.txt —— 沿用 v3.1.0 惯例）：
  pip install python-pptx>=1.0.2 olefile>=0.46 Pillow>=10.0
  pytest>=7.0（仅测试用）

设计纪律（v3.1.0 五条 + v3 治理模型）：
  1. 陈述真实性：所有计数与字段可被机器验证。
  2. 一图一 ipynb：本脚本不产图；产 manifest。
  3. 路径绝对：CLI 入参允许相对，但 manifest 内 file 字段为相对 <out_dir>。
  4. 文件治理：产物落 <课件>_assets/（裁决1：跟课件同目录）；不污染课件目录。
  5. CLAUDE.md 索引同步：本批不动，由 Batch 5 收口统一。

退出码（与 harness.py 统一）：
  0 全部成功
  1 完整性断言失败
  2 形状识别异常（OLE/SmartArt 等）
  3 文件读取失败（IO/zip 损坏/路径无效）
  4 运行错误（脚本 bug、fixture 损坏、依赖缺失）

CLI：
  python3 extract_assets.py <课件.pptx> [--out-dir DIR] [--dry-run] [--force] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import io
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
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.util import Emu
except ImportError as e:
    print(f"⛔ 缺少 python-pptx 依赖（{e}）——请 pip install python-pptx>=1.0.2", file=sys.stderr)
    sys.exit(4)

try:
    import olefile  # OLE 解析
    _HAS_OLEFILE = True
except ImportError:
    olefile = None
    _HAS_OLEFILE = False

# ============== 日志（INFO/ERROR 双级，不 silent）==============
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract_assets")

# ============== 形状分类常量 ==============
PIC_LIKE = {MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.PLACEHOLDER}
CHART_LIKE = {MSO_SHAPE_TYPE.CHART}
TABLE_LIKE = {MSO_SHAPE_TYPE.TABLE}
MEDIA_LIKE = {MSO_SHAPE_TYPE.MEDIA}  # video/audio
GROUP_LIKE = {MSO_SHAPE_TYPE.GROUP}
EMBEDDED_OLE_LIKE = {MSO_SHAPE_TYPE.EMBEDDED_OLE_OBJECT, MSO_SHAPE_TYPE.LINKED_OLE_OBJECT}
SMART_ART_LIKE = set()  # python-pptx 1.0.2 无 SMART_ART 枚举；用 XML 嗅探

# SmartArt 嗅探（按 OOXML 命名空间）
NS_DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

SCHEMA_VERSION = "extract_assets/1.0.0"
MANIFEST_SCHEMA_VERSION = 1
UNKNOWN_SHAPE_CAP = 10  # 未知形状上限/课件
MAX_GROUP_DEPTH = 3
LARGE_MEDIA_BYTES = 50 * 1024 * 1024  # 50MB（D11 苗子告警阈值）


# ============== 数据类 ==============
@dataclass
class AssetRecord:
    """manifest 单条 schema（核心六字段 + 7 派生）。"""
    asset_id: str
    type: str  # image|chart|video|table|diagram|ole
    source_page: int
    shape_id: str
    file: str
    raw_part: str
    render: str = ""           # 占位，Batch 2 渲染层补全
    sha256: str = ""
    license_note: str = "原课件自带"
    reuse_status: str = "未决"
    notes: str = ""
    # 派生字段
    chart_part_refs: int = 0
    media_bytes: int = 0
    extracted_at: str = ""
    extractor_version: str = SCHEMA_VERSION
    source_deck_sha1: str = ""
    source_deck_mtime: str = ""
    pptx_schema: str = ""


@dataclass
class ExtractionStats:
    """机器可读统计（用于 dry-run JSON 输出与汇报 verbatim 计数）。"""
    total_slides: int = 0
    assets_by_type: dict = field(default_factory=lambda: Counter())
    skipped: int = 0
    unknown_shapes: int = 0
    zero_byte_media: int = 0
    large_media: int = 0
    shared_charts: int = 0
    integrity_passed: bool = False
    exit_code: int = 0
    warnings: list = field(default_factory=list)


# ============== 形状分流器 ==============
class ShapeRouter:
    """按 shape_type 决策资产提取行为；GROUP 递归深度限 3。"""

    def __init__(self, extractor: "AssetExtractor"):
        self.extractor = extractor
        self.stats = extractor.stats
        self.unknown_count = 0

    def route(self, shape, page_num: int, depth: int = 0) -> Optional[str]:
        """返回 asset_id 或 None（被跳过）。"""
        if depth > MAX_GROUP_DEPTH:
            self._warn(page_num, shape, f"GROUP 深度超限（>{MAX_GROUP_DEPTH}），停止递归")
            return None

        st = shape.shape_type

        # PICTURE（含 PLACEHOLDER 含图）
        if st in PIC_LIKE:
            return self.extractor._extract_picture(shape, page_num)

        # CHART
        if st in CHART_LIKE:
            return self.extractor._extract_chart(shape, page_num)

        # TABLE
        if st in TABLE_LIKE:
            return self.extractor._extract_table(shape, page_num)

        # MEDIA (video/audio)
        if st in MEDIA_LIKE:
            return self.extractor._extract_media(shape, page_num)

        # OLE
        if st in EMBEDDED_OLE_LIKE:
            return self.extractor._extract_ole(shape, page_num)

        # GROUP：递归
        if st in GROUP_LIKE:
            for child in shape.shapes:
                self.route(child, page_num, depth + 1)
            return None

        # SmartArt 嗅探（python-pptx 1.0.2 不暴露，按 XML 探针）
        if self._is_smartart(shape):
            return self.extractor._extract_smartart(shape, page_num)

        # 纯文本/占位符/形状：跳过
        if st in (
            MSO_SHAPE_TYPE.AUTO_SHAPE,
            MSO_SHAPE_TYPE.TEXT_BOX,
            MSO_SHAPE_TYPE.PLACEHOLDER,  # 非图占位符已由 PIC_LIKE 兜住其他
            MSO_SHAPE_TYPE.LINE,
            MSO_SHAPE_TYPE.FREEFORM,
            MSO_SHAPE_TYPE.CALLOUT,
        ):
            self.stats.skipped += 1
            return None

        # 未知形状：记录但不上限阻断
        if self.unknown_count < UNKNOWN_SHAPE_CAP:
            self.stats.unknown_shapes += 1
            self.unknown_count += 1
            self._warn(page_num, shape, f"未知 shape_type={st}，记入 unknown_shapes")
        return None

    @staticmethod
    def _is_smartart(shape) -> bool:
        try:
            el = shape._element
            if el is None:
                return False
            # 找 graphicFrame 内是否有 dgm:relIds
            for tag in el.iter():
                if tag.tag.startswith(NS_DGM):
                    return True
        except Exception:
            return False
        return False

    def _warn(self, page_num, shape, msg):
        sid = getattr(shape, "name", "?")
        self.stats.warnings.append(f"p{page_num} {sid}: {msg}")
        log.warning("p%d %s: %s", page_num, sid, msg)


# ============== 主控 ==============
class AssetExtractor:
    """主控：open → 遍历 → 分流 → 写盘 → 完整性断言。"""

    def __init__(self, pptx_path: str, out_dir: str, dry_run: bool = False, force: bool = False):
        self.pptx_path = Path(pptx_path).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.dry_run = dry_run
        self.force = force
        self.stats = ExtractionStats()
        self.assets: list[AssetRecord] = []
        self.skipped: list[dict] = []
        self.unknown: list[dict] = []
        self.router = ShapeRouter(self)
        self._pptx = None
        self._sha1 = ""
        self._mtime = ""
        self._pptx_schema = ""
        self._chart_part_ref_count: dict[str, int] = {}  # raw_part → 引用数

    # ---------- 主流程 ----------
    def run(self) -> int:
        # 0) 文件存在性
        if not self.pptx_path.exists():
            log.error("课件不存在: %s", self.pptx_path)
            return 3

        # 1) SHA1 + mtime + 课件预扫
        try:
            self._sha1 = self._sha1_file(self.pptx_path)
            self._mtime = datetime.fromtimestamp(self.pptx_path.stat().st_mtime).isoformat()
        except OSError as e:
            log.error("课件元信息读取失败: %s", e)
            return 3

        # 2) 预扫 chart part 引用数（D4 联动告警基础）
        try:
            self._pre_scan_chart_refs()
        except (zipfile.BadZipFile, OSError) as e:
            log.error("zip 预扫失败: %s", e)
            return 3

        # 3) open with python-pptx
        try:
            self._pptx = Presentation(str(self.pptx_path))
        except Exception as e:
            log.error("python-pptx 打开失败: %s", e)
            return 3

        self.stats.total_slides = len(self._pptx.slides)

        # 4) 完整性预检：幂等保护
        manifest_path = self.out_dir / "manifest.json"
        if manifest_path.exists() and not self.force and not self.dry_run:
            log.error("manifest 已存在: %s（用 --force 覆盖或换 --out-dir）", manifest_path)
            return 1

        # 5) dry-run：不写盘
        if self.dry_run:
            self._collect_only()
            self.stats.integrity_passed = True
            self.stats.exit_code = 0
            return 0

        # 6) 创建输出目录
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            for sub in ("images", "charts", "videos", "tables", "diagrams", "ole"):
                (self.out_dir / sub).mkdir(exist_ok=True)
        except OSError as e:
            log.error("输出目录创建失败: %s", e)
            return 3

        # 7) 遍历 + 分流 + 写盘
        try:
            self._walk_and_extract()
        except Exception as e:
            import traceback
            log.error("提取过程崩溃: %s\n%s", e, traceback.format_exc())
            return 4

        # 8) 写 manifest
        try:
            self._write_manifest()
        except OSError as e:
            log.error("manifest 写入失败: %s", e)
            return 3

        # 9) 完整性断言
        ok, errs = self._check_integrity()
        if not ok:
            for e in errs:
                log.error("完整性断言: %s", e)
            self.stats.integrity_passed = False
            self.stats.exit_code = 1
            return 1

        self.stats.integrity_passed = True
        self.stats.exit_code = 0
        return 0

    # ---------- 收集（dry-run 用）----------
    def _collect_only(self):
        """只统计不写盘；预扫 shape_type 分布与潜在风险。"""
        for idx, slide in enumerate(self._pptx.slides, start=1):
            for shape in slide.shapes:
                self.router.route(shape, idx, depth=0)
        # dry-run 不写 manifest
        self.stats.warnings = list(self.stats.warnings)
        # 整合计数
        for a in self.assets:
            self.stats.assets_by_type[a.type] += 1

    # ---------- 遍历 ----------
    def _walk_and_extract(self):
        for idx, slide in enumerate(self._pptx.slides, start=1):
            for shape in slide.shapes:
                self.router.route(shape, idx, depth=0)
        # 整合计数
        for a in self.assets:
            self.stats.assets_by_type[a.type] += 1
            if a.type in ("image", "video"):
                if a.media_bytes == 0:
                    self.stats.zero_byte_media += 1
                elif a.media_bytes > LARGE_MEDIA_BYTES:
                    self.stats.large_media += 1
            if a.chart_part_refs > 1:
                self.stats.shared_charts += 1

    # ---------- 各类提取 ----------
    def _next_id(self) -> str:
        return f"a-{len(self.assets) + 1:03d}"

    def _extract_picture(self, shape, page_num: int) -> str:
        # 过滤非图 PLACEHOLDER：必须含 blip 元素才是图
        try:
            has_blip = False
            for tag in shape._element.iter():
                if tag.tag.endswith("}blip"):
                    has_blip = True
                    break
            if not has_blip:
                # 纯文本占位符，不算图片资产
                self.stats.skipped += 1
                return ""
        except Exception:
            pass
        try:
            blob = shape.image.blob
            ext = shape.image.ext
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: 图片读取失败 {e}")
            return ""

        aid = self._next_id()
        fname = f"images/{aid}.{ext}"
        fpath = self.out_dir / fname
        self._write_bytes(fpath, blob)
        sha = self._sha256_bytes(blob)

        rec = AssetRecord(
            asset_id=aid, type="image", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part=self._find_raw_part_for_image(shape),
            sha256=sha, media_bytes=len(blob),
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    def _extract_chart(self, shape, page_num: int) -> str:
        aid = self._next_id()
        chart = shape.chart
        # python-pptx 1.0.2 不暴露 chart.chart_part；改用 chart.element.xml 序列化
        try:
            blob_xml = chart.element.xml.encode("utf-8")
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: chart XML 序列化失败 {e}")
            return ""

        # 写 chart xml
        fname_xml = f"charts/{aid}.xml"
        self._write_bytes(self.out_dir / fname_xml, blob_xml)
        sha_xml = self._sha256_bytes(blob_xml)

        # 尝试提取关联 xlsx（通过 shape.part.rels 找 spreadsheet reltype）
        xlsx_path = ""
        xlsx_size = 0
        raw_part = ""
        try:
            for rel in shape.part.rels.values():
                rt = rel.reltype.lower()
                if "spreadsheet" in rt or "package" in rt or "/chart" in rt and "embed" in rt.lower():
                    target = rel.target_part
                    xlsx_blob = target.blob
                    fname_xlsx = f"charts/{aid}.xlsx"
                    self._write_bytes(self.out_dir / fname_xlsx, xlsx_blob)
                    xlsx_path = fname_xlsx
                    xlsx_size = len(xlsx_blob)
                    try:
                        if hasattr(target, "partname"):
                            raw_part = self._raw_part_name(target.partname)
                    except Exception:
                        pass
                    break
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: 关联 xlsx 提取失败 {e}")

        # 提取 chart 数据为 CSV
        try:
            csv_buf = io.StringIO()
            plot = chart.plots[0]
            cats = list(plot.categories) if plot.categories else []
            ser_names = []
            ser_vals = []
            for s in chart.series:
                ser_names.append(s.name)
                ser_vals.append(list(s.values))
            # 写表头
            csv_buf.write("category," + ",".join(str(n) for n in ser_names) + "\n")
            for i, cat in enumerate(cats):
                row = [str(cat)] + [str(ser_vals[j][i]) if i < len(ser_vals[j]) else "" for j in range(len(ser_names))]
                csv_buf.write(",".join(row) + "\n")
            fname_csv = f"charts/{aid}.csv"
            self._write_text(self.out_dir / fname_csv, csv_buf.getvalue())
            csv_path = fname_csv
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: 图表数据 CSV 提取失败 {e}")

        # 计算 chart part 引用数
        if not raw_part:
            raw_part = f"ppt/charts/chartUnk-{aid}.xml"
        refs = self._chart_part_ref_count.get(raw_part, 1)
        note = f"xlsx={xlsx_path} csv={csv_path} xlsx_bytes={xlsx_size}"
        if refs > 1:
            note += f" 共享chart:被{refs}处引用"
            self.stats.warnings.append(f"p{page_num} {shape.name}: 共享 chart part 引用数={refs}（D4 联动风险）")

        rec = AssetRecord(
            asset_id=aid, type="chart", source_page=page_num,
            shape_id=shape.name, file=fname_xml,
            raw_part=raw_part, sha256=sha_xml,
            chart_part_refs=refs, notes=note,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    def _extract_table(self, shape, page_num: int) -> str:
        aid = self._next_id()
        try:
            tbl = shape.table
            rows = []
            for r in tbl.rows:
                rows.append("| " + " | ".join((cell.text or "").replace("\n", " ").replace("|", "\\|") for cell in r.cells) + " |")
            md = "| " + " | ".join(f"c{i+1}" for i in range(len(rows[0].split("|")) - 2)) + " |\n"
            md += "| " + " | ".join(["---"] * (len(rows[0].split("|")) - 2)) + " |\n"
            md += "\n".join(rows)
            if len(rows) > 20:
                md += f"\n\n> ⚠️ 表格 >20 行（{len(rows)} 行），仅展示前 20 行"
                self.stats.warnings.append(f"p{page_num} {shape.name}: 表格 {len(rows)} 行截断至 20")
        except Exception as e:
            md = f"> ⚠️ 表格提取失败: {e}\n"
            self.stats.warnings.append(f"p{page_num} {shape.name}: 表格提取失败 {e}")

        fname = f"tables/{aid}.md"
        self._write_text(self.out_dir / fname, md)
        sha = self._sha256_text(md)

        rec = AssetRecord(
            asset_id=aid, type="table", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part="", sha256=sha,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    def _extract_media(self, shape, page_num: int) -> str:
        aid = self._next_id()
        try:
            blob = shape.image.blob
            ext = shape.image.ext
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: 媒体读取失败 {e}（可能致 D11 修复对话框）")
            return ""

        fname = f"videos/{aid}.{ext}"
        fpath = self.out_dir / fname
        self._write_bytes(fpath, blob)
        size = len(blob)
        sha = self._sha256_bytes(blob)

        notes = ""
        if size == 0:
            notes = "⚠️ 0 字节媒体（D11 苗子）"
        elif size > LARGE_MEDIA_BYTES:
            notes = f"⚠️ 媒体 {size // (1024*1024)}MB 超 50MB（D11 苗子）"

        rec = AssetRecord(
            asset_id=aid, type="video", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part=self._find_raw_part_for_image(shape),
            sha256=sha, media_bytes=size, notes=notes,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    def _extract_ole(self, shape, page_num: int) -> str:
        aid = self._next_id()
        notes = ""
        blob = b""
        try:
            blob = shape.image.blob
            ext = shape.image.ext or "bin"
        except Exception:
            ext = "bin"
            notes = "blob 读取失败，原样留存"

        fname = f"ole/{aid}.{ext}"
        self._write_bytes(self.out_dir / fname, blob)
        sha = self._sha256_bytes(blob) if blob else ""

        # 尝试 olefile 解析
        if _HAS_OLEFILE and blob:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                    tmp.write(blob)
                    tmp_path = tmp.name
                try:
                    if olefile.isOleFile(tmp_path):
                        ole = olefile.OleFileIO(tmp_path)
                        ole_streams = ole.listdir()
                        preview = ", ".join("/".join(p) for p in ole_streams[:5])
                        notes = f"OLE streams: {preview}..."
                        ole.close()
                    else:
                        notes = "非标准 OLE 格式，原样留存"
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
            except Exception as e:
                notes = f"OLE 解析失败: {e}，原样留存"
                self.stats.warnings.append(f"p{page_num} {shape.name}: OLE 解析失败 {e}")
        else:
            notes = "olefile 库未安装或 blob 为空，原样留存；如需解析请 `pip install olefile`"

        note_path = f"ole/{aid}.note.txt"
        self._write_text(self.out_dir / note_path, f"OLE 资产 {aid}\n页: {page_num}\nshape: {shape.name}\nnotes: {notes}\n需人工打开：可能含内嵌对象（Excel/Word/PDF 等）\n")

        rec = AssetRecord(
            asset_id=aid, type="ole", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part="", sha256=sha, media_bytes=len(blob),
            notes=notes,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    def _extract_smartart(self, shape, page_num: int) -> str:
        aid = self._next_id()
        notes = "SmartArt 嗅探命中；diagrams 子目录导出 data1/layout/colors/quickStyle"
        target_dir = self.out_dir / "diagrams" / aid
        if not self.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        try:
            for child in shape._element.iter():
                tag = child.tag
                if "data1" in tag or "layout" in tag or "colors" in tag or "quickStyle" in tag:
                    local = tag.split("}")[-1] + ".xml"
                    self._write_text(target_dir / local, str(child))
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: SmartArt XML 提取失败 {e}")

        rec = AssetRecord(
            asset_id=aid, type="diagram", source_page=page_num,
            shape_id=shape.name, file=f"diagrams/{aid}/",
            raw_part="", sha256="",
            notes=notes,
            extracted_at=datetime.now().isoformat(timespec="seconds"),
            source_deck_sha1=self._sha1, source_deck_mtime=self._mtime,
        )
        self.assets.append(rec)
        return aid

    # ---------- 预扫 chart part 引用数 ----------
    def _pre_scan_chart_refs(self):
        with zipfile.ZipFile(str(self.pptx_path), "r") as z:
            for name in z.namelist():
                if name.startswith("ppt/slides/_rels/") and name.endswith(".xml.rels"):
                    try:
                        data = z.read(name).decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    # 简陋扫描 r:Target 含 charts/
                    for m in re.finditer(r'Target="([^"]*charts/[^"]+)"', data):
                        tgt = m.group(1).lstrip("/")
                        if not tgt.startswith("ppt/"):
                            tgt = "ppt/" + tgt
                        self._chart_part_ref_count[tgt] = self._chart_part_ref_count.get(tgt, 0) + 1

    # ---------- 写盘/哈希辅助 ----------
    def _write_bytes(self, path: Path, data: bytes):
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def _write_text(self, path: Path, text: str):
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    @staticmethod
    def _sha1_file(path: Path) -> str:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _raw_part_name(partname) -> str:
        try:
            return str(partname).lstrip("/")
        except Exception:
            return ""

    def _find_raw_part_for_image(self, shape) -> str:
        try:
            blip = shape._element.find(".//" + NS_A + "blip")
            if blip is not None:
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                if rid:
                    target = shape.part.rels[rid].target_ref
                    return "ppt/" + target.lstrip("/") if not target.startswith("ppt/") else target
        except Exception:
            pass
        return ""

    # ---------- manifest 写盘 ----------
    def _write_manifest(self):
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "extractor_version": SCHEMA_VERSION,
            "source_deck": str(self.pptx_path),
            "source_deck_sha1": self._sha1,
            "source_deck_mtime": self._mtime,
            "extracted_at": datetime.now().isoformat(timespec="seconds"),
            "total_slides": self.stats.total_slides,
            "assets_count": len(self.assets),
            "assets_by_type": dict(self.stats.assets_by_type),
            "skipped": self.stats.skipped,
            "unknown_shapes": self.stats.unknown_shapes,
            "zero_byte_media": self.stats.zero_byte_media,
            "large_media": self.stats.large_media,
            "shared_charts": self.stats.shared_charts,
            "warnings": list(self.stats.warnings),
            "assets": [asdict(a) for a in self.assets],
        }
        manifest_path = self.out_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=False)
        log.info("manifest 已写入: %s（%d 条）", manifest_path, len(self.assets))

    # ---------- 完整性断言 4 条 ----------
    def _check_integrity(self) -> tuple[bool, list[str]]:
        errs: list[str] = []
        # 断言 1：每条 manifest 的 file 字段对应文件真实存在
        for a in self.assets:
            if not a.file:
                continue
            fpath = self.out_dir / a.file
            if "*" in a.file or a.file.endswith("/"):
                # SmartArt 目录
                if not fpath.is_dir():
                    errs.append(f"{a.asset_id} 目录不存在: {a.file}")
                continue
            if not fpath.exists():
                errs.append(f"{a.asset_id} 文件不存在: {a.file}")
                continue
            # sha256 复核（仅当非目录）
            try:
                with open(fpath, "rb") as f:
                    data = f.read()
                if a.sha256:
                    actual = hashlib.sha256(data).hexdigest()
                    if actual != a.sha256:
                        errs.append(f"{a.asset_id} sha256 不匹配")
            except OSError as e:
                errs.append(f"{a.asset_id} 读取失败: {e}")
        # 断言 2：manifest 自身可解析 + 含 schema_version
        manifest_path = self.out_dir / "manifest.json"
        try:
            with open(manifest_path, encoding="utf-8") as f:
                m = json.load(f)
            if "schema_version" not in m:
                errs.append("manifest 缺 schema_version")
        except Exception as e:
            errs.append(f"manifest 解析失败: {e}")
        # 断言 3：assets_count 与 assets 数组长度一致
        if "assets" in m and "assets_count" in m:
            if len(m["assets"]) != m["assets_count"]:
                errs.append(f"assets_count={m['assets_count']} 与实际 {len(m['assets'])} 不一致")
        return (len(errs) == 0, errs)

    # ---------- dry-run 输出 ----------
    def emit_dry_run_json(self) -> str:
        out = {
            "dry_run": True,
            "source_deck": str(self.pptx_path),
            "total_slides": self.stats.total_slides,
            "predicted_assets": dict(self.stats.assets_by_type),
            "skipped": self.stats.skipped,
            "unknown_shapes": self.stats.unknown_shapes,
            "zero_byte_media": self.stats.zero_byte_media,
            "large_media": self.stats.large_media,
            "shared_charts": self.stats.shared_charts,
            "warnings": list(self.stats.warnings),
        }
        return json.dumps(out, ensure_ascii=False, indent=2)


# ============== CLI ==============
def main():
    ap = argparse.ArgumentParser(
        description="PPT 嵌入元素资产化提取器（v3.2.0-batch1）",
    )
    ap.add_argument("pptx", help="课件 .pptx 绝对或相对路径")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认 <课件>_assets/ 跟课件同目录）")
    ap.add_argument("--dry-run", action="store_true", help="只读不写盘，输出 JSON 预测")
    ap.add_argument("--force", action="store_true", help="覆盖已有 manifest.json")
    ap.add_argument("--json", action="store_true", help="dry-run 时输出 JSON 到 stdout")
    args = ap.parse_args()

    pptx_path = Path(args.pptx).resolve()
    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = pptx_path.with_suffix("")  # 去 .pptx
        out_dir = out_dir.parent / (out_dir.name + "_assets")

    extractor = AssetExtractor(
        pptx_path=str(pptx_path),
        out_dir=str(out_dir),
        dry_run=args.dry_run,
        force=args.force,
    )
    rc = extractor.run()

    if args.dry_run and args.json:
        print(extractor.emit_dry_run_json())
    elif args.dry_run:
        print(extractor.emit_dry_run_json())

    if rc == 0:
        log.info("✓ 全部成功（%d 条资产，%d 张幻灯片）", len(extractor.assets), extractor.stats.total_slides)
    elif rc == 1:
        log.error("✗ 完整性断言失败（exit 1）")
    elif rc == 2:
        log.error("✗ 形状识别异常（exit 2）")
    elif rc == 3:
        log.error("✗ 文件读取失败（exit 3）")
    else:
        log.error("✗ 运行错误（exit 4）")
    sys.exit(rc)


if __name__ == "__main__":
    main()

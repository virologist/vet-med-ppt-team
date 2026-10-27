#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_assets.py — PPT 嵌入元素资产化提取器（v3.2.0-batch1 · v3.16.0 配图链路记录字段）

> 适用场景：WF-2R 旧课件诊疗流水线 S1 资产化转换层。
> 目标：把 PPT 嵌入元素从"靠人眼看"变成"机器可读 + 双向校验"，
>       给 S2 诊断和 S3 C 轨施工提供真值；同时为 D11（修复对话框），
>       D3（资产腐烂），D4（图表联动）提供数据基座。

v3.16.0 变更（F8 配图链路补记录字段，针对九维度诊断 M3「配图链路几乎无记录」）：
  1. 新增 4 个记录字段：width / height（EMU→px，取不到置 null 并写明原因）、
     source_url（来源链接）、doi_pmcid（文献标识）——全部在 manifest 里有真实取值。
  2. 许可纪律：license_note 默认值由「原课件自带」改为空字符串——原默认值等于
     "默认可用"的错误暗示（与 adjudication-rules.md 原则六「不默认可用」冲突）。
     license_note 为空时 reuse_status 必须为「待核查」；manifest 统计区块给出
     「未登记许可的素材数」。
  3. 新增 --require-license 门禁（默认关闭，不阻断既有流程）：存在空许可素材时
     exit 1 + 前缀行数与 asset_id 清单。
  4. 旧 manifest 兼容：AssetRecord.from_dict / load_manifest_records 缺字段容错。
  默认值与提示语的机器源：references/asset-fields.yaml（人读说明见 extract_assets_usage.md §10）。

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
  1 完整性断言失败 / 许可门禁未过（v3.16.0：--require-license 命中空许可）
  2 形状识别异常（OLE/SmartArt 等）
  3 文件读取失败（IO/zip 损坏/路径无效）
  4 运行错误（脚本 bug、fixture 损坏、依赖缺失）

CLI：
  python3 extract_assets.py <课件.pptx> [--out-dir DIR] [--dry-run] [--force] [--json]
                            [--require-license]
"""

from __future__ import annotations

import argparse
import copy
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
from dataclasses import dataclass, field, asdict, MISSING
from datetime import datetime
from pathlib import Path
from typing import Optional
import typing

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

try:
    import yaml  # 配置登记块解析（与 verify_deck.py / case_extract.py 同依赖）
    _HAS_YAML = True
except ImportError:
    yaml = None
    _HAS_YAML = False

# ============== 日志（INFO/ERROR 双级，不 silent）==============
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract_assets")

# ============== 配置登记（v3.16.0）==============
# 缘由：v3.16.0 之前 license_note 默认值「原课件自带」写死在代码里，等于"默认可用"的
#   错误暗示（诊断 M3）。新增字段的默认值与缺值提示语同样不该散落硬编码。
# 处置：默认值 / 缺值提示语 / EMU→px 换算系数集中登记在 **独立 yaml 文件**
#   references/asset-fields.yaml（唯一机器源；人读说明在 extract_assets_usage.md §10，
#   该 md 只做说明与指向，不再保留第二份可解析副本——避免"多源"）。
#   读法与 verify_deck.py#_load_threshold() 读 config/visual-rules.yaml 同风格：
#   显式路径 + 失败告警 + 内置回退（文件缺失/pyyaml 未装/YAML 语法错 → 回退，不阻断）。
#   改 yaml 不同步改下面的内置回退值，会被 test_extract_assets.py T14 判「配置漂移」。
_ASSET_FIELDS_PATH = Path(__file__).resolve().parent.parent / "references" / "asset-fields.yaml"

_BUILTIN_ASSET_FIELD_CONFIG = {
    "asset_fields": {
        "emu_per_px": 9525,              # OOXML EMU → px 换算系数（1 px = 9525 EMU）
        "width_default": None,           # 取不到尺寸时置 null（不是 0）
        "height_default": None,
        "source_url_default": "",        # 无来源链接时留空串
        "doi_pmcid_default": "",         # 无文献标识时留空串
        "license_note_default": "",      # v3.16.0：不再默认「原课件自带」
        "reuse_status_default": "待核查",  # v3.16.0：统一语义（原「未决」）
        "legacy_license_placeholders": ["原课件自带"],  # 旧 manifest 中的无效占位许可值
        "size_missing_note": "宽高未取得：{reason}",
        "legacy_placeholder_note": "旧占位许可值「{value}」已作废（v3.16.0），须人工重新登记",
    },
    "license_gate": {
        "count_line": "未登记许可的素材数 = {n}",
        "prefix": "未登记许可",
        "summary_line": "未登记许可：{n} 条素材（--require-license 已启用，须补登记后重跑）",
        "ids_line": "未登记许可明细：{ids}",
        "reuse_violation_line": "许可纪律：{asset_id} license_note 为空但 reuse_status={status}（应为「{expected}」）",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """浅层覆盖 + 二级字典合并；override 缺的键沿用 base（保证配置段可只写一部分）。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_asset_field_config() -> dict:
    """优先读 references/asset-fields.yaml；失败回退内置值并告警（不阻断提取）。

    与 verify_deck.py#_load_threshold() 同风格：显式路径 + 一次 yaml.safe_load +
    内置回退。只读本文件一处，人读文档（extract_assets_usage.md）不再参与解析。
    """
    fallback = copy.deepcopy(_BUILTIN_ASSET_FIELD_CONFIG)
    if not _HAS_YAML:
        log.warning("pyyaml 未安装，asset-fields.yaml 无法解析，回退内置值")
        return fallback
    try:
        with open(_ASSET_FIELDS_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except OSError as e:
        log.warning("配置登记读取失败（%s: %s），回退内置值", _ASSET_FIELDS_PATH.name, e)
        return fallback
    except Exception as e:  # YAML 语法错等
        log.warning("配置登记解析失败（%s: %s），回退内置值", _ASSET_FIELDS_PATH.name, e)
        return fallback
    if not isinstance(cfg, dict):
        log.warning("配置登记不是字典结构（%s），回退内置值", _ASSET_FIELDS_PATH.name)
        return fallback
    # 只消费已知配置段；yaml 里的元信息键（如 version）与注释不参与合并
    known = {k: v for k, v in cfg.items() if k in fallback}
    return _deep_merge(fallback, known)


_CFG = _load_asset_field_config()
_AF = _CFG["asset_fields"]      # asset_fields 段
_LG = _CFG["license_gate"]      # license_gate 段


# ── 漂移诊断：给「yaml 与内置回退值不一致」一个可定位的报错（v3.24.0 · FEAT-003a）──
# 病灶：`test_extract_assets.py::T14` 原本用 `assertEqual(dict, dict)` 比对两份配置，
#   失败信息只说"两处不一致"，**不给位置** ⇒ 排查时要人工翻 yaml 与代码找差异键。
# 改法：提供 `describe_asset_field_drift()`，输出**逐键**对照，每条带
#   「yaml 第 N 行」vs「scripts/extract_assets.py 第 M 行」，失败即用。
def _yaml_key_lines(yaml_path: Path) -> dict:
    """扫 yaml 文本，记录每个叶子键首次出现的行号（1-based）。

    ⚠ 只做**行定位**，不做语义解析（语义由 yaml.safe_load 负责）——
    行号仅用于加速人工定位，不参与判定。
    """
    lines: dict = {}
    try:
        text = yaml_path.read_text(encoding="utf-8")
    except OSError:
        return lines
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip()
        if key and key not in ("-",) and not key.startswith("-"):
            lines.setdefault(key, idx)
    return lines


def _builtin_key_lines() -> dict:
    """扫内置回退值字典字面量，记录每个键的行号（1-based）。"""
    lines: dict = {}
    try:
        text = Path(__file__).resolve().read_text(encoding="utf-8")
    except OSError:
        return lines
    start = 0
    for i, raw in enumerate(text.splitlines()):
        if raw.startswith("_BUILTIN_ASSET_FIELD_CONFIG"):
            start = i
            break
    for i, raw in enumerate(text.splitlines()[start:], start=start + 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or '"' not in stripped:
            continue
        key = stripped.split('"', 2)[1] if stripped.startswith('"') else ""
        if key and key not in lines:
            lines[key] = i
    return lines


def describe_asset_field_drift() -> list:
    """返回漂移明细列表；空列表 ⇒ 两份配置一致。

    每条形如：
      {'path': 'asset_fields.emu_per_px',
       'yaml_line': 27, 'code_line': 108,
       'yaml_value': 9525, 'code_value': 9526,
       'kind': 'value_mismatch' | 'only_in_yaml' | 'only_in_code'}
    """
    yaml_path = _ASSET_FIELDS_PATH
    loaded = _load_asset_field_config()
    builtin = copy.deepcopy(_BUILTIN_ASSET_FIELD_CONFIG)
    y_lines = _yaml_key_lines(yaml_path)
    c_lines = _builtin_key_lines()

    diffs: list = []
    for section in sorted(set(loaded) | set(builtin)):
        ys = loaded.get(section) or {}
        cs = builtin.get(section) or {}
        if not isinstance(ys, dict) or not isinstance(cs, dict):
            if ys != cs:
                diffs.append({
                    "path": section, "kind": "section_mismatch",
                    "yaml_line": y_lines.get(section), "code_line": c_lines.get(section),
                    "yaml_value": ys, "code_value": cs,
                })
            continue
        for key in sorted(set(ys) | set(cs)):
            yv, cv = ys.get(key), cs.get(key)
            if yv == cv:
                continue
            if key in ys and key not in cs:
                kind = "only_in_yaml"
            elif key in cs and key not in ys:
                kind = "only_in_code"
            else:
                kind = "value_mismatch"
            diffs.append({
                "path": f"{section}.{key}", "kind": kind,
                "yaml_line": y_lines.get(key), "code_line": c_lines.get(key),
                "yaml_value": yv, "code_value": cv,
            })
    return diffs


def _append_note(base: str, extra: str, sep: str = "｜") -> str:
    """notes 拼接；任一侧为空时不插分隔符（保持既有 notes 文本不变形）。"""
    base = base or ""
    extra = extra or ""
    if not extra:
        return base
    if not base:
        return extra
    return base + sep + extra


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
    """manifest 单条 schema（核心六字段 + v3.16.0 新增 4 记录字段 + 7 派生）。

    默认值一律取自 _AF（机器源：references/asset-fields.yaml），不就地写死。
    """
    asset_id: str
    type: str  # image|chart|video|table|diagram|ole
    source_page: int
    shape_id: str
    file: str
    raw_part: str
    render: str = ""           # 占位，Batch 2 渲染层补全
    sha256: str = ""
    # ── v3.16.0 新增：配图链路记录字段（取值口径与缺失语义见 usage 文档 §4.1）──
    width: Optional[int] = _AF["width_default"]        # 显示宽度 px（EMU/emu_per_px 取整）
    height: Optional[int] = _AF["height_default"]      # 显示高度 px；取不到为 null（不是 0）
    source_url: str = _AF["source_url_default"]        # 来源链接；无则 ""
    doi_pmcid: str = _AF["doi_pmcid_default"]          # 文献标识（DOI/PMCID）；无则 ""
    license_note: str = _AF["license_note_default"]    # 许可登记；空 = 未登记（不默认可用）
    reuse_status: str = _AF["reuse_status_default"]    # 未登记许可时为「待核查」
    notes: str = ""
    # 派生字段
    chart_part_refs: int = 0
    media_bytes: int = 0
    extracted_at: str = ""
    extractor_version: str = SCHEMA_VERSION
    source_deck_sha1: str = ""
    source_deck_mtime: str = ""
    pptx_schema: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "AssetRecord":
        """v3.16.0：从 manifest 字典回读，缺字段容错（旧 manifest 兼容策略）。

        兼容规则（详见 references/extract_assets_usage.md §4.2）：
          - 只取本类已声明字段，manifest 里的多余键忽略；
          - 缺失字段用默认值补齐（width/height → null，source_url/doi_pmcid/license_note → ""）；
          - license_note 命中 legacy_license_placeholders（如「原课件自带」）→ 视为未登记，
            清空并在 notes 写明原因；
          - license_note 为空但 reuse_status 不是「待核查」→ 归一为「待核查」。
        """
        d = d or {}
        hints = typing.get_type_hints(cls)
        kwargs = {}
        for f, spec in cls.__dataclass_fields__.items():
            if f in d:
                kwargs[f] = d[f]
            elif spec.default is MISSING and spec.default_factory is MISSING:
                # 核心字段缺失（旧/损坏 manifest）：按声明类型补零值，不抛异常
                kwargs[f] = 0 if hints.get(f) is int else ""
        rec = cls(**kwargs)
        # 旧占位许可值作废（M3：不默认可用）
        if rec.license_note in (_AF.get("legacy_license_placeholders") or []):
            rec.notes = _append_note(
                rec.notes, _AF["legacy_placeholder_note"].format(value=rec.license_note)
            )
            rec.license_note = _AF["license_note_default"]
        if not (rec.license_note or "").strip():
            rec.reuse_status = _AF["reuse_status_default"]
        return rec


def load_manifest_records(manifest_path) -> list:
    """v3.16.0：读取 manifest（含旧版）为 AssetRecord 列表，缺字段容错不抛异常。"""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    return [AssetRecord.from_dict(x) for x in (manifest.get("assets") or [])]


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
    # v3.16.0：许可登记统计
    unlicensed_assets: int = 0                              # 未登记许可的素材数
    unlicensed_asset_ids: list = field(default_factory=list)
    license_gate_passed: bool = True                        # --require-license 门禁是否通过


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

    def __init__(self, pptx_path: str, out_dir: str, dry_run: bool = False, force: bool = False,
                 require_license: bool = False):
        self.pptx_path = Path(pptx_path).resolve()
        self.out_dir = Path(out_dir).resolve()
        self.dry_run = dry_run
        self.force = force
        # v3.16.0：许可门禁开关，默认关闭以免阻断既有流程（CLI: --require-license）
        self.require_license = require_license
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
            self._ensure_dir(self.out_dir)
            for sub in ("images", "charts", "videos", "tables", "diagrams", "ole"):
                self._ensure_dir(self.out_dir / sub)
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

        # 7.5) 许可纪律断言（写盘前）：license_note 为空 → reuse_status 必须为「待核查」
        # v3.16.0：把"未登记许可"与"可复用"两个语义锁死，防止空许可被当作已授权流转。
        ok_lic, lic_errs = self._assert_reuse_status_consistency()
        if not ok_lic:
            for e in lic_errs:
                log.error("%s", e)
            self.stats.license_gate_passed = False
            self.stats.integrity_passed = False
            self.stats.exit_code = 1
            return 1

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

        # 10) v3.16.0：--require-license 门禁（manifest 已落盘，便于照清单补登记）
        gate_errs = self._check_license_gate()
        if gate_errs:
            for e in gate_errs:
                log.error("%s", e)
            self.stats.license_gate_passed = False
            self.stats.exit_code = 1
            return 1

        self.stats.license_gate_passed = True
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
        self._tally_license()

    # ---------- v3.16.0：许可登记统计与门禁 ----------
    def _unlicensed_assets(self) -> list:
        """返回 license_note 为空（未登记许可）的素材列表。"""
        return [a for a in self.assets if not (a.license_note or "").strip()]

    def _tally_license(self):
        """统计并打印「未登记许可的素材数」（默认流程必现，供人工与机器核对）。"""
        bad = self._unlicensed_assets()
        self.stats.unlicensed_assets = len(bad)
        self.stats.unlicensed_asset_ids = [a.asset_id for a in bad]
        log.info(_LG["count_line"].format(n=len(bad)))
        return len(bad)

    def _assert_reuse_status_consistency(self) -> tuple[bool, list]:
        """写盘前断言：license_note 为空时 reuse_status 必须是「待核查」。"""
        expected = _AF["reuse_status_default"]
        errs = [
            _LG["reuse_violation_line"].format(
                asset_id=a.asset_id, status=a.reuse_status, expected=expected
            )
            for a in self._unlicensed_assets()
            if a.reuse_status != expected
        ]
        return (len(errs) == 0, errs)

    def _check_license_gate(self) -> list:
        """--require-license 门禁：存在空许可素材时返回 [行数, asset_id 清单]，否则 []。"""
        if not self.require_license:
            return []
        bad = self._unlicensed_assets()
        if not bad:
            return []
        return [
            _LG["summary_line"].format(n=len(bad)),
            _LG["ids_line"].format(ids=", ".join(a.asset_id for a in bad)),
        ]

    # ---------- v3.16.0：尺寸（EMU→px）----------
    def _shape_px_size(self, shape) -> tuple:
        """取形状显示尺寸并换算为 px（EMU / emu_per_px，取整）。

        返回 (width_px, height_px, reason)；reason 为空串表示取得成功，
        非空时调用方须把 width/height 置 null 并把原因写进 notes。
        """
        default_w = _AF["width_default"]
        default_h = _AF["height_default"]
        try:
            w_emu = shape.width
            h_emu = shape.height
        except Exception as e:
            return default_w, default_h, f"shape.width/height 读取失败（{e}）"
        if w_emu is None or h_emu is None:
            return default_w, default_h, "shape.width/height 为 None"
        try:
            w_emu, h_emu = int(w_emu), int(h_emu)
        except (TypeError, ValueError):
            return default_w, default_h, f"shape 尺寸非数值（{w_emu!r}, {h_emu!r}）"
        if w_emu <= 0 or h_emu <= 0:
            return default_w, default_h, f"shape 尺寸非正（w={w_emu} h={h_emu} EMU）"
        per_px = _AF["emu_per_px"] or 1
        w_px, h_px = int(round(w_emu / per_px)), int(round(h_emu / per_px))
        if w_px <= 0 or h_px <= 0:
            return default_w, default_h, f"换算后不足 1px（w={w_px} h={h_px} px）"
        return w_px, h_px, ""

    @staticmethod
    def _size_note(reason: str) -> str:
        """尺寸取不到时的 notes 文本（模板登记在 references 文档 §10）。"""
        return _AF["size_missing_note"].format(reason=reason) if reason else ""

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
        # v3.16.0：统计未登记许可的素材数（默认流程必打这一行）
        self._tally_license()

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

        # v3.16.0：记录显示尺寸（EMU→px）；取不到置 null 并在 notes 写明原因
        w, h, why = self._shape_px_size(shape)
        # v3.16.0：source_url / doi_pmcid 由后续来源登记环节回填，本次留空串（缺失语义见 usage §4.1）
        rec = AssetRecord(
            asset_id=aid, type="image", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part=self._find_raw_part_for_image(shape),
            sha256=sha, media_bytes=len(blob),
            width=w, height=h,
            notes=self._size_note(why),
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

        # v3.16.0：尺寸与来源登记字段（同 _extract_picture）
        w, h, why = self._shape_px_size(shape)
        rec = AssetRecord(
            asset_id=aid, type="chart", source_page=page_num,
            shape_id=shape.name, file=fname_xml,
            raw_part=raw_part, sha256=sha_xml,
            width=w, height=h,
            chart_part_refs=refs, notes=_append_note(note, self._size_note(why)),
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

        # v3.16.0：尺寸与来源登记字段
        w, h, why = self._shape_px_size(shape)
        rec = AssetRecord(
            asset_id=aid, type="table", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part="", sha256=sha,
            width=w, height=h,
            notes=self._size_note(why),
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

        # v3.16.0：尺寸与来源登记字段
        w, h, why = self._shape_px_size(shape)
        rec = AssetRecord(
            asset_id=aid, type="video", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part=self._find_raw_part_for_image(shape),
            sha256=sha, media_bytes=size,
            width=w, height=h,
            notes=_append_note(notes, self._size_note(why)),
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

        # v3.16.0：尺寸与来源登记字段
        w, h, why = self._shape_px_size(shape)
        rec = AssetRecord(
            asset_id=aid, type="ole", source_page=page_num,
            shape_id=shape.name, file=fname,
            raw_part="", sha256=sha, media_bytes=len(blob),
            width=w, height=h,
            notes=_append_note(notes, self._size_note(why)),
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
            self._ensure_dir(target_dir)
        try:
            for child in shape._element.iter():
                tag = child.tag
                if "data1" in tag or "layout" in tag or "colors" in tag or "quickStyle" in tag:
                    local = tag.split("}")[-1] + ".xml"
                    self._write_text(target_dir / local, str(child))
        except Exception as e:
            self.stats.warnings.append(f"p{page_num} {shape.name}: SmartArt XML 提取失败 {e}")

        # v3.16.0：尺寸与来源登记字段
        w, h, why = self._shape_px_size(shape)
        rec = AssetRecord(
            asset_id=aid, type="diagram", source_page=page_num,
            shape_id=shape.name, file=f"diagrams/{aid}/",
            raw_part="", sha256="",
            width=w, height=h,
            notes=_append_note(notes, self._size_note(why)),
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
    @staticmethod
    def _ensure_dir(path: Path):
        """建目录：显式先判存在，再建。

        v3.16.0 修复：本机 WorkBuddy Python shim 的 Path.mkdir 走宿主代理实现，
        对**已存在**目录仍抛 FileExistsError（EEXIST），即 exist_ok=True 不生效 →
        `--force` 重跑到 step6 直接 exit 3（输出目录已存在）、写素材时同样会炸。
        故显式判存在后再建；**不用裸 try/except 吞异常**，以免把权限不足/只读盘/
        路径被文件占用等真实 OSError 一起静默掉（那类错误仍由调用方上报）。
        """
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

    def _write_bytes(self, path: Path, data: bytes):
        if self.dry_run:
            return
        self._ensure_dir(path.parent)
        with open(path, "wb") as f:
            f.write(data)

    def _write_text(self, path: Path, text: str):
        if self.dry_run:
            return
        self._ensure_dir(path.parent)
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
            # v3.16.0：许可登记统计（「未登记许可的素材数」= unlicensed_assets）
            "unlicensed_assets": self.stats.unlicensed_assets,
            "unlicensed_asset_ids": list(self.stats.unlicensed_asset_ids),
            "license_gate": {
                "require_license": self.require_license,
                "passed": self.stats.license_gate_passed,
            },
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
        m: dict = {}   # v3.16.0：解析失败时也要能安全走到后续断言（原实现会 NameError）
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
        # 断言 4（v3.16.0）：manifest 必须带 4 个新记录字段键，且可被 from_dict 回读
        # （回读走的是旧 manifest 兼容路径，等于每次全量跑都自测一遍容错逻辑）
        for raw in (m.get("assets") or []):
            missing = [k for k in ("width", "height", "source_url", "doi_pmcid") if k not in raw]
            if missing:
                errs.append(f"{raw.get('asset_id', '?')} 缺记录字段键: {', '.join(missing)}")
        try:
            recs = [AssetRecord.from_dict(x) for x in (m.get("assets") or [])]
            if len(recs) != len(m.get("assets") or []):
                errs.append("manifest assets 回读条数不一致")
            if "unlicensed_assets" not in m:
                errs.append("manifest 缺 unlicensed_assets（未登记许可的素材数）")
        except Exception as e:
            errs.append(f"manifest assets 回读失败: {e}")
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
            # v3.16.0：dry-run 也报未登记许可的素材数（S0 接单即可估许可核查工作量）
            "unlicensed_assets": self.stats.unlicensed_assets,
            "unlicensed_asset_ids": list(self.stats.unlicensed_asset_ids),
            "require_license": self.require_license,
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
    ap.add_argument(
        "--require-license", dest="require_license", action="store_true",
        help="v3.16.0 许可门禁：存在 license_note 为空的素材时 exit 1 并列出 asset_id"
             "（默认关闭，不阻断既有流程）",
    )
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
        require_license=args.require_license,
    )
    rc = extractor.run()

    if args.dry_run and args.json:
        print(extractor.emit_dry_run_json())
    elif args.dry_run:
        print(extractor.emit_dry_run_json())

    if rc == 0:
        log.info("✓ 全部成功（%d 条资产，%d 张幻灯片，未登记许可 %d 条）",
                 len(extractor.assets), extractor.stats.total_slides,
                 extractor.stats.unlicensed_assets)
    elif rc == 1:
        if not extractor.stats.license_gate_passed:
            log.error("✗ 许可门禁未过（exit 1）：按上方「%s」明细补登记 license_note 后重跑",
                      _LG["prefix"])
        else:
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

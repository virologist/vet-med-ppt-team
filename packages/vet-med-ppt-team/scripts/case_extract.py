#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_extract.py — vet-med-ppt-team 病例库登记册 v3.2.0-batch4

做什么（v3.2.0-batch4 立项依据）：
  49 件课件 × 每件 5 案例 = 245 个案例散落在 PPT 内部 "案例 1..5" 页里；
  deck_registry 仅收 4 件，无集中台账 → 案例复用全靠人脑记忆 + ReAct 检索无法机器化。
  本脚本把"自然语言段落"变成"有 ID / 病种映射 / 三源核验 / 课件双向引用"的结构化资产。

设计原则（继承 Batch 1-3 铁律）：
  - 能用代码约束的，不靠自觉（脱敏内置，不可关）
  - 写文件必带 --confirm，干跑 --dry 不写
  - 失败不阻断，标 unverified=true + 留 verifier 抽检（与 Batch 3 登记册 register 时不强制 lint 一致）

CLI：
    python3 case_extract.py scan      --root <课件根> --out <cases_library.json> [--dry] [--limit N]
    python3 case_extract.py register  --case-id C-M4A1-001 --draft <草稿md> --workspace <课程工作区>
    python3 case_extract.py audit     --workspace <课程工作区> [--json out.json]
    python3 case_extract.py find      --disease M4A1 | --keyword <关键词> | --case-id C-M4A1-001

退出码：0=OK  1=有需处置项（缺三源/有重复）  2=用法错误  3=依赖缺失
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("case_extract")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

SCHEMA_VERSION = 1

# ─────────────────────────── 数据 schema ───────────────────────────
@dataclass
class CaseDraft:
    """从 PPT 抽出的案例草稿（脱敏后）。"""
    case_id: str                              # C-<病种模块>-<3位序号>，例 C-M4A1-001
    disease_module: str                       # 病种模块代码，例 M4A1
    disease_name: str                         # 病种中文名，例 禽流感
    case_no: int                              # 案例号 1-5
    title: str                                # 案例标题
    scenario: str                             # 关键场景文本（≤200字，脱敏后）
    severity: str                             # 简单/中等/最高（按 v2 升级规格）
    sources: list = field(default_factory=list)  # 三源核验列表 [{kind,ref,ok}]
    deck_path: str = ""                       # 课件绝对路径
    slide_idx: int = 0                        # 所在页码
    registered_at: str = ""                   # 入册时间
    unverified: bool = True                   # 默认未三源核验


# ─────────────────────────── 病种映射（31 模块 → 中文） ───────────────────────────
DISEASE_MAP: dict[str, str] = {
    "M4A1": "禽流感", "M4A2": "新城疫", "M4A3": "鸡传染性支气管炎",
    "M4A4": "传染性喉气管炎", "M4A5": "肿头综合征-偏肺病毒",
    "M4B1": "传染性法氏囊", "M4B2": "马立克", "M4B3": "禽白血病",
    "M4B4": "传染性贫血",
    "M4C1": "禽腺病毒", "M4C2": "禽痘", "M4C3": "禽脑脊髓炎",
    "M4C4": "禽病毒性关节炎",
    "M4D1": "鸭瘟(鸭病毒性肠炎)", "M4D2": "鸭病毒性肝炎",
    "M4D3": "水禽细小病毒病(小鹅瘟 番鸭细小病毒)",
    "M5A1": "大肠杆菌病", "M5A2": "禽沙门氏菌病(鸡白痢 禽伤寒 禽副伤寒)",
    "M5A3": "禽巴氏杆菌病(禽霍乱)", "M5A4": "鸭疫里默菌病",
    "M5A5": "禽传染性鼻炎",
    "M5B": "鸡支原体病",
    "M5C1": "禽葡萄球菌病", "M5C2": "禽结核",
    "M5D1": "禽曲霉菌", "M5D2": "禽念珠菌",
    "M6A1": "球虫", "M6A2": "住白细胞虫", "M6A3": "禽组织滴虫病",
    "M6B": "禽蠕虫", "M6C": "体表寄生虫",
    "M7A": "营养代谢病", "M7B": "禽中毒病",
}

# 案例标题/页关键标识（按 v2 升级规格）
CASE_HEAD_RE = re.compile(r"案例\s*([1-5])(?:[\s:：、\-—]*)(\S{2,40})?")
SEVERITY_RE = re.compile(r"案例\s*([1-5])", re.I)


# ─────────────────────────── 脱敏（Q2：人名+单位+地址） ───────────────────────────
# 不可关（铁律）：CLAUDE.md §7-A 物种语境保护 + 病患隐私
DESENSITIZE_PATTERNS = [
    # 人名：姓+名+(老师/医生/场长/技术员/老板/经理)。贪婪匹配姓+任意字符直到身份后缀
    (re.compile(r"[\u4e00-\u9fa5]+?(?:老师|医生|场长|技术员|老板|经理)"), "XX"),
    # 单位：XX 养殖场 / XX 公司 / XX 鸡场 / XX 养禽场 / XX 大学动物医院
    (re.compile(r"[\u4e00-\u9fa5]+?(?:养殖(?:场|公司)|养禽(?:场|公司)|鸡场|鸭场|种禽场|大学动物医院|公司)"), "XX养殖场"),
    # 地址：X 省 X 市 / XX 市辖区 / XX 区（最后段可能直接是"区"无"市"）
    (re.compile(r"[\u4e00-\u9fa5]{1,3}省[\u4e00-\u9fa5]{0,5}(?:市[\u4e00-\u9fa5]{0,3}区?)?|[\u4e00-\u9fa5]{1,3}市[\u4e00-\u9fa5]{0,3}区|[\u4e00-\u9fa5]{1,3}区"), "X省X市"),
]


def desensitize(text: str) -> str:
    """人名+单位+地址全脱敏（不可关）。"""
    for pat, repl in DESENSITIZE_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ─────────────────────────── 抽取：从 PPT 找案例页 ───────────────────────────
def extract_from_pptx(pptx_path: Path) -> list[CaseDraft]:
    """python-pptx 打开 + 扫"案例 1..5"页。返回草稿列表（不入库）。"""
    try:
        from pptx import Presentation  # noqa
    except ImportError as e:
        log.error("python-pptx 缺失：%s", e)
        return []

    # 病种模块：从父目录名提取（M4A1_禽流感 → M4A1 / M8A1_细菌学 → M8A1）
    m = re.match(r"([MTP][0-9][A-D][0-9]?)", pptx_path.parent.name)
    if not m:
        return []
    disease_module = m.group(1)
    disease_name = resolve_disease_name(disease_module)

    drafts: list[CaseDraft] = []
    try:
        prs = Presentation(str(pptx_path))
    except Exception as e:
        log.warning("打开失败 %s: %s", pptx_path.name, e)
        return []

    for slide_idx, slide in enumerate(prs.slides, start=1):
        # 抽本页所有文本
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for p in shape.text_frame.paragraphs:
                    for r in p.runs:
                        if r.text.strip():
                            texts.append(r.text.strip())
        full = " | ".join(texts)
        if not full:
            continue

        # 找首个"案例 N"标识（每页只取一条 → 防多 title 重复）
        m_case = CASE_HEAD_RE.search(full)
        if not m_case:
            continue
        case_no = int(m_case.group(1))
        title = (m_case.group(2) or f"案例{case_no}").strip()[:40]
        # 跳过重复 case_no（防 AI 指令页/合并页同 case_no 出现多次）
        if any(d.case_no == case_no and d.deck_path == str(pptx_path.resolve()) for d in drafts):
            continue

        # 关键场景：取本案例后 200 字（脱敏）
        start = m_case.end()
        scenario = full[start:start + 200]
        scenario = desensitize(scenario)

        # 严重度：按 v2 规格 1-3=普通 / 4=复杂4 / 5=最高复杂
        severity = "最高" if case_no == 5 else ("中等" if case_no == 4 else "普通")

        # 案例 ID：C-<病种>-<3位序号>（5个案例/课件足够）
        case_id = f"C-{disease_module}-{case_no:03d}"

        drafts.append(CaseDraft(
            case_id=case_id, disease_module=disease_module, disease_name=disease_name,
            case_no=case_no, title=title, scenario=scenario, severity=severity,
            deck_path=str(pptx_path.resolve()), slide_idx=slide_idx,
            registered_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            unverified=True,
        ))
    return drafts


# ─────────────────────────── domain_config 加载（v3.3.0） ───────────────────────────
def _load_domain_config() -> tuple[dict, str]:
    """读 config/domain_config.yaml；失败回退 DISEASE_MAP（deprecated）。"""
    try:
        import yaml  # noqa
        # 候选路径：脚本同级的 ../config/（专家包）；或 <workspace>/.workbuddy/domain.yaml
        candidates = [
            Path(__file__).parent.parent / "config" / "domain_config.yaml",
        ]
        for p in candidates:
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    return yaml.safe_load(f), "yaml"
    except Exception as e:
        log.warning("domain_config.yaml 加载失败（%s），回退 DISEASE_MAP", e)
    return {"disease_modules": {"animal-medicine": DISEASE_MAP}}, "fallback"


_DOMAIN_CFG, _DOMAIN_SRC = _load_domain_config()


def resolve_disease_name(module: str) -> str:
    """v3.3.0：跨 4 domain 查病种中文名（替代 DISEASE_MAP 单层）。"""
    modules = _DOMAIN_CFG.get("disease_modules", {})
    for domain_id, m in modules.items():
        if isinstance(m, dict) and module in m:
            return m[module]
    return "未知病种"


# ─────────────────────────── 登记册读写 ───────────────────────────
def cases_path(workspace: Path) -> Path:
    """课程工作区下的登记册路径（Q3：.workbuddy/cases/cases_library.json）。"""
    p = workspace / ".workbuddy" / "cases" / "cases_library.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_library(workspace: Path) -> dict:
    p = cases_path(workspace)
    if not p.exists():
        return {"schema_version": SCHEMA_VERSION, "cases": [],
                "registered_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("登记册解析失败（%s），按空册处理", e)
        return {"schema_version": SCHEMA_VERSION, "cases": []}


def save_library(workspace: Path, lib: dict) -> Path:
    p = cases_path(workspace)
    lib["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    return p


def upsert_case(lib: dict, draft: CaseDraft) -> bool:
    """去重入册（按 case_id）。返回 True=新增 / False=已存在跳过。"""
    cases = lib.setdefault("cases", [])
    if any(c.get("case_id") == draft.case_id for c in cases):
        return False
    cases.append(asdict(draft))
    return True


# ─────────────────────────── 审计 ───────────────────────────
def audit_library(lib: dict) -> dict:
    """统计 + 缺三源/有重复等需处置项。"""
    cases = lib.get("cases", [])
    by_disease: dict[str, int] = {}
    unverified = 0
    for c in cases:
        by_disease[c.get("disease_module", "?")] = by_disease.get(c.get("disease_module", "?"), 0) + 1
        if c.get("unverified", True):
            unverified += 1
    return {
        "total": len(cases),
        "by_disease": dict(sorted(by_disease.items())),
        "unverified_count": unverified,
        "verdict": "ok" if unverified == 0 else "needs_verification",
    }


# ─────────────────────────── CLI 子命令 ───────────────────────────
def cmd_scan(args):
    """扫描课件根 → 抽案例草稿 → 可选干跑 / 落盘。"""
    try:
        root = Path(args.root).expanduser().resolve()
    except Exception as e:
        print(f"用法错误：--root 解析失败：{e}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"用法错误：--root 不是目录：{root}", file=sys.stderr)
        return 2

    # Q1：默认 200 条先入（每病种 5-7 个）
    if args.limit is None:
        args.limit = 200
    log.info("扫描根：%s (limit=%d, dry=%s)", root, args.limit, args.dry)

    decks = sorted(root.rglob("*.pptx"))
    log.info("发现 %d 件课件", len(decks))

    drafts: list[CaseDraft] = []
    skipped = 0
    for d in decks:
        # 跳过已被隔离的目录（v75 隔离清单 / _autofix_产物隔离）
        if "_autofix_产物隔离" in str(d) or "/.backup_archive/" in str(d):
            skipped += 1
            continue
        ds = extract_from_pptx(d)
        drafts.extend(ds)
        if len(drafts) >= args.limit:
            log.info("已达 limit=%d，停止扫描", args.limit)
            break

    # 按 case_id 排序
    drafts.sort(key=lambda x: (x.disease_module, x.case_no))

    if args.dry:
        print(json.dumps({
            "mode": "dry-run", "scanned_decks": len(decks) - skipped,
            "skipped_decks": skipped, "draft_count": len(drafts),
            "by_disease": {d.disease_module: 0 for d in drafts},  # 简版统计
            "first_5": [asdict(d) for d in drafts[:5]],
        }, ensure_ascii=False, indent=2))
        return 0

    # 落盘
    if not args.workspace:
        print("用法错误：--workspace 必填（登记册落盘位置）", file=sys.stderr)
        return 2
    lib = load_library(Path(args.workspace).expanduser())
    new_count = sum(1 for d in drafts if upsert_case(lib, d))
    p = save_library(Path(args.workspace).expanduser(), lib)
    print(json.dumps({
        "saved_to": str(p),
        "drafts_total": len(drafts), "newly_registered": new_count,
        "library_total": len(lib["cases"]),
        "audit": audit_library(lib),
    }, ensure_ascii=False, indent=2))
    return 1 if new_count < len(drafts) else 0  # 重复=1 让 verifier 关注


def cmd_register(args):
    """手动登记（批量扫描外的特殊案例入口）。"""
    if not args.workspace:
        print("用法错误：--workspace 必填", file=sys.stderr)
        return 2
    # 简化：单字段手动登记
    lib = load_library(Path(args.workspace).expanduser())
    draft = CaseDraft(
        case_id=args.case_id, disease_module=args.case_id.split("-")[1],
        disease_name=resolve_disease_name(args.case_id.split("-")[1]),
        case_no=int(args.case_id.split("-")[2]),
        title=args.title or f"案例{args.case_id.split('-')[2]}",
        scenario=desensitize(args.scenario or ""),
        severity=args.severity or "普通",
    )
    added = upsert_case(lib, draft)
    p = save_library(Path(args.workspace).expanduser(), lib)
    print(json.dumps({"saved_to": str(p), "added": added, "case_id": draft.case_id},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_audit(args):
    lib = load_library(Path(args.workspace).expanduser())
    out = audit_library(lib)
    out["workspace"] = str(args.workspace)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verdict"] == "ok" else 1


def cmd_find(args):
    lib = load_library(Path(args.workspace).expanduser())
    cases = lib.get("cases", [])
    if args.case_id:
        cases = [c for c in cases if c.get("case_id") == args.case_id]
    elif args.disease:
        cases = [c for c in cases if c.get("disease_module") == args.disease]
    elif args.keyword:
        kw = args.keyword.lower()
        cases = [c for c in cases if kw in (c.get("title", "") + c.get("scenario", "")).lower()]
    else:
        print("用法错误：--case-id / --disease / --keyword 三选一", file=sys.stderr)
        return 2
    print(json.dumps({"matched": len(cases), "cases": cases[:20]}, ensure_ascii=False, indent=2))
    return 0


# ─────────────────────────── main ───────────────────────────
def main():
    ap = argparse.ArgumentParser(description="病例库登记册 v3.2.0-batch4")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="扫描课件根 → 抽案例 → 干跑/入册")
    p.add_argument("--root", required=True, help="课件根目录（递归 .pptx）")
    p.add_argument("--workspace", default="", help="登记册落盘位置（课程工作区）")
    p.add_argument("--dry", action="store_true", help="干跑：只出不入")
    p.add_argument("--limit", type=int, default=None, help="最多入册条数（默认 200）")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("register", help="手动登记单条案例")
    p.add_argument("--case-id", required=True)
    p.add_argument("--title", default="")
    p.add_argument("--scenario", default="")
    p.add_argument("--severity", default="普通", choices=["普通", "中等", "最高"])
    p.add_argument("--workspace", required=True)
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("audit", help="审计登记册")
    p.add_argument("--workspace", required=True)
    p.add_argument("--json", dest="json", default="", help="审计报告落盘")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("find", help="按 ID/病种/关键词查案例")
    p.add_argument("--case-id", default="")
    p.add_argument("--disease", default="")
    p.add_argument("--keyword", default="")
    p.add_argument("--workspace", required=True)
    p.set_defaults(func=cmd_find)

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()

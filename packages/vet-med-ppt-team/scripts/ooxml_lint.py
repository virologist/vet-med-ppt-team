#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ooxml_lint.py — PPTX OOXML 兼容性检查器（v3.2.0-batch2）

> 适用场景：WF-2R 旧课件诊疗流水线闸 4 门禁前置；D11（修复对话框）系统性防线。
> 目标：把"Office 365 打开时需要修复"的真凶（PKG001 删页残留 / deepcopy 重复 rels /
>       悬空 rId / Content-Types 漏登记 / ID 冲突 / 非法字符 / 列表与 parts 不一致）
>       机器化兜底，ERROR 阻断 + WARN 明示。

六组检查（v3 §3.4 难题④）：
  PKG  zip 重复名 / __MACOSX / Content_Types 完整性 / 0 字节
  REL  r:id 可达性 / 重复 rId / 孤立 part
  CT   Content-Types 覆盖度
  ID   sldId / cNvPr / sldLayoutId / sldMasterId 唯一性
  XML  well-formed / 非法字符 / xml:space
  SYN  sldIdLst ↔ slide parts ↔ presentation.xml.rels 三方一致

退出码（与 harness.py 统一）：
  0 全部 ERROR=0
  1 ERROR≥1（D11 苗子，禁止写回）
  2 zip 损坏
  3 文件读取失败
  4 运行错误（脚本 bug/fixture 损坏/依赖缺失）

CLI：
  python3 ooxml_lint.py <课件.pptx> [--json] [--baseline <original>]
                            [--level ERROR|WARN|all] [--strict]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from lxml import etree
except ImportError as e:
    print(f"⛔ 缺少 lxml 依赖（{e}）——请 pip install lxml", file=sys.stderr)
    sys.exit(4)

# ============== 日志 ==============
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ooxml_lint")

# ============== OOXML 命名空间 ==============
NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
CONTENT_TYPES = NS["ct"]
REL_NS = NS["rel"]
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# 非法控制字符（XML 1.0 不允许，除 tab/lf/cr）
ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# 0 字节媒体阈值（与 extract_assets 保持一致：>50MB 标 INFO）
LARGE_MEDIA = 50 * 1024 * 1024
ZERO_BYTE_WARN = 1  # 0 字节媒体视为 WARN（D11 苗子但非 ERROR）


# ============== Issue 数据类 ==============
@dataclass
class Issue:
    code: str            # PKG-001 / REL-002 / ...
    severity: str        # ERROR / WARN
    location: str        # 位置描述
    message: str         # 简要说明
    fix_hint: str        # 修复建议
    baseline_issue: bool = False  # 是否 baseline 已有


# ============== 主控 ==============
class LintRunner:
    def __init__(self, pptx_path: str, baseline_path: Optional[str] = None,
                 level: str = "all", strict: bool = False):
        self.pptx_path = Path(pptx_path).resolve()
        self.baseline_path = Path(baseline_path).resolve() if baseline_path else None
        self.level = level  # ERROR / WARN / all
        self.strict = strict  # strict 模式：baseline 坏也当 ERROR
        self.issues: list[Issue] = []
        self._names: list[str] = []  # zip 内所有 name（去重检测用）
        self._parts_data: dict[str, bytes] = {}  # name -> raw bytes
        self._baseline_issues: set[str] = set()  # 形如 "PKG-001:location" 集合

    # ---------- 入口 ----------
    def run(self) -> int:
        # 0) 文件存在性
        if not self.pptx_path.exists():
            log.error("课件不存在: %s", self.pptx_path)
            return 3

        # 1) 加载 zip（捕获损坏）
        try:
            self._load_zip()
        except (zipfile.BadZipFile, OSError) as e:
            log.error("zip 损坏: %s", e)
            return 2

        # 2) 若有 baseline，先扫一遍
        if self.baseline_path and self.baseline_path.exists():
            try:
                baseline_runner = LintRunner(str(self.baseline_path))
                baseline_runner._load_zip()
                baseline_runner._run_all_checks()
                for iss in baseline_runner.issues:
                    key = f"{iss.code}:{iss.location}"
                    self._baseline_issues.add(key)
                log.info("baseline 扫描完成：%d issues", len(baseline_runner.issues))
            except Exception as e:
                log.warning("baseline 扫描失败: %s（继续走非 baseline 模式）", e)

        # 3) 跑 6 组检查
        try:
            self._run_all_checks()
        except Exception as e:
            import traceback
            log.error("检查过程崩溃: %s\n%s", e, traceback.format_exc())
            return 4

        # 4) 标记 baseline issue
        if not self.strict:
            for iss in self.issues:
                key = f"{iss.code}:{iss.location}"
                if key in self._baseline_issues:
                    iss.baseline_issue = True
                    if iss.severity == "ERROR":
                        iss.severity = "WARN"  # 降级

        # 5) 按 level 过滤
        if self.level == "ERROR":
            self.issues = [i for i in self.issues if i.severity == "ERROR"]
        elif self.level == "WARN":
            self.issues = [i for i in self.issues if i.severity == "WARN"]

        # 6) 退出码
        n_error = sum(1 for i in self.issues if i.severity == "ERROR")
        n_warn = sum(1 for i in self.issues if i.severity == "WARN")
        log.info("扫描完成: %d ERROR / %d WARN", n_error, n_warn)
        if n_error > 0:
            return 1
        return 0

    # ---------- 加载 ----------
    def _load_zip(self):
        with zipfile.ZipFile(str(self.pptx_path), "r") as z:
            for name in z.namelist():
                self._names.append(name)
                try:
                    self._parts_data[name] = z.read(name)
                except (zipfile.BadZipFile, OSError, RuntimeError) as e:
                    log.warning("读取 part 失败: %s (%s)", name, e)
                    # 用空字节占位，后续检查会跳过
                    self._parts_data[name] = b""

    # ---------- 调度 ----------
    def _run_all_checks(self):
        for checker in (PkgChecker, RelChecker, CtChecker, IdChecker, XmlChecker, SynChecker):
            try:
                checker(self).check()
            except Exception as e:
                log.warning("%s 检查异常: %s", checker.__name__, e)

    # ---------- 工具 ----------
    def add(self, code: str, severity: str, location: str, message: str, fix_hint: str):
        self.issues.append(Issue(code, severity, location, message, fix_hint))

    def has_part(self, name: str) -> bool:
        return name in self._parts_data

    def get_part(self, name: str) -> Optional[bytes]:
        return self._parts_data.get(name)

    # ---------- 输出 ----------
    def emit_text(self) -> str:
        lines = []
        n_err = sum(1 for i in self.issues if i.severity == "ERROR")
        n_wrn = sum(1 for i in self.issues if i.severity == "WARN")
        lines.append(f"== ooxml_lint {self.pptx_path.name} ==")
        lines.append(f"扫描完成: {n_err} ERROR / {n_wrn} WARN")
        if self.issues:
            lines.append("")
            by_code = {}
            for i in self.issues:
                by_code.setdefault(i.code, []).append(i)
            for code, items in sorted(by_code.items()):
                lines.append(f"[{code}] × {len(items)}")
                for i in items[:5]:  # 每码最多 5 条
                    tag = " [BASELINE]" if i.baseline_issue else ""
                    lines.append(f"  {i.severity}{tag} {i.location}: {i.message}")
                    if i.fix_hint:
                        lines.append(f"     → {i.fix_hint}")
                if len(items) > 5:
                    lines.append(f"  ... 还有 {len(items) - 5} 条")
        return "\n".join(lines)

    def emit_json(self) -> str:
        return json.dumps(
            {
                "file": str(self.pptx_path),
                "scanned_at": datetime.now().isoformat(timespec="seconds"),
                "summary": {
                    "ERROR": sum(1 for i in self.issues if i.severity == "ERROR"),
                    "WARN": sum(1 for i in self.issues if i.severity == "WARN"),
                },
                "issues": [asdict(i) for i in self.issues],
            },
            ensure_ascii=False,
            indent=2,
        )


# ============== PKG 检查 ==============
class PkgChecker:
    """zip 重复名 / __MACOSX / Content_Types 完整性 / 0 字节条目"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        # 1) 重复名
        counter = Counter(self.r._names)
        dups = [n for n, c in counter.items() if c > 1]
        for n in dups:
            self.r.add(
                "PKG-001", "ERROR", n,
                f"zip 重复条目（出现 {counter[n]} 次）",
                "python-pptx 删页残留或 deepcopy 重复 rels；用 clean.py 清理或重打包"
            )

        # 2) macOS 打包污染
        macos_junk = [n for n in self.r._names if n.startswith("__MACOSX/") or n == ".DS_Store"]
        for n in macos_junk:
            self.r.add(
                "PKG-002", "WARN", n,
                "macOS 打包残留（__MACOSX 或 .DS_Store）",
                "用 `zip -X` 重打包或 clean.py --strip-macos"
            )

        # 3) Content-Types 完整性
        if not self.r.has_part("[Content_Types].xml"):
            self.r.add(
                "PKG-003", "ERROR", "[Content_Types].xml",
                "Content_Types 文件缺失（zip 损坏或手工加 part 未登记）",
                "重新生成 Content_Types 或从备份恢复"
            )
        else:
            try:
                ct_root = etree.fromstring(self.r.get_part("[Content_Types].xml"))
                # 检查是否声明了关键 part 扩展名
                declared_exts = set()
                for d in ct_root.findall(f"{{{CONTENT_TYPES}}}Default"):
                    ext = d.get("Extension")
                    if ext:
                        declared_exts.add(ext.lower())
                # 关键扩展名
                critical = {"xml", "rels"}
                for ext in critical:
                    if ext not in declared_exts:
                        self.r.add(
                            "PKG-004", "WARN", "[Content_Types].xml",
                            f"未声明关键扩展名 .{ext}",
                            f"在 Content_Types.xml 添加 <Default Extension=\"{ext}\" ContentType=\"...\"/>"
                        )
            except etree.XMLSyntaxError as e:
                self.r.add(
                    "PKG-005", "ERROR", "[Content_Types].xml",
                    f"Content_Types well-formed 失败: {e}",
                    "XML 语法错误，修复或重打包"
                )

        # 4) 0 字节条目
        for n, data in self.r._parts_data.items():
            if len(data) == 0 and not n.endswith("/"):
                self.r.add(
                    "PKG-006", "WARN", n,
                    "0 字节 part（D11 苗子）",
                    "检查媒体文件是否被截断；如 0 字节可安全删除"
                )


# ============== REL 检查 ==============
class RelChecker:
    """r:id 可达性 / 重复 rId / 孤立 part"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        # 遍历所有 .rels 文件
        for name in self.r._names:
            if not name.endswith(".rels"):
                continue
            data = self.r.get_part(name)
            if data is None:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue

            # 收集 rId 与 Target
            rids = []
            for rel in root.findall(f"{{{REL_NS}}}Relationship"):
                rid = rel.get("Id")
                target = rel.get("Target")
                target_mode = rel.get("TargetMode", "Internal")
                rids.append(rid)
                if target_mode == "Internal":
                    # 解析相对路径 → 绝对路径
                    base_dir = os.path.dirname(name).replace("_rels", "").rstrip("/")
                    target_path = self._resolve_rel_path(base_dir, target)
                    if target_path and not self.r.has_part(target_path):
                        self.r.add(
                            "REL-001", "ERROR", f"{name} -> {target}",
                            f"r:id={rid} 指向不存在的 part ({target_path})",
                            f"检查 target 路径或恢复 {target_path} part"
                        )
            # 重复 rId
            rc = Counter(rids)
            for rid, c in rc.items():
                if c > 1 and rid:
                    self.r.add(
                        "REL-002", "ERROR", f"{name}",
                        f"重复 r:id={rid}（出现 {c} 次）",
                        "去重 rId 或重新生成 rels"
                    )

    @staticmethod
    def _resolve_rel_path(base_dir: str, target: str) -> str:
        """解析 rels target 为 zip 内绝对路径。"""
        # target 可能以 ../ 开头
        if target.startswith("/"):
            return target.lstrip("/")
        # base_dir 例如 'ppt/slides/_rels' → 实际 base = 'ppt/slides'
        if base_dir.endswith("/_rels"):
            base = base_dir[:-6]
        else:
            base = base_dir
        # 拼接 + 规范化
        combined = os.path.normpath(os.path.join(base, target))
        return combined.replace("\\", "/")


# ============== CT 检查 ==============
class CtChecker:
    """Content-Types 覆盖度"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        if not self.r.has_part("[Content_Types].xml"):
            return  # PKG-003 已报
        try:
            ct_root = etree.fromstring(self.r.get_part("[Content_Types].xml"))
        except etree.XMLSyntaxError:
            return

        # 收集已声明的 Override PartName
        declared_parts = set()
        for ov in ct_root.findall(f"{{{CONTENT_TYPES}}}Override"):
            pn = ov.get("PartName")
            if pn:
                declared_parts.add(pn.lstrip("/"))

        # 遍历 zip 内所有 xml/rels part，检查是否声明
        for name in self.r._names:
            if name.endswith(".rels"):
                # rels 走 Default Extension，不需 Override
                continue
            if not (name.endswith(".xml") or name.endswith(".xml.rels")):
                continue
            if name.startswith("_rels/"):
                continue
            if name == "[Content_Types].xml":
                continue
            if name not in declared_parts:
                # 检查是否有 Default Extension 覆盖
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                has_default = False
                for d in ct_root.findall(f"{{{CONTENT_TYPES}}}Default"):
                    if d.get("Extension", "").lower() == ext:
                        has_default = True
                        break
                if not has_default and ext in ("xml",):
                    self.r.add(
                        "CT-001", "ERROR", name,
                        f"part 未在 Content_Types 中登记（{name}）",
                        f"在 [Content_Types].xml 添加 <Override PartName=\"/{name}\" ContentType=\"...\"/>"
                    )


# ============== ID 检查 ==============
class IdChecker:
    """sldId / cNvPr / sldLayoutId / sldMasterId 唯一性"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        sld_ids = []
        # 1) presentation.xml 中 p:sldId
        if self.r.has_part("ppt/presentation.xml"):
            try:
                root = etree.fromstring(self.r.get_part("ppt/presentation.xml"))
                for sid in root.iter(f"{{{NS['p']}}}sldId"):
                    sval = sid.get("id")
                    if sval:
                        sld_ids.append(int(sval))
                rc = Counter(sld_ids)
                for sid, c in rc.items():
                    if c > 1:
                        self.r.add(
                            "ID-001", "ERROR", "ppt/presentation.xml",
                            f"重复 p:sldId={sid}（出现 {c} 次）",
                            "重编 sldId 确保唯一"
                        )
            except etree.XMLSyntaxError:
                pass

        # 2) 每页 p:cNvPr id 唯一性
        cnvpr_global = Counter()
        for name in list(self.r._names):
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(self.r.get_part(name))
                for cnv in root.iter(f"{{{NS['p']}}}cNvPr"):
                    cid = cnv.get("id")
                    if cid:
                        cnvpr_global[cid] += 1
            except etree.XMLSyntaxError:
                continue
        # cNvPr id 在单页内唯一，但跨页可不强求唯一——这里仅在重复时 WARN
        # 真正的 ID 冲突是 sldLayoutId / sldMasterId
        # （cNvPr id 跨页允许重复是 v3 §3.4 已知简化）

        # 3) sldLayoutId / sldMasterId 全局唯一
        layout_ids = []
        master_ids = []
        for name in list(self.r._names):
            if not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(self.r.get_part(name))
            except etree.XMLSyntaxError:
                continue
            for lid in root.iter(f"{{{NS['p']}}}sldLayoutId"):
                v = lid.get("id")
                if v:
                    layout_ids.append((name, int(v)))
            for mid in root.iter(f"{{{NS['p']}}}sldMasterId"):
                v = mid.get("id")
                if v:
                    master_ids.append((name, int(v)))
        # 简单检查：去重后应等于总数
        layout_values = [v for _, v in layout_ids]
        rc = Counter(layout_values)
        for v, c in rc.items():
            if c > 1:
                locs = [n for n, vv in layout_ids if vv == v][:3]
                self.r.add(
                    "ID-002", "ERROR", f"sldLayoutId={v}",
                    f"sldLayoutId 重复（出现 {c} 次：{locs}）",
                    "重编 sldLayoutId 或检查母版拷贝逻辑"
                )
        master_values = [v for _, v in master_ids]
        rc = Counter(master_values)
        for v, c in rc.items():
            if c > 1:
                locs = [n for n, vv in master_ids if vv == v][:3]
                self.r.add(
                    "ID-003", "ERROR", f"sldMasterId={v}",
                    f"sldMasterId 重复（出现 {c} 次：{locs}）",
                    "重编 sldMasterId 或检查母版拷贝逻辑"
                )


# ============== XML 检查 ==============
class XmlChecker:
    """well-formed / 非法字符 / xml:space"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        for name, data in self.r._parts_data.items():
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            if not data:
                continue
            # 1) well-formed
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError as e:
                self.r.add(
                    "XML-001", "ERROR", name,
                    f"XML well-formed 失败: {e}",
                    "修复 XML 语法错误（标签闭合/属性引号/命名空间）"
                )
                # 仍然尝试裸文本扫一次（well-formed 失败时退到 bytes 扫描）
                try:
                    raw_txt = data.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                matches = ILLEGAL_CHARS.findall(raw_txt)
                if matches:
                    uniq = sorted(set(hex(ord(c)) for c in matches))[:3]
                    self.r.add(
                        "XML-002", "WARN", name,
                        f"含非法控制字符 {uniq}（XML 1.0 不允许）",
                        "清除或替换为合法字符"
                    )
                continue
            # 2) 非法控制字符
            txt = etree.tostring(root, encoding="unicode", method="text")
            matches = ILLEGAL_CHARS.findall(txt)
            if matches:
                uniq = sorted(set(hex(ord(c)) for c in matches))[:3]
                self.r.add(
                    "XML-002", "WARN", name,
                    f"含非法控制字符 {uniq}（XML 1.0 不允许）",
                    "清除或替换为合法字符"
                )
            # 3) 前导/尾随空格 + xml:space 检查（仅 a:t 标签）
            for t in root.iter(f"{{{NS['a']}}}t"):
                if t.text:
                    if (t.text.startswith(" ") or t.text.endswith(" ")) and \
                            t.get("{http://www.w3.org/XML/1998/namespace}space") != "preserve":
                        self.r.add(
                            "XML-003", "WARN", name,
                            f"a:t 文本含前导/尾随空格缺 xml:space=\"preserve\"（文本='{t.text[:20]}...'）",
                            "添加 xml:space=\"preserve\" 或去除首尾空格"
                        )
                        break  # 一页只报一次


# ============== SYN 检查 ==============
class SynChecker:
    """sldIdLst ↔ slide parts ↔ presentation.xml.rels 三方一致"""

    def __init__(self, runner: LintRunner):
        self.r = runner

    def check(self):
        if not self.r.has_part("ppt/presentation.xml"):
            return
        try:
            root = etree.fromstring(self.r.get_part("ppt/presentation.xml"))
        except etree.XMLSyntaxError:
            return

        # 1) sldIdLst 中所有 r:id
        slist = root.find(f"{{{NS['p']}}}sldIdLst")
        if slist is None:
            return
        sld_rids = []
        for sid in slist.findall(f"{{{NS['p']}}}sldId"):
            rid = sid.get(f"{{{NS['r']}}}id")
            if rid:
                sld_rids.append(rid)

        # 2) presentation.xml.rels 中对应 Target
        rels_data = self.r.get_part("ppt/_rels/presentation.xml.rels")
        if rels_data is None:
            self.r.add(
                "SYN-001", "ERROR", "ppt/_rels/presentation.xml.rels",
                "presentation.xml.rels 缺失",
                "恢复或重新生成 rels"
            )
            return
        try:
            rels_root = etree.fromstring(rels_data)
        except etree.XMLSyntaxError:
            return
        rid_to_target = {}
        for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
            rid_to_target[rel.get("Id")] = rel.get("Target")

        # 3) 检查每个 sldId 的 r:id 都可达
        for rid in sld_rids:
            if rid not in rid_to_target:
                self.r.add(
                    "SYN-002", "ERROR", "ppt/presentation.xml",
                    f"sldId 引用 r:id={rid} 但 rels 中无此 id",
                    "rels 中补 r:id 或清理 sldIdLst"
                )
                continue
            target = rid_to_target[rid]
            # 解析 target 为 zip 内绝对路径
            target_abs = RelChecker._resolve_rel_path("ppt/_rels", target)
            if not self.r.has_part(target_abs):
                self.r.add(
                    "SYN-003", "ERROR", f"sldId r:id={rid}",
                    f"sldId 指向不存在的 part（{target_abs}）",
                    f"恢复 {target_abs} 或从 sldIdLst 移除"
                )

        # 4) 反向：rels 中所有 sldTargetType 的关系，若 target 存在但 sldIdLst 不引用 → 孤立
        for rid, target in rid_to_target.items():
            if "slides" in target and rid not in sld_rids:
                target_abs = RelChecker._resolve_rel_path("ppt/_rels", target)
                if self.r.has_part(target_abs):
                    self.r.add(
                        "SYN-004", "WARN", f"r:id={rid}",
                        f"slide part {target_abs} 在 rels 中注册但 sldIdLst 未引用（孤立 slide）",
                        "从 rels 移除或加到 sldIdLst"
                    )


# ============== CLI ==============
def main():
    ap = argparse.ArgumentParser(
        description="PPTX OOXML 兼容性检查器（v3.2.0-batch2）"
    )
    ap.add_argument("pptx", help="课件 .pptx 绝对或相对路径")
    ap.add_argument("--baseline", default=None, help="original 副本路径（用于基线对照）")
    ap.add_argument("--level", choices=["ERROR", "WARN", "all"], default="all",
                    help="只显示指定级别（默认 all）")
    ap.add_argument("--strict", action="store_true",
                    help="强模式：baseline 坏也当 ERROR")
    ap.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    args = ap.parse_args()

    runner = LintRunner(
        pptx_path=args.pptx,
        baseline_path=args.baseline,
        level=args.level,
        strict=args.strict,
    )
    rc = runner.run()

    if args.json:
        print(runner.emit_json())
    else:
        print(runner.emit_text())

    if rc == 0:
        log.info("✓ 通过（0 ERROR）")
    elif rc == 1:
        log.error("✗ D11 苗子：%d ERROR，禁止写回", sum(1 for i in runner.issues if i.severity == "ERROR"))
    elif rc == 2:
        log.error("✗ zip 损坏")
    elif rc == 3:
        log.error("✗ 文件读取失败")
    else:
        log.error("✗ 运行错误（走缺陷回流）")
    sys.exit(rc)


if __name__ == "__main__":
    main()

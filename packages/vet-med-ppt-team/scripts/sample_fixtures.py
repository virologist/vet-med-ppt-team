#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sample_fixtures.py — 外部课件样本的**可解析定位**层（v3.24.0）

背景（FEAT-20261023-003c 的根因取证）：
  `test_ooxml_lint.py::T1/T11` 与 `test_extract_assets.py::T6` 长期依赖**包外**课件：
    - `养禽与禽病防治/.harness-runs/M4-M7_重诊断/sample_extract/*.pptx`（该目录**已不存在**）
    - `/tmp/cross_domain/cdc_zoonotic_diseases.pptx`（`/tmp` **不持久** ⇒ 从未真跑）
  ⇒ 3 条用例在本机**从未执行过**，其正确性无本地证据（登记见 `.learnings/FEATURE_REQUESTS.md`）。

  实测（v3.24.0 取证）：4 份动医真实课件现位于
  `养禽与禽病防治/M4A1_禽流感/`，实测 `ooxml_lint` 全部 **rc=0**（0 ERROR），
  ⇒ T1 的断言本身成立；**失效的是路径，不是断言**。

设计原则（与本包既有纪律同源）：
  1. **不许把 skip 换个名字**——包外样本是**加分项**，不是**正确性的前提**。
     ⇒ 真实样本可得 ⇒ 用真实样本（证据强度最高）；不可得 ⇒ 用**确定性合成 fixture**
       顶上，断言仍然真跑。**skip 只保留在"合成 fixture 也构造不出来"的极端情形**。
  2. **路径不硬编码单点**——多候选目录 + 环境变量覆盖（`VETMED_SAMPLE_DIR` 等），
     样本搬家/换机不致再次静默 skip。
  3. **不静默降级**——每次降级都**显式登记**降级类型（`real` / `synthetic`），
     由调用方打印，禁"悄悄用弱样本假装测过真样本"。

对外 API：
  resolve_real_samples(...)  -> (list[Path], source_desc)   仅真实样本，不足即返回空
  resolve_samples(...)       -> (list[Path], source_desc)   真实优先，不足补合成
  build_synthetic_deck(...)  -> Path                       确定性合成课件
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# ── 真实样本候选目录（按优先级；每个候选下按文件名 glob 匹配）──
# ⚠ 只读：这些目录属用户工作区，本模块**只读不写**。
#   顺序即优先级：环境变量 > 挂账抽取目录 > 源课件目录。
_WORKSPACE_ROOT = Path(
    "/Users/biodog/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治"
)

#: 候选源：(目录, 文件名 glob 列表, 用途标签)
_SAMPLE_SOURCES: List[Tuple[Path, Tuple[str, ...], str]] = [
    # ① 挂账抽取目录（v3.2.0-batch2 时的原始位置；若被清理则自动落到 ②）
    (
        _WORKSPACE_ROOT / ".harness-runs" / "M4-M7_重诊断" / "sample_extract",
        ("*.pptx",),
        "挂账抽取目录",
    ),
    # ② 源课件目录（**v3.24.0 取证发现的真实位置**）
    #    ⚠ 文件名随用户整理会变，故用多个 glob 兜底（`2.1高致病性…` / `高致病性…` 两种都收）
    (
        _WORKSPACE_ROOT / "M4A1_禽流感",
        (
            "高致病性禽流感防控.pptx",
            "2.1高致病性禽流感防控.pptx",
            "7. 禽流感.pptx",
            "禽流感病毒全链攻防术.pptx",
            "禽流感鉴别诊疗要点.pptx",
        ),
        "源课件目录(M4A1_禽流感)",
    ),
]

#: 环境变量覆盖（换机/自定义样本库时用）
_ENV_SAMPLE_DIR = "VETMED_SAMPLE_DIR"
#: **强制合成**自检开关：置 1 ⇒ 忽略一切真实样本，强制走合成 fixture 分支。
#    用途：验证降级路径本身可跑通（否则降级分支永远没被执行过 = 未验证代码）。
_ENV_FORCE_SYNTH = "VETMED_FORCE_SYNTHETIC"
#: 跨学科样本（v4 通用化用）——**刻意不自动下载**：测试依赖网络会让 CI 不确定。
#    提供方可下载后置于该目录，或设 `VETMED_CROSS_DOMAIN_DIR`。
_ENV_CROSS_DIR = "VETMED_CROSS_DOMAIN_DIR"
_CROSS_DIR_DEFAULT = Path("/tmp/cross_domain")
_CROSS_FILENAME = "cdc_zoonotic_diseases.pptx"


def force_synthetic() -> bool:
    """是否强制走合成 fixture 分支（自检用）。"""
    return os.environ.get(_ENV_FORCE_SYNTH, "").strip() in ("1", "true", "yes")


def _env_dir(key: str) -> Optional[Path]:
    """读取环境变量指定的目录；未设置或为空 ⇒ None。"""
    raw = os.environ.get(key, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_real_samples(minimum: int = 1) -> Tuple[List[Path], str]:
    """定位**真实**外部课件样本。

    返回 (样本列表, 来源描述)。样本不足 ``minimum`` 时返回空列表——
    调用方据此决定是否降级到合成 fixture（**不静默**）。

    候选顺序：环境变量目录 → 挂账抽取目录 → 源课件目录。

    ⚠ 强制合成自检（`VETMED_FORCE_SYNTHETIC=1`）⇒ 直接返回空列表。
    """
    if force_synthetic():
        return [], "强制合成模式(VETMED_FORCE_SYNTHETIC=1)"
    found: List[Path] = []
    origins: List[str] = []

    # ① 环境变量优先（用户显式指定，最高优先级）
    env_dir = _env_dir(_ENV_SAMPLE_DIR)
    if env_dir and env_dir.is_dir():
        hits = sorted(env_dir.glob("*.pptx"))
        if hits:
            found.extend(hits)
            origins.append(f"环境变量 {_ENV_SAMPLE_DIR}={env_dir}")

    # ② 挂账抽取目录 → ③ 源课件目录
    for base, globs, label in _SAMPLE_SOURCES:
        if not base.is_dir():
            continue
        hits: List[Path] = []
        for g in globs:
            hits.extend(base.glob(g))
        # 去重（同一文件可能被多个 glob 命中）并保持稳定顺序
        uniq = sorted({p.resolve() for p in hits})
        if uniq:
            found.extend(uniq)
            origins.append(f"{label}({len(uniq)}份)")

    # 全局去重（不同候选目录可能指向同一文件）
    deduped: List[Path] = []
    seen = set()
    for p in found:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    desc = " + ".join(origins) if origins else "无可用真实样本"
    if len(deduped) < minimum:
        return [], desc
    return deduped, desc


def resolve_cross_domain_sample() -> Tuple[Optional[Path], str]:
    """定位跨学科样本（T11 通用化验证用）。

    返回 (路径, 描述)；不存在 ⇒ (None, 描述)。
    ⚠ **不自动下载**：网络依赖会让测试结果不确定；缺失时由调用方降级。
    ⚠ 强制合成自检（`VETMED_FORCE_SYNTHETIC=1`）⇒ 一律视为缺失。
    """
    if force_synthetic():
        return None, "强制合成模式(VETMED_FORCE_SYNTHETIC=1)"
    d = _env_dir(_ENV_CROSS_DIR) or _CROSS_DIR_DEFAULT
    p = d / _CROSS_FILENAME
    if p.is_file():
        return p, f"跨学科样本({p})"
    return None, f"跨学科样本缺失({p}；设 {_ENV_CROSS_DIR} 可覆盖)"


# ── 确定性合成 fixture ────────────────────────────────────────
def build_synthetic_deck(path: Path, *, slides: int = 3, with_text: bool = True,
                         with_image: bool = False) -> Path:
    """构造一份**确定性**的最小合法 PPTX（OOXML 合规 ⇒ lint 0 ERROR）。

    用途：外部样本不可得时，让"跑得通"这件事仍被**真实执行**而非 skip。
    参数默认值取最小可用集，保证生成结果稳定可复现。
    """
    from pptx import Presentation
    from pptx.util import Inches, Pt

    path.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    for i in range(max(1, slides)):
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式
        tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
        tf = tb.text_frame
        tf.text = f"合成样本 第{i + 1}页" if with_text else f"Synthetic page {i + 1}"
        for para in tf.paragraphs:
            for run in para.runs:
                run.font.size = Pt(14)
        if with_image:
            from PIL import Image  # 仅在需要图片时导入（可选依赖）
            img_path = path.parent / f"_synth_{i}.png"
            Image.new("RGB", (8, 8), (200, 200, 200)).save(img_path)
            slide.shapes.add_picture(str(img_path), Inches(1), Inches(3),
                                     width=Inches(1), height=Inches(1))
            img_path.unlink(missing_ok=True)
    prs.save(str(path))
    return path


def build_synthetic_suite(dest_dir: Optional[Path] = None, count: int = 4) -> List[Path]:
    """构造 ``count`` 份确定性合成课件（模拟"多份真实样本"场景）。"""
    d = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="vetmed_synth_"))
    d.mkdir(parents=True, exist_ok=True)
    decks: List[Path] = []
    for i in range(max(1, count)):
        p = d / f"synth_sample_{i + 1}.pptx"
        build_synthetic_deck(p, slides=2 + i)
        decks.append(p)
    return decks


if __name__ == "__main__":  # pragma: no cover - 人工排查用
    real, desc = resolve_real_samples()
    print(f"真实样本：{len(real)} 份 — {desc}")
    for p in real:
        print(f"  · {p}")
    cd, cdesc = resolve_cross_domain_sample()
    print(f"跨学科样本：{cd or '（缺失）'} — {cdesc}")

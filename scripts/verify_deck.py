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
  7. 课时匹配      —— 页数 vs 课时标准（双口径，--caliber）      [P0]
  8. 结构性完备    —— 目录页/题页 [P0]；备注覆盖率 [P2]
  9. 主框密度      —— 单页主框正文字符超限（标题/图注/页脚不计）[P1]  ★v3.16.0 新增（机器判定）
 10. rubric 建议级 —— V1 标题位置一致性 / V5 图文比例【默认关闭，不计门禁】★v3.16.0 新增（机器判定）

分级门禁（v2.0.0，防"全清不可达→门禁必被绕过"）：
  P0 硬阻断：写回磁盘前必须为 0（任何 level 下都阻断）
  P1 必清  ：允许中途写盘（须带修复计划），交付前必须为 0
  P2 指标  ：备注覆盖率 ≥ gate.p2_note_coverage（默认 80%），交付级阻断
  P3 明示  ：继承字号未取到 / 判定异常 / 装饰出血——不阻断，必须明示

用法：
  python3 verify_deck.py <课件.pptx> --hours 3 [--caliber course|single-ppt] \
                         [--level P0|P1|all] [--json out.json] [--strict]

  --hours     课时数（必填：1 / 1.5 / 2 / 3 / 4）
  --caliber   页数口径（v3.16.0）：
                course     = 整套课程课件口径（hours_page_range，默认，见 yaml page_caliber_default）
                single-ppt = 单次 PPT 口径（hours_page_range_single_ppt，
                             数值同源 references/course-profile-defaults.md#2）
              不加 --caliber 时结果与 v3.16.0 之前完全一致（历史复验不受影响）。

  --level P0   写回门禁：仅 P0 阻断
  --level P1   中检门禁：P0+P1 阻断
  --level all  交付门禁（默认）：P0+P1+P2(覆盖率) 阻断

退出码：0=通过(所请求 level) / 1=P0阻断 / 2=P1阻断 / 3=P2阻断 / 4=运行错误
v2.0.0 起：单页/单形状解析异常不再崩溃退出（XML 兜底继续判，异常计入 P3 明示）。

依赖：pip install python-pptx pyyaml
"""

import argparse
import json
import re
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

# v3.16.0：**下面每个键都必须与 config/visual-rules.yaml 逐项一致**
# （由 ensure_settings.py 第 19 项 check_fallback_drift() 强制；只改 yaml 不改这里 = 体检报错）。
_FALLBACK = {
    "body_min_pt": 12.0,
    "note_min_pt": 9.0,
    "title_min_pt": 28.0,
    # v3.21.0（维度 6/8 实测）：页脚/页码档——页脚 8pt 是合规设计，
    #   原先无此档 ⇒ 被按 body_min_pt 判「字号过小」且 severity 映射为 P0 硬阻断
    #   ⇒ 合规课件凭空造 P0。**不放宽密度检查的页脚判据**（那会放松既有判据）。
    "footer_min_pt": 8.0,
    "footer_max_chars": 40,
    "max_colors_per_slide": 5,
    "max_chars_per_slide": 400,
    "max_body_chars_per_slide": 150,      # v3.16.0：主框密度（v3.5.0 起配了一直没人读，本版 wiring）
    "overlap_ratio": 0.15,
    "hours_page_range": {
        1: (18, 28),
        1.5: (35, 50),
        2: (36, 52),
        3: (55, 78),
        4: (72, 104),
    },
    # v3.16.0：口径 B「单次 PPT」，同源 course-profile-defaults.md#2（详见 yaml 注释）
    "hours_page_range_single_ppt": {
        1: (12, 18),
        2: (22, 32),
        3: (32, 45),
        4: (42, 58),
    },
    "page_caliber_default": "course",
    "p2_note_coverage": 0.80,
    "severity": {
        "P0": ["字号过小", "文字越界", "配色混乱", "空白页", "课时不达标", "缺目录页", "缺题页"],
        "P1": ["元素重叠", "文字墙", "主框密度超标"],
        "P2": ["缺备注"],
    },
    # v3.16.0：建议级检查（rubric）默认值——与 yaml 的 checks 段同源，仅在 yaml 缺失时兜底
    "checks": {
        "title_position_consistency": {"enabled": False, "tolerance_in": 0.25},
        "image_area_ratio": {"enabled": False, "min": 0.20, "max": 0.50,
                             "max_consecutive_textonly": 3},
        "key_data_source": {"enabled": False, "scope": "paragraph_then_page"},
    },
}

_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "config", "visual-rules.yaml")

def _hpr_table(raw):
    """把 yaml 的 `{1: [18, 28], ...}` 规整为 `{float(课时): (下限, 上限)}`。

    v3.16.0：双口径页数表各自规整一次，互不覆盖。
    raw 为空或结构异常时返回空表——缺档/空表由调用方按 `.get(hours, (0, 9999))` 处理，
    与历史行为一致（不阻断）。
    """
    out = {}
    try:
        for k, v in (raw or {}).items():
            out[float(k)] = tuple(v)
    except Exception:
        return {}
    return out


CALIBER_COURSE = "course"           # 口径 A：整套课程课件（历史默认口径）
CALIBER_SINGLE_PPT = "single-ppt"   # 口径 B：单次 PPT（course-profile-defaults.md#2）
CALIBERS = (CALIBER_COURSE, CALIBER_SINGLE_PPT)


def _resolve_caliber(caliber=None):
    """确定页数口径：显式入参优先，否则取 yaml `page_caliber_default`（再否则 "course"）。

    ⚠️ **默认恒为 `course`（口径 A）**——这是 v3.16.0 的硬承诺：
    不加 `--caliber` 跑任何历史课件，页数判定结果必须与 v3.16.0 之前**逐字节一致**。
    默认口径不随使用场景"智能"切换：规则引擎猜场景 = 同一份文件可能给出不同结论，
    历史复验不可复现。场景差异只能由调用方显式声明。
    （该承诺由 scripts/test_verify_deck.py 的 T_default_caliber 单测守着。）
    """
    if caliber in CALIBERS:
        return caliber
    d = THRESHOLD.get("page_caliber_default") if isinstance(THRESHOLD, dict) else None
    return d if d in CALIBERS else CALIBER_COURSE


def _load_threshold():
    """优先读 config/visual-rules.yaml；失败回退内置值并告警（不中断裁判）。

    v3.16.0：页数标准一次性加载**两张表**（口径 A/B），并存互不覆盖；
    运行时由 caliber 决定用哪张（见 `_resolve_caliber` 的注释）。
    """
    try:
        import yaml
        with open(_RULES_PATH, encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        hpr = _hpr_table(rules["hours_page_range"])
        hpr_single = _hpr_table(rules.get("hours_page_range_single_ppt"))
        th = {
            "body_min_pt": float(rules["font"]["body_min_pt"]),
            "note_min_pt": float(rules["font"]["note_min_pt"]),
            # v3.19.0：title_min_pt **首次接线**（此前 yaml 配了 28.0 但零消费者——
            #   死配置；而屠明熙 MD:35 早已把它当红线写 ⇒ "文档当红线、机器不设防"）
            "title_min_pt": float(rules["font"].get("title_min_pt", 28.0)),
            "max_colors_per_slide": int(rules["density"]["max_colors_per_slide"]),
            "max_chars_per_slide": int(rules["density"]["max_chars_per_slide"]),
            # v3.16.0：主框密度终于有代码读取者了（此前 yaml 配了 150 但无人消费）
            "max_body_chars_per_slide": int(rules["density"]["max_body_chars_per_slide"]),
            "overlap_ratio": float(rules["geometry"]["overlap_ratio"]),
            "hours_page_range": hpr,                              # 口径 A
            "hours_page_range_single_ppt": hpr_single,            # 口径 B（v3.16.0）
            "page_caliber_default": str(rules.get("page_caliber_default", "course")),
            "p2_note_coverage": 0.80,
            "severity": dict(_FALLBACK["severity"]),
            # v3.16.0：建议级（rubric）检查开关，缺省用内置值（默认全关）
            "checks": {k: dict(v) for k, v in _FALLBACK["checks"].items()},
            # v3.22.0 G2：图表布局规范（**独立顶层段**，不进 checks ⇒ 不进第 19 项核对清单）
            "chart": dict(rules.get("chart") or {}) if isinstance(rules.get("chart"), dict) else {},
        }
        gate = rules.get("gate") or {}
        if "p2_note_coverage" in gate:
            th["p2_note_coverage"] = float(gate["p2_note_coverage"])
        sev = rules.get("severity") or {}
        for lv in ("P0", "P1", "P2"):
            if lv in sev:
                th["severity"][lv] = list(sev[lv])
        ck = rules.get("checks") or {}
        for cid, cfg in ck.items():
            if isinstance(cfg, dict):
                th["checks"][cid] = dict(cfg)
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

# v3.12.0：闸4.5 三源核验阈值改为读配置（此前三处硬编码 0.8/0.1）。
# 根因：harness.yaml#budgets 与 domain_config.yaml#three_source_check 都配了同值，
# 但代码从不读——"唯一数据源"纪律形同虚设，任一方单独调参会静默失效。
# v3.17.0：本段扩为**三档判定配置**的读取入口，且实现**下沉到 harness.py**
#   （唯一读取实现点，避免同一份 yaml 被两个脚本各读一遍、各维护一份兜底）。
# 依赖方向：verify_deck → harness（单向）。harness 从不 import verify_deck，
#   两者**无循环依赖**；且方向不可反——verify_deck 依赖 python-pptx，
#   让编排内核反向依赖裁判会把重依赖倒灌进 harness。
_DOMAIN_CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "config", "domain_config.yaml")


def _load_three_source_kernel():
    """惰性加载 scripts/harness.py 的三源核验内核（导入期不耦合）。

    为什么惰性：harness.py 模块级只做常量定义与函数定义（CLI 在 __main__ 守卫后），
    但仍**不在导入期**建立依赖——裁判脚本被当库导入时（如 pytest）不应连带拉起编排内核。
    加载失败必须**显式报错**（不得静默跳过实查），由调用方决定 fail-closed。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import harness  # noqa: E402  （惰性导入：见上方说明）
    return harness


def _load_three_source_thresholds():
    """读 domain_config.yaml#three_source_check **全段**（抽检率 + 通过率 + 三档判定配置）。

    失败策略与 _load_threshold 一致但更宽松：这里缺值**不阻断**整轮门禁
    （三源核验只是闸4.5 的一个子项），退回内置值并**显式告警**——
    静默回退才是这里要防的（否则改配置的人看不出没生效）。
    v3.17.0：实现下沉到 harness.py#load_three_source_config()（唯一读取实现点）；
    本函数保留旧名与旧键（sample_rate / pass_threshold 语义不变），仅**扩键**。
    """
    fallback = {"sample_rate": 0.1, "pass_threshold": 0.8}
    try:
        kernel = _load_three_source_kernel()
        cfg = kernel.load_three_source_config()
        return cfg
    except Exception as e:
        print(f"⚠ 三源核验内核加载失败（{e}），退回内置 0.1/0.8——"
              f"改配置不会生效，且实查能力不可用（本次判定将 fail-closed）", file=sys.stderr)
        return dict(fallback)


THREE_SOURCE = _load_three_source_thresholds()

# v3.0.0：机器草稿标记（与 inject_notes.py 注入的标记一致）。
# 裁决④：机器草稿**计入** P2 覆盖率，但必须单独统计占比并在交付物明示。
_MACHINE_NOTE_MARK = "AI草稿"

# 问题类型 → 分级（从 yaml severity 反转生成）
_TYPE_LEVEL = {}
for _lv in ("P0", "P1", "P2"):
    for _t in THRESHOLD["severity"].get(_lv, []):
        _TYPE_LEVEL[_t] = _lv

# v3.16.0：未登记类型的默认等级 = None（不落任何级别），此前是 "P0"。
# 改因：新增问题类型时若忘记登记 severity，旧默认值会把它算成 P0 硬阻断——
#   表面"门禁很严"，实际是**类别错误**：未知类别的严重性是未知的，默认判最严没有任何依据，
#   且会让新检查在标定期间就把课件拦死（进而诱导绕过门禁）。
# 现状核查：本文件的 red 键全部已在 yaml severity 中登记（由单测 T_red_keys_in_severity 守着），
#   故**本次改动不改变任何现有问题的分级结果**，只影响未来新增键。
# 未知类型不会静默消失：计入 gate["p3"]（明示）并在 stats["unknown_red_keys"] 列出，
#   由体检第 19 项 + 单测双保险推动"要么登记、要么删除"。
_UNKNOWN_LEVEL = None

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


def _shape_run_pairs(shape, slide):
    """v3.5.1：run 级 (文本, 字号) 配对；空 run 单列，判定时跳过。

    背景（迭代四原则④「检出≠判定」）：旧判据取 min(形状内所有 run 字号)
    与正文阈值比较，产生两类系统性误报——
      ① 空 run（无文本、投影不可见）的残留 sz 参与取 min，凭空造出 P0；
      ② 同形状内 9pt 图注/来源与 12pt 正文混排时，min=9 把整框判成"正文过小"。
    本函数把粒度降到 run，判据即可按 run 文本与用途分别取阈值。
    返回 (pairs, empty_runs)；pairs = [(text, pt_or_None), ...]
    """
    pairs = []
    empty = 0
    if not shape.has_text_frame:
        return pairs, empty
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            txt = (run.text or "").strip()
            try:
                pt = _resolve_run_sz(para, run, shape, slide)
            except Exception:
                pt = None
            if not txt:
                empty += 1
                continue
            pairs.append((txt, pt))
    return pairs, empty


def _is_note_candidate(text):
    """图注/来源判定：命中来源语义关键词 + 长度不超过图注上限 → 按低阈值。

    v3.5.1（迭代四原则④「检出≠判定」实证修正）：旧判据 `len(text) <= 40`
    过窄，把 48 字的"（资料截至 …；来源：WHO/WOAH/…）"这类合规来源注
    误判为"正文字号过小"，单份课件凭空造出 32 条 P0。
    新判据改为语义优先：必须命中来源/图注关键词，且长度 ≤80（图注上限）。
    纯正文不含关键词 → 永不降级；含"来源"的超长正文（>80）→ 仍按正文判定。
    """
    keys = ("来源", "Source", "图注", "PMC", "CC-BY", "参考文献", "数据来", "引自", "http")
    if not any(k in text for k in keys):
        return False
    return len(text) <= 80


# ── 主框密度（v3.16.0）：把 density.max_body_chars_per_slide 接到 statutory机器上 ──
# 为什么需要单独一个口径：全页口径（max_chars_per_slide=400）会把标题/图注/页码一起算进"信息量"，
# 而学生真正要读的是**主框正文**。历史上 yaml 早在 v3.5.0 就配了 150，
# 但**没有任何代码读取它**——"设计期承诺"没有机器兜底，密到无可救药才被迫瘦身（v3.5.0 事故）。
# 下面的判定全部是**确定性规则**（占位符类型 / 几何位置 / 关键词），不含任何语义猜测。

def _shape_is_title_ph(shape):
    """该形状是否为标题占位符（TITLE / CENTER_TITLE）——主框密度要排除它。"""
    try:
        if not shape.is_placeholder:
            return False
        from pptx.enum.shapes import PP_PLACEHOLDER
        return shape.placeholder_format.type in (PP_PLACEHOLDER.TITLE,
                                                 PP_PLACEHOLDER.CENTER_TITLE)
    except Exception:
        return False


def _xml_is_title_ph(elm):
    """XML 兜底路径：p:sp/p:nvSpPr/p:nvPr/p:ph@type ∈ {title, ctrTitle}。"""
    try:
        ph = elm.find(".//" + qn("p:nvSpPr") + "/" + qn("p:nvPr") + "/" + qn("p:ph"))
        if ph is None:
            return False
        return (ph.get("type") or "") in ("title", "ctrTitle")
    except Exception:
        return False


def _is_footer_frame(text, rect, slide_height):
    """页脚/页码框判定：top ≥ 0.92×页高 **且** 文本 ≤20 字。

    两个条件必须同时满足，缺一不可判为页脚：
      · 只看位置 → 真页脚之外的底部正文引文会被误排除；
      · 只看字数 → 正文里的短引导语会被误排除。
    20 字上限对应"第 N 页""1 / 24""课程名·章节"这类页脚语义的长度上限。
    """
    if rect is None or not text:
        return False
    top = rect[1]
    if slide_height and top is not None and top >= 0.92 * slide_height:
        return len(text) <= 20
    return False


def _is_footer_frame_for_font(text, rect, slide_height, max_chars):
    """**字号检查专用**的页脚判定（v3.21.0）。

    为什么要有独立的一份（不直接复用 `_is_footer_frame`）：
      · `_is_footer_frame` 的 20 字上限是**密度检查**的判据——放宽它 = 放松既有判据
        （本包铁律：既有限度不得放弱）⇒ 一个字都不改；
      · 字号检查需要覆盖"课程名·专业名 + 页码"这类**长页脚**（实测 24 字），
        20 字放不下 ⇒ 用**可配的** footer_max_chars（默认 40）。
      · 位置条件与密度检查一致（top ≥ 0.92×页高）：只看长度会把正文里的短引导语误当页脚。
    位置与长度**双条件**，缺一不可判为页脚。
    """
    if rect is None or not text:
        return False
    top = rect[1]
    if slide_height and top is not None and top >= 0.92 * slide_height:
        return len(text) <= max_chars
    return False


def body_frame_chars(adapters, slide_height):
    """按上述三条排除规则累计主框正文字符数，并返回参与计数的框数（供详情给出依据）。

    计数单位为**文本框架的原始字符数**（含段落间的换行符）——刻意取最严口径：
    多项目符号的主框会多算 (段落数-1) 个字符。想"更准"就得剔除换行，那是放松判据，
    与"既有限度不得放弱"冲突，故保留原始口径并在此明示，免得后人当作 bug 修掉。

    Args:
        adapters: 本页形状适配器列表
        slide_height: 页高（EMU），用于页脚判定；取不到时传 None（页脚判定自动不成立）
    """
    total, n = 0, 0
    for a in adapters:
        if not a.get("has_tf") or not a.get("text"):
            continue
        if a.get("is_title_ph"):
            continue                                   # ① 排除标题占位符
        if _is_note_candidate(a["text"]):
            continue                                   # ② 排除图注/来源（复用既有判据）
        if _is_footer_frame(a["text"], a.get("rect"), slide_height):
            continue                                   # ③ 排除页脚/页码框
        total += len(a["text"])
        n += 1
    return total, n


def _chart_rules():
    """读 config/visual-rules.yaml#chart（v3.22.0 G2）。

    缺口背景（第二轮独立诊断 P2）：此前 visual-rules.yaml 无 chart 段、verify_deck
    无图表检查 ⇒ 维度 6「图表布局规范」在配置/门禁/量规三层皆缺。
    ⚠ 缺配置 ⇒ 回落内置默认并**显式告警**（本包铁律：静默回落 = 不设防）。
    """
    node = THRESHOLD.get("chart") or {}
    if not isinstance(node, dict) or not node:
        print("⚠ config/visual-rules.yaml#chart 缺失或为空 → 图表检查按内置默认"
              "（enabled=false / 占比 0.15–0.60）处理", file=sys.stderr)
        return {"enabled": False, "area_ratio": {"min": 0.15, "max": 0.60}}
    ar = node.get("area_ratio") if isinstance(node.get("area_ratio"), dict) else {}
    # v3.23.1 W1：新增两项判据（axis_label_min_pt / legend_required）——
    #   均为建议级（未登记 severity ⇒ 落 unknown_out 明示不阻断）；
    #   axis_label_min_pt 缺省 = 不判（轴未写 txPr 本就无从判定，缺省不误报）；
    #   legend_required 缺省 = 不判（保守：老课件大量单系列图，默认开启会噪音爆炸）。
    #   yaml#chart.unimplemented 只剩 table_layout 一项。
    return {
        "enabled": bool(node.get("enabled")),
        "area_ratio": {
            "min": float(ar.get("min", 0.15) or 0.15),
            "max": float(ar.get("max", 0.60) or 0.60),
        },
        "axis_label_min_pt": (float(node["axis_label_min_pt"])
                              if node.get("axis_label_min_pt") is not None else None),
        "legend_required": bool(node.get("legend_required")),
    }


def check_chart_layout(slide, idx, rules, page_area):
    """图表页的**图区占比**检查（v3.22.0 G2 · 建议级）。

    判据（确定性，可机器判）：
      · 「图表页」= 页内存在 chart（graphicFrame）或 picture；
      · 图区占比 = 图表类形状面积之和 / 页面面积；
      · 占比 < min ⇒ 「图表图区占比过小」（图挤角落，讲不下去）；
      · 占比 > max ⇒ 「图表图区占比过大」（图挤满版面，讲解空间被吞）。

    ⚠ **问题类型不登记进 severity** ⇒ 落在 unknown_out（明示、**不阻断**），
      与既有 rubric 建议级同口径。

    v3.23.1 W1（第三轮盘点）：`chart.unimplemented` 三项中的两项**落地**——
      · axis_label_min_pt：图表坐标轴刻度标注字号 < 下限 ⇒ 告警
        （判据：chartSpace XML 内 `<c:catAx>/<c:valAx>` 段下 `<a:defRPr sz="N">`，
          N/100 = pt；多值取最小；**轴未写 txPr** = 继承默认字号、无从判定 ⇒ 不误报，
          与「未取得尺寸置 null 而非 0」同一纪律）；
      · legend_required：图表**多系列**（≥2 个 `<c:ser>`）却无 `<c:legend>` ⇒ 告警
        （单系列不需要图例——图例就是系列名本身）；
      · table_layout：仍不实现（表格布局判据边界未清，如实保留在 unimplemented）。
    解析通道：`shape.chart._chartSpace.xml`（python-pptx 对象模型，实测前缀稳定为
      `c:`/`a:`）；解析失败（老式图表/外部工作簿）⇒ 明示跳过、不误报。
    """
    out = []
    if not rules.get("enabled"):
        return out
    axis_min = rules.get("axis_label_min_pt")
    try:
        total = 0
        n_chart = 0
        for sh in slide.shapes:
            kind = str(getattr(sh, "shape_type", "") or "")
            is_chart = "CHART" in kind or sh.has_chart if hasattr(sh, "has_chart") else ("CHART" in kind)
            is_pic = "PICTURE" in kind
            if not (is_chart or is_pic):
                continue
            try:
                area = int(sh.width) * int(sh.height)
            except Exception:
                continue
            total += area
            if is_chart:
                n_chart += 1
                # ── W1：轴标注字号 / 图例存在性（解析 chartSpace XML）────────
                if axis_min is None and not rules.get("legend_required"):
                    continue          # 两项判据都未配置 ⇒ 不做 XML 解析
                try:
                    cxml = sh.chart._chartSpace.xml or ""
                except Exception as e:
                    # 解析失败明示跳过（老式图表 / 外部工作簿链接），不误报
                    out.append({"slide": idx, "type": "图表规范·无法解析",
                                "detail": f"chart XML 读取失败（{type(e).__name__}），"
                                          f"轴字号/图例检查跳过——请人工核对该图表",
                                "snippet": getattr(sh, "name", "") or "chart"})
                    continue
                import re as _re
                # 轴标注字号：catAx/valAx 段内 a:defRPr sz（百倍 pt），多值取最小
                if axis_min is not None:
                    szs = []
                    for _ax in ("c:catAx", "c:valAx"):
                        _m = _re.search(rf"<{_ax}>.*?</{_ax}>", cxml, _re.S)
                        if not _m:
                            continue
                        _v = _re.findall(r'<a:defRPr[^>]*\bsz="(\d+)"', _m.group(0))
                        if _v:
                            szs.append(min(int(x) for x in _v) / 100.0)
                    if szs and min(szs) < float(axis_min):
                        out.append({"slide": idx, "type": "图表轴标注字号过小",
                                    "detail": f"坐标轴刻度标注最小 {min(szs):g}pt "
                                              f"< 红线 {float(axis_min):g}pt"
                                              "（投影后看不清）",
                                    "snippet": f"{len(szs)} 根轴"})
                # 图例存在性：多系列（≥2 ser）却无 legend ⇒ 告警
                #   ⚠ ser 计数须兼容 <c:ser> 与自闭合 <c:ser/> 两种形态
                #   （真实图表的 ser 总是成对闭合标签；但判据不能依赖这个偶然——
                #     round-trip 工具/手写 XML 会产生自闭合形态，第三轮盘点实测踩过）
                if rules.get("legend_required"):
                    # <c:ser 后必须跟 /、空白或 >（防误吞 c:serX 之类前缀同名标签）
                    n_ser = len(_re.findall(r"<c:ser(?=[\s/>])[^>]*>", cxml))
                    has_legend = _re.search(r"<c:legend[\s>/]", cxml) is not None
                    if n_ser >= 2 and not has_legend:
                        out.append({"slide": idx, "type": "图表缺图例",
                                    "detail": f"{n_ser} 个系列却无图例——"
                                              "读者无法区分各系列含义（单系列不需要图例）",
                                    "snippet": "legend 缺失"})
        if total <= 0 or page_area <= 0:
            return out
        ratio = total / float(page_area)
        ar = rules.get("area_ratio") or {}
        if ratio < float(ar.get("min", 0.15)):
            out.append({"slide": idx, "type": "图表图区占比过小",
                        "detail": f"图区占比 {ratio*100:.1f}% < {float(ar.get('min',0.15))*100:.0f}%"
                                  f"（图挤角落，讲解空间被浪费）",
                        "snippet": f"{n_chart} 个图表"})
        elif ratio > float(ar.get("max", 0.60)):
            out.append({"slide": idx, "type": "图表图区占比过大",
                        "detail": f"图区占比 {ratio*100:.1f}% > {float(ar.get('max',0.60))*100:.0f}%"
                                  f"（图挤满版面，讲解空间被吞）",
                        "snippet": f"{n_chart} 个图表"})
    except Exception as e:
        out.append({"slide": idx, "type": "图表布局检查异常",
                    "detail": f"检查异常（{type(e).__name__}: {str(e)[:60]}）——按未判处理",
                    "snippet": ""})
    return out


def _shape_colors(shape):
    """收集该形状**文字**用到的颜色（v3.5.1：不再统计填充色）。

    判据口径修正（迭代四原则④「检出≠判定」实证）：
    旧实现把 shape.fill 一并计入，而卡片/警示框的浅色底（FDF0F0、FAF7E6）
    与金色装饰条（B8860B）是**版式设计**，不是学生读取的信息色。
    结果「主绿 145525 + 正文灰 333333 + 警示红 C00000 + 来源灰 999999」
    这一合规四色版式被计成 6 色、判为配色混乱。
    「配色混乱」的语义对象是信息色混乱，故改为只统计 run 文字色。
    需要单独查装饰色时，用 query/raw 视图人工看，不进机器判据。
    """
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
    return colors


def _rect(shape):
    """取形状外接矩形（EMU 四元组）；取不到返回 None。

    ⚠️ **与 ooxml_lint.py GeoChecker 的分工（v3.12.0 显式声明，避免误读为重复实现）**：
    两处都算"重叠"，但**判据不同、结论不同源，不该合并也不该互相校验**：

    | | 本函数（verify_deck 元素重叠） | GeoChecker（ooxml_lint GEO-003） |
    |---|---|---|
    | 对象 | 仅**文本框**两两 | **任意形状**两两（含图片/组合/图形） |
    | 语义 | 「文字压文字 = 学生看不见 = 零价值」 | 「任意几何冲突，含有意底纹叠放」 |
    | GROUP | 不做坐标换算（组合外接框直接用） | 按 chOff/chExt 换算子形状绝对坐标 |
    | 基线豁免 | 无 | 有（`--geo-baseline`，模板固有叠放判 inherited） |
    | 级别 | P1（交付前必须清零） | WARN（需人工结合渲染图裁定） |

    故同一份课件两个数字不同是**正常的**，不是 bug；谁也不该"修正"成另一个的值。
    本函数的几何能力弱于 GeoChecker，但语义更严格（只盯文字），两者互补。
    """
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
        # v3.5.1：run 级粒度（None = 未取到，判据回退形状级 min）
        "run_pairs": None, "empty_runs": 0,
        # v3.16.0：是否标题占位符（主框密度的排除项；不参与此前的任何判据）
        "is_title_ph": False,
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
        a["is_title_ph"] = _shape_is_title_ph(shape)
    except Exception:
        a["is_title_ph"] = False
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
            a["run_pairs"], a["empty_runs"] = _shape_run_pairs(shape, slide)
        except Exception:
            a["run_pairs"], a["empty_runs"] = None, 0
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
         "colors": set(), "is_pic": False,
         "run_pairs": None, "empty_runs": 0,
         "is_title_ph": False}          # v3.16.0
    try:
        a["is_title_ph"] = _xml_is_title_ph(elm)
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
        # v3.5.1：XML 兜底也做 run 级配对（a:r 内含 a:t 与 a:rPr@sz）
        _rp = []
        for r in elm.findall(".//" + qn("a:r")):
            t = r.find(qn("a:t"))
            txt = (t.text or "").strip() if t is not None else ""
            pr = r.find(qn("a:rPr"))
            s = _xml_sz(pr) if pr is not None else None
            if not txt:
                a["empty_runs"] += 1
                continue
            _rp.append((txt, s))
        if _rp:
            a["run_pairs"] = _rp
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
                # v3.16.0：补 rect（此前图片适配器 rect 恒为 None，图片面积占比无从计算）。
                # 影响面核查：越界检查要求 `a["text"]` 非空才判、装饰出血跳过 is_pic、
                # 重叠只取 has_tf 且有文本的适配器、配色只取 run 色——四条均与图片 rect 无关，
                # 故补这个字段不改变任何既有判定结果。
                try:
                    _r = _rect(shape)
                except Exception:
                    _r = None
                adapters.append({"ok": True, "err": None, "text": "", "has_tf": False,
                                 "rect": _r, "sizes": [], "unresolved_runs": 0,
                                 "colors": set(), "is_pic": True,
                                 "run_pairs": None, "empty_runs": 0,
                                 "is_title_ph": False})
                continue
        except Exception:
            pass
        ad = _extract_shape(shape, slide)
        if not ad["ok"]:
            stats["parse_errors"] += 1
        adapters.append(ad)
    return adapters, None


# ============ 建议级检查（rubric，v3.16.0）============
# 定位：**不是门禁，不计入 p0/p1/p2，不影响退出码**。产出只进 result["rubric"] 与 --json。
# 为什么默认关闭、何时可转正：见 config/visual-rules.yaml#checks 的注释（需先做基线标定）。

def _rubric_title_position(rows, cfg):
    """V1 版式统一（标题位置一致性）：标题占位符的 (left, top, width) 取众数，
    单页任一维偏离众数超过容差 → 出条目。

    Args:
        rows: [(slide_idx, (left, top, width)), ...]（EMU）
        cfg : {"enabled": bool, "tolerance_in": float}
    """
    out = []
    if not cfg.get("enabled") or len(rows) < 2:
        # 少于 2 页有标题占位符时"众数"无意义——不产条目。
        # 这是刻意的：众数判据在样本不足时必然产假阳性，而假阳性会让人关掉整个检查。
        return out
    tol_in = float(cfg.get("tolerance_in", 0.25))
    tol = tol_in * EMU_PER_INCH
    mode, mode_n = Counter([g for _, g in rows]).most_common(1)[0]
    for idx, g in rows:
        worst = max(abs(g[k] - mode[k]) for k in range(3))
        if worst <= tol:
            continue
        out.append({
            "check_id": "title_position_consistency",
            "slide": idx,
            "detail": (f"标题几何偏离众数 {round(worst / EMU_PER_INCH, 2)}in > 容差 {tol_in}in"
                       f"（本页 left/top/width={tuple(round(v / EMU_PER_INCH, 2) for v in g)}in；"
                       f"众数 {tuple(round(v / EMU_PER_INCH, 2) for v in mode)}in，"
                       f"{mode_n} 页同此版式）"),
        })
    return out


def _rubric_image_area(rows, cfg):
    """V5 图文比例：① 含图页的图片面积占比越界；② 纯文字页连续超过上限。

    Args:
        rows: [(slide_idx, ratio, has_pic), ...]；ratio = 图片面积合计 / 页面积
        cfg : {"enabled","min","max","max_consecutive_textonly"}
    """
    out = []
    if not cfg.get("enabled"):
        return out
    lo = float(cfg.get("min", 0.20))
    hi = float(cfg.get("max", 0.50))
    max_run = int(cfg.get("max_consecutive_textonly", 3))
    run = 0
    for idx, ratio, has_pic in rows:
        if has_pic:
            run = 0
            if not (lo <= ratio <= hi):
                out.append({
                    "check_id": "image_area_ratio",
                    "slide": idx,
                    "detail": (f"图片面积占比 {ratio * 100:.1f}% 越界"
                               f"（容许 {lo * 100:.0f}–{hi * 100:.0f}%）"),
                })
        else:
            run += 1
            if run > max_run:
                out.append({
                    "check_id": "image_area_ratio",
                    "slide": idx,
                    "detail": f"已连续 {run} 页纯文字（上限 {max_run} 页）",
                })
    return out


# ── C5 关键数据注明来源（v3.24.0 · 建议级）───────────────────────────────
# 立项依据：`.learnings/FEATURE_REQUESTS.md` 的 [缺口] V3/C5 条目——
#   `references/course-profile-defaults.md` §4.1 的 C5 长期标「暂无机器实现」，
#   而 §4.5 已如实登记该缺口（假承诺已摘掉）。本版补上 **C5** 的机器实现。
#
# ⚠ **为什么不用"正则扫全页数字"**：那样会把「25日龄」「3天」「2023年」等
#   非来源数字大量误报（FEAT 登记时的顾虑）。故判据**三层收敛**：
#   ① 指标语境（关键指标词命中）② 段落含数值 ③ 来源标记邻近
#   实测（4 份真实动医课件）：全页 1071 个数字 → 命中指标语境的仅 **7 个段落**。
#
# ⚠ **来源标记为什么不用裸 `\d{4}`**：实测「禽流感鉴别诊疗要点.pptx」
#   宽判（裸 4 位数字）命中 2/14、紧判（年份须带"年"字）命中 0/14
#   ⇒ 裸 `\d{4}` 会把段落里的**指标数字本身**误当年份（正是要防的假阳性）。
#
# ⚠ **本判据只验「有没有带来源标记」，不验「来源是否为真」**——后者是语义判断，
#   机器不可判定，**仍由人核**（与 §4.1 C5 行「+ [人] 核来源」口径一致）。
_C5_METRIC_WORDS = (
    "发病率", "死亡率", "保护率", "致死率", "感染率", "阳性率",
    "滴度", "中和抗体", "发病率", "死亡率",
)
# 来源标记：**字面串**部分（子串匹配）
#   ⚠ 年份**不能**写成字面串（`"20xx年"` 永远匹配不到「2024年」）——
#     故年份走独立的正则 `_C5_YEAR_RE`（见下）。此处只放字面标记。
_C5_SOURCE_PATTERNS = (
    "来源", "出处", "参考文献", "文献", "doi", "DOI", "PMID",
    "et al.",
    "标准", "GB", "指南", "教材",
    "WHO", "OIE", "FAO", "农业农村部", "国家卫健委",
)
# 年份：**必须**带"年"字（裸 4 位数字不算，见上文的假阳性取证）
_C5_YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年")
# 数值识别：整数 / 小数 / 百分数（**不**含年份形态的特殊处理，见来源标记注释）
_C5_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _c5_has_source(text: str) -> bool:
    """该文本是否含来源标记（字面标记 或 带"年"字的年份）。"""
    if any(p in text for p in _C5_SOURCE_PATTERNS):
        return True
    return bool(_C5_YEAR_RE.search(text))


def _rubric_key_data_source(para_rows, cfg):
    """C5 关键数据注明来源：**段落级**判据 + **页级**回退。

    Args:
        para_rows: [(slide_idx, paragraph_text), ...]（按页、按段落展开）
        cfg : {"enabled": bool, "scope": "paragraph_then_page"}

    返回 rubric 条目列表；每条含 check_id / slide / detail。
    """
    out = []
    if not cfg.get("enabled"):
        return out

    # 按页聚合（供页级回退用）
    page_texts: dict = {}
    for idx, text in para_rows:
        page_texts.setdefault(idx, []).append(text)

    # 页级：来源标记池（整页文本拼接）
    page_has_source: dict = {}
    for idx, texts in page_texts.items():
        joined = "\n".join(texts)
        page_has_source[idx] = _c5_has_source(joined)

    seen_pages = set()
    for idx, text in para_rows:
        # ① 指标语境
        if not any(w in text for w in _C5_METRIC_WORDS):
            continue
        # ② 段落含**量值**（含 % 或小数的数值）。
        #   ⚠ 纯整数不单独算数：株型编号（H5N1 / H7N9 / 亚型 2）会被误当"数据"，
        #     而它们恰恰**不需要**来源 ⇒ 计入会制造假阳性。
        nums = _C5_NUMBER_RE.findall(text)
        measures = [n for n in nums if "%" in n or "." in n]
        if not measures:
            continue
        # ③ 来源邻近：同段落 → 同页回退
        para_has_src = _c5_has_source(text)
        if para_has_src or page_has_source.get(idx):
            continue
        # 每页只出一条（避免一页多个未标源段落刷屏）
        if idx in seen_pages:
            continue
        seen_pages.add(idx)
        shown = "、".join(measures[:3]) + " 等"
        out.append({
            "check_id": "key_data_source",
            "slide": idx,
            "detail": (f"关键数据（{shown}）邻近无来源标记"
                       f"——须补「来源：…（年份）」或 DOI/PMID/标准号；"
                       f"「来源是否为真」仍需人工核"),
        })
    return out


def _count_by_level(red, unknown_out=None):
    """把 red 计数按 severity 映射拆成 (p0, p1)；未登记类型名写入 unknown_out（不清零、不落 P0）。

    抽成函数是为了可单测（T_unknown_type_not_p0）：旧实现是一行 sum() 内联表达式，
    无法对一个"假类型"验证分级行为。
    """
    p0 = p1 = 0
    for k, v in red.items():
        base = k.split("(")[0]
        lv = _TYPE_LEVEL.get(base, _UNKNOWN_LEVEL)
        if lv == "P0":
            p0 += v
        elif lv == "P1":
            p1 += v
        elif lv == "P2":
            pass                      # P2 走覆盖率口径（p2_block），不进 p0/p1 计数
        elif unknown_out is not None:
            unknown_out.append(k)     # 只有"完全没登记"的类型才进明示队列
    return p0, p1


def verify(path, hours=3, strict=False, caliber=None):
    """机械裁判主函数。

    v3.16.0 新增 `caliber` 入参：`None`=取 yaml `page_caliber_default`（当前 "course"），
    显式值 ∈ {course, single-ppt} 则按该口径取页数区间。
    **不加该参数调用时，一切判定（除本次新增的两项：主框密度 + rubric 建议级）
    与 v3.16.0 之前逐字节一致**——历史课件复验结论不得静默改变。
    """
    prs = Presentation(path)
    sw, sh = prs.slide_width, prs.slide_height
    caliber = _resolve_caliber(caliber)
    _caliber_table = {
        CALIBER_COURSE: THRESHOLD["hours_page_range"],
        CALIBER_SINGLE_PPT: THRESHOLD["hours_page_range_single_ppt"],
    }[caliber]
    issues = []
    stats = {
        "file": path,
        "total_slides": len(prs.slides),
        "visible_slides": 0,
        "hidden_slides": 0,
        "hours": hours,
        # v3.16.0：页数口径回显（报告/JSON 必须能看到实际用的哪张表与区间，防"以为用了 B 实际用了 A"）
        "caliber": caliber,
        "page_range": [0, 9999],
        "small_body": 0, "small_note": 0, "offcanvas": 0,
        "empty_runs_skipped": 0,  # v3.5.1：空 run 不计缺陷，单独计数备查
        "overlap": 0, "color_chaos": 0, "text_wall": 0,
        # v3.16.0：主框密度（此前 yaml 有 150 的承诺、代码无兜底）
        "body_wall": 0, "max_body_chars_seen": 0,
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

    # ── v3.22.0 G2：图表图区占比检查（建议级；未登记 severity ⇒ 明示不阻断）──
    _chart_rules_cfg = _chart_rules()
    if _chart_rules_cfg.get("enabled"):
        _page_area = int(prs.slide_width) * int(prs.slide_height)
        for _i, _s in visible:
            for _iss in check_chart_layout(_s, _i, _chart_rules_cfg, _page_area):
                issues.append(_iss)

    has_toc = False          # 目录页
    has_quiz = False         # 题页
    title_geom = []          # v3.16.0 V1 rubric 取数：[(页号, (left, top, width)), ...]
    img_rows = []            # v3.16.0 V5 rubric 取数：[(页号, 面积占比, 是否含图), ...]
    para_rows = []           # v3.24.0 C5 rubric 取数：[(页号, 段落文本), ...]
    for idx, slide in visible:
        adapters, fb_err = _slide_shape_adapters(slide, stats)

        text_adapters = [a for a in adapters if a["has_tf"] and a["text"]]
        page_text = " ".join(a["text"] for a in text_adapters)

        # 结构性识别
        if any(k in page_text for k in ("目录", "CONTENTS", "内容导航")):
            has_toc = True
        if any(k in page_text for k in ("思考题", "练习题", "课堂提问", "随堂测", "Q1", "答案")):
            has_quiz = True

        # v3.16.0：rubric 取数（纯读，零副作用；开关关闭时不产生任何计算外的代价）
        for a in adapters:
            r = a.get("rect")
            if a.get("is_title_ph") and r and all(v is not None for v in r):
                title_geom.append((idx, (r[0], r[1], r[2])))
                break
        pic_area = 0
        for a in adapters:
            r = a.get("rect")
            if a.get("is_pic") and r and all(v is not None for v in r):
                pic_area += (r[2] or 0) * (r[3] or 0)
        img_rows.append((idx, (pic_area / (sw * sh)) if (sw and sh) else 0.0, pic_area > 0))
        # v3.24.0 C5 rubric 取数：**段落级**文本（adapter 的 text 是整框文本，
        #   含换行 ⇒ 按行拆成段落，判"数字与来源是否同段邻近"）。
        for a in adapters:
            if not a.get("has_tf") or not a.get("text"):
                continue
            for line in a["text"].splitlines():
                line = line.strip()
                if line:
                    para_rows.append((idx, line))

        # ---------- 1. 字号（v3.5.1：run 级判定；空 run 跳过，图注按 run 文本取阈值）----------
        for a in text_adapters:
            pairs = a.get("run_pairs")
            if pairs:
                # run 级主路径：空 run 已在 _shape_run_pairs 中剔除并单独计数
                stats["empty_runs_skipped"] += a.get("empty_runs", 0)
                unresolved = 0
                for txt, pt in pairs:
                    if pt is None:
                        unresolved += 1
                        continue
                    is_note = _is_note_candidate(txt)
                    # v3.19.0：标题占位符的 run 用 title_min_pt 阈值（此前标题字号
                    #   按 body_min_pt=12 判——28pt 的红线只写在屠明熙 MD 里，机器不设防）
                    is_title = bool(a.get("is_title_ph"))
                    # v3.21.0：**页脚/页码档**——页脚是装饰性信息（课程名·章节 + 页码），
                    #   典型 8pt；原先无此档 ⇒ 被按 body_min_pt 判「字号过小」，
                    #   而 severity 映射里它是 P0 硬阻断 ⇒ 合规课件凭空造 P0（实测可复现）。
                    is_footer = _is_footer_frame_for_font(
                        a.get("text"), a.get("rect"), sh,
                        int(THRESHOLD.get("footer_max_chars", 40) or 40))
                    if is_title:
                        limit = THRESHOLD["title_min_pt"]
                        kind = "标题"
                    elif is_footer:
                        limit = THRESHOLD.get("footer_min_pt", 8.0)
                        kind = "页脚/页码"
                    elif is_note:
                        limit = THRESHOLD["note_min_pt"]
                        kind = "图注/来源"
                    else:
                        limit = THRESHOLD["body_min_pt"]
                        kind = "正文"
                    if pt < limit:
                        if is_title:
                            stats["small_title"] = stats.get("small_title", 0) + 1
                        elif is_note:
                            stats["small_note"] += 1
                        else:
                            stats["small_body"] += 1
                        issues.append({
                            "slide": idx, "type": "字号过小",
                            "detail": f"{pt}pt < {limit}pt（{kind}）",
                            "snippet": txt[:30],
                        })
                if unresolved:
                    # 按形状记一次 P3「未知」，与旧口径可比（旧口径整框只记一次）
                    stats["unknown_font"] += 1
                    if strict:
                        issues.append({
                            "slide": idx, "type": "字号过小",
                            "detail": f"{unresolved} 个 run 字号未解析（strict）",
                            "snippet": a["text"][:30],
                        })
                continue
            # 兜底：未取到 run 配对（XML 路径异常等）→ 沿用 v2.2.0 形状级 min 判据
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
            # v3.21.0：同 run 级路径——形状级兜底也须认页脚档（两条路径口径必须一致，
            #   否则"能取到 run 走 run 级、取不到走形状级"会出现口径漂移）
            is_footer = _is_footer_frame_for_font(
                txt, a.get("rect"), sh,
                int(THRESHOLD.get("footer_max_chars", 40) or 40))
            if is_footer:
                limit = THRESHOLD.get("footer_min_pt", 8.0)
            else:
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

        # ---------- 5. 文字墙（全页口径） ----------
        if len(page_text) > THRESHOLD["max_chars_per_slide"]:
            stats["text_wall"] += 1
            issues.append({
                "slide": idx, "type": "文字墙",
                "detail": f"单页 {len(page_text)} 字 > {THRESHOLD['max_chars_per_slide']} 字",
                "snippet": page_text[:40],
            })

        # ---------- 5b. 主框密度（v3.16.0：把 yaml 里躺了 8 个版本的 150 字接到机器上）----------
        # 与「文字墙」是两个口径，别合并：40 字标题 + 380 字正文不触发 400 的全页墙，
        # 但学生要读的主框已经 380 字——这正是 v3.5.0 事故的形态。
        body_chars, body_frames = body_frame_chars(adapters, sh)
        stats["max_body_chars_seen"] = max(stats["max_body_chars_seen"], body_chars)
        if body_chars > THRESHOLD["max_body_chars_per_slide"]:
            stats["body_wall"] += 1
            full = len(page_text)
            tail = (f"全页 {full} 字仍在 400 字口径内"
                    if full <= THRESHOLD["max_chars_per_slide"]
                    else f"全页 {full} 字亦超 400 字（另按「文字墙」计）")
            issues.append({
                "slide": idx, "type": "主框密度超标",
                "detail": (f"主框 {body_chars} 字（{body_frames} 个框，已排除标题/图注/页脚） > "
                           f"{THRESHOLD['max_body_chars_per_slide']} 字；{tail}"),
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

    # ---------- 7. 课时匹配（v3.16.0：按 caliber 选口径）----------
    # ⚠️ 默认走 `page_caliber_default`（当前 course = 口径 A），与 v3.16.0 之前完全一致；
    #    单份 PPT 场景须由调用方显式 `--caliber single-ppt`（口径 B）切换，机器不猜场景。
    # 措辞说明：默认口径下 detail 字符串**保持 v3.16.0 之前的原样**（不追加口径标签），
    #    以保证历史复验输出的 diff 为零；仅当显式切到口径 B 时才在 detail 里标注口径来源——
    #    此时结论本来就是新的，标注是为了让"这份绿灯是按单次 PPT 口径出的"可被追溯。
    #
    # ── 缺档与空表**不得静默通过**（v3.16.0 修 `get(hours, (0, 9999))` 的护栏空洞）──
    # 旧写法下 `--caliber single-ppt --hours 1.5` 会落到缺省 (0, 9999) → hours_ok 恒真，
    # 课时匹配这项 P0 检查**看起来在跑、实际没设防**；yaml 结构异常导致整表为空时更严重（全档静默放行）。
    # 取舍记录：缺档时**不伪造 P0**（课件是否真的不符标准，机器此刻无从判断，凭空判失败会诱导绕过门禁），
    # 但也**绝不算达标**：hours_ok=False + stats 标记 + stderr 告警 + 计入 gate.p3 明示队列。
    # 三者叠加的结果：报告里任何一处都不可能读出"课时已达标"，且 **[未判定]** 与 **[不达标]** 是两个可见状态。
    n = stats["visible_slides"]
    if not _caliber_table:
        lo, hi = 0, 9999
        _missing_detail = (f"口径 {caliber} 的页数表为空（yaml 缺该键或结构异常），"
                           f"课时匹配未执行（非通过）")
    elif hours not in _caliber_table:
        lo, hi = 0, 9999
        _missing_detail = (f"口径 {caliber} 未定义 {hours} 课时的页数标准，"
                           f"课时匹配未执行（非通过）")
    else:
        lo, hi = _caliber_table[hours]
        _missing_detail = ""
    hours_missing = bool(_missing_detail)
    stats["page_range"] = [lo, hi]
    stats["hours_standard_missing"] = hours_missing
    stats["hours_missing_detail"] = _missing_detail
    if hours_missing:
        print(f"⚠ {_missing_detail}——请改用 course 口径，"
              f"或按 references/batch-surgery-sop.md#§8 走降级签字", file=sys.stderr)

    hours_fail = (not hours_missing) and not (lo <= n <= hi)
    hours_ok = (not hours_missing) and (lo <= n <= hi)
    if caliber == CALIBER_SINGLE_PPT:
        _detail = f"可见{n}页，{hours}课时标准({lo}-{hi}页)［single-ppt·单次PPT口径］"
    else:
        _detail = f"可见{n}页，{hours}课时标准({lo}-{hi}页)"   # 与 v3.16.0 之前逐字节一致
    if hours_fail:
        issues.append({"slide": 0, "type": "课时不达标", "detail": _detail, "snippet": ""})
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
        "主框密度超标": stats["body_wall"],        # v3.16.0（P1，见 yaml severity）
        "空白页": stats["empty_slides"],
        "缺备注": stats["no_notes"],
        # v3.16.0：缺档时**不伪造这条 P0**（课件是否不符标准此刻无从判断），改为 P3 明示（见 §7 注释）
        "课时不达标": 1 if hours_fail else 0,
        "缺目录页": 0 if has_toc else 1,
        "缺题页": 0 if has_quiz else 1,
    }
    # v3.16.0：未知问题类型**不再默认落 P0**（旧代码写的是 `_TYPE_LEVEL.get(..., "P0")`）。
    #   严重性未知 ≠ 最严重；默认判 P0 会让新检查在标定期就把课件拦死，进而诱导绕过门禁。
    #   未登记类型改为计入 P3（明示）：不阻断，但**不会悄悄消失**（下面会列出来）。
    unknown_red = []
    p0, p1 = _count_by_level(red, unknown_red)
    stats["unknown_red_keys"] = unknown_red

    note_cov = 1.0 if n == 0 else round((n - stats["no_notes"]) / n, 3)
    p2_block = note_cov < THRESHOLD["p2_note_coverage"]
    # 机器草稿占比（裁决④）：计入覆盖率，但必须单独报出，供交付物明示
    noted = n - stats["no_notes"]
    machine_ratio = round(stats["machine_notes"] / noted, 3) if noted else 0.0

    # ---------- 建议级检查（rubric，v3.16.0：不计入任何分级、不影响退出码）----------
    checks_cfg = THRESHOLD.get("checks") or {}
    rubric = []
    if (checks_cfg.get("title_position_consistency") or {}).get("enabled"):
        rubric += _rubric_title_position(title_geom, checks_cfg["title_position_consistency"])
    if (checks_cfg.get("image_area_ratio") or {}).get("enabled"):
        rubric += _rubric_image_area(img_rows, checks_cfg["image_area_ratio"])
    # v3.24.0：C5 关键数据注明来源（建议级，默认关闭；开关见 visual-rules.yaml#checks）
    if (checks_cfg.get("key_data_source") or {}).get("enabled"):
        rubric += _rubric_key_data_source(para_rows, checks_cfg["key_data_source"])

    # v3.16.0：课时标准缺失/空表进 P3 明示队列——不阻断，但不可能被读成"达标"
    p3 = (stats["unknown_font"] + stats["parse_errors"] + stats["bleed_decor"]
          + (1 if hours_missing else 0))

    stats["note_coverage"] = note_cov
    stats["machine_note_pages"] = stats["machine_notes"]
    stats["machine_note_ratio"] = machine_ratio

    return {"stats": stats, "red": red, "issues": issues, "rubric": rubric,
            "gate": {"p0": p0, "p1": p1, "note_coverage": note_cov,
                     "p2_threshold": THRESHOLD["p2_note_coverage"],
                     "p2_block": p2_block, "p3": p3,
                     "machine_note_ratio": machine_ratio,
                     "machine_note_pages": stats["machine_notes"],
                     "rubric_count": len(rubric)}}


def gate_decision(gate, level):
    """按请求 level 返回 (blocked_by, exit_code)。blocked_by ∈ {None,'P0','P1','P2'}"""
    if gate["p0"] > 0:
        return "P0", 1
    if level in ("P1", "all") and gate["p1"] > 0:
        return "P1", 2
    if level == "all" and gate["p2_block"]:
        return "P2", 3
    return None, 0


# ─────────────────────── 闸4.5 三源核验（v3.3.0 / v3.17.0 重做判定口径）───────────────────
def _verdict_detail(verdict, blocked_by, pass_rate, threshold):
    """人读结论（禁止只给一个布尔值——读的人必须知道"卡在哪一步"）。"""
    if verdict == "pass":
        return "通过：抽检案例全部满足三源判定（存在性已验证口径）"
    parts = []
    if "pass_rate_below_threshold" in blocked_by:
        parts.append(f"通过率 {pass_rate:.3f} < 阈值 {threshold}")
    if "network_incomplete" in blocked_by:
        parts.append("联网核验未完成（网络失败条目未被当作已验证）")
    return "未通过：" + "；".join(parts)


def three_source_check(workspace: str, deck: str = "", scan_all: bool = False) -> dict:
    """闸4.5：抽检 unverified 案例，按**三档判定**核验其 sources 的真实性。

    v3.17.0 前的判据（已废除）：
        `any(src.get("ok") is True for src in sources)`
      —— 只看**自报布尔值**，零存在性校验。独立诊断组实跑复现：造 3 条来源
      （不存在的 PMID + 不存在的 ISBN + 不存在的 GB）把 ok 写成 true，
      闸4.5 输出 pass_rate=1.0 / verdict=pass / exit 0；交叉核验该 PMID 在
      PubMed esearch count=0（根本不存在）。注释写"至少 1 条"还与"三源"命名矛盾。

    v3.17.0 起的判据（唯一源 = config/domain_config.yaml#three_source_check）：
      · 每条来源按 kind 走各自的核验方式，归入且仅归入三档之一：
          存在性已验证 existence_verified —— 联网实查命中（当前仅 pubmed 具备）
          仅格式合规   format_only        —— ISBN 校验位 / 国标编号格式通过，
                                              **未验证存在性**（格式过 ≠ 存在）
          不可核验     unverifiable       —— 无核验器 / 格式不过 / 联网失败
      · 「仅格式合规」**不计入已验证**；判定**不读 src.ok**（自报值不构成证据）。
      · 联网失败（None）单独计数 + 显式告警，既不算已验证、也不让整轮静默通过。
      · 每案例须三类来源齐备，且其中至少 N 条达到「存在性已验证」才算通过。

    Args:
        workspace: 课程工作区根（含 .workbuddy/cases/cases_library.json）
        deck: 当前 deck 路径（仅用于过滤"此 deck 的案例"——非全库）
        scan_all: True = 不按 deck 过滤，扫全库（**存量核验清单**用；见 --scan-all）

    Returns:
        dict: 见下方返回结构；verdict ∈ {pass, needs_more_verification, no_library}
    """
    import json
    import random
    from pathlib import Path

    tsc = _load_three_source_thresholds()          # 全段（三档判定配置）
    kernel = _load_three_source_kernel()            # 内核实现（唯一实现点）

    # v3.17.0 收尾：**护栏缺失即 fail-closed**（与包内查询者口径、与 guard.yaml 的
    #   "缺键即红"标准一致）。决策键缺失 → 不补内置值、不静默按默认判，
    #   直接判「护栏缺失」并阻断：yaml 缺键 = 护栏不存在，不能当它存在。
    missing_guard = [k for k in ("sample_rate", "pass_threshold", "required_kinds",
                                 "required_existence_verified")
                     if tsc.get(k) is None]
    if missing_guard:
        msg = (f"闸4.5 护栏缺失：{missing_guard} 未在 "
               f"config/domain_config.yaml#three_source_check 配置——"
               f"不补内置值、不按默认值继续判（补了就等于 yaml 成装饰品）。"
               f"请补齐该键后重跑。")
        print(f"⛔ {msg}", file=sys.stderr)
        return {"verdict": "config_incomplete", "error": msg,
                "blocked_by": ["config_incomplete"], "alarms": [msg],
                "pass_rate": 0.0, "threshold": tsc.get("pass_threshold"),
                "total": 0, "sampled": 0, "verified": 0,
                "missing_guard_keys": missing_guard,
                "criteria": {"config_source": "config/domain_config.yaml#three_source_check",
                             "note": "护栏缺失 → fail-closed（不补内置值）"}}

    # 1. 读 cases_library
    cases_p = Path(workspace) / ".workbuddy" / "cases" / "cases_library.json"
    if not cases_p.exists():
        return {"verdict": "no_library", "error": f"未找到 {cases_p}",
                "pass_rate": 0.0, "threshold": tsc.get("pass_threshold"),
                "total": 0, "sampled": 0, "verified": 0,
                "alarms": [f"未找到案例登记册：{cases_p}——闸4.5 **未执行**，"
                           f"不得读作「已通过」"]}

    with open(cases_p, encoding="utf-8") as f:
        lib = json.load(f)
    cases = lib.get("cases", []) if isinstance(lib, dict) else (lib or [])

    # 2. 过滤：当前 deck 的案例（按 deck_path 后缀匹配）；--scan-all 时扫全库
    deck_name = Path(deck).name if deck else ""
    if scan_all or not deck_name:
        deck_cases = list(cases)
    else:
        deck_cases = [c for c in cases if Path(c.get("deck_path", "")).name == deck_name]
    unverified = [c for c in deck_cases if c.get("unverified", True)]

    # 3. 抽检（读 domain_config.yaml#three_source_check.sample_rate；可复现种子可选）
    #    ⚠ --scan-all（存量核验清单）走**全量**：清单的目的是摸清存量规模，
    #    抽样估不出规模；闸4.5 判定的抽样语义不变。
    # v3.27.0（L-5）：删掉内联字面量默认值 0.1。
    #   ⚠ 原写法 `float(tsc.get("sample_rate", 0.1))` 的 default **不可达**：
    #     `harness.load_three_source_config()` 保证 `out = dict(defaults)` 后再被 yaml 覆盖
    #     ⇒ `sample_rate` 键**永远存在** ⇒ `.get()` 的 default 分支永不触发。
    #   ⚠ 而它**看起来**像"yaml 缺了就退回 0.1" ⇒ 改配置的人会误以为
    #     "这个 0.1 是兜底值，改 yaml 不影响它" ⇒ **误导性死代码**。
    #   ⚠ 更糟的一层：若 yaml 缺该键，`harness` 按 v3.17.0 口径把**决策键置 None**
    #     （不补内置值，fail-closed）⇒ `tsc["sample_rate"] is None`
    #     ⇒ `.get(key, 0.1)` 返回 **None**（default 同样不生效）
    #     ⇒ `float(None)` 抛 TypeError ⇒ 崩在算式里，而不是给出可读报错。
    #   ⇒ 缺键策略统一由 harness 负责（置 None + 显式告警 + fail-closed）；
    #     判定点只读，不自带字面量（体检第 21 项判据③会扫）。
    sample_rate = float(tsc["sample_rate"])
    if scan_all:
        sample_n = len(unverified)
        sampling = "all"
    else:
        sample_n = max(1, int(len(unverified) * sample_rate))
        sample_n = min(sample_n, len(unverified))
        sampling = "rate"
    seed = tsc.get("sample_seed")
    rnd = random.Random(seed) if seed is not None else random
    sampled = rnd.sample(unverified, sample_n) if sample_n else []

    # 4. 联网实查（存在性核验的唯一来源）：只查格式可解析、且不在静态黑名单的 PMID
    #    v3.17.0 收尾：api_key（真值只从环境变量读）+ 可配限速 + 遇速率限制指数退避
    #    并显式告警（NCBI 对无 key 匿名访问有 3 req/s 限制，批量清单会触发封禁——
    #    这是**已知环境约束**，处置是配 key / 分批 + 批间留间隔，不是改判据）。
    online = {}
    pmids = kernel.collect_pending_pmids(sampled, tsc)
    ep = kernel._esearch_params(tsc)
    if pmids:
        print(ep["note"], file=sys.stderr)
        online = kernel.pmid_existence_check(
            pmids,
            endpoint=ep["endpoint"], db=ep["db"], timeout=ep["timeout"],
            sleep=ep["sleep"], api_key=ep["api_key"],
            max_retries=ep["max_retries"], backoff_base=ep["backoff_base"],
            backoff_cap=ep["backoff_cap"], suspect_threshold=ep["suspect_threshold"],
            abort_batch_on_rate_limit=ep["abort_batch_on_rate_limit"])

    # 5. 逐案例定档（三档判定）
    case_results = [kernel.verify_three_source_case(c, tsc, online) for c in sampled]

    # 6. 聚合
    verified = sum(1 for r in case_results if r["verdict"] == "pass")
    pass_rate = verified / max(len(sampled), 1)
    # v3.27.0（L-5）：同 sample_rate —— 删掉不可达的 default 0.8，
    #   缺键策略统一由 harness.load_three_source_config() 负责（置 None + 告警）。
    threshold = float(tsc["pass_threshold"])
    policy = str(tsc.get("network_failure_policy") or "block")
    net_err = sum(r["network_error"] for r in case_results)
    refuted = sum(r["refuted"] for r in case_results)
    tier_counts = {
        "existence_verified": sum(r["existence_verified"] for r in case_results),
        "format_only": sum(r["format_only"] for r in case_results),
        "unverifiable": sum(r["unverifiable"] for r in case_results),
    }
    alarms = []
    if net_err:
        alarms.append(f"联网核验失败 {net_err} 条（网络/端点异常，未取得结论）——"
                      f"按 network_failure_policy={policy} 处置：既不计为已验证，"
                      f"也不让整轮判 pass")
    if refuted:
        alarms.append(f"实查证伪 {refuted} 条来源（引用真实不存在／已失效）——"
                      f"这是数据错，不是环境问题，须逐条处置")
    blocked_by = []
    if pass_rate < threshold:
        blocked_by.append("pass_rate_below_threshold")
    if net_err and policy == "block":
        blocked_by.append("network_incomplete")
    verdict = "pass"
    if blocked_by:
        verdict = "needs_more_verification"

    out = {
        "deck": deck_name,
        "scope": "all_library" if (scan_all or not deck_name) else "deck",
        "total_in_deck": len(deck_cases),
        "unverified_in_deck": len(unverified),
        "sampled": len(sampled),
        "sampling": sampling,
        # ⚠ 语义变更（v3.17.0）：verified 从"任一来源 ok=true"改为
        #   "该案例按三档判定**通过**"（含存在性已验证要求）。
        "verified": verified,
        "pass_rate": round(pass_rate, 3),
        "threshold": threshold,
        "verdict": verdict,
        "blocked_by": blocked_by,
        "verdict_detail": _verdict_detail(verdict, blocked_by, pass_rate, threshold),
        "tier_counts": tier_counts,
        "existence_verified_sources": tier_counts["existence_verified"],
        "format_only_sources": tier_counts["format_only"],
        "unverifiable_sources": tier_counts["unverifiable"],
        "refuted_sources": refuted,
        "network_error_sources": net_err,
        "alarms": alarms,
        "criteria": {
            "config_source": "config/domain_config.yaml#three_source_check",
            "tiers": tsc.get("tiers"),
            "required_kinds": tsc.get("required_kinds"),
            "required_existence_verified": tsc.get("required_existence_verified"),
            "network_failure_policy": policy,
            "sample_rate": tsc.get("sample_rate"),
            "sample_seed": tsc.get("sample_seed"),
            "note": "「仅格式合规」不计入已验证；联网失败不算通过；"
                    "判定不读 src.ok（自报布尔值不构成证据）",
        },
        # v3.17.0 收尾：来源类型显示名（读 yaml#sources[*].label——此前是死配置键）
        "source_types": kernel._source_labels(tsc),
        "samples": [{"case_id": r.get("case_id"), "title": r.get("title"),
                     "sources_count": len(r.get("sources") or []),
                     "verified": r.get("verdict") == "pass",
                     "verdict": r.get("verdict"),
                     "existence_verified": r.get("existence_verified"),
                     "format_only": r.get("format_only"),
                     "unverifiable": r.get("unverifiable"),
                     "sources": [{"kind": s.get("kind"), "label": s.get("label"),
                                  "tier": s.get("tier"), "reason": s.get("reason")}
                                 for s in (r.get("sources") or [])]}
                    for r in case_results[:5]],  # 仅展示前 5
        "case_results": case_results,
    }
    if out["scope"] == "all_library":
        # 存量核验清单：按 deck 归并，便于主理人汇总存量规模
        by_deck = {}
        for r in case_results:
            k = Path(str(r.get("deck_path") or "")).name or "(未登记)"
            by_deck.setdefault(k, {"cases": 0, "passed": 0, "refuted": 0, "network_error": 0})
            by_deck[k]["cases"] += 1
            if r.get("verdict") == "pass":
                by_deck[k]["passed"] += 1
            by_deck[k]["refuted"] += r.get("refuted") or 0
            by_deck[k]["network_error"] += r.get("network_error") or 0
        out["summary_by_deck"] = by_deck
    for a in alarms:
        print(f"⚠ {a}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description="教学课件机械验证器（分级门禁 v2.0.0 + v3.3.0 三源核验）")
    ap.add_argument("deck", nargs="?",
                    help="课件路径 .pptx（--three-source-check + --scan-all 模式可省）")
    ap.add_argument("--hours", type=float, default=None,
                    help="课时数（v3.0.0 起必填：1 / 1.5 / 2 / 3 / 4。"
                         "不再默认 3——默认值会凭空判出「课时不达标」，是 B0 口径混乱的源头之一。"
                         "1.5=1小时教学单元60min档；扩展阅读页不计入可见页，由阶段0 冻结口径。"
                         "（--three-source-check 模式不需课时数，故改为运行期校验）")
    ap.add_argument("--level", choices=["P0", "P1", "all"], default="all",
                    help="门禁级别：P0=写回门禁 / P1=中检门禁 / all=交付门禁（默认）")
    # v3.16.0：页数口径显式切换（此前只有"整套课程课件"一张表，按单份 PPT 做的课件必被误判）
    ap.add_argument("--caliber", choices=list(CALIBERS), default=None,
                    help="页数口径：course=整套课程课件（hours_page_range，默认，见 yaml "
                         "page_caliber_default）；single-ppt=单次 PPT（hours_page_range_single_ppt，"
                         "数值同源 references/course-profile-defaults.md#2）。"
                         "不加此参数时不改变任何历史复验结论。")
    ap.add_argument("--json", help="输出 JSON 报告路径")
    ap.add_argument("--strict", action="store_true", help="严格模式：未解析字号也判 P0")
    ap.add_argument("--limit", type=int, default=25, help="终端最多打印多少条问题")
    # v3.3.0：闸4.5 案例三源核验模式
    ap.add_argument("--three-source-check", action="store_true",
                    help="闸4.5：读 <workspace>/.workbuddy/cases/cases_library.json，"
                         "按 domain_config.yaml#three_source_check.sample_rate 抽检 unverified 案例，"
                         "按**三档判定**核验来源真实性（存在性已验证 / 仅格式合规 / 不可核验），"
                         "按同节 pass_threshold 判定是否达标（默认 0.1 / 0.8）。"
                         "v3.17.0：判定不读 sources[].ok（自报布尔值），pubmed 走 PubMed esearch 实查，"
                         "textbook 走 ISBN 校验位、regulation 走国标编号格式；联网失败不算通过。\n"
                         "⚠ 已知环境约束（不是 bug）：NCBI 对**无 key 的匿名访问**限速 3 req/s，"
                         "连续批量请求会被 abuse 系统封禁（Access Denied / 429，"
                         "部分网络路径下表现为 SSL EOF）。⇒ **跑存量清单必须分批 + 批间留间隔**；"
                         "有 key 时设环境变量 NCBI_API_KEY（yaml 只存变量名，真值不落盘）可到 10 req/s。"
                         "遇封禁时闸4.5 判 network_incomplete（fail-closed，不静默通过）。")
    ap.add_argument("--workspace", default="",
                    help="--three-source-check 必填：课程工作区根（含 .workbuddy/cases/）")
    ap.add_argument("--scan-all", dest="scan_all", action="store_true",
                    help="闸4.5：扫全库案例（不按 deck 过滤、且**全量抽检**不用 sample_rate）"
                         "——用于生成「存量核验清单」（汇总存量规模）；配 --json 落盘。"
                         "⚠ 清单跑不完是已知环境约束（NCBI 匿名限速会封禁），"
                         "须**分批 + 批间留间隔**，或设 NCBI_API_KEY 环境变量。")
    a = ap.parse_args()

    # v3.17.0：--three-source-check 模式下 deck 位置参数与 --hours 均可省（--scan-all 清单模式用）
    if not a.three_source_check and not a.deck:
        print("用法错误：必须给出课件路径（--three-source-check 模式可用 --scan-all 免课件）",
              file=sys.stderr)
        sys.exit(2)
    if not a.three_source_check and a.hours is None:
        print("用法错误：--hours 必填（1 / 1.5 / 2 / 3 / 4）——不设默认值，"
              "避免凭空判出「课时不达标」", file=sys.stderr)
        sys.exit(2)

    # v3.3.0 短路：--three-source-check 模式只跑三源核验，不跑主门禁
    if a.three_source_check:
        try:
            r = three_source_check(a.workspace, a.deck or "", scan_all=a.scan_all)
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
        # ⚠ v3.17.0：只有 verdict=="pass" 才算达标；联网失败 / 证伪 / 未齐备一律非 0，
        #   杜绝"没查到 → 当作通过"。
        sys.exit(0 if r.get("verdict") == "pass" else 1)

    try:
        r = verify(a.deck, a.hours, a.strict, a.caliber)
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
    _hours_flag = ("✓" if s["hours_ok"]
                   else ("⚠未判定" if s.get("hours_standard_missing") else "✗"))
    print(f"目录页:{'✓' if s['has_toc'] else '✗'}  题页:{'✓' if s['has_quiz'] else '✗'}  课时匹配:{_hours_flag}")
    # v3.16.0：缺档时 stdout 必须同样喊出来（不能只在 stderr）：
    #   只写 stderr 的话，被上层脚本收走输出的使用者会看到一份"没有任何课时问题"的报告
    if s.get("hours_standard_missing"):
        print(f"⚠ 课时匹配【未执行】＝ 非通过：{s['hours_missing_detail']}"
              f"——请改用 course 口径，或按 references/batch-surgery-sop.md#§8 走降级签字")
        print(f"  报告解读：此时 `hours_ok=false` 表示**未判定**，不等于“课时不达标”，"
              f"也不等于“达标”；该项计入 P3 明示，不阻断写回。")
    # v3.16.0：口径回显——不贴这一行，读报告的人无法判断"这盏绿灯是按哪张表给的"
    _range_txt = ("未定义（该口径无此课时档，见上方告警）" if s.get("hours_standard_missing")
                  else f"{s['page_range'][0]}-{s['page_range'][1]} 页")
    print(f"页数口径 {s['caliber']}（{'整套课程课件' if s['caliber'] == 'course' else '单次PPT'}）"
          f"｜{s['hours']} 课时区间 {_range_txt}"
          f"｜来源 config/visual-rules.yaml#hours_page_range"
          f"{'' if s['caliber'] == 'course' else '_single_ppt'}")
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

    # v3.16.0：建议级（rubric）——明确"不计门禁"，避免读者把它当红灯去清
    rubric = r.get("rubric") or []
    if rubric:
        print(f"建议级提示（rubric，v3.16.0：不计入 P0/P1/P2、不阻断）共 {len(rubric)} 条：")
        for entry in rubric[:a.limit]:
            print(f"  P{entry['slide']:<3} [{entry['check_id']}] {entry['detail']}")

    verdict = {None: "✅ 通过（level=" + a.level + "）",
               "P0": "❌ P0 硬阻断——写回磁盘禁止，先清 P0",
               "P1": "❌ P1 阻断——可带修复计划写回，交付前必须清零",
               "P2": "❌ P2 阻断——备注覆盖率未达标"}[blocked_by]
    # v3.16.0：课时标准缺档时给结论加限定语——否则"✅ 通过"会被读成"课时已达标"，
    #   而这恰恰是本处罚完好几处静默失效要防的误读（exit code 仍按 P3 不阻断处理）。
    if s.get("hours_standard_missing"):
        verdict += "｜⚠ 但课时匹配未执行（口径缺此课时档），本次结论不含课时判定"
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
            # v3.16.0：口径与实际使用的区间入溯源块——复验时能反推"这条结论按哪张页数表出的"
            "caliber_arg": a.caliber,
            "caliber_used": s["caliber"],
            "page_range_used": s["page_range"],
            "page_caliber_default": THRESHOLD.get("page_caliber_default"),
            "thresholds": os.path.abspath(_RULES_PATH),
        }
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告已存：{a.json}")

    sys.exit(code)


if __name__ == "__main__":
    main()

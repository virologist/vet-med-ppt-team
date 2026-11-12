#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_contracts.py — 契约检查器：把「仅有文字说明、无实际检查」的要求转为机器判据。

v3.31.0 新建。定位：体检 27 项（ensure_settings.py）管的是**包自身的健康度**
（版本一致、镜像同步、死配置、文档漂移…），**不覆盖「系统对用户交付的东西是否合规」**。
本脚本补上那一面，且**只做确定性判定**（文件存在 / 集合相等 / 字段齐备 / 数值一致），
**不判语义与审美**——语义与审美仍由人工复核。

── 为什么需要（2026-11-11 真实运行取证，四条一手证据）─────────────────────────
  ① 交付三件套（成品 PPTX + 逐页修改说明 + 验收自检清单）只在
     `references/delivery-spec.md` 有 schema 说明，**全包无任何脚本检查齐备性**
     ⇒ 「三件缺一不算完成」这条纪律**不可执行**。
  ② 文档里体检项数口径有 15/15、22/22、23/23 三个版本，而真源是 27 项，
     **无任何守卫** ⇒ 文档口径会随版本推进继续漂移（历史已发生过 R2 同型问题）。
  ③ 闸2/3/4 **无闸1 同级的就绪检查**（只有 `gate1-check`）⇒ 上游缺失在下游才暴露。
  ④ `references/work-map.yaml` 是新增的机器可读工作地图，若无守卫，
     它会与 `config/harness.yaml#stages` 各说各话（真值分裂）。

── 设计取舍（与本包既有纪律一致）────────────────────────────────────────────
  · **只读**：本脚本不改任何被检查文件；产出检查记录（JSON）供追溯。
  · **可测**：核心判定抽成纯函数，配套 `scripts/test_contracts.py` 提供能红反例。
  · **不冒充裁判**：检出 ≠ 判定（adjudication-rules.md 迭代六原则④）。
    本脚本报「缺/不一致」并给证据，**不替用户下结论**。

退出码：
  0 = 全部契约满足
  1 = 有契约未满足（逐条列出，附证据路径）
  2 = 用法错误
  3 = 依赖缺失（被检查的文件/目录不存在）
"""

import argparse
import json
import os
import re
import sys

#: 本脚本自身的编码（Windows 终端下 stdout 可能为 GBK）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - 老平台无该属性
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)


# ═══════════════════════════════════════════════════════════════════════
# 判定结果容器
# ═══════════════════════════════════════════════════════════════════════
class Check:
    """一条契约检查结果。

    字段（对齐「检查对象 / 结果 / 证据」三要素）：
      cid    契约编号（稳定，用于跨轮次对账）
      target 被检查对象（文件路径或配置键）
      ok     是否满足
      detail 人类可读的证据说明
      level  严重级：block（阻断）/ warn（提示，不阻断）
    """

    def __init__(self, cid, target, ok, detail, level="block"):
        self.cid = cid
        self.target = target
        self.ok = bool(ok)
        self.detail = detail
        self.level = level

    def as_dict(self):
        return {"cid": self.cid, "target": self.target, "ok": self.ok,
                "detail": self.detail, "level": self.level}


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════
def load_yaml(path):
    """读 YAML；解析失败抛异常由调用方降级处理（探测受阻 ≠ 实现缺陷）。"""
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _norm_ver(v):
    return (v or "").lstrip("v").strip()


# ═══════════════════════════════════════════════════════════════════════
# 契约 C1：工作地图 ⇄ config/harness.yaml#stages 逐项一致
# ═══════════════════════════════════════════════════════════════════════
def check_workmap_matches_stages(pkg_root=PKG_ROOT):
    """C1：work-map.yaml 镜像的闸门定义必须与 harness.yaml#stages 逐项相等。

    背景（真值分裂同型问题）：本包历史上出现过「yaml 写并行 / SOP 写串行」
    （R1/R7），并由守卫锁死错误一侧。本项防止**新增**的工作地图重蹈覆辙。
    """
    out = []
    wm_path = os.path.join(pkg_root, "references", "work-map.yaml")
    hy_path = os.path.join(pkg_root, "config", "harness.yaml")
    if not os.path.isfile(wm_path):
        return [Check("C1", wm_path, False, "工作地图文件不存在")]
    if not os.path.isfile(hy_path):
        return [Check("C1", hy_path, False, "harness.yaml 不存在")]

    try:
        wm = load_yaml(wm_path) or {}
        hy = load_yaml(hy_path) or {}
    except Exception as e:
        return [Check("C1", wm_path, False,
                      f"解析失败（{type(e).__name__}: {str(e)[:80]}）——探测受阻，不判漂移",
                      level="warn")]

    stages_yaml = hy.get("stages") or {}
    stages_map = wm.get("stages") or []
    if not isinstance(stages_map, list):
        return [Check("C1", wm_path, False, "work-map.yaml#stages 不是列表")]

    # 索引 yaml 侧：键是 int 或 str（YAML 会解析 "0" 为 int）
    ymap = {int(k): v for k, v in stages_yaml.items()} if isinstance(stages_yaml, dict) else {}

    if len(ymap) != len(stages_map):
        out.append(Check("C1", "work-map.yaml#stages",
                         False,
                         f"闸数不一致：harness.yaml={len(ymap)} 闸，work-map={len(stages_map)} 闸"))

    for item in stages_map:
        if not isinstance(item, dict):
            continue
        try:
            st = int(item.get("stage"))
        except (TypeError, ValueError):
            out.append(Check("C1", "work-map.yaml#stages", False,
                             f"非法 stage 值：{item.get('stage')!r}"))
            continue
        y = ymap.get(st)
        if not isinstance(y, dict):
            out.append(Check("C1", f"stage {st}", False,
                             f"harness.yaml#stages 缺 stage {st}"))
            continue

        # 逐项比对：name / members / gate / parallel
        if item.get("name") != y.get("name"):
            out.append(Check("C1", f"stage {st}.name", False,
                             f"work-map={item.get('name')!r} vs harness.yaml={y.get('name')!r}"))
        wm_members = [str(m) for m in (item.get("members") or [])]
        y_members = [str(m) for m in (y.get("members") or [])]
        if sorted(wm_members) != sorted(y_members):
            out.append(Check("C1", f"stage {st}.members", False,
                             f"work-map={wm_members} vs harness.yaml={y_members}"))
        if item.get("gate") != y.get("gate"):
            out.append(Check("C1", f"stage {st}.gate", False,
                             f"work-map={item.get('gate')!r} vs harness.yaml={y.get('gate')!r}"))
        if bool(item.get("parallel")) != bool(y.get("parallel")):
            out.append(Check("C1", f"stage {st}.parallel", False,
                             f"work-map={bool(item.get('parallel'))} vs harness.yaml={bool(y.get('parallel'))}"))

        # 本文件新增的四要素：不得为空（否则工作地图退化成只有名字的空壳）
        # ⚠ 判空须覆盖 **None / 空列表 / 空字符串 / 只有键没有条目** 四种形态：
        #   YAML 里 `acceptance:` 后面不跟列表项，解析结果是 **None** 而非 []。
        for field in ("input", "output", "acceptance", "branch"):
            val = item.get(field)
            empty = (val is None
                     or (isinstance(val, (list, tuple, dict, str)) and len(val) == 0))
            if empty:
                out.append(Check("C1", f"stage {st}.{field}", False,
                                 f"工作地图缺 {field}（四要素之一，不得为空）"))

    if not out:
        out.append(Check("C1", "references/work-map.yaml", True,
                         f"工作地图与 harness.yaml#stages 逐项一致（{len(ymap)} 闸），四要素齐备"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C2：文档里的体检项数口径必须等于真源 N
# ═══════════════════════════════════════════════════════════════════════
#: 体检项数的**合法写法**与**作用域限定**。
#:
#: ⚠ **作用域限定是硬要求**（本项第一版判据过宽，2026-11-11 实测误报 13 处）：
#:   包内文档里大量「X/Y」是**别的判据**的通过率（`verify-ref 12/12`、
#:   `552/552` 几何豁免、`3/3` 合成样本、`7/7` 用例数），
#:   还有大量「**第 N 项**」是**项序号**（`ensure_settings 第 12 项`）而非总数。
#:   ⇒ 只有「**明确指向体检**的总数表述」才是口径声明：
#:     R1 `X/X` 形式且**同一行**提到 ensure_settings（或「体检」）
#:     R2 `ensure_settings … N 项检查` 形式（明确说体检共 N 项）
#:   两种形式都必须与真源相等。
_COUNT_RATIO = re.compile(r"(\d+)\s*/\s*(\d+)")
_COUNT_ITEMS = re.compile(r"ensure_settings[^\n]{0,40}?(\d+)\s*项检查")
#: 「提到体检」的识别词（用于 R1 的同行限定）
_HEALTHCHECK_HINT = re.compile(r"ensure_settings|体检", re.I)


def collect_doc_count_mentions(pkg_root=PKG_ROOT, docs=None):
    """扫描文档里出现的**体检项数口径**，返回 [(文件, 行号, 原文, 声称值)]。

    纯函数（可测）：不读文件、不写文件——由调用方提供文档正文。
    只认 R1（同行含体检标识的 X/X）与 R2（ensure_settings … N 项检查）。
    """
    mentions = []
    for rel, text in (docs or {}).items():
        for i, line in enumerate(text.splitlines(), 1):
            # ── R1：X/X 形式，且同行提到体检 ────────────────────────
            if _HEALTHCHECK_HINT.search(line):
                for m in _COUNT_RATIO.finditer(line):
                    a, b = int(m.group(1)), int(m.group(2))
                    if a != b:
                        continue        # 「3/10」是占比，不是口径
                    mentions.append((rel, i, line.strip()[:160], a))
            # ── R2：ensure_settings … N 项检查 ─────────────────────
            for m in _COUNT_ITEMS.finditer(line):
                mentions.append((rel, i, line.strip()[:160], int(m.group(1))))
    # 同一行可能被两条规则各命中一次 ⇒ 按 (文件, 行, 值) 去重
    seen = set()
    uniq = []
    for item in mentions:
        key = (item[0], item[1], item[3])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def check_doc_count_consistency(pkg_root=PKG_ROOT, truth=None):
    """C2：文档里写的体检项数必须等于真源（ensure_settings.py 的 N）。

    背景：真实漂移实例——`references/loop-master-prompt.md` 写「须 22/22 全绿」、
    `references/delivery-spec.md` 与 `references/dual-loop-governance.md` 写「15/15」，
    而真源是 27 项。**无守卫** ⇒ 文档口径随版本推进持续漂移。
    """
    out = []
    es_path = os.path.join(pkg_root, "scripts", "ensure_settings.py")
    if truth is None:
        if not os.path.isfile(es_path):
            return [Check("C2", es_path, False, "ensure_settings.py 不存在")]
        try:
            src = open(es_path, encoding="utf-8").read()
        except Exception as e:
            return [Check("C2", es_path, False, f"读取失败：{e}", level="warn")]
        m = re.search(r"^N\s*=\s*(\d+)", src, re.M)
        if not m:
            return [Check("C2", es_path, False, "未找到 N = <项数> 声明", level="warn")]
        truth = int(m.group(1))

    # 扫描面：references/ + agents/ 下的 md（CHANGELOG 是历史记录，不在其中——
    #   历史版本号的数字出现在 CHANGELOG 是**正常的**，不是漂移）
    docs = {}
    for sub in ("references", "agents"):
        d = os.path.join(pkg_root, sub)
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in (".git", "packages", "__pycache__")]
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(root, fn)
                try:
                    docs[os.path.relpath(fp, pkg_root)] = open(fp, encoding="utf-8",
                                                              errors="replace").read()
                except Exception:
                    continue

    mentions = collect_doc_count_mentions(pkg_root, docs)
    bad = [(r, ln, txt, v) for (r, ln, txt, v) in mentions if v != truth]
    for (r, ln, txt, v) in bad:
        out.append(Check("C2", f"{r}:{ln}", False,
                         f"文档写 {v} 项，真源是 {truth} 项 —— 口径漂移：{txt}"))
    if not out:
        out.append(Check("C2", "references/ + agents/", True,
                         f"文档体检项数口径全部等于真源 {truth} 项（扫描 {len(mentions)} 处提及）"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C3：交付三件套齐备性（文件级）
# ═══════════════════════════════════════════════════════════════════════
#: 交付三件套的三个组成部分 → 判定用的文件名模式（大小写不敏感）
#: 依据：references/delivery-spec.md#1（三件套清单）
DELIVERY_TRIPLETS = [
    ("deck", "成品 PPTX", (".pptx",)),
    ("change_note", "逐页修改说明", (".md",)),
    ("checklist", "验收自检清单", (".md",)),
]


def classify_delivery_files(names):
    """把文件名分类到三件套的三个槽位。

    纯函数（可测）。规则（从简、可解释）：
      · `.pptx` → deck 槽
      · 文件名含「修改说明 / 变更说明 / change」→ change_note 槽
      · 文件名含「自检 / 验收 / checklist」→ checklist 槽
      · 纯中文名（含「修改说明」/「验收」字样）按上述关键词命中
    """
    buckets = {"deck": [], "change_note": [], "checklist": []}
    for n in names:
        low = n.lower()
        if low.endswith(".pptx"):
            buckets["deck"].append(n)
            continue
        if any(k in n for k in ("修改说明", "变更说明", "逐页修改")) or "change" in low:
            buckets["change_note"].append(n)
        if any(k in n for k in ("自检", "验收", "清单")) or "checklist" in low:
            buckets["checklist"].append(n)
    return buckets


def check_delivery_triplet(out_dir=None):
    """C3：交付三件套是否齐备（**仅文件级存在性**）。

    边界（重要）：本项**只查文件在不在**，**不查内容对不对**——
    内容合规由 verify_deck.py（唯一裁判）与人工终审负责。
    「三件缺一不算完成」这条纪律此前**无任何脚本执行面**，本项补上。
    """
    out = []
    if not out_dir:
        return [Check("C3", "<未指定输出目录>", False,
                      "未提供 --out-dir，跳过交付三件套检查（不是缺陷，是未检查）",
                      level="warn")]
    if not os.path.isdir(out_dir):
        return [Check("C3", out_dir, False, f"目录不存在：{out_dir}")]

    try:
        names = [f for f in os.listdir(out_dir) if not f.startswith(".")]
    except Exception as e:
        return [Check("C3", out_dir, False, f"列目录失败：{e}")]

    buckets = classify_delivery_files(names)
    for slot, label, _ in DELIVERY_TRIPLETS:
        hit = buckets.get(slot) or []
        if hit:
            out.append(Check("C3", f"{out_dir}[{slot}]", True,
                             f"{label} 齐备：{', '.join(sorted(hit)[:3])}"))
        else:
            out.append(Check("C3", f"{out_dir}[{slot}]", False,
                             f"{label} 缺失（交付三件缺一不算完成）"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C4：闸间就绪（闸2/3/4 的前置产物）
# ═══════════════════════════════════════════════════════════════════════
#: 每个闸的就绪判据：需要上游留下的**证据标记**
#: 证据从工作区状态文件读（loopB_state.json / task_state.json / 洞察载体）
#: 说明：这是**软就绪**——缺失即提示「上游未就绪」，不阻断（真阻断由 gate/make-gate 负责）。
GATE_READINESS = {
    1: {"name": "闸2 设计",
        "requires": "闸1 冻结十项（gate1-check 通过）+ task_mode 已登记",
        "probe": "gate1-check"},
    2: {"name": "闸3 成稿",
        "requires": "闸2 蓝图已落盘（成员产物存在且非空）",
        "probe": "verify-artifact"},
    3: {"name": "闸4 交付",
        "requires": "闸3 页表齐备 + 成品 PPTX 存在",
        "probe": "gate"},
}


def check_gate_readiness(stage, workspace=None):
    """C4：某闸的前置产物是否就绪（**软就绪·提示级**）。

    背景（R6 同型）：闸1 有 `gate1-check`，闸2/3/4 无同级检查 ⇒
    上游缺失在下游才暴露（表现为蓝图/页表突然缺项，难回溯）。
    本项为**提示级**：缺失不阻断（真阻断在 gate / make-gate），
    目的是让「上游没做完」在**当下**可见，而不是在下游爆炸。
    """
    out = []
    spec = GATE_READINESS.get(int(stage))
    if not spec:
        return [Check("C4", f"stage {stage}", False,
                      f"非法闸号 {stage}（合法 0–4）")]

    # 闸1 特殊：直接复用既有唯一判据 gate1-check（不重造轮子）
    # ⚠ 该分支须在「未提供工作区」早退**之前**判断——否则闸1 的检查项目标
    #   里不会出现 "gate1-check"，可发现性丢失（对 LLM 等于该闸无判据）。
    if int(stage) == 1:
        if not workspace:
            return [Check("C4", "stage 1 / gate1-check", True,
                          f"{spec['requires']}；未提供 --workspace，未探测"
                          f"——按未检查登记，不判缺陷", level="warn")]
        gate1 = os.path.join(PKG_ROOT, "scripts", "harness.py")
        try:
            import subprocess
            r = subprocess.run([sys.executable, gate1, "gate1-check", "--workspace", workspace],
                               capture_output=True, text=True, timeout=120)
            ok = (r.returncode == 0)
            out.append(Check("C4", f"stage 1 / gate1-check", ok,
                             f"{spec['requires']}；gate1-check rc={r.returncode}"))
        except Exception as e:
            out.append(Check("C4", "stage 1 / gate1-check", True,
                             f"探测受阻（{type(e).__name__}）——不判缺陷", level="warn"))
        return out

    if not workspace:
        return [Check("C4", f"stage {stage}", True,
                      f"{spec['name']} 就绪度未探测（未提供 --workspace）——按未检查登记，不判缺陷",
                      level="warn")]

    # 闸3/闸4：从工作区状态找就绪证据（找不到即提示，不阻断）
    state_ok = False
    detail = "未在工作区找到就绪证据（task_state.json / loopB_state.json 缺失或无对应标记）"
    for rel in (".workbuddy/task_state.json", ".workbuddy/loopB_state.json"):
        fp = os.path.join(workspace, rel)
        if not os.path.isfile(fp):
            continue
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if int(stage) == 2 and data.get("current_stage", 0) >= 2:
            state_ok = True
            detail = f"{rel} 记录 current_stage={data.get('current_stage')}（≥2 ⇒ 闸2 已过）"
            break
        if int(stage) == 3 and data.get("current_stage", 0) >= 3:
            state_ok = True
            detail = f"{rel} 记录 current_stage={data.get('current_stage')}（≥3 ⇒ 闸3 已过）"
            break
    out.append(Check("C4", f"stage {stage}", state_ok,
                     f"{spec['name']}：{spec['requires']}；{detail}",
                     level="block" if state_ok else "warn"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C5：MERGE_GATE 门禁的**可执行性**
# ═══════════════════════════════════════════════════════════════════════
def check_merge_gate_enforceable(pkg_root=PKG_ROOT):
    """C5：`.learnings/MERGE_GATE.yaml` 声明的门禁是否**真被执行器执行**。

    背景（一手实证）：MERGE_GATE.yaml 头注自陈「机器暂无强制执行器」，
    而实测 LEARNINGS.md 23 条里 `candidate` 状态 **0 条**——
    即「登记即生效」的旧行为仍在实际发生 ⇒ 晋升门槛（复发≥3 或 ack）形同虚设。
    本项**不修改**任何学习条目，只**核验**执行器是否在位且被调用。
    """
    out = []
    mg_path = os.path.join(pkg_root, ".learnings", "MERGE_GATE.yaml")
    ex_path = os.path.join(pkg_root, "scripts", "check_contracts.py")
    lrn_path = os.path.join(pkg_root, ".learnings", "LEARNINGS.md")
    if not os.path.isfile(mg_path):
        return [Check("C5", mg_path, False, "MERGE_GATE.yaml 不存在")]
    if not os.path.isfile(ex_path):
        return [Check("C5", ex_path, False, "MERGE_GATE 执行器缺失（本项即执行器）")]

    # 执行器在位 = 本文件提供 merge-gate 子命令
    src = open(ex_path, encoding="utf-8").read()
    has_exec = "def cmd_merge_gate" in src or "merge-gate" in src
    out.append(Check("C5", "scripts/check_contracts.py#merge-gate", has_exec,
                     "MERGE_GATE 执行器在位" if has_exec else "MERGE_GATE 无执行器（声明面空转）"))

    # 实际状态分布：candidate 必须真的在用，否则门禁从未被触发过
    if os.path.isfile(lrn_path):
        try:
            text = open(lrn_path, encoding="utf-8").read()
        except Exception:
            text = ""
        n_cand = text.count("**Status**: candidate")
        n_total = len(re.findall(r"^## \[LRN-", text, re.M))
        # 提示级：candidate 为 0 说明**尚未有候选条目**，不等于门禁失效
        out.append(Check("C5", ".learnings/LEARNINGS.md", True,
                         f"学习条目 {n_total} 条，其中 candidate {n_cand} 条"
                         f"（candidate=0 表示当前无候选条目，非门禁失效）",
                         level="warn"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C6：MERGE_GATE 晋升门禁的**执行器**（把声明面变成执行面）
# ═══════════════════════════════════════════════════════════════════════
#: 学习条目的状态词表（与 .learnings/LEARNINGS.md 头部既有词表一致）
LEARN_STATUS_VALUES = ("candidate", "applied", "manual-only", "pending")

#: 条目头解析：`**Status**: applied`
_LEARN_ENTRY_RE = re.compile(
    r"^## \[(LRN-[^\]]+)\][^\n]*\n(.*?)(?=^## \[LRN-|\Z)", re.M | re.S)
_LEARN_STATUS_RE = re.compile(r"\*\*Status\*\*:\s*([a-z\-]+)")
# ⚠ v3.31.0 修正（**判据级缺陷 · 现场实证**）：Tags 字段的真实写法是
#   `- Tags: A, B, C`（Metadata 段的列表项），而本正则此前只认 `**Tags**: A, B, C`
#   ⇒ **LEARNINGS.md 里 24 条的 Tags 全部没被解析** ⇒ 候选条目的 tags 恒为 []
#   ⇒ `classify_learning_promotion` 的「同型（Tags 交集）累计」恒为 0
#   ⇒ **MERGE_GATE 的「同型 ≥3 复发」路径实质空转**（只有 ack 一条路能走）。
#   ⇒ 这正是「声明层≠执行层」的又一实例：字段写得对，解析器读不到。
#   修法：同时接受两种写法（`-\s*Tags:` 与 `**Tags**:`）。
_LEARN_TAGS_RE = re.compile(r"(?:^|\n)\s*(?:-\s*)?(?:\*\*)?Tags(?:\*\*)?:\s*(.+)")


def parse_learn_entries(text):
    """解析 LEARNINGS.md 的条目 → [(id, status, tags)]。

    纯函数（可测）：只吃文本，不读文件。
    """
    out = []
    for m in _LEARN_ENTRY_RE.finditer(text or ""):
        eid = m.group(1)
        body = m.group(2)
        sm = _LEARN_STATUS_RE.search(body)
        status = sm.group(1) if sm else None
        tm = _LEARN_TAGS_RE.search(body)
        tags = [t.strip() for t in tm.group(1).split(",")] if tm else []
        out.append((eid, status, tags))
    return out


def classify_learning_promotion(entries, recurrence_threshold=3, ack_ids=()):
    """判定每条学习条目的**晋升资格**（纯函数，可测）。

    晋升规则（取自 .learnings/MERGE_GATE.yaml#promote_rules）：
      · `candidate` 条目须满足「同型经验累计 ≥ recurrence_threshold」**或**
        「管家节点显式 ack（ack_ids 含该条 id）」才可晋升为 applied；
      · 其余状态不在本判据管辖内（applied / manual-only / pending 维持原状）。

    同型判定：用 **Tags 集合的交集非空** 作为「同型」的可操作代理——
    ⚠ 这是**近似**（不是语义判定）：同 Tag 即视为同型，宁可多要求一次 ack，
      也不误把不同型经验合并计数（假合并比漏合并代价更高）。
    """
    ack = set(ack_ids or ())
    # 同型聚类：按 Tag 分组
    tag_groups = {}
    for eid, status, tags in entries:
        if status != "candidate":
            continue
        for t in tags:
            tag_groups.setdefault(t, []).append(eid)

    results = []
    for eid, status, tags in entries:
        if status != "candidate":
            continue
        same = set()
        for t in tags:
            same.update(tag_groups.get(t, []))
        # 含自身
        count = len(same)
        promoted = (count >= recurrence_threshold) or (eid in ack)
        results.append({
            "id": eid,
            "tags": tags,
            "same_type_count": count,
            "threshold": recurrence_threshold,
            "acked": eid in ack,
            "promotable": promoted,
            "reason": (f"同型累计 {count} ≥ {recurrence_threshold}" if count >= recurrence_threshold
                       else ("管家节点已 ack" if eid in ack
                             else f"同型累计 {count} < {recurrence_threshold} 且未 ack ⇒ 维持 candidate")),
        })
    return results


def run_merge_gate(pkg_root=PKG_ROOT, ack_ids=(), lrn_path=None):
    """执行 MERGE_GATE 晋升门禁的**只读判定**。

    ⚠ 本函数**不改任何文件**（不改 Status、不写门禁结果）：
      「候选条目是否已具备晋升资格」的判定与「实际晋升」是两件事——
      实际晋升是一次**显式的人的动作**（管家节点 ack 或编辑条目），
      脚本只负责回答「哪几条够格了」（可发现性 + 防自欺）。
    """
    out = []
    mg_path = os.path.join(pkg_root, ".learnings", "MERGE_GATE.yaml")
    lrn = lrn_path or os.path.join(pkg_root, ".learnings", "LEARNINGS.md")
    if not os.path.isfile(mg_path):
        return [Check("C6", mg_path, False, "MERGE_GATE.yaml 不存在")]
    if not os.path.isfile(lrn):
        return [Check("C6", lrn, False, "LEARNINGS.md 不存在")]
    try:
        mg = load_yaml(mg_path) or {}
    except Exception as e:
        return [Check("C6", mg_path, False, f"MERGE_GATE.yaml 解析失败：{e}", level="warn")]
    pr = mg.get("promote_rules") or {}
    thr = int(pr.get("recurrence_threshold", 3) or 3)

    try:
        text = open(lrn, encoding="utf-8").read()
    except Exception as e:
        return [Check("C6", lrn, False, f"读取失败：{e}")]

    entries = parse_learn_entries(text)
    cands = [e for e in entries if e[1] == "candidate"]

    # ⚠ **grandfather 条款**：MERGE_GATE.yaml#legacy_grandfather 明确
    #   「截止日之前的既有条目按已登记处理，不回溯改 Status」。
    #   ⇒ 缺 Status 字段的条目**不是违规**，除非它晚于截止日。
    #   判据：缺 Status 且 id 日期 > 截止日 ⇒ 判红；否则计为 legacy（提示级）。
    cutoff = str((mg.get("legacy_grandfather") or {}).get("cutoff") or "")
    legacy_cutoff = cutoff.replace("-", "")   # 2026-11-08 → 20261108

    def _id_date(eid):
        m = re.search(r"LRN-(\d{8})-", eid)
        return m.group(1) if m else ""

    bad_status = []
    legacy_nostatus = []
    for eid, status, _tags in entries:
        if status is None:
            d = _id_date(eid)
            if legacy_cutoff and d and d > legacy_cutoff:
                bad_status.append((eid, "<无 Status>"))
            else:
                legacy_nostatus.append(eid)
        elif status not in LEARN_STATUS_VALUES:
            bad_status.append((eid, status))

    if bad_status:
        out.append(Check("C6", ".learnings/LEARNINGS.md", False,
                         f"{len(bad_status)} 条 Status 非法或缺字段（晚于 grandfather 截止日 "
                         f"{cutoff or '未设'}）：{bad_status[:5]}"))
    else:
        out.append(Check("C6", ".learnings/LEARNINGS.md", True,
                         f"{len(entries)} 条学习条目 Status 全部合法"
                         f"（candidate {len(cands)} 条；"
                         f"legacy 无 Status {len(legacy_nostatus)} 条，按 grandfather 条款豁免）"))

    if not cands:
        out.append(Check("C6", "candidate 晋升门禁", True,
                         "当前无 candidate 条目（无待晋升项）——非门禁失效"))
        return out

    res = classify_learning_promotion(entries, thr, ack_ids)
    ready = [r for r in res if r["promotable"]]
    notready = [r for r in res if not r["promotable"]]
    if ready:
        # ⚠ v3.31.0（**判据补齐 · 能红反例**）：已够格却仍挂 candidate ⇒ 判红。
        #   缘由：「实际晋升是显式的人的动作」，脚本不代劳 ⇒ 若脚本**只报不拦**，
        #   一条 ack 过的条目可以永远挂着 candidate ⇒ 而 candidate 又**不进待办清单**
        #   （MERGE_GATE.yaml 明文）⇒ 该条目就**永久失踪**了。
        #   ⇒ 「够格」与「已晋升」之间必须有一道机器闸，否则门禁是装饰。
        out.append(Check("C6", "candidate 晋升门禁", False,
                         f"{len(ready)}/{len(cands)} 条 candidate **已够格却仍挂 candidate**："
                         f"{[(r['id'], r['reason']) for r in ready][:5]}"
                         f"——该晋升未落地（够格 ≠ 已晋升）"))
    else:
        # ⚠ v3.31.0 语义修正（**原实现判红是判据级错误**）：
        #   `candidate` 未够格是**合法状态**——MERGE_GATE.yaml 的门禁语义是
        #   「未过闸 = 未生效」，即 candidate 条目**本来就不该进下一轮待办**。
        #   ⇒ 「未够格」不是缺陷，判红 = 把「尚未到晋升时机」误报为「门禁失效」。
        #   门禁真正要拦的是**反向**情形：**已够格却仍挂着 candidate**（该晋升没晋升）。
        #   本条判据因此改为：未够格 ⇒ 绿（合法状态），只报出「待凑够条件」的清单。
        out.append(Check("C6", "candidate 晋升门禁", True,
                         f"{len(notready)}/{len(cands)} 条 candidate 未够格晋升"
                         f"（同型累计 < {thr} 且未 ack）——**合法状态**："
                         f"未过闸 = 未生效，不进下一轮待办清单"
                         f"{'；明细：' + str([(r['id'], r['reason']) for r in notready][:5]) if notready else ''}"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C7：认可样例库的一致性（sha256 漂移检测）
# ═══════════════════════════════════════════════════════════════════════
#: 样例库条目格式（YAML 块或 Markdown 表格行均可解析）——
#: 只取**可核对的字段**，不重定义收录标准（标准在 README §1）。
_EXAMPLE_ID_RE = re.compile(r"\b(EX-\d{8}-\d{3})\b")
_EXAMPLE_SHA_RE = re.compile(r"\b([0-9a-f]{64})\b")


def check_approved_examples(pkg_root=PKG_ROOT):
    """C7：认可样例库的文件校验和是否与实际一致（样例漂移检测）。

    背景：样例库一旦入库就成为「标准参照」，若被改写而不更新 sha256，
    标准会静默漂移 ⇒ 与本包治的「真值分裂」同型。
    空库是**合法状态**（尚无被认可的产出留痕），不判红。
    """
    out = []
    ex_dir = os.path.join(pkg_root, "references", "approved-examples")
    readme = os.path.join(ex_dir, "README.md")
    if not os.path.isdir(ex_dir):
        return [Check("C7", ex_dir, False, "认可样例库目录不存在")]
    if not os.path.isfile(readme):
        return [Check("C7", readme, False, "认可样例库 README 缺失")]

    # 收集登记条目：EX-xxx 编号 + 邻近的 sha256
    try:
        text = open(readme, encoding="utf-8").read()
    except Exception as e:
        return [Check("C7", readme, False, f"读取失败：{e}")]

    ids = _EXAMPLE_ID_RE.findall(text)
    shas = _EXAMPLE_SHA_RE.findall(text)
    if not ids:
        out.append(Check("C7", "references/approved-examples/", True,
                         "认可样例库为空（尚无被用户认可并留痕的产出）——合法状态，不判缺陷"))
        return out

    # 有条目时：编号数应与校验和数一致（每个样例一条）
    if len(ids) != len(shas):
        out.append(Check("C7", "references/approved-examples/", False,
                         f"样例编号数 {len(ids)} ≠ 校验和数 {len(shas)}"
                         f"（每个样例须有且仅有一个 sha256）"))
    else:
        out.append(Check("C7", "references/approved-examples/", True,
                         f"认可样例库 {len(ids)} 条，编号与校验和数量一致"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C8：包内文件引用的**可达性**（悬空引用检测）
# ═══════════════════════════════════════════════════════════════════════
#: 只检查带**明确包内路径前缀**的引用形态，避免误报散文里的普通词：
#:   `references/xxx.md` · `scripts/xxx.py` · `config/xxx.yaml` ·
#:   `agents/xxx.md` · `.learnings/xxx.md` · `skills/xxx`
#: ⚠ **不含 `outputs/`**：该目录**不随包跟踪**（git ls-files outputs/ 为空），
#:   是历史归档工作区（诊断报告 / 收批证据）⇒ 引用它们**不算悬空**
#:   （首版把它算进去 ⇒ 22 处假阳性 ⇒ 判据过宽 = 守卫会被绕过）。
#: ⚠ 排除：含 `**` 的 glob（目录级说明）、`<包>`/`<工作区>` 占位符、
#:   带 `(` `)` 的命令片段、明显是举例的 `scripts/test_*.py`。
_REF_PATH_RE = re.compile(
    r"(?<![\w/*])((?:references|scripts|config|agents|\.learnings|skills)/"
    r"[A-Za-z0-9_./\-一-鿿]+\.(?:md|py|yaml|yml|json|txt))")


def collect_dangling_refs(pkg_root=PKG_ROOT, docs=None):
    """扫描文档中的包内路径引用，返回**不存在的**引用列表（纯函数，可测）。

    背景（本轮现场实证三次）：
      ① `references/approved-examples/README.md` 引用 `LRN-20261111-024`
         —— 该学习条目当时**并不存在**（悬空引用）；
      ② `references/work-map.yaml` 注释写「人类阅读：references/work-map.md
         （由 next --render 生成）」—— 该文件**不存在**，且 `next` **无**该选项；
      ③ `scripts/check_contracts.py` 头部写 `scripts/sample_fixtures.py`——
         该文件虽存在，但语义被写错（它是既有样本定位层，非认可样例库专用）。

    ⇒ 「文档说的」与「真实存在的」长期各说各话 ⇒ 冷启动的 AI 顺着文档找文件会扑空。
    本项把「引用可达性」变成机器判据。

    ── 收窄历程（假阳性必须为零）────────────────────────────────────────────
      首版 22 处假阳性 ⇒ 三轮收窄：
      ① 去掉 `outputs/`（不随包跟踪的历史归档区）；
      ② 排除**前瞻性引用**（「首次接单时按需建 xxx」「原文依据见 xxx（含 PDF 归档路径）」
         「本地摘要文件 | xxx」——说的是**将来要有**的文件）；
      ③ 排除 **CHANGELOG**（历史变更记录，里面的路径是**当时**的状态，
         且大量是被删除/被改名文件的快照）。
      ⇒ 收窄后只剩**真悬空**：本轮自己引入的 `references/work-map.md`。
    """
    if docs is None:
        docs = []
        for sub in ("references", "agents", "config", "scripts", ".learnings"):
            d = os.path.join(pkg_root, sub)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if fn.endswith((".md", ".yaml", ".yml")):
                    docs.append(os.path.join(d, fn))
        for fn in ("README.md", "CHANGELOG.md"):
            p = os.path.join(pkg_root, fn)
            if os.path.isfile(p):
                docs.append(p)

    #: 前瞻性引用标记：该行在说「将来要建的文件」，不是「现在应存在的文件」
    _FUTURE_MARKERS = ("首次接单", "按需建", "待建", "将来", "尚未建立", "创建后",
                       "本域尚无", "原文依据见", "含 PDF 归档路径", "本地摘要文件",
                       "本地归档", "示例", "例如", "eg.", "如 `")
    #: **引述标记**：该行在**转述旧文本**（如"初版注释写 xxx（已更正）"），
    #:   提到的路径是「历史状态」，不是「当前应存在的文件」⇒ 不判。
    _QUOTE_MARKERS = ("初版", "更正", "此前写", "原为", "曾写", "旧注释",
                      "已改为", "改为「", "原写")

    dangling = []
    for doc in docs:
        rel_doc = os.path.relpath(doc, pkg_root)
        # CHANGELOG 是**历史变更记录** ⇒ 其中的路径是「当时」的状态，不判
        if rel_doc == "CHANGELOG.md":
            continue
        try:
            text = open(doc, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        lines = text.splitlines()
        seen = set()
        for m in _REF_PATH_RE.finditer(text):
            ref = m.group(1)
            if ref in seen:
                continue
            seen.add(ref)
            # 豁免形态
            if "**" in ref or "<" in ref or "*" in ref:
                continue
            # 含 glob 通配（test_*.py 等）→ 跳过
            if "*" in os.path.basename(ref):
                continue
            if os.path.exists(os.path.join(pkg_root, ref)):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
            if any(k in line for k in _FUTURE_MARKERS):
                continue
            if any(k in line for k in _QUOTE_MARKERS):
                continue
            dangling.append({"doc": rel_doc, "line": line_no, "ref": ref})
    return dangling


def check_dangling_refs(pkg_root=PKG_ROOT):
    """C8：文档中的包内路径引用是否都真实存在。"""
    out = []
    dangling = collect_dangling_refs(pkg_root)
    if dangling:
        for d in dangling:
            out.append(Check("C8", f"{d['doc']}:{d['line']}", False,
                             f"引用了不存在的包内路径 `{d['ref']}`——"
                             f"冷启动顺着文档找文件会扑空"))
    else:
        out.append(Check("C8", "references/ + agents/ + config/ + scripts/",
                         True, "包内路径引用全部可达（无悬空引用）"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 契约 C9：工作地图 actions 段的命令**必须已注册**（可照跑性）
# ═══════════════════════════════════════════════════════════════════════
#: 从动作串里提取 harness.py 子命令名（兼容 `harness.py xxx` 与 `python3 scripts/harness.py xxx`）
_ACTION_CMD_RE = re.compile(
    r"(?:^|\s)(?:python3\s+)?(?:scripts/)?harness\.py\s+([a-z][a-z0-9\-]*)")


def check_action_commands_exist(pkg_root=PKG_ROOT):
    """C9：工作地图 `actions` 段给出的命令串，其子命令必须**真的注册**在 harness.py。

    背景（v3.31.0 现场实证）：
      `references/work-map.yaml#actions` 的定位是「**可直接照跑**的命令串」——
      冷启动的 AI 会照抄执行。若某条命令指向已删除/未实现的子命令，
      AI 照跑即失败 ⇒ 工作地图沦为「看起来能用但跑不通」的文档。
      ⇒ 与 C8 同族（C8 管「引用的文件存在」，C9 管「引用的命令可用」）。

    判据：从 harness.py 的 doctor 注册表取子命令名集合，
      与 actions 段提取出的命令名取差集；差集非空 ⇒ 判红。
    """
    out = []
    wm_path = os.path.join(pkg_root, "references", "work-map.yaml")
    hrns = os.path.join(pkg_root, "scripts", "harness.py")
    if not os.path.isfile(wm_path):
        return [Check("C9", wm_path, False, "工作地图不存在")]
    if not os.path.isfile(hrns):
        return [Check("C9", hrns, False, "harness.py 不存在")]
    try:
        wm = load_yaml(wm_path) or {}
    except Exception as e:
        return [Check("C9", wm_path, False, f"工作地图解析失败：{e}", level="warn")]
    actions = wm.get("actions") or {}
    if not isinstance(actions, dict):
        return [Check("C9", wm_path, False, "工作地图 actions 段不是映射", level="warn")]

    # 取 doctor 注册表（子命令名集合）
    try:
        import subprocess
        r = subprocess.run([sys.executable, hrns, "doctor"],
                           capture_output=True, text=True, timeout=120)
        doc = json.loads(r.stdout)
        reg = {c.get("name") for c in (doc.get("commands") or []) if c.get("name")}
    except Exception as e:
        # 探测受阻 ≠ 实现缺陷 ⇒ 提示级，不判红（同本包「假阳性必须为零」纪律）
        return [Check("C9", hrns, True,
                      f"doctor 探测受阻（{type(e).__name__}）——未做命令可达性比对，不判缺陷",
                      level="warn")]

    missing = []
    for group, cmds in actions.items():
        if not isinstance(cmds, list):
            continue
        for c in cmds:
            if not isinstance(c, str):
                continue
            for m in _ACTION_CMD_RE.finditer(c):
                cmd = m.group(1)
                if cmd not in reg:
                    missing.append((group, cmd, c))
    if missing:
        for g, cmd, c in missing:
            out.append(Check("C9", f"actions.{g}", False,
                             f"命令串引用了未注册的子命令 `{cmd}`：{c}"
                             f"——冷启动照跑会失败"))
    else:
        total = sum(len(v) for v in actions.values() if isinstance(v, list))
        out.append(Check("C9", "references/work-map.yaml#actions", True,
                         f"actions 段 {total} 条命令串引用的子命令全部已注册（{len(reg)} 个可用）"))
    return out


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════
def run_all(pkg_root=PKG_ROOT, out_dir=None, stage=None, workspace=None, ack_ids=()):
    """跑全部契约检查，返回 (checks, rc)。"""
    checks = []
    checks.extend(check_workmap_matches_stages(pkg_root))
    checks.extend(check_doc_count_consistency(pkg_root))
    if out_dir is not None:
        checks.extend(check_delivery_triplet(out_dir))
    if stage is not None:
        checks.extend(check_gate_readiness(stage, workspace))
    checks.extend(check_merge_gate_enforceable(pkg_root))
    checks.extend(run_merge_gate(pkg_root, ack_ids))
    checks.extend(check_approved_examples(pkg_root))
    checks.extend(check_dangling_refs(pkg_root))
    checks.extend(check_action_commands_exist(pkg_root))

    rc = 0
    for c in checks:
        if not c.ok and c.level == "block":
            rc = 1
    return checks, rc


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="契约检查器：把「仅有文字说明」的要求转为机器判据（只做确定性判定）")
    ap.add_argument("--pkg-root", default=PKG_ROOT, help="包根（默认由脚本位置推导）")
    ap.add_argument("--out-dir", help="交付目录（检查交付三件套齐备性）")
    ap.add_argument("--stage", type=int, help="检查某闸的前置就绪度（0–4）")
    ap.add_argument("--workspace", help="工作区（配合 --stage 探测就绪证据）")
    ap.add_argument("--ack", action="append", default=[],
                    help="管家节点显式 ack 的学习条目 id（可重复）；"
                         "满足 ack 的 candidate 即具备晋升资格")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--evidence-out", help="把检查记录写到该文件（供跨轮次对账）")
    args = ap.parse_args(argv)

    checks, rc = run_all(args.pkg_root, args.out_dir, args.stage, args.workspace, args.ack)

    if args.json:
        print(json.dumps({
            "schema": "contract-check/1",
            "pkg_root": args.pkg_root,
            "summary": {
                "total": len(checks),
                "passed": sum(1 for c in checks if c.ok),
                "failed": sum(1 for c in checks if not c.ok),
                "blocking_failed": sum(1 for c in checks if not c.ok and c.level == "block"),
            },
            "checks": [c.as_dict() for c in checks],
        }, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            mark = "✓" if c.ok else ("🔴" if c.level == "block" else "⚠")
            print(f"{mark} [{c.cid}] {c.target}")
            print(f"     {c.detail}")

    if args.evidence_out:
        try:
            with open(args.evidence_out, "w", encoding="utf-8") as f:
                json.dump({
                    "schema": "contract-check/1",
                    "summary": {
                        "total": len(checks),
                        "passed": sum(1 for c in checks if c.ok),
                        "failed": sum(1 for c in checks if not c.ok),
                    },
                    "checks": [c.as_dict() for c in checks],
                }, f, ensure_ascii=False, indent=2)
            print(f"\n证据已落盘：{args.evidence_out}")
        except Exception as e:
            print(f"⚠ 证据落盘失败：{e}", file=sys.stderr)

    return rc


if __name__ == "__main__":
    sys.exit(main())

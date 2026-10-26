#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
insight_carrier.py —— 洞察载体判定层（v3.21.0 · 多专家单载体）

为什么要有这个文件（2026-10-26 立项实测）：
  闸 2「严真奥 → 苏学法」与闸 3「苏学法 ∥ 屠明熙」并行，但产物落**三处**
  （evidence/证据包.md、<task_id>__pedagogy-architect.md、_search_requests/*.md）
  ⇒ 同一目标（PPT 某页 / 某个知识模块）上的**内容 / 教学 / 视觉**建议分散无共同落点：
    ① 冲突无处显形（严真奥要加证据、苏学法要拆页、屠明熙要加图，三者可能互斥）；
    ② 主理人合并靠 800 字摘要 ⇒ 必然丢信息；
    ③ 追溯断裂（这条洞察谁提的、改没改、为何没改散在三处）。

  本模块把三轴的洞察汇入**同一份载体**（carrier），载体是全程唯一事实源：
  轮报、冻结、验收全部从载体投影。

★ 关键纪律：「目标上互斥、载体上共享」
  现有 spawn 纪律 = 「并行任务边界必须互斥无交集」；
  本方案 = **同轴内**不重复做（那才是重复劳动），**同一目标**上的多轴条目并存
  （三轴看的是同一份内容的三个侧面，合起来才是完整洞察）。
  ⇒ 规则 R1 只检出「多轴并存 ⇒ 待人工裁决」，**不判是否互斥**——互斥是语义判断，归人。

设计纪律（与 scripts/loop_contract.py 同构，不另立一套）：
  1. **禁硬编码**：枚举、必填字段、规则、ID 格式全在 references/insight-carrier.yaml；
     缺键/空/非法一律**告警 + 显式回落**，回落写进 notes 由调用方透出
     （静默回落 = 本包反复吃亏的"看起来有护栏、实际不设防"）。
  2. **只做确定性判定**：字段/枚举/唯一性/集合比对/计数/格式/守恒。
     洞察质量、"该不该改"、冲突是否真互斥，一律**不判**——归主理人与用户。
  3. **诚实边界写进返回值**：判定函数都回 note，把"这次没判定/降级了"一并交出去。

⚠ 三处**刻意**的实现选择（都是本包踩过坑换来的，改动前先读注释）：
  ① 回落表用**元组列表**而非字典字面量：
     ensure_settings 第 18 项（死配置巡检）用 AST 收集真实读取点，其中第③种形态是
     **字典字面量的字符串键**——若本表写成字典，它里面这些键名会被当成"有代码读取者"，
     于是**回落表自己把死配置刷成绿色**：即使真正的读取点被删掉，巡检也看不出来。
  ② 取值一律在调用点写成 `node.get("键")` 的规范形式：
     同上——键名当普通实参传进 helper，AST 收集不到 ⇒ 接线了却检测不出来。
  ③ **返回标量**（不是 `(值, 是否回落)` 元组）：
     元组对布尔调用点是恒真陷阱——`if not (True, False)` 恒为 False，
     开关类判据会**永不生效**（v3.20.0 实测出的 P0 缺陷，同型复发即事故）。

用法（被 harness.py 的 insights 子命令组调用；也可直接跑本文件做自检）：
    python3 scripts/insight_carrier.py --self-check
"""

import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
CFG_REL = os.path.join("references", "insight-carrier.yaml")

# 内置回落值——**只在配置缺失/非法时启用**，且启用必须写 note。
# ⚠ 刻意用元组列表（见文件头 ①）：写成字典字面体会被第 18 项 AST 收集当成"有读取者"。
_FALLBACK = [
    ("target_kind", ["page", "module"]),
    ("axis", ["content", "pedagogy", "visual"]),
    ("severity", ["P0", "P1", "P2"]),
    ("status", ["proposed", "accepted", "rejected", "deferred"]),
    ("judge_mode", ["机", "人", "机+人"]),
    ("required", ["insight_id", "target_id", "target_kind", "axis", "expert",
                  "proposal", "rationale", "severity", "status"]),
    ("id_pattern", r"^(?P<target>.+?)-(?P<axis>[CPV])-(?P<seq>\d+)$"),
    ("module_id_pattern", r"^(?!\d+$).+$"),
    ("freeze_algorithm", "sha256"),
]
_FB = dict(_FALLBACK)


# ─────────────────────────── 配置加载 ───────────────────────────
def load_cfg(path=None):
    """读 schema 唯一源；失败时回退内置值并**显式告警**（返回 (cfg, ok)）。"""
    p = path or os.path.join(PKG, CFG_REL)
    try:
        import yaml
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict):
            raise ValueError("schema 解析结果不是映射")
        return cfg, True
    except Exception as e:
        print(f"⚠ insight-carrier.yaml 加载失败（{e}）→ 回退内置值。"
              f"载体判据已降级（跳过的键将用内置口径），请修 {CFG_REL}。", file=__import__("sys").stderr)
        return {}, False


def _section(cfg, name):
    """取顶层段；不是 dict 一律按空段处理（不抛异常，由上层按需取回落）。"""
    node = (cfg or {}).get(name)
    return node if isinstance(node, dict) else {}


def _val(raw, key, fallback_key, notes, where):
    """通用取值：缺失/空 → 回落内置值并记 note；有值 → 原样返回。

    ⚠ 第一个参数是**已取到的原始值**（调用点写 `node.get("键名")`），不是节点本身。
      为什么必须这样：ensure_settings 第 18 项靠 AST 找真实读取点，只认
      `x.get("键")` / `x["键"]` / 字典字面量键三种形态；把键名当普通实参传给本函数，
      AST 收集不到 ⇒ 接线了却检测不出来（见文件头 ②）。
    """
    if raw is None or (isinstance(raw, (str, list, dict)) and len(raw) == 0):
        notes.append(f"{where}.{key} 缺失或为空 → 回落内置值 {_FB[fallback_key]!r}")
        return _FB[fallback_key], True
    return raw, False


def _enum_list(cfg, name, notes):
    """取枚举列表。

    ⚠ **两种形态都要认**（2026-10-26 实测踩坑）：
      ① `enums.<name>: [a, b]`（直接列表）
      ② `enums.<name>: {values: [a, b], notes: ...}`（带说明的嵌套形态）
      早先只认 ①，而 schema 写的是 ② ⇒ **每次都回落内置值**——
      判据全部跑在兜底口径上，schema 事实上**不生效**，
      而外部看"有 schema、有实现、有自检"全是绿的（本包最忌讳的假绿）。
      ⇒ 两种都认；都不认才回落。
    """
    enums = _section(cfg, "enums")
    node = enums.get(name)
    raw = node
    if isinstance(node, dict):
        raw = node.get("values")
    raw, _fell = _val(raw, name, name, notes, "insight-carrier.enums")
    if not isinstance(raw, list):
        notes.append(f"insight-carrier.enums.{name} 既不是列表也不是 {{values:[...]}} "
                     f"→ 回落内置值 {_FB[name]!r}")
        return list(_FB[name])
    return [str(x) for x in raw]


def _rules(cfg):
    """取规则清单（rules 段）。每条形如 {id, desc, severity, kind, params, note}。"""
    raw = (cfg or {}).get("rules")
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def _rule(cfg, rid, notes):
    """按 id 取一条规则（找不到 ⇒ None + note）。"""
    for r in _rules(cfg):
        if str(r.get("id")) == str(rid):
            return r
    notes.append(f"insight-carrier.rules 里找不到 {rid} → 该判据**未执行**"
                 f"（声明了但没接线 = 本包核心禁忌）")
    return None


def _rule_params(cfg, rid, notes):
    """取某条规则的 params（缺 ⇒ 空 dict + note）。"""
    r = _rule(cfg, rid, notes)
    if not r:
        return {}
    p = r.get("params")
    return p if isinstance(p, dict) else {}


def _rule_when(params):
    """把规则的"条件"参数规范化成 (field, equals, not_equals)。

    ⚠ **两种形态都要认**（2026-10-26 实测踩坑）：
      ① 扁平：`when_field: axis` + `when_value: content`
      ② 嵌套：`when: {field: axis, equals: content}`
      只认一种 ⇒ 另一种静默落空 ⇒ **该规则不执行**（看起来有规则，实际不判）。
      规范化后统一用 (field, equals, not_equals) 三个值。
    """
    params = params if isinstance(params, dict) else {}
    field = params.get("when_field")
    equals = params.get("when_value")
    not_equals = params.get("when_not_value")
    w = params.get("when")
    if isinstance(w, dict):
        field = w.get("field", field)
        equals = w.get("equals", equals)
        not_equals = w.get("not_equals", not_equals)
    return field, equals, not_equals


def _required(cfg, notes):
    """取必填字段清单。"""
    raw, _fell = _val((cfg or {}).get("required"), "required", "required",
                      notes, "insight-carrier")
    if not isinstance(raw, list):
        notes.append(f"insight-carrier.required 不是列表 → 回落内置值 {_FB['required']!r}")
        return list(_FB["required"])
    return [str(x) for x in raw]


def _id_pattern(cfg, notes):
    """insight_id 格式正则（读 fields.insight_id.**pattern**）。

    ⚠ **不读 `rule`**——rule 是给人看的说明（中文 + 标点），不是可执行的正则。
      早先把 rule 当正则用 ⇒ ID 格式校验**静默失效**（正则不匹配 ⇒ 全部报错，
      或被异常吞掉 ⇒ 全部放过）。yaml 里已把两者分开：`rule` 说明 / `pattern` 执行。
    """
    node = _section(cfg, "fields").get("insight_id")
    raw = node.get("pattern") if isinstance(node, dict) else None
    raw, _fell = _val(raw, "insight_id.pattern", "id_pattern", notes,
                      "insight-carrier.fields")
    if not isinstance(raw, str):
        notes.append(f"insight-carrier.fields.insight_id.pattern 不是字符串 → "
                     f"回落内置值 {_FB['id_pattern']!r}")
        return _FB["id_pattern"]
    return raw


def _module_id_pattern(cfg, notes):
    """module 形态的 target_id 正则（须非纯数字——管家节点裁决）。"""
    node = _section(cfg, "fields").get("target_id")
    raw = node.get("module_pattern") if isinstance(node, dict) else None
    raw, _fell = _val(raw, "target_id.module_pattern", "module_id_pattern", notes,
                      "insight-carrier.fields")
    if not isinstance(raw, str):
        notes.append(f"insight-carrier.fields.target_id.module_pattern 不是字符串 → "
                     f"回落内置值 {_FB['module_id_pattern']!r}")
        return _FB["module_id_pattern"]
    return raw


def _axis_letters(cfg, notes):
    """轴 → 字母映射（axis_letter 段）——R6 的 ID 格式判据要用。

    schema 形态：`axis_letter: {content: C, pedagogy: P, visual: V}`（键名即 axis 枚举值）。
    ⚠ 兼容三种形态：dict 映射 / {map|values|letters: [...]} / 直接列表。
      没有它，ID 格式判据只能用内置的 C/P/V ⇒ 改 yaml 的轴映射不改行为（又是双声明）。
    """
    node = (cfg or {}).get("axis_letter")
    raw = node
    if isinstance(node, dict):
        for k in ("map", "values", "letters"):
            if isinstance(node.get(k), (dict, list)):
                raw = node.get(k)
                break
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list) or not raw:
        notes.append("insight-carrier.axis_letter 缺失或形态未知 → 回落内置值 'CPV'")
        return "CPV"
    letters = "".join(str(x) for x in raw)
    if not letters:
        notes.append("insight-carrier.axis_letter 为空 → 回落内置值 'CPV'")
        return "CPV"
    return letters


# ─────────────────────────── 条目校验 ───────────────────────────
def validate_entry(entry, cfg=None, notes=None):
    """校验一条洞察条目。返回 (ok, errors, warnings)。

    errors / warnings 的元素形态：{"field":..., "code":..., "detail":...}
    ⚠ 本函数**不判语义**——proposal 写得好不好、rationale 在不在理，一律不判。
    """
    notes = notes if notes is not None else []
    if cfg is None:
        cfg, _ = load_cfg()
    errors, warnings = [], []

    if not isinstance(entry, dict):
        errors.append({"field": "(entry)", "code": "E_TYPE",
                       "detail": "条目不是对象（须为 dict）"})
        return False, errors, warnings

    # ① 必填字段
    for f in _required(cfg, notes):
        v = entry.get(f)
        if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
            errors.append({"field": f, "code": "E_REQUIRED",
                           "detail": f"必填字段 {f} 缺失或为空"})

    # ② 枚举合法性
    for field, enum_name in (("target_kind", "target_kind"), ("axis", "axis"),
                             ("severity", "severity"), ("status", "status")):
        allowed = _enum_list(cfg, enum_name, notes)
        v = entry.get(field)
        if v not in (None, "") and str(v) not in allowed:
            errors.append({"field": field, "code": "E_ENUM",
                           "detail": f"{field}={v!r} 不在允许取值 {allowed} 内"})

    # ③ 规则 R3：**由 yaml 的 params 驱动**（当 + 必填字段集）
    #    为什么参数化：R3 的"何时必填哪些字段"是**判据**，写在 yaml 里；
    #    代码只执行。写死在代码里 = 改 yaml 不改行为（本包反复治理的同型缺陷）。
    r3 = _rule_params(cfg, "R3", notes)
    f3, eq3, neq3 = _rule_when(r3)
    if f3 and eq3 is not None and str(entry.get(f3)) == str(eq3):
        for f in (r3.get("require") or ["evidence"]):
            v = entry.get(f)
            if not v or not str(v).strip():
                errors.append({"field": f, "code": "E_R3_CONTENT_EVIDENCE",
                               "detail": f"axis={eq3} 的条目必须带 {f}"
                                         f"（内容轴洞察必须可溯源）——源 insight-carrier.yaml#rules[R3]"})

    # ④ 规则 R4：status != proposed 必须留裁决痕（同样参数化）
    r4 = _rule_params(cfg, "R4", notes)
    f4, eq4, neq4 = _rule_when(r4)
    st = str(entry.get("status") or "")
    hit4 = False
    if f4 and neq4 is not None:
        hit4 = bool(st) and st != str(neq4)
    elif st and st != "proposed":
        hit4 = True
    if hit4:
        for f in (r4.get("require") or ["decided_by", "decided_at"]):
            if not (entry.get(f) and str(entry.get(f)).strip()):
                errors.append({"field": f, "code": "E_R4_ADJUDICATION_TRACE",
                               "detail": f"status={st} 时必须填 {f}（裁决留痕）"
                                         f"——源 insight-carrier.yaml#rules[R4]"})

    # ⑤ 规则 R5：module 形态的 target_id 须为模块/章节级标识（参数化）
    r5 = _rule_params(cfg, "R5", notes)
    f5, eq5, _n5 = _rule_when(r5)
    if f5 and str(entry.get(f5)) == str(eq5):
        tid = str(entry.get("target_id") or "")
        min_len = int(r5.get("min_length", 2) or 0)
        forbid_num = bool(r5.get("forbid_numeric_only", True))
        bad = False
        if tid and min_len and len(tid) < min_len:
            bad = True
        if tid and forbid_num and tid.isdigit():
            bad = True
        if bad:
            errors.append({"field": "target_id", "code": "E_R5_MODULE_GRANULARITY",
                           "detail": f"{f5}={eq5} 时 target_id={tid!r} 须为"
                                     f"教学知识模块/章节级标识（非纯数字页号）"
                                     f"——源 insight-carrier.yaml#rules[R5]"})

    # ⑥ 规则 R6：insight_id 格式（参数化：轴首字母集 + 序号位数）
    r6 = _rule_params(cfg, "R6", notes)
    iid = str(entry.get("insight_id") or "")
    if iid:
        min_seq = int(r6.get("min_seq_digits", 2) or 0)
        letters = _axis_letters(cfg, notes)
        pat = None
        if letters:
            pat = re.compile(r"^(?P<target>.+?)-(?P<axis>[" + re.escape(letters) +
                             r"])-(?P<seq>\d{" + str(min_seq) + r",})$")
        else:
            pat = _id_pattern(cfg, notes)
        try:
            if pat and not re.match(pat, iid):
                errors.append({"field": "insight_id", "code": "E_ID_FORMAT",
                               "detail": f"insight_id={iid!r} 不符合 <target_id>-<轴首字母>-"
                                         f"<序号{min_seq}位> 格式"
                                         f"——源 insight-carrier.yaml#rules[R6]"})
        except re.error as e:
            warnings.append({"code": "W_ID_PATTERN_INVALID",
                             "detail": f"ID 正则非法（{e}），已跳过格式校验"})

    # ⑦ 软提醒：proposal 疑似无定位表述（反自评失真）——**只警告不判错**，
    #    因为"是否无定位"是语义判断，脚本不越界。
    prop = str(entry.get("proposal") or "")
    if prop and any(k in prop for k in ("整体优化", "已优化", "优化表述", "润色一下")):
        warnings.append({"code": "W_VAGUE_PROPOSAL",
                         "detail": "proposal 疑似无定位表述（如'整体优化'）——"
                                   "须可执行到动作级；本项只提醒不判错（是否含糊属语义判断）"})

    return (not errors), errors, warnings


def validate_part(part, cfg=None, notes=None):
    """校验一个分片。返回 (ok, errors)。

    分片形态：{"task_id":..., "member":..., "axis":..., "round":..., "entries":[...]}
    """
    notes = notes if notes is not None else []
    if cfg is None:
        cfg, _ = load_cfg()
    errors = []
    if not isinstance(part, dict):
        return False, [{"field": "(part)", "code": "E_TYPE", "detail": "分片不是对象"}]
    pspec = _section(cfg, "part")
    for f in (pspec.get("required") or ["task_id", "member", "axis", "round", "entries"]):
        if f == "entries":
            continue
        if not part.get(f) and part.get(f) != 0:
            errors.append({"field": f, "code": "E_REQUIRED", "detail": f"分片缺必填字段 {f}"})
    entries = part.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append({"field": "entries", "code": "E_REQUIRED",
                       "detail": "分片 entries 必须是非空数组"})
        return False, errors
    # 分片轴与条目轴必须一致（schema#part.axis_must_match_entry）——
    #   轴对不上说明分片被串了，是**落盘事故**而非语义分歧，必须拦。
    paxis = str(part.get("axis") or "")
    for i, e in enumerate(entries):
        ok, errs, _ = validate_entry(e, cfg, notes)
        if not ok:
            for x in errs:
                y = dict(x)
                y["detail"] = f"entries[{i}]（{x.get('field')}）：{x.get('detail')}"
                errors.append(y)
        if (pspec.get("axis_must_match_entry") and isinstance(e, dict)
                and paxis and str(e.get("axis") or "") != paxis):
            errors.append({"field": f"entries[{i}].axis", "code": "E_PART_AXIS_MISMATCH",
                           "detail": f"分片 axis={paxis!r} 与条目 axis={e.get('axis')!r} 不一致"
                                     f"——分片被串了（落盘事故），源 insight-carrier.yaml#part.axis_must_match_entry"})
    return (not errors), errors


# ─────────────────────────── 合并 ───────────────────────────
def merge_parts(parts, cfg=None, notes=None):
    """把多个分片合并成载体。返回载体 dict。

    规则 R2：insight_id 重复 ⇒ **记 error 且不静默覆盖**（两个版本都留痕）。
    ⚠ 合并**不判多轴并存**——那由 detect_conflicts 负责（职责分离：
      合并只管"把条目收进来"，冲突检出只管"哪些目标待裁决"）。
    """
    notes = notes if notes is not None else []
    if cfg is None:
        cfg, _ = load_cfg()
    carrier = {
        "schema_version": int((cfg or {}).get("schema_version", 1) or 1),
        "task_id": "",
        "targets": [],
        "merge_errors": [],
    }
    by_target = {}
    seen_ids = {}

    for pi, part in enumerate(parts or []):
        if not isinstance(part, dict):
            carrier["merge_errors"].append({"code": "E_PART_TYPE",
                                            "detail": f"分片[{pi}] 不是对象，已跳过"})
            continue
        if not carrier["task_id"]:
            carrier["task_id"] = str(part.get("task_id") or "")
        pid = str(part.get("member") or "?")
        paxis = str(part.get("axis") or "?")
        for ei, e in enumerate(part.get("entries") or []):
            if not isinstance(e, dict):
                carrier["merge_errors"].append({"code": "E_ENTRY_TYPE",
                                                "detail": f"{pid} 分片 entries[{ei}] 不是对象，已跳过"})
                continue
            iid = str(e.get("insight_id") or "")
            if iid and iid in seen_ids:
                # R2：重复 ID —— 记 error，**两个版本都保留**（不静默覆盖）
                prev = seen_ids[iid]
                carrier["merge_errors"].append({
                    "code": "E_DUP_INSIGHT_ID",
                    "detail": f"insight_id={iid!r} 重复：来自 {prev['origin']} 与 "
                              f"{pid}/{paxis}；**未覆盖**——两版均留痕，请裁决后手工清理",
                    "insight_id": iid,
                    "origins": [prev["origin"], f"{pid}/{paxis}"],
                })
            else:
                seen_ids[iid] = {"origin": f"{pid}/{paxis}"}
            key = (str(e.get("target_id") or ""), str(e.get("target_kind") or ""))
            tgt = by_target.get(key)
            if tgt is None:
                tgt = {"target_id": key[0], "target_kind": key[1], "insights": []}
                by_target[key] = tgt
            # 重复 ID 也**追加**（两版都在），下游靠 merge_errors 知道有重复
            rec = dict(e)
            rec.setdefault("_origin", f"{pid}/{paxis}")
            # ── v3.22.0 G5（第二轮独立诊断 P5）：同内容重提的机器提示 ──
            # 病灶（实测复现）：rejected 的提案换个 insight_id 原样再提，rc=0 直接入载体
            #   —— R2 只查 ID 唯一，R6 自认"内容去重是语义判断"。
            # 边界不变：**只提示不阻断**（proposal 全同才提示；近似判定是语义，仍归人）。
            #   提示写进**本条目**的 possible_duplicate_of，裁决者一眼可见。
            #
            # ⚠ **v3.22.0 修正**：初版把本块放在 `rec` 定义**之前**，而块内引用 `rec`
            #   ⇒ 首次执行时 NameError 被 `except: pass` 静默吞掉；更糟的是**第二次**迭代时
            #   `rec` 已是**上一轮迭代的残留值** ⇒ 标记被写到**错误的条目**上（实测出现
            #   s1-C-01 自指 s1-C-01，而真正该被提示的 s1-C-02 反而没提示）。
            #   ⇒ 本块必须在 `rec` 赋值**之后**执行，且用**局部变量**持有命中项，不依赖 rec。
            _prop = str(e.get("proposal") or "").strip()
            if _prop:
                for _t0 in by_target.values():
                    if (str(_t0.get("target_id") or ""),
                            str(_t0.get("target_kind") or "")) != key:
                        continue
                    for _e0 in _t0.get("insights") or []:
                        if (str(_e0.get("axis") or "") == str(e.get("axis") or "")
                                and str(_e0.get("proposal") or "").strip() == _prop
                                and _e0.get("insight_id") != e.get("insight_id")):
                            # 仅首见即止；不阻断（边界见上）
                            rec["possible_duplicate_of"] = _e0.get("insight_id")
                            break
                    if rec.get("possible_duplicate_of"):
                        break
            if iid and iid in seen_ids and len(tgt["insights"]) and \
                    any(x.get("insight_id") == iid for x in tgt["insights"]):
                rec["_duplicate_of"] = iid
            tgt["insights"].append(rec)

    carrier["targets"] = list(by_target.values())
    return carrier


def detect_conflicts(carrier, cfg=None, notes=None):
    """检出「同一 target 上多轴并存 ⇒ 待人工裁决」。

    ⚠ **只报多轴并存，不判是否冲突**——是否冲突是语义判断，归主理人与用户。
      返回：[{target_id, target_kind, axes, insight_ids, reason}]
    """
    notes = notes if notes is not None else []
    # ⚠ **必须在此补 cfg 兜底**（2026-10-26 实测踩坑）：
    #   本函数原先不用配置，所以没有这行；后来加了 R1 参数化（要读 rules 段），
    #   但调用方 `cmd_insights` 传的是 `cfg=None` ⇒ `_rule_params(None,...)` 读到空 rules
    #   ⇒ **R1 判据静默不执行**（note 里报"找不到 R1"，但 `needs_adjudication` 仍为空）
    #   ⇒ 多轴并存不被检出 ⇒ 冲突漏过。典型「加了判据却忘了让判据拿到配置」的坑。
    if cfg is None:
        cfg, _ = load_cfg()
    # R1 参数化：min_axes（默认 2）、pending_status（默认 proposed）
    r1 = _rule_params(cfg, "R1", notes)
    min_axes = int(r1.get("min_axes", 2) or 2)
    pending = str(r1.get("pending_status", "proposed") or "proposed")
    only = r1.get("only_status")
    out = []
    for t in (carrier or {}).get("targets") or []:
        axes = {}
        for e in t.get("insights") or []:
            st = str(e.get("status") or pending)
            if st != pending:
                continue          # 已裁决的不再算待裁决
            if isinstance(only, list) and only and st not in [str(x) for x in only]:
                continue
            ax = str(e.get("axis") or "?")
            axes.setdefault(ax, []).append(str(e.get("insight_id") or ""))
        if len(axes) >= min_axes:
            out.append({
                "target_id": t.get("target_id"),
                "target_kind": t.get("target_kind"),
                "axes": sorted(axes.keys()),
                "insight_ids": sorted(i for v in axes.values() for i in v),
                "reason": f"同一目标上有 {len(axes)} 个轴的待裁决条目（{sorted(axes.keys())}）"
                          f"——**需人工裁决**（本层只判结构；是否冲突属语义判断，归人）",
            })
    return out


# ─────────────────────────── 规则执行一致性自检 ───────────────────────────
# 本包的核心禁忌是「声明层 ≠ 执行层」——schema 里写了规则，代码却没执行，
# 外部看"有 schema、有实现、有自检"全是绿的，实则跑的是兜底口径。
# 2026-10-26 实测踩坑：实现读 `enums.<x>`（直接列表）与 `report_projection`，
# 而 schema 写的是 `enums.<x>.values` 与 `report.project_items`
# ⇒ **每一次都回落内置值，schema 事实上不生效**，而自检照样通过。
# ⇒ 下面这张表把"哪条规则由哪个函数执行"显式登记，并提供机器核对：
#   yaml 里新增一条 rules，但实现里没有对应执行点 ⇒ 直接报出来。
_RULE_EXECUTORS = {
    "R1": "detect_conflicts",
    "R2": "merge_parts",
    "R3": "validate_entry",
    "R4": "validate_entry",
    "R5": "validate_entry",
    "R6": "validate_entry",
}


def rule_execution_check(cfg=None, notes=None):
    """核对 schema 的 rules 段与实现的执行点是否对齐。返回 (ok, report)。

    判据：yaml 里每条规则的 id 都必须在 _RULE_EXECUTORS 里有归属，
    且该 kind/params 必须真的被对应函数消费。
    ⚠ 本检查只核对**登记的对齐关系**，不替代运行时验证——
      真正的"改配置是否改行为"由 scripts/test_insight_carrier.py 的反向例负责。
    """
    notes = notes if notes is not None else []
    if cfg is None:
        cfg, _ = load_cfg()
    declared = {str(r.get("id")): r for r in _rules(cfg)}
    report = {"declared": sorted(declared.keys()),
              "executed_by": {k: v for k, v in _RULE_EXECUTORS.items() if k in declared},
              "unwired": [], "extra": []}
    for rid in sorted(declared):
        if rid not in _RULE_EXECUTORS:
            report["unwired"].append(rid)
            notes.append(f"⚠ schema 声明了规则 {rid}，但实现里**没有对应执行点**"
                         f"——声明层≠执行层（本包核心禁忌），须补实现或删声明")
    for rid in sorted(_RULE_EXECUTORS):
        if rid not in declared:
            report["extra"].append(rid)
    ok = not report["unwired"] and not report["extra"]
    return ok, report


# ─────────────────────────── 轮报投影 ───────────────────────────
def render_round_report(carrier, cfg=None, notes=None):
    """从载体渲染轮报六项里的**第 1、2 项**（处理范围及问题 / 修改前后差异）。

    ⚠ 投影，不是创作：所有内容来自载体，**不得凭空生成**载体里没有的条目。
    ⚠ 缺 before 快照时**显式标缺失（待补）**，不得编造差异。
    """
    notes = notes if notes is not None else []
    if cfg is None:
        cfg, _ = load_cfg()
    # ── 投影配置从 **report 段**读（schema 的唯一源）────────────────────
    # ⚠ 2026-10-26 实测踩坑：schema 写的是 `report:`（含 project_items / scope_fields /
    #   unavailable_scope_fields / snapshot_bucket …），而实现读的是 `report_projection:`——
    #   两处键名不一致 ⇒ **每次都回落内置两项**，schema 的投影配置形同虚设，
    #   而外部看"有 schema、有实现"全是绿的。
    #   现在按 schema 的 report 段读，并保留 report_projection 作为**兼容形态**。
    rep = _section(cfg, "report")
    items = []
    proj = []
    if rep:
        for it in (rep.get("project_items") or []):
            proj.append({"key": it, "round_review_item": 1 if it == "scope_and_issues" else 2,
                         "title": "本轮处理范围及问题" if it == "scope_and_issues"
                                  else "修改前后差异"})
    if not proj:
        legacy = (cfg or {}).get("report_projection")
        if isinstance(legacy, list) and legacy:
            proj = legacy
        else:
            notes.append("insight-carrier.report.project_items 缺失或为空 → 按内置两项投影")
            proj = [{"key": "scope_and_issues", "round_review_item": 1,
                     "title": "本轮处理范围及问题"},
                    {"key": "before_after_diff", "round_review_item": 2,
                     "title": "修改前后差异"}]
    scope_fields = rep.get("scope_fields") if rep else None
    diff_fields = rep.get("diff_fields") if rep else None
    unavailable = rep.get("unavailable_scope_fields") if rep else None
    snap_bucket = str(rep.get("snapshot_bucket") or "snapshots") if rep else "snapshots"
    diff_keys = rep.get("diff_snapshot_keys") if rep else None
    missing_marker = str(rep.get("missing_snapshot_marker") or "缺失（待补）") if rep else "缺失（待补）"

    by_target = {}
    for t in (carrier or {}).get("targets") or []:
        by_target[str(t.get("target_id") or "")] = t

    for p in proj:
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "")
        title = str(p.get("title") or key)
        ri = p.get("round_review_item")
        if key == "scope_and_issues":
            rows = []
            for t in (carrier or {}).get("targets") or []:
                for e in t.get("insights") or []:
                    rows.append({
                        "insight_id": e.get("insight_id"),
                        "target_id": t.get("target_id"),
                        "target_kind": t.get("target_kind"),
                        "axis": e.get("axis"),
                        "expert": e.get("expert"),
                        "proposal": e.get("proposal"),
                        "severity": e.get("severity"),
                        "status": e.get("status"),
                        "judge_mode": e.get("judge_mode"),
                        "evidence": e.get("evidence"),
                    })
            items.append({"key": key, "round_review_item": ri, "title": title, "rows": rows,
                          "count": len(rows)})
        elif key == "before_after_diff":
            rows = []
            snaps = (carrier or {}).get(snap_bucket) or {}
            for t in (carrier or {}).get("targets") or []:
                tid = str(t.get("target_id") or "")
                t_snap = snaps.get(tid) if isinstance(snaps, dict) else None
                for e in t.get("insights") or []:
                    # 快照来源：条目自带优先，否则取 carrier.snapshots[target_id]
                    before = e.get("before")
                    after = e.get("after")
                    if (before is None or after is None) and isinstance(t_snap, dict):
                        before = t_snap.get("before") if before is None else before
                        after = t_snap.get("after") if after is None else after
                    row = {"insight_id": e.get("insight_id"),
                           "target_id": t.get("target_id"),
                           "before": before, "after": after}
                    if diff_fields:
                        for f in diff_fields:
                            if f not in row:
                                row[f] = e.get(f)
                    missing = []
                    for k in (diff_keys or ["before", "after"]):
                        if row.get(k) in (None, ""):
                            missing.append(k)
                    if missing:
                        # ⚠ 缺哪份就显式标缺，**不得编造**
                        row["missing"] = missing
                        row["status"] = missing_marker
                        row["note"] = (f"载体条目 {e.get('insight_id')} 缺 {missing} 快照"
                                       f"——按 insight-carrier.yaml#report 的"
                                       f"missing_snapshot_marker **显式标缺失**，不编造差异")
                    else:
                        row["missing"] = []
                        row["status"] = "齐备"
                    rows.append(row)
            items.append({"key": key, "round_review_item": ri, "title": title, "rows": rows,
                          "count": len(rows)})
    # 载体**不持有**的轮报字段 → 显式标缺失（schema#report.unavailable_scope_fields）
    if unavailable:
        marker_items = []
        for u in unavailable:
            if not isinstance(u, dict):
                continue
            marker_items.append({"field": u.get("name"),
                                 "status": str(u.get("marker") or "缺失（待补）"),
                                 "note": str(u.get("note") or "")})
        if marker_items:
            items.append({"key": "unavailable_scope_fields", "title": "载体不持有的轮报字段",
                          "rows": marker_items, "count": len(marker_items)})
    _ = by_target
    _ = scope_fields
    return {"carrier_task_id": (carrier or {}).get("task_id"), "items": items,
            "notes": notes}


# ─────────────────────────── 冻结 ───────────────────────────
def freeze_digest(carrier):
    """对载体算**稳定 digest**（sha256 over canonical JSON）。

    ⚠ 判据是「**载体内容**没变」，不是「文件字节没变」——
      重新序列化（键序变化）**不得**改变 digest。故先 canonicalize：
      sort_keys=True + 固定分隔符 + ensure_ascii=False。
    """
    blob = json.dumps(carrier or {}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ─────────────────────────── 自检 ───────────────────────────
def self_check():
    """最小自检：跑一遍内置样例，验证每个判定函数，并打印回落/降级提示。

    ⚠ **降级口径下必须判红**（v3.21.0 实测教训）：
      首次自检时 schema 有一处 YAML 语法错误 → 加载失败 → 回落内置值 →
      **自检照样全部通过** ⇒ 报出一个"绿"的假象，而实际跑的是内置口径、
      配置文件根本没生效。这正是本包最忌讳的"降级后仍报绿"。
      ⇒ 现在：schema 加载失败 ⇒ 直接 return 1，并明确打印"本次自检无效"。
    """
    import sys
    cfg, ok = load_cfg()
    notes = []
    if not ok:
        print("❌ schema 加载失败 → 本次自检**在回落口径下运行，结果无效**。"
              "请先修 references/insight-carrier.yaml 再跑。", file=sys.stderr)
        return 1
    print(f"schema 加载：ok（{CFG_REL}）")
    print(f"  enums.axis = {_enum_list(cfg, 'axis', notes)}")
    print(f"  enums.target_kind = {_enum_list(cfg, 'target_kind', notes)}")
    print(f"  required = {_required(cfg, notes)}")

    # ① 合规条目应通过
    good = {"insight_id": "s12-C-01", "target_id": "s12", "target_kind": "page",
            "axis": "content", "expert": "dvm-content-expert",
            "proposal": "把疫苗程序表述改成 2021 版口径", "rationale": "原表述引用 2016 版",
            "severity": "P1", "status": "proposed", "evidence": "PMID:31234567"}
    ok1, e1, w1 = validate_entry(good, cfg, notes)
    print(f"  [正例] 合规条目 ok={ok1} errors={len(e1)} warnings={len(w1)}")
    assert ok1, f"合规条目被判错：{e1}"

    # ② 缺必填 → 判错
    bad = dict(good)
    del bad["proposal"]
    ok2, e2, _ = validate_entry(bad, cfg, notes)
    print(f"  [反例] 缺 proposal ok={ok2}（应 False）errors={len(e2)}")
    assert not ok2, "缺必填字段未判错"

    # ③ content 轴缺 evidence → 判错（R3）
    bad3 = dict(good)
    del bad3["evidence"]
    ok3, e3, _ = validate_entry(bad3, cfg, notes)
    print(f"  [反例] content 轴缺 evidence ok={ok3}（应 False）")
    assert not ok3, "规则 R3 未生效"

    # ④ module 形态给纯数字 → 判错（R5）
    bad5 = dict(good)
    bad5.update({"target_kind": "module", "target_id": "12"})
    ok5, e5, _ = validate_entry(bad5, cfg, notes)
    print(f"  [反例] module 形态给纯数字 target_id ok={ok5}（应 False）")
    assert not ok5, "规则 R5 未生效"

    # ⑤ 合并 + 冲突检出
    parts = [
        {"task_id": "T1", "member": "dvm-content-expert", "axis": "content", "round": 1,
         "entries": [good]},
        {"task_id": "T1", "member": "pedagogy-architect", "axis": "pedagogy", "round": 1,
         "entries": [dict(good, insight_id="s12-P-01", axis="pedagogy",
                          expert="pedagogy-architect", evidence=None)]},
    ]
    carrier = merge_parts(parts, cfg, notes)
    conflicts = detect_conflicts(carrier, cfg, notes)
    print(f"  合并：targets={len(carrier['targets'])} "
          f"merge_errors={len(carrier.get('merge_errors') or [])}")
    print(f"  冲突检出：{len(conflicts)} 处（多轴并存）")
    assert conflicts, "多轴并存未被检出"

    # ⑥ 重复 insight_id → 不静默覆盖
    dup = merge_parts([parts[0], parts[0]], cfg, notes)
    blob = json.dumps(dup, ensure_ascii=False)
    print(f"  重复 ID：merge_errors={len(dup.get('merge_errors') or [])}"
          f"（两版均留痕：{'疫苗程序表述' in blob}）")
    assert dup.get("merge_errors"), "重复 insight_id 未报错"
    assert blob.count("疫苗程序表述") >= 2, "重复 ID 的其中一版被静默覆盖"

    # ⑦ 渲染：缺 before → 显式标缺失
    rep = render_round_report(carrier, cfg, notes)
    rblob = json.dumps(rep, ensure_ascii=False)
    print(f"  渲染：items={len(rep['items'])} 含缺失标记={'缺失' in rblob}")
    assert "缺失" in rblob, "缺 before 快照未显式标缺失"

    # ⑧ digest 对键序稳定
    d1 = freeze_digest(carrier)
    d2 = freeze_digest(json.loads(json.dumps(carrier, ensure_ascii=False)))
    print(f"  digest：{d1[:16]}… 对键序稳定={d1 == d2}")
    assert d1 == d2, "digest 对键序不稳定——冻结判据错了"

    # ── ⑨ 真实 schema 零回落（2026-10-26 实测踩坑后新增的关键一条）──
    #   之前自检只验"判据行为对不对"，**不验"判据是不是取自 schema"**：
    #   实现按 `enums.<x>`（直接列表）与 `report_projection` 读，而 schema 写的是
    #   `enums.<x>.values` 与 `report.project_items` ⇒ **每次都回落内置值**，
    #   schema 事实上不生效，而自检照样"通过"——本包最忌讳的假绿。
    #   ⇒ 现在用**真实 schema** 跑一遍，断言**零回落**。
    notes2 = []
    _e, _errs, _warns = validate_entry(good, cfg, notes2)
    _merged2 = ic_merge = merge_parts(parts, cfg, notes2)
    _c = detect_conflicts(_merged2, cfg, notes2)
    _r = render_round_report(_merged2, cfg, notes2)
    _rp = validate_part(parts[0], cfg, notes2)
    print(f"  [真实 schema] 零回落检查：回落 {len(notes2)} 条")
    for n in notes2:
        print(f"      ⚠ {n}")
    if notes2:
        print("❌ 用真实 schema 跑仍有回落 ⇒ **schema 未生效**，判据跑的是兜底口径。"
              "自检判红。", file=sys.stderr)
        return 1

    # ── ⑩ 规则执行一致性（声明的规则是否都有执行点）──────────────────
    rok, rreport = rule_execution_check(cfg, notes2)
    print(f"  规则对齐：declared={rreport['declared']} "
          f"unwired={rreport['unwired']} extra={rreport['extra']}")
    if not rok:
        print("❌ schema 的规则与实现执行点不对齐 ⇒ 声明层≠执行层。自检判红。",
              file=sys.stderr)
        return 1

    if notes:
        print("\n回落/降级提示（必须可见，不得静默）：")
        for n in notes:
            print(f"  ⚠ {n}")
    else:
        print("\n无回落：全部判据均取自 references/insight-carrier.yaml")
    print("\n自检通过。")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        sys.exit(self_check())
    print(__doc__)

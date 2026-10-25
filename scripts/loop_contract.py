#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
loop_contract.py —— Loop A / Loop B / delta_gate 三层契约的**唯一判定层**（v3.20.0）

为什么要有这个文件（2026-10-26 v3.20.0 逐键取证）：
  config/harness.yaml 的 loop_a / loop_b / delta_gate 三段共 34 个叶子键，
  除 scope / forbidden_paths / termination / budgets.max_rounds 等少数几个外，
  **全部没有任何代码读取者**。v3.9.0 只把「动作层」（13 个 loop 子命令）下沉成
  代码，判据层（默认档、轮审判据、增量门禁、两环身份）仍躺在 yaml 里当 Markdown
  纪律用；ensure_settings 第 18 项当时把它们登记为 known_textual（人读型），
  理由写的是「声明未接线」——即"配了但没生效"，正是本包反复治理的同型缺陷。

  本模块把这 34 个键里**可判定**的 32 个全部落地，剩下 2 类（2 个 trigger + 1 个
  insert_font_at_creation）**据实标注为不可判定**，不用"打印出来"冒充已接线：

  ┌ 已接线（32）──────────────────────────────────────────────────────┐
  │ loop_a   : enabled / state_file / confirm_before_each_batch /     │
  │            patch_discipline / regression_required                 │
  │ loop_b   : enabled / state_file / coexist_with / single_writer /  │
  │            original_readonly / budgets.retrieval_budget_per_round │
  │            round_review.*（5） / defaults.*（11）                  │
  │ delta_gate: baseline_required / baseline_fields / block_on_new_   │
  │            defects / report_format / miss_needs_human_review /    │
  │            insert_spatial_audit / image_caption_requires_reading /│
  │            caption_missing_element_policy                         │
  └──────────────────────────────────────────────────────────────────┘
  ┌ 据实标注为不可判定（3，保留 known_textual）──────────────────────┐
  │ loop_a.trigger / loop_b.trigger —— 判环判据（dual-loop-           │
  │   governance.md#1），属语义判定，代码不判环                        │
  │ delta_gate.insert_font_at_creation —— 写入时行为，成品文件态无     │
  │   痕迹（与 OOXML 病例 API-001 同型），结构性不可实现               │
  └──────────────────────────────────────────────────────────────────┘

设计纪律（与全包一致）：
  1. **禁硬编码**：阈值、字段名、格式串、路径一律从 config/ 读；
     缺键/空值/非法值一律**告警 + 显式回落**，并把回落写进 note 由调用方透出
     （静默回落 = 本包已多次吃亏的"看起来有护栏、实际不设防"）。
  2. **只做确定性判定**：路径解析、集合比对、计数、格式与守恒校验。
     语义判断（判环、判读是否属实、"最小"到什么程度算最小）仍归 LLM 与主理人——
     本模块不宣称自己判了这些。
  3. **诚实边界写进返回值**：每个判定函数都回 note，把"这次没判定/降级了/无执行器"
     一并交出去，由调用方显示给用户——不得让调用方以为判过了。

用法（被 harness.py 调用；也可直接跑本文件做自检）：
    python3 scripts/loop_contract.py --self-check
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

# 内置回落值——**只在配置缺失/非法时启用**，且启用必须写 note。
# ⚠ 不要在别处另立一份同名常量：双声明必漂移（v3.17.0 F2 已吃过这个亏）。
#
# ⚠ 为什么这里用「元组列表」而不是字典字面量（看起来别扭，但必须如此）：
#   ensure_settings 第 18 项（死配置巡检）用 AST 收集"真实读取点"，其中第③种形态
#   是**字典字面量的字符串键**——若本表写成字典，它里面这些键名会被当成"有代码
#   读取者"，于是**回落表自己会把死配置刷成绿色**：即使真正的读取点被删掉，
#   巡检也看不出来（这正是第 18 项从文本搜索改成 AST 时要消灭的"提到但没用"）。
#   用元组列表 → AST 的三种形态都不收集 → 回落表不参与"是否被读"的判定。
_FALLBACK = [
    ("state_file_a", ".workbuddy/loopA_state.json"),
    ("state_file_b", ".workbuddy/loopB_state.json"),
    ("retrieval_budget_per_round", 30),
    ("round_review_required_items", 6),
    ("invalidation", "sha256"),
    ("patch_discipline", "minimal"),
    ("confirm_before_each_batch", True),
    ("regression_required", ["ensure_settings", "test_harness", "test_five_gates"]),
    ("baseline_fields", ["p0", "p1", "p2", "pages_physical", "pages_visible", "md5"]),
    ("report_format", "P0=6（基线 6，自引入 0）"),
    ("enabled", True),
    ("original_readonly", True),
    ("single_writer", "team-lead"),
    ("geo_baseline_required", True),
    ("baseline_required", True),
    ("block_on_new_defects", True),
    ("miss_needs_human_review", True),
    ("insert_spatial_audit", True),
    ("image_caption_requires_reading", True),
    ("caption_missing_element_policy", "explicit_todo"),
    ("round_review_required", True),
    ("silent_is_not_approval", True),
    ("partial_accept_freezes_only_named", True),
    ("rework_stays_in_round", True),
]
_FB = dict(_FALLBACK)


# ─────────────────────────── 取值与回落 ───────────────────────────
def _section(cfg, name):
    """取顶层段；不是 dict 一律按空段处理（不抛异常，由上层按需取回落）。"""
    node = (cfg or {}).get(name)
    return node if isinstance(node, dict) else {}


def _val(raw, key, fallback_key, notes, where):
    """通用取值：缺失/空 → 回落内置值并记 note；有值 → 原样返回。

    ⚠ 第一个参数是**已取到的原始值**（调用点写成 `node.get("建名")`），不是节点本身。
      为什么必须这样：ensure_settings 第 18 项（死配置巡检）靠 AST 找真实读取点，
      只认 `x.get("键")` / `x["键"]` / 字典字面量键三种形态。若把键名作为普通实参
      传给本函数（形如 `_val(node, 键名, ...)` 这种"键名当普通实参"的写法），
      AST 收集不到 ⇒ 这 32 个键会被
      **误判成仍然没人读**——接线了却检测不出来，等于白接。
      规范形式放在调用点，本函数只负责"缺失/非法 → 回落 + 留痕"。

    为什么"空值"也算缺失：yaml 里写 `default_template: null` 与不写这个键，
    对调用方是同一件事（都没有可用值），但**意图不同**（显式留空 vs 忘了配）。
    这里统一按缺失处理，并在 note 里标明"显式为空"，避免把"忘了配"伪装成"有意留空"。
    """
    if raw is None or (isinstance(raw, (str, list, dict)) and len(raw) == 0):
        notes.append(f"{where}.{key} 缺失或为空 → 回落内置值 {_FB[fallback_key]!r}")
        return _FB[fallback_key], True
    return raw, False


def _bool(raw, key, fallback_key, notes, where):
    """布尔取值（raw 由调用点以 `node.get("键")` 形式取来，理由见 _val）。"""
    v, fell = _val(raw, key, fallback_key, notes, where)
    if isinstance(v, bool):
        return v, fell
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "1", "on"):
            return True, fell
        if s in ("false", "no", "0", "off"):
            return False, fell
    notes.append(f"{where}.{key}={v!r} 不是合法布尔 → 回落 {_FB[fallback_key]!r}")
    return _FB[fallback_key], True


def _int(raw, key, fallback_key, notes, where):
    """数值取值（raw 由调用点以 `node.get("键")` 形式取来，理由见 _val）。"""
    v, fell = _val(raw, key, fallback_key, notes, where)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        notes.append(f"{where}.{key}={v!r} 不是合法数值 → 回落 {_FB[fallback_key]!r}")
        return _FB[fallback_key], True
    return int(v), fell


def resolve_placeholders(p, workspace, pkg=PKG):
    """把配置里的 <包> / <工作区> 占位符解析成真实绝对路径。

    ⚠ 唯一源：harness.py 的 `_resolve_placeholders` 已改为转调本函数——
      两处各写一份替换规则正是本包"同口径漂移"的典型病灶。
    """
    return str(p).replace("<包>", pkg).replace("<工作区>", workspace)


# ─────────────────────────── 两环身份与路径 ───────────────────────────
def enabled(cfg, loop, notes=None):
    """该环是否启用（harness.yaml#loop_{a,b}.enabled）。

    此前这个键**零读取者**：把它改成 false 不会有任何脚本行为变化——
    即"停用某环"这件事在代码层无法表达。现由 cmd_loop 在动作入口检查。

    ⚠ 返回值必须是**标量 bool**（不是 `(值, 是否回落)` 元组）：
      本函数的调用点是 `if not loop_contract.enabled(cfg, loop): 拦截`——
      若返回非空元组，`not (True, False)` 恒为 False ⇒ **拦截永不触发**，
      "接线了但不设防"，比没接线更危险（看起来有开关，实际没有）。
      教训（v3.20.0 实测）：自检输出里打印出 `(True, False)` 却没深究，
      直到接线方断言 `enabled(...)` 的真假才暴露。**是否回落由 notes 传递，不占返回值。**
    """
    notes = notes if notes is not None else []
    v, _fell = _bool(_section(cfg, f"loop_{loop}").get("enabled"), "enabled", "enabled",
                     notes, f"loop_{loop}")
    return v


def state_path(cfg, workspace, loop, notes=None):
    """Loop 状态文件路径（harness.yaml#loop_{a,b}.state_file），占位符已解析。

    ⚠ 修的是一处真实漂移：配置写 Loop A 状态在 `<包>/.workbuddy/`，而代码此前
      硬写 `<工作区>/.workbuddy/loopA_state.json`——两处不一致，改配置不改行为。
      Loop B 两者恰好相同（`<工作区>/.workbuddy/loopB_state.json`），故此前无人发现。
    """
    notes = notes if notes is not None else []
    node = _section(cfg, f"loop_{loop}")
    raw, fell = _val(node.get("state_file"), "state_file", f"state_file_{loop}", notes, f"loop_{loop}")
    if fell:
        return os.path.join(workspace, _FB[f"state_file_{loop}"]), notes
    return os.path.abspath(resolve_placeholders(raw, workspace)), notes


def coexist_paths(cfg, workspace, notes=None):
    """(state_file, coexist_with) 两条绝对路径——用于"并存不覆盖"守卫。"""
    notes = notes if notes is not None else []
    lb = _section(cfg, "loop_b")
    sp, _ = state_path(cfg, workspace, "b", notes)
    raw = lb.get("coexist_with")
    if not raw or not isinstance(raw, str):
        notes.append("loop_b.coexist_with 未配置 → 无法做「并存不覆盖」守卫（跳过）")
        return sp, "", notes
    return sp, os.path.abspath(resolve_placeholders(raw, workspace)), notes


def coexist_guard(cfg, workspace, notes=None):
    """Loop B 状态文件不得与 task_state.json 撞车（loop_b.coexist_with）。

    判的是什么：两者若解析到**同一路径**，写 Loop B 状态会直接覆盖五道闸的既有
    状态机——这正是 round-review-sop.md#10「并存，不覆盖」要防的事故。
    此前该键零读取者：把 state_file 改成 coexist_with 的值，系统照样启动。
    """
    notes = notes if notes is not None else []
    sp, co, notes = coexist_paths(cfg, workspace, notes)
    if not co:
        return True, "未配置 coexist_with，跳过并存守卫", {"state_file": sp, "coexist_with": ""}
    if os.path.abspath(sp) == os.path.abspath(co):
        return False, (f"⛔ loop_b.state_file 与 loop_b.coexist_with 解析到同一路径 "
                       f"{sp}：写 Loop 状态会覆盖五道闸的 task_state.json"
                       f"（round-review-sop.md#10 要求并存不覆盖）"), {
            "state_file": sp, "coexist_with": co}
    return True, (f"ok：Loop B 状态 {sp} 与 {co} 并存，不覆盖"), {
        "state_file": sp, "coexist_with": co}


def single_writer(cfg, notes=None):
    """唯一写者（loop_b.single_writer）。"""
    notes = notes if notes is not None else []
    return _val(_section(cfg, "loop_b").get("single_writer"), "single_writer", "single_writer", notes, "loop_b")[0]


def single_writer_check(cfg, actor, notes=None):
    """写者身份校验（loop_b.single_writer）。

    判的是什么：**留痕 + 防误操作**——显式声明了别人（非 team-lead）在推进 Loop 状态
    即拒绝。诚实边界：**不防冒名**（平台无身份认证，成员照样可以传 --actor team-lead），
    所以它挡的是"误用与无声的越权"，不是"蓄意绕过"。
    """
    notes = notes if notes is not None else []
    writer = single_writer(cfg, notes)
    actor = (actor or "").strip()
    if not writer:
        return True, "loop_b.single_writer 未配置 → 不做写者校验", writer
    if not actor:
        notes.append(f"未传 --actor，无法校验写者（唯一写者应为 {writer!r}）——"
                     f"本次按未声明处理，落盘记 last_writer='未声明'")
        return True, f"未声明写者（唯一写者应为 {writer!r}）", writer
    if actor != writer:
        return False, (f"⛔ 写者不符：本次 --actor={actor!r}，唯一写者 {writer!r}"
                       f"（loop_b.single_writer；成员回传须由主理人汇编后落盘）"), writer
    return True, f"ok：写者 {actor!r} 与唯一写者一致", writer


def original_readonly(cfg, notes=None):
    """原件只读开关（loop_b.original_readonly）。

    ⚠ 返回**标量 bool**（理由同 `enabled`：调用点是 `if original_readonly(...)`，
      返回元组会让"关闭只读"这条分支永不生效——安全底线形同虚设）。
    """
    notes = notes if notes is not None else []
    v, _fell = _bool(_section(cfg, "loop_b").get("original_readonly"), "original_readonly",
                     "original_readonly", notes, "loop_b")
    return v


# ─────────────────────────── Loop A 批次门 ───────────────────────────
def loop_a_batch_cfg(cfg, notes=None):
    """Loop A 批次门三件套（confirm_before_each_batch / patch_discipline / regression_required）。"""
    notes = notes if notes is not None else []
    la = _section(cfg, "loop_a")
    confirm, _ = _bool(la.get("confirm_before_each_batch"), "confirm_before_each_batch", "confirm_before_each_batch",
                       notes, "loop_a")
    discipline, _ = _val(la.get("patch_discipline"), "patch_discipline", "patch_discipline", notes, "loop_a")
    reg, _ = _val(la.get("regression_required"), "regression_required", "regression_required", notes, "loop_a")
    if not isinstance(reg, list):
        reg = [str(reg)]
    return {"confirm_before_each_batch": confirm,
            "patch_discipline": str(discipline),
            "regression_required": [str(x) for x in reg]}


def regression_check(cfg, ran, notes=None):
    """回归项是否跑齐（loop_a.regression_required）。

    ran：已跑项列表（来自 --regression，逗号分隔）。缺一即不合格——
    "跑了两项就算了"是 Loop A 最典型的自评失真入口。
    """
    notes = notes if notes is not None else []
    required = loop_a_batch_cfg(cfg, notes)["regression_required"]
    ran_set = {str(x).strip() for x in (ran or []) if str(x).strip()}
    missing = [r for r in required if r not in ran_set]
    extra = sorted(ran_set - set(required))
    return (not missing), missing, required, extra


def patch_discipline_check(cfg, declared, actual, notes=None):
    """最小补丁纪律（loop_a.patch_discipline）的可判定部分。

    判的是什么：**改动集合 ⊆ 声明集合**（说改 scripts/x.py 就不能顺手改 config/y.yaml）。
    不判什么：改得多不多、该不该改——那是人的判断，代码判不了"最小"。

    actual 为 None 表示"拿不到实际改动集合"（如包目录不是 git 仓库 / 无 git），
    此时**不静默通过**：返回 ok=True 但 notes 里写明未比对，由调用方显式提示用户。
    """
    notes = notes if notes is not None else []
    discipline = loop_a_batch_cfg(cfg, notes)["patch_discipline"]
    declared = [str(x).strip() for x in (declared or []) if str(x).strip()]
    if discipline != "minimal":
        notes.append(f"loop_a.patch_discipline={discipline!r} —— 当前仅 'minimal' 有执行器，"
                     f"本批不做改动集合比对（只记档，不判定）")
        return True, [], declared
    if not declared:
        return False, [("no_declared_files",
                        "patch_discipline=minimal 要求开工前声明本批将改动的文件"
                        "（--files a.py,b.py）——未声明即无法判定是否最小")], declared
    if actual is None:
        notes.append("实际改动集合不可得（包目录非 git 仓库或 git 不可用）——"
                     "**未做**改动集合比对，不得据此宣称已遵守最小补丁纪律")
        return True, [], declared
    actual = [str(x).strip() for x in actual if str(x).strip()]
    extra = sorted(set(actual) - set(declared))
    problems = []
    if extra:
        problems.append(("undeclared_changes",
                         f"本批实际改动 {len(actual)} 个文件，其中 {len(extra)} 个超出声明范围："
                         f"{extra[:10]}——违反最小补丁纪律（loop_a.patch_discipline=minimal）"))
    return (not problems), problems, declared


# ─────────────────────────── Loop B 轮审判据 ───────────────────────────
def round_review_cfg(cfg, notes=None):
    """轮审五项判据（loop_b.round_review.*）。"""
    notes = notes if notes is not None else []
    rr = _section(_section(cfg, "loop_b"), "round_review")
    out = {}
    out["required"], _ = _bool(rr.get("required"), "required", "round_review_required", notes, "loop_b.round_review")
    out["silent_is_not_approval"], _ = _bool(rr.get("silent_is_not_approval"), "silent_is_not_approval",
                                             "silent_is_not_approval", notes, "loop_b.round_review")
    out["partial_accept_freezes_only_named"], _ = _bool(rr.get("partial_accept_freezes_only_named"), "partial_accept_freezes_only_named", "partial_accept_freezes_only_named",
        notes, "loop_b.round_review")
    out["rework_stays_in_round"], _ = _bool(rr.get("rework_stays_in_round"), "rework_stays_in_round",
                                            "rework_stays_in_round", notes, "loop_b.round_review")
    out["invalidation"], _ = _val(rr.get("invalidation"), "invalidation", "invalidation", notes, "loop_b.round_review")
    out["required_items"], _ = _int(rr.get("required_items"), "required_items", "round_review_required_items",
                                    notes, "loop_b.round_review")
    return out


def round_review_check(cfg, payload, notes=None):
    """轮报完整性（loop_b.round_review.required + required_items）。

    payload 可以是 dict 或 list：统计**非空项数**。为什么要数"非空"而不是查键名——
    round-review-sop.md#5 只规定六项**内容**，没规定键名；锁键名等于另立一份 schema，
    与 SOP 漂移时又是一处双源。故只校验"六项齐全且都非空"。
    """
    notes = notes if notes is not None else []
    rr = round_review_cfg(cfg, notes)
    if not rr["required"]:
        notes.append("loop_b.round_review.required=false → 本轮不强制轮报（不阻断）")
        return True, 0, rr["required_items"]
    if isinstance(payload, dict):
        n = sum(1 for v in payload.values() if v not in (None, "", [], {}))
    elif isinstance(payload, list):
        n = sum(1 for v in payload if v not in (None, "", [], {}))
    else:
        return False, 0, rr["required_items"]
    return n >= rr["required_items"], n, rr["required_items"]


def retrieval_budget(cfg, notes=None):
    """每轮检索预算（loop_b.budgets.retrieval_budget_per_round）——返回**标量 int**。

    ⚠ 必须标量：本函数是 `retrieval_check` 里 `used > limit` 比较的左操作数；
      返回元组会直接 TypeError（v3.20.0 接线时实测崩溃）。
    """
    notes = notes if notes is not None else []
    b = _section(_section(cfg, "loop_b"), "budgets")
    v, _fell = _int(b.get("retrieval_budget_per_round"), "retrieval_budget_per_round",
                    "retrieval_budget_per_round", notes, "loop_b.budgets")
    return v


def retrieval_check(cfg, used, notes=None):
    """检索预算是否触顶。此键此前零读取者——配了 30 次/轮的上限，机器从不计数。"""
    notes = notes if notes is not None else []
    limit = retrieval_budget(cfg, notes)
    used = int(used or 0)
    if used > limit:
        return False, (f"⛔ 本轮检索 {used} 次 > 上限 {limit}"
                       f"（loop_b.budgets.retrieval_budget_per_round）——"
                       f"停止检索，先把已有证据消化完再开口径")
    return True, f"ok：本轮检索 {used}/{limit} 次"


# ─────────────────────────── Loop B 默认档 ───────────────────────────
def defaults_view(cfg, notes=None):
    """本团默认档（loop_b.defaults.*）——供 `loop defaults` 展示与生成待确认模板。"""
    notes = notes if notes is not None else []
    d = _section(_section(cfg, "loop_b"), "defaults")
    if not d:
        notes.append("loop_b.defaults 整段缺失 → 无默认档可用（追问时须逐项问用户，不得编造）")
    return d


def defaults_ref_keys():
    """默认档里"指向包内文件"的键——这些必须做存在性核验（防引用悬空）。

    ⚠ 为什么返回**字典**而不是列表/元组：ensure_settings 第 18 项的 AST 读取点
      收集第③种形态是字典字面量的字符串键。这些键确实被真实消费（`d.get(k)` 按名字
      取，是一种间接读取），写成字典才能让巡检如实认账；写成元组会被判成死配置。
      值 = 该引用文件的内容说明（人读用，不参与判定）。
    """
    return {"profile_ref": "受众四层 / 课时映射 / 范围 / 验收矩阵",
            "audience_schema": "受众分层单一数据源",
            "template_ref": "默认模板指纹与三条硬约束",
            "delivery_ref": "交付三件套规格",
            "template_profile_ref": "模板档案（与 template_ref 同源）"}


def defaults_ref_check(cfg, notes=None):
    """默认档引用的包内文件是否都存在（改了文件名不会静默失效）。"""
    notes = notes if notes is not None else []
    d = defaults_view(cfg, notes)
    missing, present = [], []
    for k in defaults_ref_keys():
        v = d.get(k)
        if not v or not isinstance(v, str):
            notes.append(f"loop_b.defaults.{k} 未配置或为空 → 跳过存在性核验")
            continue
        p = os.path.join(PKG, v)
        (present if os.path.exists(p) else missing).append((k, v))
    return (not missing), missing, present


def intake_template_from_defaults(cfg, notes=None):
    """由默认档生成 intake 待确认模板（A 类五项，status 一律 suggested）。

    为什么这是真接线而不是"把默认值打印出来"：
      · 生成的模板**全部 status=suggested** —— 制作前置门只认 confirmed
        （task-intake-checklist.md#158），所以"不得用仓库默认值冒充用户确认"
        这条铁律由代码保证，而不是靠人记得住；
      · 模板内容随 loop_b.defaults.* 变化（受众/课时/范围/模板指纹…），
        改配置 → 生成的模板跟着变，有真实下游。
    """
    notes = notes if notes is not None else []
    d = defaults_view(cfg, notes)
    # ⚠ 模板这一项**不做回落**：本团若未登记默认模板，就必须是 None 并由用户指定。
    #   用内置值兜底 = 拿仓库默认值冒充用户确认，正是 task-intake-checklist 明令禁止的。
    tpl = d.get("default_template")
    if "default_template" in d and tpl in (None, ""):
        notes.append("loop_b.defaults.default_template 显式为空（本团未登记默认模板）"
                     "→ 模板一项必须由用户指定，不做回落（禁拿默认值冒充用户确认）")
    elif "default_template" not in d:
        notes.append("loop_b.defaults.default_template 键不存在 → 视为未登记，"
                     "不做回落（同上）")
    return {
        "audience": {"value": d.get("audience"), "status": "suggested",
                     "source": "harness.yaml#loop_b.defaults.audience"},
        "periods": {"value": d.get("hours_per_session"), "status": "suggested",
                    "source": "harness.yaml#loop_b.defaults.hours_per_session"},
        "template": {"value": tpl, "status": "suggested",
                     "source": "harness.yaml#loop_b.defaults.default_template",
                     "note": ("本团未登记默认模板，须用户指定（沿用/指定/重建）"
                              if tpl in (None, "") else
                              f"默认模板指纹 {d.get('template_fingerprint') or '未登记'}"
                              f"（详见 {d.get('template_profile_ref') or 'default-template-profile.md'}）")},
        "scope": {"value": d.get("scope"), "status": "suggested",
                  "source": "harness.yaml#loop_b.defaults.scope"},
        "acceptance": {"value": None, "status": "suggested", "source": "",
                       "note": "验收标准本团无默认值（task-intake-checklist.md#44）——"
                               "必须由用户给出，缺此项即停"},
        "_defaults_snapshot": {
            "audience_depth_scale": d.get("audience_depth_scale"),
            "time_structure": d.get("time_structure"),
            "keep_original_layout": d.get("keep_original_layout"),
            "geo_baseline_required": d.get("geo_baseline_required"),
            "profile_ref": d.get("profile_ref"),
            "audience_schema": d.get("audience_schema"),
            "delivery_ref": d.get("delivery_ref"),
        },
        "_note": ("本模板由 harness.yaml#loop_b.defaults 生成，所有条目 status=suggested。"
                  "**suggested ≠ confirmed**——须逐项请用户确认后改为 confirmed，"
                  "制作前置门（loop make-gate）只认 confirmed。"),
    }


def geo_baseline_required(cfg, notes=None):
    """成品 lint 是否必配几何基线（loop_b.defaults.geo_baseline_required）——返回**标量 bool**（理由同 `enabled`）。"""
    notes = notes if notes is not None else []
    d = _section(_section(cfg, "loop_b"), "defaults")
    v, _fell = _bool(d.get("geo_baseline_required"), "geo_baseline_required",
                     "geo_baseline_required", notes, "loop_b.defaults")
    return v


# ─────────────────────────── 增量门禁 delta_gate ───────────────────────────
def delta_gate_cfg(cfg, notes=None):
    """增量门禁全量判据（harness.yaml#delta_gate）。"""
    notes = notes if notes is not None else []
    g = _section(cfg, "delta_gate")
    out = {}
    out["baseline_required"], _ = _bool(g.get("baseline_required"), "baseline_required", "baseline_required",
                                        notes, "delta_gate")
    out["block_on_new_defects"], _ = _bool(g.get("block_on_new_defects"), "block_on_new_defects", "block_on_new_defects",
                                           notes, "delta_gate")
    out["miss_needs_human_review"], _ = _bool(g.get("miss_needs_human_review"), "miss_needs_human_review",
                                              "miss_needs_human_review", notes, "delta_gate")
    out["insert_spatial_audit"], _ = _bool(g.get("insert_spatial_audit"), "insert_spatial_audit", "insert_spatial_audit",
                                           notes, "delta_gate")
    out["image_caption_requires_reading"], _ = _bool(g.get("image_caption_requires_reading"), "image_caption_requires_reading",
                                                     "image_caption_requires_reading",
                                                     notes, "delta_gate")
    out["baseline_fields"], _ = _val(g.get("baseline_fields"), "baseline_fields", "baseline_fields", notes, "delta_gate")
    if not isinstance(out["baseline_fields"], list):
        out["baseline_fields"] = [str(out["baseline_fields"])]
    out["baseline_fields"] = [str(x) for x in out["baseline_fields"]]
    out["report_format"], _ = _val(g.get("report_format"), "report_format", "report_format", notes, "delta_gate")
    out["report_format"] = str(out["report_format"])
    out["caption_missing_element_policy"], _ = _val(g.get("caption_missing_element_policy"), "caption_missing_element_policy", "caption_missing_element_policy",
        notes, "delta_gate")
    out["caption_missing_element_policy"] = str(out["caption_missing_element_policy"])
    return out


def baseline_check(cfg, data, notes=None):
    """基线字段是否齐（delta_gate.baseline_fields）。字段名本身来自配置——
    加一个字段（如 export_pages）不用改代码即生效。"""
    notes = notes if notes is not None else []
    fields = delta_gate_cfg(cfg, notes)["baseline_fields"]
    data = data if isinstance(data, dict) else {}
    missing = [f for f in fields
               if f not in data or data[f] in (None, "", [], {})]
    if missing:
        notes.append(f"基线缺 {len(missing)} 个必填字段（delta_gate.baseline_fields）：{missing}")
    return (not missing), missing, fields


# 数值位识别：数字串**前面不是字母**才算数值位。
# 为什么必须排除字母后的数字：`P0=6（基线 6，自引入 0）` 里的 "P0" 是**指标名**不是数值，
#   裸 r"\d+" 会把 "P0" 的 0 也当成占位符 → 模板变成 `P{}={}（...）`（4 个槽）→ 渲染错位。
#   实测踩到：首次自检即报 "Replacement index 3 out of range"。
# 局限（如实标注）：若将来把指标名写成纯数字（如 "0=6"），本启发式会误判并告警跳过。
_NUM_SLOT = re.compile(r"(?<![A-Za-z])\d+")


def _format_slots(fmt, notes):
    """返回 (模板串, 数值位数)；位数不足 3 时记 note 并返回 (None, n)。"""
    parts = _NUM_SLOT.split(fmt)
    n = len(parts) - 1
    if n < 3:
        notes.append(f"delta_gate.report_format={fmt!r} 只识别到 {n} 个数值位（需 3 个："
                     f"当前/基线/自引入）——格式渲染与合规校验**未生效**，须按声明格式重写")
        return None, n
    if n > 3:
        notes.append(f"delta_gate.report_format={fmt!r} 识别到 {n} 个数值位（>3）——"
                     f"只按前 3 个渲染，其余按原样保留")
    return _NUM_SLOT.sub("{}", fmt), n


def delta_pattern(cfg, notes=None):
    """由 delta_gate.report_format 生成校验正则（示例串 → 模板 → 正则）。

    例：`P0=6（基线 6，自引入 0）` → `^P0=(-?\\d+)（基线 (-?\\d+)，自引入 (-?\\d+)）$`
    改配置里的格式串，正则随之改变 —— 这是"报告格式"这条纪律从文档变成判据的关键。
    """
    notes = notes if notes is not None else []
    fmt = delta_gate_cfg(cfg, notes)["report_format"]
    if _format_slots(fmt, notes)[0] is None:
        return None, fmt
    parts = _NUM_SLOT.split(fmt)
    body = "".join(re.escape(p) + r"(-?\d+)" for p in parts[:-1]) + re.escape(parts[-1])
    return re.compile(r"^" + body + r"$"), fmt


def render_delta_report(cfg, current, baseline, notes=None):
    """渲染增量报告行 + 自校验（格式合规 + 数值守恒）。

    守恒校验：`P0 = 基线 + 自引入`。自引入为负 = 本轮修好了 N 个（合法）；
    报告里三个数对不上，说明报告与基线不是同一套数——退回复算，不猜。
    """
    notes = notes if notes is not None else []
    fmt = delta_gate_cfg(cfg, notes)["report_format"]
    delta = int(current) - int(baseline)
    template, _n = _format_slots(fmt, notes)
    if template is None:
        return {"text": "", "ok": False, "delta": delta, "notes": notes,
                "conserved": False, "pattern_ok": False, "format": fmt,
                "current": int(current), "baseline": int(baseline)}
    try:
        text = template.format(int(current), int(baseline), delta)
    except Exception as e:
        notes.append(f"delta_gate.report_format={fmt!r} 渲染失败（{e}）——不产出报告行")
        return {"text": "", "ok": False, "delta": delta, "notes": notes,
                "conserved": False, "pattern_ok": False, "format": fmt}
    pat, _ = delta_pattern(cfg, notes)
    m = pat.fullmatch(text) if pat else None
    pattern_ok = bool(m)
    if pat is None:
        notes.append("无校验正则（report_format 不含数字）→ 格式合规**未判定**")
    elif not m:
        notes.append(f"报告行 {text!r} 不符合 delta_gate.report_format={fmt!r} 生成的格式——"
                     f"退回按声明格式重写")
    conserved = (m is not None) and (int(m.group(1)) == int(m.group(2)) + int(m.group(3)))
    if m is not None and not conserved:
        notes.append(f"数值不守恒：P0={m.group(1)} ≠ 基线 {m.group(2)} + 自引入 {m.group(3)}"
                     f"——报告与基线不是同一套数，退回复算")
    return {"text": text, "ok": bool(pattern_ok and conserved), "delta": delta,
            "notes": notes, "conserved": conserved, "pattern_ok": pattern_ok,
            "format": fmt, "current": int(current), "baseline": int(baseline)}


def delta_verdict(cfg, baseline, current, notes=None):
    """增量门禁总判：自引入新缺陷是否阻断（delta_gate.block_on_new_defects）。

    baseline / current 均为 {p0,p1,p2} 之类同键字典；任一指标上升即"自引入"。
    miss_needs_human_review=true 且基线/当前缺数 → **不按 0 处理**，转人工复核。
    """
    notes = notes if notes is not None else []
    g = delta_gate_cfg(cfg, notes)
    baseline = baseline if isinstance(baseline, dict) else {}
    current = current if isinstance(current, dict) else {}
    keys = ["p0", "p1", "p2"]
    missing_base = [k for k in keys if k not in baseline]
    missing_cur = [k for k in keys if k not in current]
    if (missing_base or missing_cur) and g["miss_needs_human_review"]:
        notes.append(f"基线缺 {missing_base} / 当前缺 {missing_cur} ——"
                     f"delta_gate.miss_needs_human_review=true：**不按 0 补齐**，"
                     f"须人工复核后再判（机器 MISS 未经复核不得计入缺陷）")
        return {"ok": False, "blocked": True, "reason": "missing_needs_human_review",
                "increased": [], "reports": [], "notes": notes}
    increased, reports = [], []
    for k in keys:
        b = int(baseline.get(k, 0) or 0)
        c = int(current.get(k, 0) or 0)
        if c > b:
            increased.append({"metric": k, "baseline": b, "current": c, "delta": c - b})
        r = render_delta_report(cfg, c, b, notes) if k == "p0" else None
        if r:
            reports.append({"metric": k, "report": r["text"], "ok": r["ok"]})
    bad_fmt = [r for r in reports if not r["ok"]]
    blocked = bool(increased) and g["block_on_new_defects"]
    if increased and not g["block_on_new_defects"]:
        notes.append(f"delta_gate.block_on_new_defects=false → 自引入 {len(increased)} 项"
                     f"只提示不阻断（关闭此开关须用户知情：等于允许边改边坏）")
    return {"ok": (not blocked) and (not bad_fmt), "blocked": blocked,
            "reason": ("new_defects" if blocked else ("bad_report_format" if bad_fmt else "")),
            "increased": increased, "reports": reports, "notes": notes}


def spatial_audit_check(cfg, lint_report, notes=None):
    """插入物空间避让审计（delta_gate.insert_spatial_audit）。

    执行者：ooxml_lint 的 GEO-003（`summary.geo_new_overlap` = 新增重叠条数）。
    未提供 lint 报告 ≠ 没问题 —— 声明要求审计却拿不出报告，按**未做**阻断。
    """
    notes = notes if notes is not None else []
    g = delta_gate_cfg(cfg, notes)
    if not g["insert_spatial_audit"]:
        notes.append("delta_gate.insert_spatial_audit=false → 不做空间避让审计")
        return True, "未要求（insert_spatial_audit=false）", None
    if not isinstance(lint_report, dict):
        return False, ("⛔ insert_spatial_audit=true 但未提供 ooxml_lint 报告（--lint-json）——"
                       "拿不出报告即视为**未做**审计，不得放行"), None
    summ = lint_report.get("summary")
    if not isinstance(summ, dict) or "geo_new_overlap" not in summ:
        return False, ("⛔ lint 报告缺 summary.geo_new_overlap —— 无法判定新增重叠"
                       "（须 `ooxml_lint.py <新版.pptx> --geo-baseline <模板.pptx> --json`）"), None
    n = int(summ.get("geo_new_overlap") or 0)
    inherited = summ.get("geo_inherited")
    if n > 0:
        return False, (f"⛔ 新增重叠 {n} 处（GEO-003）——插入物未避让既有形状，"
                       f"须重新排版后重插（模板固有叠放 {inherited} 处已豁免）"), n
    return True, f"ok：新增重叠 0 处（模板固有叠放 {inherited} 处已豁免）", n


def caption_elements_source(notes=None):
    """图注要素唯一源：visual-rules.yaml#caption_base_elements（通用骨架 3 项）。

    ⚠ 不读已 deprecated 的 caption_five_elements（v3.18.0 起判定只认骨架，
      域扩展在 domain-profiles.yaml#domains[].image_channel.caption_extra_elements）。
    """
    notes = notes if notes is not None else []
    path = os.path.join(PKG, "config", "visual-rules.yaml")
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            v = yaml.safe_load(f) or {}
    except Exception as e:
        notes.append(f"visual-rules.yaml 读取失败（{e}）——图注要素清单不可得，跳过要素核验")
        return [], path
    base = v.get("caption_base_elements")
    if not isinstance(base, list) or not base:
        notes.append("visual-rules.yaml#caption_base_elements 缺失或为空 → 跳过要素核验")
        return [], path
    return [str(x) for x in base], path


def caption_check(cfg, elements, notes=None):
    """图注要素缺项处理（delta_gate.caption_missing_element_policy）。

    policy == "explicit_todo"：缺项**显式挂账**（返回 todo 列表），禁静默省略——
    代码能保证的是"缺了必须写出来"，不能保证"写出来就一定对"。
    其他 policy 值：无执行器，告警说明，不做挂账（不假装处理了）。
    """
    notes = notes if notes is not None else []
    policy = delta_gate_cfg(cfg, notes)["caption_missing_element_policy"]
    base, src = caption_elements_source(notes)
    elements = [str(x).strip() for x in (elements or []) if str(x).strip()]
    missing = [e for e in base if e not in elements]
    if policy != "explicit_todo":
        notes.append(f"delta_gate.caption_missing_element_policy={policy!r} —— "
                     f"当前仅 'explicit_todo' 有执行器；缺项**未挂账**，"
                     f"不得据此宣称已按策略处置")
        return {"ok": True, "missing": missing, "todo": [], "policy": policy,
                "base_elements": base, "source": src, "executed": False}
    return {"ok": not missing, "missing": missing, "todo": missing, "policy": policy,
            "base_elements": base, "source": src, "executed": True}


def image_caption_requires_reading(cfg, notes=None):
    """图像类图注是否必须附判读记录（delta_gate.image_caption_requires_reading）。

    诚实边界：代码执行的是**留痕强制**（有没有判读记录），不是**判读正确性**
    （记录写的是不是真的）——后者只能由人复核，不得宣称机器已判。
    返回**标量 bool**（理由同 `enabled`）。
    """
    notes = notes if notes is not None else []
    v, _fell = _bool(_section(cfg, "delta_gate").get("image_caption_requires_reading"),
                     "image_caption_requires_reading", "image_caption_requires_reading",
                     notes, "delta_gate")
    return v


def image_caption_check(cfg, read_log, notes=None):
    """图注条目登记时的判读留痕校验。"""
    notes = notes if notes is not None else []
    required = image_caption_requires_reading(cfg, notes)
    has = bool(read_log and str(read_log).strip())
    if not required:
        notes.append("delta_gate.image_caption_requires_reading=false → 不强制判读留痕")
        return True, ""
    if not has:
        return False, ("⛔ 图像类图注条目必须附判读记录（--read-log）——"
                       "delta_gate.image_caption_requires_reading=true；"
                       "判读不出的特征不得写（迭代六原则·素材判读红线）")
    return True, f"ok：已附判读记录（{read_log}）"


# ─────────────────────────── 自检 ───────────────────────────
def _self_check():
    """最小自检：加载真实配置跑一遍全部判定，打印是否走了回落（回落必须可见）。"""
    path = os.path.join(PKG, "config", "harness.yaml")
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"⚠ harness.yaml 读取失败（{e}）——自检无法进行", file=__import__("sys").stderr)
        return 1
    ws = PKG
    rows = []
    notes = []

    # ── 标量守卫（v3.20.0 血的教训）───────────────────────────────
    # 这 5 个函数的调用点都是 `if not enabled(...)` / `used > limit` 这类**直接当标量用**
    # 的写法。若它们返回 `(值, 是否回落)` 元组：
    #   · `not (True, False)` 恒为 False ⇒ 环启用检查**永不拦截**（接线了但不设防）
    #   · `used > (30, False)` 直接 TypeError
    # 首次自检时打印出 `(True, False)` 却没人深究，直到接线方断言真假才暴露。
    # ⇒ 把类型断言写进自检，让"看起来有开关、实际没有"这类假绿在自检阶段就转红。
    _scalar_expect = (
        ("enabled", enabled(cfg, "a", notes), bool),
        ("original_readonly", original_readonly(cfg, notes), bool),
        ("retrieval_budget", retrieval_budget(cfg, notes), int),
        ("geo_baseline_required", geo_baseline_required(cfg, notes), bool),
        ("image_caption_requires_reading", image_caption_requires_reading(cfg, notes), bool),
        ("single_writer", single_writer(cfg, notes), str),
    )
    for _name, _v, _typ in _scalar_expect:
        ok = isinstance(_v, _typ) and not isinstance(_v, bool) or (isinstance(_v, bool) and _typ is bool)
        print(f"  [标量守卫] {_name}: {_v!r} {'✓' if ok else '✗ 应为 ' + _typ.__name__}")
        if not ok:
            notes.append(f"❌ {_name} 返回值类型错误（{type(_v).__name__}，应为 {_typ.__name__}）"
                         f"——调用点直接当标量用，类型错 = 判定永不生效")

    rows.append(("loop_a.enabled", enabled(cfg, "a", notes)))
    rows.append(("loop_b.enabled", enabled(cfg, "b", notes)))
    rows.append(("loop_a.state_file", state_path(cfg, ws, "a", notes)))
    rows.append(("loop_b.state_file", state_path(cfg, ws, "b", notes)))
    rows.append(("coexist_guard", coexist_guard(cfg, ws, notes)[0]))
    rows.append(("single_writer", single_writer(cfg, notes)))
    rows.append(("original_readonly", original_readonly(cfg, notes)))
    rows.append(("retrieval_budget", retrieval_budget(cfg, notes)))
    rows.append(("round_review", round_review_cfg(cfg, notes)))
    rows.append(("geo_baseline_required", geo_baseline_required(cfg, notes)))
    rows.append(("delta_gate", delta_gate_cfg(cfg, notes)))
    ok, missing, present = defaults_ref_check(cfg, notes)
    rows.append(("defaults_refs", {"ok": ok, "missing": missing, "present": len(present)}))
    r = render_delta_report(cfg, 6, 6, notes)
    rows.append(("delta_report", {"text": r["text"], "ok": r["ok"]}))
    rows.append(("patch_discipline_check",
                 patch_discipline_check(cfg, ["a.py"], ["a.py", "b.py"], notes)[0]))
    for k, v in rows:
        print(f"  {k}: {v}")
    if notes:
        print("\n回落/降级提示（必须可见，不得静默）：")
        for n in notes:
            print(f"  ⚠ {n}")
    else:
        print("\n无回落：全部判据均取自 config/harness.yaml")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        sys.exit(_self_check())
    print(__doc__)

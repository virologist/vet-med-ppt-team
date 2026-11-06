#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trace_events.py — trace 事件「声明 vs 产出」回归（v3.17.0 B3-2）

立项背景（不是"补几个事件"的例行动作）：
  config/harness.yaml#observability.trace_events 声明了一组 trace 事件，
  但 v3.17.0 独立复核实测**只有 5 个有代码产出**（gate / stage_enter / stage_exit /
  budget_exceeded / no_progress），另外 7 个是**纯声明**：
      team_create / preflight / spawn / spawn_failed / degrade / member_return / error

  代价是立项级的：同一份 yaml 的 fallback.require_disclosure=true 写着
  "降级必须在交付物与 trace 中显式声明"，而 degrade 事件**没有任何代码产出**
  ⇒ "降级是否发生、是否被声明"在 trace 里根本查不到。
  这正是 v2.2.0 建立整个 harness 层的原始理由（"静默降级无人察觉"）被自己重犯。

本文件把这件事钉成机器断言：
  ① 全部声明的事件**逐个**有真实产出（跑真命令 → 读真 trace 文件 → 断言事件在）；
  ② trace report 能报出"声明了但没产出"的差集（declared_events_missing）；
  ③ trace report 能报出"产出了但没声明"的差集（undeclared_events）——
     这是同型反向缺口（agent_spawn 曾是这种：代码在产、yaml 没登记）；
  ④ degrade 事件必须带齐"成员 id / 降级通道 / 原因"三要素——
     这是 fallback.require_disclosure 的机器可查形态。

用法：
    python3 -m pytest scripts/test_trace_events.py -q     # pytest 收集
    python3 scripts/test_trace_events.py                  # 直跑（ensure_settings 第 7 项会跑）
退出码（直跑）：0=全通过 1=有用例失败
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
HARNESS = os.path.join(HERE, "harness.py")

PASS, FAIL = [], []

# yaml#observability.trace_events 声明的全部事件
# ⚠ v3.18.0：**从 yaml 读**（唯一源 = config/harness.yaml），不再硬编码列表——
#   硬编码副本正是「同一口径两处各写一套」的病灶：v3.18.0 加了 compaction 事件后，
#   本文件因硬编码旧列表而误报失败（事件名是**声明与代码的契约**，改一处必须同步另一处——
#   但更好的做法是**根本不要写第二份**）。
def _declared_events_from_yaml():
    """从 config/harness.yaml#observability.trace_events 读声明的事件名列表。"""
    import yaml
    ypath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "config", "harness.yaml")
    with open(ypath, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ev = ((cfg.get("observability") or {}).get("trace_events") or [])
    return [str(x) for x in ev]


DECLARED_EVENTS = tuple(_declared_events_from_yaml())


def _pkg_changed_files():
    """取包内当前 git 改动文件 → (scope 内, scope 外) 两个绝对路径列表。

    ⚠ **v3.28.7（R9b）：声明集必须按 `loop_a.scope` 过滤**。

    病灶（本轮体检第 7 项红灯的真实根因）：本函数原先返回**全量**改动，
    而它的结果被当作 `loop batch-open --files` 的声明集；`batch-open` 会对
    每个声明文件跑越界校验 `_loop_a_scope_check` ⇒ **scope 外的改动**
    （如 `.learnings/`，本包纪律要求的经验登记目录）会让整批被拒 ⇒
    `batch_open` / `batch_close` 两个 trace 事件不落账 ⇒
    守卫「声明事件全部有产出」断言的 **missing 方向红**。

    ⇒ **工作区洁净度不是生产行为的判据**，二者不得耦合：
      scope 外的改动单列（保持可观测），**绝不混入声明集**。
    """
    import subprocess as _sp
    try:
        p = _sp.run(["git", "-C", PKG, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=20)
    except Exception:
        return [], []
    if p.returncode != 0:
        return [], []
    files = []
    for line in p.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ")[-1]
        files.append(os.path.join(PKG, rest.strip()))
    scope = _pkg_yaml_loop_a_scope()
    declared, out_of_scope = [], []
    for f in files:
        t = os.path.abspath(f)
        if any(t == p or t.startswith(p.rstrip("/") + "/") for p in scope):
            declared.append(t)
        else:
            out_of_scope.append(t)
    return declared, out_of_scope


def _pkg_yaml_regression_required():
    """读 yaml#loop_a.regression_required 现值（唯一源；硬编码=双源漂移）。

    B20-④ 扩容到 7 项后，本文件的 batch-close 触发须与生产同源取清单——
    硬编码三项会在收批时被判 regression_incomplete（rc=1）⇒ batch_close
    事件不落账本 ⇒ 契约用例假红。
    """
    import yaml as _y
    with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
        cfg = _y.safe_load(f) or {}
    return [str(x) for x in ((cfg.get("loop_a") or {}).get("regression_required") or [])]


def _pkg_yaml_loop_a_scope():
    """读 yaml#loop_a.scope 现值（唯一源；硬编码=双源漂移）。

    v3.28.7（R9b）：守卫的 batch-open 声明集必须按 scope 过滤，
    而 scope 的判定依据**只能**来自 yaml —— 硬编码一份路径列表就是
    第二份口径，改了 yaml 忘了改代码就会重演 R9b 式的假红。
    路径里的 `<包>` 占位符在此替换为包根（与 harness.yaml 的 scope 写法对齐）。
    """
    import yaml as _y
    with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
        cfg = _y.safe_load(f) or {}
    scope = ((cfg.get("loop_a") or {}).get("scope") or [])
    return [os.path.abspath(str(p).replace("<包>", PKG)) for p in scope]


def _last_batch_id(w):
    """取最近一次 batch-open 产生的批次 id（B13 契约触发用）。

    ⚠ Loop A 状态是**包级**的（state_file 恒为 <包>/.workbuddy/loopA_state.json），
      **不随 --workspace 变** ⇒ 不能去临时 workspace 里找。
    """
    p = os.path.join(PKG, ".workbuddy", "loopA_state.json")
    if not os.path.exists(p):
        return ""
    try:
        st = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ""
    batches = st.get("batches") or {}
    if not batches:
        return ""
    return sorted(batches.keys())[-1]


def run(args, cwd=None):
    p = subprocess.run([sys.executable, HARNESS] + args, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def check(name, cond, extra=""):
    """唯一断言口：记 PASS/FAIL，失败时抛 AssertionError（pytest 可见）。"""
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(name)
        msg = f"{name}  {extra}"
        print(f"  ❌ {msg}")
        raise AssertionError(msg)


def _trace_events(ws):
    """读工作区里的 trace 文件 → 事件名列表（保序）。"""
    p = os.path.join(ws, ".workbuddy", "harness_trace.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line).get("event"))
        except Exception:
            pass
    return out


def _trace_records(ws):
    """读工作区里的 trace 文件 → 完整记录列表。"""
    p = os.path.join(ws, ".workbuddy", "harness_trace.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _ws():
    return tempfile.TemporaryDirectory()


# ══════════════════════════ 用例 ══════════════════════════
def _make_deck(path):
    """造一份最小 pptx（gate 事件需要真课件）；python-pptx 不可用时退化为占位文件。"""
    try:
        from pptx import Presentation
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(path)
        return True
    except Exception:
        with open(path, "wb") as f:
            f.write(b"PK\x03\x04fake-deck-for-trace-events-test")
        return False


def test_声明的全部事件都有代码产出():
    """逐个跑真命令 → 读真 trace 文件 → 断言该事件在文件里。

    这是本任务的核心断言：**声明了却没有产出点**的事件，任何一个都会让本用例红。
    """
    with _ws() as w:
        # team_create：路由判出要建队（L1+）→ 写 team_create
        run(["route", "--level", "L2", "--workspace", w])
        # preflight：开工前可用性预检 → 写 preflight
        run(["preflight", "--team", "vet-med-ppt-team", "--task-id", "T1", "--workspace", w])
        # spawn：spawn 成功 → 写 spawn
        run(["spawn", "--agent", "dvm-content-expert", "--task-id", "T1", "--stage", "1",
             "--input-bytes", "1200", "--output-bytes", "800", "--workspace", w])
        # spawn_failed：spawn 失败 → 写 spawn_failed
        run(["spawn-failed", "--agent", "pedagogy-architect", "--task-id", "T1", "--stage", "1",
             "--attempt", "2", "--reason", "平台返回 not available", "--workspace", w])
        # degrade：成员降级 → 写 degrade
        run(["degrade", "--agent", "pedagogy-architect", "--task-id", "T1", "--stage", "1",
             "--channel", "general-purpose+persona", "--reason", "spawn 2 次均不可用", "--workspace", w])
        # member_return：成员回传 → 写 member_return
        run(["member-return", "--agent", "dvm-content-expert", "--task-id", "T1", "--stage", "1",
             "--status", "success", "--artifact", "out/blueprint.md", "--workspace", w])
        # stage_enter / stage_exit：既有产出点
        run(["stage", "--action", "enter", "--stage", "1", "--task-id", "T1", "--workspace", w])
        run(["stage", "--action", "exit", "--stage", "1", "--task-id", "T1", "--workspace", w])
        # budget_exceeded：超限即写
        run(["budget", "reset", "--kind", "spawn", "--workspace", w])
        run(["budget", "spend", "--kind", "spawn", "--n", "99", "--workspace", w])
        # no_progress：连续 N 轮 P0+P1 未下降 → 写（loop continue 路径）
        deck = os.path.join(w, "demo.pptx")
        _make_deck(deck)
        run(["loop", "start", "--deck", deck, "--workspace", w])
        # v3.20.0：loop_b.round_review.required=true 已由 loop_contract 接成**硬判据**——
        #   缺轮报 ⇒「本轮无效」exit 1，进位根本不发生 ⇒ no_progress 事件也走不到。
        #   故每轮进位前先登记六项轮报（否则本用例测的是"进位被拦"而非"无进展"）。
        for i, p0 in enumerate((3, 3, 3), 1):
            _rr = os.path.join(w, f"round_review_{i}.json")
            with open(_rr, "w", encoding="utf-8") as f:
                json.dump({"本轮改了什么": "本轮修订", "依据": "verify_deck 报告",
                           "未解决": "无", "下一步": "等用户裁决",
                           "风险": "无", "需用户裁决": "无"}, f, ensure_ascii=False)
            run(["loop", "review", "--file", _rr, "--workspace", w])
            run(["loop", "continue", "--decision", "accept", "--confirmed",
                 "--p0", str(p0), "--p1", "2", "--p2", "5", "--allow-unverified",
                 "--workspace", w])
        # gate：既有产出点（需真课件；用最小 pptx 触发 verify_deck → 写 gate 事件）
        gate_deck = os.path.join(w, "gate_demo.pptx")
        _make_deck(gate_deck)
        run(["gate", "--deck", gate_deck, "--hours", "1", "--level", "P0", "--no-snap",
             "--workspace", w])
        # ── B13/B14/B16 补触发（声明了却没在本用例产出 ⇒ 契约测试红）──────────
        # B13：批次动作与缺陷回流入账本
        # ⚠ 声明文件集必须**覆盖当前包内 scope 内的全部 git 改动**——batch-close 按
        #   `git status --porcelain` 算实际改动集（loop_a.patch_discipline=minimal），
        #   声明不全 ⇒ 判 undeclared_changes 拒绝收批 ⇒ batch_close 事件不落账本。
        #   故此处动态取当前改动集声明（不是硬编码清单——硬编码会随工作区漂移而失效）。
        # ⚠ v3.28.7（R9b）：**只取 scope 内的**。scope 外的改动（如 .learnings/）
        #   混进声明集 ⇒ batch-open 整批被拒 ⇒ batch_open/batch_close 事件不落账
        #   ⇒ 本用例误报「声明事件未产出」。
        _changed, _out_scope = _pkg_changed_files()
        _bo = run(["loop", "batch-open", "--loop", "a", "--actor", "team-lead",
                   "--note", "契约测试批次",
                   "--files", ",".join(_changed) if _changed else "scripts/harness.py",
                   "--workspace", w])
        if _out_scope:
            # 可观测而非静默丢弃；措辞刻意避开「事件缺失/未产出」——
            # 那类措辞会把「工作区状态」误读为「生产缺陷」。
            print(f"ℹ️ 本批有 {len(_out_scope)} 个改动文件在 loop_a.scope 之外"
                  f"（未纳入声明集）：{_out_scope[:5]}")
        try:
            _bid = str((json.loads(_bo[1]).get("batch") or {}).get("id") or "")
        except Exception:
            _bid = ""
        # 回归清单必须**跑齐** loop_a.regression_required（B20-④ 扩容后 7 项；
        # 动态取 yaml 现值——硬编码会在下次扩容时假红），且每个套件名真实
        # 存在（B19 真实性校验：未知名 ⇒ rc=2 拒绝 ⇒ batch_close 不落账本）。
        _req = _pkg_yaml_regression_required()
        run(["loop", "batch-close", "--loop", "a", "--actor", "team-lead",
             "--batch", _bid, "--confirmed",
             "--regression", ",".join(_req),
             "--workspace", w])
        run(["loop", "reflow", "--loop", "a", "--actor", "team-lead",
             "--file", os.path.join(PKG, "references", "defect-reflow.yaml"),
             "--workspace", w])
        # B14：成员写权限校验（放行路径也要产事件）
        run(["member-write-check", "--agent", "verifier",
             "--path", os.path.join(w, "reports", "x.md"), "--workspace", w])
        # B16：质量闭环三件套
        _cases_dir = os.path.join(w, ".workbuddy", "cases")
        os.makedirs(_cases_dir, exist_ok=True)
        with open(os.path.join(_cases_dir, "cases_library.json"), "w", encoding="utf-8") as f:
            json.dump({"cases": [{"case_id": "C-1", "disease_name": "案例",
                                  "title": "常规背景案例"}]}, f, ensure_ascii=False)
        run(["verify-tier", "--workspace", w])
        run(["sediment", "--target", "domain_profile",
             "--evidence-ref", "config/domain-profiles.yaml#demo",
             "--summary", "契约测试沉淀", "--workspace", w])
        run(["trend", "--workspace", w])
        # B17：域包五件套 machine-check → 写 domain_pack_check。
        #   ⚠ B19 修复的契约盲区：B17 加事件后本用例没补触发——
        #   「声明了却没产出」检查对新事件失明 8 天（双向对账 T4 补上后
        #   才暴露 yaml 侧也漏）。真命令跑一遍，产出点在此闭环。
        run(["domain-pack-check", "--workspace", w])
        # ── v3.28.9（C1-a / R9）：补齐 10 类新登记事件的触发路径 ──────────
        #   背景：C1-a 把 10 类此前逃逸的事件登记进 yaml 声明面，
        #   而本用例断言「**声明面里的每个事件都要有产出**」
        #   ⇒ 不补触发路径 ⇒ 登记即违约（实测报错：缺产出 6 类）。
        # ⚠ 本文件用 `run()` 取 rc，**不按 rc 判成败**（只看事件是否出现在 trace 里）
        #   ⇒ 故 `self_report_false` 的 rc=1（命令语义：文件不存在⇒自报不实）不影响断言。
        #
        # insight_carrier_init：洞察载体初始化（登记目标集）
        run(["insights", "init", "--task-id", "T1", "--target", "s1",
             "--kind", "page", "--workspace", w])
        # self_report_false：核验成员自报落盘 → 文件不存在 ⇒ 判定自报不实 ⇒ 写事件
        run(["verify-artifact", "--path", os.path.join(w, "不存在.md"), "--workspace", w])
        # verify_ref：文献引用预检（需先造最小 cases_library.json）
        _cases_p = os.path.join(w, ".workbuddy", "cases", "cases_library.json")
        os.makedirs(os.path.dirname(_cases_p), exist_ok=True)
        with open(_cases_p, "w", encoding="utf-8") as f:
            json.dump({"cases": [{"case_id": "C-1", "disease_name": "案例",
                                  "title": "常规背景案例"}]}, f, ensure_ascii=False)
        run(["verify-ref", "--path", _cases_p, "--workspace", w])
        # template_audit：模板指纹盘点
        run(["template-audit", "--root", w, "--workspace", w])
        # sweep：全量 pptx 扫描（产出 deck_registry）
        run(["sweep", "--root", w, "--workspace", w])
        # eval：自动化演进环 diff
        #   ⚠ **必须跑两次**：首次 eval 只存基线（rc=0 但**不写事件**），
        #     第二次才走 diff 路径并写 eval 事件。
        run(["eval", "--root", w, "--workspace", w])
        run(["eval", "--root", w, "--workspace", w])
        # error：顶层异常出口（经 run_command 注入异常——异常路径不能只藏在 __main__ 里）
        sys.path.insert(0, HERE)
        import harness as _h

        class _Boom:
            workspace = w
            func = staticmethod(lambda a: (_ for _ in ()).throw(RuntimeError("注入的运行期异常")))
        _h.run_command(_Boom())
        # compaction：v3.18.0 新增事件（`state compact` 状态压缩路径）
        #   先造一个够大的状态文件（超 state_max_bytes 才有压缩意义），
        #   再跑 state compact → 写 compaction 事件。
        _big_state = os.path.join(w, ".workbuddy", "task_state.json")
        os.makedirs(os.path.dirname(_big_state), exist_ok=True)
        _big = {"task_id": "T1", "workflow": "WF-1", "current_stage": 1,
                "stage_history": [{"stage": i, "status": "entered",
                                   "ts": "2026-10-25T00:00:00+08:00",
                                   "summary": "第 %d 闸的详细摘要，" % i + "长文本" * 200}
                                  for i in range(60)],
                "user_confirmations_pending": [], "tool_probe_results": {},
                "budget": {}, "next_action": "继续", "compaction": {}}
        with open(_big_state, "w", encoding="utf-8") as f:
            json.dump(_big, f, ensure_ascii=False)
        run(["state", "compact", "--workspace", w])

        evs = _trace_events(w)
        missing = [e for e in DECLARED_EVENTS if e not in evs]
        # ⚠ v3.28.7（R9b）：失败文案必须区分两类缺口——
        #   「本用例触发路径未覆盖该事件」＝真实缺口（守卫该红就红）；
        #   「工作区状态影响」＝非缺口（不得让守卫把前者误报成后者）。
        check(f"trace：{len(DECLARED_EVENTS)} 个声明事件全部有产出（实际产出 {sorted(set(evs))}）",
              not missing,
              f"缺产出：{missing}（本用例触发路径未覆盖该事件；"
              f"与工作区改动状态无关——scope 外改动已排除在声明集外）")


def test_声明与产出双向差集可查():
    """trace report 必须报出两个方向的差集。

    ① declared_events_missing —— "声明了却没产出"（本轮治的病）
    ② undeclared_events     —— "产出了却没声明"（反向同型病；agent_spawn 曾是这种）

    B19 追加第 ③ 向：**yaml 声明集 == harness#TRACE_EVENTS_DECLARED 常量集**
    （双向差集皆空）。第三轮诊断实测两份手工声明已各漂 1 项——
    单靠「yaml→产出」单向检查对「常量侧多/少」失明。
    """
    # ③ 常量侧对账（不依赖工作区，先判）
    sys.path.insert(0, HERE)
    import harness as _harness_mod
    _const = set(getattr(_harness_mod, "TRACE_EVENTS_DECLARED", ()) or ())
    check("trace：yaml 事件集 == harness 常量集（双向差集空）",
          set(DECLARED_EVENTS) == _const,
          f"yaml-only={sorted(set(DECLARED_EVENTS) - _const)} "
          f"const-only={sorted(_const - set(DECLARED_EVENTS))}")
    with _ws() as w:
        run(["spawn", "--agent", "dvm-content-expert", "--task-id", "T1", "--workspace", w])
        rc, out, _ = run(["trace", "report", "--workspace", w])
        try:
            rep = json.loads(out)
        except Exception:
            check("trace report 可解析", False, out[:200])
            return
        check("trace report 输出 declared_events（yaml 声明的全集）",
              set(rep.get("declared_events") or []) == set(DECLARED_EVENTS),
              f"got {rep.get('declared_events')}")
        check("trace report 输出 declared_events_missing（声明了却没产出的）",
              isinstance(rep.get("declared_events_missing"), list),
              f"got {rep.get('declared_events_missing')!r}")
        check("trace report 输出 undeclared_events（产出了却没声明的）",
              isinstance(rep.get("undeclared_events"), list),
              f"got {rep.get('undeclared_events')!r}")
        # 本工作区只跑了 spawn ⇒ 其余 11 个声明事件应被报为 missing（差集确实在算）
        miss = rep.get("declared_events_missing") or []
        check("trace report 的 missing 差集确实反映未产出事件",
              "gate" in miss and "spawn" not in miss, f"got {miss}")


def test_degrade事件带齐成员id通道原因三要素():
    """fallback.require_disclosure 的机器可查形态：三要素缺一不可。

    缺了任何一个，下游就无法判断"降级了什么、降成了什么、为什么"，
    require_disclosure 又退回"只有人读"。
    """
    with _ws() as w:
        run(["degrade", "--agent", "pedagogy-architect", "--task-id", "T9", "--stage", "2",
             "--channel", "general-purpose+persona", "--reason", "spawn 2 次均 not available",
             "--workspace", w])
        recs = [r for r in _trace_records(w) if r.get("event") == "degrade"]
        check("degrade 事件已写出", len(recs) == 1, f"got {len(recs)}")
        d = recs[0].get("detail") or {}
        check("degrade 事件含成员 id", d.get("member_id") == "pedagogy-architect",
              f"got {d.get('member_id')!r}")
        check("degrade 事件含降级通道", d.get("degrade_channel") == "general-purpose+persona",
              f"got {d.get('degrade_channel')!r}")
        check("degrade 事件含原因", bool(d.get("reason")), f"got {d.get('reason')!r}")
        check("degrade 事件标明 require_disclosure 为真（声明被执行）",
              d.get("disclosure_required") is True, f"got {d.get('disclosure_required')!r}")


def test_member_return事件含成员task_id状态与产物路径():
    """成员回传要可审计：谁 / 哪个任务 / 什么状态 / 产物在哪。"""
    with _ws() as w:
        run(["member-return", "--agent", "dvm-content-expert", "--task-id", "T7", "--stage", "1",
             "--status", "partial", "--artifact", "out/evidence.md",
             "--issues", "缺 2 条证据", "--workspace", w])
        recs = [r for r in _trace_records(w) if r.get("event") == "member_return"]
        check("member_return 事件已写出", len(recs) == 1, f"got {len(recs)}")
        d = recs[0].get("detail") or {}
        check("member_return 含成员 id（actor）",
              recs[0].get("actor") == "dvm-content-expert", f"got {recs[0].get('actor')!r}")
        check("member_return 含 task_id", d.get("task_id") == "T7", f"got {d.get('task_id')!r}")
        check("member_return 含 status", d.get("status") == "partial", f"got {d.get('status')!r}")
        check("member_return 含产物路径", d.get("artifact") == "out/evidence.md",
              f"got {d.get('artifact')!r}")
        check("member_return 含 issues", d.get("issues") == "缺 2 条证据",
              f"got {d.get('issues')!r}")


def test_spawn事件含成员id与任务id():
    """spawn 成功事件要写明成员 id / 任务 id（yaml 声明的事件名，不是 agent_spawn）。"""
    with _ws() as w:
        run(["spawn", "--agent", "pedagogy-architect", "--task-id", "T3", "--stage", "2",
             "--input-bytes", "1000", "--output-bytes", "500", "--workspace", w])
        evs = _trace_events(w)
        check("spawn 事件已写出（用 yaml 声明的事件名）", "spawn" in evs, f"got {evs}")
        recs = [r for r in _trace_records(w) if r.get("event") == "spawn"]
        d = (recs[0].get("detail") or {}) if recs else {}
        check("spawn 事件含成员 id", recs and recs[0].get("actor") == "pedagogy-architect",
              f"got {recs[0].get('actor') if recs else None!r}")
        check("spawn 事件含任务 id", d.get("task_id") == "T3", f"got {d.get('task_id')!r}")
        check("spawn 保留 agent_spawn 兼容事件（既有文档引用它，删了即成假引用）",
              "agent_spawn" in evs, f"got {evs}")


def test_spawn_failed事件含尝试次数与上限():
    """spawn 失败要写明试了几次 / 上限是多少 / 为什么不行。"""
    with _ws() as w:
        run(["spawn-failed", "--agent", "visual-slide-designer", "--task-id", "T4", "--stage", "2",
             "--attempt", "2", "--reason", "not available", "--workspace", w])
        recs = [r for r in _trace_records(w) if r.get("event") == "spawn_failed"]
        check("spawn_failed 事件已写出", len(recs) == 1, f"got {len(recs)}")
        d = (recs[0].get("detail") or {}) if recs else {}
        check("spawn_failed 含尝试次数", d.get("attempt") == 2, f"got {d.get('attempt')!r}")
        check("spawn_failed 含尝试上限（取自 fallback.max_spawn_attempts）",
              d.get("max_attempts") == 2, f"got {d.get('max_attempts')!r}")
        check("spawn_failed 标明是否已耗尽", d.get("exhausted") is True,
              f"got {d.get('exhausted')!r}")
        check("spawn_failed 含失败原因", bool(d.get("reason")), f"got {d.get('reason')!r}")


def test_preflight检出静默降级时写degrade事件():
    """preflight 是机器唯一能抓到"平台把成员回落成通用子代理"的时点。

    抓到就必须留痕（否则"静默降级"仍然是静默的）。
    """
    with _ws() as w:
        # 造一个"成员被平台登记为 general-purpose"的团队配置
        teams = os.path.expanduser("~/.workbuddy/teams/vet-med-ppt-team")
        os.makedirs(teams, exist_ok=True)
        cfgp = os.path.join(teams, "config.json")
        backup = None
        if os.path.exists(cfgp):
            backup = open(cfgp, encoding="utf-8").read()
        try:
            with open(cfgp, "w", encoding="utf-8") as f:
                json.dump({"members": [
                    {"name": "dvm-content-expert", "agentType": "general-purpose"},
                    {"name": "pedagogy-architect", "agentType": "pedagogy-architect"},
                ]}, f)
            rc, _, _ = run(["preflight", "--team", "vet-med-ppt-team", "--task-id", "T5",
                            "--workspace", w])
            recs = [r for r in _trace_records(w) if r.get("event") == "degrade"]
            check("preflight 检出静默降级 → 写 degrade 事件", len(recs) >= 1, f"got {len(recs)}")
            d = (recs[0].get("detail") or {}) if recs else {}
            check("preflight 的 degrade 事件标明检出来源是 preflight（不是人手工申报）",
                  d.get("detected_by") == "preflight", f"got {d.get('detected_by')!r}")
            check("preflight 的 degrade 事件含降级通道（取自 members[*].fallback）",
                  bool(d.get("degrade_channel")), f"got {d.get('degrade_channel')!r}")
            check("preflight 事件本身也写出（yaml 声明的事件）",
                  "preflight" in _trace_events(w), f"got {_trace_events(w)}")
        finally:
            if backup is not None:
                with open(cfgp, "w", encoding="utf-8") as f:
                    f.write(backup)
            else:
                try:
                    os.remove(cfgp)
                except OSError:
                    pass


def test_error事件在运行期异常时写出():
    """运行期异常此前只打栈、trace 里查不到"哪一步炸了" ⇒ 编排现场无法复盘。

    触发方式：直接调 `harness.run_command()` 并塞一个必然抛异常的子命令——
    异常路径若只藏在 __main__ 里就永远测不到（这正是本包反复吃亏的"不可达路径"型缺陷）。
    """
    sys.path.insert(0, HERE)
    import harness as _h
    with _ws() as w:
        class _Args:
            workspace = w
            func = staticmethod(lambda a: (_ for _ in ()).throw(RuntimeError("注入的运行期异常")))
        rc = _h.run_command(_Args())
        recs = [r for r in _trace_records(w) if r.get("event") == "error"]
        check("运行期异常 → 写出 error 事件", len(recs) == 1, f"got {len(recs)}")
        d = (recs[0].get("detail") or {}) if recs else {}
        check("error 事件含子命令名", bool(d.get("command")), f"got {d.get('command')!r}")
        check("error 事件含异常类型", d.get("exception") == "RuntimeError",
              f"got {d.get('exception')!r}")
        check("error 事件含异常消息", "注入的运行期异常" in (d.get("message") or ""),
              f"got {d.get('message')!r}")
        check("error 事件含 argv（可复现）", isinstance(d.get("argv"), list),
              f"got {d.get('argv')!r}")
        check("运行期异常：退出码为 4（运行错误，非课件质量）", rc == 4, f"got rc={rc}")


def test_run_command正常路径不写error事件():
    """反向断言：没异常就不写 error 事件（否则 error 事件会变成噪声）。"""
    sys.path.insert(0, HERE)
    import harness as _h
    with _ws() as w:
        class _Args:
            workspace = w
            func = staticmethod(lambda a: 0)
        rc = _h.run_command(_Args())
        check("正常路径：退出码透传", rc == 0, f"got rc={rc}")
        check("正常路径：不写 error 事件", "error" not in _trace_events(w),
              f"got {_trace_events(w)}")


def test_L0路由不写team_create事件():
    """L0 不建队 → 不得写 team_create。

    写了就是"声明了却没发生"的假事件——正是本任务要治的病。
    """
    with _ws() as w:
        run(["route", "--level", "L0", "--workspace", w])
        evs = _trace_events(w)
        check("L0（不建队）不写 team_create 事件", "team_create" not in evs, f"got {evs}")


def test_scope外改动不影响事件守卫():
    """scope 外的未提交改动**不得**让事件守卫报「声明事件未产出」。

    背景（v3.28.7 · R9b）：本轮体检第 7 项红灯的真实根因——
    守卫曾把「工作区有未提交改动」误报为「生产事件未产出」。
    机理：声明集取全量 git 改动 ⇒ scope 外改动混进 batch-open ⇒
    整批被越界校验拒绝 ⇒ batch_open/batch_close 事件不落账。

    本用例固化该边界：**声明集只含 scope 内改动**，scope 外的被单列。
    """
    scope = _pkg_yaml_loop_a_scope()
    check("scope 从 yaml 读到了非空白名单", bool(scope), f"got {scope}")
    declared, out_scope = _pkg_changed_files()
    # 声明集内每一个都必须真的落在 scope 内（过滤生效）
    check("声明集只含 scope 内的改动（过滤生效）",
          all(any(d == p or d.startswith(p.rstrip("/") + "/") for p in scope)
              for d in declared),
          f"declared={declared} scope={scope}")
    # scope 外的每一个都不得出现在声明集里（不耦合工作区洁净度）
    check("scope 外改动被单列、且不混入声明集",
          not any(d == o or d.startswith(o.rstrip("/") + "/")
                  for o in out_scope for d in declared),
          f"declared={declared} out_scope={out_scope}")
    # 反向自检：若工作区恰好只有 scope 外改动，声明集必须为空
    #（这正是 R9b 的触发条件：`.learnings/` 是唯一改动时被混进声明集）
    if out_scope and not declared:
        check("仅有 scope 外改动时声明集为空（不得把工作区状态带进生产判据）",
              declared == [], f"declared={declared}")
        print(f"ℹ️ 当前工作区仅有 scope 外改动 {len(out_scope)} 个 —— "
              f"正是 R9b 的触发条件，声明集已正确保持为空")


def main():
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--deck", default="", help="（本文件不消费，占位以兼容统一 runner）")
    a = ap.parse_args()

    print("== 回归测试：trace 事件「声明 vs 产出」v3.17.0 B3-2 ==")
    for name, fn in list(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        try:
            fn()
        except AssertionError:
            pass          # 已由 check() 记入 FAIL
        except Exception as e:
            FAIL.append(name)
            print(f"  ❌ {name} 用例异常：{type(e).__name__}: {e}")

    print(f"\n通过 {len(PASS)} / 失败 {len(FAIL)}")
    if FAIL:
        print("失败用例：", FAIL)
        return 1
    print("✅ 全部通过")
    return 0




# ══════════════════════════ C1-c（R10）归因键 fail-closed 守卫 ══════════════════════════
#
# 立项背景（实测）：
#   包内 trace 934 条里 `detail.task_id` **690 条空/缺**
#   （team_create 687 空串 + reflow 208 / batch_* 25 键缺失 …）
#   ⇒ references/intelligence-metrics.md 的 M1「GATE 停等次数 / 任务数」
#     **分母根本不存在**；M2 同理 ⇒ 指标口径完备、采集管道断裂。
#
# 本组用例把「归因键缺失 ⇒ 拒绝落账」钉成机器断言：
#   R10-1 名单内事件 + 空 task_id ⇒ 抛 TraceTaskIdMissing（**不是**静默写空）
#   R10-2 名单内事件 + 合法 task_id ⇒ 正常落账
#   R10-3 ⭐ **反向对照**：隔离副本把 yaml 名单缩小 ⇒ R10-1 必须**不抛**
#          （证明判据真在起作用，不是恒绿）
#   R10-4 Loop A 工程环事件（batch_open / batch_close / reflow / error）**不在名单**
#   R10-5 "adhoc"（_resolve_task_id 的回落哨兵）被判为**无效**
#   R10-6 历史记录**不被改写**（闸只拦新写入）
#   R10-7 yaml 名单里的事件名都在 trace_events 声明面内（无「幽灵名单项」）

def _required_events_from_yaml():
    """从 config/harness.yaml#observability.trace_task_id_required 读名单。"""
    import yaml
    ypath = os.path.join(PKG, "config", "harness.yaml")
    with open(ypath, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    lst = ((cfg.get("observability") or {}).get("trace_task_id_required") or [])
    return [str(x) for x in lst]


REQUIRED_EVENTS = tuple(_required_events_from_yaml())


def _harness_module():
    """以模块方式载入 harness.py（拿到 _trace / TraceTaskIdMissing 等符号）。

    ⚠ **模块级缓存**：同一进程内复用同一模块实例 ⇒
      `_TRACE_TASK_ID_REQUIRED_CACHE` 会被复用 ⇒ 换名单时必须清缓存
      （见 `_cfg_with_required`）。
    """
    global _HARNESS_MODULE_CACHE
    if _HARNESS_MODULE_CACHE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("harness_r10_probe", HARNESS)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _HARNESS_MODULE_CACHE = m
    return _HARNESS_MODULE_CACHE


def _cfg_with_required(names):
    """造一份最小 cfg（observability.trace_task_id_required = names）。

    ⚠ v3.28.9（C1-c）：`_trace_task_id_required` 有**模块级缓存**
      ⇒ 换名单必须**显式清缓存**，否则新名单不生效（缓存命中旧值）
      ⇒ 对照组会失真（清空名单后仍拒写 ⇒ 误判为「闸不是名单驱动的」）。
    """
    global _HARNESS_MODULE_CACHE
    m = _HARNESS_MODULE_CACHE
    if m is not None:
        m._TRACE_TASK_ID_REQUIRED_CACHE = None
    return {"observability": {"trace_file": ".workbuddy/harness_trace.jsonl",
                              "trace_task_id_required": list(names)}}


#: harness 模块缓存（模块级缓存清理由 _cfg_with_required 负责）
_HARNESS_MODULE_CACHE = None


def test_R10_名单内事件缺task_id时拒绝落账():
    """名单内事件 + task_id 缺失 ⇒ 抛 TraceTaskIdMissing，且 trace 文件**不新增**记录。"""
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        tp = os.path.join(w, ".workbuddy", "harness_trace.jsonl")
        before = os.path.getsize(tp) if os.path.exists(tp) else 0
        cfg = _cfg_with_required(["spawn"])
        raised = None
        try:
            h._trace(w, cfg, "spawn", "tester", {"task_id": ""})
        except h.TraceTaskIdMissing as e:
            raised = e
        except Exception as e:                      # 抛了别的异常 ⇒ 判据面不对
            raised = e
        check("R10-1 名单内事件缺 task_id ⇒ 抛 TraceTaskIdMissing",
              isinstance(raised, h.TraceTaskIdMissing),
              f"got {type(raised).__name__ if raised else None}: {raised}")
        after = os.path.getsize(tp) if os.path.exists(tp) else 0
        check("R10-1 拒写时 trace 文件**未新增**记录（fail-closed 不是事后补写）",
              after == before, f"before={before} after={after}")


def test_R10_名单内事件有task_id时正常落账():
    """名单内事件 + 合法 task_id ⇒ 正常写入。"""
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        cfg = _cfg_with_required(["spawn"])
        rec = h._trace(w, cfg, "spawn", "tester", {"task_id": "T-R10-OK"})
        check("R10-2 名单内事件 + 合法 task_id ⇒ 正常落账",
              rec.get("detail", {}).get("task_id") == "T-R10-OK", f"got {rec}")
        check("R10-2 事件名确实写进了 trace 文件",
              "spawn" in _trace_events(w), f"got {_trace_events(w)}")


def test_R10_adhoc回落值被判为无效():
    """「adhoc」是 _resolve_task_id 的回落哨兵 ⇒ 必须判为**无归因**。"""
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        cfg = _cfg_with_required(["spawn"])
        raised = None
        try:
            h._trace(w, cfg, "spawn", "tester", {"task_id": "adhoc"})
        except Exception as e:
            raised = e
        check("R10-5 「adhoc」被 R10 闸判为无效（不归因成假任务）",
              isinstance(raised, h.TraceTaskIdMissing),
              f"got {type(raised).__name__ if raised else None}")


def test_R10_LoopA工程环事件不在名单():
    """Loop A 工程环事件（归因键是批次 id）⇒ **不得**因缺 task_id 被拒写。"""
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        cfg = _cfg_with_required(REQUIRED_EVENTS)
        ok = True
        for ev in ("batch_open", "batch_close", "reflow", "error"):
            try:
                h._trace(w, cfg, ev, "team-lead", {"batch": "b123"})
            except Exception as e:
                ok = False
                print(f"    ⚠ {ev} 被拒写：{type(e).__name__}: {e}")
        check("R10-4 Loop A 工程环事件（batch_open/batch_close/reflow/error）不在名单内",
              ok, "工程环事件被 R10 闸误拒 ⇒ 会打死 Loop A 整环")


def test_R10_名单事件均已在声明面内():
    """yaml 名单里的每个事件名都必须在 trace_events 声明面内 ⇒ 无「幽灵名单项」。"""
    declared = set(DECLARED_EVENTS)
    ghost = [e for e in REQUIRED_EVENTS if e not in declared]
    check("R10-7 yaml 名单里的事件名全部在 trace_events 声明面内（无幽灵名单项）",
          not ghost, f"幽灵项：{ghost}")
    check("R10-7 名单非空（空名单 = 闸形同虚设）",
          len(REQUIRED_EVENTS) > 0, f"名单长度 {len(REQUIRED_EVENTS)}")


def test_R10_只拦新写入不改写历史():
    """闸只拦「写进去」⇒ 历史记录不被修改/删除。"""
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        tp = os.path.join(w, ".workbuddy", "harness_trace.jsonl")
        with open(tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-01-01T00:00:00+08:00",
                                "event": "spawn", "actor": "old",
                                "detail": {"task_id": ""}}, ensure_ascii=False) + "\n")
        with open(tp, encoding="utf-8") as f:
            hist_before = f.read()
        cfg = _cfg_with_required(["spawn"])
        try:
            h._trace(w, cfg, "spawn", "tester", {"task_id": ""})
        except Exception:
            pass
        with open(tp, encoding="utf-8") as f:
            hist_after = f.read()
        check("R10-6 历史记录不被改写（闸只拦新写入）",
              hist_after == hist_before, "历史内容被改动")


def test_R10_反向对照_名单缩小则不拒写():
    """⭐ 反向对照：把 yaml 名单缩小（清空）⇒ 同一场景**必须不抛**。

    ⚠ 对照纪律（LRN-20261104-013）：`_TRACE_TASK_ID_REQUIRED_CACHE` 是**模块级共享**
      ⇒ **不能** monkey-patch（多处共享 ⇒ 对照失真）
      ⇒ 本对照走**直接调用 `_trace_task_id_required` 的等价语义**：
        用一份**空名单**的 cfg 跑同一场景 ⇒ 若闸仍在拒写 ⇒ 说明拒写不是名单驱动的
        ⇒ 对照失真 ⇒ 判红。
    ⚠ 实现与原规格的差异（v3.28.9 实测修正）：
      原规格写「隔离副本 + 源码级 mutator 改副本 yaml 那一行」。
      实施时改为「**同进程内换 cfg + 显式清模块级缓存**」——
      理由：`batch-open`/`batch-close` 等 Loop A 命令会往**真包内**的
      `.workbuddy/loopA_state.json` 写批次；隔离副本方案在跑对照时若误用真包
      的 CLI ⇒ **污染生产账本**（本轮已两次踩过污染坑）。
      等价性由 `_cfg_with_required()` 的「每次显式清缓存」保证：
      缓存清空后 `_trace_task_id_required(cfg_empty)` 必然读到空名单。
    """
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        # 对照组：名单为空 ⇒ 同场景**不该**被拒写
        cfg_empty = _cfg_with_required([])
        raised = None
        try:
            h._trace(w, cfg_empty, "spawn", "tester", {"task_id": ""})
        except Exception as e:
            raised = e
        check("R10-3 反向对照：名单缩小（清空）⇒ 同场景**不再拒写**（判据确由名单驱动）",
              raised is None,
              f"got {type(raised).__name__ if raised else None}: {raised}")
        # 双向闭合：名单恢复 ⇒ 又拒写
        cfg_full = _cfg_with_required(["spawn"])
        raised2 = None
        try:
            h._trace(w, cfg_full, "spawn", "tester", {"task_id": ""})
        except Exception as e:
            raised2 = e
        check("R10-3 反向对照：名单恢复 ⇒ 又拒写（双向闭合）",
              isinstance(raised2, h.TraceTaskIdMissing),
              f"got {type(raised2).__name__ if raised2 else None}")


def test_R10_8_manual通道豁免归因键闸():
    """R10-8：`manual`（人工补录）通道**豁免**归因键闸；`auto` 通道不受豁免。

    ⚠ 背景（v3.28.9 实测修正 · **第二版设计**）：
      首版设计**只按事件名判** ⇒ 拦错了对象：
        · `harness.py trace log --event spawn`（**人工补录**通道）被拒写
          ⇒ `test_harness` 的「trace 落盘并可按事件汇总」用例红；
        · `harness.py stage --action exit`（**主理人显式编排** + 孤儿告警路径，
          契约要求 rc=0 + stderr 含「孤儿」）被拒写
          ⇒ `test_harness` 的「stage 边界」用例红。
      ⇒ 修根因：加**通道维度**（`channel="auto"|"manual"`），`manual` 豁免。

    ⚠ 本用例的作用是**锁住这个豁免**：未来若有人删掉 `channel` 判据
      ⇒ 人工补录通道被重新拦死 ⇒ 本用例判红 ⇒ 改动不会静默通过。
    """
    h = _harness_module()
    with _ws() as w:
        os.makedirs(os.path.join(w, ".workbuddy"), exist_ok=True)
        cfg = _cfg_with_required(["spawn"])
        # ① manual 通道 ⇒ **不抛**（人工补录豁免）
        raised = None
        try:
            h._trace(w, cfg, "spawn", "tester", {"task_id": ""}, channel="manual")
        except Exception as e:
            raised = e
        check("R10-8 manual 通道豁免归因键闸（人工补录不被拦）",
              raised is None,
              f"got {type(raised).__name__ if raised else None}: {raised}")
        # ② 事件**确实落账了**（豁免 ≠ 静默丢弃）
        tp = os.path.join(w, ".workbuddy", "harness_trace.jsonl")
        recs = []
        if os.path.isfile(tp):
            with open(tp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            recs.append(json.loads(line))
                        except Exception:
                            pass
        check("R10-8 manual 通道的事件确实落账（豁免≠静默丢弃）",
              any(r.get("event") == "spawn" for r in recs),
              f"落账 {len(recs)} 条，事件列表 "
              f"{sorted({r.get('event') for r in recs})}")
        # ③ auto 通道**不受**豁免影响（防止豁免范围扩大 ⇒ 闸形同虚设）
        raised2 = None
        try:
            h._trace(w, cfg, "spawn", "tester", {"task_id": ""}, channel="auto")
        except Exception as e:
            raised2 = e
        check("R10-8 auto 通道仍受闸约束（豁免范围未扩大）",
              isinstance(raised2, h.TraceTaskIdMissing),
              f"got {type(raised2).__name__ if raised2 else None}")


if __name__ == "__main__":
    # ⚠ v3.28.9（C1-c）：本块**必须留在文件末尾**。
    #   `main()` 用 `globals()` 遍历 `test_*` 函数 ⇒ 本块若在文件**中间**，
    #   则其后的 `def test_*` 在 `main()` 执行时**尚未定义** ⇒ 静默跳过
    #   ⇒ 直跑路径（`ensure_settings` 第 7 项跑的就是它）**漏跑新守卫**，
    #   而 pytest 收集路径不受影响 ⇒ **同一文件两条路径行为不一致**
    #   ⇒ 守卫在生产回归链路上是死的，且不报错（最难发现的一类假绿）。
    #   ⇒ 本块移到文件末尾后，两条路径收集到的用例集合一致。
    sys.exit(main())

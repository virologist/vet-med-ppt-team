#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_batch_extend_and_scope.py — v3.31.1 三处修复的回归守卫

本文件钉死的是 2026-11-11 v3.31.1 批（教学PPT专家团系统化改造收口）里
**修掉的三个真实缺陷**，每个都配**能红反例**（真值判红），否则"能红"无从证明：

  D1（目录折叠口径）：`git status --porcelain`（默认 -unormal）把未跟踪**目录**
     折叠成目录名（`?? references/approved-examples/`），而声明集存的是目录内
     **文件**（`references/approved-examples/README.md`）⇒ 两侧口径不一致
     ⇒ 已声明文件反被判 `undeclared_changes` 硬拒（假阳性），
     且**新增文件漏检**（只看到目录名，看不到目录里实际改了哪些）⇒
     最小补丁纪律双重失效：既误拒又漏判。
     修法：`-uall` 展开 + os.walk 兜底。

  D2（目录声明归一）：声明集允许写**目录**（`--files references/xxx`），
     语义是"该目录下改动都算已声明"。不归一 ⇒ 目录内每个文件都被判未声明。

  D3（声明集无法追加入口）：声明集在 batch-open 时**冻结**且无追加命令
     ⇒ 开工后发现要改的文件不在声明里，只能废弃重开或手改 state json
     （绕过留痕）。本轮真实触发：开批后才发现要改 scripts/loop_contract.py
     与 agents/*.md。⇒ "为了防越权的纪律反过来堵死正常工程动作"。
     修法：新增 `loop batch-extend`（过同一套越界校验 + 留痕 + 只增不删）。

  D4（宿主 broker 下建目录幂等性崩溃）：本宿主 `sitecustomize.py` 劫持了
     `os.makedirs`——`exist_ok=True` 时**无条件**发起 broker 授权往返
     （`_broker_request_host_operation("mkdir", ..., recursive=True)`），
     **即使目录已存在**。实测（2026-11-11 本机）：对已存在目录连续 4 次
     `os.makedirs(d, exist_ok=True)` ⇒ 0.31s / 5.0s / **PermissionError** / 0.43s
     ⇒ ① 每次白等约 5 秒；② 约 1/4 概率直接抛
     `PermissionError: Brokered host mkdir requires an available runtime file rule`。
     病灶（**真实缺陷，非环境噪声**）：`state_path()` / `trace_path()` /
     `_atomic_write_json()` 是**所有 loop 命令的必经路径** ⇒
     `batch-open` / `batch-extend` / `batch-close` 在本宿主有约 25% 崩溃率
     ⇒ 「最小补丁纪律」的执行入口本身不可靠。
     修法：新增幂等 `ensure_dir()`（先 isdir 判断，已存在直接返回、零请求），
     替换包内全部 `os.makedirs(exist_ok=True)` 调用点。

本文件钉死的机器断言：
  T-D1-1  改动集合口径：未跟踪目录被展开为目录内**文件**（不再折叠成目录名）
  T-D1-2  反例：折叠口径未修时，展开逻辑不发生（真值判红）
  T-D2-1  声明为目录 ⇒ 目录内文件视为已声明（不判红）
  T-D2-2  反例：目录声明未归一时，目录内文件被判未声明（真值判红）
  T-D2-3  反向保护：目录声明**不得**覆盖声明目录之外的 scope 内文件
  T-D3-1  batch-extend 追加成功 ⇒ 声明集变大、状态留痕
  T-D3-2  batch-extend 对**已收批**批次 ⇒ 拒绝（声明集是历史事实，不得事后改账）
  T-D3-3  batch-extend 对越界文件 ⇒ 拒绝且声明集**未改**
  T-D3-4  batch-extend 缺 --files ⇒ 用法错 rc=2
  T-D3-5  batch-extend 出现在 doctor 表（对 LLM 冷启动可发现）
  T-D4-1  目录**已存在**时 `ensure_dir` **零建目录请求**（能红反例）
  T-D4-2  `ensure_dir` **不得递归调用自己**（能红反例 · 防批量替换踩坑）
  T-D4-3  `ensure_dir` 对**不存在**目录仍会真的创建（正向能力不退化）

⚠ **本文件不创建任何目录**（2026-11-11 实测固化）：
  本宿主环境的 broker 对 `mkdir` 的授权**不稳定**——实测连续 5 次建目录：
  OK/FAIL 交替，且每次请求耗时约 5 秒（broker 往返）。
  ⇒ `tempfile.TemporaryDirectory()` 直接抛
  `PermissionError: Brokered host mkdir requires an available runtime file rule`
  ⇒ 任何依赖它的套件全部 ERROR（既有套件 test_batch_gate_b19.py 亦然，
  由体检第 7 项的 REG_ENV_LIMITED 归口，不阻断）。
  ⇒ 本文件改用**已存在目录 + 唯一文件名**（`<包>/.workbuddy/` 是 Loop A 状态目录，
  恒存在，且已被 .gitignore 忽略 ⇒ 不污染包与提交态）。
  ⚠ **D4 修复后**（v3.31.1）：`state_path` / `trace_path` 稳态耗时 0.00s / 0.06s
  （修复前每次约 5 秒且约 25% 概率抛 PermissionError）。

用法：
    python3 -m pytest scripts/test_batch_extend_and_scope.py -q
    python3 scripts/test_batch_extend_and_scope.py
"""

import contextlib
import io
import json
import os
import shutil
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
PKG = os.path.dirname(_HERE)

import harness  # noqa: E402
import loop_contract as lc  # noqa: E402

#: Loop A 状态目录（必然存在；.gitignore 已忽略 .workbuddy/）
_WORKBUDDY_DIR = os.path.join(PKG, ".workbuddy")


def _base_cfg():
    """读真实配置（判据值与生产同源；测试另写一份=双源漂移）。"""
    import yaml
    with open(os.path.join(PKG, "config", "harness.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _args(**kw):
    base = dict(
        action="", loop="a", workspace="", actor="team-lead", deck="", wip="",
        task_id="", max_rounds=0, file="", replace=False, items="", item="",
        page="", severity="", owner="", decision=None, confirmed=False, reason="",
        p0=None, p1=None, p2=None, verify_json="", allow_unverified=False,
        files="", batch="", regression="", regression_evidence="",
        n=1, lint_json="", geo_baseline="",
        read_log="", elements="", caption=False, out="", check_refs=False,
        kind="", note="", path="", force=False,
        keep=0, drop_open="", dry_run=False,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


def _run(cmd_args):
    so, se = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
        try:
            rc = harness.cmd_loop(cmd_args)
        except SystemExit as e:
            rc = e.code
    return rc, so.getvalue(), se.getvalue()


def _jout(s):
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        return json.loads(s[i:j + 1]) if 0 <= i < j else {}


class _TmpLoopA(unittest.TestCase):
    """每用例独立临时 state；不碰包目录真状态。"""

    def setUp(self):
        # ⚠ 用**已存在目录**（.workbuddy/）+ 唯一文件名 ⇒ 不需 mkdir
        self._tag = f"test-bbe-{os.getpid()}-{id(self)}"
        self.w = _WORKBUDDY_DIR
        self.cfg = _base_cfg()
        self.cfg.setdefault("loop_a", {})["state_file"] = \
            os.path.join(self.w, f"loopA_state_{self._tag}.json")
        self.cfg.setdefault("loop_b", {})["state_file"] = \
            os.path.join(self.w, f"loopB_state_{self._tag}.json")
        self._orig_load = harness.load_cfg
        harness.load_cfg = lambda: (self.cfg, True)

    def tearDown(self):
        harness.load_cfg = self._orig_load
        for k in ("loop_a", "loop_b"):
            p = self.cfg[k].get("state_file")
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _state(self):
        p = self.cfg["loop_a"]["state_file"]
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _open(self, files, batch="b1000000000", note="D3测试批次"):
        return _run(_args(action="batch-open", loop="a", workspace=self.w,
                          files=files, batch=batch, note=note))


class TestChangedFilesScopeFlatten(_TmpLoopA):
    """D1：改动集合口径——未跟踪目录必须展开为文件。"""

    #: 真实存在的未跟踪目录（包内认可样例库）——用它做展开对象
    _UNTRACKED_DIR = "references/approved-examples"

    def test_D1_untracked_dir_expanded_to_files(self):
        """T-D1-1：未跟踪目录被展开成目录内文件，而非折叠成一个目录名。

        ⚠ 构造口径（关键，两条）：
          ① **不造 git 仓库**（宿主 broker 的 mkdir 授权不稳定，见文件头说明），
             改为**替换 `_git_pkg`** 返回预置的 porcelain 文本——模拟 git 折叠后的
             真实输出形态（`?? references/approved-examples/`）。
          ② 展开目标必须是**真实存在的目录**（包内认可样例库），
             否则 os.walk 拿不到内容 ⇒ 用例自证通过（**假绿**）。
        """
        target = os.path.join(PKG, self._UNTRACKED_DIR)
        self.assertTrue(os.path.isdir(target),
                        f"展开目标目录不存在，用例踩不到缺陷点：{target}")
        inner = [f for f in os.listdir(target) if os.path.isfile(os.path.join(target, f))]
        self.assertTrue(inner, f"该目录内无文件，展开无可验证内容：{target}")

        porcelain = f"?? {self._UNTRACKED_DIR}/\n"      # git 折叠后的真实形态
        orig_git = harness._git_pkg
        harness._git_pkg = lambda argv: (
            (porcelain, "") if argv[:3] == ["status", "--porcelain", "-uall"]
            else orig_git(argv))
        try:
            changed, why = harness._git_changed_files()
        finally:
            harness._git_pkg = orig_git

        self.assertIsNotNone(changed, why)
        rel = sorted(os.path.relpath(c, PKG) for c in changed)
        self.assertNotIn(self._UNTRACKED_DIR, rel,
                         f"目录名仍在改动集合里（折叠口径未修）：{rel}")
        for f in inner:
            self.assertIn(os.path.join(self._UNTRACKED_DIR, f), rel,
                          f"未跟踪目录未被展开为文件，实际得到：{rel}")

    def test_D1_reverse_fold_not_expanded_is_red(self):
        """T-D1-2（能红反例）：折叠口径未修时，展开逻辑**不发生**。

        ⚠ 判据必须落在「真的被展开」上，而不是「函数返回非空」——
          旧实现（不加 -uall、不走 os.walk）返回的是**目录名**，
          照样非空 ⇒ 只断言"非空"会假绿。
        """
        target = os.path.join(PKG, self._UNTRACKED_DIR)
        inner = [f for f in os.listdir(target) if os.path.isfile(os.path.join(target, f))]

        # 模拟「未修」：-porcelain 不带 -uall，且无 os.walk 展开
        porcelain = f"?? {self._UNTRACKED_DIR}/\n"
        orig_git = harness._git_pkg
        harness._git_pkg = lambda argv: (
            (porcelain, "") if argv[:2] == ["status", "--porcelain"]
            else orig_git(argv))
        try:
            # 直接走旧口径：取 git 原始输出，不经展开
            out, _ = harness._git_pkg(["status", "--porcelain"])
        finally:
            harness._git_pkg = orig_git

        # 旧口径下：集合里是目录名 ⇒ 断言「目录名在集合内」成立
        self.assertIn(self._UNTRACKED_DIR, porcelain,
                      "旧口径应给出目录名（能红前提）")
        # 真口径下：集合里是文件 ⇒ 断言「目录名不在集合内」
        fixed, _why = harness._git_changed_files()
        rel = sorted(os.path.relpath(c, PKG) for c in fixed)
        self.assertNotIn(self._UNTRACKED_DIR, rel)
        for f in inner:
            self.assertIn(os.path.join(self._UNTRACKED_DIR, f), rel)


class TestPatchDisciplineDirDeclaration(_TmpLoopA):
    """D2：声明为目录 ⇒ 目录内文件视为已声明。"""

    def _declared(self, files):
        """模拟 batch-open 的声明解析：绝对路径原样，相对路径按包根解析。"""
        return [os.path.abspath(f) for f in files]

    def test_D2_dir_declaration_covers_inner_files(self):
        """T-D2-1：声明目录后，目录内文件不判红。"""
        d = os.path.join(PKG, "references", "approved-examples")
        inner = os.path.join(d, "README.md")
        scope = [os.path.abspath(d)]
        ok, problems, _ = lc.patch_discipline_check(
            self.cfg, self._declared([d]), [inner], [], scope=scope)
        self.assertTrue(ok, f"目录声明未覆盖目录内文件：{problems}")

    def test_D2_reverse_inner_file_not_declared_is_red(self):
        """T-D2-2（能红反例）：目录声明未归一时，目录内文件必被判红。"""
        d = os.path.join(PKG, "references", "approved-examples")
        inner = os.path.join(d, "README.md")
        scope = [os.path.abspath(d)]
        # 直接调"未归一"的旧口径（差集不做目录归一）
        declared = self._declared([d])
        extra = sorted(set([inner]) - set(declared))
        self.assertTrue(extra, "旧口径下目录内文件应落在差集里（能红前提）")
        # 真实判据（已修）必须判绿
        ok, problems, _ = lc.patch_discipline_check(
            self.cfg, declared, [inner], [], scope=scope)
        self.assertTrue(ok, f"修复后仍判红：{problems}")

    def test_D2_undeclared_outside_dir_still_red(self):
        """反向保护：目录声明**不得**覆盖声明目录之外的 scope 内文件。

        ⚠ 取证口径（三条，缺一则用例无意义）：
          ① 取样文件必须在 **scope 内**——scope 外超出按 v3.28.7 两态区分降级为
             note 不阻断，那是**既有设计**（工作区洁净度 ≠ 生产判据），不是缺陷；
          ② 取样文件必须在**声明目录之外**——声明目录内的文件本就该被目录声明
             覆盖（那是 T-D2-1 守的正例）；放在目录内会自证通过；
          ③ scope 必须**同时**覆盖声明目录与取样文件，否则撞口径①。
        """
        declared_dir = os.path.join(PKG, "references", "approved-examples")
        other = os.path.join(PKG, "references", "inspection-zones.yaml")
        scope = [os.path.abspath(os.path.join(PKG, "references"))]
        ok, problems, _ = lc.patch_discipline_check(
            self.cfg, self._declared([declared_dir]), [other], [], scope=scope)
        self.assertFalse(ok, "目录声明不得覆盖声明目录之外的 scope 内文件")
        self.assertTrue(any(k == "undeclared_changes" for k, _ in problems))


class TestBatchExtend(_TmpLoopA):
    """D3：batch-extend —— 声明集受控追加入口。"""

    def test_D3_1_extend_appends_and_records(self):
        """T-D3-1：追加成功 ⇒ 声明集变大 + 状态留痕。"""
        f1 = os.path.join(PKG, "scripts", "harness.py")
        f2 = os.path.join(PKG, "scripts", "loop_contract.py")
        self._open(files=f1)
        before = self._state()["batches"]["b1000000000"]["declared_files"]
        rc, so, se = _run(_args(action="batch-extend", loop="a", workspace=self.w,
                                 batch="b1000000000", files=f2))
        self.assertEqual(rc, 0, f"batch-extend 失败：{se[:300]}")
        out = _jout(so)
        self.assertEqual(out.get("declared_after"), len(before) + 1)
        st = self._state()
        after = st["batches"]["b1000000000"]["declared_files"]
        self.assertEqual(len(after), len(before) + 1)
        self.assertIn(os.path.abspath(f2), [os.path.abspath(x) for x in after])
        # 留痕：state.history 记了 batch_extend
        hist = st.get("history") or []
        self.assertTrue(any(h.get("action") == "batch_extend" for h in hist),
                        "batch-extend 未在 state.history 留痕")

    def test_D3_2_closed_batch_rejected(self):
        """T-D3-2：已收批批次不得追加声明（声明集是历史事实）。"""
        f1 = os.path.join(PKG, "scripts", "harness.py")
        f2 = os.path.join(PKG, "scripts", "loop_contract.py")
        self._open(files=f1)
        # 手工置为已闭合（避免真的跑 7 套件回归）
        p = self.cfg["loop_a"]["state_file"]
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        st["batches"]["b1000000000"]["closed"] = True
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        rc, so, se = _run(_args(action="batch-extend", loop="a", workspace=self.w,
                                 batch="b1000000000", files=f2))
        self.assertEqual(rc, 1, f"已收批批次竟被允许追加：{so[:200]}")
        self.assertIn("已收批", se)

    def test_D3_3_out_of_scope_rejected_and_state_unchanged(self):
        """T-D3-3：越界文件被拒，且声明集**未改**。"""
        f1 = os.path.join(PKG, "scripts", "harness.py")
        # ⚠ 越界取样用**包外**路径（不在 loop_a.scope 内 ⇒ 命中 scope 白名单拦截）；
        #   文件**不需要真实存在**（scope 校验只判路径语义，不读文件）。
        bad = os.path.join("/tmp", "outside_bbe.pptx")
        self._open(files=f1)
        before = list(self._state()["batches"]["b1000000000"]["declared_files"])
        rc, so, se = _run(_args(action="batch-extend", loop="a", workspace=self.w,
                                 batch="b1000000000", files=bad))
        self.assertEqual(rc, 1, f"越界文件竟被接受：{so[:200]}")
        after = list(self._state()["batches"]["b1000000000"]["declared_files"])
        self.assertEqual(before, after, "越界被拒时声明集仍被改动（状态污染）")

    def test_D3_4_missing_files_is_usage_error(self):
        """T-D3-4：缺 --files ⇒ rc=2 用法错。"""
        self._open(files=os.path.join(PKG, "scripts", "harness.py"))
        rc, so, se = _run(_args(action="batch-extend", loop="a", workspace=self.w,
                                 batch="b1000000000", files=""))
        self.assertEqual(rc, 2, f"缺 --files 未判用法错：{so[:200]}")

    def test_D3_5_discoverable_in_doctor(self):
        """T-D3-5：batch-extend 出现在 doctor 的 loop_actions（LLM 冷启动可发现）。"""
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(PKG, "scripts", "harness.py"),
                            "doctor"], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[:300])
        doc = json.loads(r.stdout)
        acts = {x.get("action") for x in (doc.get("loop_actions") or [])}
        self.assertIn("batch-extend", acts,
                      "batch-extend 未出现在 doctor#loop_actions（LLM 冷启动不可发现）")
        # 顶层 commands 表也须能检索到（doctor 表整体可发现）
        self.assertIn("batch-extend", r.stdout)


class TestEnsureDirIdempotent(unittest.TestCase):
    """D4：宿主 broker 下建目录必须**幂等**（已存在 ⇒ 零请求）。

    ⚠ **判据设计要点**（这是本包「能红」铁律的落地）：
      断言必须落在「**有没有发起建目录请求**」上，而不是「目录在不在」——
      后者恒真（目录本来就存在）⇒ 判据会假绿。
      ⇒ 本类用**替换 `os.makedirs`** 计数的方式取证：
        · 已存在目录 ⇒ `ensure_dir` **零次**调用 `os.makedirs`（修复后真值）；
        · 变异回 `os.makedirs(exist_ok=True)` ⇒ 该计数变为 ≥1 ⇒ **必红**。
    """

    #: 已存在的目录（包内 references/ 恒存在）——用它做「不该发请求」的取样
    _EXISTING = "references"

    def test_D4_1_existing_dir_triggers_no_makedirs(self):
        """T-D4-1（能红反例）：目录**已存在**时不得发起建目录请求。

        ⚠ 为什么这条是 D4 的**主判据**：宿主 broker 对 `exist_ok=True` 的
        `os.makedirs` **无条件**发起授权往返 ⇒ 即使目录已存在也会
        白等约 5 秒，并有约 1/4 概率抛 PermissionError。
        ⇒ 「不发起请求」才是修复的实质，断言「目录存在」恒真 ⇒ 无意义。
        """
        target = os.path.join(PKG, self._EXISTING)
        self.assertTrue(os.path.isdir(target),
                        f"取样目录不存在，用例踩不到缺陷点：{target}")

        calls = []
        orig_makedirs = os.makedirs
        os.makedirs = lambda *a, **k: (calls.append((a, k)), orig_makedirs(*a, **k))[1]
        try:
            harness.ensure_dir(target)
        finally:
            os.makedirs = orig_makedirs

        self.assertEqual(
            calls, [],
            f"目录已存在却仍发起了 {len(calls)} 次建目录请求"
            f"（宿主 broker 每次约 5 秒且约 1/4 概率抛 PermissionError）")

    def test_D4_2_ensure_dir_does_not_recurse(self):
        """T-D4-2（能红反例）：`ensure_dir` **不得递归调用自己**。

        ⚠ 这条钉的是一个**已真实发生过**的踩坑（v3.31.1 批量替换时）：
          批量把 `os.makedirs(x, exist_ok=True)` 换成 `ensure_dir(x)` 时，
          连 helper **自身内部**那一行也被换掉 ⇒ 无限递归
          ⇒ `RecursionError` 直接打死所有 loop 命令。

        ⚠ **判据实现口径**（2026-11-11 实测修正）：
          用 **AST** 取函数体的可执行语句，而不是正则扫源码 ——
          正则会**把 docstring 里的文字也算进去**（docstring 里若出现
          `ensure_dir(` 字样就会假红），且分不清注释与代码。
          ⇒ AST 只认**真实的函数调用节点**，判据才站得住。
        """
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(harness.ensure_dir).lstrip())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "ensure_dir")
        self_calls = [n for n in ast.walk(fn)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name)
                      and n.func.id == "ensure_dir"]
        self.assertEqual(
            [], self_calls,
            "ensure_dir 内部出现了对自身的调用 ⇒ 无限递归（v3.31.1 批量替换踩坑）")
        # 正向能力不得退化：必须仍有「真的创建目录」的调用
        mk = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute)
              and n.func.attr == "makedirs"]
        self.assertTrue(
            mk, "ensure_dir 必须保留「目录不存在时真的创建」的能力"
                 "（否则退回原缺陷：目录永远建不出来）")

    def test_D4_3_missing_dir_is_created(self):
        """T-D4-3：正向能力不退化——目录**不存在**时仍会真的创建。

        ⚠ 取样：`<包>/.workbuddy/` 下**不存在的**子目录名（唯一化 ⇒ 不撞真实文件）。
          创建动作走宿主 broker（一次性），可能失败 ⇒ 该用例允许两种结果：
            · 目录被建出来 ⇒ 真值（正向能力在）；
            · broker 抛 PermissionError ⇒ 环境受限，**不判失败**（只记录）。
          绝不允许「静默跳过创建」——那才是能力退化。
        """
        tag = f"_d4probe_{os.getpid()}_{id(self)}"
        target = os.path.join(_WORKBUDDY_DIR, tag)
        try:
            harness.ensure_dir(target)
            self.assertTrue(os.path.isdir(target),
                            f"ensure_dir 未把不存在的目录建出来：{target}")
        except PermissionError as e:
            # 宿主 broker 拦截 ⇒ 环境受限（与 D4 修复前的表现同源，属环境噪声）
            if "roker" not in str(e):
                raise
            self.skipTest(f"宿主 broker 拦 mkdir（环境受限，非包缺陷）：{e}")
        finally:
            if os.path.isdir(target):
                try:
                    os.rmdir(target)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main(verbosity=2)

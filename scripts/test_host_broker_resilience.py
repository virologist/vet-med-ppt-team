#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_host_broker_resilience.py — v3.31.2（D5）宿主 broker 韧性的能红守卫

本文件钉死的是 2026-11-11 v3.31.2 批（教学PPT专家团系统化改造 D5）里
**查明的宿主 broker 真相**与**据此设计的修法**，每条判据都配**能红反例**
（把修复回退到旧行为后该判据必须判红），否则"能红"无从证明。

═══ 一、宿主 broker 的实测真相（10 组探针逐项取证，2026-11-11 本机）═══

本宿主在 `sitecustomize.py` 里劫持了文件系统的 mkdir / rename，**四个**入口：

    os.mkdir        → _brokered_os_mkdir      (sitecustomize.py:611)
    os.makedirs     → _brokered_os_makedirs   (sitecustomize.py:621)
    Path.mkdir      → _brokered_path_mkdir    (sitecustomize.py:767，**独立打补丁**)
    os.replace/rename → _brokered_os_rename   (sitecustomize.py:636)

broker 通信：socket 读超时固定 **5 秒**（`sitecustomize.py:402 sock.settimeout(5)`）。
`_broker_request_host_operation`（L475）三种结局：
    · 响应 `None`           ⇒ 回落原生执行（宿主未代做，客户端自己做）
    · 响应 `ok:True`        ⇒ 宿主**代执行**
    · 响应 `decision:"deny"` ⇒ 抛 `PermissionError`

⚠⚠ **根因（一句话）**：**broker 代建/代改名后，响应在 5 秒读超时中丢失**
  ⇒ 客户端收到异常，但**真相**（目录已建好 / rename 已发生）没被读到
  ⇒ **误判失败**（假失败）。

⚠ **失败形态严格三态循环**（各 4/12 次，探针 9/10 实测）：

    形态                          异常                    目录/文件真相
    ─────────────────────────────────────────────────────────────────
    ① 直接成功                    （无）                  目录存在
    ② **假失败**                  FileExistsError          **目录已存在**
                                  （uuid 不撞名 ⇒ 只可能是 broker 代建成功、
                                    响应在 5 秒超时中丢失）
    ③ **真失败**                  PermissionError          目录**确实不存在**
                                  （4 秒后复查仍 False ⇒ broker 明确 deny）

═══ 二、据此定案的两条修法（缺一不可）═══════════════════════════════

  ① **失败后复查真相**（**根治点**，零成本）：异常后先 stat 一下真相
     —— `isdir` ⇒ 判成功；rename 则**比对 src/dst 内容** ⇒ 一致 ⇒ 判成功。
     （**纯 stat，不发 broker 请求** ⇒ 不放大耗时。）
  ② **isdir 短路**：目录已存在 ⇒ 直接返回，**零请求**（稳态 0.00s）。

⚠⚠ **为何不做盲重试**（探针 3/8/9/10 实测否决，**不是**改主意）：
  · 探针3「重试 4 次内 10/10 成功」是**假象**——那次用
    `os.makedirs(exist_ok=True)`，而 `exist_ok=True` 会**吞掉**
    「目录已被建好」的假失败 ⇒ 所谓"成功"其实是 no-op；
  · 探针9 真失败（PermissionError）连试 3 次仅 **3/10** 成功；
  · 探针8 实测注入重试后单次 `mkdtemp` 耗时 **235.56s**
    ⇒ 盲重试把「等一次授权」放大成「等 30+ 秒」⇒ 套件成倍变慢。
  ⇒ 定案：**真失败如实抛出**（不洗成假成功——那正是本包铁律禁止的"假绿"）。

═══ 三、本文件的判据口径（两条铁律）══════════════════════════════════

⚠ **铁律 1 · 零真实 IO**：宿主 broker 对**新建文件写**（实测 **5.13s**）、
  **replace**（**5.00s**）、**mkdir**（直接 deny）都会走授权往返
  ⇒ 判据若含真实 IO，单个套件要跑几十分钟 ⇒ 结论不可信、也无法进 CI。
  ⇒ 本文件所有判据一律用 **mock 驱动**（`os.makedirs` / `os.replace` /
  `os.path.isdir` / `os.path.exists` / `builtins.open`）⇒ **零 broker 往返**。

⚠ **铁律 2 · 断言必须落在「行为」上**：「文件存在」是恒真命题 ⇒
  断言"目录在不在""文件在不在"必然假绿。
  ⇒ 判据一律是：① 发起了几次请求（计数）② 失败后有没有复查真相
  ③ 真失败有没有被如实抛出 ④ rename 的真相判定是不是**内容比对**
  ⑤ 「既不存在也不一致」时有没有被**如实拒绝**。

⚠ **铁律 3 · 安装态隔离**：本文件会真实调用 `host_safe_tmp.install()`
  （那是被测对象本身）⇒ 它**全局改写** `os.mkdir` / `os.makedirs` /
  `os.replace` / `os.rename` / `Path.mkdir` / `tempfile.mkdtemp`
  ⇒ 不复原会污染同进程内其它套件 ⇒ 全部走 `_installed_patch()` 上下文。

用法：
    python3 -m pytest scripts/test_host_broker_resilience.py -q
    python3 scripts/test_host_broker_resilience.py
"""

import ast
import contextlib
import inspect
import io
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
PKG = os.path.dirname(_HERE)

import harness  # noqa: E402
import host_safe_tmp  # noqa: E402

#: 已存在目录（包内 references/ 恒存在）——用它做「不该发请求」的取样
_EXISTING_DIR = os.path.join(PKG, "references")

#: **导入时刻**的原始函数快照（用于安装态复原）
_SNAPSHOT = {
    "os.mkdir": os.mkdir,
    "os.makedirs": os.makedirs,
    "os.replace": os.replace,
    "os.rename": os.rename,
    "Path.mkdir": pathlib.Path.mkdir,
    "Path.touch": pathlib.Path.touch,
    "tempfile.mkdtemp": tempfile.mkdtemp,
    "_INSTALLED": dict(host_safe_tmp._INSTALLED),
    "_ORIG_MKDIR": host_safe_tmp._ORIG_MKDIR,
    "_ORIG_MAKEDIRS": host_safe_tmp._ORIG_MAKEDIRS,
    "_ORIG_REPLACE": host_safe_tmp._ORIG_REPLACE,
    "_ORIG_RENAME": host_safe_tmp._ORIG_RENAME,
    "_ORIG_PATH_MKDIR": host_safe_tmp._ORIG_PATH_MKDIR,
}


@contextlib.contextmanager
def _installed_patch():
    """安装 `host_safe_tmp` 补丁，并在退出时**逐项还原**全局状态。

    ⚠ **为什么必须复原**：install() 改写的是**进程级**全局
      （`os.mkdir` 等）⇒ 不复原会污染同进程内后续套件 ⇒ 回归结果不可信。
    """
    try:
        yield
    finally:
        os.mkdir = _SNAPSHOT["os.mkdir"]
        os.makedirs = _SNAPSHOT["os.makedirs"]
        os.replace = _SNAPSHOT["os.replace"]
        os.rename = _SNAPSHOT["os.rename"]
        pathlib.Path.mkdir = _SNAPSHOT["Path.mkdir"]
        pathlib.Path.touch = _SNAPSHOT["Path.touch"]
        tempfile.mkdtemp = _SNAPSHOT["tempfile.mkdtemp"]
        host_safe_tmp._INSTALLED.clear()
        host_safe_tmp._INSTALLED.update(_SNAPSHOT["_INSTALLED"])
        host_safe_tmp._ORIG_MKDIR = _SNAPSHOT["_ORIG_MKDIR"]
        host_safe_tmp._ORIG_MAKEDIRS = _SNAPSHOT["_ORIG_MAKEDIRS"]
        host_safe_tmp._ORIG_REPLACE = _SNAPSHOT["_ORIG_REPLACE"]
        host_safe_tmp._ORIG_RENAME = _SNAPSHOT["_ORIG_RENAME"]
        host_safe_tmp._ORIG_PATH_MKDIR = _SNAPSHOT["_ORIG_PATH_MKDIR"]


def _read_text(path):
    """读文本文件（**及时关闭句柄** ⇒ 不产生 ResourceWarning）。

    ⚠ 为什么专门写这个 helper：测试里有多处 `open(...).read()`，
      未关闭的句柄会在 pytest 输出里刷 `ResourceWarning`
      ⇒ 淹没真正的断言失败信息 ⇒ 排查时容易看错重点。
    """
    with open(path, encoding="utf-8") as f:
        return f.read()


def _isdir_sequence(*values):
    """构造 `os.path.isdir` 的 side_effect：按调用序依次返回给定的真假值。

    ⚠ 典型用法：`(False, True)` ⇒
      第一次调用（`ensure_dir` 开头的短路判断）返回 False（原本不存在），
      第二次调用（失败后的**复查**）返回 True（broker 其实已代建好）。
      ⇒ 精确复刻「假失败」形态，且**零真实 IO**。
    """
    seq = list(values)

    def _side(_path):
        return seq.pop(0) if seq else False
    return _side


def _fake_open(contents):
    """构造 `builtins.open` 的替身：按路径返回给定字节内容（**零真实 IO**）。"""
    def _op(path, mode="r", *a, **k):
        key = os.fspath(path)
        if key not in contents:
            raise FileNotFoundError(path)
        return io.BytesIO(contents[key])
    return _op


class TestEnsureDirTruthCheck(unittest.TestCase):
    """D5-A：`ensure_dir` 的「失败后复查真相」（假失败救回 + 真失败如实抛）。"""

    def test_D5A_1_false_failure_is_rescued_by_isdir(self):
        """T-D5A-1（能红反例）：**假失败**（目录其实已建好）必须被判成功。

        ⚠ **构造口径**：mock `os.makedirs` 抛 `FileExistsError`（= broker 代建
          成功但响应在 5 秒超时中丢失），同时 mock `os.path.isdir` 按序返回
          `(False, True)`（首次检查：不存在 ⇒ 真去创建；复查：已存在）
          ⇒ 精确复刻 broker 的**假失败**形态，**零 broker 往返**。
          ⇒ 若 `ensure_dir` **不**复查 `isdir`，异常直接冒泡 ⇒ 判红。
        """
        with mock.patch.object(
                os, "makedirs",
                side_effect=FileExistsError(
                    "[模拟 broker 假失败] 目录已被代建，但响应在 5 秒超时中丢失")), \
                mock.patch("os.path.isdir", side_effect=_isdir_sequence(False, True)):
            try:
                harness.ensure_dir("/nonexistent/假失败路径")
            except Exception as exc:  # noqa: BLE001
                self.fail(f"假失败未被复查真相兜住，异常直接冒泡：{exc!r}")

    def test_D5A_2_real_failure_is_raised(self):
        """T-D5A-2（能红反例）：**真失败**（目录确实不存在）必须**如实抛出**。

        ⚠ 为何这条同样重要：若实现把异常**吞掉**（`except: pass`）或
          **无脑重试到成功**，真失败就被洗成假成功 ⇒ 体检的
          `REG_ENV_LIMITED` 归口失效 ⇒ **假绿**。
        """
        boom = PermissionError(
            "Brokered host mkdir requires an available runtime file rule")
        with mock.patch.object(os, "makedirs", side_effect=boom), \
                mock.patch("os.path.isdir", side_effect=_isdir_sequence(False, False)):
            with self.assertRaises(PermissionError):
                harness.ensure_dir("/nonexistent/真失败路径")

    def test_D5A_3_no_blind_retry(self):
        """T-D5A-3（能红反例）：`ensure_dir` **不得盲重试**。

        ⚠ 为何要钉这条（探针 8/9 实测否决盲重试）：
          盲重试会把「等一次授权（≈5 秒）」放大成「等 30+ 秒」
          （探针8 实测单次 `mkdtemp` 达 **235.56s**）⇒ 套件成倍变慢。
          ⇒ 判据：真失败时 `os.makedirs` 的**调用次数必须为 1**。
        """
        calls = []
        boom = PermissionError("Brokered host mkdir requires an available runtime file rule")

        def _counting(*a, **k):
            calls.append(1)
            raise boom

        with mock.patch.object(os, "makedirs", side_effect=_counting), \
                mock.patch("os.path.isdir", side_effect=_isdir_sequence(False, False)):
            with self.assertRaises(PermissionError):
                harness.ensure_dir("/nonexistent/真失败路径")
        self.assertEqual(
            len(calls), 1,
            f"真失败时 os.makedirs 被调用了 {len(calls)} 次 ⇒ 存在盲重试"
            f"（探针8 实测会放大到 235.56s）")

    def test_D5A_4_existing_dir_zero_request(self):
        """T-D5A-4：目录**已存在** ⇒ **零**建目录请求（幂等短路不退化）。

        ⚠ 这是 v3.31.1 成果的**不退化**守卫：D5 改了失败路径，
          不得把「已存在直接返回」改回去。
        """
        calls = []
        with mock.patch.object(
                os, "makedirs",
                side_effect=lambda *a, **k: calls.append(1)), \
                mock.patch("os.path.isdir", side_effect=_isdir_sequence(True)):
            harness.ensure_dir(_EXISTING_DIR)
        self.assertEqual(calls, [],
                         f"目录已存在却仍发起了 {len(calls)} 次建目录请求")


class TestReplaceTruthCheck(unittest.TestCase):
    """D5-B：`_replace_with_truth_check` 的「内容比对真相」判定。"""

    _SRC = "/虚拟/源.json"
    _DST = "/虚拟/目标.json"

    def _patched_replace_raises(self):
        return PermissionError(
            "Brokered host rename requires an available runtime file rule")

    def test_D5B_1_content_equal_after_failure_is_success(self):
        """T-D5B-1（能红反例）：rename 抛错但 **src/dst 内容一致**
        ⇒ 判定为「rename 实际已发生」⇒ 判成功。

        ⚠ **判据必须落在「内容一致」上**，不能只落在「dst 存在」——
          状态文件**本来就存在** ⇒ 存在性恒真 ⇒ 只看存在性会假绿
          （把「没替换」判成「替换了」）。
        """
        payload = b'{"v": 1}'
        with mock.patch.object(os, "replace", side_effect=self._patched_replace_raises()), \
                mock.patch("os.path.exists", return_value=True), \
                mock.patch("builtins.open",
                           side_effect=_fake_open({self._SRC: payload,
                                                   self._DST: payload})):
            harness._replace_with_truth_check(self._SRC, self._DST,
                                              attempts=2, backoff=0)
        # 不抛异常 ⇒ 判成功 ✅

    def test_D5B_2_content_differs_still_raises(self):
        """T-D5B-2（能红反例）：rename 抛错且 **src/dst 内容不同**
        ⇒ **不得**判成功 ⇒ 异常必须冒泡。

        ⚠ 这条钉住「内容比对」**不是**「存在性比对」的替身：
          若实现只查 `dst` 是否存在 ⇒ 这里 dst 存在但内容不同
          ⇒ 会被误判成功 ⇒ **状态被洗成假成功** ⇒ 假绿。
        """
        with mock.patch.object(os, "replace", side_effect=self._patched_replace_raises()), \
                mock.patch("os.path.exists", return_value=True), \
                mock.patch("builtins.open",
                           side_effect=_fake_open({self._SRC: b'{"v": 1}',
                                                   self._DST: b'{"v": 2}'})):
            with self.assertRaises(PermissionError):
                harness._replace_with_truth_check(self._SRC, self._DST,
                                                  attempts=2, backoff=0)

    def test_D5B_3_source_gone_is_success(self):
        """T-D5B-3：src 已消失 + dst 存在 ⇒ 判成功（rename 极可能已发生）。

        ⚠ 旁证判据：真实 rename 成功后源文件**必然消失** ⇒ 这是
          「rename 发生了」的第二个独立证据（第一个是内容一致）。
        """

        def _exists(path):
            return os.fspath(path) == self._DST

        with mock.patch.object(os, "replace", side_effect=self._patched_replace_raises()), \
                mock.patch("os.path.exists", side_effect=_exists):
            harness._replace_with_truth_check(self._SRC, self._DST,
                                              attempts=2, backoff=0)

    def test_D5B_4_both_missing_and_differ_is_rejected(self):
        """T-D5B-4（能红反例）：**既不存在也不一致** ⇒ 必须如实拒绝（抛）。

        ⚠ 为何这条独立于 T-D5B-2：T-D5B-2 只覆盖「dst 存在但内容不同」；
          本条覆盖「dst 压根不存在」——若实现写成「只要 dst 不存在就当成功」
          ⇒ 状态文件丢失却被判成功 ⇒ **静默重置**（本包明令禁止）。
        """
        with mock.patch.object(os, "replace", side_effect=self._patched_replace_raises()), \
                mock.patch("os.path.exists", return_value=False):
            with self.assertRaises(PermissionError):
                harness._replace_with_truth_check(self._SRC, self._DST,
                                                  attempts=2, backoff=0)

    def test_D5B_5_atomic_write_json_uses_truth_check(self):
        """T-D5B-5（能红反例）：`_atomic_write_json` **必须**走真相判定版。

        ⚠ **AST 级钉死**（不用正则）：正则会把 docstring 里的文字也算进去
          ⇒ 若实现里写了「os.replace」字样但**代码**仍用原生 `os.replace`，
          正则判据会假绿。
        """
        tree = ast.parse(inspect.getsource(harness._atomic_write_json).lstrip())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_atomic_write_json")
        called = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
        self.assertIn(
            "_replace_with_truth_check", called,
            f"_atomic_write_json 未走真相判定版，实际调用集：{sorted(called)}")
        self.assertNotIn(
            "replace", called,
            f"_atomic_write_json 仍直接调用原生 replace：{sorted(called)}")

    def test_D5B_6_harness_all_replace_sites_use_helper(self):
        """T-D5B-6（能红反例）：`harness.py` 内**所有** `os.replace` 调用点
        都必须走 `_replace_with_truth_check`（AST 级全量扫描）。

        ⚠ **为什么必须全量**：D5 修的是「所有 loop 命令的写状态路径」——
          若只修 `_atomic_write_json` 一处，其余两处（探针结果落盘、
          损坏文件备份轮转）仍会随机挂 ⇒ 修复不完整。
        ⚠ **AST 级扫描**：用 `ast.walk` 只认真实调用节点
          ⇒ 不会把 docstring / 注释里的 `os.replace` 字样算进去。
        """
        src = _read_text(os.path.join(_HERE, "harness.py"))
        tree = ast.parse(src)
        offenders = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            # 只看 `os.replace(...)` / `os.rename(...)` 形态
            if (isinstance(f, ast.Attribute) and f.attr in ("replace", "rename")
                    and isinstance(f.value, ast.Name) and f.value.id == "os"):
                offenders.append((f.value.id + "." + f.attr, n.lineno))
        # helper 内部的原生调用是"最后一层兜底"，合法 ⇒ 用精确行号区间排除
        hlines, hstart = inspect.getsourcelines(harness._replace_with_truth_check)
        hend = hstart + len(hlines)
        real_offenders = [(a, ln) for a, ln in offenders
                          if not (hstart <= ln <= hend)]
        self.assertEqual(
            [], real_offenders,
            f"harness.py 仍有直接调用原生 os.replace/os.rename 的点：{real_offenders}")
        # 且 helper 内部**恰好** 1 处原生调用（最后一次尝试）
        helper_native = [ln for ln in offenders if hstart <= ln[1] <= hend]
        self.assertEqual(
            len(helper_native), 1,
            f"helper 内的原生调用应恰好 1 处（最后一层兜底），实得 {helper_native}")


class TestHostSafeTmpLibrary(unittest.TestCase):
    """D5-C：`host_safe_tmp` 库的 mkdir/rename 入口补丁。"""

    def test_D5C_1_install_patches_all_entrypoints(self):
        """T-D5C-1（能红反例）：`install()` 必须覆盖 **全部**入口。

        ⚠ 依据实测：宿主 shim 有**五个**独立入口
          （`os.mkdir` / `os.makedirs` / `Path.mkdir` / `os.replace|rename`
          / **`Path.touch`**），其中 `Path.mkdir` 与 `Path.touch` 是
          **独立打补丁**的 ⇒ 漏掉任一个就漏
          （探针11 V3 实测 `Path.mkdir` 0/6 失败；
            2026-11-11 补测实测 `Path.touch` 直接 deny）。
          ⇒ 判据：patch 后这些属性**必须由本库提供**
            （`__module__ == "host_safe_tmp"`）。

        ⚠⚠ **判据口径修正（2026-11-11 实测修正）**：
          初版写的是「与**导入时刻**的快照不同」⇒ **在注入环境下必然假红**：
          `usercustomize` 在**解释器启动时**就装了补丁 ⇒ 本模块被 import 时
          `os.makedirs` **已经是** `_patched_makedirs` ⇒ 快照拿到的就是补丁版
          ⇒ 「与快照不同」永远不成立。
          ⇒ 改为「**归属**判据」：`__module__` 必须是 `host_safe_tmp`
            （这才是「谁提供的补丁」的真正语义，且不受安装时机影响）。
        """
        with _installed_patch():
            host_safe_tmp._INSTALLED["done"] = False
            self.assertTrue(host_safe_tmp.install())
            for label, fn in (
                    ("os.mkdir", os.mkdir),
                    ("os.makedirs", os.makedirs),
                    ("os.replace", os.replace),
                    ("os.rename", os.rename),
                    ("pathlib.Path.mkdir", pathlib.Path.mkdir),
                    ("pathlib.Path.touch", pathlib.Path.touch),
                    ("tempfile.mkdtemp", tempfile.mkdtemp),
            ):
                self.assertEqual(
                    getattr(fn, "__module__", None), "host_safe_tmp",
                    f"{label} 未由 host_safe_tmp 提供补丁"
                    f"（当前 __module__={getattr(fn, '__module__', None)}）")

    def test_D5C_1b_retry_budget_is_bounded(self):
        """T-D5C-1b（能红反例）：重试次数**必须封顶**（防「修 A 引入 B」）。

        ⚠ **这条钉的是一次真实回归**（2026-11-11）：
          broker 读超时固定 **5 秒** ⇒ 每次失败 ≈ 5 秒。
          初版把 `attempts` 设成 6（`DEFAULT_ATTEMPTS`）⇒ 实测单次
          `os.replace` 耗时 **19.16s**（harness 侧 4 次）⇒ 直接把
          `test_five_gates.py` 里 `state set` 的 **30 秒超时打爆**
          （2 个用例由「通过」变「超时失败」）⇒ **修 A 引入 B = 回归**。
          ⇒ 判据：`DEFAULT_ATTEMPTS` **必须 ≤ 3**（2 次 ≈ 10 秒，留足预算），
            且 harness 侧 `_replace_with_truth_check` 的默认 `attempts`
            **必须 ≤ 3**。
        """
        self.assertLessEqual(
            host_safe_tmp.DEFAULT_ATTEMPTS, 3,
            f"DEFAULT_ATTEMPTS={host_safe_tmp.DEFAULT_ATTEMPTS} ⇒ "
            f"单次失败最坏 ≈ {host_safe_tmp.DEFAULT_ATTEMPTS * 5}s ⇒ "
            f"会打爆下游 30 秒超时（修 A 引入 B）")

        # harness 侧：`_replace_with_truth_check` 的默认 attempts
        import inspect
        sig = inspect.signature(harness._replace_with_truth_check)
        self.assertLessEqual(
            sig.parameters["attempts"].default, 3,
            f"harness._replace_with_truth_check 默认 attempts="
            f"{sig.parameters['attempts'].default} ⇒ 耗时放大")

    def test_D5C_2_install_is_idempotent(self):
        """T-D5C-2：`install()` 重复调用只装一次（幂等）。"""
        with _installed_patch():
            host_safe_tmp._INSTALLED["done"] = False
            self.assertTrue(host_safe_tmp.install())
            self.assertFalse(host_safe_tmp.install(), "install() 非幂等")

    def test_D5C_3_patched_mkdir_keeps_fileexists_semantics(self):
        """T-D5C-3（能红反例）：`_patched_mkdir` **必须保留**
        `FileExistsError` 原生语义。

        ⚠ 为何这条极重要：`tempfile.mkdtemp` 的**候选名循环**依赖
          `FileExistsError` 来「换名重试」⇒ 若底层把它吞成成功，
          `mkdtemp` 会返回一个**早就存在的残留目录**（危险 ⇒ 静默污染）。
          ⇒ 判据：底层抛 `FileExistsError` ⇒ 外层必须**原样**抛。
        """
        with _installed_patch():
            host_safe_tmp._INSTALLED["done"] = False
            host_safe_tmp.install()
            with mock.patch.object(
                    host_safe_tmp, "_ORIG_MKDIR",
                    side_effect=FileExistsError("已存在")):
                with self.assertRaises(FileExistsError):
                    os.mkdir(_EXISTING_DIR)

    def test_D5C_4_patched_mkdir_rescues_false_failure(self):
        """T-D5C-4（能红反例）：`_patched_mkdir` 对「代建成功 + 响应丢失」
        必须判成功（复查 `isdir`）。"""
        with _installed_patch():
            host_safe_tmp._INSTALLED["done"] = False
            host_safe_tmp.install()
            with mock.patch.object(
                    host_safe_tmp, "_ORIG_MKDIR",
                    side_effect=PermissionError(
                        "[模拟 broker 假失败] 已代建，但响应在 5 秒超时中丢失")), \
                    mock.patch("os.path.isdir", return_value=True):
                try:
                    os.mkdir("/虚拟/假失败目录")
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"假失败未被复查兜住，异常冒泡：{exc!r}")

    def test_D5C_6_patched_path_touch_rescues_false_failure(self):
        """T-D5C-6（能红反例）：`_patched_path_touch` 对「代建成功 + 响应丢失」
        必须判成功（复查文件是否存在）。

        ⚠ 宿主**第五个入口**（2026-11-11 补测发现）：
          `sitecustomize._brokered_path_touch`（:785）⇒ broker deny 时抛
          `PermissionError` ⇒ 实测 `test_five_gates.py` 的
          `test_T4_three_source_check_runs` 直接挂在 `.touch()` 那一行。
        """
        with _installed_patch():
            host_safe_tmp._INSTALLED["done"] = False
            host_safe_tmp.install()
            with mock.patch.object(
                    host_safe_tmp, "_ORIG_PATH_TOUCH",
                    side_effect=PermissionError(
                        "[模拟 broker 假失败] 已代建，但响应在 5 秒超时中丢失")), \
                    mock.patch("os.path.exists", return_value=True):
                try:
                    pathlib.Path("/虚拟/假失败文件.txt").touch()
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"Path.touch 假失败未被复查兜住，异常冒泡：{exc!r}")

    def test_D5C_5_same_content_helper(self):
        """T-D5C-5：`_same_content` 判据正确（不同内容 ⇒ False；相同 ⇒ True）。"""
        a, b = "/虚拟/a", "/虚拟/b"
        with mock.patch("builtins.open",
                        side_effect=_fake_open({a: b"x", b: b"y"})):
            self.assertFalse(host_safe_tmp._same_content(a, b))
        with mock.patch("builtins.open",
                        side_effect=_fake_open({a: b"x", b: b"x"})):
            self.assertTrue(host_safe_tmp._same_content(a, b))


class TestUsercustomizeInjection(unittest.TestCase):
    """D5-D：`usercustomize_host_safe.py` 注入点的形状判据（**不真跑注入**）。"""

    _ENTRY = os.path.join(_HERE, "usercustomize_host_safe.py")

    def test_D5D_1_entry_calls_install(self):
        """T-D5D-1：注入点必须调用 `host_safe_tmp.install()`。

        ⚠ 注入点的**唯一职责**就是装补丁 ⇒ 判据落在调用点上，
          不去真跑 `site.execsitecustomize()`（那会污染整个进程）。
        """
        self.assertTrue(os.path.isfile(self._ENTRY), f"注入点不存在：{self._ENTRY}")
        tree = ast.parse(_read_text(self._ENTRY))
        called = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
        self.assertIn("install", called,
                      f"注入点未调用 install()，实际调用集：{sorted(called)}")

    def test_D5D_2_injection_failure_is_not_silent(self):
        """T-D5D-2（能红反例）：注入**失败**必须**可见**（写 stderr）。

        ⚠ 静默失败最毒：补丁没装上 ⇒ 建目录随机失败 ⇒ 但**没人知道**
          ⇒ 直到某个 loop 命令在生产里随机挂才被发现。
          ⇒ 判据：异常分支里必须有 `sys.stderr` 写入。
        """
        tree = ast.parse(_read_text(self._ENTRY))
        handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
        self.assertTrue(handlers, "注入点缺少异常处理 ⇒ 注入失败会直接打死解释器")
        has_stderr = False
        for h in handlers:
            for sub in ast.walk(h):
                if isinstance(sub, ast.Attribute) and sub.attr == "stderr":
                    has_stderr = True
                if isinstance(sub, ast.Name) and sub.id == "stderr":
                    has_stderr = True
        self.assertTrue(has_stderr,
                        "注入失败分支未写 stderr ⇒ 静默失败（最毒的一类）")

    def test_D5D_3_entry_does_not_override_sitecustomize(self):
        """T-D5D-3（能红反例）：**不得**自带 `sitecustomize` 语义
        （那会覆盖宿主策略 = 越权）。

        ⚠ 宿主 shim 已占用 `sitecustomize`（PYTHONPATH 第一位）⇒
          我们若也提供 `sitecustomize.py`，会**顶掉**宿主的授权策略
          ⇒ 属于越权，违反本包纪律。
          ⇒ 判据：包内 `scripts/` 下**不得**存在 `sitecustomize.py`。
        """
        self.assertFalse(
            os.path.exists(os.path.join(_HERE, "sitecustomize.py")),
            "scripts/ 下出现 sitecustomize.py ⇒ 会顶掉宿主授权策略（越权）")


class TestMockAnchorSemantics(unittest.TestCase):
    """D5-E：注入后**不得**破坏 mock 锚点（否则守卫整批假绿）。"""

    def test_D5E_1_mock_patch_mkdtemp_still_effective(self):
        """T-D5E-1（能红反例）：`mock.patch("tempfile.mkdtemp")` 必须仍生效。

        ⚠ 为何这条是**全批守卫的生命线**：
          `scripts/test_arch_drift.py` 的 `TestAntiExampleSkipSemantics` 的 T4
          会 `mock.patch("tempfile.mkdtemp")` 抛错来验证「构造失败 ⇒ skip」
          这条**真实生产链**。
          ⇒ 若注入把 `tempfile.mkdtemp` 换成了**不可 mock** 的东西，
          11 个反例会全部被 skip ⇒ 守卫的"能红"属性**整批未验证**（假绿）。
          ⇒ 判据：mock 后 `tempfile.mkdtemp` 必须被替换成 mock 且调用会抛。
        ⚠ **判据口径**：不用「与快照不同」（注入环境下快照本身已是补丁版 ⇒ 必假红），
          改为断言「mock 期间该属性被换成了 `MagicMock`」。
        """
        with mock.patch("tempfile.mkdtemp") as m:
            self.assertIsInstance(tempfile.mkdtemp, mock.MagicMock,
                                  "mock.patch('tempfile.mkdtemp') 未生效")
            m.side_effect = PermissionError("[mock] 构造失败")
            with self.assertRaises(PermissionError):
                tempfile.mkdtemp()

    def test_D5E_2_arch_drift_anchor_intact(self):
        """T-D5E-2：`test_arch_drift.py` 的 `_ORIGIN_MKDOTEMP` 锚点语义完好。

        ⚠ 该锚点用于识别「mkdtemp 是否被 mock」⇒ 若注入改变了锚点指向，
          skip 语义判定会误判 ⇒ 反例全被 skip。
        """
        p = os.path.join(_HERE, "test_arch_drift.py")
        if not os.path.isfile(p):
            self.skipTest(f"锚点文件不存在：{p}")
        src = _read_text(p)
        self.assertIn("_ORIGIN_MKDOTEMP", src,
                      "test_arch_drift.py 缺少 _ORIGIN_MKDOTEMP 锚点")


if __name__ == "__main__":
    unittest.main(verbosity=2)

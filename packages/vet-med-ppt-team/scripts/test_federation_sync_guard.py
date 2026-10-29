#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_federation_sync_guard.py — 联邦 shim 巡检（第 13 项）的**反例守卫**。

══════════════════════════════════════════════════════════════════════
被守卫的缺陷（真实缺陷，2026-10-29 实测确证）：

  ① 断层本体：`vet-med-ppt-team/scripts/assemble_spawn_prompt.py` 停在
     v3.4.1 R9 形态（65 行、只找联邦 core、**无 vendor 兜底**）
     ⇒ git clone 态跑 `--list-members` 直接 exit 3（实测：退出码 3、
       缺失全部 5 个成员）⇒ 可安装性回归。

  ② 巡检漏检（**本次任务的根因**）：`ensure_settings.check_federation_sync()`
     原实现里
         skip = {"shared-core", "viral-evo-lab", expert_dir and os.path.basename(expert_dir)}
     把**自身包**也 skip 掉了 ⇒ 自身包的 shim 版本声明**永远不被扫描**
     ⇒ 「自身包 shim 未跟升」「自身包 vendor 漂移」这类断层**结构性不可见**
     ⇒ ① 的真缺陷就这样躲过了第 13 项体检。

  ③ 无反例：`check_federation_sync` 在全仓没有任何对应的反例测试
     ⇒ 即便有人再把自身包塞回 skip，也**没有任何东西会红**。

本文件把 ② ③ 一并钉死：把巡检的扫描逻辑抽成**纯函数**
`scan_federation_shims(plugins_root, core_path, skip)`，从而能在
**隔离目录**里造反例，不碰真实联邦目录。

判据清单（每条都配**能红的反例** ⇒ 防假绿）：

  G1  `scan_federation_shims` 是**纯函数**：同样入参 ⇒ 同样出参，
      且不打印、不改文件（薄壳 `check_federation_sync` 只负责打印与返回 rc）。
  G2  反例：造一个「shim 声明停留在 v3.4.1 R9」的假包
      ⇒ 必须被判为 `stale`（未跟升）。
  G3  反例：造一个 vendor 副本与 core sha256 不一致 ⇒ 必须被判为 `drift`。
  G4  **自身包不得被 skip** —— 钉死「skip 集合里不能含自身包」这条规则。
      （这是本次缺陷的根因；无此守卫，下次改回去照样绿。）
  G5  所有 shim 包都必须达 `v3.4.2 P0-1`（**含自身包**）⇒ 在真实联邦目录上
      跑一遍，断言 `stale` 为空、`drift` 为空。真实目录不满足 ⇒ 测试红
      （这正是我们要的效果）。
  G6  反例：在 tmpdir 副本里把 `v3.4.2 P0-1` 改成 `v3.4.1 R9`
      ⇒ `stale` 非空 ⇒ 证明判据对「头部声明」敏感，不是恒红也不是恒绿。

⚠ **全程不碰生产 `config/*.yaml`，也不碰真实联邦目录的写操作**：
  构造反例一律在 `tempfile` 造的 tmpdir 里手工搭最小结构
  （`plugins/<pkg>/scripts/assemble_spawn_prompt.py` + `shared-core/`），
  不依赖隔离包机制 ⇒ 更可控、更快、也不受 broker 拦 mkdir 影响。

运行：
    python3 -m pytest scripts/test_federation_sync_guard.py -v
    python3 scripts/test_federation_sync_guard.py          # 直跑
"""

import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES = PKG / "scripts" / "ensure_settings.py"

#: 本包自身的包名（联邦里的目录名）。
SELF_PKG_NAME = "vet-med-ppt-team"


def _load_es():
    """按路径加载 ensure_settings.py（不依赖包内 import 副作用）。"""
    spec = importlib.util.spec_from_file_location("es_fed_guard", ES)
    m = importlib.util.module_from_spec(spec)
    sys.modules["es_fed_guard"] = m
    spec.loader.exec_module(m)
    return m


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ───────────────────────────────────────── 反例场景构造器（tmpdir 内手工搭最小结构）
#: 假包的 shim 头部——**声明停留在旧版**（= 2026-10-29 那个真缺陷的形态）。
_SHIM_R9 = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容 shim（v3.4.1 R9 shared-core 下沉，2026-10-14）
================================================
本包的实现已下沉至联邦共享件。
"""
import sys

if __name__ == "__main__":
    sys.exit(0)
'''

#: 假包的 shim 头部——**已达当前标准**。
_SHIM_P01 = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容 shim（v3.4.2 P0-1 分发修复，2026-10-15；原 v3.4.1 R9 shared-core 下沉）
==============================================================================
本包的实现已下沉至联邦共享件。
"""
import sys

if __name__ == "__main__":
    sys.exit(0)
'''

#: 联邦真源的内容（假 core）——只用于算 sha256，不要求能跑。
_CORE_BODY = "# 假联邦 core\nx = 1\n"


def _build_fake_federation(root: Path, shims: dict, vendor: dict = None):
    """在 tmpdir 里搭一个最小联邦结构。

    参数：
      root   —— tmpdir 根（将创建 `<root>/plugins/`）
      shims  —— {包名: shim 头部文本} —— 有该键即创建该包的 shim 文件
      vendor —— {包名: vendor 副本内容} —— 有该键即创建该包的 vendor 副本

    返回：(plugins_root, core_path)
    """
    plugins_root = root / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    # 联邦真源
    core_dir = plugins_root / "shared-core"
    core_dir.mkdir(parents=True, exist_ok=True)
    core_path = core_dir / "assemble_spawn_prompt.py"
    core_path.write_text(_CORE_BODY, encoding="utf-8")
    # 各包 shim
    for name, body in shims.items():
        d = plugins_root / name / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        (d / "assemble_spawn_prompt.py").write_text(body, encoding="utf-8")
    # 各包 vendor 副本
    for name, body in (vendor or {}).items():
        d = plugins_root / name / "vendor" / "shared-core"
        d.mkdir(parents=True, exist_ok=True)
        (d / "assemble_spawn_prompt.py").write_text(body, encoding="utf-8")
    return plugins_root, core_path


class TestFederationSyncGuard(unittest.TestCase):
    """G1–G6：联邦 shim 巡检的可测性与反例能力。"""

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    def _tmp_federation(self, shims, vendor=None):
        """建 tmpdir 联邦 ⇒ 返回 (root, plugins_root, core_path)。"""
        root = Path(tempfile.mkdtemp(prefix="vetmed-fed-guard-"))
        plugins_root, core_path = _build_fake_federation(root, shims, vendor)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root, plugins_root, core_path

    # ── G1：纯函数可测（薄壳与逻辑分离）─────────────────────────────
    def test_G1_scan_is_pure_function(self):
        """G1：`scan_federation_shims` 必须是**纯函数**——可脱离真实联邦目录单测。

        判据拆成两半：
          ① **纯函数存在且签名可脱离真实联邦目录调用**
             （plugins_root / core_path / skip 全部显式传入）；
          ② **同样入参 ⇒ 同样出参**（两次调用结果全等），
             且调用期间**不产生任何 stdout 输出**（纯逻辑不打印）。

        ⚠ ② 是防假绿的关键：若 `scan_federation_shims` 内部偷偷打印，
          薄壳与纯函数就没分离 ⇒ 单测会被输出污染 ⇒ 这条会红。
        """
        _, plugins_root, core_path = self._tmp_federation(
            {"pkg-a": _SHIM_P01, "pkg-b": _SHIM_R9})

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r1 = self.es.scan_federation_shims(plugins_root, core_path)
            r2 = self.es.scan_federation_shims(plugins_root, core_path)

        self.assertEqual(buf.getvalue(), "",
                         "scan_federation_shims 打印了东西——薄壳与纯逻辑未分离")
        self.assertEqual(r1, r2, "同样入参两次调用结果不一致——不是纯函数")
        rows, stale, drift = r1
        self.assertIsInstance(rows, list)
        self.assertIsInstance(stale, list)
        self.assertIsInstance(drift, list)
        # 返回结构契约：rows 是 [(包名, 描述), ...]
        self.assertTrue(all(isinstance(r, tuple) and len(r) == 2 for r in rows),
                        "rows 元素必须是 (包名, 描述) 二元组")

    # ── G2 反例（能红）：R9 声明 ⇒ stale ─────────────────────────────
    def test_G2_reverse_example_legacy_declaration_flagged_stale(self):
        """G2 反例：造一个「shim 声明停留在 v3.4.1 R9」的假包 ⇒ 必须被判 `stale`。

        这条直接对应 2026-10-29 的真缺陷形态（vet-med-ppt-team 停在 R9）。
        若它判不出来，说明巡检对「头部声明」不敏感 ⇒ 断层可以无限潜伏。
        """
        _, plugins_root, core_path = self._tmp_federation(
            {"pkg-legacy": _SHIM_R9, "pkg-current": _SHIM_P01})

        rows, stale, drift = self.es.scan_federation_shims(plugins_root, core_path)

        self.assertIn("pkg-legacy", stale,
                      "R9 声明的假包未被判为 stale——判据失效（假绿）")
        self.assertNotIn("pkg-current", stale,
                         "已达 P0-1 的包被误判为 stale——判据过宽（假阳性）")
        self.assertEqual(drift, [], "无 vendor 副本时不应报 drift")
        # 展示行必须明确标出「未跟升」
        rowmap = dict(rows)
        self.assertIn("pkg-legacy", rowmap)
        self.assertIn("未跟升", rowmap["pkg-legacy"],
                      "展示行未标出「未跟升」——运维看不出该怎么处置")

    # ── G3 反例（能红）：vendor 哈希不一致 ⇒ drift ──────────────────
    def test_G3_reverse_example_vendor_sha_mismatch_flagged_drift(self):
        """G3 反例：造一个 vendor 副本与 core sha256 不一致 ⇒ 必须被判 `drift`。

        防的是「兜底副本悄悄老化」：联邦真源更新了，某包还留着旧副本 ⇒
        该包在 git clone 态跑出来的行为与安装态**不一致**。
        """
        _, plugins_root, core_path = self._tmp_federation(
            {"pkg-ok": _SHIM_P01, "pkg-drifted": _SHIM_P01},
            vendor={"pkg-ok": _CORE_BODY, "pkg-drifted": "# 过期副本\ny = 2\n"})

        rows, stale, drift = self.es.scan_federation_shims(plugins_root, core_path)

        self.assertIn("pkg-drifted", drift,
                      "vendor 副本与 core 不一致的包未被判为 drift——防漂移失效")
        self.assertNotIn("pkg-ok", drift,
                         "vendor 与 core 一致的包被误判为 drift——假阳性")
        self.assertEqual(stale, [], "本例只造了漂移，未造版本滞后")
        rowmap = dict(rows)
        self.assertIn("漂移", rowmap["pkg-drifted"],
                      "展示行未标出「漂移」——运维看不出该怎么处置")

    # ── G4：自身包不得被 skip（**本次缺陷的根因**）────────────────────
    def test_G4_self_package_must_not_be_skipped(self):
        """G4：**自身包不得被 skip** —— 钉死「skip 集合里不能含自身包」。

        ★ 这是本次任务的核心判据。2026-10-29 之前的实现：
            skip = {"shared-core", "viral-evo-lab", expert_dir and os.path.basename(expert_dir)}
          把自身包也 skip 掉了 ⇒ 自身包的 shim 断层**永远不可见**。

        本条钉死三件事：
          ① `federation_skip_set()` **不含**自身包名（即使显式传入才含）；
          ② `scan_federation_shims` 在 skip 不含自身时**确实扫到**自身包；
          ③ **反向对照**：自身包真出问题时（stale/drift）⇒ 一定被判红
             —— 证明「扫到」不是「扫到但无害」。
        """
        # ① 固定跳过集不含自身包
        skip_set = self.es.federation_skip_set()
        self.assertNotIn(SELF_PKG_NAME, skip_set,
                         "★ 固定跳过集里含自身包——巡检对自己的断层结构性失明")
        self.assertIn("shared-core", skip_set, "固定跳过集应含 shared-core（真源非 shim 包）")
        self.assertIn("viral-evo-lab", skip_set,
                      "固定跳过集应含 viral-evo-lab（独立定制版 shim）")

        # ② skip 不含自身 ⇒ 自身包**确实被扫到**
        _, plugins_root, core_path = self._tmp_federation(
            {SELF_PKG_NAME: _SHIM_P01, "pkg-other": _SHIM_P01})
        rows, _stale, _drift = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        scanned = {n for n, _v in rows}
        self.assertIn(SELF_PKG_NAME, scanned,
                      "★ 自身包未被扫描——这正是 2026-10-29 缺陷的根因")
        self.assertIn("pkg-other", scanned, "其他包也未被扫描（对照）")

        # ③ 反向对照：自身包**真的**出问题时必须判红
        _, plugins_root2, core_path2 = self._tmp_federation(
            {SELF_PKG_NAME: _SHIM_R9})
        rows2, stale2, _ = self.es.scan_federation_shims(
            plugins_root2, core_path2, self.es.federation_skip_set())
        self.assertIn(SELF_PKG_NAME, stale2,
                      "★ 自身包停在旧版却没被判 stale——守卫形同虚设")
        self.assertIn(SELF_PKG_NAME, {n for n, _v in rows2},
                      "自身包未出现在巡检结果里")

    def test_G4b_reverse_example_self_skip_would_hide_the_defect(self):
        """G4b 反例（**能红**）：把自身包塞进 skip ⇒ 断层必须被**掩盖**。

        这条是 G4 的**反向对照**，用来证明 G4 的判据不是恒真：
          · 若「skip 含自身包」时**照样**能判出 stale ⇒ G4 的判据毫无判别力
            （说明「扫到」与「判出」无关，G4 钉不住任何东西）；
          · 正确表现：**skip 含自身 ⇒ 判不出**（断层被掩盖）
            ⇒ 这就反证了「不 skip 自身」是断层的**必要条件**。
        """
        _, plugins_root, core_path = self._tmp_federation(
            {SELF_PKG_NAME: _SHIM_R9, "pkg-other": _SHIM_R9})

        # 不 skip 自身 ⇒ 能判出
        _, stale_ok, _ = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        self.assertIn(SELF_PKG_NAME, stale_ok,
                      "不 skip 自身时判不出断层——前提不成立，反例无意义")

        # skip 自身 ⇒ 断层被掩盖（这正是旧实现的病灶）
        _, stale_hidden, _ = self.es.scan_federation_shims(
            plugins_root, core_path,
            self.es.federation_skip_set(explicit_skip=(SELF_PKG_NAME,)))
        self.assertNotIn(SELF_PKG_NAME, stale_hidden,
                         "★ skip 自身后仍能判出断层——说明「skip 自身」并不掩盖断层，"
                         "G4 钉的不是真根因")
        # 而其他包仍照常被判出 ⇒ 证明确实只掩盖了自身，不是整个巡检失效
        self.assertIn("pkg-other", stale_hidden,
                      "skip 自身后连别的包也判不出了——对照不成立")

    # ── G5：真实联邦目录上跑一遍（**含自身包**）──────────────────────
    def test_G5_real_federation_all_shims_current_and_no_drift(self):
        """G5：真实联邦目录下，所有 shim 包（含**自身包**）都必须达 `v3.4.2 P0-1`，
        且 vendor 副本**无哈希漂移**。

        ★ 本条是**端到端守门**：若将来某个包（或本包自己）又退回 R9 形态、
        或 vendor 副本老化 ⇒ 本条立刻红。

        ⚠ 真实目录不满足时**就该红**——这是我们要的效果，不是误报。
        """
        plugins_root = PKG.parent                      # .../plugins
        core_path = plugins_root / "shared-core" / "assemble_spawn_prompt.py"
        self.assertTrue(core_path.is_file(),
                        f"联邦真源不存在：{core_path}（非安装态？本条需在安装态下跑）")

        rows, stale, drift = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())

        self.assertEqual(stale, [],
                         "★ 联邦里有包 shim 未跟升到 "
                         f"{self.es.FEDERATION_SHIM_STANDARD}（含自身包）：{stale}")
        self.assertEqual(drift, [],
                         "★ 联邦里有包 vendor 副本与联邦真源哈希不一致：{drift}".format(
                             drift=drift))

        # 自身包必须在被扫描的集合里（否则本条等于没巡检自身）
        scanned = {n for n, _v in rows}
        self.assertIn(SELF_PKG_NAME, scanned,
                      "★ 自身包不在巡检结果里——G5 变成了空巡检")

        # 且自身包必须真的达标（版本声明 + vendor 哈希）
        rowmap = dict(rows)
        self.assertIn("P0-1", rowmap[SELF_PKG_NAME],
                      f"★ 自身包未达 {self.es.FEDERATION_SHIM_STANDARD}："
                      f"{rowmap[SELF_PKG_NAME]}")
        self.assertNotIn("漂移", rowmap[SELF_PKG_NAME],
                      "★ 自身包 vendor 副本与联邦真源漂移")

    # ── G6 反例（能红）：改头部声明 ⇒ 判据转红 ───────────────────────
    def test_G6_reverse_example_changing_declaration_turns_judgement_red(self):
        """G6 反例：把 shim 头部声明从 `v3.4.2 P0-1` 改成 `v3.4.1 R9`
        ⇒ `stale` 必须**非空**。

        这条钉死判据对「头部声明」**敏感**：
          · 若改声明后 `stale` 仍为空 ⇒ 判据失效（假绿）；
          · 若改声明前 `stale` 就非空 ⇒ 判据恒红（假阳性）。
        两个方向都要覆盖 ⇒ 才有判别力。
        """
        _, plugins_root, core_path = self._tmp_federation(
            {SELF_PKG_NAME: _SHIM_P01})

        # 改之前：干净 ⇒ 不报滞后
        _rows, stale_before, _ = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        self.assertEqual(stale_before, [],
                         "改之前就不干净——反例前提不成立（判据恒红）")

        # 改声明：v3.4.2 P0-1 → v3.4.1 R9
        shim_path = (plugins_root / SELF_PKG_NAME / "scripts" /
                     "assemble_spawn_prompt.py")
        text = shim_path.read_text(encoding="utf-8")
        self.assertIn("v3.4.2 P0-1", text, "反例前提：头部声明不是 P0-1")
        shim_path.write_text(
            text.replace("v3.4.2 P0-1", "v3.4.1 R9"), encoding="utf-8")

        # 改之后：必须报滞后
        _rows2, stale_after, _ = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        self.assertIn(SELF_PKG_NAME, stale_after,
                      "★ 改掉头部声明后判据仍不报滞后——判据对声明不敏感（假绿）")

        # 复原 ⇒ 归绿 ⇒ 证明判红确由该声明改动引起，不是恒红
        shim_path.write_text(text, encoding="utf-8")
        _rows3, stale_restored, _ = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        self.assertEqual(stale_restored, [],
                         "复原声明后仍报滞后——判据不是由声明驱动的")


class TestFederationSyncThinShell(unittest.TestCase):
    """薄壳行为：`check_federation_sync` 只负责打印与返回 rc，扫描逻辑全在纯函数里。

    判据：
      S1  非安装态（plugins_root 下无 shared-core 真源）⇒ 返回 0 并明确说「跳过」
      S2  安装态且全达标 ⇒ 返回 0
      S3  安装态且有滞后/漂移 ⇒ 返回 1（**阻断**）
      S4  薄壳必须**转发** extra_skip 给纯函数（skip 语义不丢）
    """

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    def _run_shell(self, expert_dir: str) -> tuple:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.es.check_federation_sync(expert_dir)
        return rc, buf.getvalue()

    def test_S1_non_installed_state_skips(self):
        """S1：非安装态（无联邦真源）⇒ rc=0 且提示「跳过」（不误报、不阻断）。"""
        root = Path(tempfile.mkdtemp(prefix="vetmed-fed-noninst-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        pkg = root / "some-pkg"
        pkg.mkdir()
        rc, out = self._run_shell(str(pkg))
        self.assertEqual(rc, 0, "非安装态应跳过而非阻断")
        self.assertIn("跳过", out, "非安装态未给出「跳过」提示")

    def test_S2_all_current_returns_zero(self):
        """S2：安装态且全部达标 ⇒ rc=0。"""
        root = Path(tempfile.mkdtemp(prefix="vetmed-fed-ok-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        plugins_root, core_path = _build_fake_federation(
            root, {"pkg-a": _SHIM_P01}, vendor={"pkg-a": _CORE_BODY})
        rc, out = self._run_shell(str(plugins_root / "pkg-a"))
        self.assertEqual(rc, 0, f"全达标却报红：{out}")
        self.assertIn(self.es.FEDERATION_SHIM_STANDARD, out,
                      "输出未显示当前版本契约")

    def test_S3_stale_returns_one(self):
        """S3：安装态且有滞后 ⇒ rc=1（**阻断**，这是巡检的用途）。"""
        root = Path(tempfile.mkdtemp(prefix="vetmed-fed-stale-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        plugins_root, _core = _build_fake_federation(
            root, {"pkg-a": _SHIM_P01, "pkg-b": _SHIM_R9})
        rc, out = self._run_shell(str(plugins_root / "pkg-a"))
        self.assertEqual(rc, 1, f"有滞后包却未报红：{out}")
        self.assertIn("pkg-b", out, "输出未点名哪个包滞后")

    def test_S4_shell_forwards_extra_skip(self):
        """S4：薄壳必须把 `extra_skip` **转发**给纯函数（skip 语义不丢）。

        反例对照：若薄壳不转发 ⇒ 调用方显式排除某包的能力静默失效
        ⇒ 运维会以为排除了、实际没排除 ⇒ 又一个「假绿」入口。
        """
        root = Path(tempfile.mkdtemp(prefix="vetmed-fed-skip-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        plugins_root, _core = _build_fake_federation(
            root, {"pkg-a": _SHIM_P01, "pkg-b": _SHIM_R9})

        # 不排除 pkg-b ⇒ 报红
        rc_all, _ = self._run_shell(str(plugins_root / "pkg-a"))
        self.assertEqual(rc_all, 1, "有滞后包却未报红")

        # 显式排除 pkg-b ⇒ 归绿 ⇒ 证明转发生效
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_excl = self.es.check_federation_sync(
                str(plugins_root / "pkg-a"), extra_skip=("pkg-b",))
        self.assertEqual(rc_excl, 0,
                         "★ 薄壳未转发 extra_skip——显式排除能力静默失效")


if __name__ == "__main__":
    unittest.main(verbosity=2)

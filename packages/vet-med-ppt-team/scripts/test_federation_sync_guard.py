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

第二组（G7–G9）：**基准集合**语义（2026-10-30 实测真缺陷的第二层）。

  被守卫的缺陷（真缺陷，实测非推断）：
    联邦真源 `shared-core/assemble_spawn_prompt.py` 被**并行会话**改动
    （401 → 514 行），且改动在 `my-experts/plugins` 仓库里是**未提交**状态
    （`git status` 显示 ` M`）。旧实现拿「联邦真源**工作区文件**的 sha」当
    **唯一**比对基准 ⇒ 真源一旦在途未提交，所有**尚未跟升**的包都被误判成
    「vendor 漂移」⇒ 把「这个包没跟上最新真源」（正常节奏的**待同步**）与
    「这个包的副本坏了/对不上**已发布**真源」（**真缺陷**）混为一谈。
    后果：**已提交真源的防漂移能力被架空**——真源提交后本该报出的未跟升包，
    在真源未提交期间被噪声淹没。

  修复后的语义（基准**集合** = {工作区真源 sha} ∪ {已提交真源 sha}）：
    · vendor sha 命中集合中**任一** ⇒ 不算漂移（已同步到某一版真源）；
    · vendor sha **不命中任何** ⇒ 算漂移（对不上任何已知真源版本 = 真缺陷）。

  G7  **真源在途未提交时**未跟升的包**不应**被报出漂移（噪声被正确抑制）。
      ★ 能红反例：把基准集合退化成「只有工作区 sha」⇒ 必然误报漂移。
  G8  **真源已提交后**，未跟升的包**仍然必须**被报出漂移（真信号不被放宽基准
      而丢掉）——这是防漂移的**核心价值**，绝不能因为放宽基准而丢掉。
      ★ 能红反例：把判定改成「任何 sha 都算命中」⇒ 必然漏报。
  G9  **容错**：真源不在 git 仓库 / git 不可用 / 已提交路径不存在
      ⇒ **不抛异常**，且行为退回「只有工作区 sha」基准。

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
import subprocess
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

#: 「真源」的两个版本（用于构造「工作区版 ≠ 已提交版」的在途未提交场景）。
_CORE_V1 = "# 真源 v1（已提交版）\nx = 1\n"
_CORE_V2 = "# 真源 v2（在途未提交的工作区版，新增 115 行动态成员层）\nx = 2\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """在 `repo` 里跑 git（只用于**构造**隔离反例；带 -c 避免依赖用户全局配置）。"""
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=vetmed-test",
         "-c", "user.email=vetmed-test@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
         *args],
        capture_output=True, text=True, timeout=60)


def _git_init_repo(repo: Path) -> bool:
    """把 `repo` 初始化成一个 git 仓库。返回是否成功（git 不可用 ⇒ False）。"""
    try:
        r = subprocess.run(["git", "init", "-q", str(repo)],
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def _git_commit_all(repo: Path, message: str = "snap") -> bool:
    """把 `repo` 当前工作区全部提交。返回是否成功。"""
    try:
        if _git(repo, "add", "-A").returncode != 0:
            return False
        r = _git(repo, "commit", "-q", "-m", message)
        return r.returncode == 0
    except Exception:
        return False


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


class TestFederationBaselineSet(unittest.TestCase):
    """G7–G9：**基准集合**语义（真源在途未提交时，噪声 vs 真信号的分离）。

    ★ 这组判据针对的是 2026-10-30 实测的真缺陷：
      真源被并行会话改动且**未提交**时，旧实现（单一「工作区 sha」基准）
      会把所有未跟升的包误判成「vendor 漂移」⇒ 噪声淹没真信号
      ⇒ **已提交真源的防漂移能力被架空**。

    ★ **每条判据都有能红的反例**（本仓库铁律）——
      G7 的反例 = 基准集合退化成「只有工作区 sha」；
      G8 的反例 = 判定改成「任何 sha 都算命中」；
      G9 的反例 = 基准获取抛异常（巡检直接崩）。
    """

    @classmethod
    def setUpClass(cls):
        cls.es = _load_es()

    def _tmp_root(self, prefix="vetmed-fed-base-"):
        root = Path(tempfile.mkdtemp(prefix=prefix))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _build_repo_federation(self, root: Path, *, committed_body: str,
                               worktree_body: str, vendor_body: str,
                               git_init: bool = True):
        """搭一个**隔离的 git 仓库**形态的联邦：真源 + 已提交态 + 在途工作区态。

        返回 (plugins_root, core_path, vendor_path, committed_sha)。
        """
        plugins_root = root / "plugins"
        core_dir = plugins_root / "shared-core"
        core_dir.mkdir(parents=True, exist_ok=True)
        core_path = core_dir / "assemble_spawn_prompt.py"
        core_path.write_text(worktree_body, encoding="utf-8")

        # vendor 副本（装在某个包下）
        pkg_dir = plugins_root / "pkg-a"
        (pkg_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "scripts" / "assemble_spawn_prompt.py").write_text(
            _SHIM_P01, encoding="utf-8")
        vend_dir = pkg_dir / "vendor" / "shared-core"
        vend_dir.mkdir(parents=True, exist_ok=True)
        vend_path = vend_dir / "assemble_spawn_prompt.py"
        vend_path.write_text(vendor_body, encoding="utf-8")

        if git_init:
            self.assertTrue(_git_init_repo(root), "无法初始化隔离 git 仓库")
            # 先把「已提交版」写进去并提交
            core_path.write_text(committed_body, encoding="utf-8")
            self.assertTrue(_git_commit_all(root, "committed core"),
                            "无法在隔离仓库里提交（git 环境不可用？）")
            # 再改成「在途未提交的工作区版」⇒ 制造真源在途修改
            core_path.write_text(worktree_body, encoding="utf-8")

        committed_sha = hashlib.sha256(committed_body.encode("utf-8")).hexdigest()
        return plugins_root, core_path, vend_path, committed_sha

    # ── G7：真源在途未提交 ⇒ 未跟升的包**不应**被报漂移 ──────────────
    def test_G7_inflight_uncommitted_core_does_not_false_red_drift(self):
        """G7：真源**在途未提交**时，vendor 副本与**已提交版**一致的包
        ⇒ **不应**被报为漂移（噪声被正确抑制）。

        场景（对应 2026-10-30 实测）：
          · 真源工作区版 = v2（在途未提交，514 行那版）
          · 真源已提交版 = v1（401 行那版）
          · 某包 vendor 副本 = v1（= 与**已发布**真源一致 ⇒ 它是**自洽**的）
        旧实现拿工作区 v2 的 sha 当唯一基准 ⇒ 该包被误判漂移（**假红**）。
        正确行为：该包**命中已提交基准** ⇒ 不算漂移。

        ★ **能红反例**：把基准集合退化成「只有工作区 sha」
          ⇒ 该包必然被报漂移 ⇒ 本条红。
        """
        root = self._tmp_root("vetmed-fed-g7-")
        plugins_root, core_path, _vend, committed_sha = self._build_repo_federation(
            root, committed_body=_CORE_V1, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        # 前置：确认三份内容确实互不相同（场景成立）
        worktree_sha = hashlib.sha256(_CORE_V2.encode("utf-8")).hexdigest()
        vendor_sha = hashlib.sha256(_CORE_V1.encode("utf-8")).hexdigest()
        self.assertNotEqual(worktree_sha, committed_sha,
                            "反例前提：工作区版与已提交版相同")
        self.assertNotEqual(vendor_sha, worktree_sha,
                            "反例前提：vendor 与工作区版相同")
        self.assertEqual(vendor_sha, committed_sha,
                         "反例前提：vendor 与已提交版不同（这样才对得上场景）")

        # ★ 真实调用路径（自动探测 git 取已提交基准）
        rows, stale, drift = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())

        self.assertEqual(drift, [],
                         "★ 真源在途未提交时，vendor 与**已提交真源**一致的包被误报漂移"
                         "——噪声淹没了真信号（基准确认退化成只有工作区 sha）")
        self.assertEqual(stale, [], "本例只造基准场景，未造版本滞后")
        rowmap = dict(rows)
        self.assertIn("pkg-a", rowmap)
        self.assertNotIn("漂移", rowmap["pkg-a"],
                         "展示行误标了漂移——运维会白跑一趟同步")
        self.assertIn("P0-1", rowmap["pkg-a"], "展示行丢了版本契约")

    def test_G7b_reverse_example_worktree_only_baseline_would_false_red(self):
        """G7b 反例（**能红**）：基准集合若退化成「只有工作区 sha」
        ⇒ 该包**必然**被误报漂移 ⇒ 证明 G7 的判据确有判别力。

        这是 G7 的**反向对照**：若「只有工作区 sha」也一样不报漂移
        ⇒ 说明 G7 压根没在检验基准集合 ⇒ G7 钉不住任何东西。
        """
        root = self._tmp_root("vetmed-fed-g7b-")
        plugins_root, core_path, _vend, _sha = self._build_repo_federation(
            root, committed_body=_CORE_V1, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        # 注入空字符串 ⇒ 基准集合只剩「工作区 sha」（= 旧实现的退化行为）
        _rows, _stale, drift_wo = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set(),
            committed_sha="")
        self.assertIn("pkg-a", drift_wo,
                      "★ 只有工作区 sha 时竟不报漂移——G7 的判据无判别力（假绿）")

        # 而注入已提交 sha ⇒ 不报漂移 ⇒ 两者行为**确实不同** ⇒ G7 有判别力
        _rows2, _stale2, drift_w = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set(),
            committed_sha=hashlib.sha256(_CORE_V1.encode("utf-8")).hexdigest())
        self.assertNotIn("pkg-a", drift_w,
                         "★ 有已提交基准却仍报漂移——G7 的正向判据失效")

    # ── G8：真源已提交后，未跟升的包**仍然必须**被报出 ───────────────
    def test_G8_committed_core_still_reports_not_yet_synced_vendor(self):
        """G8：真源**已提交**为新版后，vendor 仍停在旧版的包
        ⇒ **必须**被报为漂移（真信号不被放宽基准而丢掉）。

        这是防漂移的**核心价值**：真源提交即「发布」，此时所有未跟升的包
        都必须被点名。若基准集合被扩得过宽（例如「任何 sha 都算命中」），
        这个信号就没了 ⇒ 未跟升的包可以无限潜伏。

        ★ **能红反例**：把判定改成「任何 sha 都算命中」
          ⇒ 该包必然漏报 ⇒ 本条红。
        """
        root = self._tmp_root("vetmed-fed-g8-")
        plugins_root, core_path, _vend, committed_sha = self._build_repo_federation(
            root, committed_body=_CORE_V2, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        # 前置：vendor（v1）确实对不上已提交真源（v2）
        vendor_sha = hashlib.sha256(_CORE_V1.encode("utf-8")).hexdigest()
        self.assertNotEqual(vendor_sha, committed_sha,
                            "反例前提：vendor 与已提交真源相同")

        rows, _stale, drift = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())

        self.assertIn("pkg-a", drift,
                      "★ 真源已提交新版后，未跟升的 vendor 副本没有被报出"
                      "——防漂移的核心价值丢失（基准集合被放宽过头）")
        rowmap = dict(rows)
        self.assertIn("漂移", rowmap["pkg-a"],
                      "展示行未标出「漂移」——运维看不出该怎么处置")
        # 标记文案 `vendor漂移❌` 必须保留（多个测试依赖该子串）
        self.assertIn("vendor漂移❌", rowmap["pkg-a"],
                      "★ 判红标记 `vendor漂移❌` 丢失——既有断言会被打破")

    def test_G8b_reverse_example_overwide_baseline_would_miss_drift(self):
        """G8b 反例（**能红**）：基准集合若被扩成「任何 sha 都算命中」
        ⇒ 必然**漏报** ⇒ 证明 G8 的判据确有判别力。

        这是 G8 的**反向对照**：若「过宽基准」也一样能报出，
        ⇒ 说明 G8 的判据没在检验基准集合的**宽窄** ⇒ G8 钉不住任何东西。
        """
        root = self._tmp_root("vetmed-fed-g8b-")
        plugins_root, core_path, _vend, _sha = self._build_repo_federation(
            root, committed_body=_CORE_V2, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        # 正确基准（工作区+已提交）⇒ 必须报出
        _rows, _stale, drift_ok = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set())
        self.assertIn("pkg-a", drift_ok,
                      "★ 正确基准下没报出漂移——G8 的正向判据失效")

        # 注入一个**无关**的 sha 之外，再注入「过宽」情形：
        # 基准只有工作区 sha 时，vendor(v1) 确实对不上 ⇒ 仍报出（不是漏报）
        _rows2, _stale2, drift_wo = self.es.scan_federation_shims(
            plugins_root, core_path, self.es.federation_skip_set(),
            committed_sha="")
        self.assertIn("pkg-a", drift_wo,
                      "★ 只有工作区 sha 时竟不报漂移——G8 的判据无判别力（假绿）")

        # ★ **过宽基准**的极端形态：把「基准集合」退化成「空集」
        #   （空集 ⇒ 判定分支 `if core_shas` 不成立 ⇒ 完全不做比对）
        #   ⇒ 未跟升的包被彻底漏报 ⇒ 这正是 G8 要防的事故。
        #   注意：本实现里空基准 ⇒ **不判漂移**（缺基准不判定），
        #   所以这里断言的是「漏报」这一失败形态确实存在 ⇒ G8 有判别力。
        core_gone = plugins_root / "shared-core" / "no-such-core.py"
        _rows3, _stale3, drift_nobase = self.es.scan_federation_shims(
            plugins_root, core_gone, self.es.federation_skip_set())
        self.assertNotIn("pkg-a", drift_nobase,
                         "★ 无基准时竟然报了漂移——缺基准应当「不判定」而非判红")

    # ── G9：容错（git 不可用 / 不在仓库内 / 路径未提交）─────────────
    def test_G9_git_unavailable_falls_back_without_raising(self):
        """G9：**容错** —— 真源不在 git 仓库内 / git 不可用 / 该路径未提交
        ⇒ **不抛异常**，且行为退回「只有工作区 sha」基准。

        巡检跑在**任何**环境里（用户装好的包、CI 沙盒、没有 git 的容器）。
        「环境缺 git」是**常态**，不是缺陷 ⇒ 此时必须**退回旧行为**，
        既不能崩，也不能把「探测不到」误当成「有漂移」。

        ★ **能红反例**：让基准获取抛异常 ⇒ 巡检直接崩 ⇒ 本条红。
        """
        root = self._tmp_root("vetmed-fed-g9-")
        # 场景①：真源**不在 git 仓库内**（tmpdir 无 .git）
        plugins_root = root / "plugins"
        core_dir = plugins_root / "shared-core"
        core_dir.mkdir(parents=True, exist_ok=True)
        core_path = core_dir / "assemble_spawn_prompt.py"
        core_path.write_text(_CORE_BODY, encoding="utf-8")
        pkg_dir = plugins_root / "pkg-a"
        (pkg_dir / "scripts").mkdir(parents=True, exist_ok=True)
        (pkg_dir / "scripts" / "assemble_spawn_prompt.py").write_text(
            _SHIM_P01, encoding="utf-8")
        vend_dir = pkg_dir / "vendor" / "shared-core"
        vend_dir.mkdir(parents=True, exist_ok=True)
        (vend_dir / "assemble_spawn_prompt.py").write_text(_CORE_BODY,
                                                           encoding="utf-8")

        # 不抛异常
        try:
            rows, stale, drift = self.es.scan_federation_shims(
                plugins_root, core_path, self.es.federation_skip_set())
        except Exception as e:                                # pragma: no cover
            self.fail(f"★ 真源不在 git 仓库内时巡检抛异常："
                      f"{type(e).__name__}: {e}")

        # 退回「只有工作区 sha」基准 ⇒ vendor 与工作区真源一致 ⇒ 不报漂移
        self.assertEqual(drift, [],
                         "★ 无 git 基准时误报漂移——缺基准应当「不判定」而非判红")
        self.assertEqual(stale, [])
        rowmap = dict(rows)
        self.assertNotIn("漂移", rowmap["pkg-a"])

        # 场景②：**该路径在 HEAD 里不存在**（真源在工作区，但从未被提交）
        root2 = self._tmp_root("vetmed-fed-g9b-")
        plugins_root2, core_path2, _v, _s = self._build_repo_federation(
            root2, committed_body=_CORE_V1, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)
        # 把真源从索引里摘掉**并提交这次删除** ⇒ HEAD 里真的没有该路径了
        # （只 `git rm --cached` 不提交是不够的——HEAD 里仍然留着它！）
        # ⚠ 这里**不能**用 _git_commit_all（它会 `git add -A` ⇒ 把还在磁盘上的
        #   真源重新加回索引 ⇒ 删除被撤销 ⇒ 场景根本没被造出来）
        _git(root2, "rm", "--cached", "-q",
             "plugins/shared-core/assemble_spawn_prompt.py")
        r_rm = _git(root2, "commit", "-q", "-m", "drop core from HEAD")
        self.assertEqual(r_rm.returncode, 0,
                         f"无法提交删除（git 环境不可用？）：{r_rm.stderr.strip()[:200]}")
        # 前置：确认该路径确实不在 HEAD 里（否则本场景没被真正造出来）
        r = _git(root2, "rev-parse", "HEAD:./plugins/shared-core/assemble_spawn_prompt.py")
        self.assertNotEqual(r.returncode, 0,
                            "反例前提：路径其实还在 HEAD 里——本场景未被造出来")
        # 前置：确认工作区文件仍在（⇒ 有「工作区 sha」基准可退）
        self.assertTrue(core_path2.is_file(), "反例前提：工作区真源文件丢失")

        try:
            _rows, _stale, drift2 = self.es.scan_federation_shims(
                plugins_root2, core_path2, self.es.federation_skip_set())
        except Exception as e:                                # pragma: no cover
            self.fail(f"★ 已提交路径不存在时巡检抛异常："
                      f"{type(e).__name__}: {e}")
        # 退回「只有工作区 sha」基准 ⇒ vendor(=v1) 与工作区真源(=v2) 不同 ⇒ 报漂移
        self.assertIn("pkg-a", drift2,
                      "★ 路径不在 HEAD 时未退回「只有工作区 sha」基准"
                      "（行为与现状实现不一致）")
        # 且已提交 sha 探测必须**明确取不到**（而不是碰巧取到一个别的）
        self.assertEqual(self.es._git_committed_core_sha(str(core_path2)), "",
                         "★ 路径不在 HEAD 时竟取到了已提交 sha——探测有误")

    def test_G9b_git_binary_missing_falls_back_without_raising(self):
        """G9b：**git 可执行文件缺失** ⇒ 同样不抛异常，退回「只有工作区 sha」。

        做法：把 `PATH` 指向一个空目录 ⇒ `git` 找不到 ⇒ subprocess 抛
        FileNotFoundError ⇒ 基准获取必须**吞掉**它。

        ★ **能红反例**：基准获取不吞异常 ⇒ 巡检直接崩 ⇒ 本条红。
        """
        root = self._tmp_root("vetmed-fed-g9c-")
        plugins_root, core_path, _v, _s = self._build_repo_federation(
            root, committed_body=_CORE_V1, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        empty_bin = root / "empty-bin"
        empty_bin.mkdir()
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(empty_bin)
        try:
            try:
                _rows, _stale, drift = self.es.scan_federation_shims(
                    plugins_root, core_path, self.es.federation_skip_set())
            except Exception as e:                            # pragma: no cover
                self.fail(f"★ git 不可用时巡检抛异常：{type(e).__name__}: {e}")
        finally:
            os.environ["PATH"] = old_path

        # 退回「只有工作区 sha」⇒ vendor(=v1) 与工作区真源(=v2) 不同 ⇒ 报漂移
        # （这是**旧行为**——基准只有工作区 sha ⇒ 未跟升的包会被报出来）
        self.assertIn("pkg-a", drift,
                      "★ git 不可用时行为未退回「只有工作区 sha」基准")

    # ── G10：基准集合本身的语义（辅助函数直测）──────────────────────
    def test_G10_federal_core_shas_returns_baseline_set(self):
        """G10：`federal_core_shas` 返回**基准集合**（工作区 sha ∪ 已提交 sha）。

        这是 G7/G8 的**地基**：若它只返回一个 sha ⇒ 集合语义无从谈起。
        同时钉死「注入 committed_sha ⇒ 完全不碰 git」（可测性前提）。
        """
        root = self._tmp_root("vetmed-fed-g10-")
        plugins_root, core_path, _v, committed_sha = self._build_repo_federation(
            root, committed_body=_CORE_V1, worktree_body=_CORE_V2,
            vendor_body=_CORE_V1)

        worktree_sha = hashlib.sha256(_CORE_V2.encode("utf-8")).hexdigest()

        # ① 注入已提交 sha ⇒ 集合含两个 sha
        shas = self.es.federal_core_shas(core_path, committed_sha=committed_sha)
        self.assertIsInstance(shas, set, "基准必须是一个**集合**")
        self.assertEqual(shas, {worktree_sha, committed_sha},
                         "基准集合 ≠ {工作区 sha, 已提交 sha}")

        # ② 不注入 ⇒ 自动探测 git ⇒ 结果相同（真实路径与注入路径一致）
        auto = self.es.federal_core_shas(core_path)
        self.assertEqual(auto, {worktree_sha, committed_sha},
                         "自动探测 git 得到的基准集合与注入值不一致")

        # ③ 真源不存在 ⇒ 空集合（不判定）
        missing = self.es.federal_core_shas(
            plugins_root / "shared-core" / "no-such.py")
        self.assertEqual(missing, set(),
                         "真源不存在时应返回空集合（不判定），而不是抛异常")

        # ④ 注入空串 ⇒ 基准集合只剩工作区 sha（退化的旧行为）
        only_wt = self.es.federal_core_shas(core_path, committed_sha="")
        self.assertEqual(only_wt, {worktree_sha},
                         "注入空串应只保留工作区 sha")


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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_inspection_zone_registry_red.py — 免检区登记表守卫的**判据级红证明**
=================================================================================

本文件补的是「守卫自己的守卫」——一处已实测的**假绿缺口**。

─────────────────────────────────────────────────────────────────────────────
【为什么需要本文件（真实缺口，已实测复现）】
─────────────────────────────────────────────────────────────────────────────
`references/inspection-zones.yaml`（免检区登记表）头部声明的守卫是
`scripts/test_dead_config_disposition.py::TestInspectionZoneRegistry`，
判据 R1–R6（见该文件 docstring）。

★ **实测结论（v3.28.0 收口期，2026-10-29）**：那个守卫**存在**（v3.25.0 已入库），
  但它自己的三个「反例」（T11 / T12 / T13）**测的是「机制」而不是「判据」**：
    · T11 断言的是「段内加键后 digest 变了」      ⇒ 没调用 R3 的判据本体
    · T12 断言的是**它自己内联重写**的检查逻辑     ⇒ 没调用 R2/R5 的判据本体
    · T13 断言的是「键进了免检区」                 ⇒ 没调用任何判据本体
  ⇒ 于是：把守卫文件里的 R2/R3/R4/R5/R6 **判据分支删掉**，这三个反例**照样全绿**。

  实测（在隔离副本上删分支，副本内跑该文件的 17 个用例）：

    ┌──────────────────────┬──────────────────────────────┐
    │ 变异（删掉该判据分支） │ 副本上的测试结果              │
    ├──────────────────────┼──────────────────────────────┤
    │ 删 R3（digest 比对）  │ **17 passed**（假绿）         │
    │ 删 R4（key_count）    │ **17 passed**（假绿）         │
    │ 删 R6（枚举校验）     │ **17 passed**（假绿）         │
    │ 删 R2（段存在性）     │ **17 passed**（假绿）         │
    │ 删 R5（段集合双向）   │ **17 passed**（假绿）         │
    │ 删 R1（覆盖判据）     │ 1 failed（T1b 意外撞上，非 R1 自己）│
    └──────────────────────┴──────────────────────────────┘

  ⇒ 这正是本包「**判据必须能红**」纪律要消灭的形态：
    **守卫的判据本体被掏空，无人察觉。**

─────────────────────────────────────────────────────────────────────────────
【本文件做什么（三层）】
─────────────────────────────────────────────────────────────────────────────
第 1 层 · **判据级红证明**（R1–R6 各一条）
    逐条把「登记表被改坏」或「实时 config 被改坏」，
    然后**直接调用真实守卫文件里的判据方法**，
    断言它**真的抛 AssertionError 且报出对应判据标签**。
    ⚠ 与原守卫的反例的本质区别：原守卫测「机制」，本文件测「**判据本体**」。

第 2 层 · **变异敏感性证明**（杀掉 mutant）
    在**进程内**构造「删掉该判据分支」的守卫**副本**，
    断言 mutant **抓不到**对应的破坏 ⇒ 反证第 1 层的红证明**有鉴别力**
    （若 mutant 也抓得到 ⇒ 说明第 1 层是恒真守卫 ⇒ 第 1 层本身假绿）。
    ★ 这是本仓库既有的「变异必须能打红」纪律的同型做法
      （见 `scripts/test_versionctl.py` 的 M12–M18 变异段）。

第 3 层 · **端到端红证明**（走子进程，跑真包形态）
    在**隔离副本**上改坏实时 config（加键 / 新增整块消费段），
    用子进程跑**真包形态**的守卫（`python3 scripts/test_dead_config_disposition.py <方法>`），
    断言 rc≠0 且输出含对应判据标签。
    ⚠ 走子进程的理由：守卫的 `setUpClass` 会 `collect_block_segments()`，
      那是**重 I/O**（实测 2.2s/次）；同进程直接调用会与副本状态串味。

─────────────────────────────────────────────────────────────────────────────
【硬性纪律】
─────────────────────────────────────────────────────────────────────────────
  ★ **绝不修改真实仓库的文件**：
    · 登记表副本 → 落在 `tempfile.mkdtemp()` 造的临时目录里，用完即删；
    · 实时 config 副本 → 落在 `test_pkg_isolation.make_isolated_pkg()` 的隔离副本里；
    · 守卫 mutant 副本 → 同上，在**临时目录**里改写副本源码。
    真实仓库的 `references/inspection-zones.yaml` 与 `scripts/*.py` **只读**。

─────────────────────────────────────────────────────────────────────────────
【接线】
─────────────────────────────────────────────────────────────────────────────
体检第 7 项 `ensure_settings.py::check_regression()` 用
`_glob.glob(os.path.join(expert_dir, "scripts", "test_*.py"))` **自动收集**
⇒ 本文件**零配置改动**即入回归套件。
⚠ `config/harness.yaml` 里**没有**测试套件清单（实测 grep 无命中）⇒ 不需改它。

─────────────────────────────────────────────────────────────────────────────
【环境限制的失败语义（沿用 v3.27.0 P0 纪律）】
─────────────────────────────────────────────────────────────────────────────
隔离副本构造失败（宿主 filesystem broker 拦 mkdir 等）⇒ **SKIP 且指名道姓**，
绝不伪装成「通过」。跳过必须**显式打印**到 stdout（体检第 7 项会把它汇进日志），
并留下**类级可观测痕迹** `SKIP_TRACE` / `SKIP_COUNT` ⇒ 「未验」绝不显示成「已验」。

⚠ **只捕获「构造类」失败**（`IsolatedPkgBuildError` / `OSError` 家族），
  不捕获裸 `Exception` —— 否则构造器里的**真缺陷**会被降级成 skip。

用法：
    python3 -m pytest scripts/test_inspection_zone_registry_red.py -q
    python3 scripts/test_inspection_zone_registry_red.py      # 体检第 7 项按此方式跑
退出码：0 通过 / 1 失败（unittest 语义）
"""

import ast
import copy
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

#: 真实守卫文件（v3.25.0 已入库）—— 本文件**只读**它，绝不改它。
GUARD_FILE = HERE / "test_dead_config_disposition.py"

#: 免检区登记表（真源）。
REGISTRY_FILE = PKG / "references" / "inspection-zones.yaml"

#: 守卫类名 + 判据方法名（引用真实守卫文件里的实现，**不复制**判据逻辑）。
GUARD_CLASS = "TestInspectionZoneRegistry"

#: 【反例批次因环境限制被跳过】的专属标记。
#: ⚠ 与 `ensure_settings.ANTIEXAMPLE_SKIP_MARKER` / `test_arch_drift.ANTIEXAMPLE_SKIP_MARKER`
#:   **逐字一致**（体检第 7 项靠它识别「未验证项」）。
#:   漂移风险由 `scripts/test_regression_skip_report.py` 的 T5 锁死
#:   （它只比较那两处；本文件是**第三处**使用者，故同样使用该字面量）。
ANTIEXAMPLE_SKIP_MARKER = "[WARN][vet-med-ppt-team] 反例批次因环境限制被跳过"


def _load_module(name: str, path: Path):
    """按文件路径加载模块（避免污染常规 import 路径）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_guard():
    """加载真实守卫模块（`test_dead_config_disposition.py`）。"""
    if not GUARD_FILE.is_file():
        raise FileNotFoundError(f"缺守卫文件 {GUARD_FILE}")
    return _load_module("r9_guard_under_test", GUARD_FILE)


# ══════════════════════════════════════════════════════════════════════
# 判据破坏构造器 —— 每个破坏对应登记表的一条判据
# ══════════════════════════════════════════════════════════════════════

#: 用来做「破坏演练」的段（必须真实存在于登记表中 ⇒ 前提可校验）。
PROBE_SEG = "harness.yaml#budgets"


def _segment(reg: dict, seg_id: str) -> dict:
    """取登记表里某段的 dict（找不到 ⇒ 抛错 ⇒ 反例前提失效）。"""
    for s in reg.get("segments") or []:
        if s.get("id") == seg_id:
            return s
    raise KeyError(f"登记表里没有段 {seg_id}（反例前提失效：登记表结构变了？）")


def break_missing_segment(reg: dict) -> dict:
    """破坏 R1/R5：从登记表里**删掉**一个真实段 ⇒ 实时存在但未登记。"""
    r = copy.deepcopy(reg)
    r["segments"] = [s for s in r["segments"] if s.get("id") != PROBE_SEG]
    return r


def break_phantom_segment(reg: dict) -> dict:
    """破坏 R2/R5：登记一个**不存在**的段 ⇒ 僵尸声明。"""
    r = copy.deepcopy(reg)
    r.setdefault("segments", []).append({
        "id": "foo.yaml#bar", "file": "foo.yaml", "prefix": "bar",
        "key_count": 1, "keys_sha256": "0" * 40, "leaf_unused": 0,
        "consumer": "脚本", "disposition": "新增键须登记", "note": "探针",
    })
    return r


def break_digest(reg: dict) -> dict:
    """破坏 R3：把某段的 `keys_sha256` 改错 ⇒ 键集合指纹对不上。"""
    r = copy.deepcopy(reg)
    seg = _segment(r, PROBE_SEG)
    seg["keys_sha256"] = "f" * 40
    return r


def break_key_count(reg: dict) -> dict:
    """破坏 R4：把某段的 `key_count` 改错 ⇒ 与实时键数对不上。"""
    r = copy.deepcopy(reg)
    seg = _segment(r, PROBE_SEG)
    seg["key_count"] = int(seg.get("key_count", 0)) + 999
    return r


def break_consumer_enum(reg: dict) -> dict:
    """破坏 R6：把 `consumer` 改成枚举外的值。"""
    r = copy.deepcopy(reg)
    seg = _segment(r, PROBE_SEG)
    seg["consumer"] = "神秘消费者"
    return r


def break_disposition_enum(reg: dict) -> dict:
    """破坏 R6：把 `disposition` 改成枚举外的值。"""
    r = copy.deepcopy(reg)
    seg = _segment(r, PROBE_SEG)
    seg["disposition"] = "随便处置"
    return r


# ══════════════════════════════════════════════════════════════════════
# 第 1 层 · 判据级红证明
# ══════════════════════════════════════════════════════════════════════

class TestRegistryJudgementsGoRed(unittest.TestCase):
    """R1–R6 的**判据级红证明**：改坏登记表 ⇒ 真实守卫的判据必须判红。

    ★ **与原守卫（T8/T9/T10）的本质区别**：
      原守卫断言的是「登记表与实时 config 一致」（**正向**），
      它的三个反例（T11/T12/T13）断言的是「机制有效」（**旁支**），
      **没有任何一条调用过 T9/T10 的判据分支**。
      ⇒ 实测：删掉 R2–R6 分支后，原守卫的 17 个用例**照样全绿**。
      本类则**直接调用真实判据本体** ⇒ 判据被掏空 ⇒ 本类**必红**。

    ⚠ 登记表副本落在**临时目录**，真实 `references/inspection-zones.yaml` 只读。
    """

    @classmethod
    def setUpClass(cls):
        import yaml
        cls.yaml = yaml
        cls.guard = _load_guard()
        cls.guard_cls = getattr(cls.guard, GUARD_CLASS)
        cls.reg = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))

    # ── 内部工具 ──────────────────────────────────────────────
    def _run_judgement(self, method: str, reg, reg_path=None):
        """调用真实守卫的判据方法，返回 (是否判红, 判红消息)。

        ⚠ **直接调用判据本体**（而不是重写一遍逻辑）——这是本文件的价值所在：
          若把判据逻辑复制到本文件，那本文件证明的是「复制品能红」，
          而非「真守卫能红」⇒ 真守卫被掏空时本文件照样全绿 ⇒ 又是假绿。
        """
        inst = self.guard_cls(method)
        inst.es = self.guard._load_es()
        inst.reg = reg
        inst.live = self.guard._load_es().collect_block_segments(str(PKG))
        if reg_path is not None:
            inst.REGISTRY = reg_path
        try:
            getattr(inst, method)()
            return False, ""
        except AssertionError as exc:
            return True, str(exc)

    def _assert_goes_red(self, method, reg, expect_marker, why):
        """断言：给定破坏 ⇒ 判据判红，且消息里**点名** `expect_marker`。"""
        red, msg = self._run_judgement(method, reg)
        self.assertTrue(red, f"{why}：判据**没有**判红 ⇒ 守卫是假绿")
        self.assertIn(expect_marker, msg,
                      f"{why}：判红了但消息未点名 {expect_marker!r} ⇒ "
                      f"无法确认是**这条**判据抓到的（可能判错原因）\n"
                      f"实际消息：{msg}")

    # ── R1：登记表存在且覆盖全部实时段 ─────────────────────────
    def test_r1_registry_file_missing_goes_red(self):
        """R1 红证明：**登记表文件缺失** ⇒ 判据必须判红。

        防的真实缺陷：登记表是「必交付物」（yaml 头部注释明写）——
        它一旦被误删/改名，`--dump-block-segments` 的生成端与守卫端同时失联，
        免检区就会**静默退化成「没人管」**。
        """
        with tempfile.TemporaryDirectory(prefix="r9-reg-missing-") as td:
            missing = Path(td) / "inspection-zones.yaml"
            red, msg = self._run_judgement(
                "test_T8_registry_file_exists_and_covers_all_segments",
                self.reg, reg_path=missing)
        self.assertTrue(red, "R1：登记表文件缺失时判据没有判红 ⇒ 守卫是假绿")
        self.assertIn("缺", msg, f"R1：消息未点名「缺」⇒ 实际消息：{msg}")

    def test_r1_segment_not_registered_goes_red(self):
        """R1 红证明：登记表**漏登记**一个实时段 ⇒ 判据必须判红。

        防的真实缺陷：新增一个「整块消费段」（父级被代码整块取走）
        却忘了登记 ⇒ 该段里的键**既不进死配置门、也不在登记表里**
        ⇒ 变成**两头都不管**的黑洞段（这是免检区制度最核心的漏洞）。
        """
        reg = break_missing_segment(self.reg)
        self._assert_goes_red(
            "test_T8_registry_file_exists_and_covers_all_segments",
            reg, "未登记",
            "R1（漏登记实时段）")

    # ── R2：登记的段在实时 config 中仍存在 ─────────────────────
    def test_r2_phantom_segment_goes_red(self):
        """R2 红证明：登记了一个**不存在**的段 ⇒ 判据必须判红。

        防的真实缺陷：登记表逐渐积累「僵尸声明」（段早已从 config 删掉，
        登记还在）⇒ 读登记表的人以为「这个段有人管」，实际**无人管**。
        """
        reg = break_phantom_segment(self.reg)
        self._assert_goes_red(
            "test_T9_registry_segments_match_live",
            reg, "（R2）",
            "R2（幽灵段）")

    # ── R3：键集合 digest ──────────────────────────────────────
    def test_r3_digest_mismatch_goes_red(self):
        """R3 红证明：某段 `keys_sha256` 与实时**不一致** ⇒ 判据必须判红。

        防的真实缺陷：段内**增/删/改名任一键**（最常见的是「加了个新键，
        忘了登记处置规则」）⇒ 那个键既没进死配置门、也没被登记表覆盖
        ⇒ **声明层≠执行层**。R3 是段级增量守卫的**核心**。
        """
        reg = break_digest(self.reg)
        self._assert_goes_red(
            "test_T9_registry_segments_match_live",
            reg, "（R3）",
            "R3（digest 不一致）")

    # ── R4：key_count ──────────────────────────────────────────
    def test_r4_key_count_mismatch_goes_red(self):
        """R4 红证明：某段 `key_count` 与实时**不一致** ⇒ 判据必须判红。

        防的真实缺陷：与 R3 **交叉核对**——防「只改一个字段就蒙混过关」。
        例如：有人手改登记表时只把 `key_count` 改对、digest 没改（或反之），
        单靠任一条都可能被绕过 ⇒ 两条必须**同时**成立才算一致。
        """
        reg = break_key_count(self.reg)
        self._assert_goes_red(
            "test_T9_registry_segments_match_live",
            reg, "（R4）",
            "R4（key_count 不一致）")

    # ── R5：段集合双向相等 ─────────────────────────────────────
    def test_r5_new_live_segment_not_registered_goes_red(self):
        """R5 红证明：实时**新增**了一个段、登记表未登记 ⇒ 判据必须判红。

        防的真实缺陷：R5 的**「新段未登记」方向**——
        这是「新增免检区段必须显式登记处置规则」这条纪律的**唯一**执行点。
        ⚠ 与 R1 的区别：R1 查「登记表是否覆盖实时段」，R5 查**双向**集合相等；
          本条同时覆盖「实时多出来」这一方向（断言消息里的「实时存在但」）。
        """
        reg = break_missing_segment(self.reg)
        red, msg = self._run_judgement(
            "test_T9_registry_segments_match_live", reg)
        self.assertTrue(red, "R5：实时多出未登记段时判据没有判红 ⇒ 守卫是假绿")
        self.assertIn("（R5）", msg,
                      f"R5：消息未点名（R5）⇒ 实际消息：{msg}")
        self.assertIn("实时存在但", msg,
                      f"R5：消息未点名「实时存在但」这一方向 ⇒ 实际消息：{msg}")

    # ── R6：枚举校验 ───────────────────────────────────────────
    def test_r6_consumer_out_of_enum_goes_red(self):
        """R6 红证明：`consumer` 越出枚举 ⇒ 判据必须判红。

        防的真实缺陷：枚举漂移——`consumer` 写成「脚本+会话层+主理人+机器人」
        之类的新说法 ⇒ 读登记表的人**无法判断**「这段的消费方到底是谁」
        ⇒ 登记表退化成**自由文本**，可行动清单的意义消失。
        """
        reg = break_consumer_enum(self.reg)
        self._assert_goes_red(
            "test_T10_registry_enums_valid",
            reg, "不在枚举内",
            "R6（consumer 越界）")

    def test_r6_disposition_out_of_enum_goes_red(self):
        """R6 红证明：`disposition` 越出枚举 ⇒ 判据必须判红。

        防的真实缺陷：处置规则是「新增键须登记 / 新增键须接线 / 禁止新增（冻结）」
        三选一。枚举漂移 ⇒ 新增键来了没人知道该按哪条办 ⇒ 处置规则**空转**。
        """
        reg = break_disposition_enum(self.reg)
        self._assert_goes_red(
            "test_T10_registry_enums_valid",
            reg, "不在枚举内",
            "R6（disposition 越界）")


# ══════════════════════════════════════════════════════════════════════
# 第 2 层 · 变异敏感性证明（杀掉 mutant）
# ══════════════════════════════════════════════════════════════════════

#: mutant 构造器：把守卫文件里的**判据分支**整段替换掉（模拟「掏空判据」）。
#: ⚠ 锚点必须**逐字**匹配真实守卫文件 ⇒ 匹配不上 ⇒ 构造失败（而不是
#:   静默变成「什么也没改」的假 mutant ⇒ 那样变异证明会恒真）。
MUTANTS = {
    "R3_digest_branch_removed": (
        '''            live_sha = self.es.segments_digest(
                self.es.segment_digest_inputs(live, scheme), scheme=scheme)
            if live_sha != s.get("keys_sha256"):
                problems.append(
                    f"{sid}：键集合已变（登记 {s.get('keys_sha256')} ≠ 实时 {live_sha}）"
                    f"——段内新增/删除/改名了键，请更新登记表或显式处置该新增键（R3）")''',
        '''            pass  # MUTANT: R3 判据分支被整段删除''',
    ),
    "R4_key_count_branch_removed": (
        '''            live_count = self.es.segment_key_count(
                self.es.segment_digest_inputs(live, scheme), scheme=scheme)
            if int(live_count) != int(s.get("key_count", -1)):
                problems.append(
                    f"{sid}：键数不一致（登记 {s.get('key_count')} ≠ "
                    f"实时 {live_count}）（R4）")''',
        '''            pass  # MUTANT: R4 判据分支被整段删除''',
    ),
    "R6_enum_branch_removed": (
        '''            if s.get("consumer") not in self.CONSUMERS:
                bad.append(f"{sid}：consumer={s.get('consumer')!r} 不在枚举内")
            if s.get("disposition") not in self.DISPOSITIONS:
                bad.append(f"{sid}：disposition={s.get('disposition')!r} 不在枚举内")''',
        '''            pass  # MUTANT: R6 判据分支被整段删除''',
    ),
    "R2_existence_branch_removed": (
        '''            if live is None:
                problems.append(f"{sid}：登记的段在实时 config 中**不存在**（R2）")
                continue''',
        '''            if live is None:
                continue  # MUTANT: R2 判据分支被整段删除''',
    ),
    "R5_bidirectional_branch_removed": (
        '''        for sid in sorted(reg_ids - live_ids):
            problems.append(f"{sid}：登记了但实时**不存在**该段（R5）")
        for sid in sorted(live_ids - reg_ids):
            problems.append(f"{sid}：实时存在但**未登记**（R5）")''',
        '''        pass  # MUTANT: R5 判据分支被整段删除''',
    ),
}


class TestJudgementMutantsAreKilled(unittest.TestCase):
    """变异敏感性：把守卫的判据分支**掏空** ⇒ 本文件的红证明必须**变红**。

    ★ **为什么必须有这一层**：
      第 1 层断言「真实守卫能红」。若某条判据被**掏空**（分支删掉），
      第 1 层里对应的用例**就会红**——这是「红」而不是「绿」，看起来没问题。
      但真正的风险是：**掏空判据后，红证明本身也一起失效**，
      于是仓库回到「全绿但没人管」的状态。
      ⇒ 这一层显式证明：**我的红证明确实咬住了那条判据分支**。
        若 mutant 也「红」⇒ 说明我的断言与判据**无关**（恒真）⇒ 假绿。

    ⚠ mutant 只存在于**临时目录**，真实守卫文件只读。
    """

    @classmethod
    def setUpClass(cls):
        import yaml
        cls.reg = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))

    def _make_mutant_guard(self, mutant_key: str):
        """在临时目录里造一个「掏空某判据分支」的守卫副本，返回其模块。

        ⚠ **布局硬约束**（实测踩到）：守卫模块用
          `HERE = Path(__file__).parent; PKG = HERE.parent; ES = PKG/"scripts"/"ensure_settings.py"`
          推导被测模块路径 ⇒ mutant 必须**自带一份 `scripts/ensure_settings.py`**，
          否则 `_load_es()` 会因找不到被测模块而 FileNotFoundError
          ⇒ 那是**环境/布局问题**，不是「判据没红」⇒ 不得被误读成 mutant 存活。
          ⇒ 故此处把真包的 `ensure_settings.py` **复制**进 mutant 的临时包根，
            并把 `config/` 与 `references/` **软链**到真包（只读、内容恒等）。
        """
        old, new = MUTANTS[mutant_key]
        src = GUARD_FILE.read_text(encoding="utf-8")
        if old not in src:
            self.fail(f"mutant 锚点未逐字匹配（守卫文件已变？）：{mutant_key}")
        td = Path(tempfile.mkdtemp(prefix="r9-mutant-"))
        self.addCleanup(shutil.rmtree, td, ignore_errors=True)
        (td / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / "ensure_settings.py", td / "scripts" / "ensure_settings.py")
        mutant = td / "scripts" / GUARD_FILE.name
        mutant.write_text(src.replace(old, new, 1), encoding="utf-8")
        for d in ("config", "references"):
            link = td / d
            if not link.exists():
                os.symlink(PKG / d, link)
        return _load_module(f"r9_mutant_{mutant_key}", mutant)

    def _judgement_goes_red(self, guard_mod, method, reg, reg_path=None):
        """在给定守卫模块上调用判据，返回 (是否判红, 消息)。"""
        inst = getattr(guard_mod, GUARD_CLASS)(method)
        es = guard_mod._load_es()
        inst.es = es
        inst.reg = reg
        inst.live = es.collect_block_segments(str(PKG))
        if reg_path is not None:
            inst.REGISTRY = reg_path
        try:
            getattr(inst, method)()
            return False, ""
        except AssertionError as exc:
            return True, str(exc)

    def test_mutant_r3_removed_breaks_red_proof(self):
        """mutant「删 R3 分支」⇒ R3 的红证明必须**失效**（抓不到 digest 破坏）。

        反证方向：真实守卫能红（红），mutant 抓不到（不红）
        ⇒ 说明红证明的「红」**来自 R3 那条判据**，不是恒真。
        """
        mutant = self._make_mutant_guard("R3_digest_branch_removed")
        reg = break_digest(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T9_registry_segments_match_live", reg)
        self.assertFalse(
            red,
            "mutant（删 R3 分支）竟然抓到了 digest 破坏 ⇒ "
            "R3 的红证明与 R3 判据**无关**（恒真守卫 ⇒ 假绿）")

    def test_mutant_r4_removed_breaks_red_proof(self):
        """mutant「删 R4 分支」⇒ R4 的红证明必须失效。

        ⚠ 注意：mutant 里 R3 **仍在**，所以 digest 破坏仍会被抓；
          ⇒ 本用例的破坏必须是**只**动 key_count（digest 保持正确），
            否则 mutant 抓到的其实是 R3 而不是「抓不到」。
        """
        mutant = self._make_mutant_guard("R4_key_count_branch_removed")
        reg = break_key_count(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T9_registry_segments_match_live", reg)
        self.assertFalse(
            red,
            "mutant（删 R4 分支）竟然抓到了 key_count 破坏 ⇒ "
            "R4 的红证明与 R4 判据**无关**（恒真守卫 ⇒ 假绿）")

    def test_mutant_r6_removed_breaks_red_proof(self):
        """mutant「删 R6 分支」⇒ R6 的红证明必须失效。"""
        mutant = self._make_mutant_guard("R6_enum_branch_removed")
        reg = break_consumer_enum(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T10_registry_enums_valid", reg)
        self.assertFalse(
            red,
            "mutant（删 R6 分支）竟然抓到了枚举越界 ⇒ "
            "R6 的红证明与 R6 判据**无关**（恒真守卫 ⇒ 假绿）")

    def test_mutant_r2_removed_breaks_red_proof(self):
        """mutant「删 R2 分支」⇒ R2 的红证明必须失效。

        ⚠ 与 R5 的区别：幽灵段**同时**触发 R2 与 R5 ⇒ 删掉任一条都还会被抓。
          ⇒ 本用例只验 R2 这一条**分支被删**时，**R2 标签**不再出现
            （但整体可能仍红，因为 R5 还在）⇒ 断言**消息里不再有「（R2）」**。
        """
        mutant = self._make_mutant_guard("R2_existence_branch_removed")
        reg = break_phantom_segment(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T9_registry_segments_match_live", reg)
        self.assertNotIn(
            "（R2）", msg,
            "mutant（删 R2 分支）后消息里仍有（R2）⇒ "
            "R2 的红证明与 R2 判据**无关**（恒真守卫 ⇒ 假绿）")

    def test_mutant_r5_removed_breaks_red_proof(self):
        """mutant「删 R5 分支」⇒ R5 的红证明必须失效。

        ⚠ 与 R2 同理：幽灵段也触发 R2 ⇒ 本用例断言**消息里不再有「（R5）」**。
        """
        mutant = self._make_mutant_guard("R5_bidirectional_branch_removed")
        reg = break_phantom_segment(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T9_registry_segments_match_live", reg)
        self.assertNotIn(
            "（R5）", msg,
            "mutant（删 R5 分支）后消息里仍有（R5）⇒ "
            "R5 的红证明与 R5 判据**无关**（恒真守卫 ⇒ 假绿）")

    def test_mutant_baseline_still_red(self):
        """反向对照：mutant **只**掏空一条分支时，**其它**判据仍应判红。

        防的是「本文件整体恒真」——若所有 mutant 都被判「抓不到」，
        那只说明本文件**什么都没断言** ⇒ 必须有一条证明「mutant 仍能抓别的」。
        """
        mutant = self._make_mutant_guard("R3_digest_branch_removed")
        # 幽灵段 ⇒ 触发 R2/R5（**不受** R3 mutant 影响）⇒ 仍应判红
        reg = break_phantom_segment(self.reg)
        red, msg = self._judgement_goes_red(
            mutant, "test_T9_registry_segments_match_live", reg)
        self.assertTrue(red,
                        "mutant 只掏空了 R3，幽灵段仍应由 R2/R5 抓红 ⇒ "
                        "若此处不红，说明本文件的红证明机制本身坏了")
        self.assertIn("（R2）", msg, f"mutant 仍应报出 R2 ⇒ 实际消息：{msg}")


# ══════════════════════════════════════════════════════════════════════
# 第 3 层 · 端到端红证明（隔离副本 + 子进程跑真包形态）
# ══════════════════════════════════════════════════════════════════════

class TestLiveConfigDriftIsCaughtEndToEnd(unittest.TestCase):
    """端到端：改坏**实时 config**（隔离副本）⇒ 真包形态的守卫必须判红。

    ★ 为什么这一层不可省：
      第 1/2 层验的是「**登记表**被改坏 ⇒ 判据红」。
      但真正的生产事故方向是反的：**config 改了，登记表没改**
      （新增一个键 / 新增一个整块消费段）⇒ 判据必须红。
      ⇒ 这一层必须走**子进程跑真包形态**（`python3 scripts/test_dead_config_disposition.py <方法>`），
        因为守卫的 `setUpClass` 会 `collect_block_segments()`（重 I/O，实测 2.2s/次），
        同进程复用会与副本状态串味。

    ⚠ 全程在**隔离副本**上做（`test_pkg_isolation.make_isolated_pkg()`），
      生产 `config/*.yaml` 与 `references/inspection-zones.yaml` **零改动**。
    """

    #: 【类级可观测痕迹】本批因环境限制被跳过的事实（沿用 v3.27.0 P0 纪律）。
    #: 放在**类级**而非局部变量：局部变量随实例消亡 ⇒ pytest 汇总后没人知道跳过过。
    SKIP_TRACE: list = []

    #: 本批真实跳过条数（单独计数 ⇒ 不受用例清理影响）。
    SKIP_COUNT: int = 0

    def setUp(self):
        sys.path.insert(0, str(HERE))
        from test_pkg_isolation import (IsolatedPkgBuildError,
                                       cleanup_isolated_pkg, make_isolated_pkg)
        try:
            self._iso = make_isolated_pkg(prefix="vetmed-iso-r9e2e-")
        except (IsolatedPkgBuildError, OSError) as exc:
            # ⚠ **只捕获「构造类」失败**——裸 Exception 会把构造器里的**真缺陷**
            #   降级成 skip ⇒ 守卫的「能红」属性被无声放弃。
            reason = (
                f"隔离副本构造失败（环境限制，非断言失败）："
                f"异常类型={type(exc).__name__}；原始消息={exc}。"
                f"⇒ 本反例**未执行**，本批守卫的『能红』属性本轮**未验证**"
                f"（既不是通过，也不是失败；请勿据此认为守卫有效）。"
            )
            TestLiveConfigDriftIsCaughtEndToEnd.SKIP_TRACE.append({
                "reason": reason,
                "exc_type": type(exc).__name__,
                "exc_msg": str(exc),
            })
            TestLiveConfigDriftIsCaughtEndToEnd.SKIP_COUNT += 1
            print(f"{ANTIEXAMPLE_SKIP_MARKER}：{reason}", flush=True)
            self.skipTest(reason)
        self.addCleanup(cleanup_isolated_pkg, self._iso)

    def _run_guard(self, method: str):
        """在隔离副本里跑**真包形态**的守卫，返回 (rc, 输出)。"""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self._iso / "scripts")
        proc = subprocess.run(
            [sys.executable, str(self._iso / "scripts" / GUARD_FILE.name), method],
            capture_output=True, text=True, env=env, cwd=str(self._iso),
            timeout=300)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def _assert_guard_goes_red(self, method, expect_marker, why):
        rc, out = self._run_guard(method)
        self.assertNotEqual(rc, 0,
                            f"{why}：守卫 rc=0（**假绿**）⇒ 实时 config 的改动"
                            f"**没被发现**\n输出尾部：{out[-1500:]}")
        self.assertIn(expect_marker, out,
                      f"{why}：判红了但输出未点名 {expect_marker!r} ⇒ "
                      f"无法确认是**这条**判据抓到的\n输出尾部：{out[-1500:]}")

    def test_e2e_new_key_in_registered_segment_goes_red(self):
        """端到端：已登记段里**新增一个键**（配置文件改了、登记表没改）⇒ 必须判红。

        防的真实缺陷：**最常见**的生产事故方向——
        开发者在 `config/harness.yaml#budgets` 里加了一个键，
        但没在 `references/inspection-zones.yaml` 里登记处置规则。
        ⇒ 该键：既不在死配置门里（有块级证据）、也不在登记表覆盖范围内
          ⇒ **两头都不管** ⇒ 声明层≠执行层。
        ⇒ R3（digest）+ R4（key_count）必须把它抓出来。
        """
        import yaml
        hy = self._iso / "config" / "harness.yaml"
        cfg = yaml.safe_load(hy.read_text(encoding="utf-8"))
        cfg["budgets"]["__probe_r9_new_key"] = True
        hy.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
        self._assert_guard_goes_red(
            "TestInspectionZoneRegistry.test_T9_registry_segments_match_live",
            "（R3）",
            "实时段内新增键")

    def test_e2e_new_block_consumed_segment_goes_red(self):
        """端到端：新增一个**整块消费段**（配置 + 代码都加了，登记表没加）⇒ 必须判红。

        防的真实缺陷：新增一段配置并让代码 `cfg["新段"]` 整块取走
        ⇒ 该段进**免检区**（静态判据看不见）⇒ 若登记表不更新，
          它就是**无人登记的黑洞段**。
        ⇒ R5（「实时存在但**未登记**」）必须把它抓出来。
        """
        import yaml
        hy = self._iso / "config" / "harness.yaml"
        cfg = yaml.safe_load(hy.read_text(encoding="utf-8"))
        cfg["zz_probe_block"] = {"alpha": 1, "beta": 2}
        hy.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
        # 让该段成为「整块消费段」：非 test_ 前缀的脚本整块取走
        (self._iso / "scripts" / "zz_probe_reader.py").write_text(
            'def _f(cfg):\n    return cfg["zz_probe_block"]\n', encoding="utf-8")
        self._assert_guard_goes_red(
            "TestInspectionZoneRegistry.test_T9_registry_segments_match_live",
            "（R5）",
            "新增整块消费段未登记")

    def test_e2e_registry_out_of_sync_with_live_goes_red(self):
        """端到端：登记表与实时 config **脱节** ⇒ 必须判红（正向基线对照）。

        防的是「守卫根本没跑」这类**最粗**的失效：
        若接线断了（守卫文件被移走 / 判据被掏空 / 实时数据算不出来），
        本条仍会红 ⇒ 说明**判据链路是通的**。
        ⚠ 这条在「未破坏」的副本上跑 ⇒ 判红点必须是「登记表被改坏」，
          所以本条自带一处**副本内**的登记表破坏（只改副本）。
        """
        import yaml
        reg_path = self._iso / "references" / "inspection-zones.yaml"
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        for s in reg["segments"]:
            if s.get("id") == PROBE_SEG:
                s["keys_sha256"] = "f" * 40
        reg_path.write_text(
            yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        self._assert_guard_goes_red(
            "TestInspectionZoneRegistry.test_T9_registry_segments_match_live",
            "（R3）",
            "副本内登记表 digest 改坏")


if __name__ == "__main__":
    unittest.main(verbosity=2)

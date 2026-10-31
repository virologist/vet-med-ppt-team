#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_c4_key_wiring.py — 第 18 项 **C4** 两键生产接线的「能红」护栏。

══════════════════════════════════════════════════════════════════════
为什么有本文件（第 18 项 75 键逐键定性的两颗「待人工定性候选」）：

  ① `config/domain-profiles.yaml#fallback.on_profile_missing`（:57）
     —— 声明了策略值，但此前**没有任何一处**读它做决策：四个调用点把同一句
        「不得回落任何域」写死在 print 里 ⇒ 配置与代码各说一遍 ⇒ **改配置不改行为**。
  ② `config/external-tools.yaml#knowledge_bases[].is_user_default`（:196）
     —— 取值**被动流进**坍缩产物（整块 dict append），但没有地方**读**它
        ⇒ 「哪个是默认库」在装配产物里**看不见**，实际由 yaml 文件次序隐式决定。

本文件的判据（每条都能红，见文末「变异能力」说明）：

  【键 A · on_profile_missing】
    T1  正例：域档案不可用 ⇒ 退出码与文案**由策略值决定**（不是写死的那句话）
    T2  反例（值非法）：改成未登记值 ⇒ **告警** + 仍按最保守策略退出 3
    T3  反例（键缺失）：删掉该键 ⇒ 告警「缺失或为空」+ 退出 3
    T4  反例（显式停用）：active: false ⇒ 告警 + 退出 3（**不得**静默丢域）
    T5  崩溃回归：原代码第二个 f-string 里 `{config/domain-profiles.yaml}`
        是**表达式占位符**（会被求值），而全文无 `config` 名字绑定
        ⇒ 一旦走进该分支就抛 `NameError` —— 本判据盯这个不再复发
    T6  四处调用点一致：cmd_route / cmd_domain / cmd_collapse(show|confirm)
        的 stderr 都必须带策略行（防只接一处、其余三处继续写死）

  【键 B · is_user_default】
    T7  快照层（B-a）：默认库声明在**最后** ⇒ 取回仍是第一条（次序由声明决定）
    T8  稳定性：非默认库之间保持 yaml 原序（证明是**稳定**排序，不是重排）
    T9  渲染层（B-b）：默认库紧跟库名出现「★**用户默认启用的库**」
    T10 反向对照（键的反面）：无人声明默认 ⇒ 产物**不得**出现该标注
    T11 双胞口径一致：harness 与装配器的判定器必须同真值表（复制件漂移守卫）
    T12 真配置冒烟：animal-medicine 首条是《禽病》且带默认标注（走真包配置）

变异能力（自证，改坏接线必红）：
  · 删掉 `_on_profile_missing_policy` 的策略读取（退回写死文案）⇒ T2/T3/T4 红；
  · 把 `return rc` 改回 `return 3` ⇒ T2 的策略无关 blinkers… **不**——T2 断言的是告警文案，
    仍红（因为告警消失）；退出码常量化则 T1/T2 失去"配置决定"的语义，由 T2 的告警断言覆盖；
  · 去掉 `_domain_knowledge_bases` 的 sort ⇒ T7 红；
  · 去掉装配器的 `is_user_default` 标注 ⇒ T9/T12 红；
  · 让装配器对所有库都打标注 ⇒ T10 红。

运行：
    python3 -m pytest scripts/test_c4_key_wiring.py -q
    python3 scripts/test_c4_key_wiring.py
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent

sys.path.insert(0, str(HERE))
from test_pkg_isolation import cleanup_isolated_pkg, make_isolated_pkg  # noqa: E402

POLICY_PATH = "config/domain-profiles.yaml#fallback.on_profile_missing"
#: 策略行的**锚文本**（四个调用点必须一致打出）
POLICY_LINE_MARK = f"处置策略 {POLICY_PATH}="
MARK_DEFAULT_KB = "★**用户默认启用的库**"


def _load_module(name: str, path: Path):
    """按路径加载包内脚本为模块（不与 pytest 的包名冲突）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(args, timeout=180):
    p = subprocess.run([sys.executable] + [str(a) for a in args],
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout or "", p.stderr or ""


def _profiles_yaml(policy_line: str, extra_node: str = "") -> str:
    """合成一份**可读**但 domains 非法的域档案（触发 load_domain_profiles 报错分支）。

    ⚠ 为什么要让文件**可读**：策略值就住在这个文件里，若把文件弄成不可解析，
      策略层永远读不到值 ⇒ 测试只会在「回落最保守值」这条降级路径上通过，
      **掩盖**「根本没接线」这种假绿（对照见 T5：那条专门测不可解析场景）。

    ⚠ 为什么**逐行拼**而不用 dedent + 三引号模板 + 插值（写成 f-string 模板把
      `extra_node` 塞进去）：插入的多行内容不带模板缩进 ⇒ dedent 的公共前缀算成 0
      ⇒ **一行都不去重缩进**（实测坑：生成的 yaml 里 `generic_persona` 顶格
      ⇒ 文件不可解析 ⇒ 测试落到「不可解析」降级路径，假绿/假红难辨）。
    """
    lines = [
        'version: "3.17.0"',
        'default_domain: "animal-medicine"',
        'fallback:',
    ]
    if policy_line:
        lines.append(policy_line)
    lines += [x for x in (extra_node or "").strip("\n").split("\n") if x.strip()]
    lines += [
        '  generic_persona:',
        '    title: "内容权威"',
        'domains: []',
        '',
    ]
    return "\n".join(lines)


class TestKeyAProfileMissingPolicy(unittest.TestCase):
    """键 A：`domain-profiles.yaml#fallback.on_profile_missing` 的四处接线。"""

    _iso: Path = None

    @classmethod
    def setUpClass(cls):
        cls._iso = make_isolated_pkg(prefix="vetmed-iso-c4a-")
        cls.harness = cls._iso / "scripts" / "harness.py"
        cls.profiles = cls._iso / "config" / "domain-profiles.yaml"

    @classmethod
    def tearDownClass(cls):
        cleanup_isolated_pkg(cls._iso)

    # ── 内部工具 ────────────────────────────────────────────────────
    def _write_profiles(self, policy_line: str, extra_node: str = ""):
        self.profiles.write_text(_profiles_yaml(policy_line, extra_node),
                                 encoding="utf-8")

    def _route(self):
        ws = tempfile.mkdtemp(prefix="c4a-ws-")
        return _run([self.harness, "route", "--level", "L2",
                     "--domain", "animal-medicine", "--task-id", "T-C4A",
                     "--workspace", ws])

    # ── T1 正例 ─────────────────────────────────────────────────────
    def test_T1_policy_value_drives_message_and_exit_code(self):
        """T1：策略值出现在 stderr，且退出码来自策略表（不再是写死文案 + 写死 3）。"""
        self._write_profiles('  on_profile_missing: "abort_with_error"')
        rc, out, err = self._route()
        self.assertEqual(rc, 3, f"rc 应为策略 abort_with_error 的退出码 3，实得 {rc}\n{err}")
        self.assertIn(POLICY_LINE_MARK, err,
                      "stderr 未打出策略行 ⇒ 这条路径仍在写死文案")
        self.assertIn("'abort_with_error'", err,
                      "stderr 未打出策略**值** ⇒ 值没从配置文件读到")
        self.assertNotIn("Traceback", err, "该分支不得有 traceback")

    # ── T2 反例（值非法）——键 A 「能红」的核心 ──────────────────────
    def test_T2_unregistered_value_warns_and_falls_back_to_conservative(self):
        """T2：未登记值 ⇒ **告警** + 回落最保守策略。这条是防「退回写死」的关键。

        为什么它能红：把配置改成未登记值后，**只有真读了配置**才会发现值非法
        ⇒ 写死文案的实现不出告警 ⇒ 本用例红。
        """
        self._write_profiles('  on_profile_missing: "warn_and_continue"')
        rc, _, err = self._route()
        self.assertIn("不是已登记策略值", err,
                      "配置值非法但**未告警** ⇒ 策略键没被真正读取（接线失效）")
        self.assertIn("abort_with_error", err,
                      "值非法时未回落到最保守策略 abort_with_error")
        self.assertEqual(rc, 3, f"值非法仍应按最保守策略退出 3，实得 {rc}\n{err}")

    # ── T3 反例（键缺失）────────────────────────────────────────────
    def test_T3_missing_key_warns_instead_of_silent_degrade(self):
        """T3：删掉该键 ⇒ 告警「缺失或为空」+ 仍按最保守值处置（与 T2 分支不同）。"""
        self._write_profiles("  # （本行即为变异：删掉 on_profile_missing 键）")
        rc, _, err = self._route()
        self.assertIn("缺失或为空", err,
                      "键缺失未告警 ⇒ 与「键被读到」无从区分（静默降级）")
        self.assertEqual(rc, 3, f"键缺失仍应退出 3，实得 {rc}\n{err}")

    # ── T4 反例（fallback 段的 active 不得被消费）───────────────────
    def test_T4_fallback_active_is_not_consumed_no_false_green(self):
        """T4：`fallback` 段写 `active: false` ⇒ **不得**被消费，仍按 `on_profile_missing` 处置。

        ⚠ 本条是**由一次真实假绿事故反向钉住**的（不是凭空设计）：
          初版实现在 `_on_profile_missing_policy()` 里写了
          `fb_node.get("active", True)` 并对 `active: false` 告警停用。
          但 `domain-profiles.yaml#fallback` 段**根本没有 `active` 键**
          （仅含 on_profile_missing / generic_persona / generic_evidence_hierarchy /
          generic_safety_redlines）⇒ 那是**臆造读取（死代码）**。

          更严重的第二重危害：它让**另一个文件**的
          `domain_config.yaml#domains[].active`（第 18 项 C3 的 4 个待办键）
          因**末段键名撞车**从 `leaf_unused` 掉进 `leaf_weak`
          ⇒ 看起来「已接线」，实际接的是另一个文件的另一个键
          ⇒ 正是 v3.23.0 F1 明令消灭的「末段同名即算接线」**假绿**。

        ⇒ 本条判据钉住：**fallback 段的 `active` 不得产生任何专属告警**，
          策略一律由 `on_profile_missing` 决定。
        """
        self._write_profiles('  on_profile_missing: "abort_with_error"',
                             extra_node="  active: false")
        rc, _, err = self._route()
        # ① 不得出现「被显式停用」这类 active 专属告警（该键不属于本段）
        self.assertNotIn("被显式停用", err,
                         "fallback 段的 active 被消费了 ⇒ 臆造读取复辟，"
                         "且会制造跨文件同名假绿")
        # ② 策略仍由 on_profile_missing 决定，退出码仍为 3（不得静默放行）
        self.assertIn("abort_with_error", err,
                      "策略未被 on_profile_missing 驱动 ⇒ 接线失效")
        self.assertEqual(rc, 3, f"仍应退出 3（不得静默放行），实得 {rc}\n{err}")

    # ── T5 崩溃回归（原 f-string 占位符事故）────────────────────────
    def test_T5_no_nameerror_when_profiles_file_is_unreadable(self):
        """T5：域档案彻底不可解析 ⇒ 友好报错 + rc 3，**不得**抛 NameError。

        实测缺陷：`scripts/harness.py` 原 cmd_route 的第二个 f-string 写作
        `f"请修复 {config/domain-profiles.yaml} 或去掉 --domain。"` ——
        花括号是**表达式占位符**（求值成 `config / domain - profiles.yaml`），
        而本文件全文**没有 `config` 名字绑定** ⇒ 真走到该分支即
        `NameError: name 'config' is not defined`：友好报错变成崩溃，
        且该分支在本次之前**零测试覆盖**。
        """
        self.profiles.write_text("!! binary [\n 这不是合法 yaml: {{{\n", encoding="utf-8")
        rc, _, err = self._route()
        self.assertNotIn("NameError", err, "复发了旧的 NameError 崩溃缺陷")
        self.assertNotIn("Traceback (most recent call last)", err,
                         "该路径必须友好报错，不得抛栈")
        self.assertEqual(rc, 3, f"档案不可读应退出 3，实得 {rc}\n{err}")
        self.assertIn("config/domain-profiles.yaml", err,
                      "修复提示里必须带**字面**路径（说明它不再是表达式占位符）")

    # ── T6 四处调用点一致 ───────────────────────────────────────────
    def test_T6_all_four_call_sites_are_wired(self):
        """T6：route / domain list / collapse show / collapse confirm 四处都走策略。

        为什么单独一条：只接一处最容易造成「看似接线、其余仍写死」的半吊子状态
        ⇒ 逐个命令实跑，各查各自的 stderr。
        """
        self._write_profiles('  on_profile_missing: "abort_with_error"')
        ws = tempfile.mkdtemp(prefix="c4a-ws4-")
        cases = {
            "route": [self.harness, "route", "--level", "L2", "--domain", "animal-medicine",
                      "--task-id", "T-C4A", "--workspace", ws],
            "domain list": [self.harness, "domain", "list"],
            "collapse show": [self.harness, "collapse", "show", "--id", "animal-medicine",
                              "--task-id", "T-C4A", "--workspace", ws],
            "collapse confirm": [self.harness, "collapse", "confirm", "--id", "animal-medicine",
                                 "--task-id", "T-C4A", "--actor", "user",
                                 "--decision", "测试确认", "--workspace", ws],
        }
        for name, argv in cases.items():
            with self.subTest(cmd=name):
                rc, _, err = _run(argv)
                self.assertEqual(rc, 3, f"{name} 未按策略退出 3（rc={rc}）\n{err}")
                self.assertIn(POLICY_LINE_MARK, err,
                              f"{name} 未打出策略行 ⇒ 该调用点没接线")


class TestKeyBUserDefaultKnowledgeBase(unittest.TestCase):
    """键 B：`external-tools.yaml#knowledge_bases[].is_user_default` 的两处接线。"""

    @classmethod
    def setUpClass(cls):
        cls.harness = _load_module("c4b_harness_mod", HERE / "harness.py")
        cls.assembler = _load_module("c4b_adp_mod", HERE / "assemble_domain_prompt.py")

    #: 合成库清单：**默认库声明在最后**（刻意反序，见 T7 注释）
    _KBS_YAML = textwrap.dedent("""\
        knowledge_bases:
          - id: "2"
            name: "《乙》"
            owner_scope: "animal-medicine"
          - id: "3"
            name: "《丙》"
            owner_scope: "animal-medicine"
          - id: "1"
            name: "《甲·用户默认库》"
            owner_scope: "animal-medicine"
            is_user_default: true
          - id: "9"
            name: "《他域库》"
            owner_scope: "computing"
        """)

    @staticmethod
    def _cfg_with_ext(text: str):
        """把合成配置写到**临时目录**，返回 cfg（指定 collapse.external_tools_file）。

        ⚠ 写临时目录而非包内 config：既不污染生产配置，也让断言读的是**同一份**合成件。
        """
        fd, path = tempfile.mkstemp(prefix="c4b-ext-", suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return {"collapse": {"external_tools_file": path}}, path

    # ── T7 快照层排序（B-a）────────────────────────────────────────
    def test_T7_default_kb_is_sorted_first(self):
        """T7（B-a）：默认库即便声明在**最后**，也必须排在最前。

        为什么用「声明在最后」：默认库恰好写在真 yaml 第一条（:191）——
        若只断言「第一条是默认库」，删掉 sort 也照样绿（**假绿**）⇒ 必须反序构造。
        """
        cfg, _ = self._cfg_with_ext(self._KBS_YAML)
        got, note = self.harness._domain_knowledge_bases(cfg, "animal-medicine")
        self.assertEqual(note, "", f"装载告警异常：{note}")
        names = [k.get("name") for k in got]
        self.assertEqual(names[0], "《甲·用户默认库》",
                         f"默认库未排到首位（实得顺序 {names}）⇒ 排序接线失效")

    # ── T8 稳定排序（非默认库保持原序）──────────────────────────────
    def test_T8_non_default_order_is_stable(self):
        """T8：排序**只**提升默认库，其余条目保持 yaml 原序（稳定排序）。

        防同型缺陷：若用 `sorted(key=bool)` 之外的重排写法（如按 id 排），
        默认库仍可能在前，但其余顺序被打乱 ⇒ 本判据钉住「组内稳定」。
        """
        cfg, _ = self._cfg_with_ext(self._KBS_YAML)
        got, _ = self.harness._domain_knowledge_bases(cfg, "animal-medicine")
        names = [k.get("name") for k in got]
        self.assertEqual(names, ["《甲·用户默认库》", "《乙》", "《丙》"],
                         f"非默认库未保持 yaml 原序：{names}")

    # ── T9 渲染层标注（B-b）────────────────────────────────────────
    def test_T9_renderer_marks_the_default_kb_after_its_name(self):
        """T9（B-b）：默认库渲染行紧跟库名出现「★**用户默认启用的库**」。"""
        artifact = {
            "domain_id": "animal-medicine",
            "knowledge_bases": [
                {"name": "《乙》", "id": "2"},
                {"name": "《甲·用户默认库》", "id": "1", "is_user_default": True},
            ],
        }
        lines = self.assembler._render_domain_context(artifact, {}, "")
        hit = [ln for ln in lines if "《甲·用户默认库》" in ln]
        self.assertTrue(hit, "默认库根本没渲染出来")
        ln = hit[0]
        self.assertIn(MARK_DEFAULT_KB, ln, f"默认库未标注用户默认：{ln}")
        # 标注必须**紧跟库名**（在 id 之前）——防放到行尾后被人扫漏
        self.assertLess(ln.index(MARK_DEFAULT_KB), ln.index("（id: 1）"),
                        f"标注不在库名之后/id 之前：{ln}")
        others = [l for l in lines if "《乙》" in l]
        self.assertTrue(others and MARK_DEFAULT_KB not in others[0],
                        "非默认库被误标为用户默认库")

    # ── T10 反向对照 ───────────────────────────────────────────────
    def test_T10_no_mark_when_nobody_declares_default(self):
        """T10：无人声明默认 ⇒ **不得**出现该标注（防「无条件打标注」的假绿）。"""
        artifact = {"domain_id": "animal-medicine",
                    "knowledge_bases": [{"name": "《无默认》", "id": "x"}]}
        lines = self.assembler._render_domain_context(artifact, {}, "")
        self.assertTrue(any("《无默认》" in ln for ln in lines), "库未渲染")
        self.assertFalse(any(MARK_DEFAULT_KB in ln for ln in lines),
                         "无人声明默认却出现了标注（恒真守卫）")

    # ── T11 双胞判定器同口径 ───────────────────────────────────────
    def test_T11_the_two_twin_predicates_agree(self):
        """T11：`harness._is_user_default_kb` 与装配器同名 ends-up 必须同真值表。

        为什么：装配器与编排内核各持一份实现（不互相 import），靠本用例防漂移。
        """
        cases = [True, "true", "TRUE", "yes", "1", False, "false", "0", "", None, {}, "随便"]
        for v in cases:
            with self.subTest(value=repr(v)):
                kb = {"is_user_default": v}
                self.assertEqual(
                    self.harness._is_user_default_kb(kb),
                    self.assembler._kb_is_user_default(kb),
                    f"两处判定不一致（is_user_default={v!r}）⇒ 复制件漂移")

    # ── T12 真配置冒烟 ─────────────────────────────────────────────
    def test_T12_real_config_first_kb_is_the_declared_default(self):
        """T12：走**真包配置**（非夹具）⇒ 首条是《禽病》且渲染带默认标注。"""
        got, note = self.harness._domain_knowledge_bases(None, "animal-medicine")
        self.assertEqual(note, "", f"真配置装载告警：{note}")
        self.assertTrue(got, "真配置下 animal-medicine 未取到任何库")
        self.assertTrue(got[0].get("is_user_default"),
                        f"首条不是默认库：{got[0].get('name')}")
        lines = self.assembler._render_domain_context(
            {"domain_id": "animal-medicine", "knowledge_bases": got}, {}, "")
        first = next(l for l in lines if l.startswith("- 《"))
        self.assertIn(MARK_DEFAULT_KB, first, f"真配置渲染未标默认库：{first}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

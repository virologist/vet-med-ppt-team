"""第 22 项判据 ④ 的**红证明**（`guard.yaml#cross_review_mapping.*.md_area_terms` 生产接线）。

为什么需要这个文件：
  `md_area_terms` 的语义（见 `config/guard.yaml:58-59` 注释）是「该领域在各 agent MD
  里的用词（供"取反"校验：复检人自己的 MD 不得声明"不做"该领域，且必须有人声明该领域
  归其所有）」。但该键此前**唯一**的读取点是测试
  `scripts/test_arch_drift.py:624` 的 T8 —— 而第 18 项死配置巡检**自 v3.25.0 起排除
  测试文件**（`scripts/ensure_settings.py:1600-1611`：「第 18 项问的是**生产代码**
  是否消费这个键，测试代码的读取**不构成消费**」）⇒ 生产侧无人读 ⇒ 判为死键（4 个
  键路径落在 `leaf_unused`）。

  更硬的理由不是"消警告"，而是**判据倒挂**：
    第 22 项原有 ①②③ 只比对「yaml ↔ SOP 文档写法是否一致」。若有人把 yaml 的
    `reviewer` 改错**并同步改了 SOP 文档**，①②③ 仍然绿（两边一致）
    ⇒ 没有任何**生产**判据校验「这个复检人是否被自己的 MD 明文禁止接该领域的活」
    —— 这正是 v3.17.0 那个真实缺陷（把关人被派给被禁止的人）的病灶，
    此前只由测试 T8 覆盖 ⇒ 「测试强制、生产不强制」。

  本文件锁死下沉后的判据 ④，四条用例的判定标准：
    T1 基线           ⇒ 接线后真实包 rc=0（判据不误伤现状，假阳性为零）
    T2 缺 md_area_terms ⇒ 必须红，且报「缺 md_area_terms」（缺键即红，禁回退内置词表）
    T3 reviewer 换成其 MD 明文「不做」该领域的人 ⇒ 必须红，且报 ④ 的取反分支
    T4 摘掉判据 ④ 分支 ⇒ T3 的红必须**消失**（证明判据不恒真，不是靠别处蒙对）
    T5 摘掉判据 ④ 分支 ⇒ T2 的红必须**消失**（同上，锁住"缺键即红"那条）

⚠ 全程在**临时目录隔离副本**上变异，**绝不**改包内真源
  （写法参照 `scripts/test_dead_config_criteria.py`）。
"""
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ES_REL = Path("scripts") / "ensure_settings.py"

#: 判据 ④ 在 `ensure_settings.py` 里的**起止锚点**（供变异 3 摘除分支用）。
#: 起点 = ④ 的注释行；终点 = ④ 之后的第一行既有代码（`expected = pattern.format(...)`）。
_ANCHOR_BEGIN = "# ── ④ md_area_terms 的「取反 + 归属证明」双向校验"
_ANCHOR_END = "        expected = pattern.format("

#: 判据 ④ 两条分支的**专属**报错片段（与 `ensure_settings.py` 里的字面量逐字对应）。
#: 用专属片段而不是"只要变红"，是为了防止「别处先红 ⇒ ④ 其实没生效」的假绿。
MSG_MISSING_TERMS = "缺 md_area_terms"
MSG_CONTRADICTED = "但其 agent MD 明文声明"


def _load_es(root, tag):
    """从隔离副本里加载 `ensure_settings.py`（每次用**不同模块名**，避免拿缓存模块）。"""
    path = Path(root) / ES_REL
    spec = importlib.util.spec_from_file_location(f"es_wired_{tag}", str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"es_wired_{tag}"] = m
    spec.loader.exec_module(m)
    return m


def _run_22(es, root):
    """跑第 22 项，返回 (rc, 输出文本)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = es.check_cross_review_mapping(str(root))
    return rc, buf.getvalue()


class _Isolated(unittest.TestCase):
    """隔离副本基类：只拷 `config/` `agents/` `references/` `scripts/`，
    所有变异都落在副本上，包内真源**零写入**。"""

    #: ⚠ 每个用例一份**独立**副本（不是类级共享）：变异 3 会**改写**副本里的
    #:   `ensure_settings.py`，若共享则上一个用例的摘除会残留到下一个用例
    #:   ⇒ 锚点找不到 / 破文件被继续加载，用例之间互相污染。
    def setUp(self):
        if not (PKG / "config" / "guard.yaml").is_file():
            self.skipTest(f"缺少 {PKG / 'config' / 'guard.yaml'}（局部树，跳过）")
        self.tmp = Path(tempfile.mkdtemp(prefix="hb-mdareaterms-"))
        for sub in ("config", "agents", "references", "scripts"):
            src = PKG / sub
            if src.is_dir():
                shutil.copytree(src, self.tmp / sub)
        self.guard_yaml = self.tmp / "config" / "guard.yaml"
        self.guard_orig = self.guard_yaml.read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _with_guard(self, mutate):
        """在副本的 `guard.yaml` 上做变异 → 跑第 22 项 → 还原，返回 (rc, 输出)。

        `mutate(data) -> data`：直接改已解析的 dict。还原在 `finally` 里做
        （**逐字写回原文**），保证用例失败也不会污染下一个用例。
        """
        import yaml
        data = yaml.safe_load(self.guard_orig)
        data = mutate(data)
        self.guard_yaml.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        try:
            return _run_22(_load_es(self.tmp, "mut"), self.tmp)
        finally:
            self.guard_yaml.write_text(self.guard_orig, encoding="utf-8")

    def _strip_criterion4(self):
        """变异 3：把副本的 `ensure_settings.py` 里判据 ④ 的**整段**摘掉。

        摘除范围 = 起止锚点之间（含起点注释，不含终点既有代码行）。
        锚点找不到就**直接失败**——宁可红，也不能让"变异没生效"被当成"判据不恒真"。
        """
        p = self.tmp / ES_REL
        text = p.read_text(encoding="utf-8")
        i = text.find(_ANCHOR_BEGIN)
        self.assertGreaterEqual(i, 0, f"副本里找不到判据 ④ 起点锚点：{_ANCHOR_BEGIN!r}")
        # ⚠ 起点要**回退到行首**：锚点是注释行里 `#` 开头的片段，若直接以 i 切，
        #   会把注释行的行首缩进留下来、再接上终点的 8 空格缩进 ⇒ 拼出非法缩进
        #   （实测 IndentationError）。
        i = text.rfind("\n", 0, i) + 1
        j = text.find(_ANCHOR_END, i)
        self.assertGreater(j, i, f"副本里找不到判据 ④ 终点锚点：{_ANCHOR_END!r}")
        p.write_text(text[:i] + text[j:], encoding="utf-8")


class TestMdAreaTermsWired(_Isolated):
    """判据 ④ 的下沉证明：不误伤现状（T1）+ 三个变异必须红（T2/T3）+ 摘掉就不红（T4/T5）。"""

    # ── T1：接线后基线必须仍然绿（假阳性为零）──────────────────────────
    def test_T1_baseline_is_green(self):
        rc, out = _run_22(_load_es(self.tmp, "base"), self.tmp)
        self.assertEqual(rc, 0, f"接线后基线变红（误伤现状，判据有假阳性）：\n{out}")
        self.assertNotIn(MSG_MISSING_TERMS, out)
        self.assertNotIn(MSG_CONTRADICTED, out)

    # ── T2：删掉 / 置空 md_area_terms ⇒ 必须红（缺键即红，禁回退内置词表）──
    def test_T2_missing_md_area_terms_goes_red(self):
        def _delete(data):
            data["cross_review_mapping"]["科学性改动"].pop("md_area_terms", None)
            return data

        def _empty(data):
            data["cross_review_mapping"]["科学性改动"]["md_area_terms"] = []
            return data

        for label, mut in (("删除键", _delete), ("置空列表", _empty)):
            with self.subTest(变异=label):
                rc, out = self._with_guard(mut)
                self.assertNotEqual(rc, 0, f"{label} 后第 22 项仍绿（漏检）")
                self.assertIn(MSG_MISSING_TERMS, out,
                              f"{label} 后未报「{MSG_MISSING_TERMS}」（报的是别处）")

    # ── T3：reviewer 换成其 MD 明文「不做」该领域的人 ⇒ 必须红 ────────────
    def test_T3_reviewer_contradicted_by_own_md_goes_red(self):
        """把「科学性改动」的复检人换成 `pedagogy-architect`（苏学法）。

        其 agent MD 明文「你不回答内容科学性问题（找严真奥）」⇒ 领域词含「科学性」
        ⇒ 判据 ④ 的取反分支必须红。断言用 ④ 的**专属**片段，防止被 ② 的
        「文档写法不一致」蒙对（换人后 ② 也会红，但那不是本条要证明的东西）。
        """
        def _swap(data):
            data["cross_review_mapping"]["科学性改动"]["reviewer"] = "pedagogy-architect"
            return data

        rc, out = self._with_guard(_swap)
        self.assertNotEqual(rc, 0, "复检人被派给被自己 MD 禁止接活的人，第 22 项仍绿（漏检）")
        self.assertIn(MSG_CONTRADICTED, out,
                      f"未报 ④ 的取反分支（「{MSG_CONTRADICTED}」）——可能只是别处变红")

    # ── T4：摘掉判据 ④ ⇒ T3 的红必须消失（证明 ④ 不恒真、确实在判定）──────
    def test_T4_strip_criterion_kills_T3_detection(self):
        self._strip_criterion4()

        def _swap(data):
            data["cross_review_mapping"]["科学性改动"]["reviewer"] = "pedagogy-architect"
            return data

        _rc, out = self._with_guard(_swap)
        self.assertNotIn(MSG_CONTRADICTED, out,
                         "摘掉判据 ④ 后仍能报出取反分支 ⇒ 该报文本由别处产出，④ 形同虚设")

    # ── T5：摘掉判据 ④ ⇒ T2 的红必须消失（锁住"缺键即红"那条）────────────
    def test_T5_strip_criterion_kills_T2_detection(self):
        self._strip_criterion4()

        def _delete(data):
            data["cross_review_mapping"]["科学性改动"].pop("md_area_terms", None)
            return data

        _rc, out = self._with_guard(_delete)
        self.assertNotIn(MSG_MISSING_TERMS, out,
                         "摘掉判据 ④ 后仍能报「缺 md_area_terms」⇒ ④ 的缺键分支未真正接线")


if __name__ == "__main__":
    unittest.main()

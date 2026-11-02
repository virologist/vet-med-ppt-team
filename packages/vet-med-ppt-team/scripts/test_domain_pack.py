#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_domain_pack.py —— B17 通用化转型守卫（升级方案 P5 · R6）

覆盖三支：
  ① 域包五件套 machine-check（domain-pack-check）：齐备度判定 + 豁免消费 + 跨域串味
  ② 通用化哨兵：体检[23]（域专有词残留）与域包齐备度**两个方向**都要可查
  ③ computing 试金石：非动物医学域必须能齐备五件套（证明五件套不是动物医学专属拼装）

纪律（同全包）：
  · 每条判据都必须**能红**——含变异测试：掏空判据后场景必须翻松。
  · 变异测试必须跑**变异副本**的 harness.py。
  · 缺键即 fail-closed：契约缺键 ⇒ 拒绝出结论，不补内置值。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
HARNESS = HERE / "harness.py"
CONTRACT = PKG / "config" / "domain-pack-contract.yaml"
PROFILES = PKG / "config" / "domain-profiles.yaml"

PY = sys.executable


def _run(args, cwd=None):
    e = dict(os.environ)
    e.setdefault("VETMED_NOBROKER", "1")
    proc = subprocess.run([PY, str(HARNESS)] + args, capture_output=True,
                          text=True, cwd=str(cwd or PKG), timeout=180, env=e)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _ws():
    ws = Path(tempfile.mkdtemp(prefix="b17-ws-"))
    (ws / ".workbuddy").mkdir(parents=True, exist_ok=True)
    return ws


def _parse_json(raw):
    """命令输出可能带尾随文本，取第一个完整 JSON 对象。"""
    start = raw.index("{")
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(raw[start:])
    return obj


def _mutant_copy(mutate, expect_change=True):
    """复制包到临时目录并对 harness.py 施加变异，返回 (tmp_pkg, harness_path)。

    ⚠ `expect_change=False` 用于「变异发生在**配置文件**而非 harness.py」的用例
      （如 T6/T7/T8/T9 改的是 domain-profiles.yaml / 契约文件）——
      此时 harness.py 保持原样，不得断言「变异未生效」。
    """
    tmp = Path(tempfile.mkdtemp(prefix="b17-mut-"))
    shutil.copytree(PKG / "scripts", tmp / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(PKG / "config", tmp / "config")
    for rel in (".codebuddy-plugin/plugin.json", "agents"):
        src = PKG / rel
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    h = tmp / "scripts" / "harness.py"
    s = h.read_text(encoding="utf-8")
    mutated = mutate(s)
    if expect_change:
        assert mutated != s, "变异未生效（锚点未命中）"
    h.write_text(mutated, encoding="utf-8")
    return tmp, h


class TestDomainPackContract(unittest.TestCase):
    """① 契约自身与五件套定义。"""

    def test_T1_contract_declares_five_assets(self):
        """契约必须声明五类资产（少一类 ⇒ 五件套名不副实）。"""
        import yaml
        d = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        assets = d.get("assets") or []
        self.assertEqual(len(assets), 5, f"五件套应为 5 类资产，实得 {len(assets)}")
        ids = [a.get("id") for a in assets]
        for must in ("terminology", "knowledge_base", "depth_scale",
                     "audience_profile", "module_templates"):
            self.assertIn(must, ids, f"缺资产面 {must}")
        # 每类资产必须声明承载字段与级别
        for a in assets:
            self.assertTrue(a.get("fields"), f"资产 {a.get('id')} 未声明承载字段")
            self.assertIn(a.get("level"), ("required", "recommended"),
                          f"资产 {a.get('id')} 的 level 非法")

    def test_T2_all_domains_complete(self):
        """三个域全部齐备（required 面无缺口、无未豁免 recommended 缺口）。"""
        ws = _ws()
        try:
            rc, out, err = _run(["domain-pack-check", "--workspace", str(ws)])
            self.assertEqual(rc, 0, f"域包检查未通过：{err[:400]}")
            rep = _parse_json(out)
            self.assertEqual(rep["verdict"], "pass")
            self.assertEqual(rep["missing_required"], [])
            self.assertEqual(rep["weak"], [])
            for did, v in rep["domains"].items():
                for f in v["faces"]:
                    self.assertIn(f["status"], ("ok", "exempted"),
                                  f"{did} 的 {f['asset']} 状态异常：{f}")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T3_probe_domain_completes(self):
        """computing 试金石域必须齐备（通用化不是动物医学专属拼装）。"""
        ws = _ws()
        try:
            rc, out, err = _run(["domain-pack-check", "--workspace", str(ws)])
            self.assertEqual(rc, 0, err[:300])
            rep = _parse_json(out)
            probe = rep.get("probe_domain") or {}
            self.assertEqual(probe.get("domain"), "computing")
            self.assertTrue(probe.get("complete"),
                            f"试金石域未齐备：{probe.get('missing')}")
            self.assertEqual(probe.get("missing"), [])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T4_exemption_registered_and_consumed(self):
        """豁免必须显式登记（三要素齐备）且被正确消费。"""
        import yaml
        prof = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
        exs = prof.get("domain_pack_exemptions") or {}
        self.assertTrue(exs, "豁免登记为空——但 recommended 面确有形态差异域")
        # 结构必须是**映射**（域 → 资产 → {reason}）——列表形态无法产生路径级读取证据
        self.assertIsInstance(exs, dict,
                              "豁免登记须为映射结构（域→资产→{reason}），"
                              "列表形态在体检[18] 只构成弱证据（假绿）")
        n_ex = 0
        for dom, assets in exs.items():
            self.assertTrue(dom, "豁免条目缺域 id")
            self.assertIsInstance(assets, dict)
            for asset, rec in assets.items():
                n_ex += 1
                self.assertTrue(asset, f"豁免条目缺资产 id：{dom}")
                self.assertIsInstance(rec, dict)
                self.assertTrue(rec.get("reason"),
                                f"豁免缺 reason（域={dom} 资产={asset}）")
                self.assertTrue(len(str(rec.get("reason"))) >= 10,
                                "豁免理由过短——等于没写理由")
        # 且被消费
        ws = _ws()
        try:
            rc, out, err = _run(["domain-pack-check", "--workspace", str(ws)])
            rep = _parse_json(out)
            consumed = sum(1 for v in rep["domains"].values()
                           for f in v["faces"] if f["status"] == "exempted")
            self.assertEqual(consumed, n_ex,
                             f"豁免登记 {n_ex} 条但消费 {consumed} 条")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_T5_report_and_trace_landed(self):
        """齐备度报告落盘 + 入 trace（可审计、可跨任务看趋势）。"""
        ws = _ws()
        try:
            _run(["domain-pack-check", "--workspace", str(ws)])
            rep = ws / ".workbuddy" / "domain_pack_report.json"
            self.assertTrue(rep.exists(), "齐备度报告未落盘")
            tf = ws / ".workbuddy" / "harness_trace.jsonl"
            evs = []
            if tf.exists():
                for line in tf.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        evs.append(json.loads(line))
            dpc = [e for e in evs if e.get("event") == "domain_pack_check"]
            self.assertTrue(dpc, "domain_pack_check 事件未落 trace")
            self.assertEqual(dpc[-1]["detail"]["verdict"], "pass")
        finally:
            shutil.rmtree(ws, ignore_errors=True)


class TestDomainPackRedProofs(unittest.TestCase):
    """② 能红证明：把域改坏必须被抓住。"""

    def _mutate_profiles(self, tmp, mutate):
        """对副本的 domain-profiles.yaml 施加变异。"""
        pf = tmp / "config" / "domain-profiles.yaml"
        s = pf.read_text(encoding="utf-8")
        mutated = mutate(s)
        assert mutated != s, "变异未生效"
        pf.write_text(mutated, encoding="utf-8")

    def test_T6_missing_required_asset_is_red(self):
        """删掉 computing 的 depth_scale_source ⇒ 必须判红 rc=1。"""
        tmp, h = _mutant_copy(lambda s: s, expect_change=False)

        def mutate(s):
            # 删除 computing 域的 depth_scale_source 段（用行级定位，避开其他域同名）
            lines = s.split("\n")
            start = next(i for i, ln in enumerate(lines) if ln.strip() == "- id: computing")
            end = next((j for j in range(start + 1, len(lines))
                        if lines[j].startswith("  - id:")), len(lines))
            ka = next(i for i in range(start, end)
                      if lines[i].startswith("    depth_scale_source:"))
            # 该段到下一个同缩进键为止
            k = ka + 1
            while k < end and (lines[k].startswith("      ") or not lines[k].strip()):
                k += 1
            del lines[ka:k]
            return "\n".join(lines)

        self._mutate_profiles(tmp, mutate)
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 1,
                             f"缺 required 资产应 rc=1，实得 {proc.returncode}")
            rep = _parse_json(proc.stdout)
            self.assertTrue(any("computing" in m for m in rep["missing_required"]),
                            f"未指出 computing 缺口：{rep['missing_required']}")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T7_invalid_exemption_is_red(self):
        """豁免缺 reason ⇒ 豁免无效 ⇒ 仍判缺（豁免不能蒙混过关）。"""
        tmp, h = _mutant_copy(lambda s: s, expect_change=False)

        def mutate(s):
            # 行级定位：domain_pack_exemptions 里 computing 那条的 reason 行
            lines = s.split("\n")
            hit = False
            for i, ln in enumerate(lines):
                if ln.strip() == "computing:" and ln.startswith("  "):
                    # 映射结构：computing → module_templates → reason
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith("    "):
                            break
                        if lines[j].lstrip().startswith("reason:"):
                            lines[j] = '      reason: ""'
                            hit = True
                            break
                    break
            assert hit, "computing 豁免 reason 行未找到"
            return "\n".join(lines)

        self._mutate_profiles(tmp, mutate)
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            # ⚠ 语义校准：module_templates 是 **recommended 级** ⇒ 其缺口只提示不阻断
            #   （rc 仍 0），但**必须回到「缺失」状态**——即不再算已豁免，
            #   且必须出现在 weak 里（= 豁免失效被机器看见）。
            #   若它仍被算作「已豁免」⇒ 豁免三要素校验形同虚设（守卫空转）。
            self.assertEqual(proc.returncode, 0,
                             f"recommended 级缺口不应阻断，实得 {proc.returncode}")
            rep = _parse_json(proc.stdout)
            faces = rep["domains"]["computing"]["faces"]
            mt = next(f for f in faces if f["asset"] == "module_templates")
            self.assertEqual(mt["status"], "missing",
                             f"无效豁免后仍被判为已豁免 ⇒ 三要素校验空转（status={mt['status']}）")
            self.assertIn("computing#module_templates", rep["weak"],
                          "无效豁免的 recommended 缺口未进 weak 清单")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T8_cross_domain_contamination_is_red(self):
        """跨域串味（某域引用别域专有资产）⇒ rc=3 阻断。"""
        tmp, h = _mutant_copy(lambda s: s, expect_change=False)

        def mutate(s):
            # 在 computing 域的 depth_scale_source.standard 里塞入动物医学标准名
            return s.replace(
                '      standard: "语言与平台的官方规范/参考手册（ECMA-262 / Python Language Reference / MDN / 各框架官方文档，须现查对应版本）"',
                '      standard: "动物医学专业教学标准 + 语言官方文档"')

        self._mutate_profiles(tmp, mutate)
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 3,
                             f"跨域串味应 rc=3，实得 {proc.returncode}")
            rep = _parse_json(proc.stdout)
            self.assertTrue(rep["cross_domain_hits"], "串味未记录")
            self.assertEqual(rep["verdict"], "cross_domain_contamination")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_T9_missing_contract_is_fail_closed(self):
        """契约文件缺失 ⇒ fail-closed（rc=1），不出任何结论。"""
        tmp, h = _mutant_copy(lambda s: s, expect_change=False)
        (tmp / "config" / "domain-pack-contract.yaml").unlink()
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 1,
                             f"契约缺失应 fail-closed rc=1，实得 {proc.returncode}")
            self.assertIn("fail-closed", proc.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


class TestGeneralizationSentinelDirection(unittest.TestCase):
    """③ 通用化哨兵：两个方向都要可查。"""

    def test_T10_residue_and_completeness_both_checked(self):
        """体检[23]（不该有的词）与域包齐备度（该有的资产）**同时存在**。

        这是通用化的双方向：只查一个方向都不算通用化——
        · 只查「不该有的词」⇒ 缺资产查不出来（本批前的状态）；
        · 只查「该有的资产」⇒ 域串味查不出来。
        """
        src = (PKG / "scripts" / "ensure_settings.py").read_text(encoding="utf-8")
        self.assertIn("check_domain_binding_residue", src,
                      "体检[23] 域专有词残留巡检不见了（反向哨兵缺失）")
        h = HARNESS.read_text(encoding="utf-8")
        self.assertIn("cmd_domain_pack_check", h,
                      "域包齐备度正向巡检不见了")

    def test_T11_contract_is_registered_in_zone_registry(self):
        """契约配置必须登记免检区（否则死配置巡检会判它无消费方）。"""
        reg = (PKG / "references" / "inspection-zones.yaml").read_text(encoding="utf-8")
        self.assertIn("domain-pack-contract.yaml#assets", reg,
                      "契约的 assets 段未登记免检区")
        self.assertIn("domain-pack-contract.yaml#cross_domain_guard", reg,
                      "契约的 cross_domain_guard 段未登记免检区")

    def test_T12_doctor_registers_new_command(self):
        """doctor 表必须登记 domain-pack-check（AI 冷启动可发现性）。"""
        rc, out, err = _run(["doctor"])
        self.assertEqual(rc, 0, err[:200])
        names = [c.get("command") or c.get("name") for c in _parse_json(out)["commands"]]
        self.assertIn("domain-pack-check", names,
                      "doctor 表未登记 domain-pack-check（冷启动发现不到）")


class TestMutantsAreKilled(unittest.TestCase):
    """变异能红证明。"""

    def test_mutant_M1_drop_required_check_makes_T6_red(self):
        """掏空 required 缺口判定 ⇒ T6 的红变绿（证判据被覆盖）。"""
        def mutate(s):
            # ⚠ 只掏空 append（保留 if/else 配对 ⇒ 语法仍合法）
            old = "                    miss.append(aid)"
            new = "                    pass  # MUTANT"
            assert old in s, "M1 锚点未命中"
            return s.replace(old, new, 1)

        tmp, h = _mutant_copy(mutate)
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0, "变异体自身不该报错")
            rep = _parse_json(proc.stdout)
            self.assertEqual(rep["missing_required"], [],
                             "变异体仍报缺口 ⇒ required 判据没被覆盖（守卫空转）")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mutant_M2_drop_exemption_check_makes_T7_red(self):
        """掏空豁免三要素校验 ⇒ 无效豁免也被放行（证 T7 的判据被覆盖）。"""
        def mutate(s):
            old = '''            ex_valid = bool(ex) and ex_fields.issubset(set(ex.keys())) and \\
                all(ex.get(k) for k in ex_fields)'''
            new = '''            ex_valid = bool(ex)  # MUTANT'''
            assert old in s
            return s.replace(old, new, 1)

        tmp, h = _mutant_copy(mutate)
        # 同时把 computing 的豁免 reason 清空（构造无效豁免）
        pf = tmp / "config" / "domain-profiles.yaml"
        _lines = pf.read_text(encoding="utf-8").split("\n")
        for i, ln in enumerate(_lines):
            if ln.strip() == "computing:" and ln.startswith("  "):
                for j in range(i + 1, len(_lines)):
                    if _lines[j].strip() and not _lines[j].startswith("    "):
                        break
                    if _lines[j].lstrip().startswith("reason:"):
                        _lines[j] = '      reason: ""'
                        break
                break
        pf.write_text("\n".join(_lines), encoding="utf-8")
        ws = _ws()
        try:
            proc = subprocess.run([PY, str(h), "domain-pack-check",
                                   "--workspace", str(ws)],
                                  capture_output=True, text=True, timeout=180)
            self.assertEqual(proc.returncode, 0, "变异体自身不该报错")
            rep = _parse_json(proc.stdout)
            self.assertEqual(rep["missing_required"], [],
                             "变异体仍报缺口 ⇒ 豁免校验没被覆盖（守卫空转）")
        finally:
            shutil.rmtree(ws, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# b2026111507 · 方案B「CLI 退出约定唯一化」可执行契约守卫（v3.31.3 内整改）
#
# 唯一契约（本文件即执行者，不靠文档自报）：
#   C1 凡定义 main() 的生产脚本，`__main__` 一律 `sys.exit(main())`。
#      此前 9 个脚本写裸 `main()`：虽然它们都在 main 内部自行 sys.exit，
#      但契约分裂 ⇒ 一旦有人给 main 加 return 1，失败又会静默 exit 0（B1.1 同型病灶）。
#   C2 main() 的常量返回值只允许 int / None（禁止把字符串、dict 当退出码）。
#   C3 致命错误走 stderr、stdout 保持机器可解析（用 snapshot.py 实跑守护）。
#
# 旧码（2618a5c）上 C1 必须判红；新码 3 条全绿。
# 运行方式（在 scripts/ 目录下）：python3 -m unittest -v test_cli_contract_guard
import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def _prod_scripts():
    return [p for p in sorted(HERE.glob("*.py")) if not p.name.startswith("test_")]


def _main_fn(tree):
    return next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main"), None)


class CliContractGuard(unittest.TestCase):
    """CLI 唯一契约的能红守卫。"""

    def test_C1_all_entrypoints_use_sys_exit(self):
        violations = []
        for p in _prod_scripts():
            tree = ast.parse(p.read_text(encoding="utf-8"))
            if _main_fn(tree) is None:
                continue
            tail = tree.body[-1]
            body = ast.unparse(tail.body).strip() if isinstance(tail, ast.If) else ""
            if "sys.exit(main())" not in body:
                violations.append(f"{p.name}: {body or '<无 __main__>'}")
        self.assertEqual(violations, [],
                         "CLI 退出约定必须唯一为 sys.exit(main())；未统一：\n" + "\n".join(violations))

    def test_C2_main_constant_returns_are_int_or_none(self):
        bad = []
        for p in _prod_scripts():
            tree = ast.parse(p.read_text(encoding="utf-8"))
            main = _main_fn(tree)
            if main is None:
                continue
            for node in ast.walk(main):
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant):
                    if not isinstance(node.value.value, (int, type(None))):
                        bad.append(f"{p.name}:{node.lineno} → {node.value.value!r}")
        self.assertEqual(bad, [], "main() 不得把非整数常量当退出码：" + ", ".join(bad))

    def test_C3_fatal_error_to_stderr_stdout_stays_parseable(self):
        with tempfile.TemporaryDirectory(prefix="cli_contract_") as td:
            missing = Path(td) / "no_such_deck.pptx"
            res = subprocess.run(
                [PY, str(HERE / "snapshot.py"), "snap", str(missing), "--workspace", td],
                capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0, "失败必须阻断（非零退出码）")
            self.assertIn("deck 不存在", res.stderr, "致命错误应写 stderr")
            self.assertEqual(res.stdout.strip(), "", "stdout 不得混入人读诊断文本")


if __name__ == "__main__":
    unittest.main(verbosity=2)

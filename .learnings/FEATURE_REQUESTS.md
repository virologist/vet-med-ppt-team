# Feature Requests

Capabilities requested by the user.

---

## [FEAT-20261022-001] 静态数据流分析以发现「提到但没用」的配置键

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: medium
**Status**: pending

### Requested Capability
能区分「代码里提到某个配置键」与「代码真的读了这个值」的静态检查能力。

### User Context
第 18 项死配置体检做完后（已降级为 INFO），反例实测暴露其固有局限：
把 `verify_deck.py` 的 `cfg.get("three_source_check")` 改成 `{}`（读取行为已破坏），
第 18 项统计**完全不变**——因为该键名在其它脚本、注释、docstring 中仍出现，
纯文本包含匹配判定为"有读取者"。

即：本项只能发现"完全无人提及"的键，发现不了"提到但没用"的键。
后者才是更危险的一类（看起来有护栏，实际不生效）。

### Complexity Estimate
medium

### Suggested Implementation
本轮已用"专项断言脚本"作为务实替代（`verify_three_source_config.py`：
逐键断言"运行时值 == 配置值" + 静态扫字面量残留）。
若要通用化，可考虑：
- 用 AST 解析出 `cfg.get("<key>")` / `cfg["<key>"]` 形式的真实读取点，
  排除注释与 docstring（比文本包含精确，但只覆盖显式取值的写法）
- 或对每个"关键阈值键"配一份专项断言脚本，纳入体检

### Metadata
- Frequency: first_time
- Related Features: check_dead_config_keys（第 18 项）

---
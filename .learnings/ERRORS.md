# Errors

Command failures and integration errors.

---

## [ERR-20261022-001] Bash grep 空结果

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: infra

### Summary
Bash 里的 grep 在本环境偶发返回空结果，而 Grep 工具返回正常——单次空结果不可作为"未命中"的证据

### Error
```
Command: grep -rn "pattern" scripts/harness.py
Stdout: (empty)
```

但同一时刻用 Grep 工具查同一模式，能正常返回 20 处命中。

### Context
- 同一会话内多次出现：查 `ENVELOPE_REQUIRED`、查 `threading|Lock|fcntl`、
  查 `writes_allowed|duty|degrade_modes` 等，Bash grep 均返回空，Grep 工具均正常
- 沙箱环境偶发问题，非文件本身问题

### Suggested Fix
断言"代码里没有 X"时，**必须用 Grep 工具复核**，不要只信 Bash grep 的空输出。
否则会把"工具抽风"误判成"代码没问题"，或反之误报缺陷。

### Metadata
- Reproducible: intermittent
- Related Files: scripts/harness.py, scripts/verify_deck.py
- See Also: ERR-20261022-002

---

## [ERR-20261022-002] Bash 复合命令被沙箱拒绝

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: low
**Status**: resolved
**Area**: infra

### Summary
`cd X && $PY - <<'EOF' ... EOF` 这类复合命令偶发被沙箱拦截（decisionRecord missing actual resource subject）

### Error
```
Error: sandbox-center cmd decisionRecord missing actual resource subject
```

### Context
- 触发形态：heredoc（`<<'EOF'`）与 `cd` 组合，或较长内联 `python3 -c`
- 变通：把验证逻辑写成独立 .py 文件用 Write 落盘，再 `python3 <文件>` 执行；
  或用 Edit 工具直接改文件而非 shell 内联

### Suggested Fix
验证逻辑较复杂时，一律 Write 成独立脚本再执行，不要塞进 `python3 -c` 内联。
顺带好处：脚本可留作回归证据（如 verify_three_source_config.py）。

### Metadata
- Reproducible: intermittent
- Related Files: scripts/verify_deck.py
- See Also: ERR-20261022-001

---

## [ERR-20261022-003] 递归闭包漏 nonlocal

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: low
**Status**: resolved
**Area**: backend

### Summary
给嵌套函数新增计数变量时忘记同步 nonlocal 声明，且编辑时误删了 list 分支

### Error
```
UnboundLocalError: cannot access local variable 'textual' where it is not associated with a value
  File "ensure_settings.py", line 916, in walk
    textual += 1
```

### Context
- 起因：给 `check_dead_config_keys` 的 `walk()` 加 `textual` 计数器时，
  `nonlocal alive` 没改成 `nonlocal alive, textual`
- 修这个错误时的 Edit 又误删了 `elif isinstance(node, list)` 分支，导致
  YAML 列表元素被当标量处理

### Suggested Fix
嵌套递归函数里新增外层变量：**声明与赋值要同一处改完**；
修改 `walk()` 这类递归体后，立刻用含列表的真实 YAML 跑一遍，
不要只看编译通过（本次编译通过、运行才炸）。

### Metadata
- Reproducible: no
- Related Files: scripts/ensure_settings.py

---
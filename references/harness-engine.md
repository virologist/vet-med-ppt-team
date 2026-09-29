# 编排内核使用规范（v2.2.0，主理人必读）

> 本文件是 `config/harness.yaml` + `scripts/harness.py` 的**人读入口**。
> 制定依据：2026-09-29 基线实测——成员不可调度导致整链阻断、静默降级无人察觉、成本与耗时零计量。
> 原则：**能用代码约束的，绝不靠自觉**。本文件只说明"什么时候跑哪个命令"，规则真身在 yaml。

## 1. 开工三步（阶段0 内必做，缺一不可）

```bash
H="python3 <专家包>/scripts/harness.py"
W="<工作空间>"

# ① 成员可用性预检（含静默降级探测）——把"降级"从事后发现变成开工前告警
$H preflight --team <团队名> --workspace "$W"

# ② 确定性路由：复杂度 → spawn 计划（不再靠主理人临场判断）
$H route --level L2

# ③ 初始化状态机与预算
$H state init --workflow WF-1 --stage 0 --workspace "$W"
```

判定复杂度仍由主理人做（语义判断），但**spawn 计划本身由 `route` 给出**（确定性）。

## 2. 降级协议（成员不可调度时不再整链阻断）

| 情况 | 处置 |
|---|---|
| preflight 报 `degraded`（platform 把成员回落成 general-purpose） | spawn 通用子代理，**任务包开头必须注入该成员 MD 全文**（人格+红线），并在交付物与 trace 中显式声明"本次为降级执行" |
| spawn 报 `not available` | 同一成员**最多再试 1 次**（`max_spawn_attempts=2`），仍失败即走上一行的降级通道，**不再阻断** |
| 降级通道也不可用 | 才允许 `blocked`，写入 trace 并向用户明说；**主理人代写成员产出仍然是红线，不得借降级之名代写** |

> 与旧规则的关系：v2.1.0 的"Agent 不可用＝任务阻断"被本条**修订**——阻断是最后手段，不是第一反应。
> 红线未松动：禁止代写成员产出；降级只是换执行者，不换职责边界。

## 3. 状态机纪律

- `current_stage` **只接受 0–5 整数**；`M5A2`、`stage_6` 这类便签值一律被 `state set/validate` 拒绝
- `task_state.json` 只允许 `context.state_allowed_keys` 白名单内的键（防 27KB/32 键式膨胀）
- 每次阶段切换：`state set --stage N` → 自动追加 `stage_history`，并写 trace

## 4. 预算护栏（纪律变计数）

```bash
$H budget spend --kind spawn --n 1      # 每 spawn 一名成员扣 1（上限 8）
$H budget spend --kind react  --n 1     # 严真奥每轮检索扣 1（单缺口≤3，总≤15）
$H budget spend --kind rework --n 1     # 阶段返工（每阶段≤2）
$H budget check --kind spawn            # 剩余额度查询
```

超限时命令**返回非 0 并写 trace**，主理人必须上报用户或切降级，不得硬冲。

## 5. 上下文隔离

- 成员产出**只回传路径 + ≤800 字摘要**（`context.handoff_mode=path_only`），全文落盘不进对话
- **落盘路径必须是绝对路径**（v2.2.0 实测教训：成员按相对文件名落盘，产物散落各自 cwd，主理人拿不到）；任务包 `output_format` 里写的路径一律给绝对路径
- **主理人必须核验落盘真实性**：成员回传后 `ls -la <绝对路径>` 确认文件存在且非空；"已落盘"的自述不作为交付依据（实测出现过自报文件根本不存在）
- 单个产物超过 `max_artifact_bytes`（60KB）强制压缩为"路径+摘要"

## 6. 门禁统一入口（不再裸调 verify_deck）

```bash
$H gate --deck <课件.pptx> --hours 2 --level all
```

- exit 0/1/2/3 语义不变（通过 / P0 / P1 / P2）
- **exit 4 = 运行错误**（脚本 bug 或文件不可读），**走缺陷回流修脚本，不得当作课件红灯打回成员**
- 每次调用自动写 trace（退出码、耗时、stderr 尾部）

## 7. 收尾

```bash
$H trace report --workspace "$W"   # 事件计数、按成员统计、阶段耗时（秒）
```

交付物须附 trace 摘要；A/B 对比、成本核算以 trace 为准，不以任何自述为准。

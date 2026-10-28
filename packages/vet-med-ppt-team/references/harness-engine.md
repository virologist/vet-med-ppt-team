# 编排内核使用规范（v2.2.0，主理人必读）

> 本文件是 `config/harness.yaml` + `scripts/harness.py` 的**人读入口**。
> 制定依据：2026-09-29 基线实测——成员不可调度导致整链阻断、静默降级无人察觉、成本与耗时零计量。
> 原则：**能用代码约束的，绝不靠自觉**。本文件只说明"什么时候跑哪个命令"，规则真身在 yaml。

<!-- 机器比对用镜像块（v3.17.0 新增）：scripts/test_arch_drift.py#T9 把它与
     config/harness.yaml#stages 逐项比对——改 yaml#stages 必须同步本块，由守卫强制、不靠自觉。 -->
<!-- STAGE_MIRROR_BEGIN -->
stage 0 | 闸1 任务冻结 | members: - | gate: user_confirm | parallel: no
stage 1 | 闸2 设计（证据先行→蓝图·串行） | members: pedagogy-architect, dvm-content-expert | gate: user_confirm | parallel: no
stage 2 | 闸3 成稿（页表∥版式） | members: pedagogy-architect, visual-slide-designer | gate: script_check | parallel: yes
stage 3 | 闸4 交付（门禁+独立验证） | members: verifier | gate: gate_script+verifier | parallel: no
stage 4 | 闸4.5 案例三源核验（v3.3.0） | members: dvm-content-expert, verifier | gate: three_source_check | parallel: yes
<!-- STAGE_MIRROR_END -->

## 1. 开工三步（闸1 内必做，缺一不可）

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

- `current_stage` **只接受 0–4 整数**（唯一源 = `config/harness.yaml#stages`；v3.3.0 起双轨期 0–4 合法）；`M5A2`、`stage_6` 这类便签值一律被 `state set/validate` 拒绝
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
$H gate --deck <课件.pptx> --hours <N> --level P0|all
```

- 退出码语义**逐项**见下方镜像块（机器比对面）；**唯一源 = `config/harness.yaml#gate_exit_codes`**（yaml 改了就必须同步本块，由守卫强制）

<!-- GATE_EXIT_MIRROR_BEGIN -->
exit 0 | 通过
exit 1 | P0 硬阻断——禁止写回，先组织修复
exit 2 | P1 阻断——可带修复计划写回，交付前清零
exit 3 | P2 阻断——备注覆盖率未达标
exit 4 | 运行错误——脚本/文件问题，非课件质量；必须报 traceback 并走缺陷回流，不得当作红灯打回成员
<!-- GATE_EXIT_MIRROR_END -->

<!-- 机器比对用镜像块（v3.25.0 新增）：scripts/test_arch_drift.py#TestGateExitMirror 把它与
     config/harness.yaml#gate_exit_codes 逐码对账（码集合双向 + 语义逐字）——
     删 yaml 的任一码、改任一语义、删本块，都会在体检期判红。 -->

- ⚠️ **`--hours` 必填**（v3.0.0）：课时口径在闸 1 冻结并显式声明。**禁用按可见页数反推课时的 `--auto-hours`**——那是自证式通过（页数永远"符合"自己推导的档位），历史上正是它掩盖了真实的"课时不达标"
- 每次调用自动写 trace（退出码、耗时、stderr 尾部）
- **P2 覆盖率含机器草稿**，但输出会单独报 `machine_note_ratio`（AI 草稿页 / 已备注文页）；交付物必须明示该比例并标"待教师复核"（裁决④）

## 7. 唯一裁判（B0：结论可比的前提）

**全包只允许一份权威门禁**：`scripts/verify_deck.py`（SSOT）。理由：它具备 P0/P1/P2/P3 分级与退出码语义、3 个 None 崩溃修复史、trace 集成、judge 溯源字段。

- ❌ **禁止**在包内出现第二份 `verify_deck.py`（`ensure_settings.py` 第 6 项会拦）
- ❌ **禁止**任何脚本私自定义分级常量（`P0_KEYS` 之类）——分级唯一定义在 `config/visual-rules.yaml#severity`
- 其它系统（如课程工作区的 `vet-ppt-pipeline` skill）里的同类脚本，只能是**非门禁工具**：快速体检、现场抽查，**不得产生放行结论**
- 台账每条门禁结论必须记 `judge_provenance`（脚本绝对路径 + 角色 SSOT + 版本 + 等级 + 课时口径）
- 口径变更（改 `severity` / 改阈值 / 改判定逻辑）**须经 verifier 第二签**，否则无效

## 8. 工具白名单的平台铁律（不要再加回去）

⚠️ **WorkBuddy 专家包不支持在 agent frontmatter 声明 `tools:` 字段**（2026-09-30 实测确认，已回退 v2.2.0 的相关改动）。
最小权限的正确实现是：
1. **人设装配**：`assemble_domain_prompt.py --member <ID> --task-file <绝对路径> --check-task-package --collapse-artifact <坍缩产物路径>`（把成员 MD 全文 + **域上下文** + 资源绝对路径确定性注入；详见 `references/spawn-protocol.md#二`）
2. **任务包约束**：在 `objective / output_format / constraints / task_boundary` 四要素里写清"不做什么"
3. `config/harness.yaml#members[*].tools_whitelist` 是**主理人的编排意图声明**，供 preflight 与人工核对，不是平台强制

## 9. 收尾

```bash
$H trace report --workspace "$W"   # 事件计数、按成员统计、阶段耗时（秒）
```

交付物须附 trace 摘要；A/B 对比、成本核算以 trace 为准，不以任何自述为准。

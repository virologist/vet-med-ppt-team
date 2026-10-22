# Spawn 协议（任务包 schema + 成员人设注入）

> 从主理人 MD 外置（v3.4.3 遗留批瘦身，P1-3 三轮的延续）。主 MD 只留索引。
> 适用：所有 Agent spawn / 降级 spawn 场景。
> **v3.12.0 变更**：本文件此前自称「回传 schema 唯一权威源」，其字段定义
> （`{from, stage, artifact, warnings, evidence_used, next_recommendation}`）与
> `scripts/harness.py` 的校验字段**互斥**——按本文产出的合规信封会被校验器判
> 「缺字段 → 退回补充」。根因是"多处各自定义"。现回传信封改为
> **`references/result-envelope.yaml` 单一数据源**，本文件只引用、不再定义。

## 一、下发任务包 schema（v1.7.0：spawn 成员必附，防委派模糊）

每次 spawn 成员时，任务包必须含以下四要素（Anthropic 委派协议），缺一即补齐再 spawn：

```json
{
  "objective": "一句话目标（该成员要产出什么）",
  "output_format": "输出结构（对应其 MD 的输出规范节名 + 回传 schema）",
  "constraints": ["边界与红线（受众/课时/禁项/证据要求）"],
  "task_boundary": "明确的任务边界（做什么/不做什么/输入是什么）"
}
```

### 回传信封（v3.12.0：定义见 `references/result-envelope.yaml`，此处只列必填）

必填六字段：`agent_id` / `task_id` / `phase` / `status` / `confidence` / `deliverable_summary`
选填四项：`evidence` / `issues` / `next_agent_hint` / `metrics`
`status` 只能取 `success` / `partial` / `failed` / `blocked`。

校验命令：`python3 scripts/harness.py verify-envelope --path <成员产出文件>`
（字段定义、语义判据、旧字段别名映射全部以 yaml 为准，本文件不复述——避免两处定义再次漂移）

- **绝对路径强制（v2.2.0）**：任务包里的落盘路径一律给**绝对路径**；成员回传后主理人必须 `ls -la <绝对路径>` 核验文件真实存在且非空——实测出现过成员自报"已落盘 19.5KB"而文件全盘不存在
- 并行 spawn 时任务边界必须互斥无交集（防重复劳动与覆盖缺口）；任务包写入 task_state.json 备查

## 二、成员人设注入协议（P0 强制 · v2.2.0 落地）

> **平台事实（2026-09-29 实测）**：`Agent(name=成员ID)` spawn 出的 teammate `agentType` 恒为 `general-purpose`，`agents/<member>.md` **不会**被自动注入。本团成员各自守着 `config/visual-rules.yaml` 红线、`references/sop-stages.md` 阶段规范、`scripts/verify_deck.py` 门禁——人设不注入，这些规范一条都不会被遵守。

### 强制三步

1. **装配**（确定性脚本）
   ```bash
   EXPERT_DIR=~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
   RUN_DIR=<workspace>/.harness-runs/<task_id>
   python3 "$EXPERT_DIR/scripts/assemble_spawn_prompt.py" \
     --member <member-id> --phase <阶段号> --task-id <task_id> \
     --task-file <任务包文件> --run-dir "$RUN_DIR" --check-task-package \
     --out "$RUN_DIR/spawn__<member-id>.md"
   ```
   脚本确定性完成：成员 MD 全文注入 + **`config/visual-rules.yaml` / `references/*.md` / `scripts/*.py` 绝对路径清单**（本团无 skills 目录，这些就是成员的资源根，必须显式下发）+ 白名单校验（非 `plugin.json` 成员 exit 2）+ 任务包四要素校验（缺 exit 4）+ 落盘契约。
2. **spawn**：`Agent(name=<member-id>, subagent_type="general-purpose", prompt=<上一步产物>)`
3. **收产出**：以落盘文件 `<RUN_DIR>/<task_id>__<member-id>.md` 为准，SendMessage 仅作摘要通知。文件缺失 = 未交付。

> ⚠️ 本团成员实测可能**无 Write 权限**（仅有 Bash/Read/Grep/Glob/Web 系）。落盘契约已内置回退：无 Write 时用 Bash heredoc 写文件。主理人下发时不要假设成员能 Write。

### 严禁

- ❌ 不跑装配脚本直接 spawn
- ❌ 成员横向直连（实测发生跨团队串台）。跨成员信息流经主理人中转
- ❌ 以"成员自称完成"替代文件校验——与本团「反自评失真」红线一致，完成声明必须引用可验证计数（落盘文件存在 + verify_deck 原始 P0/P1/P2 计数），禁止"归零/100%"表述

### 工具/通道不可用回退

| 通道 | 回退 |
|---|---|
| TeamCreate | 并行 Bash 调度成员输出到临时文件 + Read（质量降低但链路通） |
| SendMessage | 成员回传文本放对话内 + 主理人显式 ack「收到XX成员产出」 |
| Agent tool（subagent） | **v2.2.0 修订：先降级，后阻断**。① 同一成员最多再试 1 次（`harness.yaml#fallback.max_spawn_attempts=2`）；② 仍不可用 → spawn 通用子代理并在任务包开头**注入该成员 MD 全文**（人格+红线照旧生效），交付物与 trace 显式声明「本次为降级执行」；③ 降级通道也不可用才允许 blocked。**红线不变：任何情况下禁止主理人代写成员专业产出**（详见 references/harness-engine.md#2） |
| Ima/UpNote/ToolSearch | 不可用即明示，不空转重试；记忆复用尝试 > 证据检索跳过 |

> **红线**：官方 team-spec 明确「禁止主理人代写成员产出」。**主理人代行 = 违规，不是降级容错**（2026-09-13 复合角色代写事故教训，v1.5.0 修复）。

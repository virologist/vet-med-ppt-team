# Spawn 协议（任务包 schema + 成员人设注入）

> 从主理人 MD 外置（v3.4.3 遗留批瘦身，P1-3 三轮的延续）。主 MD 只留索引。
> 适用：所有 Agent spawn / 降级 spawn 场景。
> **v3.12.0 变更**：本文件此前自称「回传 schema 唯一权威源」，其字段定义
> （`{from, stage, artifact, warnings, evidence_used, next_recommendation}`）与
> `scripts/harness.py` 的校验字段**互斥**——按本文产出的合规信封会被校验器判
> 「缺字段 → 退回补充」。根因是"多处各自定义"。现回传信封改为
> **`references/result-envelope.yaml` 单一数据源**，本文件只引用、不再定义。

## 一、下发任务包 schema（v1.7.0：spawn 成员必附，防委派模糊）

每次 spawn 成员时，任务包必须含以下**五要素**（Anthropic 委派协议 + v3.17.0 增补第五要素），缺一即补齐再 spawn：

```json
{
  "objective": "一句话目标（该成员要产出什么）",
  "output_format": "输出结构（对应其 MD 的输出规范节名 + 回传 schema）",
  "constraints": ["边界与红线（受众/课时/禁项/证据要求）"],
  "task_boundary": "明确的任务边界（做什么/不做什么/输入是什么）",
  "acceptance_criteria": [
    {
      "check": "可判定的具体命题（如「每页正文字号 ≥ 正文下限」）",
      "judge_mode": "机",
      "threshold": "数值 + 判据出处（如「>= 12.0，源 config/visual-rules.yaml#font.body_min_pt」）"
    }
  ]
}
```

### 第五要素 `acceptance_criteria` 的字段纪律（v3.17.0）

- **数组**，每条含**三件套**：`check`（检查项）/ `judge_mode`（判定方式）/ `threshold`（阈值）
- `judge_mode` 取值 **机 / 人 / 机+人**——与诊断报告同一套口径（唯一源
  `references/diagnosis-report-schema.yaml#enums.judge_mode`），**不另立枚举**
- `threshold` **必须写数值 + 判据出处**（`源 <文件>#<键>`）；
  **禁止**「尽量」「合理」「高质量」「差不多」这类**不可判定**的表述
- **机判项必须附可复跑的命令或脚本**（否则「机」是空头支票）；人判项必须给出**对照对象**（如「对照基线快照逐页比」）
- 数量下限：L0/L1 微/轻任务 ≥1 条；L2 标准任务 ≥3 条；L3 重任务 ≥5 条
- 判据的**阈值本身不要在任务包里另写一份**——**引用既有唯一源**
  （`config/visual-rules.yaml` / `references/course-profile-defaults.md` / `references/seven-dimension-rubric.md`），
  任务包只写「源 <文件>#<键>」，避免出现第二份数值

> ⚠️ **代码侧尚未强制（跨批需求，v3.17.0 如实标注，不粉饰）**
> 装配脚本 `shared-core/assemble_spawn_prompt.py` 的 `check_task_package()` 目前**只校验四要素**：
> 常量 `TASK_PACKAGE_FIELDS`（该文件第 63 行）与函数体（第 210–217 行）做的是
> 「**字段名是否作为子串出现在任务包文本里**」的字符串包含判断——
> `"objective": "x"` 这类**占位写法同样能过**，且**没有验收标准字段**。
> 因此 `acceptance_criteria` 目前是**文档级契约**，**装配脚本不会拦**；
> 主理人在 spawn 前须**人工核对**本要素是否齐备（尤其阈值是否指向唯一源）。
> 代码侧补强方案见本批交付报告的「跨批需求」条目（`shared-core/` 属 vendor 目录，由主理人统一派单）。
>
> ⚠️ 另注：四要素的现有校验是**子串包含**而非**结构解析**，因此
> 「字段名出现在正文散文里」也算「已填」——这条弱校验已被本包既有行为证实
> （正文提及即过），**不可**据此认为任务包合规。

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
   脚本确定性完成：成员 MD 全文注入 + **`config/visual-rules.yaml` / `references/*.md` / `scripts/*.py` 绝对路径清单**（本团无 skills 目录，这些就是成员的资源根，必须显式下发）+ 白名单校验（非 `plugin.json` 成员 exit 2）+ 任务包**四要素**校验（缺 exit 4；**第五要素 `acceptance_criteria` 脚本暂不校验**，见 §一 注）+ 落盘契约。
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

## 四、外部依赖登记与检查（v3.17.0 新增）

### 4.1 事实与判断依据（为什么 plugin.json 里没有依赖声明）

本包原先把「七维量规的唯一执行源」放在**包外**的用户级 skill `teaching-ppt-studio`，
而 `.codebuddy-plugin/plugin.json` **没有任何依赖声明字段**——
WorkBuddy 专家包清单规范（`plugin-json-spec.md`）的字段全集分四组：
基础字段 / 类型字段 / 资源声明（`agents`、`skills`）/ 展示字段 / Team 专用字段，
**其中不存在** `dependencies` / `requires` / `skillDependencies` / `pluginDependencies` 一类字段；
WorkBuddy 内置 11 个插件的清单顶层键也均无依赖字段；
平台自带的清单校验脚本
`<WorkBuddy>/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts/validate_expert.py`
对 plugin.json 的校验只覆盖必填 / 类型 / 展示 / Team / `agents` / `skills` 路径，**无依赖概念**
（该脚本属**平台自带**、不在本包 `scripts/` 内——引用它只作事实依据，不作本包论据）。

**结论（v3.17.0 判断）**：平台**不支持**依赖声明字段 →
**不向 plugin.json 塞平台不认的键**（可能被忽略，也可能触发未知键校验失败）；
改用「登记 + 可执行检查」把静默失效变成显式可见。

### 4.2 v3.17.0 的三步处置

1. **内化**：量规执行源改为包内 `references/seven-dimension-rubric.md`
   （内化自 `teaching-ppt-studio` v2.6.0 的同名文件，已去领域化；上游副本仅作比对更新用）
2. **登记**：`references/dependency-manifest.yaml` —— 外部依赖的包内 SSOT
   （逐条写明用途 / 探针路径 / 探针文件 / 内化兜底 / 缺失文案 / 是否阻断）
3. **显式化**：`scripts/check_external_deps.py` —— 可执行检查

### 4.3 可执行检查

```bash
# 默认不阻断（缺失只影响「与上游比对更新」，不影响本包使用）
python3 scripts/check_external_deps.py

# 严格模式：缺失 exit 1（供 CI / 发布流程显式启用）
python3 scripts/check_external_deps.py --strict

# 机器可读输出
python3 scripts/check_external_deps.py --json
```

缺失时的实际输出（**必须真打出来，不许假装依赖存在**）：

> ⚠ 外部 skill teaching-ppt-studio 未安装 → 本包已内化 references/seven-dimension-rubric.md，以包内版本为准；外部副本仅用于比对上游更新

**纪律**：依赖缺失**不得阻断**本包的正常使用（内化就是为了自包含），
但**不得**因此假装依赖存在——「未安装」这句必须真的打出来。

### 4.4 与体检的衔接（跨批需求，本批不改 scripts/）

体检第 23 项由 `scripts/ensure_settings.py` 维护（属另一批次）。
落地方式（主理人派单时可直接照抄）：

- 在体检中调用 `scripts/check_external_deps.py` 的 `main([])`，或直接以子进程方式执行
- **必须按「提示级·不阻断」接入**（与第 18 项死配置巡检同级）——依赖缺失**不阻断**发布
- **假阳性为零**：只认 `references/dependency-manifest.yaml` 里登记的依赖，
  **不做目录名猜测**、不扫全盘 skills 目录
- 建议输出格式与既有项一致：`[23/22] ✓/ℹ …`（提示级，不改 `N = 22`）

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
> 装配脚本 `vendor/shared-core/assemble_spawn_prompt.py` 的 `check_task_package()` 目前**只校验四要素**：
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
   python3 "$EXPERT_DIR/scripts/assemble_domain_prompt.py" \
     --member <member-id> --phase <阶段号> --task-id <task_id> \
     --task-file <任务包文件> --run-dir "$RUN_DIR" --check-task-package \
     --collapse-artifact "$RUN_DIR/_collapse/collapse_<task_id>_<域id>.json" \
     --out "$RUN_DIR/spawn__<member-id>.md"
   ```
   脚本确定性完成：成员 MD 全文注入 + **域上下文注入**（见下 §2.1）+ **`config/visual-rules.yaml` / `references/*.md` / `scripts/*.py` 绝对路径清单**（本团无 skills 目录，这些就是成员的资源根，必须显式下发）+ 白名单校验（非 `plugin.json` 成员 exit 2）+ 任务包**四要素**校验（缺 exit 4；**第五要素 `acceptance_criteria` 脚本暂不校验**，见 §一 注）+ 落盘契约。

   > **为什么用 `assemble_domain_prompt.py` 而不是 `assemble_spawn_prompt.py`**（v3.17.0 批次 B 实测）：
   > 后者是**联邦 shim**，转调 shared-core 的装配实现（本包内另有一份快照 `vendor/shared-core/assemble_spawn_prompt.py`）；
   > 而 shared-core 的实现**从不读 `_collapse/` 目录、也不读 `config/domain-profiles.yaml`**——
   > 2026-10-24 端到端实测：坍缩产物已 `status=confirmed / effective=true`，
   > 装配产物中域人格关键词命中数仍是 **0**。
   > 本包**不修改 shared-core**（影响另外 4 个包，需另案上提），
   > 而是在包内新增 `scripts/assemble_domain_prompt.py` 做**基础装配 + 域上下文注入 + frontmatter 键补偿**。
   > `scripts/assemble_spawn_prompt.py` 保留为**基础装配入口**（不带域上下文），仅供不需要域人格的场合。

2. **spawn**：`Agent(name=<member-id>, subagent_type="general-purpose", prompt=<上一步产物>)`
3. **收产出**：以落盘文件 `<RUN_DIR>/<task_id>__<member-id>.md` 为准，SendMessage 仅作摘要通知。文件缺失 = 未交付。

> ⚠️ 本团成员实测可能**无 Write 权限**（仅有 Bash/Read/Grep/Web 系）。落盘契约已内置回退：无 Write 时用 Bash heredoc 写文件。主理人下发时不要假设成员能 Write。

### 2.2 洞察载体写入契约（v3.21.0 · 多专家单载体）

> **定位**：成员除了"我这一轴做了什么"的**专业产物**（证据包 / 教学蓝图 / 检索单），
> 还要把"我针对**哪些目标**提了哪些**洞察条目**"写进**同一份载体**的分片。
> 载体是本次任务多专家洞察的**唯一事实源**（下游轮报/冻结/验收全部从它投影）。
> **两者不是替代关系**：专业产物照旧写，载体是**洞察的汇入通道**。

**为什么要有（真实病灶，非假设）**：闸 2「严真奥 → 苏学法」与闸 3「苏学法 ∥ 屠明熙」并行，
但产物落**三处**（`evidence/证据包.md`、`<task_id>__pedagogy-architect.md`、`_search_requests/*.md`），
同一页/同一模块的内容、教学、视觉建议**分散无共同落点** ⇒
① 冲突无处显形（严真奥要加证据、苏学法要拆页、屠明熙要加图，三者可能互斥）；
② 主理人合并要靠 800 字摘要（**必然丢信息**）；
③ 追溯断裂（这条洞察谁提的、改没改、为何没改散在三处）。

**路径约定**（`config/harness.yaml#insight_carrier` 是唯一源）：
- 载体：`<RUN_DIR>/<carrier_rel>`（默认 `_insights/carrier.json`）——**主理人合并后写**
- 分片：`<RUN_DIR>/<parts_rel>/<member_id>__<axis>.json`（默认 `_insights/parts/`）——**成员写**

**分片结构**（schema 唯一源 = `references/insight-carrier.yaml`）：
```json
{"task_id": "...", "member": "dvm-content-expert", "axis": "content", "round": 1,
 "entries": [{"insight_id": "s12-C-01", "target_id": "s12", "target_kind": "page",
              "axis": "content", "expert": "dvm-content-expert",
              "proposal": "……具体改什么", "rationale": "……依据",
              "severity": "P1", "status": "proposed",
              "evidence": "PMID/DOI 或 文件:行号（content 轴必填）"}]}
```

**"目标上互斥、载体上共享"**（本契约最要紧的一条）：
- 同一 target 上**不同轴**的条目并存**不算重复劳动**——三轴看的是同一份内容的三个侧面，
  合起来才是完整洞察。脚本只检出「多轴并存 ⇒ 待人工裁决」，**不判是否互斥**（语义判断归人）。
- **同轴内不得做两遍**（那才是重复劳动）。
- 成员**只写自己轴**的分片，不得改别人的分片，也不得直接改合并后的载体。

**⚠ 闸 3 是真并行**（苏学法 ∥ 屠明熙）——两方同时写**同一份文件会丢更新**
（本包 `_StateLock` 的由来）。所以：**各写各的分片，脚本合并，下游只认合并后的载体**。
主理人合并命令：`harness.py insights add --part <分片> --workspace <W>`。

**成员 MD 的落盘契约段必须写明**：分片绝对路径（按 `member_id` + `axis` 算）、
分片 JSON 骨架、必填字段、以及"只写自己轴"的纪律。装配器（`assemble_domain_prompt.py`）
负责把这段注入成员 prompt——**注入是唯一合法路径**（同域人格注入的先例：
人设不注入，规范就不会被遵守）。

### 2.1 域上下文注入（v3.17.0 批次 B · P0 强制）

**域人格进 prompt 的唯一合法路径** = 装配器注入。装配产物中「角色定义」段**之后**、「任务包」段**之前**
会多出一段：

```
==================== 域上下文（v3.17.0 坍缩产物注入） ====================
【生效状态】✅ 域人格已生效（status=confirmed / effective=true）
【所属域】<域 id>（<域中文名>）
【坍缩产物】<产物绝对路径>
【一、域人格】… 【八、知识锚点】
==================== 域上下文结束 ====================
```

内容源 = **坍缩产物 JSON**（`role_persona` / `content_axes` / `evidence_hierarchy` /
`image_channel` / `safety_redlines` / `knowledge_bases` / `terminology` / `knowledge_anchor`），
域档案 `config/domain-profiles.yaml` 补缺并提供**通用兜底**段。

**参数**：

| 参数 | 说明 |
|---|---|
| `--collapse-artifact <路径>` | 显式指定坍缩产物路径（**推荐**）；缺省时按 `--run-dir` / `--workspace` 自动发现 `_collapse/` 下产物 |
| `--domain-profile <路径>` | 域档案路径（默认本包 `config/domain-profiles.yaml`） |
| `--run-dir <路径>` | 本轮运行目录（同时用于产出落盘契约与坍缩产物自动发现） |
| `--workspace <路径>` | 工作区（用于 `<workspace>/.harness-runs/*/_collapse/` 自动发现） |

**安全语义（不满足即不注入，绝不静默按已确认处理）**：

| 情形 | 装配产物中的表现 |
|---|---|
| 坍缩产物 `status=confirmed` **且** `effective=true` | 完整八段域上下文注入 |
| 坍缩产物未确认（`status != confirmed` 或 `effective != true`） | **不注入**域人格 + 显式警告「⚠️ 域人格未生效（未确认）」 |
| 域档案读不到 / 档案中无该域 | **不注入**域人格 + 「⚠️ 域档案不可用——**本条按通用兜底处理**」+ 通用兜底人设 |
| 无坍缩产物 | **不注入**域人格 + 「⚠️ 未找到坍缩产物」+ 通用兜底人设 |
| 成员在该域的绑定为 `domain_neutral` | 不注入域人格 + 「ℹ️ 本成员在本域为 `domain_neutral`」 |

> ❌ **严禁**在缺域档案时静默回落某个**具体域**（尤其不得回落 animal-medicine）——那是"看起来能用、实际跑偏"。
> 通用兜底只给"内容权威"这一档通用身份与通用证据轴，**不含**任何域专有信息。

**回归守卫**：`python3 -m pytest scripts/test_spawn_injection.py -q`
（覆盖：正文逐字节一致 / frontmatter 三键 / 已确认注入 / 未确认拒注入 / 兜底标注 / 端到端 route→confirm→装配）。


### 严禁

- ❌ 不跑装配脚本直接 spawn
- ❌ **域未确认就 spawn 内容专家**（坍缩产物 `status != confirmed` 或 `effective != true` 时，
  装配器会拒绝注入域人格并打警告——此时 spawn 出去的是"无域上下文的通用内容权威"，
  等于让成员冒充专家）
- ❌ 缺域档案时**静默回落某个具体域**（尤其不得回落 animal-medicine）——只允许带标注的通用兜底
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

### 4.4 与体检的衔接（v3.17.0 如实登记：**未接入**）

**当前实况：本检查尚未并入体检**——它是一个独立可执行脚本，需手动或由 CI 调用：

```bash
python3 scripts/check_external_deps.py            # 默认不阻断；缺失时明确打印提示
python3 scripts/check_external_deps.py --strict   # 严格模式：缺失 exit 1
python3 scripts/check_external_deps.py --json     # 机器可读输出
```

- 登记表（唯一源）：`references/dependency-manifest.yaml`
- 判据边界：只认登记表里登记的依赖，**不做目录名猜测**、不扫全盘 skills 目录；
  依赖缺失**不阻断**本包使用（量规已内化到 `references/seven-dimension-rubric.md`，以包内版本为准）
- ⚠️ **不要再写「待并入体检第 23 项」这类承诺**：
  体检第 23 项现为「域绑定残留巡检」，与依赖检查无关；
  `references/dependency-manifest.yaml#checker.integration_status` 已明令「勿再写待并入第 23 项」。
  若将来要接入体检，须**新开一项**（体检当前共 **23** 项），并同步改那一行登记。
- 副作用登记：`references/dependency-manifest.yaml` 的 `checker.path` / `invocation` /
  `scripts/check_external_deps.py` 的文件头，是**同一件事的三处副本**——
  改路径须三处同改，体检第 17 项（悬空脚本引用）只保证「引用的文件存在」，
  **不保证「三处指向同一处」**。

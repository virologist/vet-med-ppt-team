# vet-med-ppt-team 专家团 · Harness 全链路诊断与重构报告

- 对象：`vet-med-ppt-team`（动物医学教学PPT智造团，Team 型专家，v2.1.0）
- 包内安装路径：`/Users/biodog/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team`
- 源码/导出仓库：`/Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team`（`packages/vet-med-ppt-team/`）
- GitHub：`https://github.com/virologist/vet-med-ppt-team`
- 实测日期：2026-09-29
- 事实/推测标注：凡带 🟢 者为本次实测可复现的硬证据；带 ⚪ 者为基于文件内容的静态推断

---

## 1. 定位与通读：现状与调用入口

### 1.1 物理构成

| 类别 | 文件 | 作用 |
|---|---|---|
| 清单 | `.codebuddy-plugin/plugin.json`（WorkBuddy 侧）、`.claude-plugin/plugin.json`（Claude Code 侧） | 声明 `expertType: team`、`leadAgent`、`memberAgents`、成员 displayName/avatar/profession |
| 角色配置 | `agents/vet-med-ppt-team-team-lead.md`（主理人 全课吉）+ 4 个成员 MD | 系统提示词本体；frontmatter 仅 `name/description/displayName/profession/maxTurns` |
| 编排路由 | 主理人 MD「直调路由表」「任务复杂度分级 L0–L3」「预设 Workflow WF-1/2/3」「六阶段索引表」 | 纯自然语言路由，无代码、无状态机文件 |
| 循环控制 | `references/sop-stages.md`（六阶段 SOP）+ `references/adjudication-rules.md`（裁决与终检）+ `references/batch-surgery-sop.md`（版面外科 SOP） | SOP 以 Markdown 描述，靠主理人自觉遵守 |
| 状态持久化 | `<workspace>/.workbuddy/task_state.json`（无 schema 约束）、`deck_registry.json`（课件台账） | 手写字典，无版本、无校验 |
| 确定性工具 | `scripts/verify_deck.py`（分级门禁，退出码 0/1/2/3/4）、`surgery_deck.py`（版面外科）、`inject_notes.py`（讲稿注入）、`ensure_settings.py`（包体检/自愈） | 真正的机器执行层，是全包最有价值资产 |
| 单一数据源 | `config/visual-rules.yaml` | 视觉红线参数；verify_deck 与批量脚本同源消费 |

### 1.2 调用入口（三条）

1. **WorkBuddy 专家市场选中该专家** → 宿主加载 `agentName: vet-med-ppt-team-team-lead` 作为会话主 agent → 主理人按 SOP `TeamCreate` → `Agent(spawn, name=成员ID)` → 成员 `SendMessage` 回传。
2. **Claude Code / Desktop**：读同一份 `agents/*.md`，用 `TeamCreate/SendMessage` 单兵调用（README 声明兼容）。
3. **脚本直调**：`python3 scripts/verify_deck.py <课件.pptx> --hours <课时> --level P0|P1|all`（不依赖任何 agent，是唯一"确定性"入口）。

### 1.3 现状判断（一句话）

> 这是一个**「重提示词、轻 harness」**的专家团：专业方法论的密度极高（六阶段门控、分级门禁、反自评红线、Maker/Checker 分离都写得很到位），
> 但**编排层 100% 依赖主理人的自然语言自觉**——没有状态机代码、没有成员可用性预检、没有预算护栏、没有执行日志、没有回归测试。
> 真正落地的确定性能力只有 `scripts/` 下 4 个脚本，其余全靠 LLM 现场发挥。

🟢 证据：`agents/*.md` frontmatter 只有 5 个字段，**无 `tools:` 白名单**；包内无任何 `state machine` / `runner` / `logger` 代码；`scripts/` 无任何 token/耗时/日志埋点（`grep token|elapsed|logging` 全空）。

---

## 2. 实测：一轮真实任务的完整轨迹

任务 T 见 `baseline_trace.md`。结论先行：

| 指标 | 基线实测值 |
|---|---|
| 计划调度成员 | 4（严真奥/苏学法/屠明熙/郅作基） |
| 实际成功调度 | 2（严真奥=静默降级为 general-purpose；屠明熙） |
| 调度失败 | 苏学法 ×3（`Task agent pedagogy-architect is not available`） |
| 阶段完成度 | 阶段0 ✅ / 阶段2 ✅ / 阶段3 ❌阻断 / 阶段5 ❌未达 |
| 门禁脚本 | 4 次调用，1 次崩溃（exit 4，无 traceback）、1 次通过 |
| token 计量 | **不可得**——包内外均无埋点，平台未向主理人暴露成员用量 |
| 耗时 | 严真奥 ≈5min（35,503 bytes 产出）；门禁脚本 0.03–3s；苏学法 = ∞（阻断） |

### 关键实况

1. 🟢 **苏学法不可调度，且无降级路径** → 按现行规则（"Agent tool 不可用＝任务阻断，禁止代写"）整条流水线在阶段 3 停摆。这是"正确性"与"可用性"的直接冲突：红线保护了质量，却因缺少 fallback 让任务彻底失败。
2. 🟢 **严真奥被静默降级**：团队注册文件里 `agentType=general-purpose`（而非 `dvm-content-expert`），即成员的 MD 人格/红线**未被注入**，平台不报错，主理人无从察觉。
3. 🟢 **门禁脚本会崩溃**：`verify_deck.py "7. 禽流感.pptx" --level all` → `运行错误：'<' not supported between instances of 'NoneType' and 'float'`，只打印一行、无 traceback、无页码定位。主理人无法区分"课件有问题"还是"脚本有 bug"，v2.0.0 宣称的"抗崩溃"未覆盖此路径。
4. 🟢 **成本不可观测**：全程没有任何 token/耗时/调用次数的记录落盘，A/B 对比只能靠人工计时与字节数代理。

---

## 3. 九维度诊断（逐条：严重度 + 证据 + 影响）

### D1 角色职责划分

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 1.1 | 成员职责"一岗多责"膨胀：屠明熙=规则引擎+外科判据+抽样复核；郅作基=门禁+台账+制作包。违背单一职责 | 中 | `visual-slide-designer.md` 三大职责、`ppt-producer.md` 三大职责 |
| 1.2 | 郅作基"从零创作制作包（路径A）"长期空转（历史 0 次 spawn），职责与路径 B 并存造成路由歧义 | 中 | `ppt-producer.md` 职责3；SOP 阶段5 又规定"路径B默认" |
| 1.3 | 主理人既做编排又可在 L0–L1 亲自施工（含 XML 手术），Maker/Checker 在其身上合并 | 中 | 主理人 MD 协作规则 2："L0-L1 单件任务主理人可直接施工" |
| 1.4 | 苏学法的 `speaker_note`/`page_role` 是砍页与 P2 达标的关键产出，但她是**单点**，不可调度即全链断 | 高 | 本次实测苏学法 ×3 失败 → 阶段3/5 全断 |

### D2 提示词质量

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 2.1 | 主理人 MD 155 行、成员 MD 60–140 行，密度高但**规则堆叠**：v1.5–v2.1 的补丁逐层叠加，出现"强制/必做/不得/禁止"共 60+ 处，执行时优先级不明确 | 中 | 各 MD 全文 grep |
| 2.2 | 同一规则散落三处（主理人 MD / sop-stages.md / adjudication-rules.md），更新易漂移 | 中 | "分级门禁"同时出现在主理人 MD:71、sop-stages.md:58-63、adjudication-rules.md:48-49 |
| 2.3 | 大量"软指令"无法执行：如"超时>5min未回传则降级"——LLM 无法可靠计时 | 高 | sop-stages.md 阶段3 第1条 |
| 2.4 | 规则无版本号/生效日期，只有零散 `(v2.0.0 新增)` 标记，无法机器校验一致性 | 低 | 各 MD |

### D3 上下文传递与隔离

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 3.1 | 成员产出全文回传主理人再转发，主理人上下文线性膨胀（单次证据包即 35KB） | 高 | 实测 `baseline_stage2_evidence.md` 35,503 bytes |
| 3.2 | 无"只传路径不传内容"的强制约定（SOP 仅在阶段4提"只传diff"） | 高 | sop-stages.md 阶段4 |
| 3.3 | `task_state.json` 无 schema，实测 32 个顶层键、27KB、stage_history 单条摘要 300+ 字，且出现 `stage_6_status`（SOP 只有 0–5 阶段） | 高 | 实测工作空间 `.workbuddy/task_state.json` |
| 3.4 | `current_stage` 取值混杂（"0"/"M5A2" 都出现），状态机字段被当便签用 | 高 | 同上 |
| 3.5 | 冷启动恢复只写"Read 最小集"，无落盘校验 | 中 | sop-stages.md Compaction 节 |

### D4 工具权限最小化

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 4.1 | **所有成员 frontmatter 无 `tools:` 白名单**，默认继承宿主全部工具（含 Bash/Write） | 高 | 5 个 `agents/*.md` frontmatter 仅 5 字段 |
| 4.2 | 严真奥本应只读+检索，实际可写文件；郅作基需要写权限，二者无差别 | 高 | 同上 |
| 4.3 | 无"脚本前置断言"的机器强制：SOP 要求的注入四断言在两个新脚本里 0 实现 | 高 | `grep min_font_pt|require_empty_slot|max_overlap|assert` in surgery_deck.py/inject_notes.py = 空 |

### D5 路由与交接机制

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 5.1 | 路由完全靠主理人自然语言判断（复杂度分级 L0–L3 无判定代码） | 中 | 主理人 MD 分级表 |
| 5.2 | **成员可用性无预检**：不做"开工前探测 4 个成员能否 spawn"，失败后才暴露 | 致命 | 实测苏学法 ×3 失败 |
| 5.3 | **无降级路由**：成员不可用时的唯一选项是"阻断"，无备用通道（同角色通用子代理+注入 MD / 脚本流水线） | 致命 | 主理人 MD 回退表："Agent tool 不可用＝任务阻断" |
| 5.4 | 成员间禁止直连，全部经主理人中转 → 主理人是带宽瓶颈也是单点故障 | 中 | 协作铁律 3 |
| 5.5 | 回传 schema 六字段靠成员自觉，无校验器 | 中 | 主理人 MD 下发任务包 schema |

### D6 Loop 的迭代与终止条件

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 6.1 | ReAct"单缺口≤3轮/累计≤15轮"写在 MD 里，**无计数器可强制** | 高 | dvm-content-expert.md 工作流程 3 |
| 6.2 | 阶段返工"≤2 轮"无计数；任务包里没有 retry budget 字段 | 高 | 主理人 MD；`task_state.json` 无 retry 字段 |
| 6.3 | "阶段4 小改动免确认"的判定边界模糊，可能反复横跳 | 中 | sop-stages.md 阶段4 |
| 6.4 | 无全局步数/耗时上限（maxTurns 200 是宿主级，不是任务级预算） | 高 | plugin 无 budget 配置 |

### D7 错误处理与重试

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 7.1 | `verify_deck.py` 顶层 `except Exception` 只打印一行信息，**吞掉 traceback**，无法定位 | 高 | verify_deck.py:632-637；实测崩溃无堆栈 |
| 7.2 | 崩溃根因（字号列表含 `None` 时 `min()` 返回 `None` 后与 float 比较）未做防御 | 高 | verify_deck.py:465-469；实测触发 |
| 7.3 | yaml 加载失败 → 静默回退内置阈值（仅 stderr 一行），护栏可被绕过 | 高 | surgery_deck.py:51-53 / verify_deck.py 同型 |
| 7.4 | 无重试策略：脚本失败、成员失败、工具失败都无 backoff/重试上限 | 高 | 全包检索无 retry 逻辑 |
| 7.5 | 门禁"运行错误 exit 4"与"P0 阻断 exit 1"在主理人侧未区分处置流程 | 中 | adjudication-rules.md 未提 exit 4 |

### D8 可观测性

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 8.1 | **无任何执行日志/追踪**：谁在何时被调度、耗时、失败原因，全部不留痕 | 致命 | 实测：只有人工手写的 `baseline_trace.md` |
| 8.2 | 无 token/成本埋点 | 高 | `grep token|elapsed|logging` in scripts = 空 |
| 8.3 | `deck_registry.json` 只记录课件门禁结果，不记录 agent 调用，二者无法关联 | 中 | registry schema |
| 8.4 | 无回归测试：4 个脚本无 test 文件、无 CI | 高 | 包内/仓库内无 tests/ |

### D9 成本与延迟

| # | 问题 | 严重度 | 证据 |
|---|---|---|---|
| 9.1 | 无任务级预算上限（token/时间/成员调用次数） | 高 | 全包检索 |
| 9.2 | L0/L1 也走 TeamCreate 建团，固定开销不随复杂度缩放（L0 明文免建团，但 L1 仍建） | 中 | 复杂度分级表 |
| 9.3 | 阶段1/阶段3 并行 2 成员，但产出全文回传，主理人 token 峰值不可控 | 高 | 实测证据包 35KB |
| 9.4 | 串行确认门最多 6 次，长任务人机往返成本高，无"批量确认"通道 | 中 | sop-stages.md 门控原则 |

---

## 4. 对标 Agent Harness 工程准则

| 准则 | 现状 | 差距 | 优先级 |
|---|---|---|---|
| **单一职责子代理** | 4 成员大体正交，但屠明熙/郅作基各 3 职责；主理人兼具 Maker 与 Checker | 中 | P2 |
| **显式状态机 Loop** | 六阶段靠 Markdown 描述 + `task_state.json` 自由字典；`current_stage` 取值混乱，出现 SOP 外的 stage_6 | **大** | P0 |
| **确定性路由** | 路由=主理人自然语言判断；无成员可用性预检、无降级路由 | **极大** | P0 |
| **上下文压缩与隔离** | 有"按需 Read"纪律与 compaction 最小集，但产出全文回传、状态文件 27KB/32 键无 schema | **大** | P0 |
| **工具白名单** | 全部缺失，成员默认拿全工具 | **极大** | P0 |
| **护栏与预算上限** | ReAct/返工/重试上限只写在 MD；无任务级预算；yaml 失败可静默回退 | **大** | P0 |
| **可评估性** | `verify_deck.py` 分级门禁是强项（真机器裁判、退出码语义清晰）；但无脚本回归测试、无执行 trace、无成本指标 | **大** | P0/P1 |

**一句话对标结论**：这个专家团在"专业方法论"与"机器裁判"上已经达到 harness 工程的优秀水准（分级门禁、单一数据源、反自评红线都值得保留），
缺的是**把方法论从"提示词里的纪律"下沉为"代码里的状态机、路由、白名单、预算与日志"**——即 Anthropic 所说 "Agents aren't hard, the harness is hard" 的那一半。

---

## 5. 重构方案与落地（v2.2.0）

原则：**保持原有核心目标与使用方式不变**（六阶段门控 + 四成员 + 分级门禁 + 视觉红线单一源），只在**编排层**新增确定性内核。

### P0（实测直接命中，必做）

| # | 文件 | 关键改动 | 缘由 |
|---|---|---|---|
| 1 | `config/harness.yaml`（新） | 显式状态机 `stages`（只认 0–5）、成员注册表（职责 + 工具白名单 + 降级通道）、L0–L3 路由表、预算护栏、上下文策略、trace 配置、退出码语义 | 编排层此前零代码，全靠自觉 |
| 2 | `scripts/harness.py`（新） | 7 个子命令：`preflight` / `route` / `state` / `budget` / `trace` / `gate` / `verify-artifact` | 把纪律变可执行、可计数、可追溯 |
| 3 | `scripts/verify_deck.py` | ① 越界检测几何含 `None` 崩溃修复 ② 重叠检测同样问题修复 ③ 字号 `min()` 遇 `None` 崩溃修复 ④ 顶层异常打印 traceback + 处置指引 ⑤ yaml 加载失败改硬失败（禁静默回退） | 实测一个课件撞出 3 个崩溃；且只打一行无法定位 |
| 4 | 5 个 `agents/*.md` | frontmatter 新增 `tools:` 白名单 | 此前成员默认继承宿主全部工具 |
| 5 | 主理人 MD + `references/harness-engine.md`（新）+ `sop-stages.md` | 规则修订：**"成员不可用＝阻断" → "先降级，后阻断"**；新增开工三步；阶段5 换统一门禁入口；落盘必须绝对路径且主理人机器核验 | 基线里苏学法 ×3 失败即整链停摆；屠明熙/郅作基自报落盘不实 |

### P1

| # | 文件 | 改动 | 缘由 |
|---|---|---|---|
| 6 | `scripts/test_harness.py`（新） | 10 条回归用例 | 本包此前 0 测试、0 CI，3 个崩溃正是后果 |
| 7 | 三处版本号漂移 | `packages/.../plugin.json` ×2 升 2.2.0；根 `marketplace.json` ×2 从 **1.5.1** 同步到 2.2.0 | 官方 `validate_expert.py` 只校验包内清单，根清单漂移 6 个小版本无人发现 |

### 未采纳 / 留作后续

- **拆细屠明熙/郅作基职责**（加第 5、6 个成员）：会改变使用方式与调用入口，且 4 成员正交性尚可，本轮不动。
- **L3 自动 RedTeam**：成本考量，维持"用户同意才跑"。

---

## 6. 验证：同任务重跑对比（diff）

同一任务 T、同一课件、同一受众与课时。

| 维度 | v2.1.0 基线 | v2.2.0 重跑 | 差异 |
|---|---|---|---|
| 苏学法（页表产出） | ❌ 3 次 spawn 全失败 → **阶段3 整链阻断，0 产出** | ✅ 降级通道产出：**20 页页表 / 60,853 bytes**，speaker_note 中位数 283 字（≥80 达标），page_role 20/20 | **从 0 到 1** |
| 静默降级 | ❌ 严真奥被登记为 `general-purpose`，无人察觉 | ✅ `preflight` 显式报 `degraded` 并给出处置建议 | 隐形 → 可见 |
| 郅作基（门禁） | ❌ 自报 P0=13/P1=25/备注 82.6%，**实测 136/81/64.4%**；自报落盘文件不存在 | ✅ 降级为 `script_pipeline`，由 `harness.py gate` 直跑，2 份课件复验完成、退出码语义正确 | 失真 → 机器判定 |
| 门禁（曾崩溃课件） | ❌ exit 4 崩溃，无 traceback，无法判定 | ✅ exit 1：P0=5 / P1=1 / P2=0% / P3=1，**可判定可修复** | 不可判 → 可判 |
| 产物真实性 | ❌ 屠明熙自报"已落盘 19.5KB"、郅作基自报"已落盘"，**全盘检索均不存在** | ✅ `verify-artifact` 当场判"文件不存在"并退回重做；苏学法返工后真实落盘 | 无校验 → 硬校验 |
| 执行日志 | ❌ 仅人工手写 | ✅ JSONL trace：spawn_failed×2、degrade×2、gate×4，可按成员/事件汇总 | 无 → 有 |
| 预算护栏 | ❌ 无（屠明熙 20m41s 无从判断是慢还是死） | ✅ `max_stage_minutes=20` + spawn/rework/react 计数，超限即上报 | 无 → 有 |
| 回归测试 | ❌ 0 用例 | ✅ **10/10 通过** | 0 → 10 |
| 成功率（本次 T） | 2/4 成员可用，阶段完成度 2/5 | 4/4 职责闭环（2 走降级通道），阶段完成度 5/5 | **显著** |
| token 成本 | 平台未暴露，不可得 | 平台未暴露，不可得（**诚实标注：本项 A/B 无法量化**） | — |

> 说明：token 计量在本环境不可获取，成本对比只能用"是否完成 / 耗时 / 返工次数"代理。
> 苏学法降级通道耗时 10m15s 完成基线根本无法完成的工作；屠明熙基线 20m41s 已超新内核的阶段预算，护栏会触发上报而非无限等待。

---

## 7. 落地与同步

- WorkBuddy 安装目录：已 rsync 同步（含新增 harness.yaml / harness.py / test_harness.py / harness-engine.md），`ensure_settings.py` 体检 4/4 通过（两侧清单均 2.2.0），安装目录回归测试 10/10 通过
- 导出/源码仓库：`/Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team`，CHANGELOG 双份一致（根 + `packages/.../docs/repo-meta/`），版本链自检 v2.2.0→v2.1.0→v2.0.0→v1.9.0→v1.8.0 完整
- GitHub：`virologist/vet-med-ppt-team`，commit + tag `v2.2.0` + Release（附打包 zip）

### 残余挂账（如实记录，不粉饰）

1. **成员自报失真未根治**：v2.2.0 只是加了机器校验（能拦住），成员仍会自报不实（3/3 命中）。治本需在平台侧暴露"成员是否真的写了文件"，本包做不到。
2. **token/成本不可观测**：平台未向主理人暴露用量，`harness.py` 只能记事件与挂钟，记不了 token。
3. **成员注册依赖宿主会话**：本次实测中 vet-med-ppt-team 的成员 subagent_type 未被平台解析（1 个静默降级、1 个不可用）。**在正常选中该专家的会话中是否如此，本次未能验证**——需在使用该专家的真实会话里再跑一次 `preflight` 确认。
4. **屠明熙/郅作基一岗多责**未拆，留待下一轮。

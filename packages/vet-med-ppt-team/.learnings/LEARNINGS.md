# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## 📌 `Status` 字段语义（v3.25.0 补定义 · 与 `FEATURE_REQUESTS.md` 共用同一套）

> ⚠ **此前无定义** —— 这是「登记状态与实际落地脱节」的根因：
> 每条 LRN 都写 `pending`，但**不区分「建议动作尚未做」与「建议动作已做完、这条经验转为常驻纪律」**，
> 于是下一轮盘点会**重复拾取已落地项**（v3.25.0 实测：6 条 LRN 全部标 pending，
> 其中 4 条的建议动作早已落地）。
> ⚠ **v3.25.0 初版两个文件的词表不一致**（本文件缺 `partial`/`resolved`），
> 且 `FEAT-20261022-001` 条目内部自相矛盾 —— 均已修正为下表这一套。

| 取值 | 含义 | 判据 |
|---|---|---|
| `pending` | 建议动作**尚未做**，有具体待办 | 能指出"还差哪一步没做" |
| `partial` | **部分实现** | 须写明已做哪部分、未做哪部分 |
| `applied` | 建议动作**已落地**（代码/流程已实现），经验转为常驻纪律 | 能在代码里指出落地位置 |
| `manual-only` | 建议动作**本质是人工纪律**，工具化收益低于成本 | 须说明为何不值得工具化 |
| `resolved` | **已闭合**（含"经实测否决、如实登记"这类闭合式结论） | 结论明确，无需再动 |
| `superseded` | 已被后续做法取代 | 须指向取代它的那条 |

> **纪律**：只有 `pending` / `partial` 才是待办；`applied` / `manual-only` / `resolved` / `superseded`
> **不再进入下一轮遗留盘点**（它们是常驻纪律或已闭合结论）。
> 状态更新须在**落盘的同一批**完成，不留到下轮。

---

## [LRN-20261022-001] best_practice

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: applied
**Area**: config

### Summary
"配了没人读"的死配置，判死前必须先分清「代码该读」与「主理人/流程该读」，否则体检会被塞满误报而失效

### Details
本项目连续三轮出现同型问题（v3.11.0 受众分层、v3.12.0 预算项与三源阈值、
v3.14.0 回退阈值），根因统一为**多处各自定义 / 配了没人读**。

修 v3.12.0 死配置体检时首版失败：把"`scripts/` 中无读取者"一律判死配置，
首跑报 **80 项**；放宽到路径段白名单仍报 **100 项**。抽样核实发现绝大多数是
`tools_whitelist`（成员工具权限）、`pass_rule`（AI 素养判据）、
`snapshot.*`（快照策略）——**有意义的配置，但本就由主理人/流程消费而非脚本**。

继续调白名单会退化成「为了让检查变绿而往白名单塞」，那是自欺欺人。
最终降级为 INFO 提示、不阻断：假阳性必须为零，否则体检会被绕过（真问题被淹没）。

### Suggested Action
新增任何"静态检查型"体检前，先用 2-3 个已知键跑一遍首版，确认误报率可接受；
若判据本质依赖人的意图（如"该谁消费"），直接设计为提示项而非门禁项。

### Metadata
- Source: error
- Related Files: scripts/ensure_settings.py, config/harness.yaml, config/domain_config.yaml
- Tags: 死配置, 体检设计, 误报率, 假阳性
- Pattern-Key: check.design.false_positive
- Recurrence-Count: 1
- First-Seen: 2026-10-22
- Last-Seen: 2026-10-22

### Resolution（v3.25.0 核实：已落地）
建议动作「新增静态检查型体检前先跑首版、假阳性优先」**已在代码层落地**：
- `scripts/ensure_settings.py` 有 `known_weak`（弱证据登记区，L1351+）与
  `known_leaf_only`（通用词裸段名白名单，L1298+）两处显式登记机制；
- 第 18 项据此从「阻断全盘判死」降级为分栏计数（代码读取 / 人读型登记 / 弱证据登记），
  与本条「假阳性必须为零」的核心主张一致。
⇒ 本条转为**常驻纪律**（`applied`），不再作为待办进入下一轮盘点。

---

## [LRN-20261022-002] correction

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: manual-only
**Area**: docs

### Summary
断言"某文件/某能力不存在"前，必须查全所有可能的根目录——我曾漏搜用户技能目录，误报了一个不存在的问题

### Details
2026-10-22 我在 v3.12.0 的 CHANGELOG 中写下
「`seven-dimension-rubric.md`（诊断量规唯一源）在本机 marketplace 仍不可解析」，
并列为待处理问题。

管家节点让继续处理时，我按该结论准备"修复"，先做了核实——结果该文件
**确实存在**：`~/.workbuddy/skills/teaching-ppt-studio/references/seven-dimension-rubric.md`
（9794 B，2026-10-17 更新）。

**错因**：当时只用 `find ... plugins/marketplaces` 搜了 marketplace 目录，
而 WorkBuddy 的用户级 skills 装在 `~/.workbuddy/skills/`，**根本没搜**。
我据此虚报了一个缺陷，浪费了一次立项与一轮讨论。

### Suggested Action
断言"不存在/不可解析"前，至少查两个根：① marketplace 插件目录
`~/.workbuddy/plugins/marketplaces/*/plugins/*` ② 用户技能目录 `~/.workbuddy/skills/*`
（以及 `~/.codebuddy/skills/*`）。宁可说"我查了 A、B 两处都没有"，
也不要说"不存在"。

### Metadata
- Source: user_feedback
- Related Files: CHANGELOG.md, agents/vet-med-ppt-team-team-lead.md
- Tags: 事实核查, 误报, 搜索范围
- See Also: LRN-20261022-001
- Recurrence-Count: 1
- First-Seen: 2026-10-22
- Last-Seen: 2026-10-22

### Resolution（v3.25.0 核实：人工纪律，不工具化）
建议动作「断言"不存在"前查两个根（专家包 marketplace + 用户技能目录）」——
v3.25.0 实测：`scripts/ensure_settings.py` 中**无**对应工具层实现
（`rg 'skills' scripts/ensure_settings.py` 无命中），即该条**从未进入代码**。
**定性为 `manual-only`**：它是**取证纪律**（"我说不存在"时必须给出查过的根），
不是可自动判定的检查项——「某文件是否存在」本身是事实核查，交给工具反而会
把"我查了 A、B 两处都没有"这个**证据链**降级成"工具说没有"。
⇒ 保留为常驻人工纪律（每次诊断/取证时自问），不再作为待办。
**配套措施**：本轮所有"不存在/未找到"结论均按此条附上**查过的根与命令**，可被他人复核。

---

## [LRN-20261022-003] best_practice

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: applied
**Area**: backend

### Summary
修并发/一致性缺陷必须做 before/after 对照实验，否则无法证明修复真的起作用

### Details
v3.12.0 修 Loop 状态的并发写缺陷时，我做了 `git stash` 对照实验：
同一工作区并发跑 20 次 `loop add-item`——
修复前**只保住 1/20 条**（丢 19 条），修复后 **20/20**。

若只跑修复后版本，看到"20/20 全对"无法排除"本来就没问题"或"测试不具区分度"。
对照实验才把"缺陷真实存在"与"修复确实有效"两件事分开证明。

同样地，第 19/20 项体检也都做了反例验证（改坏 → 应报警 → 恢复 → 应转绿）：
- 改 `visual-rules.yaml` 的 `body_min_pt` 不改 `_FALLBACK` → 精确报出漂移项并阻断
- 把"流转：交严真奥补查"还原成无载体写法 → 精确报出行号并阻断

### Suggested Action
任何"修好了"的断言，都要有一条能失败的测试证明它原本会失败。
检查类同此理：新增体检项必须反例验证过能抓到，否则可能一直是空转。

### Metadata
- Source: insight
- Related Files: scripts/harness.py, scripts/ensure_settings.py
- Tags: 对照实验, 反例验证, 并发, 假完成
- Pattern-Key: verify.prove_failure_first
- Recurrence-Count: 1
- First-Seen: 2026-10-22
- Last-Seen: 2026-10-22

### Resolution（v3.25.0 核实：已落地并已制度化）
建议动作「任何"修好了"的断言都要有一条能失败的测试证明它原本会失败」——
v3.25.0 实测：包内**反例/对照护栏已成体系**（5 个测试文件含对照或反例验证）：
- `scripts/test_dead_config_criteria.py` —— 第 18 项同名碰撞反例；
- `scripts/test_arch_drift.py` —— 镜像块与旧口径复活检测；
- `scripts/test_loop_state.py` —— 停等/冻结/预算触顶反例；
- `scripts/test_insight_carrier.py`、`scripts/test_fix_md_image_refs.py` —— 合并/引用修复反例。
且第 19/20 项体检的历史反例验证（改坏→应报警→恢复→应转绿）已写入代码注释。
⇒ 本条转为**常驻纪律**（`applied`），不再作为待办。

---
## [LRN-20261024-001] best_practice

**Logged**: 2026-10-24T20:40:00+08:00
**Priority**: high
**Status**: applied
**Area**: docs

### Summary
「机制已实现」不等于「机制已接入消费端」——v3.17.0 坍缩机制建了完整状态机却零消费者

### Details
v3.17.0 新增「专家团动态坍缩」：route --domain 落盘 → collapse confirm → 域人格生效。
状态机部分正确（pending→confirmed→effective 全通），但装配链
（shared-core/assemble_spawn_prompt.py）从不读 _collapse/ 目录，
端到端实测：坍缩已 confirmed/effective，注入产物中域人格关键词命中 = 0。
即：**产出侧写完了，消费侧没接线**。

### Suggested Action
凡新增「产出物→消费端」的机制，必须跑一次端到端实测断言**消费端产物里真的出现了该内容**，
不能只看产出侧的状态位。判据：机制类改动一律配"端到端断言"而非"单元测试"。

### Metadata
- Source: conversation
- Related Files: scripts/assemble_spawn_prompt.py, config/domain-profiles.yaml, config/harness.yaml
- Tags: mechanism-wiring, end-to-end-assert, collapsed-expert
- See Also: ERR-20261022-001

### Resolution（v3.25.0 核实：已修复 —— 但**本条描述的缺陷位置需更正**）
v3.25.0 主理人取证发现：本条描述的「装配链不读 `_collapse/`、零消费者」**已不成立**——
消费端**存在**，且接线完整：
- `scripts/assemble_domain_prompt.py` 已实现 `read_collapse_artifact()` /
  `discover_collapse_artifacts()` / `pick_collapse_artifact()`，
  并有 `--collapse-artifact` / `--run-dir` / `--workspace` 三个入参（L949+）；
- 端到端护栏 `scripts/test_collapse_domain_render.py`（**9 例 T1–T9**，每例带反例）已覆盖
  「route → collapse confirm → assemble」全链路。
⚠ **注意**：`shared-core/assemble_spawn_prompt.py`（**另一份**装配器，非本包的）
确实不读 `_collapse/` —— 但那是**别的专家团**的装配器，不是本条所说的链路。
⇒ 本条**已修复**（v3.19.1·S1 批次），转为常驻纪律（`applied`），不再作为待办。
**留下的价值**：本条确立的「机制类改动必须配端到端断言」这一要求，
已被 v3.23.0 F3 的 `test_inject_notes_assertions.py`（9 例）继续执行。

---

## [LRN-20261026-001] best_practice

**Logged**: 2026-10-26T22:20:00+08:00
**Priority**: high
**Status**: applied
**Area**: testing

### Summary
「末段键名同名」不能当作「该配置已被代码读取」的证据——静态判据必须落到**路径级**，否则判据本身会被键名撞车静默绕过

### Details
第 18 项（死配置巡检）自 v3.20.0 起是**阻断级**门，历轮主线（33 键 → 24 个 → …）全靠它兜底。
但原判定是 `n_full in norm_reads or n_leaf in norm_reads`——**末段键名同名即算已接线**。
而 `norm_reads` 收录 1268 个键名（`enabled` 27 处 / `note` 47 处 / `max_retries` 7 处，
其中 390 个**仅**来自字典字面量）⇒ 新增配置键只要与代码中任意键名重名就自动绿灯。

反向例（隔离副本实测）：未登记新段放叶名 `enabled` 的键 ⇒ rc=0 **漏检**；
同段放唯一名键 ⇒ 检出。**唯一差异是叶名是否撞车** ⇒ 同名碰撞可独立造成假绿。
量化：1433 个 alive 判定中**路径级强证据只有 22 个（1.5%）**，其余 98.5% 靠撞名。

修法：alive 改**三层证据**——A 路径级（AST 链式路径，≥2 段后缀）/ B 块级（父段整块取走，
计数可见）/ C 名级（**弱证据须登记 `known_weak`**，同样阻断）。
链式重建须支持本包两种主流读法：**节访问器约定**（`_section(cfg, "段名")`——段名以实参传入，
纯属性链在此断裂）与**局部变量绑定**（`x = f(cfg, "段名")`）。补齐后弱证据 17 → 4。

### Suggested Action
任何"静态判据型"门禁，上线前必须构造**反向例**证明它能失败：
① 找代码里高频出现的通用键名（enabled/note/target/count…）；
② 在未登记新段放一个同名键 ⇒ 门禁须转红；
③ 再放一个唯一名键 ⇒ 门禁须同样转红（证明不是无差别全盘变红）。
判据若只能靠"名字出现过"成立，它就不是判据，是巧合。

### Metadata
- Source: error
- Related Files: scripts/ensure_settings.py, scripts/test_dead_config_criteria.py, scripts/test_dead_config_disposition.py
- Tags: 静态判据, 路径级证据, 同名碰撞, 假绿, 反向例

### Resolution（v3.25.0 核实：已落地）
建议动作「静态判据型门禁上线前必须构造反向例证明它能失败」——
v3.25.0 实测：`scripts/test_dead_config_criteria.py` 已按此要求建立
「F1 反向例：同名碰撞不得造成假绿」，含 T1（同名撞车必须被检出）等用例，
且与 `scripts/test_dead_config_disposition.py`（登记处置）配套。
判据侧的三层证据（路径级 / 块级 / 弱证据）亦已落地于 `ensure_settings.py`。
⇒ 本条转为**常驻纪律**（`applied`），不再作为待办。

---

## [LRN-20261026-002] gotcha

**Logged**: 2026-10-26T22:20:00+08:00
**Priority**: medium
**Status**: manual-only
**Area**: tooling

### Summary
macOS 自带 BSD grep **不支持 BRE 的 `\|` 分支**——`grep -n "a\|b" file` 静默返回空，看起来像「不存在」

### Details
本轮取证时用 `grep -n "font_below_min\|overlap_exceeded\|..." scripts/inject_notes.py` 搜四断言，
返回空 ⇒ 差点误报「v3.22.0 G1 四断言未落地」。改用 `grep -E` / ripgrep（Grep 工具）后证伪：
四断言**确实存在**（`inject_notes.py:20-30, 69-121`）。

BSD grep 遇到不支持的分支表达式时**不报错、不输出**，退出码 1——
与「确实没有匹配」完全无法区分。这与包内长期强调的「假阳性必须为零」同源：
**取证工具本身也会造假绿**。

### Suggested Action
取证阶段的「搜不到」必须用**两种不同工具**各验一次（`grep -E` 与 ripgrep），
否则「未找到」会被当成「不存在」。
推论：报告里凡写「不存在 / 零处命中」的结论，都必须附**工具名 + 命令**，
以便他人用另一工具复核。

### Metadata
- Source: error
- Related Files: scripts/inject_notes.py, scripts/ensure_settings.py
- Tags: grep, macOS, BSD, 取证工具, 假绿, 可复核性

### Resolution（v3.25.0 核实：人工纪律，不工具化）
建议动作「取证阶段的『搜不到』必须用两种不同工具各验一次」——
v3.25.0 实测：`scripts/*.py` 中**无**对应工具层实现
（`rg 'grep -E|ripgrep' scripts/*.py` 零命中），即该条**从未进入代码**。
**定性为 `manual-only`**：这是**取证方法**（用两个工具复核同一个"搜不到"），
不是可自动判定的检查项——「某模式是否存在」是事实核查，
把它自动化反而会丢掉"我用了哪两个工具"这个**可复核性证据**。
⇒ 保留为常驻人工纪律，不再作为待办。
**配套措施**：本轮所有"零命中/未找到"结论均附**工具名 + 命令**
（如 `rg -n 'pattern' <path>` 与 `grep -E` 各一次），可被他人用另一工具复核。
**已验证有效性**：v3.25.0 取证中，成员正是靠双工具复核避免了一次误报。

---

## [LRN-20261104-001] correction

**Logged**: 2026-11-04T11:40:00+08:00
**Priority**: high
**Status**: pending
**Area**: config

### Summary

「**守卫断言了错误的事实**」比「没有守卫」更危险——它把一个已知错误焊死成不可证伪的公理。
本轮实测：`scripts/test_orchestration_v2.py` T2 断言 `harness.yaml#stages.1.parallel` 为真
（闸2 并行），而 `references/sop-stages.md#闸2 §1` 明确写「**串行**（v3.17.0 批次 B 修正），
理由是苏学法的二八难点清单依赖严真奥证据包里的『易误解』标注，存在真实数据依赖，
边界并不互斥」，`agents/vet-med-ppt-team-team-lead.md:198` 也承认「闸 2 实为**串行**」。
⇒ 真值在 yaml 一侧、事实在一侧、守卫站在了事实的反面。

### Why It Matters

- 守卫的价值来自「它代表事实」；一旦它代表的是**决策**（当时的并行决策），
  后续修正就必须**同时改代码和守卫**，任何一处漏改都会把修正变成红灯——
  于是修正被成本阻挡，错误被固化。
- 本例的后果是**双重伤害**：① 调度指令（并行）与真实数据依赖（串行）相反，
  必然多一轮往返；② 要改正必须先改 `test_orchestration_v2`，
  而改测试在「回归必须全绿」的收批门禁下会被误判为「改测试骗绿灯」。

### Suggested Fix

1. **守卫断言须区分两类**：`事实型`（FSOT 类唯一源的值，如版本号、键集合）
   vs `决策型`（可被裁定推翻的编排选择）。决策型守卫的断言文案须自带来源，
   如「本断言代表 v3.x 的编排决策，非事实；改决策时**连同本断言一起改**」。
2. **新增「真值三面一致性」巡检**：对每个带 `parallel` / `order` 的编排字段，
   同时比对 ① yaml 真源 ② SOP 叙述 ③ 守卫断言方向；
   三者不一致即判红，并指出**哪一面是孤岛**。
3. 本例具体修法（C2 批次）：`stages.1.parallel: no` + 新增
   `depends_on_members: [dvm-content-expert]`（成员级顺序依赖成为一等公民），
   同时把 T2 断言方向翻转为「闸2 应串行且顺序为 dvm → pedagogy」。

### Metadata
- Source: correction
- Related Files: scripts/test_orchestration_v2.py, config/harness.yaml, references/sop-stages.md, agents/vet-med-ppt-team-team-lead.md
- Tags: 守卫, 断言方向, 真值分裂, 编排决策, 固化错误

---

## [LRN-20261104-002] insight

**Logged**: 2026-11-04T11:45:00+08:00
**Priority**: high
**Status**: pending
**Area**: observability

### Summary

「**声明面 ↔ 生产流量**」与「**声明面 ↔ 声明面**」是两件完全不同的事，
而本包把后者当成了前者。`config/harness.yaml#observability.trace_events`
↔ `scripts/harness.py#TRACE_EVENTS_DECLARED` 的双向对账（B19）只保证
**两份手工声明互相对齐**，完全不涉及生产流量是否落在声明面内。

本轮实测（真实课件首跑 `T-xuexue-20261103`，工作区 114 事件 / 22 类）：
- **4 类生产事件逃逸**：`insight_carrier_init`（×44，占全量 38.6%）、
  `lint_passed`（×3）、`loop_start`（×1）、`agent_spawn`（×2，兼容别名）。
- **14 类声明事件工作区零产出**（含 `stage_exit`/`member_return`/`verify_tier`/`sediment`）。
- `insight_carrier_init` 单类占 38.6% 却**在账本里没有名字**——
  意味着「载体初始化」这一核心机制在 trace 里完全隐形。

### Why It Matters

- 指标体系（`references/intelligence-metrics.md` M1–M4）全部挂在
  `observability.trace_events` 声明的事件上。声明面与生产面脱节 ⇒
  **指标的口径是完备的，但采集管道是断的**。
- 更隐蔽的一层：本轮还实测到包内 trace 893 条的 `detail.task_id`
  **687/687 全为空串**（`team_create` 全部为空）⇒
  M1「GATE 停等总次数 / 任务数」的**分母根本不存在**。
  工作区较新的一批里 `gate`/`preflight` 的 task_id 是**字符串 `'None'`**
  而非 null ⇒ 聚合时会污染去重。
- 结论：**「口径定义层完成」不等于「指标可采」**。中间还隔着
  ① 事件是否真的落在声明面 ② 事件是否带得起归因键 ③ 聚合实现是否接线。

### Suggested Fix

1. **声明面单一化**：取消 `harness.py#TRACE_EVENTS_DECLARED` 这份
   **第二份手工同步的常量**，改为从 yaml **单向派生**；
   守卫反向断言「该常量不存在，或等于派生结果」。
2. **生产对账常态化**：`trace report` 已输出 `undeclared_events` /
   `declared_events_missing` 差集——升级为**收尾必检**
   （`trace report --strict`：工作区有未声明事件 ⇒ rc=1 并列出事件名与次数）。
3. **归因键 fail-closed**：`--task-id` 在闸内改为必填；
   `detail.task_id` 为空串 ⇒ 事件写入**拒绝并告警**，
   不静默落账（静默落账 = 账本有洞）。
4. **别名显式化**：`agent_spawn` 是 `spawn` 的兼容事件，
   应登记为 `trace_event_aliases` 而非独立事件；
   `insight_carrier_init`/`lint_passed`/`loop_start` 应正式入声明面。
5. **指标就绪判据**：每个 M 指标须补「**采集就绪**」判据
   （事件出现数 ≥ N 且归因键非空率 ≥ X%），未就绪输出「无数据」——
   遵 `intelligence-metrics.md` 的「无数据 ≠ 0」红线。

### Metadata
- Source: insight
- Related Files: config/harness.yaml, scripts/harness.py, scripts/test_batch_gate_b19.py, references/intelligence-metrics.md
- Tags: 观测性, 事件声明面, 生产流量, 任务归因, 指标可采性, 静态对账盲区

---

## [LRN-20261104-003] gotcha

**Logged**: 2026-11-04T11:50:00+08:00
**Priority**: medium
**Status**: pending
**Area**: config

### Summary

「**分流器已实现**」≠「**分流表已完整**」。本轮初判时看到
`harness.py loop worklist` + `loop_contract.fix_class_split` 已存在，
差点记成「B24③ 已闭环」。实际实测：
- `config/visual-rules.yaml#fix_class` 只登记 **7 种** issue type
  （`文字墙`/`课时不达标`/`缺目录页`/`缺题页`/`空白页` → ai_unfixable；
  `配色混乱`/`主框密度超标` → human）；
- 而 `scripts/verify_deck.py` 实产 **18 种** type；
- 差集 11 种（`字号过小`/`文字越界`/`元素重叠`/`缺备注`/5 种图表类）
  **全部落缺省 `default: ai`**。

⇒ 几何类缺陷（元素重叠/文字越界）被**系统性地判为「AI 可修」**——
这正是 N2「几何版式三轮证伪」的机制性根因：
**不是没接线，而是接了但表不完整 + 缺省策略是「猜」。**

### Why It Matters

- `default` 的语义选择决定了「漏判据」时的行为方向。
  `default: ai` = 「没登记就交给 AI 干」；在几何问题上已被证伪三轮。
  正确的默认方向是 **fail-closed**：没登记 ⇒ 落人工挂账区并标 `unclassified`，
  **宁可不修，不可乱修**。
- 同型陷阱在本包还有两处：
  ① 闸1 冻结清单文档写「六项」而 yaml 实为 9 项；
  ② `TEAMS_TOPOLOGY.md` 写「闸2 串行」而 yaml 写并行，且该文件
  **不在 `test_arch_drift` 的镜像对账清单内**（本轮 grep 确认零命中）。
  ⇒ 「查了没接线」与「接了但不全」要分开验，**后者更难发现**。

### Suggested Fix

1. **登记表完备性守卫**：`verify_deck.py` 产出的 type 全集
   ⊆ `fix_class` 登记表 type 全集——差集非空即判红
   （防「新增判据时忘记登记」）。
2. **缺省改 fail-closed**：`default` 从 `ai` 改为「落人工挂账区 + 标
   `unclassified`」；分流器输出**第 4 类** `unclassified`。
3. **清单项数守卫**：凡文档里出现「N 项清单」的表述，
   该 N 必须与 yaml 实际项数一致——纳入 `test_arch_drift` 镜像机制。
4. **镜像覆盖面盘点**：`references/` 与 `docs/` 下所有含编排事实的文件
   须逐个确认「在镜像对账清单内 or 明确声明为自由文本」——
   当前 `TEAMS_TOPOLOGY.md` 属**未声明的第三份编排事实源**。

### Metadata
- Source: insight
- Related Files: config/visual-rules.yaml, scripts/verify_deck.py, scripts/loop_contract.py, scripts/harness.py, config/harness.yaml, TEAMS_TOPOLOGY.md
- Tags: 分流表完备性, fail-closed, 缺省策略, 项数漂移, 第三事实源

---

## [LRN-20261104-004] correction

**Logged**: 2026-11-04T12:20:00+08:00
**Priority**: high
**Status**: pending
**Area**: scripts

### Summary

**守卫把「合法操作」误判为「生产缺陷」——比守卫漏判更危险，因为它会训练人忽略守卫。**

本轮体检第 7 项报「9/56 个套件不通过」，`test_trace_events` 首跑绿、
后续恒红。根因**不是环境问题**（此前误判为 broker 限制），
而是一条**结构性冲突**：

- `scripts/test_trace_events.py` 用 `_pkg_changed_files()`
  （= 包内 `git status --porcelain` 全量）当 `loop batch-open` 的
  **声明文件集**；
- `batch-open` 对每个声明文件跑 `_loop_a_scope_check`，
  而 `loop_a.scope` 白名单只有
  `scripts` / `config` / `references` / `agents` / `vendor/shared-core`
  + 6 个单文件——**`.learnings/` 不在其中**，
  尽管它是包内 **tracked 目录**（`git log` 有 3 次提交）；
- ⇒ 只要 `.learnings/LEARNINGS.md` 有任何未提交改动，
  `batch-open` 必返 rc=1 ⇒ `batch_open` / `batch_close` 两个事件
  **不落账** ⇒ 守卫「21 个声明事件全部有产出」断言的
  **missing 方向红**。

**可复现证据**：
1. 写入 3 条 `.learnings` 条目后跑守卫 → `通过 38 / 失败 1`；
2. `git stash` 掉该改动 → `通过 39 / 失败 0`（全绿）；
3. `git stash pop` → 立刻复红。

### Why It Matters

- **守卫噪声化 = 守卫失效**。登记一条经验是本包**纪律要求**的正常动作，
  却让体检门禁必红 ⇒ 人会学会「红灯是常态，可以先跳过」⇒
  守卫的边际价值归零。
- **淹没效应**：真实生产缺陷若恰好落在 `batch_open` 事件上，
  也会被这条误报**一起淹没**——**误报比漏报更贵**，
  因为它消耗的是「相信守卫」这份信用额度。
- **它把「工作区状态」当成了「生产行为」**：守卫测的应是
  *生产代码在给定触发路径下是否产出声明事件*，
  而非 *当前 git 工作区是否干净*。
  二者本无因果关系，却因共用 `batch-open` 的声明集而耦合到了一起。
- **与 [LRN-20261104-001] 同型**：「守卫断言了错误的事实比没有守卫更危险」。
  001 是断言了错误**口径**（伪并行），004 是断言了错误**状态**
  （工作区洁净度）——**两者都是把「可变量」写成了「守卫前提」**。

### Suggested Fix

1. **`loop_a.scope` 补入 `<包>/.learnings`**：它是包内 tracked 目录，
   本就在包内容之内，此前漏登记是**配置缺陷**。
2. **守卫声明集按 scope 过滤**：`test_trace_events` 的 batch-open
   声明集只取 scope 内的改动；scope 外的改动走
   「本批未声明/不可声明」独立分支，**不得混进 batch-open**。
3. **断言方向修正**：从「声明事件必须全部产出」改为
   「声明事件在**本用例所声明的触发路径**下产出」——
   不得把「工作区有未提交改动」报成「生产事件缺失」。
4. **固化回归**：新增用例「`.learnings/LEARNINGS.md` 处于修改态时，
   守卫仍 `通过 39 / 失败 0`」——**把这次的踩坑变成不可复现**。
5. **通用巡检**：凡守卫以「工作区/仓库状态」为输入的，
   一律检查它是否被当成了「生产行为判据」。

### Metadata
- Source: correction
- Related Files: scripts/test_trace_events.py, scripts/harness.py, scripts/loop_contract.py, config/harness.yaml, .learnings/LEARNINGS.md
- Tags: 守卫噪声化, 误报淹没, scope白名单, 工作区状态耦合, 声明集污染, 经验登记冲突

---

## [LRN-20261104-005] gotcha/medium · 改已登记的 config 段，必然触发免检区登记表连带刷新

### 现象
C0 批次改动 1 往 `config/harness.yaml` 的 `loop_a.scope` 加了一项（`.learnings`），
回归跑到 `test_dead_config_disposition` 报 **`FAILED (failures=2)`**：
- `test_T9_registry_segments_match_live` —— 「键集合已变（登记 9d37e352 ≠ 实时 cfbe9d7c）」
- `test_T39_backward_compatible_old_scheme_registry_still_passes`

### 根因
`references/inspection-zones.yaml` 的「免检区登记表」对每个已登记段存了**三个机算字段**：
`keys_sha256`（叶子路径集合摘要）、`key_count`（同口径键数）、`leaf_weak`（弱证据数）。
⚠ 口径是**叶子路径**（`ensure_settings.segment_key_count` / `segments_digest`），
**不是顶层键数** —— 所以 `loop_a` 顶层仍是 9 个键，但登记的 `key_count` 从 19 变 20。

⇒ **改 `harness.yaml` 里任何已被登记的段（含其子段），就必须连带刷新这三个字段**，
否则守卫必红。而这类红**长得像缺陷，其实不是**——是登记表陈旧。

### 实证
```
$ python3 scripts/sync_zone_registry.py          # 官方刷新器，dry-run
段总数 57 | 已对齐 56 | 需刷新 1 | 跳过(无实时对应) 0
  ↻ harness.yaml#loop_a: keys_sha256 9d37e3527fdf → cfbe9d7c85e1 | key_count 19 → 20
```
⇒ **恰好只有这 1 段需刷新**，其余 56 段全对齐 ⇒ 唯一变化源就是本次那一项。
刷新后复跑 `test_dead_config_disposition.py` → **36/36 OK**。

### 为什么值得单独记一条
1. **「守卫红了」的第一反应不该是「我改错了」**——也可能是「登记表陈旧」。
   判别方法：跑 `sync_zone_registry.py`（dry-run），看**需刷新段数**：
   恰好 1 段且该段正是我改的 ⇒ 连带刷新；多段 ⇒ 真改错了。
2. **这是「零遗漏」类教训的第 7 次触发**（前 6 次见 2026-11-03 记忆日志）。
   同一类联动反复出现 ⇒ 必须固化成流程动作，不能靠记忆。
3. **连带刷新会撑破 Loop A 声明集**：本例实际改动 4 个文件而声明集只有 2 个，
   按 `patch_discipline=minimal`（`extra = set(actual) - set(declared)`）收批必红。
   ⇒ **开批时必须把「连带会改的文件」一并写进 `--files`**，
   或在收批前发现缺口时走 `batch-gc --drop-open` 废弃重开（留痕可溯），
   **不得手工改 state 绕过纪律**。

### Suggested Fix
1. 改 `harness.yaml` 已登记段前，先跑 `sync_zone_registry.py`（dry-run）**预估连带范围**。
2. 把连带会改的文件**提前写进 batch-open 的 `--files`**。
3. 收批前若发现声明集不全 → `batch-gc --drop-open` 废弃 + 重开，**不手工改 state**。
4. 「守卫红了」先跑 dry-run 判别「连带刷新」vs「真缺陷」，再决定修哪边。

### Metadata
- Source: gotcha
- Related Files: references/inspection-zones.yaml, scripts/sync_zone_registry.py, scripts/test_dead_config_disposition.py, scripts/ensure_settings.py, config/harness.yaml
- Tags: 免检区登记表, 连带刷新, keys_sha256, key_count, leaf_weak, 声明集缺口, patch_discipline, 零遗漏第7次

---

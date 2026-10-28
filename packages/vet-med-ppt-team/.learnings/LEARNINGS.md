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

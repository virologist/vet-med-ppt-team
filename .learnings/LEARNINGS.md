# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20261022-001] best_practice

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: pending
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

---

## [LRN-20261022-002] correction

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: pending
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

---

## [LRN-20261022-003] best_practice

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: high
**Status**: pending
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

---
## [LRN-20261024-001] best_practice

**Logged**: 2026-10-24T20:40:00+08:00
**Priority**: high
**Status**: pending
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

---

## [LRN-20261026-001] best_practice

**Logged**: 2026-10-26T22:20:00+08:00
**Priority**: high
**Status**: pending
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

---

## [LRN-20261026-002] gotcha

**Logged**: 2026-10-26T22:20:00+08:00
**Priority**: medium
**Status**: pending
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

---

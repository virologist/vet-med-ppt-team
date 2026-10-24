# 架构设计 · Architecture

> 详细解释 vet-med-ppt-team 的设计原则与运行机制。

## 设计哲学

1. **学生学到什么，而非教师放了什么**——每一页服务于明确的学习动作（建立兴趣/激活先验/理解机制/辨认现象/比较鉴别/执行步骤/作出决策/练习反馈/总结迁移）
2. **课堂 PPT 是协同界面**——不是教材投影，不是论文摘抄，不是讲稿搬运
3. **专业准确性 > 生物安全 > 教学有效性 > 视觉表现力**——质量优先级写死

---

## 团队组成

> 🔒 **单一数据源纪律（v3.16.0）**：本表及全篇的**成员 / 阶段 / 门禁 / 工具白名单**事实以
> `config/harness.yaml#members` 与 `#stages` 为**唯一源**。本表只给人读视图
> （中文名 / 职业 / 一句话职责），**工具白名单与降级通道一律不在本文档复述**
> （平台禁 frontmatter `tools` 字段 + 单一数据源纪律，两处都写必然分化）。

| Agent ID | 中文名 | 职业 | 核心职责 |
|----------|--------|------|----------|
| `vet-med-ppt-team-team-lead` | 全课吉 | 课件总导演 | 五闸编排（stage 0–4）、跨角色裁决、对外唯一接口 |
| `dvm-content-expert` | 严真奥 | 动物医学内容专家 | Ima 知识库检索 + 证据分级 + 术语规范 |
| `pedagogy-architect` | 苏学法 | 教学法架构师 | 反向设计三层目标 + 形成性评价 + 互动节点 |
| `visual-slide-designer` | 屠明熙 | 视觉规则引擎架构师 | 版式选型 + 视觉层级 + 医学图像规范 |
| `ppt-producer` | 郅作基 | 课件执行工程师 | 写回门禁 + 跨任务台账 + 批量脚本驾驶 |
| `verifier` | 都衡言 | 独立验证官 | 独立复算与判决（V 层），不产内容、不施工 |

> **v3.16.0 补记**：本表此前**遗漏 `verifier`**（5 行），而 `harness.yaml#members` 自 v3.0.0 起
> 就登记了 5 名成员（含 verifier）——MD 与 yaml 分化无守卫，属 M7「四面楚歌」式不一致。
> 现已补齐，并加机器守卫（见文末「防漂移守卫」）。

---

## 五闸门控流水线（stage 0–4）

> 🔒 **本节的阶段 / 成员 / 门禁事实以 `config/harness.yaml#stages` 为唯一源，本节只解释动机与协作方式。**
> 改 yaml 必须同步下方「阶段镜像块」——守卫脚本 `scripts/test_arch_drift.py` 会逐项比对并失败。

### 阶段镜像块（机器比对用 · 真源 = `config/harness.yaml#stages`）

<!-- STAGE_MIRROR_BEGIN -->
stage 0 | 闸1 任务冻结 | members: - | gate: user_confirm | parallel: no
stage 1 | 闸2 设计（证据先行→蓝图·串行） | members: pedagogy-architect, dvm-content-expert | gate: user_confirm | parallel: no
stage 2 | 闸3 成稿（页表∥版式） | members: pedagogy-architect, visual-slide-designer | gate: script_check | parallel: yes
stage 3 | 闸4 交付（门禁+独立验证） | members: verifier | gate: gate_script+verifier | parallel: no
stage 4 | 闸4.5 案例三源核验（v3.3.0） | members: dvm-content-expert, verifier | gate: three_source_check | parallel: yes
<!-- STAGE_MIRROR_END -->

### 人读视图（同一事实的动机说明）

| 闸 | 名称 | 干活的人 | 是否并行 | 门禁 | 为什么要这么排 |
|---|---|---|---|---|---|
| 0 | 闸1 任务冻结 | 主理人（无常驻成员） | — | `user_confirm` | 澄清 + 判级 + 工具探针 + 页数口径与 `--hours` 冻结；用户未确认不得推进 |
| 1 | 闸2 设计（蓝图∥证据） | 苏学法 ∥ 严真奥 | **并行** | `user_confirm` | 蓝图的页数/目标依赖证据边界，证据检索也依赖蓝图的范围；串行会互相空等，故并行后一次性确认 |
| 2 | 闸3 成稿（页表∥版式） | 苏学法 ∥ 屠明熙 | **并行** | `script_check` | 教学列与版式列是同一页表的两列，不是两份文档；并行产出后由主理人合并，机器校验取代人工确认门 |
| 3 | 闸4 交付（门禁+独立验证） | 都衡言（叠加机器门禁） | — | `gate_script+verifier` | 门禁本质是脚本（`harness.py gate`），verifier 独立复判防自评失真；主理人自评不作放行依据 |
| 4 | 闸4.5 案例三源核验 | 严真奥 ∥ 都衡言 | **并行** | `three_source_check` | 严真奥补证据、都衡言独立复算，抽 `cases_library` 10% 未核验案例重跑 |

### 并行 / 串行的判据（易错点）

- **并行判据 = `harness.yaml#stages[*].members` 数组长度 ≥ 2**：stage 1 / 2 / 4 三名数组 → 并行开工；
  stage 0 无成员、stage 3 单成员 → 不并行（stage 3 是"机器门禁 ∥ 人复判"的双轨，不是成员间并行）。
- **旧文档把阶段 3 写成「苏学法→屠明熙 串行」是错的**：二者是页表的两列作者（并行），
  串行描述会让屠明熙空等苏学法整份产出，也是历史上页表被拆成两份文档的成因之一。

### verifier：独立的 V 层（不在产出链上）

- **角色**：v3.0.0 因「自评失真跨 4 个版本复发」而设，是**组织级独立裁判**，不是第 6 个产出者。
- **做什么**：闸4 独立复算门禁、裁判口径变更的第二签、存量 P0 挂账审判、对抗性抽检。
- **不做什么**：不产内容（严真奥）、不做教学设计（苏学法）、不做版式（屠明熙）、不施工（郅作基）、**不修红灯**。
- **与 ppt-producer 的关系**：郅作基 = Checker（执行门禁/施工），都衡言 = 判放行。
  二者**不得合并**——Maker/Checker 对偶是 R18 事故（258 处字号红灯写回无人拦截）留下的防线。
- **降级**：verifier 不可调度时退化为 `harness gate` + `verify-artifact` 组合（`harness.yaml#members.verifier.fallback`），
  且必须在交付物与 trace 中显式声明降级（`fallback.require_disclosure`）。

### 门控原则

- **固定 2 次用户确认门**：闸1 任务冻结、闸2 设计确认；确认权永远归用户，不得跳过
- **闸3 免确认**：改走「非作者交叉复检」（复检人 ≠ 产出人）——不是取消把关，是把人工确认换成外部验证
- **闸4 交付终审**：机器门禁（唯一裁判 `verify_deck.py`）+ verifier 独立复判，任一不过即打回
- **可合并 / 可压缩**：闸1+闸2 可合并确认；用户明说「直接继续」时可进一步压缩；**未明示不得跳闸**

---

## 关键约束（写死）

| 约束 | 说明 | 出处 |
|------|------|------|
| Ima 库路由 | 每次任务选 1-3 个库，禁止全库齐搜 | dvm-content-expert.md |
| 跨物种上限 | 跨物种主题最多 3 库 | dvm-content-expert.md |
| ReAct 硬限 | 单条缺口≤3轮循环；累计≤15轮 | dvm-content-expert.md |
| 蓝图确认 | 闸2（stage 1）用户未确认不得进入 stage 2 | vet-med-ppt-team-team-lead.md |
| 成稿把关方式（v3.16.0 纠正） | 闸3（stage 2）**免用户确认**，改走非作者交叉复检；旧文「阶段3 用户未确认不得进入阶段4」与 yaml 的 `script_check` 冲突，以 yaml 为准 | config/harness.yaml#stages.2 |
| GOF 红线 | 流感功能获得性突变内容直接拒绝 | vet-med-ppt-team-team-lead.md |
| 药物内容红线 | 强调诊断依据+处方合规+耐药+休药期+食品安全 | vet-med-ppt-team-team-lead.md |
| 隐私红线 | 不使用未授权患者/学生/养殖场可识别信息 | vet-med-ppt-team-team-lead.md |
| 路径决断权 | 路径A/B 选择由主理人下发，郅作基不自主决定 | vet-med-ppt-team-team-lead.md |
| 偏差裁决权 | handoff_out deviations_from_handoff 非空时主理人裁决 | ppt-producer.md |
| 并发防护 | task_state.json task_id 不匹配时停止推进 | vet-med-ppt-team-team-lead.md |

---

## 与 teaching-ppt-studio 的协同

详见 [协同协议章节](../README.md#跨工具协同)（README 主文档）

### 关键 schema（v2.1.0+）

**交接包** `*.handoff_in.json`：
```json
{
  "artifact_purpose": "make_new_from_scratch|optimize_existing|...",
  "from_team": "vet-med-ppt-team vX.Y.Z",
  "page_script_merged_table": [...],
  "global_visual": {"ratio":"16:9", "primary_color":"#145525", ...},
  "constraints": {"audience":"...", "duration_minutes":..., "page_budget":"..."},
  "red_lines": ["拒绝GOF", "药物剂量仅参考", ...],
  "output_path": "/abs/path/to/output.pptx"
}
```

**回传包** `*.handoff_out.json`：
```json
{
  "artifact": "/abs/path/to/final.pptx",
  "report": "/abs/path/to/report.md",
  "page_count": N,
  "checks": {"p0_geometry":0, "p0_offcanvas":0, "p1_count":N, "p2_count":N},
  "evidence_respect": {"annotation_coverage":"100%", "red_line_respected":[...]},
  "pending_items": [{"type":"image", "page":N, "desc":"..."}],
  "constraints_followed": {...},
  "deviations_from_handoff": []
}
```

---

## 文件结构详解

```
packages/vet-med-ppt-team/
├── .codebuddy-plugin/plugin.json    ← WorkBuddy 必需：定义 experts 元数据
│                                          - name, version
│                                          - displayName (en/zh), profession (en/zh)
│                                          - tags (3 个), quickPrompts (3 个)
│                                          - members 数组（含主理人+5成员）
│                                          - teamInfo (leadAgent + memberAgents)
├── agents/                           ← 6 份 agent MD（角色定义；文件名 = Agent ID）
│   ├── vet-med-ppt-team-team-lead.md ← 必含：五闸编排索引、协作铁律、裁决原则
│   ├── dvm-content-expert.md         ← 必含：Ima 路由表、记忆复用、ReAct 硬限
│   ├── pedagogy-architect.md         ← 必含：反向设计、三层目标、形成性评价三件套
│   ├── visual-slide-designer.md      ← 必含：版式选型、可读性红线、医学图像规范
│   ├── ppt-producer.md               ← 必含：写回门禁、台账、批量脚本驾驶
│   └── verifier.md                   ← 必含：独立复算、口径第二签、挂账审判
├── avatars/                          ← 6 张头像（512×512 PNG, ≤500KB）
│   ├── team.png                      ← 团队整体头像
│   ├── <member>.png                  ← 每个成员（含主理人）
├── settings.json                     ← Team 型必需：{"agent": "<lead-name>"}
├── README.md                         ← 子包说明（与根 README 不同）
└── vet-med-ppt-team.zip              ← 一键分发版
```

---

## 上下文交接（口径单一源）

| 口径 | 唯一源 | 人读说明 |
|---|---|---|
| 交接方式 | `config/harness.yaml#context.handoff_mode = path_only` | 成员只回传**落盘路径 + ≤800 字摘要**，全文不进对话 |
| 回传信封字段 | `references/result-envelope.yaml` | 必填六字段 `agent_id/task_id/phase/status/confidence/deliverable_summary`；各 agent MD 只引用不复述 |
| 产物字节上限 | `harness.yaml#budgets.max_artifact_bytes = 60000` | 超限强制降级为「只传路径 + 摘要」 |
| 跨成员信息流 | 经主理人中转（平台无 agent-to-agent 通道） | 合法通道三条：信封 `issues` 字段 / 共享目录落盘 / 下一轮任务包分派 |

---

## 历史沿革（已废弃口径，仅供回溯）

> 以下均为**已废弃**的历史口径，不得作为当前实现依据：
> - **六阶段门控流水线（阶段 0–5）**：v2.x 及更早的口径。v3.0.0 压缩为**四道闸（stage 0–3）**，
>   v3.3.0 追加 stage 4（闸 4.5 案例三源核验）形成现行**五闸**。
>   本文件在 v3.16.0 之前仍按六阶段描述流水线，属文档漂移，已于 v3.16.0 纠正。
> - **成员表 5 行（缺 verifier）**：v3.16.0 补齐为 6 行（主理人 + 5 成员）。
> - 旧页数口径「1 课时 18-28 页 / 2 课时 36-52 页」：v3.11.0 起以 `references/course-profile-defaults.md#2` 为唯一源。

---

## 防漂移守卫（v3.16.0 建 / v3.17.0 扩面）

> 起因：本文件在 v3.0.0 改五闸、**v3.3.0 加闸 4.5** 之后仍描述六阶段流水线并漏掉 verifier，
> 与 `config/harness.yaml` 分化**无人察觉、无机器拦截**。文档与真源之间没有守卫，必然继续漂移。
>
> **v3.17.0 扩面（实测同型漂移复发）**：上一轮只修了本文件，同型的
> `references/sop-stages.md`（闸号口径与闸4.5 章节未同步）与
> `references/harness-engine.md`（`current_stage` 取值范围未同步）**无人拦**——
> 守卫覆盖面只有一个文件时，同型文件必然继续漂移。现覆盖面改为**一组文档**，
> 清单 = `config/guard.yaml#guarded_docs`。

### 守卫实现

`scripts/test_arch_drift.py`（随 `python3 -m pytest scripts/ -q` 与 `ensure_settings.py` 第 7 项自动执行）：

| 断言 | 比对内容 | 失败意味着 |
|---|---|---|
| T1 | 「阶段镜像块」的 stage 集合 / 名称 / 成员 / gate == `harness.yaml#stages` 逐项 | 本文档与真源分化 |
| T2 | 镜像块格式可解析（5 段竖线分隔、stage 编号连续） | 有人改了格式没同步守卫 |
| T3 | 每个 stage 的成员都登记在 `harness.yaml#members` | 调度了未注册的成员 |
| T4 | 「团队组成」表的 Agent ID == {主理人} ∪ `members` 全键 | 成员表漏人 / 多出幽灵成员 |
| T5 | `agents/*.md`（除 team-lead）文件名集合 == `members` 全键 | 有 MD 未注册，或注册了没有 MD 的成员 |
| T6 | 「六阶段」仅出现在「历史沿革」章节之后 | 已废弃的旧口径复活 |
| T7 | 每个成员 MD 都把工具白名单指向 `config/harness.yaml` | 工具权限在 MD 与 yaml 各写一份 |
| T8 | `config/guard.yaml#cross_review_mapping` 与各 agent MD「你不做…」边界**取反**一致 | 闸3 交叉复检把关人被派给了被明文禁止接活的人 |
| T9 | **受守卫文档**（`guard.yaml#guarded_docs` 清单）的阶段镜像块 == `harness.yaml#stages` 逐项 | 清单里的文档与真源分化（含缺镜像块） |
| T10 | 受守卫文档正文不得出现旧口径词表（`guard.yaml#legacy_wording`） | 旧口径在正文复活 |

**口径唯一源 = `config/guard.yaml`**（v3.17.0 新增）：`guarded_docs`（覆盖面清单）、
`legacy_wording`（旧口径词表）、`cross_review_mapping`（闸3 交叉复检映射）三段均在此，
**不在脚本里硬编码**——改覆盖面 / 词表 / 映射只改 yaml，不改代码。

**为何不会假阳性**：守卫只解析镜像块 sentinel 之间的结构化行与两张显式表格，
不扫描散文；yaml 侧只做「stage 成员 ⊆ 成员注册表」的单向子集判定（新增注册成员不会误报）；
`docs/architecture.md` / `config/harness.yaml` / `agents/` 任一缺失时该断言 **SKIP 而非 FAIL**
（避免在 packages/ 副本等局部树里误报）。
**旧口径豁免区用可判定的声明式标记**（不靠关键词猜测）：① 标题行以「## 历史沿革」开头的章节
（其下的 `###` 子标题仍在区内）；② `<!-- LEGACY_HISTORY_BEGIN --> … <!-- LEGACY_HISTORY_END -->` 哨兵块。

### yaml 变动时的同步清单（改 `config/harness.yaml` 必须同步本文档的条款）

1. 增/删/改 `stages[*]` → 同步**全部受守卫文档**（`config/guard.yaml#guarded_docs` 清单）的「阶段镜像块」全行 + 本文件「人读视图」表 + 「并行 / 串行的判据」小节
2. 增/删 `members` 键 → 同步「团队组成」表，且 `agents/` 下必须有同名 MD
3. 改 `members[*].tools_whitelist` → **本文档不同步**（文档不复述工具清单，这是刻意的防分化设计）
4. 改 `context.handoff_mode` / `budgets.max_artifact_bytes` → 同步「上下文交接」表
5. 改 `gate_exit_codes` / `delta_gate` → 同步「关键约束」表
6. 增删受守卫文档 / 改旧口径词表 / 改交叉复检映射 → **只改 `config/guard.yaml`**（覆盖面与词表不写进本文档，避免第三份声明）

> 未覆盖项（已知，见 `.learnings/FEATURE_REQUESTS.md` 的 v3.16.0 条目）：
> 工具白名单与门禁退出码目前**只靠人工核对**——它们不在本文档复述，故无机器比对面。

---

## 演进历史

详见 [CHANGELOG.md](../CHANGELOG.md)

- v1.0.0：初始版本
- v1.1.0：内部迭代（11 项优化）
- v1.2.0：+ teaching-ppt-studio 协同
- v1.3.0：16 项协同 bug 修复
- v1.4.0：5 项并发/裁决/流转修复

---

## 已知技术约束

| 约束 | 原因 | 缓解措施 |
|------|------|----------|
| `~/.workbuddy` 目录疑似 OneDrive 同步竞态 | settings.json 已被删过两次 | UPGRADE.md 提供一键恢复命令 |
| Claude Code 是单 Agent 模式 | TeamCreate/SendMessage 不能在单兵模式生效 | team-lead MD 内嵌"协作机制"指令模拟多角色调度 |
| Ima 知识库 ID 可能漂移 | mcp 服务端 ID 偶有变更 | 严真奥每次任务开始 ToolSearch 探测 |
| OneDrive 同名文件覆盖合并 | 备份必须不同前缀而非仅后缀差异 | UPGRADE.md 强调使用 rsync 完整目录同步 |

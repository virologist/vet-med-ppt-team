# 双层 Loop 治理（Loop A 工程进化 / Loop B 旧课件优化）

> 建立：v3.8.1（补完批：把已落在 `config/harness.yaml#loop_a/#loop_b` 的两环配置，补齐为可执行的治理契约）
> 上位配置：`config/harness.yaml#loop_a`、`#loop_b`
> 执行细则唯一源：**Loop B = `references/round-review-sop.md`**；本文**不重定义**其条款，只负责**判环、授权隔离与阶段契约**。
> 全文生效的既有规则：`references/adjudication-rules.md`（迭代六原则 + 原则六素材判读红线）、`references/iron-rules.md`、`references/harness-engine.md`。

## 0. 为什么立这份文档

v3.8.0 把两环配置写进了 `harness.yaml`，但**没有一份文档回答三个操作问题**：
① 主理人接到一句话指令时，怎么判这是 Loop A 还是 Loop B？
② 用户在 Loop A 里批准的"升级指令"，凭什么不能当成 Loop B 的"处理课件授权"？
③ Loop B 的"启动/继续/返修/恢复/制作"各自该敲什么、谁有权敲？

这三问不落盘，两环隔离就只是配置注释。本文是这三问的唯一答案源。

## 1. 判环路由（主理人接单第一步，先判环再干活）

| 判据 | 结论 |
|---|---|
| 指令对象是**专家团本身**（改脚本/配置/成员 MD/规则/版本/发布） | **Loop A** |
| 指令对象是**某份真实课件**（诊断/改内容/配图/出新版 PPTX） | **Loop B** |
| 一句话里两者都有 | **拆成两个 Loop**，分别建状态、分别确认；**不得合并处理** |
| 判不出（如"把 PPT 这块再优化优化"） | **必须追问**：「您说的是改专家团规则，还是改某份课件？」——不猜 |

判环结果必须写进状态文件并在首轮回复中告知用户：「本指令判定 Loop X」。

## 2. 授权隔离（三条硬约束）

1. **授权不互通**：用户在 Loop A 里批准"升级指令" **≠** 授权处理任何课件。Loop B 的启动必须由用户在**课件级**单独点名（文件名 + 范围）。
2. **状态不互通**：`loopA_state.json` 与 `loopB_state.json` 各自独立、并存不覆盖，`task_state.json` 语义不变（五道闸既有状态机）。
3. **目录不互通**：Loop A 白名单 = `<包>/{scripts,config,references,agents}`；`forbidden_paths` 为用户课件目录与 `.workbuddy/artifacts`。越界即越权，verifier 逮到即挂账。

> **诚实标注（v3.20.0 重写——原文自 v3.8.1 起已过期两年多版本）**：
> 原文写的是"以上三条是配置声明 + 文档契约，不是代码级强制——`harness.py` 尚未实现
> `loop_a.forbidden_paths` 的写前校验"。**这句话自 v3.9.0 起就是错的**：`loop check-path`
> 已实现写前越界校验（见 §8 第 3 项）。文档追不上代码，正是本包"双源漂移"的又一实例。
>
> v3.20.0 的实际强制面（判定层统一在 `scripts/loop_contract.py`，配置唯一源 `config/harness.yaml`）：
> | # | 约束 | 是否代码强制 | 落点 |
> |---|---|---|---|
> | 1 | 授权不互通 | **否（语义判定）** | 判环靠主理人——`loop_a.trigger` / `loop_b.trigger` 是**人读判据**，代码不判一句话在说哪个环 |
> | 2 | 状态不互通 | **是** | `coexist_guard`：两环状态文件路径**解析后不得相同**（相同会覆盖 `task_state.json` → 拒绝启动） |
> | 3 | 目录不互通 | **是（非沙箱）** | `loop check-path`：A 碰课件目录 / B 碰包目录或原件 → exit 1。**拦不住成员绕开脚本直接写文件**（平台无 hook） |
> | 4 | 单写者 | **是（不防冒名）** | `single_writer_check`：`--actor` 与 `loop_b.single_writer` 不符即拒；**平台无身份认证**，成员照样可传 `--actor team-lead` |
> | 5 | 环总开关 | **是** | `enabled`：置 false 后该环所有动作 exit 1 |
>
> **不得对外宣称"两环隔离已由代码完全强制"**——第 1 条不是代码判定，第 3/4 条也各有明确的失效路径（见上表）。

## 3. Loop A：专家团工程进化

| 步 | 动作 | 出口 |
|---|---|---|
| 1 | **只读探针**：`harness.py doctor` + `ensure_settings.py`（读实际安装版本、文件、工具能力） | 真实基线，不用仓库默认值冒充事实 |
| 2 | **缺口清单**：只列**已核验**的真实缺口，标注四类能力分级 `[D]官方文档 / [R]仓库实现 / [L]本地可调用 / [T]已实测` | 缺口清单 |
| 3 | **最小补丁提案**：每批只解决一个主题的缺口，写清改哪些文件、为什么、回归项 | 提案 |
| 4 | **用户确认**：`confirm_before_each_batch: true`——**每批修改前停一次**，未确认不动手 | 授权记录 |
| 5 | **实施**：只碰白名单目录；版本号变更须**十处**同步（见 §8 第 12 项，v3.20.0 实测为 10 处，不是四处） | 补丁 |
| 6 | **验证与回归**：`ensure_settings`（须全绿）+ `test_harness` + `test_five_gates`；任一红即回滚本批 | 回归报告 |

**三条禁令**：① 不得因一次课件的特殊要求擅自改全局规则（单课件诉求走 Loop B，要改规则须在 Loop A 单独立项）；② 不得把 `[D]/[R]/[L]` 冒充 `[T]`；③ 达到预算上限只暂停并报告，**不自动宣布通过**。

> **v3.20.0：第 3/4/6 步已代码化**（此前仨步骤全是 Markdown 纪律，`loop_a` 的
> `confirm_before_each_batch` / `patch_discipline` / `regression_required` 三个键
> **零代码读取者**——把 `confirm_before_each_batch` 改成 false 不会有任何行为变化）：
> ```bash
> harness.py loop batch-open  --loop a --note <本批主题> --files scripts/<目标脚本>.py,config/<目标配置>.yaml
> harness.py loop batch-status --loop a [--batch <id>]
> harness.py loop batch-close --loop a --batch <id> --confirmed \
>            --regression <yaml#loop_a.regression_required 现值（B20 后 7 项，勿硬编码）> \
>            [--regression-evidence <实测证据.json>]
> harness.py loop batch-gc    --loop a [--keep N] [--drop-open <id,...>] [--dry-run]
> ```
> · `batch-open`：声明文件须先过白名单（`loop_a.scope` / `forbidden_paths`），越界即拒
> · `batch-close` 六条判据（均读 `config/harness.yaml#loop_a`）：
>   ① `confirm_before_each_batch=true` 且未带 `--confirmed` → **exit 1**（第 4 步）
>   ② `regression_required` 列出的项没跑齐 → exit 1 并列出缺哪几项（第 6 步）
>   ③ `patch_discipline=minimal` → 用 `git status` 比对**实际改动集合 ⊆ 声明集合**（第 3 步）
>   ④ **B19 套件名真实性**：`--regression` 含未知套件（既非 `scripts/<名>.py`
>      亦非 `scripts/test_<名>.py` 亦非 `ensure_settings`）→ **exit 2** 且批次保持
>      open——「跑过回归」不得是幻觉声明（第三轮诊断实证：`nonexist_suite`
>      曾被静默接受且 ok:true）
>   ⑤ **B19 闭合归属**：存在更新的未闭合批次时闭合旧批次 → **exit 2**
>      （旧批次曾被诊断探针用假套件名顺手闭合——跨批污染状态机）
>   ⑥ **任务F·病灶② 回归实测证据**（`--regression-evidence`，六条判据的最后一条）：
>      `--regression` 是**声明**（名字列表），B19 只验「名字像真的」⇒ **纯声明即可收批**
>      （实测 `b1793794707` 在 1 秒内完成 open→close，却记录了 7 项从未执行的回归）。
>      ⇒ 落账时**声明与实测分列两个字段**：
>        · `regression_ran`      —— **声明**（`--regression` 的名字列表，字段名不变）
>        · `regression_verified` —— **实测**（`--regression-evidence` 的证据清单）
>        · `confirmed`           —— 账本里**唯一**代表「这批验收过」的标记
>      证据文件格式：`{"suites": [{"suite": ..., "rc": 0, "duration_s": ...}]}`
>      降级规则（fail-closed，但不过度阻断）：
>        · 证据齐备且全 rc=0 → `confirmed=true`（`confirmed_reason=evidence_ok`）
>        · 某项 rc≠0         → **exit 1** 拒绝收批，批次保持 open（点名哪项失败）
>        · 套件名与 `--regression` 名单不一致（少一项或多一项）→ **exit 2** 拒绝
>          （防张冠李戴；少一项 = 有声明无实测）
>        · 证据文件不存在 / JSON 非法 / 结构非法 → **exit 2** 拒绝
>          （证据不可得**不按 0 处理**——静默取 0 会造出「回归全绿」的假象）
>        · **未提供证据** → 放行（向后兼容，历史批次命令不失效）但
>          `confirmed=false`、`confirmed_reason=no_regression_evidence`、
>          `regression_verified=[]`，并在 stderr 打 ⚠ 警告
>          ⇒ 「没验证过」在账本里**不得**看起来像「验证过」
> · **任务F·病灶⑤（v3.28.8）：「废弃」口径两处一致** ——
>   `batch-gc --drop-open` 的 `before_open` 与 `batch-close` 的归属校验
>   **必须用同一口径**：未闭合 ∧ **未废弃**。
>   背景（实测）：此前 `batch-gc` 认 `abandoned` 而 `batch-close` 不认
>   ⇒ **标记废弃 ≠ 判定废弃** ⇒ ① 真正的最新批次可能因一个**已废弃**的
>   更晚批次被 stale 误拦（收不掉）；② `batch-gc` 报告的 open 数与
>   `batch-close` 实际认定的 open 数对不上 ⇒ **操作成功、效果为零**。
>   ⇒ 根治：抽 `_open_batches()` 单一真源（`harness.py`），三处调用同一函数：
>     `batch-gc` 的 `before_open` / `batch-close` 的归属校验 / `batch-close` 的
>     `--batch` 缺省推断。⇒ 口径不可能再漂移。
> · **R18-续（v3.28.8）：体检第 7 项的超时第三态 `REG_TIMEOUT`** ——
>   套件在阈值内**没跑完** ⇒ 既非失败、也非环境受限 ⇒
>   **不阻断**（rc 仍为 0）但**必须**进「未验证」累加器
>   ⇒ 结论区降级为「⚠️ 存在未验证项」，**绝不**写「✅ 全部通过」（假绿）。
>   阈值真源：`config/harness.yaml#loop_a.regression_timeout_s`（禁硬编码；
>   改动该键须连带刷新 `references/inspection-zones.yaml` 的机算字段）。
>   ⚠ 五态对照：`REG_FAIL`（阻断）/ `REG_PASS_WITH_SKIPS`（⚠·未验证）/
>     `REG_ENV_LIMITED`（⚠·未验证）/ `REG_TIMEOUT`（⚠·未验证）/ `REG_PASS`（真通过）。
> · `batch-gc`（**B20 · 第三轮 P2-1**）：批次历史压缩，**显式触发不自动**——
>   closed 超保留数（`loop_a.batch_history_keep`，缺省 20）压入
>   `archived_batches` 摘要区（id/theme/closed_at 三元组，可溯不可展开）；
>   误开批次走 `--drop-open` 显式废弃（标记 abandoned 留痕）；`--dry-run` 只看计划。
>   背景：71 批次/200KB 无压缩先例（snapshot 有 LRU keep=3、task_state 有 keep=10）。
> ⚠ ③ 判的是"改动有没有超出声明范围"，**不是**"改得多不多、该不该改"——后者是人的判断。
> ⚠ 包目录非 git 仓库或 git 不可用时，③ **不做比对并显式告警**（不静默放行、也不假称已判）。

### 3.0-bis 裁决点爆炸半径车道表（v3.30.0 B3 · 升级项③-3）

> 车道语义：**绿 = 自动放行**（确定性、可逆、有轨迹）；**黄 = 确定性检查 + 轨迹**（机器判 + 事后可审计）；
> **红 = 永远人工**（高撤销成本/不可逆/语义裁决——红道**不设置信度阈值**，机器不代行）。

| 裁决点 | 车道 | 现有强制面（不新建，R7） |
|---|---|---|
| 触碰 forbidden_paths（用户课件目录） | 🔴 红 | `loop_a.forbidden_paths` + check-path + batch-open 拒批 |
| scope 白名单外写操作 | 🔴 红 | `loop_a.scope` + batch-open 越权拒批 |
| 收批放行（batch-close --confirmed） | 🔴 红 | `confirm_before_each_batch` + 回归 7 套件 + defect_reflow 对账 |
| knowledge_channel 用户确认放行（跨专业库） | 🔴 红 | 闸1 第 8 项 + 沉默不构成确认（v3.30.0 B2/R9 语义） |
| gate1_freeze 各项用户确认 | 🔴 红 | `gate1-check` 十项机器校验 + 沉默不构成确认 |
| 版本 13(15) 处声明点提版 | 🟡 黄 | 体检第 14 项 `check_version_consistency` rc 对账 |
| config/*.yaml 判据键变更 | 🟡 黄 | 登记表 keys_sha256 失配 + sync_zone_registry + dead_config 判据 |
| 成员 MD 红线段 / 受守卫文档 | 🟡 黄 | `guard.yaml#guarded_docs` + test_arch_drift T8/T9/T10 + T12 项数扫描 |
| defect_reflow 台账条目 | 🟡 黄 | `loop reflow` 哈希对账（E_HASH_STALE 防事后改账） |
| 经验条目晋升（candidate→applied） | 🟡 黄 | `MERGE_GATE.yaml`（≥3 复发或 ack；2026-11-08 后生效） |
| 打回/退回指令 | 🟡 黄 | 打回包五要素模板（round-review-sop §4.1；SCOPE 缺失 = 指令无效） |
| Lint/登记表机算字段刷新（sync_zone_registry） | 🟢 绿 | 机算确定、可重放、随批 commit 留痕 |
| trace 事件写入 | 🟢 绿 | 31 事件 fail-closed 声明面对账（test_trace_events） |
| 镜像同步（mirror_sync） | 🟢 绿 | dry-run 默认 + --confirm 显式 + 同步后零差异校验 |

> 维护纪律：新裁决点先判车道再接入；车道变更 = 本表变更 = Loop A 批次（红道表格自身变更须经管家节点确认）。

### 3.1 缺陷回流台账（v3.28.2 新增 · 「改规则不改输出」的留痕面）

**缺口（本轮十三维度诊断 D6/P0-1 实测）**：Loop A 反复出现「改规则不改输出」——
`config/` 的判据键或 `references/` 的纪律条款改了、判据代码也改了，**同一任务重跑的产出
毫无变化**，而全包**没有任何触发记录与台账**（rg「回流 / 改规则不改输出」0 命中）
⇒ 规则改动与产出效果之间**无可回证的链路**。

**机制**：每次**规则类改动**必须在 `references/defect-reflow.yaml`（唯一登记面，禁建平行台账）
登记一条，机器判据 = `harness.py loop reflow --loop a`：

```bash
harness.py loop reflow --loop a            # 校验 yaml#defect_reflow.ledger 指向的台账
harness.py loop reflow --loop a --file <台账路径>   # 显式指定（默认取配置）
```

四条判据（判据源 `config/harness.yaml#defect_reflow`，实现 `loop_contract.py::defect_reflow_check`）：
1. 台账结构合法（顶层映射 + `entries` 列表）；
2. 每条登记**必填字段非空**：`id` / `rule_ref` / `change` / `rule_hash_before` / `rule_hash_after` / `output_evidence`；
3. `output_evidence` 为空时必须齐**豁免三要素**（`waiver_reason` / `waiver_by` / `waiver_at`）——**口头豁免不算**；
4. `rule_hash_after` 必须与**当前文件** sha256 前 12 位一致 —— 防**事后改账**（规则又改了却没更新台账，哈希立刻不匹配）。

**什么算规则类改动（须登记）**：`config/*.yaml` 里被判据消费的键（阈值/字段表/映射/开关语义）、
`references/*.md` 里带「必须/不得/判据/红线」的纪律条款。
**什么不必登记**：错别字、格式重排、注释补全（不改变任何判定语义）。

**边界（不宣称判了什么）**：本机制只保证「有一条可复核的产出证据指向」，
**不判断证据是否真的支持结论**——那是语义判断，归主理人与管家节点。
与批次门的分工：批次门管「本批改了哪些文件」，本台账管「改动有没有产出效果」，两者互补。

**能红证明**：`scripts/test_defect_reflow.py`（7 例：正向绿 / 缺字段红 / 哈希过期红 /
无证据须豁免 / 重复 id 红 / 台账缺失按依赖错误 / 掏空判据的变异证明）。


## 4. Loop B：五条操作指令（逐轮停等）

> 执行细则（转换层、条目字段、裁决语义、冻结、终止、终审）**一律以 `round-review-sop.md` 为准**。下表只给操作入口。

| 指令 | 触发 | 主理人动作 | 禁止 |
|---|---|---|---|
| **启动** | 用户点名某份已有 PPT + 范围 | 建 `loopB_state.json`；原件算 sha256/mtime 存档；建工作副本 `<name>_wip/`；跑 §2 转换层（markitdown + extract_assets + 渲染） | 未拿到范围就开工；动原件 |
| **继续** | 上一轮获"接受"或"部分接受" | **先出机器数**（`verify_deck --json` → `loop continue --verify-json`，见下方「质量数来源纪律」）；再 `round += 1`；按下一条小批（≤ `max_items_per_round`）出轮报六项 | 把"沉默"当批准；一次塞满多轮条目；**用手填 `--p0/--p1/--p2` 顶替机器复算** |
| **返修** | 用户说方向对、执行不对 | **round 不变**；生成返工单回灌本轮；计入 `max_rework_per_item` | 进位；改已冻结条目 |
| **恢复** | 断线/换会话 | 读状态最小集（task_id / source_ppt{sha256,mtime} / wip_dir / current_round / frozen / pending / budgets / blockers）；**先报"恢复到第 R 轮，已冻结 N 条，待办 M 条"，等用户确认再继续** | 重跑已确认条目；覆盖 `_draft` |
| **制作** | 全部条目冻结 + §8 制作前置门全过 | 冻结包 → ppt-producer 制作 → verifier 独立验收（打开/渲染/可编辑性三项） | 制作期遇内容问题自行改写（须退回内容轮） |

> ### 4.1 质量数来源纪律（B23① · 第五轮诊断 N7 · **行为收紧**）
>
> **病灶（真实首跑证据，非推测）**：Loop B 首跑 `T-xuexue-20261103` 的
> `quality_history[0].source = "manual"`（主理人手填），state 里虽如实标了
> `unverified: 自报值`——但**调度面无人接线**：B16 建好的 verify-tier 机制
> （风险分级 / 跨任务趋势 / 闸5 后沉淀）在 doctor 表里、机制齐全，却**零消费**。
> 手填的数一路走到制作门，全程没有任何机器交叉核验。
>
> **纪律（与 `round_review.silent_is_not_approval` 同源：「沉默不算确认」的孪生条款）**：
> **「自报数不算验收」。**
>
> | 步 | 命令 | 说明 |
> |---|---|---|
> | ① 出机器数 | `verify_deck.py <课件> --hours N --level all --json <报告>` | 机器复算的 P0/P1/P2 |
> | ② 案例风险分级 | `harness.py verify-tier --workspace <工作区>` | 按风险出检验强度计划（高危全检 / 低危登记待办） |
> | ③ 进位 | `harness.py loop continue --decision accept --confirmed --verify-json <报告>` | 快照 source=`verify_json|<路径>` |
>
> **硬拦**：`loop continue` 带手工 `--p0/--p1/--p2` 且无 `--verify-json` ⇒ **exit 1**
> （判据源 = `harness.yaml#loop_b.budgets.quality_source_required`，当前值 `"verify"`）。
>
> **逃生口**：`--allow-unverified` 仍在（登记 blocker 事件 + trace + 快照标
> `source=manual_unverified`，且 `make-gate` 阻断）——理由：纯文档轮/无课件轮
> 确实拿不到 verify_deck 报告，完全堵死会让流水线停摆。但**默认路径必须走机器复算**。
>
> **回退**：本条是行为收紧，回退 = revert 单 commit（`quality_source_required` 改回
> 可空即可，其余机制不受影响）。
>
> ### 4.2 施工清单分流纪律（B24③ · 第五轮诊断 N2）
>
> **病灶（首跑实证）**：几何版式修复连续**三轮证伪**（重叠 4→16→19），
> AI 不可修复的缺陷（文字墙要拆页 / 课时不达标要增删页 / 缺题页要真实字段）
> 与可修缺陷混在同一张施工清单里 ⇒ 白烧 3 轮，且中途引入过自引入缺陷。
>
> **纪律**：闸3 施工前先分流，**AI 修不了的条目不进 AI 施工清单**。
>
> ```bash
> harness.py loop worklist --verify-json <报告> --out <清单.json>
> ```
>
> 分流三张清单（分类唯一源 = `config/visual-rules.yaml#fix_class`，逐条带理由）：
> - `ai` → AI 施工清单（确定性可修，派工对象）
> - `human` → 人工确认区（AI 可出方案，须人拍板）
> - `ai_unfixable` → **人工挂账区**（AI 修不了；理由逐条在 `fix_class_reason`）
>
> ⚠ 诚实边界：分类依据是**问题类型登记**，不是语义判断——代码不判断
> 「这一条具体能不能修」，只按登记面分流。
>
> ### 4.3 成员调用预算护栏（B24⑤ · 第五轮诊断 N6）
>
> **病灶（首跑实证）**：严真奥撞 429 中断，**撞限前无任何预警**，且成员调用
> 时长全程无记录 ⇒ 事后无法回答「这次调用是不是已经超了合理预算」。
>
> **纪律**：成员单次调用预算 = `harness.yaml#loop_b.budgets.member_call_minutes`
> （默认 **15** 分钟）。
> - `harness.py spawn` 登记起始时间戳；
> - `harness.py member-return --elapsed-minutes N`（或 `--started-at`）回填耗时；
> - 超预算 ⇒ **trace warning + 建议拆分任务**（**不阻断**：撞限的正式处置是
>   `spawn-failed --reason quota`，此处只做事前可见，不重复执法）。
>
> ### 4.4 spawn 前成员通道探测（B24④ · 第五轮诊断 N4）
>
> **病灶（首跑实证）**：degrade 5 条**全部同因**（平台把成员回落成
> `general-purpose` ≠ 成员 id），且**全是事后记录**——`preflight` 此前只探
> 外部工具通道，**不探成员通道本身**。
>
> **纪律**：开工前跑 `harness.py preflight --probe-members`，
> 不一致 ⇒ 报 `member_channel_mismatch` 并给降级预案（装配注入成员 MD 全文）。
> degrade 从**事后**变**事前**。
>
> > **v3.9.0：五条指令已代码化**，状态推进一律走 `scripts/harness.py loop <动作>`
> （`start/intake/add-item/status/resume/continue/rework/freeze/verify/make-gate/block/terminate/check-path`），
> **不得靠口头记账**。命令表见 `agents/vet-med-ppt-team-team-lead.md#双 Loop 路由`；
> 机器背书 `scripts/test_loop_state.py`（33 例）。
>
> **v3.20.0：判据层也已代码化**（此前只有动作层下沉，判据仍是纯 Markdown 纪律）——
> `harness.yaml#loop_a` / `#loop_b` / `#delta_gate` 的 34 个键里 **32 个**已接到
> `scripts/loop_contract.py`，loop 子命令从 13 个动作扩到 **23 个**。新增：
> - **Loop A 批次门**：`batch-open` / `batch-close` / `batch-status`（先确认 / 最小补丁 / 回归必跑）
> - **Loop B 判据动作**：`review`（轮报六项）/ `retrieval`（检索预算）/ `baseline`（基线字段）/
>   `delta`（自引入阻断 + 报告格式守恒 + 空间审计）/ `geo-baseline`（几何基线登记）/
>   `defaults`（默认档 + 引用核验 + intake 待确认模板）
> - **写者声明**：写动作须带 `--actor`（`loop_b.single_writer`，不防冒名）
> - **环总开关**：`loop_{a,b}.enabled=false` → 该环所有动作 exit 1
>
> 机器背书：`scripts/test_loop_contract.py`（87 例，正例+反向例+破坏实现双向验证）
> + `scripts/test_loop_wiring.py`（23 例，harness.py × loop_contract.py 接线回归）。
> ⚠ 3 个键**据实不可判定**（`loop_a.trigger` / `loop_b.trigger` 属语义判定、
> `delta_gate.insert_font_at_creation` 属写入时行为）——详见 §8 第 12 项。
>
> **v3.21.0：轮报从「洞察载体」投影**（Loop B 内的产物机制，不改变两环隔离口径）——
> 闸 2/闸 3 各专家的洞察写进**同一份载体**（`references/spawn-protocol.md#2.2`），
> 轮报六项的**第 1、2 项**（处理范围及问题 / 修改前后差异）改为**从载体渲染**，
> 不得另写一份（两处各写 = 两份真相）。
> ⚠ **载体条目 ≠ Loop B 条目**（两层，别混）：
> · 载体条目 = **洞察**（谁提的、依据、裁决状态）——是待改条目的**上游**；
> · Loop B 条目 = **待改对象**（file + sha256 + decision，冻结对象）；
> · 衔接 = 载体条目裁决为 `accepted` 后，主理人用 `loop add-item` 登记为待改条目。
> Loop A（改专家团）**不涉及载体**——载体的目标集是"用户给定的内容"，不是专家团自身。

## 5. 七阶段契约（输入 / 输出 / 责任人 / 权限 / 退出状态）

| # | 阶段 | 输入 | 输出 | 责任人 | 权限 | 退出状态 |
|---|---|---|---|---|---|---|
| 1 | 只读探针与任务对齐 | 指令 + 实际安装版本 + 原 PPT | 基线报告 + 追问清单（**九项清单：`references/task-intake-checklist.md`**；A 类 5 项缺一即停） | 主理人 | 只读 | 信息齐 → 2；缺 A 类任一项 → **等待用户** |
| 2 | 内容与资产转换 | 原 PPTX（只读） | `_raw/original.md` + `_assets/` + `manifest.json` + 渲染图 + **`original.refs.md`（引用修复稿）+ `*.refs.json`（引用报告）** | 主理人 + ppt-producer | 只读原件，写工作副本 | 转换完成且引用报告无未决项 → 3；缺页/缺图/引用缺失 → 挂账清单 → 3 |
| 3 | 细颗粒度诊断 | 转换产物 + 渲染图 | 条目清单（八字段，全局扫描仅第 1 轮一次） | dvm / pedagogy / visual | 只读 | 有条目 → 4；零条目 → 报"无需修改"待确认 |
| 4 | ReAct 证据检索与候选优化 | 条目 | 每条目：检索行动 + 证据（PMID/DOI/指南）+ 适用边界 + 未决项 | dvm（内容）/ pedagogy（教学） | 只读 + 联网 | 证据足 → 5；关键结论无法核验 → **能力或证据阻塞**（该结论不进正式内容） |
| 5 | 用户逐轮审阅 | 本轮小批 | 轮报六项（范围/差异/正文/来源/配图/验收+下轮候选） | 主理人（唯一提问通道） | 只读 | 接受 → 冻结进位；部分接受 → 只冻点名条目；返修 → 回 4；暂停/终止 → 停 |
| 6 | 内容与素材冻结 | 用户裁决 | 冻结记录（item_id / file / sha256 / round / decision / decided_at） | 主理人（单写者） | 写 `loopB_state.json` | 覆盖制作输入 → 7；sha256 漂移 → 批准失效，回 5 |
| 7 | 可编辑 PPTX 制作与独立验收 | 冻结包 + 模板 | 新版 PPTX + 验收矩阵（10 项逐条判据） | ppt-producer 制作 / verifier 独立验收 | 写工作副本与交付物 | 全过 → **成功完成**；任一阻断点 → 回对应阶段；预算触顶 → **达到预算但未完成** |

## 6. 终止五类

唯一源 `round-review-sop.md#7`：成功完成 / 等待用户 / 能力或证据阻塞 / 达到预算但未完成 / 用户取消。
补充一条纪律：**沉默与超时归入"等待用户"，绝不自动推进**。

## 7. 验收矩阵

终审 10 项见 `round-review-sop.md#11`（逐项须给判据，无法检查写明原因，不写"看起来没问题"）。
本文件补充一条**元验收**：交付时必须同时回答——本轮改动落在哪个 Loop？该 Loop 的状态文件是否已更新？授权记录是否可追溯？答不出即不得交付。

## 8. 未验证项清单（如实标注，不虚报）

| # | 项 | 分级 | 现状 |
|---|---|---|---|
| 1 | 图片引用修复 | `[T]` **已实测**（v3.8.2） | 由新脚本 `scripts/fix_md_image_refs.py` 提供（**不是**给 `extract_assets.py` 加参数——职责分离：extract 只抽资产，fix 只修引用）。合成样本 3/3 全解析、缺图/孤立资产/三方计数不一致均正确报出；回归 7/7 通过 |
| 2 | `ooxml_lint` 可编辑性与几何判定 | `[T]` 部分实测 | **GEO-003 已实现**（v3.8.2，WARN 级，合成样本 75% 重叠正确报出、无重叠不误报）；**API-001 保持人工项——结构性不可实现**（写入时行为，文件态无痕迹）；GEO-001/GEO-002（已规避）/TXT-001/TXT-002/CTX-001 仍为人工项 |
| 3 | 两环隔离强制力 | `[T]` **部分实测**（v3.9.0） | `harness.py loop check-path` 已实现 `loop_a.forbidden_paths` 与 `loop_a.scope` 的**写前越界校验**（A 碰课件目录/B 碰包目录或原件 → exit 1），`test_loop_state.py` 4 例背书。**但非沙箱级**：拦不住成员绕开脚本直接写文件（平台无 hook），也不判定内容对错——不得宣称"已由代码完全强制" |
| 4 | Loop B 端到端 | `[未实测]` | **状态机层面已实测**（v3.9.0，`test_loop_state.py` 33 例覆盖启动/登记/停等/部分冻结/sha256 失效/返修/预算触顶/制作门/终止/越界）；**真实课件全链仍未实测**——尚未在真课件上跑完"转换→诊断→多轮→冻结→制作→验收" |
| 5 | markitdown 转换 | `[T]` 已实测 | 0.1.7，见 `references/markitdown_0.1.7_实测报告.md` |
| 6 | 渲染链路 | `[T]` 已实测 | soffice 26.8.1.1 → PDF → PNG；`pdftoppm` 依赖 poppler，缺则须换 `sips` |
| 7 | 双源备注核验 | `[T]` 已实测 | v3.2.0 四样本中 2/4 口径不一致 → 双源核验为硬约束 |
| 8 | python-pptx | `[T]` 已实测 | 1.0.2 打开/写入正常 |
| 9 | 任务信息九项 | `[已确认]` v3.10.0 | 用户 2026-10-22 已给：受众（职业本科默认 + 四层切换）/ 课时（1–4×45min）/ 模板（5fa78154）/ 范围（全部页逐页六查）/ 验收（内容 5 + 视觉 7）/ 交付三件套。落盘 `references/course-profile-defaults.md` + `default-template-profile.md` + `delivery-spec.md`。**每单仍需确认是否覆盖**，覆盖须记入 intake |
| 10 | 默认模板可用性 | `[T]` 已实测 | 15.2MB OOXML 有效、lint 0 ERROR；但有三条硬约束：**版式零占位符**、**页眉为每页硬编码文本框**、**零原生表格/图表**（详见 `default-template-profile.md`） |
| 11 | Loop B 端到端 | `[未实测]` | 仍未在真实课件上跑完"转换→诊断→多轮→冻结→制作→验收"全链；**缺具体课件路径**（用户已给默认参数，未给本单课件） |
| 12 | `delta_gate.insert_font_at_creation` | `[无执行器]` **结构性不可判定** | "新元素文字规格**创建时**即达合规"是**写入时行为**，成品文件态无痕迹——与 OOXML 病例 **API-001 同型**（第 2 项已判不可实现）。v3.20.0 逐键定性时据实登记为不可判定，**不为凑数伪造执行器**：代码能做的是"事后 lint 查字号"，那查的是**结果合规**，不是"创建时即设"，二者不得混称 |
| 13 | 版本号十处同步 | `[T]` 已实测（v3.20.0） | `ensure_settings` 第 14 项实测为 **10 处**（不是 §3 第 5 步原写的"四处"）：2 份 plugin.json + 2 份 marketplace.json + config/harness.yaml + config/domain_config.yaml + references/result-envelope.yaml + harness.py 三处（文件头/doctor 常量/argparse 描述）。原文档写"四处"是 v3.7.0 的旧数，已过时 |

> 标注纪律：`[D]/[R]/[L]` **不得**冒充 `[T]`；未实测的机器检查项一律标"仅静态检查，未在用户 WorkBuddy 实测"；
> **无执行器的键一律标 `[无执行器]`**——不得因为"配置里有这一行"就宣称已由代码强制（v3.20.0 新增纪律）。

## 9. 本地最小实测清单（跑通才算数，不跑就标"未实测"）

| # | 场景 | 最小实测动作 | 期望 |
|---|---|---|---|
| 1 | 用户拒绝 | 轮报后回"接受"→ 再回"这条不要" | 只冻结被点名条目，其余回 `pending`，不进位 |
| 2 | 部分批准 | 5 条中点名 2 条 | `frozen=2`，`pending=3`，`round` 不变 |
| 3 | 人工改稿 | 用户手工改 `_draft.md` 后要求继续 | sha256 与冻结记录不一致 → 该条目批准**自动失效**并重审 |
| 4 | 断线恢复 | 杀会话后重开 | 报"恢复到第 R 轮、已冻结 N、待办 M"，**等确认**才继续 |
| 5 | 缺图 | 删掉 `_assets/` 中一张图 | 条目显式列"引用缺失"，不留空链接/占位图 |
| 6 | 无法取回原文 | 关键结论只拿到搜索摘要 | 结论不进正式内容，记 `[待核实]` 并报阻塞 |
| 7 | 模板失败 | 指定模板不存在/不可用 | 报缺口 + 核验方法，**不降级**"沿用原模板试试"了事 |
| 8 | 渲染失败 | soffice 不可用 | 视觉结论标"未经渲染核实"，按能力阻塞上报 |
| 9 | 新建 PPT 回归 | `ensure_settings` + `test_five_gates.py` | 28/28 绿 + 五闸测试通过，Loop B 改动**未破坏**新建能力 |

**已实测记录（2026-10-22，v3.9.0 更新）**：

| 场景 | 载体 | 结果 |
|---|---|---|
| 1 用户拒绝/返修 | `test_loop_state.py` | ✅ 返修不进位；超 `max_rework_per_item` 挂阻塞并 exit 1 |
| 2 部分批准 | `test_loop_state.py` | ✅ 5 条点名 2 条 → `frozen=2 / pending=3`，`round` 不变 |
| 3 人工改稿 | `test_loop_state.py` | ✅ 改 `_draft.md` → `verify` 报 `sha256_drift`，条目转 `invalidated`，exit 1 |
| 4 断线恢复 | `test_loop_state.py` | ✅ `resume` 报"恢复到第 R 轮，已冻结 N 条，待办 M 条"，置 `awaiting_user_confirm=true` 不续跑 |
| 5 缺图 | `test_fix_md_image_refs.py` | ✅ 7/7（含缺图、孤立资产、原始 md 不被覆盖、`--out==--md` 拦截） |
| 6 制作前置门 | `test_loop_state.py` | ✅ 有未冻结/失效条目/阻塞 → 阻断并列出原因；全齐才 exit 0 |
| 7 模板可用性核验 | **v3.10.0 已实测**（默认模板） | ✅ 指纹 5fa78154、lint 0 ERROR/555 WARN；发现三条硬约束（零占位符/页眉硬编码/零原生图表）。**「模板不存在」故障分支**由 `test_ooxml_lint.py::G4` 覆盖（基线缺失不崩溃、不静默豁免） |
| 8 渲染失败 | **仍未实测** | 需构造 soffice 不可用环境；当前环境 soffice 26.8.1.1 可用，未做故障注入 |
| 9 新建 PPT 回归 | `ensure_settings` + 全套件 | ✅ 28/28 绿 + 9 个测试套件全过 |
| 10 遮挡验收（V7） | `test_ooxml_lint.py::G1–G5` | ✅ v3.10.0 新增：自身比对 552/552 豁免、新增框 12 条全检出、同名形状多组重叠正确豁免（修 ratio 集合 bug） |

**仍未实测**：场景 8（渲染失败）需故障注入；**真实课件端到端全链**仍缺具体课件路径
（九项参数已由用户确认，见 §8 第 9 项，但**本单课件尚未指定**）。

## 10. 与既有规则的优先级

1. 两环冲突时，**用户课件相关的安全约束（原件只读、逐轮停等）优先于任何效率建议**。
2. 本文**只定义判环、授权与阶段契约**；Loop B 的执行判定语义一律回 `round-review-sop.md`，裁决原则一律回 `adjudication-rules.md`——本文不得成为第二规则源。

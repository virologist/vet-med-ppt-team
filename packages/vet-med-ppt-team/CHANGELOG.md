# 更新日志 · CHANGELOG

本文件记录动物医学教学PPT智造团（vet-med-ppt-team）的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [v3.2.0] - 2026-10-14

### 概述（第四轮：v4 通用化战略级纠偏 + WF-2R 旧课件诊疗流水线基础）

应用户战略级纠偏——**项目是测试和迭代的试验地，不是产品归属**。本批完成 4 项通用化修订 + v3.2.0 升版 + Batch 1 资产化 + Batch 2 兼容性 lint 与快照治理。动物医学工作区作为"测试样本 A"被显式声明，未来可换测试样本 B（猪病）/C（宠物）/D（水产）/任何学科；产品目标 = 通用教学 PPT 诊断与设计专家团。

### Added
- **`scripts/extract_assets.py`**（Batch 1）：S1 资产化转换层，8 类形状分流（PICTURE/CHART/TABLE/MEDIA/OLE/GROUP/SMARTART/TEXT），生成 `<课件>_assets/manifest.json`（六字段 + 7 派生）
- **`scripts/ooxml_lint.py`**（Batch 2）：OOXML 兼容性检查器，6 组检查码（PKG/REL/CT/ID/XML/SYN），ERROR 阻断 + WARN 明示；支持 baseline 对照 + 强模式
- **`scripts/snapshot.py`**（Batch 2）：快照库，K=3+里程碑+500MB+LRU 治理，sha256 去重；支持 snap/list/rollback/gc/status 子命令
- **`references/ooxml-compat.md`**（Batch 2）：D11 防线病例库，初始 7 病例（PKG001 删页残留 / deepcopy 重复 rels / 悬空 rId / CT 漏登记 / ID 冲突 / 非法字符 / md5 复核）
- **`references/extract_assets_usage.md`**（Batch 1）+ **`references/snapshot_usage.md`**（Batch 2）：8 节人读手册
- **`scripts/test_extract_assets.py`**（Batch 1，8 例 + 4 subtest）+ **`scripts/test_ooxml_lint.py`**（Batch 2，10 例 + 4 subtest）+ **`scripts/test_snapshot.py`**（Batch 2，6 例）：回归测试
- **`ensure_settings.py` +3 项治理自检**（D12 备份膨胀）：活跃目录文件数 / scratch 超期 / 快照库超容；7→10 项

### Changed
- **`.claude-plugin/plugin.json` + `.codebuddy-plugin/plugin.json`**：version 3.1.0→3.2.0；description 去 `veterinary medicine` 改 `domain-portable`；通用化声明
- **`harness.py cmd_gate`**：lint 前置集成（ERROR→exit 1 阻断）+ snapshot 写回前自动打点（`--no-snap` 可跳）
- **`ensure_settings.py`**：7 项→10 项，+3 项治理自检（D12）；脚本清单 7 个→10 个（+extract_assets/ooxml_lint/snapshot）

### Discipline
- **D11 修复对话框**（用户实锤痛点）：ooxml_lint 四层防线（lint/基线/纪律/病例库）
- **D12 备份膨胀**（用户实锤痛点）：snapshot.py + 治理自检 + 一原一活模型
- **v4 通用化**：项目层与常驻用户层解耦；样本可换；agent ID 命名巧合保留；description 改通用
- **陈述真实性律**：4 份挂账样本 lint 全 0 ERROR = 实证"用户痛点不是普遍"事实修正（XML-003 a:t 空格 WARN 15+8+6+2=31 次，与学科无关）

### Batch 状态
- Batch 1 ✅ 完成（2026-10-14 上午）
- Batch 2 ✅ 完成（2026-10-14 上午）
- Batch 3-5 待确认后实施

---

## [v3.1.0] - 2026-10-14

### 概述（第三轮：闸外防护 + 用户五条纪律 + 状态自愈）

v3.0.0 发布后 10 天的真实使用数据（trace/state/registry 全空、10-13 大清理把状态层抹掉）暴露一个根本性缺口：v3.0.0 修的是"被调用时的行为"，**没有任何机制保证"它被调用"**。v3.1.0 不再只盯闸内，**给闸外也装上钩子**：闸外产物能事后收编、状态基础设施缺失时专家团能自愈、用户五条工程纪律入各角色提示词。

### Added
- **`harness.py sweep`（P0-1 闸外收编）**：扫描工作区全 .pptx，逐份跑 SSOT 门禁，从课件现状重建 `deck_registry.json`（**不依赖任何 checkpoint**），含 `judge_provenance`（SSOT/版本/3.1.0/课时口径来源 csv 或 default）与 `disposition` 字段（verifier 挂账审判落点）。课时口径支持 CSV 显式声明（阶段1 冻结值），绝不按页数反推
- **`preflight` 环境自愈提示（P0-3）**：检测工作区 `.workbuddy/` 三件套（task_state/deck_registry/trace）状态，缺失则报 `degraded_env` 并给一行重建指引（state init / sweep）。实测 10-13 实例：环境被外部清理时专家团此前毫无感知，现在报"环境缺失但冷启动合法"
- **`harness.py gate --dry-run`**：verifier 只读边界——不写 JSON、trace 仍记

### Changed
- **6 个 agent MD 全部纳入用户五条工程纪律**（v3.1.0，2026-10-14）：
  - **陈述真实性律**（主理人 MD + verifier 抽样复核）——反幻觉/不虚报完成/陈述可核查/数字与历史一致；反面教材：2026-10-13 的清理清单"39 隔离候选"实际只移走 2、且丢失 2 个原始目录未在清单外披露
  - **一图一 ipynb**（屠明熙主责）——图与代码必须绑定，先改代码再出图
  - **输入输出路径标明**（屠明熙主责）——绝对路径，输出 pdf 格式
  - **文件治理律**（主理人 MD）——优先改旧非必要不新建；清理只能产清单，动手必须用户圈定；清单与实际一致
  - **CLAUDE.md 索引同步**（主理人 MD 文件治理子条款）
- 成员回传 schema 增 `self_check`（一句话自述本回传最可能不实的点，verifier 定向核查）

### Fixed
- `verify_deck.py` 写 JSON 前 `os.makedirs(..., exist_ok=True)`——根因：冷启动时 `.workbuddy/` 不存在导致所有 JSON 报告失败，sweep 测试中逮住
- `sweep` 预创建 `.workbuddy/`，与上一条配套

### 验证
- `test_harness.py` **16/16 通过**（v3.0.0 13/13 + 3 条新：sweep 重建台账 / preflight 环境报告 / gate --dry-run 不写盘）
- 安装态 `ensure_settings.py` **7/7 全绿**（6 agent / 7 脚本 / 唯一裁判 / 回归自跑 / 版本一致）
- 端到端：M4A1 实测 `sweep` 4 份课件 3 秒收编；P0 总 62，3 份被阻断（其中"禽流感病毒全链攻防术" P0=34 + 备注 0%——正是闸外未受护约束生产）

### 已知遗留
- 36 份历史 `deck_registry` 已无 checkpoint 可继承（10-13 清理抹掉），`sweep` 是新基线
- 14 份旧课件 P0>0 的挂账审判仍待 verifier 在闸4 首次运行时批量清偿（`sweep` 已输出 `P0_blocked_list`，verifier 直接据表行事）
- `overlay_injection` 四键（min_font_pt/require_empty_slot/max_overlap_ratio/sample_review_ratio）**仍零脚本消费**——R18 事故的对症药，下一版
- token/成本仍不可观测（平台不向主理人暴露成员用量），不以估算冒充

---

## [v3.0.0] - 2026-10-04

### 概述（第二轮组织诊断落地：唯一裁判 + 独立验证 + 四道闸）

管家节点裁决四项全部执行：① 郅作基降级为按需调用（职责保留）② 新增按需验证者 ③ 门禁归一（非权威版降级不删）④ P2 覆盖率计入机器草稿但单独统计占比并明示。

本轮先修**致命问题**（安装态门禁不可执行、同一批课件两个结论），再改组织（角色/流程），最后补机制（信封校验、护栏下沉）。

### Fixed（三个致命问题，均由本轮实测逮住）
- **安装态机器裁判断链**：整仓克隆导致根级 `scripts/` 只剩 1 个文件，6 个核心脚本（verify_deck/harness/surgery_deck/inject_notes/ensure_settings/test_harness）缺失 → MD 里的门禁命令必然 FileNotFoundError。已补齐并加第 5 项体检（全脚本完整性）
- **唯一裁判缺失（B0）**：门禁语义曾有**三处各自独立的定义**——专家包 `verify_deck.py`（724 行，分级门禁）、工作区 `.claude/skills/vet-ppt-pipeline/verify_deck.py`（375 行，**无 `--level`**，被台账引为权威）、工作区 `registry_rebuild.py`（私自定义 `P0_KEYS` 排除"课时不达标"）。同一批 36 份课件得出 P0=15 与 P0=0 两个结论。
  实测追查定案：**真因是课时口径而非 P0 定义**——非权威版用 `--auto-hours` 按可见页数反推课时，故永远"匹配"；权威版要求显式 `--hours`。修法：宣布专家包版为 SSOT、非权威版降级为"非门禁工具"（加显著横幅 + 运行告警，不删）、`registry_rebuild.py` 改为只读 yaml、台账新增 `judge_provenance` 与 `caliber_warning`
- **`--hours` 由默认值改为必填**：原默认 3 会凭空判出"课时不达标"（B0 口径混乱源头之一）
- 顺带：台账 md5/mtime 快照全部失效（36/36）→ 重建后刷新；`gate_cmd`/`ssot` 字段改指 SSOT

### Added
- **`agents/verifier.md`（都衡言，独立验证官）**：承接此前完全缺失的 V 层。依据是硬证据——**自评失真在 v1.5.1→v2.2.0 四个版本全部复发，跨 11 天一次没修好**（每轮修的是规则文本，不是产生自评的机制）。职责：自己重跑门禁复算（不采信任何自报）、裁判口径变更第二签、P0 挂账逐条审判（修/降级/例外签字）、抽页 ≥20%
- **`harness.py verify-envelope`**：把 `result_envelope` 从文档约定变成代码校验（六字段齐备 + status 合法 + 产物路径交叉核验）
- **`avatars/verifier.png`**
- 回归测试从 10 → **13 例**（新增信封校验、judge 溯源字段、`--hours` 必填、机器草稿占比）

### Changed
- **流程：六阶段（0–5）→ 四道闸（0–3）**，确认门由"最少 2 最多 6"降为**固定 2 次**（设计确认 + 交付终审）。依据：实测 1 课时任务跑到阶段3 已耗 25 分钟；`stage_history` 75% 是 SOP 外非法值、`current_stage` 合法率 0/4
- **角色**：郅作基职责一条未删但**不再常驻 spawn**（判据落点是 `harness.yaml#routing` 的默认 spawn 计划，不是角色存废；取证明确反对删除 M 级职责）；屠明熙职责收窄（红线参数与外科判据文本迁出，人只做高价值页设计与抽样裁决）；**二者不得合并**（Maker/Checker 对偶是 R18 防线）
- **P2 覆盖率口径（裁决④）**：机器草稿**计入**覆盖率，但门禁单独输出 `machine_note_ratio`，终检清单要求交付物明示"其中 m 页为 AI 草稿，待教师复核"。依据：`inject_notes.py` 的 bootstrap 会批量生成讲稿，不统计就等于把没人复核的机器文本算作达标
- **`ensure_settings.py` 4 项 → 7 项**：新增全脚本完整性、唯一裁判检测（包内同名 `verify_deck.py` 只许 1 份）、回归测试自跑
- **护栏下沉**：`verify_deck.py` 开始真正消费 `config/visual-rules.yaml#severity`（此前 `registry_rebuild.py` 私自定义同名常量）
- 规则去重：agents 内门禁规则定义收敛为**唯一定义源** `references/harness-engine.md#6`（其余改为引用）

### 平台铁律备忘（写进来避免下轮重犯）
⚠️ **WorkBuddy 专家包不支持 agent frontmatter 的 `tools:` 字段**（2026-09-30 实测确认，v2.2.0 的白名单方案已回退）。
最小权限只能靠：① `assemble_spawn_prompt.py` 确定性注入人设 ② 任务包四要素约束 ③ `harness.yaml#members[*].tools_whitelist` 作为编排意图声明。

### 已知遗留（如实挂账）
- 36 份课件的历史 P0/P1 计数继承自**旧口径** checkpoint（`--auto-hours`），台账已加 `caliber_warning` 标注；**须用 SSOT + 显式 `--hours` 重跑全量**才能得到可比结论，本次未做（涉及 36 份课件只读全量扫描，另行安排）
- 14/14 课件挂账超 3 天、58 个残余 P0 **尚无处置记录**；已把"挂账审判"写入 verifier 职责，待闸 4 首次运行时批量清偿
- `overlay_injection` 四键（`min_font_pt`/`require_empty_slot`/`max_overlap_ratio`/`sample_review_ratio`）**仍零脚本消费**——R18 事故的对症药尚未装上，属 B2 批次待办
- token/成本仍不可观测（平台不向主理人暴露成员用量），不以估算冒充

---

## [v2.2.0] - 2026-09-29

### 概述（Harness 工程化：把编排纪律从提示词下沉为代码）

对专家团做了一次完整闭环诊断（定位通读 → 实测 → 九维度诊断 → 对标 → 重构 → 同任务重跑验证）。
实测暴露的核心事实：**专家团的"专业方法论"密度很高，但"执行框架"几乎为零**——
成员不可调度即整链阻断、平台静默降级无人察觉、门禁脚本撞出 3 个未发现的崩溃、全程零日志零预算。
v2.2.0 不改动原有核心目标与使用方式（仍是六阶段门控 + 四成员 + 分级门禁），
只在**编排层新增确定性内核**，把"靠自觉"的纪律变成"靠代码"的约束。

### Added
- **`config/harness.yaml`（新增）**：编排层唯一数据源——显式状态机 `stages`（只认 0–5 整数）、成员注册表（职责 + **工具白名单** + 降级通道）、复杂度→spawn 路由表、预算护栏（spawn/rework/react 上限 + 阶段挂钟上限 + 产物字节上限）、上下文隔离策略、trace 配置、门禁退出码语义
- **`scripts/harness.py`（新增，确定性编排内核）**：6 个子命令——
  - `preflight`：开工前成员可用性预检，**专抓"平台把成员静默降级为 general-purpose"**（实测抓到严真奥）
  - `route`：复杂度 L0–L3 → 确定性 spawn 计划
  - `state`：状态机读写与校验（拒绝非法阶段值、拒绝白名单外的键、超限强制 compaction）
  - `budget`：任务级预算计数（纪律变计数，超限即阻断并写 trace）
  - `trace`：JSONL 执行日志 + `report` 汇总（事件计数 / 按成员统计 / 阶段耗时秒数）
  - `gate`：包装 verify_deck，统一退出码语义并落 trace 与耗时
- **`references/harness-engine.md`（新增）**：人读入口，规定开工三步、降级协议、状态机纪律、预算用法、上下文隔离、统一门禁入口
- **`scripts/test_harness.py`（新增）**：9 条回归用例（路由确定性 / 状态合法性 / 白名单 / 预算阻断 / trace / preflight / 静默降级探测 / 门禁不崩溃），本包首个测试文件

### Changed
- **工具白名单（P0）**：5 个 agent MD 的 frontmatter 新增 `tools:`（与 `harness.yaml#members` 同源），结束"成员默认继承宿主全部工具"的状态
- **降级协议（P0，规则修订）**：旧规则"Agent tool 不可用＝任务阻断"改为 **"先降级，后阻断"**——同一成员最多 2 次尝试，仍不可用则 spawn 通用子代理并**注入该成员 MD 全文**（人格与红线照旧生效），且必须在交付物与 trace 中显式声明。**红线未松动：任何情况下禁止主理人代写成员产出**
- **状态机纪律（P0）**：`task_state.json` 只允许白名单内键、阶段值只认 0–5 整数（杜绝实测中出现的 `M5A2` / `stage_6` / 32 键 27KB 膨胀）
- **统一门禁入口（P0）**：阶段5 一律走 `harness.py gate`，**exit=4（运行错误）走缺陷回流修脚本，不得当作课件红灯打回成员**
- 主理人 MD 新增「编排内核」节；`sop-stages.md` 阶段0 新增开工三步、阶段5 换统一入口

### Fixed（三个被实测当场撞出来的崩溃，全部是"没有回归测试"的后果）
- **越界检测崩溃**：形状几何元组含 `None` 时 `x < -tol` 抛 TypeError → 整个门禁 exit 4（实测 `7. 禽流感.pptx` 触发）。修复：几何取不到记 `parse_errors`（P3 明示），不参与比较
- **重叠检测崩溃**：同上，`_overlap_area` 的 `max()` 收到 None 崩溃（修完越界后暴露的第二处）。修复：比较前过滤含 None 的矩形
- **字号比较崩溃**：`sizes` 含 None 时 `min()` 返回 None 后与阈值比较崩溃（第三处）。修复：过滤 None，取不到字号记 `unknown_font`
- **静默回退护栏可绕过**：`visual-rules.yaml` 加载失败时静默用内置阈值继续裁判——改**硬失败**，仅 `VERIFY_ALLOW_FALLBACK=1` 才回退（并醒目告警）
- **错误不可诊断**：verify_deck 顶层只打印一行错误信息、吞掉 traceback → 主理人无法区分"课件有问题"与"脚本有 bug"。修复：打印完整堆栈 + 错误类型 + 处置指引

### 实测对比（同一任务 T 重跑，详见 outputs/harness-ab/REPORT.md）

| 指标 | v2.1.0 基线 | v2.2.0 重跑 |
|---|---|---|
| 苏学法（页表产出） | ❌ 3 次调度失败 → 阶段3 整链阻断 | ✅ 降级通道产出（通用子代理 + 注入成员 MD） |
| 静默降级 | ❌ 严真奥被登记为 general-purpose，无人察觉 | ✅ preflight 显式报 `degraded` 并给处置建议 |
| 门禁（曾崩溃课件） | ❌ exit 4 崩溃，无法判定 | ✅ exit 1：P0=5 / P1=1 / P2=0% / P3=1，可判定可修复 |
| 执行日志 | ❌ 无 | ✅ JSONL trace（事件/成员/阶段耗时） |
| 预算护栏 | ❌ 无计数 | ✅ spawn/rework/react 计数，超限阻断 |
| 回归测试 | ❌ 0 用例 | ✅ 9/9 通过 |

---

## [v2.1.0] - 2026-09-26

### 概述（v2.0.0 挂账清单执行：P1 版面外科 + P2 备注覆盖率，修复能力沉淀为正式工具）

对 14 份真实课件执行 v2.0.0 定义的挂账修复，并把可复用能力固化为专家团工具。**全程按"工具自报不算数、verify_deck 复验才算数"纪律执行。**

### Added
- **scripts/surgery_deck.py**：批量版面外科工具（屠明熙出判据/郅作基执行）——重叠卡位迁移（网格搜空位、注入卡优先、避图 30%、找不到空位如实记 unresolved）+ 越界画布内微调；dry-run 先行、偏好 C 备份后执行
- **scripts/inject_notes.py**：讲稿备注注入工具——按页面真实内容生成【AI草稿·待教师复核】讲稿四件套（本页定位/讲授要点/讲法建议/提问话术/易错提醒），含纯图片页指图讲分支；内容多的页优先，补到 P2 覆盖率达标即止
- **deck_registry.json `v2_1_0_pass` 记录**：每课件的手术统计/备注注入数/复验退出码，前后对照可追溯

### Fixed（工具开发过程中被复验当场逮住的三个 bug，全部反成纪律教材）
- **漏 save 空转**：surgery_deck 首版在内存改完形状未写盘，"迁移 515"全部无效——verify_deck 复验重叠数纹丝不动当场逮住。教训固化：**工具自报数不算数，复验才算数**
- **容差单位错**：0.25 英寸容差被当 EMU 比较（≈0），把装饰性微出血误判为越界去"修"——P0 计数与复验对不上（修了 21 处 P0 只降 1）暴露
- **单文本框页漏检**：`len(texts)<2` 守卫本意是跳过无重叠可能的页，却把越界检测连带跳过（M4C1 P3"标题标签+大图"型页面复现）——守卫改为只管重叠阶段

### 实测结果（14 份课件，verify_deck --level all 现场复验口径）
- **P1：728 → 210**（-71%；重叠大头已清，残余=文字墙 56+过满页未解重叠，拆页属内容决策留苏学法工作流）
- **P2 备注：13/14 不达标 → 14/14 覆盖率 ≥80%**（注入 195 页 AI 草稿讲稿，全部显著标注待教师复核）
- **P0：60 → 58**（越界清零；残余 58=配色/目录/题页/课时结构决策项，非脚本范围，如实挂账）
- deck_registry.json 全程记录前后对照（gate_pre_v210 → gate_post）

---

## [v2.0.0] - 2026-09-26

### 概述（v1.9.0 首战实测驱动：M4A1 六阶段流水 + 14 份课件现场复跑 1281 条红灯 0 份全绿；报告：outputs/vet-med-ppt-team_v2.0.0实战诊断与改造方案_20260926.md）

核心发现：①写回门禁三态失效（宣告式——stage5 四项 deviations 上升用户拍板；不可达式——"全清"物理不可达必被绕过；崩溃式——M4D2 unrecognized shape type 致裁判 exit=2）；②最大红灯源是团队自己的 A 轨叠加层法（只加框不重排 → 元素重叠 486 处居首；试做 12pt 批量写成 8pt，R18 同型两张皮复发）；③职责真空三处（几何修复/讲稿备注/砍页裁决）；④自评失真（final_report 同文件"三维归零"与 38+28 未修并存）；⑤屠明熙 v1.9.0 转型副作用（批量几何施工能力被抽走）。

**角色结论：不增删不合并（4 成员正交无冗余），以职责回补 + 规则项补齐代替加人。**

### Added
- **分级门禁（本版核心）**：红灯四级——P0 硬阻断（字号/越界/配色/空白/课时/目录/题页，写回前必须=0）/ P1 必清（重叠/文字墙，可带修复计划写回、交付前清零）/ P2 指标（备注覆盖率 ≥80%）/ P3 明示（继承未取到/解析异常/装饰出血）。门禁判据从"全清"改为"P0=0"，可达即可执行
- **verify_deck.py v2.0.0**：`--level P0|P1|all` 参数；退出码语义 0=通过/1=P0/2=P1/3=P2/4=运行错误；逐形状 try/except + XML 兜底解析（抗 mc:AlternateContent 崩溃，M4D2 实测恢复可判定）；字号继承解析链（run→段落 defRPr→版式占位符→母版 txStyles，2.1HPAI 盲区 77 处大幅收敛）；隐藏页纳管统计；分级计数进 JSON 报告
- **references/batch-surgery-sop.md**：批量版面外科 SOP（屠明熙所有）——叠加层注入四前置断言（空位检测/字号≥12pt/重叠≤15%/逐页清单）、几何红灯修复四级顺序（缩小→移动→拆页→删冗余）、拆页规则与验收
- **config/visual-rules.yaml 新增三节**：`gate`（p2_note_coverage 0.80 + 写回/交付级别名）、`severity`（分级映射，单一数据源）、`overlay_injection`（注入规范）
- **苏学法页表三字段→五字段**：+`speaker_note`（每页讲稿 ≥80 字，备注产出权归苏学法——241 页缺备注挂账无主的对症药）、+`page_role`（core/extended/optional，砍页依据链：苏学法定角色→郅作基按 optional→extended 执行——stage5 砍页双向落空的闭合）；课时表新增"扩展阅读"档
- **主理人阶段0 两项强制裁决**：隐藏页处置（恢复/删除/保留+明示数量）+ 页数口径（正式课时 vs 扩展阅读分开计数）——阶段5 不得就同一问题再上升用户
- **deck_registry.json 全局台账（郅作基）**：manifest 升级为跨任务活台账（mtime/md5/页数/隐藏/P0-P3/备份/first_seen），冷启动扫描 P0>0 且挂账 >3 天必须主动上报用户；已由 repair_p0_v200.py 建立 14 份种子账
- **反自评失真红线（adjudication-rules.md）**：禁"归零/100%"表述除非引用 verify_deck 原始计数；强制结论格式 `P0=x/P1=y/P2 n%/P3 k处`；终检页面性门必须附原始输出片段

### Changed
- **屠明熙职责回补**：规则引擎之外加挂"批量版面外科 SOP 所有者"（出判据不施工，Maker/Checker 不破坏）；抽样复核量化 ≥20% 且几何红灯页 100% 复查（原 10% 实测挡不住 486 处重叠）
- **郅作基写回门禁改分级语义**：`--level P0` 写回 / `--level all` 交付；deviations 纪律——P0/P1 项主理人必须先组织修复，不得作为待决事项上升用户拍板
- **sop-stages.md 阶段5 重写** + 修复既有"两个 5."编号错误；阶段3 七字段→九字段（教学列五字段＋版式列）

### Fixed（存量回修，用户批准执行）
- **14 份课件字号 P0 回修**：1125 处钳制（run 1104 + defRPr 0 级别按份计），阈值直接 Read visual-rules.yaml；**P0 总量 681 → 60**（字号类全清，残余 60 为配色/目录/题页/课时等结构决策项）；偏好 C 备份链完整；deck_registry.json 记录前后门禁计数

---



## [v1.9.0] - 2026-09-26

### Changed（v1.8.0 后 14 天实战诊断驱动：郅作基 0/14 天未上场 + R18 事故 258 处字号红灯 + 门禁无人值守；报告：outputs/vet-med-ppt-team_v1.8.0实战诊断与改造报告_20260926.md）
- **屠明熙转型"视觉规则引擎架构师"**：红线参数化至 config/visual-rules.yaml（唯一数据源，verify_deck 与批量脚本共同消费）；高价值页（封面/机制流程图/预测-揭示对）保留人工设计；批量场景规则布防+抽样复核。核心理念：**人可以不在场，规则必须在场**
- **郅作基转型"课件执行工程师"**：写回门禁（Write-Gate）硬性职责——任何课件写回磁盘前 verify_deck 红灯清零+manifest 页数核对+备份确认，无例外（主理人亲自施工也过门禁）；批量脚本合规驾驶（前置断言：缩字号 <12pt 直接拒绝）
- **主理人 L0-L1 施工合法化**：单件任务诊断后主理人可直接修改（09-23 两任务验证高效）；L2+ 批量仍禁代写。原"严禁亲自施工"教条按实战修订
- **课件改造三级路径固化**（R16/R17 实测结论制度化）：①A 轨轻改造全员批量(~30min/课件)→②B 轨三段倒序重点课件(15-25min/页)→③A 轨真重构精品(完整六阶段)；每级注明执行/验收人

### Added
- **config/visual-rules.yaml**：字号/容量/几何/课时页数/图注五要素五节红线参数，单一数据源；verify_deck.py THRESHOLD 改为动态加载（yaml 失败回退内置值并告警），改造前后裁判判定一致性已实测（M5A1 258 处红灯不变）

---

## [v1.8.0] - 2026-09-18

### Changed（John Conway 教育洞察注入，宪法级；四项裁决：宪法级/疾病课倒序/双侧同步/职业生存转化）
- **主理人第一性原理 5→6 条**：原理4 重写为 Conway 原命题「讲有趣的内容可以达到教育的目的；讲有用的内容达不到教育的目的」+ 三条操作化禁令（禁考点式组织/禁知识清单平铺/先过有趣关再过完整关）；新增原理6 权威律（权威=知道学生需要什么；知识诅咒防线：高职大二学生视角默认）

### Added
- **苏学法 · 预测-违反-更新导入律**：每模块开场强制学生预测（猜失败案例成因/判病变归属），预期正确率 30-60%；禁用成功故事开场
- **苏学法 · 二八难点定位**：蓝图必标约 20% 影响 80% 理解的关键难点清单，页数与互动密度向其倾斜
- **苏学法 · 双轨教学结构**：顺序轨（案例→理论→实践→总结）/倒序轨（场景→功能→结构→原理）；疾病课默认倒序、诊断技术课默认顺序、模块级切轨
- **苏学法 · 能力3 升级为隐性知识师徒传承**：塔西图隐性知识显性化 + 知识诅咒自检（每页问"学生具备前置知识吗"）+ 输出→讨论→思考→再输出闭环 + 每课至少 1 个元认知目标（学会学习）
- **严真奥 · 知识诅咒标注**：证据包概念必标「学生已知/需铺垫/易误解」三类；「易误解」自动进二八难点候选；隐性知识线索标注
- **屠明熙 · 预测-揭示版式对**：预测页（大问题+选项大字+倒计时视觉）→揭示页（你以为vs实际是对照+惊讶点强调色）；权威感视觉律（视觉焦点=学生下一步需要的，非我们想展示的）
- **studio v2.5.0 同步**（用户裁决双侧）：SKILL.md 注入 Conway 有趣律/预测律/二八/双轨/知识诅咒五律 + 预测-揭示版式对；teaching-style.yaml 新增 conway_interest_law 配置块（YAML 已验证）

---

## [v1.7.0] - 2026-09-18

### Changed（Harness 工程化重构，基于 2025-2026 领域规范检索：Anthropic 四支柱/四失败模式、OpenAI 百万行实验、Anthropic 多智能体研究系统）
- **主理人 MD 深度瘦身：212 行/24.2KB → 141 行/10.1KB（-58%）**——六阶段 SOP 细节与裁决/终检规则下沉至 references/（sop-stages.md + adjudication-rules.md），主理人 MD 只留索引+红线+schema+路由表。对齐 OpenAI "AGENTS.md ~100 行索引+地图" 规范，spawn 上下文负载减半，破 40% sweet spot 风险消除
- **阶段4 复检改非作者交叉复检（Maker/Checker 分离）**：教学性改动→严真奥复检、科学性改动→苏学法复检、页面性改动→苏学法复检——复检人≠产出人，只答「从我的专业视角会不会埋雷」。对齐 Anthropic "Agents are incapable of accurately evaluating their own work"

### Added
- **任务复杂度分级（L0/L1/L2/L3）**：微任务直调零编排 / 轻任务 1-2 成员 / 标准 6 阶段 / 重任务打样-流水线+可选 RedTeam。对齐 Anthropic "Scale Effort to Query Complexity"（防简单任务过度编排、复杂任务偷工）
- **下发任务包 schema（四要素委派协议）**：objective/output_format/constraints/task_boundary，spawn 必附；并行任务边界互斥。对齐 Anthropic "Teach the Orchestrator to Delegate"（防重复劳动与覆盖缺口）
- **阶段5 终检结构化清单**：科学性门/教学性门/页面性门/交付完整性门四门逐项打勾，任一不过打回
- **缺陷回流协议（熵回收）**：同类错误≥2次触发，流程缺陷→改规则、知识缺陷→严真奥知识回注、脚本缺陷→升级脚本。对齐 Mitchell Hashimoto "每发现一个错误就工程化消除其再现" + OpenAI 熵垃圾回收
- **Compaction 最小集策略**：task_state.json 新增 compaction 字段（task_id/current_stage/关键决策/文件路径四必保），冷启动恢复=最小集+对应阶段章节，禁止重读全部历史。对齐 Anthropic 记忆持久化规范

### References 新增
- references/sop-stages.md（六阶段完整 SOP + task_state 规范 + Compaction 策略）
- references/adjudication-rules.md（裁决优先级 + 六项自检 + 终检四门清单 + 缺陷回流协议 + 安全合规）

---

## [v1.6.0] - 2026-09-18

### Added（用户教学理念 DNA 有机注入，经四项裁决：两边同步/扩展课时表/参数化泛养殖/分层时限）
- **主理人 · 第一性原理 3→5 条**：新增「职业教育的核心产品是学生的自信」（可达成任务+及时正向反馈）与「讲有趣的故事达成有用的教育」；新增「三层内容律」（是什么/为什么这么做/现场会遇到什么坑）
- **苏学法 · 疾病课十模块模板**：疾病专题课专用架构（导入→病原→流行→临床病理→机制免疫→综合诊断→防控→案例决策→总结思政→测评），与诊断技术课八大模块并存，按课型选用；含裁剪优先级（保1/4/6/8→压2/3/5→并7/9→测评10独立保留）
- **苏学法 · 课时表新增 1 小时教学单元档（60min=35-50页）**：用户「约1小时」授课习惯的标准档；verify_deck.py 同步支持 --hours 1.5（float 类型）
- **苏学法 · 测评量化指引**：3-5 道选择题 + 1 道综合案例分析题（人机协同+批判性核验 AI 输出+现实可行性），附参考答案与评分要点
- **苏学法 · 故事化与费曼翻译**：比喻库沉淀于教学蓝图，同课件比喻体系一致
- **苏学法 · 学生自信设计律**：每学习单元至少 1 个可达成分析任务（10min 内完成+可判对错），参考答案含表扬要点；后进学生每课至少一次成功体验
- **苏学法 · 三层内容律（页面脚本强制字段）**：每模块三层覆盖，缺层须在蓝图风险栏标注
- **严真奥 · MSD Vet Manual 入列正式权威源**（国际组织之后、综述之前）
- **严真奥 · 文献时限分层律**：诊疗/流行病学/疫苗毒株/禁药=近5年；机制类/基础免疫学=近10年；教材与指南不受限但须核现行版本
- **严真奥 · 一体化养殖企业实战经验供给**（物种参数化：默认禽，可换猪/牛羊/伴侣动物）：为三层内容律第③层供素材（育种/饲养/营养/环控/设施全链路实战偏差）
- **屠明熙 · 图注五要素制**：对照关系+物种/日龄/病程+来源许可+教学意义+（示意图）免责声明，缺一不可
- **屠明熙 · 机制页强制流程图版式**：病原入侵-复制-扩散等动态过程禁止大段文字，必须流程图/时序图（配合十模块第5模块）
- **同步 studio v2.4.0**：SKILL.md 双课型架构+坍缩映射表新增养殖全链路模块+P2 分层时限+P3 加 MSD+Step3 页数预算加 1 小时档；teaching-style.yaml 新增 content_three_layers / course_architecture / assessment_quantum 三配置块+两大理念入 core_beliefs

### Added
- **ensure_settings.py 升级为 doctor（4 项体检 + 1 项自愈）**：从"恢复 settings.json 单点工具"升级为发布前强制门禁。诊断耗时 <1s，4 项全绿才能发布
  1. settings.json 存在且 `agent` 字段与 plugin.json 一致 → 缺失/损坏则**自愈**重建
  2. `.codebuddy-plugin/plugin.json`（WorkBuddy 侧）与 `.claude-plugin/plugin.json`（Claude Code 侧）版本号一致 → 漂移则告警【只读】—— `validate_expert.py` 只校验前者，单靠官方工具查不出此项（2026-09-17 实证 v1.4.1→v1.5.1 漂移 2 个小版本未被发现）
  3. 清单声明的 5 个 agent 文件全部存在 → 缺失则告警
  4. `scripts/verify_deck.py`（机械验证门禁）随包分发 → 缺失则告警
- **vet-med-ppt-team.zip 重打包**：旧包停在 2026-09-12 的 v1.4.1（仅 20 文件、无 scripts/、无 docs/），新版 32 文件、含 scripts/、含 docs/repo-meta/

### Changed
- **UPGRADE.md「修改后必做」段落**：从"必跑 ensure_settings.py 单点恢复"升级为"必跑 doctor 4 项门禁"。两插件清单版本漂移是导致 settings.json 反复丢失的潜在根因之一（每次手动 cp 都可能遗漏另一侧）

### Fixed
- **本插件包 5 次丢失 settings.json（2026-09-12、09-17×4）**：从"事后手动恢复"升级为"事先检测+事后自愈"闭环。同 marketplace 下其他 4 个 Team 型专家因未被持续修改而不丢失，确认删除源是 WorkBuddy 宿主热重载，不是随机故障

---

---

## [v1.5.2] - 2026-09-17

### Added
- **ensure_settings.py 升级为 doctor（4 项体检 + 1 项自愈）**：从"恢复 settings.json 单点工具"升级为发布前强制门禁。诊断耗时 <1s，4 项全绿才能发布
  1. settings.json 存在且 `agent` 字段与 plugin.json 一致 → 缺失/损坏则**自愈**重建
  2. `.codebuddy-plugin/plugin.json`（WorkBuddy 侧）与 `.claude-plugin/plugin.json`（Claude Code 侧）版本号一致 → 漂移则告警【只读】—— `validate_expert.py` 只校验前者，单靠官方工具查不出此项（2026-09-17 实证 v1.4.1→v1.5.1 漂移 2 个小版本未被发现）
  3. 清单声明的 5 个 agent 文件全部存在 → 缺失则告警
  4. `scripts/verify_deck.py`（机械验证门禁）随包分发 → 缺失则告警
- **vet-med-ppt-team.zip 重打包**：旧包停在 2026-09-12 的 v1.4.1（仅 20 文件、无 scripts/、无 docs/），新版 32 文件、含 scripts/、含 docs/repo-meta/

### Changed
- **UPGRADE.md「修改后必做」段落**：从"必跑 ensure_settings.py 单点恢复"升级为"必跑 doctor 4 项门禁"。两插件清单版本漂移是导致 settings.json 反复丢失的潜在根因之一（每次手动 cp 都可能遗漏另一侧）

### Fixed
- **本插件包 5 次丢失 settings.json（2026-09-12、09-17×4）**：从"事后手动恢复"升级为"事先检测+事后自愈"闭环。同 marketplace 下其他 4 个 Team 型专家因未被持续修改而不丢失，确认删除源是 WorkBuddy 宿主热重载，不是随机故障


## [v1.5.1] - 2026-09-17

### Fixed
- **屠明熙字号红线不可执行**：原定"正文≥24pt"为理论理想值，13.33×7.5in 画布下仅容 8-10 行/页，2026-09 实战 34 课件中**从未被执行**（实际普遍 10-12pt）。改为底线+推荐双轨（正文底线 12pt / 推荐 18-24pt；图注底线 9pt）
- **郅作基路径默认与实战背离**：原以"路径A·交付指令包"为默认，但实战 34 课件全部为已有 .pptx 优化（100% 走 B），六件套从未真正交付。改为"存在待处理 .pptx 时 B 为默认，A 仅用于从零创作"
- **苏学法课时-页数标准缺失**："课时适配"在 R2/R4/R6/R7 四轮反复返工的根因——负责页数区间的角色没有标准值。新增课时-页数换算表（1课时18-28页 / 2课时36-52 / 3课时55-78 / 4课时72-104）

### Added
- **严真奥 · Europe PMC 图片主力通道**：实战中 Ima 图片检索常 0 命中、共享库报 220030、UpNote 无图片，真正稳定的取图通道此前**不在设计内**，属临时发挥。现列为正式主力通道并给出 API、许可、图注三要素、禁用清单
- **严真奥 · 时效敏感字段清单**：疫苗毒株/禁药休药期/诊断标准号/流行毒株每年必须联网核验，防"教去年的法规"
- **严真奥 · 知识回注协议**：成果写入 `knowledge/`，MD 正文只留检索指针（防上下文膨胀）
- **屠明熙 · 美学量化红线**：元素重叠=0、单页配色≤5 种、单页字数≤400（学生视角硬约束：看不见/看不下去 = 教学事故）
- **郅作基 · 交付前机械验证门禁**：必须跑 `verify_deck.py`，红灯清零方可回传（R6 自称四维100%、R9 复验出 3408 处的教训）
- **郅作基 · 快照与 manifest**：改前 `cp` 到 `_backup/`（禁 /tmp）、记录页数+md5、回传前校验页数一致（M4B4 丢 19 页无人察觉的教训）
- **郅作基 · 备注 100% 硬门槛**：新城疫 63 页中 33 页无备注却仍被宣布"达标"
- **scripts/verify_deck.py**：8 项机械验证器，与 Claude Code 侧 `vet-ppt-pipeline` 共用同一裁判（AB 测试可比性的前提）
- **scripts/ensure_settings.py**：settings.json 幂等恢复器

### Changed
- 专家包自包含化：验证脚本内置于专家包（便于日后分享），郅作基 MD 中原 `<skill>/scripts/...` 占位符改为实际路径

---

## [v1.5.0] - 2026-09-17

### Fixed
- **主理人代写漏洞（本次最关键修复）**：v1.3 引入的"Agent tool 不可用 → 主理人代行角色内容"回退规则，与官方 team-spec 五条红线（禁止跳过 TeamCreate 自己模拟成员发言／禁止自己代写成员专业产出）直接冲突。实战后果：2026-09-13 批量任务中主理人以"复合角色"一人代写四名成员产出，六阶段门控全程空转，最终由用户 10 轮迭代兜底。
  - 新规则：成员无法 spawn = **任务阻断**，停止推进 + 向用户明说 + `task_state.json` 标记 `blocked`
  - 明确禁止"复合角色""一人分饰多角""参考成员视角自行综合"等任何变体
- **settings.json 丢失**：插件目录 `settings.json` 缺失致 validate 失败（Team 型必需），已补回并同步（此文件已第三次丢失，属已知竞态问题）

### Changed
- **协作规则第 1 条强化**：`TeamCreate → Agent spawn（name 传 Agent ID）→ SendMessage 回传` 为唯一合法调度路径；成员未成功 spawn 即视为该阶段未完成，禁止推进
- 主理人 MD 增加 v1.5.0 红线条目，写明历史教训与判定依据，防止后续迭代中被再次"容错化"

### Added
- 双轨演进：本团队（WorkBuddy 侧）与 Claude Code `vet-ppt-pipeline` skill 并行 AB 测试，以机械验证脚本 `verify_deck.py` 作为统一裁判

---

## [v1.4.1] - 2026-09-11

### Added
- **双 marketplace 清单**：仓库根新增 `.claude-plugin/marketplace.json`（Claude Code）与 `.codebuddy-plugin/marketplace.json`（WorkBuddy），`/plugin marketplace add virologist/vet-med-ppt-team` 从此真正可用
- **Claude Code 插件清单**：`packages/vet-med-ppt-team/.claude-plugin/plugin.json`（与 WorkBuddy 版内容对齐，满足 Claude Code 目录名规范）
- **私有仓库认证说明**：INSTALL.md 顶部前置条件 + 故障排查新增 401 条目
- **Claude Code subagent 挂载方式**：INSTALL.md 方法 C（agent MD 直接复制到 `~/.claude/agents/`）

### Fixed
- **安装命令语法错误**：`/plugin install virologist/vet-med-ppt-team@packages/vet-med-ppt-team`（语法不存在的路径式引用）修正为标准两步：`/plugin marketplace add virologist/vet-med-ppt-team` → `/plugin install vet-med-ppt-team@vet-med-ppt-team`
- **zip 分发版过期**：内含旧版 team-lead MD（21002B vs 仓库 22471B）且嵌套多余 zip，重新打包并消除嵌套

### Removed
- **skillstash 方法**（INSTALL.md WorkBuddy 原方法 C）：未经本人环境验证的第三方工具指引，移除以避免误导

---

## [v1.4.0] - 2026-09-10

### Changed
- **路径决断权属主理人**：郅作基不再自主选择路径A/B；由主理人在 task_state.json 的 `next_action` 字段下发
- **路径B偏差裁决协议**：handoff_out.json 的 `deviations_from_handoff` 非空时强制主理人裁决，郅作基不得自主整合

### Fixed
- **pending_items 流转丢失**：主理人终检项新增"遗留待办转发"，用户能拿到 teaching-ppt-studio 的待补充清单
- **预取事实过期**：严真奥阶段2启动前校验 task_state.json，用户改需求后强制重新检索而非盲目沿用阶段1预取
- **task_state.json 并发冲突**：原子比对 task_id，检测到并发立即停止推进并报警

---

## [v1.3.0] - 2026-09-10

### Added
- **统一回传 schema**：所有成员回传主理人使用 `{from, stage, artifact, warnings, evidence_used, next_recommendation}` 结构
- **任务状态文件 task_state.json**：长任务中断/切换会话时主理人必读恢复状态
- **工具/通道不可用回退表**：TeamCreate / SendMessage / Agent tool / Ima 四通道全覆盖

### Fixed
- 严真奥 vs 屠明熙医学图像归属边界模糊（C1）
- 路径B移交 schema 字段与 teaching-ppt-studio 不齐（C2）
- 阶段3并行任一方超时阻塞（L1）
- 严真奥 ReAct 循环无限（L2）
- 阶段1预取与阶段2重检（R1）
- 苏学法案例与评价双独立产出（R2）
- 工具探针双登记（R3）
- 阶段4自查+强制复检双质检（R4）
- Ima 库ID 硬编码（T1）
- UpNote 未做探针（T2）
- python-pptx 路径硬编码漂移（T3）
- SendMessage 无回退（T4）

---

## [v1.2.0] - 2026-09-10

### Added
- **协同路径A/B分流决策表**：郅作基按场景决定输出指令包还是调 teaching-ppt-studio
- **路径B交接协议**：写入 `*.handoff_in.json`，字段对齐 teaching-ppt-studio v2.1.0 schema
- **teaching-ppt-studio 协同入口**：新增「何时使用」「协同入口识别」「协同回传结构」三段

### Changed
- 专家团升 v1.2.0，teaching-ppt-studio 升 v2.1.0（反映协同能力）

---

## [v1.1.0] - 2026-09-10

### Added
- 工具探针协议（markitdown + python-pptx venv 检测）
- 低证据风险跳阶段2门控捷径（用户同意制）
- 阶段1预取机制（严真奥≤5条核心事实）
- 阶段3合并页表单文档（教学列+版式列一表）
- 阶段4质检分轨（单页自查/跨模块回传+diff）
- 任务收尾协议（工作空间记忆写入）
- Ima 路由表下沉至严真奥MD（主理人不直接检索）

### Fixed
- 主理人/严真奥/苏学法/屠明熙/郅作基 11 处问题（含 Ima 路由归属、ReAct 循环无硬限、上下文按需传递、工具编排主动性等）

---

## [v1.0.0] - 2026-09-10

### Added
- 初始版本发布
- 五人 Team 型架构：主理人（Quan Keji）+ 严真奥（Yan Zhen'ao）+ 苏学法（Su Xuefa）+ 屠明熙（Tu Mingxi）+ 郅作基（Zhi Zuoji）
- 六阶段门控流水线：阶段0任务冻结 → 阶段1教学蓝图 → 阶段2证据核验 → 阶段3页面级设计 → 阶段4迭代修订 → 阶段5制作交付
- 3 个预设 Workflow：WF-1 新制作完整流程 / WF-2 旧课件优化 / WF-3 汇报型课件
- 7 个 Ima 订阅知识库默认挂载：《禽病》Avian Disease（主力库）/《猪病》/《牛羊病》/《伴侣动物疾病》/病毒学-免疫学-细胞学/流感/动物疫病诊断技术（WOAH/FAO/WHO）
- 6 张统一风格头像（navy slate-blue 主题）

---

## 路线图（规划中）

- [ ] 严真奥阶段1预取的"≤5条核心事实"扩展为可选的预检索缓存层（写入 `<workspace>/.workbuddy/evidence_cache/`）
- [ ] 阶段3合并页表导出为 JSON Schema（便于其他工具解析复用）
- [ ] 加入"教学竞赛"专属 Workflow（评委视角+说课节奏优化）
- [ ] 加入"翻转课堂"模式（学生预习→课堂答疑的脚本变体）
- [ ] 国际化：英文版 agent MD（中英文双语提示词）

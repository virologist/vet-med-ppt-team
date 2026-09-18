# 更新日志 · CHANGELOG

本文件记录动物医学教学PPT智造团（vet-med-ppt-team）的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

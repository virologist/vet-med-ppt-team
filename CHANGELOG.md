# 更新日志 · CHANGELOG

本文件记录动物医学教学PPT智造团（vet-med-ppt-team）的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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

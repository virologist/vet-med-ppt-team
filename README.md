# Vet-Med Teaching PPT Team · 动物医学教学PPT智造团

> 一个六人专家团（5 名产出成员 + 1 名独立验证员），把任意动物医学教学主题做成证据核验、教学对齐、可直接投影授课的完整PPT方案与页面内容。

![Team Avatar](packages/vet-med-ppt-team/avatars/team.png)

## 这是什么？

**动物医学教学PPT智造团**是一个面向高校动物医学职业本科教学场景的多Agent协作系统。它把"如何做一份科学准确、面向学习结果、可直接投影的PPT课件"这件事拆成**五闸（stage 0–4）门控流水线**，由6个角色协同完成：

> ⚠️ **阶段事实的唯一源是 `config/harness.yaml#stages`**，README 与 `docs/architecture.md` 只解释动机，脚本据此校验。v3.0.0 前的「六阶段（0–5）」、v3.3.0 前的「四道闸（0–3）」均已废弃，仅保留在 `docs/architecture.md` 的「历史沿革」里。

- **主理人 全课吉**（课件总导演）：五闸（stage 0–4）门控调度、跨角色裁决、对外唯一接口
- **严真奥**（动物医学内容专家）：Ima知识库检索+证据分级+术语规范
- **苏学法**（教学法架构师）：反向设计三层学习目标+形成性评价+互动节点
- **屠明熙**（课件视觉设计师）：版式选型+视觉层级+医学图像规范
- **郅作基**（PPT制作师）：制作指令包+teaching-ppt-studio协同+导出检查
- **都衡言**（独立验证官 / verifier）：终检独立复算、裁判口径第二签、挂账审判；不写课件，只写验证报告

## 核心特性

- ✅ **五闸（stage 0–4）门控**——闸门为：闸1 任务冻结 → 闸2 设计（蓝图∥证据）→ 闸3 成稿（页表∥版式）→ 闸4 交付（门禁+独立验证）→ 闸4.5 案例三源核验；默认固定 2 次用户确认（设计确认 + 交付终审），以 `config/harness.yaml#stages` 为唯一源
- ✅ **证据驱动**——7个Ima订阅知识库按主题选1-3个，ReAct循环+硬上限防死循环
- ✅ **教学对齐**——学习目标-活动-评价三件套强制（建设性对齐）
- ✅ **多Agent兼容**——WorkBuddy Team型完整支持；Claude Code/Claude Desktop 通过 TeamCreate/SendMessage 单兵调用
- ✅ **跨工具协同**——与本地 `teaching-ppt-studio` skill 无缝衔接（路径A/B分流决策表）

## 外部依赖（v3.17.0）

**外部依赖：`teaching-ppt-studio` skill（七维量规的上游副本）——非必需，缺失不阻断本包。**

- **七维量规已内化进本包**：`references/seven-dimension-rubric.md`
  （内化自 `teaching-ppt-studio` v2.6.0 的同名文件并做了去领域化改造；上游更新时需重新比对）
- 外部副本**仅用于比对上游更新**；两者不一致时**以包内版本为准**
- **自查命令**：`python3 scripts/check_external_deps.py`
  （缺失会明确打印「未安装 → 本包已内化 …，以包内版本为准」，**不阻断**任何能力）
- **登记位置**：`references/dependency-manifest.yaml`（外部依赖的包内唯一数据源）
- **为什么没写进 plugin.json**：WorkBuddy 专家包清单规范（`plugin-json-spec.md`）的字段全集
  **不存在**依赖声明字段——平台不认的键不写进清单（详见 `references/spawn-protocol.md#4`）

## 仓库结构

```
vet-med-ppt-team/
├── README.md                          ← 你正在看的入口
├── INSTALL.md                         ← 多Agent详细安装指南
├── UPGRADE.md                         ← 维护/更新流程
├── CHANGELOG.md                       ← 版本历史
├── LICENSE                            ← 许可证
├── .gitignore                         ← 忽略规则
├── .claude-plugin/
│   └── marketplace.json               ← Claude Code 插件市场清单
├── .codebuddy-plugin/
│   └── marketplace.json               ← WorkBuddy 插件市场清单
├── packages/
│   └── vet-med-ppt-team/              ← 专家包子目录
│       ├── .claude-plugin/plugin.json ← Claude Code 插件清单
│       ├── .codebuddy-plugin/plugin.json ← WorkBuddy 插件清单（含团队编制）
│       ├── agents/                    ← 5份agent MD
│       │   ├── vet-med-ppt-team-team-lead.md  ← 主理人
│       │   ├── dvm-content-expert.md  ← 内容专家
│       │   ├── pedagogy-architect.md  ← 教学法架构师
│       │   ├── visual-slide-designer.md ← 视觉设计师
│       │   └── ppt-producer.md        ← 制作师
│       ├── avatars/                   ← 6张头像 PNG (512×512)
│       ├── settings.json              ← Team型必需
│       ├── README.md                  ← 子包说明
│       └── vet-med-ppt-team.zip       ← 一键打包分发
└── docs/
    ├── architecture.md                ← 团队结构与五闸（stage 0–4）门控详解（+ poultry-disease-index.md 之外的主要内容索引）
    └── iteration-log-v1.0-to-v1.4.md ← 迭代记录
```

## 快速安装（按你的 Agent 选择）

> **私有仓库提示**：本仓库当前为私有。任何 Agent 执行 `marketplace add` / `git clone` 前需先通过 GitHub 认证——终端场景运行 `gh auth login`（或 `git clone` 时使用已配置 SSH/PAT 的凭据）；Claude Code 场景需本机已登录 `gh`。仓库转公开后此提示可删除。

| Agent | 安装命令 | 详细指南 |
|-------|---------|---------|
| **Claude Code** | ① `/plugin marketplace add virologist/vet-med-ppt-team`<br>② `/plugin install vet-med-ppt-team@vet-med-ppt-team` | [INSTALL.md#ClaudeCode](INSTALL.md#claude-code) |
| **WorkBuddy** | ① `/plugin marketplace add virologist/vet-med-ppt-team`<br>或手动 `cp -r packages/vet-med-ppt-team ~/.workbuddy/plugins/marketplaces/my-experts/plugins/` | [INSTALL.md#WorkBuddy](INSTALL.md#workbuddy) |
| **Claude Desktop** | Settings → Plugins → Add Plugin → 输入 `virologist/vet-med-ppt-team` | [INSTALL.md#ClaudeDesktop](INSTALL.md#claude-desktop) |
| **通用（手动）** | 解压 zip → 放入对应 Agent 的 skill/plugin 目录 | [INSTALL.md#通用](INSTALL.md#通用手动安装) |

## 快速使用

启动任意 Agent 后，说出你的教学主题：

```
帮我把《禽流感》这一章做成2课时的教学PPT，受众是动物医学职业本科大二学生
```

系统会启动**五闸（stage 0–4）**流水线：闸1 任务冻结 → 闸2 设计（蓝图∥证据，两成员并行）→ 闸3 成稿（页表∥版式，两成员并行）→ 闸4 交付（门禁 + 独立验证）→ 闸4.5 案例三源核验。默认固定 2 次用户确认（设计确认 + 交付终审）。

## 版本与维护

- **当前版本**：v1.4.1（2026-09-11）
- **变更历史**：见 [CHANGELOG.md](CHANGELOG.md)
- **更新流程**：见 [UPGRADE.md](UPGRADE.md)
- **架构设计**：见 [docs/architecture.md](docs/architecture.md)

## 许可证

仓库当前为私有（个人使用），预留公开选项。License 见 `LICENSE` 文件。

## 贡献与反馈

这是个人专属教学工具，外部贡献暂不开放。如发现 bug 或有改进建议：
- 在本地仓库 `Claude/vet-med-ppt-team/` 修改
- 通过 `git commit` 记录变更
- 通过 `git push` 同步到 GitHub
- 大版本迭代后重新打包 zip 分发

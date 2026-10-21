# Vet-Med Teaching PPT Team · 动物医学教学PPT智造团

> 一个五人专家团，把任意动物医学教学主题做成证据核验、教学对齐、可直接投影授课的完整PPT方案与页面内容。

![Team Avatar](packages/vet-med-ppt-team/avatars/team.png)

## 这是什么？

**动物医学教学PPT智造团**（v1.4.0）是一个面向高校动物医学职业本科教学场景的多Agent协作系统。它把"如何做一份科学准确、面向学习结果、可直接投影的PPT课件"这件事拆成6个阶段门控流水线，由5个角色协同完成：

- **主理人 全课吉**（课件总导演）：六阶段门控调度、跨角色裁决、对外唯一接口
- **严真奥**（动物医学内容专家）：Ima知识库检索+证据分级+术语规范
- **苏学法**（教学法架构师）：反向设计三层学习目标+形成性评价+互动节点
- **屠明熙**（课件视觉设计师）：版式选型+视觉层级+医学图像规范
- **郅作基**（PPT制作师）：制作指令包+teaching-ppt-studio协同+导出检查

## 核心特性

- ✅ **六阶段门控**——保留质量门槛的同时允许合并确认（最少2次、最多6次用户确认）
- ✅ **证据驱动**——7个Ima订阅知识库按主题选1-3个，ReAct循环+硬上限防死循环
- ✅ **教学对齐**——学习目标-活动-评价三件套强制（建设性对齐）
- ✅ **多Agent兼容**——WorkBuddy Team型完整支持；Claude Code/Claude Desktop 通过 TeamCreate/SendMessage 单兵调用
- ✅ **跨工具协同**——与本地 `teaching-ppt-studio` skill 无缝衔接（路径A/B分流决策表）

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
    ├── architecture.md                ← 团队结构与六阶段门控详解
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

系统会启动六阶段流水线：任务冻结 → 教学蓝图 → 证据核验 → 页面设计 → 迭代修订 → 制作交付。

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

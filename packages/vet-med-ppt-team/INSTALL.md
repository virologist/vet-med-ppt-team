# 安装指南 · INSTALL

> 针对不同 AI Agent 工具的详细安装步骤。所有路径均为相对于本仓库根。

> **⚠️ 私有仓库前置条件**：本仓库当前为私有。无论使用哪种 Agent，执行以下任意安装命令前，需先在本机完成 GitHub 认证：
> - **终端**：`gh auth login`（推荐）或配置 SSH key / PAT
> - **未认证直接 clone 的后果**：`git clone https://github.com/virologist/vet-med-ppt-team.git` 返回 401/找不到仓库
> - 仓库转公开后，本提示可整体删除

## 目录

- [WorkBuddy](#workbuddy)
- [Claude Code](#claude-code)
- [Claude Desktop](#claude-desktop)
- [通用（手动安装）](#通用手动安装)
- [外部依赖（可选）](#外部依赖可选)
- [验证安装成功](#验证安装成功)
- [故障排查](#故障排查)

---

## WorkBuddy

**适用**：WorkBuddy 桌面应用（推荐，最完整支持 Team 型 expert）

### 方法 A：marketplace 添加（推荐）

在 WorkBuddy 对话框中执行：

```
/plugin marketplace add virologist/vet-med-ppt-team
```

WorkBuddy 会读取仓库根的 `.codebuddy-plugin/marketplace.json`，自动注册 `vet-med-ppt-team` 插件。

### 方法 B：手动复制（离线/已 clone）

```bash
# 1. 克隆仓库到本地
git clone https://github.com/virologist/vet-med-ppt-team.git /tmp/vet-med-ppt-team

# 2. 复制到 WorkBuddy 专家目录
cp -r /tmp/vet-med-ppt-team/packages/vet-med-ppt-team \
      ~/.workbuddy/plugins/marketplaces/my-experts/plugins/

# 3. 启动 WorkBuddy → 专家中心 → 应能看到"动物医学教学PPT智造团"
```

### 方法 C：解压 zip 安装（最快，适合无 git 环境）

```bash
# 1. 下载 release zip（从 GitHub Releases 或直接取仓库内 packages/vet-med-ppt-team/vet-med-ppt-team.zip）
# 2. 解压
unzip vet-med-ppt-team.zip -d ~/.workbuddy/plugins/marketplaces/my-experts/plugins/

# 3. 启动 WorkBuddy 验证
```

---

## Claude Code

**适用**：Claude Code CLI

### 方法 A：插件市场安装（推荐）

在 Claude Code 对话框中依次执行两步：

```
# 第一步：添加本仓库为 marketplace（读取仓库根 .claude-plugin/marketplace.json）
/plugin marketplace add virologist/vet-med-ppt-team

# 第二步：从该 marketplace 安装插件（插件名@marketplace名，两者同名）
/plugin install vet-med-ppt-team@vet-med-ppt-team
```

> 注意：第二步的语法是 `插件名@marketplace名`，两个名字均来自 `marketplace.json` 的 `name` 字段与其中 `plugins[].name`，**不是** GitHub 路径或子目录路径。

### 方法 B：手动克隆（离线场景）

```bash
# 1. 直接克隆到 Claude Code 的 marketplaces 目录
#    （仓库根自带 .claude-plugin/marketplace.json，放在此目录即被识别）
git clone https://github.com/virologist/vet-med-ppt-team.git \
            ~/.claude/plugins/marketplaces/vet-med-ppt-team

# 2. 重启 Claude Code，执行 /plugin 确认 marketplace 与插件已加载

# 3. 测试：新对话 → 输入"帮我把《禽流感》做成2课时教学PPT"
#    → 应触发 vet-med-ppt-team-team-lead 角色
```

### 方法 C：只用单个成员（subagent 方式）

Claude Code 支持将 agent MD 直接作为 subagent 使用：

```bash
# 复制 5 份 agent MD 到 Claude Code 的 agents 目录
mkdir -p ~/.claude/agents
cp ~/.claude/plugins/marketplaces/vet-med-ppt-team/packages/vet-med-ppt-team/agents/*.md \
   ~/.claude/agents/

# 每份 MD 的 frontmatter 已含 name + description，符合 subagent 规范
# 此方式只挂载角色定义，不含 marketplace 级的插件管理
```

> **注意**：Claude Code 是单 Agent 模式。Team型 expert 的多角色调度由 team-lead MD 内的"协作机制"指令模拟——它会自己调度各成员 agent MD 的内容。不会创建真正的 Team 实体，但所有规则、门控、红线都会被遵守。

---

## Claude Desktop

**适用**：Claude Desktop（macOS / Windows）

### 方法 A：插件管理安装

1. 打开 Claude Desktop
2. 进入 **Settings** → **Plugins** → **Add Plugin**
3. 输入仓库地址：`virologist/vet-med-ppt-team`（Claude Desktop 会读取仓库根的 `.claude-plugin/marketplace.json`）
4. 点击 **Install**
5. 重启 Claude Desktop

> 前提：Claude Desktop 需已配置 GitHub 凭据（本仓库为私有）。如无法配置，改用方法 B 手动放置。

### 方法 B：手动放置

```bash
# macOS
git clone https://github.com/virologist/vet-med-ppt-team.git \
            ~/Library/Application\ Support/Claude/plugins/vet-med-ppt-team

# Windows (PowerShell)
git clone https://github.com/virologist/vet-med-ppt-team.git \
            $env:APPDATA\Claude\plugins\vet-med-ppt-team
```

重启 Claude Desktop 即可。

---

## 通用（手动安装）

**适用**：任何支持 SKILL.md 或自定义 plugin 的 Agent

### 核心原则

本专家团是 **Team 型**（多 agent MD 协同），不是单 SKILL.md。安装时需保留目录结构：

```
你的Agent技能目录/
└── vet-med-ppt-team/                ← 必须保持这个目录名
    ├── .codebuddy-plugin/plugin.json
    ├── agents/                       ← 5份MD必须都在
    ├── avatars/                      ← 头像可选（仅影响显示）
    └── settings.json                  ← Team型必需
```

### 步骤

1. **克隆或下载 zip**
   ```bash
   git clone https://github.com/virologist/vet-med-ppt-team.git /tmp/vet-ppt
   ```

2. **找到你的 Agent 技能目录**（常见路径）

   | Agent | 路径 |
   |-------|------|
   | WorkBuddy | `~/.workbuddy/plugins/marketplaces/my-experts/plugins/` |
   | Claude Code | `~/.claude/plugins/` |
   | Claude Desktop | `~/Library/Application Support/Claude/plugins/` (macOS) |
   | Codex | `~/.codex/plugins/` |
   | Cursor | `~/.cursor/plugins/` |

3. **复制子目录**
   ```bash
   cp -r /tmp/vet-ppt/packages/vet-med-ppt-team /your/agent/skills/
   ```

4. **重启 Agent** 让其重新扫描技能目录

---

## 外部依赖（可选）

> **v3.17.0 新增**。本节说明「装了才更好、不装也能跑」的外部件。

### 外部依赖：`teaching-ppt-studio` skill（七维量规上游副本）

| 项 | 说明 |
|---|---|
| **用途** | 七维精准诊断量规的**上游对照源**（用于比对上游更新）。**不是运行期必需** |
| **是否必需** | **否**——v3.17.0 起，七维量规已**内化**进本包：`references/seven-dimension-rubric.md` |
| **缺失时的行为** | **不阻断**本包任何能力；诊断入口照常工作，量规以**包内版本**为准 |
| **安装位置** | `~/.workbuddy/skills/teaching-ppt-studio/`（或 `~/.codebuddy/skills/teaching-ppt-studio/`） |
| **检查命令** | `python3 references/check_external_deps.py`（缺失时明确打印提示；`--strict` 才返回非零码） |
| **登记位置** | `references/dependency-manifest.yaml`（外部依赖的包内唯一数据源） |

**为什么没有把它写进 plugin.json**：WorkBuddy 专家包清单规范（`plugin-json-spec.md`）
的字段全集中**不存在**依赖声明字段（`dependencies` / `requires` / `skillDependencies` 之类），
内置 11 个插件的清单顶层键也均无此类字段——
**平台不认的键不写进清单**，改用「登记 + 可执行检查」把静默失效变成显式可见。

```bash
# 一键检查外部依赖状态（默认不阻断；缺失只影响「与上游比对更新」）
python3 references/check_external_deps.py
```

---

## 验证安装成功

### WorkBuddy

1. 打开 WorkBuddy
2. 进入 **专家中心** → **我的专家**
3. 应看到 **动物医学教学PPT智造团** 卡片（5个成员头像）
4. 新建对话，输入：
   ```
   用 vet-med-ppt-team 团队帮我把《禽流感》做成2课时教学PPT
   ```
5. 应触发全课吉主理人调度 5 个角色的对话流

### Claude Code

```
在 Claude Code 中输入：
> 列出已安装的插件
应包含：vet-med-ppt-team
```

### Claude Desktop

1. Settings → Plugins
2. "Installed" 列表应包含 vet-med-ppt-team
3. 新对话测试：输入教学PPT制作指令

---

## 故障排查

### Q: 私有仓库 clone/marketplace add 返回 401 或 "repository not found"

**A**: GitHub 对私有仓库的未认证访问统一返回 404/401 以避免泄露存在性。解决：
1. 终端运行 `gh auth login`，按提示完成浏览器授权
2. 验证：`gh repo view virologist/vet-med-ppt-team` 应返回仓库信息
3. 重试安装命令

### Q: 安装后看不到专家团

**A**: 检查以下三项：
1. 目录名是否严格为 `vet-med-ppt-team`（kebab-case）
2. `agents/` 下是否有完整的5份 MD
3. Agent 是否已重启（很多 Agent 只在启动时扫描技能目录）

### Q: 点击专家团后报错"工具不可用"

**A**: 这是 normal behavior。Team lead 会按用户输入决定调哪些成员。如果用户输入是"病理剖检"这种模糊指令，主理人可能要求澄清而不是立即 spawn 成员。

### Q: Ima 知识库检索失败

**A**: 检查你的 Agent 是否连接了 ima-mcp。本专家团的严真奥成员依赖 ima-mcp 的 `search_knowledge` 工具。如果 Agent 未配置 ima-mcp，严真奥会自动 fallback 到工作空间记忆复用或教材级表述（不会编造）。

### Q: teaching-ppt-studio skill 调用失败

**A**: 先分清两件事（v3.17.0 起）：
- **七维量规不再依赖外部 skill**——它已内化在本包 `references/seven-dimension-rubric.md`，
  外部副本**缺失不影响诊断入口**，以包内版本为准；外部副本只用于「比对上游更新」。
- **路径 B 的制作链协同**才需要本地安装 `teaching-ppt-studio` skill。
  检查 `~/.workbuddy/skills/teaching-ppt-studio/`（或 `~/.codebuddy/skills/teaching-ppt-studio/`）是否存在。
  若没有，主理人会自动回退到路径 A（只输出制作指令包）。

随时可自查外部依赖状态：

```bash
python3 references/check_external_deps.py
# 缺失时会明确打印：外部 skill teaching-ppt-studio 未安装 → 本包已内化
# references/seven-dimension-rubric.md，以包内版本为准；外部副本仅用于比对上游更新
```

### Q: settings.json 反复丢失

**A**: 已知的 OneDrive/CloudStorage 同步竞态问题。`settings.json` 是空目录占位必备文件，建议在 `.gitignore` 中**不忽略**该文件，并提供自动恢复脚本：

```bash
# 修复命令
echo '{"agent": "vet-med-ppt-team-team-lead"}' > \
     ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/settings.json
```

---

## 下一步

- 阅读 [UPGRADE.md](UPGRADE.md) 了解如何更新本专家团
- 阅读 [docs/architecture.md](docs/architecture.md) 了解团队组成与**五闸（stage 0–4）门控流水线**设计（阶段事实以 `config/harness.yaml#stages` 为唯一源）
- 阅读 [CHANGELOG.md](CHANGELOG.md) 查看版本历史

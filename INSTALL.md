# 安装指南 · INSTALL

> 针对不同 AI Agent 工具的详细安装步骤。所有路径均为相对于本仓库根。

## 目录

- [WorkBuddy](#workbuddy)
- [Claude Code](#claude-code)
- [Claude Desktop](#claude-desktop)
- [通用（手动安装）](#通用手动安装)
- [验证安装成功](#验证安装成功)
- [故障排查](#故障排查)

---

## WorkBuddy

**适用**：WorkBuddy 桌面应用（推荐，最完整支持 Team 型 expert）

### 方法 A：自动注册（推荐）

```bash
# 1. 克隆仓库到本地
git clone https://github.com/virologist/vet-med-ppt-team.git /tmp/vet-med-ppt-team

# 2. 复制到 WorkBuddy 专家目录
cp -r /tmp/vet-med-ppt-team/packages/vet-med-ppt-team \
      ~/.workbuddy/plugins/marketplaces/my-experts/plugins/

# 3. 触发 WorkBuddy 重新扫描 marketplace.json
#    启动 WorkBuddy → 专家中心 → 应能看到"动物医学教学PPT智造团"
```

### 方法 B：解压 zip 安装（最快）

```bash
# 1. 下载 release zip（从 GitHub Releases）
# 2. 解压
unzip vet-med-ppt-team.zip -d ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 3. 启动 WorkBuddy 验证
```

### 方法 C：使用 skillstash（跨工具同步）

```bash
# 安装 skillstash CLI
npm install -g skillstash

# 注册此仓库为 skillstash hub
cd /path/to/vet-med-ppt-team
skillstash init  # 如果未初始化
skillstash link --agent workbuddy
```

---

## Claude Code

**适用**：Claude Code CLI

### 方法 A：插件市场安装（推荐）

在 Claude Code 对话框中直接粘贴：

```
/plugin install virologist/vet-med-ppt-team@packages/vet-med-ppt-team
```

Claude Code 会自动从 GitHub 克隆仓库并安装到插件目录。

### 方法 B：手动克隆

```bash
# 1. 克隆到 Claude Code 技能目录
git clone https://github.com/virologist/vet-med-ppt-team.git \
            ~/.claude/plugins/vet-med-ppt-team

# 2. 在 Claude Code 中测试
#    新对话 → 输入"帮我把《禽流感》做成2课时教学PPT"
#    → 应触发 vet-med-ppt-team-team-lead 角色
```

> **注意**：Claude Code 是单 Agent 模式。Team型 expert 的多角色调度由 team-lead MD 内的"协作机制"指令模拟——它会自己调度各成员 agent MD 的内容。不会创建真正的 Team 实体，但所有规则、门控、红线都会被遵守。

---

## Claude Desktop

**适用**：Claude Desktop（macOS / Windows）

### 方法 A：插件管理安装

1. 打开 Claude Desktop
2. 进入 **Settings** → **Plugins** → **Add Plugin**
3. 输入仓库地址：`virologist/vet-med-ppt-team`
4. 点击 **Install**
5. 重启 Claude Desktop

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

**A**: 路径 B 需要本地安装 teaching-ppt-studio skill。检查 `~/.workbuddy/skills/teaching-ppt-studio/` 或类似路径是否存在。若没有，主理人会自动回退到路径 A（只输出制作指令包）。

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
- 阅读 [docs/architecture.md](docs/architecture.md) 了解六阶段门控流水线设计
- 阅读 [CHANGELOG.md](CHANGELOG.md) 查看版本历史

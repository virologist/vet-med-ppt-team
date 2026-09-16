# 升级与维护指南 · UPGRADE

> 适用于开发者本人（TZUVet）维护本专家团的标准流程。

## 维护流程总览

> ## ⚠️ 禁止事项（2026-09-12 实际事故）
>
> **禁止把本仓库直接 `git clone` 到 `~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/`。**
>
> 仓库根结构（README/packages/docs）≠ 插件包结构（agents/avatars/plugin.json）。直接 clone 覆盖会导致：
> 1. `plugin.json` 被埋进 `packages/vet-med-ppt-team/.codebuddy-plugin/` 深处，WorkBuddy 扫描不到
> 2. `my-experts/marketplace.json` 注册条目被自动清除 → 专家团从列表中消失、不可调用
>
> **正确更新方式**：只把 `packages/vet-med-ppt-team/` 的**内容**同步到插件目录（见下方场景 1/2），保持插件根为扁平结构。

```
发现需求
  ↓
[本地] /Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team/  修改
  ↓
本地验证（pytest + validate_expert.py）
  ↓
git commit
  ↓
git push  → GitHub  virologist/vet-med-ppt-team
  ↓
同步本地 WorkBuddy 专家目录（rsync 包内容，勿覆盖目录结构）
  ↓
打包新 zip 替换 packages/vet-med-ppt-team/vet-med-ppt-team.zip
  ↓
更新 CHANGELOG.md 与 README.md（如有破坏性变更）
```

---

## ⚠️ 每次修改专家包后必做（2026-09-17 新增，第 5 步是血泪）

修改 `agents/*.md` 或 `plugin.json` 后，**WorkBuddy 热重载会吞掉 `settings.json`**（已复现 4 次，同 marketplace 下其他 4 个 Team 型专家因未被修改而不受影响）。跳过第 5 步会导致 validate 报"Team type must have settings.json"、专家不可用。

```bash
cd ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 5. 【必做】恢复 settings.json（幂等，可重复执行）
python3 scripts/ensure_settings.py

# 6. 校验 + 注册
python3 /Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts/validate_expert.py .
python3 /Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts/register_expert.py .
```

> 注：本机 `/usr/bin/git` 会触发 Xcode 许可证拦截（SIGTERM），推送请用 `/opt/homebrew/bin/git`。

---

## 场景 1：日常微调（修改某个 agent 的某段 SOP）

**触发**：用户偏好改变、发现小bug、补充案例

**步骤**：

```bash
# 1. 打开本地仓库（GitHub 镜像同步源）
cd /Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team

# 2. 编辑目标文件
# 例如：修改主理人的阶段3并行超时降级逻辑
vim packages/vet-med-ppt-team/agents/vet-med-ppt-team-team-lead.md

# 3. 同步到 WorkBuddy 实际使用目录
cp packages/vet-med-ppt-team/agents/vet-med-ppt-team-team-lead.md \
   ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/agents/

# 4. 在新会话验证
#    启动新对话 → 调用 vet-med-ppt-team → 测试修改场景

# 5. 提交
git add packages/vet-med-ppt-team/agents/vet-med-ppt-team-team-lead.md
git commit -m "stage3 timeout降级: 增加超阈值告警"

# 6. 推送
git push origin main

# 7. 重新打包 zip 分发版
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/package_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 8. 同步新 zip 到仓库
cp ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/.codebuddy-plugin/vet-med-ppt-team.zip \
   packages/vet-med-ppt-team/
git add packages/vet-med-ppt-team/vet-med-ppt-team.zip
git commit -m "v1.4.1: 重新打包zip"
git push origin main
```

---

## 场景 2：版本升级（v1.x → v1.y）

**触发**：新增功能、修复重要bug、重构

**步骤**：

```bash
# 1. 在仓库中编辑 plugin.json 的 version 字段
vim packages/vet-med-ppt-team/.codebuddy-plugin/plugin.json
# 将 "version": "1.4.0" → "1.5.0"

# 2. 更新 CHANGELOG.md（追加新版本段落）
vim CHANGELOG.md
# 格式见下方"CHANGELOG 格式"

# 3. 同步本地 WorkBuddy 目录
rsync -av packages/vet-med-ppt-team/ \
      ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/ \
      --exclude='*.zip'

# 4. 验证
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/validate_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/register_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 5. 端到端测试
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/package_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 6. 重新打包
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/package_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 7. 同步 zip
cp ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/.codebuddy-plugin/vet-med-ppt-team.zip \
   packages/vet-med-ppt-team/

# 8. 三连提交
git add -A
git commit -m "v1.5.0: <一句话总结>"
git tag v1.5.0
git push origin main --tags
```

---

## 场景 3：添加新成员（扩编）

**触发**：需要新的专家角色（例如"病例数据库架构师"）

**步骤**：

```bash
# 1. 创建新 agent MD（参照 expert-manager 规范）
#    - agents/ < 5份现有 MD 的结构与 SOP 段
#    - 必填 frontmatter: name, description, displayName, profession, maxTurns
#    - body 包含：角色定义、核心能力、工作流程、输出规范、注意事项
vim packages/vet-med-ppt-team/agents/case-db-architect.md

# 2. 更新 plugin.json
#    - agents 数组添加 "./agents/case-db-architect.md"
#    - teamInfo.memberAgents 添加 "case-db-architect"
#    - members 数组添加成员对象（含 avatar、profession）
vim packages/vet-med-ppt-team/.codebuddy-plugin/plugin.json

# 3. 生成新成员头像
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/... # 用 ImageGen
# 输出 512×512 ≤500KB PNG → packages/vet-med-ppt-team/avatars/case-db-architect.png

# 4. 更新主理人 MD：添加成员到"团队成员"表、能力清单、路由表
vim packages/vet-med-ppt-team/agents/vet-med-ppt-team-team-lead.md

# 5. 同步到本地 WorkBuddy 目录
cp packages/vet-med-ppt-team/agents/case-db-architect.md \
   ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/agents/
cp packages/vet-med-ppt-team/avatars/case-db-architect.png \
   ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/avatars/

# 6. 验证（必跑 validate）
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/validate_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 7. 更新 CHANGELOG.md（标注扩编）
# 8. 更新 README.md（团队编制表）
# 9. 提交 + 推送 + 打包

```

---

## 场景 4：变更 avatar 或 settings.json

**avatar 变更**：

```bash
# 1. 准备新图（512×512, ≤500KB, PNG/JPG）
# 2. 替换
cp new-avatar.png packages/vet-med-ppt-team/avatars/team.png
# 3. 同步本地
cp packages/vet-med-ppt-team/avatars/team.png \
   ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/avatars/
# 4. 不需要改 plugin.json（avatar 文件名已固定）
# 5. 提交
git add packages/vet-med-ppt-team/avatars/team.png
git commit -m "chore: 团队头像更新"
git push
```

**settings.json 恢复**：

```bash
# settings.json 仅含 {"agent": "vet-med-ppt-team-team-lead"} 一行
# 若丢失（一键恢复）：
echo '{"agent": "vet-med-ppt-team-team-lead"}' > \
     packages/vet-med-ppt-team/settings.json

# 同步到 WorkBuddy
cp packages/vet-med-ppt-team/settings.json \
   ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/
```

---

## 关键脚本路径速查

| 用途 | 路径 |
|------|------|
| 验证专家包 | `~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/validate_expert.py` |
| 注册到 marketplace | `~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/register_expert.py` |
| 打包成 zip | `~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/package_expert.py` |

> 如果 expert-manager skill 目录不存在，请先安装 WorkBuddy expert-manager skill（WorkBuddy → 技能 → 搜索"expert-manager"）。

---

## CHANGELOG 格式

```markdown
## [v1.x.y] - YYYY-MM-DD

### Added（新增）
- 新功能描述

### Changed（变更）
- 既有功能改动

### Fixed（修复）
- bug 描述 + 根因

### Removed（移除）
- 移除的功能

### Migration（升级指引，若有破坏性变更）
- v1.x.y → v1.x.z 的必要操作
```

---

## 紧急回滚（如果新版本出问题）

```bash
# 1. 回滚 WorkBuddy 实际目录到上一个版本
cd ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team

# 2. 从 git 历史恢复
git -C /Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team \
    log --oneline -10  # 找上一个稳定 tag
git -C /Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team \
    checkout v1.4.0 -- packages/

# 3. 同步回 WorkBuddy
rsync -av packages/vet-med-ppt-team/ \
      ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/

# 4. 验证
python3 ~/.workbuddy/plugins/marketplaces/my-experts/plugins/expert-manager/scripts/validate_expert.py \
        ~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team
```

---

## 长期维护检查清单

每季度（建议）：

- [ ] 检查 ima-mcp 库 ID 是否变更（若有变更，更新严真奥 MD 的路由表）
- [ ] 检查 teaching-ppt-studio skill 版本（若有 v2.x 大版本，更新郅作基 MD 的协同协议）
- [ ] 跑一次完整端到端测试（README 中的 quickPrompts）
- [ ] 确认 marketplace.json 注册有效（无会话警告）
- [ ] 备份 zip 保留至少 3 个最近版本

---

## 反馈与问题

- 仓库地址：https://github.com/virologist/vet-med-ppt-team
- 本地工作目录：`/Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/Claude/vet-med-ppt-team/`
- WorkBuddy 实际生效目录：`~/.workbuddy/plugins/marketplaces/my-experts/plugins/vet-med-ppt-team/`

# 架构设计 · Architecture

> 详细解释 vet-med-ppt-team 的设计原则与运行机制。

## 设计哲学

1. **学生学到什么，而非教师放了什么**——每一页服务于明确的学习动作（建立兴趣/激活先验/理解机制/辨认现象/比较鉴别/执行步骤/作出决策/练习反馈/总结迁移）
2. **课堂 PPT 是协同界面**——不是教材投影，不是论文摘抄，不是讲稿搬运
3. **专业准确性 > 生物安全 > 教学有效性 > 视觉表现力**——质量优先级写死

---

## 团队组成

| Agent ID | 中文名 | 职业 | 核心职责 |
|----------|--------|------|----------|
| `vet-med-ppt-team-team-lead` | 全课吉 | 课件总导演 | 六阶段门控调度、跨角色裁决、对外唯一接口 |
| `dvm-content-expert` | 严真奥 | 动物医学内容专家 | Ima 知识库检索 + 证据分级 + 术语规范 |
| `pedagogy-architect` | 苏学法 | 教学法架构师 | 反向设计三层目标 + 形成性评价 + 互动节点 |
| `visual-slide-designer` | 屠明熙 | 课件视觉设计师 | 版式选型 + 视觉层级 + 医学图像规范 |
| `ppt-producer` | 郅作基 | PPT 制作师 | 制作指令包 + teaching-ppt-studio 协同 |

---

## 六阶段门控流水线

```
[阶段0] 任务冻结与澄清（主理人亲自主导）
   ├─ 读取上下文 + 工具探针（旧课件/汇报型必做）
   ├─ 输出：≤5 个澄清问题（含推荐答案）
   └─ 门控：用户未确认前不进入下一阶段

[阶段1] 教学蓝图（苏学法∥严真奥 并行）
   ├─ 苏学法：三层目标+时间预算+MECE框架+互动节点+形成性评价
   ├─ 严真奥：证据缺口清单（标注每条"必须检索"或"可沿用教材"）
   └─ 门控：用户确认蓝图（+ 决定是否跳阶段2）

[阶段2] 证据核验（严真奥主力，低风险可跳）
   ├─ 记忆复用优先（Read 优于检索）
   ├─ ReAct 核证循环（硬上限：单条3轮、累计15轮）
   ├─ 来源分级 P1-P5 + 边界标注
   └─ 门控：用户确认证据包

[阶段3] 页面级设计（苏学法→屠明熙 串行）
   ├─ 苏学法：学习动作+学生可见内容+讲授提示
   ├─ 屠明熙：版式+视觉焦点+素材规格
   ├─ 输出：合并页表（单文档，不分两份）
   └─ 门控：用户确认页面脚本

[阶段4] 迭代修订（快速通道）
   ├─ 单页级小改动：主理人自查清单
   └─ 跨模块改动：回传对应成员复检（外部验证优先于自查）

[阶段5] 制作交付（郅作基主力）
   ├─ 路径A：输出六件套制作包（工具无关）
   ├─ 路径B：调 teaching-ppt-studio 实际生成 .pptx
   ├─ 主理人终检：含 pending_items 转发
   └─ 交付物 + 任务收尾（写入工作空间记忆）
```

### 门控原则

- **保留门控**：阶段1蓝图与阶段3页面脚本的确认权永远归用户
- **允许合并**：阶段0+1可合并确认（最少2次确认）、阶段4为快速通道
- **可压缩**：用户明说「直接继续」时可进一步压缩
- **不可跳过**：用户未明示时不得跳阶段

---

## 关键约束（写死）

| 约束 | 说明 | 出处 |
|------|------|------|
| Ima 库路由 | 每次任务选 1-3 个库，禁止全库齐搜 | dvm-content-expert.md |
| 跨物种上限 | 跨物种主题最多 3 库 | dvm-content-expert.md |
| ReAct 硬限 | 单条缺口≤3轮循环；累计≤15轮 | dvm-content-expert.md |
| 蓝图确认 | 阶段1用户未确认不得进入阶段2 | vet-med-ppt-team-team-lead.md |
| 页面脚本确认 | 阶段3用户未确认不得进入阶段4 | vet-med-ppt-team-team-lead.md |
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
│                                          - members 数组（含主理人+4成员）
│                                          - teamInfo (leadAgent + memberAgents)
├── agents/                           ← 5 份 agent MD（角色定义）
│   ├── vet-med-ppt-team-team-lead.md ← 必含：六阶段SOP、协作铁律、裁决原则
│   ├── dvm-content-expert.md         ← 必含：Ima 路由表、记忆复用、ReAct 硬限
│   ├── pedagogy-architect.md         ← 必含：反向设计、三层目标、形成性评价三件套
│   ├── visual-slide-designer.md      ← 必含：版式选型、可读性红线、医学图像规范
│   └── ppt-producer.md               ← 必含：路径A/B 决策表、handoff schema 对齐
├── avatars/                          ← 6 张头像（512×512 PNG, ≤500KB）
│   ├── team.png                      ← 团队整体头像
│   ├── <member>.png                  ← 每个成员（含主理人）
├── settings.json                     ← Team 型必需：{"agent": "<lead-name>"}
├── README.md                         ← 子包说明（与根 README 不同）
└── vet-med-ppt-team.zip              ← 一键分发版
```

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

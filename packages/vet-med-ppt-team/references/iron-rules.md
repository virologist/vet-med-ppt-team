# 铁律与工具纪律（v3.4.0/v3.4.2 详情）

> 定位：v3.4.0 五条铁律（反幻觉/反自评/反虚假承诺）与 v3.4.2 工具采用闭环的完整正文。
> 主理人 MD（vet-med-ppt-team-team-lead.md）只留精简索引 + 红线摘要，全文按需 Read 本文件。
> v3.4.2 P1-3 MD 瘦身二轮：team-lead 21KB→目标 ≤14KB；本文件承接大段纪律内容。

---

## A. v3.4.0 五条铁律（反幻觉/反自评/反虚假承诺）

适用对象：全团所有成员。每一项的实操判定可被机器代码背书（v3.4.2 verify-ref / verify-artifact / harness gate）。

### A1 禁幻觉

不得引入虚假/臆测/未经核验的 PMID/DOI/教科书/法规引用；引用必带原始 PMID 或 DOI；不确信的标"未核验"。

**机器背书**：`harness.py verify-ref`（v3.4.2 P0-3）：
- 假号黑名单 `PMID:12345/00000/99999/11111/012345` 命中即拒（exit 1）
- `ok=true` 但缺 `verified_at` 时间戳 → 标 stale_ok（v3.4.2 红线）
- PMID 长度 < 6 位 → 标 suspicious
- DOI 格式不合规 → 标 format_err

### A2 禁虚假完成声明

不得声称已完成实际未完成的任务；产物落地以 `verify-artifact` 落盘校验为准；门禁数字以 `verify_deck` 机器复算为准。

**机器背书**：
- `harness.py verify-artifact --path X --expect-bytes N`：体积偏差 > 20% 即拒
- `harness.py gate --deck X --hours N --level P0|all`：P0 红灯 → exit 1 阻断（不是 4）；exit 4 走缺陷回流
- 反例：CHANGELOG v3.1.0 声称"harness.py sweep 已实现+16/16 测试通过"，git 全历史实证 0 实现——v3.4.2 P0-1 落地，CHANGELOG 同步补勘误

### A3 一图对应一个 ipynb / 一个源文件

本团暂无可视化模块，但若未来新增图表/示意图，必须先修改源文件（.ipynb/.py/.md），再基于修改后代码重新生成图片；禁止"代码未动但图已换"。

### A4 路径显式

每个产物声明绝对输入路径与输出路径；输出图保存为 PDF（与团队既有约定一致）；不得用相对路径或"已发给用户"等模糊表述。

### A5 文件治理优先复用

清理历史冗余无效文件优先在旧文件基础上修改更新；非必要不新建；同步更新相关 CLAUDE.md 的文件夹索引，避免文件膨胀与硬盘占用。

**机器背书**（v3.4.2 ensure_settings 第 12 项候选）：
- `check_bypass_versions()`：扫 `_v[0-9]|副本|优化版|\([0-9]\)` 命名命中即挂账
- `check_doc_implementation_drift()`（候选）：CHANGELOG 声称子命令 vs argparse 注册表交叉核验

---

## B. v3.4.2 工具采用闭环（强制纪律）

> 根因（2026-10-15 五维诊断）：v3.4.0/v3.4.1 建的新工具（stage/spawn/doctor/verify-ref/sweep）在真实工作区采用率 0；trace 17 事件中 6 类从未产生。

### B1 每闸动作序列（逐步必跑，trace 留痕）

1. **闸0 开工**：`harness.py doctor`（看可发现性表+版本）→ `preflight --team vet-med-ppt-team`（成员静默降级预检）→ `state init`（持久状态机）→ `stage --action enter --stage 0`
2. **每闸切换**：`stage --action exit --stage N --note "<闸结论>"`（前闸关闭）→ `state set --stage N+1`（持久）→ `stage --action enter --stage N+1`（新闸开启）
3. **每次 spawn 成员**：`spawn --agent <成员> --task-id <id> --stage N --input-bytes N --output-bytes N`（写 trace agent_spawn）
4. **成员回传时**：主理人 `trace log --event member_return --actor <成员> --detail '<阶段/产物/警告/...>'`（P1-2：回传可审计；之前 0 事件）
5. **成员不可用降级**：`trace log --event degrade --actor <成员> --detail '<原因+退化模式>'`（P1-2：降级不被静默；遵守 harness.yaml#fallback.require_disclosure）
6. **闸4 终检前**：`verify-ref --path .workbuddy/cases/cases_library.json`（确保引文真伪已预检）→ `harness.py gate --deck <.pptx> --hours N --level all`（SSOT 门禁+trace lint+自动 snap）
7. **收尾必贴**：`trace report` 的 `stage_seconds`（每闸耗时）+ `by_event`/`by_actor` 计数 + `tokens_by_actor` / `budget_usage`（P1-4 成本可见性）→ **复制进交付物**作为可审计附件

### B2 反采用缺口（已诊断识别）

v3.4.2 起的回归测试 (test_harness.py) 增"工具使用率"指标：
- `events_total` 递增
- `expected_actors` 覆盖率（missing_actors 数应逐步→0）
- `tokens_by_actor` 分布（成本可见性）

### B3 工具清单（截至 v3.4.2）

| 工具 | 何时用 | 不变体 |
|---|---|---|
| `doctor` | 冷启动 / 任何新会话首查 | 可发现性表永远返回 14 命令 |
| `preflight` | 闸0 开工 | 抓"成员静默降级为 general-purpose" |
| `route` | 任务复杂度判定 | L0-L3 → spawn 计划 |
| `state` | 任务状态机持久 | init/get/set/validate，白名单外键拒 |
| `budget` | 任务级预算计数 | spawn/react/rework 8/15/2 |
| `trace log/report` | 留痕与汇总 | report 含 8 个 section（见 B1-7） |
| `spawn` | 每次调成员 | token 估算 + trace 留痕 |
| `stage` | 每闸切换 | enter/exit + 孤儿 exit 防护 |
| `gate` | 课件写回前 | lint+snap+gate 一体，exit 4≠exit 1 |
| `verify-artifact` | 反自评失真 | 文件存在+体积合理+expect_bytes±20% |
| `verify-envelope` | 成员回传 | 六字段齐备 + status 合法 |
| `verify-ref` | **v3.4.2 P0-3 新增** | cases_library 文献预检（假 PMID 黑名单+时间戳+格式） |
| `sweep` | **v3.4.2 P0-1 新增** | v3.1.0 失落的闸外收编能力终于落地 |
| `template-audit` | 换模板前 | 未登记指纹不许换 |

---

## C. 关联：adjudication-rules.md / sop-stages.md

- **裁决与终检**（六项自检/四门清单/缺陷回流/反自评失真红线）→ `adjudication-rules.md`
- **五闸 SOP 细节**（闸1-闸4.5 完整流程）→ `sop-stages.md`
- **harness 工程细节**（开工三步/降级协议/上下文隔离/门禁退出码）→ `harness-engine.md`

本文件只承担"五条铁律 + 工具纪律"的承接；裁决与 SOP 仍在原位。

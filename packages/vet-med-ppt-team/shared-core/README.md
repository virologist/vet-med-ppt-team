# shared-core — 联邦共享方法库（v3.4.1 R9 建立）

> 定位：跨专家包的**确定性公共实现**单一真源。本目录不是独立插件，不随任何单一包分发；
> 安装态唯一真源位于 `.../plugins/marketplaces/my-experts/plugins/shared-core/`，
> vet-med-ppt-team 的 git 仓库随包携带一份副本（该仓库是联邦导出锚）。

## 为什么建（诊断报告 Q6 裁决：分批下沉）

2026-10-14 实测：`assemble_spawn_prompt.py` 在 6 个包中各存一份，其中 4 包 md5 完全一致
（`4b556514035027738410b1b3b737d14c`，369 行）——纯拷贝漂移风险：改一处漏三处，
且各包 git 仓库各自演化，公共 bug 修复无法同步到位。Q6 裁决"分批"：先下沉已证同构的
公共件，包私有增量留在包内。

## 当前内容

| 文件 | 状态 | 引用方 |
|---|---|---|
| `assemble_spawn_prompt.py` | 公共版 369 行 + shared-core 归属声明（378 行） | 4 包 shim 转调 + viral-evo-lab 定制版对齐 |

### 引用方清单（2026-10-14）

- **shim 转调**（scripts/assemble_spawn_prompt.py = 45 行兼容入口）：
  `vet-med-ppt-team` / `research-orchestration-team` / `smart-textbook-team` / `triz-invention-team`
- **定制版独立维护**（公共版 + V1 数字核验增量，头部有来源声明）：
  `viral-evo-lab`

## 维护纪律（改前必读）

1. **改本目录 = 同时影响 4 包行为**。改前先跑各包 `--list-members` 基线对比
   （md5 不一致即漂移，先查因再发布）。
2. 公共逻辑必须所有引用包同受益；**包私有需求走各包增量，不回染本文件**
   （viral-evo-lab 的 V1 增量是正面样板）。
3. 新增下沉候选（评估顺序）：`snapshot.py`（vet-med 有，K=3+LRU 治理已成熟）/
   `ooxml_lint.py`（vet-med 有，6 组检查码）/ `ensure_settings.py` 的治理自检段
   （各包 ensure_settings 高度同构）。候选须满足：≥2 包同构 + 无包私有耦合。
4. shim 的 core 定位用**向上查找**（最多 4 层），不写死层数——安装态路径随
   marketplace 嵌套深度变化。

## 验证基线（2026-10-14 下沉时快照）

| 包 | `--list-members` md5 |
|---|---|
| vet-med-ppt-team | `8b5f17b43d5674eb1af60df625f14c20` |
| research-orchestration-team | `6b362e8d5d924f8d6970bdc82855be1a` |
| smart-textbook-team | `22468161f42c53dcbeaf970f5f12106f` |
| triz-invention-team | `77118fcd8858dabf1795f5bb699d56d5` |
| viral-evo-lab（定制版，不适用基线对比） | `dddb79e9bbcb54fc7d0f134066faa495` |

shim 与 core 直跑等价性已实测（`--member dvm-content-expert` 全文 md5 一致：
`7867ed2551cc8c11fd80047abdcd5019`）。

## 已知边界

- **git 仓库结构下 shim 不可用**（core 不随各包仓库分发）：shim 会以 exit 3 +
  明确指引报错。安装态（平台实际调用路径）不受影响。vet-med 仓库因携带 core 副本，
  其 shim 在仓库结构下同样可用。
- plugins 层（联邦层）无 git 仓库：shared-core 的版本历史依赖 vet-med 仓库副本 +
  CHANGELOG 人工记录。新建联邦 git 仓库列为后续治理项（P3，未承诺）。

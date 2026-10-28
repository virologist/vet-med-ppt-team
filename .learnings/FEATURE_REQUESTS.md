# Feature Requests

Capabilities requested by the user.

---

## 📌 `Status` 字段语义（v3.25.0 补定义 · 与 `LEARNINGS.md` 共用同一套）

> ⚠ **此前无定义** —— 与 `LEARNINGS.md` 同源问题：状态不区分"能力已做但未通用化"
> 与"能力根本没做"，导致下一轮盘点重复拾取。
> ⚠ **v3.25.0 初版两个文件的词表不一致**（本文件缺 `manual-only`、`LEARNINGS.md` 缺 `partial`/`resolved`），
> 且 `FEAT-20261022-001` **条目内部自相矛盾**（头部 `pending` vs Resolution `partial`）——
> 均已修正为下表这一套。

| 取值 | 含义 | 判据 |
|---|---|---|
| `pending` | **尚未实现**，有具体待办 | 能指出"还差哪一步没做" |
| `partial` | **部分实现** | 须在 Resolution 里写明"已做哪部分、**未做哪部分**" |
| `applied` | **已落地并生效** | 能在代码里指出落地位置 |
| `manual-only` | **本质是人工纪律**，工具化不可行或不划算 | 须说明为何不值得工具化 |
| `resolved` | **已闭合**（含"经实测否决、如实登记"这类闭合式结论） | 结论明确，无需再动 |
| `superseded` | 已被后续做法取代 | 须指向取代它的那条 |

> **纪律**：只有 `pending` / `partial` 才是待办；其余**不再进入下一轮遗留盘点**（它们是常驻纪律或已闭合结论）。
> `partial` 必须写清剩余部分的**具体形态**，否则下轮无法判断该不该做。
> **头部 `Status` 与 Resolution 内的 `Status` 必须一致**（v3.25.0 修正过一处自相矛盾）。

---

## [FEAT-20261022-001] 静态数据流分析以发现「提到但没用」的配置键

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: medium
**Status**: resolved

### Requested Capability
能区分「代码里提到某个配置键」与「代码真的读了这个值」的静态检查能力。

### User Context
第 18 项死配置体检做完后（已降级为 INFO），反例实测暴露其固有局限：
把 `verify_deck.py` 的 `cfg.get("three_source_check")` 改成 `{}`（读取行为已破坏），
第 18 项统计**完全不变**——因为该键名在其它脚本、注释、docstring 中仍出现，
纯文本包含匹配判定为"有读取者"。

即：本项只能发现"完全无人提及"的键，发现不了"提到但没用"的键。
后者才是更危险的一类（看起来有护栏，实际不生效）。

### Complexity Estimate
medium

### Suggested Implementation
本轮已用"专项断言脚本"作为务实替代（`verify_three_source_config.py`：
逐键断言"运行时值 == 配置值" + 静态扫字面量残留）。
若要通用化，可考虑：
- 用 AST 解析出 `cfg.get("<key>")` / `cfg["<key>"]` 形式的真实读取点，
  排除注释与 docstring（比文本包含精确，但只覆盖显式取值的写法）
- 或对每个"关键阈值键"配一份专项断言脚本，纳入体检

### Metadata
- Frequency: first_time
- Related Features: check_dead_config_keys（第 18 项）

### Resolution（v3.15.0 部分落实）
- **Static 部分已做**：新增 `_collect_ast_reads()`，第 18 项判据由纯文本搜索改为
  AST 真实读取点（`.get("k")` / `["k"]` / 字典字面量键），排除注释与 docstring。
  实测效果：yaml 150 个叶子键中，原文本判据认为"有读取者"但 AST 无读取点的有 **109 个（73%）**；
  修正后人读型登记 34→84、提示 139→89。
- **但反例验证证明静态判据有原理性天花板**：删掉 `cfg.get("three_source_check")` 后，
  `three_source_check` 正确消失，然而 `sample_rate` / `pass_threshold` **仍被判为活跃**——
  因为它们同时存在于 fallback 字典与对 `THREE_SOURCE` 的取值中，不依赖外层 cfg。
  即静态判据能发现"读取链被删"，**发现不了"读了 fallback 而没读配置"**。
- **结论（已写入代码注释）**：这一类必须靠**运行时断言**（配置值 == 运行时值）覆盖，
  即 `verify_three_source_config.py` 的做法。静态判据原理上做不到，不应继续投入。
- **Status**: resolved（v3.25.0 ADR-5 结案：路径 A（逐键运行时断言）正式结案为 not-doing，由路径 D 段级增量守卫覆盖）
- **v3.25.0 核实（剩余部分的具体形态）**：通用化的**剩余部分**是
  「对块级消费区（v3.24.0 实测 1608 键中的 1489 项）里的键，
  建立『运行时值 == 配置值』的逐键断言」。
  现状：包内**唯一**的运行时断言机制是第 21 项 `check_three_source_single_source`
  （`scripts/ensure_settings.py:1746`），**只覆盖 2 个键**（`sample_rate` / `pass_threshold`）。
  工作区的 `verify_three_source_config.py`（在
  `/Users/biodog/Library/CloudStorage/OneDrive-Personal/GPT/WorkBuddy/2026-09-10-08-59-15/`）
  **不在包内**且与第 21 项功能重复 ⇒ 它是第 21 项的**前身**，非互补件。
  ⇒ 剩余部分的**具体形态**已明确：**一套可泛化的运行时断言机制**，
    覆盖面从 2 键扩到块级消费区，且派生值/换算系数/人读型键须能显式排除
    （否则假阳性会淹没真问题，违反本包铁律）。
  **本轮（v3.25.0）正在处理此项** —— 见 01-research 与 02-design 产出。
- **v3.25.0 结案（ADR-5 · 路径 A 正式结案为 not-doing）**：
  「通用化的剩余部分**不是**逐键断言」——本轮实测给出三条否决理由：
  1. **量级不匹配**：1669 键里 ≥261 键（57 人读型登记 + 204 键名从未出现）必须逐条人工登记，
     而 LRN-20261022-001 已记录「往白名单里塞以让检查变绿」的**同型退化**；
  2. **断言表达式无自动来源**：静态判据给不出「运行时的值是什么表达式」，
     生成 1669 条断言须再造一个解析器，且必然在派生值上假阳性
     （实测 `asset-fields.yaml#emu_per_px` 运行时 = `round(EMU/9525)` ≠ 9525；
     `visual-rules.yaml#severity.P0` 运行时是 list、yaml 是首元素）；
  3. **与本包铁律冲突**：「假阳性必须为零」在 1669 键规模不可达 ⇒ 只能是提示项
     ⇒ 而提示项噪声高会被绕过（历史已发生三轮）。
  ⇒ **替代覆盖**：路径 D（段级增量守卫 R3/R5 + 段清单输出）为主，
    路径 B（运行时追踪）**定位为观测工具、不是门禁**，本轮**不实现**。
  ⇒ **Status**: resolved（路径 A 结案；由路径 D 覆盖）

---

## [FEAT-20261023-002] config/harness.yaml 变更自动同步 docs/architecture.md（含未覆盖项）

**Logged**: 2026-10-23（v3.16.0 批次 · W5）
**Priority**: medium
**Status**: resolved

### Requested Capability
`config/harness.yaml`（阶段/成员/门禁/工具白名单的唯一源）一旦变更，
`docs/architecture.md` 与人读视图能**被机器强制同步**，而不是靠人记得改。

### User Context
真实缺陷（非假设）：yaml 自 v3.0.0 起是 5 闸（stage 0–4）、自 v3.0.0 起成员表含 `verifier`，
而 `docs/architecture.md` 直到 v3.16.0 仍在描述**已废弃的六阶段流水线**，且成员表**漏 verifier**。
两者之间**没有任何守卫**，属"文档漂移无人察觉"。同类漂移在其他 MD 也有
（如 team-lead MD 标题写"四道闸"而表格列 5 行）。

### Complexity Estimate
low（已做部分）/ medium（未做部分）

### Suggested Implementation
**已落地（v3.16.0，low 成本）**：`scripts/test_arch_drift.py` —— architecture.md 内嵌
sentinel 包裹的「阶段镜像块」，与 yaml#stages 逐项比对；再比对成员表与 `agents/` 目录；
并检测"六阶段"旧口径复活。随 `pytest scripts/` 与 `ensure_settings` 第 7 项自动执行。

**未做（本次刻意不做，避免负债娩生的半成品）**：
1. **工具白名单无机器比对面**——`members[*].tools_whitelist` 目前**没有**在 MD/文档复述
   （这是刻意的防分化设计），因此无法像阶段镜像那样做文本比对；
   只能做"每个成员 MD 都指向 yaml"的存在性断言（已含 T7），值本身仍靠人工核对。
2. **门禁退出码 `gate_exit_codes` / `delta_gate` 未纳入比对**——它们散在多个 MD 的散文中，
   做文本比对必然假阳性；若要覆盖，应先在 MD 内也建立 sentinel 镜像块，再扩断言。
3. **yaml schema 变更（增/删键）的自动发现**——现状靠"改的人记得同步"，无 schema 契约测试。

**v3.25.0 逐项复核结论（研究简报：`01-research/研究简报-漂移守卫与跨学科样本.md`）**：

| # | 项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 工具白名单 | **不做**（改标 `manual-only`） | **无闭合工具全集** ⇒ 「MD 提及工具 ⊆ 白名单」关系**不可判定**；实测当前即有 7 类越界 token（`SendMessage` 在 5 份成员 MD 全命中、`markitdown`/`pdftotext`、Ima 库 API 方法名、`Glob`×1）。且 `tools_whitelist` **无代码强制力**（AST 读取点 0 处）⇒ 给它配机器断言产出的是**提示噪音**，不是护栏。可机器化的部分（存在性 + 指向）已由 `test_arch_drift.py::T7` 覆盖。 |
| 2a | `delta_gate` | **不做** | 已有 4 个文件级测试 + 反向反例覆盖；MD 复述全在历史验证报告里，按定义必假阳性。 |
| 2b | `gate_exit_codes` | **做**（v3.25.0 实施） | **零测试覆盖**（`rg gate_exit_codes scripts/test_*.py` ⇒ 无输出）**且已发生真实漂移**：实测删 `gate_exit_codes[4]` ⇒ 体检 rc=0 + 全量 pytest 400 passed 零失败，运行时退化为"未知退出码"。补「键集合相等」断言 + MD 侧 sentinel 镜像块。 |
| 3 | yaml schema 变更 | **部分做**（v3.25.0 实施） | 实测：**删键零检测**（rc=0 + 400 passed）；**新增顶层段**被检出（rc=1，判"死配置"）；**已登记段内加叶子键**漏检（`delta_gate` 被段级消费 ⇒ 天然豁免）。本期只补 `gate_exit_codes` 键集合断言；段内加叶子键**不做**（需叶子级白名单 = 又一份声明源）。 |

### Metadata
- Frequency: first_time
- Related Features: 单一数据源纪律（harness.yaml 为编排事实唯一源）、ensure_settings 第 7 项

### Resolution（v3.16.0）
- 已做：阶段镜像块守卫 T1–T7（见 `scripts/test_arch_drift.py` 与 `docs/architecture.md#防漂移守卫`）。
- 未做：上列 1/2/3 项；如需继续，建议按"先在 MD 建 sentinel 镜像块、再扩断言"的顺序推进，
  **不要**直接对散文做正则匹配（FEAT-20261022-001 已证明纯文本判据假阳性不可控）。
- **Status**: partial

### Resolution（v3.25.0：逐项复核 + 部分实施）
- **第 1 项（工具白名单）→ `manual-only`**：不做机器断言（理由见上表：关系不可判定 + 无代码强制力）。
  「每个成员 MD 都指向 yaml」的存在性断言已由 `test_arch_drift.py::T7` 覆盖 ⇒ 该项**实质闭合**。
- **第 2 项 → 拆分**：`delta_gate` 不做（已有覆盖）；`gate_exit_codes` **v3.25.0 实施**
  （补 MD 侧 sentinel 镜像块 + 键集合断言，堵「删键零检测」缺口）。
  ⚠ 实测的**决定性障碍**：包内**至少 8 个互不相同的"退出码"命名空间**
  （gate / loop review / extract_assets / snapshot / case_library / fetch_oa_image /
  assemble_domain / loop-master），同一组数字含义各不相同
  ⇒ **任何跨 MD 的散文级退出码文本比对必然假阳性** ⇒ 只能用 sentinel 镜像块。
- **第 3 项 → 部分做**：`gate_exit_codes` 键集合断言（补删键缺口）；
  已登记段内加叶子键**不做**（天然豁免于段级消费；补它需叶子级白名单 = 又一份声明源）。
- **额外发现（已发生的漂移，非待办）**：`docs/architecture.md`（**受守卫文档**）内部已分化 ——
  `STAGE_MIRROR` 块已更新为新口径（"闸2 设计（证据先行→蓝图·串行）"、parallel=no），
  但同一文件的「人读视图」表仍是旧口径（"闸2 设计（蓝图∥证据）"、"并行"）。
  守卫只解析 sentinel 块与两张显式表，**不解析「人读视图」表** ⇒ 漂移未被拦。
  同型旧口径另见 `README.md:22`、`TEAMS_TOPOLOGY.md:52`（stage1 旧名）与
  `TEAMS_TOPOLOGY.md:43`（"退出码 0-5"，yaml 实为 0–4）。
  ⇒ v3.25.0 处置：先对齐到 yaml 真值，**再**把「人读视图」表纳入断言（顺序不可反）。
- **v3.25.0 实施完成（批 3 落地）**：
  - **2b `gate_exit_codes` 已做**：`references/harness-engine.md` 新增 `GATE_EXIT_MIRROR` 哨兵块
    （每行承载**完整语义文本**，与 yaml **逐字一致**）；
    `test_arch_drift.py::TestGateExitMirror` 落地 G1（块可解析）/ G2（**码集合双向相等**）/
    G3（语义非空）/ G4（语义**逐字**相等）/ G5（代码 fallback 码集 == yaml 码集，**默认关闭**）。
  - **人读视图表已纳入断言**：`TestHumanReadStageTable` 只比 **3 列**（闸号 / 是否并行 / 门禁）；
    ⚠「名称」列**不比**（yaml 带「（v3.3.0）」而人读表压缩掉了，逐字比必假阳性）。
  - **同型旧口径已一并修正**：`README.md`（2 处）/ `TEAMS_TOPOLOGY.md`（stage 1 旧名 + 「退出码 0-5」→「0-4」）/
    `team-lead.md:79`（唯一源指针改为 `config/harness.yaml#gate_exit_codes`）/ `architecture.md` 并行判据小节。
  - **ADR-7 裁决落地**：代码 `_FALLBACK` 的**第 5 码已删**（yaml 无产出者）⇒ fallback 与 yaml 对齐为 0–4
    ⇒ G5 断言**保持默认关闭**（裁决已落、守卫未启，待主理人确认后同批开启）。
  - **反例 12 条全部固化**（能红 10 条 + 防误伤 2 条）。
- **Status**: resolved（第 1 项 `manual-only` 实质闭合；第 2b 项已实施并带反例；
  第 3 项中「段内加叶子键」经 ADR-5 结案为 not-doing，由段级增量守卫 R3/R5 覆盖）

---

---

## [缺口] V3 配色符合模板 / C5 关键数据注明来源 —— 标了 `[机]` 但无实现

### Problem / Use Case
`references/course-profile-defaults.md` §4 验收矩阵长期把 V3（取色比对模板 `clrScheme`）
与 C5（关键数字逐条带来源与年份）标为 `[机]`，但 `verify_deck.py` 中**没有任何对应实现**——
成员看到 `[机]` 会默认"这项不用我人工查"，实际上无人兜底。
这是本轮九维度诊断「声明层与执行层两张皮」的具体实例之一（同类问题见 C3/V1/V5 已在 v3.16.0 修掉）。

### Frequency
first_time（2026-10-23 诊断发现）

### Complexity Estimate
medium

### Suggested Implementation
- **V3**：先把模板 `clrScheme`（见 `references/default-template-profile.md`）抽成机器可读色表
  （如 `config/template-clrscheme.yaml`），再判"新增元素的取色是否落在已声明色令牌内"。
  须与 `visual-rules.yaml#theme.max_new_colors_per_slide=0` 的语义对齐，别做成第二套判据。
- **C5**：不要用正则扫页面上的全角/半角数字——"25日龄""3天""2023年"等非来源数字会大量误报，
  假阳性会让这一项很快被绕过。建议改从**内容侧契约**入手：要求关键数字在页面或备注携带
  `来源：…（年份）` 伴生字段，机器只验"数字是否紧邻来源标记"，"来源是否为真"仍留给人。

### Metadata
- Frequency: first_time
- Related Features: course-profile-defaults.md §4.1 C5 / §4.2 V3（§4.5 已如实登记为"无机器实现"）

### Resolution
- **Status**: partial（v3.16.0 摘假承诺 → **v3.24.0 C5 已落地，V3 实测否决**）
- v3.16.0 已在 `references/course-profile-defaults.md#4.5` 新增「`[机]` 标记的真实执行者」表，
  把 V3/C5 显式标为"暂无机器实现"，先把假承诺摘掉，实现待后续排期。

#### v3.24.0 处置（两项分别结论）

**C5 —— 已落地**（建议级，默认关闭）：
- 判据落在 `scripts/verify_deck.py` 的 `_rubric_key_data_source()`，
  配置键 `visual-rules.yaml#checks.key_data_source`。
- 口径按上方 Suggested Implementation 的建议落地：「机器只验数字是否紧邻来源标记，
  来源是否为真仍留给人」——三层收敛：**指标语境 → 量值 → 来源邻近**。
- ⚠ **假阳性实测取证（4 份真实动医课件）**：
  - 全页 1071 个数字 → 仅 **7 个段落**命中指标语境（收敛比约 1/150）⇒ 「25日龄」「3天」
    这类非来源数字**不会**被扫进来（正是 Suggested Implementation 的顾虑，已实证规避）。
  - 来源标记**不用裸 `\d{4}`**：实测「禽流感鉴别诊疗要点.pptx」宽判命中 2/14、紧判 0/14
    ⇒ 裸 4 位数字会把段落里的**指标数字本身**误当年份。年份**必须**带"年"字。
  - **量值须含 `%` 或小数**：株型编号（H5N1 / H7N9）纯整数不算量值
    （它们恰恰**不需要**来源，计入会制造假阳性）。
- 护栏：`scripts/test_verify_deck.py::TestKeyDataSourceC5`（9 例），
  含正例触发 / 非指标数字不判 / 株型编号不判 / 同段来源抑制 / 页级回退抑制 /
  裸 4 位数字不算年份 / 每页只一条 / 展示不混株型编号。
- **状态**：机器侧完成；「来源是否为真」**永远**由人核（语义判断，机器不可判定）⇒ 永不转正为门禁。

**V3 —— 实测否决，不实现**：
- 原设想「取色均落在模板 `clrScheme` 12 色内」经实测**不可行**：
  4 份真实动医课件的 slide 内 `srgbClr` 取色，落在**自身** clrScheme 外的比例达 **51%–100%**
  （`高致病性禽流感防控.pptx` 85.7%、`7. 禽流感.pptx` 51.0%、`禽流感鉴别诊疗要点.pptx` 100%）。
- 且这些课件的 clrScheme 与默认模板**完全不同**（橙系 `#F87A00` vs 蓝灰系 `#4472C4`）
  ⇒ "落在模板色内"这个参照系本身不成立。
- ⇒ 按原设想实现会产生**海量假阳性**（违反本包铁律「假阳性必须为零」）。
  **保持缺口登记，如实说明否决理由**——不做一个明知会刷屏的判据。
- 可用的替代：`visual-rules.yaml#theme.max_new_colors_per_slide`（人读型登记，
  消费方 = 屠明熙抽取登记 + 主理人复核），已在 v3.19.0 明确登记为人读型，非死配置。
- **若将来重启 V3**，应改判据方向：**不是**"取色是否在调色板内"，
  而是"**新增**元素相对**模板基线**是否引入了新色"——
  即以模板自身用色为基线做**差集**（`max_new_colors_per_slide=0` 的本意），
  而非要求全量取色落在 clrScheme 内。此方向需另立独立取证。

---

## FEAT-20261023-003 · v3.16.0 独立测试的三条遗留建议（不阻塞发版）

> 来源：`agent-harness-tester` 对 v3.16.0 的 20 项对抗性验证（20 PASS / 0 阻断）。
> 均为**建议**级，不影响本次发版；登记在此以免遗忘。

### FEAT-003a · 双份配置的漂移哨兵失败时应直打行号
`scripts/extract_assets.py` 同时存在 `references/asset-fields.yaml` 与代码内 `_BUILTIN_ASSET_FIELD_CONFIG`
两份值。`scripts/test_extract_assets.py::T14` 三方一致哨兵能拦住漂移，
但失败信息只给键名不给行号，排查时需人工定位。
**诉求**：哨兵失败时输出「yaml 第 N 行 vs 代码第 M 行」的对照位置。

### FEAT-003b · 1.5 课时说明与 single-ppt 缺档提示交叉引用
`references/course-profile-defaults.md` 讲 1.5 课时处置、`config/visual-rules.yaml#hours_page_range_single_ppt`
注释讲缺档行为，两处说的是同一件事但互不指向。将来任一处改动易造成表述分裂。
**诉求**：两处互相加显式引用（并入 v3.17.0 的文档同步批次即可）。

### FEAT-003c · 3 处 skip 依赖包外样本课件，本机从未真正跑过
`python3 -m pytest scripts/ tests/ -q` 的 3 个 skip 均因缺少包外课件样本
（如 `M4A1_禽流感/2.1高致病性禽流感防控.pptx`），非因测试弱化。
但这意味着这些用例**在本机从未执行过**，其正确性无本地证据。
**诉求**：登记样本课件的获取方式（来源仓库/生成脚本）或提供最小合成 fixture，
让这 3 条从 skip 转为真跑；在此之前不得把它们计入"覆盖已验证"。

### Metadata
- Frequency: first_time
- Related Features: scripts/extract_assets.py / references/course-profile-defaults.md / 测试用例集
- Status: resolved（v3.24.0 三项全部处置）

---

## FEAT-20261023-003 的 v3.24.0 处置（三项逐条）

### FEAT-003a · 双份配置的漂移哨兵失败时应直打行号 —— ✅ 已落地
- 新增 `scripts/extract_assets.py::describe_asset_field_drift()`：逐键对比
  `references/asset-fields.yaml` 与 `_BUILTIN_ASSET_FIELD_CONFIG`，
  每条差异给出 **`yaml 第 N 行` vs `代码 第 M 行`**。
- `scripts/test_extract_assets.py::T14` 改为消费该函数 ⇒ 失败信息可直接定位。
- 实测反例（注入 `emu_per_px: 9525→9526`）：
  `· asset_fields.emu_per_px [value_mismatch] yaml 第 25 行（值=9526） vs 代码 第 109 行（值=9525）`
  ——行号经人工核对**精确命中**目标键。
- 附注：实现中顺带修掉一个真实缺陷——年份/字面标记混用导致「2024年」不被识别
  （C5 判据开发期发现，见 CHANGELOG v3.24.0）。

### FEAT-003b · 1.5 课时说明与 single-ppt 缺档提示交叉引用 —— ✅ 已落地
- 双向互指：`references/course-profile-defaults.md#2` ⇄ `config/visual-rules.yaml#hours_page_range_single_ppt`，
  两处各加一段「同源声明」并互点对方路径。
- 防单边删除的护栏：`scripts/test_arch_drift.py::TestHoursCaliberCrossRef`（2 例）。
  判据只认**明确锚点**（路径 + `FEAT-003b` 标记串），**不判散文措辞**
  （遵 FEAT-20261022-001 的教训：纯文本判据假阳性不可控）。
- 反例已验证：单边删除 yaml 侧互指 ⇒ `test_T11b` 判红。

### FEAT-003c · 3 处 skip 依赖包外样本课件 —— ✅ 已落地（skip 全部消除）
- **根因取证**（v3.24.0）：
  - `test_ooxml_lint.py::T1` 的路径 `…/.harness-runs/M4-M7_重诊断/sample_extract/` **已不存在**；
  - `test_extract_assets.py::T6` 的 4 条精确路径中，**第一条文件名已变**
    （`2.1高致病性禽流感防控.pptx` → 实际为 `高致病性禽流感防控.pptx`）；
  - `test_ooxml_lint.py::T11` 的 `/tmp/cross_domain/` **不持久** ⇒ 从未真跑。
  - ⇒ 失效的是**路径**，不是断言：实测 4 份真实动医课件 `ooxml_lint` 全部 **rc=0**（0 ERROR），
    满足 T1 断言。
- **处置**：新增 `scripts/sample_fixtures.py` —— 样本定位**下沉**为可解析层：
  多候选目录自动发现（环境变量 → 挂账抽取目录 → 源课件目录）+ 环境变量覆盖
  （`VETMED_SAMPLE_DIR` / `VETMED_CROSS_DOMAIN_DIR`）+ **确定性合成 fixture 兜底**。
- **降级链**：真实样本优先；不可得 ⇒ 合成 fixture ⇒ **断言始终真跑**，不再 skip。
  降级类型（`real` / `synthetic`）**显式打印**，禁"悄悄用弱样本假装测过真样本"。
- **两端均已验证**：
  - 真实分支：`[T1] 样本来源：real — 源课件目录(M4A1_禽流感)(4份)`；
  - 合成分支（`VETMED_FORCE_SYNTHETIC=1` 自检开关）：
    `[T1] 样本来源：synthetic — …合成 fixture（4 份）`，31 passed。
- **样本获取方式已登记**（本条诉求原文的另一半）：
  - 动医真实样本 → `/Users/biodog/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治/M4A1_禽流感/`
    （4 份，只读）；换机时设 `VETMED_SAMPLE_DIR` 指向等价目录即可。
  - 跨学科样本 → 下载 CDC 公共领域课件置于 `VETMED_CROSS_DOMAIN_DIR` 指定目录；
    **刻意不自动下载**（网络依赖会让测试结果不确定）。
- 结果：**386 passed / 3 skipped → 390 passed / 0 skipped**（T1/T6/T11 的 8 个 subtest 首次真跑）。

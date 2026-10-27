# Feature Requests

Capabilities requested by the user.

---

## [FEAT-20261022-001] 静态数据流分析以发现「提到但没用」的配置键

**Logged**: 2026-10-22T21:45:00+08:00
**Priority**: medium
**Status**: pending

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
- **Status**: partial（静态部分已做，"运行时断言通用化"未做——需逐键脚本，暂以专项脚本覆盖）

---

## [FEAT-20261023-002] config/harness.yaml 变更自动同步 docs/architecture.md（含未覆盖项）

**Logged**: 2026-10-23（v3.16.0 批次 · W5）
**Priority**: medium
**Status**: partial

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

### Metadata
- Frequency: first_time
- Related Features: 单一数据源纪律（harness.yaml 为编排事实唯一源）、ensure_settings 第 7 项

### Resolution（v3.16.0）
- 已做：阶段镜像块守卫 T1–T7（见 `scripts/test_arch_drift.py` 与 `docs/architecture.md#防漂移守卫`）。
- 未做：上列 1/2/3 项；如需继续，建议按"先在 MD 建 sentinel 镜像块、再扩断言"的顺序推进，
  **不要**直接对散文做正则匹配（FEAT-20261022-001 已证明纯文本判据假阳性不可控）。
- **Status**: partial

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

# 更新日志 · CHANGELOG

本文件记录动物医学教学PPT智造团（vet-med-ppt-team）的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [v3.16.0] - 2026-10-23

### 概述（九维度独立诊断整改：F1–F9 全部落地 · 治「声明层与执行层两张皮」）

本次整改的起点是一份**从零开始的九维度独立诊断**（4 个只读子代理并行覆盖 + 主理人复核），
确认 7 条高严重度短板（H1 页数口径冲突 / H2 三源阈值双重声明 / H3 信封字段规则不被消费 /
H4 单页文字三套数值 / H5 缺「修复不得降级」条款 / H6 无质量收敛判据 / H7 领域知识零沉淀）。

**诊断同时推翻了此前两个「已修复」的自评**：

| 此前声称 | 实际 | 后果 |
|---|---|---|
| v3.13.0「页数口径冲突已消解」 | 只改了 MD，没改 yaml、没给代码豁免 | 按 MD 口径做的课件必被闸 4 P0 阻断 |
| v3.15.0「第 18 项已用 AST 精确判据」 | 提示数从 83 变 89，判据变了但未同步口径说明 | 判据变更未声明 |

> **本版贯穿的纪律**：每条规则必须回答「谁执行 / 什么算违反 / 违反后走到哪一步」。
> 凡「写在文档里但没有执行者」的，一律治本（要么实现读取、要么删掉、要么显式登记为待办），
> 不再允许「看起来有护栏、实际不设防」。

### ① 页数双口径（F1 · 治 H1）

`config/visual-rules.yaml` 保留 `hours_page_range`（整套课程口径）并新增
`hours_page_range_single_ppt`（单次 PPT，取 `course-profile-defaults.md#2` 的 12–18/22–32/32–45/42–58）
与 `page_caliber_default: "course"`；`verify_deck.py` 新增 `--caliber {course,single-ppt}`。

**默认恒为 `course`，绝不因使用场景静默切换**——规则引擎猜场景 = 同一份文件可能给出不同结论。
单次 PPT 必须显式 `--caliber single-ppt`。
验证：同一份 24 页课件，`--caliber course --hours 2` 判「课时不达标」(36-52)，
`--caliber single-ppt --hours 2` 通过 (22-32)，结论相反；不加参数与显式 course 输出一致。

**缺档不再静默通过**：单次 PPT 口径只定义 1/2/3/4 课时，故 `--hours 1.5` 报
「课时匹配未执行（非通过）」，`hours_ok=false` 明确表示**未判定**（既非达标也非不达标），
计入 P3 明示、不阻断写回。**本版不推导 1.5 课时的新页数区间**——没有依据的数字宁可不写。

### ② 单页主框字数真接线（F4 · 治 H4）

`density.max_body_chars_per_slide: 150` 从 v3.5.0 起就配在 yaml 里却**零代码引用**，
本版接入 `verify_deck.py`「主框密度」检查：排除标题占位符、图注/来源、页脚页码框后统计，
超出发问题类型 `主框密度超标`（级别 **P1**，已显式登记进 `severity.P1`）。

**三个数字各司其职，不再混为一谈**：400 看整页（发「文字墙」P1）／150 看主框（机器门禁）／120 看草稿（设计期自检目标，**机器不读**）。

**附带修正一个类别错误**：`_TYPE_LEVEL` 未登记类型的默认级别此前是 `P0`——
未知类别的严重性是未知的，默认判最严没有依据，且会让新检查在标定期就拦死课件（进而诱导绕过门禁）。
改为不落任何级别、计入 P3 明示并列进 `stats.unknown_red_keys`，由单测 `T_red_keys_in_severity` 守着
「现有 red 键必须全部已登记」，因此**不改变任何现有问题的分级结果**。

### ③ 三源阈值单一数据源（F2 · 治 H2）

删除 `harness.yaml#budgets` 里与 `domain_config.yaml#three_source_check` 重复的两个键，
`harness.py` 的 `budget` 改读后者并在输出中标明 `config_source`；
`executed_by` 由错误的「verify_deck.py#闸4.5」更正为真实函数 `_load_three_source_thresholds()`。

**新增体检第 21 项**（阻断）作复发防线：双重声明检测 + 运行时断言
（`budget check` 的值必须等于 domain_config 的值且来源指向 domain_config）。
这条同时补上了第 18 项 AST 判据的已知盲区——「读了 fallback 而没读配置」静态原理上查不出，只能靠运行时断言。

### ④ 回传信封字段规则落地（F3 · 治 H3）

`references/result-envelope.yaml` 新增 `validation.content_rules`（5 条），`harness.py` 真实消费：
confidence 禁裸标签 / deliverable_summary 须含可验证计数 / `status=success` 须 `issues` 为空 /
metrics 键须为子集（未知键只告警）。规则、词表、正则全部读 yaml，代码只做执行。

**取舍已写入代码注释**：`status=success` 且 `issues` 非空判**失败**（告警会被当可放行，拦不住自评失真）；
metrics 未知键判**告警**（选填自增字段，判失败会逼成员删指标或谎报键名）。

**顺带修掉一条判据漏网**（由新单测反向验证抓出，非测试写错）：`"问题已修复归零"` 曾因
「归零」的汉字被证据正则当成可验证计数而逃过拦截——修法是命中裸词后**先剔除裸词再判计数**
（`evidence_check_excludes_bare_terms`），判据侧修而非放宽覆盖面。

### ⑤ 质量收敛判据（F6 · 治 H6）

`loop_b.budgets.no_progress_threshold` 此前**零命中**（配了无执行者），五类终止条件全是工作量/交互维度，
机器检不出「缺陷数已不再下降」。现于每轮 `continue` 落质量快照，连续 N 轮 P0+P1 未下降即
exit 1 + 终止建议 + trace 事件 `no_progress`。

**报告优先于自报**：`--verify-json <verify_deck 报告>` 从机器复算结果取数；
手工 `--p0/--p1/--p2` 保留但标注「自报值，未经交叉核验」；两者冲突以报告为准并留证；
报告缺字段/不可解析 → **显式报错，不静默退回手工值也不按 0 处理**。
另：`quality_history` 必须登记进 `context.state_allowed_keys` 白名单，否则写入被静默拒绝（联动已在代码注释标明）。

### ⑥ 修复不得降级（F5 · 治 H5）

`references/batch-surgery-sop.md` 新增 §8：`adjudication-rules.md`、`references/sop-stages.md`、
`agents/verifier.md` **三处降级授权**同步加约束——降级须①主理人显式签字 ②理由+恢复期限+受影响检查项清单
③留痕可回滚，**缺任一步 = 未完成，门禁仍按原判据计**。明确「调字号改版面 ≠ 降级，把 12pt 红线往下调 = 降级」，
并把「为让红灯变绿而放宽判据」定义为无效修复 + 自引入缺陷。

### ⑦ 领域知识最小集（F7 · 治 H7）

新增 `references/poultry-disease-index.md`（24 条家禽疫病索引 + 8 种实验室诊断方法对照表），
填补此前全包 `ELISA`/`PCR`/`血凝`/`药敏` **均 0 命中**的空白。
**零处编造编号/数值**：发病率、滴度阈值、药敏折点、国标编号、DOI/PMID 一处未写，
不确定项（如 FAdV 血清型-综合征对应、HI/ELISA 判定阈值）就地标 ⚠️ 并集中列入「待人工核实」13 项。

### ⑧ 配图链路记录字段（F8）

`extract_assets.py` 增 `width/height`（EMU→px，取不到置 null 并在 notes 说明原因，不填 0 掩盖）、
`source_url`、`doi_pmcid`；**`license_note` 默认值由「原课件自带」改为空**
（原默认值暗示素材默认可用，与许可纪律冲突）；空许可 ⇒ `reuse_status` 必须为「待核查」，
写盘前断言；`--require-license` 非 0 退出版并列出 asset_id。
新配置源 `references/asset-fields.yaml`（**独立 yaml 文件，不采用 md 内嵌 yaml**——包内机器源只有
`references/*.yaml` 与 `config/*.yaml` 两种范式，再开第三种就是本次要治的多源病根）。

### ⑨ 架构与 agent 治理（M7 + 关联项）

`docs/architecture.md` 由**已废弃的六阶段**改为 `harness.yaml#stages` 的**五闸 stage 0–4**
（含并行判据、补上此前遗漏的 verifier），并声明 yaml 为唯一源。
新增 `scripts/test_arch_drift.py`（7 断言）：镜像块与 yaml 逐项比对、成员表 == 注册表+主理人、
每个成员 MD 必须把工具白名单指向 yaml、散文里不得再出现旧六阶段口径。

7 个无归属脚本补「所有者/执行者 + 用途 + 何时被调用」头块；5 份成员 MD 的工具清单改为引用 yaml
（不再各自复述）；逐字复制的信封 JSON 副本改为引用式；5 份 MD 补**可照抄的合规回传示例**
（示例已落 /tmp 真跑过 `verify-envelope` 验证 rc）；README/INSTALL 的「六阶段」表述同步。

### ⑩ 建议级检查（rubric，默认关闭）

新增 `visual-rules.yaml#checks`：`title_position_consistency`（V1 标题位置众数偏离）、
`image_area_ratio`（V5 图片面积占比 + 纯文字页连续上限）。产出进 `result["rubric"]`，
**不计入 p0/p1/p2、不影响退出码**。默认关闭的理由写进 yaml 注释：缺乏基线标定，
默认开启会产生无法校准的假阳性，而本项目铁律是「假阳性必须为零，否则门禁会被绕过」。

### 版本与工程状态

- 版本**五处**同步 **3.16.0**（`.claude-plugin/plugin.json` / `.codebuddy-plugin/plugin.json` /
  `config/harness.yaml` / `scripts/harness.py` 文件头 + doctor 常量 / 两棵树的对应副本）
  ——第 5 处（`harness.py` doctor 常量）是**体检第 14 项在收口时抓出来的**，说明该检查确实在起作用。
- 体检 **21/21 全绿**（第 19 项漂移核对由 11 项扩至 26 项；新增第 21 项三源单一数据源）
- 回归 **112 passed / 3 skipped**（新增 `test_verify_deck.py` 14 例、`test_arch_drift.py` 7 例；
  `test_harness.py` 由「0 个 `def test_`（pytest 假绿）」改为 21 个可发现用例）
- 双树同步：`packages/vet-med-ppt-team/` 与根目录逐字节一致

### 已知瑕疵（如实登记，未修）

1. `config/harness.yaml#stages.4.name` 仍含「（v3.3.0）」版本串——去化需连带改 architecture.md
   镜像块与 `test_arch_drift.py`，收益/风险不划算，留待后续。
2. **V3（取色比对）与 C5（数字来源）仍未实现**——V3 需模板 `clrScheme` 外部数据，
   C5 的正则误报率高；已在 `course-profile-defaults.md#4.5` 显式登记为「无机器实现」，
   并在 `.learnings/FEATURE_REQUESTS.md` 追加缺口条目（含误报原因分析）。
3. 三源核验仍是**自证循环**：代码只查 `sources[].ok` 是否被写成 true，不验证来源真实存在。
4. 单次 PPT 口径无 1.5 课时档（见 ①），已给出处置规则而非自造数值。

---

## [v3.15.0] - 2026-10-22

### 概述（FEAT-001：死配置判据由文本搜索升级为 AST · 含一次判据局限的实证标注）

补 v3.14.0 遗留的 FEAT-001：让第 18 项能区分「代码提到键名」与「代码真读了值」。

### ① 第 18 项判据：纯文本 → AST 真实读取点

新增 `_collect_ast_reads()`，解析三种形态：
① `x.get("key")` ② `x["key"]` ③ **字典字面量的字符串键**
（如 `threshold_map = {"stage_minutes": ("max_stage_minutes", …)}`——
这类键**真被消费**（`b.get(key)` 按名查）但不出现在任何 `.get("…")` 字面量里，
只按 ①② 判会漏，实测 `max_stage_minutes` 即是此例）。

**探针实测**：yaml 150 个叶子键中，纯文本判据认为"有读取者"但 **AST 无真实读取点的有
109 个（73%）**——这就是原判据的假阳性规模。修正后：人读型登记 **34→84**、提示 **139→89**，
剩余项语义清晰（`three_source_check.enabled`、`stages.*.next`、`observability.trace_events` 等）。

**顺带修一个真 bug**：`seg_hit` 的路径前缀构造写成 `"." + segs[i:]`，
只拼出 `.domains.active`，**首段前缀 `.domains` 从未被单独试过** → 路径白名单整条失效。
改为逐段前缀检查后，白名单才真正生效。

### ② AST 判据的局限（反例实测，如实标注）

把 `cfg.get("three_source_check")` 改成 `{}`（读取链被删）后：
- ✓ `three_source_check` 正确从 AST 读取集消失 → **判据能发现"读取链被删"**
- ✗ **但** `sample_rate` / `pass_threshold` **仍被判为活跃**——它们同时出现在
  fallback 字典（`verify_deck.py:134/142`）与对 `THREE_SOURCE` 的取值（`:824/837/849`）中，
  **不依赖外层 cfg 也能活着**。

**结论**：静态判据能发现"读取链被删"，**发现不了"读了 fallback 而没读配置"**——
后者必须靠**运行时断言**（配置值 == 运行时值）覆盖，即 `verify_three_source_config.py` 的做法。
已写入代码注释与 `.learnings/FEATURE_REQUESTS.md`，标注为 partial，
并明确"不应继续投入静态方向"。

### 验证

- 体检 **20/20 全绿**（第 18 项仍为 INFO 不阻断）
- 反例改动的 `verify_deck.py` 已复原（git 0 残留）
- 9 个 `test_*.py` 回归套件全过
- 版本四处同步 **3.15.0**

### 仍未做

- FEAT-001 的"运行时断言通用化"（给每个关键阈值键配自动断言）——本批实证证明**静态路线
  有天花板**，通用化需另设机制，暂以专项脚本 `verify_three_source_config.py` 覆盖
- `_FALLBACK` 逃生舱本身保留（受 `VERIFY_ALLOW_FALLBACK=1` 管控，设计如此）

---

## [v3.14.0] - 2026-10-22

### 概述（收官批：回退阈值漂移防护 + 交接落盘契约防护 + 经验沉淀）

补齐 v3.13.0 列出的两项遗留，并按 `self-improving-agent` 纪律把本轮教训沉淀进 `.learnings/`。

### ① `_FALLBACK` 回退阈值防漂移（第 19 项 · 阻断）

**先核实再动手**：实测 `_FALLBACK` 的 7 项阈值与 `visual-rules.yaml` **完全一致、零漂移**。
故真问题不是"值错了"，而是**没有任何机制防止将来漂移**——
改了 yaml 忘了改 `_FALLBACK`，yaml 加载失败时门禁会拿**过期阈值继续判且完全静默**，
比无护栏更危险（人以为用新红线，实际是老红线）。

新增 `check_fallback_drift()`：用 `ast` 解析 `_FALLBACK` 字面量（不用正则，避免误抓），
与 yaml 逐项比对（6 项标量 + `hours_page_range` 各档 = 11 项核对），漂移即告警并指出该同步哪一项。

**与第 18 项的区别**：18 项查"配置有没有人读"（判据模糊→降级 INFO）；
本项查"**两份同源数据是否一致**"（判据确定：等值即可比，假阳性为零）→ **阻断**。

**反例验证**：改 `visual-rules.yaml` 的 `body_min_pt` 12→14 而不改 `_FALLBACK` →
`⚠ body_min_pt: _FALLBACK=12.0 ≠ yaml=14.0（font.body_min_pt）` 并阻断；已复原（git 0 改动）。

### ② 跨成员交接落盘契约防护（第 20 项 · 阻断）

v3.13.0 把 3 处「交严真奥补查」类表述改成了落盘契约，但那是**一次性修复**——
这是文风问题，下次写文档极易复现。

新增 `check_handoff_paths()`：扫 `agents/` 与 `references/` 中形如
「交/找/通知/传给 + 某成员」的交接表述，检查同行或下两行内是否给出合规载体
（① 信封 `issues` ② 落盘路径 ③ 明示经主理人 ④ 明示不得直接联系），
四者皆无即判悬空交接。上下文窗口限定 3 行以收敛误报面。

**反例验证**：把「流转：由主理人分派…」还原成「流转：交严真奥补查即可」→
`⚠ agents/visual-slide-designer.md:108` 精确报出行号并阻断；已复原（git 0 改动）。

### ③ 经验沉淀（`.learnings/`）

按 `self-improving-agent` 纪律新建 `.learnings/`，记录 3 条教训 + 3 条报错 + 1 条能力诉求：

| ID | 类别 | 要点 |
|---|---|---|
| LRN-001 | best_practice | 「配了没人读」判死前须分清「代码该读」与「主理人该读」，否则体检塞满误报即失效 |
| LRN-002 | correction | 断言"不存在"前必须查全两个根（marketplace + 用户技能目录）——本项目已因此虚报过一次缺陷 |
| LRN-003 | best_practice | 修缺陷/加检查都必须做 before/after 对照或反例验证，否则无法排除"本来就没问题" |
| ERR-001 | infra | Bash grep 偶发返空，空结果不可作为"未命中"证据，须用 Grep 工具复核 |
| ERR-002 | infra | `cd && python - <<EOF` 复合命令偶发被沙箱拦截；验证逻辑写成独立脚本更稳 |
| ERR-003 | backend | 递归闭包新增变量漏 `nonlocal`；且改递归体后编译通过≠运行正确 |
| FEAT-001 | feature | 需能区分"提到键名"与"真读了值"的静态检查（第 18 项固有局限） |

### 验证

- 体检 **20/20 全绿**（新增第 19/20 项，均经反例验证会真报警）
- 9 个 `test_*.py` 回归套件全过
- 两处反例验证用的临时改动均已复原，`git status` 确认 0 残留
- 版本四处同步 **3.14.0**

### 仍未做

- `verify_deck._FALLBACK` 本身**仍保留**（受 `VERIFY_ALLOW_FALLBACK=1` 管控的逃生舱，设计如此）——
  本批只加了防漂移，**未删**逃生舱本身（删了会让 yaml 损坏时门禁完全无法运行）
- FEAT-001（区分"提到"与"真读"）暂以专项脚本务实替代，未做通用静态分析

---

## [v3.13.0] - 2026-10-22

### 概述（收尾批：通信冲突落地化 + 阈值接配置 + 死配置体检）

按 v3.12.0 遗留四项的建议动作逐项执行。**其中一项经核查后撤回**（见下）。

### ① 跨成员通信冲突（P1 · 三处措辞改落盘契约）

4 处禁令（禁止横向直连）与 3 处业务指令（「交严真奥补查」「进入二八难点候选」）冲突——
平台**确实**无 agent-to-agent 通道，问题不在禁令而在**业务指令的交接路径未定义**，
成员可能因此干等或私聊。修法：把口头约定变成可执行落盘路径（沿用"单一数据源"思路）：

| 处 | 原措辞 | 改为 |
|---|---|---|
| `visual-slide-designer.md:106` | 「交严真奥补查」 | 落盘 `<RUN_DIR>/_search_requests/`，**由主理人下一轮分派**；❌ 不得 SendMessage；只写对话=未交付 |
| `adjudication-rules.md:102` | 「交内容专家补查」 | 同上（含补查结果回写同目录） |
| `dvm-content-expert.md:39` | 「自动进入苏学法的二八难点候选」 | 写进**证据包 `issues` 字段**（唯一上抛通道），由主理人汇编进蓝图 |

并在 `team-lead.md` 禁令处加**三条合规路径**（信封 `issues` 字段 / 共享目录落盘 / 下一轮任务包分派），
明令"成员不得自行发明第四种"，杜绝再有人误读为直连。

### ② verify_deck 三源阈值接配置（P2 · 行为零变化）

`:776/788/799` 三处硬编码 `0.8/0.1` → 改读 `domain_config.yaml#three_source_check`（新增
`_load_three_source_thresholds()`，与既有 `_load_threshold` 同风格、失败显式告警）。
help 文本同步（去掉"抽 10%/≥80%"的写死表述）。

**决定性验证**：yaml `pass_threshold` 0.8→0.55 → 运行时 `THREE_SOURCE` 随之变 0.55
（修复前无论如何都是 0.8）；已复原为 0.8，**默认行为零变化**。
配套 `verify_three_source_config.py`：断言运行时值 == yaml 值 + 静态扫字面量残留。

### ③ 重叠双实现加互注（P3 · 不合并）

经核查**二者判据本就不同**（verify_deck=仅文本框·P1·无 GROUP 换算；GeoChecker=任意形状·WARN·
有 GROUP 换算与基线豁免），不是重复实现，合并会丢失一个语义且移植 264 行风险高。
故在两侧 docstring 加**分工对照表**，明确"同一份课件两个数字不同是正常的，
谁也不该把一个修正成另一个的值"。

### ④ 量规不可解析 —— **撤回，非问题**

上轮结论有误：当时只搜 marketplace 目录，未搜用户技能目录。实测
`~/.workbuddy/skills/teaching-ppt-studio/references/seven-dimension-rubric.md`
**存在**（9794 B，2026-10-17 更新），引用链是通的，**无需任何动作**。
教训：断言"不存在"前须查全两个根（marketplace + 用户技能目录）。

### ⑤ 死配置体检（第 18 项 · 含一次失败后的降级）

**首次尝试失败并已据实记录**：把"无代码读取者"一律判死配置 → 首跑报 80 项；
放宽白名单仍报 100 项。根因是**「谁该被代码读」无法自动判定**——
`tools_whitelist`（成员工具权限）、`pass_rule`（AI 素养判据）、`snapshot.*`（快照策略）
都是有意义的配置，但本就由主理人/流程消费而非脚本。继续调白名单只会变成
「为了让检查变绿而往白名单塞」，那是自欺。

**最终设计**：降级为 **INFO 提示，不阻断不计入 rc**。当前输出：
`代码读取 227 项 · 人读型登记 43 项 · 提示 83 项`。取舍理由：**假阳性必须为零，
否则体检会被绕过**。真正会阻断的判死配置已由更精确的专项检查覆盖（第 16/17 项、budget list）。

**已知局限（反例实测，如实标注）**：本检查是纯文本包含匹配，无法区分
「代码提到该键名」与「代码真读了该值」。反例——把 `cfg.get("three_source_check")` 改成 `{}`
（读取行为已破坏）后统计**不变**，因该键名在其它脚本/注释中仍出现。
故本项只能发现"完全无人提及"的键，发现不了"提到但没用"的键；
后者需 `verify_three_source_config.py` 这类**逐键断言运行时值 == 配置值**的专项验证。

### 验证

- 体检 **18/18 全绿**（第 18 项为 INFO 不阻断）
- 9 个 `test_*.py` 回归套件全过
- `verify_three_source_config.py` 通过（运行时值 == yaml 值 + 无字面量残留）
- 版本四处同步 **3.13.0**

### 仍未做

- `verify_deck` 的 `_FALLBACK` 内置阈值仍在（受 `VERIFY_ALLOW_FALLBACK` 环境变量管控，属受控逃生舱）
- 跨成员通信三条合规路径的**机器校验**未做（当前仍是文档约定，可考虑后续加 check）

---

## [v3.12.0] - 2026-10-22

### 概述（回传信封治本批 + 并发安全 + 死配置激活）

管家节点指令「优先解决回传信封互斥」，并给出排查方向（并发/重试/幂等/锁）。
**据实澄清**：实测两条线都查了——并发隐患**真实存在且已实证**，
但它**不是信封互斥的根因**；根因是「多处各自定义 schema」。两线均修。

### ① 回传信封单一数据源（根因修复 · P0）

包内此前有**四套互斥定义**：`spawn-protocol.md:19` 自称唯一权威源要
`{from,stage,artifact,warnings,evidence_used,next_recommendation}`；
`harness.py` 校验 `{agent_id,task_id,phase,status,confidence,deliverable_summary}`；
5 个 agent MD 第三套（10 字段）；`ppt-producer.md` 同一文件内 §75/§117 又两套。
后果：按权威源产出的**合规**信封被校验器判「缺字段 → 退回」。

- **新增 `references/result-envelope.yaml`**：必填 6 / 选填 4 / status 枚举 / 逐字段语义判据
  + **legacy_aliases**（from→agent_id 等 6 组映射）+ 校验行为 + 漂移守卫
- `harness.py` 改为**读 yaml**（`load_envelope_schema`），不再硬编码 `ENVELOPE_REQUIRED`
- 新增**旧字段归一化**：读到旧名自动改写并在报告标注 `normalized_keys`（历史 trace 仍可回溯，
  不用因旧名把整条历史判红）；`reject_legacy_keys` 确保新产出不再用旧名
- 报错信息补「字段定义见 references/result-envelope.yaml」——修前只说"缺字段"，不知道该按哪份补

### ② 并发安全（实证缺陷 · A 线）

- **原子写**：`_write_loop_state` 原为裸 `open(w)` + `json.dump`——先截断后写，
  中途崩溃会留半截 JSON，而 `_read_loop_state` 解析失败会「按空状态处理」= **静默重置整个 Loop 状态**。
  改为 `mkstemp` 同目录 → `fsync` → `os.replace`（同 fs 内原子替换，读者只见旧版或新版）
- **文件锁**：新增 `_StateLock`（`fcntl.flock` 排他；无 fcntl 退化为进程内并**显式告警**），
  并把 `cmd_loop` 的 10+ 分支抽为 `_loop_dispatch`，使「读状态 → 改 → 写」**整段事务**在锁内
- **对照实验（决定性证据）**：同一工作区并发跑 20 次 `loop add-item`——
  **修复前只保住 1/20 条**（丢 19），**修复后 20/20 全存**，`history` 亦 20 条

### ③ 6 项死配置激活（`budget` 从 3 项 → 9 项）

`harness.yaml#budgets` 有 9 项，但 `cmd_budget` 的 `limit_map` 只映射 3 项；
其余 6 项（`max_spawn_attempts_per_member` / `max_react_rounds_per_gap` / `max_stage_minutes` /
`max_artifact_bytes` / `three_source_sample_rate` / `three_source_pass_threshold`）
**只在 `_FALLBACK` 兜底字典出现、代码从不读**，而 `sop-stages.md` 等文档仍把它们当生效约束引用
——「看起来有护栏、实际不设防」。

- 分两类处理，不混为一谈：① 计数型 → 补进可 check/spend；② 阈值型 → 注册为**可查但不由 harness 执行**，
  输出标明 `executed_by`（哪个脚本/文档负责），未配值时 **exit 1 暴露"护栏缺失"**而非静默通过
- 新增 `budget list`：一次列出全部 9 项及其执行者；argparse 的 `--kind` 放开硬编码 `choices`

### ④ 悬空脚本引用（agent MD 拿包外脚本当论据）

`ppt-producer.md` 两处把 `registry_rebuild.py` / `repair_p0_v200.py` 作为「职责已被承接」的依据，
但两者**均不在 `scripts/`**（Glob 确认无此文件，属课程工作区）。包外脚本随工作区丢失后，
该论据自动失效且无人察觉。已删除「已由 registry_rebuild 承接」的表述（包内真正承接者是 `harness.py gate`），
另一处改为显式标注**外部依赖** + 工作区不可用时改用 `harness.py state init`。

### ⑤ 体检第 17 项（悬空脚本引用巡检，防复发）

扫描 agents/ 与 references/ 中反引号包裹的 `<name>.py`，不在 `scripts/` 且不在
**显式外部白名单**（登记即"承认这是外部依赖"）→ 告警。
反例验证：植入 `ghost_script_xyz.py` → `[17/17] ⚠` → 恢复 → `✓`。

### 验证

- 体检 **17/17 全绿**（16 受众分层 + 17 悬空引用，反例验证均通过）
- 9 个 `test_*.py` 回归套件全过（**test_loop_state 33/33**：状态机重构未破坏）
- 信封校验实测：新 schema ✓ 合规 / 旧 schema 归一化后再按新规则判缺（信息里带正确文件指引）
- `budget`：计数型 check/spend 行为不变；阈值型可查、spend 被拒（exit 2 用法错误）
- 版本四处同步 **3.12.0**

### 未做 / 挂账

- `verify_deck.py` 的 three_source 阈值仍**硬编码** 0.8/0.1（本次只让 harness 能查、能标注"执行者是 verify_deck"，
  **没改 verify_deck 本身**——改它涉及闸4.5 判定逻辑，须单独评审）
- `seven-dimension-rubric.md`（诊断量规唯一源）在本机 marketplace 仍不可解析
- 元素重叠双实现（verify_deck 26 行 vs ooxml_lint 264 行）未合并
- 跨成员通信禁令与「视觉→内容 交检索单」等 2 处业务指令的冲突未裁决（需管家节点定口径）

---

## [v3.11.0] - 2026-10-22

### 概述（受众分层治本批：四层 + 国家标准深度标尺 + 第 16 项体检兜底）

管家节点裁决后执行。要解决的不是"改一张表"，而是**「单点定义 + 11 处各自引用 + 无机器校验」**
这个结构性隐患——v3.10.0 已因同类原因发生过"终审 10 项改 11 后漏改 3 处"的事故。

### ① 深度标尺改用国家教学标准（第一性原理，证据可复核）

依据教育部《动物医学专业教学标准》（**高等职业教育本科 / 专科**两版，2025-02）——该标准的
**专业核心课程第 2 项即「禽病防治技术」**，与本包课件同门。标准用**三档行为动词**规定深度：

| 知识点 | 专科版 | 本科版 |
|---|---|---|
| 禽病诊断 | 了解 | 了解 |
| 发病机理 / 防控原理 / 废弃物处理 | 理解 | 理解 |
| 预防控制 / 诊断 / 治疗方法 | 掌握 | 掌握 |
| 禽-人共患病 | —（未列） | 掌握 |

**关键结论**：两版对同一课程的三档动词**完全一致**，层次差别体现在**覆盖面更宽**而非难度递进。
故本包受众深度标尺改用 `了解 / 理解 / 掌握` 三档，**替代**此前的"案例篇幅百分比"推测口径。

### ② 受众分层三层半 → 四层（管家节点 2026-10-22 确认）

新增**大专**层；「职业本科」与「本科生」**合并为一层**；默认层 = 职业本科与本科生。

### ③ 课内时间结构统一 90/5/5（四层统一）

讲授 90% / 案例 5% / 互动 5%（管家节点确认）。受众差异体现在**讲授内容的深度档位**，
不体现在时间比例。

> ⚠️ **防误用注释**：国家标准「实践性教学 ≥60% 总学时」是**四年课程总学时**口径；
> 90/5/5 是**单次 45 分钟课内**结构。**层级不同，不可互推**（schema 与文档均已加注）。
> 实务推论：案例时间仅 2min/课时起 → 案例以"一页速览 + 备注展开"承载，**不做整节案例讨论**。

### ④ 页数口径冲突消解（P0 级，此前一直未发现）

`pedagogy-architect.md` 原「1 课时 18-28 页 / 2 课时 36-52 页」与
`course-profile-defaults.md#2`「12-18 / 22-32」**两套区间完全不重叠**，且门禁
`verify_deck.py#hours_page_range` 按前者判定——按后者制作的课件会被误判「课时不达标」。
现**统一以 course-profile-defaults#2 为唯一页数口径**，pedagogy 旧区间已删改为引用。

### ⑤ 落地文件（对齐方案 M1–M8 全部完成）

| # | 改动 | 文件 |
|---|---|---|
| M1 | 受众表重写为四层 + 三档深度 + 90/5/5；§4.3 差异化阈值同步四层；§2 课时表按 90/5/5 折算 | `references/course-profile-defaults.md` |
| M2 | **新增单一数据源**（4 层 / 三档 / 90-5-5 / 唯一默认 / 必备键 / 漂移守卫） | `references/audience-profile-schema.yaml`（新） |
| M3 | **体检第 16 项** `check_audience_profile()`：层数 / 深度档 / 时间结构和 / 唯一默认 / 每层必备键 / 旧层名残留扫描 | `scripts/ensure_settings.py`（N 15→16） |
| M4 | 默认受众改合并层 + 深度档 + 时间结构写入 yaml | `config/harness.yaml#loop_b.defaults` |
| M5 | 受众小节改四层三档；页数表改引用 | `agents/pedagogy-architect.md` |
| M6 | 受众表四层 + **学术扩展标注纪律**（超国家标准内容须标「学术扩展·非课程标准要求」） | `agents/dvm-content-expert.md` |
| M7 | intake 默认值同步 + `audience_layers` 须取 schema 的四个 id | `references/task-intake-checklist.md` |
| M8 | 提示词同步四层 / 90-5-5 / 沿用理由三选一 / **每轮强制自检** / 内容页不强补页眉 | `references/loop-master-prompt.md` |

### ⑥ 第 16 项当场抓出一处漏改（自证有效）

首次运行即报：`references/course-profile-defaults.md` **§4.3 差异化阈值表仍留旧三层结构**
（「③ 本科生」行）——人工改 §1 时漏了 §4.3。修正后 16/16 全绿。
**这正是本次加体检项的目的：把"人靠自觉同步 11 处"换成"机器兜底"。**

### 验证

- 体检 **16/16 全绿**（第 16 项输出：4 层 · 深度档 了解/理解/掌握 · 时间 90/5/5 · 默认层 zhiye_benke_benke）
- 9 个 `test_*.py` 回归套件全过
- 版本四处同步 **3.11.0**

### 未做 / 挂账

- 国家标准 PDF 未随包分发（体积大），深度标尺的论证过程见管家节点侧提案目录；包内保留 schema 的 `depth_scale` 定义与 `standard_ref` 字段指向标准名称与条目
- 已交付的 v1 课件受众标签**不重标**（管家节点裁决 5）
- 回传信封三套 schema 互斥（P0）、6 项 budget 配而不生效、元素重叠双实现等——属六维度诊断发现的**其他维度问题**，本批未处理，另行立项

---

## [v3.10.1] - 2026-10-22

### 概述（首次真实课件运行修 bug 批：GROUP 嵌套图片计数）

Loop B 首次在真实课件上跑转换层（33 页 / 37 资产），`fix_md_image_refs.py` 三方计数立即现形一个
合成样本测不出的 bug。端到端实跑的价值当场兑现。

### 修的内容

**`fix_md_image_refs.py` `count_deck_images_by_page()`**：图片全在 GROUP 内时 deck 计数=1、
md/manifest=3，误报"计数不一致"（exit 1）。

- **真因（两层）**：① `has_blip()` 用 `_element.iter()` 扫描整个形状子树——组合形状必然"含"
  其子图片的 blip；② 旧 `walk()` 的递归条件写反（`has_blip(sh) is False` 才递归），导致组合
  被整体计 1 且不再下钻。
- **修法**：先判 `MSO_SHAPE_TYPE.GROUP` 递归（组合自身不计数），散图再判 blip。
- **为什么合成样本没测出**：v3.8.2 fixture 全是顶层散图。真实模板 slide1 三图全在组合内。
- **回归锁**：`test_fix_md_image_refs.py` 新增 **T8**（`TestNestedGroupCount`，造一页两页
  PPTX：第 1 页顶层散图、第 2 页两图入组，页分布对齐 manifest；PIL 缺失时回退最小合法 PNG）。
  套件 7 → 8 例，全过。

### 验证

- 既有 7 例回归 OK；真实课件复测：**37/37/37 三方一致，exit 0**。
- `ensure_settings` 15/15（9/9 套件）。

### 关联

- Loop B 端到端首跑同时完成：start → intake（A 类 5 项 confirmed）→ markitdown 374 行 →
  extract_assets 37 资产 → 引用修复 37/37 → soffice 渲染 33/33 页 PNG → verify_deck 全量
  （P0：课时不达标/缺目录/缺题页；P1：P22 框交叠、33 页缺备注）→ 5 条诊断条目登记 →
  Round 1 轮报落盘、状态机停等用户裁决（方向 A/B，见 `*_wip/round1_report.md`）。
- 版本四处同步 **3.10.1**。

---

## [v3.10.0] - 2026-10-22

### 概述（接单默认落地批：用户九项信息落盘 + 默认模板实测 + GEO-003 基线豁免）

用户补齐了长期悬空的接单信息（受众 / 课时 / 模板 / 范围 / 验收 / 交付）。此前这些信息只存在于对话中，
换个会话就丢；本批把它们落盘为**可执行契约**，并对用户指定的默认模板做只读实测，
实测过程中暴露一个会直接破坏验收的问题（GEO-003 噪音），一并修掉。

### ① 新增三份默认档案（references/）

| 文件 | 内容 |
|---|---|
| `course-profile-defaults.md` | 受众四层参数表（术语密度/实操与案例比重/机理深度/互动形式，四维度须同时调）；课时映射（1–4×45min → 页数/知识点/案例/图表/互动时长）；范围（全部页 + 逐页六查）；验收矩阵（内容 5 条 + 视觉 7 条 + 受众/课时差异化阈值） |
| `default-template-profile.md` | 默认模板实测报告（指纹 `5fa78154`）+ **三条硬约束** + 登记册执行步骤 |
| `delivery-spec.md` | 交付三件套 schema（成品 PPTX / 逐页修改说明 / 验收自检清单），含逐页说明字段表与自检清单模板 |

三项声明纪律：用户**给定**的（受众方向/课时/模板路径/范围/验收维度/交付形态）标「已确认」；
由给定方向**推导**的数值（各层案例占比、课时→页数映射）标「建议值，首轮轮报追认」——不冒充实测、不冒充用户确认。

### ② 默认模板只读实测（三项硬约束，制作师必读）

实测方式：`theme_fingerprint.py` + `ooxml_lint.py` + python-pptx 直读（非目测）。

| 实测事实 | 后果 |
|---|---|
| **layouts=2 且两个版式 placeholders 均为空** | ❌ 禁止按占位符填内容（`slide.placeholders[0]` 必炸）；只能深拷贝既有页或新建文本框按坐标对齐 |
| **母版无页眉页脚占位符**，页眉由每页「文本框 18」硬编码（20 页=禽流感 / 8 页=感谢！） | ⚠️ 换课题必须**逐页改**，改母版无效；新增页必须手动复制该框，否则视觉不一致 |
| **原生表格 0 / 原生图表 0**（33 页） | 可编辑图表只能 `add_chart` 从零建并手工着色，取色须落在 clrScheme 十二色内 |
| 实际用字 Microsoft YaHei（166 处）vs 主题 fontScheme「等线」 | 字体方案与主题不一致，沿用须以实际用字为准 |

### ③ GEO-003 基线豁免（`--geo-baseline`）——修一个会让验收失效的问题

**问题**：默认模板自身产生 **552 条 GEO-003 WARN**（「矩形 9 × 矩形 10」重叠 63% 等模板固有底纹叠放）。
新稿如果不加基线直接 lint，这 552 条会**淹没真正的新增遮挡**，验收 V7「无文字溢出或遮挡」根本无法判定。

**修法**：`ooxml_lint.py` 新增 `--geo-baseline <模板.pptx>`，构建模板固有叠放指纹
`{slide_no: {(name_a, name_b): [ratio...]}}`；命中（同页序号 + 同名形状对 + 重叠率差 ≤5%）记为
`inherited` **不计 WARN 但如实计数**，只报新增重叠。

**修 bug 实录**：首版按名字对**取 max ratio**，同文件比自身仍残留 1 条。真因：模板 slide1 有**两个同名
「Picture 2」**，与「Picture 4」形成 1.000 / 0.908 两组重叠，取 max=1.000 后 0.908 那对差值 0.092 > 容差
被误判新增。改为**存 ratio 集合**逐值比对后归零。**同名形状是 PPTX 常态，不能假设名字唯一**。

**实测**（默认模板 33 页）：

| 场景 | 结果 |
|---|---|
| 模板 vs 自身 | `geo_inherited=552 / geo_new_overlap=0` ✅ |
| 副本加一个新框压住底纹 | `geo_new_overlap=12`，全部指向新框 ✅（不误豁免） |
| 不带 `--geo-baseline` | 555 WARN，与 v3.8.2 行为一致（向后兼容）✅ |

回归：`test_ooxml_lint.py` 新增 `TestGeoBaseline` **5 例**（G1 自身比对零新增 / G2 新增必报 /
G3 向后兼容 / G4 基线缺失不崩溃不静默豁免 / G5 同名形状多组重叠——**锁住本次 bug**）。

### ④ 关联文件同步

- `task-intake-checklist.md`：新增 §0-bis「用户已确认默认基线」；A 类 5 项 + 交付项不再每次追问，
  但保留**每单确认是否覆盖**的纪律（默认值 ≠ 本单意图）
- `config/harness.yaml#loop_b.defaults`：新增默认档案引用、模板路径与指纹、`geo_baseline_required: true`
- `agents/pedagogy-architect.md`：新增《受众分层与课时密度》——四维度须同时调、先问课时再定页数、每课时末独立小结页
- `agents/dvm-content-expert.md`：新增《受众驱动的术语与深度控制》——四层术语/机理/数据表 + 案例贴合生产一线 + 关键数据必注来源
- `agents/ppt-producer.md`：新增《默认模板的三条硬约束》+ GEO-003 必配基线跑
- `references/round-review-sop.md`：§11 终审验收清单 **10 项 → 11 项**（新增「无文字溢出或遮挡」，判据 `geo_new_overlap == 0`）
- `references/ooxml-compat.md`：GEO-003 状态补基线豁免
- `references/dual-loop-governance.md`：§8 第 9 项由「待用户提供」→「已确认」；新增第 10/11 项；§9 实测记录补场景 7/10
- `references/loop-master-prompt.md`：第 2 步内嵌默认基线摘要；第 7 步补无遮挡验收与交付三件套

### ⑤ 版本号

四处同步 **3.10.0**：`.claude-plugin/plugin.json` / `.codebuddy-plugin/plugin.json` /
`config/harness.yaml` / `scripts/harness.py`。

### 仍未解决 / 未实测（据实标注）

- **真实课件端到端全链仍未跑**：九项参数已确认，但**本单课件路径未给**。给课件路径即可开工。
- 场景 8（渲染失败故障注入）未做；soffice 26.8.1.1 当前可用。
- 课时映射与各层案例占比为**推导建议值**，首轮轮报须请用户追认。

---

## [v3.9.0] - 2026-10-22

### 概述（双层 Loop 契约下沉批：五条指令与越界校验从 Markdown 变成代码）

来源：2026-10-22 需求逐项核对时发现——v3.8.x 把 `loop_a/loop_b` 写进了
`config/harness.yaml`、把五条指令与终止五类写进了 `references/dual-loop-governance.md`，
但 **`scripts/harness.py` 从未含 loop 子命令**（grep 全文件确认零命中）。
即"逐轮停等""部分接受只冻点名条目""sha256 漂移即失效""沉默不推进""预算触顶不宣布通过"
全是靠自觉遵守的 Markdown 纪律——同一份治理文档 §8 第 3 项自己就写着"非代码级强制"。
配置注释 ≠ 可执行契约。本版把其中**可确定性判定**的部分下沉为代码。

### Added
- **`scripts/harness.py loop`（新子命令，13 个动作）**：
  `start`（存档原件 sha256/size/mtime + 建 `<name>_wip/`）· `intake`（九项 A 类缺一即
  `confirmed=false` + exit 1）· `add-item`（条目八字段落盘）· `status`（含原件是否被改动）·
  `resume`（**只报"第 R 轮/已冻 N/待办 M"并置等待确认，不续跑**）· `continue`
  （**缺 `--decision` 即 exit 2**——沉默不构成确认）· `rework`（**不进位**，超
  `max_rework_per_item` 挂阻塞）· `freeze`（只冻点名条目，绑定 file+sha256+round+decided_at）·
  `verify`（sha256 漂移→`invalidated`；原件被改→`original_modified`）· `make-gate`
  （制作前置门四项全过才 exit 0）· `block` · `terminate`（五类穷举，自造状态 exit 2）·
  `check-path`（两环目录越界校验）
- **`loop check-path` 实现 `loop_a.forbidden_paths` 与 `loop_a.scope` 写前校验**：
  Loop A 触碰用户课件目录 / 超出包内白名单 → exit 1；Loop B 触碰专家包目录或原件 → exit 1。
  此前治理文档 §8 第 3 项自认"非代码级强制"，本版起有代码背书
- **`scripts/test_loop_state.py`（新回归套件，33 例）**：锁死停等、部分冻结、sha256 失效、
  返修不进位、预算触顶、制作门、终止穷举、原件只读、两环越界
- **`references/loop-master-prompt.md`（新文档）**：原始设计任务交付物 #1——可粘贴到
  WorkBuddy 的专家团升级总控提示词（含判环/探针/九项/转换/诊断/检索/停等/冻结/制作/终止全链）
- `--max-rounds`：任务级轮次上限覆盖（dual-loop-governance 要求"提出为可确认参数"）

### Changed
- **`ensure_settings.py` 第 7 项扩为跑 `scripts/` 下全部 `test_*.py`**：此前只跑
  `test_harness.py`，v3.8.2 新增的 `test_fix_md_image_refs.py` 挂了体检完全看不见——
  第 7 项形同虚设。现逐个报码，任一失败即告警（9 套件实测约 44s）
- `ensure_settings.py` 脚本清单 17→18（+`test_loop_state.py`）；`SUB_WHITELIST` 加 `loop`
- `agents/vet-med-ppt-team-team-lead.md`：双 Loop 路由小节补 13 条 `harness.py loop` 命令表
- `references/dual-loop-governance.md`：§8 第 3/4 项改标 `[T]` 部分实测；§9 实测清单
  从"2/9 已跑"更新为"7/9 已跑"，并标注剩余两项（模板失败/渲染失败）需故障注入
- `references/round-review-sop.md`：§10 补 SOP 条款 ↔ `harness.py loop` 命令对照表

### 诚实边界（不虚报）
- `loop` 子命令**不是沙箱**：它拦不住成员绕开脚本直接写文件（平台无 hook），
  也不判定条目内容的专业对错（仍归成员与主理人）。仍**不得宣称"两环隔离已由代码完全强制"**
- 真实课件端到端全链**仍未实测**——状态机层面已 33 例背书，但"转换→诊断→多轮→冻结→
  制作→验收"在真课件上跑通仍需九项任务信息（受众/课时/模板/范围/验收标准）

---

## [v3.8.2] - 2026-10-22

### 概述（补齐悬空能力批：图片引用修复 + GEO-003 落地 + 接单九项清单）

来源：v3.8.1 的未验证项清单把三件事标为"协议要求但仓库没有"——
① SOP §2.1 要的"图片引用修复"无脚本；② GEO-003/API-001 长期"仅登记未实现"；
③ 真跑旧 PPT 所需的九项任务信息无处收集。本版逐项处置，**不再让协议悬空**。

### Added
- **`scripts/fix_md_image_refs.py`（新脚本）+ `test_fix_md_image_refs.py`（7 例回归）**：
  markitdown 悬空图片链接 → `_assets/` 实际路径。配对依据 **2026-10-22 实测**
  （markitdown 0.1.7 对 PPTX 输出 `<!-- Slide number: N -->` + `![原文件名](PictureN.jpg)`，
  target 指向不存在的文件）：页号+页内序号为主，磁盘文件存在时升级为 sha256 证据。
  未匹配项显式列 `missing_refs` + 行内 `REF-MISSING` 标记（原文本保留，**不留空链接/占位图**）；
  manifest 有而 md 未引用 → `orphan_assets`；可选 `--deck` 做三方计数核验。
  退出码 1 = 存在未决项（须人工处置），`--out == --md` 直接 exit 2（守原始转换结果只读留存）
- **`ooxml_lint.py` 新增 GeoChecker（GEO-003 落地）**：逐页取 `a:xfrm` 矩形（GROUP 按 chOff/chExt
  换算，顺带规避 GEO-002 误报），两两求交，重叠率 ≥ `--geo-threshold`（默认 15%）报 **WARN**。
  **只报 WARN 不报 ERROR**——教学课件存在有意叠放（文字压图），机器分不清设计与事故，
  判 ERROR 会一律阻断合法设计
- **`references/task-intake-checklist.md`（新文档）**：接单九项（受众/课时/模板/范围/验收标准
  为 A 类缺一即停；用途/交付/素材许可/禁止事项为 B 类制作前置门前补齐）+ 一次问完的追问话术
  + `loopB_state.json#intake` 落盘 schema；制作前置门追加硬检查：A 类 5 项必须 `confirmed`

### Changed
- `round-review-sop.md` §2.1 补脚本命令与实测依据；§3.3 把 GEO-003 标为已实现、API-001 标为保持人工项
- `ppt-producer.md` 实现状态标注同步（含新脚本跑法）
- `ooxml-compat.md` 检查码表：GEO-003 → 已实现；API-001 → 标注"结构性不可实现"并说明原因
- `dual-loop-governance.md` 未验证项表（第 1/2/9 项）与实测记录同步

### 本版不做的事（据实标注）
- **不给 `extract_assets.py` 加引用修复参数**——职责分离：extract 只抽资产，fix 只修引用
- **不实现 API-001 的 lint**：它是写入时行为，成品 PPTX 里没有"当初是否猜属性名"的痕迹，
  结构性不可检；防线仍在写入纪律（批量原子语义 + 首次属性名先查）
- GEO-001 / TXT-001 / TXT-002 / CTX-001 仍为人工项（需看渲染图或属语义判断）
- 不替用户填九项任务信息——**不得用仓库默认值冒充用户事实**

---

## [v3.8.1] - 2026-10-22

### 概述（双层 Loop 治理补完批）

来源：v3.8.0 把两环配置写进 `config/harness.yaml#loop_a/#loop_b` 后，仍缺一份回答
「怎么判环 / 授权怎么隔离 / 五条操作指令怎么敲」的治理文档——配置注释不等于可执行契约。
本版只补齐治理层，**不改动 v3.8.0 已确认的任何执行条款**。

### Added
- **`references/dual-loop-governance.md`（新文件）**：判环路由表；授权/状态/目录三不互通；
  Loop A 六步（只读探针→缺口清单→最小补丁→每批确认→实施→回归）；
  Loop B 五条操作指令（启动/继续/返修/恢复/制作）；七阶段契约表（输入/输出/责任人/权限/退出状态）；
  **未验证项清单（能力分级 [D]/[R]/[L]/[T]，含 extract_assets 无引用修复参数、ooxml_lint 仅登记未实现、
  Loop B 端到端未实测、任务信息九项缺失）**；本地最小实测清单（9 场景，跑通才算数）
- **主理人 MD 新增《双 Loop 路由》小节**：接单第一步先判环，判不出必须追问不猜；
  三条硬约束（授权不互通/状态不互通/目录不互通）落到主理人日常动作

### 本版不做的事
- 不重定义 Loop B 执行条款（转换层、条目字段、裁决语义、终止、终审仍以 `round-review-sop.md` 为唯一源）
- 不实现 `loop_a.forbidden_paths` 的代码级写前校验（仍是配置+文档契约，文档中已显式标注"非代码强制"）
- 不给 `extract_assets.py` 加引用修复参数（缺真实样本验证，先如实标注缺口）

---

## [v3.7.0] - 2026-10-17

### 概述（诊断颗粒度升级批：七维精准诊断 + 三级修复路由 + AI 融合教学维）

来源：用户对"任意兽医教学 PPT 精准诊断、分级修复、AI 时代教学升级"的能力要求，
叠加 v5-v7 三轮迭代中"诊断结论无法直接映射投入档位"的实操痛点。
本版确立**诊断-修复双路由**：诊断按七维细颗粒度量规（量规唯一源放下游 skill，本团消费不重定义），
修复按 大修/中修/细节修 三级（按侵入性），与既有 A/B/C 三轨（按手段）正交组合。

### Added
- **七维精准诊断**（量规唯一源：`teaching-ppt-studio/references/seven-dimension-rubric.md`）：
  ①知识准确性 ②教学结构与认知链 ③认知负荷 ④视觉与几何 ⑤学习动力与互动 ⑥评价与岗位对齐
  ⑦**AI 融合与数智素养**（新维：AI 示范/批判审查训练/边界教育/学生 AI 任务/讲师 AI 教学法）——
  每维 3-6 细检查项，标注 严重度×判定方式[机/人/机+人]×建议修复级；报告契约含基线与路由建议
- **三级修复路由**（主理人 MD#诊断-修复双路由）：大修（结构/骨架/准确性核心）/ 中修（页内重组）/
  细节修（元素微调）；总级取最高、条目按自身级；与三轨正交；路由是建议、用户裁决后开工
- **`config/domain_config.yaml#ai_literacy`**：维⑦配置化（I1-I5 清单 + 课型达标线 理论2/实训1/研讨1 + P2 语义）
- **WF-2 更新**：闸1 诊断入口改为七维诊断 + 修复级路由裁决
- 成员联动：pedagogy-architect 加 AI 元素检查（建议维提示）；verifier 加维⑦抽检（不阻断）

### Changed
- 下游 skill teaching-ppt-studio v2.5.0 → **v2.6.0**（Step 2 主诊断框架切至七维量规；
  三维/八维降为上位视角；新增 references/seven-dimension-rubric.md；核心红线加"诊断唯一执行源"条）

### 本版不做的事
- 不在本团内复制量规全文（防双源漂移——量规演进归 skill，专家团只引路径）
- 维⑦不设 P0/P1（AI 教学元素是增强项不是及格线，强制会催生形式主义）
- 不实现维⑦的机器扫描（保持 [人] 判定，防虚报覆盖率）

---

## [v3.6.0] - 2026-10-17

### 概述（三轮课件迭代实战治理批：迭代四原则扩为六原则）

来源：同一课件连续三轮迭代实战（v5 降密+数据时效核验 / v6 顺序重整+拆页+图表增补 / v7 病例图教学化+图注补齐，
累计 100+ 条批量写入、3 轮自引入缺陷回零、14 张图逐张识图判读）。本版不加新工具、不改流水线结构，
只把新踩的坑抽象为两条新原则与两个新病例，并给出机器背书与 verifier 抽检项。

### Added
- **迭代原则⑤：插入物避让**（`references/adjudication-rules.md`）：向既有页插入新元素前强制空间审计
  （逐形状枚举区间，重叠率 0%）；无空隙按序降级（单行短注→完整内容进备注→缩宿主框→挂账）；
  新元素文字规格**创建时即达合规**，禁"先插后调"。经验来源：v6 流程条 +8、v7 图注 +5 处自引入重叠，同类 2 次 → 规则化
- **迭代原则⑥：素材判读红线**（同文件）：图像类图注/讲稿只能写图像本体判读得出的内容——判读不出不得写、
  低清图降级"情境图"、来源缺失不编造、要素缺项显式挂账。经验来源：v7 病例图教学化中识图发现 5 张低清新闻图、
  1 张图无预设病变，若按"看标题写图注"惯例将与图像本体不符
- **`config/harness.yaml#delta_gate` 扩展**：`insert_spatial_audit` / `insert_font_at_creation` /
  `image_caption_requires_reading` / `caption_missing_element_policy=explicit_todo`（原则⑤⑥的机器背书段）
- **`config/visual-rules.yaml#caption_five_elements` 补充判据**：判读先行 / 来源诚实 / 缺项挂账 / 看图任务推荐形态
- **OOXML 病例 13–14**（`references/ooxml-compat.md`）：
  GEO-003 插入物与既有形状空间冲突（frequency=2 触发规则化）/
  API-001 写入属性名凭记忆猜测（原子批次整批回滚，异质操作须分批）
- **闸2 新增 3.3 素材判读前置**（`references/sop-stages.md`）：涉图像方案必须在设计期逐张判读本体，
  判读记录随蓝图交确认，禁止"方案先行、施工时再看图"
- **verifier 增量类抽检新项**（`agents/verifier.md`）：插入物空间审计复核 + 图像图注溯源抽验（人工项，lint 未实现已声明）

### Changed
- **迭代四原则 → 迭代六原则**：全文锚点同步（adjudication-rules / sop-stages ×3 / team-lead ×4）
- 成员 MD 注意事项追加：visual-slide-designer（避让 + 判读红线）、ppt-producer（原子批次语义 + 属性名核验 + @id 页内作用域）
- `version` → 3.6.0（harness.yaml / plugin.json）

### 本版不做的事
- 不把"识图工具名"写进规则（判据是"逐张判读本体"，工具可替换——防特化绑定）
- 不实现 GEO-003/API-001 的 lint（守反自评失真铁律，登记即声明未实现）
- 不回填 v3.5.0 遗留 lint 实现（另立任务）

---

## [v3.5.0] - 2026-10-17

### 概述（实战经验治理批：把一次多轮增补的教训抽象为通用判据）

来源：一次「旧课件按用户指令做三轮增补深化」的实战（v1 方案→v2 四课时版→v3 四方向深化，最终 97 页/可见 78）。
本版**不加新工具、不改流水线结构**，只把零散教训抽象为可复用原则并落到既有文件，
使同类任务（任何改造/增补/多轮迭代）不再重踩。

### Added
- **迭代四原则**（`references/adjudication-rules.md` 新节，主理人 MD 索引同步）：
  ① **骨架冻结**——课时划分/模块序列/叙事轨一经确认即冻结，改骨架须回退闸 2
  ② **方向裁决**——多方向先请用户按 强/中/弱 分档，按档投入，未裁决不开工
  ③ **增量门禁**——验收基准 = 自引入缺陷 0，存量挂账不阻断，禁只报绝对数
  ④ **检出 ≠ 判定**——机器 MISS 须规范化复核后才定性，未经复核不得升 P0
- **`config/harness.yaml#delta_gate`**：基线必填字段、block_on_new_defects、报告格式、miss_needs_human_review
- **`config/visual-rules.yaml`**：`density.max_body_chars_per_slide=150`（主框口径，与全页 400 并存）、`density.shrink_order`（降密固定顺序，调字号为最后手段）、`theme` 段（色令牌槽位结构，禁自创配色，值由工作区/源课件指纹提供）
- **OOXML 病例 8–12**（`references/ooxml-compat.md`）：GEO-001 图片单维尺寸失控 / TXT-001 表格文本取不到 / TXT-002 跨 run 整串匹配失效 / GEO-002 GROUP 子元素越界误报 / CTX-001 新增页标题缺失
  ⚠️ 五码**仅登记，ooxml_lint 未实现**，已在同一文件明示实现状态（反自评失真铁律）

### Changed
- **闸1**（sop-stages.md）：页数口径升级为**三口径**（物理/可见/导出）并给出导出页换算规则（隐藏页导致 PPTX 与 PDF 页码错位）；新增**重复指令对账协议**（重提同类指令先对账 已覆盖/部分/未覆盖，再给 A 验收/B 补强/C 换方向 三路径）
- **闸2**：新增**方案颗粒度四坐标**验收项（教学单元/学习目标/岗位能力/标准依据），清单式方案一律退回；新增方向裁决步骤
- **闸3**：新增骨架冻结、降密先行、批量幂等与断点续跑三条
- **闸4**：新增增量门禁与检出≠判定两条核对项
- **`references/batch-surgery-sop.md`**：新增 §2 降低信息密度（前置步骤）+ §7 幂等与断点续跑；原 §2–§5 顺延为 §3–§6
- **成员 MD 同步**：pedagogy-architect（颗粒度四坐标+方向表）、verifier（三口径+增量判定+MISS 复核）、ppt-producer（幂等四断言+增量基线）、visual-slide-designer（density 新键+主题令牌+按裁决强度投入）

### 本版不做的事
- 不改五闸结构与确认门数量（保持固定 2 次确认）
- 不改 verify_deck / ooxml_lint 脚本逻辑（新病例码为人工检查项，实现另开任务）
- 不动 cases_library 与 deck_registry

---

## [v3.8.0] - 2026-10-21

### 概述（双层 Loop 落地批 · Loop A 第 1–3 批 + 五协议条款整合）

来源：v3.8.0 双层 Loop 设计稿（Loop A 工程进化 + Loop B 旧课件优化）+ 用户下发的五份协议/条款
（运行约束、逐轮优化协议、四角色追加条款、官方规范对标）。本版**不改五道闸结构、不重造诊断量规**。

### Fixed（真实缺陷）

- **agent frontmatter 未闭合（🔴 双平台隐性缺陷）**：`verifier.md` 与 `vet-med-ppt-team-team-lead.md`
  全文只有开头一个 `---`、无终止符。WorkBuddy 平台解析器宽容故体检照过，但 Claude Code 官方规范
  规定 frontmatter 未闭合时按普通文档处理（name/description/maxTurns 全失效，极端情况跳过该 agent，
  **含主理人**）。已补闭合符，YAML 真解析验证通过
- **ensure_settings 第 12 项覆盖盲区**：该项只校验「CHANGELOG 声称的子命令是否都在 doctor 表中」，
  不校验版本号 —— 四处版本各说各话无人能发现。已增第 14 项四处一致性巡检
- **四处版本漂移**：`.claude-plugin/plugin.json` 停在 3.4.4、harness.py doctor 常量停在 v3.4.3、
  文件头 docstring 停在 v3.4.0（v3.5.0–v3.7.0 三版推进只改 `config/` 与 `references/`）。已四处对齐 3.7.0

### Added

- **第 14 项 `check_version_consistency`**：四处版本号互等（v 前缀归一），以 `.codebuddy-plugin` 为权威
- **第 15 项 `check_agent_frontmatter`**：agent frontmatter 闭合巡检，防未闭合复发（反向验证：删闭合符即告警）
- **`references/round-review-sop.md`（逐轮审阅 SOP）**：七种用户裁决语义（含「沉默不构成确认」）/ 每轮必展六项
  （缺任一项即本轮无效）/ 条目级 sha256 冻结与批准自动失效 / 五类终止状态 / 制作前置门 / 断线恢复最小集
- **`config/harness.yaml#loop_a`**：scope 白名单 4 段 + `forbidden_paths` 3 条绝对禁区（课件目录与 artifacts）
  + `patch_discipline: minimal` + 每批确认 + `regression_required` 三项
- **`config/harness.yaml#loop_b`**：状态文件与 `task_state.json` 并存不覆盖 + 单写者 team-lead +
  `round_review` 5 条 + budgets 五参数（含 `max_items_per_round: 5`）+ termination 五类
- **转换层与前置检查（SOP §2）**：MarkItDown 出 `_raw/original.md`（只读留存）+ `extract_assets.py` 出 `_assets/`
  + 图片引用修复 + **双源核验硬约束**（v3.2.0 实测 4 样本备注口径 2/4 不一致，单源不可作依据）
  + 渲染前置命令链（soffice → PDF → PNG），视觉诊断不得仅凭 Markdown
- **诊断条目字段规范（SOP §3.1）**：item_id/page_id/原文摘录/关联素材/诊断维度/严重度/判定方式/责任人八字段，
  缺任一项即不合格；Loop B 五维轻量口径与七维量规并存（量规唯一源仍在下游 skill，不复制全文）
- **制作后三项检查（SOP §3.3）**：打开 / 渲染 / 对象可编辑性分级；明示 ooxml_lint 的 GEO-003、API-001
  **仅登记未实现**，此类靠人工抽检并标注「lint 未实现」
- **终审验收清单（SOP §11）**：10 项逐项打勾，含「无法检查的写明原因，不得因看起来没问题写通过」
- **通道纪律（SOP §10.1）**：只有主理人可向用户提问与接收确认；成员不直接联系用户、不横向直连

### Changed（角色条款）

- **内容专家**：新增「联网检索循环」（检索→读原文→核对适用范围→必要时补查，记录检索式/通道/是否读到原文/
  适用范围判断/结论；**禁止以搜索摘要代替原文**）+ 证据冲突**并列不抹平**（转主理人裁决）
- **内容专家 + 验收员**：`[待核实]` 与 `[推测]` 双标记制（B3）——`[待核实]`=取不到原文的关键结论，
  **不得进入正式内容**；`[推测]`=基于证据的推断，可入但须物理分离。两者语义不同不得互相替代
- **教学法架构师**：旧课件教学逻辑/结构层次诊断须逐条对应问题条目（同页多问题须拆条），**禁止「整体优化」**
  代替具体修改项；三对齐硬要求（目标↔活动 / 活动↔评价 / 目标↔评价），只给结论不给对齐表视为不合格退回
- **视觉设计师**：配图建议五要素（保留/替换/新增 + 页面位置 + **图的教学作用** + **来源与许可核查** +
  清晰度是否足够教学判读）；找不到合适图时出**检索单**（检索词+候选来源+清晰度+图注要求）不填错误图
- **视觉设计师 + 验收员 + 制作师**：新增「制作后三项检查」（打开/渲染/对象可编辑性）与制作发现不一致
  **上报不自行修正**
- **验收员**：新增抽检项 —— AI 生成图冒充检查（命中判 **P0 阻断**）、许可核查、双标记分列、
  批准稿一致性（sha256 比对）、原件未改动核对
- **主理人**：frontmatter 闭合修复 + description 人数口径修正（「4 域成员+verifier」→「5 名成员」）

### Changed（唯一源联动）

`adjudication-rules.md#原则六`（素材判读红线唯一源）新增三条：**AI 生成图禁令**（医学图像不得用 AI 生成图
冒充真实病例/显微图，教学示意图须标「示意图（非真实病例）」）、许可核查要求、找不到图出检索单。
按该文件自身纪律（L37「凡兄弟资产有对应条目须同步」）已同步 `visual-slide-designer.md` 与 `verifier.md`。

### 本版不做的事

- 不重造诊断量规（量规唯一源仍在下游 skill teaching-ppt-studio，本团只引路径）
- 不改五道闸结构与门禁退出码语义
- 不实现 ooxml_lint 的 GEO-003/API-001 检出（登记即声明未实现，守反自评失真铁律）
- 不新增「图片引用修复」脚本能力（`extract_assets.py` 现无此参数，属独立任务）
- 不以 AI 生成图扫描为独立学术诚信基线任务（本次未扫盘，如需另立项）

---

## [v3.4.4] - 2026-10-15

### 概述（遗留收口：体检首全绿 + 双仓 push）

- **[13] 联邦同步**：2 包 vendor 跟升到 core 02a69d1f（P2-5 补丁版，401 行），VENDOR.json sha/lines/synced_at 三件套更新；防漂移测试 6/6×2 PASS
- **[8] 口径修复**：ensure_settings 第 8 项从"目录文件总数 >20"改为"备份模式文件 ≥3"（正则：括号数字后缀/副本/优化版/_v2/.bak），对齐告警名"备份膨胀"；消除"广东职业养禽与禽病防治 27 份/环境控制 21 份/粪便虫卵检查 23 份"等合法教学内容目录的误报；正则自测 12/12 PASS（6 应命中/6 不应命中）
- **team-lead MD 瘦身**：21.5KB → 13.9KB（目标 ≤14KB），任务包 schema+人设注入协议（约 4.3KB）外置到 `references/spawn-protocol.md`（一字不丢）；闸索引表/编排内核/三级路径/v3.4.2 采用闭环等节密实化
- **agents v3.4.0 补账**：6 个 agents MD v3.4.0/v3.3.1 演进入库（description 去版本化中文重写、dvm/verifier 五条铁律专版、verifier 三源抽检职责、v3.3.1 旁路版本检查节）——又一处双仓库漂移实证（L13）
- **release-sync**：v3.4.0-3.4.4 全部 7 个 commit 经开发仓 fast-forward push 到 origin（`c4f7106..77a83bc`），GitHub 仓库远端同步；上轮汇报中的"release-sync.sh 待推"为误判——脚本是安装态 git hook 提示器，真身已通过手工 git push 等价执行
- **plugin.json**：8 处 3.4.3 → 3.4.4
- **双仓拓扑确认**：origin/main 权威 = 开发仓链（含全部 v3.x tag）；安装态仓 remote origin 缓存陈旧（v3.2.0），但 v3.2.0 后是分叉不可 push，已 `git fetch` 刷新缓存到 v3.4.4 view
- **体检终态**：13 项 **全绿**（自 v3.2.0 建立 13 项体检以来首次 13/13 ✓），[8]/[10]/[11]/[13] 四个长期挂账项全清

### 本版不做的事

- 不动病例核验/cases_library（保持 v3.4.2 形态）
- 不动 deck_registry（保持 135/140 收编）
- 不重跑 stage 状态机（A6 仍挂起等下次真实课件任务走 5 闸）
- 不合并 6 个 v3.0.0 时代的 TaskList 僵尸（#16-21），改记 lessons L13 案例保留为版本治理回溯参考

---

## [v3.4.3] - 2026-10-15

### 概述（采用迁移批：机制 94% → 拉采用率）

五维独立诊断的定性是"工程完工 vs 实际采用脱节（94% vs 68%）"，本版**不加新机制**，四个裁决点经用户拍板后执行：稳健核心 10 项 + 模板按频次补登 + 挂账无风险部分；stage 强制采用挂起等下次真实任务。

### Added
- **`harness.py verify-ref --online / --write-back`**：PubMed esearch 联网核验 + 受控写回（静态门禁→.bak 备份→写回→复检，net_err>0 拒写）——消除上一版"脚本直写绕过预检"的旁路；全链路实测 hit=1/拒绝门禁生效
- **`ensure_settings.py` 第 13 项联邦 shim 巡检**：各包 shim 声明版本一致性 + vendor sha256 比对（上线当日即抓到跨会话改 core 未同步 vendor 的漂移）
- **`harness eval` 周期化**：WorkBuddy automation 每周一 08:30 自动跑（首跑归档 outputs/harness-ab/eval_weekly/）

### Changed
- **trace log 死值源堵死**：`--event` 漏写或传 "event" 一律 exit 2（上一版只清了已生数据，默认值未堵）
- **联邦 shim 全对齐 P0-1**：research-orchestration-team + triz-invention-team 60 行 R9 → 102 行（vendor 兜底 + 防漂移测试 6/6 PASS），shared-core README 勘误（"45 行"→分档版本表）
- **template_registry 4 → 26 指纹**：活跃口径按频次补登，96 份活跃 deck 覆盖 35.4%→90.6%；顺带修 theme_fingerprint.batch_report 混入快照副本的口径缺陷（238→96）
- **挂账 [10]/[11] 转绿**：harness.yaml snapshot.max_mb 对齐"基线永久"决策（500→6000，未删快照）；2 份旁路版本副本移 _trash_ 区（zip 双保险）；ensure_settings 快照上限改读 yaml 去硬编码
- **lessons.md L12-L15**：虚假完成复利损耗 / 双仓库同步缺口（安装态 git 落后三个版本的教训与双仓同批 commit 纪律）/ 零采用四分类口径 / CHANGELOG 密度红线（单条版本号提及 ≤3 次）

### 验证
- A1 三场景 + A2 全链路（含拒绝门禁）+ test_vendor_core 6/6×2 包 + test_harness 15/15 全过
- ensure_settings 13 项：11 ✓（[10]/[11] 新转绿）、[8] 目录整理按裁决另开战线、[13] ⚠ 为并行会话 P2-5 改 core 未同步 vendor 的真实漂移（待其收敛后消化）

---

## [v3.4.2] - 2026-10-15

### 概述（专家团全面诊断 P0-P3 全量执行日）

五维诊断（专业能力🔴/协作🟡/决策🟡/资源🟡/沟通🟡）后，用户指令"全部按默认、不留死角"——P0-P3 共 14 项一次性全量落地。**核心：机制建成 → 资产层落地 → 工具采用闭环**——sweep 收回 135 份课件、56 条病例全量联网核验、文档-实现一致性机器体检、联邦层 git 化。

### Added
- **`harness.py sweep`（P0-1 落地）**：v3.1.0 CHANGELOG 声称的"闸外收编"能力于 v3.4.2 真正落地——递归扫全量 .pptx → SSOT 门禁 → 收编 deck_registry（judge_provenance 保留）。**实测 140 份 → 收编 135 份 → P0 阻断 137 份**（99.9s）。`v3.1.0 CHANGELOG` 同条目补勘误
- **`harness.py verify-ref`（P0-3）**：cases_library.json 文献引用预检——假 PMID 黑名单（12345/00000/99999/11111/012345）+ 缺 verified_at 时间戳红线 + PMID/DOI 格式预检。**已修 3 条假 PMID 为 unverified**
- **`harness.py eval`（P3-3）**：自动化演进环——基线 vs 当前 sweep diff（P0_total/P1_total/P0_blocked_decks/sweep_errors 增减）；产物 eval_diff.json。**首跑 elapsed 99.9s → 80.9s（-19s）**
- **`shared-core/check_viral_evo_merge.py`（P3-2）**：自动列出 viral-evo-lab 定制版与共享公共段 diff（裁头后 206 增/67 删），供维护者评估合并
- **`ensure_settings.py` 第 12 项 `check_doc_implementation_drift()`（P2-4）**：CHANGELOG 声称子命令 vs `harness.py doctor` 实际注册表交叉核验——7/7 一致（v3.1.0 sweep 虚构类问题未来自动被逮）
- **`references/iron-rules.md`（P1-3）**：承接 v3.4.0 五条铁律 + v3.4.2 工具采用闭环的完整正文；team-lead MD 由 22.9KB 收 21.5KB（仍超 14KB 目标，下一轮继续）
- **联邦层 git 仓库（my-experts/plugins/.git，P3-1）**：6 专家包 + shared-core + TEAMS_INDEX 初始提交 9994f4b

### Changed
- **trace report 增 token 汇总（P1-4）**：`tokens_by_actor` + `tokens_total` + `budget_usage`（spawn_used/spawn_max/spawn_pct/react_max）
- **team-lead MD 加 v3.4.2 工具采用闭环节**（P1-1/P1-2）：7 步动作序列每闸必跑，绑定 harness/trace/stage/spawn 调用；成员回传与降级必须落 trace
- **课程工作区**：trash 1.2G 处置（P2-1）→ 整目录转入 `.workbuddy/_trash_20261015_frozen_20261015/`（脱离后悔期）+ 备份 zip 留在工作区根；.snapshots 95 份 baseline 永久快照（P2-3，5.6G 突破 500M 上限但 milestone tag 永久保留——harness.yaml 已加注释解释）
- **cases_library 56/56 全量核验（P0-2 两批）**：M8A1+M4A2/M4A3/M4A4 第一批 17 条 + M4B/M4C/M4D/M5A/M5C/M6A/M7B 第二批 39 条，**全部通过 PubMed esearch 联网取真 PMID + verified_at 时间戳**。fake_unverified 3 条（原 PMID:12345 假引用）已 unverified
- **deck_registry 4/108 → 135/140（P0-1）**：覆盖率 3.7%→96.4%（+92.7 pp）；P0_blocked_decks 3→137；sweep_errors=0
- **template_registry 1 → 5（P2-2）**：高频指纹批量 register（majority-v1-a97ffad5 + A/C/D/E 系 v342），覆盖 80+ 课件
- **版本统一 v3.4.2**：harness.yaml 3.4.1→3.4.2；四份 plugin.json 3.4.1→3.4.2

### 事实修正（如实挂账）
- 诊断原报告"v3.4.1 时 team-lead 21KB→目标 ≤14KB"——实际仅收 22.9KB→21.5KB（差 0.5KB），**14KB 目标未达**，因 P1-1 工具采用闭环新增 7 步动作序列、v3.4.2 多处接入索引表格，整体 MD 仍长；下一轮需进一步外置（建议：adjudication-rules.md#六项自检、四门清单外置 references/）
- P2-3 .snapshots 突破 500M 上限未通过 GC 收敛（milestone 永久保留是设计预期，harness.yaml 已加注释解释）——如工作区磁盘受限，可手动调高 max_mb 或关闭 milestone_tags_permanent
- P1-3 MD 瘦身二轮目标"主理人负载降 1/3"未达——team-lead 21.5KB / 7 成员总 MD 73KB；pedagogy 15.5KB / dvm 13.5KB 附录外置评估未做（v3.4.2+ 安排）

### 验证
- test_harness.py **15/15 通过**（v3.4.1 基础 + 2 例 stage 边界，无回归）
- ensure_settings **12/12 全跑**（1-7 全绿，8/10/11 既有挂账无回归，**12/12 ✓** 文档-实现一致）
- harness.py doctor **15 命令**（新增 verify-ref/sweep/eval 三个）
- sweep 收编 135/140 课件（96.4% 覆盖率）
- verify-ref 56/56 病例全过（0 fake/0 stale_ok/0 suspicious/0 format_err）
- eval 演进环首跑 elapsed 99.9s→80.9s（-19s 优化）

### 已知遗留
- v3.4.2 仅在本工作区 + 联邦层两个 git 仓库落地；viral-evo-lab 定制版与公共段 diff 由 P3-2 工具检测，**待维护者评估是否合并**
- ensure_settings 8/10/11 告警为持续挂账（活跃目录文件数/快照超容/旁路版本）——均属"按设计预期"，需用户在工作区侧处置
- team-lead 21.5KB 仍超 14KB 目标 53%——v3.4.3 安排二轮外置（adjudication-rules.md 节）

---

## [v3.4.1] - 2026-10-14

### 概述（v3.4.0 待办收尾：stage 计时入口 + description 历史补账 + shared-core 第一批）

v3.4.0 重构收尾时挂账的 4 项待办（R4b/R10/R11/R9）全部落地。另修复两处历史欠账：
plugin.json 四份停在 v3.2.0（v3.3.0→v3.4.0 三轮未升，属 v1.6.0 doctor 第 2 项要防的清单漂移）；
repo-meta/CHANGELOG.md 缺 v3.2.0 条目。

### Added
- **`harness.py stage` 子命令（R11）**：`--action enter|exit --stage 0-4 [--task-id] [--note]`，写 trace event=`stage_enter`/`stage_exit`（detail 含 stage/stage_name/task_id/note，stage_name 从 harness.yaml#stages 读）。**孤儿 exit 防护**：同 stage 无未闭合 enter 时 stderr 警告（防 stage_seconds 静默丢失）。与 `state set --stage` 分工：state 管持久状态，stage 管执行轨迹
- **`shared-core/` 联邦共享方法库（R9 第一批）**：安装态唯一真源 `plugins/shared-core/assemble_spawn_prompt.py`（公共版 369 行 + 归属声明）；4 个 md5 同构包（vet-med/research-orchestration/smart-textbook/triz）的 `scripts/assemble_spawn_prompt.py` 改为 45 行兼容 shim（向上查找 core 最多 4 层，EXPERT_DIR 显式传专家包根）；viral-evo-lab 定制版头部加来源声明（公共版 + V1 增量 105 行，独立维护）；`shared-core/README.md` 维护纪律 + 验证基线
- **回归测试 +2 例**：stage enter/exit 配对写入 stage_seconds；stage 边界（stage=9 拒绝 exit 2、孤儿 exit 有警告）

### Changed
- **6 个 agent MD description 去版本化补齐（R4b+R10）**：pedagogy-architect / visual-slide-designer / ppt-producer 三成员改为中文意图描述（角色定位+何时用+工具前提+边界），v1.x/v2.x/v3.x 升级历史补入 CHANGELOG §Description 去版本化历史承接
- **team-lead.md 编排循环接入 stage 事件**：「每闸」指令改为 `state set --stage N`（持久）+ `stage --action enter/exit`（计时）双写；顺带修复两处文档漂移（四道闸表补闸4.5 行；"只认 0-3"改"只认 0-4"，与 state 代码及 harness.yaml 对齐）
- **版本统一 v3.4.1**：harness.yaml 3.3.1→3.4.1；四份 plugin.json 3.2.0→3.4.1（此前三轮未升）；repo-meta/CHANGELOG.md 同步补齐
- **TEAMS_INDEX.md**：§2 增 shared-core 资产行；§4 C1 第一批落地记录

### §事实修正（计划 vs 实证）
诊断报告原计划"snapshot/lint/ensure_settings 三件套下沉"——实测 **snapshot.py / ooxml_lint.py / ensure_settings.py 均为 vet-med 独有**（其余 5 包无同构件），真正同构的是 assemble_spawn_prompt.py（4 包 md5 完全一致）。下沉门槛改为"≥2 包同构实证"，不预设名单；第二批候选待评估。

### 验证
- shim 替换前后 4 包 `--list-members` md5 逐一比对一致（8b5f17b4/6b362e8d/22468161/77118fcd）；shim vs core 直跑等价（--member dvm-content-expert 全文 md5 7867ed25 一致）；非法成员 exit=2 透传正常
- viral-evo-lab 定制版注释后 --list-members md5 不变（dddb79e9）
- `test_harness.py` **15/15 通过**（原 13 + stage 2 新例）
- stage 实测：enter→exit→report 链路 stage_seconds={"1":[1.0]}、status=ok（此前恒空字典）

### 已知遗留（如实挂账）
- shared-core 在 git 仓库结构下仅 vet-med 可用（其余 3 包 shim 会 exit 3 + 指引；安装态不受影响）；plugins 联邦层无 git 仓库，shared-core 版本历史依赖 vet-med 仓库副本 + CHANGELOG 人工记录——新建联邦 git 仓库列为后续治理项（P3，未承诺）
- viral-evo-lab 定制版与公共版的跟进合并无自动机制，靠头部声明的同步纪律人工执行

---

## [v3.4.0] - 2026-10-14

### 概述（第五轮：harness 可观测性补全 + 反幻觉五条铁律 + description 去版本化）

基于真实任务运行结果的九维度诊断（路由🟠 / 可观测性🔴 两严重差距）驱动重构。核心动作：harness.py 从"能跑"到"可诊断可发现"；成员提示词沉淀反幻觉五条铁律；6 个 agent MD 的 description 字段去版本化（升级历史归本文件，description 只放"何时用+工具前提+边界"）。**被删除的 description 版本历史在此承接**（下文 §Description 去版本化历史承接）。

### Added
- **`harness.py doctor` 子命令（R1）**：LLM 友好可发现性表——11 个命令的 JSON（name/purpose/required/optional/exit/example）+ exit_codes 字典 + global_options。直接动因：实测中 3 处参数错位（preflight 不接 `--expert-dir` / route 必接 `--level` / state 不接 `--task-id`）全是"无发现机制"撞出来的
- **`harness.py spawn` 子命令（R5）**：`--agent/--task-id/--stage/--input-bytes/--output-bytes`，写 trace event=`agent_spawn`，detail 含 `approx_tokens = (input+output)/4`——平台不暴露成员 token 用量，改为显式记录近似值，不以估算冒充实测
- **`TEAMS_TOPOLOGY.md`（R7）**：6 成员拓扑图 + 5 闸表 + "我不做什么"边界矩阵 + 工具白名单唯一源 + 五条铁律

### Changed
- **`harness.py cmd_budget` 修复（R2）**：kind=None 时原返回 `used=0 limit=0 exceeded=true`（`limit_map.get(None,"")` → `b.get("",0)=0` → `0>=0=True` 误阻断）→ 改为 `exceeded:false` + hint"指定 --kind spawn|react|rework" + exit 2
- **`harness.py cmd_trace.report` 增强（R3）**：新增 `dead_event_count`/`dead_event_hint`（event='event' 死值检测）/`missing_actors`（expected_actors − seen）/`missing_actors_hint`/`stage_seconds_status`（空时标"未启用 stage 追踪"而非静默空字段）
- **6 个 agent MD description 去版本化（R4b+R10）**：统一中文意图描述（角色定位+何时用+工具前提+边界），displayName/profession 双语保留。涉及：team-lead / dvm-content-expert / verifier / pedagogy-architect / visual-slide-designer / ppt-producer
- **3 个 agent MD 新增 v3.4.0 硬约束专版**：dvm-content-expert（PMID/DOI 必带+核验通过定义+病例优先复用+路径显式+register 不手写 JSON）、verifier（复算证据+禁虚假通过判决+判决可追溯+路径显式+只写报告）、team-lead（五条铁律总版）；verifier 另加"旁路版本检查"节（闸4 扫 `_v[0-9]|副本|优化版|\([0-9]\)` 命名）

### §Description 去版本化历史承接（原 description 内联版本记录，2026-10-14 迁入本文件）
- **苏学法 pedagogy-architect**：v3.2.0-batch4 case-driven teaching——设计模块时经 `case_extract.py find --disease <模块>` 查询 cases_library.json 对齐互动节点与量规（五案例制式：案例1-3 普通/案例4 中等/案例5 最高，CLAUDE.md §4 v2 spec 约束默认）；v3.3.0 跨 domain 适配——domain 由 config/domain_config.yaml 抽离（animal-medicine/microbiology/pet/tcm-vet），`assemble_spawn_prompt.py` 注入 domain 上下文，教学设计原则不变
- **郅作基 ppt-producer**：v3.2.0 batch pipeline awareness——与 extract_assets.py（资产化）/ooxml_lint.py（兼容检查）/snapshot.py（回滚）/theme_fingerprint.py+template_migrate.py（模板对齐）/case_extract.py（案例台账）/harness.py gate+template-audit（裁判调用）协同；v3.3.0 五闸扩展——闸4.5 三源核验（`verify_deck.py --three-source-check`）为交付前最后一道闸，domain_config.yaml 抽离后 pipeline 跨 domain 通用
- **屠明熙 visual-slide-designer**：description 无内联版本号；v1.9.0 转型（逐页设计师→规则引擎架构师）/v2.0.0 加挂批量版面外科/v3.0.0 职责收窄的完整演进记录保留在各 MD 正文"转型依据"节

### 验证
- 同任务重跑 diff：参数错位 3→0、trace 报告事件 13→17、回归测试 51 passed/2 skipped 不变
- `ensure_settings.py` 11 项全绿；`doctor` 11 命令实测可发现

### 已知遗留（如实挂账）
- stage_enter/stage-exit 事件尚未接入主理人编排循环（trace report 的 stage_seconds 字段仍为空标"未启用"）——v3.4.1 待办
- shared-core 共享方法库抽离未启动（snapshot/lint/ensure_settings 三件套仍各包一份）——v3.4.1 待办，按诊断 Q6 裁决分批执行

---

## [v3.3.1] - 2026-10-14

### 概述（治理批：备份文件治理 + 中间产物资产化 + 联邦总线，深度诊断报告方案全默认执行）

应用户三大痛点诊断（备份膨胀 / 中间产物干扰 / 专家团缺治理层）执行治理批。核心：**快照机制从"建而未启"到真启用**；写回纪律成文；三区分离落地；联邦层总线建立。

### Added
- **`config/harness.yaml` `snapshot:` 段**：enabled:true / max_mb:500 / keep:3 / auto_snap_on_writeback:true / milestone_tags_permanent:true / first_snap_targets:"194"——此前 snapshot.py 已存在但配置缺位形同虚设（建而未启）
- **写回纪律条款（各成员 MD）**：唯一活跃版（禁 `_v2_v3`/`优化版`/`副本` 旁路文件）+ 写前 snap + 原始件双轨；旁路文件=违纪
- **`ensure_settings.py` 第 11 项 `check_bypass_versions()`**：扫工作区一级目录旁路版本文件（`(_v\d|副本|优化版|\(\d\))\.(pptx?|ppt)$`），命中 return 1 挂账。**首跑即逮 5 个违纪**（3 个 AI 优化版移 trash，2 个 newcastle 用户手工副本保留）
- **`TEAMS_INDEX.md`（联邦总线，新建）**：6 包清单表 / 核心资产索引（cases_library 跨包引用）/ 产出物登记 / 演进路线 / 通讯约定
- **`virus-evolution-researcher/DEPRECATED.md`**：继任者 viral-evo-lab，保留 9 个调试接口定义，观察 1 个月后归档
- **课程工作区 `.workbuddy/memory/lessons.md`**：8 条首批经验沉淀（L1-L8）
- **课程工作区 `.workbuddy/三区治理README.md`**：scratch（TTL 7天）/ artifacts（有价值中间产物）/ archive（冷数据）三区定义与写入纪律
- **课程工作区 `.workbuddy/scratch/` + `.workbuddy/artifacts/batch1_extract_manifests_20261014/`**（4 份 manifest 留存）
- **课程工作区 `_trash_20261015/`**（1.2G）：35 个 v75 清单文件 + 2 autofix + 280M sample_extract + 3 旁路版 + 处置说明，保留至 10-22（7 天后悔期）

### Changed
- **快照库实建 5 份 baseline**：消毒剂双版 / 鉴别诊疗 / M03 / 鸭疫（各 194 目标对象）
- **harness.yaml version 3.0.0→3.3.1**

### 验证
- 回归测试 51 passed / 2 skipped
- ensure_settings 安装态首跑：11 项中 10 绿 + 1 项旁路版本检查挂账（预期内，5 违纪已处置）

---

## [v3.3.0] - 2026-10-14

### 概述（Release：Batch 5 五闸扩展 + domain_config 抽离 + 跨学科打样 + git 瘦身收口）

### Added
- **五闸扩展**：闸4.5 三源核验（`verify_deck.py --three-source-check`）作为交付前最后一道闸
- **`config/domain_config.yaml`**：domain 抽离（animal-medicine/microbiology/pet/tcm-vet），pipeline 跨 domain 通用
- **跨学科打样**：动物医学工作区作为"测试样本 A"显式声明
- **`harness.py verify-artifact` / `verify-envelope` / `template-audit`**：产物落盘校验 / 回传信封六字段校验 / 模板审计

### Changed
- **git 瘦身**：本地仓库 6.1M→2.9M、远程 3.8M、zip 清零（ annotated tag v3.3.0 指向 a3db65b，克隆实测确认）
- **5 闸状态机**：stage 0-4 整数（闸1 冻结→闸2 设计→闸3 成稿→闸4 交付→闸4.5 三源核验），双轨期兼容
- **8 项 budgets 护栏**：max_member_spawns=8 / max_react_rounds=15 / max_rework=2 / max_stage_minutes=20 / max_artifact_bytes=60000
- **6 退出码语义**：0=通过 / 1=P0阻断 / 2=用法错误 / 3=依赖缺失 / 4=运行错误 / 5=三源未达标

---

## [v3.2.0] - 2026-10-14

### 概述（第四轮：v4 通用化战略级纠偏 + WF-2R 旧课件诊疗流水线基础）

应用户战略级纠偏——**项目是测试和迭代的试验地，不是产品归属**。本批完成 4 项通用化修订 + v3.2.0 升版 + Batch 1 资产化 + Batch 2 兼容性 lint 与快照治理。动物医学工作区作为"测试样本 A"被显式声明，未来可换测试样本 B（猪病）/C（宠物）/D（水产）/任何学科；产品目标 = 通用教学 PPT 诊断与设计专家团。

### Added
- **`scripts/extract_assets.py`**（Batch 1）：S1 资产化转换层，8 类形状分流（PICTURE/CHART/TABLE/MEDIA/OLE/GROUP/SMARTART/TEXT），生成 `<课件>_assets/manifest.json`（六字段 + 7 派生）
- **`scripts/ooxml_lint.py`**（Batch 2）：OOXML 兼容性检查器，6 组检查码（PKG/REL/CT/ID/XML/SYN），ERROR 阻断 + WARN 明示；支持 baseline 对照 + 强模式
- **`scripts/snapshot.py`**（Batch 2）：快照库，K=3+里程碑+500MB+LRU 治理，sha256 去重；支持 snap/list/rollback/gc/status 子命令
- **`references/ooxml-compat.md`**（Batch 2）：D11 防线病例库，初始 7 病例（PKG001 删页残留 / deepcopy 重复 rels / 悬空 rId / CT 漏登记 / ID 冲突 / 非法字符 / md5 复核）
- **`references/extract_assets_usage.md`**（Batch 1）+ **`references/snapshot_usage.md`**（Batch 2）：8 节人读手册
- **`scripts/test_extract_assets.py`**（Batch 1，8 例 + 4 subtest）+ **`scripts/test_ooxml_lint.py`**（Batch 2，10 例 + 4 subtest）+ **`scripts/test_snapshot.py`**（Batch 2，6 例）：回归测试
- **`ensure_settings.py` +3 项治理自检**（D12 备份膨胀）：活跃目录文件数 / scratch 超期 / 快照库超容；7→10 项

### Changed
- **`.claude-plugin/plugin.json` + `.codebuddy-plugin/plugin.json`**：version 3.1.0→3.2.0；description 去 `veterinary medicine` 改 `domain-portable`；通用化声明
- **`harness.py cmd_gate`**：lint 前置集成（ERROR→exit 1 阻断）+ snapshot 写回前自动打点（`--no-snap` 可跳）
- **`ensure_settings.py`**：7 项→10 项，+3 项治理自检（D12）；脚本清单 7 个→10 个（+extract_assets/ooxml_lint/snapshot）

### Discipline
- **D11 修复对话框**（用户实锤痛点）：ooxml_lint 四层防线（lint/基线/纪律/病例库）
- **D12 备份膨胀**（用户实锤痛点）：snapshot.py + 治理自检 + 一原一活模型
- **v4 通用化**：项目层与常驻用户层解耦；样本可换；agent ID 命名巧合保留；description 改通用
- **陈述真实性律**：4 份挂账样本 lint 全 0 ERROR = 实证"用户痛点不是普遍"事实修正（XML-003 a:t 空格 WARN 15+8+6+2=31 次，与学科无关）

### Batch 状态
- Batch 1 ✅ 完成（2026-10-14 上午）
- Batch 2 ✅ 完成（2026-10-14 上午）
- Batch 3-5 待确认后实施

---

## [v3.1.0] - 2026-10-14

### 概述（第三轮：闸外防护 + 用户五条纪律 + 状态自愈）

v3.0.0 发布后 10 天的真实使用数据（trace/state/registry 全空、10-13 大清理把状态层抹掉）暴露一个根本性缺口：v3.0.0 修的是"被调用时的行为"，**没有任何机制保证"它被调用"**。v3.1.0 不再只盯闸内，**给闸外也装上钩子**：闸外产物能事后收编、状态基础设施缺失时专家团能自愈、用户五条工程纪律入各角色提示词。

### Added
- **`harness.py sweep`（P0-1 闸外收编）**：扫描工作区全 .pptx，逐份跑 SSOT 门禁，从课件现状重建 `deck_registry.json`（**不依赖任何 checkpoint**），含 `judge_provenance`（SSOT/版本/3.1.0/课时口径来源 csv 或 default）与 `disposition` 字段（verifier 挂账审判落点）。课时口径支持 CSV 显式声明（阶段1 冻结值），绝不按页数反推
- **`preflight` 环境自愈提示（P0-3）**：检测工作区 `.workbuddy/` 三件套（task_state/deck_registry/trace）状态，缺失则报 `degraded_env` 并给一行重建指引（state init / sweep）。实测 10-13 实例：环境被外部清理时专家团此前毫无感知，现在报"环境缺失但冷启动合法"
- **`harness.py gate --dry-run`**：verifier 只读边界——不写 JSON、trace 仍记

### Changed
- **6 个 agent MD 全部纳入用户五条工程纪律**（v3.1.0，2026-10-14）：
  - **陈述真实性律**（主理人 MD + verifier 抽样复核）——反幻觉/不虚报完成/陈述可核查/数字与历史一致；反面教材：2026-10-13 的清理清单"39 隔离候选"实际只移走 2、且丢失 2 个原始目录未在清单外披露
  - **一图一 ipynb**（屠明熙主责）——图与代码必须绑定，先改代码再出图
  - **输入输出路径标明**（屠明熙主责）——绝对路径，输出 pdf 格式
  - **文件治理律**（主理人 MD）——优先改旧非必要不新建；清理只能产清单，动手必须用户圈定；清单与实际一致
  - **CLAUDE.md 索引同步**（主理人 MD 文件治理子条款）
- 成员回传 schema 增 `self_check`（一句话自述本回传最可能不实的点，verifier 定向核查）

### Fixed
- `verify_deck.py` 写 JSON 前 `os.makedirs(..., exist_ok=True)`——根因：冷启动时 `.workbuddy/` 不存在导致所有 JSON 报告失败，sweep 测试中逮住
- `sweep` 预创建 `.workbuddy/`，与上一条配套

### 验证
- `test_harness.py` **16/16 通过**（v3.0.0 13/13 + 3 条新：sweep 重建台账 / preflight 环境报告 / gate --dry-run 不写盘）
- 安装态 `ensure_settings.py` **7/7 全绿**（6 agent / 7 脚本 / 唯一裁判 / 回归自跑 / 版本一致）
- 端到端：M4A1 实测 `sweep` 4 份课件 3 秒收编；P0 总 62，3 份被阻断（其中"禽流感病毒全链攻防术" P0=34 + 备注 0%——正是闸外未受护约束生产）

### 已知遗留
- 36 份历史 `deck_registry` 已无 checkpoint 可继承（10-13 清理抹掉），`sweep` 是新基线
- 14 份旧课件 P0>0 的挂账审判仍待 verifier 在闸4 首次运行时批量清偿（`sweep` 已输出 `P0_blocked_list`，verifier 直接据表行事）
- `overlay_injection` 四键（min_font_pt/require_empty_slot/max_overlap_ratio/sample_review_ratio）**仍零脚本消费**——R18 事故的对症药，下一版
- token/成本仍不可观测（平台不向主理人暴露成员用量），不以估算冒充

---

## [v3.0.0] - 2026-10-04

### 概述（第二轮组织诊断落地：唯一裁判 + 独立验证 + 四道闸）

管家节点裁决四项全部执行：① 郅作基降级为按需调用（职责保留）② 新增按需验证者 ③ 门禁归一（非权威版降级不删）④ P2 覆盖率计入机器草稿但单独统计占比并明示。

本轮先修**致命问题**（安装态门禁不可执行、同一批课件两个结论），再改组织（角色/流程），最后补机制（信封校验、护栏下沉）。

### Fixed（三个致命问题，均由本轮实测逮住）
- **安装态机器裁判断链**：整仓克隆导致根级 `scripts/` 只剩 1 个文件，6 个核心脚本（verify_deck/harness/surgery_deck/inject_notes/ensure_settings/test_harness）缺失 → MD 里的门禁命令必然 FileNotFoundError。已补齐并加第 5 项体检（全脚本完整性）
- **唯一裁判缺失（B0）**：门禁语义曾有**三处各自独立的定义**——专家包 `verify_deck.py`（724 行，分级门禁）、工作区 `.claude/skills/vet-ppt-pipeline/verify_deck.py`（375 行，**无 `--level`**，被台账引为权威）、工作区 `registry_rebuild.py`（私自定义 `P0_KEYS` 排除"课时不达标"）。同一批 36 份课件得出 P0=15 与 P0=0 两个结论。
  实测追查定案：**真因是课时口径而非 P0 定义**——非权威版用 `--auto-hours` 按可见页数反推课时，故永远"匹配"；权威版要求显式 `--hours`。修法：宣布专家包版为 SSOT、非权威版降级为"非门禁工具"（加显著横幅 + 运行告警，不删）、`registry_rebuild.py` 改为只读 yaml、台账新增 `judge_provenance` 与 `caliber_warning`
- **`--hours` 由默认值改为必填**：原默认 3 会凭空判出"课时不达标"（B0 口径混乱源头之一）
- 顺带：台账 md5/mtime 快照全部失效（36/36）→ 重建后刷新；`gate_cmd`/`ssot` 字段改指 SSOT

### Added
- **`agents/verifier.md`（都衡言，独立验证官）**：承接此前完全缺失的 V 层。依据是硬证据——**自评失真在 v1.5.1→v2.2.0 四个版本全部复发，跨 11 天一次没修好**（每轮修的是规则文本，不是产生自评的机制）。职责：自己重跑门禁复算（不采信任何自报）、裁判口径变更第二签、P0 挂账逐条审判（修/降级/例外签字）、抽页 ≥20%
- **`harness.py verify-envelope`**：把 `result_envelope` 从文档约定变成代码校验（六字段齐备 + status 合法 + 产物路径交叉核验）
- **`avatars/verifier.png`**
- 回归测试从 10 → **13 例**（新增信封校验、judge 溯源字段、`--hours` 必填、机器草稿占比）

### Changed
- **流程：六阶段（0–5）→ 四道闸（0–3）**，确认门由"最少 2 最多 6"降为**固定 2 次**（设计确认 + 交付终审）。依据：实测 1 课时任务跑到阶段3 已耗 25 分钟；`stage_history` 75% 是 SOP 外非法值、`current_stage` 合法率 0/4
- **角色**：郅作基职责一条未删但**不再常驻 spawn**（判据落点是 `harness.yaml#routing` 的默认 spawn 计划，不是角色存废；取证明确反对删除 M 级职责）；屠明熙职责收窄（红线参数与外科判据文本迁出，人只做高价值页设计与抽样裁决）；**二者不得合并**（Maker/Checker 对偶是 R18 防线）
- **P2 覆盖率口径（裁决④）**：机器草稿**计入**覆盖率，但门禁单独输出 `machine_note_ratio`，终检清单要求交付物明示"其中 m 页为 AI 草稿，待教师复核"。依据：`inject_notes.py` 的 bootstrap 会批量生成讲稿，不统计就等于把没人复核的机器文本算作达标
- **`ensure_settings.py` 4 项 → 7 项**：新增全脚本完整性、唯一裁判检测（包内同名 `verify_deck.py` 只许 1 份）、回归测试自跑
- **护栏下沉**：`verify_deck.py` 开始真正消费 `config/visual-rules.yaml#severity`（此前 `registry_rebuild.py` 私自定义同名常量）
- 规则去重：agents 内门禁规则定义收敛为**唯一定义源** `references/harness-engine.md#6`（其余改为引用）

### 平台铁律备忘（写进来避免下轮重犯）
⚠️ **WorkBuddy 专家包不支持 agent frontmatter 的 `tools:` 字段**（2026-09-30 实测确认，v2.2.0 的白名单方案已回退）。
最小权限只能靠：① `assemble_spawn_prompt.py` 确定性注入人设 ② 任务包四要素约束 ③ `harness.yaml#members[*].tools_whitelist` 作为编排意图声明。

### 已知遗留（如实挂账）
- 36 份课件的历史 P0/P1 计数继承自**旧口径** checkpoint（`--auto-hours`），台账已加 `caliber_warning` 标注；**须用 SSOT + 显式 `--hours` 重跑全量**才能得到可比结论，本次未做（涉及 36 份课件只读全量扫描，另行安排）
- 14/14 课件挂账超 3 天、58 个残余 P0 **尚无处置记录**；已把"挂账审判"写入 verifier 职责，待闸 4 首次运行时批量清偿
- `overlay_injection` 四键（`min_font_pt`/`require_empty_slot`/`max_overlap_ratio`/`sample_review_ratio`）**仍零脚本消费**——R18 事故的对症药尚未装上，属 B2 批次待办
- token/成本仍不可观测（平台不向主理人暴露成员用量），不以估算冒充

---

## [v2.2.0] - 2026-09-29

### 概述（Harness 工程化：把编排纪律从提示词下沉为代码）

对专家团做了一次完整闭环诊断（定位通读 → 实测 → 九维度诊断 → 对标 → 重构 → 同任务重跑验证）。
实测暴露的核心事实：**专家团的"专业方法论"密度很高，但"执行框架"几乎为零**——
成员不可调度即整链阻断、平台静默降级无人察觉、门禁脚本撞出 3 个未发现的崩溃、全程零日志零预算。
v2.2.0 不改动原有核心目标与使用方式（仍是六阶段门控 + 四成员 + 分级门禁），
只在**编排层新增确定性内核**，把"靠自觉"的纪律变成"靠代码"的约束。

### Added
- **`config/harness.yaml`（新增）**：编排层唯一数据源——显式状态机 `stages`（只认 0–5 整数）、成员注册表（职责 + **工具白名单** + 降级通道）、复杂度→spawn 路由表、预算护栏（spawn/rework/react 上限 + 阶段挂钟上限 + 产物字节上限）、上下文隔离策略、trace 配置、门禁退出码语义
- **`scripts/harness.py`（新增，确定性编排内核）**：6 个子命令——
  - `preflight`：开工前成员可用性预检，**专抓"平台把成员静默降级为 general-purpose"**（实测抓到严真奥）
  - `route`：复杂度 L0–L3 → 确定性 spawn 计划
  - `state`：状态机读写与校验（拒绝非法阶段值、拒绝白名单外的键、超限强制 compaction）
  - `budget`：任务级预算计数（纪律变计数，超限即阻断并写 trace）
  - `trace`：JSONL 执行日志 + `report` 汇总（事件计数 / 按成员统计 / 阶段耗时秒数）
  - `gate`：包装 verify_deck，统一退出码语义并落 trace 与耗时
- **`references/harness-engine.md`（新增）**：人读入口，规定开工三步、降级协议、状态机纪律、预算用法、上下文隔离、统一门禁入口
- **`scripts/test_harness.py`（新增）**：9 条回归用例（路由确定性 / 状态合法性 / 白名单 / 预算阻断 / trace / preflight / 静默降级探测 / 门禁不崩溃），本包首个测试文件

### Changed
- **工具白名单（P0）**：5 个 agent MD 的 frontmatter 新增 `tools:`（与 `harness.yaml#members` 同源），结束"成员默认继承宿主全部工具"的状态
- **降级协议（P0，规则修订）**：旧规则"Agent tool 不可用＝任务阻断"改为 **"先降级，后阻断"**——同一成员最多 2 次尝试，仍不可用则 spawn 通用子代理并**注入该成员 MD 全文**（人格与红线照旧生效），且必须在交付物与 trace 中显式声明。**红线未松动：任何情况下禁止主理人代写成员产出**
- **状态机纪律（P0）**：`task_state.json` 只允许白名单内键、阶段值只认 0–5 整数（杜绝实测中出现的 `M5A2` / `stage_6` / 32 键 27KB 膨胀）
- **统一门禁入口（P0）**：阶段5 一律走 `harness.py gate`，**exit=4（运行错误）走缺陷回流修脚本，不得当作课件红灯打回成员**
- 主理人 MD 新增「编排内核」节；`sop-stages.md` 阶段0 新增开工三步、阶段5 换统一入口

### Fixed（三个被实测当场撞出来的崩溃，全部是"没有回归测试"的后果）
- **越界检测崩溃**：形状几何元组含 `None` 时 `x < -tol` 抛 TypeError → 整个门禁 exit 4（实测 `7. 禽流感.pptx` 触发）。修复：几何取不到记 `parse_errors`（P3 明示），不参与比较
- **重叠检测崩溃**：同上，`_overlap_area` 的 `max()` 收到 None 崩溃（修完越界后暴露的第二处）。修复：比较前过滤含 None 的矩形
- **字号比较崩溃**：`sizes` 含 None 时 `min()` 返回 None 后与阈值比较崩溃（第三处）。修复：过滤 None，取不到字号记 `unknown_font`
- **静默回退护栏可绕过**：`visual-rules.yaml` 加载失败时静默用内置阈值继续裁判——改**硬失败**，仅 `VERIFY_ALLOW_FALLBACK=1` 才回退（并醒目告警）
- **错误不可诊断**：verify_deck 顶层只打印一行错误信息、吞掉 traceback → 主理人无法区分"课件有问题"与"脚本有 bug"。修复：打印完整堆栈 + 错误类型 + 处置指引

### 实测对比（同一任务 T 重跑，详见 outputs/harness-ab/REPORT.md）

| 指标 | v2.1.0 基线 | v2.2.0 重跑 |
|---|---|---|
| 苏学法（页表产出） | ❌ 3 次调度失败 → 阶段3 整链阻断 | ✅ 降级通道产出（通用子代理 + 注入成员 MD） |
| 静默降级 | ❌ 严真奥被登记为 general-purpose，无人察觉 | ✅ preflight 显式报 `degraded` 并给处置建议 |
| 门禁（曾崩溃课件） | ❌ exit 4 崩溃，无法判定 | ✅ exit 1：P0=5 / P1=1 / P2=0% / P3=1，可判定可修复 |
| 执行日志 | ❌ 无 | ✅ JSONL trace（事件/成员/阶段耗时） |
| 预算护栏 | ❌ 无计数 | ✅ spawn/rework/react 计数，超限阻断 |
| 回归测试 | ❌ 0 用例 | ✅ 9/9 通过 |

---

## [v2.1.0] - 2026-09-26

### 概述（v2.0.0 挂账清单执行：P1 版面外科 + P2 备注覆盖率，修复能力沉淀为正式工具）

对 14 份真实课件执行 v2.0.0 定义的挂账修复，并把可复用能力固化为专家团工具。**全程按"工具自报不算数、verify_deck 复验才算数"纪律执行。**

### Added
- **scripts/surgery_deck.py**：批量版面外科工具（屠明熙出判据/郅作基执行）——重叠卡位迁移（网格搜空位、注入卡优先、避图 30%、找不到空位如实记 unresolved）+ 越界画布内微调；dry-run 先行、偏好 C 备份后执行
- **scripts/inject_notes.py**：讲稿备注注入工具——按页面真实内容生成【AI草稿·待教师复核】讲稿四件套（本页定位/讲授要点/讲法建议/提问话术/易错提醒），含纯图片页指图讲分支；内容多的页优先，补到 P2 覆盖率达标即止
- **deck_registry.json `v2_1_0_pass` 记录**：每课件的手术统计/备注注入数/复验退出码，前后对照可追溯

### Fixed（工具开发过程中被复验当场逮住的三个 bug，全部反成纪律教材）
- **漏 save 空转**：surgery_deck 首版在内存改完形状未写盘，"迁移 515"全部无效——verify_deck 复验重叠数纹丝不动当场逮住。教训固化：**工具自报数不算数，复验才算数**
- **容差单位错**：0.25 英寸容差被当 EMU 比较（≈0），把装饰性微出血误判为越界去"修"——P0 计数与复验对不上（修了 21 处 P0 只降 1）暴露
- **单文本框页漏检**：`len(texts)<2` 守卫本意是跳过无重叠可能的页，却把越界检测连带跳过（M4C1 P3"标题标签+大图"型页面复现）——守卫改为只管重叠阶段

### 实测结果（14 份课件，verify_deck --level all 现场复验口径）
- **P1：728 → 210**（-71%；重叠大头已清，残余=文字墙 56+过满页未解重叠，拆页属内容决策留苏学法工作流）
- **P2 备注：13/14 不达标 → 14/14 覆盖率 ≥80%**（注入 195 页 AI 草稿讲稿，全部显著标注待教师复核）
- **P0：60 → 58**（越界清零；残余 58=配色/目录/题页/课时结构决策项，非脚本范围，如实挂账）
- deck_registry.json 全程记录前后对照（gate_pre_v210 → gate_post）

---

## [v2.0.0] - 2026-09-26

### 概述（v1.9.0 首战实测驱动：M4A1 六阶段流水 + 14 份课件现场复跑 1281 条红灯 0 份全绿；报告：outputs/vet-med-ppt-team_v2.0.0实战诊断与改造方案_20260926.md）

核心发现：①写回门禁三态失效（宣告式——stage5 四项 deviations 上升用户拍板；不可达式——"全清"物理不可达必被绕过；崩溃式——M4D2 unrecognized shape type 致裁判 exit=2）；②最大红灯源是团队自己的 A 轨叠加层法（只加框不重排 → 元素重叠 486 处居首；试做 12pt 批量写成 8pt，R18 同型两张皮复发）；③职责真空三处（几何修复/讲稿备注/砍页裁决）；④自评失真（final_report 同文件"三维归零"与 38+28 未修并存）；⑤屠明熙 v1.9.0 转型副作用（批量几何施工能力被抽走）。

**角色结论：不增删不合并（4 成员正交无冗余），以职责回补 + 规则项补齐代替加人。**

### Added
- **分级门禁（本版核心）**：红灯四级——P0 硬阻断（字号/越界/配色/空白/课时/目录/题页，写回前必须=0）/ P1 必清（重叠/文字墙，可带修复计划写回、交付前清零）/ P2 指标（备注覆盖率 ≥80%）/ P3 明示（继承未取到/解析异常/装饰出血）。门禁判据从"全清"改为"P0=0"，可达即可执行
- **verify_deck.py v2.0.0**：`--level P0|P1|all` 参数；退出码语义 0=通过/1=P0/2=P1/3=P2/4=运行错误；逐形状 try/except + XML 兜底解析（抗 mc:AlternateContent 崩溃，M4D2 实测恢复可判定）；字号继承解析链（run→段落 defRPr→版式占位符→母版 txStyles，2.1HPAI 盲区 77 处大幅收敛）；隐藏页纳管统计；分级计数进 JSON 报告
- **references/batch-surgery-sop.md**：批量版面外科 SOP（屠明熙所有）——叠加层注入四前置断言（空位检测/字号≥12pt/重叠≤15%/逐页清单）、几何红灯修复四级顺序（缩小→移动→拆页→删冗余）、拆页规则与验收
- **config/visual-rules.yaml 新增三节**：`gate`（p2_note_coverage 0.80 + 写回/交付级别名）、`severity`（分级映射，单一数据源）、`overlay_injection`（注入规范）
- **苏学法页表三字段→五字段**：+`speaker_note`（每页讲稿 ≥80 字，备注产出权归苏学法——241 页缺备注挂账无主的对症药）、+`page_role`（core/extended/optional，砍页依据链：苏学法定角色→郅作基按 optional→extended 执行——stage5 砍页双向落空的闭合）；课时表新增"扩展阅读"档
- **主理人阶段0 两项强制裁决**：隐藏页处置（恢复/删除/保留+明示数量）+ 页数口径（正式课时 vs 扩展阅读分开计数）——阶段5 不得就同一问题再上升用户
- **deck_registry.json 全局台账（郅作基）**：manifest 升级为跨任务活台账（mtime/md5/页数/隐藏/P0-P3/备份/first_seen），冷启动扫描 P0>0 且挂账 >3 天必须主动上报用户；已由 repair_p0_v200.py 建立 14 份种子账
- **反自评失真红线（adjudication-rules.md）**：禁"归零/100%"表述除非引用 verify_deck 原始计数；强制结论格式 `P0=x/P1=y/P2 n%/P3 k处`；终检页面性门必须附原始输出片段

### Changed
- **屠明熙职责回补**：规则引擎之外加挂"批量版面外科 SOP 所有者"（出判据不施工，Maker/Checker 不破坏）；抽样复核量化 ≥20% 且几何红灯页 100% 复查（原 10% 实测挡不住 486 处重叠）
- **郅作基写回门禁改分级语义**：`--level P0` 写回 / `--level all` 交付；deviations 纪律——P0/P1 项主理人必须先组织修复，不得作为待决事项上升用户拍板
- **sop-stages.md 阶段5 重写** + 修复既有"两个 5."编号错误；阶段3 七字段→九字段（教学列五字段＋版式列）

### Fixed（存量回修，用户批准执行）
- **14 份课件字号 P0 回修**：1125 处钳制（run 1104 + defRPr 0 级别按份计），阈值直接 Read visual-rules.yaml；**P0 总量 681 → 60**（字号类全清，残余 60 为配色/目录/题页/课时等结构决策项）；偏好 C 备份链完整；deck_registry.json 记录前后门禁计数

---



## [v1.9.0] - 2026-09-26

### Changed（v1.8.0 后 14 天实战诊断驱动：郅作基 0/14 天未上场 + R18 事故 258 处字号红灯 + 门禁无人值守；报告：outputs/vet-med-ppt-team_v1.8.0实战诊断与改造报告_20260926.md）
- **屠明熙转型"视觉规则引擎架构师"**：红线参数化至 config/visual-rules.yaml（唯一数据源，verify_deck 与批量脚本共同消费）；高价值页（封面/机制流程图/预测-揭示对）保留人工设计；批量场景规则布防+抽样复核。核心理念：**人可以不在场，规则必须在场**
- **郅作基转型"课件执行工程师"**：写回门禁（Write-Gate）硬性职责——任何课件写回磁盘前 verify_deck 红灯清零+manifest 页数核对+备份确认，无例外（主理人亲自施工也过门禁）；批量脚本合规驾驶（前置断言：缩字号 <12pt 直接拒绝）
- **主理人 L0-L1 施工合法化**：单件任务诊断后主理人可直接修改（09-23 两任务验证高效）；L2+ 批量仍禁代写。原"严禁亲自施工"教条按实战修订
- **课件改造三级路径固化**（R16/R17 实测结论制度化）：①A 轨轻改造全员批量(~30min/课件)→②B 轨三段倒序重点课件(15-25min/页)→③A 轨真重构精品(完整六阶段)；每级注明执行/验收人

### Added
- **config/visual-rules.yaml**：字号/容量/几何/课时页数/图注五要素五节红线参数，单一数据源；verify_deck.py THRESHOLD 改为动态加载（yaml 失败回退内置值并告警），改造前后裁判判定一致性已实测（M5A1 258 处红灯不变）

---

## [v1.8.0] - 2026-09-18

### Changed（John Conway 教育洞察注入，宪法级；四项裁决：宪法级/疾病课倒序/双侧同步/职业生存转化）
- **主理人第一性原理 5→6 条**：原理4 重写为 Conway 原命题「讲有趣的内容可以达到教育的目的；讲有用的内容达不到教育的目的」+ 三条操作化禁令（禁考点式组织/禁知识清单平铺/先过有趣关再过完整关）；新增原理6 权威律（权威=知道学生需要什么；知识诅咒防线：高职大二学生视角默认）

### Added
- **苏学法 · 预测-违反-更新导入律**：每模块开场强制学生预测（猜失败案例成因/判病变归属），预期正确率 30-60%；禁用成功故事开场
- **苏学法 · 二八难点定位**：蓝图必标约 20% 影响 80% 理解的关键难点清单，页数与互动密度向其倾斜
- **苏学法 · 双轨教学结构**：顺序轨（案例→理论→实践→总结）/倒序轨（场景→功能→结构→原理）；疾病课默认倒序、诊断技术课默认顺序、模块级切轨
- **苏学法 · 能力3 升级为隐性知识师徒传承**：塔西图隐性知识显性化 + 知识诅咒自检（每页问"学生具备前置知识吗"）+ 输出→讨论→思考→再输出闭环 + 每课至少 1 个元认知目标（学会学习）
- **严真奥 · 知识诅咒标注**：证据包概念必标「学生已知/需铺垫/易误解」三类；「易误解」自动进二八难点候选；隐性知识线索标注
- **屠明熙 · 预测-揭示版式对**：预测页（大问题+选项大字+倒计时视觉）→揭示页（你以为vs实际是对照+惊讶点强调色）；权威感视觉律（视觉焦点=学生下一步需要的，非我们想展示的）
- **studio v2.5.0 同步**（用户裁决双侧）：SKILL.md 注入 Conway 有趣律/预测律/二八/双轨/知识诅咒五律 + 预测-揭示版式对；teaching-style.yaml 新增 conway_interest_law 配置块（YAML 已验证）

---

## [v1.7.0] - 2026-09-18

### Changed（Harness 工程化重构，基于 2025-2026 领域规范检索：Anthropic 四支柱/四失败模式、OpenAI 百万行实验、Anthropic 多智能体研究系统）
- **主理人 MD 深度瘦身：212 行/24.2KB → 141 行/10.1KB（-58%）**——六阶段 SOP 细节与裁决/终检规则下沉至 references/（sop-stages.md + adjudication-rules.md），主理人 MD 只留索引+红线+schema+路由表。对齐 OpenAI "AGENTS.md ~100 行索引+地图" 规范，spawn 上下文负载减半，破 40% sweet spot 风险消除
- **阶段4 复检改非作者交叉复检（Maker/Checker 分离）**：教学性改动→严真奥复检、科学性改动→苏学法复检、页面性改动→苏学法复检——复检人≠产出人，只答「从我的专业视角会不会埋雷」。对齐 Anthropic "Agents are incapable of accurately evaluating their own work"

### Added
- **任务复杂度分级（L0/L1/L2/L3）**：微任务直调零编排 / 轻任务 1-2 成员 / 标准 6 阶段 / 重任务打样-流水线+可选 RedTeam。对齐 Anthropic "Scale Effort to Query Complexity"（防简单任务过度编排、复杂任务偷工）
- **下发任务包 schema（四要素委派协议）**：objective/output_format/constraints/task_boundary，spawn 必附；并行任务边界互斥。对齐 Anthropic "Teach the Orchestrator to Delegate"（防重复劳动与覆盖缺口）
- **阶段5 终检结构化清单**：科学性门/教学性门/页面性门/交付完整性门四门逐项打勾，任一不过打回
- **缺陷回流协议（熵回收）**：同类错误≥2次触发，流程缺陷→改规则、知识缺陷→严真奥知识回注、脚本缺陷→升级脚本。对齐 Mitchell Hashimoto "每发现一个错误就工程化消除其再现" + OpenAI 熵垃圾回收
- **Compaction 最小集策略**：task_state.json 新增 compaction 字段（task_id/current_stage/关键决策/文件路径四必保），冷启动恢复=最小集+对应阶段章节，禁止重读全部历史。对齐 Anthropic 记忆持久化规范

### References 新增
- references/sop-stages.md（六阶段完整 SOP + task_state 规范 + Compaction 策略）
- references/adjudication-rules.md（裁决优先级 + 六项自检 + 终检四门清单 + 缺陷回流协议 + 安全合规）

---

## [v1.6.0] - 2026-09-18

### Added（用户教学理念 DNA 有机注入，经四项裁决：两边同步/扩展课时表/参数化泛养殖/分层时限）
- **主理人 · 第一性原理 3→5 条**：新增「职业教育的核心产品是学生的自信」（可达成任务+及时正向反馈）与「讲有趣的故事达成有用的教育」；新增「三层内容律」（是什么/为什么这么做/现场会遇到什么坑）
- **苏学法 · 疾病课十模块模板**：疾病专题课专用架构（导入→病原→流行→临床病理→机制免疫→综合诊断→防控→案例决策→总结思政→测评），与诊断技术课八大模块并存，按课型选用；含裁剪优先级（保1/4/6/8→压2/3/5→并7/9→测评10独立保留）
- **苏学法 · 课时表新增 1 小时教学单元档（60min=35-50页）**：用户「约1小时」授课习惯的标准档；verify_deck.py 同步支持 --hours 1.5（float 类型）
- **苏学法 · 测评量化指引**：3-5 道选择题 + 1 道综合案例分析题（人机协同+批判性核验 AI 输出+现实可行性），附参考答案与评分要点
- **苏学法 · 故事化与费曼翻译**：比喻库沉淀于教学蓝图，同课件比喻体系一致
- **苏学法 · 学生自信设计律**：每学习单元至少 1 个可达成分析任务（10min 内完成+可判对错），参考答案含表扬要点；后进学生每课至少一次成功体验
- **苏学法 · 三层内容律（页面脚本强制字段）**：每模块三层覆盖，缺层须在蓝图风险栏标注
- **严真奥 · MSD Vet Manual 入列正式权威源**（国际组织之后、综述之前）
- **严真奥 · 文献时限分层律**：诊疗/流行病学/疫苗毒株/禁药=近5年；机制类/基础免疫学=近10年；教材与指南不受限但须核现行版本
- **严真奥 · 一体化养殖企业实战经验供给**（物种参数化：默认禽，可换猪/牛羊/伴侣动物）：为三层内容律第③层供素材（育种/饲养/营养/环控/设施全链路实战偏差）
- **屠明熙 · 图注五要素制**：对照关系+物种/日龄/病程+来源许可+教学意义+（示意图）免责声明，缺一不可
- **屠明熙 · 机制页强制流程图版式**：病原入侵-复制-扩散等动态过程禁止大段文字，必须流程图/时序图（配合十模块第5模块）
- **同步 studio v2.4.0**：SKILL.md 双课型架构+坍缩映射表新增养殖全链路模块+P2 分层时限+P3 加 MSD+Step3 页数预算加 1 小时档；teaching-style.yaml 新增 content_three_layers / course_architecture / assessment_quantum 三配置块+两大理念入 core_beliefs

### Added
- **ensure_settings.py 升级为 doctor（4 项体检 + 1 项自愈）**：从"恢复 settings.json 单点工具"升级为发布前强制门禁。诊断耗时 <1s，4 项全绿才能发布
  1. settings.json 存在且 `agent` 字段与 plugin.json 一致 → 缺失/损坏则**自愈**重建
  2. `.codebuddy-plugin/plugin.json`（WorkBuddy 侧）与 `.claude-plugin/plugin.json`（Claude Code 侧）版本号一致 → 漂移则告警【只读】—— `validate_expert.py` 只校验前者，单靠官方工具查不出此项（2026-09-17 实证 v1.4.1→v1.5.1 漂移 2 个小版本未被发现）
  3. 清单声明的 5 个 agent 文件全部存在 → 缺失则告警
  4. `scripts/verify_deck.py`（机械验证门禁）随包分发 → 缺失则告警
- **vet-med-ppt-team.zip 重打包**：旧包停在 2026-09-12 的 v1.4.1（仅 20 文件、无 scripts/、无 docs/），新版 32 文件、含 scripts/、含 docs/repo-meta/

### Changed
- **UPGRADE.md「修改后必做」段落**：从"必跑 ensure_settings.py 单点恢复"升级为"必跑 doctor 4 项门禁"。两插件清单版本漂移是导致 settings.json 反复丢失的潜在根因之一（每次手动 cp 都可能遗漏另一侧）

### Fixed
- **本插件包 5 次丢失 settings.json（2026-09-12、09-17×4）**：从"事后手动恢复"升级为"事先检测+事后自愈"闭环。同 marketplace 下其他 4 个 Team 型专家因未被持续修改而不丢失，确认删除源是 WorkBuddy 宿主热重载，不是随机故障

---

---

## [v1.5.2] - 2026-09-17

### Added
- **ensure_settings.py 升级为 doctor（4 项体检 + 1 项自愈）**：从"恢复 settings.json 单点工具"升级为发布前强制门禁。诊断耗时 <1s，4 项全绿才能发布
  1. settings.json 存在且 `agent` 字段与 plugin.json 一致 → 缺失/损坏则**自愈**重建
  2. `.codebuddy-plugin/plugin.json`（WorkBuddy 侧）与 `.claude-plugin/plugin.json`（Claude Code 侧）版本号一致 → 漂移则告警【只读】—— `validate_expert.py` 只校验前者，单靠官方工具查不出此项（2026-09-17 实证 v1.4.1→v1.5.1 漂移 2 个小版本未被发现）
  3. 清单声明的 5 个 agent 文件全部存在 → 缺失则告警
  4. `scripts/verify_deck.py`（机械验证门禁）随包分发 → 缺失则告警
- **vet-med-ppt-team.zip 重打包**：旧包停在 2026-09-12 的 v1.4.1（仅 20 文件、无 scripts/、无 docs/），新版 32 文件、含 scripts/、含 docs/repo-meta/

### Changed
- **UPGRADE.md「修改后必做」段落**：从"必跑 ensure_settings.py 单点恢复"升级为"必跑 doctor 4 项门禁"。两插件清单版本漂移是导致 settings.json 反复丢失的潜在根因之一（每次手动 cp 都可能遗漏另一侧）

### Fixed
- **本插件包 5 次丢失 settings.json（2026-09-12、09-17×4）**：从"事后手动恢复"升级为"事先检测+事后自愈"闭环。同 marketplace 下其他 4 个 Team 型专家因未被持续修改而不丢失，确认删除源是 WorkBuddy 宿主热重载，不是随机故障


## [v1.5.1] - 2026-09-17

### Fixed
- **屠明熙字号红线不可执行**：原定"正文≥24pt"为理论理想值，13.33×7.5in 画布下仅容 8-10 行/页，2026-09 实战 34 课件中**从未被执行**（实际普遍 10-12pt）。改为底线+推荐双轨（正文底线 12pt / 推荐 18-24pt；图注底线 9pt）
- **郅作基路径默认与实战背离**：原以"路径A·交付指令包"为默认，但实战 34 课件全部为已有 .pptx 优化（100% 走 B），六件套从未真正交付。改为"存在待处理 .pptx 时 B 为默认，A 仅用于从零创作"
- **苏学法课时-页数标准缺失**："课时适配"在 R2/R4/R6/R7 四轮反复返工的根因——负责页数区间的角色没有标准值。新增课时-页数换算表（1课时18-28页 / 2课时36-52 / 3课时55-78 / 4课时72-104）

### Added
- **严真奥 · Europe PMC 图片主力通道**：实战中 Ima 图片检索常 0 命中、共享库报 220030、UpNote 无图片，真正稳定的取图通道此前**不在设计内**，属临时发挥。现列为正式主力通道并给出 API、许可、图注三要素、禁用清单
- **严真奥 · 时效敏感字段清单**：疫苗毒株/禁药休药期/诊断标准号/流行毒株每年必须联网核验，防"教去年的法规"
- **严真奥 · 知识回注协议**：成果写入 `knowledge/`，MD 正文只留检索指针（防上下文膨胀）
- **屠明熙 · 美学量化红线**：元素重叠=0、单页配色≤5 种、单页字数≤400（学生视角硬约束：看不见/看不下去 = 教学事故）
- **郅作基 · 交付前机械验证门禁**：必须跑 `verify_deck.py`，红灯清零方可回传（R6 自称四维100%、R9 复验出 3408 处的教训）
- **郅作基 · 快照与 manifest**：改前 `cp` 到 `_backup/`（禁 /tmp）、记录页数+md5、回传前校验页数一致（M4B4 丢 19 页无人察觉的教训）
- **郅作基 · 备注 100% 硬门槛**：新城疫 63 页中 33 页无备注却仍被宣布"达标"
- **scripts/verify_deck.py**：8 项机械验证器，与 Claude Code 侧 `vet-ppt-pipeline` 共用同一裁判（AB 测试可比性的前提）
- **scripts/ensure_settings.py**：settings.json 幂等恢复器

### Changed
- 专家包自包含化：验证脚本内置于专家包（便于日后分享），郅作基 MD 中原 `<skill>/scripts/...` 占位符改为实际路径

---

## [v1.5.0] - 2026-09-17

### Fixed
- **主理人代写漏洞（本次最关键修复）**：v1.3 引入的"Agent tool 不可用 → 主理人代行角色内容"回退规则，与官方 team-spec 五条红线（禁止跳过 TeamCreate 自己模拟成员发言／禁止自己代写成员专业产出）直接冲突。实战后果：2026-09-13 批量任务中主理人以"复合角色"一人代写四名成员产出，六阶段门控全程空转，最终由用户 10 轮迭代兜底。
  - 新规则：成员无法 spawn = **任务阻断**，停止推进 + 向用户明说 + `task_state.json` 标记 `blocked`
  - 明确禁止"复合角色""一人分饰多角""参考成员视角自行综合"等任何变体
- **settings.json 丢失**：插件目录 `settings.json` 缺失致 validate 失败（Team 型必需），已补回并同步（此文件已第三次丢失，属已知竞态问题）

### Changed
- **协作规则第 1 条强化**：`TeamCreate → Agent spawn（name 传 Agent ID）→ SendMessage 回传` 为唯一合法调度路径；成员未成功 spawn 即视为该阶段未完成，禁止推进
- 主理人 MD 增加 v1.5.0 红线条目，写明历史教训与判定依据，防止后续迭代中被再次"容错化"

### Added
- 双轨演进：本团队（WorkBuddy 侧）与 Claude Code `vet-ppt-pipeline` skill 并行 AB 测试，以机械验证脚本 `verify_deck.py` 作为统一裁判

---

## [v1.4.1] - 2026-09-11

### Added
- **双 marketplace 清单**：仓库根新增 `.claude-plugin/marketplace.json`（Claude Code）与 `.codebuddy-plugin/marketplace.json`（WorkBuddy），`/plugin marketplace add virologist/vet-med-ppt-team` 从此真正可用
- **Claude Code 插件清单**：`packages/vet-med-ppt-team/.claude-plugin/plugin.json`（与 WorkBuddy 版内容对齐，满足 Claude Code 目录名规范）
- **私有仓库认证说明**：INSTALL.md 顶部前置条件 + 故障排查新增 401 条目
- **Claude Code subagent 挂载方式**：INSTALL.md 方法 C（agent MD 直接复制到 `~/.claude/agents/`）

### Fixed
- **安装命令语法错误**：`/plugin install virologist/vet-med-ppt-team@packages/vet-med-ppt-team`（语法不存在的路径式引用）修正为标准两步：`/plugin marketplace add virologist/vet-med-ppt-team` → `/plugin install vet-med-ppt-team@vet-med-ppt-team`
- **zip 分发版过期**：内含旧版 team-lead MD（21002B vs 仓库 22471B）且嵌套多余 zip，重新打包并消除嵌套

### Removed
- **skillstash 方法**（INSTALL.md WorkBuddy 原方法 C）：未经本人环境验证的第三方工具指引，移除以避免误导

---

## [v1.4.0] - 2026-09-10

### Changed
- **路径决断权属主理人**：郅作基不再自主选择路径A/B；由主理人在 task_state.json 的 `next_action` 字段下发
- **路径B偏差裁决协议**：handoff_out.json 的 `deviations_from_handoff` 非空时强制主理人裁决，郅作基不得自主整合

### Fixed
- **pending_items 流转丢失**：主理人终检项新增"遗留待办转发"，用户能拿到 teaching-ppt-studio 的待补充清单
- **预取事实过期**：严真奥阶段2启动前校验 task_state.json，用户改需求后强制重新检索而非盲目沿用阶段1预取
- **task_state.json 并发冲突**：原子比对 task_id，检测到并发立即停止推进并报警

---

## [v1.3.0] - 2026-09-10

### Added
- **统一回传 schema**：所有成员回传主理人使用 `{from, stage, artifact, warnings, evidence_used, next_recommendation}` 结构
- **任务状态文件 task_state.json**：长任务中断/切换会话时主理人必读恢复状态
- **工具/通道不可用回退表**：TeamCreate / SendMessage / Agent tool / Ima 四通道全覆盖

### Fixed
- 严真奥 vs 屠明熙医学图像归属边界模糊（C1）
- 路径B移交 schema 字段与 teaching-ppt-studio 不齐（C2）
- 阶段3并行任一方超时阻塞（L1）
- 严真奥 ReAct 循环无限（L2）
- 阶段1预取与阶段2重检（R1）
- 苏学法案例与评价双独立产出（R2）
- 工具探针双登记（R3）
- 阶段4自查+强制复检双质检（R4）
- Ima 库ID 硬编码（T1）
- UpNote 未做探针（T2）
- python-pptx 路径硬编码漂移（T3）
- SendMessage 无回退（T4）

---

## [v1.2.0] - 2026-09-10

### Added
- **协同路径A/B分流决策表**：郅作基按场景决定输出指令包还是调 teaching-ppt-studio
- **路径B交接协议**：写入 `*.handoff_in.json`，字段对齐 teaching-ppt-studio v2.1.0 schema
- **teaching-ppt-studio 协同入口**：新增「何时使用」「协同入口识别」「协同回传结构」三段

### Changed
- 专家团升 v1.2.0，teaching-ppt-studio 升 v2.1.0（反映协同能力）

---

## [v1.1.0] - 2026-09-10

### Added
- 工具探针协议（markitdown + python-pptx venv 检测）
- 低证据风险跳阶段2门控捷径（用户同意制）
- 阶段1预取机制（严真奥≤5条核心事实）
- 阶段3合并页表单文档（教学列+版式列一表）
- 阶段4质检分轨（单页自查/跨模块回传+diff）
- 任务收尾协议（工作空间记忆写入）
- Ima 路由表下沉至严真奥MD（主理人不直接检索）

### Fixed
- 主理人/严真奥/苏学法/屠明熙/郅作基 11 处问题（含 Ima 路由归属、ReAct 循环无硬限、上下文按需传递、工具编排主动性等）

---

## [v1.0.0] - 2026-09-10

### Added
- 初始版本发布
- 五人 Team 型架构：主理人（Quan Keji）+ 严真奥（Yan Zhen'ao）+ 苏学法（Su Xuefa）+ 屠明熙（Tu Mingxi）+ 郅作基（Zhi Zuoji）
- 六阶段门控流水线：阶段0任务冻结 → 阶段1教学蓝图 → 阶段2证据核验 → 阶段3页面级设计 → 阶段4迭代修订 → 阶段5制作交付
- 3 个预设 Workflow：WF-1 新制作完整流程 / WF-2 旧课件优化 / WF-3 汇报型课件
- 7 个 Ima 订阅知识库默认挂载：《禽病》Avian Disease（主力库）/《猪病》/《牛羊病》/《伴侣动物疾病》/病毒学-免疫学-细胞学/流感/动物疫病诊断技术（WOAH/FAO/WHO）
- 6 张统一风格头像（navy slate-blue 主题）

---

## 路线图（规划中）

- [ ] 严真奥阶段1预取的"≤5条核心事实"扩展为可选的预检索缓存层（写入 `<workspace>/.workbuddy/evidence_cache/`）
- [ ] 阶段3合并页表导出为 JSON Schema（便于其他工具解析复用）
- [ ] 加入"教学竞赛"专属 Workflow（评委视角+说课节奏优化）
- [ ] 加入"翻转课堂"模式（学生预习→课堂答疑的脚本变体）
- [ ] 国际化：英文版 agent MD（中英文双语提示词）

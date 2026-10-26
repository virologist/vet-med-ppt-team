# 更新日志 · CHANGELOG

本文件记录动物医学教学PPT智造团（vet-med-ppt-team）的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [v3.23.1] - 2026-10-27（残留收口：chart 判据落地两项 + 静默异常留痕）

> 依据：v3.23.0 发布后的**残留盘点**（用户指令：解决残留问题 + 继续未完成任务）。
> 本版为小版本：只收口已登记残留，不动既有判据与护栏，**零破坏性变更**。

### W1 · `chart.unimplemented` 三项中两项落地（残留自 v3.22.0 G2）

`config/visual-rules.yaml#chart` 原登记 `unimplemented: [axis_label_min_pt,
legend_required, table_layout]`。本轮实证判据可**确定性解析**（chartSpace XML 内
`<c:catAx>/<c:valAx>` 段下 `<a:defRPr sz="N">`——N/100=pt；`<c:legendPos val>`；
`<c:ser>` 计数），落地前两项：

- `axis_label_min_pt`：轴刻度标注最小字号 < 下限 ⇒ 告警「图表轴标注字号过小」。
  **轴未写 txPr = 继承默认字号、无从判定 ⇒ 不误报**（与「未取得尺寸置 null 而非 0」
  同一纪律）。**缺省键 = 不判**（向后兼容，旧配置行为不变）。
- `legend_required`：多系列（≥2 个 ser）却无 legend ⇒ 告警「图表缺图例」；
  单系列不需要（图例即系列名）。**缺省键 = 不判**（老课件单系列图多，默认开启
  会噪音爆炸）。
- `table_layout` **仍不实现**（判据边界未清），`unimplemented` 缩为 `[table_layout]`。
- 两者均**建议级**（不登记 severity ⇒ 落 unknown_out 明示不阻断），与 G2 同口径。
- 解析通道：`shape.chart._chartSpace.xml`（python-pptx 对象模型，实测命名空间前缀
  稳定为 `c:`/`a:`）；解析失败 ⇒ 明示「无法解析，请人工核对」，不误报。
- 护栏：`test_verify_deck.py` 新增 `TestChartLayoutW1` 5 例
  （反例触发 / 正例不触发 / 缺省键不判 / 自闭合 ser 兼容 / serX 前缀不误吞）。

### W2 · `fetch_oa_image.py` 的 `LICENSE_TODO` 口径澄清（定性：非缺陷）

`LICENSE_TODO = "[待核实]"` 疑似 TODO 挂账。定性结果：它是**许可红线的显式日志标记**
（许可判定被拒 ⇒ 拒绝下载 + 日志挂账，**不写入 manifest**）；manifest 回填的
`reuse_status` 取 `asset-fields.yaml#reuse_status_default`（「待核查」），语义一致、
来源不同。真缺口是**口径无说明** ⇒ 已在常量处补注释（只用于日志 / 不参与判定 /
判定的键是 `license_uncertain_markers`），防后人误当 TODO 删掉或误接线。

### W3 · `classify_source` 未知 mode 分支补 stderr 告警（定性：fail-closed 正确）

`mode` 未实现 ⇒ `TIER_UNVERIFIABLE`（不可核验档不计入已验证，案例判否）——
**fail-closed 设计正确，不改判定**。唯一缺口：reason 只进返回结构，stderr 无声；
若将来 yaml 新增 mode 名却拼错，整批来源会静默落不可核验档，人要逐条翻 reason 才能发现。
修：补 stderr 告警（列出全部合法 mode + 指向配置段），判定语义不变。

### W4 · 三处静默 `except` 补留痕（一处定性为可容忍）

| 位置 | 原行为 | 处置 |
|---|---|---|
| `_write_collapse_artifact`（旧产物读失败） | 静默当 None ⇒ 已填 selection_rationale 被无告警抹掉 | **补 stderr 告警**（判定不变，幂等重建） |
| `collapse list`（单文件解析失败） | 静默 continue ⇒ 已确认产物在 list 里"查无此人" | **以 `status: unparseable` 条目显式列出** |
| `preflight`（task_state 读失败） | 静默回落空 probe ⇒ 与「真没探测过」不可区分 | **补 stderr 告警**（判定不变） |
| `_resolve_task_id`（读失败回落 "adhoc"） | 无害降级 | **定性可容忍，不改** |

### 本批实测揪出的真缺陷（独立验证发现，非自述）

1. **【P1】`<c:ser/>` 自闭合形态漏检**：ser 计数正则初版 `<c:ser(?:\s[^>]*)?>` 抓不到
   自闭合形态（`/` 非空白）⇒ 合成样例 ser 计数为 0。修：`<c:ser(?=[\s/>])[^>]*>`
   （`c:ser` 后必须跟 `/`、空白或 `>`，同时防误吞 `c:serX` 前缀同名标签）。
2. **【P2】测试自身两处写错**：`check_chart_layout` 引用漏 `vd.` 前缀（NameError）；
   测试替身类的类属性继承让负例用回正例 XML。均按**测试改正、不改实现**。

### W5 · 测试的**跨轮配置污染固化**（本轮实测踩中的真缺陷）

`test_collapse_domain_render.py` 与 `test_external_tools.py` 都会直接改写包内
`config/external-tools.yaml`（反例测试），各自用 `setUp` 备份 / `tearDown` 恢复。
**隐患实测踩中**：`setUp` 读备份时若文件已被**上一轮失败运行污染**（本轮 v3.23.1 首跑
T3 失败后 `knowledge_bases` 被清成空、进程结束前未恢复），备份存的就是**脏值**
⇒ `tearDown`「恢复」回脏值 ⇒ 污染**跨轮固化** ⇒ 下一轮 `test_external_tools` 的
T4/T7 拿到空库清单而**假失败**（`IndexError: list index out of range`）。

修法（两文件同步）：
- `setUpClass` **类级一次性备份**、`tearDownClass` 无条件恢复（替代逐测备份——
  逐测备份把「起点脏」也当基线存下来）；
- 每个 `setUp` **校验当前文件与类基线一致**，不一致 ⇒ 先重置再跑
  （让失败归因到「上一轮污染」而不是本测试）。

> 教训同 v3.20.0「隔离验证必须保证被测对象与被改配置同源」：
> **改共享配置的测试，其恢复基准不能取自可能已脏的现场。**

### 残留（如实登记）

- `table_layout` 仍无执行器（`chart.unimplemented` 缩为单项）；
- 块级消费免检区、判环语义判定、`tools_whitelist` 平台限制、Ima 凭据——均既有残留，未变。

---

## [v3.23.0] - 2026-10-26（第三轮独立诊断的 6 项修复：F1–F6）

> 依据：v3.22.0 基线上的**第三轮从零独立诊断**（13 维度，不沿用历史结论）。
> 诊断报告全文见工作区 `04-test/v3.22.0-第三轮从零诊断与对齐方案.md`；
> 主理人逐条取证实录见 `04-test/v3.22.0-第三轮-主理人独立探针记录.md`。
> ⚠ 本轮 **4 名独立诊断员全部 429 失败**（Token Plan 用量上限，**连续第三轮同型失败**），
> 按撞限协议由主理人接管全部 13 维度取证——**未伪造成员产出**。

### F1 · 死配置门（第 18 项）的**同名碰撞绕过**口子 —— 严重度：高

病灶实测（反向例，隔离副本，未触碰包内文件）：第 18 项的 alive 判定是
`n_full in norm_reads or n_leaf in norm_reads` —— **末段键名同名即算「已被代码读取」**。
`norm_reads` 含 **1268 个键名**（`enabled` 27 处 / `note` 47 处 / `max_retries` 7 处…，
其中 390 个**仅**来自字典字面量）⇒ 新增配置键只要与代码中任意键名重名，就自动判为已接线。

| 探针 | 构造 | 旧口径 |
|---|---|---|
| A | 已登记段 + 唯一叶名 | 检出 |
| B | **未登记新段** + 唯一叶名 | 检出 |
| C | **未登记新段** + 叶名 `enabled` | ❌ **漏检（rc=0 假绿）** |
| D | 既有段 + 叶名 `enabled`（现实场景） | ❌ 漏检 |
| E | 既有段 + 叶名 `max_retries` | ❌ 漏检（代码中另有 7 处同名） |

B vs C 是干净对照（同段同层级，唯一差异是叶名是否撞车）⇒ **同名碰撞可独立造成假绿**。
且 1433 个 alive 判定中**路径级强证据只有 22 个（1.5%）**，其余 98.5% 靠撞名。

修法：alive 判定改为**三层证据**——
  A 路径级（强）：AST 链式访问路径命中该键的整条路径或 ≥2 段后缀
  B 块级  （强）：父级配置段被代码整块取走 ⇒ 该子树随父级被消费（**单独计数可见**）
  C 名级  （弱）：**仅**末段键名撞车 ⇒ **不算已接线**，须登记 `known_weak` 并写明理由
新增 `_collect_chain_reads()`：AST 重建 `x.get("a").get("b")["c"]` ⇒ `a.b.c`，
并支持本包两种主流读法——**节访问器约定**（`_section(cfg, "段名")`）与**局部变量绑定**
（`x = f(cfg, "段名")` ⇒ `x.get("键")`）。弱证据**同样阻断**（旧口径下它被算作已接线）。
实测：真实包 17 个弱证据键 → 13 个经链式还原为路径级证据、4 个（`language-profile#languages.*`
展示元数据）改为**显式登记**；当前基线 rc=0。

### F2 · 人读型登记的**通用词裸段名**造成大范围自动豁免区 —— 严重度：中

`known_textual` 混着「末段键名」与「段名」两类条目，而 `path_prefixes` 把**两类都**派生成了
段级白名单 ⇒ 凡挂在名为 `name`/`note`/`description`/`version`/`duty`/`comment` 的段下的键
**一律自动豁免**。修法：通用词只按**末段键名**豁免（规则①保留），不再派生为段级白名单；
真正的段级登记（stages/collapse/…）维持原样。

### F3 · 四前置断言与三个零触达脚本**无行为性回归护栏** —— 严重度：中-高

实测：`inject_notes.py`（425 行，v3.22.0 G1 刚在此落地三道拒写防线）
**从未被任何测试 import 或执行**——唯一提到它的测试文件只在**注释**里引用它。
⇒ 任何对配置读取段的重构都可能悄悄废掉三道防线，而**没有一条测试会转红**。

修法：新增两个测试文件（12 例）：
- `scripts/test_inject_notes_assertions.py`（9 例）：字号 `font_below_min`、
  重叠 `overlap_exceeded`、空位 `no_empty_slot` 三条拒写路径 + 结果清单字段完整性
  + 正常路径（【AI草稿·待教师复核】+ 12pt）+ dry-run 判据不降级且不写盘
  + 断言① 配置读取与 yaml 一致；另附 `surgery_deck` / `fetch_authority` /
  `check_external_deps` 的冒烟护栏
- `scripts/test_dead_config_criteria.py`（3 例）：**F1 的直接反向例**
  （同名撞车必须被检出）+ 唯一名对照组 + 真实包基线

### F4 · `wip` 相对路径按 **cwd** 解析 ⇒ 运行期产物写进**专家包本体** —— 严重度：中-高

`harness.py:5447` 用 `os.path.abspath(args.wip)`（按 cwd），而同一函数里 `state_file`
落在 `workspace/.workbuddy/` ⇒ **两个基准不一致**。实测：以包根为 cwd 执行
`--wip "测试课件"` ⇒ **包根下生成 `测试课件/` 目录**（已复现两次）。
该目录被 `.gitignore` 遮蔽 ⇒ `git status` 仍显示「干净」，而本包用**文件拷贝**发布
到 OneDrive 镜像与包内 `packages/` 镜像 ⇒ **脏目录会被一起带走**；
同时违反 `loop_b.original_readonly`「原件只读」纪律。

修法：相对 `--wip` 以 `--workspace` 为基准；并加**包目录写入守卫**——
解析结果落在专家包目录内 ⇒ 拒绝并提示改用 workspace 内路径或绝对路径。

### F5 · `fetch_authority` 无通道输入时**假失败** —— 严重度：中

`fetch_authority.py --purpose "..." --domain "..."`（脚本自述的常规用法）
⇒ `results=[]` / `problems=[]` / 退出码 **3（EXIT_ALL_FAILED）**，
但**一个通道都没尝试过**（只有给了 `--pmid`/`--source-json`/`--record` 才真正执行）。
「全通道失败」与「网络故障」不可区分 ⇒ 把人引向错误排查方向。

修法：未给任何可执行通道输入 ⇒ 退出码改 **2（用法错误）**并明示「这是用法错误，
不是全通道失败」，并列出四种正确用法。

### F6 · 五闸 `active` 是**假开关** —— 严重度：中-低

`config/domain_config.yaml#gates.N.active` 全库 0 读取点 ⇒ 改成 false 不会关闭任何一闸
（假 affordance）。处置：按包内既有口径（五闸人读判据，机器判据在 verify_deck）
**如实标注为声明而非开关**，并在配置里写明真实判据位置。

### 本批实测揪出的真缺陷（独立验证发现，非自述）

1. **【P1】T1b 反向例的前提被合法改变**（第二次）：F1 引入的**块级证据层**使
   `shrink_order`（父段 `density` 被整块读取）去掉登记后仍存活 ⇒ T1b 转红；
   换到 `legacy_compat` 又因 `.gates` 路径前缀白名单兜住 ⇒ 再转红。
   ⇒ 动态挑样例的路走不通（会退化成 skip，护栏名存实亡）。
   修法：**改为自足式合成反例**——在隔离副本里自造「探针配置键 + known_textual 登记」，
   撤登记后断言必须重新变死；全程在 tempdir 上做（不再直接改包内文件再复原，
   原做法写盘瞬间会让并行体检读到半截文件——历轮已踩过）。
2. **【P1】链式重建初版把 `loop_contract.py` 的主流读法判成弱证据**：
   本包用 `_section(cfg, "delta_gate")` 读取，段名以**实参**传入 ⇒ 纯属性链在此断裂；
   局部变量绑定（`lb = _section(cfg, "loop_b")`）亦断。
   ⇒ 链式重建补**节访问器约定**与**局部变量绑定**两种能力，
   弱证据从 17 项降到 4 项（其余 13 项还原为路径级证据）。
3. **【P1】T1b 样例筛选漏查**前缀：只查后缀不查前缀 ⇒ 挑出"去掉登记后仍存活"的样例
   （`shrink_order` 即属此型）。
4. **【P2】取证工具本身造假绿**：macOS 自带 BSD grep **不支持 BRE 的 `\|` 分支**
   ⇒ `grep -n "a\|b" file` 静默返回空（看着像"不存在"）。
   本轮因此差点误报「v3.22.0 G1 四断言未落地」。改用 `grep -E` / ripgrep 后证伪。
   ⇒ **新增纪律**：取证阶段的"搜不到"必须用**两种不同工具**各验一次。
5. **【P2】测试自身写错**：python-pptx 拒绝 <1 英寸的页高；备注标注文案是
   「【AI草稿·待教师复核｜inject_notes v3.22.0 批量生成】」而非「【AI草稿·待教师复核】」
   ⇒ 断言按实际实现改正（**不改实现去迁就测试**）。

### 残留（如实登记，未假装已覆盖）

- **块级消费层的固有局限**：父级段被代码整块取走 ⇒ 该子树随父级被消费，
  静态判据**无法逐键确认**（实测 1489/1608 键属此型）⇒ 该层**单独计数可见**
  （输出「块级消费 N 项」），但它**仍是免检区**：在被整块读取的段里新增键，静态判据抓不到。
  这由静态判据原理决定，不是实现缺陷（与包内既有注释「AST 判据发现不了『读了 fallback
  而没读配置』」同源）。彻底解决需**运行时探针**（逐键断言配置值 == 运行时值），属后续独立立项。
- 判环（trigger）仍是语义判定，代码不判；`insert_font_at_creation` 结构性不可判定；
  `tools_whitelist` 无代码强制力（平台限制）；载体只承载结构与留痕，不承载质量判断。
- 会话层工具（pubmed/fetch/Ima）未做端到端实调（只核到登记级）；Ima 凭据未配置。
- **本轮诊断自身局限**：4 名诊断员全部 429 失败 ⇒ 覆盖广度由主理人一人承担（**盲区风险仍在**）；
  维度 5/7/10 仅静态核查无运行时实测；维度 2/6/11/13 的「软」面无成员配额。

---

## [v3.22.0] - 2026-10-26（第二轮独立诊断的 7 项修复：G1–G7）

> 依据：v3.21.1 基线上的**第二轮从零独立诊断**（13 维度，不沿用历史结论）。
> 诊断报告全文见工作区 `04-test/v3.21.1-第二轮从零诊断与对齐方案.md`。
> 修复顺序（管家节点确认）：G6 → G3/G4/G5 → G1 → G2 → G7。

### G6 · `insights add` 缺 `--task-id` ⇒ 静默写 default 载体（跨任务混装）
病灶实测：`add` 不带 `--task-id` 时 task_id 缺省 "" ⇒ 落 `_runs/default/_insights/carrier.json`，
rc=0 无告警。修法：除 `init` 外，动作缺 `--task-id` ⇒ **exit 2**（载体按任务隔离）。

### G3 · 洞察载体入闸 1（第 9 项冻结项）
病灶：`sop-stages.md` 写「目标集登记完成前**不得 spawn 任何成员**」，但 `gate1_freeze` 八项
无载体项 ⇒ 跳过 `insights init` 照样放行。修法：新增 `insight_carrier_targets`
（载体已登记 + 目标数），`gate1-check` 校验；留 `--allow-no-carrier` 显式豁免口（纯诊断单用）。

### G4 · 待裁决条目数并入收敛判定
病灶：`no_progress` 只看 verify_deck 的 P0/P1/P2 ⇒ 看不到「冲突挂 5 轮无人裁决」这种
真实不收敛形态（课件 P0 降为 0 ⇒ 机器判已收敛 ⇒ 带着矛盾收口）。
修法：`continue` 读载体 `needs_adjudication` 计数 ⇒ 进质量快照 `pending_adjudications` + 显式告警。

### G5 · 同内容重提的机器提示（`possible_duplicate_of`）
病灶：R2 只查 ID 唯一 ⇒ rejected 的提案换个 `insight_id` 原样再提，rc=0 直接入载体。
修法：同 target + 同轴 + proposal 全同 ⇒ 载体记 `possible_duplicate_of`（**只提示不阻断**——
精确去重是语义判断，仍归人）。

### G1 · 批量注入四前置断言落地（**声明了 8 个月没人读**）
病灶：`references/batch-surgery-sop.md:16-22` 写「注入脚本前置断言（必须实现，缺一即拒跑）」，
而四键 `min_font_pt` / `require_empty_slot` / `max_overlap_ratio` / `sample_review_ratio`
在 `scripts/` 里 **AST 读取点 0 处**；实际注入脚本 `inject_notes.py` 只读 1 个键。
修法：`inject_notes.py` 落地四断言——①读配置（缺则告警+回落，不崩）②注入字号 < min ⇒ 拒写
（`font_below_min`）③空位检测 + 与既有文本框两两求交 > max_overlap_ratio ⇒ 拒写
（`overlap_exceeded` / `no_empty_slot`）④每页输出注入结果清单（页码/坐标/字号/重叠值/写或拒+拒因）。
**唯一源 = `config/visual-rules.yaml#overlay_injection`**（复用既有段，不另立新段）。

### G2 · 图表布局规范（起步：建议级）
病灶：`visual-rules.yaml` **无 chart 段**、`verify_deck` **无图表检查**、量规无条目 ⇒
维度 6「图表布局规范」在配置/门禁/量规三层皆缺。
修法：新增 `chart` 段（图区占比 min/max；`enabled: false` 建议级起步，先积累证据）；
`verify_deck` 新增 `check_chart_layout`（只判**图区面积比**——确定性可判）；
问题类型**不登记进 severity** ⇒ 落 unknown_out（**明示、不阻断**）。

### G7 · 装配体量分段表 + 超阈值告警
病灶：装配产物实测 **71,543 字符**，而 `context.summary_max_chars: 800` 只管**回传摘要**、
管不到**注入体量**；注入逐版叠加 ⇒ 关键纪律有被中后段稀释的风险。
修法：装配器输出分段字符占比；总长超 60,000 告警。⚠ **不自动裁剪**——裁哪段是内容决策，归主理人。

### 本批实测揪出的真缺陷（独立验证发现，非自述）

1. **【P0】G5 标记写错条目**：初版把 G5 块放在 `rec` 定义**之前**而块内引用 `rec`
   ⇒ 首次执行 NameError 被 `except: pass` 静默吞掉；更糟的是**第二次**迭代时 `rec`
   已是**上一轮迭代的残留值** ⇒ 标记被写到**错误的条目**上（实测出现 `s1-C-01` 自指 `s1-C-01`，
   而真正该被提示的 `s1-C-02` 反而没有）。修法：块移到 `rec` 赋值**之后**。
2. **【P1】G4 的 task_id 来源不一致**：`insights init --task-id T-1` 写 `_runs/T-1/`，
   而读取器从 loop 状态取 id（无状态文件 ⇒ `default`）⇒ 载体找不到、待裁决数**恒 0**。
   修法：改为**遍历** `.harness-runs/*/` 全部载体（与 `_insight_carrier_state` 同口径）。
3. **【P1】T1b 反向例的前提被合法改变**：它固定拿 `overlay_injection.*` 当"仍无人读"的样例，
   而 G1 正要让这四键有读取点 ⇒ 删掉人读型登记后它们本就不该变死 ⇒ 反例转红。
   修法：样例段**动态挑选**（当前仍无 AST 读取点者）+ 计数模式兼容标量/列表两种输出形态
   （`seg.` 与 `seg =`）——**不是削弱断言，是让它换个仍成立的样例**。
4. **【P2】双源漂移**：G1 执行者曾新增 `batch_surgery` 段，与既有 `overlay_injection` 段
   四键完全重复 ⇒ 同一纪律两份配置。已统一为复用 `overlay_injection`（`batch_surgery` 归零）。

### 残留（如实登记，未假装已覆盖）

- **图表规范只实现了"图区面积比"**：坐标轴标注字号 / 图例位置 / 表格布局**尚无执行器**
  （需解析 chart XML 与表格形状，判据边界未清）——`config/visual-rules.yaml#chart.unimplemented` 已列明。
- **G1 的"注入框"是虚拟落点**：`inject_notes.py` 只写备注页、没有版面坐标，
  空位/重叠判定按"讲稿要点提升为页内叠加元素时的落点矩形"建模（会话层给坐标，脚本判）。
- **G1 拒写后无"拆页建议"链路**：拒写只记清单，不自动生成拆页建议（拆页是内容决策）。
- **G1 拒写不占名额、顺延下一页**：属口径微调（否则一次拒写会让整册覆盖率缺口被误算）。
- 判环仍为语义判定；`tools_whitelist` 无代码强制力（平台限制）；载体只承载结构与留痕。

---

## [v3.21.1] - 2026-10-26（独立复验新发现：4 个域档案字段从未进快照 → 补接线）

> v3.21.0 发布后的**第 3 轮独立复验**（跨专业复用真实可用性）里发现的第 24 个
> 「声明未接线」点。本版只做这一件事，不夹带其他改动。

### 病灶（AST 实测，可复现）
`config/domain-profiles.yaml` 的域档案里有 **4 个字段在 `scripts/` 里 0 处读取点**：
`depth_scale_source` / `audience_profile` / `course_module_templates` / `user_supplied_sources`
⇒ 它们配了、却**从未进坍缩快照** ⇒ 装配产物里没有 ⇒ 成员拿不到：

| 字段 | 缺了会怎样 | 直接命中管家节点的哪条诉求 |
|---|---|---|
| `depth_scale_source` | **深度三档的出处**（= 该专业教学标准的要求用词）缺失 ⇒ 深度要求无据可依 | 维度 10「用专业标准耦合 PPT 诊断」 |
| `audience_profile` | 四层受众的差异（层说明/数据要求/病例形态/岗位语境）缺失 | 维度 6「PPT 制作颗粒度」 |
| `course_module_templates` | 该域的模块/页序模板缺失 ⇒ 模块化优化没有现成骨架 | 维度 5「工作流链路」 |
| `user_supplied_sources` | 用户指定源策略（优先级/冲突/可追溯）缺失 | 维度 13「联网权威资源编排」 |

### 修复
- `scripts/harness.py` 坍缩快照补 4 个字段
- `scripts/assemble_domain_prompt.py` 新增四段渲染：
  【二之二、深度三档的出处（专业标准要求）】/【二之三、受众分层（本域差异）】/
  【二之四、模块/页序模板（本域现成骨架）】/【二之五、用户指定源策略】
- 版本号 12 处 → 3.21.1

### 验证
- AST 读取点：4 键各由 **0 处 → 2 处**（harness.py 快照 + 装配器渲染）
- 跨专业复用端到端复验（用 `references/domain-profile-template.md` 的「医学影像技术」样例，
  注入临时域档案 → route → confirm → 装配）：装配 rc=0，四段全部出现在产物里，
  且**教育部《医学影像技术专业教学标准》**、核心课程「医学影像检查技术」、岗位语境、
  「影像专题课十模块」均已渲染 ⇒ **专业标准真的接进了 PPT 诊断与设计**
- 全量 pytest + ensure_settings 全量门禁

---

## [v3.21.0] - 2026-10-26（多专家单载体 + 13 维度独立诊断的 9 项修复）

> 本版两件事：① 完成 v3.19.2 递延的 **G-C 多专家单载体**立项（洞察载体落地）；
> ② 按管家节点要求做了一次**独立从零诊断**（13 维度），并据诊断结论修掉 9 项短板。
> 诊断报告全文：`04-test/v3.21.0-13维度独立诊断与对齐方案.md`（工作区）。

### ① 多专家单载体（围绕同一份给定内容做洞察和设计）

管家节点的设计意图原文：**「围绕给定模块内容或给定 PPT 的内容进行多专家洞察和设计」**。
管家节点裁决两项口径：**全链汇入**（闸1 后建载体，闸2/闸3 全程写回）+ **module 严格指教学知识模块/章节**。

**病灶（真实，非假设）**：闸 2「严真奥 → 苏学法」与闸 3「苏学法 ∥ 屠明熙」并行，
但产物落**三处**（`evidence/证据包.md`、`<task_id>__pedagogy-architect.md`、`_search_requests/*.md`）
⇒ 同一目标的内容/教学/视觉建议**分散无共同落点**：冲突无处显形、合并靠 800 字摘要（必然丢信息）、追溯断裂。

**★ 关键张力与解法**：现有纪律「并行任务边界必须互斥无交集」⟷ 用户要的「多专家围绕同一份内容」。
解法 = **目标上互斥、载体上共享**：同轴内不重复做（那才是重复劳动），同一目标上多轴并存
（三轴看同一份内容的三个侧面，合起来才是完整洞察）。脚本只检出「多轴并存 ⇒ 待人工裁决」，
**不判是否冲突**（语义判断归人）。

**落地**：
- 新增 `references/insight-carrier.yaml`（schema 唯一源）+ `scripts/insight_carrier.py`（判定层，纯函数）
- `harness.py` 新增 `insights` 子命令组 6 个动作：`init`/`add`/`merge`/`verify`/`render`/`freeze`
- 三份成员 MD 增「洞察载体写入契约」段；`assemble_domain_prompt.py` 注入载体段
  （**注入是唯一合法路径**——人设不注入，规范就不会被遵守）
- 轮报六项的第 1、2 项改为**从载体投影**（两处各写 = 两份真相，冻结 digest 也就失去意义）

### ② 13 维度独立诊断 → 9 项修复（每项都有可复现证据）

| # | 修复项 | 诊断维度 | 证据（可复现） |
|---|---|---|---|
| F1 | **收口载体半成品**：修 3 死配置（`insight_carrier.axes.*`）＋ `detect_conflicts` 缺 cfg 兜底（R1 静默不执行）＋ 修 `add` 是"替换"非"合并"（第二个分片冲掉第一个） | 2/4/5 | 第 18 项 rc=1 阻断；verify 时 needs_adjudication 恒空 |
| F2 | **版本号收口**：12 处 → 3.21.0 | 全局 | CHANGELOG 已写 v3.21.0 段而 plugin.json 停在 3.20.0 |
| F3 | **doctor 表补 `gate1-check`** | 4/9 | argparse 23 个子命令 vs doctor 表 22 个（闸1 自检对 LLM 冷启动不可见） |
| F4 | **语言判据接线**：`english_allowed_when`/`english_minimum` 注入成员 prompt | 6 | 二者 AST 读取点 **0 处**（"极少数场景做英语 PPT"只有配置声明、无执行面） |
| F5 | **页脚字号档**（`font.footer_min_pt` 8.0 / `footer_max_chars` 40） | 6/8 | 字号检查只分标题/图注/正文三类，**无页脚档** ⇒ 页脚 8pt 被按 12pt 判 P0 硬阻断（实测 20 页造 20 条 P0；P0 总数 121→51，而 11pt 真正文违规 10 条**完整保留**） |
| F6 | **跨专业复用**：新增 `references/domain-profile-template.md`（域档案生成模板，含"医学影像技术"完整样例）+ `references/standards-collection-sop.md`（专业标准收录 SOP） | 1/10 | 域档案只有 3 个、standards 只有 1 个 ⇒ 新主题无档案时坍缩退化为通用兜底人格 |
| F7 | **L1 通道重试**（指数退避；4xx 不重试、5xx/429/网络错重试） | 11/13 | `fetch_authority.py:136` 是单次 urlopen（无 retry/attempt）；同包有跨通道降级链但**同通道内无重试** |
| F8 | **`pending_work` 覆盖闸 4.5** | 5/12 | 只查 loopB 未终止与 task.current_stage≠0，不查 cases_library 的 unverified 条目 |
| F9 | **白名单定位正名** | 9 | `tools_whitelist`/`writes_allowed` AST 读取点 0 处——**平台结构性限制**（spawn 恒为 general-purpose），只能正名为"职责边界声明"；preflight 显式告知，并列出真正有强制力的代码层防线 |

### ③ 本批实测揪出的真缺陷（均由独立验证发现，非自述）

1. **【P0】标量接口被破坏 ⇒ 开关恒真**：`enabled()` 等 5 个函数曾返回 `(值, 回落标志)` 元组，
   调用点 `if not enabled(...)` ⇒ **非空元组恒真 ⇒ 环启用检查永不拦截**。「接线了却不设防」比没接线更危险。
2. **【P0】`add` 是替换不是合并**：载体形态被当分片形态传给 `merge_parts`（`entries` 取空）⇒
   原有条目全丢 ⇒ **不同 ID 的条目被静默覆盖**——正是"不静默覆盖"纪律的反面。
3. **【P1】`detect_conflicts` 缺 cfg 兜底**：加了 R1 参数化却没让判据拿到配置 ⇒ **R1 静默不执行**。
4. **【P1】F4 注入污染既有段口径**：判据写成 `  - ` 放进【六之二】段 ⇒ 词条计数 32≠29 ⇒
   **既有护栏失败**。修法：判据另起【六之三】段（不污染老段）。
5. **【P2】成员 MD 契约段插入位置错误**：按 `^##+ .*交接方式` 定位失配（「交接方式」是段内加粗行不是标题）
   ⇒ fallback 把段插到**文首**、打断成员 MD 正文结构 ⇒ 域上下文不渲染。
6. **【P2】版本漂移** + **【P2】doctor 漏 `gate1-check`**（见上表）。

### ④ 诚实边界（本版不宣称的能力）

- 判环（`loop_a.trigger`/`loop_b.trigger`）**仍是语义判定**，代码不判。
- `delta_gate.insert_font_at_creation` **结构性不可判定**（写入时行为，成品文件态无痕迹）。
- `tools_whitelist`/`writes_allowed` **无代码强制力**（平台限制）；真正有强制力的是
  原件只读、目录越界写前校验、状态单写者、两环不覆盖四条**代码层**防线。
- 载体只承载**结构与留痕**，不承载质量判断；"是否冲突"归人。
- 配图"精准匹配"属语义判断，只能靠素材判读红线（人工），本版**未提出机器方案**。
- 会话层工具（pubmed 检索 / fetch 抓取 / Ima 检索）本批**未做端到端实调**（只核到登记级可用）；
  Ima 凭据未配置时探针如实报"降级走联网现查机构权威源"。

---

## [v3.21.0] - 2026-10-26（多专家单载体：围绕同一份给定内容做洞察和设计）

> **起因（管家节点裁决）**：G-C「多专家单载体」自 v3.19.2 登记递延，本版立项落地。
> 管家节点的设计意图原文：**「围绕给定模块内容或给定 PPT 的内容进行多专家洞察和设计」**。

### ★ 结论：多专家的洞察与设计汇入**同一份载体**，载体是全程唯一事实源

| 决策项 | 管家节点裁决 |
|---|---|
| 载体挂在哪一层 | **全链汇入**——闸 1 后建载体，闸 2（设计）与闸 3（成稿/迭代）的洞察、设计、返修都写回同一载体 |
| 「模块」的粒度 | **只指教学知识模块/章节**（教材章节级）——**不是**任意文本片段 |

### ① 病灶（真实，非假设）

闸 2「严真奥 → 苏学法」与闸 3「苏学法 ∥ 屠明熙」并行，但**产物落三处**：
`evidence/证据包.md`、`<task_id>__pedagogy-architect.md`、`_search_requests/*.md`。
⇒ 同一页/同一模块的**内容 / 教学 / 视觉**建议分散无共同落点，三连后果：
① **冲突无处显形**（严真奥要加证据、苏学法要拆页、屠明熙要加图，三者可能互斥）；
② 主理人合并靠 `context.summary_max_chars`（800 字）摘要 ⇒ **必然丢信息**；
③ **追溯断裂**（这条洞察谁提的、改没改、为何没改，散在三处）。

### ② 关键张力与解法（本版最要紧的一条）

现有纪律「并行 spawn 时任务边界必须互斥无交集」 ⟷ 管家节点要的「多专家围绕同一份内容」。
**表面矛盾。解法 = 目标上互斥、载体上共享**：

| | 什么互斥 | 什么共享 | 为什么 |
|---|---|---|---|
| 旧纪律 | 任务边界互斥无交集 | — | 防重复劳动与覆盖缺口 |
| 本版 | **同轴内**不重复做 | **同一目标**上的多轴条目并存 | 三轴看的是同一份内容的三个侧面，合起来才是完整洞察 |

⚠ 载体**共享 ≠ 并行**：闸 2 实为**串行**（苏学法依赖严真奥的证据包，v3.17.0 修正），
闸 3 才**真并行**。并行时两方同时写同一文件会丢更新（本包 `_StateLock` 的由来），
故：**专家各写各的分片 → 脚本合并 → 下游只认合并后的载体**。

### ③ 落地面

- **新增 `references/insight-carrier.yaml`**：载体 schema 的**唯一数据源**
  （字段 / 枚举 / 规则 / ID 格式 / 必填性）。`config/harness.yaml#insight_carrier` 只放**编排参数**
  （路径约定、轴↔成员映射、阻断策略、轮报投影项）——**两处不重复定义**，防双源漂移。
- **新增 `scripts/insight_carrier.py`**：判定层（纯函数、全配置驱动、禁硬编码、缺键告警+显式回落），
  与 `scripts/loop_contract.py` 同构。**只判结构**：字段/枚举/唯一性/多轴并存/裁决留痕/digest；
  **不判语义**——"是否互斥""洞察好不好"归人。
- **`harness.py` 新增 `insights` 子命令组**（6 个动作）：
  `init`（登记目标集）/`add`（合并分片）/`merge`（合并全部分片）/`verify`（结构校验 + 冲突检出）/
  `render`（渲染轮报第 1、2 项）/`freeze`（稳定 digest 写回载体）。
- **三份成员 MD 的落盘契约改造**：各自写 `<RUN_DIR>/_insights/parts/<member_id>__<axis>.json`；
  **保留**原有专业产物（证据包 / 教学蓝图 / 检索单照旧写）——载体是**洞察的汇入通道**，不是取代产物。
- **装配器注入**（`assemble_domain_prompt.py`）：把载体路径 + 分片骨架 + "只写自己轴"的纪律
  注入成员 prompt（注入是唯一合法路径——人设不注入，规范就不会被遵守）。
- **阶段契约接入**（`references/sop-stages.md`）：闸 1 建载体（**目标集登记完成前不得 spawn 成员**）、
  闸 2/闸 3 写回载体、闸 4 冻结 + 轮报投影。
- **轮报六项的第 1、2 项改为从载体渲染**——两处各写就是两份真相，冻结的 digest 也就失去意义。

### ④ 目标粒度口径（管家节点已裁决，禁自造）

- `--kind page` ⇒ **稳定页面 ID**（如 `s12`）
- `--kind module` ⇒ **教学知识模块/章节**（教材章节级，如"禽流感 HA 糖基化与宿主适应"）——
  用户丢一段话要加工时，**先归入某个模块再登记**，不新开第三种形态。

### ⑤ 载体条目 ≠ Loop B 条目（两层，别混）

- **载体条目 = 洞察**（谁提的、依据、裁决状态）——是待改条目的**上游**；
- **Loop B 条目 = 待改对象**（file + sha256 + decision，冻结对象）；
- **衔接**：载体条目裁决为 `accepted` 后，主理人用 `loop add-item` 登记为待改条目。
- Loop A（改专家团）**不涉及载体**——载体的目标集是"用户给定的内容"，不是专家团自身。

### ⑥ 诚实边界（本版不宣称的能力）

- 脚本**只检出「同一目标上多轴并存 ⇒ 待人工裁决」，不判是否互斥**——"严真奥要加证据"与
  "苏学法要拆页"是否冲突是**语义判断**，归主理人与用户。
- 载体承载**结构与留痕**，不承载质量判断。
- 未裁决的冲突**不得带着往下走**（`insights verify` exit 1）——但"如何裁决"仍归人。
- 载体**不替代**各成员的专业产物（证据包 / 蓝图 / 检索单照旧）。

---

## [v3.20.0] - 2026-10-26（33 键「声明未接线」收口：判据层从 Markdown 下沉为代码）

> **起因**：v3.19.3 的 L3 逐键定性在 75 个死配置里确认了一个结构性事实——
> `config/harness.yaml` 的 `loop_a`(4) + `loop_b`(20) + `delta_gate`(9) = **33 键**
> **整批"配了但没有任何代码读取者"**。v3.9.0「双层 Loop 契约下沉批」只把**动作层**
> 下沉为代码（loop 子命令 13 个动作），而 yaml 里的**默认值段 / 轮审判据 /
> 增量门禁判据**三类仍躺在配置里当 Markdown 纪律用。
> 本版把其中**可判定的 32 键**全部落为代码判定，剩 3 键据实标注为不可判定。

### ★ 结论：32 键已接线，3 键据实标注不可判定（不伪造执行器）

| 段 | 键数 | 处置 | 执行面 |
|---|---|---|---|
| `loop_a` | 5（含 `enabled`） | 全接线 | 批次门（先确认/最小补丁/回归必跑）+ 环开关 + 状态路径 |
| `loop_b` | 21（含 `enabled`） | 全接线 | 单写者/原件只读/并存守卫/轮审五判据/检索预算/默认档 |
| `delta_gate` | 9 | **8 接线 + 1 不可判定** | 基线字段/自引入阻断/报告格式守恒/空间审计/判读留痕/图注挂账 |
| 合计 | 34 | 32 接线 + 2 不可判定（`trigger`×2 属语义判定，`insert_font_at_creation` 属写入时行为） | |

### ① 新增 `scripts/loop_contract.py`：判定层唯一源（795 行）

- **纯函数、全配置驱动、禁硬编码**：阈值、字段名、格式串、路径一律从 `config/harness.yaml` 读；
  缺键/空值/非法值一律**告警 + 显式回落**，回落写进 `notes` 由调用方透出（静默回落 = 不设防）。
- **只做确定性判定**：路径解析、集合比对、计数、格式与守恒校验。
  "最小到什么程度算最小""判读是否属实"仍归人与 LLM——**不宣称自己判了**。
- **回落表刻意用元组列表而非字典字面量**（`_FALLBACK = [(k, v), ...]` + `_FB = dict(_FALLBACK)`）：
  `ensure_settings` 第 18 项用 AST 收集真实读取点，其中第③种形态是**字典字面量的字符串键**——
  若回落表写成字典，它会被当成"有代码读取者"，于是**回落表自己把死配置刷成绿色**。

### ② `scripts/harness.py`：loop 子命令从 13 动作扩到 23 动作

新增 **Loop A 批次门**（`batch-open` / `batch-close` / `batch-status`）——
此前 `confirm_before_each_batch` / `patch_discipline` / `regression_required` 三个键
**零读取者**（把它们改成 false 不会有任何行为变化）。
`batch-close` 三条判据：① 未 `--confirmed` → exit 1；② `regression_required` 没跑齐 → exit 1；
③ `patch_discipline=minimal` → 用 `git status` 比对**实际改动集合 ⊆ 声明集合**。
⚠ ③ 判的是"有没有超出声明范围"，**不是**"改得多不多"；包目录非 git 仓库时**不做比对并显式告警**。

新增 **Loop B 判据动作**（`review` / `retrieval` / `baseline` / `delta` / `geo-baseline` / `defaults`）：
- `review`：轮报六项齐全才让 `continue` 进位（此前只是文档纪律）
- `retrieval`：每轮检索次数计数，超 `retrieval_budget_per_round` 即拦（此前该键零命中）
- `baseline`：基线字段按 `delta_gate.baseline_fields` 逐项校验，**字段名来自配置**（加字段不用改代码）
- `delta`：自引入新缺陷阻断 + 报告格式守恒校验（`P0 = 基线 + 自引入`）+ 空间审计
- `defaults`：打印默认档 + 引用文件存在性核验 + 生成 intake 待确认模板
  （**全部 status=suggested** —— 制作前置门只认 confirmed，"不得用仓库默认值冒充用户确认"由代码保证）

### ③ 修一处真实漂移：Loop A 状态文件路径

配置写 `<包>/.workbuddy/loopA_state.json`，代码此前硬写 `<工作区>/.workbuddy/loopA_state.json`
——改配置不改行为。Loop B 两者恰好同值，故此漂移长期无人发现。

### ④ 第 18 项从「提示不阻断」改为「阻断」

v3.19.2 就报出了这 33 键，但因为**只提示不阻断**，它们在随后三轮里**反复被重新发现、反复未被处置**
（v3.19.2 → v3.19.3 登记 → v3.19.4 逐键定性 → v3.20.0 才接线）。
不阻断 ⇒ 每次都是"下次再说" ⇒ 核心禁忌永远清不干净。
基线已归零后再出现死键，只可能是**新增**（新增配置忘接线 / 新增人读型忘登记），两种都须当次处置。

### ⑤ 撤销 `loop_a`/`loop_b`/`delta_gate` 整段的人读型登记

只保留 3 个确属不可判定的键，用带文件前缀的限定路径登记：
`harness.loop_a.trigger` / `harness.loop_b.trigger`（判环是**语义判定**，代码不判环）、
`harness.delta_gate.insert_font_at_creation`（"创建时即设字体"是**写入时行为**，
成品文件态无痕迹，与 OOXML 病例 API-001 同型，**结构性不可判定**）。
⚠ 执行面与不可判定面**不得混说**——不得因某键出现在输出里就宣称已由代码强制。

### ⑥ 本批实测揪出的 3 个真缺陷（均由成员/独立验证发现，非自述）

1. **标量接口被破坏 ⇒ 开关恒真（最严重）**：`enabled()` 等 5 个函数一度返回 `(值, 是否回落)` 元组，
   而调用点是 `if not enabled(...)` —— **非空元组恒真 ⇒ 环启用检查永不拦截**。
   "接线了却不设防"，比没接线更危险。现统一为标量，并在 `--self-check` 加了 6 项**类型守卫**。
2. **`retrieval_check` 直接 TypeError**：`limit = retrieval_budget(cfg, notes)` 拿到元组就比大小。
3. **`image_caption_requires_reading=false` 关不掉**：同上，`if not required:` 分支是死代码。

三条都已由 `scripts/test_loop_contract.py`（87 例）加了**形态守卫**，下次同类缺陷在测试阶段就红。

### ⑦ 版本号同步：10 处 → **12 处**

新增 `config/language-profile.yaml` 与 `config/external-tools.yaml` 两处——它们带 `version` 键却
**不在第 14 项巡检清单**（v3.19.0 新增文件时漏了巡检）。与第 14 项自己踩过的坑完全同型
（4 处 → 8 处 → 10 处，每次都是"新发现一处漏掉"）。

### ⑧ 文档追不上代码：`dual-loop-governance.md` §2 重写

原文写"以上三条是配置声明 + 文档契约，不是代码级强制——`harness.py` 尚未实现
`loop_a.forbidden_paths` 的写前校验"——**这句话自 v3.9.0 起就是错的**（`loop check-path` 已实现）。
现改为逐条标注**实际强制面**：授权不互通=否（语义判定）/ 状态不互通=是 / 目录不互通=是（非沙箱）/
单写者=是（不防冒名）/ 环总开关=是。**不得对外宣称"两环隔离已由代码完全强制"**。

### 独立验证（16 条「改配置 → 行为跟着变」，全部通过）

驱动真实 CLI（被测 harness.py 与被改 yaml **同源**，在临时副本里跑）：

| 判据 | 反例 | 结果 |
|---|---|---|
| `loop_b.enabled` | 置 false | `status` 被拒（exit 1）✓ |
| `loop_b.single_writer` | 改成他人 | 写动作被拒；改回则放行（不误杀）✓ |
| `loop_b.coexist_with` | 撞 `state_file` | `start` 被拒（exit 2，不覆盖 task_state）✓ |
| `loop_b.round_review.required` | 置 false | `continue` 不再因缺轮报被拦 ✓ |
| `loop_b.budgets.retrieval_budget_per_round` | 改 10 | 第 11 次检索被拦；上限 30 则不拦 ✓ |
| `delta_gate.baseline_fields` | 加 `export_pages` | 旧数据立刻判缺（字段名真来自配置）✓ |
| `delta_gate.report_format` | 改格式串 | 报告行跟着变 ✓ |
| `delta_gate.insert_spatial_audit` | 拿不出 lint 报告 | 按**未做**阻断（不是放行）✓ |
| `delta_gate.miss_needs_human_review` | 基线缺字段 | 不按 0 处理，转人工复核 ✓ |
| `loop_b.defaults.*` | 改受众等 | intake 模板内容跟着变，且 **status 全为 suggested** ✓ |

### 诚实边界（本版不宣称的能力）

- ① `loop_a.trigger` / `loop_b.trigger`：**判环是语义判定**，代码不判——"这句话在改专家团还是在改课件"
  由主理人追问（dual-loop-governance §1 的追问表）。
- ② `delta_gate.insert_font_at_creation`：**结构性不可判定**（写入时行为，成品文件态无痕迹）。
- ③ `single_writer` **不防冒名**：平台无身份认证，成员照样可传 `--actor team-lead`。
- ④ `check-path` **不是沙箱**：拦不住成员绕开脚本直接写文件（平台无 hook）。
- ⑤ 判据层只做确定性判定，**不判内容的专业对错**。

---

## [v3.19.4] - 2026-10-25（35 键逐键独立定性：抓出 3 个被批量登记埋没的漏消费）

> **起因**：v3.19.3 的 L3 用「段名批量登记」把 75 死键压到 0。批量高效，
> 但**可能掩盖个别键的真实情况**——本轮把当时未逐个性定的 35 键全部独立定性，
> 验证批量登记是否埋没了「本该接线的漏消费」。

### ★ 结论：批量登记确实埋没了 3 个真缺陷

35 键中 **3 键是漏消费（B 类，已接线）**，32 键确属人读型（A 类，登记正确）。

### ① 【P0】`domain_config.yaml#image_fetch.license_uncertain_markers`（最重发现）

yaml 声明 `['待核实','未明','未知','待定']`，而 `scripts/fetch_oa_image.py:266`
**硬编码** `("待核实","未明","未知","待定")` ——**配置写了、代码硬编码同值**
⇒ 改配置不改行为。**与 v3.12.0 修掉的 `three_source_check` 阈值硬编码完全同型**。

v3.19.3 把它登记为人读型的理由写的是「供成员判断许可是否可信，语义判断不由脚本做」
——**该理由不成立**：`fetch_oa_image.py` 正是脚本侧做许可判定的地方，它本该读这个配置。

**修复**：新增 `license_uncertain_markers(cfg)`，与既有 `retry_spec()` 同模式
（优先 yaml，读不到回落内置值并**告警**，不静默）。反例：改 yaml ⇒ 读到值跟着变。

### ② 【P1】`visual-rules.yaml#gate.write_gate_level` / `#gate.deliver_gate_level`（双份真相）

yaml 声明 sweep 写回门禁 = P0、gate 交付门禁 = all；而 `harness.py:5456/5474` 的
argparse `default` 是**硬编码** `"P0"`/`"all"` ——同值但互不知晓。

**修复**：新增 `_default_gate_level(key, fallback)`，两处默认值改从 yaml 读；
读不到/值非法回落并**告警**。反例：改 yaml ⇒ 默认等级跟着变；路径不存在 ⇒ 告警不静默。

### ③ 其余 32 键逐条核实为 A 类（批量登记正确）

逐条依据见 `04-test/v3.19.4-35键定性表.md`。其中两条澄清：
- `overlay_injection.*` 4 键的 LLM 消费方**确认存在**（visual-slide-designer.md /
  ppt-producer.md / batch-surgery-sop.md 均引用）⇒ A 类正确；
- `overlay_injection.max_overlap_ratio` 与**活键** `geometry.overlap_ratio`
  （被 verify_deck.py:165 消费）是**两个不同键**，勿混。

### ④ 方法论沉淀（本轮最值钱的产出）

**批量登记后必须做「反向抽查」**：对每个键问——
「**如果这个值改了，哪个脚本的行为应该跟着变？**」
答不上来的才是真 A 类；答得上来却没接线的就是 B 类。
本轮正是用这个问句抓出了 3 个被压平的缺陷。

### ④-bis 破坏性反例中补强的两处（第 3 轮检查）

反例验证时发现并修掉**两个测试/实现缺口**（这正是破坏性反例的价值）：

1. **T6 假绿**：首版只断言返回值，而 `write_gate_level` 的回退值恰好也是 `"P0"`
   ⇒ 把接线改坏后走回退仍返回 "P0"，断言照样通过。补强：**同时断言「无告警」**
   （真读到 yaml 就不该往 stderr 写东西）。
2. **`_default_gate_level` 静默回落缺口**：首版只在**值非法**时告警，
   **键缺失/取到空**时静默走回落 ⇒ 破坏性反例抓出。修复：三种失败形态
   （读不到文件 / 键缺失 / 值非法）**全部告警**。
   ⇒ 复验：三种形态分别注入 ⇒ T6 **全部变红**（守卫真正有效）。

> 教训（第三轮复现）：**反例必须破坏到「被测对象本身」**——我曾把 argparse 的
> `default=` 改回硬编码，但 T6 测的是 `_default_gate_level()` 函数，破坏调用点
> 对函数毫无影响 ⇒ 反例假阴性。破坏前先确认「破坏的是被测路径」。

### 回归

`pytest scripts/` **223 passed / 3 skipped**（基线 218 → +5，零失败）；
`test_dead_config_disposition.py` 6 → **11 用例**（新增 T5/T5b/T6/T6b/T7，含 3 反例）；
validate_expert 0 errors · 体检 24/24（rc=0）· 双树 0 差异。

---

## [v3.19.3] - 2026-10-25（第八轮：H1/M1/M2 落地 + L3 死配置 75 键全量处置）

> **执行方式**：轻量型快速通道。子代理 `agent-harness-coder` 派出后先落盘第一步
> （第 18 项全量输出，已被主理人误提交进 d650d66），后续**因网络 socket 错误失败**
> ⇒ 按撞限协议由**主理人接管**完成第二步/第三步。阶段产出未经成员产出，已披露。

### ① 【P0】第 18 项人读型白名单机制**全面失效**（L3 确证的核心判据缺陷）

三条证据链（均实跑）：
- `known_textual` 登记的是**段名**（`overlay_injection`），而 walk 判据查**末段键名**
  （`max_overlap_ratio`）⇒ 永不匹配，登记形同虚设；
- `path_prefixes` 是**硬编码 7 个老段**元组，不含任何 v3.19.0 新增段 ⇒ `seg_hit` 兜底也失效；
- 结果：v3.19.3 批次3 声称"已登记人读型"的 4 组键，**实际全部仍在 dead 清单里**
  ——体检第 18 项自己没守住自己的白名单。

**修复**：
- 判据新增 `_is_textual()`：末段键名命中 **或** 任一路径前缀段命中 **或** 带文件前缀的限定路径命中
  （如 `visual-rules.gate` 只豁免该文件的 gate 段，避免与 `harness.yaml#gate.*` 混淆）；
- `path_prefixes` 改为**自动派生** = 原 7 段 ∪ known_textual 中的裸段名。

### ② 【P0】75 键全量定性（结构发现：33 键整批"声明了但没接线"）

**结构性结论**：`loop_a`(4) + `loop_b`(20) + `delta_gate`(9) = **33 键 / 占 75 键的 44%**
整批声明未接线。根因：v3.9.0「双层 Loop 契约下沉批」只把**动作层**下沉为代码
（loop 子命令 13 个动作），而 yaml 里的**默认值段 / 轮次复核判据 / delta 门禁判据**
三类仍是纯声明（代码字面量 0 处；`delta_gate` 在 harness.py 的 2 次出现是文件头 docstring）。

**处置（75 键逐条，理由据实）**：
- 33 键 → 登记人读型，理由写「**声明未接线**」（不谎称"由会话层消费"）；
  实际接线留 v3.20.0（残留登记·中严重度）；
- 5 键（`stages.0..4.next`）→ 人读型顺序说明（`next_stage` 代码 0 次），
  **另加第 24 项漂移守卫**防双份真相；
- 2 键（`caption_five_elements` / `caption_base_elements_note`）→ v3.19.0 G4 明确标注的
  **历史键**（向后兼容保留，不可删）；
- 其余按段名/限定路径登记（ima / standards / channels / terminology /
  english_allowed_when / consistency / english_minimum / visual-rules.gate /
  collapse / observability / report_only / license_uncertain_markers）。

**结果**：第 18 项 **75 → 0**（人读型登记 211 → 309），且全量输出不再截断
（原只列前 12 条，其余 63 条**永远不可见** = 体检项形同虚设）。

### ③ 【P1】新增第 24 项：阶段顺序漂移守卫（阻断）

`stages.{i}.next == i+1`（末级为 None）。理由：yaml 的 `next` 与代码的
`current_stage+1` 是**同一事实的两处写法**，不一致即「配置说走 A、代码走 B」的静默分叉。
⚠ **守卫首版踩坑记录**：YAML 的 `0:` 键被解析成 **int**，`stages.get("0")` 恒取到 None
⇒ 把「所有 next 都是 None」误报成漂移（**假红**）。harness.py 里早有同款归一化注释，
未参照 ⇒ 修正为 `{str(k): v for k, v in stages.items()}`。**教训：写守卫先看同文件已有的同类归一化。**

### ④ H1 / M1 / M2（上一轮核对发现的 2 处未闭环项，本轮落地）

- **H1**：OneDrive 镜像 `GPT/Claude/vet-med-ppt-team` 从 9cfd228 (v3.15.0)
  fast-forward 到 d650d66 (v3.19.2)，180 → 238 文件，v3.16–3.19 全部资产到位。
  **该镜像有 origin remote（同一 GitHub 仓库）⇒ 直接 git pull，无需 rsync**。
  三副本（私有源 / 镜像 / GitHub）现全为 d650d66，逐字节 0 差异。
- **M1**：补 `docs/v3.19.2-verification-report.md`（前三版都有独立报告，唯 v3.19.2 缺
  = 审计链断一环）。
- **M2**：2 份 v3.17.0 批次历史报告经 diff 核实**包内无对应资产（非重复）**⇒ 补入 docs/；
  删项目侧空目录 `03-code/`；项目侧 `04-test/` 补 v3.19.2 报告 ⇒ **5 份报告双向 sha256 一致**。

### ⑤ 主理人失误记录（已入日志）

**成员并行工作时用 `git add -A`，把 coder 正在进行的改动卷入了 d650d66**。
⇒ 纪律：成员并行期间，提交必须**按文件精确 add**，禁止 `git add -A`。

### 回归

`pytest scripts/` **218 passed / 3 skipped**（基线 212 → +6，零失败）；
新增 `scripts/test_dead_config_disposition.py` 6 用例全绿，**含 3 个反例**：
- T1b 去掉段名登记 ⇒ overlay_injection.* 4 键**重现**（证明登记真实生效，非假绿）；
- T3b 注入 stages.2.next=5 ⇒ 第 24 项**精确报红**；
- T4 75 键处置后残留 = 0。
validate_expert 0 errors · 体检 **24/24** · 双树 0 差异。

---

## [v3.19.2] - 2026-10-25（第七次从零诊断 · 前六轮未覆盖取证面 + 2 低严重度收口）

> **诊断性质**：不沿用任何历史结论，与前六轮的实质差异在取证面——
> ① L2 会话层 MCP 真实可调性（ToolSearch 实探 4 工具，全部可发现且 schema 完整）；
> ② 全包死链扫描（428 处引用，0 真死链）；③ business-training 域端到端实战
> （route→confirm→assemble 全 rc=0，2 专家段/库零泄漏/术语表 21/21/换库提醒在位）
> ⇒ **第五轮登记的"另两域实战未验"就此清账**；④ MD 引用锚点 vs 配置真键全扫（15 处全为正则误报）。

> **诚实披露——本轮自查纠正 3 次误报**：glossary"实渲 63≠21"实为跨段计数噪声（段内精确一致）；
> "user_supplied_sources 无消费"实为搜错词（真名 --source-json，已实现且含校验+未确认阻断）；
> 死链/锚点扫描各 1 类正则误报。**每条经二次核实后反转，未进问题清单。**

> **结论：13 维度零高/中新短板**——v3.17→v3.19.1 五轮修复未回归，基线 212 passed 完好。

### ① 【低·G-A】fetch_authority 的 --source-json / --record 调用指引缺失

功能已实现（用户指定源优先 + access≠confirmed 阻断 rc=4 + L2 实调回填记账）但
任何 agent MD 里**零调用示例** ⇒ 有变成"死功能"的风险。补两处指引：
dvm.md Ima 调用规程增 3 行（sources.json 形态 + 阻断语义 + --record 回填）；
team-lead.md 闸4.5 行增 1 处工具引用。

### ② 【低·G-B】体检第 18 项同键多值重复虚增

walk 对列表每个标量项走同一路径 ⇒ `license_uncertain_markers` 4 枚举值计 4 条、
`channels[].probe` 7 通道计 7 条——13 条展示中 9 条是重复虚增，**稀释真长尾信号**。
修法：展示与计数按**唯一路径**算（同键多值只报 1 次，标注枚举值个数）；103 → **75 唯一键**
（另 28 条重复正确分离）。反例：构造 4 值列表 + 1 标量的 yaml ⇒ 报 2 键而非 5，附"共 4 个枚举值"。

### ③ 【结构性·递延（管家节点已裁决）】G-C 多专家单载体 → v3.20.0 单独立项

4 子专家（avian_virologist 等）共用 dvm-content-expert 一个 agent——当前"分段注入"机制
实测有效，但"真多 agent"需拆 4 个 MD + plugin.json agents 数组 + spawn 编制 + 预算 +
信封路由全套变更。**本轮仅登记不动架构**，v3.20.0 主任务。

### 回归

`pytest scripts/` **212 passed / 3 skipped**（零失败）；validate_expert 0 errors；
体检 23/23（第 18 项 103→75 唯一键 + 28 重复分离标注）；版本 10 处一致 3.19.2。

---

## [v3.19.1] - 2026-10-25（第六次从零诊断 · v3.19.0 发布后复核：修迁移回归）

> **诊断性质**：发布后独立复核（不沿用历史结论），重点攻**v3.19.0 新增机制自身的缺陷面**
> （新代码 = 新风险）。13 维度逐项重新实测，**全部证据为本机实跑**。
> **执行方式**：Agent Harness 专家团轻量型快速通道；子代理 `agent-harness-coder`
> 派出后 11 分钟零落盘（Token Plan 429 同型）⇒ 判定卡死，**主理人接管实施**。

### 诊断期实测证据（本轮新增）

1. **标题字号接线零误报**（消险结论）：真实课件 `Research/H10/H10.pptx`（34 页）跑 verify_deck，
   问题分布 = 缺备注 17 / 元素重叠 14 / 主框密度 2 / 配色 1 / 越界 2 / 课时 1 / 缺目录 1 / 缺题页 1，
   **「标题字号」0 条** ⇒ v3.19.0 新接的 `title_min_pt=28` 阈值不产生假红。
2. **S1 回归实锤**：端到端（route→confirm→assemble）产物【五、知识库路由】渲染
   「本域无账号内知识库——…严禁静默回落」，**同屏**又写「说明：本域库路由见 external-tools.yaml」
   ⇒ **自相矛盾且与事实相反**（animal-medicine 实有 7 库）；【六之二】交付语言/术语表段**完全缺失**。
3. **取证脚本自身错误已否决**：实测④的 rc=0 是 `| python3 -c` **管道吞退出码**，直接跑 rc=4 正确
   ——非产品缺陷（记录此教训：退出码断言必须直接跑，不用管道）。
4. 其余 12 维度逐项复验**无新缺陷**（证据见测试报告）。

### ① 【P0·S1】坍缩快照层未跟上 v3.19.0 迁移（高严重度 · 回归缺陷）

**根因三段断裂**：
`harness.py:899` 快照取值 `dom.get("knowledge_bases")`（v3.19.0 已把 7 库迁到
`config/external-tools.yaml`，域档案**不再有此键**）⇒ 快照恒存 `list[0]`；
装配器 `pick()` 见空列表 ⇒ 走 else 分支渲染「无知识库」；
`glossary` / `delivery_language`（v3.19.0 新增域级键）**从未进快照、也从未被渲染**。

**修复**：
- `harness.py` 新增 `_external_tools_path()` / `_domain_knowledge_bases(cfg, domain_id)`——
  快照层改从**唯一源** external-tools.yaml 取库并**按 `owner_scope` 过滤**到本域
  （computing / business-training 无匹配 ⇒ 空列表，**这是正确行为**）；
  快照新增 `glossary` / `delivery_language` / `language_profile_ref` 三键；
  装载告警另存 `knowledge_bases_load_warning`（**不覆盖**域语义 note——
  两个来源不共用一个键，避免"一份口径两处写"）；
- `assemble_domain_prompt.py`：【五】段逐条渲染库（名称/id/何时用/**适用专业**/**导航链接**）
  + **可由用户灵活选择与配置**的更换提醒（裁决 #1）；无库时给出**明确通用兜底**（不再半句话）
  + 域级换库提醒（裁决 #4）；**新增【六之二、交付语言与术语表】段**（交付语言 + 唯一源引用 +
  词条逐条，**一条不可省**）；`pick()` 回落读域档案 ⇒ **旧产物兼容**。
- 实现中自查并修掉一处真 bug：`_reminder` 在 except 分支未初始化 ⇒ `UnboundLocalError`
  （由 T5 旧产物兼容用例抓出）。

### ①之二 【高·S1 审计补修】成员审计发现 3 处遗漏（主理人已逐条独立复核为真）

> 背景：S1 修复提交后，`agent-harness-coder` 成员**审计**该提交并找出 3 处遗漏
> （主理人此前判定其"卡死"实为误判——其产出在工作区未丢失，已找回）。
> **主理人逐条独立复核**（含对照实验：切回 508dbe8 旧版跑同反例）确认 3 处**全部为真**，
> 并独立复现其红证（4 个用例精确变红）后采纳。

- **缺口①（高）**：域档案 `glossary` 29 条 = dict 25 + **字符串 4**（"同一课件术语前后一致"等）；
  装配器只渲染 dict 形态 ⇒ 字符串条目被 `continue` **静默丢弃**，
  而段标题自称「29 条」⇒ **自称数 ≠ 事实数**（与本批修的"自相矛盾"同属一类病），成员漏收 4 条。
  修法：dict → 中英形态、字符串 → 原样列出，**一条不省**；条数按**实渲**数写。
- **缺口②（高）**：无库分支同屏仍矛盾——「本域无账号内知识库」+「该库组仅动物医学专业可用」
  （**对照实验实证**：切回旧版跑"清空库"反例，两行同屏）。
  修法：判据取域档案 `knowledge_bases_ref`（**声明式，不靠字符串匹配**）——
  声明"本域应有库"却一条没装上 ⇒ 报**装载异常**告警；声明"本域无库" ⇒ 其无库语义 note 照登
  （computing/business-training **不误报**，T9 反向判据防过度修法）。
- **缺口③（中）**：快照 `knowledge_bases_ref` 硬编码 `#knowledge_bases`，
  但 computing/business-training 实为 `#domains_without_knowledge_bases`
  ⇒ 装配器会把"本域本就无库"误判成"应有库却没装上"（假警）。
  修法：取域档案自己的指针；附带把 `language_profile_ref` 从**死键**变为被装配器消费。

新增 T7/T8/T9 三用例 + **T1 判据加严**（原 T1 只查标题自称条数 ⇒ **假绿**，
改为数**实渲行数**并逐条比对域档案）。

### ② 【中·S2】探针对**未知域 id** 缺归因提示

现象对（7 库全报 scope 冲突）但**归因错**——成员会以为"库坏了"，真因是"域 id 传错"。
修复：探针读 `config/domain-profiles.yaml` 的合法域清单，未知域时产出
`invalid_domain` 提醒（warn 级，点破真因 + 列出合法域 id）。正反例实测：未知域 1 条、
合法域 0 条（不误报）。

### ③ 【低·S3】`format_fallback`（isbn_checksum / gb_number_format）登记人读型

判据是**语义规则**（ISBN 校验位算法 / GB 标准号格式），由**会话层**执行，脚本不算
⇒ 登记第 18 项 known_textual（与 shrink_order 同判据）。死配置 105 → 103。

### 回归

`pytest scripts/` **212 passed / 3 skipped**（基线 200 → +12，零失败）；
新增 `scripts/test_collapse_domain_render.py` **9 用例**全绿（**含 3 个反例**：库清空→回到
「无知识库」；glossary 清空→词条 0；ref 硬编码 → 精确变红）+ T5 旧产物兼容 + T6 跨域过滤
+ T7 字符串词条一条不省 + T8 无库分支无矛盾 + T9 本就无库域不误报；
`test_external_tools.py` 扩到 16 用例（新增 T13/T13b invalid_domain 正反例 + T14 人读型登记）；
validate_expert 0 errors · 体检 23/23（域绑定残留 0）· 双树 0 差异 · 版本 10 处一致 3.19.1。

---

## [v3.19.0] - 2026-10-25（第五次从零诊断：交付语言规格 + 外部工具唯一源 + 联网权威编排）

> **诊断方式**：不沿用任何历史结论，按管家节点最新 13 维度需求为唯一基准重新取证。
> **管家节点 4 项裁决**（已全部落地）：① Ima 库可灵活配置 + **主动提醒更换/更新**；
> ② PubMed **MCP 优先 + esearch 兜底**；③ 英语场景**只写判据**（受众全英文授课/留学生班
> → 允许英语 PPT），不列具体场景；④ 教育部教学标准**进包但仅动物医学专业**，
> 其他专业**提醒更换**，保持「只记标尺来源 + 现查原文」。
> **执行约束**：本会话 Token Plan 配额耗尽（429），子代理三连失败 ⇒ 全部由主理人接管
> （团队已建、成员已派，按撞限协议处理——阶段产出标注「未经成员产出」）。

### 诊断期决定性实测（全部真跑，非推断）

1. **外部工具引用面 = 0**：包内对 `ima-mcp` / `mcp__pubmed` / `firecrawl` / `mcp__fetch`
   的引用**全包 0 命中**；域档案 7 个 Ima 库 ID **零消费者**；
   `IMA_OPENAPI_CLIENTID/APIKEY` 本机**未设置** ⇒ 库 ID 是死数据且无检测。
2. **维度 6 语言规格 = 0**：「英文PPT」「默认语言」「英语场景」三类关键词**全包零命中**；
   唯一语言规则是 domain-profiles.yaml 一条泛化术语标注。
3. **Ima 形态澄清**：Ima 是 **skill**（`~/.workbuddy/skills/腾讯ima/`，OpenAPI:
   POST https://ima.qq.com/openapi/wiki/v1/*，Header 认证），**不是 MCP**；
   本机 connector `ima-mcp` 为 disabled——dvm.md 旧版引用 `mcp__ima-mcp__search_knowledge`
   是**错误形态**（从未存在）。
4. **shareId ≠ knowledge_base_id**：全部 Ima 接口只收数字库 ID；
   管家节点给的 shareId 链接是**人工导航链接**，不可填入 API。
5. **教育部标准可落地**：官方 PDF 直链实测 HTTP 200（10 页，sha256 已登记）；
   pypdf 可提取 10,418 字符；行为动词实测「了解×9 / 理解×7 / 掌握×24」
   ⇒ 包内 `audience_depth_scale` **源头可核**。
6. **探针实现中抓到 3 个真缺陷**（假红/假绿类）：国图端点 HEAD→000 而 GET→200
   ⇒ 改 GET；OpenLibrary 带 Range 头 → SSL EOF ⇒ Range 失败去 Range 重试；
   endpoint_ref 实际有 **4 种形态**（原解析器只认 2 种 ⇒ 4 通道被误判不可用）。

### ① 【P0·维度6】新增 config/language-profile.yaml（交付语言唯一源）

`default_language: zh-CN` · `terminology.format「中文（English, Abbreviation）」` ·
`english_allowed_when`（**只判据**）· `english_minimum`（英语场景的中文保留项：
疾病中文名/药名/法规条款号/数值单位）· `consistency`（受众-交付语言一致性策略）。

### ② 【P0·维度10/13】新增 config/external-tools.yaml（外部 skill/MCP 唯一源）

`channels[]`（按能力组织 + **L1/L2 分层契约**：MCP 通道 layer=L2 声明式可达、
HTTP 通道 layer=L1 脚本实探）/ `ima`（完整 API 契约：endpoints 必填参数、
凭据环境变量、**shareId 约束**、selection_discipline、降级路径）/
`knowledge_bases`（7 库**从域档案迁入**，增 owner_scope / replaceable /
share_url / is_user_default）/ `standards`（教育部标准 + owner_scope）/
`domains_without_knowledge_bases`（无库域的**主动提醒**文案）。

### ③ 【P0·维度11/13】新增 scripts/probe_channels.py（通道探针 + 主动提醒）

8 通道三态探测（available/degraded/unavailable）；**replace_suggestions** 主动提醒
（四级判据：库属其他专业=**block** / 凭据缺失=warn 可降级 / 标准更新=warn /
replaceable 常驻 info）；探针结果落 `task_state.json#tool_probe_results`
（**已在 state_allowed_keys 白名单内**）。
实测：**8/8 通道 available**。

### ④ 【P0】harness.py preflight 增 `--probe-channels`（此前**只查成员不查通道**）

gate1-check 增两项冻结检查：**delivery_language**（语言规格可读 + 受众一致性）与
**knowledge_channel**（配置就位 + scope 冲突**阻断**）；`gate1_freeze` 6 → **8 项**。
探针异常**不崩 preflight**（预检不能因探针挂了开不了工 → verdict=degraded）。

### ⑤ 【P0·维度10】domain-profiles.yaml：knowledge_bases **迁出**

三域旧键全清（改 `knowledge_bases_ref` 指向唯一源）——**不留两份真相**；
`knowledge_channel_ref` 同步改指 external-tools.yaml。

### ⑥ 【P1·维度13】新增 scripts/fetch_authority.py（统一编排层）

**L1/L2 分层契约**（脚本**不可能**调 MCP ⇒ L1 执行 HTTP 通道 + 出编排决策；
L2 由会话层实调后 `--record` 回填记账）；用户指定源**优先于**默认通道；
`access != confirmed` ⇒ **阻断**（rc=4）；esearch 实测走通且标 `degraded`。

### ⑦ 【P1·维度10/13】agents/dvm-content-expert.md：Ima 调用规程重写

修正旧错误引用（`mcp__ima-mcp__*` 从未存在）；按实测 API 契约写规程
（凭据 → 找库 → 检索（cursor 首传空串）→ shareId 约束 → 降级声明）；
新增术语与交付语言段。

### ⑧ 【P1·维度6】三域 glossary + delivery_language

29/23/21 条 `{zh, en, abbr}` 词条（动物医学按其 6 条内容轴覆盖）；
规格唯一源在 language-profile.yaml，域档案只列词条。

### ⑨ 【P1·维度2】`stages.parallel` 首次接线

route 的 plan 增 `stage` / `parallel` / `parallel_members` / `parallel_policy`
（此前该字段**零消费者**——纯声明；stage 1 曾因伪并行返工，正说明字段有用却没人读）。

### ⑩ 【P1·维度7】extract_assets_usage.md §11：新下载图落盘规范

抽取素材与下载素材**物理隔离**（`_assets/images/` vs `_assets/images_new/`）、
**共用同一 manifest**（channel 字段区分——不建第二个清单）、三条纪律。

### ⑪ 【P1·维度10】references/standards/animal-medicine-teaching-standard.md

教育部标准结构化摘要（源 URL + sha256 + 原文摘录 + 行为动词档位实测 +
owner_scope + **本科版未核实不编造 URL**）；保持「摘要不替代原文，现查为准」。

### ⑫ 【P2】死配置处置（诊断点名的 4 组，逐一实测消费者=0）

- `font.title_min_pt` → **接线** verify_deck（run 级判定加标题分支：标题占位符
  用 28pt 阈值——此前屠明熙 MD 当红线写而机器不设防）；
  反例A（对照法）：删 yaml 键 vs 不删键行为一致 ⇒ 回退默认值生效。
- `density.shrink_order` / `theme.*` / `overlay_injection.*` → **登记人读型白名单**
  （第 18 项 known_textual）：给 LLM/人的执行指令本就不该由脚本读。
- 页数矛盾项**实查否决**：pedagogy.md:55 与 course-profile-defaults 口径表一致，
  1.5 课时缺位是显式记录的已知限制——非缺陷（诊断报告误报）。

### ⑬ 【P2·维度9】cmd_gate 三处 subprocess 加 timeout + snapshot 校验补漏

TimeoutExpired → exit 4（运行错误走缺陷回流，不当课件红灯）；
**补 snapshot returncode 检查**——此前 snapshot 失败被**静默跳过**
（"写回前自动打点"安全网形同虚设）。

### 回归

`pytest scripts/` **200 passed / 3 skipped**（基线 187 → +13，零失败）；
新增 `scripts/test_external_tools.py` 13 用例全绿（**每条新判据都有反例**）；
体检第 14 项 10 处版本一致（3.19.0）；批次 1（`2c72782`）与批次 2+3（`04ceb1b`）
独立提交、可单独 revert。

---

## [v3.18.0] - 2026-10-25（第四次从零独立诊断：坍缩真专家团 + 确认强制化 + 联网端点入 prompt）

> **诊断方式**：不沿用任何历史结论，按最新 12 维度需求为唯一基准重新编排
> 「4 组并行子代理从零读文件 + 主理人逐条交叉核验（Grep 阳性对照）+ 运行时实测」。
> 诊断证据：4 组独立报告（含 file:line 原文 + 实跑输出）+ 主理人复核实测。

### 诊断期两条决定性实测证据

1. **坍缩在真实运行中从未被触发过**：`.workbuddy/harness_trace.jsonl` 共 35 条事件，
   **全部是 `team_create`**，且 `domain` 字段**全为 `null`**（L1=9 / L2=17 / L3=9）；
   trace 中**无一条** `spawn` / `member_return` / `gate` 事件。
2. **发布前体检实测 120.26 秒**（包内文档自陈「诊断耗时 <1s」）——根因是第 7 项
   串行跑 `scripts/` 下全部 `test_*.py`（单套 `timeout=180`），其中联网套件
   `test_three_source_online.py` 真联网约 25 秒。

### ① 【P0·G1】坍缩从「注入 1 段域人格」升级为「坍缩出匹配的资深专家团队」

**缺陷**（规格 vs 事实落差）：
- 规格原文要求「依据输入的 PPT 或指定主题/模块（如**禽流感→禽流感病毒学家+禽病学家**）
  动态坍缩生成匹配的资深专家团队」；
- 事实：`domain-profiles.yaml` 只有**单个** `role_persona`（title/background/stance），
  三域的 `member_bindings` **完全相同**（仅 `dvm-content-expert` 吃人格注入），
  成员集恒为固定 5 人 ⇒ **「专家团」在数据结构与代码路径上都不存在**。

**处置**：
- `config/domain-profiles.yaml`：三域各增 `expert_panel[]`（子专家池，声明式）——
  animal-medicine 4 位（avian_virologist / poultry_pathologist / vet_pharmacologist /
  vet_public_health）、computing 3 位、business-training 3 位；
  每位含 `title` / `background` / `stance` / `duties` / `duty_boundary` / `coverage_axes` /
  `activation_hints`（后者是**给人看的选型线索**，脚本严禁据此自动选人）。
- `scripts/harness.py`：
  - 新增 `_select_experts()`（选人逻辑：主理人显式指定优先；未指定 → `pending_selection`，
    **脚本不替用户做专家选型**）；非法 id **先于落盘**拦截（不落半成品）；
  - 坍缩产物新增 `expert_panel`（池）+ `selected_experts`（本次选中）；
  - `route` 新增 `--panel <id1,id2>`，并把 `expert_panel_pool` / `selected_experts` /
    `expert_selection_status` 输出到 plan（供主理人**输出给用户对齐**）。
- `scripts/assemble_domain_prompt.py`：装配产物新增「专家面板」段——**逐位子专家分段渲染**
  （称号/背景/立场/职责/职责边界/覆盖知识轴），成员据此知道自己此刻扮演哪几位专家、各管哪块。

**验证（实跑）**：
```
$ harness.py route --level L2 --domain animal-medicine --panel avian_virologist,poultry_pathologist ...
  expert_selection_status: explicit
$ harness.py collapse confirm --id animal-medicine --task-id T-G1 --actor user --decision "..." ...
  selected_experts: 2 位
$ assemble_domain_prompt.py --member dvm-content-expert --collapse-artifact <已确认产物> ...
  ✅ 装配完成（27053 字符）| domain_context=effective
  产物核验：▍专家 1：禽流感病毒学家 / ▍专家 2：禽病学专家
```

### ② 【P0·G2】「坍缩结果经确认后方可生效」从**声明**升级为**代码强制**

**缺陷**：此前未确认态只打警告、仍 `rc=0` 并写出**完整 spawn prompt**（实测 24212 字符）
⇒「未确认照样能 spawn」；`test_spawn_injection.py` 里名为 `test_T7b_..._is_blocked` 的用例
**实际断言 `rc == 0`**；`gate1_freeze` 六项**全包无任何代码读取**；
`collapse confirm` 的 `--actor` 默认 `"team-lead"` ⇒「主理人自己确认自己」畅通无阻。

**处置**：
- `scripts/assemble_domain_prompt.py`：新增 `--require-confirmed`（**默认开启**）与逃生口
  `--allow-unconfirmed`；未确认态**拒绝产出装配产物**（`rc=5`，且不写文件）；
- `scripts/harness.py`：`collapse confirm` 新增**必填** `--decision`（用户裁决语义，缺失 `rc=2`）
  与 `--actor` 校验（**不得为 `team-lead`**，且不可缺省）；坍缩产物新增 `confirmed_decision`；
  新增 `gate1-check` 子命令——把 `config/harness.yaml#gate1_freeze` 六项变成**机器可校验判据**
  （受众/课时/模板/范围/验收/**已坍缩的专家团配置**），未就绪 `rc=1` 并逐项说明缺什么；
- `scripts/test_spawn_injection.py`：T4/T4b 改为断言**真阻断**（`rc=5` + 不写文件），
  新增 T4c 验证 `--allow-unconfirmed` 逃生口（放行但**仍不注入域人格**），
  T7 端到端补 `--panel` / `--decision` / `--actor user` 与「两位子专家须被注入」断言。

**验证（实跑）**：未确认装配 `rc=5` 且 `spawn.md` 不存在；缺 `--decision` `rc=2`；
`actor=team-lead` `rc=2`；未选人时 `collapse confirm` `rc=1`；非法 `--panel` `rc=2` 且未落盘。

### ③ 【P0·D1】机构权威源实端点**注入成员 prompt**（此前为 0）

**缺陷**：`assemble_domain_prompt.py` 渲染 `evidence_hierarchy` 时只挑 5 个子键，
`institutional_endpoints`（MSD 兽医手册 / WOAH 陆生法典 / WOAH 诊断试验与疫苗手册 /
WOAH 疾病卡 / FAO 动物卫生 / WHO 人畜共患，共 6 条**实测可达端点**）**被丢弃**
⇒ 成员只拿到机构**名称**、只能盲搜网页，**恰好违反同文件 `institutional_endpoints_note`
自立的纪律**（"机构轴 = 端点直达，不得盲搜网页"）。

**处置**：装配器新增「机构权威源实端点」段，逐条渲染 name/role/status/endpoint/
retrieval_patterns/note/license_rule + 该纪律原文。

**验证（实跑，装配产物 grep 计数）**：`msdvetmanual` 0→**6**、`woah.org` 0→**13**、
`fao.org` 0→**6**、`who.int` 0→**5**；端点条目 7 处。

### ④ 【P1·G5】默认模板**不再硬编码个人机器路径**

**缺陷**：`config/harness.yaml#loop_b.defaults.default_template` 硬编码
`/Users/biodog/.../OneDrive-Personal/.../禽病防治技术PPT模板.pptx`，且它是**闸1 冻结项**
（`gate1_freeze.template`，required: true），V1 页眉 / V3 取色等验收判据全挂在它上面；
该行还**不在任何 DOMAIN_EXAMPLE 哨兵块内**。

**处置**：置 `null`（包内**不预置任何模板文件**）；模板实际路径改由**工作区模板登记册**
`<工作区>/.workbuddy/templates/template_registry.json` 提供（`template_migrate.py register`）；
模板**约束**（三条硬约束 + 指纹 + GEO-003 基线用法）留在 `references/default-template-profile.md`
（唯一源）；新增 `template_profile_ref` 指向它。缺模板时 `gate1-check` 报「模板待提供」并阻断闸1，
**不静默回落任何路径**。

### ⑤ 【P1·G7】`marketplace.json` 版本漂移 + 巡检盲区

**缺陷**：两份 `marketplace.json` 的 `plugins[0].version` 仍停在 **2.2.0**（包内实际 3.17.0），
而体检第 14 项只核 8 处（**全是包内源**）⇒ **不覆盖 marketplace** —— 安装入口侧长期版本不符
且**体检全绿**。这是「声明层≠执行层」在**发布侧**的实例。

**处置**：4 份 marketplace.json 同步版本号；第 14 项新增 2 处 marketplace 校验
（注意其 `version` 在 `plugins[0]` 下，不能复用 yaml 正则，须走 JSON 解析），
并更新告警处置文案。**验证**：第 14 项输出由「8 处一致」变为「**10 处一致**」。

### ⑥ 【P1·G8】发布前体检耗时**分层**（实测 120s → quick 16s）

**缺陷**：全量体检实测 **120.26 秒**，而包内自陈「诊断耗时 <1s」；`--quick` 开关
（跳过第 7 项回归测试）**存在但无任何文档/提示告知使用者** ⇒ 读者只会跑 120 秒那条。

**处置**：`UPGRADE.md` 的必做段显式列出 `--quick`（日常改包，约 16 秒）与全量（发布前，含回归）；
`ensure_settings.py` 全量模式启动时打印分层提示与实测耗时。

### ⑦ 文档同步

- `agents/vet-med-ppt-team-team-lead.md`：「成员人设注入协议」新增**专家面板与选人**四步表
  （route --panel → 输出给用户对齐 → collapse confirm --decision/--actor user → gate1-check）、
  域上下文状态表改为「未确认 → **装配器直接拒绝**（exit 5）」、新增模板来源说明；
  闸1 行补「选域与选人」步骤与 `gate1-check` 自检命令。

### ⑧ 【P0·D2】Loop B intake 确认态校验（此前「已填但未确认」照样放行）

**缺陷**（实测复现）：`harness.py` 的 intake 与 make-gate 只判 `not intake.get(k)`，
而 A 类五项的登记格式是 dict（`{"value": ..., "status": "confirmed|suggested"}`）——
`status="suggested"`（**未确认**）的 dict 非空 ⇒ 被判为已确认 ⇒ **直接放行进制作**，
与 `references/task-intake-checklist.md:158-159`「存在 suggested 即不得进入制作阶段」**直接矛盾**。

**处置**：
- 新增 `_intake_item_state()`——**三态**判定（missing / unconfirmed / confirmed）：
  dict 必须 `status == "confirmed"`；list 元素带 status 时要求至少一条 confirmed；
  **纯标量保持旧行为**（非空即已确认，不破坏既有递进式登记）；
  `_intake_item_confirmed()` 降为薄封装（**两处实现必须同源**——曾并存两份，正是本项目
  「同一口径两处漂移」的典型病灶）；
- intake 分支输出新增 `unconfirmed_A`，把「缺失」与「未确认」**分开报告**
  （处置动作不同：缺失=去问；未确认=去追认。混在一起等于把未确认伪装成缺失，用户会
  绕过"追认"直接重填）；
- make-gate 分支走**同一个**判定函数；
- 新增 `loop intake --replace`：本次文件即**完整快照**（此前是增量合并⇒删掉的键永远删不掉，
  用户"撤回某一项"在系统里无法表达）。默认仍是合并（向后兼容）。

**验证（实跑）**：全 suggested → rc=1 且 `unconfirmed_A` 列全五项；全 confirmed → rc=0；
纯标量 → rc=0（向后兼容）；缺两项 + `--replace` → rc=1 且 `missing_A` 精确列出那两项。

### ⑨ 【P0·D3】冷启动**自动发现**未完成任务（维度 12）

**缺陷**：`harness.py doctor`（新会话首查命令）**不读** `loopB_state.json` / `task_state.json`
⇒ 会话中断后"是否恢复、从哪恢复"完全靠主理人记忆，**无机器托底**。

**处置**：`doctor` 输出新增顶层 `pending_work` 段——扫 Loop B 状态（termination 为空即未结束）
与 task_state（current_stage ≠ 0），报出轮次/待办/冻结项/下一步，并给出**可直接执行**的
`resume_hint` 命令串。**无状态文件时该段为 null**（不输出空壳）。**只读**，不修改任何状态。

**验证（实跑）**：空工作区 → `pending_work = null`；造未结束 Loop B + task_state →
输出 `kind=loopB`（第 2 轮 / 待办 I-001 / 已冻 I-002）+ `resume_hint` 含 `loop resume`。

### ⑩ 【P0·G6】`state compact` 状态压缩（此前「必须 compaction」只是一句报错）

**缺陷**：`state validate` 报「状态文件 N bytes 超过上限，必须 compaction」，
但**全包无任何 compaction 实现**（grep `compact` 在 scripts/ 下只有 init 置 `{}` 与报错文案）
⇒ 超限后只能人工手改状态文件。

**处置**：新增 `harness.py state compact`——
必保 `task_id` / `workflow` / `current_stage` / `next_action` / `budget` / `tool_probe_results`；
`stage_history` 只留最近 N 条（N = `config/harness.yaml#context.state_history_keep`，默认 10）；
`user_confirmations_pending` 只留未决项；**丢弃动作全部记进 `compaction` 账本**（不静默）；
原子写 + 写 `compaction` trace 事件（事件名已登记进 `observability.trace_events`）。

**验证（实跑）**：117995 字节 → `state validate` rc=1 → `state compact` → 23837 字节 →
`state validate` rc=0；必保六项全在；`stage_history` 裁到 10 条；账本记录丢弃 50 条。

### ⑪ 【P0·G3】配图检索脚本（此前端点只有声明、**零实现**）

**缺陷**：`domain-profiles.yaml` 登记了 Europe PMC 端点与许可规则，但**脚本侧零实现**
（无下载器、无 API 客户端）⇒ 配图能力不可复现、不可审计、换机器即静默归零。

**处置**：新增 `scripts/fetch_oa_image.py`——**端点从域档案读**（不硬编码 URL）；
下载 → 落 `<out>/images/` → **回填 manifest 三字段**（`source_url` / `doi_pmcid` /
`license_note`）；**许可红线**：许可规则缺失或含"待核实/未明"等标记 ⇒ **拒绝下载**（exit 4）
并标 `[待核实]` 挂账，**绝不编造许可**；退避参数从 `config/domain_config.yaml#image_fetch.retry`
读且**每次退避显式告警**（不静默 sleep）；新增 `scripts/test_fetch_oa_image.py`（7 用例，不依赖真实网络）。

**验证（实跑）**：7/7 OK；反例——把端点改成硬编码常量后 T5 **精确报警**
（"脚本未使用域档案里的端点——说明端点被硬编码了"），复原后恢复绿。

### ⑫ 【P0·G4】图注要素统一为「通用骨架 + 域扩展」

**缺陷**：图注要素**四套定义并存**（`visual-rules.yaml#caption_five_elements` 域口径 5 项 /
`seven-dimension-rubric.md:107` 域无关 5 项 / `dvm-content-expert.md` 3 项 /
各域 `caption_elements` 又不同），且 rubric **自认冲突并声明「本文件不替 config 做决定」**
——即明知冲突而不调和 ⇒ 判据随域而变，与"通用诊断工作流"目标直接冲突。

**处置**：
- `visual-rules.yaml` 新增 **`caption_base_elements`（通用骨架·唯一源）**：对象 / 来源与许可 /
  教学意义；`caption_five_elements` 保留为**历史键**（向后兼容）并标 deprecated；
- 三域的 `caption_elements` → **`caption_extra_elements`（域扩展）**，并去掉与骨架重复的项
  （如"教学意义"）；
- `seven-dimension-rubric.md` 的 V5 口径改为指向骨架+扩展（**不再自认冲突**）；
- `dvm-content-expert.md` / `visual-slide-designer.md` 的图注要求改为**引用唯一源**；
- 装配器同时呈现骨架与域扩展并标注二者角色。

### ⑬ 【P1】防漂移守卫升级为 **AST 真实读取点**判据

**教训（v3.18.0 实测）**：T11a 守卫首版用 `if "institutional_endpoints" not in src` 判"是否接线"，
反例验证时把读取改成 `inst_eps = []`（字面量仍在文件里）→ **守卫没红**——文本判据是假的。
改为 **AST 真实读取点**采集（`X.get("k")` / `X["k"]` / 字典字面量三种形态），
反例随即精确报警（"装配器无 institutional_endpoints 的真实读取点"），复原后恢复绿。

新增守卫：`T11a` 面板/端点接线 · `T11b` SOP 须写选域选人四步 · `T11c` 面板 id 唯一且字段齐 ·
`T11d` 图注骨架与域扩展**不得重复** · `T11e` 包内不得有第三套图注定义。
**反例验证**：域扩展塞入骨架重复项 → T11d **精确报警**，复原后绿。

### ⑭ 【P1】`test_trace_events.py` 去硬编码（同一口径两处漂移的又一次复发）

该文件把「声明的事件列表」硬编码成 12 元组，而 v3.18.0 加了 `compaction` 事件后
**误报失败**——正是「同一口径两处各写一套」的病灶。改为**从 yaml 读**（唯一源），
并为 `compaction` 补真实触发路径（造大状态文件 → `state compact`）。

### 回归

`pytest scripts/` **187 passed / 3 skipped**（基线 167 → +20 用例，零失败）；
`test_spawn_injection.py` 19/19 OK · `test_arch_drift.py` 16/16 OK ·
`test_gate1_check.py` 7/7 OK · `test_fetch_oa_image.py` 7/7 OK · `test_trace_events.py` 10/10 OK；
体检 23/23 通过（第 14 项 10 处版本一致；第 23 项域绑定残留 0）；
双树 `diff -rq` 零差异。

---

## [v3.17.0+批次B] - 2026-10-25（v3.17.0 发布后从零复核的修复批次）

> **为什么不是 v3.18.0**：本批次是对 v3.17.0 的**发布后从零复核**发现的缺陷修复，
> 版本号未升（内容与 v3.17.0 同线），单独成段以便追溯。下次正式发布时合并升版。

### 批次 B 背景

v3.17.0 发布后按同一 11 维度基准做**第三次独立复核**（不沿用历史结论）。复核发现
**2 个 v3.17.0 CHANGELOG 未登记的 P0 缺口** + 若干 P1/P2，用户裁决 4 点后执行本批次。
执行过程中 3 个并行子代理因 Token Plan 配额耗尽（429）中断，剩余工作由主理人接手完成。

### ① 【P0】坍缩产物接入装配链（域人格此前**从未进入成员 prompt**）

- **实测证据**：`route --domain computing` → `collapse confirm` 全通（status=confirmed /
  effective=true），但 `assemble_spawn_prompt.py` 装配出的 33578 字符产物中，域人格关键词
  命中数 = **0**（"软件工程内容权威"/"事件循环"/"asyncio" 全部 0）。
- **根因**：本包 `scripts/assemble_spawn_prompt.py` 是 shim，转调 `shared-core`；
  后者**不读 `_collapse/`、也不读 `config/domain-profiles.yaml`**。
- **修法（按裁决①：先本包内实现，不上提共享件）**：新增 `scripts/assemble_domain_prompt.py`
  （本包装配层，in-process 调 core 后做三步后处理：稳健切分 → frontmatter 键补偿 →
  插入域上下文段）。**`shared-core/` 零改动**（已 md5 + Grep 核验）。
- **修复后实测**：域人格「软件工程内容权威」0→1、「事件循环」0→3、content_axes 首项 0→1、
  frontmatter 三键（name/description/maxTurns）全回填、撕裂残留 0。
- **遗留**：旧 shim 入口仍不带域上下文（文档已改指新脚本）；shared-core 的两处缺陷
  （不读 `_collapse/`、`split("---",2)` 丢键）**另外 4 个包仍带**，待另案上提。

### ② 【P0】dvm-content-expert.md frontmatter 被装配器撕裂

- **根因**：`shared-core` 的 `parse_frontmatter` 用 `md_text.split("---", 2)`，而该文件
  frontmatter 注释里含**行内 `---` 字面量** → 切分提前截断，丢失 description/profession/
  displayName，正文开头混入半截注释。逐个复验 6 份成员 MD，**仅此 1 份受影响**。
- **修法**：注释措辞去掉行内字面量 + 本包装配层用加固正则
  `\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)`（**带 `re.DOTALL`**）自行切分。
  ⚠ 主理人最初给的正则 `^---\n(.*?)\n---\n` **缺 DOTALL，6/6 全部失配**——由执行成员实测纠错。

### ③ 【P0】三源核验：textbook/regulation 由「仅格式合规」升级为「可实查存在性」

- **立项**：CHANGELOG 已知瑕疵 #1（此前两类源只有确定性结构校验，永远只到格式档）。
- **⚠ 本批次发现并修复一处引入性回归**：前序工作只改了 `config/domain_config.yaml`
  （textbook.mode → `isbn_online`、regulation.mode → `gb_online`），**代码侧无对应分支**
  ⇒ 两类源落到「mode 未实现 → 不可核验」，**比改之前的「仅格式合规」更差**（实测：
  真实 ISBN 与 GB 号均判 unverifiable）。
- **修法**：`harness.py` 新增 `_verify_isbn_online` / `_verify_gb_online` 两个分支 +
  `_net_fetch`（超时/重试/退避/限速全从 yaml 读）。
- **端点现查证据（主理人实测，不凭记忆）**：
  | 端点 | 实测结果 |
  |---|---|
  | 国图 OPAC `opac.nlc.cn` | 可达；伪造号 34076 bytes 且含未命中文案；题名检索自取真实 ISBN `9787559120946` 回填 → 64481 bytes 且无未命中文案（判据成立） |
  | OpenLibrary | 可达；`numFound` 有效；校验位不过的号不命中（无假阳性） |
  | 全国标准信息公共服务平台 `std.samr.gov.cn` | 可达；`GB 10648-2013` → 现行；`GB 10648` → 两条（含 1999[废止]）；`NY/T 1167-2006` → total=0（**不覆盖行业标准**） |
- **新增能力**：引用**已废止/被代替**的标准现在能被抓出（`state_warning`）——
  此前格式校验完全查不出来。
- **诚实边界**：非 GB 国标号（NY/T、公告号）该平台不覆盖 → 判「不可核验」并显式登记
  **人工核验项**，且不得用"格式不合规"误导（NY/T 格式合规，只是查不到）。
- **守卫**：新增 `scripts/test_three_source_online.py`（8 用例）。**根因守卫 T1**
  断言「yaml 声明的 mode 必须有代码分支」——变异测试证明有效（改 mode 后 4 用例变红）。

### ④ 【P1】质量收敛判据纳入 P2

- **缺陷**：`_loop_no_progress_streak` 只比 `p0p1` ⇒ 一轮只把备注覆盖率补达标
  （p2: 1→0）而 P0/P1 不动时，被误判「无进展」并**终止**（终止不可逆）。
- **修法**：改比 `p0+p1+p2` 合计（三者**同向**：都是缺陷/阻断计数，越少越好；
  P2 语义是「备注覆盖率**未达标**」而非覆盖率百分比，故可直接相加——已写入函数注释，
  若将来改口径必须同步改向）。快照新增 `p0p1p2` 键，保留 `p0p1` 兼容旧报表。
- **守卫**：新增 `scripts/test_no_progress_p2.py`（7 用例，含方向与向后兼容）。

### ⑤ 【P1】闸2 伪并行修正（声明服从事实）

- **缺陷**：4 处镜像块 + 文档声明「闸2 并行、任务边界互斥」，但 pedagogy 的二八难点清单
  **明确依赖** dvm 证据包的「易误解」标注 —— 边界不互斥，并行必然回问，每次多一轮往返。
- **修法**：改 `parallel: no` + 名称「闸2 设计（证据先行→蓝图·串行）」，同步
  `config/harness.yaml#stages[1]` 与 4 处 STAGE_MIRROR 块 + `sop-stages.md` 说明。
- **⚠ 连带修一处测试缺陷**：`test_arch_drift.py` 原判据恒为
  `len(members) > 1 ? yes : no`（"多人必并行"），**否定了"多人串行"的合法性**——
  会让"如实声明串行"变成测试失败，逼人改事实而非改声明。改为**读 yaml 显式
  `parallel` 字段**（yaml 成唯一源，缺键才推导）。
  ⚠ 修时踩到布尔陷阱：YAML 的 `no` 解析为 `False`，`False or ""` 得空串会把显式声明
  误判成"未声明" —— 已修并写进注释。

### ⑥ 【P1】用户指定 PDF/URL 接单通道（维度 11）

- `references/task-intake-checklist.md` 增**第 10 项**（B 类，落盘 `intake.user_sources`）
- `config/domain-profiles.yaml` 三域各增 `user_supplied_sources` 策略段
- `agents/dvm-content-expert.md` 新增「外部指定源处理纪律」（定位通道 / 可复查定位 /
  三源口径（**不能充抵两条独立来源**）/ 冲突并列不自行抹平 / 取不到标 `[待核实]` /
  许可不因"是用户给的"而豁免）—— 补齐域档案第 384 行引用的锚点（此前**悬空**）。

### ⑦ 【P1】机构权威源端点补全（维度 11）

`domain-profiles.yaml` 新增 `institutional_endpoints`：MSD 兽医手册 / WOAH 陆生法典 /
WOAH 陆生手册 / WOAH 技术疾病卡 / FAO 动物卫生 / WHO 人畜共患，各带 endpoint +
检索式模板 + 用途说明；并同步修正文件头「本文件不含 URL」的诚实声明（否则声明与内容矛盾）。
⚠ WHO 一处深链实测 404 → **未登记**（不编造）。

### ⑧ 【P1】七维量规唯一源收敛 + routing.L1 伪 ID 修正

- 量规：**包内 `references/seven-dimension-rubric.md` 为执行源**（与 `dependency-manifest.yaml`
  一致），改两处 agent MD 的"唯一执行源在下游 skill"表述。
  ⚠ 另行发现：`scripts/check_external_deps.py` **只做存在性探测、无内容比对**，
  而 manifest 承诺登记 drift（`drift_checked_at`/`upstream`）⇒ **无执行者**（第 5 个
  声明层≠执行层缺口），已交 docs 组处置。
- routing.L1：`spawn` 由伪 ID 字符串改为真 ID 数组，`"按需1-2名"` 语义移到 `spawn_policy`。

### ⑨ 【P1】域绑定残留全量处置（用户裁决④）

**41 处 → 0 处**。处置中发现并修复：
- **【关键】第 7 个「声明层≠执行层」缺陷**：`config/hygiene-words.yaml` 把
  `exempt_markers` / `exempt_headings` / `profile_ref_patterns` 嵌在 `scan:` 之下，
  而 `ensure_settings.py` 从**顶层**取（只有 `frontmatter_comment_exempt` 一处写对了）
  ⇒ **哨兵块、章节豁免、域档案引用行豁免三组机制从未生效**，体检第 23 项长期虚高，
  且"围哨兵就能豁免"这条契约是**假的**。已修（以 `scan` 为唯一读取位置，兼容顶层回退）。
- 处置方式分三类（逐条判定，不批量替换）：
  ① **正当举例** → 行级哨兵块（21 行）；
  ② **表格行**（插注释会打断表格渲染）→ 改写为域中立表述（6 处）；
  ③ **人设/标题** → 域中立化（4 处：pedagogy description、team-lead 标题与导语等）。

### 已知欠账（本批次未完成，诚实登记）

1. **`references/course-profile-defaults.md` 未下沉**：其受众四层与深度标尺**整体取自**
   教育部《动物医学专业教学标准》，属 animal-medicine 域专属。正确处置是下沉为域档案的
   受众分层字段（各域一份）。本批次以 `exclude_files` 登记排除，reason 明确写
   **「待下沉，不谎报为按设计专有」**——这是欠账，不是豁免理由。
2. **shared-core 两处缺陷未上提**：另外 4 个包仍带「不读 `_collapse/`」与
   「`split("---",2)` 丢键」。按裁决①本轮不改共享件。
3. **旧 shim 入口不带域上下文**：`scripts/assemble_spawn_prompt.py` 仍可被沿旧习惯调用，
   此时域人格不生效（文档已改指新脚本，但非强制）。
4. **check_external_deps.py 的内容比对**（量规 drift 登记）本批次未完成。

### 回归状态

- `pytest scripts/`：**159 passed, 3 skipped**（非联网）+ `test_three_source_online.py`
  **8 passed**（联网）= **167 passed**；基线 120 无回归。
- `ensure_settings.py`：**23/23，rc=0**，结论「✅ 全部通过」。
- 双副本：`packages/vet-med-ppt-team/` 与根目录 **0 差异**（rsync 后 `diff -rq` 校验）。

---

## [v3.17.0] - 2026-10-24

### 概述（11 维度独立诊断整改：通用化重构 · 治「声明层 ≠ 执行层」与「规则存在 ≠ 规则生效」）

本版起点是一份**从零开始的 11 维度独立诊断**（4 组只读子代理并行 + 主理人交叉核验），
对标基准是该包的**新定位：可复用于任意教学/培训主题的通用 PPT 诊断与优化工作流**。

**诊断推翻了一条历史断言**：上一版称「三源核验是自证循环、不验证来源真实存在」——**不成立**。
`harness.py::_pmid_online_check` 真联网 PubMed esearch 验 PMID 存在性，`verify-ref --online/--write-back`
是受控路径。真问题不是「没有反幻觉能力」，而是**「护栏装在了闸外」**——闸4.5 从不调它，
且 `--online` 只覆盖 `kind==pubmed`。

**本版贯穿的两条纪律**：
1. **声明层 ≠ 执行层**——凡是「写在文档里但没有执行者」的，一律治本（实现读取 / 删掉 / 显式登记待办）。
2. **规则存在 ≠ 规则生效**——凡是「配了但执行者不读 / 读了 fallback 不读配置 / 判据只写在散文里」的，
   一律补执行者或改为 fail-closed。

### ① 专家团动态坍缩（本版地基 · 规格 P0）

新增 `config/domain-profiles.yaml`（声明式域档案，唯一数据源）与 `harness.py domain list/show`、
`route --domain`：

```
$ harness.py route --level L2 --domain computing
  "role_persona": {"title": "软件工程内容权威", "stance": "能复现的才算数——不编造 API 行为…"}
  "collapse_artifact": "…/_collapse/collapse_adhoc_computing.json"
  "collapse_status": "pending_confirmation"   "collapse_effective": false
  "collapse_note": "待确认，未生效（须经 `collapse confirm` 确认后域人格方可生效）"
```

**关键设计决策：坍缩不做关键字匹配。** 按本项目分工宪法，「用户主题 → 选哪个域」是**语义判断**，
绝不能用规则匹配/关键字/正则实现——故脚本只提供**域菜单（给 LLM 选）+ 域档案 + 确定性组装 + 落盘 + 校验**，
**选域由主理人（LLM）做**。这既满足规格「坍缩结果须主动输出并与我对齐」，又不违反铁律。

坍缩产物落盘 + **进闸1 确认门**（新增第 6 项冻结项），未确认时域人格**不生效**。
内置 3 域（`animal-medicine` / `computing` / `business-training`）；
非兽医域的 `knowledge_anchor` **如实写 null 并注明「需联网现查；写 null 是如实登记，不是缺漏」**。

### ② 内容角色去兽医化（规格 P0）

`agents/dvm-content-expert.md` **保留文件名**（专家包铁律：改 `agents/*.md` 文件名 = 专家丢失），
正文改为「**域无关方法论 + 域人格引用**」：原硬编码的 Ima 七库路由表、检索式模板
（`chicken AND ("Newcastle disease virus" OR APMV-1) AND (proventriculus...)`）、高风险拒收条款，
全部外置到域档案；**方法论内核一字未删**（五条铁律、证据分级、双标记制、术语规范、三源核验循环、
issues 唯一上抛通道）。

### ③ 诊断入口归位（规格 P0 · 「诊断」这一半原本在包外）

- **内化** `references/seven-dimension-rubric.md`（七维量规，原唯一执行源在包外 skill
  `teaching-ppt-studio`，且 `plugin.json` 无任何依赖声明字段 → 换机器静默失效）。
  去兽医化：表头「典型病症」→「典型问题」，兽医学例子改域无关表述。**保留来源溯源，不假称原创**。
- 新增 `references/diagnosis-report-schema.yaml`（诊断报告唯一 schema，与 `round-review-sop.md`
  的**八字段**逐字段一致，不另立一套；severity 只引用 `visual-rules.yaml` 不复制）。
- 新增 `scripts/check_external_deps.py` + `references/dependency-manifest.yaml`：
  外部依赖缺失从**静默失效**变成显式可见，且**不阻断**（内化就是为了自包含）。
- 「只诊断不修改」成为真出口：交付清单补「纯诊断任务的交付物是诊断报告」分支。
- 任务包新增第五要素 `acceptance_criteria`（检查项 + 判定方式[机/人] + 阈值）。

### ④ 闸4.5 三源核验：三档判定（治「可被纯编造数据骗过」）

原判据是 `any(src.get("ok") is True)` —— **纯编造数据即可 100% 骗过**。
现分三档（唯一源 `domain_config.yaml#three_source_check.tiers`）：
`existence_verified`（PubMed 实查命中）/ `format_only`（ISBN 校验位、国标编号格式合规，
**未验证存在性，不计入已验证**）/ `unverifiable`。

**判定不读 `sources[].ok` 与 `verified_at`**（自报值不构成证据）；
网络失败（None）单独计数 + 显式告警 + `network_failure_policy=block` → **整轮不得判 pass**。
「三源齐备」现要求：三类来源齐备且至少 1 条达「存在性已验证」。

**越权修复（经主理人裁决批准保留）**：`verify-ref --online` 原只核「缺 ok/缺 verified_at」的来源，
于是编造来源只要写上 ok=true+verified_at 就永远不被实查——**同一缺陷的另一个出口**，一并改为实查所有。

### ⑤ 收敛判据堵漏（治「可注水」）

- `--verify-json` 报告**与被优化课件绑定**（读 `stats.file` 比对，不匹配即 exit 2，
  报错原文：「拿别处课件的报告喂收敛判据 = 拿别人的成绩单算自己的进度」）；
- 一旦历史轮次用过手工值，后续轮次**强制** `--verify-json`（逃生口 `--allow-unverified` 留痕 + 记 blocker）；
- `make-gate` 检查 `quality_history` 的来源（此前 `source` 字段无任何下游消费者）；
- **判据侧修漏网**：「问题已修复归零」的汉字被证据正则当成计数 → 命中裸词先剔除再判计数。

### ⑥ 状态机持久化加固（治「文档声称有防护、代码是裸写」）

`task_state.json` 原为**非原子裸写**，而两处文档声称有「写入前原子比对 task_id」的并发防护。
现复用 `_StateLock` + 原子写，并**兑现**该承诺：task_id 不一致 → 拒绝推进 + 报警 + exit 1；
状态文件损坏 → **拒绝操作、原文件保留（不覆盖不重建）**，不走「按空状态继续跑」；
`state set --value` 非法 JSON → **显式报错**，不再静默存字符串（那正是 quality_history 静默失效的根因）。

### ⑦ 闸3 交叉复检映射三处全反（治「把关人被全部绕开」）

`sop-stages.md` 原写「科学性改动→苏学法；教学性改动→严真奥；页面性改动→苏学法」，
而两份 agent MD 明文禁止对方做对方的事。已订正为
**科学性→严真奥 / 教学性→苏学法 / 页面性→屠明熙**，
并新增**体检第 22 项**把该映射登记进 `config/guard.yaml`（唯一源）并双向校验：
文档写法 == yaml 登记 == 各成员 MD「你不做…」边界取反。

### ⑧ 前置元问题：frontmatter 实际不可解析，而体检对它假绿

**为拦截这类缺陷而建的检查，被同一类缺陷骗过。**
体检第 15 项（v3.8.0 专为「frontmatter 未闭合」而建）判据是「数 `---`」——
而 `dvm-content-expert.md` 的第二个 `---` 恰好落在**正文里**（第 21 行），
`yaml.safe_load` 直接 ScannerError → **Claude Code 侧该 agent 被当作普通文档，
name/description/maxTurns 全部失效 → 包里的签名内容专家在一个目标平台上等于不存在**。

现第 15 项改为**真解析 YAML**（逐个候选闭合符试解析，能解析出合法 frontmatter 才算真闭合符），
并**区分两种缺陷**（「未闭合」vs「闭合符位置错」——修法不同，报错也不同）+ 报行号。

### ⑨ 文档口径归一 + 防漂移守卫扩面

`references/sop-stages.md` 整份停在「四道闸 / 只认 0–3」而 yaml 是 stage 0–4 —— 已全份同步为
**五闸 stage 0–4** 并补闸4.5 章节（此前完全缺失，而 `iron-rules.md` 承诺该文件含闸1-闸4.5 完整流程）。
`test_arch_drift.py` 从只比 `docs/architecture.md` 扩到**多文档**（T7–T10），
口径唯一源为新增的 `config/guard.yaml`。

### ⑩ 工程卫生

- 成员 MD 的**同源副本压缩**（信封契约块 6 份 × ~12 行 ≈ 70 行 → 1 处定义 + N 处一行引用）；
  顺带发现「消除重复」的整改说明本身被复制 4 次——**整改动作成了新的重复源**，一并清除。
- 修正「≤800 字摘要」指向错误（原指向 `budgets.max_artifact_bytes`，实为 `context.summary_max_chars`）；
  dvm 补齐交接方式声明（此前是唯一缺失的成员，而它恰是 issues 唯一通道的重度使用者）。
- 依赖检查脚本从 `references/` 归位 `scripts/`（原位置会被体检第 17 项漏扫、回归套件未必收录）。

### ⑪ 回传信封承载域与坍缩（规格 P0）

新增选填字段 `domain`（枚举取自 `domain-profiles.yaml`）与 `routing`（`level`/`members`/`collapse_artifact`），
`metrics.keys` 硬限 2 键 → 放宽为 `known_keys` 白名单 + 未知键只告警
（原硬限会把成员逼到「删指标」或「谎报键名」，比不登记更糟）。

### ⑫ 外部权威资源的真实联网核验

三源核验新增 `api_key` 支持（**真值只从环境变量读，yaml 只存变量名，包内任何文件都不含真 key**）、
可配限速、**指数退避 + 疑似速率限制的显式告警**、以及 `abort_batch_on_rate_limit` 熔断
（默认开：一条退避耗尽即中止本批剩余实查并显式告警，整批从 ~56s 降到 15.3s，**仍 fail-closed**）。

### 工程状态

- 版本**八处**同步 **3.17.0**（体检第 14 项已扩到 8 处并守住：两份 plugin.json / harness.yaml /
  harness.py 的 doctor 常量+文件头+argparse 描述 / result-envelope.yaml / domain_config.yaml）
- 体检 **23/23 通过**（21 项 ✓ + 2 项提示级 ℹ：第 18 项「85 个配置键无读取者」属人读型登记、
  第 23 项「40 处域绑定残留」属待下沉清单——**两项均提示不阻断**；独立测试判此表述比「全绿」准确）
- 回归 **120 passed / 3 skipped**；`test_loop_state.py` **33 → 74 例**（v3.16.0 招牌特性此前**零覆盖**）
- 双树逐字节一致（`packages/vet-med-ppt-team/` ← 用户实际加载的那份，`marketplace.json` 的 source 指向它）

### 已知瑕疵（如实登记，未修）

1. **三源中只有 pubmed 有存在性核验能力**——textbook/regulation 无权威可查端点，
   永远只到「仅格式合规」档，**不计入已验证**。口径限制，非实现缺陷。
2. **NCBI 对无 key 的匿名访问有速率限制**，批量清单会触发封禁 → 判 `network_incomplete`
   （fail-closed，不静默通过）。跑清单须分批 + 批间留间隔 + 配 `NCBI_API_KEY`。
3. **`domain` 的选域仍是 LLM 决策**（脚本不自动选域）——这是分工宪法的要求，不是能力缺失；
   但意味着选域质量依赖主理人判断，无机器兜底。
4. **闸2 仍是伪并行**（dvm 证据与 pedagogy 蓝图存在双向数据依赖，却声明「边界互斥」）——本版只记录未改。
5. **7 个声明的 trace 事件仍无代码产出**（`team_create`/`preflight`/`spawn`/`spawn_failed`/
   `degrade`/`member_return`/`error`；yaml 声明 12 个，`gate`/`stage_enter`/`stage_exit`/
   `budget_exceeded`/`no_progress` 已有产出），`require_disclosure: true` 的消费者仍是人不是代码。
   *（原写「9 个」，独立测试实测为 7 个——静态扫描漏了 `cmd_stage` 的 f-string 动态事件名
   `stage_{action}`。方向对、数字错，已按实测修正。）*

6. **第 23 项检出 40 处域绑定残留尚未处置**——集中在 `agents/pedagogy-architect.md`
   （禽/禽流感/新城疫/鸡/病原）、`references/course-profile-defaults.md`（兽医×6、法氏囊）等。
   属**提示级**（不阻断），需逐条判定「应下沉到 `config/domain-profiles.yaml`」还是
   「正当的兽医域专属内容」；本版只做检出，未做处置。
7. **坍缩产物默认写在包根 `.harness-runs/`**（已 gitignore，不入版本库/不进第二副本），
   但更干净的形态是落在工作区而非已安装的包目录。
8. **V3（取色比对）与 C5（数字来源）仍未实现**；三源仍是部分自证（pubmed 有实查，另两类无）。

### 独立测试（P3）发现并已在本版修掉的 7 项

独立测试员冷眼复核 27 项，**0 阻断**，发现 9 项——其中 7 项已在 v3.17.0 内修掉：

| # | 级别 | 问题 | 处置 |
|---|---|---|---|
| F1 | 高 | `dependency-manifest.yaml` 的 `checker.path` 仍写 `references/check_external_deps.py`（脚本已归位 `scripts/`）→ **悬空引用**，按文档执行 EXIT=2 | 已改为 `scripts/…`；并**补强体检第 17 项**（见下） |
| F2 | 高 | `integration_status` 写「待并入体检第 23 项」——**该集成从未发生**，且第 23 项现为域绑定残留巡检 | 改为如实登记「**未并入体检**」，并写明「勿再写『待并入第 23 项』」 |
| F3 | 高 | 版本一致性有**第 6 处**未同步：`harness.py` argparse 描述仍 `v3.4.2` | 已改 3.17.0 |
| F4 | 中 | `result-envelope.yaml`（+50 行）与 `domain_config.yaml`（+92 行）的 `version:` 键仍停 3.12.0 / 3.3.0 | 已更新为 3.17.0 |
| F5 | 中 | 第 23 项的 40 处域绑定残留**未被 CHANGELOG 登记** | 已登记为已知瑕疵 #6（含具体文件与词例） |
| F6 | 中 | 包根残留本轮自跑的坍缩产物 `.harness-runs/`（已 gitignore，但第二副本无此目录 → 运行时层不一致） | 已清除 |
| F7 | 中 | `.workbuddy/harness_trace.jsonl` **被 git 跟踪**，含 8 行用户本机绝对路径 → 随分发包泄漏本地目录结构 | 已从版本库移除（两树）并加 `.gitignore` |

**F1 暴露的更深一层（已修）**：体检第 17 项「悬空脚本引用」的正则只匹配**裸文件名**
（`` `name.py` ``），**带相对路径的引用**（`references/xxx.py`）完全不被扫到——
所以它既看不见 F1，也看不见我自己修完 F1 后 `spawn-protocol.md` 里残留的同款悬空引用。
**为拦截这类缺陷而建的检查，看不见同类缺陷。** 现正则同时匹配带路径的引用并按
「相对包根是否存在」判定；补强后**当场又抓出一个此前隐藏的悬空引用文件**——`references/spawn-protocol.md`，该文件内有 5 处（`:132/:138/:141/:144/:159`）未被扫到。

**第 2 轮独立复核追加的两项（已修）**：
- **R1（高·用户可见破命令）**：`README.md:35`（自查命令）与 `INSTALL.md:196/206/276`（检查命令）仍指向
  `references/check_external_deps.py` → 按文档执行 `EXIT=2`、No such file。
  **危害比原 F1 更大**：README 的「自查命令」是用户换机后验证外部依赖的**第一入口**。
  已全部改为 `python3 scripts/check_external_deps.py`。
- **R2（中）**：`scripts/check_external_deps.py` 头部仍写「本脚本刻意不放在 scripts/」「待体检第 23 项落地后…」——
  与同文件下方「已归位 scripts/」**自相矛盾**，且含被明令禁止的失效承诺。已改为如实登记。
- **第 17 项补强的三个追加盲区**（均由第 2 轮独立测试实测发现并已修）：
  ② 扫描范围漏了包根 `README.md`/`INSTALL.md`（用户最先看的两份文档）→ 已纳入；
  ③ 匹配形态漏了「命令行无反引号」与「裸路径」→ 已加（现覆盖反引号裸名/反引号带路径/命令行/裸路径/连字符目录 5 种）；
  ④ 首段字符类不含连字符 → `shared-core/…` 整体逃逸 → 已修并加负向边界断言防子串误配；
  ⑤ **变量/占位符路径**（`$EXPERT_DIR/…`、`<WorkBuddy>/…`）静态不可判定 → 明确**跳过**（否则是假阳性），
  并在代码注释登记为人工复核项。`CHANGELOG.md` **刻意不纳入扫描**（历史日志里的旧脚本名是记录，不是会被照抄的命令）。

**F8/F9**：CHANGELOG 原写「体检 23/23 全绿」不精确（实为 21 ✓ + 2 ℹ）、
已知瑕疵 #5 的 trace 事件数「9 个」夸大（实测 7 个）——两处均已按实测修正。
**方向对、数字错**的两类失准，正是本轮要治的病。

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

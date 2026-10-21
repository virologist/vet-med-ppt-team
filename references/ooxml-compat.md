# OOXML 兼容性病例库（v3.2.0-batch2）

> WF-2R D11 防线病例库。每个病例 5 字段：**症状 / 根因 / 触发步骤 / 防线 / 检查码**。
> 字段 `last_seen` + `frequency` 机器可读，便于缺陷回流协议追踪。
> 性质：**与学科无关**——OOXML 工程问题，任何 subject-domain 课件都适用。

---

## 病例 1｜PKG-001 删页残留（zip 重复条目）

- **症状**：Office 365 打开课件时弹"需要修复"；recover 后内容缺失或乱序
- **根因**：python-pptx 1.0.2 删页可能只移 `sldIdLst` 中条目，**未从 zip 包清除 slide part**；自建页再写入时同名条目共存
- **触发步骤**：
  1. 课件有 N 张幻灯片
  2. 调用 `prs.slides[0]._element.getparent().remove(...)` 或类似部分删除
  3. 重新保存 → zip 内 `slide1.xml` 重复
- **防线**：
  - 删页 = `drop_rel` + clean 双步，repack 后跑 zip 重复名检测
  - ooxml_lint PKG-001 ERROR 阻断
- **检查码**：PKG-001
- **last_seen**：2026-10-14 / **frequency**：0（v3.1.0 课程工作区 4 份样本实证 0 命中）

## 病例 2｜deepcopy 复制页导致 rels 重复

- **症状**：复制页后保存，Office 365 弹修复；recover 后部分图/图表丢失
- **根因**：deepcopy 形状时把 slideLayout/slideMaster 的 rels 一并复制 → zip 出现 `Duplicate name: ppt/slideLayouts/slideLayout1.xml`
- **触发步骤**：
  1. 用 lxml `copy.deepcopy(shape.element)` 复制形状
  2. 写入新 slide 时未隔离 slideLayout/slideMaster/theme rels
  3. 保存 → rels 重复
- **防线**：
  - 跨稿深拷贝**禁复制** layout/master/theme rels
  - 复制后重编 `cNvPr id`（避开现有 id 集合）
  - ooxml_lint PKG-001 阻断
- **检查码**：PKG-001
- **last_seen**：2026-10-14 / **frequency**：0

## 病例 3｜悬空 rId（REL-001）

- **症状**：课件打开后部分图/图表显示 X 占位或丢失
- **根因**：rels 文件中 `Relationship Id="rIdN" Target="..."` 指向不存在的 part（如手工编辑后忘了恢复）
- **触发步骤**：
  1. 删 ppt/media/ 下某个媒体文件
  2. 但 slide.rels 中 rId 仍指向它
  3. 打开后图丢失
- **防线**：
  - 删媒体时同步删 rels
  - ooxml_lint REL-001 ERROR 阻断
- **检查码**：REL-001
- **last_seen**：2026-10-14 / **frequency**：0

## 病例 4｜Content_Types 漏登记（CT-001）

- **症状**：Office 365 弹修复
- **根因**：手工加 part（如新 slide xml）但未在 [Content_Types].xml 中登记 Override，且 part 扩展名无 Default Extension 覆盖
- **触发步骤**：
  1. 业务逻辑加新 slide XML
  2. 未更新 Content_Types
  3. 打开报错
- **防线**：
  - 加 part 三件套：part + rels + Content_Types Override（lxml 必走）
  - ooxml_lint CT-001 ERROR 阻断
- **检查码**：CT-001
- **last_seen**：2026-10-14 / **frequency**：0

## 病例 5｜cNvPr id 冲突（ID-001/002/003）

- **症状**：Office 365 弹修复；recover 后部分元素错位
- **根因**：`p:cNvPr id` 在同一页内必须唯一；`p:sldLayoutId` / `p:sldMasterId` 全局唯一。复制页/母版未重编 id
- **触发步骤**：
  1. deepcopy 整页后插入
  2. id 未重编
  3. 与原页 id 冲突
- **防线**：
  - deepcopy 形状后重编该页 `cNvPr id`
  - 跨稿深拷贝后重编 `sldLayoutId` / `sldMasterId`
  - ooxml_lint ID-001/002/003 ERROR 阻断
- **检查码**：ID-001 / ID-002 / ID-003
- **last_seen**：2026-10-14 / **frequency**：0

## 病例 6｜XML 非法控制字符（XML-002）

- **症状**：课件打开时 XML 解析失败；Office 365 弹修复
- **根因**：a:t 标签内含 0x00-0x08、0x0B、0x0C、0x0E-0x1F 等 XML 1.0 不允许字符；多来自复制粘贴外部数据
- **触发步骤**：
  1. 从 PDF/Word/网页复制文本
  2. 含控制字符（如换页符 0x0C）
  3. 粘贴进 PPT
- **防线**：
  - 粘贴前 sanitize
  - ooxml_lint XML-002 WARN 明示
- **检查码**：XML-002
- **last_seen**：2026-10-14 / **frequency**：0

## 病例 7｜md5 复核（OneDrive 同步——v3 修正为低危但保留）

- **症状**：写回活跃文件后，再打开课件报损坏
- **根因**：OneDrive/网盘同步工具在写回瞬间可能截断文件（实测 0 概率但理论存在）；本地编辑器锁文件导致部分写入
- **v3 修正（2026-10-14）**：用户实锤 OneDrive **未实际同步**（仅为残存文件名），此风险降为低危
- **防线**：
  - 写回后 md5 复核（轻量防线）
  - ooxml_lint XML-001 well-formed 检查（捕获截断导致的 XML 损坏）
- **检查码**：XML-001（间接）
- **last_seen**：2026-10-14 / **frequency**：未触发（v3 修正后）

---

## 病例 8｜图片单维尺寸导致版式失控（GEO-001）

- **症状**：插入图片后宽度撑爆页面（或高度失控），压盖既有文字框，制造一批新的重叠红灯
- **根因**：`add_picture` 只约束一维（常见：只传 `height`），另一维由源图宽高比决定；源图比例与版面预期不符时即失控
- **触发步骤**：
  1. 读源图（横版/长图）
  2. 只传 height 插入
  3. 实际宽度超出可用矩形 → 越界 + 与相邻文本框重叠
- **防线**：插入前读源图宽高比，**宽高双约束**（先按可用矩形等比缩放，两维显式传入）；插入后立即跑越界 + 重叠检测
- **检查码**：GEO-001
- **last_seen**：2026-10-17 / **frequency**：1

## 病例 9｜表格文本取不到（TXT-001）

- **症状**：用 `shape.text_frame` 读表格文字返回空，替换动作静默失败（脚本报成功但页面没变）
- **根因**：表格是 `graphicFrame`，文本在 `cell.text_frame` 内，`shape.has_text_frame` 为 False
- **触发步骤**：
  1. 遍历 `slide.shapes`
  2. 未判 `shape.has_table`，直接取 `text_frame`
  3. 写回后表格原样不动
- **防线**：先判 `shape.has_table` → 表格走 cell 级遍历；兜底用 lxml 遍历 `a:t` 节点做整节点替换；**替换后必须回读校验**
- **检查码**：TXT-001
- **last_seen**：2026-10-17 / **frequency**：1

## 病例 10｜跨 run 文本整串匹配失效（TXT-002）

- **症状**：目标串在页面上肉眼可见，脚本却报 MISS；把 MISS 当缺陷上报，产出一批假阳性
- **根因**：一句文本被拆进多个 `a:t`/run（编辑历史、格式变化、粘帖来源不同都会拆分），整串比对必然失败
- **触发步骤**：
  1. 以整句为目标串做 `in` / `==` 匹配
  2. 该句跨 3 个 run
  3. 报 MISS
- **防线**：匹配前**规范化**（合并节点文本 → 去空白与全半角差异 → 去软换行）再比对；写回走整节点重写而非按 run 拼接；**机器 MISS 一律人工复核后才定性，不得直接计为缺陷**
- **检查码**：TXT-002
- **last_seen**：2026-10-17 / **frequency**：1

## 病例 11｜GROUP 子元素坐标误判越界（GEO-002）

- **症状**：组合形状被判"文字越界/出画布"，实际显示正常
- **根因**：组合内子元素坐标是组内相对坐标，真实位置 = `off + (child − chOff) × ext / chExt`；直接拿子元素 off 与画布比必然误报
- **触发步骤**：
  1. 遍历页内形状做越界检测
  2. 未判 GROUP，直接取子元素 off
  3. 误报越界
- **防线**：越界检测对 GROUP 先做坐标换算再判定；无换算能力时对该页标"未判定"，禁止按误报执行"修复"
- **检查码**：GEO-002
- **last_seen**：2026-10-17 / **frequency**：1

## 病例 12｜新增页标题缺失（CTX-001）

- **症状**：新建页后页面上没有标题；或页重排后标题/内容错位
- **根因**：① `add_slide` 后 `shapes.title` 可能为 None 或空文本（布局占位符未自动填充）；② 按 `sldIdLst` 索引定位写入，重排后索引漂移
- **触发步骤**：
  1. `add_slide(layout)` 后直接写正文
  2. 依赖 `shapes.title` 存在
  3. 新页无标题；后续重排后按索引写入落到错页
- **防线**：新增页后**二次校验标题**，缺失即补文本框；页移动/重排后按 slide 对象（非序号）定位写入，重排结束再全量回读标题清单
- **检查码**：CTX-001
- **last_seen**：2026-10-17 / **frequency**：1

## 病例 13｜插入物与既有形状空间冲突（GEO-003）

- **症状**：向既有页面插入图注/流程条/时间轴后，门禁新增多处"元素重叠"（实测一轮 +5 处，重叠率 21%–76%）
- **根因**：页面底部区域（约 6.4in 以下）常被原生标签、页脚、装饰条、栏目块占用；插入前只看"页面下方还有空间"的直觉，未逐形状核对 `(top, bottom)` 区间
- **触发步骤**：
  1. 选定插入位（如"页面底部 6.72in"）
  2. 未枚举该页全部形状几何
  3. 插入框与既有标签区间相交 → 门禁重叠红灯
- **防线**：
  - 插入前强制**空间审计**：枚举目标页全部形状区间，插入区间与既有区间重叠率必须为 0%
  - 无空隙时按序降级：压缩单行短注 → 完整内容移讲稿备注（页面留短注）→ 缩宿主框腾位 → 挂账
  - 新元素文字规格**创建时即达合规**（正文 ≥12pt），禁"先插后调"两步走
- **检查码**：GEO-003
- **last_seen**：2026-10-17 / **frequency**：2（v6 流程条 +8、v7 图注 +5，同类两次 → 触发规则化）

## 病例 14｜写入属性名凭记忆猜测（API-001）

- **症状**：批量写入部分条目失败（如 chart 标题报 `UNSUPPORTED props: chartTitle`），原子事务下**整批回滚**，已成功的条目也不落盘
- **根因**：写入属性名按印象拼写（chartTitle），未查工具的能力参考；且不知道 batch 为原子语义——一条失败 = 全批回滚
- **触发步骤**：
  1. 批量 JSON 混合多种操作（文本 + 图表 + 备注）
  2. 其中图表标题用猜测属性名
  3. 执行报 `23 succeeded, 5 failed (atomic: no changes were applied)`——全批作废
- **防线**：
  - 首次使用任何写入属性前查 `officecli help <format> <element>`（报错信息会列出全部合法属性名，直接采纳）
  - **异质操作分批**：shape 文本 / chart / notes 分开成批，避免单点失败放大为整批回滚
  - 失败信息里的 `@id` 不匹配（No shape found with @id=X）说明 id 是**页内作用域**，跨页不可复用记忆值，须逐页实测
- **检查码**：API-001
- **last_seen**：2026-10-17 / **frequency**：1

---

## 跨学科差异说明

> 上述 12 病例**与学科无关**——OOXML 是通用标准，任何 subject-domain 的 PPTX 都会触发同类问题。
> v4 通用化实证：Batch 2 跨学科样本对照（≥1 个非动医学样本）将走同一套 lint 规则；若触发新 ERROR（如某种特殊 chart/SmartArt），新病例追加本文件。
> 频率统计由 harness.py 自动累计：每次 lint 输出写入 trace，相同 (code, location) 第二次出现 frequency++。

## 与 ooxml-lint.py 检查码对应

| 检查码 | 触发函数 | 严重性 |
|---|---|---|
| PKG-001 | 重复 zip 条目 | ERROR |
| PKG-002 | __MACOSX / .DS_Store | WARN |
| PKG-003 | Content_Types 缺失 | ERROR |
| PKG-004 | 关键扩展名未声明 | WARN |
| PKG-005 | Content_Types well-formed | ERROR |
| PKG-006 | 0 字节 part | WARN |
| REL-001 | rId 指向不存在 | ERROR |
| REL-002 | 重复 rId | ERROR |
| CT-001 | xml part 未登记 | ERROR |
| ID-001 | sldId 重复 | ERROR |
| ID-002 | sldLayoutId 重复 | ERROR |
| ID-003 | sldMasterId 重复 | ERROR |
| XML-001 | well-formed 失败 | ERROR |
| XML-002 | 非法控制字符 | WARN |
| XML-003 | 前导/尾随空格缺 xml:space | WARN |
| SYN-001 | presentation.xml.rels 缺失 | ERROR |
| SYN-002 | sldId r:id 不可达 | ERROR |
| SYN-003 | sldId 指向不存在 part | ERROR |
| SYN-004 | 孤立 slide（rels 有但 sldIdLst 无）| WARN |
| GEO-001 | 图片尺寸失控（v3.5.0 登记） | **人工检查项（lint 未实现）** |
| GEO-002 | GROUP 越界误报（v3.5.0 登记） | **人工检查项（lint 未实现）** |
| GEO-003 | 插入物空间冲突（v3.6.0 登记 → **v3.8.2 已实现**） | ✅ **lint 已实现**：WARN 级，矩形两两求交，阈值 `--geo-threshold` 默认 15%；GROUP 按 chOff/chExt 换算（顺带规避 GEO-002） |
| TXT-001 | 表格文本取不到（v3.5.0 登记） | **人工检查项（lint 未实现）** |
| TXT-002 | 跨 run 匹配失效（v3.5.0 登记） | **人工检查项（lint 未实现）** |
| CTX-001 | 新增页标题缺失（v3.5.0 登记） | **人工检查项（lint 未实现）** |
| API-001 | 写入属性名猜测（v3.6.0 登记） | **人工检查项（lint 未实现，且结构性不可实现）** |

> ⚠️ **实现状态声明（反自评失真铁律，v3.8.2 更新）**：GEO/TXT/CTX/API 各码为病例登记。
> - **GEO-003 已于 v3.8.2 实现**（GeoChecker，WARN 级，实测样本：两框 75% 重叠正确报出、无重叠不误报）。
> - 其余各码 `scripts/ooxml_lint.py` **尚未实现**，仅作人工检查项与缺陷回流追踪用，未实现不得在门禁输出中记作"已检查通过"。
> - **API-001 属结构性不可实现**：它是写入时行为，成品 PPTX 里不存在"当初是否猜属性名"的痕迹；
>   防线在写入纪律（批量原子语义 + 首次属性名先查），不因"没法自动检"就宣称已检。

## 演进规则（v3 缺陷回流协议）

- 新病例出现 → 走缺陷回流（同类 ≥2 次修规则不修输出）→ 写入本文件
- 病例 5 字段必须齐：**症状 / 根因 / 触发步骤 / 防线 / 检查码**
- 频率统计：每次 lint 跑后自动追加 `last_seen`；`frequency` ≥ 3 触发规则修改
- 错误码统一：PPKG/REL/CT/ID/XML/SYN/GEO/API + 3 位数字（如 PKG-001）

## 与 WF-2R 衔接

- **S0**：原文件 lint 跑 → baseline_issue 标 WARN；用户裁决是否修复
- **S4 门禁**：lint 前置 ERROR→exit 1 阻断
- **verifier 复判**：lint baseline 对照（区分原文件坏 vs 我们改坏）
- **病例库 → 沉淀**：每条病例是知识资产，可被未来 AI 助手/培训材料引用

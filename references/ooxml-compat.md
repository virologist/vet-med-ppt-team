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

## 跨学科差异说明

> 上述 7 病例**与学科无关**——OOXML 是通用标准，任何 subject-domain 的 PPTX 都会触发同类问题。
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

## 演进规则（v3 缺陷回流协议）

- 新病例出现 → 走缺陷回流（同类 ≥2 次修规则不修输出）→ 写入本文件
- 病例 5 字段必须齐：**症状 / 根因 / 触发步骤 / 防线 / 检查码**
- 频率统计：每次 lint 跑后自动追加 `last_seen`；`frequency` ≥ 3 触发规则修改
- 错误码统一：PPKG/REL/CT/ID/XML/SYN + 3 位数字（如 PKG-001）

## 与 WF-2R 衔接

- **S0**：原文件 lint 跑 → baseline_issue 标 WARN；用户裁决是否修复
- **S4 门禁**：lint 前置 ERROR→exit 1 阻断
- **verifier 复判**：lint baseline 对照（区分原文件坏 vs 我们改坏）
- **病例库 → 沉淀**：每条病例是知识资产，可被未来 AI 助手/培训材料引用

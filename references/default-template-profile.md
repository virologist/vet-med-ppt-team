# 默认模板档案与核验报告（指纹 5fa78154）

> 建立：2026-10-22 · 用户指定：`无另行指定时统一套用本模板`
> 上位：`references/course-profile-defaults.md#6`（intake.template）
> 核验方式：**只读实测**（`theme_fingerprint.py` + `ooxml_lint.py` + python-pptx 直读），非目测。

## 1. 基本信息（实测）

| 项 | 实测值 |
|---|---|
| 路径 | `/Users/biodog/Library/CloudStorage/OneDrive-Personal/养禽与禽病防治/教材编写-刘/禽病防治技术PPT模板.pptx` |
| 大小 / 格式 | 15,210,456 B · Microsoft PowerPoint 2007+（OOXML 有效） |
| md5 | `8d899d8fe51b69c90ff1426bb9297b06` |
| 主题指纹 | **`5fa78154`**（sha256(clrScheme+fontScheme c14n)[:8]） |
| 规模 | themes=3 · masters=**1** · layouts=**2** · slides=**33** |
| 版式清单 | `[0] 空白`、`[1] 1_标题和内容` |
| 主题配色 | dk1 sys:000000 · lt1 sys:FFFFFF · dk2 #44546A · lt2 #E7E6E6 · accent1 #4472C4 · accent2 #ED7D31 · accent3 #A5A5A5 · accent4 #FFC000 · accent5 #5B9BD5 · accent6 #70AD47 · hlink #0563C1 · folHlink #954F72 |
| 主题字体 | major.latin=等线 Light · minor.latin=等线 |
| **实际用字** | **Microsoft YaHei（166 处 run）**——与主题 fontScheme 的"等线"**不一致** |
| 字号分布 | 14pt(43) · 28pt(25) · 24pt(25) · 72pt(20) · 20pt(19) · 36pt(10) · 48pt(8) · 40pt(4) · 60pt(2) · 32pt(1) |
| 对象构成 | 图片 33 · **原生表格 0** · **原生图表 0** · 组合 58 · 文本类 130 |
| lint 健康度 | **0 ERROR / 555 WARN**（552×GEO-003 + 3×XML-003） |

---

## 2. 三条硬约束（制作师必读，违反即返工）

### 约束① 版式**零占位符**——禁止按占位符填内容

实测：`空白` 与 `1_标题和内容` 两个版式的 `placeholders` **均为空列表**。
名为"标题和内容"却无占位符，说明版式仅保留背景/底纹，内容全靠每页硬摆。

- ❌ 禁止 `slide.placeholders[0].text = ...`（IndexError，或静默取到空）
- ❌ 禁止假设"套版式后标题会自动归位"
- ✅ 正确做法：**深拷贝同类型既有页**（`surgery_deck.py` 的跨稿深拷贝，遵守 Batch 2 三条防修复铁律：
  删页必 drop_rel / 禁复制 layout-master-theme rels / 每页 cNvPr id 重编），或新建文本框后**按模板既有同类页的坐标对齐**

### 约束② 页眉是**每页硬编码文本框**，不是母版页眉页脚

实测：母版 `placeholders` 为空、母版仅 2 个形状（矩形 28、矩形 9）。
页眉由每页名为「**文本框 18**」的 TEXT_BOX 承载，取值分布：`禽流感`×20 页、`感谢！`×8 页（其余页为空）。

- ⚠️ **换课题时必须逐页改**，改母版无效——这是最容易被漏掉、且漏了必然被用户发现的问题
- ⚠️ 新增页**必须手动复制该文本框**并改文案，否则新页无页眉（视觉不一致直接违反验收 V1）
- ✅ 制作后用确定性脚本扫一遍「文本框 18」取值分布，确保非空页取值一致

### 约束③ 模板**零原生表格/图表**——可编辑图表须从零建

实测：33 页中原生表格 0 个、原生图表 0 个，数据呈现靠图片与组合形状。

- 验收 C/V 要求"数据图须为原生可编辑对象"（`round-review-sop#3.3`）：
  **本模板无法继承图表样式**，只能用 python-pptx `add_chart` 从零建，并按主题配色手工着色
- 图表样式一致性判据：取色必须落在上表 `clrScheme` 十二色内（验收 V3 的机器判定依据）
- 表格同理：用 `add_table` 新建，字号对齐 14/20pt 两档

---

## 3. GEO-003 噪音与基线豁免（必须执行）

默认模板自身产生 **552 条 GEO-003 WARN**（典型：「矩形 9 × 矩形 10」重叠 63%），
绝大多数是**有意的底纹/色块叠放**，属模板固有设计。

若对新稿直接跑 lint，这 552 条会**淹没真正的新增遮挡**，使验收 V7（无文字溢出或遮挡）无法判定。

**强制用法**：

```bash
python3 scripts/ooxml_lint.py <新版.pptx> --geo-baseline "<本模板绝对路径>"
```

口径：与基线同页序、同名形状对、重叠率差 ≤5% 的重叠标记为 `inherited` → **只计 INFO 不阻断**；
其余为新增重叠 → 计入 WARN。**V7 通过判据 = 新增重叠数 0**。
`inherited` 条数须在自检清单中写明（不静默豁免）。

---

## 4. 沿用原稿版式的情形

用户规则：**已有原稿版式的沿用原稿**（不强制迁到本模板）。

判据：若原稿页面已有稳定版式且视觉自洽 → 沿用原稿，本模板仅作为**新建页与配色/字号的参照**；
若原稿版式混乱或缺失 → 套用本模板。该判断由 **pedagogy-architect + visual-slide-designer 联合给出**，
并在轮报写明"沿用/迁移"的理由，不由制作师自行决定。

---

## 5. 登记册说明

模板基因登记册（`template_registry.json`）位于**课程工作区** `<工作区>/.workbuddy/templates/`，
**不属专家包**（专家包随升级被覆盖）。开工时按 `template_registry_usage.md` 三步执行：

```bash
PY=<python>; SCRIPTS=<专家包>/scripts; TPL="<本模板路径>"
$PY $SCRIPTS/theme_fingerprint.py "$TPL"                       # ① 指纹（已实测：5fa78154）
$PY $SCRIPTS/template_migrate.py register --template-name 禽病防治技术-v1 \
    --deck "$TPL" --registry <工作区>/.workbuddy/templates/template_registry.json \
    --domain animal-medicine/家禽                              # ② 登记（未登记则做）
$PY $SCRIPTS/template_migrate.py audit "$TPL" \
    --registry <工作区>/.workbuddy/templates/template_registry.json   # ③ 查册
```

> **本文件只记录核验事实与制作约束，不替代工作区登记册**；每次开工仍须在工作区完成登记（耗时数秒）。

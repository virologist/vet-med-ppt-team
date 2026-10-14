# OOXML 主题迁移技术笔记（v3.2.0-batch3）

> 支撑脚本：`scripts/theme_fingerprint.py`（指纹）· `scripts/template_migrate.py`（三档迁移）。
> 本文记录实现时踩过的 OOXML 结构细节与坑，供后续维护/扩展（如 T4 跨学科迁移）时查阅。

## 1. theme1.xml 的三级结构

```
ppt/theme/theme1.xml
└── a:theme
    └── a:themeElements
        ├── a:clrScheme    ← 12 个颜色槽：dk1/lt1/dk2/lt2/accent1-6/hlink/folHlink
        ├── a:fontScheme   ← majorFont + minorFont（各含 latin/ea/cs 三通道）
        └── a:fmtScheme    ← fillStyleLst/lnStyleLst/effectStyleLst/bgFillStyleLst
```

- **T1 只动前两个子树**（clrScheme + fontScheme），fmtScheme 保留源文件原值——跨 Office 版本的
  fmtScheme 差异大（效果样式数量不同），硬替换会造成渲染偏差。
- 颜色槽陷阱：`dk1/lt1` 实际存储的是 `sysClr`（窗口文本/背景）或 `srgbClr`，两种形态都要兼容。
  我们按**子树整体 deepcopy 替换**处理，不逐槽比对，天然规避形态差异。

## 2. Theme 指纹算法（为什么不含 fmtScheme）

- 算法：`sha256( c14n(clrScheme) + c14n(fontScheme) )[:8]`，lxml 的 W3C canonicalization。
- c14n 的作用：消除属性顺序/自闭合标签/空白差异。同一模板在 WPS 与 PowerPoint 间互存后
  指纹不变，靠的就是这一步。
- **fmtScheme 不入指纹**：Office 2010/2016/365 保存同一主题时 fmtScheme 的默认效果样式存在
  版本级差异，入指纹会导致"同主题不同指纹"，误报模板漂移。
- 布局清单（layout names）不入指纹：它们是 T2/T3 的评估维度，由 dry-run 单独报告。

## 3. T1（主题级）重打包的三个坑

1. **__MACOSX / .DS_Store**：Finder 解压再压缩的 zip 会混入垃圾条目，重打包时必须跳过，
   否则 PowerPoint 打开报"需要修复"。
2. **[Content_Types].xml 不变**：T1 只替换 part 内容，不改部件清单，无需动 Content_Types。
3. **压缩级别**：用 `ZIP_DEFLATED` 即可；不要试图保持原 zip 的压缩顺序，PowerPoint 不敏感。

## 4. T2（母版级）注册链——三处必须同步，缺一即打不开

T2 把模板的 slideMaster + layouts + theme 注入源稿，注册链为：

| # | 部件 | 动作 |
|---|---|---|
| 1 | `ppt/slideMasters/slideMasterN.xml` + 对应 layouts + themeN.xml | 注入 part |
| 2 | `ppt/_rels/slideMasterN.xml.rels` | 注入对应 rels（layout/theme 指向） |
| 3 | `ppt/presentation.xml` 的 `<p:sldMasterIdLst>` | 追加 `<p:sldMasterId id="max+1" r:id=…/>` |
| 4 | `ppt/_rels/presentation.xml.rels` | 加指向新 master 的 rId |
| 5 | `[Content_Types].xml` | **补 Override**（CT-001 防线）：每个新 part 都要有 ContentType 声明 |

- 漏 #5 是最常见事故：part 存在但无 Override，PowerPoint 直接判文件损坏。
- **同名 part 冲突**：源稿已有 `slideMaster2.xml` 时，我们采取保守策略——跳过注入并 WARN
  降级为 T1，不自动重编号。自动重编号要级联改所有 rels，风险收益不成比例。

## 5. T3（重灌级）防修复三铁律

T3 = 空稿重建 + 逐页深拷贝。三条铁律各对应一类"迁移后 PowerPoint 要修复"的损坏：

1. **删 slides 必须 drop_rel**：`prs.slides._sldIdLst` 只删节点不删 rels 会留下孤儿关系。
   正确姿势：先 `_sldIdLst` 移除节点，再 `prs.part.drop_rel(rId)`。
2. **跨稿深拷贝禁复制 slideLayout / slideMaster / theme rels**：页面 XML 里可能内嵌指向
   源稿 layout 的引用，deepcopy `spTree` 时只拷形状子节点（跳过 `nvGrpSpPr`/`grpSpPr`），
   rels 只重建 slide 级（图片/媒体/超链接），layout 一律指向目标稿的 layout。
3. **每页 cNvPr id 重编**：不同页的形状 id 可能撞车（OOXML 只要求页内唯一，但跨页复制时
   注释/动画引用会乱），迁移完统一 `id=1..N` 重编。

## 6. rels 重建的语义区分

- **external rels**（超链接）：`get_or_add_ext_rel()`，TargetMode="External"，Target 原样保留。
- **internal rels**（图片/媒体/嵌入对象）：先深拷贝 part 内容再 `relate_to()` 建立指向**目标稿内
  新 part** 的关系。直接把 rels 指向源稿路径 = 交付后图片全裂。
- notes：只迁纯文本（`notes_text_frame.text`），notesSlide 的 rels（音频批注等）不迁——
  教学场景音频批注几乎为零，风险收益不成比例。

## 7. 已实测踩坑记录

| 现象 | 根因 | 处置 |
|---|---|---|
| 测试里造蓝主题改 `4472C4` 无效 | python-pptx 默认模板 accent1 是 `4F81BD`（Office 2007 默认，非 2013+） | 替换值改为 4F81BD，并加 `assert theme_new != theme` 防回归 |
| dry-run 评估 T2 报 layout miss | layout 名匹配是**精确字符串**，"标题和内容"≠"标题和内容(自定义)" | 保留精确匹配 + 报告中列出目标可用 layout 名，人工裁决 |
| chart 数量统计失真 | 图表可能被 layout 引用而非 slide 引用 | `_pre_scan_chart_refs` 在 zip 层扫 slide 级 rels，chart 在 rels 中即计 R-SHARED-CHART |
| WPS 保存的 pptx repack 后变慢 | WPS zip 条目无压缩级别声明 | 无需处理，PowerPoint/LibreOffice 均正常打开 |

## 8. 迁移决策速查（与 CLAUDE.md 索引行配套）

```
换模板前：
1. python theme_fingerprint.py <目标模板.pptx>   → 查指纹
2. grep 指纹 .workbuddy/templates/template_registry.json
   ├─ 已登记 → 直接用（先登记的原则是"复用先登记"）
   └─ 未登记 → register 登记后再用
3. 迁移档位选择：只换色/字体=T1 · 需要模板版式=T2 · 版式/母版全部对齐=T3
4. 先 dry-run 看 6 类风险码，高风险页 >50% 即停（exit 1）
5. 正式迁移必带 --confirm，成功后自动跑 lint，ERROR≠0 视为失败
```

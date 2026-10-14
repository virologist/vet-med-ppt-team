# markitdown 0.1.7 实测报告（v3.2.0-batch1）

> 实测日期：2026-10-14
> 实测样本：4 份挂账课件（备份于 `.harness-runs/M4-M7_重诊断/sample_extract/`）
> 实测目标：3 项行为——备注保留度 / 图表数据表覆盖度 / `[unsupported chart]` 出现条件
> 性质：**事实记录**，只描述实测结果，不写期望；如实不达预期，调实现不调预期。

---

## 1. 样本与背景

| 样本 | 大小 | 幻灯片 | 备注覆盖（deck_registry v7） |
|---|---|---|---|
| 2.1高致病性禽流感防控.pptx | 41.5 MB | 65 | 100% |
| 7. 禽流感.pptx | 8.0 MB | 30 | 0% |
| 禽流感病毒全链攻防术.pptx | 7.7 MB | 29 | 0% |
| 禽流感鉴别诊疗要点.pptx | 35.0 MB | 99 | 8.1% |

---

## 2. 实测 1｜备注保留度

| 样本 | markitdown 输出 `### Notes:` 块数 | 与 deck_registry 备注覆盖率对照 |
|---|---|---|
| 2.1高致病性禽流感防控.pptx | 47 | 47/65 = 72%（deck 报 100%，有差）|
| 7. 禽流感.pptx | 0 | deck 报 0%，**一致** |
| 禽流感病毒全链攻防术.pptx | 29 | deck 报 0%，**不一致**（markitdown 出了备注）|
| 禽流感鉴别诊疗要点.pptx | 8 | 8/99 = 8.1%，**与 deck 8.1% 一致** |

**结论**：
- 3/4 样本与 deck_registry 备注覆盖**有出入**；最大差异在"全链攻防术"——deck 报 0% 但 markitdown 拿到 29 个 Notes 块。
- 解释候选：① deck_registry 备注覆盖率基于"speaker note 字段"判定，markitdown 按"### Notes:" 段落判定，统计口径不同；② 备注挂载位置不同（slide notes vs custom XML）。
- **对 WF-2R 影响**：S2 严真奥读备注时**应同时看 markitdown 文本层与 extract_assets 的源课件备注字段**，不能仅以任一方为准。

---

## 3. 实测 2｜图表数据表覆盖度

**实测方法**：markitdown 0.1.7 转换后用 grep 数"Category/Values"型数据表段数 + extract_assets 提取的 chart 数对照。

| 样本 | extract_assets 抽到 chart 数 | markitdown 数据表段 | 覆盖度 |
|---|---|---|---|
| 2.1高致病性禽流感防控.pptx | 0 | 0 | — |
| 7. 禽流感.pptx | 0 | 0 | — |
| 禽流感病毒全链攻防术.pptx | 0 | 0 | — |
| 禽流感鉴别诊疗要点.pptx | 0 | 0 | — |

**结论**：
- **4 份挂账样本中 0 个原生图表（chart shape）**——教学课件以"图（image）"为主，几乎不用原生数据图表。
- extract_assets 的 chart 三件套（xml/xlsx/csv）能力**当前未在本批样本触发**，但作为通用能力保留。
- 4 份样本图像 94/20/22/80 张，**图片是 S1 真值的主战场**。

---

## 4. 实测 3｜`[unsupported chart]` 出现条件

| 样本 | markitdown `[unsupported chart]` 出现数 | extract_assets image/chart 分流 |
|---|---|---|
| 全部 4 份 | **0** | 0 chart / 94-20-22-80 image |

**结论**：
- 0 次出现 → 在这 4 份样本**无法复现** markitdown 文档中"`[unsupported chart]` 占位"行为。
- 可能原因：教学课件 0 原生 chart，所以该路径**未被触发**。
- 不能据此推断"markitdown 不输出 [unsupported chart]"，应理解为"本批样本未触发该路径"。
- 对 WF-2R 影响：当未来遇到含 chart 的课件时，需在 S1 阶段重跑 markitdown 看是否出 [unsupported chart]，并据实调整 extract_assets 的 chart 兜底逻辑。

---

## 5. 机器可读附录（JSON）

```json
{
  "markitdown_version": "0.1.7",
  "tested_at": "2026-10-14",
  "tester": "extract_assets/1.0.0 + markitdown 0.1.7",
  "samples_path": ".harness-runs/M4-M7_重诊断/sample_extract/",
  "decks": [
    {
      "deck": "2.1高致病性禽流感防控.pptx",
      "size_bytes": 43571497,
      "total_slides": 65,
      "extract_assets": {"image": 94, "table": 4, "ole": 1, "chart": 0, "video": 0, "diagram": 0, "skipped": 557, "zero_byte_media": 0, "shared_charts": 0},
      "markitdown": {"notes_blocks": 47, "unsupported_charts": 0, "total_chars": 47147},
      "registry_note_coverage_v7": 1.0,
      "verdict": "markitdown 备注 72% vs deck 100%（口径差）；图表 0；资产层补位为主"
    },
    {
      "deck": "7. 禽流感.pptx",
      "size_bytes": 8427104,
      "total_slides": 30,
      "extract_assets": {"image": 20, "table": 1, "ole": 5, "chart": 0, "video": 0, "diagram": 0, "skipped": 187, "zero_byte_media": 0, "shared_charts": 0},
      "markitdown": {"notes_blocks": 0, "unsupported_charts": 0, "total_chars": 6107},
      "registry_note_coverage_v7": 0.0,
      "verdict": "markitdown 与 deck 备注覆盖一致 0%；图表 0；图片+ole 为主"
    },
    {
      "deck": "禽流感病毒全链攻防术.pptx",
      "size_bytes": 8096299,
      "total_slides": 29,
      "extract_assets": {"image": 22, "table": 1, "ole": 0, "chart": 0, "video": 0, "diagram": 0, "skipped": 473, "zero_byte_media": 0, "shared_charts": 0},
      "markitdown": {"notes_blocks": 29, "unsupported_charts": 0, "total_chars": 12656},
      "registry_note_coverage_v7": 0.0,
      "verdict": "markitdown 备注 100% vs deck 0%（口径差显著，需 S2 双源核验）"
    },
    {
      "deck": "禽流感鉴别诊疗要点.pptx",
      "size_bytes": 36743080,
      "total_slides": 99,
      "extract_assets": {"image": 80, "table": 0, "ole": 0, "chart": 0, "video": 0, "diagram": 0, "skipped": 120, "zero_byte_media": 0, "shared_charts": 0},
      "markitdown": {"notes_blocks": 8, "unsupported_charts": 0, "total_chars": 27884},
      "registry_note_coverage_v7": 0.081,
      "verdict": "markitdown 备注 8.1% 与 deck 完全一致；图表 0；图片 80 张为资产层核心"
    }
  ],
  "summary": {
    "total_samples": 4,
    "markitdown_unsupported_chart_seen": false,
    "chart_extraction_hit_rate": 0,
    "image_extraction_hit_rate": "94+20+22+80=216",
    "note_coverage_consistency": "2/4 一致，2/4 口径差"
  },
  "implication_for_wf2r": [
    "S1 必跑 extract_assets 作为图表/图片兜底（markitdown 0 chart / 0 unsupported_chart 触发不到该路径）",
    "S2 严真奥读备注时需 markitdown 文本层 + 源课件备注字段双源核验（2/4 样本口径差）",
    "S3 C 轨在教学课件域以图片重生为主，chart 兜底作为通用能力保留（未来非教学课件触发）",
    "打样 80 张图的「禽流感鉴别诊疗要点.pptx」是 S2/S3 最佳试炼场"
  ]
}
```

---

## 6. 与 F1 extract_assets 联动的关键事实

1. **0 字节媒体**：4 份样本 0 命中 → D11（修复对话框）苗子告警路径**当前未触发**；Batch 2 lint 跑存量扫描时可能检出（课件外的样本）。
2. **共享 chart**：0 命中 → D4（图表联动）告警路径当前未触发；同上。
3. **OLE**：4 份样本 1+5+0+0=6 个 OLE 资产，全走"原样留存"降级路径（olefile 解析未跑——需人工打开），未阻断。

---

## 7. 局限与下一步

- 样本规模 4 份全为"动物医学教学课件"，结论对其他领域 PPT（如汇报型、论文配图）外推需谨慎。
- Batch 2 lint 跑**49 件已交付课件**时会得到更广的样本分布，到时可补一份 lint 视角的实测量。
- 若未来有含原生图表的课件，markitdown 0.1.7 在该路径的实测需重跑。

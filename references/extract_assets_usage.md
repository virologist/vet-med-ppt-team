# extract_assets.py 使用手册（v3.2.0-batch1）

> WF-2R 旧课件诊疗流水线 S1 资产化转换层。版本：`extract_assets/1.0.0`。
> 适用读者：主理人（编排）、严真奥（诊断输入消费）、屠明熙（视觉诊断消费）、郅作基（台账字段）、开发者（维护）。

---

## 1. 这是干什么的

把 PPT 嵌入元素（图、图表、视频、表格、SmartArt、OLE）从"靠人眼看"变成"机器可读 + 双向校验"，生成 `manifest.json` 与资产目录，为 S2 诊断、S3 C 轨施工、Batch 2 lint、D4 联动告警提供真值。

**不做啥**：不产图、不解析图像内容（语义分析属 Batch 5 扩展项）、不修改原课件、不覆盖已有 manifest（除非 `--force`）。

---

## 2. 快速上手

```bash
# 最小命令（输出落 <课件>_assets/ 跟课件同目录）
python3 scripts/extract_assets.py /path/to/课件.pptx

# 干跑（不写盘，输出 JSON 预测）
python3 scripts/extract_assets.py /path/to/课件.pptx --dry-run --json

# 显式指定输出目录
python3 scripts/extract_assets.py /path/to/课件.pptx --out-dir /tmp/my_assets --force
```

期望输出：
```
[10:30:01] INFO  manifest 已写入: /path/to/<课件>_assets/manifest.json（42 条）
[10:30:01] INFO  ✓ 全部成功（42 条资产，99 张幻灯片）
```

---

## 3. 输出目录结构

```
<课件>_assets/
├── manifest.json          # 主索引（六字段 + 7 派生）
├── images/                # 原始图二进制（不重新编码）
│   ├── a-001.png
│   ├── a-002.jpg
│   └── ...
├── charts/                # 图表三件套
│   ├── a-005.xml          # chart XML
│   ├── a-005.xlsx         # 关联 Excel（如有）
│   └── a-005.csv          # 数据表
├── videos/                # 媒体二进制
│   ├── a-010.mp4
│   └── ...
├── tables/                # 表格 MD
│   ├── a-015.md
│   └── ...
├── diagrams/              # SmartArt XML 子目录
│   ├── a-020/
│   │   ├── data1.xml
│   │   ├── layout.xml
│   │   ├── colors.xml
│   │   └── quickStyle.xml
│   └── ...
└── ole/                   # OLE 对象（olefile 解析或原样留存）
    ├── a-025.bin
    └── a-025.note.txt     # 解析说明 + 人工打开提示
```

---

## 4. manifest 字段表

**顶层字段**：
| 字段 | 含义 | 消费方 |
|---|---|---|
| `schema_version` | 1 | 机器校验 |
| `extractor_version` | extract_assets/1.0.0 | 版本追踪 |
| `source_deck` | 原课件绝对路径 | 跨会话锚点 |
| `source_deck_sha1` | 原课件 sha1 | 防止 active 漂移 |
| `source_deck_mtime` | 原课件 mtime | 同上 |
| `extracted_at` | 提取时间 ISO8601 | 时间锚点 |
| `total_slides` | 幻灯片数 | 课时匹配 |
| `assets_count` | 资产条数 | 计数（反自评失真） |
| `assets_by_type` | 按 type 分布 | 诊断概览 |
| `skipped` | 跳过的非资产形状数 | 透明 |
| `unknown_shapes` | 未知 shape 数（上限 10） | 透明 |
| `zero_byte_media` | 0 字节媒体数（D11 苗子） | 苗子告警 |
| `large_media` | >50MB 媒体数（D11 苗子） | 苗子告警 |
| `shared_charts` | chart part 引用数 >1 数（D4 联动） | 联动告警 |
| `warnings` | 详细告警列表 | 人工复核 |
| `assets[]` | 资产数组 | 详见下 |

**资产数组每条字段**（六字段 + 7 派生）：
| 字段 | 含义 | 消费方 |
|---|---|---|
| `asset_id` | 课件内唯一 | 引用锚点 |
| `type` | image/chart/video/table/diagram/ole | 分流 |
| `source_page` | 1-based 页码 | 渲染真值映射 |
| `shape_id` | 原 shape.name | 追溯 |
| `file` | 相对 `<out_dir>` 路径 | 文件路径 |
| `raw_part` | zip 内原始路径 | 回溯 |
| `render` | 渲染 PNG 路径占位 | Batch 2 补全 |
| `sha256` | 文件 sha256 | 跨课件去重 |
| `license_note` | 许可备注 | 复用合规 |
| `reuse_status` | 未决/已复用/已弃用 | 跨轮追踪 |
| `notes` | 自由文本 | 透明 |
| `chart_part_refs` | 共享 chart 引用数 | D4 联动 |
| `media_bytes` | 文件字节数 | D11 苗子 |
| `extracted_at` | ISO8601 | 时间 |
| `extractor_version` | extract_assets/1.0.0 | 版本 |
| `source_deck_sha1` | 父课件 sha1 | 防漂移 |
| `source_deck_mtime` | 父课件 mtime | 防漂移 |
| `pptx_schema` | pptx schemaVersion | 兼容性 |

---

## 5. 退出码语义

| 码 | 含义 | 应对 |
|---|---|---|
| 0 | 全部成功 | 直接消费 |
| 1 | 完整性断言失败（manifest 字段与实际不符） | 重跑或检查环境 |
| 2 | 形状识别异常（OLE/SmartArt 解析失败且无法降级） | 检查源文件 |
| 3 | 文件读取失败（IO/zip 损坏/路径无效） | 检查路径与权限 |
| 4 | 运行错误（脚本 bug/fixture 损坏/依赖缺失） | 走缺陷回流修脚本，不挂账课件 |

---

## 6. `--dry-run` 用法

**用途**：
- S0 阶段预估工作量（资产类型分布、风险项）
- 试运行（不污染磁盘）
- 与全量模式对比验证（drift 检测）

**输出**：
- 默认打印到 stderr（INFO 级日志）
- `--json` 同时打印 JSON 到 stdout（机器可解析）

**不创建任何目录与文件**（T8 用例验证）。

---

## 7. 已知坑与限制

1. **python-pptx 1.0.2 不暴露 `chart.chart_part`**：F1 改用 `chart.element.xml` 序列化 + `shape.part.rels` 关联遍历 xlsx。`raw_part` 在 chart 情况下可能为占位值（`ppt/charts/chartUnk-a-NNN.xml`），跨课件去重需二次校验 sha256。
2. **OLE 解析依赖 olefile**：宿主 venv 一次性 `pip install olefile`；未装则 OLE 走"原样留存 .bin + note.txt"降级，不阻断。
3. **SmartArt 嗅探按 OOXML 命名空间**：python-pptx 不暴露 SmartArt 枚举，按 XML 探针 dgm:relIds 命中。
4. **PLACEHOLDER 误入图片路径**：用 blip 元素是否存在区分，非图占位符归 `skipped` 计数。
5. **macOS LibreOffice 中文字体回退不稳**：本脚本不渲染 PNG，由 Batch 2 处理。

---

## 8. 与 WF-2R 的衔接

**S0 接单冻结**（主理人）：用 `--dry-run --json` 预估工作量（资产类型/风险/D11 苗子/D4 联动苗子）。
**S1 资产化转换**（本脚本）：跑全量，生成 `<课件>_assets/` 与 `manifest.json`。
**S2 三角色并行诊断**：
- 严真奥：用 `assets_by_type.chart` + `assets` 数组中 `notes` 字段判断"图与数据是否一致"；
- 苏学法：用 `source_page` 映射到 MD 内容；
- 屠明熙：只看渲染 PNG（Batch 2 补），不直接读 manifest。
**S3 C 轨图件重生**：用 `asset_id` 引用 → 按 `file` 取素材 → 改完后 `reuse_status` 改"已复用"。
**S4 门禁交付**：本批 0 字节媒体与共享 chart 数自动入台账，verifier 复判时核验。
**Batch 2 lint**：本批的 `source_deck_sha1` 与 `pptx_schema` 字段是 lint 基线对照的真值。
**Batch 5 verify_deck 扩展**：本批的 `manifest.json` 是新检查项（manifest 一致性 / 引用完整性）的输入。

---

## 9. 回归测试

```bash
# 8 例 + 4 subtest，本批独立可跑
python3 -m pytest scripts/test_extract_assets.py -v
```

用例：T1 纯文本 / T2 含图 / T3 含图表 / T4 0 字节媒体 WARN / T5 GroupShape 嵌套 / T6 4 份真课件 dry-run / T7 完整性断言触发 / T8 dry-run 无副作用。

本批回归测试**暂未并入** `scripts/test_harness.py`（保持单文件独立性，便于 pytest 直接跑），Batch 5 收口时统一并入。

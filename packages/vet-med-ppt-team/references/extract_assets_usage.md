# extract_assets.py 使用手册（v3.2.0-batch1 · v3.16.0 配图链路记录字段）

> WF-2R 旧课件诊疗流水线 S1 资产化转换层。版本：`extract_assets/1.0.0`。
> 适用读者：主理人（编排）、严真奥（诊断输入消费）、屠明熙（视觉诊断消费）、郅作基（台账字段）、开发者（维护）。
>
> **v3.16.0 变更（F8 配图链路补记录字段）**：新增 `width` / `height` / `source_url` / `doi_pmcid`
> 四个记录字段；`license_note` 默认值由「原课件自带」改为空字符串（**不默认可用**），
> `reuse_status` 默认「待核查」；manifest 统计区块给出「未登记许可的素材数」；
> 新增 `--require-license` 门禁。新增内容集中在 §4.1 / §4.2 / §4.3 / §4.4 / §10。

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
| `unlicensed_assets` | **未登记许可的素材数**（`license_note` 为空的条数，v3.16.0） | 许可核查工作量 |
| `unlicensed_asset_ids` | 未登记许可的 `asset_id` 清单（v3.16.0） | 逐条补登记 |
| `license_gate` | `{require_license: bool, passed: bool}`（v3.16.0） | 门禁审计 |
| `warnings` | 详细告警列表 | 人工复核 |
| `assets[]` | 资产数组 | 详见下 |

**资产数组每条字段**（六字段 + v3.16.0 新增 4 记录字段 + 7 派生）：
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
| `width` | 显示宽度 px（v3.16.0） | 清晰度判读 / 是否够教学用 |
| `height` | 显示高度 px（v3.16.0） | 同上 |
| `source_url` | 来源链接（v3.16.0） | 溯源 / 许可核查 |
| `doi_pmcid` | 文献标识 DOI/PMCID（v3.16.0） | 溯源 / Europe PMC 回查 |
| `license_note` | 许可登记（v3.16.0：空 = 未登记） | 复用合规 |
| `reuse_status` | 待核查/已复用/已弃用（v3.16.0：「未决」统一为「待核查」） | 跨轮追踪 |
| `notes` | 自由文本（含宽高取不到的原因） | 透明 |
| `chart_part_refs` | 共享 chart 引用数 | D4 联动 |
| `media_bytes` | 文件字节数 | D11 苗子 |
| `extracted_at` | ISO8601 | 时间 |
| `extractor_version` | extract_assets/1.0.0 | 版本 |
| `source_deck_sha1` | 父课件 sha1 | 防漂移 |
| `source_deck_mtime` | 父课件 mtime | 防漂移 |
| `pptx_schema` | pptx schemaVersion | 兼容性 |

---

### 4.1 v3.16.0 新增字段：取值口径与缺失语义

| 字段 | 取值口径 | 有值示例 | 缺失时写什么 | 缺失语义（**不等于**"合格"） |
|---|---|---|---|---|
| `width` | 形状**显示宽度** EMU ÷ 9525 取整（`round(EMU/9525)`，系数见 §10 `emu_per_px`） | `192` | `null` + notes 追加 `宽高未取得：<原因>` | 该形状没取到尺寸，**不可当作 0 也不可当作"够清晰"**；须人工打开原课件判读 |
| `height` | 形状**显示高度** EMU ÷ 9525 取整 | `192` | `null` + notes 追加 `宽高未取得：<原因>` | 同上 |
| `source_url` | 素材来源页面链接（人工登记或来源通道回填） | `https://europepmc.org/article/PMC/PMC1234567` | `""` | **来源未登记**，不得进"已溯源"口径 |
| `doi_pmcid` | 文献标识（DOI 或 PMCID，二选一填） | `10.3389/fvets.2023.1234567` / `PMC1234567` | `""` | **文献未登记**，无法回查原文与许可 |

> ⚠️ 口径说明：`width` / `height` 取的是**幻灯片上的显示尺寸**（EMU→px），不是位图固有分辨率。
> 一张 4000×3000 的图被缩到 1cm² 显示时，这里就是几十 px——判"清晰度是否够教学判读"
> 时必须看 `width`/`height`，不能只看文件字节数。

**取不到尺寸的常见原因**（会原样写进 `notes`）：
- `shape.width/height 读取失败（...）` —— 该形状类型不暴露尺寸属性；
- `shape.width/height 为 None` —— OOXML 里没写 `a:ext`；
- `shape 尺寸非数值（...）` —— 异常课件/损坏 XML；
- `shape 尺寸非正（w=.. h=.. EMU）` —— 尺寸为 0 或负；
- `换算后不足 1px（w=.. h=.. px）` —— 显示尺寸极小，按"取不到"处理而不是写 0。

### 4.2 旧 manifest 兼容策略（v3.16.0）

旧 manifest（本版之前生成）**可以直接读，不用重跑**。兼容由 `AssetRecord.from_dict()` /
`load_manifest_records(path)` 保证，规则如下（代码可测，见用例 T13）：

| 情况 | 处理 | 结果 |
|---|---|---|
| 缺 `width` / `height` 键 | 用默认值补齐 | `null`（**不是 0**） |
| 缺 `source_url` / `doi_pmcid` / `license_note` 键 | 用默认值补齐 | `""` |
| `license_note == "原课件自带"`（旧占位值） | 视为**未登记**：清空 `license_note`，`reuse_status` 归一为「待核查」，notes 追加 `旧占位许可值「原课件自带」已作废（v3.16.0），须人工重新登记` | 与"不默认可用"纪律一致 |
| `license_note` 为空但 `reuse_status` 是「未决」 | 归一为「待核查」 | 语义统一 |
| manifest 里出现本表未定义的键 | 忽略，不报错 | 前向兼容 |

> manifest 的 `schema_version` 仍为 `1`：新增字段是**向后兼容的增量**（缺键可容错），
> 不升版是为了不打断既有消费方；若下游强校验键集合，请按 §4.1 表做 `.get()` 兜底。
> 旧 manifest 的 `unlicensed_assets` / `unlicensed_asset_ids` / `license_gate` 三个统计键**没有**——
> 读到旧 manifest 时请自行按 `license_note` 是否为空统计，不要假定键存在。

### 4.3 许可核查步骤（陌生人照着跑）

> 纪律来源：`references/adjudication-rules.md` 原则六——**不默认可用**；许可不明 → 挂账或改走 OA 通道。

1. **先跑提取，看基数**（不写盘也能看）：
   ```bash
   python3 scripts/extract_assets.py /path/to/课件.pptx --dry-run --json | grep unlicensed
   ```
   输出里的 `unlicensed_assets` 就是要核查的条数；正式跑时日志也会打一行
   `未登记许可的素材数 = N`。
2. **正式提取**：`python3 scripts/extract_assets.py /path/to/课件.pptx`
3. **逐条补登记**（按 `manifest.json` 的 `unlicensed_asset_ids` 清单）：
   对每条素材确认三件事，然后手工改写该条的三个字段——
   - `source_url`：来源页面链接（找不到就留 `""`，**不许编造**）；
   - `doi_pmcid`：DOI 或 PMCID（Europe PMC / 期刊页取；无则 `""`）；
   - `license_note`：许可状态，写清楚口径，如 `CC-BY-4.0 · Europe PMC OA` /
     `需授权·已邮件申请（2026-10-23）` / `本单位自有素材` / `版权受限·弃用`。
   补完把 `reuse_status` 从「待核查」改成「已复用」或「已弃用」。
   - **判据**：只取 CC-BY / 开放获取；许可状态不明 → 挂账或改用 OA 通道（Europe PMC），
     不写"应该能用"这类模糊措辞。
4. **回看计数**：重跑（加 `--force`）后确认 `未登记许可的素材数 = 0`。
5. **交付前卡门禁**：`python3 scripts/extract_assets.py /path/to/课件.pptx --force --require-license`
   ——还有空许可就 exit 1 并列出 `asset_id`，不许带病交付。

### 4.4 `--require-license` 用法（v3.16.0）

- **默认关闭**：不加这个开关时，未登记许可只统计、不阻断（既有流程不受影响）。
- **开启后**：只要存在 `license_note` 为空的素材，就在 manifest 落盘后 exit 1，
  stderr 打两行——汇总行数 + `asset_id` 清单：

```bash
$ python3 scripts/extract_assets.py /tmp/demo.pptx --out-dir /tmp/demo_assets --force --require-license
[10:30:01] INFO  未登记许可的素材数 = 2
[10:30:01] ERROR 未登记许可：2 条素材（--require-license 已启用，须补登记后重跑）
[10:30:01] ERROR 未登记许可明细：a-001, a-002
[10:30:01] ERROR ✗ 许可门禁未过（exit 1）：按上方「未登记许可」明细补登记 license_note 后重跑
$ echo $?
1
```

全部登记完（`未登记许可的素材数 = 0`）或课件零素材时，同一条命令 exit 0。

---

## 5. 退出码语义

| 码 | 含义 | 应对 |
|---|---|---|
| 0 | 全部成功 | 直接消费 |
| 1 | 完整性断言失败（manifest 字段与实际不符）；<br>v3.16.0 起亦含 **许可门禁未过**（`--require-license` 命中空许可）与**许可纪律断言**（空许可却标了非「待核查」的 `reuse_status`） | 按 stderr 明细补登记 / 重跑或检查环境 |
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
# 14 例（T1-T14，含 4 subtest），本批独立可跑
python3 -m pytest scripts/test_extract_assets.py -v
```

用例：T1 纯文本 / T2 含图 / T3 含图表 / T4 0 字节媒体 WARN / T5 GroupShape 嵌套 / T6 4 份真课件 dry-run / T7 完整性断言触发 / T8 dry-run 无副作用。

v3.16.0 增补（F8 配图链路）：
- **T9** 新字段出现在 manifest 且有**真实取值**（2 张图 → `width`/`height` 为 int 且 > 0，不只看键存在）；
- **T10** `license_note` 默认值不再是「原课件自带」（为空）+ `reuse_status` 为「待核查」+ `unlicensed_assets` 计数正确；
- **T11** `--require-license`：CLI 端到端——有空许可 exit 1 且列出 `a-001`/`a-002`；全部登记（含零素材）exit 0；
- **T12** 许可纪律断言：空许可却标「已复用」→ 写盘前 exit 1；手工补齐许可后门禁返回 0 条；
- **T13** 旧 manifest 兼容：缺新字段容错为 `null`/`""`，旧占位值「原课件自带」作废并归一为「待核查」；
- **T14** 配置漂移哨兵：`references/asset-fields.yaml` 的值 == 代码内置回退值 == §10 表格列出的字段名集合，三者一致才过；同时断言 usage.md **不含第二份可解析副本**；
- **T15** `--force` 对已存在 out_dir 重跑 → exit 0（守 `mkdir` EEXIST 修复）。

本批回归测试**暂未并入** `scripts/test_harness.py`（保持单文件独立性，便于 pytest 直接跑），Batch 5 收口时统一并入。

---

## 10. 配置登记（机器源：`references/asset-fields.yaml`）

> ⚠️ **本节不是机器数据源**，只是人读说明与指向。真正的机器源是独立文件
> **`references/asset-fields.yaml`**——与包内既有惯例一致（机器可读配置一律是独立 yaml：
> `references/audience-profile-schema.yaml`、`references/result-envelope.yaml`；
> `verify_deck.py` 读的则是 `config/visual-rules.yaml`）。**本节刻意不留可解析副本**，
> 避免"配置该去哪找"的多源问题。

**读取方式**（`scripts/extract_assets.py#_load_asset_field_config()`，与
`verify_deck.py#_load_threshold()` 同风格）：显式路径 → `yaml.safe_load` →
失败（文件缺失 / pyyaml 未装 / YAML 语法错）则**告警并回退内置值**，不阻断提取。

**改名/改值纪律**：改 `references/asset-fields.yaml` 的任何值都会改变脚本行为——必须同步改
`scripts/extract_assets.py` 的 `_BUILTIN_ASSET_FIELD_CONFIG`，否则 T14 用例判「配置漂移」失败。

### 10.1 `asset_fields` 段（字段默认值 / 缺值提示语 / 换算系数）

| 键 | 值 | 作用 | 人读口径 |
|---|---|---|---|
| `emu_per_px` | `9525` | EMU→px 换算系数 | 见 §4.1 |
| `width_default` | `null` | 取不到尺寸时的填充值 | **null 不是 0** |
| `height_default` | `null` | 同上 | 同上 |
| `source_url_default` | `""` | 无来源链接时的填充值 | 见 §4.1 |
| `doi_pmcid_default` | `""` | 无文献标识时的填充值 | 见 §4.1 |
| `license_note_default` | `""` | 许可登记默认值 | **不默认可用** |
| `reuse_status_default` | `"待核查"` | 未登记许可时的 `reuse_status` | 见 §4.3 |
| `legacy_license_placeholders` | `["原课件自带"]` | 旧 manifest 中的无效占位许可值，读到即作废 | 见 §4.2 |
| `size_missing_note` | `"宽高未取得：{reason}"` | 尺寸取不到时写进 `notes` 的模板 | 见 §4.1 |
| `legacy_placeholder_note` | `"旧占位许可值「{value}」已作废（v3.16.0），须人工重新登记"` | 旧占位值作废时写进 `notes` | 见 §4.2 |

### 10.2 `license_gate` 段（许可门禁输出文案）

| 键 | 值 | 出现时机 |
|---|---|---|
| `count_line` | `未登记许可的素材数 = {n}` | 每次提取必打（默认流程也打） |
| `prefix` | `未登记许可` | 门禁输出前缀（grep 用） |
| `summary_line` | `未登记许可：{n} 条素材（--require-license 已启用，须补登记后重跑）` | `--require-license` 命中 |
| `ids_line` | `未登记许可明细：{ids}` | 同上（`{ids}` = 逗号分隔 asset_id） |
| `reuse_violation_line` | `许可纪律：{asset_id} license_note 为空但 reuse_status={status}（应为「{expected}」）` | 写盘前许可纪律断言命中 |

> 注：`license_gate` 与 `asset_fields` 同属"配图链路许可登记"配置，故同文件登记；
> 若将来门禁独立成段，可整体迁出，脚本只需改 `_load_asset_field_config()` 的取值键。

---

## 11. v3.16.0 变更说明（F8）

| 项 | 改前 | 改后 | 理由 |
|---|---|---|---|
| `license_note` 默认值 | `"原课件自带"` | `""` | 原默认值等于"默认可用"的错误暗示，与 adjudication-rules 原则六冲突（诊断 M3） |
| `reuse_status` 默认值 | `"未决"` | `"待核查"` | 与"未登记许可"语义统一；空许可必须是「待核查」 |
| manifest 统计 | 无许可计数 | `unlicensed_assets` / `unlicensed_asset_ids` / `license_gate` | 许可核查工作量可机器核对 |
| 记录字段 | 无 | `width` / `height` / `source_url` / `doi_pmcid` | 配图链路"几乎无记录"：尺寸、来源、文献三项补齐 |
| 门禁 | 无 | `--require-license`（默认关闭） | 需要时能卡住带病交付，平时不阻断 |
| 旧 manifest | 无容错 | `from_dict` / `load_manifest_records` 容错读取 | 存量 manifest 不必重跑 |

**未做（不粉饰）**：`source_url` / `doi_pmcid` 目前**只留空串位**，脚本不自动回填来源
（回填要联网检索与人工判定，属配图链路后续批次）；`width` / `height` 取的是显示尺寸 EMU→px，
**不是位图固有分辨率**。

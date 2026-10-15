# template_migrate.py 使用手册（三档模板迁移）

> v3.2.0-batch3。配套：`theme_fingerprint.py`（指纹/盘点）、`template_registry_usage.md`（登记册）、
> `theme_migrate_ooxml_notes.md`（OOXML 原理）。CLI 出错码沿用 verify_deck 约定：0=成功，1=门禁拦截，2=参数错。

## 1. 五个子命令总览

```bash
PY=<python 解释器>
$PY template_migrate.py <子命令> …
```

| 子命令 | 作用 | 写文件？ |
|---|---|---|
| `fingerprint <deck>` | 单件指纹 + 结构摘要 | 否 |
| `audit <deck> --tier T1\|T2\|T3` | dry-run 三态评估（逐页风险码） | 否 |
| `dryrun` | = audit 的批量别名 | 否 |
| `migrate <deck> --tier T --template <tpl> --confirm` | 正式迁移 | **是** |
| `register <tpl> --name --use-case --domain` | 登记模板基因 | 是（registry + gene） |

## 2. dry-run 报告解读

```bash
$PY template_migrate.py audit 打样课件.pptx --tier T2 --json out.json
```

- **三态**：`可无损迁移` / `需重建` / `有风险`，逐页标注。
- **6 类风险码**：

| 码 | 含义 | 典型处置 |
|---|---|---|
| R-SHARED-CHART | 页内图表被共享引用 | 该页走 T3 手工重建 |
| R-SVG-EMF | SVG/EMF 矢量图，重灌后渲染差异 | 迁移后逐页目检 |
| R-FONT-MISS | 源字体目标环境缺 | 先装字体或接受替换 |
| R-OVERFLOW | 文本 >400 字，重灌后可能溢出 | 迁移后跑布局复核 |
| R-LAYOUT-MISS | 源 layout 名不在目标模板 | 换模板或改用 T3 |
| R-MASTER-DRIFT | 源 layouts 数 > 目标×2 | 母版差异过大，放弃 T2 |

- **exit 1 触发**：高风险页 >50% 或迁移后 lint 有 ERROR。此时降档或放弃，不硬迁。

## 3. 三档迁移怎么选

| 档位 | 动什么 | 什么时候用 | 实测耗时（99 页） |
|---|---|---|---|
| T1 主题级 | 只换 clrScheme+fontScheme | 只想统一配色/字体 | ~3 min |
| T2 母版级 | T1 + master/layouts/theme 注入注册 | 要模板版式但保页面结构 | ~13 min |
| T3 重灌级 | 空稿 + 逐页深拷贝重建 | 版式全对齐、彻底统一 | ~88 min |

选档原则：**能 T1 不 T2，能 T2 不 T3**。T3 的 88 分钟是真实成本（含逐页风险处理）。

## 4. 正式迁移标准命令

```bash
# T1：源稿 + 目标模板，输出到 -migrated 后缀文件（不覆盖原件）
$PY template_migrate.py migrate 源稿.pptx --tier T1 --template 基准模板.pptx --confirm

# 成功后自动跑 ooxml_lint：ERROR≠0 则整体判失败（exit 1）
# 建议流程收尾三件事：lint 结果 → md5 落盘 → verify_deck 抽检
```

- `--confirm` 缺省时不写文件（只打印将执行的动作），防止误操作。
- **永不覆盖 L0 原始件**：输出固定为新文件；覆盖交付件前先走 CLAUDE.md §6 备份链。

## 5. 批量盘点（指纹普查）

```bash
# 目录递归，出统一性报告（deck 数 / unique 指纹数 / majority 占比）
$PY theme_fingerprint.py <课件根目录> --recursive --json 盘点.json
```

- 实测基线（2026-10-14，139 件）：**37 个唯一指纹，majority a97ffad5 仅 33 件 23.7%**——
  模板碎片化远超预期，这正是登记册+统一迁移立项的依据。
- 盘点产物入 `outputs/harness-ab/` 留档，作为后续迁移的 before 证据。

## 6. 与 harness 的关系

`harness.py template-audit <课件根目录>` 是本工具的薄封装（盘点+登记册审计一步跑），
日常巡检用它；本脚本的完整 CLI 留给打样与特殊迁移。

## 7. 边界与已知限制

- 图表页 T2 迁移 = 只保形状外壳，图表数据可能失效 → 一律标 R-SHARED-CHART 建议手工
- 数学公式（OMML）、SmartArt、3D 模型未专项测试，出现即走 T3 + 人工目检
- 跨学科模板（微生物/宠物）迁移属 Batch 5 范围，当前 domain 字段先占位
- 密码保护/只读推荐的课件直接拒绝处理（python-pptx 无法打开）

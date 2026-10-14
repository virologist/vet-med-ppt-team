# 模板基因登记册使用手册（template_registry.json）

> v3.2.0-batch3 起生效。登记册 = 换模板前的唯一查询入口。
> 底层算法见 `theme_migrate_ooxml_notes.md` §2；命令细节见 `template_migrate_usage.md`。

## 1. 文件布局

```
<课程工作区>/.workbuddy/templates/
├── template_registry.json          ← 登记册主文件（可手工读，脚本维护）
├── majority-v1-a97ffad5.gene.json  ← 基因快照（每模板一份，register 自动生成）
└── template_frozen_v1.json         ← 历史冻结件（v3.0 遗留，只读保留）
```

## 2. 登记册条目 schema

```json
{
  "name": "majority-v1-a97ffad5",       // 人类可读名（默认 majority-v1-<指纹前8位>）
  "path": "/绝对路径/传染性法氏囊.pptx",  // 基准源文件绝对路径
  "theme_fingerprint": "a97ffad5",      // sha256(clrScheme+fontScheme c14n)[:8]
  "use_case": "教学 PPT 全量交付统一基线", // 适用场景
  "domain": "animal-medicine/家禽",      // 学科域
  "fonts": ["Calibri"],                 // 字体清单（gene 快照摘要）
  "colors": ["5B9BD5"],                 // 主色（gene 快照摘要）
  "registered_at": "2026-10-14T…"
}
```

基因快照 `*.gene.json` 额外含 layouts 完整清单（11 项）+ 逐项计数，供 T2 dry-run 的
R-LAYOUT-MISS 判定离线使用。

## 3. 标准工作流（换模板三步）

```bash
PY=<python 解释器>
SCRIPTS=<专家包>/scripts

# ① 指纹目标模板
$PY $SCRIPTS/theme_fingerprint.py 新模板.pptx

# ② 未登记则登记（register 同时写 registry.json 和 gene.json）
$PY $SCRIPTS/template_migrate.py register 新模板.pptx \
    --name 蓝色简明-v1 --use-case "XX 模块新基线" --domain animal-medicine/家禽

# ③ 查册：指纹命中 = 可直接复用；未命中 = 走 ② 再用
$PY $SCRIPTS/template_migrate.py registry-audit 新模板.pptx
```

**铁律（用户裁决 2）**：换模板前先查此册，复用先登记。登记是零成本动作（几秒），
漏登记的代价是指纹漂移无人知晓、批量迁移后基线不可追溯。

## 4. 已登记模板（现行）

| 名称 | 指纹 | 来源 | 场景 |
|---|---|---|---|
| majority-v1-a97ffad5 | a97ffad5 | M4B1_传染性法氏囊/传染性法氏囊.pptx | 全量交付统一基线（139 件盘点中 33 件 23.7% 多数派） |

## 5. 维护纪律

- registry.json 由 `register` 子命令维护，**不手工编辑**（手工改会导致 gene 快照与主文件失配）
- 模板文件本体不复制进登记册目录，只记绝对路径——源文件移动后需重新 register 更新 path
- 学科域命名：`animal-medicine/<细分>` / `microbiology/<细分>`，跨学科打样（Batch 5）时新增
- 登记册随课程工作区走（`.workbuddy/templates/`），不进 git；专家包仓库只沉淀脚本与文档

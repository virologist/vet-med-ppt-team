# 病例库使用手册（cases_library）

> v3.2.0-batch4。配套：`case_extract.py`（CLI）+ `case_extract_sop.md`（三源核验协议）。
> 数据位置：`<课程工作区>/.workbuddy/cases/cases_library.json`。

## 1. 快速使用

```bash
PY=/Users/biodog/.workbuddy/binaries/python/versions/3.13.12/bin/python3
SCRIPTS=<专家包>/scripts
WS=<课程工作区>

# ① 入库（首次）
$PY $SCRIPTS/case_extract.py scan --root "$WS" --workspace "$WS"

# ② 查"新城疫的所有案例"
$PY $SCRIPTS/case_extract.py find --workspace "$WS" --disease M4A2

# ③ 查"含'腺胃乳头出血'的案例"
$PY $SCRIPTS/case_extract.py find --workspace "$WS" --keyword "腺胃乳头出血"

# ④ 审计（看哪些待三源核验）
$PY $SCRIPTS/case_extract.py audit --workspace "$WS"
```

## 2. 字段含义

| 字段 | 含义 | 示例 |
|---|---|---|
| `case_id` | 全局唯一 ID | `C-M4A2-004` |
| `disease_module` | 病种代码 | `M4A2` |
| `disease_name` | 病种中文 | `新城疫` |
| `case_no` | 1-5（v2 升级规格位置） | `4` |
| `title` | 案例标题（≤40字） | `新城疫典型案例（中等）` |
| `scenario` | 关键场景（≤200字，已脱敏） | `180 日龄，产蛋率…腺胃乳头出血` |
| `severity` | 普通/中等/最高 | `中等` |
| `sources` | 三源核验列表 | `[{kind, ref, ok}]` |
| `deck_path` | 来源课件绝对路径 | `/Users/.../新城疫.pptx` |
| `slide_idx` | 来源页码 | `64` |
| `registered_at` | 入册时间（ISO 8601） | `2026-10-14T15:23:09+08:00` |
| `unverified` | 是否待三源核验 | `true`（默认） |

## 3. 与其他资产的关系

```
        ┌──────────────┐
        │ 课件（49 件） │ ←─── source of truth
        └──────┬───────┘
               │ case_extract scan
               ▼
        ┌──────────────┐
        │ cases_library │  ←─── 集中台账（51 条实测）
        └──────┬───────┘
               │ case_extract find/audit
       ┌───────┴───────┐
       ▼               ▼
  dvm-content       verifier
  (三源核验)        (10% 抽检)
```

## 4. 出错码

| 退出码 | 含义 | 处置 |
|---|---|---|
| 0 | OK / 全部 verified | 继续 |
| 1 | 有需处置项（缺三源/有重复） | 走 verifier 抽检 |
| 2 | 用法错误（参数/根不存在） | 看 usage |
| 3 | 依赖缺失（python-pptx 未装） | 装依赖 |

## 5. 与 harness.py 的关系（v3.2.0-batch5 拟扩展）

`harness.py case-audit <课程工作区>` 拟作为本工具的薄封装（盘点+查登记册一步跑），
日常巡检用它；本脚本的完整 CLI 留给登记与特殊录入。

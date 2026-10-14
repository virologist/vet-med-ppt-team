# 病例库提取与三源核验 SOP（v3.2.0-batch4）

> 配套工具：`scripts/case_extract.py`（扫描+抽取+脱敏+登记+审计+查询）。
> 数据落点：`<课程工作区>/.workbuddy/cases/cases_library.json`（**不进 git**，CLAUDE.md §3 同步登记）。
> 关系：v2 升级规格"每件 +6~7 页含 5 案例" → 245 案例理论数；实测抽取 51 条（已覆盖 19 病种），剩余 194 条需 v2 补充流程继续抽取。

## 1. 为什么需要本 SOP

v2 升级规格（CLAUDE.md §4）规定每件课件加 5 个案例（普通 3 + 复杂 4 + 复杂 5），但 245 个案例**散落在 PPT 内部页里**，无集中台账。后果：
- 案例复用全靠人脑记忆，跨课件迁移无依据
- 新案例无机器化去重 → 重复造轮子
- 三源核验（PubMed/教辅/法规）无法机器化
- 病种映射（31 模块）无统一代码 → 跨域引用失败

本 SOP 把"自然语言段落"变成"有 ID / 病种映射 / 三源核验 / 课件双向引用"的结构化资产。

## 2. 案例 ID 规范

**格式**：`C-<病种模块>-<3 位序号>`

- 病种模块：从课件父目录提取（`M4A1_禽流感` → `M4A1`），由 `DISEASE_MAP` 查中文名
- 序号：1-5（v2 升级规格固定 5 个案例位），3 位补零
- 案例：3-普通 / 4-中等 / 5-最高（严重度自动映射）

**示例**：
- `C-M4A1-001` = M4A1 禽流感第 1 个案例（普通）
- `C-M6A1-005` = M6A1 球虫第 5 个案例（最高复杂）

## 3. 提取流程（5 步）

### 3.1 干跑（不入库）

```bash
PY=/Users/biodog/.workbuddy/binaries/python/versions/3.13.12/bin/python3
SCRIPTS=<专家包>/scripts
WS=<课程工作区>

$PY $SCRIPTS/case_extract.py scan --root "$WS" --dry --limit 200
```

输出：`scanned_decks / draft_count / by_disease / first_5`。**干跑不写任何文件**。

### 3.2 落盘入册

```bash
$PY $SCRIPTS/case_extract.py scan --root "$WS" --workspace "$WS" --limit 200
```

输出：`saved_to / drafts_total / newly_registered / library_total / audit`。

- `newly_registered < drafts_total` 表示有重复（按 case_id 去重）
- `audit.verdict=ok` 全部 unverified=false；`needs_verification` 有待三源

### 3.3 审计

```bash
$PY $SCRIPTS/case_extract.py audit --workspace "$WS" --json audit_report.json
```

输出：`total / by_disease / unverified_count / verdict`。**unverified_count 是 verifier 抽检的入口**。

### 3.4 查询

```bash
# 按 ID 查单条
$PY $SCRIPTS/case_extract.py find --workspace "$WS" --case-id C-M4A1-004

# 按病种批量查
$PY $SCRIPTS/case_extract.py find --workspace "$WS" --disease M4A1

# 按关键词查
$PY $SCRIPTS/case_extract.py find --workspace "$WS" --keyword "腺胃乳头出血"
```

### 3.5 手动登记（特殊案例）

```bash
$PY $SCRIPTS/case_extract.py register --case-id C-M4A1-006 \
    --title "罕见 H5N6 病例" --scenario "..." --severity 最高 --workspace "$WS"
```

## 4. 脱敏规则（Q2：人名+单位+地址，**不可关**）

脱敏在 `case_extract.desensitize()` 内置，**不在 CLI 暴露开关**。规则（顺序敏感，后写覆盖前写）：

| 类别 | 模式 | 替换为 |
|---|---|---|
| 人名 | `[\u4e00-\u9fa5]+?(?:老师\|医生\|场长\|技术员\|老板\|经理)` | `XX` |
| 单位 | `[\u4e00-\u9fa5]+?(?:养殖场\|养禽场\|鸡场\|鸭场\|种禽场\|公司\|大学动物医院)` | `XX养殖场` |
| 地址 | `X省Y市Z区` 或 `Y市Z区` 或 `X区` | `X省X市` |

**铁律（CLAUDE.md §7-A 物种语境保护）**：
- 🚫 禁止在课件/案例中暴露真实患者姓名/单位/地址
- 🚫 禁止关闭脱敏（无 CLI 开关）
- 跨学科样本（微生物/宠物）也走同套脱敏

## 5. 三源核验协议（Q4：失败不阻断，标 unverified=true）

按 CLAUDE.md §9 ReAct 核验原则：P0 数字/毒株/药物剂量/国标更新 → 多源核验。

### 5.1 三源类型

| kind | 来源 | 适用 |
|---|---|---|
| `pubmed` | PubMed 检索（PMID） | 病原学/药理/毒株 |
| `textbook` | 教辅/规划教材（ISBN） | 临床案例/剖检变化 |
| `regulation` | 国标/农业农村部公告（GB/公告号） | 防控/疫苗/检疫 |

### 5.2 核验流程

1. 提取自动登记 → `unverified=true`（默认）
2. 严真奥（dvm-content-expert）按 case_id 抽查 10% → ReAct 核验
3. 核验通过 → 改 `unverified=false` + 填 `sources=[{kind, ref, ok=true}]`
4. 核验失败 → 留 `unverified=true` + 标 `sources=[{kind, ref, ok=false, reason=…}]`
5. 期末 verifier 抽页 20% 二次复算（CLAUDE.md §4 v2 规格）

### 5.3 sources 字段 schema

```json
"sources": [
  {"kind": "pubmed", "ref": "PMID:12345678", "ok": true},
  {"kind": "textbook", "ref": "ISBN:978-7-109-XXXXX", "ok": true},
  {"kind": "regulation", "ref": "GB 19438-2004", "ok": false, "reason": "已废止，新版 GB 19438-2024"}
]
```

## 6. 与 Batch 1-3 的衔接

| Batch 1-3 资产 | 病例库怎么用 |
|---|---|
| `extract_assets.py`（课件→md） | 病例抽取的"上游"——`extract_assets` 输出 md 后，case_extract 用 python-pptx 重新打开（保留 slide_idx） |
| `snapshot.py` | **首次入册时自动打 `case_<id>_initial` 快照**（Q4 防止登记错乱后无法回滚）——v3.3.0 实现 |
| `ooxml_lint.py` | 案例页含图表时复用 R-SHARED-CHART 判定 |
| `template_registry.json` | 案例页若走 T3 模板迁移，复用 Batch 3 登记册闸门 |
| `deck_registry.json` | 病例库登记时登记 `case_id → deck_path + slide_idx` 双向引用 |
| `harness.py` | **本批新增** `case-audit` 子命令（盘点+查登记册一步跑，verdict=needs_verification 触发 verifier） |

## 7. 维护纪律

- 登记册**不手工编辑**（`register` 子命令维护，避免与基因快照失配）
- 案例 ID **不重用**（即使删除也不重号——防历史引用断裂）
- 病种模块**不新增**（v3.3.0 才允许扩 domain，跨学科打样时新增）
- 三源核验不阻断入库（Q4），但 `unverified_count` 长期不下降 → 触发治理整顿

## 8. 已知限制

- v1 阶段课件无结构化"案例 N"页，**只能抽到 v2 升级后**的 51 条；剩余 194 条需 v2 补充流程继续抽取
- 抽不到 ≠ 不存在——可能因页模板差异（v1 案例用"案例"作为段落而非标题）
- 跨学科样本（微生物/宠物）暂未入库（domain 未扩展）
- 图表/示意图无 OCR（v3.3.0 拟接入 easy-ocr）

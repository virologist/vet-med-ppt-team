# 外部课件样本登记册（sample-registry.md）

> v3.25.0 新建。**这是什么**：本包有若干条用例需要**包外的真实课件**才能真跑
> （`scripts/test_ooxml_lint.py::T11` 跨学科样本、`scripts/test_extract_assets.py::T6` 等）。
> 这些样本**不随包分发**（体积 + 版权），因此需要一份**可复现的获取方式**登记册，
> 让任何人在任何机器上都能用同一份样本把用例跑成 `real` 分支而不是 `synthetic` 兜底。
>
> **本文件只登记事实**（来源 / 校验和 / 放置路径 / 用法 / 局限）；
> **代码只管定位**（`scripts/sample_fixtures.py` 的 `resolve_cross_domain_sample()`）。
> 两者分开：代码里不堆下载 URL 与 sha256，文档里不写选取逻辑。

---

## 1. 跨学科样本（cross-domain sample）

### 1.1 登记条目

| 字段 | 值 |
|---|---|
| 用途 | `scripts/test_ooxml_lint.py::T11`——验证「非本团队产出的课件」也能走同一套规则集 |
| 标题 | 《SEDRIC: System for Enteric Disease Response, Investigation, and Coordination》 |
| 来源站点 | CDC Stacks（美国 CDC 公共文献库），条目号 `cdc/118221` |
| 发布方 | National Center for Emerging and Zoonotic Infectious Diseases（NCEZID） |
| 版权标注 | **Public Domain**（美国联邦政府作品，可自由使用） |
| 文档属性 | Document Type: Presentation · 26 页 · 发布日期 2020-01-22 |
| 下载 URL | `https://stacks.cdc.gov/view/cdc/118221/cdc_118221_DS_MS_NON_EXCEL.pptx` |
| sha256 | `ed217fc68e2fc818bf0f1355bcd102e5029bc601ff9bc71f1bdf716f387d0fd9` |
| 文件大小 | 4,559,117 B |
| 文件类型 | `Microsoft PowerPoint 2007+`（OOXML） |
| lint 实测 | `scripts/ooxml_lint.py` → **0 ERROR / 35 WARN / rc=0**（WARN 均为该课件固有：GEO-003 形状叠放 30 处、XML-003 缺 `xml:space="preserve"` 5 处） |

### 1.2 放置路径与用法

样本**不随包分发**。自行下载后放进**任意一个持久目录**，再用环境变量告诉本包：

```bash
# ① 下载（注意：不要落到 /tmp——/tmp 不持久，这正是 v3.24.0 前
#    「T11 从未在本机真跑过」的根因）
mkdir -p "$SAMPLES/cross_domain"
curl -sS -L --max-time 120 -o "$SAMPLES/cross_domain/cdc_zoonotic_diseases.pptx" \
    "https://stacks.cdc.gov/view/cdc/118221/cdc_118221_DS_MS_NON_EXCEL.pptx"

# ② 校验（sha256 必须与上表一致，否则说明拿到的是别的文件）
shasum -a 256 "$SAMPLES/cross_domain/cdc_zoonotic_diseases.pptx"
#   期望：ed217fc68e2fc818bf0f1355bcd102e5029bc601ff9bc71f1bdf716f387d0fd9

# ③ 指向本包
export VETMED_CROSS_DOMAIN_DIR="$SAMPLES/cross_domain"

# ④ 跑用例（应看到「跨学科样本来源：real」而不是 synthetic 兜底）
python3 -m pytest scripts/test_ooxml_lint.py -q -k T11 -s
```

**本包已落盘的位置**（v3.25.0 实测取证所用）：

```
<工作区>/01-research/samples/cross_domain/cdc_zoonotic_diseases.pptx
```

### 1.3 选取规则（`scripts/sample_fixtures.py`）

`resolve_cross_domain_sample()` 按**两段式**定位，`VETMED_CROSS_DOMAIN_DIR` 未设置时
回落到 `/tmp/cross_domain`：

1. **固定文件名优先**——目录里恰有 `cdc_zoonotic_diseases.pptx` 时选它（向后兼容，
   保证既有已落位样本的选取结果不变）；
2. 否则取目录内**任意** `*.pptx`，按**文件名升序**取第一个（确定性：同一目录内容
   ⇒ 同一结果；跳过 Office 锁文件 `~$*` 与隐藏文件）。

⇒ v3.25.0 起，**不同来源的跨学科样本不必改名**即可落位（v3.24.0 必须改名成固定文件名）。

### 1.4 为什么选它作为「跨学科样本」

T11 要验证的是「**规则集对非本团队产物同样成立**」，因此样本须满足三条件：

| 条件 | 本样本是否满足 |
|---|---|
| **非本团队产物**（不是我们做出来的课件） | ✅ CDC/NCEZID 官方课件 |
| **非中文**（排除"我们自己那套排版"的干扰） | ✅ 英文课件 |
| **非动医主题**（验证跨学科适用性，而非重复验动医样本） | ✅ 主题为肠道疾病监测系统（SEDRIC） |
| **公共领域 / 可自由使用** | ✅ CDC Stacks 标注 Public Domain |
| **格式合法**（lint 0 ERROR，能真正触发规则集） | ✅ 实测 0 ERROR / 35 WARN / rc=0 |

### 1.5 ⚠ 诚实说明（必须一并读）

1. **文件名与内容不完全对应**：落盘时用了 `cdc_zoonotic_diseases.pptx` 这个名字，
   是因为 v3.24.0 的定位层按**固定文件名**查找；**内容实为 SEDRIC 课件，
   并不是标题为 "zoonotic diseases" 的课件**。
   v3.25.0 已改为「目录内任意 `*.pptx`」，**该文件名今后不再是必需的**——
   下载后**不必改名**，直接用真实文件名（如 `cdc_118221_DS_MS_NON_EXCEL.pptx`）即可落位。
2. **未找到标题完全对应的 CDC "zoonotic diseases" pptx**：如实报告——
   - `stacks.cdc.gov/view/cdc/130144`《What Providers Need to Know About Zoonotic Influenza》
     的**主文档是 PDF**（`cdc_130144_DS1.pdf`），附件只有 `062023_video.mp4`，**无 pptx**；
   - CDC Stacks 站内检索端点 `/gsearch?terms=…` 实测 **404**（站点搜索为动态渲染，脚本化不可靠）；
   - `restoredcdc.org` 的 Marburg（NCEZID）培训页实测 **45s 超时**，未取到 pptx 直链。
   ⇒ 即：**站内没有标题含 zoonotic 的可直接下载 pptx**；本册登记的是**同属 NCEZID 的
   公共领域 pptx**，已给出可复现 URL + sha256，**不以无关文件冒充**。
3. **本册登记的是「可复现的获取方式」，不是「包内自带样本」**：
   样本文件本体不在本包内（体积 + 版权），未放置时相关用例会**显式降级**为
   合成 fixture 并打印降级类型（`real` / `synthetic`）——**不静默**。

---

## 2. 其它外部样本（占位）

<!-- DOMAIN_EXAMPLE_BEGIN -->
| 样本 | 用途 | 状态 |
|---|---|---|
| 动医真实课件 4 份（`M4A1_禽流感/` 等用户工作区目录） | `test_ooxml_lint.py::T1`、`test_extract_assets.py::T6` | 由 `scripts/sample_fixtures.py::resolve_real_samples()` 多候选目录自动发现；不可得时降级为合成 fixture（降级类型显式打印） |

> 上表中的「动医真实课件」「M4A1_禽流感」等为**正当举例**（外部样本的现实出处说明）；
> 物种/病种词条本身已下沉到 `config/domain-profiles.yaml`（animal-medicine 域），
> 本文件**不复制**域档案词条。
<!-- DOMAIN_EXAMPLE_END -->

> **登记纪律**：新增外部样本条目时，**必须**同时写明 URL、sha256、放置路径、
> 校验命令与「为什么选它」；**只贴链接不写校验和**的条目视为未登记。

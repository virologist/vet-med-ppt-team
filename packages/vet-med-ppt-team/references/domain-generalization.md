# 通用化转型指南（v3.28.3 · B17）

> **本文件不得成为第二规则源**——域档案字段的唯一源是 `config/domain-profiles.yaml`，
> 五件套判据的唯一源是 `config/domain-pack-contract.yaml`，
> 执行器是 `scripts/harness.py domain-pack-check`。
> 本文件只讲**为什么**与**怎么用**，规则本体不复述。

## 一、为什么要做这件事

本团的真实目标是「**可复用于任意教学/培训主题**的通用 PPT 诊断与优化工作流」。
但在本批之前，「通用」只做到了**提示词层**：

- 包内三个域（animal-medicine / computing / business-training）确实各有独立档案；
- 但 `animal-medicine` **独占 4 个关键段**：`depth_scale_source`（深度标尺）、
  `audience_profile`（受众画像）、`course_module_templates`（课程模块模板）、
  `knowledge_bases_scope`（知识库范围）；
- 另两个域**一个都没有**。

⇒ 换到 computing 域时，专家团拿到的是「**换了人格、没换资产**」的班子：
深度没标尺（同一主题在不同域产出同样深度）、受众没画像（教学设计退化为通用方法论）、
模块没模板（页表结构靠临场发挥）、知识库范围没声明（检索范围靠 default）。

**且这些缺口此前无任何机器可查的地方**——
体检第 23 项（域绑定残留巡检）管的是「**不该有的词**」（域专有词漏进通用文档），
管不了「**该有的资产缺没缺**」。

## 二、通用化的两个方向

| 方向 | 治什么 | 谁判 | 判据源 |
|---|---|---|---|
<!-- DOMAIN_EXAMPLE_BEGIN -->
| **反向**（既有）：域专有词残留 | 某域专有词漏进 `agents/` `references/` 等通用文档 | 体检第 23 项 | `config/hygiene-words.yaml#domain_specific_terms` |
<!-- DOMAIN_EXAMPLE_END -->
| **正向**（本批新增）：域包齐备度 | 某域该有的资产缺了（深度标尺 / 受众画像 / …） | `harness.py domain-pack-check` | `config/domain-pack-contract.yaml` |

**两个方向都必须可查**——只查反向 ⇒ 缺资产查不出来（本批之前的状态）；
只查正向 ⇒ 域串味查不出来。

## 三、五件套是什么

一个域包要算「接好了」，必须齐备五类资产（详见契约的 `assets` 段）：

| # | 资产面 | 治什么病 | 级别 |
|---|---|---|---|
| 1 | **词条与术语规范** | 该域专名/缩写/口径不统一 | required |
| 2 | **知识库接入面** | 从哪取料；**没有时怎么办**（不许静默回落别的域） | required |
| 3 | **深度标尺** | 该域内容深到哪一档（决定跨域产出的差异化） | required |
| 4 | **受众画像** | 面向谁、各层要什么、案例形态与互动形态 | required |
| 5 | **课程模块模板** | 页表骨架从哪来 | recommended |

**级别语义**：
- `required` 缺任一 ⇒ **rc=1 阻断**（域没接好就不该出课件）；
- `recommended` 缺 ⇒ 提示不阻断（非教学域可豁免）；
- 形态差异导致的缺失 ⇒ **必须**在 `config/domain-profiles.yaml#domain_pack_exemptions`
  显式登记豁免（三要素齐备：域 / 资产 / 理由），**不得静默缺失**。

## 四、怎么接一个新域

```bash
# ① 照 references/domain-profile-template.md 产出域档案
#    （追加进 config/domain-profiles.yaml#domains）

# ② 验齐备度（机器判定）
python3 scripts/harness.py domain-pack-check --workspace <课程工作区>
#    rc=0 → 齐备；rc=1 → 有 required 缺口（看 missing_required）；rc=3 → 跨域串味

# ③ 形态差异登记豁免（在 domain-profiles.yaml 顶层 domain_pack_exemptions）
#    结构是**映射**（域 → 资产 → {reason}），不是列表——
#    列表形态在体检第 18 项只构成「末段键名撞车」的弱证据（假绿）。

# ④ 用域
python3 scripts/harness.py route --level L2 --domain <新id> --panel <id1,id2>
```

## 五、跨域串味哨兵

契约的 `cross_domain_guard` 段声明：**某域不得引用别域的专有资产标识**。
命中 ⇒ **rc=3 阻断**。这是「换了域还留着旧域的引用」的守卫。

⚠ **已知局限（如实标注）**：该哨兵是**枚举式**（词表在契约里逐条列）——
未列入词表的跨域引用**检不出来**。它挡的是「已知的典型串味」，不是全覆盖。
覆盖率提升需要扩词表（改契约，不改代码）。

## 六、试金石：computing 域

升级方案要求「以 computing 域为试金石验证即插即用」——
即：一个**与默认域无关**的域必须能齐备五件套并通过 machine-check。
这不是形式检查——若五件套只是把默认域的资产换个名字搬过来，
computing 域的 `depth_scale_source` / `audience_profile` 就会在内容上露馅
（它们写的是语言规范/复杂度分析/在岗工程师，**不是**默认域的脱敏改名）。

机器判据：契约的 `probe_domain` 段声明试金石域，检查会把它单列出来
（`probe_domain.complete`）——**试金石域不 complete ⇒ 通用化不成立**。

## 七、跨任务看齐备度演进

检查会把报告落 `<课程工作区>/.workbuddy/domain_pack_report.json`，
并写 trace 事件 `domain_pack_check` ⇒ 可与 B16 的 `harness.py trend`
放在同一时间轴上看（域包齐备度 ↔ 产出质量）是否同向。

## 八、纪律

- 域档案字段的唯一源是 `config/domain-profiles.yaml`——**别在别处复制一份**。
- 五件套判据的唯一源是 `config/domain-pack-contract.yaml`——**代码只执行，不硬编码**。
- 豁免不是万能钥匙：单域豁免数有上限（契约 `max_exemptions_per_domain`），
  且豁免必须写理由——**「没写理由的豁免」等于没豁免**。
- 缺键即 fail-closed：契约缺键 ⇒ 拒绝出结论，**不补内置值**。

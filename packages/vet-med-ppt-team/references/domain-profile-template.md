# 域档案生成模板（v3.21.0 · 跨专业复用 · 多专家单载体）

> **为什么有这份模板**：本团的真实目标是「**可复用于任意教学/培训主题**的通用 PPT 诊断与优化工作流」。
> 但 `config/domain-profiles.yaml#domains` 只内置了 3 个域（animal-medicine / computing / business-training），
<!-- DOMAIN_EXAMPLE_BEGIN -->
> `references/standards/` 只有 1 个专业标准摘要（动物医学）。
<!-- DOMAIN_EXAMPLE_END -->
> （哨兵块内是**现状举例**——第 23 项巡检豁免口径；本文件本身是**域无关模板**。）
> ⇒ 遇到**未内置的新主题**时，坍缩会退化成通用兜底人格（`domain_context=fallback_profile_missing`），
> **知识覆盖深度无从谈起**——用户要"匹配的资深团队"，退化成兜底就不是。
>
> **用法**：主理人接到新主题 → 照本模板产出一个域档案 → 追加进 `config/domain-profiles.yaml#domains`
> → `harness.py route --level <L> --domain <新id> --panel <id1,id2>` 即可生成匹配的专家面板。
> **目标：一个新主题 10 分钟内产出可用域档案。**
>
> ⚠ **字段纪律**（`config/domain-profiles.yaml` 是唯一源，本模板**不新增字段**）：
> 下面每个字段名都**真实存在于** `config/domain-profiles.yaml#domains[].<字段>`；
> 照抄字段名，**不要自造**——自造字段会被装配器忽略（不报错、也不生效），
> 那正是本包反复治理的「声明层≠执行层」病灶。
> 装配器的消费面见 `scripts/assemble_domain_prompt.py`（域上下文八段）。

---

## 一、填写流程（5 步，每步都有产出物）

| 步 | 动作 | 产出 | 判据 |
|---|---|---|---|
| 1 | **定域**：给新主题起 id（kebab-case）+ 中文名 | id / display_name | id 出现在 `route --domain <id>` 的候选里 |
| 2 | **定轴**：写 `content_axes`（3-5 条知识覆盖方向） | content_axes | 专家面板的 coverage_axes 必须能对上这些轴 |
| 3 | **定人**：写 `expert_panel`（2-4 位子专家） | expert_panel | **每个轴至少有一位专家覆盖**（否则有知识无人守） |
| 4 | **定依据**：写 `evidence_hierarchy` + `safety_redlines` | 证据层级与红线 | 层级里的机构源**要能联网核实现行版本** |
| 5 | **自检**：跑 `harness.py route --domain <新id> --panel ...` | 坍缩产物 | `collapse show` 输出里专家面板与轴对得上 |

---

## 二、字段清单（照抄即可，每项标了"填什么/不填会怎样"）

### 1. 基本标识
```yaml
- id: <域id>                    # kebab-case；route --domain 用它
  display_name: <中文名>
  match_hints: [<关键词1>, <关键词2>]   # 供主理人按主题选域时参考（语义匹配由人做）
```
- **不填 `id`** → 该域**根本选不中**（route 报域不存在）。

### 2. `role_persona`（域人格——坍缩产物里的"这个人是谁"）
```yaml
  role_persona:
    title: <该域内容权威的称号>       # 如"医学影像内容权威"
    background: <背景一句话>          # 如"医学影像诊断与超声/放射学双背景"
    stance: <立场一句话>              # 什么情况下他会拒绝写（反幻觉的锚）
    duties: [<职责1>, <职责2>]        # 他负责供给什么
    duty_boundary: <他明确不做什么>   # 边界写清，避免越界抢活
```
- **不填** → 装配时走通用兜底（`fallback_profile_missing`），域人格**不生效**。
- ⚠ `duty_boundary` 与 `expert_panel[].duty_boundary` **要呼应**：域级说"不做教学设计"，
  成员级说"不核验我的领域"——两级不冲突。

### 3. `expert_panel`（子专家面板——**"多专家"的载体**）
```yaml
  expert_panel:
    - id: <专家id>                   # kebab-case；route --panel 用它
      title: <称号>                   # 如"超声诊断专家"
      background: <背景>
      stance: <立场/证据纪律>
      duties: [<职责1>, <职责2>]
      duty_boundary: <职责边界>
      coverage_axes: [<轴1>, <轴2>]  # **必须对上 content_axes**
      activation_hints: [<触发词1>, <触发词2>]   # 供主理人按主题选人
```
- ⚠ **怎么确定该域需要哪几位子专家**（这是"知识覆盖深度"的落地方法）：
  1. 先写 `content_axes`（本域要讲的知识方向，3-5 条）；
  2. 每条轴问自己："这一轴上，**谁有资格**下结论？"（不是"谁讲得好"，是"谁的结论可溯源"）；
  3. 一个轴若无人可答 ⇒ 说明该域**需要新专家**或**该轴不进本单**（别硬凑）；
  4. 每位专家的 `coverage_axes` 与 `content_axes` 求交集不得为空；
  5. 专家数 **2-4 位**：1 位 = 没多专家；5 位以上 = 装配产物过长、成员上下文被稀释。
- ⚠ **`coverage_axes` 留空或对不上** ⇒ 面板看着有专家、实际那个轴**无人覆盖**——
  且机器**检不出来**（轴覆盖是语义判断）。所以要人工核对（`collapse show` 的覆盖核对表）。

### 4. `content_axes`（知识覆盖方向）
```yaml
  content_axes: [<轴1>, <轴2>, <轴3>]
```
- 是 `expert_panel[].coverage_axes` 的**上位集合**——专家的轴必须从属于此。

### 5. `evidence_hierarchy`（证据层级——**反幻觉的骨架**）
```yaml
  evidence_hierarchy:
    institutional: [<机构权威源1>, <机构权威源2>]
    institutional_endpoints:
      - name: <来源名>
        role: <它在本域的权威位次>
        status: <可达性状态>
        endpoint: <直链>
        retrieval_patterns: [<怎么搜到具体条目>]
    academic: [<学术源>]
    teaching: [<教材/教辅>]
    local: [<用户/本地资料>]
```
- ⚠ **机构源必须联网核实现行版本**并标注国家/地区与生效年份；
  **直链未核实就写"未核实"，禁止编造 URL**（本包铁律）。
- 层级顺序 = **取证优先级**；跨层冲突按 `references/adjudication-rules.md` 的证据冲突并列原则处理。

### 6. `image_channel`（取图通道与许可）
```yaml
  image_channel:
    channels:
      - name: <通道名>
        role: <该通道在本域的用途>
        status: <稳定有效 / 常失败 / 不可指望>
        endpoint: <直链或取图式>
        license_rule: <许可约束>
    caption_elements: [<图注要素>]     # 域扩展项（通用骨架见 config/visual-rules.yaml#caption_base_elements）
    retrieval_patterns: [<检索式>]
```
- ⚠ `caption_elements` 是**域扩展**，**不得与** `config/visual-rules.yaml#caption_base_elements`
  （对象 / 来源与许可 / 教学意义）**重复**——重复由 `scripts/test_arch_drift.py` 漂移守卫阻断。
- ⚠ 通道 `status` 要**如实写**（"常失败""不可指望"也是有效信息——本包禁止把降级写成可用）。

### 7. `knowledge_bases_ref` / `knowledge_bases_scope` / `knowledge_bases_note`
```yaml
  knowledge_bases_ref: "config/external-tools.yaml#knowledge_bases"
  knowledge_bases_scope: <该域可用的库范围说明>
  knowledge_bases_note: <给成员看的一句话>
```
- ⚠ **本域没有账号内库**时，`knowledge_bases_ref` 改指
  `config/external-tools.yaml#domains_without_knowledge_bases`——
  装配器据此判定"无库"语义（`domains_without_knowledge_bases` 这个串是**判据**，
  写错会让"有库域"渲染成无库、或反之，属同屏矛盾）。
- ⚠ 库的实际清单在 `config/external-tools.yaml#knowledge_bases`，靠**每条库的 `owner_scope`** 归属到域。
  新域要用新库时：在 `external-tools.yaml#knowledge_bases` 加条目并设 `owner_scope: <新域id>`。

### 8. `terminology` / `delivery_language` / `glossary`
```yaml
  terminology: [<术语规范条目>]
  delivery_language: zh-CN          # 默认中文（唯一源 config/language-profile.yaml#default_language）
  glossary:                        # 词条：dict 形态 {zh,en,abbr} 或字符串形态
    - {zh: <中文名>, en: <English>, abbr: <缩写>}
```
- ⚠ 交付语言与"何时可做英语 PPT"由 `config/language-profile.yaml` 决定，**不在本域档案里另立**。

### 9. `safety_redlines`（安全红线——拒收项）
```yaml
  safety_redlines: [<红线1>, <红线2>]
```
- 如"不提供超纲操作细节""不给出处方剂量""不涉及未获批适应症"。

### 10. `knowledge_anchor`（本域的**本地导航锚点**）
```yaml
  knowledge_anchor:
    path: references/<本域索引文件>.md
    note: <这个文件解决什么问题>
```
- ⚠ `path` 指向的文件**必须真实存在**（装配器会引用它）；不存在就留空并说明。

### 11. `user_supplied_sources`（用户指定源策略）
```yaml
  user_supplied_sources:
    enabled: true
    intake_field: intake.user_sources
    default_strategy: <用户指定源优先但不豁免核验>
    conflict_rule: <与机构源冲突怎么办>
    traceability_rule: <每条结论须附什么定位>
```

### 12. `member_bindings`（成员 × 域的绑定）
```yaml
  member_bindings:
    - {member: dvm-content-expert, binding: persona_subject, note: <说明>}
```
- `binding` 取 `persona_subject`（承载域人格）或 `domain_neutral`（职责与域无关，**不注入**域人格）。

### 13. `audience_profile` / `depth_scale_source` / `course_module_templates`
- `audience_profile`：四层受众的差异（层说明 / 数据要求 / 病例形态 / 岗位语境）。
- `depth_scale_source`：深度三档（了解/理解/掌握）的**出处**——
  ⚠ 优先写**该专业的教学标准**（如"教育部《XX专业教学标准》"），这是"用专业标准耦合 PPT 诊断"的关键字段。
  收录流程见 `references/standards-collection-sop.md`。
- `course_module_templates`：该域的模块/页序模板（十模块式、案例式等）。

---

<!-- DOMAIN_EXAMPLE_BEGIN -->
## 三、完整样例（"医学影像技术"——刻意选一个与动物医学不同的主题，用于证明跨专业可用）
<!-- DOMAIN_EXAMPLE_END -->

```yaml
- id: medical-imaging
  display_name: 医学影像技术
  match_hints: [影像, X线, 超声, CT, MRI, 放射, 超声诊断]
  role_persona:
    title: 医学影像内容权威
    background: 医学影像诊断与放射/超声双背景的教师
    stance: 影像征象描述必须能追到教材或指南，模棱两可的征象不上课件
    duties:
      - 供给经核验的影像学知识（检查原理、正常解剖、常见征象、鉴别要点）
      - 对课件中的影像学错误直接指出并给正确表述
    duty_boundary: 只做内容核验、证据检索与分级、术语规范；不做教学设计、不做版式设计
  expert_panel:
    - id: radiology_expert
      title: 放射诊断专家
      background: 放射诊断学背景，长期从事 X 线/CT 的征象判读
      stance: 征象结论须能追到教材图谱或指南页码，不采信未溯源的判读
      duties: [把关 X 线/CT 的检查原理与征象表述, 核验影像定位与征象描述的证据等级]
      duty_boundary: 只对放射学结论负责；超声与核医学由对应专家负责
      coverage_axes: [成像原理与设备, 正常解剖与变异, 常见征象与鉴别]
      activation_hints: [X线, CT, 放射, 平片, 断层]
    - id: ultrasound_expert
      title: 超声诊断专家
      background: 超声医学背景，擅长腹部与浅表器官检查
      stance: 超声测量值须写明切面与体位，否则判为不可复现
      duties: [把关超声检查规范与测量方法, 核验超声征象与鉴别诊断表述]
      duty_boundary: 只对超声结论负责；放射与核医学由对应专家负责
      coverage_axes: [成像原理与设备, 检查规范与测量, 常见征象与鉴别]
      activation_hints: [超声, B超, 声像, 测量, 扫查]
    - id: medical_imaging_teacher
      title: 医学影像教学设计专家
      background: 医学影像技术专业教学背景
      stance: 教学顺序按"成像原理→正常→征象→鉴别"推进，不按检查项目平铺
      duties: [把影像知识组织成可学可练的教学单元, 设计看图任务与判读训练]
      duty_boundary: 只管教学组织与学情，不判影像学结论对错
      coverage_axes: [教学单元设计, 看图任务与判读训练, 学情与难点]
      activation_hints: [教学, 实训, 看图, 判读, 学情]
  content_axes: [成像原理与设备, 正常解剖与变异, 常见征象与鉴别, 教学单元设计]
  evidence_hierarchy:
    institutional:
      - 现行诊疗技术规范与卫生行业标准（须联网核验现行版本，标注发布年份）
      - 中华医学会放射学分会指南
    institutional_endpoints:
      - name: 医学影像学（人卫版教材配套数字资源）
        role: 条目级权威参考（正常解剖与征象图谱）
        status: 需校内/机构订阅
        endpoint: <按实填写，未核实就写未核实>
        retrieval_patterns: [<怎么定位到具体章节>]
    academic: [PubMed 检索综述与原始研究, 中国知网教学研究]
    teaching: [医学影像学教材, 医学影像技术专业教学指导]
    local: [用户指定教材与课件, 校内实训指导书]
  image_channel:
    channels:
      - name: 开放获取论文附图（Europe PMC）
        role: 图片主力——真实征象图
        status: 稳定有效
        endpoint: https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/supplementaryFiles
        license_rule: 仅取 CC-BY / 开放获取论文图片
      - name: 教材插图
        role: 正常解剖图谱
        status: 受版权限制，须授权或改用自绘示意
        license_rule: 不得直接取用未授权教材图
    caption_elements: [检查方法与体位, 切面与测量, 影像与征象的对应关系]
    retrieval_patterns: ["<影像特征名> radiograph ultrasound sign", "site:openaccess PubMed <主题> figure"]
  knowledge_bases_ref: "config/external-tools.yaml#domains_without_knowledge_bases"
  knowledge_bases_scope: 本域暂无账号内知识库，走联网机构源与开放获取
  knowledge_bases_note: 本域无账号内知识库——按通用兜底（联网查机构规范/指南）执行，**严禁**静默用其它域的库
  terminology: ["影像征象术语统一用中文（English, Abbreviation）", "检查方法名以现行规范为准"]
  delivery_language: zh-CN
  glossary:
    - {zh: 超声, en: Ultrasonography, abbr: US}
    - {zh: 计算机断层扫描, en: Computed Tomography, abbr: CT}
    - {zh: 磁共振成像, en: Magnetic Resonance Imaging, abbr: MRI}
  safety_redlines:
    - 不给出具体检查剂量与操作参数（超出技术规范范围）
    - 不对个体病例下诊断结论（只讲判读思路与转诊指征）
  knowledge_anchor:
    path: ""
    note: 本域尚无本地导航锚点——首次接单时按需建 references/medical-imaging-index.md
  user_supplied_sources:
    enabled: true
    intake_field: intake.user_sources
    default_strategy: 用户指定源 > 通用检索；不豁免机构轴核验与双源要求
    conflict_rule: 与机构规范冲突时按机构轴优先，并显式提示冲突、并列呈现
    traceability_rule: 每条取自指定源的结论须附 PDF 页码/章节号或 URL + 访问日期
  member_bindings:
    - {member: dvm-content-expert, binding: persona_subject, note: 内容专家 = 域人格承载者}
  audience_profile:
    layer_notes:
      - ② 基层医技：设备与操作规范、常见征象识别、质控要点
      - ③ 职业本科与本科生：成像原理 + 正常解剖 + 征象判读 + 病例
      - ④ 研究生：成像新进展、图像后处理、文献争议
    data_requirements:
      - ② 可复现的判读要点 + 阈值 + 来源
      - ③ 结论性数字 + 样本量与来源
    case_forms: ["真实影像病例（讲怎么看）", "典型征象对照（讲怎么辨）"]
    job_context: 影像技师/诊断医师/质控岗的职责边界与执业要求
  depth_scale_source:
    standard: 教育部《医学影像技术专业教学标准》（须核验现行版本）
    core_course: 医学影像检查技术
    note: 三档动词（了解/理解/掌握）以该专业教学标准用词为准
  course_module_templates:
    - id: imaging_ten_module
      title: 影像专题课十模块
      applies_to: 病种/检查专题课
      note: 按课时裁剪，不得按教科书目录平铺
      modules:
        - {name: 导入与概述, focus: 真实病例引入 → 知识地图 → 学习目标}
        - {name: 成像原理, focus: 设备与物理基础（配高质量图）}
        - {name: 正常解剖, focus: 标准切面与正常变异}
        - {name: 常见征象, focus: 典型征象与机制}
        - {name: 鉴别诊断, focus: 易混淆征象对照}
        - {name: 检查规范, focus: 摆位、参数、质控}
        - {name: 病例串讲, focus: 真实病例读片}
        - {name: 实训与看图任务, focus: 判读训练与自评}
        - {name: 小结与红线, focus: 要点回顾 + 安全红线}
        - {name: 拓展与前沿, focus: 新技术进展}
```

---

## 四、接入后的自检（3 条命令，1 分钟）

```bash
H="python3 <专家包>/scripts/harness.py"; W="<工作空间>"
# ① 域能被选中
python3 "$H" domain list | grep -A 2 "<新域id>"
# ② 专家面板能生成（先选人，再确认）
python3 "$H" route --level L2 --domain <新域id> --task-id T-1 --panel <id1,id2> --rationale "<理由>" --workspace "$W"
python3 "$H" collapse show --id <新域id> --task-id T-1 --workspace "$W"   # 看专家面板与覆盖轴
# ③ 装配后域人格真注入（不是兜底）
python3 "$H" collapse confirm --id <新域id> --task-id T-1 --actor user --decision "<裁决>" --rationale "<理由>" --workspace "$W"
python3 <专家包>/scripts/assemble_domain_prompt.py --member dvm-content-expert \
  --collapse-artifact "$W/.harness-runs/T-1/_collapse/collapse_T-1_<新域id>.json" \
  --task-id T-1 --out /tmp/spawn.md
grep -c "【一、域人格】" /tmp/spawn.md   # 应 ≥ 1；且输出 domain_context=effective
```

⚠ 若 ③ 显示 `domain_context=fallback_*` ⇒ 域档案没生效（字段名写错或 YAML 结构错），
**别靠兜底凑合**——回到本模板核字段名。

---

## 五、常见坑（都是本包实测踩过的）

| 坑 | 症状 | 根因 | 修法 |
|---|---|---|---|
| 字段名自造 | 装配产物里该段是兜底内容 | 字段名不在 domain-profiles 现有结构里 | 照本模板字段清单，**不新增字段** |
| 库归属写错 | 域显示"无账号内知识库" | 库条目的 `owner_scope` 不是本域 id | 改 `external-tools.yaml#knowledge_bases[].owner_scope` |
| `knowledge_bases_ref` 写错 | 有库域渲染成无库（或反之） | 该串是**判据**（含 `domains_without_knowledge_bases`） | 按第三节的写法二选一 |
| 专家轴对不上 | 面板有人但某轴无人 | `coverage_axes` 与 `content_axes` 不交 | 人工核对覆盖（机器判不了） |
| 深度三档没出处 | 教学深度无依据 | `depth_scale_source` 留空 | 引该专业教学标准（见 standards-collection-sop） |
| 图注要素重复 | 漂移守卫报错 | `caption_elements` 重复了通用骨架 | 域扩展只写**骨架之外**的项 |

---
name: maintain-knowledge-base
description: "Design, initialize, query, audit, and safely maintain durable local knowledge bases for scientific research and administrative work. Use when Codex needs to create a knowledge-base structure; register equipment, software, datasets, samples, organizations, standards, projects, or sources; add or update facts and reusable knowledge; connect project knowledge to shared entities; promote validated project findings; answer inventory or relationship questions; detect duplicates, conflicts, stale records, broken links, or missing provenance; or archive obsolete material without losing history. 适用于构建、维护、整理、审计和新增科研及事务型长期本地知识库。"
---

# 维护长期知识库

把本地文件知识库视为长期权威记忆。聊天记忆只能辅助召回，不得取代已验证的本地事实、项目记录和来源。

## 工作契约

- 优先适配现有知识库；除非用户要求迁移，不要强行套用默认目录。
- 每项事实只有一个权威维护位置。索引、项目和知识笔记通过 ID 或链接引用，不复制易变化字段。
- 先检索再新增。无法确认新旧记录是否同一对象时，停止合并并说明歧义。
- 统计数量和状态时读取结构化登记表，不根据文件夹数量或聊天记忆推断。
- 不编造缺失事实。将“未知”“未记录”“没有”严格区分。
- 保留来源、验证日期和变更原因。重要历史采用归档或决策记录，不静默覆盖。
- 默认使用开放、可迁移的 Markdown、CSV 和相对路径；不要让某个笔记软件成为唯一读取方式。
- 不保存密码、令牌、私钥或不必要的敏感个人信息；只记录安全存储位置的引用。

## 按任务读取参考资料

- 新建知识库或调整整体结构：读取 [references/architecture.md](references/architecture.md) 和 [references/schema.md](references/schema.md)。
- 新增、更新、提炼或归档知识：读取 [references/maintenance.md](references/maintenance.md) 和 [references/schema.md](references/schema.md)。
- 处理科研实验、数据、论文或事务项目：读取 [references/research-and-operations.md](references/research-and-operations.md)。
- 解释设计依据或比较知识管理方法：读取 [references/research.md](references/research.md)。
- 审计现有知识库：读取 [references/maintenance.md](references/maintenance.md)，并优先运行 `scripts/audit_kb.py`。

只读取当前任务需要的参考文件，不要一次加载全部资料。

## 首次使用与知识库路径

Skill 可以全局安装，但知识库路径不得写死在 Skill 内。除非用户在当前请求中明确给出知识库路径，否则每次任务开始先运行：

```text
python <skill-dir>/scripts/configure_kb.py resolve --json
```

处理结果：

1. 已配置且路径存在：使用返回的默认知识库。
2. 尚未配置：询问用户要使用现有目录还是创建新知识库，并让用户给出目录。不要扫描整块磁盘猜测位置。
3. 用户选择现有目录：先只读检查其内容和写入边界，再运行 `configure_kb.py set <name> <path> --default`。
4. 用户选择新目录：先运行 `init_kb.py`，确认初始化成功后再保存配置。
5. 已配置路径失效：报告旧路径并要求用户确认新位置；不要擅自在旧位置重新创建空知识库。

用户在当前请求中明确指定的路径优先于默认配置，但不会自动改写默认配置。只有用户明确要求“以后默认使用这里”时才更新配置。

配置保存在 Codex home 下的 `maintain-knowledge-base/config.json`，只保存知识库名称和路径，不保存知识内容或凭据。支持登记多个知识库，并选择其中一个作为默认值。

## 核心模型

将内容分为五类，并确定唯一权威位置：

| 内容 | 默认权威位置 | 处理原则 |
|---|---|---|
| 可统计事实与对象身份 | `catalog/`、`domains/` | 使用稳定 ID、状态、日期和来源 |
| 通用概念、方法与流程 | `knowledge/` | 围绕概念或用途组织，明确适用范围 |
| 项目过程与项目结论 | `projects/<project-id>/` | 保留上下文、实验、决策和证据 |
| 外部原始资料 | `sources/` | 尽量保持原始内容，记录出处和访问条件 |
| 对象间关系 | `catalog/relations.csv` | 使用受控关系词和双端实体 ID |

默认架构面向科研与事务处理，但允许按领域增加类型。不要为少量内容预建大量空分类。

## 通用工作流

### 1. 确认知识库和请求范围

1. 使用用户明确路径或已配置的默认路径定位知识库；若多个候选目录会导致写入不同位置，先询问用户。
2. 读取根目录 `AGENTS.md`、`README.md`、`catalog/vocabulary.md` 和相关项目的 `PROJECT.md`。
3. 判断任务是查询、新增、更新、提炼、审计、迁移还是归档。
4. 在写入前检查工作区现状和未提交修改，保留无关的用户改动。

### 2. 分类待处理内容

判断内容属于：

- `entity/fact`：设备、探头、软件、样本、数据集、组织、标准、人员角色等客观对象或状态；
- `relationship`：项目使用设备、数据由实验产生、方法依据标准等关系；
- `concept/explanation`：跨项目成立的概念、原理或解释；
- `method/protocol`：可复用的方法、操作流程或故障处理；
- `project-context`：仅在特定科研或事务项目中成立的过程与结论；
- `decision`：带背景、选项、理由和影响的决定；
- `source/evidence`：论文、说明书、标准、会议纪要或其他证据；
- `fleeting`：尚未判断价值的零散信息，先进入 `inbox/`。

一个输入可以拆成多个类型，但不要为了原子化而破坏上下文。

### 3. 检索和消歧

1. 搜索名称、别名、型号、序列号、已有 ID 和相近标题。
2. 检查 `entities.csv`、类型专用登记表、关系表以及目标项目。
3. 判断是新对象、新事实、已有事实更新、冲突事实，还是已有知识的补充证据。
4. 对同名不同物、同一物多名称和型号/实物混淆进行显式消歧。

### 4. 写入权威位置

按以下顺序更新：

1. 登记或确认实体 ID；
2. 写入或更新结构化事实；
3. 更新对象说明、项目记录或通用知识正文；
4. 登记关系及其证据；
5. 更新必要的导航入口；
6. 记录 `updated_at`，客观事实同时记录 `verified_at`；
7. 运行审计。

若某字段已有权威位置，只更新那里；其他页面使用链接或生成视图展示。

### 5. 验证和交付

- 检查 ID 唯一、CSV 结构、相对路径、关系端点、日期和必需元数据。
- 检查事实是否有来源、观察记录或用户明确陈述作为证据。
- 检查项目知识是否被错误提升为通用知识。
- 告知用户新增、更新、冲突、未确定和归档了什么，并给出可点击的权威文件路径。

## 新建知识库

读取架构和模式参考后运行：

```text
python <skill-dir>/scripts/init_kb.py <knowledge-base-root> --name "知识库名称"
```

脚本只创建缺失目录和文件，不覆盖现有内容。初始化后：

1. 根据真实需求精简或扩展 `catalog/vocabulary.md`；
2. 在根 `AGENTS.md` 中记录权威来源、隐私边界和维护规则；
3. 先登记少量真实对象和项目，再决定是否增加新类型；
4. 运行 `audit_kb.py` 建立干净基线。

## 查询知识库

根据问题选择入口：

- 数量、状态、位置、负责人：先查 `catalog/` 或领域登记表；
- 某项目涉及什么：先读项目 `PROJECT.md`，再按 ID 查关系和对象；
- 某概念或方法是什么：先查 `knowledge/`，再查来源和采用它的项目；
- 某结论依据什么：沿知识条目的 `sources`、项目证据和关系记录追溯；
- 当前有哪些事项：查活动项目和项目入口；不要把历史归档混入当前状态。

回答时区分“登记事实”“从文件推断”和“当前无法确认”。尽可能引用本地权威文件。

## 从项目提炼通用知识

只有同时满足以下条件才提升：

- 能在原项目之外复用；
- 结论有可追溯证据或明确经验边界；
- 已删除样本、人员、日期等不必要的项目特异信息；
- 写明适用条件、限制和不适用场景；
- 通用条目反向链接原项目和来源；
- 原项目保留完整原始上下文，不因提升而删除。

不满足时继续保留在项目内，并标记 `candidate` 或 `unverified`。

## 审计与归档

运行：

```text
python <skill-dir>/scripts/audit_kb.py <knowledge-base-root>
```

修复顺序：结构错误、重复 ID、断裂关系、缺失路径、冲突事实、缺失来源、陈旧记录、孤立内容。自动化审计之后仍需人工判断语义重复、结论过期和分类不当。

默认归档而非删除。归档时保留 ID、原路径或重定向、归档时间、原因以及替代对象。不得复用已分配的 ID。

## 边界

- 知识库保存长期可复用信息；实时任务提醒优先交给任务或日历系统，只在项目中保留长期有价值的承诺、决策和结果。
- 大型原始数据可以保存在外部数据目录；知识库保存稳定路径、指纹、访问条件、生成过程和结果说明。
- 外部来源不等于已验证知识。先保存来源，再由项目或知识条目明确提炼出的主张。
- 向量检索是可选加速层，不是权威存储层。即使索引丢失，Markdown、CSV、来源和关系仍须可独立恢复。

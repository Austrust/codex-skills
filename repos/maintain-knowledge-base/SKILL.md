---
name: maintain-knowledge-base
description: "Query, record, continue, audit, and safely maintain durable local knowledge bases stored as Markdown + CSV. Use when the user asks what is recorded (inventory, status, decisions, past work), asks to remember or update a fact, decision, method, or lesson, continues an existing project and needs prior context, or asks to audit, migrate, back up, or restore a knowledge base. 适用于查询、记住、继续项目与审计迁移；不负责 README/目录导航（用 research-readme-index）。"
---

# 维护长期知识库

本技能只负责三件事：**记什么、存哪里、以后怎么找**。目录导航、会话收尾、文件夹重组不属于本技能。

## 定位与边界

| 场景 | 归属 |
|---|---|
| 一条事实/经验是否入库、放哪个权威文件、怎么命名、以后怎么检索 | 本技能 |
| 目录 README 的入口、链接、层级导航 | `research-readme-index` |
| 会话收尾：多层文档/记忆是否过期、矛盾、重复 | `neat-freak` |
| 文件夹混乱、搬家、归档批次、项目结构重组 | `research-folder-organizer` |
| 实时待办、排期、提醒 | 看板/日历/任务系统；本技能只存长期承诺与决定 |

同一事实只维护一处；其他位置只放链接、ID 或可重建投影：

| 内容 | 唯一权威位置 |
|---|---|
| 身份、类型、生命周期状态（对象/项目） | `catalog/entities.csv`；项目专用字段在 `catalog/projects.csv`；`PROJECT.md` 的 status 必须与 CSV 一致 |
| 知识条目状态与日期（KN/MT/PTC） | 条目 YAML front matter；`entities.csv` 行是索引投影 |
| 关系 | `catalog/relations.csv` |
| 类型专用事实（型号、序列号、许可、地址、连接信息） | 对应领域条目 `domains/**/README.md` |
| 解释、方法、经验、限制 | 条目正文（`knowledge/`、领域条目、`PROJECT.md`） |
| 外部证据 | `sources/` 或 SRC 条目 |
| 日期 | `created_at` 创建、`updated_at` 记录修改、`verified_at` 实际重新核实；不得混用 |
| 导航 | README（readme-index 维护）；本技能不往 README 写状态、日期、数量 |
| 规则 | 各层 `AGENTS.md` 只写本层差异：流程在技能，库布局/权威映射在库内 AGENTS，库位置声明在工作区 AGENTS |
| 凭据 | 安全存储位置；库内只写「见某条目/脚本」 |

## 三种操作模式

先判断模式，只做该模式需要的动作。

| 模式 | 典型话 | 动作 | 写入与审计 |
|---|---|---|---|
| 查询 | 「我有哪些探头」「上次结论是什么」 | 按检索协议只读查找并回答 | 零写入、零审计 |
| 日常维护 | 「记一下」「这个值更新为…」「新增一台…」 | 按变化落点更新唯一权威位置，见下表 | 只写必要位置；不跑审计 |
| 结构操作 | 「搬到…」「合并重复」「改 schema/词表」「恢复备份」 | 预演 → 备份 → 执行 → 审计 → 复核入口 | 至少一次 `audit_kb.py`；恢复后必须审计 |

日常维护的落点判断（只改需要改的地方）：

| 变化 | 更新位置 |
|---|---|
| 已有事实的补充、修正、经验细节 | 该权威条目正文 + `updated_at`（实际重新核实才改 `verified_at`） |
| 对象/项目的状态、数量、负责人 | `catalog/entities.csv`（项目另加 `catalog/projects.csv`）；条目展示同步一次 |
| 新对象（设备、软件、数据集、来源等） | 新条目 + `entities.csv` 行 + 未用 ID；按需写 `aliases` |
| 真实跨对象关系且未来会被查询 | `catalog/relations.csv` 一行；不为填满结构补关系 |
| 需长期引用的外部证据 | `sources/` 文件或 SRC 条目；用户口述/本次命令输出写成行内证据即可 |

写入底线：先检索再新增；不编造缺失事实；不静默覆盖冲突；归档而非删除；不复用 ID。目录类结构变化（新增/移动/删除导航入口）交给 `research-readme-index`，本技能不改 README。

## 检索协议

1. 入口顺序：`catalog/*.csv`（ID、名称、型号、序列号、状态）→ 条目 front matter 的 `aliases`/`title` → 正文关键词 → `catalog/relations.csv` 关系链。
2. 候选排序：ID 精确 > 名称/别名精确 > 名称/别名宽松（大小写、全半角、空格/连字符、中英）> 正文关键词 > 关系链。同分优先权威条目、已验证、更新时间新。
3. 名称与别名只写在条目 front matter（规范见 `references/schema.md`）；IP、主机名、账号地址属于带 `verified_at` 的连接信息，不作为永久身份别名。
4. 失败处理：零命中回答「库内未记录」并列出检索词与范围，给出 1–3 个相近候选（ID + 一句话），问用户是否要记；多命中列候选与区分依据，提一个具体消歧问题；不猜、不静默合并。
5. 回答格式：结论 → 为什么匹配（命中 ID/别名/关键词）→ 权威文件链接 → 何时需核实（`verified_at` 陈旧、历史记录≠当前状态、与用户新说法冲突）。

## 路径优先级

1. 本次请求明确给出的知识库路径（不改默认配置）。
2. 当前工作区 `AGENTS.md`/`README.md` 已声明的知识库位置。
3. 本机默认：`python <skill-dir>/scripts/configure_kb.py resolve --json`。
4. 都没有或失效：问用户用现有目录还是新建；不扫盘猜测，不在旧位置重建空库。只有用户明确说「以后默认这里」才 `set --default`。

多库用 `--name` 选择。配置、初始化、失效处理见 [references/paths.md](references/paths.md)。

## 审计时机

- 查询与日常维护不跑审计（只读或只更新少量权威位置）。
- 需要 `python <skill-dir>/scripts/audit_kb.py <kb-root>`：新增/删除 ID、改 `catalog` 行、改关系、移动/合并/改名条目、改 schema/词表/模板/CSV 列、恢复备份后、迁移前后。
- 结构操作顺序：预演（列出将改的文件与 ID）→ 备份 → 执行 → 审计 → 复核入口；出问题按 [references/backup-restore.md](references/backup-restore.md) 恢复。
- 用户要求「体检/整理」或 neat-freak 收尾：跑脚本 + 人工判断语义重复、结论过期、分类不当；审计通过不等于内容正确。

## 不做

- 不建向量库/嵌入索引：当前规模用 CSV + grep 足够；派生索引会漂移且恢复成本高。
- 不用数字置信度：用状态词（validated/candidate/unverified/conflicted）+ 日期 + 来源表达不确定性。
- 不每次写入全量审计：脚本只查结构，频繁运行噪声大。
- 不为一次补充强制新建实体、关系或来源文件。
- 不在 README、AGENTS、多个条目之间复制状态、日期、导航。
- 不在 SKILL.md 写机器路径与个人偏好。

## 参考文件（按需加载，不要一次全读）

| 任务 | 读取 |
|---|---|
| 路径、配置、多库、失效处理 | [references/paths.md](references/paths.md) |
| 建库、目录与字段设计 | [references/architecture.md](references/architecture.md)、[references/schema.md](references/schema.md) |
| 登记、更新、晋升、冲突、审计清单 | [references/maintenance.md](references/maintenance.md)、[references/schema.md](references/schema.md) |
| 科研与事务项目流程 | [references/research-and-operations.md](references/research-and-operations.md) |
| 备份、恢复、迁移 | [references/backup-restore.md](references/backup-restore.md) |
| 设计依据与方法比较 | [references/research.md](references/research.md) |

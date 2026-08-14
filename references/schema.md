# 默认模式与受控词汇

## 目录

1. 权威字段原则
2. 中央表
3. ID 规则
4. 内容元数据
5. 状态与关系词
6. 冲突和时间语义

## 1. 权威字段原则

每个字段必须指定唯一权威所有者：

- `entities.csv`：跨类型身份、类型、当前生命周期状态和权威路径；
- `projects.csv`：项目专用字段；
- `relations.csv`：对象间关系、有效期和关系证据；
- 领域登记表：设备序列号、软件许可证、样本条件等类型专用事实；
- Markdown 条目：解释、适用范围、方法步骤、限制和叙述性历史；
- 来源文件：外部证据的原始内容或可定位引用。

同一信息出现在非权威页面时，应通过 ID、链接或生成视图呈现。

## 2. 中央表

### `catalog/entities.csv`

```csv
entity_id,type,subtype,name,status,canonical_path,evidence_path,created_at,verified_at,updated_at
EQ-0001,equipment,probe,P5-1探头01,available,domains/equipment/EQ-0001,sources/manuals/P5-1,2026-08-14,2026-08-14,2026-08-14
PRJ-2026-001,project,research,肝脏超声成像,active,projects/PRJ-2026-001,,2026-08-14,2026-08-14,2026-08-14
```

要求：

- `entity_id` 永久唯一且不得复用；
- `type` 和 `subtype` 使用受控词汇；
- `status` 表示当前生命周期状态；
- `canonical_path` 使用相对知识库根目录的路径；
- `evidence_path` 可为空，但客观外部事实应尽量提供；
- 日期使用 `YYYY-MM-DD`。

### `catalog/projects.csv`

```csv
project_id,project_kind,area,objective,owner,started_at,target_end,ended_at,updated_at
PRJ-2026-001,research,ultrasound,评估指定条件下的成像效果,研究组,2026-08-14,,,2026-08-14
```

项目也必须在 `entities.csv` 中登记为 `type=project`。此表只保存项目专用字段，不重复名称、状态和路径。

### `catalog/relations.csv`

```csv
from_id,relation,to_id,context,evidence_path,valid_from,valid_to,updated_at
PRJ-2026-001,uses,EQ-0001,用于采集原始数据,projects/PRJ-2026-001/PROJECT.md,2026-08-14,,2026-08-14
```

关系具有方向。反向查询通过交换端点完成，不必为每条关系手工写反向副本。

## 3. ID 规则

推荐前缀：

| 类型 | 前缀 | 示例 |
|---|---|---|
| 设备 | `EQ` | `EQ-0001` |
| 软件 | `SW` | `SW-0001` |
| 数据集 | `DS` | `DS-0001` |
| 样本 | `SMP` | `SMP-0001` |
| 组织 | `ORG` | `ORG-0001` |
| 标准 | `STD` | `STD-0001` |
| 方法 | `MT` | `MT-0001` |
| 协议 | `PTC` | `PTC-0001` |
| 概念 | `KN` | `KN-0001` |
| 来源 | `SRC` | `SRC-0001` |
| 项目 | `PRJ` | `PRJ-2026-001` |
| 决策 | `DEC` | `DEC-2026-001` |
| 实验 | `EXP` | `EXP-2026-001` |

规则：

- ID 表达身份，不编码可能变化的状态、负责人或位置；
- 型号和实物使用不同实体，例如 `equipment_model` 与 `equipment_unit`；
- 合并重复实体时保留废弃 ID，并使用 `superseded_by` 指向保留 ID；
- 文件改名或移动不改变 ID。

## 4. 内容元数据

通用知识条目使用简洁 YAML front matter：

```yaml
---
id: MT-0001
title: 探头校准方法
kind: method
status: validated
scope: 超声探头
sources:
  - SRC-0001
origin_projects:
  - PRJ-2026-001
created_at: 2026-08-14
verified_at: 2026-08-14
updated_at: 2026-08-14
---
```

正文至少说明：目的或定义、适用范围、内容或步骤、限制、证据、相关知识。

项目入口使用：

```yaml
---
id: PRJ-2026-001
title: 肝脏超声成像
kind: research
status: active
updated_at: 2026-08-14
---
```

项目状态的权威值位于 `entities.csv`；入口页的状态用于可读展示，审计时必须保持一致。

## 5. 状态与关系词

建议状态：

- 知识：`draft`、`candidate`、`validated`、`deprecated`、`archived`；
- 项目：`planned`、`active`、`blocked`、`completed`、`cancelled`、`archived`；
- 资产：`available`、`in_use`、`maintenance`、`retired`、`lost`、`archived`；
- 通用：`unknown`、`inactive`。

建议关系：

| 关系 | 方向含义 |
|---|---|
| `uses` | 项目或方法使用对象 |
| `produces` | 实验或项目产生数据、报告或结果 |
| `applies` | 项目采用方法、协议或标准 |
| `derived_from` | 知识、数据或报告来源于另一对象 |
| `supports` | 证据支持主张或决策 |
| `contradicts` | 证据或知识与另一项冲突 |
| `part_of` | 对象属于更大对象 |
| `instance_of` | 实物属于某型号或类别 |
| `located_at` | 对象位于某地点实体 |
| `owned_by` | 对象由组织或角色持有 |
| `supersedes` | 新对象或知识替代旧对象或知识 |
| `related_to` | 无法使用更精确关系时的最后选择 |

## 6. 冲突和时间语义

- 新信息与现有事实冲突时，不直接选择较新的说法；比较来源、观察时间和权威性。
- 当前事实更新后，把需要保留的旧事实写入历史、决策或事件记录，并说明有效期。
- `updated_at` 表示文件或记录被修改；`verified_at` 表示事实最后一次被实际核实。两者不得混用。
- `valid_from`/`valid_to` 表示关系在现实中的有效期，不是录入日期。
- 无法解决的冲突应保留双方证据，并标记 `conflicted` 或在项目决策中记录待确认事项。

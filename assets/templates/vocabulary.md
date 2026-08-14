# 受控词汇

本文件定义知识库允许使用的实体类型、状态、关系和 ID 前缀。扩展前先确认现有词汇不能准确表达需求。

## 实体类型

| type | 常见 subtype | ID 前缀 |
|---|---|---|
| equipment | probe, sensor, instrument, computer, equipment_model | EQ |
| software | application, library, license, environment | SW |
| dataset | raw, processed, reference | DS |
| sample | biological, material, phantom | SMP |
| organization | laboratory, vendor, collaborator, authority | ORG |
| standard | standard, policy, specification | STD |
| project | research, administrative | PRJ |
| method | experimental, analytical, statistical | MT |
| protocol | acquisition, processing, operational | PTC |
| concept | principle, model, explanation | KN |
| source | paper, manual, standard, meeting-record | SRC |

## 状态

- 知识：draft, candidate, validated, deprecated, archived
- 项目：planned, active, blocked, completed, cancelled, archived
- 资产：available, in_use, maintenance, retired, lost, archived
- 通用：unknown, inactive

## 关系

uses, produces, applies, derived_from, supports, contradicts, part_of, instance_of, located_at, owned_by, supersedes, related_to

关系必须填写方向、上下文和证据；仅在没有更准确词汇时使用 `related_to`。

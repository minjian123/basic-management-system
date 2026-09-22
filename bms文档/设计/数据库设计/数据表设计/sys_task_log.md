# sys_task_log（任务执行记录表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_task_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 24-任务调度 |
| 上游依据 | [需求 02-13](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-13)、《架构设计 · 任务调度》、《架构设计 · 后端基础类体系》「跨阶段基座」节 |
| ORM 模型 | `app/models/system.py::SysTaskLog`（继承 `BaseModel`） |
| 状态 | 已设计 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_task](sys_task.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `task_id` | BIGINT | 否 | `idx_sys_task_log_task_id` | 任务定义 ID（逻辑外键 → `sys_task.id`） |
| `status` | VARCHAR(16) | 否 | — | 执行状态（`running` / `success` / `failed`） |
| `started_at` | DATETIME | 是 | — | 开始时间（UTC） |
| `finished_at` | DATETIME | 是 | — | 结束时间（UTC） |
| `result` | TEXT | 是 | — | 执行结果 / 异常摘要 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_task_log_task_id` | 普通 | `(task_id)` | 按任务查执行记录 |

- 无物理外键；`task_id` 为逻辑外键（`sys_task.id`），同库。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（量级可控；如需按月分片随任务调度节点评估）。
- **归档**：按归档策略可归档（`sys_archive_policy` 落地后评估）。
- **迁移**：随租户库 Alembic 迁移落地（真实迁移归落库阶段）；本阶段仅结构声明，不建表。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（租户库；随回补阶段迁移） | minjian |
| 2026-09-22 | v2 | 索引名对齐实际库与模型元数据（`idx_task_id` → `idx_sys_task_log_task_id`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

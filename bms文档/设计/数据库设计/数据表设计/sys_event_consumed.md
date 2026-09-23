# sys_event_consumed（消费幂等账本）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_event_consumed

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` + 租户库 `bms_tenant_{code}`（双链，同库同事务） |
| 覆盖模块 | 05-服务间通信与一致性（幂等消费） |
| 上游依据 | 《架构设计 · 服务间通信与分布式一致性》「幂等与重放」节、《架构设计 · 事件总线》「幂等与重试」节、[需求 05-3](../../../项目/02_后端基座与服务化地基/需求/05_需求_服务间通信与一致性.md#r05-3) |
| ORM 模型 | `bms_core/models/outbox.py::SysEventConsumed`（继承 `BaseModel`） |
| 状态 | 已落库（平台链 `0003_sys_outbox` / 租户链 `0002_sys_outbox`，2026-09-23） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[架构 16-事件总线](../../架构设计/16_架构设计_子系统_事件总线.md)、[sys_outbox](sys_outbox.md)、[sys_event_dead_letter](sys_event_dead_letter.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `consumer` | VARCHAR(128) | 否 | 与 `event_id` 复合唯一（`uq_sys_event_consumed`） | 消费者标识（消费组 / 处理者） |
| `event_id` | VARCHAR(64) | 否 | 同上 | 事件 ID（与 `sys_outbox.event_id` 同源） |
| `event_type` | VARCHAR(128) | 是 | — | 事件类型（排障用） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |

> **物理账本口径（偏离说明）**：本表为消费幂等账本，行不作软删除，唯一约束 **不并入 `deleted_at`**（唯一 `(consumer, event_id)`）——去重须跨方言严格成立；若按 `(consumer, event_id, deleted_at)` 复合唯一，MySQL / PostgreSQL / SQLite 对 NULL 视作互异，重复事件可再次插入、去重失效。`created_at` 即「消费登记时间」。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_event_consumed` | 唯一 | `(consumer, event_id)` | 消费幂等（命中即视为已处理） |

- 无物理外键；公共软删除索引 `idx_sys_event_consumed_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（一库一表）。
- **归档**：暂不归档；过期记录清理随任务调度阶段（登记开放项）。
- **迁移**：随**平台链** `0003_sys_outbox` 与**租户链** `0002_sys_outbox` 落地（2026-09-23）；表集登记见 `bms_core/db/migration.py`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-23 | v1 | 新建表结构（平台链 + 租户链双落；消费幂等账本，随 05_03 迁移落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

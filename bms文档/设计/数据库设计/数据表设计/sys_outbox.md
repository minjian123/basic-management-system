# sys_outbox（事务性发件箱）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_outbox

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` + 租户库 `bms_tenant_{code}`（双链，同库同事务） |
| 覆盖模块 | 05-服务间通信与一致性（事务性 Outbox / 事件账本） |
| 上游依据 | 《架构设计 · 事件总线》「生产一致性」节、《架构设计 · 服务间通信与分布式一致性》「事务性 Outbox」节、《架构设计 · 核心交互时序》「跨服务调用与 Outbox 发布」节、[需求 05-3](../../../项目/02_后端基座与服务化地基/需求/05_需求_服务间通信与一致性.md#r05-3) |
| ORM 模型 | `bms_core/models/outbox.py::SysOutbox`（继承 `BaseModel`） |
| 状态 | 已落库（平台链 `0003_sys_outbox` / 租户链 `0002_sys_outbox`，2026-09-23） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[架构 16-事件总线](../../架构设计/16_架构设计_子系统_事件总线.md)、[架构 37-服务间通信与分布式一致性](../../架构设计/37_架构设计_子系统_服务间通信与一致性.md)、[sys_event_consumed](sys_event_consumed.md)、[sys_event_dead_letter](sys_event_dead_letter.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `event_id` | VARCHAR(64) | 否 | 唯一（`uq_sys_outbox_event_id`） | 事件 ID（幂等键；应用侧生成雪花 ID 字符串） |
| `event_type` | VARCHAR(128) | 否 | — | 事件类型（`{域}.{对象}.{动作}`） |
| `aggregate_key` | VARCHAR(128) | 是 | `idx_sys_outbox_aggregate` | 聚合 / 分区键（同聚合按序投递；空 = 独立事件） |
| `tenant_id` | VARCHAR(64) | 是 | — | 租户标识 |
| `payload` | JSON | 否 | — | 事件负载（事件信封 payload） |
| `occurred_at` | DATETIME | 否 | — | 事件发生时间（UTC） |
| `status` | VARCHAR(16) | 否 | 默认 `pending`；`idx_sys_outbox_dispatch` | 投递状态：`pending` / `delivered` / `dead` |
| `retry_count` | INT | 否 | 默认 0 | 已重试次数 |
| `next_retry_at` | DATETIME | 是 | `idx_sys_outbox_dispatch` | 下次可投递时间（指数退避；NULL = 立即可投） |
| `delivered_at` | DATETIME | 是 | — | 投递成功时间（UTC） |
| `error_msg` | VARCHAR(512) | 是 | — | 最近一次失败原因（截断） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |

> **物理账本口径（偏离说明）**：本表为基础发件箱账本，行不作软删除，唯一约束 **不并入 `deleted_at`**（唯一 `event_id`）——发件箱要求跨方言严格唯一；若按 `(event_id, deleted_at)` 复合唯一，MySQL / PostgreSQL / SQLite 对 NULL 视作互异，同一 `event_id` 可重复插入、破坏幂等。`deleted_at` / `version` 列随 `BaseModel` 保留但业务不使用。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_outbox_event_id` | 唯一 | `(event_id)` | 事件 ID 全局唯一（幂等键） |
| `idx_sys_outbox_dispatch` | 普通 | `(status, next_retry_at, id)` | 取待投递（按状态 + 到期 + 插入序） |
| `idx_sys_outbox_aggregate` | 普通 | `(aggregate_key, id)` | 同聚合顺序（队首判定） |

- 无物理外键；公共软删除索引 `idx_sys_outbox_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（一库一表；每服务 / 每租户库各自持有）。
- **归档**：暂不归档（保留期内作事件账本可重放）；过期 `delivered` 记录清理随任务调度阶段（登记开放项）。
- **迁移**：随**平台链** `alembic/versions/platform/0003_sys_outbox.py` 与**租户链** `alembic/versions/tenant/0002_sys_outbox.py` 落地（2026-09-23；一套方言无关脚本、四库通用）；命令 `alembic -n alembic:platform upgrade head` / `alembic -n alembic:tenant upgrade head`；SQLite 开发库由启动期自动建表覆盖。表集登记见 `bms_core/db/migration.py`（`PLATFORM_TABLES` / `TENANT_TABLES`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-23 | v1 | 新建表结构（平台链 + 租户链双落；事务性发件箱，随 05_03 迁移落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

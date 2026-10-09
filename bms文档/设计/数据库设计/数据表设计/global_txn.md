# global_txn（跨服务全局事务主记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › global_txn

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_txn`（归属服务 `txn`；`datasource = PLATFORM`，与业务库物理分离） |
| 覆盖模块 | 05-服务间通信与一致性（跨服务事务管理器 TM 账本） |
| 上游依据 | [任务 05_07 详细设计](../../../项目/02_后端基座与服务化地基/任务/05_服务间通信与一致性/05_服务间通信与一致性_07_跨服务事务管理器强一致专项/设计/01_详细设计_07_跨服务事务管理器强一致专项.md) §4；《[架构设计 · 服务间通信与分布式一致性](../../架构设计/37_架构设计_子系统_服务间通信与一致性.md)》「强一致场景处理」节；[需求 05-5](../../../项目/02_后端基座与服务化地基/需求/05_需求_服务间通信与一致性.md#r05-5) |
| ORM 模型 | `bms_txn/models/ledger.py::GlobalTxn`（继承 `BaseModel`） |
| 状态 | 待落库 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[global_txn_branch](global_txn_branch.md)、[global_txn_recovery](global_txn_recovery.md) |

> **基础设施表口径**：TM 是**纯跨库协调基础设施**——**与租户、与业务无关**，任何服务 / 任何业务均可接入；故本表**不含租户列、不分库、不分区**（原「账本按 `tenant` 分区、一次全局事务只允许同一租户」的口径**作废**，见详设 §4 与 §8 第 7 项）。分支目标库以**不透明库键**（`global_txn_branch.db_key`）表达，TM 不作业务解释。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `global_txn_id` | VARCHAR(64) | 否 | 唯一（`uq_global_txn_global_txn_id_deleted_at`） | 全局事务标识（对外业务主键；同时作为 XA `gtrid`，见详设 §3.3 `xid` 规范） |
| `caller_service` | VARCHAR(64) | 否 | `idx_global_txn_state` | 发起方服务键（调用方自报并经服务身份校验） |
| `state` | VARCHAR(24) | 否 | 默认 `active`；`idx_global_txn_state` | 状态机：`active` / `preparing` / `committing` / `committed` / `rolling_back` / `rolled_back` / `heuristic_commit` / `heuristic_rollback` / `heuristic_mixed` |
| `deadline_at` | DATETIME | 否 | — | 提交决定截止时间（UTC）；到期仍未提交 ⇒ 恢复器置回滚 |
| `decided_at` | DATETIME | 是 | — | 提交决定点时间（UTC；落 `committing` 的那一刻，**唯一权威**） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel`；`version` 兼作**行级乐观锁**（并发写冲突即重试） |

> **状态机不变量**：`decided_at` 非空即「已过决定点」——此之前一切失败一律回滚，此之后**只 commit、不再回滚**（详设 §3.1）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_global_txn_global_txn_id_deleted_at` | 唯一 | `(global_txn_id, deleted_at)` | 全局事务标识唯一 |
| `idx_global_txn_state` | 普通 | `(state, deadline_at)` | 恢复器扫描非终态事务（按状态 + 截止时间） |

- 无物理外键；公共软删除索引 `idx_global_txn_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（单库单表；账本集中于 `bms_txn`）。
- **归档**：终态事务（`committed` / `rolled_back`）保留期内供审计与对账，过期清理随运维阶段（登记开放项）。
- **迁移**：随**`txn:platform` 链** `alembic/versions/txn/platform/0001_txn_ledger.py` 落地；命令 `alembic -n alembic:txn:platform upgrade head`。**不建 `tenant` 链**。表集登记见 `bms_core/services/table_registry.py`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-09 | v1 | 新建表结构（跨服务事务管理器 TM 账本主记录；落 `bms_txn` 平台侧独立基础设施库，随 05_07 落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

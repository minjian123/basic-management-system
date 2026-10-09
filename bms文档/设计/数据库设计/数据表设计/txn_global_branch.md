# txn_global_branch（跨服务全局事务分支）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › txn_global_branch

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_txn`（归属服务 `txn`；`datasource = PLATFORM`） |
| 覆盖模块 | 05-服务间通信与一致性（跨服务事务管理器 TM 账本——参与方分支） |
| 上游依据 | [任务 05_07 详细设计](../../../项目/02_后端基座与服务化地基/任务/05_服务间通信与一致性/05_服务间通信与一致性_07_跨服务事务管理器强一致专项/设计/01_详细设计_07_跨服务事务管理器强一致专项.md) §4 / §5；[需求 05-5](../../../项目/02_后端基座与服务化地基/需求/05_需求_服务间通信与一致性.md#r05-5) |
| ORM 模型 | `bms_txn/models/ledger.py::GlobalTxnBranch`（继承 `BaseModel`） |
| 状态 | 待落库 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[txn_global](txn_global.md)、[txn_global_recovery](txn_global_recovery.md) |

> **分支寻址**：`db_key` 为**调用方在 `begin` 时声明的不透明库键**（平台库 / 租户库 / 归档库均可），TM **原样存储与回传、不作业务解释**；参与方按该键经本服务引擎注册表取引擎执行分支（详设 §4）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `global_txn_id` | VARCHAR(64) | 否 | 与 `branch_id` 复合唯一（`uq_txn_global_branch_txn_branch_deleted_at`） | 所属全局事务标识 |
| `branch_id` | VARCHAR(64) | 否 | 同上复合唯一 | 分支标识（租户内唯一；同时作为 XA `bqual`） |
| `service` | VARCHAR(64) | 否 | — | 参与方服务键（分支执行端点的服务身份白名单来源） |
| `db_key` | VARCHAR(128) | 否 | — | **不透明库键**（分支目标库；TM 不解释） |
| `xid` | VARCHAR(160) | 否 | — | XA 事务标识（由 TM 生成，满足 MySQL `XA` xid ≤ 64 字节约束） |
| `state` | VARCHAR(24) | 否 | 默认 `active`；`idx_txn_global_branch_state` | 分支状态机：`active` / `prepared` / `committed` / `rolled_back` / `rejected` |
| `retry_count` | INT | 否 | 默认 0 | TM 驱动重试次数（退避重试，不静默放弃） |
| `last_error` | VARCHAR(512) | 是 | — | 最近一次驱动失败原因（截断） |
| `request_hash` | VARCHAR(64) | 是 | — | 分支执行载荷摘要（**分支级幂等**：同 `xid` 同摘要的重复执行直接返回原结果） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel`；`version` 兼作**行级乐观锁** |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_txn_global_branch_txn_branch_deleted_at` | 唯一 | `(global_txn_id, branch_id, deleted_at)` | 同事务内分支唯一 |
| `idx_txn_global_branch_txn` | 普通 | `(global_txn_id, state)` | 按事务取分支与核验票数 |
| `idx_txn_global_branch_state` | 普通 | `(state, updated_at)` | 恢复器扫描未确认分支 |

- 无物理外键（`global_txn_id` 为逻辑外键，同库）；公共软删除索引 `idx_txn_global_branch_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（单库单表）。
- **归档**：随所属全局事务归档。
- **迁移**：随 **`txn:platform` 链** `alembic/versions/txn/platform/0001_txn_ledger.py` 落地；**不建 `tenant` 链**。表集登记见 `bms_core/services/table_registry.py`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-09 | v1 | 新建表结构（TM 账本分支表；`db_key` 为不透明库键，TM 不感知租户 / 业务；随 05_07 落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

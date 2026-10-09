# txn_global_recovery（跨服务全局事务恢复 / 对账记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › txn_global_recovery

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_txn`（归属服务 `txn`；`datasource = PLATFORM`） |
| 覆盖模块 | 05-服务间通信与一致性（跨服务事务管理器 TM 账本——恢复 / 对账台账） |
| 上游依据 | [任务 05_07 详细设计](../../../项目/02_后端基座与服务化地基/任务/05_服务间通信与一致性/05_服务间通信与一致性_07_跨服务事务管理器强一致专项/设计/01_详细设计_07_跨服务事务管理器强一致专项.md) §4 / §6 / §8 第 6 项；[需求 05-5](../../../项目/02_后端基座与服务化地基/需求/05_需求_服务间通信与一致性.md#r05-5) |
| ORM 模型 | `bms_txn/models/ledger.py::GlobalTxnRecovery`（继承 `BaseModel`） |
| 状态 | 待落库 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[txn_global](txn_global.md)、[txn_global_branch](txn_global_branch.md) |

> **人工处置的硬边界**：处置方（恢复器 / 人）的动作被定义为**依账本提交决定点驱动协议完成**（`drive_commit` / `drive_rollback`）——**不是修改业务数据内容**；全程在本表留痕（详设 §6 硬口径、§8 第 6 项）。人的动作＝**幂等重放 / 驱动协议**，**禁止手工改数据**。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `global_txn_id` | VARCHAR(64) | 否 | `idx_txn_global_recovery_txn` | 被处置的全局事务标识 |
| `branch_id` | VARCHAR(64) | 是 | — | 被处置分支（悬挂 / 启发式定位到具体分支时填写；空 = 整事务级） |
| `detected_at` | DATETIME | 否 | `idx_txn_global_recovery_detected_at` | 发现时刻（UTC） |
| `hung_seconds` | INT | 是 | — | 悬挂时长（秒；非悬挂类为空） |
| `action` | VARCHAR(24) | 否 | — | 处置动作：`drive_commit` / `drive_rollback`（**只驱动协议**） |
| `actor` | VARCHAR(64) | 否 | — | 处置方：`recoverer`（恢复器自动）/ `operator`（`ops/txn_recovery.py` 人工驱动） |
| `handler` | VARCHAR(64) | 是 | — | 人工处置时的操作人标识（自动处置为空） |
| `conclusion` | VARCHAR(255) | 是 | — | 处置结论（成功 / 失败原因；截断） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_txn_global_recovery_txn` | 普通 | `(global_txn_id, id)` | 按事务查处置历史 |
| `idx_txn_global_recovery_detected_at` | 普通 | `(detected_at)` | 处置台账按时间检索 / 保留期清理 |

- 无物理外键；公共软删除索引 `idx_txn_global_recovery_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（单库单表）。
- **归档**：保留期内供审计；过期清理随运维阶段（登记开放项）。
- **迁移**：随 **`txn:platform` 链** `alembic/versions/txn/platform/0001_txn_ledger.py` 落地；**不建 `tenant` 链**。表集登记见 `bms_core/services/table_registry.py`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-09 | v1 | 新建表结构（TM 恢复 / 对账台账；处置动作只驱动协议、禁止改业务数据；随 05_07 落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_recycle_log（回收站清理批次表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_recycle_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 归属业务域 | `recycle`（回收站） |
| 覆盖模块 | 33-回收站（超期软删除数据物理清理留痕） |
| 上游依据 | [需求 07-2](../../../项目/08_通用能力/需求/07_需求_数据生命周期.md#r07-2)、《[概要设计 · 回收站](../../概要设计/32_概要设计_回收站.md)》§2.3 / §4 |
| ORM 模型 | `bms_core/models/platform/recycle.py::SysRecycleLog`（继承 `BaseModel`） |
| 状态 | 待落库（已进 platform 服务租户链） |
| 相关节点 | [33-回收站](../33_数据库设计_回收站.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | ID（清理批次行标识） |
| `batch_key` | VARCHAR(64) | 否 | 与表名、`deleted_at` 复合唯一 | 批次键（同一次清理作业共享，如 `recycle:20261118043000:ab12cd34`） |
| `table_name` | VARCHAR(64) | 否 | 与批次键、`deleted_at` 复合唯一 | 被清理的逻辑表名 |
| `status` | VARCHAR(16) | 否 | 默认 `running` | 状态（`running` / `success` / `failed`） |
| `retention_days` | INT | 否 | — | 本次清理采用的保留天数 |
| `cutoff_at` | DATETIME | 否 | — | 清理截止时刻（UTC；`deleted_at < cutoff_at` 才删） |
| `deleted_count` | INT | 否 | 默认 0 | 本表本批物理删除条数 |
| `cost_time` | INT | 是 | — | 耗时（毫秒） |
| `started_at` | DATETIME | 否 | — | 开始时间（UTC） |
| `finished_at` | DATETIME | 是 | — | 结束时间（UTC） |
| `error_msg` | VARCHAR(512) | 是 | — | 失败摘要（截断 512） |
| `detail` | TEXT | 是 | — | 明细 JSON（批次上限 / 实际批次数 / 备注） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_recycle_log_batch_table` | 唯一 | `(batch_key, table_name, deleted_at)` | 同一批次同一表只一行（重试 / 并发幂等） |
| `idx_sys_recycle_log_table_started` | 普通 | `(table_name, started_at)` | 按表看清理历史 |
| `idx_sys_recycle_log_status` | 普通 | `(status)` | `running` 超时回收 / 失败巡检 |

- 无物理外键；`table_name` 为逻辑表名，不指向具体表。
- 公共软删除索引 `idx_sys_recycle_log_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（每个租户每日每表至多一行，量级小）。
- **归档**：本表不归档（清理留痕，随租户库备份保留）。
- **保留**：不设硬删入口；清理记录长期保留。
- **建表**：进入 platform 服务**租户链**，由启动期自动建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-18 | v1 | 新建（13_01 回收站）：超期软删除数据物理清理的逐表批次留痕 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_archive_policy（归档策略表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_archive_policy

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 归属业务域 | `archive`（归档管理） |
| 覆盖模块 | 31-归档管理（策略配置） |
| 上游依据 | [需求 07-1](../../../项目/08_通用能力/需求/07_需求_数据生命周期.md#r07-1)、《[概要设计 · 归档管理](../../概要设计/30_概要设计_归档管理.md)》§2 / §4、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》「回收站机制」节 |
| ORM 模型 | `bms_core/models/platform/archive.py::SysArchivePolicy`（继承 `BaseModel`） |
| 状态 | 已设计（随 14_01 转 `enabled` 进平台链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [31-归档管理](../31_数据库设计_归档管理.md)、[sys_archive_log](sys_archive_log.md)、[sys_archive_record](sys_archive_record.md)、[sys_archive_chain_tail](sys_archive_chain_tail.md) |

> **落库位置口径例外**：《概要设计 · 归档管理》§4 原文写「策略 / 执行记录落租户库」，实际按 14_01 定稿落**平台库**——归档是平台治理动作，一条策略覆盖全租户（归档行仍带 `tenant_id`），与审计分片台账同库便于链校验与统一调度。差异已回写概要设计节点。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | ID（策略标识） |
| `table_name` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 逻辑表名（须为平台库已登记表；审计分片表取逻辑名） |
| `time_field` | VARCHAR(64) | 否 | — | 归档判定时间字段（审计分片表固定 `occurred_at`） |
| `threshold_days` | INT | 否 | 默认 90 | 阈值天数：`time_field` 早于「当前 - 阈值」即达归档条件 |
| `retention_days` | INT | 否 | 默认 180 | 归档库保留天数：满期后冷化到对象存储；`target=minio` 时不参与 |
| `target` | VARCHAR(16) | 否 | 默认 `archive_db` | 归档目标（`archive_db` 两段式 / `minio` 直冷） |
| `batch_size` | INT | 否 | 默认 1000 | 单批迁移条数（1 ~ `[archive].max_batch_rows`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`；停用策略不执行、可删除） |
| `require_chain` | BOOLEAN | 否 | 默认 false | 归档前强制哈希链校验（审计分片表强制为 true，不可关闭） |
| `remark` | VARCHAR(256) | 是 | — | 备注 |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_archive_policy_table` | 唯一 | `(table_name, deleted_at)` | 同表仅一条在用策略（软删后可重建） |
| `idx_sys_archive_policy_status` | 普通 | `(status)` | 调度扫描启停策略 |

- 无物理外键；`table_name` 指向表归属登记的逻辑表名（同库 / 跨库均有，逻辑引用）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（行数量级等于可归档表数）。
- **归档**：本表不归档（治理配置，随平台库备份）。
- **建表**：进入 platform 服务**平台链**，由启动期建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（14_01 归档管理）：策略表落平台库，支撑全表可配归档 | minjian |

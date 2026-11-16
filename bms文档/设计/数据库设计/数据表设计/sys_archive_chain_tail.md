# sys_archive_chain_tail（归档链尾表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_archive_chain_tail

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 归属业务域 | `archive`（归档管理） |
| 覆盖模块 | 31-归档管理（审计分片整月归档后的链尾留存） |
| 上游依据 | [需求 07-1](../../../项目/08_通用能力/需求/07_需求_数据生命周期.md#r07-1)、《[概要设计 · 归档管理](../../概要设计/30_概要设计_归档管理.md)》§2.2「哈希链随归档导出」、《[架构设计 · 审计哈希链](../../架构设计/19_架构设计_子系统_审计哈希链.md)》§3 / §5 / §6 |
| ORM 模型 | `bms_core/models/platform/archive.py::SysArchiveChainTail`（继承 `BaseModel`） |
| 状态 | 已设计（随 14_01 转 `enabled` 进平台链） |
| 相关节点 | [31-归档管理](../31_数据库设计_归档管理.md)、[sys_audit_shard](sys_audit_shard.md)、[sys_archive_log](sys_archive_log.md) |

> **存在理由**：审计分片表整月归档后会**删除物理分片表**。后续月份的链校验需要「上一月各租户链尾哈希」，物理表已不在，必须把链头 / 链尾落到台账。本表按 `(日志类型, 月份, 租户键)` 一行，删表前写入、校验器只读。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | ID（链尾记录标识） |
| `log_type` | VARCHAR(16) | 否 | 与 `shard_month` / `tenant_key` 复合唯一 | 日志类型（`operation` / `login` / `data_audit`） |
| `shard_month` | CHAR(6) | 否 | 同上 | 分片月份（`yyyyMM`） |
| `tenant_key` | VARCHAR(32) | 否 | 同上 | 链所属租户键（雪花 id 十进制字符串；平台全局链为 `global`） |
| `first_prev_hash` | CHAR(64) | 否 | — | 该月该租户首条记录的 `prev_hash`（链头，供独立校验） |
| `last_record_hash` | CHAR(64) | 否 | — | 该月该租户末条记录的 `record_hash`（链尾，后续月份校验依据） |
| `record_count` | INT | 否 | 默认 0 | 该月该租户记录条数（导出清单核对） |
| `archive_log_id` | DECIMAL(38,0) | 是 | — | 对应归档批次（逻辑外键 `sys_archive_log.id`） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_archive_chain_tail_month` | 唯一 | `(log_type, shard_month, tenant_key)` | 一个月一租户一条链尾（重复归档幂等） |
| `idx_sys_archive_chain_tail_lookup` | 普通 | `(log_type, shard_month)` | 校验器按类型 + 月份取链尾 |

- 无物理外键；`archive_log_id` 为逻辑外键（`sys_archive_log.id`，同库）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（行数 = 日志类型 × 归档月份 × 活跃租户数）。
- **归档**：本表不归档（链校验依据，随平台库长期保留）。
- **建表**：进入 platform 服务**平台链**，由启动期建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（14_01 归档管理）：审计分片删表后保留按租户的链头 / 链尾，支撑跨归档链校验 | minjian |

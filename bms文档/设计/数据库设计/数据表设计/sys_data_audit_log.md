# sys_data_audit_log（字段级变更审计表，按月分片）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_data_audit_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（平台治理数据集中存放；不按租户分库） |
| 覆盖模块 | 29-审计合规 |
| 上游依据 | [需求 05-2](../../../项目/08_通用能力/需求/05_需求_日志与审计.md#r05-2)、《[概要设计 · 审计合规](../../概要设计/28_概要设计_审计合规.md)》§2 / §4、《[架构设计 · 审计哈希链](../../架构设计/19_架构设计_子系统_审计哈希链.md)》§2 / §3 |
| ORM 模型 | 无实体模型：物理表按月分片、由运行期 `ensure_shard` 以 SQLAlchemy Core 建表；结构声明见 `bms_platform/domains/log/schema.py` |
| 状态 | 已设计 |
| 相关节点 | [29-审计合规](../29_数据库设计_审计合规.md)、[sys_audit_shard](sys_audit_shard.md) |

## 2. 字段 <a id="fields"></a>

审计数据只追加、物理保留，**无软删除 / 乐观锁 / 更新审计字段**（不继承 `BaseModel` 的公共列）。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键（同分片内按升序成链） |
| `event_id` | VARCHAR(64) | 否 | 唯一索引 | 事件幂等键（消费去重兜底） |
| `tenant_id` | DECIMAL(38,0) | 是 | `idx_sys_data_audit_log_tenant_id_id` 首列 | 租户主键（无租户事件为空；链按租户分条） |
| `table_name` | VARCHAR(64) | 否 | `idx_sys_data_audit_log_table_record` 首列 | 被审计的逻辑表名 |
| `record_id` | DECIMAL(38,0) | 是 | 同上 | 被审计记录主键（雪花 ID；无主键的批量场景可空） |
| `field` | VARCHAR(64) | 否 | — | 变更字段名（列名；显式留痕时为判定要素名） |
| `old_value` | TEXT | 是 | — | 变更前值（JSON 文本；敏感列 `***`；超长截断；新增为 null） |
| `new_value` | TEXT | 是 | — | 变更后值（JSON 文本；敏感列 `***`；超长截断；删除为 null） |
| `operator_id` | DECIMAL(38,0) | 是 | `idx_sys_data_audit_log_operator_occurred` 首列 | 操作人主键（作业 / 内部通道为空） |
| `domain_key` | VARCHAR(64) | 否 | — | 业务域归属（表归属派生；未登记为 `unknown`） |
| `occurred_at` | DATETIME | 否 | `idx_sys_data_audit_log_occurred_at` | 事件发生时间（UTC；查询与展示口径） |
| `prev_hash` | VARCHAR(64) | 否 | — | 前一条记录哈希（首条为 `GENESIS_HASH` 或上月同租户末条） |
| `record_hash` | VARCHAR(64) | 否 | — | 本条记录哈希（`SHA256(prev_hash + 规范化记录)`） |
| `created_at` | DATETIME | 否 | — | 写入时间（UTC；分片键 = 该时刻所在月） |

> 值列口径：字符串原样、数字转字符串、时间按 ISO8601（UTC）、布尔按 `true` / `false`、其余按 `str()`；**空串与 null 语义不同**（前者是「值被改为空串」，后者是「无此端值」）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_data_audit_log_event_id` | 唯一 | `(event_id)` | 消费幂等兜底 |
| `idx_sys_data_audit_log_tenant_id_id` | 普通 | `(tenant_id, id)` | 同租户链尾查找 / 跨月衔接 |
| `idx_sys_data_audit_log_table_record` | 普通 | `(table_name, record_id)` | 「这条记录被谁改过哪些字段」 |
| `idx_sys_data_audit_log_operator_occurred` | 普通 | `(operator_id, occurred_at)` | 按操作人 + 时间范围 |
| `idx_sys_data_audit_log_occurred_at` | 普通 | `(occurred_at)` | 时间范围筛选与 90 天归档扫描 |

- 无物理外键（`tenant_id` / `record_id` / `operator_id` 为逻辑外键）。
- 索引名含物理表名（分片后缀不同，索引名随分片生成，互不冲突）；每表索引数 ≤5。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：按月分片，物理表名 `sys_data_audit_log_{yyyyMM}`，逻辑表名不带后缀；分片键 = **写入时刻**（消费时刻），事件时间另存 `occurred_at`。
- **建表**：运行期 `ensure_shard` 幂等建表（四方言、`checkfirst`）+ 分片台账 `sys_audit_shard`（`log_type=data_audit`）登记；启动预热当月 / 次月，内置任务 `precreate_shard_tables` 每月预创建。不进入 `Base.metadata` 与迁移链（`sys_table_ownership.status = planned`）。
- **归档**：热表保留 90 天；归档前经链校验，两段式归档（归档库 → 对象存储）归 14_01。归档清单从 `sys_audit_shard` 取。
- **只追加**：不提供更新 / 删除入口；合规销毁留销毁日志（14_01）。
- **覆盖边界**：只覆盖经 ORM 的写入；不经 ORM 的直连 SQL 不产生审计（口径显式声明）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（06_02 字段级变更审计与哈希链）：按月分片 + 哈希链 + 域归属；值列 JSON + 敏感脱敏 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_archive_record（归档数据行表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_archive_record

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 归档库 `bms_archive`（`datasource=archive`，不服务化，统一收存各租户归档数据） |
| 归属业务域 | `archive`（归档管理） |
| 覆盖模块 | 31-归档管理（第一段归档 / 只读查询） |
| 上游依据 | [需求 07-1](../../../项目/08_通用能力/需求/07_需求_数据生命周期.md#r07-1)、《[概要设计 · 归档管理](../../概要设计/30_概要设计_归档管理.md)》§4、《[架构设计 · 数据架构](../../架构设计/07_架构设计_数据架构.md)》「数据分布」节 |
| ORM 模型 | `bms_core/models/platform/archive.py::SysArchiveRecord`（追加型模型，不继承 `BaseModel`） |
| 状态 | 待落库（已进归档库建表集） |
| 相关节点 | [31-归档管理](../31_数据库设计_归档管理.md)、[sys_archive_policy](sys_archive_policy.md)、[sys_archive_log](sys_archive_log.md) |

> **存储模型口径**：归档库以**通用行表**承载，不按源表镜像建表——`payload` 存源行完整字段 JSON，`tenant_id` + `source_table` + `source_id` 提供检索维度，避免跨四库动态 DDL 与类型映射风险；查询粒度按租户 / 源表 / 时间 / 源主键（与概要设计页面筛选口径一致）。

## 2. 字段 <a id="fields"></a>

本表为**只追加**数据表，不继承公共基类（无软删除 / 无乐观锁），审计列只保留写入时刻。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | ID（归档行标识） |
| `tenant_id` | DECIMAL(38,0) | 是 | — | 租户主键（雪花 id；平台全局链数据为空） |
| `source_table` | VARCHAR(64) | 否 | 与 `source_id` 复合唯一 | 源逻辑表名 |
| `source_id` | VARCHAR(64) | 否 | 同上 | 源行主键（雪花 id 十进制字符串） |
| `source_month` | CHAR(6) | 是 | — | 源分片月份（`yyyyMM`；审计分片表有值，普通表为空） |
| `source_datasource` | VARCHAR(16) | 否 | 默认 `platform` | 源库类别（本期恒 `platform`，为后续租户库 / 产品库归档预留） |
| `policy_id` | DECIMAL(38,0) | 否 | — | 归档策略 ID（逻辑外键 `sys_archive_policy.id`，跨库不建物理外键） |
| `batch_id` | DECIMAL(38,0) | 否 | — | 归档批次 ID（逻辑外键 `sys_archive_log.id`，跨库） |
| `payload` | TEXT | 否 | — | 源行完整字段 JSON（时间 ISO8601、金额字符串、空值 `null`） |
| `archived_at` | DATETIME | 否 | — | 归档时刻（UTC；冷化保留期判定依据） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_archive_record_source` | 唯一 | `(source_table, source_id)` | 同一源行只归档一次（重复执行不重复归档的最后防线） |
| `idx_sys_archive_record_tenant` | 普通 | `(tenant_id, source_table, archived_at)` | 租户维度只读查询 / 冷化扫描 |
| `idx_sys_archive_record_policy` | 普通 | `(policy_id, archived_at)` | 按策略执行第二段冷化 |
| `idx_sys_archive_record_time` | 普通 | `(source_table, archived_at)` | 按源表 + 时间筛选 |

- 无物理外键；`policy_id` / `batch_id` 为跨库逻辑外键（`sys_archive_policy.id` / `sys_archive_log.id`）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一期按单表 + 索引承载；量级超阈值时按 `archived_at` 再评估分区 / 分表）。
- **归档**：本表即归档数据的在线层；满 `retention_days` 后由第二段冷化到对象存储并从本表删除（冷化文件为 NDJSON + gzip）。软删除与物理清理不适用（数据到期只走冷化 / 销毁）。
- **建表**：登记 `datasource=archive`，进入归档库建表集（`archive` 库键），由启动期建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（14_01 归档管理）：通用归档行表，承载任意平台库表的两段式归档 | minjian |

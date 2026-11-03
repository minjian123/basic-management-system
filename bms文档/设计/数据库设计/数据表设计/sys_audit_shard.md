# sys_audit_shard（审计分片台账表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_audit_shard

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform` |
| 覆盖模块 | 12-操作日志 / 13-登录日志（分片台账） |
| 上游依据 | [需求 05-1](../../../项目/08_通用能力/需求/05_需求_日志与审计.md#r05-1)、《[概要设计 · 操作日志](../../概要设计/11_概要设计_操作日志.md)》§4.2「新月份分片表提前创建」 |
| ORM 模型 | `bms_core/models/platform/log.py::SysAuditShard`（继承 `BaseModel`） |
| 状态 | 已设计 |
| 相关节点 | [sys_operation_log](sys_operation_log.md)、[sys_login_log](sys_login_log.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表只列业务字段。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `log_type` | VARCHAR(16) | 否 | 与 `shard_month` 复合唯一 | 日志类型（`operation` / `login`；后续可扩 `data_audit` / `open`） |
| `shard_month` | CHAR(6) | 否 | 同上 | 分片月份（`yyyyMM`） |
| `physical_table` | VARCHAR(64) | 否 | — | 物理表名（如 `sys_operation_log_202611`） |
| `status` | VARCHAR(16) | 否 | 默认 `active` | 状态（`active` / `archived`；归档状态由 14_01 更新） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_audit_shard_type_month` | 唯一 | `(log_type, shard_month, deleted_at)` | 一类日志一个月一条台账（幂等建表依据） |

- 无物理外键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：本表不分片（每类日志每月一行，量级极小）。
- **归档**：台账随日志保留期保留；14_01 归档分片后把 `status` 置 `archived`（保留行，供审计追溯）。
- **建表**：进入 platform 服务**平台链**，由启动期建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-03 | v1 | 新建（06_01）：审计分片台账，支撑运行期建表 / 查询路由 / 预创建 / 归档清单 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_operation_log（操作日志表，按月分片）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_operation_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（平台治理数据集中存放；不按租户分库） |
| 覆盖模块 | 12-操作日志 |
| 上游依据 | [需求 05-1](../../../项目/08_通用能力/需求/05_需求_日志与审计.md#r05-1)、《[概要设计 · 操作日志](../../概要设计/11_概要设计_操作日志.md)》§4、《[架构设计 · 审计哈希链](../../架构设计/19_架构设计_子系统_审计哈希链.md)》§3 |
| ORM 模型 | 无实体模型：物理表按月分片、由运行期 `ensure_shard` 以 SQLAlchemy Core 建表；结构声明见 `bms_platform/domains/log/schema.py` |
| 状态 | 已设计 |
| 相关节点 | [12-操作日志](../12_数据库设计_操作日志.md)、[sys_audit_shard](sys_audit_shard.md) |

## 2. 字段 <a id="fields"></a>

审计数据只追加、物理保留，**无软删除 / 乐观锁 / 更新审计字段**（不继承 `BaseModel` 的公共列）。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键（同分片内按升序成链） |
| `event_id` | VARCHAR(64) | 否 | 唯一索引 | 事件幂等键（消费去重兜底） |
| `tenant_id` | DECIMAL(38,0) | 是 | `idx_sys_operation_log_tenant_id_id` 首列 | 租户主键（无租户事件为空；链按租户分条） |
| `user_id` | DECIMAL(38,0) | 是 | `idx_sys_operation_log_user_id_occurred_at` 首列 | 操作人主键（未登录 / 系统内部为空） |
| `username` | VARCHAR(64) | 是 | — | 操作账号快照（避免跨服务反查） |
| `module` | VARCHAR(32) | 否 | `idx_sys_operation_log_module_action` 首列 | 模块（取权限码业务段，缺省路径首段） |
| `action` | VARCHAR(64) | 否 | 同上 | 动作（权限码 `业务:动作`；无权限码端点回落方法动词） |
| `method` | VARCHAR(8) | 否 | — | HTTP 方法 |
| `path` | VARCHAR(512) | 否 | — | 请求路径（不含查询串） |
| `query_params` | TEXT | 是 | — | 查询串原文（已脱敏） |
| `params` | TEXT | 是 | — | 请求体参数 JSON（已脱敏；非 JSON / 超限为空） |
| `ip` | VARCHAR(64) | 是 | — | 客户端 IP（`X-Forwarded-For` 首值兜底连接地址） |
| `user_agent` | VARCHAR(512) | 是 | — | User-Agent（截断） |
| `cost_time` | INT | 是 | — | 耗时（毫秒） |
| `status` | INT | 否 | — | HTTP 状态码 |
| `error_msg` | VARCHAR(512) | 是 | — | 错误摘要（未捕获异常原文 / `HTTP {status}`） |
| `occurred_at` | DATETIME | 否 | `idx_sys_operation_log_occurred_at` | 事件发生时间（UTC；查询与展示口径） |
| `prev_hash` | VARCHAR(64) | 否 | — | 前一条记录哈希（首条为 `GENESIS_HASH` 或上月同租户末条） |
| `record_hash` | VARCHAR(64) | 否 | — | 本条记录哈希（`SHA256(prev_hash + 规范化记录)`） |
| `created_at` | DATETIME | 否 | — | 写入时间（UTC；分片键 = 该时刻所在月） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_operation_log_event_id` | 唯一 | `(event_id)` | 消费幂等兜底 |
| `idx_sys_operation_log_tenant_id_id` | 普通 | `(tenant_id, id)` | 同租户链尾查找 / 跨月衔接 |
| `idx_sys_operation_log_user_id_occurred_at` | 普通 | `(user_id, occurred_at)` | 按用户 + 时间范围筛选 |
| `idx_sys_operation_log_module_action` | 普通 | `(module, action)` | 按模块 / 动作筛选 |
| `idx_sys_operation_log_occurred_at` | 普通 | `(occurred_at)` | 时间范围筛选与 90 天归档扫描 |

- 无物理外键（`tenant_id` / `user_id` 为逻辑外键）。
- 索引名含物理表名（分片后缀不同，索引名随分片生成，互不冲突）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：按月分片，物理表名 `sys_operation_log_{yyyyMM}`，逻辑表名 `sys_operation_log` 不带后缀；分片键 = **写入时刻**（消费时刻），事件时间另存 `occurred_at`（避免延迟事件插入旧月破坏跨月链）。
- **建表**：运行期 `ensure_shard` 幂等建表（四方言、`checkfirst`）+ 分片台账 `sys_audit_shard` 登记；启动预热当月 / 次月，内置任务 `precreate_shard_tables` 每月 25 日预创建下月。不进入 `Base.metadata` 与迁移链（`sys_table_ownership.status = planned`）。
- **归档**：热表保留 90 天；归档前经链校验，两段式归档（归档库 → 对象存储）归 14_01。归档清单从 `sys_audit_shard` 取。
- **只追加**：不提供更新 / 删除入口；合规销毁留销毁日志（14_01）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-03 | v1 | 新建（06_01 操作日志与登录日志）：按月分片 + 哈希链 + 分片台账；`params` 脱敏后落库 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

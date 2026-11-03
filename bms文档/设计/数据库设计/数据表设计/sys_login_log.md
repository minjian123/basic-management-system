# sys_login_log（登录日志表，按月分片）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_login_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（平台治理数据集中存放；不按租户分库） |
| 覆盖模块 | 13-登录日志 |
| 上游依据 | [需求 05-1](../../../项目/08_通用能力/需求/05_需求_日志与审计.md#r05-1)、《[概要设计 · 登录日志](../../概要设计/12_概要设计_登录日志.md)》§4、《[架构设计 · 审计哈希链](../../架构设计/19_架构设计_子系统_审计哈希链.md)》§3 |
| ORM 模型 | 无实体模型：物理表按月分片、由运行期 `ensure_shard` 以 SQLAlchemy Core 建表；结构声明见 `bms_platform/domains/log/schema.py` |
| 状态 | 已设计 |
| 相关节点 | [13-登录日志](../13_数据库设计_登录日志.md)、[sys_audit_shard](sys_audit_shard.md) |

## 2. 字段 <a id="fields"></a>

审计数据只追加、物理保留，**无软删除 / 乐观锁 / 更新审计字段**（不继承 `BaseModel` 的公共列）。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键（同分片内按升序成链） |
| `event_id` | VARCHAR(64) | 否 | 唯一索引 | 事件幂等键（消费去重兜底） |
| `tenant_id` | DECIMAL(38,0) | 是 | `idx_sys_login_log_tenant_id_id` 首列 | 租户主键（链按租户分条） |
| `user_id` | DECIMAL(38,0) | 是 | — | 命中用户主键（账号不存在 / 校验失败为空） |
| `username` | VARCHAR(64) | 否 | `idx_sys_login_log_username_occurred_at` 首列 | 登录名（明文记录；密码不落日志） |
| `ip` | VARCHAR(64) | 是 | `idx_sys_login_log_ip` | 客户端 IP |
| `user_agent` | VARCHAR(512) | 是 | — | User-Agent（截断） |
| `status` | VARCHAR(16) | 否 | `idx_sys_login_log_status_occurred_at` 首列 | 结果（`success` / `failed`） |
| `fail_reason` | VARCHAR(32) | 是 | — | 失败原因（`rate_limited` / `captcha_invalid` / `account_locked` / `account_disabled` / `bad_credentials` / `backend_unavailable` / `internal_error`；成功为空） |
| `occurred_at` | DATETIME | 否 | `idx_sys_login_log_occurred_at` | 事件发生时间（UTC） |
| `prev_hash` | VARCHAR(64) | 否 | — | 前一条记录哈希 |
| `record_hash` | VARCHAR(64) | 否 | — | 本条记录哈希 |
| `created_at` | DATETIME | 否 | — | 写入时间（UTC；分片键） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_login_log_event_id` | 唯一 | `(event_id)` | 消费幂等兜底 |
| `idx_sys_login_log_tenant_id_id` | 普通 | `(tenant_id, id)` | 同租户链尾查找 / 跨月衔接 |
| `idx_sys_login_log_username_occurred_at` | 普通 | `(username, occurred_at)` | 按用户名 + 时间范围筛选 |
| `idx_sys_login_log_status_occurred_at` | 普通 | `(status, occurred_at)` | 按结果筛选 |
| `idx_sys_login_log_ip` | 普通 | `(ip)` | 按来源 IP 检索（安全排查） |
| `idx_sys_login_log_occurred_at` | 普通 | `(occurred_at)` | 时间范围与归档扫描 |

- 无物理外键（`tenant_id` / `user_id` 为逻辑外键）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：物理表名 `sys_login_log_{yyyyMM}`；分片键 = 写入时刻；`occurred_at` 供筛选。
- **建表**：同 `sys_operation_log`（运行期 `ensure_shard` + 台账 + 预创建任务；`status = planned`，不进迁移链）。
- **归档**：90 天热表，归档前链校验，两段式归档归 14_01。
- **与锁定联动**：本表只记事实；`fail_limit` 锁定判定仍由认证域 + `sys_account_lock` 执行。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-03 | v1 | 新建（06_01 操作日志与登录日志）：按月分片 + 哈希链；失败原因枚举登记 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

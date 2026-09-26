# sys_session（会话记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_session

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | identity 服务租户库 `bms_identity_{code}`（归属服务 `identity`） |
| 覆盖模块 | 15-会话管理 |
| 上游依据 | [需求 01-3](../../../项目/06_认证与安全/需求/01_需求_认证与会话.md#r01-3)、《概要设计 · 会话管理》「数据模型与表设计」节 |
| ORM 模型 | `bms_identity/models/session.py::SysSession`（继承 `BaseModel`） |
| 状态 | 已落库（`identity:tenant` 链迁移 `0001_sys_session`，2026-09-26） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 14-会话管理](../../概要设计/14_概要设计_会话管理.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键（= 会话 id） |
| `session_id` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 会话 id（= JWT `jti`；与 `id` 同值；Redis 标记键名依据） |
| `user_id` | BIGINT | 否 | — | 用户 ID（跨服务逻辑外键 → org 服务 `sys_user.id`） |
| `refresh_token_hash` | VARCHAR(128) | 否 | — | refresh token 哈希（SHA-256 hex；不落原始值） |
| `device` | VARCHAR(255) | 是 | — | 设备标识（User-Agent 摘要） |
| `ip` | VARCHAR(64) | 是 | — | 登录 IP |
| `login_at` | DATETIME | 否 | — | 登录时间（UTC） |
| `expires_at` | DATETIME | 否 | — | refresh 过期时间（UTC），与 Redis 标记 TTL 对齐 |
| `revoked_at` | DATETIME | 是 | — | 撤销时间（UTC；NULL=有效；登出 / 踢出 / 超限作废写入） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_session_session_id_deleted_at` | 唯一 | `(session_id, deleted_at)` | 会话 id 唯一（软删除后可复用） |
| `idx_sys_session_user_id` | 普通 | `(user_id)` | 在线会话查询主路径（`user_id + revoked_at IS NULL`；01_04） |

- 无物理外键；`user_id` 指向 org 服务 `sys_user.id`（跨服务逻辑外键，只持值）。
- 运行时活跃标记另落 Redis `bms:{租户}:sess:{session_id}`（TTL 与 refresh 对齐）；本表为持久事实源。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；按用户数 × 并发会话数线性增长）。
- **归档**：不归档（历史会话行保留供审计，随日志归档策略处理，不物理删除业务外数据）。
- **迁移**：随 **`identity:tenant` 链** Alembic 迁移落地（`alembic/versions/identity/tenant/0001_sys_session.py`，2026-09-26 已落库；命令 `alembic -n alembic:identity:tenant upgrade head`）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-26 | v1 | 新建表结构（identity 服务租户库；随 01_03 落库迁移 `0001_sys_session`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

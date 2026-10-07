# sys_account_lock（账号锁定记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_account_lock

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`，与 `sys_user` 同库）；**02_05 由 org 服务租户库迁入** |
| 覆盖模块 | 03-用户管理（账号锁定 / 解锁记录；锁定类型与用户状态一致） |
| 上游依据 | [需求 03-7](../../../项目/06_认证与安全/需求/03_需求_验证码与账号治理.md#r03-7)、《[概要设计 · 用户管理](../../概要设计/03_概要设计_用户管理.md)》「核心表」节、《[概要设计 · 会话管理](../../概要设计/14_概要设计_会话管理.md)》、《[架构设计 · 认证与会话](../../架构设计/14_架构设计_子系统_认证与会话.md)》§5、[需求 07-10](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-10) |
| ORM 模型 | `bms_platform/models/user.py::SysAccountLock`（继承 `BaseModel`；登记于 `bms_platform/models/__init__.py::MODEL_MODULES`） |
| 状态 | 已落库（`platform:tenant` 链迁移 `0008_user_tables`，2026-10-07；原 `org:tenant` 链 `0002_password_policy_and_account_lock`（建表）/ `0004_sys_account_lock_expire`（补列）保留为历史，`0006_drop_user_tables` 删表） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 03-用户管理](../../概要设计/03_概要设计_用户管理.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `user_id` | BIGINT | 否 | — | 用户主键（逻辑外键 `sys_user.id`；**同库**、只持值、不建物理外键） |
| `lock_type` | VARCHAR(16) | 否 | — | 锁定类型（`fail_limit` / `inactive` / `manual`） |
| `reason` | VARCHAR(255) | 是 | — | 锁定原因 |
| `locked_at` | DATETIME | 否 | — | 锁定时间（UTC） |
| `locked_by` | BIGINT | 是 | — | 锁定操作人（`inactive` / `fail_limit` 系统触发为 NULL；`manual` 为操作人） |
| `expire_at` | DATETIME | 是 | — | 锁定到期时间（UTC；`fail_limit` = 锁定时间 + 限流窗口；`inactive` / `manual` = NULL 表示需手动解锁） |
| `unlock_at` | DATETIME | 是 | — | 解锁时间（UTC；NULL=未解锁） |
| `unlock_by` | BIGINT | 是 | — | 解锁操作人（手动解锁为操作人；自动解锁为 NULL） |
| `unlock_mode` | VARCHAR(16) | 是 | — | 解锁方式（`manual` 手动 / `auto` 到期自动；NULL=未解锁） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_account_lock_user_locked` | 普通 | `(user_id, locked_at)` | 按用户查锁定历史 / 锁定时间排序 |
| `idx_sys_account_lock_user_unlock` | 普通 | `(user_id, unlock_at)` | 按用户查活跃锁（`unlock_at IS NULL`） |
| `idx_sys_account_lock_unlock_by` | 普通 | `(unlock_by)` | 解锁记录按操作人查询（概要 14 §5） |

- 无物理外键；`user_id` 为逻辑外键指向同库 `sys_user.id`。
- 无唯一约束：同一用户可有多条历史锁定记录（活跃性以 `unlock_at IS NULL` 与 `expire_at` 判定）；并发 / 幂等由服务层保证。
- 活跃锁判定：`unlock_at IS NULL AND (expire_at IS NULL OR expire_at > now)`——`fail_limit` 到期即视为非生效，`inactive` / `manual`（`expire_at=NULL`）须手动解锁。
- 公共软删除索引 `idx_sys_account_lock_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在本表重复列出。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；按锁定事件线性增长）。
- **归档**：解锁记录保留 90 天后随审计归档（归后续审计归档策略）。
- **迁移**：随 **`platform:tenant` 链** Alembic 迁移落地（建表 `0008_user_tables`，2026-10-07）；命令 `alembic -n alembic:platform:tenant upgrade head`；**已部署环境迁移顺序**为「platform 建表 → `ops/migrate_user_tables.py` 搬数据 → `org:tenant` 链 `0006_drop_user_tables` 删表」；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（org 服务租户库；随 `03_05` 落 `org:tenant` 链迁移 `0002_password_policy_and_account_lock`） | minjian |
| 2026-09-28 | v2 | 补 `expire_at`（锁定期限）/ `unlock_mode`（解锁方式）两列，随 `03_07` 落 `org:tenant` 链迁移 `0004_sys_account_lock_expire` | minjian |
| 2026-10-07 | v3 | **归属库迁移**：org 服务租户库 → **platform 服务租户库**（随 02_05 落 `platform:tenant` 链 `0008_user_tables`；字段 / 索引 / 约束不变） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

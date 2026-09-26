# sys_user（用户最小模型）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | org 服务租户库 `bms_org_{code}`（归属服务 `org`） |
| 覆盖模块 | 03-用户管理（本表只承载本地登录所需最小字段；完整用户档案随用户管理阶段扩展） |
| 上游依据 | [需求 01-3](../../../项目/06_认证与安全/需求/01_需求_认证与会话.md#r01-3)、《架构设计 · 认证与会话》「密码与账号策略」节 |
| ORM 模型 | `bms_org/models/user.py::SysUser`（继承 `BaseModel`） |
| 状态 | 已落库（`org:tenant` 链迁移 `0001_sys_user`，2026-09-26） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[架构 14-认证与会话](../../架构设计/14_架构设计_子系统_认证与会话.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `username` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 登录账号（唯一；软删除后可复用） |
| `password_hash` | VARCHAR(255) | 否 | — | 口令哈希（PBKDF2 自描述串） |
| `name` | VARCHAR(128) | 否 | — | 用户昵称 / 显示名 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） |
| `failed_count` | INT | 否 | 默认 0 | 连续登录失败次数 |
| `locked_until` | DATETIME | 是 | — | 锁定到期时间（UTC；NULL=未锁） |
| `pwd_changed_at` | DATETIME | 是 | — | 密码最近变更时间（UTC） |
| `pwd_history` | TEXT | 是 | — | 历史密码哈希（JSON 数组，仅应用侧读写；不参与库内检索，故用 TEXT 取最大跨方言安全） |
| `last_login_at` | DATETIME | 是 | — | 最近登录时间（UTC） |
| `locale` | VARCHAR(16) | 是 | — | 语言偏好（如 `zh-cn`） |
| `timezone` | VARCHAR(64) | 是 | — | 时区偏好（如 `Asia/Shanghai`） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_username_deleted_at` | 唯一 | `(username, deleted_at)` | 登录账号唯一（软删除后可复用） |

- 无物理外键；`sys_session.user_id` 为跨服务逻辑外键指向本表 `id`（identity 服务只持值，不建物理外键、不直连本表）。
- 登录以 `username` 等值查询为主路径，复合唯一索引已覆盖，不另建普通索引。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；按用户数线性增长）。
- **归档**：不归档（用户主数据生命周期数据）。
- **迁移**：随 **`org:tenant` 链** Alembic 迁移落地（`alembic/versions/org/tenant/0001_sys_user.py`，2026-09-26 已落库；命令 `alembic -n alembic:org:tenant upgrade head`，或经 `ops/migrate_tenants.py` 批量）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-26 | v1 | 新建表结构（org 服务租户库；随 01_03 落库迁移 `0001_sys_user`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

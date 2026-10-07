# sys_user_tenant（用户↔租户可达关系）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user_tenant

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_tenant`（归属服务 `tenant`，与 `sys_tenant` 同库） |
| 覆盖模块 | 26-租户管理（租户自助） |
| 上游依据 | [需求 11-1](../../../项目/06_认证与安全/需求/11_需求_租户自助与用户租户关系.md#r11-1)、《架构设计 · 多租户路由》「租户自助」节、《架构设计 · 数据架构》「数据分布」节 |
| ORM 模型 | `bms_tenant/models/user_tenant.py::SysUserTenant`（继承 `BaseModel`） |
| 状态 | 待落库（`tenant:platform` 链迁移 `0006_sys_user_tenant`，2026-10-04 生成；真库执行随部署窗口） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_tenant](sys_tenant.md)、[架构 12-多租户路由](../../架构设计/12_架构设计_子系统_多租户路由.md) |

- **语义**：一行 = 「**某租户（`tenant_id`，用户归属租户，即用户登录 / 建号所在租户）内的某用户（`user_id`）可访问目标租户（`target_tenant_id`）**」；每个用户**恒有**一行指向其归属租户自身（`target_tenant_id = tenant_id`，即「自有租户」），其余行表示被额外授予 / 加入的租户。
- **跨租户「同一用户」标识**：组合键 `(tenant_id, user_id)`——不引入平台级账号 ID；`username` 仅租户内唯一、跨租户**不假设同人**。
- **读写归属**：写方 = tenant 服务（本表唯一写方；其他服务经「关系数据源」远端实现调用本服务内部端点）；读方 = 租户自助（`my_tenants` / `switch`）。
- **不落 PII**：不承载口令、邮箱、手机号、姓名等个人信息；**不含角色 / 权限**（RBAC 归属不在本表）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `tenant_id` | BIGINT | 否 | 与 `user_id`、`target_tenant_id`、`deleted_at` 复合唯一 | 归属租户主键（同库逻辑外键 → `sys_tenant.id`，只持值） |
| `user_id` | BIGINT | 否 | 同上 | 用户主键（跨服务逻辑外键 → platform 服务租户库 `sys_user.id`，只持值） |
| `target_tenant_id` | BIGINT | 否 | 同上 | 可访问目标租户主键（同库逻辑外键 → `sys_tenant.id`，只持值） |
| `source` | VARCHAR(32) | 否 | — | 写入来源（`super_admin` / `admin_create` / `import` / `sso_jit` / `self_register` / `self_heal`；末值＝读路径兜底自愈补建） |
| `status` | VARCHAR(16) | 否 | 默认 `active` | 状态（`active` / `disabled`）；回收置 `disabled`（保留行、可再启），彻底移除才软删 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_tenant_tenant_user_target_deleted_at` | 唯一 | `(tenant_id, user_id, target_tenant_id, deleted_at)` | 同一用户对同一目标租户唯一（软删除后可重挂） |

- 无物理外键；`tenant_id` / `target_tenant_id` 指向同库 `sys_tenant.id`，`user_id` 指向 platform 服务租户库 `sys_user.id`（均只持值、不建物理外键）。
- **不另建普通索引**：读路径主查询 `WHERE tenant_id = ? AND user_id = ? AND status = 'active' AND deleted_at IS NULL` 由上述复合唯一索引的前缀 `(tenant_id, user_id)` 覆盖（《数据库开发规范》§4「禁止冗余索引」）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻；行数 = 用户 × 可访问租户数，增长可控）。
- **归档**：不归档（可达关系为生命周期数据，随用户 / 租户生命周期软删除）。
- **迁移**：随 **`tenant:platform` 链** Alembic 迁移 `0006_sys_user_tenant` 落地（2026-10-04 生成；`down_revision=0005_sys_outbox_tenant_bigint`；降级 `drop_table`）；命令 `alembic -n alembic:tenant:platform upgrade head`（或 `-x db_key=platform_tenant`）；SQLite 开发库由启动期自动建表覆盖；写入见租户服务关系仓储与内部端点（`/api/v1/tenant/internal/memberships`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库 `bms_tenant`；归属租户 + 用户 + 目标租户 + 来源 + 状态，复合唯一 `(tenant_id, user_id, target_tenant_id, deleted_at)`；随 `tenant:platform` 迁移 `0006_sys_user_tenant`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

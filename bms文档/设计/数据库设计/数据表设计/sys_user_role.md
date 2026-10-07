# sys_user_role（角色 × 用户分配）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user_role

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 07-角色管理（角色分配 · 用户分配） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限计算与缓存」节、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_platform/models/role.py::SysUserRole`（继承 `BaseModel`） |
| 状态 | 已落库（`platform:tenant` 链 `0007_role_tables` 建表；模型 / 仓储 / 服务 / API 随 `02_03` 落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_role](sys_role.md)、[sys_user](sys_user.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `role_id` | BIGINT | 否 | 建索引 | 角色 ID（逻辑外键 → `sys_role.id`，同库） |
| `user_id` | BIGINT | 否 | 建索引 | 用户 ID（逻辑外键 → `sys_user.id`，同库） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人（分配操作人） |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_role_role_user_deleted_at` | 唯一 | `(role_id, user_id, deleted_at)` | 同一角色 ↔ 同一用户唯一（软删除后可复用） |
| `idx_sys_user_role_role_id` | 普通 | `role_id` | 按角色取已分配用户 |
| `idx_sys_user_role_user_id` | 普通 | `user_id` | 按用户取已绑定角色（主体链收敛） |

- 无物理外键；`role_id` / `user_id` 为逻辑外键，**同库**（`sys_role` / `sys_user` 均在 `bms_platform_{code}`）。
- **与用户管理页「用户分配角色」同一张关系表**：用户管理页（`02_02`）与角色管理页（本任务）共用本表读写，不另建。
- **不设数量上限**（原型：仅显示已分配计数）；列表与角色页各自维护，变更后经权限版本失效即时生效。
- **岗位 / 部门分配不落本表**：归 mdm 组织域（`org_role_post` / `org_role_dept`），经插件挂接，bms 不落表。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻）。
- **归档**：不归档（在用授权数据）。
- **迁移**：随 **`platform:tenant` 链**迁移落地（`alembic/versions/platform/tenant/0007_role_tables.py`，本任务新增）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；与用户管理页「用户分配角色」同表） | minjian |
| 2026-10-07 | v2 | 角色域**落点改定** platform 服务租户库（02_03）；用户表随 02_05 归口 platform → `user_id` 回归**同库**逻辑引用（可 join） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

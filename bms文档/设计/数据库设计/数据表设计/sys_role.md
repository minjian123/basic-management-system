# sys_role（角色）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_role

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 07-角色管理（角色定义） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」节、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_platform/models/role.py::SysRole`（继承 `BaseModel`） |
| 状态 | 已落库（`platform:tenant` 链 `0007_role_tables` 建表、`0009_role_type` 加 `role_type` 列并回填内置角色；模型 / 仓储 / 服务 / API 随 `02_03` 落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_user_role](sys_user_role.md)、[sys_role_permission](sys_role_permission.md)、[sys_role_field](sys_role_field.md)、[sys_data_scope](sys_data_scope.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 角色码（租户内唯一；格式受 `role.code_pattern` 约束；**创建后可修改**） |
| `name` | VARCHAR(128) | 否 | — | 角色名称 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） |
| `role_type` | VARCHAR(16) | 否 | 默认 `custom` | 角色类型（`custom` / `system` / `security` / `audit`；**内置判定依据，不可修改**） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_role_code_deleted_at` | 唯一 | `(code, deleted_at)` | 角色码租户内唯一（软删除后可复用） |
| `idx_sys_role_status` | 普通 | `status` | 状态筛选 |

- 无物理外键；本表为角色域主表，其余角色域表以 `role_id` 逻辑引用。
- **内置角色按 `role_type` 列判定**（2026-10-08 改定）：内置角色（系统 / 安全 / 审计管理员）由 `role_type`（`system` / `security` / `audit`，非 `custom` 即内置）判定，取代原配置常量 `role.protected_codes`（常量与系统参数**已退役**，迁移 `0009_role_type` 按缺省清单回填存量行）；内置角色**禁删、禁停用、禁改类型**，`role_type` 不提供修改入口。
- **角色码创建后可修改**（2026-10-08 改定）：接口接受 `code` 更新——格式受 `role.code_pattern` 约束、按 `(code, deleted_at)` 校验唯一（自身同值豁免）；**内置角色的角色码同样可改**（改码不影响内置保护）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻小型配置数据）。
- **归档**：不归档（角色为在用授权数据；删除走软删除 —— 回收站语义归后续）。
- **迁移**：随 **`platform:tenant` 链**迁移落地（`alembic/versions/platform/tenant/0007_role_tables.py`，本任务新增）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；角色域 5 表随本任务落地） | minjian |
| 2026-10-08 | v2 | 增 `role_type` 列（内置判定由配置常量改为列判定）、角色码放开可修改（子任务「角色码可改与内置判定脱钩」，迁移 `0009_role_type`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

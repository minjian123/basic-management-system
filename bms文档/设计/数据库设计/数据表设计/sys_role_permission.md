# sys_role_permission（角色授权：菜单 / 表单 / 操作）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_role_permission

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | org 服务租户库 `bms_org_{code}`（归属服务 `org`） |
| 覆盖模块 | 07-角色管理（菜单 / 表单 / 操作授权） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》「核心表」节、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」节、《[组件设计 · 权限配置](../../组件设计/08_交互类/07_组件设计_权限配置/07_组件设计_权限配置.md)》、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_org/models/role.py::SysRolePermission`（继承 `BaseModel`；待落地） |
| 状态 | 待落库（表文件就绪；模型 / 迁移随本任务落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_role](sys_role.md)、[sys_menu_form](sys_menu_form.md)、[sys_menu](sys_menu.md)、[sys_form](sys_form.md)、[sys_action](sys_action.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `role_id` | BIGINT | 否 | 建索引 | 角色 ID（逻辑外键 → `sys_role.id`，同库） |
| `perm_type` | VARCHAR(16) | 否 | — | 授权类型（`menu` / `form` / `action`） |
| `target_id` | BIGINT | 否 | 建索引 | 授权目标 ID（平台实体雪花 ID：`sys_menu.id` / `sys_form.id` / `sys_action.id`；**跨库逻辑外键**） |
| `source_menu_id` | BIGINT | 否 | 默认 `0` | 来源菜单入口 ID；**`0` = 表单级直接授予**（不用 NULL，避免唯一约束在 NULL 上的跨库语义差异） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_role_permission_role_type_target_source_deleted_at` | 唯一 | `(role_id, perm_type, target_id, source_menu_id, deleted_at)` | 同一角色对同一目标同一来源唯一（支持同一表单 / 动作由多入口分别授予） |
| `idx_sys_role_permission_role_type` | 普通 | `(role_id, perm_type)` | 按角色取各类授权 |
| `idx_sys_role_permission_target` | 普通 | `target_id` | 反查授权引用（删除保护 / 引用校验） |

- 无物理外键；`role_id` 同库逻辑引用，`target_id` **跨库逻辑引用平台实体**（不 join，采集经平台只读契约批量回显）。
- **权限分层语义**：菜单权限（`menu`，仅菜单入口）→ 勾选菜单入口**连带授予其表单查看权限**（落显式 `form` 行、`source_menu_id` = 该菜单入口）；操作权限（`action`，默认无）；**业务权限不落表**（由已授予表单按「表单→业务」对照关系推导）。
- **来源判定**：`source_menu_id != 0` 的行由对应菜单入口连带生成，**本入口可改**、其它来源只读；`source_menu_id = 0` 为「表单权限」页签的**表单级直接授予**。取消勾选菜单入口时**仅删该来源行**，其它来源保留。
- **写入方式**：整份授权**全量覆盖提交**（先删后插、单事务、`Idempotency-Key` 幂等），成功一次版本 +1。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻）。
- **归档**：不归档（在用授权数据）。
- **迁移**：随 **`org:tenant` 链**迁移落地（`alembic/versions/org/tenant/0006_role_tables.py`，本任务新增）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；`source_menu_id` 以 `0` 表示表单级直接授予） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

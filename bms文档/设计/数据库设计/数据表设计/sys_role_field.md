# sys_role_field（角色字段权限）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_role_field

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | org 服务租户库 `bms_org_{code}`（归属服务 `org`） |
| 覆盖模块 | 07-角色管理（字段权限授予） |
| 上游依据 | 《[概要设计 · 角色管理](../../概要设计/06_概要设计_角色管理.md)》「核心表」节、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「字段权限」节、《[组件设计 · 权限配置](../../组件设计/08_交互类/07_组件设计_权限配置/07_组件设计_权限配置.md)》「字段权限」节、《[需求 07-3](../../../项目/07_RBAC基础模块/需求/02_需求_用户与角色.md#r07-3)》 |
| ORM 模型 | `bms_org/models/role.py::SysRoleField`（继承 `BaseModel`；待落地） |
| 状态 | 待落库（表文件就绪；模型 / 迁移随本任务落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_role](sys_role.md)、[sys_field](sys_field.md)、[sys_role_permission](sys_role_permission.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `role_id` | BIGINT | 否 | 建索引 | 角色 ID（逻辑外键 → `sys_role.id`，同库） |
| `form_id` | BIGINT | 否 | — | 表单 ID（平台实体，**跨库逻辑外键** → `sys_form.id`） |
| `field_id` | BIGINT | 否 | — | 字段 ID（平台实体，**跨库逻辑外键** → `sys_field.id`） |
| `visible` | BOOLEAN | 否 | 默认 `true` | 是否可见（`false` = 读时过滤，不返回不渲染） |
| `editable` | BOOLEAN | 否 | 默认 `true` | 是否可编辑（`false` = 写时拒绝） |
| `source_menu_id` | BIGINT | 否 | 默认 `0` | 来源菜单入口 ID；`0` = 表单级直接授予（口径同 [sys_role_permission](sys_role_permission.md)） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_role_field_role_form_field_source_deleted_at` | 唯一 | `(role_id, form_id, field_id, source_menu_id, deleted_at)` | 同一角色对同一字段同一来源唯一 |
| `idx_sys_role_field_role_form` | 普通 | `(role_id, form_id)` | 按角色 + 表单取字段权限 |

- 无物理外键；`role_id` 同库逻辑引用，`form_id` / `field_id` **跨库逻辑引用平台实体**。
- **默认全开，只存收窄项**：未配置的字段全部可见可编辑；本表**只落 `visible = false` 或 `editable = false` 的收窄行**（全开不落行），授予后收窄。
- **约束语义**：`editable = false` 时 `visible` 必须为 `false`（不可见即不可编辑）；字段须属该 `form_id` 字段集合（不匹配拒绝，错误码 `30049`）。
- **来源判定**：与 [sys_role_permission](sys_role_permission.md) 同口径（本菜单入口连带可改、非本入口来源只读）。
- **与布局叠加**：字段权限与表单布局可见性**叠加、权限优先**（布局可见但权限不可见则不渲染）。
- **写入方式**：全量覆盖提交（先删后插、单事务）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻）。
- **归档**：不归档（在用授权数据）。
- **迁移**：随 **`org:tenant` 链**迁移落地（`alembic/versions/org/tenant/0006_role_tables.py`，本任务新增）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-06 | v1 | 新建表结构（org 服务租户库；只存收窄项、带来源标记） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

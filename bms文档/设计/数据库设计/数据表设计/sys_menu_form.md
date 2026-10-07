# sys_menu_form（菜单 ↔ 表单关联）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_menu_form

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理（菜单 ↔ 表单挂接） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_platform/models/menu.py::SysMenuForm`（继承 `BaseModel`） |
| 状态 | 已落库（`platform:platform` 链 `0008_menu_form_multi` 建表，并把既有 `sys_form.menu_id` 幂等搬迁入本表；模型 / 仓储 / 服务 / 契约随 `02_03` 返工落地） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_menu](sys_menu.md)、[sys_form](sys_form.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `menu_id` | BIGINT | 否 | 建索引 | 菜单 ID（逻辑外键 → `sys_menu.id`） |
| `form_id` | BIGINT | 否 | 建索引 | 表单 ID（逻辑外键 → `sys_form.id`） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_menu_form_menu_form_deleted_at` | 唯一 | `(menu_id, form_id, deleted_at)` | 同一菜单 ↔ 同一表单唯一（软删除后可复用） |
| `idx_sys_menu_form_menu_id` | 普通 | `menu_id` | 按菜单取表单列表（授权树 / 动态菜单） |
| `idx_sys_menu_form_form_id` | 普通 | `form_id` | 反查表单被哪些菜单入口引用 |

- 无物理外键；`menu_id` / `form_id` 为逻辑外键，同库。
- **多对多**：一个菜单入口可关联多个表单；同一表单可被多个菜单入口引用；表单也可无任何菜单入口（「孤儿表单」，经营授权页「表单权限」页签直接授予）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **迁移**：随**平台链**迁移落地（`alembic/versions/platform/platform/0008_menu_form_multi.py`，`02_03` 返工）：建本表 → 按 `sys_form.menu_id` 幂等搬迁（软删表单随其 `deleted_at` 一并落软删）→ 删 `sys_form.menu_id` 与唯一约束；`downgrade` 加回可空列并回填后删本表。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-05 | v1 | 新建表结构（平台库；菜单 ↔ 表单多对多关联；随后端返工任务落地） | minjian |
| 2026-10-07 | v2 | 随 `02_03` 返工**落库**：`0008_menu_form_multi` 建表并搬迁既有 `sys_form.menu_id`（软删表单随其 `deleted_at` 一并落软删）；`sys_form` 去 `menu_id` 与唯一约束 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

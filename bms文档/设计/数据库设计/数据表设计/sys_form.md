# sys_form（表单）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_form

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理（表单 → 业务 挂接；菜单 ↔ 表单 经关联表 `sys_menu_form` 多对多） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_platform/models/menu.py::SysForm`（继承 `BaseModel`） |
| 状态 | 已落库（`platform:platform` 链 `0007_menu_metadata` 建表，`0008_menu_form_multi` 去 `menu_id` 与唯一约束）。菜单 ↔ 表单多对多经关联表 `sys_menu_form` 承载（支持多入口指向同一表单、无入口表单） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_menu_form](sys_menu_form.md)、[sys_menu](sys_menu.md)、[sys_business](sys_business.md)、[sys_button](sys_button.md)、[sys_field](sys_field.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `business_id` | BIGINT | 否 | 与 `deleted_at` 复合唯一（**1:1**） | 所属业务码 ID（逻辑外键 → `sys_business.id`） |
| `component` | VARCHAR(255) | 是 | — | 表单视图组件标识（缺省取菜单 `component`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` · **系统字段**：状态（通用可选） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_form_business_id_deleted_at` | 唯一 | `(business_id, deleted_at)` | 业务 1:1 挂表单 |

- 无物理外键；`business_id` 为逻辑外键，同库。
- **菜单 ↔ 表单**：经关联表 [sys_menu_form](sys_menu_form.md) 承载**多对多**（不同菜单入口可指向同一表单；表单也可无菜单入口）；`sys_form` 不再挂 `menu_id`（2026-10-05 变更）。
- **挂接链完整性**：表单 → 业务缺一即该链路不可见 / 不可用；角色授予时前置校验并提示（错误码 40202）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **迁移**：随**平台链**迁移落地（`0007_menu_metadata` 建表；`0008_menu_form_multi` 建 `sys_menu_form`、搬迁既有 `menu_id` 后删列与唯一约束）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |
| 2026-10-05 | v2 | 移除 `menu_id` 及其唯一索引；菜单 ↔ 表单改由关联表 `sys_menu_form` 多对多承载（支持多入口指向同一表单、无入口表单）。关联表模型 / 迁移与 `03_01` 已交付实现待返工 | minjian |
| 2026-10-07 | v3 | 随 `02_03` 返工**落库**：`0008_menu_form_multi` 建 `sys_menu_form`、搬迁既有 `menu_id` 数据后删列与唯一约束；`MenuFormRepository` / 快照多表单 / `my_menu` 多表单 / 契约 `menu_ids` 同步 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

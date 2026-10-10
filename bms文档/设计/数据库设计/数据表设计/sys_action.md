# sys_action（动作码）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_action

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理（动作码字典维护） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「权限模型」「业务码 / 动作码 / 权限码清单」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_platform/models/menu.py::SysAction`（继承 `BaseModel`） |
| 状态 | 已落库（表文件与平台链迁移 `0007_menu_metadata` 就绪；真库随部署窗口） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_action_i18n](sys_action_i18n.md)、[sys_permission](sys_permission.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `code` | VARCHAR(64) | 否 | `(code, deleted_at)` 复合唯一 | 动作码（如 `query`、`create`、`manage`；**全局唯一动词**） |
| `name` | VARCHAR(128) | 否 | — | 名称（默认文案；多语言见 `sys_action_i18n`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用代替删除） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_action_code_deleted_at` | 唯一 | `(code, deleted_at)` | 动作码全局唯一（软删除后可复用） |

- 无物理外键；动作码为纯维度表，被 `sys_permission.action_id` 引用（同库）。
- **三词分治（2026-10-10）**：动作码**解耦业务**（去 `business_id`），退化为**全局动词维度**（权限码右半）；同一动词（如 `query`）全库一条，与业务的组合改由 `sys_permission` 承载。
- 动作码含义与典型权限码见《英文简称规范》「动作码简称」节；权限码形如 `{业务码}:{动作码}`。
- 动作码一经发布稳定不变；**停用代替删除**。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **迁移**：随**平台链**迁移落地（`0007_menu_metadata`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |
| 2026-10-10 | v2 | 三词分治：去 `business_id`，动作码改全局唯一（唯一键 `(code, deleted_at)`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

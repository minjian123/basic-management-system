# sys_field（表单字段）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_field

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理（字段实体与字段权限依据） |
| 上游依据 | 《[概要设计 · 菜单管理](../../概要设计/07_概要设计_菜单管理.md)》、《[架构设计 · 权限计算引擎](../../架构设计/15_架构设计_子系统_权限计算引擎.md)》「字段权限」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》 |
| ORM 模型 | `bms_platform/models/menu.py::SysField`（继承 `BaseModel`） |
| 状态 | 已落库（表文件与平台链迁移 `0007_menu_metadata` 就绪；真库随部署窗口） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_form](sys_form.md)、[sys_field_i18n](sys_field_i18n.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `form_id` | BIGINT | 否 | `(form_id, field_key, deleted_at)` 复合唯一；建索引 | 所属表单 ID（逻辑外键 → `sys_form.id`） |
| `field_key` | VARCHAR(64) | 否 | 同上 | 字段键（表单内唯一，如 `username`、`status`） |
| `name` | VARCHAR(128) | 否 | — | 字段名（**按优先级兜底派生的快照**：系统默认语言 → 必填语言 → 首个有值语言；写侧只提交「locale → 文案」映射，多语言见 `sys_field_i18n`） |
| `type` | VARCHAR(32) | 否 | — | 字段类型（组件语义键，如 `input` / `select` / `date`） |
| `sort` | INT | 否 | 默认 `0` | 同表内排序（升序） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_field_form_key_deleted_at` | 唯一 | `(form_id, field_key, deleted_at)` | 同表单内字段键唯一（软删除后可复用） |
| `idx_sys_field_form_id` | 普通 | `form_id` | 按表单列示字段 |

- 无物理外键；`form_id` 为逻辑外键（`sys_form.id`），同库。
- 字段权限：授予存 `sys_role_field`（role_id + form_id + field_id + visible + editable，归角色管理），**默认全部可见可编辑、授予后收窄**；读时过滤 / 写时校验在权限计算侧落地。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（权限元数据）。
- **迁移**：随**平台链**迁移落地（`0007_menu_metadata`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

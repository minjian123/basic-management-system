# sys_field_i18n（表单字段名多语言表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_field_i18n

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 08-菜单管理 |
| 上游依据 | 《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》「多语言与 i18n 附表」节、《[需求 07-5](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-5)》「多语言」项 |
| ORM 模型 | `bms_platform/models/menu.py::SysFieldI18n`（继承 `BaseModel`） |
| 状态 | 待落库（随主表 `sys_field` 迁移 `0007_menu_metadata`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_field](sys_field.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `field_id` | BIGINT | 否 | `(field_id, locale, deleted_at)` 复合唯一 | 字段 ID（逻辑外键 → `sys_field.id`） |
| `locale` | VARCHAR(16) | 否 | 同上 | 语言标识（如 `zh-CN`、`en-US`） |
| `name` | VARCHAR(128) | 否 | — | 字段名的该语言文案 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_field_i18n_field_locale_deleted_at` | 唯一 | `(field_id, locale, deleted_at)` | 同字段同语言唯一（软删除后可复用） |

- 无物理外键；`field_id` 为逻辑外键（`sys_field.id`），同库。
- 查询按 locale 关联，未命中回退主表默认文案。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（随主表 `sys_field`）。
- **迁移**：随**平台链**迁移落地（`0007_menu_metadata`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-04 | v1 | 新建表结构（平台库；随平台链 `0007_menu_metadata` 迁移落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

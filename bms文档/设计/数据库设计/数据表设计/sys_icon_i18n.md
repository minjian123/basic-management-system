# sys_icon_i18n（自定义图标名称多语言表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_icon_i18n

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属服务 `platform`） |
| 覆盖模块 | 03_03 权限元数据维护页（自定义图标维护；租户库） |
| 上游依据 | 《[数据库设计 · 数据规范](../02_数据库设计_数据规范.md)》「多语言与 i18n 附表」节、[需求 07-17](../../../项目/07_RBAC基础模块/需求/03_需求_菜单与权限.md#r07-17) |
| ORM 模型 | `bms_platform/models/system.py::SysIconI18n`（继承 `BaseModel`） |
| 状态 | 已落库（`enabled`：随主表 `sys_icon` 入 `platform:tenant` 链） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[sys_icon](sys_icon.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `icon_id` | BIGINT | 否 | `(icon_id, locale, deleted_at)` 复合唯一 | 图标 ID（逻辑外键 → `sys_icon.id`） |
| `locale` | VARCHAR(16) | 否 | 同上 | 语言标识（如 `zh-CN`、`en-US`） |
| `name` | VARCHAR(128) | 否 | — | 图标名称的该语言文案 |
| `parent_id` | BIGINT | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） · **系统字段**：上级明细 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_icon_i18n_icon_locale_deleted_at` | 唯一 | `(icon_id, locale, deleted_at)` | 同图标同语言唯一（软删除后可复用） |

- 无物理外键；`icon_id` 为逻辑外键（`sys_icon.id`），同库。
- 查询按 locale 关联，未命中回退主表默认文案。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（随主表 `sys_icon`）。
- **建表**：随 **`platform:tenant` 链**幂等建表落地（表集经表归属登记派生；启动期自动建表、运维经 `ops.init_tenant`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-21 | v1 | 新建表文件；`sys_icon` 转 `enabled` 随 03_03 图标真实 CRUD 入 `platform:tenant` 链落库 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_icon（自定义图标）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_icon

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | platform 服务租户库 `bms_platform_{code}`（归属部署单元 `platform`） |
| 覆盖模块 | 02-4-26 自定义图标与代码校验基座（platform 服务租户库；平台官方与业务自绘图标随代码发布、不落表） |
| 上游依据 | 任务 `02-4-26`（自定义图标与代码校验基座）、《数据库设计 · 数据规范》「公共字段」节、《数据库开发规范》「系统字段」节 |
| ORM 模型 | `bms_core/models/platform/system.py::SysIcon`（继承 `BaseModel`；基座共享模型，14_01 下沉；登记于 `bms_core/models/platform::MODEL_MODULES`） |
| 状态 | 已落库（`enabled`：03_03 已入 `platform:tenant` 链，启动期 / `ops.init_tenant` 幂等建表） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[sys_icon_i18n](sys_icon_i18n.md)（多语言附表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 自建图标码（snake_case，租户内唯一；icon key = `custom:{code}`） · **系统字段**：代码 |
| `name` | VARCHAR(128) | 否 | — | 图标名称（默认文案；多语言见 `sys_icon_i18n`） · **系统字段**：名称 |
| `category` | VARCHAR(64) | 否 | `idx_sys_icon_category` | 图标分组（分类） |
| `tags` | VARCHAR(256) | 否 | 默认 `''` | 标签（逗号分隔，搜索用；跨方言安全） |
| `svg` | TEXT | 否 | — | SVG 内容（上传前清洗归文件管理阶段） |
| `status` | VARCHAR(16) | 否 | 默认 `active` | 状态（`active` / `disabled`） · **系统字段**：状态 |
| `parent_id` | BIGINT | 是 | — | 上级字典 ID（自引用同表 `id`；顶层 NULL；本表无层级，按系统字段口径保留） · **系统字段**：上级字典 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 · **系统字段**：审计字段 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） · **系统字段**：审计字段 |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 · **系统字段**：审计字段 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） · **系统字段**：软删除 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 · **系统字段**：版本号 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_icon_code_deleted_at` | 唯一 | `(code, deleted_at)` | 图标键租户内唯一（软删除后可复用） |
| `uq_sys_icon_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |
| `idx_sys_icon_category` | 普通 | `category` | 按分组取图标 |

- 无物理外键；公共软删除索引 `idx_sys_icon_deleted_at` 由 `BaseModel` 元数据命名约定生成，不在本表重复列出。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（租户库常驻；单租户自定义图标为个位数行）。
- **归档**：不归档（配置类数据保留审计轨迹，软删除即可）。
- **建表**：`enabled`——已入 `platform:tenant` 链，由启动期自动建表 / `ops.init_tenant` 幂等建表落地（`form_key` / `parent_id` 已随表落地）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-11 | v1 | 新建表文件（`planned`；补 `form_key`（表单标识，多表联合判别列）+ `parent_id`，系统字段对齐 02_11；本阶段仅结构声明、不建表） | minjian |
| 2026-10-21 | v2 | 转 `enabled` 并入 `platform:tenant` 链落库（03_03 图标真实 CRUD；`sys_icon_i18n` 表文件随补） | minjian |
| 2026-10-22 | v3 | ORM 模型落点迁基座共享 `bms_core/models/platform/system.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |
| 2026-10-26 | v4 | `code` 口径由 kebab-case 收紧为 snake_case（任务 `01_08` 登记标识二期；仅注释与校验口径，无 DDL 变更、存量行不迁移） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

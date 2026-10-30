# sys_data_source（数据源声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_data_source

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | [需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1、《[跨产品协同登记清单](../../../跨产品协同登记清单.md)》§5 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysDataSource`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_collaboration](sys_collaboration.md)（`dataset` 类能力引用本表键） |

- **语义**：一行 = 一个**字典 / 参考数据源**声明（平台内建或产品自持），供表单字段与选择器按数据源键取数。
- **写入归属**：写方 = platform 服务（注册通道；平台内建源由平台自身声明）。读方 = 字典出口、前端目录、`dataset` 类能力的取数。
- **不存数据**：只存「从哪里取、取哪些字段、支持哪些取数策略」，数据本身在提供方。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `data_source_key` | VARCHAR(64) | 否 | 全局唯一（含 `deleted_at`） | 数据源键（前端与后端共用标识） |
| `product_key` | VARCHAR(32) | 否 | 索引 | 声明方产品键（`origin = platform` 时为 `platform`） |
| `name` | VARCHAR(64) | 否 | — | 显示名（多语言由 `_i18n` 附表承载，本表存默认文案键） |
| `kind` | VARCHAR(16) | 否 | 默认 `dict` | 数据源类型（`dict` / `tree` / `remote`） |
| `data_source` | VARCHAR(128) | 否 | — | 取数实现标识（如 `{产品}.{域}.{表}`） |
| `origin` | VARCHAR(16) | 否 | 默认 `product` | 来源（`platform` 内建 / `product` 产品自持） |
| `path` | VARCHAR(255) | 是 | — | 提供方访问面路径（产品自持源必填） |
| `allowlist` | TEXT | 是 | JSON 数组 | 允许下发的字段白名单（不列即不下发） |
| `cascade` | BOOLEAN | 否 | 默认 false | 是否级联取数（父子联动） |
| `strategies` | TEXT | 是 | JSON 数组 | 支持的取数策略（`select` / `region` / `match`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_data_source_key_deleted_at` | 唯一 | `(data_source_key, deleted_at)` | 数据源键全局唯一 |
| `idx_sys_data_source_product_status` | 普通 | `(product_key, status)` | 按声明方取全量（注册对账 / 整体退役） |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级为「产品数 × 数据源数」）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入（平台内建源 + 产品自持源同一入口）。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

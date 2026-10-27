# sys_product_route（产品级路由声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_product_route

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | [需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1、《[架构设计 · 产品与服务划分](../../../设计/架构设计/39_架构设计_子系统_产品与服务划分.md)》 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysProductRoute`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_product](sys_product.md)、[sys_module](sys_module.md) |

- **语义**：一行 = 一个产品的前端命名空间映射（产品键 → 域段 → 承载服务键），是网关路由生成与前端目录取址的输入。
- **写入归属**：写方 = platform 服务（注册通道）。读方 = 网关配置生成（`ops.gateway_config`）、前端目录出口。
- **唯一性**：域段与服务键全局唯一（`validate_product_routes` 口径），且目标服务须为 `product` 分组并归属同一产品。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `product_key` | VARCHAR(32) | 否 | 与 `domain`、`deleted_at` 复合唯一 | 产品键（声明方） |
| `domain` | VARCHAR(64) | 否 | 全局唯一（含 `deleted_at`） | 域段（前端命名空间段，如 `mdm`） |
| `service_key` | VARCHAR(64) | 否 | 全局唯一（含 `deleted_at`） | 承载服务键 |
| `description` | VARCHAR(255) | 是 | — | 说明（对外路由前缀提示等） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_product_route_product_domain_deleted_at` | 唯一 | `(product_key, domain, deleted_at)` | 一产品一域段一条 |
| `uq_sys_product_route_domain_deleted_at` | 唯一 | `(domain, deleted_at)` | 域段全局唯一（网关前缀冲突兜底） |
| `uq_sys_product_route_service_deleted_at` | 唯一 | `(service_key, deleted_at)` | 服务键全局唯一（一服务只挂一个产品路由） |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级等于产品数）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入；「目标服务为 product 分组且产品归属一致」由注册校验保证（不做物理外键）。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

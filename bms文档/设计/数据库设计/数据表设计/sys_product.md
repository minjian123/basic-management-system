# sys_product（产品档案）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_product

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` |
| 覆盖模块 | 03-模块注册（产品级注册 / R4.1） |
| 上游依据 | 《[架构设计 · 模块注册](../../架构设计/11_架构设计_子系统_模块注册.md)》「模块契约与产品下线」节、《[平台可扩展性规划](../../规划/平台可扩展性规划.md)》落地路线图 R4.1、[需求 12-1](../../../项目/02_后端基座与服务化地基/需求/12_需求_产品服务接入.md#r12-1) |
| ORM 模型 | `bms_core/models/platform.py::SysProduct`（继承 `BaseModel`） |
| 状态 | 已设计（实现在任务 `12_01`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_module](sys_module.md)（`product_key` 逻辑引用本表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `product_key` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 产品标识（如 `mdm` / `biz` / `cw`） |
| `name` | VARCHAR(128) | 否 | — | 产品名称（默认文案） |
| `frontend_package_source` | VARCHAR(255) | 是 | — | 前端包来源（产品前端模块产物的获取来源；如仓库 / 包标识） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` / `retired`（下线保留登记，不物理删除） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_product_key_deleted_at` | 唯一 | `(product_key, deleted_at)` | 产品标识唯一（软删除后可复用） |

- 无物理外键；`sys_module.product_key` 逻辑引用本表 `product_key`（产品级属性只存本表，模块行不重复）。
- **产品下线不物理删除**：`status` 置 `retired`，保留登记便于回溯（架构 11「模块契约与产品下线」节）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（产品档案为契约元数据，注销态保留）。
- **迁移**：随**平台链** Alembic 迁移落地（实现在任务 `12_01`；平台库单库执行）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-07 | v1 | 新建表结构（平台库；产品级注册档案，`sys_module.product_key` 逻辑引用） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

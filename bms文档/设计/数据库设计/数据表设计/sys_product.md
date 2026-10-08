# sys_product（产品档案）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_product

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` |
| 覆盖模块 | 03-模块注册（产品级注册 / R4.1） |
| 上游依据 | 《[架构设计 · 模块注册](../../架构设计/11_架构设计_子系统_模块注册.md)》「模块契约与产品下线」节、《[平台可扩展性规划](../../../规划/平台可扩展性规划.md)》落地路线图 R4.1、[需求 12-1](../../../项目/02_后端基座与服务化地基/需求/12_需求_产品服务接入.md#r12-1) |
| ORM 模型 | `bms_platform/models/catalog.py::SysProduct`（继承 `BaseModel`；与 `SysModule` 同文件，06_02「模型归服务」口径） |
| 状态 | 已落库（平台链迁移 `0009_sys_product` 建表，2026-10-07；产品档案三行种子见 `ops/seed_module.py` 幂等 upsert） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_module](sys_module.md)（`product_key` 逻辑引用本表） |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `product_key` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 产品标识（如 `mdm` / `biz` / `cw`） |
| `name` | VARCHAR(128) | 否 | — | 产品名称（默认文案） |
| `frontend_package_source` | VARCHAR(255) | 是 | — | 前端包来源：**产品前端工程标识** `{仓库名}#{前端根}`（如 `mdm#frontend`）——只记「从哪里取」；主机 / 凭据 / 访问地址由部署环境配置注入，不入库。已接入产品回填、未接入留空 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` / `planned`（已注册未建代码 / 建表，先注册后建表的预登记态）/ `retired`（下线保留登记，不物理删除） |
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
- **迁移**：随**平台链** Alembic 迁移 `alembic/versions/platform/platform/0009_sys_product.py` 落地（2026-10-07；平台库单库执行，SQLite 经 `batch_alter_table` 兼容）；种子走 `ops/seed_module.py` 幂等 upsert（`PRODUCT_CATALOG` 单一来源）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-07 | v1 | 新建表结构（平台库；产品级注册档案，`sys_module.product_key` 逻辑引用） | minjian |
| 2026-10-07 | v2 | 迁移落地：随平台链 `0009_sys_product` 建表 + 表归属登记（`platform` / 平台服务库）+ 产品档案种子三行（`biz` / `cw` / `mdm`）；ORM 落点按 06_02 口径修正为 `bms_platform/models/catalog.py::SysProduct` | minjian |
| 2026-10-07 | v3 | `status` 取值补 `planned`（已注册未建代码 / 建表：`mdm` 先注册后建表的预登记态，与 `sys_module.status` 口径一致） | minjian |
| 2026-10-08 | v4 | `frontend_package_source` 取值口径定稿（产品前端工程标识 `{仓库名}#{前端根}`，不含主机与凭据）并回填已接入产品 `mdm`（`mdm#frontend`）；随 bms 任务 `03_04`（R4.3 跨仓模块产物接入）交付 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

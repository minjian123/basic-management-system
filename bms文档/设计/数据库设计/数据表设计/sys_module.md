# sys_module（业务模块注册表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_module

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` |
| 覆盖模块 | 03-模块注册（服务目录与契约登记） |
| 上游依据 | 《架构设计 · 模块注册》「注册表结构与数据」「服务目录与契约登记」节、《命名规范》「数据库命名」节、[需求 02-16](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-16)、[需求 03-1](../../../项目/02_后端基座与服务化地基/需求/03_需求_服务目录与契约登记.md#r03-1) |
| ORM 模型 | `bms_core/models/platform.py::SysModule`（继承 `BaseModel`） |
| 状态 | 已落库（平台链迁移 `0001_sys_tenant_module` 建表、`0002_sys_module_catalog` 升格服务目录，2026-09-22；服务目录 16 行种子见 `ops/seed_module.py` 幂等 upsert） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[架构 11-模块注册](../../架构设计/11_架构设计_子系统_模块注册.md)、[sys_module_i18n](sys_module_i18n.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `module_key` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 行登记标识（模块简称 / 服务标识；如 `pur`、`sys`、`identity`） |
| `service_key` | VARCHAR(32) | 是 | 应用 / CI 层唯一（**不建 DB 唯一**） | 服务维度标识（微服务工程名，如 `platform`、`identity`；模块行可空） |
| `name` | VARCHAR(128) | 否 | — | 名称（默认文案；多语言见 `sys_module_i18n`） |
| `table_prefix` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 表前缀（形如 `{module_key}_`，如 `pur_`、`sys_`、`identity_`） |
| `business_code` | VARCHAR(64) | 是 | — | 业务权限码（`sys_business.code`；模块行默认取 `module_key`，服务行可空） |
| `errcode_segment` | VARCHAR(8) | 是 | 应用 / CI 层唯一（**不建 DB 唯一**） | 错误码段号（字符串；产品模块 `10` 起，平台域 `01`~`04`，纯服务留空） |
| `event_domain` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 事件域（全小写，默认与 `module_key` 一致） |
| `service_group` | VARCHAR(16) | 否 | 默认 `foundation` | 归属分组：`foundation`（平台地基）/ `capability`（平台能力）/ `product`（产品服务） |
| `build_batch` | INT | 否 | 默认 `0` | 建设批次（`0`~`3`，对齐《微服务演进规划》） |
| `service_version` | VARCHAR(16) | 否 | 默认 `0.1.0` | 服务版本（semver） |
| `contract_version` | VARCHAR(16) | 否 | 默认 `0.1.0` | 公开契约（OpenAPI）版本（semver） |
| `product_key` | VARCHAR(32) | 是 | — | 产品标识（`biz` / `cw`；空 = 平台） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` / `planned` |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_module_key_deleted_at` | 唯一 | `(module_key, deleted_at)` | 行登记标识唯一（软删除后可复用） |
| `uq_sys_module_prefix_deleted_at` | 唯一 | `(table_prefix, deleted_at)` | 表前缀唯一 |
| `uq_sys_module_domain_deleted_at` | 唯一 | `(event_domain, deleted_at)` | 事件域唯一 |

- 无物理外键；业务模块用 `{table_prefix}` 建表，`errcode_segment` / `event_domain` 为契约值（注册即定、不回收）。
- **`service_key` / `errcode_segment` 不建 DB 唯一**（均可空）：达梦视复合唯一中的 NULL 相等（01_05 实测、计划「后续阶段待办 #1」），多个空值行无法共存；其唯一性由启动 / CI 校验承担（需求 03-2）。
- 段号列宽留余量（`VARCHAR(8)`）：当前校验 2 位数字（产品 `10` 起），将来段位不足可放宽为 3 位而无需改列。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（注册契约元数据，注销态保留）。
- **迁移**：随**平台链** Alembic 迁移落地（脚本 `alembic/versions/platform/0001_sys_tenant_module.py` 建表（2026-09-22）、`0002_sys_module_catalog.py` 升格服务目录（2026-09-22）；命令 `alembic -n alembic:platform upgrade head`）；新增模块 = 一个 revision（建表 + 种子）原子落地，平台库单库执行，运行时不提供增删改。种子走 `ops/seed_module.py` 幂等 upsert 脚本（复用 `SERVICE_CATALOG` 单一来源）；SQLite 开发库由启动期自动建表（按迁移链表集）覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（平台库；随落库阶段迁移） | minjian |
| 2026-09-22 | v2 | 迁移落地：随平台链 `0001_sys_tenant_module` 建表（索引名统一 `idx_*`；种子脚本退化为纯种子） | minjian |
| 2026-09-22 | v3 | 升格服务目录：增 `service_key` / `business_code` / `service_group` / `build_batch` / `service_version` / `contract_version` / `product_key`；`errcode_segment` 改可空并去 DB 复合唯一（随平台链 `0002_sys_module_catalog`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

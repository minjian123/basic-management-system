# sys_module（业务模块注册表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_module

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` |
| 覆盖模块 | 03-模块注册（服务目录与契约登记） |
| 上游依据 | 《架构设计 · 模块注册》「注册表结构与数据」「服务目录与契约登记」节、《命名规范》「数据库命名」节、[需求 02-16](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-16)、[需求 03-1](../../../项目/02_后端基座与服务化地基/需求/03_需求_服务目录与契约登记.md#r03-1) |
| ORM 模型 | `bms_core/models/platform/catalog.py::SysModule`（继承 `BaseModel`；基座共享模型，14_01 下沉；06_02 分链后随服务迁出） |
| 状态 | 已落库（平台链迁移 `0001_sys_tenant_module` 建表、`0002_sys_module_catalog` 升格服务目录，2026-09-22；服务目录 16 行种子见 `ops/seed_module.py` 幂等 upsert） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[架构 11-模块注册](../../架构设计/11_架构设计_子系统_模块注册.md)、[sys_module_i18n](sys_module_i18n.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 行登记标识（模块简称 / 服务标识；如 `pur`、`sys`、`identity`）。**DB 列名 `code`，ORM 属性与契约字段名仍为 `module_key`**（列名 ↔ 属性映射见「索引与约束」） · **系统字段**：代码 |
| `service_key` | VARCHAR(32) | 是 | 应用 / CI 层唯一（**不建 DB 唯一**） | 服务维度标识（微服务工程名，如 `platform`、`identity`；模块行可空） |
| `name` | VARCHAR(128) | 否 | — | 名称（**按优先级兜底派生的快照**：系统默认语言 → 必填语言 → 首个有值语言；写侧只提交「locale → 文案」映射，多语言见 `sys_module_i18n`） |
| `table_prefix` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 表前缀（形如 `{module_key}_`，如 `pur_`、`sys_`、`identity_`） |
| `business_code` | VARCHAR(64) | 是 | — | 业务码（`sys_business.code`；模块行默认取 `module_key`，服务行可空） |
| `errcode_segment` | VARCHAR(8) | 是 | 应用 / CI 层唯一（**不建 DB 唯一**） | 错误码段号（字符串；产品模块 `10` 起，平台域 `01`~`04`，纯服务留空） |
| `event_domain` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 事件域（全小写，默认与 `module_key` 一致） |
| `service_group` | VARCHAR(16) | 否 | 默认 `foundation` | 归属分组：`foundation`（平台地基）/ `capability`（平台能力）/ `product`（产品服务） |
| `build_batch` | INT | 否 | 默认 `0` | 建设批次（`0`~`3`，对齐《微服务演进规划》） |
| `service_version` | VARCHAR(16) | 否 | 默认 `0.1.0` | 服务版本（semver） |
| `contract_version` | VARCHAR(16) | 否 | 默认 `0.1.0` | 公开契约（OpenAPI）版本（semver） |
| `product_key` | VARCHAR(32) | 是 | — | 产品标识（`biz` / `cw`；空 = 平台） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` / `planned` · **系统字段**：状态 |
| `tenant_base` | BOOLEAN | 否 | 默认 `false` | 租户恒开通标记（产品服务行在自持清单声明 `tenant_base = true`）：为真者不参与开通勾选与模块门禁；平台模块恒开通由基座常量承载，不依赖本列 |
| `parent_id` | BIGINT | 是 | — | 上级字典 ID（自引用同表 `id`；顶层 NULL；本表无层级，按系统字段口径保留） · **系统字段**：上级字典 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） · **系统字段**：审计字段 |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_module_code_deleted_at` | 唯一 | `(code, deleted_at)` | 行登记标识唯一（软删除后可复用；原 `uq_sys_module_key_deleted_at`） |
| `uq_sys_module_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |
| `uq_sys_module_prefix_deleted_at` | 唯一 | `(table_prefix, deleted_at)` | 表前缀唯一 |
| `uq_sys_module_domain_deleted_at` | 唯一 | `(event_domain, deleted_at)` | 事件域唯一 |

- 无物理外键；业务模块用 `{table_prefix}` 建表，`errcode_segment` / `event_domain` 为契约值（注册即定、不回收）。
- **`service_key` / `errcode_segment` 不建 DB 唯一**（均可空）：达梦视复合唯一中的 NULL 相等（01_05 实测、计划「后续阶段待办 #1」），多个空值行无法共存；其唯一性由启动 / CI 校验承担（需求 03-2）。
- 段号列宽留余量（`VARCHAR(8)`）：当前校验 2 位数字（产品 `10` 起），将来段位不足可放宽为 3 位而无需改列。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（注册契约元数据，注销态保留）。
- **建表**：随 **`platform:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（平台库；随落库阶段迁移） | minjian |
| 2026-09-22 | v2 | 迁移落地：随平台链 `0001_sys_tenant_module` 建表（索引名统一 `idx_*`；种子脚本退化为纯种子） | minjian |
| 2026-09-22 | v3 | 升格服务目录：增 `service_key` / `business_code` / `service_group` / `build_batch` / `service_version` / `contract_version` / `product_key`；`errcode_segment` 改可空并去 DB 复合唯一（随平台链 `0002_sys_module_catalog`） | minjian |
| 2026-10-11 | v4 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `parent_id`；既有标识列 `module_key` **DB 列名改 `code`**（ORM 属性 / 契约字段名保持 `module_key`），唯一约束改 `uq_sys_module_code_deleted_at`；随 `platform:platform` 链 `0010_system_fields_form_key` | minjian |
| 2026-10-22 | v5 | ORM 模型落点迁基座共享 `bms_core/models/platform/catalog.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |
| 2026-10-28 | v6 | 增 `tenant_base`（租户恒开通声明，07B `03_01`）：产品服务行在自持清单声明、随注册落库并纳入接库对账；建表仍随 `platform:platform` 链，开发 / 演示库删库重建（无迁移链） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

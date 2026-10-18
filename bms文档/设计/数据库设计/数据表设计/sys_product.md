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
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(32) | 否 | 与 `deleted_at` 复合唯一 | 产品标识（如 `mdm` / `biz` / `cw`）。**DB 列名 `code`，ORM 属性与契约字段名仍为 `product_key`** · **系统字段**：代码 |
| `name` | VARCHAR(128) | 否 | — | 产品名称（默认文案） · **系统字段**：名称 |
| `frontend_package_source` | VARCHAR(255) | 是 | — | 前端包来源：**产品前端工程标识** `{仓库名}#{前端根}`（如 `mdm#frontend`）——只记「从哪里取」；主机 / 凭据 / 访问地址由部署环境配置注入，不入库。已接入产品回填、未接入留空 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled` / `planned`（已注册未建代码 / 建表，先注册后建表的预登记态）/ `retired`（下线保留登记，不物理删除） · **系统字段**：状态 |
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
| `uq_sys_product_code_deleted_at` | 唯一 | `(code, deleted_at)` | 产品标识唯一（软删除后可复用；原 `uq_sys_product_key_deleted_at`） |
| `uq_sys_product_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |

- 无物理外键；`sys_module.product_key` 逻辑引用本表 `product_key`（产品级属性只存本表，模块行不重复）。
- **产品下线不物理删除**：`status` 置 `retired`，保留登记便于回溯（架构 11「模块契约与产品下线」节）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（产品档案为契约元数据，注销态保留）。
- **建表**：随 **`platform:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-07 | v1 | 新建表结构（平台库；产品级注册档案，`sys_module.product_key` 逻辑引用） | minjian |
| 2026-10-07 | v2 | 迁移落地：随平台链 `0009_sys_product` 建表 + 表归属登记（`platform` / 平台服务库）+ 产品档案种子三行（`biz` / `cw` / `mdm`）；ORM 落点按 06_02 口径修正为 `bms_platform/models/catalog.py::SysProduct` | minjian |
| 2026-10-07 | v3 | `status` 取值补 `planned`（已注册未建代码 / 建表：`mdm` 先注册后建表的预登记态，与 `sys_module.status` 口径一致） | minjian |
| 2026-10-08 | v4 | `frontend_package_source` 取值口径定稿（产品前端工程标识 `{仓库名}#{前端根}`，不含主机与凭据）并回填已接入产品 `mdm`（`mdm#frontend`）；随 bms 任务 `03_04`（R4.3 跨仓模块产物接入）交付 | minjian |
| 2026-10-11 | v5 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `parent_id`；既有标识列 `product_key` **DB 列名改 `code`**（ORM 属性 / 契约字段名保持 `product_key`），唯一约束改 `uq_sys_product_code_deleted_at`；随 `platform:platform` 链 `0010_system_fields_form_key` | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

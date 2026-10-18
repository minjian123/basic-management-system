# sys_tenant（租户注册表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_tenant`（归属服务 `tenant`，06_03 定案；06_01 起随平台服务库拆分） |
| 覆盖模块 | 26-租户管理 |
| 上游依据 | 《架构设计 · 数据架构》「数据分布」节、《架构设计 · 多租户路由》「租户解析链」节、[需求 02-15](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-15) |
| ORM 模型 | `bms_tenant/models/tenant.py::SysTenant`（继承 `BaseModel`；06_03 由共享基座库迁出） |
| 状态 | 已落库（平台链迁移 `0001_sys_tenant_module`，2026-09-22；`db_key` 改可空见 `0005_sys_tenant_db_key_nullable`，2026-09-23；种子见 `ops/seed_tenant.py`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[架构 12-多租户路由](../../架构设计/12_架构设计_子系统_多租户路由.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 租户编码（全小写） · **系统字段**：代码 |
| `name` | VARCHAR(128) | 否 | — | 租户名称 · **系统字段**：名称 |
| `domain` | VARCHAR(255) | 是 | `idx_sys_tenant_domain` | 子域名（`{domain}`） |
| `db_key` | VARCHAR(64) | 是 | — | **已废弃**（06_01 起不再写入）：服务化后库键由 `tenant_{service}_{code}` 派生，注册表不持有数据源键；存量取值保留但不再被消费 |
| `status` | VARCHAR(16) | 否 | — | 状态（`active` / `suspended`） |
| `expire_at` | DATETIME | 是 | — | 到期时间（UTC） |
| `parent_id` | BIGINT | 是 | — | 上级字典 ID（自引用同表 `id`；顶层 NULL；本表无层级，按系统字段口径保留） · **系统字段**：上级字典 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_tenant_code_deleted_at` | 唯一 | `(code, deleted_at)` | 租户编码唯一（软删除后可复用） |
| `uq_sys_tenant_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |
| `idx_sys_tenant_domain` | 普通 | `(domain)` | 子域名解析查询 |

- 无物理外键；租户库按命名约定 `bms_{service}_{tenant}` 由「服务标识 + 租户编码」派生（键 `tenant_{service}_{code}`），注册表不再持有数据源键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（租户注册生命周期数据）。
- **建表**：随 **`tenant:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（平台库；随落库阶段迁移） | minjian |
| 2026-09-22 | v2 | 迁移落地：随平台链 `0001_sys_tenant_module` 建表（原 `ix_*` 索引名统一为 `idx_*`） | minjian |
| 2026-09-22 | v3 | 索引名对齐实际库与模型元数据（`idx_domain` → `idx_sys_tenant_domain`） | minjian |
| 2026-09-23 | v4 | `db_key` 废弃：改可空（平台链 `0005`）且不再写入，库键改由 `tenant_{service}_{code}` 派生（06_01）；归属库 / ORM 模型两栏对齐 06_03 迁出结果 | minjian |
| 2026-10-11 | v5 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `parent_id`；随 `tenant:platform` 链 `0007_system_fields_form_key` | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

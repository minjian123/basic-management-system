# sys_tenant_database（租户库名对照）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant_database

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_tenant`（归属服务 `tenant`，与 `sys_tenant` 同库） |
| 覆盖模块 | 26-租户管理 |
| 上游依据 | 《架构设计 · 多租户路由》「三库命名与建库标准」节、[需求 10-1](../../../项目/06_认证与安全/需求/10_需求_租户标识内部化.md#r10-1)、[10_01 详细设计与口径定稿](../../../项目/06_认证与安全/任务/10_租户标识内部化/10_租户标识内部化_01_详细设计与口径定稿/设计/01_详细设计_01_详细设计与口径定稿.md) §3、需求 [09-2](../../../项目/06_认证与安全/需求/09_需求_类体系根治理.md#r09-2) |
| ORM 模型 | `bms_tenant/models/tenant_database.py::SysTenantDatabase`（继承 `BaseModel`） |
| 状态 | 已落库（`tenant:platform` 链迁移 `0004_sys_tenant_database`，2026-09-29） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「已设计数据表登记」、[sys_tenant](sys_tenant.md)、[架构 12-多租户路由](../../架构设计/12_架构设计_子系统_多租户路由.md) |

- **语义**：租户主键 ↔ 库名基对照；一租户一行，各服务共享同一基。库键 / 库名保持 code 派生（`tenant_{db_basis}` / `bms_{service}_{db_basis}`），但 code 段为**创建时冻结的库名基 `db_basis`**，**不随租户编码变更而变**——由此避免「code 复用 = 物理层串号」，code 变更不重命名库。
- **读写归属**：写方 = tenant 服务（租户开通 / 建库 / 种子时与 `sys_tenant` 同事务写入）；读方 = 租户源（随快照 / 契约下发 `db_basis`）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `tenant_id` | BIGINT | 否 | 与 `deleted_at` 复合唯一（`uq_sys_tenant_database_tenant_deleted_at`） | 租户主键（同库逻辑外键 → `sys_tenant.id`，只持值） |
| `db_basis` | VARCHAR(64) | 否 | — | 库名基（创建时冻结的租户编码，稳定不可变） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- `(tenant_id, deleted_at)` 复合唯一是「一租户一对照行」的事实源（软删除后可重挂）；`db_basis` 与 `sys_tenant.code` 可不一致（code 变更后），由本表解释库归属。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_tenant_database_tenant_deleted_at` | 唯一 | `(tenant_id, deleted_at)` | 一租户一对照行（软删除后可重挂） |

- 无物理外键；`tenant_id` 指向同库 `sys_tenant.id`（同库逻辑外键，只持值）。
- 不按 `db_basis` 建索引（解析链按 `tenant_id` / `code` 命中 `sys_tenant` 后取本表，无按 `db_basis` 反查需求）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（租户开通生命周期数据）。
- **迁移**：随 **`tenant:platform` 链** Alembic 迁移 `0004_sys_tenant_database` 落地（2026-09-29；含存量租户回填 `db_basis=当前 code`；降级 `drop_table`）；命令 `alembic -n alembic:tenant:platform upgrade head`；SQLite 开发库由启动期自动建表覆盖；种子 / 开通写入见 `ops/seed_tenant.py` 与租户注册仓储（同事务写 `sys_tenant` + 本表）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-29 | v1 | 新建表结构（平台库 `bms_tenant`；`tenant_id` + `db_basis` 对照，随 10_04 迁移 `0004_sys_tenant_database` 落地并回填存量） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

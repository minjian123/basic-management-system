# sys_tenant（租户注册表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform` |
| 覆盖模块 | 26-租户管理 |
| 上游依据 | 《架构设计 · 数据架构》「数据分布」节、《架构设计 · 多租户路由》「租户解析链」节、[需求 02-15](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-15) |
| ORM 模型 | `app/models/platform.py::SysTenant`（继承 `BaseModel`） |
| 状态 | 已设计 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[架构 11-多租户路由](../../架构设计/11_架构设计_子系统_多租户路由.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 租户编码（全小写） |
| `name` | VARCHAR(128) | 否 | — | 租户名称 |
| `domain` | VARCHAR(255) | 是 | `idx_domain` | 子域名（`{domain}`） |
| `db_key` | VARCHAR(64) | 否 | — | 数据源键（`tenant_{code}`） |
| `status` | VARCHAR(16) | 否 | — | 状态（`active` / `suspended`） |
| `expire_at` | DATETIME | 是 | — | 到期时间（UTC） |
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
| `idx_domain` | 普通 | `(domain)` | 子域名解析查询 |

- 无物理外键；`db_key` 指向数据源配置，租户库由命名约定 `bms_tenant_{code}` 派生。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（租户注册生命周期数据）。
- **迁移**：随平台库 Alembic 迁移落地（真实迁移与种子归落库阶段）；本阶段仅结构声明，不建表。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（平台库；随落库阶段迁移） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文档规范」节配套

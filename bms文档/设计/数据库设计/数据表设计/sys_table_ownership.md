# sys_table_ownership（表归属登记表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_table_ownership

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 覆盖模块 | 06-数据拓扑升级（表归属登记） |
| 上游依据 | 《架构设计 · 数据架构》「数据分布」「迁移策略」节、《微服务演进规划》「服务化地基要求与门禁」S2、《数据库设计 · 数据规范》「库划分与迁移归属」节 |
| ORM 模型 | `bms_core/models/ownership.py::SysTableOwnership`（继承 `BaseModel`） |
| 状态 | 已落库（平台服务链迁移 `0005_sys_table_ownership`，2026-09-23） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_module](sys_module.md) |

> **单一来源**：归属清单为代码常量 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；本表是**落库登记
> 与对账载体**（`ops/seed_tables.py` 幂等 upsert、`ops/check_tables.py` 双向对账、`platform` 服务启动期接库
> 对账）。库键与库名、迁移链表集均从该清单派生。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `table_name` | VARCHAR(64) | 否 | `(table_name, deleted_at)` 复合唯一 | 表名（小写 snake_case） |
| `owner` | VARCHAR(32) | 否 | — | 归属服务标识（取服务目录 `service_key`；`*` = 每服务自有） |
| `datasource` | VARCHAR(16) | 否 | 默认 `tenant` | 库类别（`platform` / `tenant` / `archive` / `both`；`both` 仅限 `*` 归属） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` = 已定案且入链 / `planned` = 未定稿、不进链） |
| `note` | VARCHAR(255) | 否 | 默认 `''` | 说明（用途 / 归属备注） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_table_ownership_name_deleted_at` | 唯一 | `(table_name, deleted_at)` | 同表名唯一（软删除后可复用） |

- 无物理外键；`owner` 为逻辑外键（服务目录 `sys_module.service_key` / `module_key`），跨库逻辑引用。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（配置类元数据，行数与表数同量级）。
- **归档**：不归档。
- **迁移**：随**平台服务链**（`platform:platform`）Alembic 迁移落地
  （`alembic/versions/platform/platform/0005_sys_table_ownership.py`，2026-09-23）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-23 | v1 | 新建表结构（平台服务库；随分链迁移 `0005_sys_table_ownership` 落地） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

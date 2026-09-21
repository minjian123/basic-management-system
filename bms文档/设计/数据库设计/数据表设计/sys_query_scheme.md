# sys_query_scheme（查询方案表（泛化：字典高级查询 + 列表筛选））

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_query_scheme

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 10-字典管理 / 列表接口（泛化） |
| 上游依据 | 需求 [02-56](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-56)、需求 [02-44](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-44)、《概要设计 · 字典管理》「核心表」节、《组件设计 · 字典字段》第 3 / 7 / 8 节、[02-4-27 详细设计](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存/设计/27_详细设计_01_字典真实取数与缓存.md) |
| ORM 模型 | `app/listing/models.py::SysQueryScheme`（继承 `BaseModel`） |
| 状态 | 待落库 |
| 相关节点 | 数据库设计总览「核心表清单总表 · 租户库」、[02-4-20 列表查询与偏好契约基座](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座_20_列表查询与偏好契约基座/02_后端基座_04_跨阶段基座_20_列表查询与偏好契约基座.md)、[02-4-27 字典真实取数与缓存](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | VARCHAR(64) | 否 | 与作用域组合唯一 | 方案名 |
| `scope` | VARCHAR(16) | 否 | — | 作用域（user / tenant / platform） |
| `owner_id` | BIGINT | 是 | 个人方案填 | 归属用户 ID |
| `target` | VARCHAR(16) | 否 | — | 目标（items 字典条目 / business 列表筛选） |
| `dict_type` | VARCHAR(64) | 是 | — | 字典类型（target=items 时填） |
| `field_key` | VARCHAR(64) | 是 | — | 表单标识（target=business 时为 form_key） |
| `provider_key` | VARCHAR(64) | 是 | — | 查询提供者键（高级查询可选） |
| `conditions` | JSON | 是 | — | 条件组 JSON（AND/OR 分组树） |
| `params` | JSON | 是 | — | 额外参数 JSON（提供者参数） |
| `layout` | JSON | 是 | — | 展示配置 JSON（结果列等） |
| `is_default` | BOOLEAN | 否 | 默认 false | 是否默认方案 |
| `shared` | BOOLEAN | 否 | 默认 false | 是否共享 |
| `status` | VARCHAR(16) | 否 | 默认 enabled | 状态（enabled / disabled） |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_scheme_scope_name_deleted_at` | 唯一 | `(scope, owner_id, target, dict_type, field_key, name, deleted_at)` | 同作用域下方案名唯一（软删除后可复用） |
| `idx_scheme_lookup` | 普通 | `(target, field_key, status, scope)` | 方案清单与默认解析 |
| `ix_sys_query_scheme_deleted_at` | 普通 | `(deleted_at)` | 软删除过滤 |

- 无物理外键；`type_id` / `dict_item_id` / `dict_type_id` / `dict_attr_id` 为逻辑引用（同租户库），`parent_id` 逻辑引用条目 `value`（级联父值）。 三级优先级（个人 > 租户 > 平台）解析由存储实现承载（`SqlQuerySchemeStore`）；契约见 02-4-20。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（字典为小型热配置数据）。
- **归档**：不归档（在用配置数据；审计留痕走操作日志与字段级审计）。
- **迁移**：随租户库 Alembic 迁移落地（**迁移脚本已就位**：`alembic/versions/0001_dict_and_query_scheme.py`，SQLite 实测执行通过；三库真库执行随**阶段二 后端基座**窗口）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-21 | v1 | 新建表结构（随 02-4-27 首个迁移 `0001_dict_and_query_scheme`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表设计文档组织」节配套

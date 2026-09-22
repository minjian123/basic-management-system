# sys_dict_type（字典类型表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_dict_type

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 10-字典管理 |
| 上游依据 | 需求 [02-56](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-56)、需求 [02-44](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-44)、《概要设计 · 字典管理》「核心表」节、《组件设计 · 字典字段》第 3 / 7 / 8 节、[02-4-27 详细设计](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存/设计/27_详细设计_01_字典真实取数与缓存.md) |
| ORM 模型 | `app/dict/models.py::SysDictType`（继承 `BaseModel`） |
| 状态 | 已落库（租户链迁移 `0001_dict_query_scheme`，2026-09-22；开发库由迁移 + 种子落地） |
| 相关节点 | 数据库设计总览「核心表清单总表 · 租户库」、[02-4-27 字典真实取数与缓存](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存/02_后端基座_04_跨阶段基座_27_字典真实取数与缓存.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `type` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 类型编码（唯一） |
| `name` | VARCHAR(64) | 否 | — | 类型名称（默认语言） |
| `sort` | INT | 否 | 默认 0 | 排序值 |
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
| `uq_dict_type_code_deleted_at` | 唯一 | `(type, deleted_at)` | 类型编码唯一（软删除后可复用） |
| `idx_dict_type_status_sort` | 普通 | `(status, sort)` | 运行时按状态 + 排序取类型 |
| `ix_sys_dict_type_deleted_at` | 普通 | `(deleted_at)` | 软删除过滤 |

- 无物理外键；`type_id` / `dict_item_id` / `dict_type_id` / `dict_attr_id` 为逻辑引用（同租户库），`parent_id` 逻辑引用条目 `value`（级联父值）。 类型停用后运行时取数不可见；i18n 附表见 [sys_dict_type_i18n.md](sys_dict_type_i18n.md)。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（字典为小型热配置数据）。
- **归档**：不归档（在用配置数据；审计留痕走操作日志与字段级审计）。
- **迁移**：随**租户链** Alembic 迁移落地（脚本 `alembic/versions/tenant/0001_dict_and_query_scheme.py`；2026-09-22 已落库：SQLite 开发库实测 + 三库真库演练均通过，索引名统一 `idx_*`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-21 | v1 | 新建表结构（随 02-4-27 首个迁移 `0001_dict_and_query_scheme`） | minjian |
| 2026-09-22 | v2 | 迁移脚本迁入租户链目录（`alembic/versions/tenant/0001_dict_and_query_scheme.py`），索引名统一 `idx_*` | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表设计文档组织」节配套

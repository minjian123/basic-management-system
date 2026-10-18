# sys_task（定时任务定义表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_task

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 24-任务调度 |
| 上游依据 | [需求 02-13](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-13)、《架构设计 · 任务调度》、《架构设计 · 后端基础类体系》「跨阶段基座」节 |
| ORM 模型 | `app/models/system.py::SysTask`（继承 `BaseModel`） |
| 状态 | 已设计 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[02-4 跨阶段基座](../../../项目/01_项目骨架/任务/02_后端基座/02_后端基座_04_跨阶段基座/02_后端基座_04_跨阶段基座.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `form_key` | VARCHAR(64) | 否 | `(form_key, deleted_at)` 复合唯一 | 表单标识（**多表联合判别列**；全局唯一、保存后不变） · **系统字段**：表单标识 |
| `code` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 任务代码（如 `cleanup_outbox`） · **系统字段**：代码 |
| `name` | VARCHAR(128) | 否 | 与 `deleted_at` 复合唯一 | 任务名（唯一） · **系统字段**：名称 |
| `handler` | VARCHAR(256) | 否 | — | 执行体（调用路径） |
| `cron` | VARCHAR(64) | 是 | — | 调度表达式（NULL=手动触发） |
| `enabled` | BOOLEAN | 否 | 默认 true | 是否启用 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） · **系统字段**：状态 |
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
| `uq_sys_task_name_deleted_at` | 唯一 | `(name, deleted_at)` | 任务名唯一（软删除后可复用） |
| `uq_sys_task_code_deleted_at` | 唯一 | `(code, deleted_at)` | 任务代码唯一（软删除后可复用） |
| `uq_sys_task_form_key_deleted_at` | 唯一 | `(form_key, deleted_at)` | 表单标识唯一（多表联合判别列） |

- 无物理外键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（任务定义随租户库）。
- **建表**：本阶段仅结构声明，不建表；随落库阶段补模型与表文件后自动进所属服务租户链，由启动期 / `ops.init_schema` 幂等建表落地。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（租户库；随回补阶段迁移） | minjian |
| 2026-10-11 | v2 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `code` + `status` + `parent_id`（`planned` 表只补表文件与模型，迁移随其入链时补） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

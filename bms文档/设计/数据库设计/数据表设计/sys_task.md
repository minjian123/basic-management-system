# sys_task（定时任务定义表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_task

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 24-任务调度 |
| 上游依据 | [需求 02-13](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-13)、《架构设计 · 任务调度》、《架构设计 · 后端基础类体系》「跨阶段基座」节 |
| ORM 模型 | `bms_core/models/platform/task.py::SysTask`（继承 `BaseModel`；基座共享模型，14_01 下沉） |
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
| `cron` | VARCHAR(64) | 是 | — | 调度表达式（标准 5 段；NULL=仅手动触发） |
| `args` | TEXT | 是 | — | 任务参数（JSON 对象或数组；保存时校验可解析） |
| `next_run_at` | DATETIME | 是 | 与 `status` 组复合索引 | 下次到期时间（UTC；NULL=尚未计算 / 仅手动触发） |
| `last_run_at` | DATETIME | 是 | — | 最近一次派发时间（UTC） |
| `enabled` | BOOLEAN | 否 | 默认 true | 是否启用（**与 `status` 同步写入**；读取一律以 `status` 为准） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`） · **系统字段**：状态 |
| `remark` | VARCHAR(256) | 是 | — | 备注 |
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
| `idx_sys_task_status_next_run_at` | 普通 | `(status, next_run_at)` | 到期任务扫描唯一热路径（调度器按 `status` + 到期时间取候选） |

- 无物理外键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（任务定义随租户库）。
- **建表**：已定稿并进入 platform 服务的**租户链**，由启动期建表引导 / `ops.init_schema` 幂等建表落地（`sys_table_ownership.status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（租户库；随回补阶段迁移） | minjian |
| 2026-10-11 | v2 | 系统字段对齐（02_11）：增 `form_key`（表单标识，多表联合判别列）+ `code` + `status` + `parent_id`（`planned` 表只补表文件与模型，迁移随其入链时补） | minjian |
| 2026-10-22 | v3 | ORM 模型落点迁基座共享 `bms_core/models/platform/system.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |
| 2026-10-31 | v4 | 01_02 任务调度落库：增 `args` / `next_run_at` / `last_run_at` / `remark` 四字段与 `idx_sys_task_status_next_run_at`；`enabled` 收敛为「与 `status` 同步写入、读取只认 `status`」；状态由 `planned` 转 `enabled` 进租户链 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

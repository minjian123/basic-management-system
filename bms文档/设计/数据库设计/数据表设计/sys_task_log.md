# sys_task_log（任务执行记录表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_task_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 租户库 `bms_tenant_{code}` |
| 覆盖模块 | 24-任务调度 |
| 上游依据 | [需求 02-13](../../../项目/01_项目骨架/需求/02_需求_后端基座.md#r02-13)、《架构设计 · 任务调度》、《架构设计 · 后端基础类体系》「跨阶段基座」节 |
| ORM 模型 | `bms_core/models/platform/task.py::SysTaskLog`（继承 `BaseModel`；基座共享模型，14_01 下沉） |
| 状态 | 已设计 |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[sys_task](sys_task.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `task_id` | BIGINT | 否 | `idx_sys_task_log_task_id_started_at` 首列 | 任务定义 ID（逻辑外键 → `sys_task.id`） |
| `run_id` | VARCHAR(64) | 是 | — | 本次执行标识（UUID；日志与事件串联的排障键） |
| `trigger_source` | VARCHAR(16) | 否 | 默认 `schedule` | 触发来源（`schedule` / `manual`） |
| `status` | VARCHAR(16) | 否 | — | 执行状态（`running` / `success` / `failed` / `skipped`） |
| `retry_count` | INT | 否 | 默认 0 | 已重试次数（与最终状态一并可查） |
| `started_at` | DATETIME | 是 | — | 开始时间（UTC） |
| `finished_at` | DATETIME | 是 | — | 结束时间（UTC） |
| `cost_time` | INT | 是 | — | 耗时（毫秒） |
| `result` | TEXT | 是 | — | 成功输出摘要（按 `result_max_chars` 截断） |
| `error_msg` | VARCHAR(512) | 是 | — | 错误摘要（截断 512，与死信同口径） |
| `parent_id` | BIGINT | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） · **系统字段**：上级明细 ID |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `idx_sys_task_log_task_id_started_at` | 普通 | `(task_id, started_at)` | 按任务查执行记录并按开始时间排序（覆盖单列 `task_id` 查询） |
| `idx_sys_task_log_status` | 普通 | `(status)` | 失败 / 超时记录检索（运维排查与告警） |

- 无物理外键；`task_id` 为逻辑外键（`sys_task.id`），同库。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（量级可控；如需按月分片随任务调度节点评估）。
- **归档**：按归档策略可归档（`sys_archive_policy` 落地后评估）。
- **建表**：已定稿并进入 platform 服务的**租户链**，由启动期建表引导 / `ops.init_schema` 幂等建表落地（`sys_table_ownership.status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-13 | v1 | 新建表结构（租户库；随回补阶段迁移） | minjian |
| 2026-09-22 | v2 | 索引名对齐实际库与模型元数据（`idx_task_id` → `idx_sys_task_log_task_id`） | minjian |
| 2026-10-11 | v3 | 系统字段对齐（02_11）：增 `parent_id`（上级明细 ID）（`planned` 表只补表文件与模型，迁移随其入链时补） | minjian |
| 2026-10-22 | v4 | ORM 模型落点迁基座共享 `bms_core/models/platform/system.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |
| 2026-10-31 | v5 | 01_02 任务调度落库：增 `run_id` / `trigger_source` / `retry_count` / `cost_time` / `error_msg`；`result` 收窄为成功输出摘要；`status` 取值扩 `skipped`；索引 `idx_sys_task_log_task_id` 升级为 `(task_id, started_at)` 复合并增 `idx_sys_task_log_status`；状态由 `planned` 转 `enabled` 进租户链 | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

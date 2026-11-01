# sys_job_monitor（平台作业监控投影）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_job_monitor

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`、业务域 `job`、库类别 `platform`） |
| 覆盖模块 | 08-通用能力 · 01 异步底座 · 03 作业消费者基建（作业监控投影） |
| 上游依据 | 《架构设计 · 异步作业中心》「监控与投影」节、[需求 03-3](../../../项目/08_通用能力/需求/03_需求_消息与任务.md#r03-3)、[01_03 详细设计 §4.9](../../../项目/08_通用能力/任务/01_异步底座/01_异步底座_03_作业消费者基建/设计/01_详细设计_03_作业消费者基建.md#events) |
| ORM 模型 | `bms_core/models/platform/job.py::SysJobMonitor`（继承 `BaseModel`） |
| 状态 | 已设计（随 01_03 进平台链） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)、[40-异步作业中心](../38_数据库设计_异步作业中心.md)、[sys_job](sys_job.md)、[sys_job_type](sys_job_type.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表只列业务字段。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 |
| `job_id` | DECIMAL(38,0) | 否 | 唯一（`uq_sys_job_monitor_job_id`） | 作业标识（`sys_job.id`，雪花；跨服务全局唯一） |
| `service_key` | VARCHAR(64) | 否 | — | 提供方服务键（取消 / 重试转发依据） |
| `job_type` | VARCHAR(128) | 否 | `idx_sys_job_monitor_type` | 作业类型 |
| `tenant_id` | DECIMAL(38,0) | 是 | `idx_sys_job_monitor_tenant` | 租户主键（平台链作业为 NULL） |
| `status` | VARCHAR(16) | 否 | `idx_sys_job_monitor_status` | 作业状态（六态同 `sys_job`） |
| `progress_done` | BIGINT | 否 | 默认 0 | 已完成量 |
| `progress_total` | BIGINT | 是 | — | 总量（NULL = 不确定进度） |
| `attempts` | INT | 否 | 默认 0 | 尝试次数 |
| `error` | VARCHAR(512) | 是 | — | 错误摘要（截断） |
| `submitted_at` | DATETIME | 是 | — | 提交时刻（`sys.job.submitted` 事件） |
| `started_at` | DATETIME | 是 | — | 开始时刻（`sys.job.started` 事件） |
| `finished_at` | DATETIME | 是 | — | 终态时刻（`sys.job.completed` 事件） |
| `last_event_at` | DATETIME | 否 | `idx_sys_job_monitor_status` / `idx_sys_job_monitor_type` / `idx_sys_job_monitor_tenant` | 最近事件时刻（防旧事件覆盖） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |
| 2026-11-01 | v2 | 雪花 ID 列（主键 / 逻辑外键 / `tenant_id` / 审计人 / `parent_id`）类型 `BIGINT` → `DECIMAL(38,0)`（126 位；SQLite 测试库 38 位补零 `TEXT`） | minjian |
> **投影口径**：本表由平台 `job-monitor` 消费组消费 `sys.job.submitted` / `started` / `progress` / `completed` 四条事件，按 `job_id` upsert；`last_event_at` 小于等于既有值时丢弃（乱序保护）。投影**可重建**，不可用时只影响平台统一列表，不影响作业执行与服务本地查询。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_job_monitor_job_id` | 唯一 | `(job_id)` | 一作业一行（投影 upsert 键；不并入 `deleted_at`） |
| `idx_sys_job_monitor_status` | 普通 | `(status, last_event_at)` | 按状态 / 时间筛选与保留期清理 |
| `idx_sys_job_monitor_type` | 普通 | `(job_type, last_event_at)` | 按类型筛选 |
| `idx_sys_job_monitor_tenant` | 普通 | `(tenant_id, last_event_at)` | 按租户筛选 |

- 无物理外键（跨服务作业，逻辑关联 `sys_job.id`）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库单表）。
- **保留期**：与作业记录同为 30 天；平台清理作业按 `last_event_at` 过期硬删。
- **归档**：不归档；需要长期统计时由报表域另行汇总。
- **建表**：随平台链幂等建表（`PLATFORM_MODEL_MODULES` 纳入 `bms_core.models.platform.job`；域布局 `job` 域）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-01 | v1 | 新建表结构（异步作业中心 01_03；平台监控投影） | minjian |

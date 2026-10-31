# sys_job（异步作业记录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_job

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 每服务每链各一份：服务平台库 `bms_{service}` + 服务租户库 `bms_{service}_{code}`（基础设施表，`owner=*`、`datasource=both`） |
| 覆盖模块 | 08-通用能力 · 01 异步底座 · 03 作业消费者基建（异步作业中心） |
| 上游依据 | 《架构设计 · 异步作业中心》§3~§6、《架构设计 · 任务调度》「执行归作业中心」节、[需求 03-3](../../../项目/08_通用能力/需求/03_需求_消息与任务.md#r03-3)、[01_03 详细设计 §4.1](../../../项目/08_通用能力/任务/01_异步底座/01_异步底座_03_作业消费者基建/设计/01_详细设计_03_作业消费者基建.md#data) |
| ORM 模型 | `bms_core/models/job.py::SysJob`（继承 `BaseModel`） |
| 状态 | 已设计（随 01_03 进链，启动期自动建表 / `ops.init_schema`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)、[40-异步作业中心](../38_数据库设计_异步作业中心.md)、[sys_job_error](sys_job_error.md)、[sys_job_type](sys_job_type.md)、[sys_job_monitor](sys_job_monitor.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 作业标识（接口按字符串输出；全系统唯一依赖部署 `worker_id` 唯一） |
| `job_type` | VARCHAR(128) | 否 | `idx_sys_job_type_created` | 作业类型（全局唯一形态 `{服务/业务域}.{作业名}`，与 `[[jobs]]` 声明一致） |
| `service_key` | VARCHAR(64) | 否 | — | 提供方服务键（执行者所在服务） |
| `domain_key` | VARCHAR(64) | 否 | — | 提供方业务域（取自声明，排障 / 统计用） |
| `tenant_id` | BIGINT | 是 | `idx_sys_job_tenant_status` | 租户主键（雪花 id；平台链作业为 NULL） |
| `status` | VARCHAR(16) | 否 | 默认 `queued`；`idx_sys_job_claim` / `idx_sys_job_lease` | 状态：`queued` / `running` / `succeeded` / `failed` / `canceled` / `dead` |
| `priority` | INT | 否 | 默认 0；`idx_sys_job_claim` | 租户内优先级（大者先；不跨租户抢占） |
| `payload` | TEXT | 否 | — | 负载 JSON（业务无关；版本见 `payload_version`） |
| `payload_version` | VARCHAR(16) | 否 | 默认 `1.0.0` | 负载版本（语义化版本） |
| `result` | TEXT | 是 | — | 结果 JSON 摘要（成功输出；按 `[jobs].result_max_chars` 截断） |
| `progress_done` | BIGINT | 否 | 默认 0 | 已完成量 |
| `progress_total` | BIGINT | 是 | — | 总量（NULL = 不确定进度） |
| `attempts` | INT | 否 | 默认 0 | 已执行次数（每次抢占 +1） |
| `max_attempts` | INT | 否 | 默认 3 | 最大执行次数（提交时快照自声明 / 提交覆盖） |
| `next_run_at` | DATETIME | 是 | `idx_sys_job_claim` | 下次可执行时刻（退避 / 延迟；NULL = 立即可执行） |
| `lease_owner` | VARCHAR(128) | 是 | — | 当前执行者（worker 实例标识） |
| `lease_until` | DATETIME | 是 | `idx_sys_job_lease` | 租约到期时刻（失联回收依据） |
| `last_heartbeat_at` | DATETIME | 是 | — | 最近心跳时刻（排障 / 指标） |
| `cancel_requested` | BOOLEAN | 否 | 默认 false | 是否请求取消（协作式取消信号） |
| `error` | VARCHAR(512) | 是 | — | 失败 / 死信摘要（按 `[jobs].error_max_chars` 截断） |
| `remark` | VARCHAR(256) | 是 | — | 备注（取消原因 / 运维说明） |
| `idempotency_key` | VARCHAR(128) | 是 | `uq_sys_job_idempotency` | 提交幂等键（业务方提供；同类型内唯一） |
| `started_at` | DATETIME | 是 | — | 首次开始时刻（UTC） |
| `finished_at` | DATETIME | 是 | — | 终态时刻（UTC） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |

> **物理账本口径（偏离说明）**：作业记录是运行态数据，按保留期**硬删**，不做软删除；幂等唯一约束 **不并入 `deleted_at`**（`(job_type, idempotency_key)`）——若并入，MySQL / PostgreSQL / SQLite 对 NULL 视作互异，同一幂等键可重复插入、破坏提交幂等。`deleted_at` / `version` 列随 `BaseModel` 保留，`version` 用于抢占 / 终态的条件更新。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_job_idempotency` | 唯一 | `(job_type, idempotency_key)` | 提交幂等（NULL 幂等键可多行，数据库不约束） |
| `idx_sys_job_claim` | 普通 | `(status, next_run_at, priority, id)` | 抢占热路径（状态 + 到期 + 优先级 + 插入序） |
| `idx_sys_job_lease` | 普通 | `(status, lease_until)` | 租约过期回收 |
| `idx_sys_job_type_created` | 普通 | `(job_type, created_at)` | 管理面按类型 / 时间筛选 |
| `idx_sys_job_creator` | 普通 | `(created_by, created_at)` | 按提交人筛选 |
| `idx_sys_job_tenant_status` | 普通 | `(tenant_id, status)` | 租户维度公平与统计 |

- 无物理外键；业务行级错误见 [sys_job_error](sys_job_error.md)（逻辑外键 `job_id`）。
- 公共软删除索引 `idx_sys_job_deleted_at` 由元数据命名约定生成，不在此重复列出。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（一库一表；每服务每链各自持有）。
- **保留期**：终态作业保留 30 天（`[jobs].retention_days`），由内置清理作业按 `finished_at` 硬删；`queued` / `running` 永不删除。清理时同步硬删 `sys_job_error` 行级明细。
- **归档**：不归档（运行态数据，保留期内可重试 / 排障）。
- **建表**：基础设施表随**各服务平台链**与**各服务租户链**幂等建表落地（`BASE_MODEL_MODULES` 纳入 `bms_core.models.job`；历史迁移脚本已清空，结构以模型为唯一事实源）；启动期自动建表、运维 / CI 经 `ops.init_schema`。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-01 | v1 | 新建表结构（异步作业中心 01_03；`owner=*`、双链，随作业消费者基建落库） | minjian |

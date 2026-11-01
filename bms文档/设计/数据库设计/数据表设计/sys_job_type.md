# sys_job_type（作业类型目录）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_job_type

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`、业务域 `job`、库类别 `platform`） |
| 覆盖模块 | 08-通用能力 · 01 异步底座 · 03 作业消费者基建（作业类型目录） |
| 上游依据 | 《架构设计 · 异步作业中心》「作业类型注册」节、《架构设计 · 跨产品协同》「产品自持声明」节、[需求 03-3](../../../项目/08_通用能力/需求/03_需求_消息与任务.md#r03-3)、[01_03 详细设计 §4.8](../../../项目/08_通用能力/任务/01_异步底座/01_异步底座_03_作业消费者基建/设计/01_详细设计_03_作业消费者基建.md#registry) |
| ORM 模型 | `bms_core/models/platform/job.py::SysJobType`（继承 `BaseModel`） |
| 状态 | 已设计（随 01_03 进平台链） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)、[40-异步作业中心](../38_数据库设计_异步作业中心.md)、[sys_job](sys_job.md)、[sys_job_monitor](sys_job_monitor.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表只列业务字段。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | 主键 |
| `job_type` | VARCHAR(128) | 否 | 唯一（`uq_sys_job_type`） | 作业类型（全局唯一，`{服务/业务域}.{作业名}`） |
| `service_key` | VARCHAR(64) | 否 | `idx_sys_job_type_service` | 提供方服务键（执行者所在服务） |
| `domain_key` | VARCHAR(64) | 否 | — | 提供方业务域（域布局登记） |
| `handler` | VARCHAR(256) | 否 | — | 执行者点分路径（`module:attr`；装载期只校验格式，执行期由服务 worker 解析） |
| `description` | VARCHAR(255) | 否 | — | 说明（目录展示） |
| `timeout_seconds` | INT | 否 | 默认 1800 | 单次执行超时（提示 / 监控；失联由租约兜底） |
| `max_attempts` | INT | 否 | 默认 3 | 最大执行次数 |
| `backoff_seconds` | INT | 否 | 默认 30 | 退避基数（秒） |
| `concurrency` | INT | 否 | 默认 4 | 单租户该类型并发上限 |
| `payload_version` | VARCHAR(16) | 否 | 默认 `1.0.0` | 负载版本 |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 目录状态：`enabled` / `deprecated` / `retired` |
| `source` | VARCHAR(16) | 否 | — | 声明来源：`platform` / `product` |
| `content_hash` | CHAR(64) | 否 | — | 声明要素稳定哈希（未变不写） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 继承 `BaseModel` |
| 2026-11-01 | v2 | 雪花 ID 列（主键 / 逻辑外键 / `tenant_id` / 审计人 / `parent_id`）类型 `BIGINT` → `DECIMAL(38,0)`（126 位；SQLite 测试库 38 位补零 `TEXT`） | minjian |
> **只读投影口径**：本表是 `[[jobs]]` 清单声明的**只读投影**，由平台装载写入（`content_hash` 去重），平台不手写产品记录；`status=retired` 仅停止新提交，历史作业仍可查。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_job_type` | 唯一 | `(job_type)` | 作业类型全局唯一（不并入 `deleted_at`：目录是声明投影，退役用 `status` 表达） |
| `idx_sys_job_type_service` | 普通 | `(service_key, status)` | 按服务取目录 / 启停筛选 |

- 无物理外键。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库单表）。
- **保留期**：不清理（声明投影，条数等于声明作业类型数；退役行保留供历史作业解释）。
- **归档**：不归档。
- **建表**：随平台链幂等建表（`PLATFORM_MODEL_MODULES` 纳入 `bms_core.models.platform.job`；域布局 `job` 域）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-01 | v1 | 新建表结构（异步作业中心 01_03；声明投影目录） | minjian |

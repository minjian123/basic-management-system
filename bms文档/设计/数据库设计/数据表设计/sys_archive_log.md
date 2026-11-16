# sys_archive_log（归档执行记录表）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_archive_log

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 归属业务域 | `archive`（归档管理） |
| 覆盖模块 | 31-归档管理（执行记录 / 冷化 / 清理与销毁留痕） |
| 上游依据 | [需求 07-1](../../../项目/08_通用能力/需求/07_需求_数据生命周期.md#r07-1)、《[概要设计 · 归档管理](../../概要设计/30_概要设计_归档管理.md)》§2.2 / §2.3 / §4 |
| ORM 模型 | `bms_core/models/platform/archive.py::SysArchiveLog`（继承 `BaseModel`） |
| 状态 | 待落库（已进平台链） |
| 相关节点 | [31-归档管理](../31_数据库设计_归档管理.md)、[sys_archive_policy](sys_archive_policy.md)、[sys_archive_record](sys_archive_record.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表业务字段之外不再重复展开公共字段语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | DECIMAL(38,0) | 否 | 主键，雪花 ID | ID（执行批次标识） |
| `policy_id` | DECIMAL(38,0) | 是 | — | 策略 ID（逻辑外键 `sys_archive_policy.id`，同库；销毁 / 清理记录可空） |
| `table_name` | VARCHAR(64) | 否 | — | 源逻辑表名（冷化 / 销毁记录沿用所属策略的表名） |
| `batch_key` | VARCHAR(160) | 否 | 与 `deleted_at` 复合唯一 | 批次幂等键（`{policy_id}:{target}:{run_id}` 或 `{policy_id}:minio:{tenant}:{run_id}`） |
| `target` | VARCHAR(16) | 否 | — | 动作 / 目标（`archive_db` / `minio` / `cleanup` / `destroy`） |
| `tenant_id` | DECIMAL(38,0) | 是 | — | 租户主键（冷化文件按租户分文件时记录；平台级批次为空） |
| `archived_count` | INT | 否 | 默认 0 | 本次处理条数（归档 / 冷化 / 销毁条数） |
| `file_key` | VARCHAR(512) | 是 | — | 冷化数据对象 key（`target=minio`） |
| `status` | VARCHAR(16) | 否 | 默认 `running` | 状态（`running` / `success` / `failed` / `skipped`） |
| `cost_time` | INT | 是 | — | 耗时（毫秒） |
| `started_at` | DATETIME | 否 | — | 开始时间（UTC） |
| `finished_at` | DATETIME | 是 | — | 结束时间（UTC） |
| `error_msg` | VARCHAR(512) | 是 | — | 失败摘要（截断 512） |
| `detail` | TEXT | 是 | — | 明细 JSON（时间窗 / 分片月份 / 链头尾 / sha256 / 处置原因） |
| `retention_until` | DATETIME | 是 | — | 冷化文件保留到期时刻（UTC；清理判定依据） |
| `disposed_at` | DATETIME | 是 | — | 文件处置时刻（UTC；清理 / 销毁后回填，幂等依据） |
| `dispose_type` | VARCHAR(16) | 是 | — | 处置类型（`cleanup` 到期清理 / `destroy` 合规销毁） |
| `operator_id` | DECIMAL(38,0) | 是 | — | 手动触发 / 销毁操作人（定时任务为空） |
| `created_at` / `created_by` / `updated_at` / `updated_by` / `deleted_at` / `version` | — | — | 公共字段 | 审计 / 软删除 / 乐观锁（语义见《数据规范》） |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_archive_log_batch_key` | 唯一 | `(batch_key, deleted_at)` | 批次幂等键唯一（软删后可重建） |
| `idx_sys_archive_log_policy_started` | 普通 | `(policy_id, started_at)` | 按策略看执行历史 |
| `idx_sys_archive_log_status` | 普通 | `(status)` | running 超时回收 / 失败巡检 |
| `idx_sys_archive_log_dispose` | 普通 | `(target, retention_until, disposed_at)` | 过期冷化文件清理扫描 |

- 无物理外键；`policy_id` 为逻辑外键（`sys_archive_policy.id`，同库）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（执行批次量级小）。
- **归档**：本表不归档（执行留痕，随平台库备份保留）。
- **保留**：不设硬删入口；审计留痕长期保留。
- **建表**：进入 platform 服务**平台链**，由启动期建表 / `ops.init_schema` 幂等建表（`status = enabled`）。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-11-16 | v1 | 新建（14_01 归档管理）：两段式归档 / 冷化 / 清理 / 销毁的统一执行记录 | minjian |

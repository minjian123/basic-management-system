# sys_collaboration_usage（消费方使用声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_collaboration_usage

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | [需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysCollaborationUsage`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_collaboration](sys_collaboration.md) |

- **语义**：一行 = 某产品**作为消费方**对某外部能力的使用声明（降级策略），第八类记录；声明方即消费方。
- **写入归属**：写方 = platform 服务（注册通道）。读方 = 能力取用（`call_capability` 按声明降级）、使用声明校验。
- **用途**：取代原先「使用声明写在清单里由各进程各自装载」的做法——现在声明与视图同一来源，跨进程一致。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `product_key` | VARCHAR(32) | 否 | 与 `capability_name`、`deleted_at` 复合唯一 | 声明方（＝消费方）产品键 |
| `capability_name` | VARCHAR(128) | 否 | 同上 | 被消费能力名（逻辑外键 → [sys_collaboration](sys_collaboration.md).`name`） |
| `degrade` | VARCHAR(16) | 否 | 默认 `none` | 降级模式（`none` / `empty` / `stale`；`stale` 当前拒收） |
| `reason` | VARCHAR(255) | 是 | — | 降级理由（`degrade != none` 必填） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_collaboration_usage_owner_name_deleted_at` | 唯一 | `(product_key, capability_name, deleted_at)` | 同一消费方对同一能力只允许一条声明 |
| `idx_sys_collaboration_usage_capability` | 普通 | `(capability_name, status)` | 反向查询：某能力被哪些消费方声明使用 |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级为「消费方数 × 被消费能力数」）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入（产品上报 + 平台自身清单）；**校验**：被消费能力必须已在 [sys_collaboration](sys_collaboration.md) 注册，写 / 强一致能力不得声明降级。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

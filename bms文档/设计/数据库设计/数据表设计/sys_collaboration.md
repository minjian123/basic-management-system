# sys_collaboration（跨产品能力声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_collaboration

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | 《[架构设计 · 跨产品协同](../../../设计/架构设计/38_架构设计_子系统_跨产品协同.md)》§4 ~ §7、[需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysCollaboration`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_collaboration_usage](sys_collaboration_usage.md)、[sys_capability_grant](sys_capability_grant.md)、[sys_module](sys_module.md) |

- **语义**：一行 = 一个跨产品**能力声明**（第五类记录），由提供方产品注册写入；平台据此派生能力视图、入站授权基线与前端命名空间。
- **写入归属**：写方 = platform 服务（注册通道；来源为产品上报或平台自身清单）。读方 = `resolve_capability`（消费方取址）、授权基线重算（`02_04`）、目录出口。
- **不按租户**：能力是平台级全局声明，不落 `tenant_id`。
- **退役不删行**：本次全量注册未出现的能力置 `status = retired`，历史保留（重启与回滚可追）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `name` | VARCHAR(128) | 否 | 全局唯一（含 `deleted_at`） | 能力名（`{产品}.{业务域}.{能力}`，全局唯一，与提供方实现标识解耦） |
| `product_key` | VARCHAR(32) | 否 | 索引 | 声明方产品键（提供方；注册只能写自己名下） |
| `domain` | VARCHAR(64) | 否 | 索引 | 提供方**业务域**标识（须在域布局登记；非服务键） |
| `kind` | VARCHAR(16) | 否 | — | 访问面类别（`read` / `write` / `txn-branch` / `dataset` / `codes`） |
| `contract_version` | VARCHAR(16) | 否 | semver | 随提供方服务契约版本（主版本须与服务行兼容） |
| `path` | VARCHAR(255) | 是 | — | 访问面路径模板（可含 `{param}` 占位；`codes` 类为 NULL） |
| `branch_id` | VARCHAR(16) | 是 | 长度 ≤ 16 | 事务分支标识（`txn-branch` 必填；一经确定不随版本漂移） |
| `branch_op` | VARCHAR(128) | 是 | — | 事务分支动作名（`txn-branch` 必填） |
| `data_source_key` | VARCHAR(64) | 是 | — | 关联数据源键（`dataset` 必填，指向 [sys_data_source](sys_data_source.md)） |
| `permission_codes` | TEXT | 是 | JSON 数组 | 业务码 / 权限码集合（`codes` 类必填） |
| `frontend_prefix` | VARCHAR(32) | 是 | — | 前端命名空间域段（非 `codes` 类须有值） |
| `default_consumers` | TEXT | 是 | JSON 数组 | 默认分配消费方（服务键 / 产品键；前端应用不入列） |
| `replacement` | VARCHAR(128) | 是 | — | 替代能力名（`deprecated` 态必填） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled` / `deprecated` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 声明要素稳定哈希（内容未变不写；变更检测） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 不做物理外键：`product_key` 指向 [sys_product](sys_product.md)、`data_source_key` 指向 [sys_data_source](sys_data_source.md)，均为登记类逻辑外键，只持值。
- `retired_at` 不单列：退役时间取 `updated_at` + `status = retired`（与软删除语义区分：退役是「本次未声明」，软删除是「误录清理」）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_collaboration_name_deleted_at` | 唯一 | `(name, deleted_at)` | 能力名全局唯一（软删后可重录） |
| `idx_sys_collaboration_product_status` | 普通 | `(product_key, status)` | 按声明方取全量（注册对账 / 整体退役） |
| `idx_sys_collaboration_domain_status` | 普通 | `(domain, status)` | 按业务域取（授权视图 provider 维度预热） |

- `branch_id` 不建唯一索引：唯一性由装载/注册校验按「同域可多、跨域不可重复」判定（DB 唯一会误伤同域多能力）。
- `frontend_prefix` 不索引（只随能力整行读取）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻；行数量级为「产品数 × 域内能力数」）。
- **归档**：不归档（退役行保留）。
- **建表**：随 `platform:platform` 链幂等建表（表集经表归属登记派生），运维 / CI 经 `ops.init_schema`。
- **数据来源**：产品启动注册（`PUT /api/v1/internal/declarations`）与平台自身清单注册；**不存在其它写入口**。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

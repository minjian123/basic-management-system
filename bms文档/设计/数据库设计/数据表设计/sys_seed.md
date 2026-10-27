# sys_seed（产品种子声明）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_seed

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`） |
| 覆盖模块 | 07B-跨产品协同（产品自注册通道） |
| 上游依据 | [需求 02-3](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-3)、[需求 02-6](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-6)、《[02_06 详细设计](../../../项目/07B_跨产品协同/任务/02_协同基座/02_协同基座_06_产品自注册通道/设计/01_详细设计_06_产品自注册通道.md)》§3.1 |
| ORM 模型 | `bms_core/models/platform/declaration.py::SysSeed`（继承 `BaseModel`） |
| 状态 | 待落库（随平台链自动建表 / `ops.init_schema`） |
| 相关表 | [sys_module](sys_module.md) |

- **语义**：一行 = 一个默认数据种子声明（第六类记录）；声明 = 模块路径 + 入口 + 依赖顺序，内容归产品仓。
- **写入归属**：写方 = platform 服务（注册通道）。读方 = 种子编排（`02_03`，一个 XA 全局事务内串行执行）。
- **只存声明不存数据**：种子数据本身由产品入口函数写入，本表不承载种子内容。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`，下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `name` | VARCHAR(64) | 否 | 全局唯一（含 `deleted_at`） | 种子名（与平台自身种子共用命名空间） |
| `product_key` | VARCHAR(32) | 否 | 索引 | 声明方产品键（执行身份来源） |
| `service` | VARCHAR(64) | 否 | — | 执行服务键（决定 XA 分支参与方） |
| `db_key` | VARCHAR(64) | 否 | — | 目标库键（支持 `{tenant}` 占位） |
| `module` | VARCHAR(255) | 否 | — | 入口模块点分路径 |
| `entry` | VARCHAR(64) | 否 | — | 入口函数名（签名 `async def entry(session, args) -> None`） |
| `op` | VARCHAR(64) | 是 | 默认同 `name` | 分支操作名（编排器登记用） |
| `after` | TEXT | 是 | JSON 数组 | 依赖的种子名（拓扑排序） |
| `description` | VARCHAR(255) | 是 | — | 说明（审计读用） |
| `tables` | TEXT | 是 | JSON 对象 | 目标表 → 自然键（编排器做执行前后对比、逐项统计） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `retired`） |
| `content_hash` | CHAR(64) | 否 | 索引 | 内容稳定哈希（未变不写） |
| `created_at` / `created_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 创建时间 / 创建人 |
| `updated_at` / `updated_by` | DATETIME / BIGINT | 否 / 是 | 审计 | 更新时间 / 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除 | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_seed_name_deleted_at` | 唯一 | `(name, deleted_at)` | 种子名全局唯一（平台种子与产品种子同空间） |
| `idx_sys_seed_product_status` | 普通 | `(product_key, status)` | 按声明方取全量（注册对账 / 整体退役） |

- `after` 的引用完整性由编排器拓扑排序时校验（不建物理外键）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片 / 归档**：均不（行数量级为「产品数 × 种子数」）。
- **建表**：随 `platform:platform` 链幂等建表；运维 / CI 经 `ops.init_schema`。
- **数据来源**：注册通道写入；执行仍由 `python -m ops.seed_platform --tenant <租户>` 统一编排（`02_03`）。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

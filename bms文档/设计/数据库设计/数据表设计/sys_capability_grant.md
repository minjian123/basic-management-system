# sys_capability_grant（能力分配授权）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_capability_grant

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`；能力登记与授权同域） |
| 覆盖模块 | 07B-跨产品协同（能力分配） |
| 上游依据 | 《[架构设计 · 跨产品协同](../../../设计/架构设计/38_架构设计_子系统_跨产品协同.md)》「能力分配与授权」节、[需求 02-4](../../../项目/07B_跨产品协同/需求/02_需求_协同基座.md#r02-4)、《[跨产品协同登记清单](../../../跨产品协同登记清单.md)》§4 |
| ORM 模型 | `bms_core/models/platform/capability_grant.py::SysCapabilityGrant`（继承 `BaseModel`；07B `02_04` 已落地） |
| 状态 | 已落库（归 `platform_registry` 域 × 归属部署单元 `platform`；建表随平台链自动建表 / `ops.init_schema`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_module](sys_module.md)、[sys_product](sys_product.md) |

- **语义**：一条记录 = 一个「能力 × 消费方」的**有效授权**；有有效授权即合法（直连或经平台中转均可），无授权即越界。
- **写入归属**：写方 = platform 服务（① 装载产品声明中的默认消费方；② 管理面人工授予 / 撤销）。读方 = 入站校验（谁能调我）、出站 scope（我能调谁）、监控归因（按「调用方 × 能力」）。
- **不按租户**：服务实例跨租户共享、授权是平台级全局数据，**不落 `tenant_id`**；与 `sys_tenant_module`（按租户）语义不同。
- **撤销不删行**：撤销只切 `status` 与 `revoked_at`，保留授权历史；软删除仅用于误录清理。
- **有效期**：`expire_at` 非空且已过期视为**无效**（运行时判定，不依赖定时任务），供排障 / 迁移窗口的临时授权使用。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `capability_name` | VARCHAR(128) | 否 | 与 `consumer_key`、`deleted_at` 复合唯一 | 能力名（跨库逻辑外键 → 产品自持声明中的 `collaborations[].name`，只持值） |
| `consumer_key` | VARCHAR(64) | 否 | 同上 | 消费方标识（服务键或产品键；写入前经服务目录校验「已登记」） |
| `source` | VARCHAR(16) | 否 | 默认 `declared` | 来源（`declared` 随产品声明装载 / `manual` 管理面人工授予） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` 有效 / `disabled` 已撤销） |
| `expire_at` | DATETIME | 是 | — | 有效期截止（UTC；NULL = 长期有效；过期视为无效） |
| `granted_by` | BIGINT | 是 | — | 授予人（`sys_user.id`；声明装载为 NULL） |
| `granted_at` | DATETIME | 是 | — | 授予时间（UTC） |
| `revoked_at` | DATETIME | 是 | — | 最近撤销时间（UTC；重新授予时清空） |
| `note` | VARCHAR(255) | 是 | — | 授予理由（人工授予时建议填写；声明装载写默认说明） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 关联表口径：**不落 `form_key` / `parent_id`**（关系表判定同 `sys_tenant_module`）。
- **不做物理外键**：`capability_name` 指向产品清单声明、`consumer_key` 指向 `sys_module.code`，均为**跨源逻辑外键，只持值**（声明不落库，无法建物理约束）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_capability_grant_capability_consumer_deleted_at` | 唯一 | `(capability_name, consumer_key, deleted_at)` | 一能力一消费方一条有效记录（撤销后重新授予走同一行；软删除后可重录） |
| `idx_sys_capability_grant_consumer_status` | 普通 | `(consumer_key, status)` | 出站查询：某消费方被授权的全部能力（派生 scope / 直连判定） |
| `idx_sys_capability_grant_capability_status` | 普通 | `(capability_name, status)` | 入站查询：某能力的全部授权消费方（派生白名单） |

- 不建 `(status)` 单列索引（选择性低，且均随上述复合索引使用）。
- `expire_at` 不建索引（按能力 / 消费方整取后内存判定，行数受「能力数 × 消费方数」约束）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（授权历史随行保留；撤销不删行）。
- **建表**：随 **`platform:platform` 链**幂等建表落地（表集经表归属登记派生）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。
- **数据来源**：启动装载时按产品声明 UPSERT `source=declared` 行；人工授予写 `source=manual`；**声明不覆盖人工撤销**（优先级口径见 `02_04` 详细设计）。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

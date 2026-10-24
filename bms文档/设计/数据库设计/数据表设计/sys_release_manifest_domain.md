# sys_release_manifest_domain（发布清单·域明细）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_release_manifest_domain

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 业务域 | 平台注册与目录 |
| 覆盖模块 | 07C-产品与服务划分（发布对账） |
| 上游依据 | 《[架构设计 · 产品与服务划分](../../../设计/架构设计/39_架构设计_子系统_产品与服务划分.md)》「发布与版本」节、[需求 04-1](../../../项目/07C_产品与服务划分/需求/04_需求_发布与迁移.md#r04-1) |
| ORM 模型 | `bms_core/models/platform/release_manifest.py::SysReleaseManifestDomain`（继承 `BaseModel`；随 `04_01` 落地） |
| 状态 | 待落库（设计已定；建表随 `platform:platform` 链） |
| 相关节点 | [sys_release_manifest](sys_release_manifest.md)、[数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」 |

- **语义**：一次发布中，**每个业务域一行**——记录该域本次发布的表结构 revision、服务版本与契约版本。
- **回滚的最小信息单元**：回滚时按明细逐域回退到「上一次发布的版本」，因此明细必须完整（漏一行就会有一个域回不去）。
- **三方一致校验的载体**：`schema_revision` / `service_version` / `contract_version` 三者在本表同时落盘，发布前的对账结论与发布后的实际值可对照。
- **不落能力清单**：能力契约版本并入 `contract_version`（07B 口径），不单列。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `manifest_id` | BIGINT | 否 | 与 `domain_key`、`deleted_at` 复合唯一 | 发布清单主键（同库逻辑外键 → `sys_release_manifest.id`，只持值） |
| `domain_key` | VARCHAR(64) | 否 | 同上 | 业务域标识（跨库逻辑外键 → 业务域清单，只持值） |
| `schema_revision` | VARCHAR(64) | 是 | — | 本次发布后该域「表结构变更记录表」的 revision（无表结构的域为空） |
| `service_version` | VARCHAR(32) | 否 | — | 承载该域的服务版本 |
| `contract_version` | VARCHAR(32) | 否 | — | 该域所属服务的契约版本（能力契约随服务契约） |
| `status` | VARCHAR(16) | 否 | 默认 `released` | 状态（`released` / `rolled_back`） |
| `note` | VARCHAR(255) | 是 | — | 说明（如“本次仅契约兼容变更”） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 关联表口径：**不落 `form_key` / `parent_id`**。
- **不做物理外键**：`manifest_id` 为同库逻辑外键只持值（与项目"禁物理外键"口径一致）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_release_manifest_domain_manifest_domain_deleted_at` | 唯一 | `(manifest_id, domain_key, deleted_at)` | 一次发布内一域一行 |
| `idx_sys_release_manifest_domain_domain_created` | 普通 | `(domain_key, created_at)` | 查某域的发布历史（回滚目标定位） |

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片。
- **归档**：不归档（发布历史长期保留；量级 = 发布次数 × 域数）。
- **建表**：随 **`platform:platform` 链**幂等建表落地。
- **写入方式**：与主表同事务写入；回滚时新增一行（`status=rolled_back`）而非修改原行，保留历史。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

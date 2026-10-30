# sys_release_manifest（发布清单·主）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_release_manifest

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属部署单元 `platform`） |
| 业务域 | 平台注册与目录（`platform_registry`；与拓扑、能力授权同域） |
| 覆盖模块 | 07C-产品与服务划分（发布对账） |
| 上游依据 | 《[架构设计 · 产品与服务划分](../../../设计/架构设计/39_架构设计_子系统_产品与服务划分.md)》「发布与版本」节、[需求 04-1](../../../项目/07C_产品与服务划分/需求/04_需求_发布与迁移.md#r04-1) |
| ORM 模型 | `bms_core/models/platform/release_manifest.py::SysReleaseManifest`（继承 `BaseModel`；随 `04_01` 落地） |
| 状态 | 已落库（2026-10-30，随 `04_01`） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_release_manifest_domain](sys_release_manifest_domain.md)、[sys_tenant_topology](sys_tenant_topology.md) |

- **语义**：一次发布 = 一行；记录「某个部署单元（某租户范围内）这一次发布包含了哪些域、各自到哪个版本」，是**回滚的原子单位**与版本对账的依据。
- **发布单元 = 部署单元**：合并部署时一次发布覆盖多域，故清单必须按单元登记，而不是按域。
- **作用范围**：`tenant_scope = 0` 表示全局（默认拓扑下的单元）；非 0 表示该租户专属单元，用于按租户分实例的形态。
- **不可变**：发布记录写入后不修改（回滚另起一行 `status=rolled_back` 的新记录指向原清单），保证历史可追溯。
- **与记录表的关系**：明细中的 `schema_revision` 取自各域「表结构变更记录表」的当前值，是发布后的快照；回滚时按它回退。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `unit_key` | VARCHAR(64) | 否 | 与 `tenant_scope`、`manifest_version`、`deleted_at` 复合唯一 | 部署单元标识（跨库逻辑外键 → `sys_tenant_topology.unit_key`，只持值） |
| `tenant_scope` | BIGINT | 否 | 同上；默认 `0` | 作用范围（`0` = 全局 / 默认拓扑；非 0 = 该租户 ID） |
| `manifest_version` | INT | 否 | 同上；默认 1 | 发布批次号（同一单元同一范围内递增，不允许回退） |
| `topology_version` | INT | 否 | — | 本次发布对应的拓扑版本（取自 `sys_tenant_topology`） |
| `status` | VARCHAR(16) | 否 | 默认 `released` | 状态（`released` 已发布 / `rolled_back` 已回滚 / `failed` 发布失败） |
| `released_at` | DATETIME | 否 | — | 发布时间（UTC） |
| `released_by` | BIGINT | 是 | — | 发布人（`sys_user.id`；自动化发布为 NULL） |
| `rolled_back_from` | BIGINT | 是 | — | 回滚来源清单主键（本行由回滚产生时填写，指向被回滚的那次发布） |
| `note` | VARCHAR(255) | 是 | — | 说明（发布摘要 / 回滚原因） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 关联表口径：**不落 `form_key` / `parent_id`**（关系表判定同 `sys_tenant_module`）。
- 明细不落主表：域级版本放在 [sys_release_manifest_domain](sys_release_manifest_domain.md)，避免用 JSON 大字段（《数据库开发规范》大字段独立成表口径）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_release_manifest_unit_scope_version_deleted_at` | 唯一 | `(unit_key, tenant_scope, manifest_version, deleted_at)` | 一单元一范围一版本一行；版本不许重复 |
| `idx_sys_release_manifest_unit_released_at` | 普通 | `(unit_key, released_at)` | 查某单元最近发布（回滚目标定位） |

- 不建 `(status)` 索引（选择性低，随上表整取）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（发布历史是审计与回滚依据，长期保留）。
- **建表**：随 **`platform:platform` 清单**幂等建表落地（域化后归 `platform_registry:platform`）（表集经表归属登记派生）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`。
- **写入方式**：发布流程在结构与数据变更全部成功后写入主表 + 明细（同一事务）；失败则写 `status=failed` 的一行（便于排查），不写明细。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

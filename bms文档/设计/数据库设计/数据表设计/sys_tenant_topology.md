# sys_tenant_topology（租户部署拓扑）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant_topology

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_platform`（归属服务 `platform`） |
| 业务域 | 平台注册与目录（`platform-registry`；与能力登记、能力授权同域） |
| 覆盖模块 | 07C-产品与服务划分（租户拓扑） |
| 上游依据 | 《[架构设计 · 产品与服务划分](../../../设计/架构设计/39_架构设计_子系统_产品与服务划分.md)》「部署拓扑」「标识与库派生」节、[需求 02-1](../../../项目/07C_产品与服务划分/需求/02_需求_拓扑机制.md#r02-1) |
| ORM 模型 | `bms_core/models/platform/tenant_topology.py::SysTenantTopology`（继承 `BaseModel`；随 `02_01` 落地） |
| 状态 | 待落库（设计已定；建表随 `platform:platform` 链） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_tenant](sys_tenant.md)、[sys_capability_grant](sys_capability_grant.md) |

- **语义**：一条记录 = 「某租户的某业务域由哪个部署单元承载」；库由部署单元派生，不在本表重复存库名。
- **平台级默认拓扑**：`tenant_id = 0` 表示**默认拓扑**（未单独配置的租户沿用）；租户一旦有自身记录则**完全覆盖**默认（不做逐域合并）。
- **发布时生效**：一次发布内写入的所有行使用同一个 `topology_version`；运行时解析只取该租户**最大版本**的行集合，故写入必须整批替换而非逐行改。
- **变更留历史**：当前版本 = **未软删除**的行；被替换的行软删除保留（可查、不参与解析），重大变更同时进审计链。
- **不落库名**：库随部署单元，按 `{prefix}_{unit}` / `{prefix}_{unit}_{db_basis}` 派生，避免拓扑表成为库名的第二份事实源。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `tenant_id` | BIGINT | 否 | 与 `domain_key`、`deleted_at` 复合唯一 | 租户主键（同库逻辑外键 → `sys_tenant.id`，只持值）；`0` = 平台级默认拓扑 |
| `domain_key` | VARCHAR(64) | 否 | 同上 | 业务域标识（跨库逻辑外键 → 业务域清单，只持值；写入前校验已登记） |
| `unit_key` | VARCHAR(64) | 否 | — | 部署单元标识（同一租户内由本表定义；写入前校验命名合法） |
| `topology_version` | INT | 否 | 默认 1 | 拓扑版本（同租户同版本号；发布时整批写入，解析取最大版本） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` 承载中 / `disabled` 已停用） |
| `note` | VARCHAR(255) | 是 | — | 说明（如“按业务重心拆分”“模板：分组型”） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 关联表口径：**不落 `form_key` / `parent_id`**（关系表判定同 `sys_tenant_module`）。
- **不做物理外键**：`domain_key` 指向业务域清单（代码/文档声明，不落库），`tenant_id` 为同库逻辑外键只持值。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_tenant_topology_tenant_domain_deleted_at` | 唯一 | `(tenant_id, domain_key, deleted_at)` | 一租户一域一条当前映射（禁止双活）；同时承担按租户整取 |
| `idx_sys_tenant_topology_tenant_unit` | 普通 | `(tenant_id, unit_key)` | 反查：某单元承载哪些业务域（部署编排用） |

- 不建 `(topology_version)` 索引：版本按租户整取后在内存比较。
- `status` 不建单列索引（选择性低，随上表整取）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（当前版本为未删除行；被替换行软删除保留，量级受租户数与域数约束）。
- **建表**：随 **`platform:platform` 清单**幂等建表落地（域化后归 `platform-registry:platform`）（表集经表归属登记派生）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。
- **写入方式**：一次发布内**整批替换**某租户的行集合（旧行删除、新行写入、`topology_version` 递增），保证解析只看到完整版本。

> 本文档依《[文档生成规范](../../../规范/文档生成规范.md)》与《[数据库开发规范](../../../规范/数据库开发规范.md)》编写

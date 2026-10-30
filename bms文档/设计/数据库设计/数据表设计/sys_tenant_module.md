# sys_tenant_module（租户-模块关系）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant_module

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_tenant`（归属部署单元 `tenant`，与 `sys_tenant` 同库） |
| 覆盖模块 | 26-租户管理 |
| 上游依据 | 《架构设计 · 模块注册》3.4 租户模块开关、《架构设计 · 多租户路由》「租户开通/停用」节、[需求 07-7](../../../项目/07_RBAC基础模块/需求/04_需求_租户与平台超管.md#r07-7) |
| ORM 模型 | `bms_core/models/tenant/tenant_module.py::SysTenantModule`（继承 `BaseModel`；基座共享模型，14_01 下沉） |
| 状态 | 已落库（随 `tenant:platform` 链幂等建表，2026-10-20） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_tenant](sys_tenant.md)、[26-租户管理](../26_数据库设计_租户管理.md) |

- **语义**：租户开通的模块清单与启停状态；一租户 × 一模块一行。
- **写入归属**：写方 = tenant 服务（开通写入清单、运营期开关）；读方 = 租户模块门禁（经内部契约）与租户管理页。
- **基础模块**：平台域基础能力（foundation + capability + `org`）开通时自动写 `enabled` 行；产品模块仅开通向导勾选才写。**未勾选 = 无行 = 未开通**。
- **停用不删行**：开关只切 `status` 并更新 `opened_at` / `closed_at`，存量数据与进行中流程不受影响。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `tenant_id` | BIGINT | 否 | 与 `deleted_at` 复合唯一（`uq_sys_tenant_module_tenant_module_key_deleted_at`） | 租户主键（同库逻辑外键 → `sys_tenant.id`，只持值） |
| `module_key` | VARCHAR(32) | 否 | 同上 | 模块标识（跨库逻辑外键 → `sys_module.code`，只持值；写入前经目录快照校验「已注册且启用」） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` 已开通 / `disabled` 已停用） |
| `opened_by` | BIGINT | 是 | — | 开通操作人（平台租户 `sys_user.id`；引导 / 系统开通为 NULL） |
| `opened_at` | DATETIME | 是 | — | 最近开通时间（UTC） |
| `closed_at` | DATETIME | 是 | — | 最近停用时间（UTC） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 关联表口径：**不落 `form_key` / `parent_id`**（《数据库开发规范》§3.1 关联表判定，同 `sys_tenant_module` 一类的多对多/关系表）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_tenant_module_tenant_module_key_deleted_at` | 唯一 | `(tenant_id, module_key, deleted_at)` | 一租户一模块一行（软删除后可重挂）；同时承担按租户取清单的索引 |

- 无物理外键；`tenant_id` 指向同库 `sys_tenant.id`，`module_key` 指向 platform 平台库 `sys_module.code`（跨库逻辑外键，只持值）。
- 不另建 `(tenant_id)` 普通索引（唯一索引左前缀已覆盖）。
- `status` 不建索引（清单按租户整取，行数受模块数量约束）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（租户模块生命周期数据；停用不删行）。
- **建表**：随 **`tenant:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-20 | v1 | 新建表结构（任务 `04_01`：租户开通清单与模块开关；PLANNED → ENABLED） | minjian |
| 2026-10-22 | v2 | ORM 模型落点迁基座共享 `bms_core/models/tenant/tenant_module.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

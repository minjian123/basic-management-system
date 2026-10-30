# sys_tenant_quota（租户配额）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_tenant_quota

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台服务库 `bms_tenant`（归属部署单元 `tenant`，与 `sys_tenant` 同库） |
| 覆盖模块 | 26-租户管理 |
| 上游依据 | 《架构设计 · 多租户路由》「配额管理」节、[需求 07-7](../../../项目/07_RBAC基础模块/需求/04_需求_租户与平台超管.md#r07-7) |
| ORM 模型 | `bms_core/models/tenant/tenant_quota.py::SysTenantQuota`（继承 `BaseModel`；基座共享模型，14_01 下沉） |
| 状态 | 已落库（随 `tenant:platform` 链幂等建表，2026-10-20） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[sys_tenant](sys_tenant.md)、[26-租户管理](../26_数据库设计_租户管理.md) |

- **语义**：租户配额（一租户 × 一维度一行），`limit_value` 为限额、`used_value` 为实时用量。
- **写入归属**：写方 = tenant 服务（开通播种默认值、平台超管配置限额、内部契约实时占用 / 释放）；读方 = 租户管理页与调用方。
- **无行 = 不限制**：未配置配额的租户（含平台租户）不做拦截，便于引导期与既有部署平滑。
- **计数口径**：`user_count` 为用户数、`storage_bytes` 为字节、`open_calls` 为当日开放接口调用量（日重置随开放接口平台，当前 used 恒 0）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 · **系统字段**：ID |
| `tenant_id` | BIGINT | 否 | 与 `deleted_at` 复合唯一（`uq_sys_tenant_quota_tenant_quota_key_deleted_at`） | 租户主键（同库逻辑外键 → `sys_tenant.id`，只持值） |
| `quota_key` | VARCHAR(32) | 否 | 同上 | 配额维度：`user_count` / `storage_bytes` / `open_calls` |
| `limit_value` | BIGINT | 否 | — | 限额（`open_calls` 为日限额；`storage_bytes` 单位字节） |
| `used_value` | BIGINT | 否 | 默认 0 | 已用量（原子增量维护；释放时下限为 0） |
| `parent_id` | BIGINT | 是 | — | 上级明细 ID（自引用同表 `id`；本表无层级，按明细系统字段口径保留） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间（NULL=未删） |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 明细表口径：带 `tenant_id`（主表 ID）→ 落 `parent_id` 系统字段、不落 `form_key`。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_tenant_quota_tenant_quota_key_deleted_at` | 唯一 | `(tenant_id, quota_key, deleted_at)` | 一租户一维度一行（软删除后可重挂）；左前缀覆盖按租户取配额 |

- 无物理外键；`tenant_id` 指向同库 `sys_tenant.id`（同库逻辑外键，只持值）。
- 不另建普通索引（行数 = 租户数 × 3，按租户整取）。

## 4. 分片 / 归档 / 建表 <a id="storage"></a>

- **分片**：不分片（平台库常驻）。
- **归档**：不归档（配额为运营期实时数据）。
- **建表**：随 **`tenant:platform` 链**幂等建表落地（表集经表归属登记派生；**历史迁移脚本已随 06_05 清空**，结构以模型为唯一事实源）；启动期按服务表集自动建表、运维 / CI 经 `ops.init_schema`；开发 / 演示库一律删库重建。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-10-20 | v1 | 新建表结构（任务 `04_01`：用户数 / 存储 / 开放接口调用量三配额；PLANNED → ENABLED） | minjian |
| 2026-10-22 | v2 | ORM 模型落点迁基座共享 `bms_core/models/tenant/tenant_quota.py`（14_01 整包下沉；表名 / 字段 / 索引 / 归属不变） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

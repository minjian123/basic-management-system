# sys_user_identity（SSO 全局身份映射）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_user_identity

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | 平台库 `bms_platform`（归属服务 `identity`） |
| 覆盖模块 | 27-身份认证SSO |
| 上游依据 | [需求 02-2](../../../项目/06_认证与安全/需求/02_需求_SSO与身份联邦.md#r02-2)、《概要设计 · 身份认证SSO》「数据模型与表设计」节、《架构设计 · 认证与会话》§4 |
| ORM 模型 | `bms_identity/models/user_identity.py::SysUserIdentity`（继承 `BaseModel`） |
| 状态 | 已落库（`identity:platform` 链迁移 `0001_sys_user_identity`，2026-09-27） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 平台库」、[概要 26-身份认证SSO](../../概要设计/26_概要设计_身份认证SSO.md) |

- **落平台库的依据**：SSO 回调在**租户定位前**即需按外部身份命中映射（由映射行反查租户 / 用户），故全局映射放平台库、不随租户库分片（需求 02-2 口径）。
- **写路径归属**：JIT 建号与映射写路径归 **02_02**；02_01 仅落表 + 读路径（命中查询）。

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `idp_key` | VARCHAR(160) | 否 | 与 `external_id`、`deleted_at` 复合唯一 | 映射键 = `{tenant_code}:{provider_key}`（跨租户共享 IdP 不冲突、issuer 变更不破坏映射） |
| `external_id` | VARCHAR(255) | 否 | 同上 | 外部身份主体（OIDC 取 `sub`；CAS / 企微 / 钉钉取各自主体标识） |
| `tenant_id` | VARCHAR(64) | 否 | — | 租户编码（需求字段名口径；与 `sys_tenant.code` 值传递） |
| `user_id` | BIGINT | 否 | — | 用户 ID（跨服务逻辑外键 → org 服务 `sys_user.id`，只持值） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- `(idp_key, external_id)` 唯一约束是并发首次登录防重复建号的事实源（02_02 写路径在唯一冲突时回读命中，不产生重复用户）。
- `idp_key` 含租户前缀：同一 IdP 实例被多租户共享时，各租户外部身份互不串号；无租户前缀的裸 provider key 不允许落库。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_user_identity_idp_external_deleted_at` | 唯一 | `(idp_key, external_id, deleted_at)` | 外部身份全局唯一（防并发重复建号；软删除后可重绑） |
| `idx_sys_user_identity_user_id` | 普通 | `(user_id)` | 按本地用户反查绑定（`sso:bind` 只读端点 / 解绑，归 02_02） |

- 无物理外键；`user_id` 指向 org 服务 `sys_user.id`（跨服务逻辑外键，只持值）。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（平台库常驻；行数 = 启用 SSO 的用户数，增长可控）。
- **归档**：不归档（身份绑定关系保留审计轨迹，随用户生命周期软删除）。
- **迁移**：随 **`identity:platform` 链** Alembic 迁移落地（`alembic/versions/identity/platform/0001_sys_user_identity.py`，2026-09-27，新建链；命令 `alembic -n alembic:identity:platform upgrade head`）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（平台库；随 02_01 落库迁移 `0001_sys_user_identity`，新建 `identity:platform` 链） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

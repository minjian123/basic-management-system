# sys_identity_provider（租户外部 IdP 配置）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_identity_provider

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | identity 服务租户库 `bms_identity_{code}`（归属服务 `identity`） |
| 覆盖模块 | 27-身份认证SSO |
| 上游依据 | [需求 02-1](../../../项目/06_认证与安全/需求/02_需求_SSO与身份联邦.md#r02-1)、[需求 02-6](../../../项目/06_认证与安全/需求/02_需求_SSO与身份联邦.md#r02-6)、《概要设计 · 身份认证SSO》「数据模型与表设计」节、《架构设计 · 认证与会话》§4 |
| ORM 模型 | `bms_identity/models/identity_provider.py::SysIdentityProvider`（继承 `BaseModel`） |
| 状态 | 已落库（`identity:tenant` 链迁移 `0002_sys_identity_provider`，2026-09-27） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 26-身份认证SSO](../../概要设计/26_概要设计_身份认证SSO.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `name` | VARCHAR(64) | 否 | — | 显示名（登录页入口文案） |
| `idp_key` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 租户内稳定标识 slug（路由参数 `{idp_key}`；映射键组成 `{tenant}:{idp_key}`） |
| `type` | VARCHAR(32) | 否 | — | 协议类型，取 `IDP_PROTOCOLS`（`oidc` / `cas` / `wecom` / `dingtalk`） |
| `icon` | VARCHAR(255) | 是 | — | 图标（可空，前端按空回退默认样式） |
| `config` | TEXT | 否 | JSON | 协议配置 JSON（`issuer` / `client_id` / `client_secret_ref` / `scopes` / `redirect_uri` / `jit_enabled` 等）；**密钥类只存引用**（`env:变量名` 或预留 `secret:标识`） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态：`enabled` / `disabled`（停用不出现在入口清单、不可发起授权） |
| `sort` | INT | 否 | 默认 0 | 登录页排序（升序） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- `config` 用 `TEXT` 存 JSON，规避 MySQL / PostgreSQL / 达梦 DM8 的 JSON 类型差异；字段级口径由 `02_06` 管理面延续（掩码 / 校验 / SSRF）。
- `idp_key` 仅允许小写字母 / 数字 / 连字符 / 下划线（服务层校验）；同一租户内唯一（软删除后可复用）。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_identity_provider_idp_key_deleted_at` | 唯一 | `(idp_key, deleted_at)` | 租户内 IdP 标识唯一（软删除后可复用） |
| `idx_sys_identity_provider_status_sort` | 普通 | `(status, sort)` | 入口清单主路径（`status = enabled` 按 `sort` 排序） |

- 无物理外键；租户归属由所在租户库 `bms_identity_{code}` 隐含承载。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；单租户 IdP 配置为个位数行）。
- **归档**：不归档（配置类数据保留审计轨迹，软删除即可）。
- **迁移**：随 **`identity:tenant` 链** Alembic 迁移落地（`alembic/versions/identity/tenant/0002_sys_identity_provider.py`，2026-09-27；命令 `alembic -n alembic:identity:tenant upgrade head`）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（identity 服务租户库；随 02_01 落库迁移 `0002_sys_identity_provider`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

# sys_client（第三方应用客户端）

> BMS · 数据库设计 · 数据表设计

[文档首页](../../../文档首页.md) › [数据库设计总览](../01_数据库设计_总览.md) › [已设计数据表登记](../01_数据库设计_总览.md#tables-registry) › sys_client

## 1. 归属与依据 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 归属库 | identity 服务租户库 `bms_identity_{code}`（归属服务 `identity`） |
| 覆盖模块 | 27-身份认证SSO（BMS 兼作 IdP 客户端注册；开放接口管理模块复用） |
| 上游依据 | [需求 02-5](../../../项目/06_认证与安全/需求/02_需求_SSO与身份联邦.md#r02-5)、《概要设计 · 身份认证SSO》「数据模型与表设计」节、《概要设计 · 开放接口管理》「数据模型与表设计」节 |
| ORM 模型 | `bms_identity/models/client.py::SysClient`（继承 `BaseModel`） |
| 状态 | 已落库（`identity:tenant` 链迁移 `0003_sys_client`，2026-09-27） |
| 相关节点 | [数据库设计总览](../01_数据库设计_总览.md)「核心表清单总表 · 租户库」、[概要 26-身份认证SSO](../../概要设计/26_概要设计_身份认证SSO.md) |

## 2. 字段 <a id="fields"></a>

公共字段继承 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁），下表不再重复说明其语义。

| 字段 | 类型 | 可空 | 约束 / 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | 否 | 主键，雪花 ID | 主键 |
| `client_id` | VARCHAR(64) | 否 | 与 `deleted_at` 复合唯一 | 客户端标识（服务端生成 `bms_` + 随机串；租户内唯一） |
| `client_secret_hash` | VARCHAR(255) | 是 | — | 客户端密钥哈希（PBKDF2 自描述串）；**公共客户端为空**，明文仅创建 / 重置响应回显一次 |
| `name` | VARCHAR(128) | 否 | — | 应用名称（管理展示） |
| `redirect_uris` | TEXT | 否 | JSON 数组 | 授权码流程回调地址白名单（精确匹配）；`authorization_code` 客户端必填 |
| `grant_types` | TEXT | 否 | JSON 数组 | 授权类型（取 `GRANT_TYPES`：`client_credentials` / `authorization_code`） |
| `scopes` | TEXT | 否 | JSON 数组 | 允许申请的 scope 集合（`authorization_code` 须含 `openid`） |
| `ip_whitelist` | TEXT | 否 | JSON 数组（默认值由应用侧写 `[]`） | 来源 IP / CIDR 白名单（开放接口阶段十消费；空 = 不限制） |
| `status` | VARCHAR(16) | 否 | 默认 `enabled` | 状态（`enabled` / `disabled`；停用后授权 / 换码拒绝） |
| `created_at` | DATETIME | 否 | 审计 | 创建时间（UTC） |
| `created_by` | BIGINT | 是 | 审计 | 创建人 |
| `updated_at` | DATETIME | 否 | 审计 | 更新时间（UTC） |
| `updated_by` | BIGINT | 是 | 审计 | 更新人 |
| `deleted_at` | DATETIME | 是 | 软删除（NULL=未删） | 软删除时间 |
| `version` | INT | 否 | 默认 1 | 乐观锁版本 |

- 多值字段（`redirect_uris` / `grant_types` / `scopes` / `ip_whitelist`）统一用 `TEXT` 存 JSON 数组，规避 MySQL / PostgreSQL / 达梦 DM8 的 JSON 类型差异（与 `sys_identity_provider.config` 同口径）。
- `client_credentials` 授权类型、`ip_whitelist` 生效与调用审计归开放接口阶段十；本期只落表并由 OIDC 授权码流程读取 `authorization_code` 客户端。

## 3. 索引与约束 <a id="index"></a>

| 名称 | 类型 | 列 | 说明 |
| --- | --- | --- | --- |
| `uq_sys_client_client_id_deleted_at` | 唯一 | `(client_id, deleted_at)` | 客户端标识租户内唯一（软删除后可复用） |

- 无物理外键；租户归属由所在租户库 `bms_identity_{code}` 隐含承载。

## 4. 分片 / 归档 / 迁移 <a id="storage"></a>

- **分片**：不分片（租户库常驻；单租户客户端为个位数行）。
- **归档**：不归档（配置类数据保留审计轨迹，软删除即可）。
- **迁移**：随 **`identity:tenant` 链** Alembic 迁移落地（`alembic/versions/identity/tenant/0003_sys_client.py`，2026-09-27；命令 `alembic -n alembic:identity:tenant upgrade head`）；SQLite 开发库由启动期自动建表覆盖。

## 5. 变更记录 <a id="revlog"></a>

| 日期 | 版本 | 变更 | 作者 |
| --- | --- | --- | --- |
| 2026-09-27 | v1 | 新建表结构（identity 服务租户库；随 02_05 落库迁移 `0003_sys_client`） | minjian |

> 数据表设计 · 与《数据库开发规范》「数据表文件规范」节配套

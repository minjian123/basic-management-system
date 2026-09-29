# 05 详细设计 · BMS 兼作 IdP 与客户端注册

> 认证与安全 · 02 SSO 与身份联邦 · 子任务 05（需求 02-5）· 详细设计

[文档首页](../../../../../../文档首页.md) › [02 SSO 与身份联邦](../../02_SSO与身份联邦.md) › 详细设计　|　[← 任务](../02_SSO与身份联邦_05_BMS兼作IdP与客户端注册.md)　[需求 02-5 →](../../../../需求/02_需求_SSO与身份联邦.md#r02-5)

## 1. 设计目标与范围 <a id="goal"></a>

在 01_02（用户令牌密钥体系）与既有 SSO 客户端链路之上，交付 **BMS 兼作 IdP（OIDC Provider 内核）与 `sys_client` 最小客户端注册**：

1. **OIDC Provider 能力域**——新增 `bms_core/oauth/` 下的 `BaseOidcProvider` 契约 + `JwtOidcProvider` 真实实现 + fail-closed Null 实现与工厂；ID Token / IdP access token 复用 `[security]` 用户令牌密钥体系（`usr-` kid），仅以 `iss`（按租户派生）与 `aud`（`client_id` / `userinfo`）口径区分。
2. **Provider 端点**——`{issuer}/.well-known/openid-configuration`（Discovery）、`{issuer}/jwks`、`{issuer}/authorize`、`{issuer}/token`、`{issuer}/userinfo`，授权码流程（PKCE、`state`、`nonce`）。
3. **客户端注册（最小）**——`sys_client` 表先设计后落库（identity 服务租户库），`client_id` 租户内唯一、`client_secret` 只存哈希；提供内部最小管理接口（创建 / 列表 / 详情 / 启停 / 重置凭据；`open:manage` 权限码占位）。
4. **令牌与撤销**——授权码单次有效短 TTL（复用 `idp_state_store` 一次性消费）；`/token` 本期不签发 refresh token；客户端凭据重置即旧密钥失效；签发审计经操作日志占位（`sys_open_log` 与开放接口鉴权归阶段十）。
5. **并存边界**——BMS 兼作 IdP（服务端）与「BMS 作为外部 IdP 客户端」（`bms_core/idp/`，SSO 链路 02_01~02_04）两向能力分列，互不占用契约（`aud=api` 用户令牌 / `aud=userinfo` IdP access token / `aud=service` 服务令牌 / ID Token `aud=client_id` 四向隔离）。
6. **联调演示**——`ops/seed_oidc_client.py` 播种测试客户端，完成一次授权码流程 E2E（授权 → 换码 → userinfo），作为 「BMS 作 IdP 通过」证据。

**不在本期**：客户端管理页面、调用审计（`sys_open_log`）、开放接口鉴权（`/api/open/token` Client Credentials）与 refresh token（归阶段十）；前端登录页与扫码（域五）；ID Token 中的 `email` 声明（`sys_user` 无该字段，待用户管理阶段）；真实生产密钥轮换与第三方 IdP 一致性测试（运维 / 验收随）。

**安全影响（SDL）**：涉及对外签发的身份断言（ID Token）与第三方客户端凭据。专项验收点：签名算法仅非对称白名单、私钥不入库 / 不落日志；`client_secret` 只存 PBKDF2 哈希、明文仅创建 / 重置响应回显一次；`redirect_uri` 精确匹配已注册值（防开放重定向）；授权码一次性原子消费（Redis `GETDEL`）且短 TTL；PKCE S256（公共客户端强制）；`state` / `nonce` 透传校验；`/authorize` 未登录只跳配置内登录页（防开放重定向）；`aud` / `iss` / `typ` 四向隔离防令牌串用；`/token` 客户端认证常量时间比对、失败不区分原因。

### 1.1 现状与缺口 <a id="gap"></a>

```text
backend/libs/bms_core/src/bms_core/
├── oauth/
│   ├── base.py                # 开放接口服务端 BaseOAuthServer（Client Credentials 占位，阶段十）——非 OIDC Provider
│   ├── token.py               # 服务 JWT 契约（aud=service）
│   ├── user_token.py          # 用户双 token 契约（aud=api；kid 强制 usr- 前缀）
│   ├── user_jwt.py            # JwtUserTokenIssuer（复用 [security] 密钥）——无 ID Token / IdP access 签发
│   ├── keys.py                # TokenKey / build_jwks / to_key_set
│   ├── verify.py              # UnifiedTokenVerifier（aud 分流 service / api）
│   └── null.py                # NullOAuthServer / NullUserTokenIssuer 等——无 NullOidcProvider
├── idp/state/base.py          # BaseIdpStateStore.save/consume/delete（键 bms:{租户}:idpstate:{state}）——无 namespace
├── core/assembly.py           # PLUGIN_WIRINGS 无 oidc_provider
└── services/table_registry.py # sys_client 为 PLANNED
backend/services/identity/src/bms_identity/
├── models/__init__.py         # MODEL_MODULES 无 client
├── repositories/              # 无 client 仓储
├── services/sso.py            # 仅「BMS 作外部 IdP 客户端」链路——无服务端 Provider
├── api/wellknown.py           # /.well-known/jwks.json（服务 + 用户令牌公钥）——非 IdP Discovery
└── api/router.py              # 无 oidc / clients 路由
backend/alembic/versions/identity/tenant/  # 0001_sys_session / 0002_sys_identity_provider——无 sys_client
```

缺口：① `sys_client` 无表文件 / 模型 / 迁移 / 归属启用；② 无 OIDC Provider 能力域与真实签发实现；③ 无 Discovery / JWKS / authorize / token / userinfo 端点与编排服务；④ `idp_state_store` 无 namespace，授权码无处一次性存储；⑤ 无客户端注册 / 启停 / 重置凭据接口；⑥ 8xxxx 段无 OIDC / 客户端错误码；⑦ 无 `[oidc_provider]` 配置与网关公开路径；⑧ 无 dev / E2E 测试客户端种子与集成用例。

## 2. 交付物清单 <a id="deliver"></a>

```text
backend/libs/bms_core/src/bms_core/
├── oauth/
│   ├── oidc_provider.py       # 新：Provider 常量 + IdTokenSpec / AccessTokenSpec / OidcAccessClaims + BaseOidcProvider + build_discovery_document + get_oidc_provider
│   ├── oidc_jwt.py            # 新：JwtOidcProvider（复用 [security] 密钥；ID Token / access token 签发与校验）+ JwtOidcProviderFactory
│   ├── null.py                # 改：增 NullOidcProvider（fail-closed）
│   └── __init__.py            # 改：域说明（新增 Provider 服务端能力）
├── idp/state/
│   ├── base.py                # 改：save / consume / delete 增可选 namespace；build_idp_state_key 增 namespace
│   ├── redis.py / memory.py / null.py  # 改：透传 namespace（向后兼容默认 idpstate）
│   └── __init__.py            # 改：域说明
├── core/
│   ├── config.py              # 改：OidcProviderSettings（[oidc_provider]）+ Settings.oidc_provider；GatewaySettings.public_paths 默认增 /api/identity/v1/oidc
│   ├── error_codes.py         # 改：增 OIDC_*（8010x）/ CLIENT_*（8011x）
│   ├── exceptions.py          # 改：OidcError 子段（含标准 error 串）+ ClientError 子段
│   └── assembly.py            # 改：PLUGIN_WIRINGS 增 oidc_provider；register_plugin("oidc_provider","jwt",…)
├── api/deps.py                # 改：导出 get_oidc_provider
└── services/table_registry.py # 改：sys_client PLANNED → ENABLED

backend/services/identity/src/bms_identity/
├── models/__init__.py         # 改：MODEL_MODULES 增 client
├── models/client.py           # 新：SysClient（identity / 租户库）
├── repositories/client.py     # 新：SysClientRepository（按 client_id / 主键取行 + 标准 CRUD）
├── schemas/oidc.py            # 新：Discovery / Token / UserInfo / 客户端管理 DTO
├── services/oidc_provider.py  # 新：OidcProviderService（发现文档 / authorize / token / userinfo 编排）
├── services/clients.py        # 新：ClientService（注册 / 列表 / 详情 / 启停 / 重置凭据）
├── api/oidc.py                # 新：/.well-known/openid-configuration、/jwks、/authorize、/token、/userinfo
├── api/clients.py             # 新：/open/clients 最小管理端点
└── api/router.py              # 改：挂 oidc / clients 路由

backend/alembic/versions/identity/tenant/0003_sys_client.py   # 新（down_revision=0002_sys_identity_provider）
backend/config.toml / config.dev.toml                         # 改：[oidc_provider]；[gateway].public_paths
backend/ops/seed_oidc_client.py                               # 新：dev/E2E 测试客户端种子（幂等、显式执行）
deploy/contracts/identity.json                                # 改：重生成（新端点非破坏新增）
frontend/packages/api-types/src/identity.ts                   # 改：重生成（零漂移）
deploy/gateway/apisix.yaml                                    # 改：重生成（路由 / 公开路径变化时）

bms文档/
├── 设计/数据库设计/数据表设计/sys_client.md                     # 新
├── 设计/数据库设计/01_数据库设计_总览.md                         # 改：§7.3 已设计数据表登记
├── 设计/概要设计/26_概要设计_身份认证SSO.md                      # 改：§5.1 端点清单、§5.2 幂等口径
├── 设计/概要设计/20_概要设计_开放接口管理.md                     # 改：§5.1 注记（本期身份侧最小接口，页面归阶段十）
├── 设计/架构设计/09_架构设计_接口与集成.md                       # 改：已发布码位补 801xx
├── 设计/架构设计/14_架构设计_子系统_认证与会话.md                 # 改：§4 BMS 兼作 IdP 口径
├── 后端基类清单.md                                             # 改：oidc_provider 条目
└── 项目/06_认证与安全/…
 ├── 计划/01_计划_认证与安全.md
    ├── 任务/02_SSO与身份联邦/02_SSO与身份联邦.md               # 改：子任务状态与完成日期
    └── 任务/…_05_…/                                           # 改：任务状态 + 实施 / 测试记录

test/scripts/kiwi/cases|exports/…                             # 新：本任务策展用例登记输入与回读
```

## 3. 接口 / 契约与边界 <a id="contract"></a>

### 3.1 数据库表与归属 <a id="tables"></a>

新增一张表（表文件为字段唯一事实源，本节只列要点，字段清单不复制）：

| 表 | 归属库 | 模块 | ORM 模型 | 迁移链 | 本期范围 |
| --- | --- | --- | --- | --- | --- |
| `sys_client` | identity 服务租户库 `bms_identity_{code}` | 27-身份认证SSO（阶段十开放接口复用） | `bms_identity/models/client.py::SysClient` | `identity:tenant`（0003） | 落表 + 注册 / 管理最小接口 + IdP 客户端读取 |

- 关键字段：`client_id`（服务端生成，租户内唯一 `uq_sys_client_client_id_deleted_at`）、`client_secret_hash`（PBKDF2 自描述串；**公共客户端可空**）、`name`、`redirect_uris`（`TEXT` 存 JSON 数组）、`grant_types`（`TEXT` JSON 数组，取值 `GRANT_TYPES`：`client_credentials` / `authorization_code`）、`scopes`（`TEXT` JSON 数组）、`ip_whitelist`（`TEXT` JSON 数组，阶段十消费）、`status`（`enabled` / `disabled`，默认 `enabled`）；公共字段继承 `BaseModel`。
- 多值字段统一用 `TEXT` 存 JSON 数组，规避 MySQL / PostgreSQL / 达梦 DM8 的 JSON 类型差异（与 `sys_identity_provider.config` 同口径）；**`TEXT` 列不设 DB 级默认值**（MySQL 不支持列级 `DEFAULT`），默认值由应用侧写入（实施回写见 §9）。
- 归属登记（`bms_core/services/table_registry.py::TABLE_OWNERSHIP`）：`sys_client` 由 `PLANNED` 转 `ENABLED`（删 `status` 行；owner `identity`、`TENANT` 不变）。
- 变更顺序（《[数据库开发规范](../../../../../../规范/数据库开发规范.md)》强制）：**先表文件（含变更记录）→ 总览登记 → ORM 模型 → Alembic 迁移 → 回写状态两处**。
- `client_credentials` 的签发 / 校验与 IP 白名单 / 调用审计归阶段十；本期只建字段与 `authorization_code` 流程读取，不实现 Client Credentials。

### 3.2 OIDC Provider 能力域 <a id="provider"></a>

新增 `bms_core/oauth/oidc_provider.py`（契约）与 `bms_core/oauth/oidc_jwt.py`（真实实现）：

- 常量：`OIDC_PROVIDER_KEY = "oidc_provider"`；`OIDC_SCOPE_OPENID / PROFILE / EMAIL`、`OIDC_DEFAULT_SCOPES = ("openid", "profile", "email")`；`OIDC_RESPONSE_TYPE_CODE = "code"`；`OIDC_GRANT_AUTHORIZATION_CODE`；`OIDC_TOKEN_TYPE_ID = "id_token"` / `OIDC_TOKEN_TYPE_ACCESS = "idp_access"`；`OIDC_ACCESS_AUDIENCE = "userinfo"`；`DEFAULT_AUTHORIZATION_CODE_TTL = 60` / `DEFAULT_ID_TOKEN_TTL = 300` / `DEFAULT_IDP_ACCESS_TTL = 300`。
- 数据契约（frozen dataclass）：
  - `IdTokenSpec(subject, client_id, issuer, nonce="", auth_time=0, preferred_username="", name="", ttl=None)`；
  - `AccessTokenSpec(subject, tenant, client_id, issuer, scopes=(), ttl=None)`；
  - `OidcAccessClaims(subject, tenant, client_id, scopes, expires_at, issued_at, token_id, payload)`。
- `BaseOidcProvider(BasePluggable, ABC)`（`key = plugin_key = "oidc_provider"`）：
  - `async issue_id_token(spec) -> str`（`iss` / `aud=client_id` / `typ=id_token` / `nonce` / `auth_time`）；
  - `async issue_access_token(spec) -> str`（`iss` / `aud=userinfo` / `typ=idp_access` / `tenant_id` / `client_id` / `scope` / `jti`）；
  - `def verify_access_token(token, *, issuer) -> OidcAccessClaims`（签名 / `exp` / `iss` / `aud=userinfo` / `typ=idp_access`）；
  - `def jwks() -> Mapping[str, object]`（公开 JWKS，只含公钥）。
- `build_discovery_document(*, issuer, authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri, scopes=OIDC_DEFAULT_SCOPES, algorithms=...) -> dict[str, object]`：标准字段（`issuer` / 四端点 / `scopes_supported` / `response_types_supported=["code"]` / `response_modes_supported=["query"]` / `grant_types_supported=["authorization_code"]` / `subject_types_supported=["public"]` / `id_token_signing_alg_values_supported=["RS256","ES256"]` / `token_endpoint_auth_methods_supported=["client_secret_basic","client_secret_post","none"]` / `code_challenge_methods_supported=["S256"]` / `claims_supported=["sub","iss","aud","exp","iat","auth_time","nonce","preferred_username","name"]`）。
- `JwtOidcProvider`（`plugin_name = "jwt"`）：读取 `[security].keys`（**kid 强制 `usr-` 前缀**，复用 `TokenKey` / `build_jwks` / `to_key_set`），`active_kid` 选签名密钥；`verify_access_token` 复用 `verify_jwt`（`issuer` 由调用方按租户传入、`audience="userinfo"`、算法白名单 / `leeway` 同 `idp/jwks.py`）；TTL 缺省取 `[oidc_provider]` 配置。
- `JwtOidcProviderFactory(BasePluginFactory)`：读 `[oidc_provider].issuer`（**支持 `{tenant}` 占位**）与 `[security]` 密钥 / `[oidc_provider]` TTL；构造不因无密钥而拒，签发时无可用私钥才 `ConfigError`。
- `NullOidcProvider`（`oauth/null.py`，fail-closed）：`issue_*` 抛 `ConfigError`、`verify_access_token` 恒抛 `AuthError`、`jwks()` 返回 `{"keys": []}`。
- 装配：`PLUGIN_WIRINGS` 增 `PluginWiring("oidc_provider", BaseOidcProvider, "oidc_provider", "oidc_provider")`；`register_platform_plugins` 增 `register_plugin("oidc_provider", "jwt", JwtOidcProviderFactory(settings))`；`get_oidc_provider(request)` 经 `api/deps.py` 导出。
- `iss` 口径：`issuer = [oidc_provider].issuer.format(tenant=tenant)`（含 `{tenant}` 占位时按租户派生，dev 无占位则全租户同名）；四端点由 issuer 后缀派生（`/authorize` 等）。

### 3.3 流程状态存储 namespace 扩展 <a id="state-namespace"></a>

`BaseIdpStateStore.save / consume / delete` 与 `build_idp_state_key` 增**可选** `namespace: str = "idpstate"`（键 `bms:{租户}:{namespace}:{state}`）；Redis / Memory / Null 三实现同步透传。向后兼容：既有 SSO 调用不传即保持 `idpstate` 键形。

- 授权码 namespace 常量 `OIDC_CODE_NAMESPACE = "oidccode"`；授权码值 `token_urlsafe(32)`，TTL = `[oidc_provider].authorization_code_ttl_seconds`，`consume` 一次性原子消费（Redis `GETDEL`）。
- 授权码载荷（服务层序列化为 JSON）：`client_id` / `redirect_uri` / `subject`（用户 id 字符串）/ `tenant` / `nonce` / `code_challenge` / `code_challenge_method` / `scope` / `auth_time`。

### 3.4 identity OIDC Provider 端点契约 <a id="endpoints"></a>

挂 identity 服务 `/api/v1/oidc`（外部经网关为 `/api/identity/v1/oidc`）；issuer 与端点由 `[oidc_provider].issuer` 派生，租户经标准解析链（子域 / `X-Tenant-ID` / `tenant` 参数回落）确定。

| 方法 | 路径 | 鉴权 / 租户 | 说明 |
| --- | --- | --- | --- |
| GET | `/.well-known/openid-configuration` | 公开；租户解析生效 | Discovery 文档（无统一响应包体） |
| GET | `/jwks` | 公开；租户解析生效 | IdP 公开 JWKS（无统一响应包体） |
| GET | `/authorize` | 公开；`require_auth`（登录态） | 授权端点：校验客户端 → 签发授权码 → `302` 回 `redirect_uri` |
| POST | `/token` | 公开；客户端认证 | 换码：授权码 → ID Token + access token（标准 OAuth2 JSON） |
| GET/POST | `/userinfo` | 公开；Bearer access token | 用户信息（标准 userinfo JSON） |

**Discovery**：`200` 返回标准文档；`issuer` = 按租户派生值，端点为其后缀（`/authorize` 等）。

**authorize**（查询参数 `response_type` / `client_id` / `redirect_uri` / `scope` / `state` / `nonce` / `code_challenge` / `code_challenge_method`）：

```text
GET /api/v1/oidc/authorize?response_type=code&client_id=…&redirect_uri=…&scope=openid+profile&state=…&nonce=…&code_challenge=…&code_challenge_method=S256
  ├─ require_auth：Bearer access token / 网关可信身份；未登录 → 302 {login_url}?return_to=<原样 authorize URL>（未配 login_url → 401）
  ├─ 载入客户端（租户库，client_id）：不存在 → 无法安全回跳 → 400 标准错误 JSON（invalid_request）
  ├─ 校验：status=enabled / grant_types 含 authorization_code / response_type=code / redirect_uri 精确命中 redirect_uris
  │    └─ 不合法 → 302 {redirect_uri}?error=…&error_description=…&state=…（redirect_uri 未知则 400 JSON）
  ├─ 校验 scope ⊆ 已注册 scopes 且含 openid；公共客户端（无 secret）强制 code_challenge（S256）
  ├─ 生成授权码落 idp_state_store（namespace=oidccode，TTL 短，一次性）
  └─ 302 {redirect_uri}?code=…&state=…
```

- 未登录跳转地址 `[oidc_provider].login_url` 与 `return_to` 只取配置 / 当前请求 URL（不允许外部任意地址），防开放重定向。
- 错误回跳遵循 OAuth2：已知 `redirect_uri` 用 `302` 带 `error` / `error_description` / `state`；未知或非法 `redirect_uri` 返回 `400` 标准错误 JSON（不回跳）。

**token**（`application/x-www-form-urlencoded`；客户端认证支持 `client_secret_basic` 与 `client_secret_post`）：

```text
POST /api/v1/oidc/token
  grant_type=authorization_code&code=…&redirect_uri=…&code_verifier=…
  ├─ 客户端认证：Basic 头或表单 client_id + client_secret；先按 client_id 取行，secret 经 password_hasher.verify（常量时间）
  ├─ consume 授权码（一次性）→ 无 → invalid_grant
  ├─ 校验 code.client_id == 认证客户端 / code.redirect_uri == 请求 redirect_uri
  ├─ 若 code 含 code_challenge：校验 BASE64URL(SHA256(code_verifier)) == challenge（不符 → invalid_grant）
  └─ 200：{access_token, token_type:"Bearer", expires_in, id_token, scope}（本期不发 refresh_token）
```

**userinfo**：`Authorization: Bearer <access_token>` → `verify_access_token`（`iss=issuer(租户)` / `aud=userinfo` / `typ=idp_access`）→ org 用户概要（`POST /api/v1/org/internal/users/profile`）→ `200` `{sub, preferred_username, name}`（`sys_user` 无 `email`，本期不返）；令牌非法 → `401`（`WWW-Authenticate: Bearer`），用户不存在 / 停用 → `401`（不泄露细节）。

### 3.5 `sys_client` 最小管理接口 <a id="clients"></a>

挂 identity 服务 `/api/v1/open/clients`（对齐阶段十《[概要设计 · 开放接口管理](../../../../../../设计/概要设计/20_概要设计_开放接口管理.md)》路径与权限码）；模块级 `Depends(require_auth)` + `require_permission("open:manage")`（RBAC 前权限基座为 Null = 超管口径）：

| 方法 | 路径 | 请求 / 响应 | 说明 |
| --- | --- | --- | --- |
| POST | `/open/clients` | `{name, redirect_uris[], grant_types[], scopes[], ip_whitelist?[]}` → `{client_id, client_secret, …}` | 注册；`client_id` 服务端生成、`client_secret` **仅本次明文返回** |
| GET | `/open/clients` | 分页（`page` / `size`，可选 `status` / `name` 筛选） | 列表（**永不返回 secret 与哈希**） |
| GET | `/open/clients/{id}` | 详情 | 单条（同上） |
| POST | `/open/clients/{id}/status` | `{status: enabled\|disabled}` | 启停 |
| POST | `/open/clients/{id}/reset-secret` | → `{client_id, client_secret}` | 重置凭据；**新明文仅本次返回**，旧值即时失效 |

- `client_id` 生成口径：`bms_` + `secrets.token_urlsafe(24)`；`client_secret`：`secrets.token_urlsafe(32)`（公共客户端可传 `client_secret` 为空以登记为无密钥客户端；`authorization_code` 时强制 PKCE）。
- `redirect_uris` 校验：仅 `http` / `https`，非空（`grant_types` 含 `authorization_code` 时必填）；`grant_types` / `scopes` 校验取值合法、去重。
- 写操作（创建 / 启停 / 重置）经 `sys_client` 落库；签发审计经既有 `audit` 能力域占位（`AuditCapturer.capture`，真实落库随审计阶段）。
- 失败语义（平台统一响应）：id 不存在 → `ClientNotFoundError`（`80111/404`）；`client_id` 冲突 → `ClientConflictError`（`80113/409`）；字段非法 → `ClientInvalidError`（`80112/400`）。

### 3.6 配置契约 <a id="config"></a>

```toml
[oidc_provider]
provider = "jwt"                               # jwt / 空（Null，fail-closed）
issuer = "http://localhost:8000/api/v1/oidc"   # IdP 签发方；可含 {tenant} 占位（生产按租户子域派生）
authorization_code_ttl_seconds = 60            # 授权码一次性短 TTL（秒）
id_token_ttl_seconds = 300                     # ID Token 有效期（秒）
access_token_ttl_seconds = 300                 # IdP access token 有效期（秒）
login_url = ""                                 # /authorize 未登录跳转的前端登录页（空 = 401）
```

| 配置键 | 环境变量 | 口径 |
| --- | --- | --- |
| `[oidc_provider].provider` | `BMS_OIDC_PROVIDER__PROVIDER` | 基线 `jwt`；测试置空回落 Null |
| `[oidc_provider].issuer` | `BMS_OIDC_PROVIDER__ISSUER` | 可含 `{tenant}` 占位；Discovery / 令牌 `iss` 与四端点据此派生 |
| `[oidc_provider].authorization_code_ttl_seconds` | `BMS_OIDC_PROVIDER__AUTHORIZATION_CODE_TTL_SECONDS` | 授权码 TTL（一次性） |
| `[oidc_provider].id_token_ttl_seconds` / `access_token_ttl_seconds` | `BMS_OIDC_PROVIDER__ID_TOKEN_TTL_SECONDS` / `__ACCESS_TOKEN_TTL_SECONDS` | 两类令牌有效期 |
| `[oidc_provider].login_url` | `BMS_OIDC_PROVIDER__LOGIN_URL` | 未登录跳转（只取配置，防开放重定向） |
| `[gateway].public_paths`（新增项） | — | 增 `/api/identity/v1/oidc`（前缀匹配，覆盖 Discovery / jwks / authorize / token / userinfo） |

- ID Token / IdP access token 密钥与算法沿用 `[security].keys`（`usr-` 前缀）与 `[user_token]` 口径；`iss` 取 `[oidc_provider].issuer`。

### 3.7 错误码口径 <a id="errors"></a>

新增开放 / 租户 / SSO 段（8xxxx）子段（`core/error_codes.py` 登记；架构 09「平台已发布码位」同步）：

| 码位 | 含义 | HTTP | 异常类 | 响应形态 |
| --- | --- | --- | --- | --- |
| `80101` | OIDC 请求非法（缺参 / `response_type` 不支持 / 未知客户端） | 400 | `OidcInvalidRequestError`（`error=invalid_request`） | 端点标准错误 JSON / 回跳 |
| `80102` | 客户端认证失败（未知客户端或密钥错误） | 401 | `OidcInvalidClientError`（`error=invalid_client`） | 端点标准错误 JSON |
| `80103` | 授权码无效 / 已消费 / 过期 / PKCE 不符 | 400 | `OidcInvalidGrantError`（`error=invalid_grant`） | 端点标准错误 JSON |
| `80104` | scope 未注册或缺少 `openid` | 400 | `OidcInvalidScopeError`（`error=invalid_scope`） | 回跳 / 端点标准错误 JSON |
| `80105` | `grant_type` 不支持（本期仅 `authorization_code`） | 400 | `OidcUnsupportedGrantError`（`error=unsupported_grant_type`） | 端点标准错误 JSON |
| `80106` | 未登录且未配登录页 | 401 | `OidcAccessDeniedError`（`error=access_denied`） | 标准错误 JSON |
| `80111` | 客户端不存在 | 404 | `ClientNotFoundError` | 平台统一响应体 |
| `80112` | 客户端字段非法 | 400 | `ClientInvalidError` | 平台统一响应体 |
| `80113` | 客户端标识冲突 | 409 | `ClientConflictError` | 平台统一响应体 |

- **异常体系**：`OidcError(OpenTenantError)` 子段基（携 `error` / `error_description` / `http_status`）；`ClientError(OpenTenantError)` 子段基。`OidcError` 在 `api/oidc.py` 端点边界捕获并转**标准 OAuth2 错误 JSON**（`{"error": …, "error_description": …}`），不进平台统一响应体；`ClientError` 走全局处理器转平台统一 `{code,message,data}`。
- IdP 端点不区分「未知客户端」与「密钥错误」（统一 `invalid_client`），防客户端枚举（常量时间比对）。

### 3.8 失败分支与错误语义 <a id="failures"></a>

| 场景 | 行为 |
| --- | --- |
| Discovery / jwks：无租户上下文且无 `tenant` 参数 | `TenantNotFoundError`（既有，与 refresh 同口径） |
| Discovery / jwks：Provider 无密钥 | jwks 返回 `{"keys": []}`；Discovery 正常（字段合规） |
| authorize：未登录且配 `login_url` | `302 {login_url}?return_to=<authorize URL>` |
| authorize：未登录且未配 `login_url` | `OidcAccessDeniedError`（`80106/401`，标准错误 JSON） |
| authorize：未知 / 停用客户端，或缺参数 | `OidcInvalidRequestError`（`80101/400`，标准错误 JSON，不回跳） |
| authorize：`redirect_uri` 不在已注册集合 | `80101/400` 标准错误 JSON（不回跳到未注册地址） |
| authorize：`scope` 非法 / 缺 `openid` | `302 {redirect_uri}?error=invalid_scope&…`（已知地址回跳） |
| authorize：公共客户端缺 `code_challenge` / 非 S256 | `302 {redirect_uri}?error=invalid_request&…` |
| authorize / token / userinfo：限流命中 | `RateLimitError`（`10005/429`）；authorize 已知 `redirect_uri` 则回跳 `error=server_error` |
| token：`grant_type` 非 `authorization_code` | `OidcUnsupportedGrantError`（`80105/400`） |
| token：客户端认证失败 | `OidcInvalidClientError`（`80102/401`，`WWW-Authenticate: Basic`） |
| token：授权码缺失 / 已消费 / 过期 | `OidcInvalidGrantError`（`80103/400`） |
| token：`client_id` / `redirect_uri` 与授权码不符 | `OidcInvalidGrantError`（`80103/400`） |
| token：PKCE `code_verifier` 不符 | `OidcInvalidGrantError`（`80103/400`） |
| userinfo：缺 / 非法 access token | `401`（`WWW-Authenticate: Bearer error="invalid_token"`） |
| userinfo：access token 租户与请求租户不符 | `401`（`iss` 不符，跨租户拒绝） |
| userinfo：org 用户不存在 / 停用 | `401`（不泄露细节） |
| userinfo：org 接口不可达 | `ServiceUnavailableError`（`10007/503`，fail-closed） |
| 客户端管理：id 不存在 / 字段非法 / 冲突 | `80111/404`、`80112/400`、`80113/409`（平台统一响应） |
| 达梦 / 三库方言 | 结构走迁移零漂移；`redirect_uris` 等用 `TEXT` 存 JSON 规避方言差异 |
| 与 SSO 客户端链路（02_01~02_04） | 完全不受影响（两向能力分列，`aud` 隔离） |

## 4. 兼容性与消费方影响 <a id="compat"></a>

- **新增**：`oidc_provider` 能力域（契约 + JWT 实现 + Null + 工厂）、`sys_client`（表 + 模型 + 迁移 + 仓储）、`sys_client` 最小管理接口、identity OIDC 五端点与 `OidcProviderService`、`ClientService`、`OidcError` / `ClientError` 子段与八错误码、`[oidc_provider]` 配置、`ops/seed_oidc_client.py`。
- **扩展**：`BaseIdpStateStore` 三方法**可选 `namespace` 参数**（向后兼容，既有 SSO 调用零改动）；`GatewaySettings.public_paths` 默认增项；`table_registry` `sys_client` 转 ENABLED（进 `identity:tenant` 链）。
- **不改**：SSO 客户端链路（`bms_core/idp/` 与 identity `api/sso.py`）、既有 `/.well-known/jwks.json`（服务 + 用户令牌公钥合并）、用户令牌 / 服务令牌 / 统一校验契约、`oauth_server` 与 Client Credentials（阶段十）、`sys_identity_provider` 表与迁移链。
- **迁移链影响**：`identity:tenant` 增 `0003_sys_client`（单 head，`down_revision=0002_sys_identity_provider`）；`test_alembic_chains` 断言同步（表集含 `sys_client`）。
- **默认值变更（需回归）**：新增 `[oidc_provider].provider="jwt"`（各测试套 `conftest` 置空回落 Null，与 `user_token` / `idp_state_store` 同模式，仅 identity OIDC 用例显式开启）；`config.toml` 新增 `[oidc_provider]` 默认值。
- **数据所有权**：identity 不 import org 模型；userinfo 经 org 公开契约（服务间调用）取用户概要；`sys_client` 平台库 / 租户库归属不变。
- **消费方前置契约标注**：阶段十（`sys_client` 管理页面 / Client Credentials / IP 白名单 / 调用审计复用本表与 `open:manage` 路径）、域五（前端登录页 `return_to` 落点）、用户管理阶段（`sys_user.email` 补齐后 ID Token / userinfo 补 `email`）。

## 5. 测试设计与验收映射 <a id="test"></a>

用例**先登记 Kiwi TCMS 再编码**（本任务登记**一条**策展用例覆盖全部分支，编号以平台回读为准），自动化用例以 `@pytest.mark.kiwi_id(...)` 标注；真实联调（mjbk + 网关）以人工留痕记录。

| # | 用例 / 文件 | 断言要点 | 对应完成标准 |
| --- | --- | --- | --- |
| 1 | `libs/bms_core/tests/idp/test_state_store.py`（扩展） | `build_idp_state_key` 带 `namespace`；三实现 namespace 隔离（同 state 不同 namespace 互不影响）；既有默认 `idpstate` 行为不变 | 流程状态复用 |
| 2 | `libs/bms_core/tests/oauth/test_oidc_provider.py`（新） | `issue_id_token` claims（`iss/aud=client_id/typ=id_token/nonce/auth_time`）+ 本地验签；`issue_access_token` claims（`aud=userinfo/typ=idp_access/tenant_id/client_id/scope`）+ `verify_access_token` 往返；`iss` / `aud` / `typ` 不符拒；无密钥 `ConfigError`；Null fail-closed；`build_discovery_document` 字段合规 | Provider 内核与字段合规 |
| 3 | `services/identity/tests/oidc/test_discovery.py`（新） | Discovery `200` 字段齐全且 `issuer` 与端点前缀一致；jwks 返回公钥（与 `/.well-known/jwks.json` 的 `usr-` 公钥同源）；无租户 → 404 | Discovery / JWKS 可访问且合规 |
| 4 | `services/identity/tests/oidc/test_authorize.py`（新） | 成功：登录态 → 授权码落库（payload / TTL）→ `302` 回 `redirect_uri`（含 `code` / `state`）；未登录跳 `login_url` / 未配 401；未知客户端 / 非法 `redirect_uri` → 400 标准错误（不回跳）；未注册 `redirect_uri` 拒；scope 非法回跳；公共客户端缺 PKCE 拒；停用客户端拒 | 授权跳转与安全分支 |
| 5 | `services/identity/tests/oidc/test_token.py`（新） | 成功：换码 → ID Token 验签（`aud=client_id` / `nonce` / `sub`）+ access token 验签（`aud=userinfo`）；basic 与 post 两认证；授权码重放 / 过期 → invalid_grant；`redirect_uri` 不符 / PKCE 不符 → invalid_grant；未知客户端 / 错密钥 → invalid_client；`grant_type` 非授权码 → unsupported_grant_type；无 refresh_token | 授权码流程 E2E 与错误分支 |
| 6 | `services/identity/tests/oidc/test_userinfo.py`（新） | Bearer access token → `{sub, preferred_username, name}`；缺 / 错 / 过期 / 跨租户令牌 → 401；用户不存在 / 停用 → 401；org 不可达 → 503 | userinfo 与失败语义 |
| 7 | `services/identity/tests/oidc/test_clients.py`（新） | 创建返回 `client_id` + 明文 secret 一次；重置后旧 secret 失效、新密钥可换码；列表 / 详情不含 secret 与哈希；启停后 authorize / token 拒绝；字段非法 → 80112；不存在 → 80111；权限依赖生效 | 注册 / 停用 / 重置可用且落库 |
| 8 | `services/identity/tests/oidc/test_e2e.py`（新） | 单测内全链路：登录建会话 → authorize（Bearer）→ 换码 → userinfo；测试客户端种子可用 | 「BMS 作 IdP 通过」证据 |
| 9 | `services/identity/tests/oidc/test_units.py`（新） | helper 分支：`issuer` 占位派生 / scope 校验 / redirect_uri 匹配 / PKCE S256 计算 / 授权码载荷编解码非法结构 | 覆盖率 100% |
| 10 | `libs/bms_core/tests/alembic/test_alembic_chains.py`（扩展） | `identity:tenant` 单 head 新 revision；表集含 `sys_client`；`branch_labels` 正确 | 迁移链与零漂移 |
| 11 | `services/platform/tests/crosscut/test_plugin_registration.py`（扩展） | `_EXPECTED_PLUGIN_KEYS` 与接线一致（`oidc_provider` 登记） | 装配一致性 |
| 12 | 既有全量回归 + 门禁 | `pytest` / `ruff` / `pyright` / 契约快照 `check`（identity.json 重生成）/ `check-backend-base` / `check-service-boundaries` / `preflight --fast` 全绿 | 回归与门禁 |
| 13 | mjbk 真实冒烟（人工留痕） | 开发环境 identity + org + Redis：`ops.seed_oidc_client.py` 播种 → 登录 → authorize → token → userinfo；Gateway 公开路径放行 | 端到端 |

**验收映射**：需求 02-5 完成标准四句——「Discovery / JWKS 可访问且字段合规」落用例 2/3；「测试客户端授权码流程 E2E 通过（PKCE、授权码单次、scope 校验）」落用例 4/5/8；「`sys_client` 注册 / 停用 / 重置经最小接口可用且落库」落用例 7；「错误分支（非法 redirect_uri / 未知 client / 授权码重放）有用例」落用例 4/5。「`sys_client` 表文件 ↔ 登记 ↔ 迁移零漂移」落用例 10 + `preflight --fast` 基座校验。`pytest`、`pyright`、`ruff`、契约门禁与基座校验全绿为准出门禁；新增 / 变更模块（`oauth/oidc_provider`、`oauth/oidc_jwt`、`idp/state` 差异、identity `oidc` / `clients` 全套、`SysClient` / 仓储）覆盖率 100%。

## 6. 登记落点 <a id="registry"></a>

| 内容 | 落点 |
| --- | --- |
| `sys_client` 表文件与总览登记 | `设计/数据库设计/数据表设计/sys_client.md`、总览 §7.3 |
| 表归属（`sys_client` 转 enabled） | `bms_core/services/table_registry.py::TABLE_OWNERSHIP` |
| `oidc_provider` 能力域条目 + `idp_state_store` namespace 扩展 | 《[后端基类清单](../../../../../../后端基类清单.md)》开放接口服务端 / 流程状态条目 |
| 错误码与口径回写 | 架构 09 行（`801xx`）；概要 26 §5.1 / §5.2；概要 20 §5.1；架构 14 §4 |
| 契约与生成件 | `deploy/contracts/identity.json`、`frontend/packages/api-types/src/identity.ts` 重生成零漂移 |
| 网关生成件 | `deploy/gateway/apisix.yaml`（路由 / 公开路径变化时重生成） |

| 消费方前置契约标注 | 阶段十（`sys_client` 管理 / 开放接口 / 审计）、域五（登录页 `return_to`）、用户管理阶段（`email`） |
| Kiwi TCMS / 测试资产仓 | 登记本任务策展用例并回读编号；`test/scripts/kiwi/cases|exports/` 对应文件 |
| 实施 / 测试记录 | 本目录 `实施/`、`测试/` 各一份 |

## 7. 边界与开放项 <a id="boundary"></a>

- **归阶段十**：客户端管理页面、Client Credentials（`/api/open/token`）、IP 白名单生效、`sys_open_log` 调用审计、refresh token 与独立撤销、scope 与 RBAC 精细结合。
- **归域五（前端）**：登录页 `return_to` 落点与登录后回跳 `/authorize`；扫码 / 内嵌登录与 BMS 兼作 IdP 的入口区分。
- **归用户管理阶段**：`sys_user` 补 `email` 后，ID Token 与 userinfo 增 `email` 声明（现口径为留空）。
- **归运维 / 验收**：生产 issuer 域与租户子域规划、密钥轮换演练、第三方 OIDC 一致性测试（如 oidc-provider 兼容性）。
- **开放项（浏览器会话 cookie）**：本期 `/authorize` 依赖 `require_auth`（Bearer / 网关可信身份）；真实浏览器导航的 BMS 会话 cookie 联动（使前端登录后直接回跳即签发授权码）留域五评估——当前以 `login_url` + `return_to` 过渡。
- **开放项（issuer 单基址 vs 租户子域）**：`[oidc_provider].issuer` 支持 `{tenant}` 占位；dev 用单基址 + `X-Tenant-ID`，生产按租户子域呈现（部署定稿）。
- **开放项（授权码存储复用）**：授权码复用 `idp_state_store`（namespace 隔离）；若后续需持久审计，再评估独立表（本期不落库）。
- **开放项（userinfo 每次回源 org）**：userinfo 每次经 org 内部接口取概要（无本地缓存）；高频调用优化留后续（可加缓存或以 ID Token claims 为主）。
- **开放项（Client Credentials 共存）**：`sys_client.grant_types` 已含 `client_credentials` 值，本期 Provider 只实现 `authorization_code`，Client Credentials 由阶段十在 `oauth_server` 域落地。

## 8. 对齐记录 <a id="align"></a>

| # | 事项 | 结论（2026-09-27 拍板） |
| --- | --- | --- |
| 1 | Provider 内核落点 | **新增 `oauth` 能力域 `oidc_provider`**（契约 + JWT 实现 + Null + 工厂），identity 服务 API 薄封装 |
| 2 | ID Token 密钥 | **复用 `[security]` 用户令牌密钥**（`usr-` kid，同 JWKS）；仅 `iss`（`[oidc_provider].issuer`）与 `aud`（`client_id` / `userinfo`）区分 |
| 3 | issuer / 端点 | **`{issuer}` 基址下全套端点**（Discovery / jwks / authorize / token / userinfo） |
| 4 | 租户模型 | **单 issuer 基址 + 标准租户解析**（`{tenant}` 占位可选）；`sys_client` 租户内唯一 |
| 5 | authorize 登录态 | **`require_auth` + 未登录跳 `login_url`**（`return_to` 只取配置）；未配则 401 |
| 6 | 授权码存储 | **复用 `idp_state_store` + namespace**（一次性 `GETDEL`，短 TTL） |
| 7 | access token 形态 | **自签 JWT**（`aud=userinfo` / `typ=idp_access`，无状态） |
| 8 | 客户端认证 / PKCE | **支持 basic + post；公共客户端强制 PKCE S256** |
| 9 | secret 哈希 | **复用 `password_hasher`（PBKDF2）**，常量时间比对 |
| 10 | 注册接口路径 | **`/api/v1/open/clients` + `open:manage` 占位**（对齐阶段十） |
| 11 | 错误响应形态 | **OIDC 端点标准 OAuth2 JSON；客户端管理接口平台统一响应** |
| 12 | 错误码 | **新增 8xxxx 子段**（`8010x` OIDC / `8011x` 客户端） |
| 13 | `sys_client` 字段 | **一次建全**（含 `ip_whitelist` 等阶段十预留），`TEXT` 存 JSON |
| 14 | 凭据生成 | **服务端生成；secret 仅创建 / 重置回显一次**，库中只存哈希 |
| 15 | 联调种子 | **`ops/seed_oidc_client.py` 显式执行**（仅 dev / E2E） |
| 16 | ID Token 声明 | **标准声明**（`sub/iss/aud/exp/iat/nonce/auth_time/preferred_username/name`）；userinfo 同源不含 `email` |
| 17 | refresh token | **本期不签发**（仅 `authorization_code` 换 `id_token` + 短时 access） |
| 18 | 网关 / 租户 | **网关公开 + 保留租户解析**（`public_paths` 增 `/api/identity/v1/oidc`） |

## 9. 实施回写（2026-09-27） <a id="impl-backfill"></a>

| # | 事项 | 回写结论 |
| --- | --- | --- |
| 1 | 服务层 helper 命名 | `clean_scope` / `code_from_payload` / `verify_pkce` / `load_list` / `redirect_error` / `with_query` 去前导下划线（适配测试引用与严格类型检查）；语义不变 |
| 2 | `OidcProviderService.jwks()` | 未落地为服务方法——`/jwks` 端点直接取 Provider 能力域 `provider.jwks()`，避免无谓透传（§3.4 端点契约不变） |
| 3 | 内存流程状态键形 | `MemoryIdpStateStore` 键形对齐 Redis（`build_idp_state_key(state, tenant, namespace)`）；SSO 测试 `peek` / `flow_payload` 同步按键取数（§3.3 语义不变） |
| 4 | 客户端写操作审计 | `ClientService.audit` 由可选改必填（应用恒注入 `AuditCapturer` 占位），删除不可达的空分支（§3.5 审计占位口径不变） |
| 5 | 端点错误转换 | `/authorize` 端点边界捕获 `OidcError` 转标准 OAuth2 错误 JSON（`/token` 同）；客户端管理接口走全局处理器转平台统一响应（§3.7 不变） |
| 6 | 契约与生成件 | `deploy/contracts/identity.json` 与 `frontend/packages/api-types/src/identity.ts` 按实施重生成，`check` / `gen:check` 零漂移；网关 `apisix.yaml` 无变更（路由按服务目录生成，`gateway_config check` 零漂移） |
| 7 | 基座清单补登 | 《后端基类清单》增 `oidc_provider` 能力域条目与认证链路 02_05 模块行（含服务 / 结果契约），`idp_state_store` 条目补 `namespace` |
| 8 | 测试落点与 Kiwi | 新增 `libs/bms_core/tests/oauth/`、`services/identity/tests/oidc/`（含 `conftest.py` / `helpers.py`）；Kiwi 策展用例 **2202**（先登记后编码）；新增 / 变更模块覆盖率 100% |
| 9 | 方言实测修正（真机暴露） | `sys_client.ip_whitelist` 原设 `TEXT NOT NULL DEFAULT '[]'`，MySQL 8 报 `1101`（TEXT 列不支持列级 DEFAULT）；移除 DB 默认值（迁移 / 模型 / 表文件同步），默认值改由应用侧写入；结论回写《数据库设计 · 方言特性（MySQL）》「DDL 与对象差异」节（标实测） |
| 10 | 真机冒烟（mjbk） | `bms-identity:19a620b9` 部署 + `identity:tenant` 0003 迁移 + 健康门禁通过；Discovery / JWKS 经网关 `200`；容器内以真实密钥签发用户令牌 + Redis 会话标记完成授权 → 换码 → userinfo 全链路（`302` / `200` / `200`）；`ops.seed_oidc_client` 播种测试客户端（seed 脚本 argparse 问题修正见《[05 实施](../实施/05_实施_05_BMS兼作IdP与客户端注册.md)》「问题与处置」节） |

> 详细设计定稿后按《[AI开发规范](../../../../../../规范/AI开发规范.md)》「单任务交付一条龙」自动续行：实施 → 测试（Kiwi 先登记）→ 验证 → 登记回写 → 记录 → 提交。

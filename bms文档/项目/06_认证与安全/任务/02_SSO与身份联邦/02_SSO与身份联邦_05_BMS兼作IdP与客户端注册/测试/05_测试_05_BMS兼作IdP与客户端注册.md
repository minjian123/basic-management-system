# 05 测试 · BMS 兼作 IdP 与客户端注册

> 认证与安全 · 02 SSO 与身份联邦 · 子任务 05（需求 02-5）· 测试记录

[文档首页](../../../../../../文档首页.md) › [02 SSO 与身份联邦](../../02_SSO与身份联邦.md) › 测试记录　|　[← 实施记录](../实施/05_实施_05_BMS兼作IdP与客户端注册.md)　[任务 →](../02_SSO与身份联邦_05_BMS兼作IdP与客户端注册.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [05 BMS 兼作 IdP 与客户端注册](../02_SSO与身份联邦_05_BMS兼作IdP与客户端注册.md) |
| 对应需求 | [02-5](../../../../需求/02_需求_SSO与身份联邦.md#r02-5) |
| 详细设计 | [05 详细设计](../设计/05_详细设计_05_BMS兼作IdP与客户端注册.md) |
| 实施记录 | [05 实施记录](../实施/05_实施_05_BMS兼作IdP与客户端注册.md) |
| Kiwi 用例 | **2202**（策展用例，先登记后编码；平台回读确认，2026-09-27） |
| 测试日期 | 2026-09-27 |
| 测试人 | minjian |
| 测试环境 | 本地开发机（Python 3.14.4 / uv；ASGI 内存客户端；SQLite 租户库 / 平台库 + joserfc 真实签验；org 用户概要替身） |
| 结论 | 通过（自动化用例全绿；新增 / 变更代码覆盖率 100%；契约 / 基座 / 预检全绿） |

## 2. 测试范围与用例 <a id="cases"></a>

用例**先登记 Kiwi TCMS 取得编号 2202** 再编码，自动化用例以 `@pytest.mark.kiwi_id(2202)` 标注。

| # | 文件 | 覆盖点（Kiwi 编号） |
| --- | --- | --- |
| 1 | `libs/bms_core/tests/oauth/test_oidc_provider.py`（新） | Discovery 文档字段；ID Token 签发 / 本地验签（`iss` / `aud=client_id` / `typ=id_token` / `nonce` / `auth_time` / TTL）；access token 往返（`aud=userinfo` / `typ=idp_access` / `tenant_id` / `client_id` / `scope` / `jti`）；issuer / typ 不符拒；空主体 `ParamError` / 空 sub `AuthError`；密钥解析（单密钥自动 / 无密钥 / active_kid 未命中 / 多密钥未指定 / `usr-` 前缀）；Null fail-closed（**2202**） |
| 2 | `libs/bms_core/tests/idp/test_state_store.py`（改） | `build_idp_state_key` 带 `namespace`；内存 / Redis 命名空间隔离（同 state 不同命名空间互不影响）；默认 `idpstate` 键形不变（**2202**） |
| 3 | `services/identity/tests/oidc/test_discovery.py`（新） | Discovery `200` 字段齐全且 issuer 与端点前缀一致；`tenant` 参数回落分支；jwks 发布 `usr-` 公钥；无租户头回落演示租户（**2202**） |
| 4 | `services/identity/tests/oidc/test_authorize.py`（新） | 成功：授权码落 `oidccode` 命名空间（payload / 租户 / nonce）→ 302 含 code / state；未登录 401（未配登录页）/ 302 跳登录页（配 `login_url` + `return_to`）；未知客户端 / 未注册 `redirect_uri` / 停用客户端 / 缺参数 / 租户不一致 → 400 标准错误（不回跳）；scope 非法 / `response_type` 非 code / 未授权授权码 / PKCE 方法非 S256 / 公共客户端缺 PKCE → 302 回跳带 `error`（**2202**） |
| 5 | `services/identity/tests/oidc/test_token.py`（新） | basic 与 post 两认证；换码签发 ID Token（`aud=client_id` / `nonce` / `sub`）与 access token；授权码重放 / 缺参 / 用户不存在 / `redirect_uri` 不符 / PKCE 不符 → `invalid_grant`；未知客户端 / 错密钥 / 公共客户端携带密钥 → `invalid_client`；非授权码 `grant_type` → `unsupported_grant_type`；无 `refresh_token`（**2202**） |
| 6 | `services/identity/tests/oidc/test_userinfo.py`（新） | Bearer access token → `{sub, preferred_username, name}`；缺 / 非法令牌 401；跨租户令牌 401；用户不存在 / 停用 401；org 不可达 503（**2202**） |
| 7 | `services/identity/tests/oidc/test_clients.py`（新） | 创建返回 `client_id` + 明文 secret 一次并可用于完整换码；列表 / 详情不含 secret；`status` / `name` 筛选；启停后授权拒绝；重置密钥旧失效新可用；公共客户端 secret 为空、重置被拒（80112）；非法授权类型 / 回调 / scope（80112）；不存在（80111）（**2202**） |
| 8 | `services/identity/tests/oidc/test_e2e.py`（新） | 端到端：授权 → 换码 → userinfo；issuer 占位派生与非法模板回落；`_resolve` 四分支；API helper 分支（租户缺失 / JSON 非法 / Basic 头非法 / 表单缺值 / Bearer 解析）（**2202**） |
| 9 | 迁移与装配 | `libs/bms_core/tests/alembic/test_alembic_chains.py`、`libs/bms_core/tests/services/test_table_registry.py`（`sys_client` 进链）、`services/platform/tests/crosscut/test_plugin_registration.py`（`oidc_provider` 登记） |
| 10 | 既有全量回归 + 门禁 | SSO 客户端链路（02_01~02_04）、JIT、本地登录 / 刷新 / 登出全量回归不受影响；`pytest` / `ruff` / `pyright` / 契约与生成件零漂移 / 基座校验 / `preflight --fast` 全绿 |

## 3. 执行结果 <a id="result"></a>

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 全量用例 | `cd backend && uv run pytest -q` | **1623 passed，37 skipped**（1 warning：aiosqlite 事件循环关闭，既有现象） |
| OIDC / 状态存储定向 | `uv run pytest libs/bms_core/tests/oauth libs/bms_core/tests/idp/test_state_store.py services/identity/tests/oidc -q` | **66 passed** |
| 覆盖率（新增 / 变更模块） | 见 §4 | 语句 **100%** |
| 静态 / 类型 | `uv run ruff check .`、`ruff format --check .`、`uv run pyright` | 全绿（0 errors） |
| 契约与生成件 | `ops.contract_snapshot check` / `ops.gateway_config check` / `ops.event_contracts check`（23 条契约）/ api-types `gen:check` | 零漂移 |
| 基座 / 预检 | `check-backend-base.py` / `check-base.py` / `check-links.py` / `check-service-boundaries.py` / `check-status.py` / `preflight --fast` | 全绿 |

## 4. 覆盖率 <a id="coverage"></a>

`uv run pytest libs/bms_core/tests/oauth/test_oidc_provider.py libs/bms_core/tests/idp/test_state_store.py services/identity/tests/oidc` 带 `--cov`：

| 模块 | 语句 | 覆盖 |
| --- | --- | --- |
| `bms_core.oauth.oidc_provider` | 106 | 100% |
| `bms_core.oauth.oidc_jwt` | 98 | 100% |
| `bms_identity.services.oidc_provider` | 185 | 100% |
| `bms_identity.services.clients` | 94 | 100% |
| `bms_identity.api.oidc` | 140 | 100% |
| `bms_identity.api.clients` | 81 | 100% |
| `bms_identity.repositories.client` | 25 | 100% |
| `bms_identity.models.client` | 14 | 100% |
| **合计** | **743** | **100%** |

## 5. 端到端证据 <a id="e2e"></a>

- **授权码流程 E2E（ASGI 内存客户端 + 真实 JWT 签验）**：`test_e2e.py::test_end_to_end_flow` —— 登录态（测试用户令牌）→ `GET /api/v1/oidc/authorize`（PKCE S256）→ 302 回跳含 `code` / `state` → `POST /api/v1/oidc/token`（basic）→ 返回 `id_token`（`aud=client_id`）+ `access_token` → `GET /api/v1/oidc/userinfo` 返回 `sub=1001` / `preferred_username=alice` / `name=Alice`。
- **Discovery / JWKS 合规**：`test_discovery.py` 断言标准字段与 `issuer` / 端点前缀一致；`jwks` 公钥 `kid` 带 `usr-` 前缀（与用户令牌密钥同源）。
- **M6「BMS 作 IdP 通过」证据**：上述 E2E + 授权码一次性（`test_token_code_replay` 重放 `invalid_grant`）+ scope 校验（`test_authorize_invalid_scope_redirects_error`）+ PKCE 校验（`test_token_pkce_mismatch`）。
- **客户端管理闭环**：`test_clients.py::test_create_and_use_client`（注册产物直接换码）、`test_reset_secret_invalidates_old`（旧密钥失效、新密钥可用）、`test_status_disable_blocks_authorize`（停用即拒）。

## 6. 偏差与遗留 <a id="deviations"></a>

- **偏差**：
  1. `/authorize` 未登录行为：配 `login_url` 时 302 到登录页（附 `return_to`），未配则 401 标准错误——与设计 §3.4 / §3.8 一致。
  2. OIDC 端点错误统一为标准 OAuth2 `{error, error_description}`（端点边界捕获 `OidcError`），客户端管理接口走平台统一响应——与设计 §3.7 一致。
- **遗留**：
  1. 客户端管理页面、Client Credentials、IP 白名单生效、`sys_open_log` 调用审计、refresh token 与独立撤销（**归口：阶段十**）。
  2. 浏览器 SSO 会话 cookie 联动与 `return_to` 登录页落点（**归口：域五**）。
  3. ID Token / userinfo 的 `email` 声明（**归口：用户管理阶段**）。
  4. 生产 issuer 域与租户子域规划、密钥轮换演练、第三方 OIDC 一致性测试（**归口：运维 / 阶段验收 M6**）。
  5. 真机冒烟（mjbk + 网关）随任务收尾窗口执行并留痕（**归口：本任务收尾**）。

> 本文档依《[文档生成规范](../../../../../../规范/文档生成规范.md)》编写

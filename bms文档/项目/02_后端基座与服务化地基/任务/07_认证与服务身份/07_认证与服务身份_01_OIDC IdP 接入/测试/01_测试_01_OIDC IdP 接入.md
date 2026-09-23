# OIDC IdP 接入测试记录

> 后端基座与服务化地基 · 07 认证与服务身份 · 01 OIDC IdP 接入 · 测试记录

[文档首页](../../../../../../文档首页.md) › [01 OIDC IdP 接入](../07_认证与服务身份_01_OIDC IdP 接入.md) › 01 测试　|　[详细设计](../设计/01_详细设计_01_OIDC IdP 接入.md) · [实施记录](../实施/01_实施_01_OIDC IdP 接入.md)

## 1. 测试信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 任务 | [01 OIDC IdP 接入](../07_认证与服务身份_01_OIDC IdP 接入.md) |
| 对应需求 | [07-1](../../../../需求/07_需求_认证与服务身份.md#r07-1) |
| Kiwi 用例 | **2179**（策展 1 条，多条断言共用；先登记后编码） |
| 测试日期 | 2026-09-23 |
| 测试人 | minjian |
| 测试环境 | 开发机（Python 3.14 / pytest）；mjbk（Docker，Keycloak 26.7.4） |

## 2. 用例设计与覆盖 <a id="cases"></a>

| 用例 / 文件 | 类型 | 断言要点 | 结果 |
| --- | --- | --- | --- |
| `services/identity/tests/idp/test_oidc.py::test_authorize_builds_authorization_url` | 单元 | 授权 URL 含 `response_type=code` / `client_id` / `redirect_uri` / `scope` / `state` | 通过 |
| `...::test_exchange_token_and_userinfo_mapping` | 单元 | 换码映射 `IdentityToken`（含 `id_token` / `refresh_token` / `expires_in`）；userinfo 映射 `IdentityUser`（`idp_key=issuer`） | 通过 |
| `...::test_verify_token_success` | 单元 | 经 JWKS 验签通过并回读 `IdentityClaims`（`idp_key=issuer` / `audience` / `expires_at` / `payload`） | 通过 |
| `...::test_verify_token_rejects_bad_tokens` | 单元 | 签名错 / 过期 / `iss` 不符 / `aud` 不符 / 对称算法（HS256）非白名单均抛 `AuthError` | 通过 |
| `...::test_verify_token_refreshes_jwks_on_kid_miss` | 单元 | 首次 JWKS 无匹配 `kid` 时强制刷新一次再验签（密钥轮换），JWKS 拉取 2 次 | 通过 |
| `...::test_verify_token_list_audience` | 单元 | `aud` 为数组时归一化为元组并按给定受众命中 | 通过 |
| `...::test_verify_token_without_iat` | 单元 | 缺失 `iat` / `aud` 时归属一化（时间 0、受众空），不整体失败 | 通过 |
| `...::test_jwks_error_branches` | 单元 | JWKS 端点不可达 → `ServiceUnavailableError`；响应非对象 / 非法内容 → `AuthError` | 通过 |
| `...::test_token_endpoint_non_object_response` | 单元 | 令牌端点响应非对象 → `ConfigError` | 通过 |
| `...::test_idp_unreachable_and_missing_endpoint` | 单元 | Discovery 不可达 → `ServiceUnavailableError`；缺字段 → `ConfigError` | 通过 |
| `...::test_identity_provider_settings_and_factory` | 单元 | `IdentityProviderSettings` 默认值；工厂配置不全 `PluginError`；配置齐产出 `OidcIdentityProvider` | 通过 |
| `...::test_oidc_provider_resolves_in_app` | 装配（独立子进程） | `provider=oidc` 且配置齐时应用可启动、`app.state.identity_provider` 解析到 `OidcIdentityProvider` | 通过 |
| `...::test_realm_deployment_has_no_plaintext_secret` | 部署件护栏 | `deploy/keycloak/bms-realm.json` 可解析、客户端字段正确、secret 为 `${KEYCLOAK_CLIENT_SECRET}` 占位（无明文） | 通过 |
| `...::test_real_keycloak_jwks_verification` | 集成（`@pytest.mark.integration`） | 真实 Keycloak：`client_credentials` 取令牌 → `verify_token` 经 JWKS 通过 | 通过（mjbk） |
| `services/identity/tests/idp/test_idp.py::test_contract_extensions` | 单元 | `IdentityToken` 增字段默认 / 赋值；`IdentityUser.idp_key` 默认；`IdentityClaims` 不可变 | 通过 |
| `...::test_verify_token_default_and_null` | 单元 | `BaseIdentityProvider.verify_token` 默认抛 `ConfigError`；占位实现返回占位声明 | 通过 |

## 3. 门禁结果 <a id="gates"></a>

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 全量用例 | `uv run pytest -q --cov=bms_core --cov-branch` | 1208 passed / 37 skipped；总体覆盖率 96% |
| 新增模块覆盖率 | `uv run pytest services/identity/tests/idp --cov=bms_core.idp --cov-branch` | idp 包语句 + 分支 **100%** |
| 静态检查 | `ruff check .` / `ruff format --check .` / `pyright` | 全通过（0 error） |
| 基座校验 | `check-base.py` / `check-backend-base.py` / `check-service-boundaries.py` / `check-status.py --stage 02_后端基座与服务化地基` | 全通过 |
| 本地预检 | `check-preflight.py --fast` | 全通过 |

## 4. mjbk 真实冒烟 <a id="smoke"></a>

Keycloak 26.7.4（容器 `bms-keycloak`，元数据复用 `bms-postgres` 独立库 `keycloak`），realm `bms` 启动自动导入；issuer `http://<mjbk-IP>:8090/realms/bms`：

| 场景 | 操作 | 观察结果 |
| --- | --- | --- |
| 容器健康 | `docker inspect --format '{{.State.Health.Status}}' bms-keycloak` | **healthy**；日志 `Realm 'bms' imported` → `Bootstrap completed` |
| Discovery | `curl <issuer>/.well-known/openid-configuration` | `issuer` 与配置基址一致；`jwks_uri` / `token_endpoint` / `userinfo_endpoint` 齐备 |
| JWKS 公钥 | `curl <issuer>/protocol/openid-connect/certs` | 2 个 RSA 公钥（`alg=RS256`） |
| 令牌验签通过 | 服务账号 `client_credentials` 取令牌 → `OidcIdentityProvider.verify_token` | **通过**：`claims.issuer == issuer`、`claims.idp_key == issuer`、`subject` 非空 |
| 集成用例 | `IDP_TEST_*` + `pytest services/identity/tests/idp/test_oidc.py -k real_keycloak` | 1 passed（真实 Keycloak，非跳过） |
| 清理 | 无（Keycloak 为常驻身份源，保留运行） | 部署件与本机 `deploy/keycloak/` 一致 |

## 5. 偏差与遗留 <a id="deviations"></a>

- **偏差**：客户端以 authlib 的 JOSE 拆分包 `joserfc` + `httpx` 实现（authlib `jose` 模块与 `integrations.httpx_client` 弃用告警）；postgres 初始化脚本用 `.sh` 读环境变量（避免明文密码）——均已登记实施记录 §4 / §7。
- **遗留（归口）**：双类 JWT 与 JWKS 分发 → **07_02**；网关 `openid-connect` 接线与服务 JWT 校验 → **07_03**；完整登录链路 / CAS / 企微钉钉 / JIT 建号 → **阶段六 / 七**；生产 TLS 与 K8s 平移 → **部署阶段**。
- 用例编号以平台回读（**2179**）为准，代码 `@pytest.mark.kiwi_id(2179)` 标注一致（`test_oidc.py` / `test_idp.py`）。

> 依《文档生成规范》编写 · 与《实施记录》配套

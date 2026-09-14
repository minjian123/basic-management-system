# 开放接口 OAuth2 服务端与 scope 基座详细设计

> 项目骨架 · 02 后端基座 · 03 core 横切基座 · 13 开放接口OAuth2服务端与scope基座 · 详细设计

[文档首页](../../../../../../../文档首页.md) › [02-3-13 开放接口OAuth2服务端与scope基座](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md) › 01 详细设计　|　[← 父任务](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md)

## 1. 概述 <a id="overview"></a>

- **目标**：落地开放接口服务端两组契约与占位实现——`app/oauth/base.py` 的数据契约 `ClientCredentials` / `OAuthToken`、服务端契约 `BaseOAuthServer`（`issue_token` / `revoke`）、scope 校验契约 `BaseScopeChecker`（`check`）、占位实现 `NullOAuthServer` / `NullScopeChecker`；常量清单 `GRANT_TYPES` / `TOKEN_TYPE_BEARER`；`app/api/deps.py` 新增提供者 `get_oauth_server` / `get_scope_checker`；`app/main.py` 装配两单例。
- **范围**：`app/oauth/`（新增）、`app/api/deps.py`（提供者导出）、`app/main.py`（装配）、单测；架构 04 / 《后端基类清单》/《后端开发规范》/ 计划 / 需求 02-41 登记。
- **不含**（归后续阶段）：真实 authlib（OIDC Provider 授权码流程、Client Credentials 自签 JWT、scope 分配 / 回收、独立撤销黑名单、`sys_open_log` 调用审计）→ **系统集成 / 认证阶段**；`/api/open` 路由与防重放 / IP 白名单 / 按 client 限流 → **系统集成阶段**（复用 [02-3-10 限流幂等防重放中间层](../../02_后端基座_03_core横切基座_10_限流幂等防重放中间层/02_后端基座_03_core横切基座_10_限流幂等防重放中间层.md) 的 `BaseReplayGuard` / `BaseRateLimiter` / `SignatureCodec`）；用户双 token（access / refresh）→ **认证阶段**（架构 13 §2）；客户端 IdP 适配 `BaseIdentityProvider` / 会话存储 `BaseSessionStore` → **02-4-8**（需求 02-27）；`sys_client` / `sys_open_log` 落库 → 落库阶段。
- **依据**：需求 [02-41](../../../../../需求/02_需求_后端基座.md#r02-41)、《[架构设计 · 接口与集成](../../../../../../../设计/架构设计/09_架构设计_接口与集成.md)》「对外 API」节、《[架构设计 · 认证与会话](../../../../../../../设计/架构设计/13_架构设计_子系统_认证与会话.md)》「开放接口鉴权」节、《[架构设计 · 后端基础类体系](../../../../../../../设计/架构设计/04_架构设计_后端基础类体系.md)》「阶段落地（地基波 + 回补）」节、《[后端开发规范](../../../../../../../规范/后端开发规范.md)》「后端基座体系（强制）」节、《[命名规范](../../../../../../../规范/命名规范.md)》「后端命名」节。

## 2. 现状与差距 <a id="gap"></a>

| 现状 | 差距 |
| --- | --- |
| 全库无 `BaseOAuthServer` / `BaseScopeChecker` / `OAuthToken`（检索零命中）；无 `app/oauth/` 目录 | 开放接口服务端签发 / scope 校验 / 撤销无统一契约；各集成点自研会让 scope 语义与令牌形态发散 |
| 开放接口鉴权已定案（架构 09 / 13：OAuth2 Client Credentials + scope + 独立撤销 + 调用审计；BMS 兼作 OIDC Provider） | 无契约承载「服务端签发 / 撤销」与「授权面 scope 校验」 |
| 已有 `BasePermissionChecker`（内部权限码，02-3-9）与 `DataScope`（数据范围，`app/scope/`） | 开放接口的**授权面收敛（scope）**无契约；且 `app/scope/` 为数据范围注入，与 OAuth scope 语义不同，不可混用 |
| 防重放 / 限流 / 签名原语已就位（02-3-10：`BaseReplayGuard` / `BaseRateLimiter` / `SignatureCodec`） | 开放接口 ingress 的防重放 / 限流已可复用，但服务端令牌与 scope 校验尚缺 |
| 客户端侧 IdP 适配已立项（02-4-8 / 需求 02-27：`BaseIdentityProvider` / `BaseSessionStore`） | 客户端与会话存储归 02-4-8；**服务端签发 / scope** 归本任务，二者不重叠 |
| `api/deps.py` 已汇总 16 个能力域提供者 | 两个新能力域无提供者，「依赖注入可解析」无落点 |

## 3. 交付物清单 <a id="tree"></a>

```text
backend/
├── app/oauth/__init__.py                  # 新增：能力域包（docstring 口径）
├── app/oauth/base.py                      # 新增：GRANT_TYPES / TOKEN_TYPE_BEARER / NULL_ACCESS_TOKEN / ClientCredentials / OAuthToken / BaseOAuthServer / NullOAuthServer / BaseScopeChecker / NullScopeChecker / get_oauth_server / get_scope_checker
├── app/api/deps.py                        # 修改：导出 get_oauth_server / get_scope_checker
├── app/main.py                            # 修改：装配 app.state.oauth_server / app.state.scope_checker
└── tests/
    └── oauth/test_oauth.py                # 新增：Kiwi 46（契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 恒定允许 / 依赖解析）

bms文档/
├── 设计/架构设计/04_架构设计_后端基础类体系.md      # 修改：§4 基类清单 + §8 跨阶段基座契约表
├── 后端基类清单.md                                  # 修改：§2 分层总览 + §9 跨阶段基座 + §10 继承链与代码位置
├── 规范/后端开发规范.md                              # 修改：§3.1 强制用法（开放接口服务端 / scope 口径）
├── 项目/01_项目骨架/计划/01_计划_项目骨架.md        # 修改：§3.1 后续阶段待办（新增 OAuth2 服务端 / scope 真实实现行）+ 02_03 偏差跟踪
├── 项目/01_项目骨架/需求/02_需求_后端基座.md        # 修改：需求 02-41 补实现期要点注块 + 状态 / 完成日期
├── 项目/01_项目骨架/需求/00_需求_项目骨架.md        # 修改：需求总览 02-41 状态 / 完成日期回写
├── 项目/01_项目骨架/任务/02_后端基座/…13…/…13….md   # 修改：参考文档补本设计 / 实施 / 测试链接，实施后回写状态
└── 项目/01_项目骨架/任务/02_后端基座/…03….md        # 修改：子任务清单 13 状态 / 完成日期回写
```

## 4. OAuth2 服务端能力域 <a id="oauth"></a>

| 成员 | 形态 | 说明 |
| --- | --- | --- |
| `GRANT_TYPES` | `tuple[str, ...]` 常量 | 授权类型清单：`("client_credentials", "authorization_code", "refresh_token")`（Client Credentials 开放接口 / OIDC 授权码 / 刷新；占位期**仅登记不校验**） |
| `TOKEN_TYPE_BEARER` | `str` 常量 | 令牌类型 `"Bearer"`（响应 `token_type` / `Authorization` 头） |
| `NULL_ACCESS_TOKEN` | `str` 常量 | 占位令牌取值 `"null-access-token"`（`NullOAuthServer` 固定返回，便于断言与调用链贯穿） |
| `ClientCredentials` | frozen dataclass（数据契约） | 客户端凭证：`client_id: str` / `client_secret: str` / `scopes: tuple[str, ...] = ()` |
| `OAuthToken` | frozen dataclass（数据契约） | 令牌响应：`access_token: str` / `token_type: str = TOKEN_TYPE_BEARER` / `expires_in: int = 0` / `scopes: tuple[str, ...] = ()` |
| `BaseOAuthServer(BaseCapability, ABC)` | 能力域契约中间层 | `key: str = "oauth_server"` |
| `issue_token(credentials) -> OAuthToken` | 抽象方法（async） | Client Credentials 签发（真实实现自签 JWT 短 TTL + scope 收敛 + 调用审计） |
| `revoke(token) -> None` | 抽象方法（async） | 独立撤销（真实实现解析 jti 入黑名单 / 吊销） |
| `NullOAuthServer(BaseOAuthServer, BaseNullObject)` | 占位实现 | `issue_token` 固定返回占位令牌（`NULL_ACCESS_TOKEN` / `expires_in=0` / `scopes=()`，**不签发、不落库存**）；`revoke` 空操作 |
| `get_oauth_server(request) -> BaseOAuthServer` | 模块函数（提供者） | 取应用级单例（`request.app.state.oauth_server`） |

**口径**：

| 情形 | 处置 |
| --- | --- |
| `issue_token` 入参 | 以 `ClientCredentials` 数据契约传入（`client_id` / `client_secret` / 可选 `scopes`），便于后续扩展（如 grant_type、redirect_uri）而不改方法签名 |
| `issue_token` 返回 | `OAuthToken`（贴 OAuth2 令牌响应语义，含 `scopes` 供 scope 校验读取）；占位固定 `NULL_ACCESS_TOKEN`、`expires_in=0`、`scopes=()` |
| `revoke` 入参 | access token 字符串；实现内部解析 jti / 黑名单（调用方无需知道 jti） |
| 授权类型 | `GRANT_TYPES` 登记三种；Client Credentials（开放接口）与 OIDC 授权码（BMS 兼作 IdP）均属真实实现，占位不校验 |
| 与用户双 token | 本契约只覆盖**开放接口 client 侧**（Client Credentials）；用户 access / refresh 双 token 归认证阶段（架构 13 §2），两者不混用 |
| 与防重放 / 限流 | `/api/open` ingress 的防重放与限流取 02-3-10 已交付契约，本域不重复 |
| 安全默认 | 真实实现按 client 注册 scope 最小化分配、写接口需显式授予；占位固定返回不体现该策略（回补阶段落地） |

## 5. scope 校验能力域 <a id="scope"></a>

| 成员 | 形态 | 说明 |
| --- | --- | --- |
| `BaseScopeChecker(BaseCapability, ABC)` | 能力域契约中间层 | `key: str = "scope_checker"` |
| `check(granted, required) -> bool` | 抽象方法（同步） | 判定已授权 scope 是否覆盖接口所需 scope（`granted: Iterable[str]` / `required: str`） |
| `NullScopeChecker(BaseScopeChecker, BaseNullObject)` | 占位实现 | **恒定允许**（返回 `True`，不校验，未接入真实 scope 体系时使用） |
| `get_scope_checker(request) -> BaseScopeChecker` | 模块函数（提供者） | 取应用级单例（`request.app.state.scope_checker`） |

**口径**：

| 情形 | 处置 |
| --- | --- |
| 签名 | **同步纯比对**（与 `BasePermissionChecker.check` 同款，无 IO）：`granted` 来自 access token 的 scope、`required` 为接口声明 scope |
| 与权限码分工 | scope 为**授权面收敛**（第三方应用可访问范围），权限码校验仍走 `BasePermissionChecker`（`require_permission`）；开放接口两级叠加——**先 scope 后权限码**（架构 13 §7、[02-3-13 任务文档](../02_后端基座_03_core横切基座_13_开放接口OAuth2服务端与scope基座.md) 协同契约） |
| 与数据范围区分 | `app/scope/` 的 `DataScope` 是**数据范围注入**（行级过滤），与本域 OAuth scope 语义不同；两者命名接近但用途无关，本域落 `app/oauth/` 避免混淆 |
| 通配 / 层级 | 真实实现是否支持通配（如 `user:*`）由实现决定；占位恒定通过 |
| 写接口安全默认 | 真实实现中写接口（POST / PUT / DELETE）需显式授予 scope；占位不体现 |

## 6. 依赖注入与应用装配 <a id="di"></a>

| 位置 | 变更 |
| --- | --- |
| `app/api/deps.py` | 导出 `get_oauth_server` / `get_scope_checker`（`app/oauth/base.py`）；模块 docstring 补「开放接口」 |
| `app/main.py` `create_app()` | 装配 `app.state.oauth_server = NullOAuthServer()`、`app.state.scope_checker = NullScopeChecker()`（置于能力域基座装配段） |

两个提供者为普通同步函数（取 `app.state` 单例，无 IO）；本任务**不落 `/api/open` 路由**（真实开放接口路由含 token / 撤销 / 调用，归系统集成 / 认证阶段），故无中间件与路由改动。

## 7. 继承与分层 <a id="base"></a>

- `BaseOAuthServer` / `BaseScopeChecker → BaseCapability → BaseObject`；`NullOAuthServer` / `NullScopeChecker → 对应契约 + BaseNullObject → BasePlaceholder → BaseObject`。
- `ClientCredentials` / `OAuthToken` 为能力域数据契约（frozen dataclass，同 `SpanContext` / `HealthCheckResult` / `RateLimitDecision` 风格）。
- 与 `BasePermissionChecker` / `DataScope` 三方分工：**OAuth scope（授权面）→ 权限码（功能面）→ 数据范围（行级）**，逐层收敛，互不替代。

## 8. 登记落点 <a id="register"></a>

| 落点 | 登记内容 |
| --- | --- |
| 《架构设计 · 后端基础类体系》§4 基类清单 | 新增行（`ClientCredentials` / `OAuthToken`、`BaseOAuthServer` / `NullOAuthServer`、`BaseScopeChecker` / `NullScopeChecker`）+ 继承链补两条 |
| 《架构设计 · 后端基础类体系》§8 跨阶段基座契约表 | 新增「开放接口 OAuth2 服务端 / scope」行（代码位置、契约、回补阶段＝**系统集成 / 认证阶段**） |
| 《架构设计 · 后端基础类体系》§6 core 横切基座 | 补「开放接口鉴权三层分工」口径（scope / 权限码 / 数据范围） |
| 《后端基类清单》 | §2 分层总览补 `app/oauth/`；§9 跨阶段基座补一行；§10 继承链与目录补两条 |
| 《后端开发规范》「后端基座体系」节 §3.1 | 补口径：开放接口服务端签发 / 撤销一律走 `BaseOAuthServer`（`issue_token` / `revoke`，入参 `ClientCredentials`、返回 `OAuthToken`），scope 校验一律走 `BaseScopeChecker.check`（先 scope 后权限码）；禁止自研令牌签发 / 撤销或另立 scope 判定 |
| 计划《01_计划_项目骨架》§3.1「后续阶段待办」 | 新增「开放接口 OAuth2 服务端 / scope 真实实现（authlib OIDC Provider + Client Credentials + scope 分配回收 + 撤销 + `sys_open_log` 审计）」行，出处 02-3-13；02_03 表「偏差与遗留」补 02-3-13 |
| 需求 [02-41](../../../../../需求/02_需求_后端基座.md#r02-41) | 参考文档后补 `> 注：实现期要点` 块；实施完成后回写状态 / 完成日期 |
| 需求总览《00_需求_项目骨架》 | 02-41 行状态 / 完成日期随实施回写 |
| 02-3-13 任务文档 | 参考文档补本设计 / 实施 / 测试链接；实施后回写状态 / 完成日期 |

## 9. 测试设计（Kiwi 46 先行） <a id="tests"></a>

用例**先登记 Kiwi TCMS 再编码**；本任务新分配 **Kiwi 46**（平台登记后回填编号，题面与平台一致）：

| Kiwi | 用例 | 断言要点 | 自动化文件 |
| --- | --- | --- | --- |
| 46 | 服务端契约继承与能力域标识 | `NullOAuthServer → BaseOAuthServer → BaseCapability → BaseObject`；`placeholder` / `describe()`；`key == "oauth_server"` | `tests/oauth/test_oauth.py` |
| 46 | scope 契约继承与能力域标识 | `NullScopeChecker → BaseScopeChecker → BaseCapability → BaseObject`；`key == "scope_checker"` | 同上 |
| 46 | 授权类型与令牌类型常量 | `GRANT_TYPES` 三项无重复；`TOKEN_TYPE_BEARER == "Bearer"` | 同上 |
| 46 | 数据契约默认值与不可变 | `ClientCredentials` / `OAuthToken` 默认值正确（`scopes=()` / `token_type=Bearer` / `expires_in=0`）；frozen 不可赋值 | 同上 |
| 46 | 占位服务端固定返回（不签发） | 任意 `ClientCredentials` 入参 `issue_token` 均返回同一占位令牌（`NULL_ACCESS_TOKEN` / `expires_in=0` / `scopes=()`） | 同上 |
| 46 | 占位撤销空操作 | `revoke` 返回 `None`、不抛错 | 同上 |
| 46 | 占位 scope 恒定允许 | `NullScopeChecker.check` 对任意 `granted` / `required` 组合返回 `True` | 同上 |
| 46 | 两提供者依赖解析 | `create_app()` 装配两单例；探针路由经 `Depends(get_oauth_server)` / `Depends(get_scope_checker)` 取到同一实例 | 同上 |

回归：全量 `pytest`（含接口冒烟）。

## 10. 实施步骤 <a id="steps"></a>

1. 新增 `app/oauth/`（`GRANT_TYPES` / `TOKEN_TYPE_BEARER` / `NULL_ACCESS_TOKEN` / `ClientCredentials` / `OAuthToken` / `BaseOAuthServer` / `NullOAuthServer` / `BaseScopeChecker` / `NullScopeChecker` / `get_oauth_server` / `get_scope_checker`）。
2. `app/api/deps.py` 导出两提供者；`app/main.py` 装配 `app.state.oauth_server` / `app.state.scope_checker`。
3. 测试：先登记 Kiwi 46，再写 `tests/oauth/test_oauth.py`。
4. 登记：架构 04 §4 / §6 / §8、《后端基类清单》§2 / §9 / §10、《后端开发规范》§3.1、计划「后续阶段待办」+ 02_03 偏差跟踪、需求 02-41 注块与状态、需求总览、任务 / 父任务状态。
5. 验证：`uv run pytest --cov=app -q`、`uv run ruff check .`、`uv run ruff format --check .`、`uv run pyright` 全绿；`python3 scripts/tools/base-check/check-base.py` 通过。
6. 回写：实施 / 测试记录 + 任务（02-3-13、02_03 core 横切基座）与需求 02-41 状态、计划表。
7. 收尾：按「处理偏差与遗留」套路闭环后提交。

## 11. 验收映射 <a id="accept-map"></a>

| 完成标准（需求 02-41 / 任务 02-3-13） | 验证方式 |
| --- | --- |
| 接口 / 抽象声明就位、可被上层引用 | 三契约（server / scope + 数据契约）落地 + 继承 / 契约断言 + Kiwi 46 |
| 依赖注入可解析、应用可启动不报错 | `create_app` 装配两单例 + 两提供者解析用例 + 应用冒烟 |
| 占位实现固定返回（不签发 / 恒定允许） | `NullOAuthServer.issue_token` 固定占位令牌、`revoke` 空操作；`NullScopeChecker.check` 恒 True；无 authlib / Redis 依赖 |
| 常量清单登记 | `GRANT_TYPES` 三项 + `TOKEN_TYPE_BEARER` 用例 |
| 不实现真实能力 | 无 authlib 依赖、无 `/api/open` 路由、无令牌存储 / 黑名单 / 审计落库 |
| 登记齐备 | 架构 04 §4 / §6 / §8、《后端基类清单》§2 / §9 / §10、《后端开发规范》§3.1、计划「后续阶段待办」 |
| 无 lint / 类型错误 | `uv run ruff check .`、`uv run ruff format --check .`、`uv run pyright` |

## 12. 边界与开放项 <a id="boundary"></a>

- **真实 authlib 服务端**（OIDC Provider 授权码流程、Client Credentials 自签 JWT 短 TTL、scope 分配 / 回收、独立撤销黑名单、`sys_open_log` 调用审计）→ 系统集成 / 认证阶段；已登记计划「后续阶段待办」。
- **`/api/open` 路由与 ingress 防护**（前缀隔离、防重放、IP 白名单、按 client 限流）→ 系统集成阶段；复用 02-3-10 `BaseReplayGuard` / `BaseRateLimiter` / `SignatureCodec` 与 02-3-13 任务文档协同契约。
- **用户双 token**（access / refresh、会话、踢出）→ 认证阶段（架构 13 §2）；与开放接口 client 令牌不混用。
- **客户端 IdP 适配与会话存储**（`BaseIdentityProvider` / `BaseSessionStore`）→ 02-4-8（需求 02-27）。
- **开放接口管理模块**（scope 分配 / 回收、IP 白名单、客户端注册 `sys_client`）→ 系统集成阶段；`sys_client` / `sys_open_log` 落库 → 落库阶段。
- **占位语义已知项**：占位令牌为常量串、不反映真实签发与 scope 收敛（已知、可接受）；真实判定随回补阶段生效。
- **测试**：真实签发 / scope 校验 / 撤销用例（JWT 校验、scope 最小化、撤销后拒绝）随回补阶段补充。

## 13. 对齐记录 <a id="align"></a>

| # | 事项 | 结论 |
| --- | --- | --- |
| 1 | 代码落点 | `app/oauth/base.py`（一域一目录；避开既有 `app/scope/` 数据范围与 openapi 文档术语）（用户拍板） |
| 2 | 能力域拆分 | `BaseOAuthServer` + `BaseScopeChecker` 两契约同模块、各提供者（按需求 02-41）（用户拍板） |
| 3 | 令牌返回契约 | 新增 `OAuthToken`（`access_token` / `token_type` / `expires_in` / `scopes`）frozen 数据契约（用户拍板） |
| 4 | `issue_token` 入参 | 以 `ClientCredentials` 数据契约对象传入（`client_id` / `client_secret` / `scopes`），便于扩展（用户拍板） |
| 5 | `revoke` 入参 | `revoke(token)` 按 access token 字符串，实现内部解析 jti / 黑名单（用户拍板） |
| 6 | `BaseScopeChecker.check` | **同步纯比对** `check(granted, required) -> bool`（与 `BasePermissionChecker.check` 同款）（用户拍板） |
| 7 | `/api/open` 路由 | **不落路由**；仅契约 + 占位 + 提供者，真实路由归系统集成 / 认证阶段（用户拍板） |
| 8 | 常量清单 | `GRANT_TYPES`（三项）+ `TOKEN_TYPE_BEARER`，占位期登记不校验（用户拍板） |
| 9 | 占位语义 | `NullOAuthServer` 固定返回占位令牌（`NULL_ACCESS_TOKEN` / `expires_in=0` / `scopes=()`）且 `revoke` 空操作；`NullScopeChecker` 恒定允许（混合口径同 02-3-11 / 02-3-12） |
| 10 | 三层分工 | OAuth scope（授权面）→ 权限码 `BasePermissionChecker`（功能面）→ 数据范围 `DataScope`（行级），逐层收敛 |
| 11 | 依赖注入 | `get_oauth_server` / `get_scope_checker` + `app.state.oauth_server` / `app.state.scope_checker` 两单例 |
| 12 | 异步口径 | 服务端签发 / 撤销异步（含密钥与存储 IO）；scope 校验同步（纯比对，无 IO） |
| 13 | 登记落点 | 架构 04 §4 / §6 / §8、《后端基类清单》§2 / §9 / §10、《后端开发规范》§3.1、计划「后续阶段待办」+ 02_03 偏差、需求 02-41 注块、需求总览 |
| 14 | 测试 | 新分配 Kiwi 46（平台登记 + `@pytest.mark.kiwi_id(46)`），8 条 |
| 15 | 交付范围 | 一条龙（设计 / 实施 / 测试 / 登记 / 记录 / 提交推送）+ 随后独立「处理偏差与遗留」 |
| 16 | 工时 / 窗口 | 1h；02_03 core 横切基座窗口（2026-09-14 ~ 09-20） |

> 本文档依《文档生成规范》编写 · 关键决策逐项确认

# authlib 技术介绍

> OAuth/OIDC 协议库 · BMS 统一认证与 SSO

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › authlib 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**authlib** 是 Python 生态中功能最全的 OAuth/OIDC 协议库：一个库同时覆盖
**客户端（Client）**与**服务端（Provider/Server）**两侧，
支持 OAuth 1.0、OAuth 2.0、OpenID Connect（OIDC）与 CAS 等协议。
它让"接入外部身份提供方"和"对外提供统一认证"都只需配置化编码，无需手写协议细节。

- **定位**：BMS 的 SSO 统一认证——作为客户端接入租户外部 IdP，同时提供 OIDC Provider 能力，并兼容 CAS 协议。
- **版本**：持续迭代的 1.x 系列，API 稳定。
- **许可**：BSD-3-Clause，OSI 认证开源。
- **依赖**：底层使用 requests/httpx 发起认证流程，无需自建协议栈。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| OIDC（OpenID Connect） | 建立在 OAuth 2.0 之上的身份认证层：授权码 + ID Token（含用户身份 claims），本项目 SSO 主力协议 |
| ID Token | OIDC 签发、由 IdP 签名的 JWT，携带 `sub`（用户主体）、`iss`（签发方）等身份声明，客户端验签后即得用户身份 |
| IdP / OP / RP | 身份提供方（IdP，OIDC 中称 OP）；依赖方（RP，即 BMS 这类接入方）——接入方只信任 IdP 的令牌 |
| 授权码模式（Authorization Code） | 浏览器跳 IdP 登录 → 回跳带一次性授权码 → 后端换令牌；用户密码永不经 BMS，本项目主用该流程 |
| PKCE | 授权码模式附加的防拦截挑战（code_verifier/code_challenge），尤其适合无密客户端与移动端免登 |
| Provider（服务端） | authlib 也可让 BMS 充当 IdP：对外发布 OIDC discovery 文档、签发 ID Token 与访问令牌 |
| CAS 协议 | 经典单点登录协议（ticket 校验）；authlib 客户端支持 CAS，用于兼容遗留系统 |
| JIT 建号（Just-In-Time Provisioning） | SSO 首次登录时按 IdP 返回的身份自动创建本地账号，无需管理员预建 |
| 身份映射（sys_user_identity） | 外部 IdP 的用户标识 ↔ BMS 本地账号的映射表；回跳后经全局映射定位租户并关联账号 |
| Discovery（发现文档） | IdP 发布 `/.well-known/openid-configuration`，RP 自动获取端点与算法配置，免手填 |
| 企业微信/钉钉免登 | 第三方 OAuth 变体，复用同一外部身份框架：内嵌 H5 静默授权 → 取身份 → 映射账号 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

按《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节与 3.1 节选型说明：

- **OIDC 客户端（主）**：接入各租户外部 IdP（Keycloak / AD / Authing 等），登录页展示租户配置的 IdP 入口（`sys_identity_provider`），授权码 + PKCE 流程，Discovery 自动获取端点。
- **CAS 兼容**：对仍使用 CAS 协议的遗留 IdP 保持兼容，同一身份框架内切换。
- **OIDC Provider（BMS 兼作统一认证源）**：其他系统以 BMS 租户用户体系为统一认证源，走 OIDC 接入（2.1 节"SSO"、12 节"BMS 兼作 IdP"）。
- **JIT 自动建号**：外部 IdP 认证回跳后经 `sys_user_identity` 全局映射定位租户并自动建号，随后签发 BMS 双 token（见《[JWT 技术介绍](JWT与PBKDF2技术介绍.md)》）。
- **本地登录并存**：本地账号密码登录作为超管应急通道保留（防 IdP 故障锁死系统）。
- **企业微信/钉钉免登**：内嵌 H5 走各自 OAuth 免登，复用外部身份框架（12 节移动端免登）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **authlib（选中）** | 客户端 + Provider + CAS 一库全包，协议实现经过广泛生产验证，与 FastAPI 异步栈可用 | 同时满足"接入外部 IdP"与"BMS 作 IdP"双向需求，生态最省心 |
| python-jose + 手写 OIDC 流程 | 轻量但只解决 JWT 加解密，授权码/token 交换/Discovery 全要自研，安全细节易错 | 重复造轮子且风险高，不采用 |
| python3-openid / oic | 仅覆盖 OIDC 客户端，无 Provider、无 CAS，维护活跃度一般 | 功能覆盖面不足，不采用 |
| Keycloak 全家桶接管认证 | 功能强但引入重型依赖，租户 IdP 各有不同，强绑 Keycloak 不可行 | 与"多租户多 IdP"架构冲突，不采用 |
| 自研认证网关 | 完全可控但成本高、周期长 | 不必要，直接用成熟协议库 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **redirect_uri 必须白名单校验**：authlib 配置的授权回跳地址必须是注册过的精确 URI，否则成为开放重定向漏洞；生产用 https。
- **state 参数防 CSRF**：发起授权时必须生成并校验 state（随机串，回跳时比对），防登录流程 CSRF；会话间校验失败直接拒绝。
- **ID Token 必须验签 + 校验 iss/aud/exp**：使用 Discovery 拉取的 JWKS 验签；`iss` 与配置的 IdP 一致、`aud` 是本系统 client_id，防止跨 IdP 令牌混用。
- **JIT 建号不能盲目信任外部身份**：建号/关联账号前按租户 IdP 配置做邮箱/域校验与唯一性检查，避免身份注入或账号接管。
- **Provider 侧密钥与 scope 管理**：BMS 作 IdP 时，client 注册、密钥轮换、scope 最小化都要走管理界面，勿硬编码。
- **移动端免登注意 UA 与回调**：企业微信/钉钉 OAuth 回调走各自 webview，注意 redirect_uri 域名备案与 https；token 仍按 BMS 双 token 机制管理。
- **与 Redis 会话校验协同**：SSO 登录签发的令牌同样受会话标记与黑名单约束，踢出/登出逻辑对 SSO 账号一视同仁。
- **升级兼容**：authlib 1.x 与 0.x 的 API 差异较大，锁定依赖版本（uv.lock）后升级需跑认证链路全量用例。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| authlib 官方文档 | https://docs.authlib.org/ | 客户端/服务端全部用法与示例，权威 |
| authlib GitHub | https://github.com/authlib/authlib | 源码与 issue 讨论 |
| OpenID Connect 官方规范 | https://openid.net/connect/ | OIDC 协议说明与规范入口 |
| OAuth 2.0 RFC 6749 | https://datatracker.ietf.org/doc/html/rfc6749 | 授权码等模式的标准定义 |
| OIDC Playground | https://openidconnect.net/ | 在线演练授权码流程，联调 IdP 时排查用 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 | SSO 登录、JIT 建号、本地应急登录、移动端免登全套设计 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 | authlib 选型理由（OIDC 为主 + CAS 兼容） |
| 《[JWT 技术介绍](JWT与PBKDF2技术介绍.md)》 | SSO 回跳后签发双 token 的认证骨架 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 会话标记与踢出即时生效 |
| 《[项目规划说明](../../../规划/项目规划说明.md#integ-in)》9.2 节 | BMS 对外提供认证能力的出站集成视角 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
# JWT 与 PBKDF2 技术介绍

> 无状态令牌 + 密码哈希 · BMS 认证基石

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › JWT 与 PBKDF2 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**JWT**（JSON Web Token）是一种**自包含的令牌**格式：把用户身份、有效期等信息
签名后放进一个紧凑的字符串，服务端无需保存会话即可校验令牌真伪——这就是"无状态认证"。
**PBKDF2**（Password-Based Key Derivation Function 2）是标准化的**密码哈希算法**：
通过加盐 + 重复迭代把密码变成不可逆的哈希值，用于安全存储密码。
两者构成 BMS 认证体系的两个支柱：签发/校验令牌 + 存储密码。

- **定位**：JWT 做访问令牌（access/refresh 双 token），PBKDF2 做本地账号密码哈希（Python 标准库实现）。
- **实现**：JWT 用 PyJWT（持续迭代的 2.x 系列）；PBKDF2 用标准库 `hashlib.pbkdf2_hmac`，零第三方依赖。
- **许可**：PyJWT 为 MIT，OSI 认证开源；PBKDF2 为算法/标准，标准库实现随 Python（PSF-2.0）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| JWT 三段式结构 | `header.payload.signature`：头（算法）、载荷（claims）、签名（防篡改），三段 Base64URL 拼接 |
| Claims（声明） | 载荷里的字段：`sub`（用户）、`iat`（签发时间）、`exp`（过期时间）、`jti`（令牌唯一 ID，用于黑名单）等 |
| 签名算法 | HS256（对称：同一密钥签/验）与 RS256（非对称：私钥签、公钥验）为常用选项；项目用 HS256，密钥可轮换 |
| access token / refresh token | 短效令牌（本项目 30 分钟）+ 长效刷新令牌（14 天、滚动轮换），兼顾安全与体验 |
| 无状态认证 | 服务端不存会话即可验签通过；但 BMS 为支持"踢出即时生效"，额外随 token 校验 Redis 会话有效标记（见下节） |
| 黑名单（Blacklist） | 登出/被盗后把令牌 `jti` 写入 Redis 黑名单即时失效，弥补"自包含令牌无法撤销"的短板 |
| PBKDF2 密码哈希 | 密码 + 随机盐 → 迭代 HMAC 多次 → 定长哈希；攻击者只能逐盐爆破，成本极高 |
| 盐（Salt） | 每个用户独立的随机值，与密码一起参与哈希；防彩虹表、防同密码同哈希 |
| 迭代次数 | 重复哈希轮数，越大越慢；按硬件水平取"单次校验 ~100ms"量级，可随时间调高 |
| 哈希 vs 加密 | 哈希不可逆、只做比对（`hashlib.compare_digest` 常量时间比较）；密码绝不加密存储 |
| 滚动轮换（Rotation） | 刷新时签发新 refresh token 并作废旧 token（记录其 `jti`），限制令牌泄露窗口 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

按《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节"认证与安全"与 3.1 节选型说明：

- **双 token 机制**：access token（30 分钟）+ refresh token（14 天，滚动轮换）；access token 仅存前端内存（刷新页面后静默续期），refresh token 存 httpOnly + Secure + SameSite cookie，防 XSS 窃取。
- **横向扩展友好**：JWT 自包含、服务端无会话存储，多实例/多副本无需共享会话数据；鉴权时随 access token 一并校验 Redis 会话有效标记（每请求一次 Redis 读，毫秒级开销），强制踢出即时生效——这是"无状态 + 可撤销"的折中设计（3.1 节、19.2 节）。
- **token 黑名单**：登出时 refresh token 的 `jti` 加入 Redis 黑名单（`bms:global:token:blacklist:{jti}`）即时失效；重置密码成功后强制失效该账号全部会话。
- **PBKDF2 密码哈希**：标准库 `hashlib.pbkdf2_hmac` 实现，无第三方依赖；配合密码策略（复杂度校验、90 天有效期强制改密、近 5 次历史密码不可重复、180 天未登录自动锁定）。
- **密钥管理**：JWT secret 支持轮换（新旧并行验证期），走 Secret 管理，不落库不入镜像（12 节、17 节）。
- **SSO 协同**：外部 IdP 认证回跳后签发 BMS 双 token，本地账号密码登录作为超管应急通道并存（见《[authlib 技术介绍](authlib技术介绍.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **JWT（PyJWT）+ Redis 会话校验（选中）** | 自包含便于横向扩展，Redis 校验兜住"踢出/作废"需求，标准成熟 | 与集群无状态架构契合，已被规划定为认证方案 |
| 服务端 session（内存/DB 存储） | 可即时撤销，但多实例需共享存储或粘性会话，扩展性差 | 不满足横向扩展目标，不采用 |
| Opaque token（Redis 存映射） | 可撤销性强，但每次鉴权都要查 Redis，令牌无自校验能力 | 作为补充手段（黑名单/会话标记）使用，不作为主令牌 |
| Fernet / 自研签名令牌 | 可控但生态与审计资料少，自研签名易出安全漏洞 | 不必要，标准 JWT + 成熟库更稳 |
| （密码哈希）bcrypt / argon2 | 同为优秀密码哈希算法，但需第三方库依赖 | PBKDF2 标准库零依赖已满足要求，不额外引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **access token 有效期不可过长**：规划定为 30 分钟；过长会放大泄露风险窗口，过短则频繁刷新体验差。
- **禁设算法为 none、禁弱密钥**：验签时必须显式指定允许的算法白名单（HS256），防止攻击者伪造未签名令牌；secret 强度要够、可轮换（新旧并行验证期）。
- **密码必须加盐 + 足够迭代次数**：盐用 `secrets.token_bytes` 生成，存入库与哈希同存；迭代次数随硬件上调，校验用 `hashlib.compare_digest` 常量时间比较防时序攻击。
- **敏感信息不进 claims**：JWT 载荷只做 Base64URL 编码、可被任何人解码，手机号/身份证等脱敏字段绝不能写进 token。
- **黑名单 TTL 与业务对齐**：`jti` 黑名单的 TTL 要覆盖 refresh token 剩余有效期，过期自动清理；会话标记 key 同理。
- **刷新令牌防重放**：滚动轮换时对已轮换的旧 token 做复用检测（记录使用过的 `jti`），发现复用立即失效全家会话。
- **日志脱敏**：token、密码、密钥等敏感字段记录日志时必须脱敏，不落原始值（12 节日志要求）。
- **时钟与 exp 校验**：校验 `exp` 时留少量时钟偏移容忍度，避免多实例时钟漂移导致误判；`jti` 必须唯一（黑名单机制依赖它）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| PyJWT 官方文档 | https://pyjwt.readthedocs.io/ | 签发/校验/算法选择用法 |
| PyJWT GitHub | https://github.com/jpadilla/pyjwt | 源码与 issue 讨论 |
| JWT 官方规范（RFC 7519） | https://datatracker.ietf.org/doc/html/rfc7519 | JWT 标准定义，权威但偏理论 |
| jwt.io 调试器 | https://jwt.io/ | 在线解码/校验令牌，联调排查利器 |
| Python 标准库 hashlib | https://docs.python.org/3/library/hashlib.html | `pbkdf2_hmac` 官方用法与参数说明 |
| OWASP Password Storage Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html | PBKDF2 迭代次数等密码存储安全基线 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 | 双 token、黑名单、会话校验、密码策略全套认证设计 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 | JWT + Redis 会话状态校验 + PBKDF2 选型理由 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 会话有效标记、token 黑名单的存储实现 |
| 《[authlib 技术介绍](authlib技术介绍.md)》 | SSO 认证回跳后签发 BMS 双 token 的协同 |
| 《[API 接口规范](../../../规范/API接口规范.md)》 | 401 处理、令牌刷新约定 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
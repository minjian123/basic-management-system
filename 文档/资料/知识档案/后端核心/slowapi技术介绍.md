# slowapi 技术介绍

> FastAPI 限流方案 · BMS 接口防爆破

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › slowapi 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**slowapi** 是为 FastAPI / Starlette 提供的限流（rate limiting）库，
从 **flask-limiter** 适配而来，底层真正的限流计数工作由
**limits** 库完成，slowapi 本身是对 limits 的一层 FastAPI 封装。
它的核心价值是：用**装饰器声明式**地给接口挂上「N 次 / 时间窗口」规则，
并支持 Redis 等共享后端做**集群统一计数**。
在 BMS 中它承担接口级限流，重点是**登录防爆破**。

- **定位**：BMS 接口级限流方案，登录防爆破优先。
- **版本**：0.1.x 系列（持续迭代，建议锁定依赖版本）。
- **许可**：MIT，OSI 认证开源（limits 同为 MIT）。
- **语言**：Python（本项目 3.14+），支持同步与异步接口。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Limiter | 限流器实例：持有 key_func、存储后端（storage_uri）、默认限流规则，挂载到 `app.state.limiter` |
| key_func | 提取限流维度的函数：默认取客户端 IP，也可自定义为用户 ID、client 标识等 |
| limit 装饰器 | 给单个接口挂限流规则，如 `@limiter.limit("5/minute")`，需放在路由装饰器下方 |
| 限流字符串 | 「次数/时间窗口」表达式（如 `100/hour`、`5/minute`），limits 负责解析与计数 |
| 存储后端 | 计数存放处：redis / memcached / memory；Redis 后端实现多实例共享同一计数 |
| in_memory_fallback | 主存储（Redis）故障时降级到进程内 memory 后端继续限流，保证防护不中断 |
| RateLimitExceeded | 超限抛出的异常，需注册 `_rate_limit_exceeded_handler` 统一转为 429 响应 |
| X-RateLimit 头 | 开启 `headers_enabled` 后在响应头返回剩余配额，便于客户端感知 |
| shared_limit | 让一组路由共享同一条限流配额（如多个登录相关接口共用一个池） |
| exempt | 将某路由排除在限流之外（`@limiter.exempt`） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为 FastAPI 限流方案，用装饰器声明限流规则，支持 IP / 用户 / client 三种维度（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节）。
- 计数走 [Redis](Redis技术介绍.md) 后端，多实例集群共享同一计数，避免「每实例各限各的」导致总配额被放大。
- Redis 故障时降级为 memory 后端，限流能力不中断（见《[项目规划说明](../../../规划/项目规划说明.md#perf)》14 节「限流与降级」）。
- 登录防爆破优先：如登录接口「5 次锁 15 分钟」，与 [Pillow](Pillow技术介绍.md) 图形验证码叠加（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节「认证与安全」）。
- 开放接口（`/api/open`）按 client 维度独立限流（见《[项目规划说明](../../../规划/项目规划说明.md#integ-open)》9.4 节）。
- AI 接口独立限流与预算控制（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 AI 安全）。
- 限流命中统一按《[API 接口规范](../../../规范/API接口规范.md)》的错误码约定返回（429 + 业务错误码）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **slowapi + limits（选中）** | 原生适配 FastAPI、装饰器声明式、Redis 共享计数、支持降级 | 与 FastAPI + Redis 技术栈契合，社区主流方案 |
| flask-limiter | 功能成熟，但面向 Flask/WSGI，不适配 FastAPI/ASGI | 框架不匹配，slowapi 即其 FastAPI 版 |
| 自研（Redis INCR + EXPIRE） | 灵活可控，但滑动窗口、多维度、降级都要自己写，维护成本高 | 重复造轮子，limits 已把这些做好 |
| 网关层限流（nginx limit_req） | 部署简单，但粒度粗、难区分用户/client、与业务规则脱节 | 可作为外层粗粒度补充，不能替代应用层限流 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **必须显式传 request**：被限流的接口函数签名里要有 `request: Request` 参数，否则 slowapi 拿不到请求上下文、限流失效。
- **装饰器顺序**：路由装饰器（`@app.post(...)`）要写在 `@limiter.limit(...)` 的**上方**，顺序反了会出错。
- **注册异常处理器**：必须 `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`，否则超限抛裸异常而非 429。
- **降级并非集群一致**：Redis 故障降级 memory 后，计数退化为「每进程独立」，多实例总配额会被放大，属可接受的降级取舍，需有日志告警。
- **限流维度**：默认按 IP，用户/client 维度需自定义 key_func；注意代理/网关后取真实 IP（X-Forwarded-For）。
- **时间窗口与配额**：限流字符串要按接口风险分级（登录最严、查询较松），避免一刀切误伤正常用户。
- **版本锁定**：slowapi 0.1.x 迭代较快，升级后需回归「超限返回 429、降级生效」等关键路径。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| slowapi 官方文档 | https://slowapi.readthedocs.io/ | 权威文档，含安装、示例、API 参考 |
| slowapi GitHub | https://github.com/laurentS/slowapi | 源码与 issue 讨论 |
| limits 官方文档 | https://limits.readthedocs.io/ | 底层限流库：限流字符串、存储后端详解 |
| limits GitHub | https://github.com/alisaifee/limits/ | limits 源码（slowapi 的实际限流引擎） |
| slowapi PyPI | https://pypi.org/project/slowapi/ | 版本历史与安装信息 |
| flask-limiter（参考实现） | https://github.com/alisaifee/flask-limiter | slowapi 的前身，功能设计可对照参考 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节 | 后端技术栈与选型说明（slowapi 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 | 认证与安全：登录限流、AI 接口独立限流 |
| 《[项目规划说明](../../../规划/项目规划说明.md#perf)》14 节 | 性能与高并发设计：分布式限流与降级 |
| 《[API 接口规范](../../../规范/API接口规范.md)》 | 统一响应、错误码、限流约定 |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 限流计数共享后端（bms:global:rate:*） |
| 《[Pillow 技术介绍](Pillow技术介绍.md)》 | 图形验证码，与限流叠加防爆破 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 被限流的 Web 框架（中间件/异常处理器机制） |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
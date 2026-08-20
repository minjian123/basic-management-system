# structlog 技术介绍

> Python 结构化日志库 · BMS 日志底座

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › structlog 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**structlog** 是 Python 生态里做**结构化日志**的事实标准库，
由 Hynek Schloegel 维护，自 2013 年起在生产环境大规模使用。
它把「一条日志」建模成一个**字典（event dict）**，
通过一串**处理器（processor）**逐步加工，最终渲染成 JSON、logfmt 或控制台彩色输出。

- **定位**：BMS 后端**唯一日志库**——结构化 JSON 日志，携带 `request_id`/`trace_id` 贯穿请求链路，配合 Loki 跨实例聚合检索。
- **版本**：26.1.0（CalVer 日历版本，主版本号=年份，持续迭代）。
- **许可**：Apache-2.0 或 MIT（双许可，任选其一）。
- **特性**：零配置即可用、可深度定制、原生支持 asyncio 与 contextvars、可无缝接管标准库 `logging`。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 结构化日志 | 日志不是自由文本，而是带字段的键值对（如 `{"event":"login","user_id":42}`），便于机器解析、检索、聚合 |
| event dict | structlog 里一条日志的本质——一个字典；上下文 + 本次事件参数合并后一起输出 |
| bound logger（绑定日志器） | 用 `logger.bind(user_id=42)` 预置上下文的日志器；之后每条日志自动带上这些字段，无需重复传 |
| context（上下文） | 提前绑定、跨多次日志复用的字段（租户、用户、request_id），是「贯穿请求链路」的关键 |
| processor（处理器） | 接收 event dict、返回新 event dict 的函数，串成一条「处理器链」逐步加工日志（加级别、加时间戳、脱敏、渲染） |
| merge_contextvars | 从 `contextvars` 读取上下文的处理器，配合 asyncio/多线程让 request_id 等自动进入每条日志，无需手动传 |
| TimeStamper | 给日志加时间戳的处理器，可指定格式与是否 UTC（BMS 统一 UTC 存储） |
| 渲染器（Renderer） | 把 event dict 变成最终字符串：JSONRenderer（生产 JSON）、ConsoleRenderer（开发彩色）、KeyValueRenderer（logfmt） |
| stdlib 集成 | structlog 可接管标准库 `logging`：第三方库走 logging 的输出也能被统一加工，不影响它们正常工作 |
| request_id / trace_id | 请求链路标识：request_id 为进程内请求序号（兜底），trace_id 为跨服务链路 ID（OpenTelemetry），二者关联后日志可与链路互查 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

structlog 是 BMS 后端的**日志底座**，目标是「日志可被机器检索、可跨实例聚合、可关联链路」。
所有业务日志统一走 structlog，禁止 `print`。

- **结构化 JSON 输出**：生产环境渲染为单行 JSON（每行一条），字段名 snake_case，`event` 为动作描述（`user_created`、`login_failed`），便于 Loki 逐行解析与检索（见《[日志规范](../../../规范/日志规范.html#format)》3 节）。
- **request_id 贯穿链路**：中间件在请求入口生成 `request_id` 并 bind 到日志上下文，整条请求链路的日志都带上它，配合 Loki 跨实例聚合检索（见《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节「structlog」）。
- **与标准 logging 集成**：structlog 接管标准库 `logging`，FastAPI/SQLAlchemy/Celery 等第三方库的日志也能被统一加工，不影响它们原有输出（见《[可观测性](../../../设计/架构设计/23_架构设计_子系统_可观测性.html#log)》2 节）。
- **关联 OpenTelemetry trace_id**：`trace_id` 与 structlog 的 `request_id` 关联，日志可与 Jaeger 链路互查，随 Grafana 统一可视化（见《[OpenTelemetry 技术介绍](OpenTelemetry技术介绍.md)》）。
- **脱敏**：密码、token、密钥、PII 经脱敏处理器过滤后才落日志，不落原始值（见《[日志规范](../../../规范/日志规范.html#mask)》5 节）。
- **异步任务贯通**：Celery 任务与 event-worker 消费者在入口沿用或生成 trace_id，保证异步链路日志可追踪。

> 日志示例（生产 JSON 单行）：
> `{"ts":"2026-08-19T09:00:00.123+00:00","level":"info","event":"user_created","trace_id":"a1b2c3d4","tenant":"demo","user_id":42,"duration_ms":35}`

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **structlog（选中）** | 结构化原生、处理器链灵活、asyncio/contextvars 一等公民、可接管 stdlib、性能高、生产验证久 | 与 BMS「JSON 日志 + 链路贯通 + 第三方兼容」需求完全契合，首选 |
| 标准库 logging + 自定义 Formatter | 零依赖、熟悉；但天然面向文本，结构化要自己拼、上下文传递弱、asyncio 支持差 | 能凑合但上下文与结构化能力不足，工程化成本高 |
| python-json-logger | 直接把 logging 输出成 JSON；但只是「格式化器」，无上下文绑定/处理器链，能力有限 | 适合轻量场景，BMS 需要上下文贯通，不够用 |
| loguru | API 极简、开箱即用；但偏「便捷日志器」，结构化/处理器链/stdlib 接管不如 structlog 精细 | 适合小项目，BMS 要精细控制日志管线，选 structlog |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **别用 print**：业务代码一律走 structlog，`print` 输出无法被 Loki 结构化解析，也丢失上下文（见《[日志规范](../../../规范/日志规范.html#level)》2 节）。
- **上下文靠 bind/contextvars，别手动传**：request_id、tenant、user_id 在入口 bind 一次，后续日志自动带上；每条日志手动传既啰嗦又易漏。
- **异步场景用 contextvars**：asyncio 下线程局部变量不可靠，必须用 `merge_contextvars` 处理器从 contextvars 读上下文，否则并发请求上下文会串。
- **多行堆栈要合并**：异常堆栈默认多行，需替换换行为 `\n` 转义成单行，否则 Loki 逐行解析会断（见《[日志规范](../../../规范/日志规范.html#format)》3 节）。
- **脱敏要进处理器链**：密码/token/PII 必须在渲染前的处理器里过滤，别指望「记得不打印」——要机制保证。
- **stdlib 接管方式**：用 `structlog.stdlib.recreate_defaults()` 让第三方库日志也走 structlog 管线；但注意别重复加处理器导致字段叠加。
- **时间戳统一 UTC**：TimeStamper 设 `utc=True`，与 BMS「时间 UTC 存储」口径一致，前端再按本地时区展示。
- **级别别滥用 DEBUG**：DEBUG 默认关闭（dev 可开），生产只留 INFO 以上的关键节点，避免日志量爆炸。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| structlog 官方文档 | https://www.structlog.org/ | 权威文档：Getting Started、处理器、stdlib 集成、Glossary |
| structlog GitHub | https://github.com/hynek/structlog | 源码、issue 与 release notes |
| structlog @ PyPI | https://pypi.org/project/structlog/ | 安装包与版本历史 |
| Standard Library 集成 | https://www.structlog.org/en/stable/standard-library.html | 如何接管 logging、让第三方库输出统一加工 |
| Processors 详解 | https://www.structlog.org/en/stable/processors.html | 处理器链、脱敏、渲染机制 |
| 《[日志规范](../../../规范/日志规范.html)》 | 项目内文档 | BMS 日志级别、JSON 格式、脱敏、链路约定 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》2.1 / 3.1 节 | 日志选型：structlog 结构化日志 |
| 《[日志规范](../../../规范/日志规范.html)》 | 日志级别、JSON 格式、上下文字段、脱敏、保留归档 |
| 《[可观测性（架构设计）](../../../设计/架构设计/23_架构设计_子系统_可观测性.html)》 | 日志 + 指标 + 链路 + 告警统一体系 |
| 《[OpenTelemetry 技术介绍](OpenTelemetry技术介绍.md)》 | trace_id 与 request_id 关联、链路追踪 |
| 《[Loki 技术介绍](../部署与运维/Loki技术介绍.md)》 | 日志聚合检索，消费 structlog 的 JSON 日志 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 中间件注入 request_id 到日志上下文 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
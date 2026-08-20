# OpenTelemetry 技术介绍

> 分布式链路追踪 · BMS 可观测性

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › OpenTelemetry 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**OpenTelemetry**（简称 OTel）是云原生计算基金会（CNCF）的**可观测性**事实标准，
统一了链路追踪（Traces）、指标（Metrics）、日志（Logs）三类遥测数据的采集与上报模型。
它由原先的 OpenTracing 与 OpenCensus 两个项目合并而来，目标是「一次埋点、多后端可用」，
避免被某一家 APM 厂商锁定。
BMS 用它做**分布式链路追踪**：应用把 trace 经 **otel-collector** 上报，
由 **Jaeger** 存储与展示，并随 Grafana 统一可视化。

- **定位**：BMS 链路追踪（可观测性三件套之一），MVP 即接入。
- **版本**：Python SDK 1.x（Traces API/SDK 已稳定），部分实验性组件为 0.x。
- **许可**：Apache-2.0（otel-collector、Jaeger 同为 Apache-2.0）。
- **语言**：Python（本项目 3.14+），经 OTLP 上报，后端语言无关。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Trace | 一次请求的完整链路，由多个 Span 按父子关系串成，跨进程/服务传播 |
| Span | 链路中的一个操作单元（一次接口调用、一次 DB 查询），含起止时间、属性、状态 |
| trace_id / span_id | trace_id 全链路唯一；span_id 标识单个 Span；两者组合成 SpanContext 在调用间传递 |
| TracerProvider | 创建 Tracer 的入口，承载 Resource（如 service.name）与 SpanProcessor |
| SpanProcessor | 决定 Span 何时、如何被处理导出；`BatchSpanProcessor` 批量导出以降低开销 |
| Exporter | 把 Span 发送到后端，OTLP exporter 按 OTel 数据模型无损导出 |
| OTLP | OpenTelemetry 协议，统一上报协议：gRPC 4317 / HTTP 4318，被 collector 与多数后端支持 |
| otel-collector | 遥测数据的「中转站」：统一接收、批处理、采样、再转发到后端，是生产环境最佳实践 |
| Jaeger | trace 的存储与展示后端，原生支持 OTLP 接收，UI 默认端口 16686 |
| 自动埋点 | `opentelemetry-instrument` 自动为 FastAPI、SQLAlchemy、Redis 等常见库注入 Span，无需手写 |
| 采样（Sampling） | 按头采样/尾采样决定哪些 trace 落盘，控制高并发下的存储与开销 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 链路追踪：应用经 **otel-collector** 上报 trace 至 **Jaeger** 存储展示（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节）。
- **trace_id 与 structlog 的 request_id 关联**：日志里带上 trace_id，实现「日志 ↔ 链路」互跳定位（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》structlog 条目）。
- 随 **Grafana** 统一可视化：Grafana 配置 Jaeger 数据源，与 Prometheus 指标、Loki 日志同屏排查（见《[项目规划说明](../../../规划/项目规划说明.md#deploy)》19 节监控）。
- **MVP 即接入**：链路追踪不放到后期，登录、审批等核心链路从早期就可观测。
- 部署端口：Jaeger UI 16686、otel-collector OTLP 4317/4318，仅内网（见《[开发部署规划](../../../规划/开发部署规划.md#ports)》9 节端口规划）。
- 验收口径：「链路追踪（Jaeger 链路可见）」纳入功能测试与 MVP 验收（见《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **OpenTelemetry + Jaeger（选中）** | CNCF 标准、厂商中立、自动埋点成熟、生态最大 | 行业标准组合，避免厂商锁定 |
| Zipkin | 轻量、Google 出品，但生态与自动埋点覆盖不如 OTel | 可用但非主流，埋点能力弱 |
| SkyWalking | APM 全家桶、功能强，但体系较重、与 OTel 标准并行 | 偏重，与本项目轻量可观测目标不符 |
| 云厂商 APM（如某云 Trace） | 开箱即用，但强绑定单一云、私有协议、成本随量增长 | 自托管场景不适用，存在锁定风险 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **service.name 必设**：Resource 里不设置 `service.name`，trace 在 Jaeger 里可能查不到或归不到服务。
- **OTLP 端点对齐**：应用 exporter 的 endpoint 要与 otel-collector 的接收端口一致（gRPC 4317 / HTTP 4318），协议（grpc/http）也要匹配。
- **批量导出**：务必用 `BatchSpanProcessor`，逐条同步导出会显著拖慢接口。
- **开销与采样**：高并发下全量 trace 存储压力大，需配置采样策略；生产经 collector 统一处理，不建议应用直连 Jaeger。
- **日志关联**：trace_id 要注入 structlog 上下文，否则日志与链路割裂，排查时无法互跳。
- **自动埋点版本匹配**：`opentelemetry-instrumentation-*` 各插件版本要与 SDK 版本对齐，错配会静默失效。
- **敏感信息**：Span 属性里不要写入密码、token 等敏感数据，避免随 trace 落盘泄露。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| OpenTelemetry 官网 | https://opentelemetry.io/ | 权威文档：概念、规范、各语言入口 |
| OpenTelemetry Python | https://opentelemetry.io/docs/languages/python/ | Python 入门、exporter、自动埋点配置 |
| opentelemetry-python GitHub | https://github.com/open-telemetry/opentelemetry-python | Python SDK 源码与 issue |
| otel-collector GitHub | https://github.com/open-telemetry/opentelemetry-collector | collector 源码与配置参考 |
| Jaeger 官网 | https://www.jaegertracing.io/ | trace 后端：部署、UI、OTLP 接收 |
| Jaeger GitHub | https://github.com/jaegertracing/jaeger | Jaeger 源码与发布 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节 | 后端技术栈：链路追踪（OpenTelemetry + Jaeger）条目 |
| 《[项目规划说明](../../../规划/项目规划说明.md#deploy)》19 节 | 部署与运维：监控体系（Prometheus + Loki + Grafana + Jaeger） |
| 《[开发部署规划](../../../规划/开发部署规划.md#ports)》9 节 | 端口规划：Jaeger UI 16686 / otel-collector 4317、4318 |
| 《[日志规范](../../../规范/日志规范.md)》 | structlog 结构化日志与 request_id / trace_id 关联 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 被埋点的 Web 框架（中间件/请求上下文） |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 被自动埋点的缓存/限流依赖（Span 可见） |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
# Prometheus 与 Alertmanager 技术介绍

> 指标采集与告警 · 可观测性三件套之 Metrics

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › Prometheus 与 Alertmanager 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Prometheus** 是时序监控系统：主动拉取（scrape）各服务的 `/metrics` 指标，
存入自带时序数据库（TSDB），用 PromQL 查询，并触发告警规则。
它起源于 SoundCloud，2016 年捐给 CNCF，已是云原生监控的事实标准。
**Alertmanager** 是配套告警组件，负责告警的路由、分组、静默与通知发送。

- **定位**：BMS 可观测性三件套（指标 / 日志 / 链路）中的指标与告警层（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：Prometheus 3.x 系列（持续迭代）；Alertmanager 随主仓库版本走。
- **许可**：Apache-2.0，免费开源（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：mjbk 以 Docker Compose 容器常驻，与 Loki / Grafana / Jaeger 一并纳入监控编排（《[项目规划说明](../../../规划/项目规划说明.md#deploy-compose)》19.3 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 指标类型 | counter（只增计数）/ gauge（可增可减）/ histogram（分桶分布）/ summary（分位数），覆盖绝大多数监控场景 |
| /metrics 端点 | 服务暴露的纯文本指标接口，Prometheus 周期性拉取（pull 模型） |
| TSDB | 自带时序数据库，按时间线（label 组合）存储，压缩率高、查询快 |
| PromQL | 查询语言：`rate()` 算增速、`histogram_quantile()` 算 P99，表达力强 |
| 标签（labels） | 指标的维度（app、env、tenant），是索引与查询的基础——也是基数爆炸的源头 |
| 告警规则（alert rules） | PromQL 表达式 + 持续时长，满足即产生告警，交给 Alertmanager |
| Alertmanager 路由 | 按标签把告警分发给不同 receiver（邮件组 / 群机器人） |
| 分组 / 静默 / 抑制 | 同类告警合并成一条、维护窗口静默、上游故障抑制下游告警，防告警风暴 |
| SMTP receiver | 原生邮件通知，配 SMTP 服务器地址与 STARTTLS 即可 |
| webhook receiver | 把告警 JSON POST 到任意 HTTP 端点——企业微信 / 钉钉群机器人走这条路 |
| retention | 指标保留时长（如 15d），到期自动清理，规划时按磁盘预算定 |
| exporter | 为没有 /metrics 的组件（Redis、MySQL、node 等）提供指标的桥接小服务 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **指标采集**：Prometheus 拉取后端 `/metrics` 及各组件 exporter（Redis、数据库、node 等）的指标（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **告警推送**：Alertmanager 统一出口——邮件走原生 SMTP receiver；企业微信 / 钉钉群机器人经 webhook receiver 转 BMS 内部接口转换格式后推送（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **看板展示**：指标经 Grafana 统一可视化，BMS 系统监控页跳转 / 嵌入（见《[Grafana 技术介绍](Grafana技术介绍.md)》）。
- **监控面**：覆盖健康检查、Socket.IO 连接数、缓存（Redis key 分布 / 内存）、DB/Redis/MinIO 依赖状态（《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节系统监控模块）。
- **链路协同**：trace_id 与 structlog 的 request_id 关联，指标、日志、链路在 Grafana 内互跳（《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 OpenTelemetry 条目）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Prometheus + Alertmanager（选中）** | 优点：CNCF 事实标准、exporter 生态最全、PromQL 表达力强、与 Grafana 无缝；缺点：单机 TSDB，超大规模需联邦 / remote write | BMS 规模下单机足够，生态与团队资料成本最低 |
| Zabbix | 优点：传统监控老牌、agent 体系成熟；缺点：云原生指标生态弱，PromQL 式查询体验差 | 传统主机监控可用，指标场景不如 Prometheus |
| InfluxDB | 优点：通用时序库、语言绑定多；缺点：告警生态弱，需另配告警组件 | 存储可用，但告警与查询生态不如 Prometheus 一体 |
| Datadog | 优点：SaaS 开箱即用、功能全；缺点：按量收费、数据出域，信创场景不可接受 | 数据不出域是硬约束，不采用 |
| VictoriaMetrics | 优点：兼容 PromQL、压缩率高、省资源；缺点：生态与资料略少 | 资源紧张时的优质备选，MVP 阶段不引入 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **基数爆炸**：标签组合数 = 时间线数，把 user_id、request_id 这类高基数字段写进指标会撑爆 TSDB——它们属于日志（Loki），不属于指标。
- **retention 规划**：保留时长 × 时间线数决定磁盘占用，按 mjbk 磁盘预算设定，别默认无限留。
- **rate() 与 increase()**：counter 增速用 `rate()`（每秒），区间增量用 `increase()`，混用会导致告警误报。
- **webhook 接收端**：Alertmanager 发的是 POST JSON，BMS 内部转换接口要能接住并转成企业微信 / 钉钉的报文格式，超时与重试要处理。
- **SMTP 配置**：明确 STARTTLS / 端口 / 发件人，先用测试告警（`amtool`）验证再上生产规则。
- **Windows 与 Linux 差异**：Prometheus 官方支持 Linux（生产容器），Windows 本地体验请用 Docker 跑，别装 Windows 移植版。
- **告警去重**：规则侧写清 `for` 时长防抖动，Alertmanager 侧用分组 + 抑制防风暴，两层都要做。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Prometheus 官网 | https://prometheus.io/ | 项目入口、下载、生态组件一览 |
| Prometheus 官方文档 | https://prometheus.io/docs/introduction/overview/ | 从概念到 PromQL 的完整文档 |
| Prometheus 源码 | https://github.com/prometheus/prometheus | 源码与 issue 讨论 |
| Alertmanager 源码 | https://github.com/prometheus/alertmanager | 路由 / 分组 / 接收器配置参考 |
| PromCon 会议 | https://promcon.io/ | 官方年度大会，历年演讲是进阶最佳材料 |
| 《Prometheus: Up & Running》 | https://www.oreilly.com/library/view/prometheus-up/9781492034131/ | O'Reilly 经典书籍（第 2 版），系统学习首选 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（监控条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：指标采集 + 三类告警通道 |
| 《[项目规划说明](../../../规划/项目规划说明.md#deploy-topo)》19.1 节 | 部署拓扑：监控组件清单 |
| 《[Grafana 技术介绍](Grafana技术介绍.md)》 | 指标的统一可视化出口 |
| 《[Loki 技术介绍](Loki技术介绍.md)》 | 日志聚合：与 Prometheus 分工互补 |
| 《[structlog 技术介绍](../后端核心/structlog技术介绍.md)》 | 日志侧：request_id 贯穿，进 Loki 不进指标 |
| 《[OpenTelemetry 技术介绍](../后端核心/OpenTelemetry技术介绍.md)》 | 链路侧：trace 与指标 / 日志互跳 |
| 《[Redis 技术介绍](../后端核心/Redis技术介绍.md)》 | 被 exporter 采集的缓存组件 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
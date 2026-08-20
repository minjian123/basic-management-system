# Loki 技术介绍

> 日志聚合 · 只索引元数据，类 Prometheus 思路

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › Loki 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Loki** 是 Grafana Labs 出品的日志聚合系统，设计哲学一句话：
**「像 Prometheus 一样做日志」**——只给日志的**元数据**（labels）建索引，
日志原文压缩存储、不建全文索引。因此它比 Elasticsearch 轻得多，
代价是「先按标签缩小范围，再行内过滤」的查询方式。

- **定位**：BMS 可观测性三件套中的日志层，聚合 structlog 日志跨实例检索（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：3.x 系列（持续迭代）。
- **许可**：AGPL-3.0。BMS 仅作独立日志服务部署、不修改源码，无传染影响（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：mjbk 以 Docker Compose 容器常驻，与 Prometheus / Grafana 一并编排（《[项目规划说明](../../../规划/项目规划说明.md#deploy-compose)》19.3 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| labels | 唯一的索引维度（如 app、env、tenant），查询先按 labels 定位日志流 |
| 日志流（stream） | 同一组 labels 的日志序列，是 Loki 存储与检索的基本单位 |
| 日志行（line） | 原文压缩存储、不建全文索引——省钱省资源的核心设计 |
| LogQL | 日志查询语言：labels 选流（`{app="bms"}`）+ 行过滤（`|= "error"`）两段式 |
| push 模型 | 客户端主动推送到 `/loki/api/v1/push`，与 Prometheus 的 pull 相反 |
| Alloy（采集器） | Grafana 官方采集器（promtail 的继任者），从文件 / 容器 / 系统读日志推给 Loki |
| 对象存储后端 | 日志落本地盘或 S3 兼容存储（MinIO），Loki 本身无状态化 |
| compactor | 把旧日志块压缩归档，降低长期存储成本 |
| structured metadata | 行级结构化字段（如 request_id），比 labels 便宜、比全文索引快 |
| retention | 按日志流设保留策略，到期自动删除 |
| Grafana 数据源 | Loki 作为 Grafana 数据源接入，LogQL 直接在看板里查 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **跨实例日志聚合**：后端多副本 + celery-worker + event-worker 的 structlog JSON 日志统一进 Loki，一处检索全部实例（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **请求链路串联**：structlog 日志携带 request_id，Loki 内按 request_id 过滤即可还原一次请求在各实例的完整轨迹（《[项目规划说明](../../../规划/项目规划说明.md#sel-backend)》3.1 节 structlog 条目）。
- **统一展示**：与 Prometheus 指标、Jaeger 链路一起挂在 Grafana 数据源上，指标 → 日志 → 链路互跳（见《[Grafana 技术介绍](Grafana技术介绍.md)》）。
- **审计辅助**：操作日志、登录日志等审计类检索走 Loki，与数据库审计表互为补充（《[项目规划说明](../../../规划/项目规划说明.md#audit)》13 节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Loki（选中）** | 优点：只索引元数据、资源占用低、与 Grafana 同厂无缝、部署简单；缺点：无全文索引，行过滤是扫描式 | BMS 日志量级下最省资源，查询模式与 structlog 契合 |
| Elasticsearch（ELK） | 优点：全文索引强、生态成熟；缺点：JVM 内存开销大、集群运维重，小团队养不起 | 功能过剩，mjbk 单机规模不划算 |
| ClickHouse + vector | 优点：列存查询强、可玩性高；缺点：自建栈、运维与排障成本高 | 适合有专职运维的团队，BMS 不选 |
| Splunk | 优点：企业级功能全；缺点：商业收费按量计费、数据出域 | 成本与信创约束下不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **labels 别放高基数字段**：request_id、user_id 放 labels 会炸日志流数量；用 structured metadata 或行过滤承载。
- **查询先选流再过滤**：`{app="bms"} |= "error"` 比裸 `|= "error"` 快几个量级，养成先写 labels 的习惯。
- **采集器选型**：promtail 已进入维护模式，新部署直接用 Grafana Alloy（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节监控栈配套）。
- **retention 与后端存储**：保留策略 + 对象存储后端（MinIO / 本地盘）一起规划，别默认全量长留。
- **时间同步**：Loki 按日志时间戳归档，各容器时钟不同步会导致查询「丢日志」，统一 NTP。
- **push 带宽**：日志量突增时关注网络与磁盘 IO，必要时在采集侧先过滤 DEBUG 级。
- **Windows 与 Linux 差异**：生产为 Linux 容器；Windows 本地体验请用 Docker 跑 Loki + Alloy，别装 Windows 版采集器。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Loki 产品页 | https://grafana.com/oss/loki/ | 定位、架构与许可说明 |
| Loki 官方文档 | https://grafana.com/docs/loki/latest/ | 安装、配置、LogQL 完整参考 |
| Loki 入门概览 | https://grafana.com/docs/loki/latest/get-started/overview/ | labels / 日志流 / 存储模型入门 |
| Grafana Alloy 文档 | https://grafana.com/docs/alloy/latest/ | 官方采集器（promtail 继任者）配置参考 |
| Loki 源码 | https://github.com/grafana/loki | 源码与 issue 讨论 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（日志条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：Loki 聚合 structlog 日志跨实例检索 |
| 《[structlog 技术介绍](../后端核心/structlog技术介绍.md)》 | 日志生产者：JSON 结构化日志 + request_id |
| 《[Grafana 技术介绍](Grafana技术介绍.md)》 | Loki 作为数据源的展示出口 |
| 《[Prometheus 与 Alertmanager 技术介绍](Prometheus与Alertmanager技术介绍.md)》 | 指标侧分工：高基数字段归日志、趋势值归指标 |
| 《[OpenTelemetry 技术介绍](../后端核心/OpenTelemetry技术介绍.md)》 | trace_id 与 request_id 关联，日志 / 链路互跳 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
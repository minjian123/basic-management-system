# Grafana 技术介绍

> 监控可视化 · 指标 / 日志 / 链路统一看板

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › Grafana 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Grafana** 是开源可观测性可视化平台：把 Prometheus（指标）、
Loki（日志）、Jaeger（链路）、MySQL 等**多种数据源**接进来，
用拖拽式看板统一展示。它自己**不存数据、不做告警主脑**，
专注「把数据画好看、查得快」。

- **定位**：BMS 可观测性三件套的统一展示层（《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节）。
- **版本**：1x.x 系列（每年 2-3 个大版本，持续迭代）。
- **许可**：AGPL-3.0。BMS 仅作独立展示服务部署、不修改源码，无传染影响；Grafana Enterprise 为商业版，本项目不用（《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节）。
- **落地形态**：mjbk 以 Docker Compose 容器常驻，浏览器访问；BMS 系统监控页跳转 / 嵌入（《[项目规划说明](../../../规划/项目规划说明.md#deploy-compose)》19.3 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| 数据源（Data Source） | 查询入口：Prometheus、Loki、Jaeger、MySQL 各注册一个，一个看板可混查多源 |
| Dashboard | 看板：一组 panel 的布局容器，可 JSON 导出、版本化、一键复制 |
| Panel | 面板：一个查询 + 一种可视化（折线 / 表格 / 热力图 / 状态点） |
| 查询语言 | 按数据源切换：PromQL（指标）、LogQL（日志）、TraceQL（链路），Grafana 统一入口 |
| 变量（Variables） | 看板级下拉参数（租户、环境、实例），一个模板看板适配多对象 |
| Alerting | 内置告警引擎；BMS 的告警主脑在 Alertmanager，Grafana 侧只做展示与跳转，避免双头告警 |
| Provisioning | 数据源 / 看板 / 用户用 YAML 声明式管理，可随 Compose 一键初始化 |
| 嵌入（Embed） | iframe 嵌入其他系统页面，需同源且目标站点放行 X-Frame-Options |
| 组织与用户 | 多组织、角色（Admin / Editor / Viewer），按职责分配看板权限 |
| 插件 | 可视化与数据源均可插件扩展，官方市场丰富 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **统一展示**：Prometheus 指标、Loki 日志、Jaeger 链路三类数据源挂在一个 Grafana 上，指标异常 → 跳日志 → 跳链路，一处排障（《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节）。
- **BMS 内跳转 / 嵌入**：系统监控页提供 Grafana 入口（页面跳转或同源嵌入），依赖状态（DB / Redis / MinIO）与缓存管理同页呈现（《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节系统监控模块）。
- **嵌入前提**：nginx 配 X-Frame-Options SAMEORIGIN，兼容同源 Grafana 嵌入（《[项目规划说明](../../../规划/项目规划说明.md#deploy-cluster)》19.2 节）。
- **监控面示例**：健康检查、Socket.IO 连接数、Redis key 分布 / 内存占用、DB 依赖状态等看板（《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节）。
- **告警分工**：告警规则与推送由 Alertmanager 承担（邮件 / 企业微信 / 钉钉），Grafana 不重复建告警，避免双头告警（见《[Prometheus 与 Alertmanager 技术介绍](Prometheus与Alertmanager技术介绍.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Grafana（选中）** | 优点：事实标准、多数据源混查、看板拖拽快、插件生态大；缺点：本身不存数据，必须配后端 | 与 Prometheus / Loki / Jaeger 组合是云原生标配 |
| Kibana | 优点：ELK 全家桶配套、日志检索强；缺点：绑定 Elasticsearch，指标 / 链路弱 | 选了 ELK 才顺理成章，BMS 未选 ES 做日志 |
| SigNoz | 优点：指标 + 日志 + 链路一体化，开箱省心；缺点：较新，社区与资料少于 Grafana | 备选，MVP 阶段不引入 |
| Datadog | 优点：SaaS 全托管、功能全；缺点：按量收费、数据出域 | 成本与信创约束下不采用 |
| Zabbix 前端 | 优点：传统监控自带界面；缺点：多源混查与看板灵活性弱 | 指标场景已被 Prometheus + Grafana 覆盖 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **AGPL 边界**：独立部署、不改源码、不深度定制，遵守《[项目规划说明](../../../规划/项目规划说明.md#stack-license)》2.5 节约束；若未来计划深度定制，提前评估许可。
- **嵌入三要素**：同源部署 + X-Frame-Options 放行 + 匿名 / 只读账号，缺一 iframe 就白屏。
- **别双头告警**：告警主脑在 Alertmanager，Grafana Alerting 默认不开，防止同一故障两条告警。
- **看板版本化**：看板 JSON 导出进仓库（或 provisioning），避免「只有我知道这个看板怎么搭」。
- **查询性能**：大时间范围 + 高基数查询会拖慢面板，用变量收窄范围、拆小面板。
- **Windows 与 Linux 差异**：本地体验可用官方 Windows 版或 Docker 容器，生产按 Linux 容器口径。
- **账号最小权限**：BMS 嵌入用只读账号，Admin 账号只给运维，别用 root 账号裸奔。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Grafana 官网 | https://grafana.com/ | 产品入口、下载、许可说明 |
| Grafana 官方文档 | https://grafana.com/docs/ | 安装、数据源、看板、嵌入完整参考 |
| Grafana 官网（中文） | https://grafana.com/zh-cn/ | 官方中文入口 |
| Grafana 源码 | https://github.com/grafana/grafana | 源码与 issue 讨论 |
| Grafana 官方博客 | https://grafana.com/blog/ | 新版本特性与最佳实践 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-ops)》2.4 节 | 部署与运维技术栈（可视化条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | 选型说明：统一展示 + BMS 内跳转 / 嵌入 |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 系统监控模块：Grafana 跳转 + 依赖状态 + 缓存管理 |
| 《[Prometheus 与 Alertmanager 技术介绍](Prometheus与Alertmanager技术介绍.md)》 | 指标数据源与告警主脑 |
| 《[Loki 技术介绍](Loki技术介绍.md)》 | 日志数据源 |
| 《[OpenTelemetry 技术介绍](../后端核心/OpenTelemetry技术介绍.md)》 | 链路数据源（Jaeger） |
| 《[nginx 技术介绍](nginx技术介绍.md)》 | 同源嵌入依赖的 X-Frame-Options 配置 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
# APISIX 技术介绍

> Apache APISIX 边缘网关 · 本项目统一入口（路由 / 认证 / 限流 / 观测 / 灰度）

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › APISIX 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Apache APISIX** 是 Apache 软件基金会的**云原生 API 网关**，基于 **Nginx + OpenResty（Lua）** 构建，
以**动态、高性能、可扩展**为核心：路由 / 上游 / 插件规则可在运行期热更新（无需 reload Nginx），
数百个官方插件覆盖认证、限流、流量治理与可观测，一次给全。

APISIX 有两种配置形态：**etcd 控制面**（Admin API 动态写入、默认）与 **standalone 文件驱动**
（`config_provider: yaml`，读 `conf/apisix.yaml`、轮询热加载）。本项目采用 **standalone 文件驱动**：
规则声明式入 Git、随流水线发布，**不引入 etcd / Admin API / Dashboard**，配置模型可平移 K8s
Ingress / Gateway API。

- **定位**：本项目边缘统一入口（南北向）；承载路由、认证校验、限流、灰度与边缘观测。
- **版本**：本项目锁定 `apache/apisix:3.18.0-debian`（官方 Docker 标签带 `-debian`；勿用 `latest`）。
- **许可**：Apache-2.0，OSI 认证开源。
- **运行时**：Nginx / OpenResty + Lua；容器运行，standalone 由 `APISIX_STAND_ALONE=true` 跳过 etcd 初始化。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Route（路由） | 按路径 / 主机 / 方法把请求绑定到上游；含 `uris`、`upstream_id` / `service_id`、`plugins`、`priority`、`filter` |
| Upstream（上游） | 后端服务集群：节点（`host:port` 与权重）、负载均衡类型（`roundrobin` 等）、健康检查 |
| Service（服务） | 可复用的上游 + 插件组合，多个 Route 引用同一 Service 共享配置 |
| Plugin（插件） | 挂在 Route / Service / Consumer / Global Rule 上的能力；按**阶段**（rewrite / access / header_filter / body_filter / log）执行，按 **priority** 排序 |
| Consumer（消费者） | 调用方身份实体，绑定认证凭据（key-auth / jwt-auth 等），限流可按 `consumer_name` 维度 |
| Global Rule（全局规则） | 对所有请求生效的插件集合（不绑定具体路由），如统一剥头、real-ip |
| Plugin Metadata（插件元数据） | 插件的全局配置段（`plugin_metadata`），与具体实例解耦；**各插件支持范围不同**（见第 5 节） |
| Router（路由器） | `radixtree_uri` 等；按 `priority` 优先、同优先级按路径精度匹配（精确静态路径优先于通配） |
| standalone 文件驱动 | `deployment.role: data_plane` + `role_data_plane.config_provider: yaml`；读 `apisix.yaml`，**每 1 秒轮询文件热更新**；文件以 `#END` 结束 |
| 环境变量替换 | 配置中写 `${{VAR:=默认值}}`，启动时按环境变量替换（`config.yaml` 与 `apisix.yaml` 均支持） |
| 控制面 / 数据面 | `deployment.role` 取 `traditional` / `control_plane` / `data_plane`；standalone 即单数据面、无控制面 |

## 3. 在本项目中的用途 <a id="usage"></a>

- **边缘统一入口，路由以服务目录为依据**：外部路径 `/api/{service_key}/v1/...` 经 `proxy-rewrite`
  剥离为服务内 `/api/v1/...`；上游按 Compose DNS 服务名 `{service_key}:8000` 寻址（**禁硬编码 IP**），
  迁 K8s 平移 Service 名（见平台《架构设计 · API 网关与边缘》）。
- **声明式配置入 Git**：`deploy/gateway/apisix.yaml` 由服务目录 `SERVICE_CATALOG` **生成**、
  流水线**零漂移校验**（`backend/ops/gateway_config.py render|check`），运行时文件替换即 1s 内热加载。
- **边缘认证与请求净化**：`global_rules` 统一剥除客户端伪造身份头，路由级 `proxy-rewrite.headers.set`
  注入网关验证过的身份；真实用户 / 服务 JWT 校验随认证任务接线（见 04_02 / 07_03）。
- **边缘限流（共享 Redis 多副本一致）**：`limit-count` + `policy: redis`，按真实客户端 IP，
  认证敏感路径（登录）走独立路由、更严档位、Redis 故障放行（见 04_03）。
- **边缘观测出口**：路由挂 `prometheus` 采集指标（`plugin_attr.prometheus` 暴露端点），
  `nginx_config.http` 配访问日志；真实采集 / 展示 / 告警归可观测性栈（见 08_需求）。
- **灰度预留**：`traffic-split` 按版本 / 权重灰度（规则声明式入 Git，迁 K8s 平移 HTTPRoute 权重）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Apache APISIX（选中）** | OIDC/JWT、Redis 分布式限流、RocketMQ/ES 日志出口一次给全；standalone → K8s 同配置模型；插件生态丰富 | 与「Compose 现网 → k3s」演进路线契合，不换选型 |
| Kong | 生态成熟、企业版功能强；核心依赖 PostgreSQL + 控制面较重 | 组件更重，单机起步成本高 |
| Traefik | 配置简洁、K8s 原生集成好；高级流量治理与插件能力相对弱 | 复杂边缘功能需自建 |
| Nginx（原生） | 稳定、性能好、团队熟悉；动态配置与插件化能力弱，改配置需 reload | 适合静态托管与粗粒度限流，不作动态边缘网关 |
| Envoy / Gateway API | 云原生标准、数据面强大；配置复杂、上手成本高 | K8s 阶段可作为平移目标之一，当前单机偏重 |

> 详细候选对比与推荐见《[微服务 · 12 选型对比（BMS）](../微服务/12_微服务_选型对比.md)》。

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

以下为本项目在 `3.18.0-debian` standalone 形态下的**实测结论**（2026-09-23，mjbk）：

- **standalone 必须 `#END`**：`apisix.yaml` 末尾缺 `#END` 会整份不加载（全 404）；由生成器保证 + 零漂移校验兜底。
- **热加载要目录挂载 + 软链**：Docker **单文件 bind mount** 在宿主文件被替换（`git pull` / 重建，新 inode）后，
  容器内仍指向旧 inode，APISIX 的文件轮询读不到新内容、**无法热加载**；改为**挂载配置目录并软链进 `conf/`**，
  宿主替换即时可见（目录挂载 + `ln -sfn` 进 `/usr/local/apisix/conf/`）。
- **环境变量替换语法为 `${{VAR:=默认}}`**：`config.yaml` 与 `apisix.yaml` **均支持**（旧 `$ENV://` 已不是现行语法）；
  变量需 `export` / 容器 `environment` 注入；**容器初始化后新增环境变量需重建 / reload 才生效**。
- **整数类型字段不能用环境变量占位（关键坑）**：`limit-count` 的 `redis_port` / `redis_database` 等
  schema 要求**整数**，经 `${{…}}` 替换后为字符串，会触发
  `failed to check the configuration of plugin limit-count err: then clause did not match` 致**整份配置加载失败**；
  整数用字面量、仅字符串字段（如 `redis_host` / `redis_password`）用替换。`config.yaml` 的 `node_listen` 等标量可替换。
- **`limit-count` 的 Redis 配置不能经 `plugin_metadata` 共享**：其 metadata_schema **仅含响应头名**
  （`limit_header` / `remaining_header` / `reset_header`），Redis 连接（`policy` / `redis_host` / `redis_port` /
  `redis_password` / `redis_database` / `redis_timeout` / `allow_degradation` / `sync_interval`）必须写进**每个插件实例**；
  用生成器逐路由统一注入避免遗漏。Redis 故障 `allow_degradation: true` 时跳过插件（放行），可用性优先。
- **限流维度**：`key_type` 取 `var` / `var_combination` / `constant`；默认 `remote_addr`，多维度用
  `var_combination`（如 `$remote_addr $http_x_tenant_id`）；`group` 可让多条路由共享同一配额。
- **真实客户端 IP 用 `real-ip`**：APISIX 位于反代 / nginx 之后时，`remote_addr` 是代理 IP；
  `real-ip` 插件按 `source`（如 `http_x_real_ip` / `http_x_forwarded_for`）+ `trusted_addresses`（可信网段）
  还原真实客户端 IP；`trusted_addresses` 未收紧时存在伪造头绕过面（生产应关闭网关直连暴露）。
- **`global_rules` 与路由级同插件的 `headers` 不叠加**：同一 `proxy-rewrite` 在 global 与 route 两处，
  路由级执行后 global 的 `headers.set` 会被丢弃；**剥头放 global、标记 / 身份注入放路由级**（实测结论）。
- **standalone 明文密码可用**：`limit-count` 的 `redis_password` 加密字段仅在 `etcd` 模式生效，
  file-driven 模式按明文原样使用（凭据仍应经环境变量 / Secret 注入，不入库）。
- **指标需按路由挂载**：`prometheus` 插件默认在启用列表，但**按路由采集需路由显式挂 `prometheus: {}`**；
  导出端点与地址在 `config.yaml` 的 `plugin_attr.prometheus`（`export_addr.ip: 0.0.0.0` 才能外部访问）。
- **版本锁定**：官方 Docker 标签形如 `apache/apisix:3.18.0-debian`；勿用 `latest`（行为随版本变化）。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| APISIX 官方文档 | https://apisix.apache.org/docs/apisix/ | 权威文档：入门、概念、插件、部署模式 |
| APISIX 部署模式 | https://apisix.apache.org/docs/apisix/deployment-modes/ | standalone 文件驱动与控制面 / 数据面 |
| APISIX 插件市场 | https://apisix.apache.org/plugins/ | 全量插件清单与检索 |
| `limit-count` 插件 | https://apisix.apache.org/docs/apisix/plugins/limit-count/ | Redis / 共享计数 / 多维度限流 |
| `real-ip` 插件 | https://apisix.apache.org/docs/apisix/plugins/real-ip/ | 反代后真实客户端 IP 还原 |
| `prometheus` 插件 | https://apisix.apache.org/docs/apisix/plugins/prometheus/ | 指标导出与 `plugin_attr` 配置 |
| `traffic-split` 插件 | https://apisix.apache.org/docs/apisix/plugins/traffic-split/ | 按权重 / 条件灰度 |
| 基于环境配置（`${{VAR}}`） | https://apisix.apache.org/docs/apisix/profile/ | 环境变量替换语法与用法 |
| APISIX GitHub | https://github.com/apache/apisix | 源码与 issue |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 平台《架构设计 · API 网关与边缘》 | 边缘定位、边缘功能、部署形态与安全边界 |
| 平台《架构设计 · 部署与运维》 | 基础设施编排、集群设计要点、故障降级 |
| [部署发布规范](../../../规范/部署发布规范.md) | 「API 网关配置与热加载」节：声明式入 Git、服务目录单一来源、限流与观测口径 |
| [APISIX 部署使用说明](../../开发服务器/linux/APISIX部署使用说明.md) | mjbk 部署实录、配置来源、验证与排障 |
| 04_01 / 04_02 / 04_03 详细设计 | 网关接入与声明式配置 / 边缘认证与请求净化 / 限流与服务发现（实现侧口径） |
| 《[Redis 技术介绍](Redis技术介绍.md)》 | 限流共享计数与分布式锁的 Redis 底座 |
| 《[slowapi 技术介绍](slowapi技术介绍.md)》 | 后端接口级限流（与边缘限流分层互补） |
| 《[微服务 · 12 选型对比（BMS）](../微服务/12_微服务_选型对比.md)》 | 网关 / 编排 / 发现配置等候选对比与推荐 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写

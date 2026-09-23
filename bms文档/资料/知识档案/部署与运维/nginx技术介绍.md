# nginx 技术介绍

> Web 服务器 · 静态托管 / 反向代理 / TLS 终止

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › nginx 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**nginx**（发音 "engine-x"）是高性能 HTTP 服务器与反向代理，
2004 年由 Igor Sysoev 发布，以**事件驱动**架构（epoll）著称，
用很少的内存扛住高并发，是互联网上占比最高的 Web 服务器之一。
在本项目里它承担**边缘入口层**：托管前端静态资源，并把 `/api` 流量反代至边缘网关
Apache APISIX（网关只处理 API），生产阶段承担 TLS 终止与入口安全响应头。

- **定位**：本项目边缘入口层——静态资源就地吐出、`/api` 反代至网关 APISIX；浏览器流量先到 nginx 再分流（平台《架构设计 · 总体架构》「技术栈全景 · 部署与运维」节）。
- **版本**：1.2x 系列（stable 与 mainline 双轨发布，生产用 stable；本项目容器用 `nginx:1.27`）。
- **许可**：BSD-2-Clause，免费开源无商用限制（平台《项目规划说明》「开源与许可协议」节）。
- **落地形态**：容器 `bms-gateway-nginx` 运行（配置 `deploy/gateway/nginx.conf`，随 `deploy/compose/gateway.yml` 编排），托管 PC + 移动端静态资源并把 `/api` 反代至网关容器 `apisix:9080`。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| master-worker | master 进程管配置与信号，worker 进程处理请求，改配置可平滑 reload 不中断服务 |
| 事件驱动 | 基于 epoll 的单线程多路复用，一个 worker 可服务大量并发连接，内存占用低 |
| server / location | 虚拟主机与路径匹配的两级配置：按域名选 server，按路径选 location |
| 静态 / API 分流 | `location /api/` 反代至网关、`location /` 托管静态资源——**网关只处理 API**，静态与 API 流量分流 |
| SPA 回退 | 前端单页应用用 `try_files $uri $uri/ /index.html`，未命中的前端路由回退到入口页 |
| upstream | 后端服务器组定义，负载均衡的对象集合 |
| proxy_pass | 反向代理核心指令：把请求转发给 upstream / 网关，可改写路径与头 |
| 真实客户端 IP 透传 | 反代时置 `X-Real-IP` / `X-Forwarded-For`，供网关 `real-ip` 与限流按真实客户端 IP 计数 |
| TLS 终止 | 在 nginx 层解密 HTTPS，内部再走明文，后端不必各自配证书 |
| WebSocket 代理 | 转发 `Upgrade`/`Connection` 头，让 /socket.io 长连接穿透代理（本项目已透传至网关） |
| 负载均衡策略 | 轮询 / ip_hash / Cookie 亲和（sticky），Socket.IO 场景必须固定到同一后端实例（本项目后端负载均衡由网关 APISIX 承担） |
| 泛域名证书 | 一张 `*.example.com` 证书覆盖所有子域名，支撑子域名租户路由 |
| 子域名租户路由 | 不同租户走不同子域名，nginx 按 Host 头分发到对应后端，实现租户隔离入口 |
| 静态资源优化 | gzip 压缩、缓存头、长连接，前端构建产物由 nginx 直接吐出 |
| 安全响应头 | CSP / HSTS / X-Frame-Options / Referrer-Policy 等统一在入口层配置（见 `deploy/gateway/nginx.conf`） |

## 3. 在本项目中的用途 <a id="usage"></a>

- **静态托管**：托管前端构建产物（PC 管理端 + 移动端），浏览器直接拿静态资源，不打扰后端（平台《项目规划说明》「部署与运维」节）。
- **API 分流（静态 / API 分离）**：`location /api/` 反代至**边缘网关 Apache APISIX**（`proxy_pass http://apisix:9080`，Compose DNS 服务名、禁硬编码 IP），`location /` 托管静态资源——网关只处理 API；网关再按服务目录路由到各后端服务（平台《项目规划说明》「环境与配置」节，详见《[APISIX 技术介绍](../后端核心/APISIX技术介绍.md)》）。
- **真实客户端 IP 透传**：反代时置 `X-Real-IP` / `X-Forwarded-For`，网关 `real-ip` 据此还原真实客户端 IP，使边缘限流按真实 IP 计数（见部署发布规范「API 网关配置与热加载」节）。
- **TLS 终止 + 入口**：生产在 nginx 层解密 HTTPS，内部走明文；后端负载均衡由网关 APISIX 承担（`roundrobin` / 按服务），nginx 负责入口与静态分发（平台《项目规划说明》「部署拓扑」节）。
- **子域名租户路由**：多租户按子域名区分入口，配泛域名证书（平台《架构设计 · 总体架构》「技术栈全景 · 部署与运维」节）。
- **WebSocket 透传**：`/socket.io` 路径放行 `Upgrade`/`Connection` 头并透传至网关（后端连接的固定/亲和由网关与后端承担）（平台《项目规划说明》「集群设计要点」节）。
- **安全响应头**：`deploy/gateway/nginx.conf` 统一配置 `X-Content-Type-Options`、`X-Frame-Options`（SAMEORIGIN，兼容同源 Grafana 嵌入）、`Referrer-Policy`、`Permissions-Policy`；CSP / HSTS（dev 关闭）随 TLS 启用（平台《项目规划说明》「集群设计要点」节）。
- **文档收敛**：生产环境关闭 Swagger/ReDoc 在线文档，对外只发 CI 导出的 swagger.json 快照（平台《项目规划说明》「API 设计规范」节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **nginx（选中）** | 优点：事实标准、性能高、静态托管与反代都强、资料最多；缺点：配置是 C 风格语法，初学略陡 | 静态 + 反代 + TLS 三合一，团队与社区最熟 |
| Apache HTTP Server | 优点：.htaccess 灵活、mod 生态老；缺点：进程模型偏重，高并发反代不是强项 | 静态托管可，反代与负载均衡场景不如 nginx |
| Caddy | 优点：自动 HTTPS、配置极简；缺点：生态与团队熟悉度弱于 nginx，子域名租户路由等复杂场景资料少 | 备选，本项目无特殊诉求不引入 |
| HAProxy | 优点：域基类/L7 负载均衡专家，性能极强；缺点：静态托管弱，功能面窄 | 纯 LB 场景可用，本项目需要静态托管，不单独选它 |
| OpenResty | 优点：nginx + Lua 脚本，动态逻辑强；缺点：多一层 Lua 学习成本 | 本项目动态边缘逻辑（路由 / 认证 / 限流）交给基于 OpenResty 的 APISIX，nginx 专注静态托管与反代 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **WebSocket 断连**：必须 `proxy_http_version 1.1` 并转发 Upgrade/Connection 头，否则 /socket.io 握手失败（本项目 nginx → 网关 → 后端全链路均需透传）。
- **反代目标用服务名**：`/api` 反代目标必须是网关的稳定主机名（Compose DNS `apisix:9080`；迁 K8s 为 Service 名），**禁硬编码 IP**；网关侧同样按服务名寻址。
- **真实 IP 与信任边界**：反代置 `X-Real-IP` / `X-Forwarded-For` 后，网关才可能按真实客户端 IP 限流；网关 `real-ip` 的可信网段须与实际代理网段一致，否则伪造头可绕过（生产应关闭网关直连暴露）。
- **Socket.IO 亲和**：连接升级后必须固定同一后端实例（ip_hash / Cookie 亲和或网关粘性），否则重连后状态丢失。
- **证书续期**：泛域名证书有有效期，到期前续期并 reload，避免全站 HTTPS 中断。
- **X-Frame-Options**：设 SAMEORIGIN 既能防点击劫持，又允许本项目同源嵌入 Grafana，别误设 DENY。
- **SPA 回退**：前端单页路由用 `try_files $uri $uri/ /index.html`，否则刷新子路由 404。
- **平滑 reload**：改配置用 `nginx -s reload`（容器内同理），先 `nginx -t` 校验语法，避免打挂入口。
- **Windows 与 Linux 差异**：本地可用官方 Windows 版或 Docker 容器试配置，生产按 Linux 口径（路径、用户、信号）。
- **dev / prod 配置分离**：两套配置分开维护，HSTS、日志级别、文档开关等按环境切换，不混用一份。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| nginx 官方文档 | https://nginx.org/en/docs/ | 配置指令权威参考，反代 / WebSocket / TLS 均有专章 |
| nginx 官网 | https://nginx.org/ | 下载（含 Windows 版）、changelog、安全公告 |
| nginx 中文社区 | https://www.nginx.cn/ | 中文资料与问答聚合 |
| nginx 源码 | https://github.com/nginx/nginx | 源码与 issue 讨论 |
| MDN：Upgrade 头 | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Upgrade | WebSocket 升级机制的协议背景 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 平台《架构设计 · 总体架构》「技术栈全景 · 部署与运维」节 | 部署与运维技术栈（nginx 条目） |
| 平台《项目规划说明》「部署与运维」节 | 选型说明：静态托管 / 反代 / 负载均衡 / 子域名租户路由 |
| 平台《项目规划说明》「部署拓扑」节 | 部署拓扑：nginx 为统一入口 |
| 平台《项目规划说明》「集群设计要点」节 | WebSocket 放行、安全响应头、X-Frame-Options 约定 |
| 《[APISIX 技术介绍](../后端核心/APISIX技术介绍.md)》 | `/api` 反代目标：边缘统一入口（路由 / 认证 / 限流 / 观测） |
| [部署发布规范](../../../规范/部署发布规范.md) | 「API 网关配置与热加载」节：声明式入 Git、边缘限流与观测口径 |
| [APISIX 部署使用说明](../../开发服务器/linux/APISIX部署使用说明.md) | 边缘网关部署实录与排障（nginx 与其分工） |
| 《[Docker 与 Compose 技术介绍](Docker与Compose技术介绍.md)》 | nginx 以 `bms-gateway-nginx` 容器方式编排（`deploy/compose/gateway.yml`） |
| 《[Vite 技术介绍](../前端/Vite技术介绍.md)》 | 产出被 nginx 托管的前端构建产物 |
| 《[python-socketio 技术介绍](../后端核心/python-socketio技术介绍.md)》 | 被 nginx 透传代理的 WebSocket 长连接 |
| 《[Grafana 技术介绍](Grafana技术介绍.md)》 | 同源嵌入依赖 X-Frame-Options SAMEORIGIN |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写
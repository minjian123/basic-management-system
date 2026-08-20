# nginx 技术介绍

> Web 服务器 · 静态托管 / 反向代理 / TLS 终止

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [部署与运维](../技术栈知识档案总览.md#ops) › nginx 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**nginx**（发音 "engine-x"）是高性能 HTTP 服务器与反向代理，
2004 年由 Igor Sysoev 发布，以**事件驱动**架构（epoll）著称，
用很少的内存扛住高并发，是互联网上占比最高的 Web 服务器之一。
在 BMS 里它承担统一入口：托管前端静态资源、反向代理 API、TLS 终止与负载均衡。

- **定位**：BMS 生产入口层，所有浏览器流量先到 nginx 再分发（《[项目规划说明](../../../规划/项目规划说明.html#stack-ops)》2.4 节）。
- **版本**：1.2x 系列（stable 与 mainline 双轨发布，生产用 stable）。
- **许可**：BSD-2-Clause，免费开源无商用限制（《[项目规划说明](../../../规划/项目规划说明.html#stack-license)》2.5 节）。
- **落地形态**：frontend 容器内运行，托管 PC + 移动端静态资源并反代 /api（《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| master-worker | master 进程管配置与信号，worker 进程处理请求，改配置可平滑 reload 不中断服务 |
| 事件驱动 | 基于 epoll 的单线程多路复用，一个 worker 可服务大量并发连接，内存占用低 |
| server / location | 虚拟主机与路径匹配的两级配置：按域名选 server，按路径选 location |
| upstream | 后端服务器组定义，负载均衡的对象集合 |
| proxy_pass | 反向代理核心指令：把请求转发给 upstream，可改写路径与头 |
| TLS 终止 | 在 nginx 层解密 HTTPS，内部再走明文，后端不必各自配证书 |
| WebSocket 代理 | 转发 `Upgrade`/`Connection` 头，让 /socket.io 长连接穿透代理 |
| 负载均衡策略 | 轮询 / ip_hash / Cookie 亲和（sticky），Socket.IO 场景必须固定到同一后端实例 |
| 泛域名证书 | 一张 `*.example.com` 证书覆盖所有子域名，支撑子域名租户路由 |
| 子域名租户路由 | 不同租户走不同子域名，nginx 按 Host 头分发到对应后端，实现租户隔离入口 |
| 静态资源优化 | gzip 压缩、缓存头、长连接，前端构建产物由 nginx 直接吐出 |
| 安全响应头 | CSP / HSTS / X-Frame-Options / Referrer-Policy 等统一在入口层配置 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **静态托管**：托管前端构建产物（PC 管理端 + 移动端），浏览器直接拿静态资源，不打扰后端（《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节）。
- **反向代理**：`/api` 反代到后端多副本；生产同源部署，不开放跨域（《[项目规划说明](../../../规划/项目规划说明.html#env)》17 节）。
- **负载均衡 + TLS 终止**：后端无状态可横向扩展，nginx 负责分发与 HTTPS 解密（《[项目规划说明](../../../规划/项目规划说明.html#deploy-topo)》19.1 节）。
- **子域名租户路由**：多租户按子域名区分入口，配泛域名证书（《[项目规划说明](../../../规划/项目规划说明.html#stack-ops)》2.4 节）。
- **WebSocket 支持**：`/socket.io` 路径放行 Upgrade/Connection 头，负载均衡用 ip_hash / Cookie 亲和，保证 Socket.IO 连接升级后固定在同一后端实例（《[项目规划说明](../../../规划/项目规划说明.html#deploy-cluster)》19.2 节）。
- **安全响应头**：统一配置 CSP、HSTS（dev 关闭）、X-Frame-Options（SAMEORIGIN，兼容同源 Grafana 嵌入）、X-Content-Type-Options、Referrer-Policy、Permissions-Policy（《[项目规划说明](../../../规划/项目规划说明.html#deploy-cluster)》19.2 节）。
- **文档收敛**：生产环境关闭 Swagger/ReDoc 在线文档，对外只发 CI 导出的 swagger.json 快照（《[项目规划说明](../../../规划/项目规划说明.html#api)》8 节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **nginx（选中）** | 优点：事实标准、性能高、静态托管与反代都强、资料最多；缺点：配置是 C 风格语法，初学略陡 | 静态 + 反代 + TLS 三合一，团队与社区最熟 |
| Apache HTTP Server | 优点：.htaccess 灵活、mod 生态老；缺点：进程模型偏重，高并发反代不是强项 | 静态托管可，反代与负载均衡场景不如 nginx |
| Caddy | 优点：自动 HTTPS、配置极简；缺点：生态与团队熟悉度弱于 nginx，子域名租户路由等复杂场景资料少 | 备选，本项目无特殊诉求不引入 |
| HAProxy | 优点：L4/L7 负载均衡专家，性能极强；缺点：静态托管弱，功能面窄 | 纯 LB 场景可用，BMS 需要静态托管，不单独选它 |
| OpenResty | 优点：nginx + Lua 脚本，动态逻辑强；缺点：多一层 Lua 学习成本，BMS 用不到 | 过度设计，不采用 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **WebSocket 断连**：必须 `proxy_http_version 1.1` 并转发 Upgrade/Connection 头，否则 /socket.io 握手失败。
- **Socket.IO 亲和**：连接升级后必须固定同一后端实例（ip_hash / Cookie 亲和），否则重连后状态丢失。
- **证书续期**：泛域名证书有有效期，到期前续期并 reload，避免全站 HTTPS 中断。
- **X-Frame-Options**：设 SAMEORIGIN 既能防点击劫持，又允许 BMS 同源嵌入 Grafana，别误设 DENY。
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
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-ops)》2.4 节 | 部署与运维技术栈（nginx 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-ops)》3.4 节 | 选型说明：静态托管 / 反代 / 负载均衡 / 子域名租户路由 |
| 《[项目规划说明](../../../规划/项目规划说明.html#deploy-topo)》19.1 节 | 部署拓扑：nginx 为统一入口 |
| 《[项目规划说明](../../../规划/项目规划说明.html#deploy-cluster)》19.2 节 | WebSocket 放行、安全响应头、X-Frame-Options 约定 |
| 《[Docker 与 Compose 技术介绍](Docker与Compose技术介绍.md)》 | nginx 以 frontend 容器方式编排 |
| 《[Vite 技术介绍](../前端/Vite技术介绍.md)》 | 产出被 nginx 托管的前端构建产物 |
| 《[python-socketio 技术介绍](../后端核心/python-socketio技术介绍.md)》 | 被 nginx 代理的 WebSocket 长连接 |
| 《[Grafana 技术介绍](Grafana技术介绍.md)》 | 同源嵌入依赖 X-Frame-Options SAMEORIGIN |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
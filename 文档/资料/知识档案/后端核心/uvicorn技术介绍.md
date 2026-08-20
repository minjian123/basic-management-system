# uvicorn 技术介绍

> ASGI 服务器 · BMS 后端核心

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › uvicorn 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**uvicorn** 是一个基于 asyncio 的轻量级 **ASGI 服务器**，
负责把 HTTP/WebSocket 请求翻译成 ASGI 协议事件，交给 FastAPI 应用处理。
它是 FastAPI 官方推荐的服务器，启动快、原生异步、支持 WebSocket。

- **定位**：承载 FastAPI 应用的进程入口，任何环境的启动与部署都离不开它。
- **版本**：0.3x 系列（跟随 asyncio/ASGI 生态持续迭代）。
- **许可**：BSD-3-Clause，宽松开源。
- **语言**：Python（本项目 3.14+）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| ASGI | 异步服务器网关接口：HTTP/WebSocket 与 Python 应用的通信协议标准，是 WSGI（同步旧标准）的异步继任者 |
| WSGI | 同步版网关接口（gunicorn/Flask 时代的标准），不支持 WebSocket 与长连接 |
| 事件循环（Event Loop） | 单进程内调度所有异步任务的引擎，uvicorn 基于 asyncio，可选用 uvloop（更快） |
| Worker（工作进程） | 独立进程，各自跑一个事件循环；多 worker 并行利用多核 CPU |
| `--reload` | 开发模式热重载：代码变更自动重启，生产环境禁用 |
| `--workers N` | 启动 N 个 worker 进程（需配合 `--proxy-headers` 等信任反向代理参数使用） |
| uvloop | 基于 libuv 的高性能事件循环实现，比 asyncio 默认循环更快，仅 POSIX 平台可用 |
| HTTP/1.1 与 HTTP/2 | uvicorn 默认 HTTP/1.1；HTTP/2 需 `--http2` 且要求 TLS（本项目由 nginx 终止 TLS） |
| WebSocket | 全双工长连接协议，uvicorn 原生支持，是 Socket.IO 实时推送的承载通道 |
| 进程模型 | master 进程 + N 个 worker：worker 数量决定并发上限，也决定数据库连接池的规划基数 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为唯一 ASGI 服务器承载 FastAPI，开发命令：`uv run uvicorn app.main:app --reload --port 8000`（见《[开发部署规划](../../../规划/开发部署规划.md)》5.3 节）。
- **多 worker 部署**：生产按规划以多 worker 运行（如 4 worker），并通过 nginx 反向代理统一入口（见《[项目规划说明》14 节](../../../规划/项目规划说明.md#perf)）。
- 支持 HTTP/WebSocket：普通 REST 接口与 python-socketio 实时推送共用同一 uvicorn 进程。
- **连接池规划联动**：数据库连接池大小按 worker 数规划，确保 `总连接数 = worker × (pool_size + max_overflow) ≤ 数据库 max_connections 的 70%`（见《[项目规划说明》14 节](../../../规划/项目规划说明.md#perf)）。
- 容器化部署时由 Docker Compose 启动 backend 多副本（见《[项目规划说明》19.3 节](../../../规划/项目规划说明.md#deploy-compose)）。
- 健康检查 `/healthz`、`/readyz` 由 uvicorn 提供 HTTP 入口，供编排与监控探测。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **uvicorn（选中）** | FastAPI 官方推荐、原生异步、支持 WebSocket、启动快；多 worker 需注意进程内状态共享问题 | 与 FastAPI 异步栈契合度最高，零适配成本 |
| hypercorn | 支持 HTTP/3、worker 管理内置；但性能与社区资料略逊 | 无 HTTP/3 需求，不必引入 |
| gunicorn（配 uvicorn worker） | 经典同步服务器，进程管理成熟；同步 worker 会阻塞异步应用 | 需额外包一层，uvicorn 自带多 worker 即可 |
| daphne | Django Channels 的 ASGI 服务器 | 与 FastAPI 无关联，排除 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **worker 数不是越多越好**：worker 数 × 连接池要算总连接数预算（≤ 数据库 70% 上限），同时注意内存开销；规划建议值 4 起评估。
- **多 worker 与进程内状态**：每个 worker 是独立进程，进程内缓存（dogpile.cache 字典内存）各自为政，跨实例一致性靠全局版本号，不要依赖单进程变量。
- **--reload 只能用于开发**：生产开启会重复监视文件、降低性能且存在安全隐患。
- **反向代理头**：置于 nginx 之后时必须正确传递 `X-Forwarded-For`/`X-Forwarded-Proto`（--proxy-headers 或 nginx 配置），否则日志 IP 与 HTTPS 判断错误。
- **uvloop 平台限制**：仅 Linux/macOS 可用，Windows 开发环境走默认 asyncio 循环，行为一致性能略降。
- **WebSocket 与 worker**：多 worker 下 Socket.IO 长连接分发到不同 worker，必须配合 Redis 适配器跨实例广播（python-socketio 已内置方案）。
- **优雅退出**：部署停止时应发送 SIGTERM 让 uvicorn 完成在途请求（--timeout-graceful-shutdown 控制），避免直接 SIGKILL。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| uvicorn 官方文档 | https://www.uvicorn.org/ | 权威文档：配置项、部署参数、命令行说明 |
| uvicorn GitHub | https://github.com/encode/uvicorn | 源码、issue 与版本发布 |
| ASGI 规范文档 | https://asgi.readthedocs.io/ | ASGI 协议标准，理解协议底层的必读 |
| FastAPI 部署章节 | https://fastapi.tiangolo.com/deployment/ | 官方部署指引：uvicorn 多 worker、代理、容器化 |
| uvloop 项目页 | https://github.com/MagicStack/uvloop | 高性能事件循环实现，生产部署可选加速 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明》2.1 节](../../../规划/项目规划说明.md#stack-backend) | 技术栈：ASGI 服务器条目（多 worker 部署） |
| 《[项目规划说明》14 节](../../../规划/项目规划说明.md#perf) | worker 数与数据库连接池规划口径 |
| 《[项目规划说明》19.3 节](../../../规划/项目规划说明.md#deploy-compose) | Docker Compose：backend 多副本编排 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 被承载的 Web 框架 |
| 《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》 | 连接池大小与 worker 数的联动规划 |
| 《[nginx 技术介绍](../部署与运维/nginx技术介绍.md)》 | 反向代理与 TLS 终止，uvicorn 前端网关 |
| 《[部署发布规范](../../../规范/部署发布规范.md)》 | 生产部署的启动参数与优雅停机要求 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19
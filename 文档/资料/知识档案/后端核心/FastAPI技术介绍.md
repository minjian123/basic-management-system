# FastAPI 技术介绍

> Python 高性能 Web 框架 · BMS 后端核心

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › FastAPI 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**FastAPI** 是一个基于 Python 的现代 Web 框架，用于构建 RESTful API。
它由 Sebastian Ramirez 于 2018 年发布，主打**高性能**（与 Node.js、Go 同级）、
**原生异步**与**自动生成 API 文档**。
截至 2026 年，FastAPI 已是 Python Web 框架中增长最快、社区最活跃的之一。

- **定位**：BMS 后端 API 的唯一 Web 框架，承载全部 HTTP 接口。
- **版本**：0.1xx 系列（持续迭代，无大版本跳变）。
- **许可**：MIT，OSI 认证开源。
- **语言**：Python（本项目 3.14+）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| ASGI | 异步服务器网关接口：FastAPI 运行于 ASGI 协议之上，支持 WebSocket、HTTP/2 与长连接，由 uvicorn 等 ASGI 服务器承载 |
| 路径操作（Path Operation） | 用装饰器（如 `@app.get("/users")`）声明的接口：一个路径 + 一种方法 = 一个操作 |
| 依赖注入（DI） | `Depends()` 机制：公共逻辑（数据库会话、认证、分页）写成依赖函数，自动注入到接口，可复用可测试 |
| 类型注解驱动 | 接口参数直接写 Python 类型注解（`user_id: int`），FastAPI 据此自动完成校验与转换 |
| Pydantic 模型 | 请求体、响应体用 Pydantic 模型声明，校验失败自动返回 422 错误（见《[Pydantic 技术介绍](Pydantic技术介绍.md)》） |
| OpenAPI 自动生成 | 框架自动产出 OpenAPI（Swagger）schema，内置 Swagger UI 与 ReDoc 交互文档（见《[Swagger UI 技术介绍](../工程化与质量/SwaggerUI与ReDoc技术介绍.md)》） |
| 异步支持 | 接口函数可声明 `async def`，配合异步数据库驱动实现高并发，I/O 等待时不阻塞事件循环 |
| Background Tasks | 内置后台任务机制，响应返回后异步执行轻量任务（如发邮件），重任务建议走 Celery |
| 异常处理器 | `@app.exception_handler` 统一捕获异常，转换为统一错误响应格式 |
| 中间件（Middleware） | 请求进/响应出的钩子链，可用于日志、CORS、限流、请求 ID 注入等横切逻辑 |
| APIRouter | 路由分组工具，按模块拆分路由文件，BMS 分层架构中 api 层的组织基础 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 作为后端唯一 Web 框架，全部 RESTful API（`/api/v1/...`）由 FastAPI 承载。
- 与异步 SQLAlchemy 天然契合：接口 `async def` + 异步会话，见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》。
- 自动生成的 Swagger UI / ReDoc 作为接口联调与验收依据。
- 分层架构约束：api 层只做参数校验与路由分发（依赖注入），业务逻辑下沉 services 层，禁止在 api 层直接操作模型。
- 健康检查 `/healthz`、`/readyz` 为 FastAPI 路由，供编排系统滚动发布。
- 测试用 `httpx.ASGITransport` 免启服务器直测应用（见《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》）。

## 4. 选型对比 <a id="compare"></a>

| 框架 | 异步 | 类型校验 | API 文档 | 生态 | 结论 |
| --- | --- | --- | --- | --- | --- |
| **FastAPI（选中）** | 原生 async | Pydantic 强校验 | 自动生成 | 活跃、增长最快 | 与项目异步栈、类型安全目标完全契合 |
| Django + DRF | 部分（3.1+ 有限） | DRF Serializer | 需第三方 | 最成熟、全家桶 | 重、异步支持弱，管理后台与 BMS 场景不匹配 |
| Flask | 需扩展 | 无内置 | 需第三方（flasgger 等） | 轻量经典 | 同步为主，无类型体系，工程化约束靠自觉 |
| Starlette | 原生 async | 无内置 | 无 | FastAPI 底层 | 太底层，需自建大量基础设施，直接用 FastAPI 即可 |
| Sanctum / Litestar | 原生 async | 有 | 有 | 较新较小 | 生态与资料不如 FastAPI，团队上手成本高 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **同步函数阻塞事件循环**：接口内调用 CPU 密集或阻塞 I/O 的同步库（如 openpyxl）会卡住整个进程，需用线程池（`run_in_executor`）或交给 Celery。
- **异步会话跨请求共享**：SQLAlchemy 异步会话不能跨请求复用，每个请求通过依赖注入创建独立会话（见《[SQLAlchemy 技术介绍](SQLAlchemy技术介绍.md)》）。
- **422 与 400 混淆**：参数校验失败返回 422（FastAPI 默认），客户端需按统一错误码约定处理。
- **依赖循环注入**：依赖之间相互引用会抛错，公共依赖（认证、会话）放到 `core/` 层。
- **OpenAPI 文档暴露内网细节**：生产环境按需关闭或加访问控制，避免泄露接口结构。
- **版本兼容**：FastAPI 0.1xx 迭代快，依赖锁定（uv.lock）后升级需跑全量测试；Python 3.14 兼容性纳入阶段一验证口径。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| FastAPI 官方文档 | https://fastapi.tiangolo.com/ | 权威文档，含完整教程，支持多语言 |
| FastAPI 官方文档（中文） | https://fastapi.tiangolo.com/zh/ | 官方中文版教程 |
| FastAPI GitHub | https://github.com/fastapi/fastapi | 源码与 issue 讨论 |
| fastapi-users | https://fastapi-users.github.io/fastapi-users/ | 注册/登录/认证的现成方案（参考实现） |
| Full Stack FastAPI 模板 | https://github.com/fastapi/full-stack-fastapi-template | 官方全栈项目模板，学习项目结构的最佳样例 |
| FastAPI 中文社区 | https://fastapi.org.cn/ | 中文资料聚合 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html)》2.1 节 | 后端技术栈与选型说明（FastAPI 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.html#structure)》4 节 | 目录结构：backend/app/api 路由层职责 |
| 《[API 接口规范](../../../规范/API接口规范.html)》 | 统一响应、错误码、幂等限流约定 |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | FastAPI 测试方式（httpx ASGITransport） |
| 《[Swagger UI 技术介绍](../工程化与质量/SwaggerUI与ReDoc技术介绍.md)》 | 接口文档自动生成机制 |
| 《[uvicorn 技术介绍](uvicorn技术介绍.md)》 | 承载 FastAPI 的 ASGI 服务器 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19
# FastAPI 集成技术介绍

> 插件如何接进 FastAPI · Depends 注入 · APIRouter 挂载与生命周期

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [插件化架构](../技术栈知识档案总览.md#plugin) › FastAPI 集成技术介绍　|　[← 返回总览](01_插件化架构_总览.md)

---

## 1. 技术概述 <a id="overview"></a>

FastAPI 自带的**依赖注入（Depends）**与 **`APIRouter`** 天然适合插件化：插件向宿主返回一个 router 或注册函数，宿主决定挂载前缀、注入共享服务、管理启动/关闭。FastAPI 官方也直言「用依赖即可实现无限扩展，无需另造插件机制」——但工程上仍需约定**注册方式、共享上下文与生命周期**，避免插件各自为政。

- **定位**：把插件机制（注册表/发现）与 Web 框架对接的一层；对应阶段一的装配挂载。
- **关键点**：宿主掌握组合权，插件只提供能力（返回 router / 注册依赖），不直接改 `app`。
- **共享上下文**：通过 `PluginContext` 暴露允许插件使用的服务（配置、DB 会话、注册表），插件不依赖宿主内部实现。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| `Depends` | 声明式依赖注入：路径函数声明所需依赖，框架负责解析与注入 |
| `APIRouter` | 路由集合，可带 `prefix` / `tags`，由宿主 `include_router` 挂载 |
| 依赖层级树 | 依赖可再依赖其他依赖，框架自动解析整棵树 |
| 生命周期（lifespan） | 应用启动/关闭钩子，用于初始化与释放插件资源 |
| 共享上下文 | 宿主构造并传入的 `PluginContext`，限定插件可用的服务边界 |
| 能力包（capability package） | 独立包子包，自带上路由/依赖/测试，宿主按需装载 |

```python
# 插件侧：返回 router，不直接改 app
from dataclasses import dataclass
from fastapi import APIRouter, Depends

@dataclass
class PluginContext:
    settings: object
    id_generator: object

def get_router(ctx: PluginContext) -> APIRouter:
    router = APIRouter(prefix="/plugins/id", tags=["plugins"])

    @router.get("/next")
    async def next_id(tenant_id: int = 0):
        return {"id": await ctx.id_generator.next_id()}

    return router
```

```python
# 宿主侧：加载、注入、挂载
from contextlib import asynccontextmanager
from fastapi import FastAPI

def load_plugins(app: FastAPI, ctx: PluginContext) -> None:
    for name, factory in load_registry():      # 发现/注册表
        app.include_router(factory(ctx))       # 宿主掌握挂载与前缀

@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx = build_context()                       # 装配：config + 注册表
    load_plugins(app, ctx)
    yield
    await shutdown_plugins(ctx)                 # 释放资源

app = FastAPI(lifespan=lifespan)
```

## 3. 在本项目中的用途 <a id="usage"></a>

- **能力插件提供路由**：如 ID 生成的运维查询接口、存储/通知插件的自检接口，以 router 形式挂载。
- **产品扩展的页面与接口**：产品前端模块经平台注册、后端扩展包以 router + 模型 + 任务注册的方式并入平台（横向扩展），宿主掌握组合。
- **依赖注入装配服务**：`Depends` 把 [09 配置驱动实现选择](09_插件化架构_配置驱动实现选择.md) 装配出的实现注入路径函数，业务代码只认端口。
- **生命周期统一管理**：插件的连接、任务、缓存初始化放 lifespan，避免模块导入期副作用。
- **挂载规范**：插件路由统一前缀（如 `/api/v1/plugins/{name}`）与 `tags`，防止路径冲突并便于权限与审计挂接。

## 4. 设计要点 <a id="practice"></a>

- **插件返回 router，宿主挂载**：比让插件直接 `app.include_router` 更可控（前缀、鉴权、限流集中处理）。
- **共享上下文最小化**：`PluginContext` 只暴露契约允许的服务；插件不得 `import` 宿主内部模块。
- **前缀与命名空间**：插件路由使用独立前缀，避免与平台路径冲突；冲突在启动阶段检测。
- **鉴权与权限**：插件路由复用平台认证/权限依赖（`Depends`），不自建鉴权。
- **异常与限流**：宿主统一异常处理与限流中间件；插件异常不得绕过统一错误码体系。
- **异步一致**：插件路径函数用 `async def`，阻塞操作放线程池，避免拖垮事件循环。
- **可测试**：插件 router 用 `TestClient`/`ASGITransport` 独立测试，不必起完整应用。

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **导入期副作用**：插件模块顶层创建连接/任务，导入即执行，测试与启动都受影响。
- **插件直接改 app**：绕过了宿主的挂载规范，导致前缀、鉴权、审计散落不可控。
- **依赖循环**：插件与宿主互相 `import`，需以 `PluginContext` 解耦。
- **路由重复**：多个插件注册相同路径，后挂载者被忽略或覆盖；用前缀 + 启动校验避免。
- **lifespan 遗漏释放**：插件持有的连接/任务未在关闭时释放，滚动发布时报错累积。
- **把 Depends 当 DIP**：注入具体实现仍耦合，注入的应是端口抽象。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| FastAPI Dependencies | https://fastapi.tiangolo.com/tutorial/dependencies/ | 依赖注入与插件式集成 |
| FastAPI Bigger Applications | https://fastapi.tiangolo.com/tutorial/bigger-applications/ | `APIRouter` 组织多模块 |
| FastAPI Lifespan Events | https://fastapi.tiangolo.com/advanced/events/ | 启动/关闭生命周期 |
| FastAPI Testing | https://fastapi.tiangolo.com/tutorial/testing/ | 插件路由测试 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[08 自建注册表](08_插件化架构_自建注册表.md)》 | 插件的注册与查找 |
| 《[09 配置驱动实现选择](09_插件化架构_配置驱动实现选择.md)》 | 装配入口与配置 |
| 《[11 生命周期与热插拔](11_插件化架构_生命周期与热插拔.md)》 | 启停与资源释放 |
| 《[FastAPI 技术介绍](../后端核心/FastAPI技术介绍.md)》 | 宿主框架基础 |
| 《[Pydantic 技术介绍](../后端核心/Pydantic技术介绍.md)》 | 请求/响应模型与配置校验 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写

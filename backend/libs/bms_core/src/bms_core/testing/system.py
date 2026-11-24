"""全系统装配组件（13_10）：初始化之后、用例之前，把本仓全部后端服务装配一次。

真实运行是「初始化 → 装配一次 → 多实例并发使用」：测试若按用例 / 文件 / 单个服务各自装配，
就等于预设「其他功能没有在跑」，与「库是干净的」同属错误前提。

本模块只提供**装配容器**，不导入任何服务包（依赖方向：`bms_core` 不反向依赖业务服务）：

- 服务清单与工厂由调用方（测试插件 / 夹具）以 `{service_key: factory}` 传入；
- `assemble()` 逐个创建应用并进入 lifespan（失败即整体回滚并抛出，不带病继续）；
- `client(service_key)` 供用例以「用户」身份访问已装配实例；
- `reset_per_test()` 只复位跨用例存活的缓存，**不重建应用**。

进程级单例由 `set_assembled_system()` 登记，供服务间进程内直连按 `service_key` 取应用。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.testing.fixtures import clear_tenant_cache

__all__ = (
    "AssembledSystem",
    "AssembledTransport",
    "get_assembled_system",
    "reset_assembled_system",
    "set_assembled_system",
)

_system: AssembledSystem | None = None
"""进程级已装配系统（每个 pytest 进程 / worker 一份）。"""


class AssembledSystem:
    """全系统装配容器：一次创建并启动全部服务应用。

    Attributes:
        apps: 已装配应用（`service_key` → `FastAPI`，插入序）。
    """

    def __init__(
        self,
        factories: ConcurrentStableDict[str, Callable[[], FastAPI]],
        *,
        before_start: Callable[[str, FastAPI], None] | None = None,
    ) -> None:
        """初始化（尚未装配）。

        Args:
            factories: 服务键 → 应用工厂（零参，返回未进入 lifespan 的应用）。
            before_start: 每个应用进入 lifespan 前的准备回调（服务键, 应用）；用于装载对端声明等。
        """
        self._factories: ConcurrentStableDict[str, Callable[[], FastAPI]] = ConcurrentStableDict(factories)
        self.apps: ConcurrentStableDict[str, FastAPI] = ConcurrentStableDict()
        self._stack: AsyncExitStack | None = None
        self._before_start = before_start

    async def assemble(self) -> AssembledSystem:
        """按清单顺序创建并启动全部应用（只允许一次）。

        Returns:
            AssembledSystem: 自身（便于链式调用）。

        Raises:
            RuntimeError: 重复装配。
        """
        if self._stack is not None:
            raise RuntimeError("AssembledSystem 只允许装配一次")
        stack = AsyncExitStack()
        try:
            for service_key, factory in self._factories.items():
                app = factory()
                if self._before_start is not None:
                    self._before_start(service_key, app)
                await stack.enter_async_context(app.router.lifespan_context(app))
                self.apps[service_key] = app
        except BaseException:
            await stack.aclose()
            self.apps.clear()
            raise
        self._stack = stack
        return self

    async def aclose(self) -> None:
        """逆序退出全部 lifespan（未装配时无操作）。"""
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()
        self.apps.clear()

    def app(self, service_key: str) -> FastAPI:
        """取已装配应用。

        Args:
            service_key: 服务键（如 `platform`）。

        Returns:
            FastAPI: 应用实例。

        Raises:
            RuntimeError: 系统未装配或服务未在装配清单内。
        """
        app = self.apps.get(service_key)
        if app is None:
            available = "、".join(self.apps)
            raise RuntimeError(f"服务 `{service_key}` 未装配（可用：{available or '无'}）")
        return app

    @asynccontextmanager
    async def client(
        self,
        service_key: str,
        *,
        headers: ConcurrentStableFrozenDict[str, str] | None = None,
    ) -> AsyncGenerator[httpx.AsyncClient]:
        """按服务键取一个指向已装配应用的异步客户端。

        Args:
            service_key: 服务键。
            headers: 默认请求头。

        Yields:
            httpx.AsyncClient: 测试客户端（退出即关闭）。
        """
        transport = httpx.ASGITransport(app=self.app(service_key))
        async with httpx.AsyncClient(transport=transport, base_url=f"http://{service_key}.internal") as client:
            if headers:
                client.headers.update(dict(headers))
            yield client

    def reset_per_test(self) -> None:
        """复位跨用例存活的进程内缓存（不重建应用）。

        目前只清租户源缓存；请求上下文 / 审计开关 / 权限缓存的复位仍由函数级夹具负责。
        """
        for app in self.apps.values():
            clear_tenant_cache(app)


def get_assembled_system() -> AssembledSystem:
    """取进程级已装配系统。

    Returns:
        AssembledSystem: 已装配系统。

    Raises:
        RuntimeError: 尚未装配（用例不应自行装配，应由会话级装配夹具负责）。
    """
    if _system is None:
        raise RuntimeError("全系统尚未装配：请由会话级装配夹具在用例开始前完成")
    return _system


def set_assembled_system(system: AssembledSystem) -> None:
    """登记进程级已装配系统（装配夹具调用）。

    Args:
        system: 已装配系统。
    """
    global _system
    _system = system


def reset_assembled_system() -> None:
    """清空进程级登记（测试隔离 / 会话结束调用）。"""
    global _system
    _system = None


class AssembledTransport(httpx.AsyncBaseTransport):
    """按主机名（服务键）路由到已装配应用的 ASGI 传输。

    供服务间调用使用：`base_url_template = "http://{service}"` 时，主机名就是服务键；
    请求直接进入对应已装配应用的 ASGI 栈，不经过网络。

    Attributes:
        transports: 服务键 → ASGI 传输（惰性创建、按模块复用）。
    """

    def __init__(self, system: AssembledSystem) -> None:
        """初始化。

        Args:
            system: 已装配系统。
        """
        self._system = system
        self.transports: ConcurrentStableDict[str, httpx.ASGITransport] = ConcurrentStableDict()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """按请求主机名路由到已装配应用。

        Args:
            request: httpx 请求（主机名 = 服务键）。

        Returns:
            httpx.Response: 目标应用返回的响应。

        Raises:
            RuntimeError: 服务未装配（不静默回落网络）。
        """
        service_key = request.url.host
        transport = self.transports.get(service_key)
        if transport is None:
            transport = httpx.ASGITransport(app=self._system.app(service_key))
            self.transports[service_key] = transport
        return await transport.handle_async_request(request)

    async def aclose(self) -> None:
        """释放全部 ASGI 传输（幂等）。"""
        for transport in self.transports.values():
            await transport.aclose()
        self.transports.clear()

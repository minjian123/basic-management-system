"""数据库访问门钩子：生产默认直通，测试基座注入跨进程读写门（13_08）。

为什么放在生产侧：`db/session.py` 不能依赖 `bms_core.testing`（测试基座是可选面，运行镜像不装）。
这里只留一个可替换的钩子——生产进程不注入（零开销），测试会话由启动插件在 `pytest_configure`
注入读写门，使「所有数据库读写都在门上排队」只有一份实现，且会话入口不必区分运行环境。
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final

GateHook = Callable[[str, bool, "float | None"], AbstractAsyncContextManager[None]]
"""门钩子签名：（数据源键, 是否只读, 等待上限）→ 异步上下文管理器。"""

GATE_CRITICAL_WAIT: Final = 30.0
"""整段临界区的等门上限（秒）：建表、用例级独占、显式写区间等「整段」场景用它。

与单次写的短上限（测试基座默认 5s）分工：单次写是毫秒级，等超几秒就是有长占用，报错更有用；
而整段临界区本身合法地要跑若干秒（首次建表、跨多步全局状态），用短上限会把正常作业打死。

13_08 T7 从 180s 收到 30s：180s 一轮的卡顿会让整批 worker 的启动引导全部等满超时，
一次全量只暴露一个现场；30s 既能容下正常的整段作业，又能让卡点快速失败、快速暴露。
"""

_hook: GateHook | None = None
"""已注入的门钩子；None 表示直通（生产默认）。"""


def set_gate_hook(hook: GateHook | None) -> None:
    """注入或清除门钩子（测试基座在会话起始调用）。

    Args:
        hook: 门钩子；None 清除。
    """
    global _hook
    _hook = hook


def current_gate_hook() -> GateHook | None:
    """取当前门钩子（诊断与自测用）。

    Returns:
        GateHook | None: 门钩子；未注入为 None。
    """
    return _hook


@asynccontextmanager
async def db_access_gate(db_key: str, *, read_only: bool, wait: float | None = None) -> AsyncGenerator[None]:
    """数据库访问门（未注入钩子时直通）。

    Args:
        db_key: 数据源键（平台库键或租户库键）。
        read_only: 是否只读（只读取读门，写取写门）。

    Yields:
        None: 门内区间。
    """
    hook = _hook
    if hook is None:
        yield
        return
    async with hook(db_key, read_only, wait):
        yield


class LazyGatedSession:
    """把门推迟到「第一次真正用库」再取（懒请求）。

    为什么要它：请求进来就取门，会把鉴权、能力调用、装配这些**不碰库**的时间也算进
    临界区（实测单次可达数秒）。本类包一层会话：第一次 `await` 数据库方法时才进入门，
    `aclose()` 时释放。生产（未注钩子）不会创建本类，零开销。

    Attributes:
        info: 底层会话的 `info`（SQLAlchemy 内部也读它）。
    """

    def __init__(self, scope: AbstractAsyncContextManager[None], session: object) -> None:
        """初始化。

        Args:
            scope: 门上下文（每次会话一个）。
            session: 底层会话对象。
        """
        object.__setattr__(self, "_scope", scope)
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_entered", False)

    def __getattr__(self, name: str) -> Any:
        """代理属性：协程方法包一层「先取门」，其余原样返回。

        Args:
            name: 属性名。

        Returns:
            Any: 属性值或包装后的方法。
        """
        attr = getattr(object.__getattribute__(self, "_session"), name)
        # 只包协程方法：`begin()` / `add()` 这类同步方法必须原样返回，包成协程会直接崩。
        if not inspect.iscoroutinefunction(attr):
            return attr

        async def _call(*args: object, **kwargs: object) -> object:
            await self._ensure()
            return await attr(*args, **kwargs)

        return _call

    async def _ensure(self) -> None:
        """首次使用时进入门。"""
        if not object.__getattribute__(self, "_entered"):
            await object.__getattribute__(self, "_scope").__aenter__()
            object.__setattr__(self, "_entered", True)

    async def aclose(self) -> None:
        """关闭底层会话并放门（未取过门则只关会话）。"""
        session = object.__getattribute__(self, "_session")
        with contextlib.suppress(Exception):
            await session.aclose()
        if object.__getattribute__(self, "_entered"):
            with contextlib.suppress(Exception):
                await object.__getattribute__(self, "_scope").__aexit__(None, None, None)
            object.__setattr__(self, "_entered", False)

    def __repr__(self) -> str:
        """诊断用表示。

        Returns:
            str: 表示串。
        """
        return f"LazyGatedSession({object.__getattribute__(self, '_session')!r})"

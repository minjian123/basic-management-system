"""数据库访问门钩子：生产默认直通，测试基座注入跨进程读写门（13_08）。

为什么放在生产侧：`db/session.py` 不能依赖 `bms_core.testing`（测试基座是可选面，运行镜像不装）。
这里只留一个可替换的钩子——生产进程不注入（零开销），测试会话由启动插件在 `pytest_configure`
注入读写门，使「所有数据库读写都在门上排队」只有一份实现，且会话入口不必区分运行环境。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

GateHook = Callable[[str, bool], AbstractAsyncContextManager[None]]
"""门钩子签名：（数据源键, 是否只读）→ 异步上下文管理器。"""

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
async def db_access_gate(db_key: str, *, read_only: bool) -> AsyncGenerator[None]:
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
    async with hook(db_key, read_only):
        yield

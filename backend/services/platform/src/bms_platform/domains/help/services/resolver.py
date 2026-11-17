"""`help_content` 的数据库实现（08_03）：按候选顺序直读租户库。

- 每次解析按当前租户上下文开只读会话（`session_scope`），不缓存（内容缓存归 12_01）；
- 解析算法在 `repositories/content.py::HelpContentRepository.resolve`，本模块只做会话与降级；
- 租户库不可用 / 表缺失时返回空结果并告警，不阻断页面（与「未命中」同形）；
- 插件名 `db`，由平台服务在装配期显式登记并注入应用级引擎注册表。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from bms_core.core.config import get_settings
from bms_core.core.exceptions import BizError
from bms_core.core.logging import get_logger
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.help.content import (
    BaseHelpContentResolver,
    HelpContentQuery,
    HelpContentResult,
)
from bms_platform.domains.help.repositories.content import HelpContentRepository

__all__ = ["DB_HELP_CONTENT_PROVIDER", "DatabaseHelpContentResolver"]

DB_HELP_CONTENT_PROVIDER = "db"
"""内容侧落库实现名（`[help_content].provider = "db"`）。"""

_LOGGER = get_logger("bms.help")

type SessionOpener = Callable[[], AbstractAsyncContextManager[DbSession]]
"""会话开合口（默认按当前租户上下文；测试注入共享租户库回滚会话）。"""


class DatabaseHelpContentResolver(BaseHelpContentResolver):
    """帮助内容解析：按候选顺序直读租户库。"""

    plugin_name: str = DB_HELP_CONTENT_PROVIDER

    def __init__(
        self,
        *,
        engines: EngineRegistry | None = None,
        session_opener: SessionOpener | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 引擎注册表（None 首次使用时按配置懒建）。
            session_opener: 会话开合口（None 按当前租户上下文开只读会话）。
        """
        self._engines = engines
        self._session_opener = session_opener

    async def resolve(self, query: HelpContentQuery, *, request: Request | None = None) -> HelpContentResult:
        """按候选顺序解析帮助内容。

        Args:
            query: 解析请求（候选有序）。
            request: 当前请求（本实现不读取，保留契约）。

        Returns:
            HelpContentResult: 解析结果；库不可用 / 无租户上下文时为空结果。
        """
        try:
            async with self._opener() as session:
                return await HelpContentRepository(session).resolve(query)
        except (SQLAlchemyError, BizError) as exc:
            _LOGGER.warning("help_content_resolve_unavailable", error=str(exc))
            return HelpContentResult()

    @asynccontextmanager
    async def _open(self) -> AsyncGenerator[DbSession]:
        """按当前租户上下文开只读会话。

        Yields:
            DbSession: 租户库只读会话。
        """
        if self._engines is None:
            self._engines = EngineRegistry(EngineFactory(get_settings()))
        async with session_scope(self._engines, read_only=True) as session:
            yield session

    def _opener(self) -> AbstractAsyncContextManager[DbSession]:
        """取会话开合口（测试可注入）。

        Returns:
            AbstractAsyncContextManager[DbSession]: 会话上下文。
        """
        if self._session_opener is not None:
            return self._session_opener()
        return self._open()

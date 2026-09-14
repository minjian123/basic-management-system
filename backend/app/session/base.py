"""会话存储能力域：会话存取契约（真实 Redis + `sys_session` 随认证阶段回补）。

- `DEFAULT_SESSION_TTL`：默认会话 TTL（秒，14 天，与 refresh token 对齐）。
- `BaseSessionStore`：能力域中间层契约（`key = "session_store"`）——异步 `save` / `load` / `delete`。
- `NullSessionStore`：占位实现——`save` / `delete` 空操作、`load` 返回占位会话（**不连 Redis**）。
- `get_session_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：`session_id` 对应架构「会话管理」的会话 id（真实 key `bms:{租户}:sess:{session_id}` 由实现拼接）；
`load` 未命中返回 None（与会话不存在 = 已踢出 / 登出语义一致）。强制踢出、多端会话上限、`sys_session`
持久化归认证阶段上层；本契约只落会话存取原语（客户端侧）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from app.core.capability import BaseCapability, BaseNullObject

__all__ = [
    "DEFAULT_SESSION_TTL",
    "BaseSessionStore",
    "NullSessionStore",
    "get_session_store",
]

DEFAULT_SESSION_TTL = 1209600
"""默认会话 TTL（秒，14 天，与 refresh token 有效期对齐）。"""


class BaseSessionStore(BaseCapability, ABC):
    """会话存储契约：写入 / 读取 / 删除。"""

    key: str = "session_store"

    @abstractmethod
    async def save(
        self,
        session_id: str,
        payload: Mapping[str, object],
        *,
        ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """写入 / 覆盖会话（真实实现落 `sys_session` + Redis 标记）。

        Args:
            session_id: 会话 id。
            payload: 会话数据。
            ttl: 有效期（秒，默认 `DEFAULT_SESSION_TTL`）。
        """

    @abstractmethod
    async def load(self, session_id: str) -> Mapping[str, object] | None:
        """读取会话（不存在返回 None）。

        Args:
            session_id: 会话 id。

        Returns:
            Mapping[str, object] | None: 会话数据；不存在返回 None。
        """

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """删除会话（幂等，不存在不报错）。

        Args:
            session_id: 会话 id。
        """


class NullSessionStore(BaseSessionStore, BaseNullObject):
    """占位会话存储：写入 / 删除空操作、读取返回占位会话（不连 Redis，未接入真实实现时使用）。"""

    async def save(
        self,
        session_id: str,
        payload: Mapping[str, object],
        *,
        ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """空操作（占位不写入）。

        Args:
            session_id: 会话 id（占位忽略）。
            payload: 会话数据（占位忽略）。
            ttl: 有效期（占位忽略）。
        """

    async def load(self, session_id: str) -> Mapping[str, object] | None:
        """固定返回占位会话。

        Args:
            session_id: 会话 id（占位回显）。

        Returns:
            Mapping[str, object] | None: 占位会话（`{"session_id": session_id}`）。
        """
        return {"session_id": session_id}

    async def delete(self, session_id: str) -> None:
        """空操作（占位不删除）。

        Args:
            session_id: 会话 id（占位忽略）。
        """


def get_session_store(request: Request) -> BaseSessionStore:
    """取应用级会话存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseSessionStore: 应用装配的会话存储实例。
    """
    return cast("BaseSessionStore", request.app.state.session_store)

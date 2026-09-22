"""session 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.session.base.py 迁入）。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.session.base import DEFAULT_SESSION_TTL, BaseSessionStore

__all__ = [
    "NullSessionStore",
]


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

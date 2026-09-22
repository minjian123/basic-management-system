"""idempotency 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.idempotency.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.idempotency.base import DEFAULT_IDEMPOTENCY_TTL, IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore

__all__ = [
    "NullIdempotencyStore",
]


class NullIdempotencyStore(IdempotencyStore, BaseNullObject):
    """占位幂等存储：**恒定首次**（不连 Redis、不缓存结果，未接入真实存储时使用）。"""

    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """恒定首次（占位不写入任何存储，不拦截重复请求）。

        Args:
            key: 幂等 key（占位不区分）。
            ttl: 键有效期（占位忽略）。

        Returns:
            bool: True。
        """
        return True

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """恒定无缓存结果。

        Args:
            key: 幂等 key（占位不区分）。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: None。
        """
        return None

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """空操作（占位不缓存结果）。

        Args:
            key: 幂等 key（占位不区分）。
            payload: 首次结果载荷（占位忽略）。
            ttl: 键有效期（占位忽略）。
        """

"""lock 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.lock.base.py 迁入）。"""

from uuid import uuid4

from bms_core.core.capability import BaseNullObject
from bms_core.lock.base import DEFAULT_LOCK_TTL, DEFAULT_WAIT, BaseDistributedLock

__all__ = [
    "NullDistributedLock",
]


class NullDistributedLock(BaseDistributedLock, BaseNullObject):
    """占位分布式锁：恒定获取成功（不连 Redis），释放 / 续租恒定成功。"""

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """恒定返回锁令牌（占位不连 Redis、不写入任何存储）。

        Args:
            key: 锁 key（占位不区分）。
            ttl: 锁 TTL（占位忽略）。
            wait: 等待时长（占位忽略）。

        Returns:
            str | None: 新生成的锁令牌（UUID4 十六进制串）。
        """
        return uuid4().hex

    async def release(self, key: str, token: str) -> bool:
        """恒定释放成功（占位不校验令牌）。

        Args:
            key: 锁 key（占位不区分）。
            token: 锁令牌（占位不校验）。

        Returns:
            bool: True。
        """
        return True

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """恒定续租成功（占位不校验令牌）。

        Args:
            key: 锁 key（占位不区分）。
            token: 锁令牌（占位不校验）。
            ttl: 新的 TTL（占位忽略）。

        Returns:
            bool: True。
        """
        return True

"""replay 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.replay.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.replay.base import REPLAY_WINDOW, BaseReplayGuard

__all__ = [
    "NullReplayGuard",
]


class NullReplayGuard(BaseReplayGuard, BaseNullObject):
    """占位防重放：时间窗与签名真实校验，nonce 去重**恒定通过**（不连 Redis）。"""

    async def claim_nonce(self, nonce: str, *, ttl: int = REPLAY_WINDOW) -> bool:
        """恒定占用成功（占位不写入任何存储＝不拦截重复 nonce）。

        Args:
            nonce: 随机唯一串（占位不区分）。
            ttl: 占用有效期（占位忽略）。

        Returns:
            bool: True。
        """
        return True

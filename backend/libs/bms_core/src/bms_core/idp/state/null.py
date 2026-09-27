"""流程状态存储能力域缺省实现（Null Object）：占位返回、无副作用（未接入真实实现时使用）。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.idp.state.base import DEFAULT_IDP_STATE_TTL, BaseIdpStateStore

__all__ = [
    "NullIdpStateStore",
]


class NullIdpStateStore(BaseIdpStateStore, BaseNullObject):
    """占位流程状态存储：写入 / 删除空操作、消费恒定未命中（不连 Redis）。

    未配置真实实现时授权跳转会因状态无法持久（回调必然校验失败）而不可用——
    该口径与「能力域未接入即不可用」的 fail-closed 一致。
    """

    async def save(
        self,
        state: str,
        payload: Mapping[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_IDP_STATE_TTL,
    ) -> None:
        """空操作（占位不写入）。

        Args:
            state: 流程状态（占位忽略）。
            payload: 状态数据（占位忽略）。
            tenant: 租户编码（占位忽略）。
            ttl: 有效期（占位忽略）。
        """

    async def consume(self, state: str, *, tenant: str | None = None) -> Mapping[str, object] | None:
        """消费流程状态（占位恒定未命中）。

        Args:
            state: 流程状态（占位忽略）。
            tenant: 租户编码（占位忽略）。

        Returns:
            Mapping[str, object] | None: 恒定 None。
        """
        return None

    async def delete(self, state: str, *, tenant: str | None = None) -> None:
        """空操作（占位不删除）。

        Args:
            state: 流程状态（占位忽略）。
            tenant: 租户编码（占位忽略）。
        """

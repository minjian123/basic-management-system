"""幂等能力域：写接口幂等键去重与首次结果复用契约（真实 Redis SETNX 随性能与安全阶段回补）。

- `IDEMPOTENCY_HEADER`：幂等键请求头（`Idempotency-Key`，见《API接口规范》「幂等 / 限流 / 审计」节）。
- `IdempotencyStore`：能力域中间层契约（`key = "idempotency"`）——`begin` 前置去重（首次 True）、
  `load` 取首次结果、`save` 写首次结果；重复请求直接返回首次响应，并发穿透由幂等键字段唯一约束兜底
  （约束归落库阶段，见《架构设计 · 接口与集成》「对外 API」节）。
- `build_idempotency_key`：幂等 key 统一拼接（`bms:{租户|global}:idem:{键}`，
  见《架构设计 · 数据架构》「key 空间规划」节）。
- `get_idempotency_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：基座只做**去重与结果存取**、不判定业务；调用方在 `begin` 为 False 时用 `load` 的首次结果
直接回响应，不再执行业务。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

IDEM_KEY_PREFIX = "bms"
"""幂等 key 前缀（与缓存 / 锁 key 同前缀）。"""

GLOBAL_IDEM_SCOPE = "global"
"""全局幂等作用域位（无租户维度的幂等键）。"""

DEFAULT_IDEMPOTENCY_TTL = 86400
"""默认幂等键 TTL（秒，24 小时）；窗口内重复请求复用首次结果。"""

IDEMPOTENCY_HEADER = "Idempotency-Key"
"""幂等键请求头（写接口 POST / PUT 统一携带）。"""

IDEMPOTENCY_PAYLOAD_TYPE = dict[str, object]
"""首次结果载荷类型（序列化后的响应体）。"""


def build_idempotency_key(*, key: str, tenant: str | None = None) -> str:
    """构建幂等 key（规范 `bms:{租户|global}:idem:{键}`）。

    Args:
        key: 幂等键（取自请求头 `Idempotency-Key`）。
        tenant: 租户标识；None 表示全局键。

    Returns:
        str: 幂等 key。
    """
    return f"{IDEM_KEY_PREFIX}:{tenant or GLOBAL_IDEM_SCOPE}:idem:{key}"


class IdempotencyStore(BasePluggable, ABC):
    """幂等存储契约：前置去重 + 首次结果复用。"""

    key: str = "idempotency"
    plugin_key: str = "idempotency"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def begin(self, key: str, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> bool:
        """前置去重（幂等键首次占用）。

        Args:
            key: 幂等 key（经 `build_idempotency_key` 构建）。
            ttl: 键有效期（秒）。

        Returns:
            bool: 首次为 True（可继续执行业务）；重复为 False（应取首次结果返回）。
        """

    @abstractmethod
    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果。

        Args:
            key: 幂等 key。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果的序列化载荷；未缓存返回 None。
        """

    @abstractmethod
    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = DEFAULT_IDEMPOTENCY_TTL) -> None:
        """写首次结果（供重复请求复用）。

        Args:
            key: 幂等 key。
            payload: 首次结果的序列化载荷。
            ttl: 键有效期（秒）。
        """


def get_idempotency_store(request: Request) -> IdempotencyStore:
    """取应用级幂等存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        IdempotencyStore: 应用装配的幂等存储实例。
    """
    return cast("IdempotencyStore", request.app.state.idempotency_store)

"""一致性屏障能力域：执行前「等待目标变更已应用」的契约与提供者。

分布式事务默认方案（本地事务 + 最终一致）的一环：补上「执行前等待收敛」——
写方提交后产生版本、收敛点落副作用后推进「已应用版本」、执行方在执行前校验并等待。

- `BaseConsistencyBarrier`：能力域中间层契约（`key = "consistency_barrier"`）——
  `await_applied`（等待至已应用版本 ≥ 目标版本，超时抛 `ConsistencyBarrierTimeout`）、
  `applied_version`（读当前已应用版本）、`mark_applied`（推进已应用版本，单调不回退）。
- `build_consistency_key`：键空间统一拼接（`bms:{租户|global}:consistency:{scope}`）。
- `get_consistency_barrier`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：缺省实现为 `null`（即返回、不拦业务）；存储不可用时 `await_applied` 放行（degrade-open），
屏障自身不做单点。真正要求强一致的核心链路应在业务侧同时保留版本校验兜底。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

CONSISTENCY_KEY_PREFIX = "bms"
"""一致性屏障键前缀（与缓存 / 锁 / 幂等键同前缀）。"""

GLOBAL_CONSISTENCY_SCOPE = "global"
"""全局收敛作用域位（无租户维度的收敛键）。"""

DEFAULT_BARRIER_TIMEOUT_MS = 3000
"""默认等待超时（毫秒）；超时抛 `ConsistencyBarrierTimeout`。"""

DEFAULT_BARRIER_POLL_MS = 100
"""默认轮询间隔（毫秒）。"""


def build_consistency_key(*, scope: str, tenant: str | None = None) -> str:
    """构建一致性屏障键（规范 `bms:{租户|global}:consistency:{scope}`）。

    Args:
        scope: 收敛域键（如 `perm` 表权限、`org` 表组织）。
        tenant: 租户标识；None 表示全局键。

    Returns:
        str: 一致性屏障键。
    """
    return f"{CONSISTENCY_KEY_PREFIX}:{tenant or GLOBAL_CONSISTENCY_SCOPE}:consistency:{scope}"


class BaseConsistencyBarrier(BasePluggable, ABC):
    """一致性屏障契约：等待收敛 + 读 / 推进已应用版本。"""

    key: str = "consistency_barrier"
    plugin_key: str = "consistency_barrier"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def await_applied(
        self,
        *,
        scope: str,
        target_version: int,
        tenant: str | None = None,
        timeout_ms: int | None = None,
        poll_ms: int | None = None,
    ) -> None:
        """阻塞至「已应用版本 ≥ 目标版本」。

        Args:
            scope: 收敛域键。
            target_version: 目标版本（写方产生）。
            tenant: 租户标识；None 表示全局。
            timeout_ms: 等待超时（毫秒）；None 取配置缺省。
            poll_ms: 轮询间隔（毫秒）；None 取配置缺省。

        Raises:
            ConsistencyBarrierTimeout: 超时仍未收敛（`10011` / 409）。
        """

    @abstractmethod
    async def applied_version(self, *, scope: str, tenant: str | None = None) -> int:
        """读取当前已应用版本。

        Args:
            scope: 收敛域键。
            tenant: 租户标识；None 表示全局。

        Returns:
            int: 已应用版本；无记录返回 0。
        """

    @abstractmethod
    async def mark_applied(self, *, scope: str, version: int, tenant: str | None = None) -> None:
        """推进已应用版本（收敛点 / 消费方在副作用落库后调用；单调不回退）。

        Args:
            scope: 收敛域键。
            version: 本次已应用的版本。
            tenant: 租户标识；None 表示全局。
        """


def get_consistency_barrier(request: Request) -> BaseConsistencyBarrier:
    """取应用级一致性屏障（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseConsistencyBarrier: 应用装配的一致性屏障实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseConsistencyBarrier",
        resolve_plugin(
            "consistency_barrier",
            settings.consistency_barrier.provider,
            expected_version=BaseConsistencyBarrier.contract_version,
        ),
    )

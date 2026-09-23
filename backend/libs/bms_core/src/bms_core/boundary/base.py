"""数据所有权边界守卫能力域契约（`key = plugin_key = "data_ownership_guard"`）。

- `OWNERSHIP_MODES` / `DEFAULT_OWNERSHIP_MODE`：运行模式（`off` 不检测 / `warn` 记录计数 / `enforce` 阻断）。
- `BOUNDARY_METRIC_CROSS_ACCESS`：跨库访问计数指标名（经 `metrics` 能力域上报）。
- `OwnershipViolation`：越界数据契约（复用 `assess` 定义）。
- `OwnershipStats`：守卫计数快照（触及语句 / 越界 / 阻断）。
- `BaseDataOwnershipGuard`：能力域中间层契约——同步 `assess`（在 SQL 执行前调用）+ `snapshot`。
- `get_data_ownership_guard`：依赖注入提供者（按 `[data_ownership].provider` 解析）。

口径：基座只**判定与计数 / 阻断**，不持有连接、不改写 SQL；具体 SQL 解析与归属判定复用
`bms_core/boundary/{sql,assess}.py`（与静态硬校验同源）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.boundary.assess import OwnershipViolation
from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "BOUNDARY_METRIC_CROSS_ACCESS",
    "DEFAULT_OWNERSHIP_MODE",
    "OWNERSHIP_MODES",
    "BaseDataOwnershipGuard",
    "OwnershipStats",
    "OwnershipViolation",
    "get_data_ownership_guard",
]

OWNERSHIP_MODES: tuple[str, ...] = ("off", "warn", "enforce")
"""运行模式：`off` 不检测 / `warn` 记录 + 计数 + 告警 / `enforce` 越界阻断。"""

DEFAULT_OWNERSHIP_MODE = "warn"
"""默认运行模式（渐进治理：先可观测，边界稳定后再按需切 `enforce`）。"""

BOUNDARY_METRIC_CROSS_ACCESS = "bms_boundary_cross_access_total"
"""跨库访问计数指标名（经 `metrics` 能力域上报；缺省 null 实现时空操作）。"""


@dataclass(frozen=True)
class OwnershipStats(BaseObject):
    """守卫计数快照。"""

    statements: int = 0
    """已检测语句数。"""

    violations: int = 0
    """命中的越界数（含 `enforce` 阻断）。"""

    blocked: int = 0
    """被阻断（抛错）的越界数。"""


class BaseDataOwnershipGuard(BasePluggable, ABC):
    """数据所有权守卫契约：SQL 执行前的同步越界判定与计数。"""

    key: str = "data_ownership_guard"
    plugin_key: str = "data_ownership_guard"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def assess(self, statement: str, *, service: str) -> tuple[OwnershipViolation, ...]:
        """判定语句是否越界访问他服务表（不抛错，由调用方按模式处置）。

        Args:
            statement: SQL 语句。
            service: 当前服务标识。

        Returns:
            tuple[OwnershipViolation, ...]: 越界项（无越界返回空元组）。
        """

    @abstractmethod
    def snapshot(self) -> OwnershipStats:
        """取计数快照。

        Returns:
            OwnershipStats: 计数快照。
        """


def get_data_ownership_guard(request: Request) -> BaseDataOwnershipGuard:
    """取应用级数据所有权守卫（依赖注入提供者）。

    Args:
        request: 应用请求（取装配 settings）。

    Returns:
        BaseDataOwnershipGuard: 应用装配的守卫实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseDataOwnershipGuard",
        resolve_plugin(
            "data_ownership_guard",
            settings.data_ownership.provider,
            expected_version=BaseDataOwnershipGuard.contract_version,
        ),
    )

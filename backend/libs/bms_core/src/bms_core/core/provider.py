"""core 层提供者契约与注册表：注册项公共契约 + 跨域注册表公共实现。

- `BaseProvider`：注册项公共契约（抽象 `key` + 抽象 `describe` 元信息）；继承 `BaseCapability`
  而**不继承** `BasePluggable`——提供者走**组合轨**（域注册表 / `register_plugin` 显式登记），
  不进入继承自动登记（边界护栏见 `tests/crosscut/test_provider_contracts.py`）。
- `BaseProviderRegistry[ItemT]`：跨域注册表公共实现（登记唯一性拒重、`get` 未命中返回 `None`、
  `keys` / `values` 保序）；聚合模板（校验 / 查询 / 聚合等）留在各能力域。
- 注册项键由各域以 `_provider_key` 钩子声明（统一取 `provider.key`；健康检查项键经 `name` 别名兼容）。

`BaseProviderRegistry` 自 `app/core/registry.py` 归位本模块（03-2）；过渡导出模块已于 05 清理删除。
"""

from abc import ABC, abstractmethod

from bms_core.core.capability import BaseCapability
from bms_core.core.exceptions import ConflictError
from bms_core.core.plugin import BasePluggable

__all__ = ["BaseProvider", "BaseProviderRegistry"]


class BaseProvider(BaseCapability, ABC):
    """注册项公共契约：键 + 元信息。"""

    @property
    @abstractmethod
    def key(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
        """注册项键（域内唯一；域注册表以 key 解析）。"""

    @abstractmethod
    def describe(self) -> str:
        """元信息描述（供清单 / 日志 / 文档对齐；实现类强制提供）。"""


class BaseProviderRegistry[ItemT](BasePluggable, ABC):
    """提供者注册表中间层：唯一性登记 + 未命中语义 + `keys` / `values` 公共实现。"""

    key: str = "provider_registry"

    def __init__(self) -> None:
        """初始化空注册表（登记保序）。"""
        self._providers: dict[str, ItemT] = {}

    @classmethod
    @abstractmethod
    def _provider_key(cls, provider: ItemT) -> str:
        """注册项键（各域注册表覆写，统一取 `provider.key`）。

        Args:
            provider: 注册项。

        Returns:
            str: 注册项键。
        """

    def register(self, provider: ItemT) -> None:
        """登记提供者（重复键拒重，不静默覆盖）。

        Args:
            provider: 注册项。

        Raises:
            ConflictError: 键已登记（10003）。
        """
        item_key = self._provider_key(provider)
        if item_key in self._providers:
            raise ConflictError(f"{self.key} 重复登记：{item_key}")
        self._providers[item_key] = provider

    def get(self, key: str) -> ItemT | None:
        """按 key 取提供者（未命中返回 `None`）。

        Args:
            key: 注册项键。

        Returns:
            ItemT | None: 提供者；未命中为 None。
        """
        return self._providers.get(key)

    def keys(self) -> tuple[str, ...]:
        """已登记键（注册顺序）。

        Returns:
            tuple[str, ...]: 键元组。
        """
        return tuple(self._providers)

    def values(self) -> tuple[ItemT, ...]:
        """已登记提供者（注册顺序）。

        Returns:
            tuple[ItemT, ...]: 提供者元组。
        """
        return tuple(self._providers.values())

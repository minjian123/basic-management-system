"""core 层提供者注册表中间层：唯一性登记 / 未命中语义 / keys 公共实现。

- `BaseProviderRegistry[ItemT]`：跨域注册表公共实现（登记唯一性拒重、`get` 未命中返回 `None`、
  `keys` / `values` 保序）；聚合模板（校验 / 查询 / 聚合等）留在各能力域。
- 注册项键由各域以 `_provider_key` 钩子声明（如 `provider.key` / `check.name`）。

供能力域注册表继承（健康检查项注册表已接入；字段类型 / 查询提供者 / 仪表盘卡片注册表
随域三 03-3 收敛）。
"""

from abc import ABC, abstractmethod

from app.core.exceptions import ConflictError
from app.core.plugin import BasePluggable

__all__ = ["BaseProviderRegistry"]


class BaseProviderRegistry[ItemT](BasePluggable, ABC):
    """提供者注册表中间层：唯一性登记 + 未命中语义 + `keys` / `values` 公共实现。"""

    key: str = "provider_registry"

    def __init__(self) -> None:
        """初始化空注册表（登记保序）。"""
        self._providers: dict[str, ItemT] = {}

    @classmethod
    @abstractmethod
    def _provider_key(cls, provider: ItemT) -> str:
        """注册项键（各域注册表覆写，如 `provider.key` / `check.name`）。

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

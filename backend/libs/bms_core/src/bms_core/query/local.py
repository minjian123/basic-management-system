"""查询提供者注册表真实实现（插件名 `local`）：登记与聚合查询（模板继承基类）。

- 契约面见 `app/query/base.py`（`BaseQueryProvider` / `BaseQueryProviderRegistry`，02-4-9 交付）。
- 内建提供者由装配工厂注册（`app/dict/providers.py` 的字典条目示例提供者）；未注册 provider 查询抛
  `NotFoundError`（10002 / 404，基类模板统一处置）。
"""

from bms_core.query.base import BaseQueryProvider, BaseQueryProviderRegistry

__all__ = ["LocalQueryProviderRegistry"]


class LocalQueryProviderRegistry(BaseQueryProviderRegistry):
    """真实查询提供者注册表（登记保序、唯一性拒重；`query` 走基类模板）。"""

    @classmethod
    def _provider_key(cls, provider: BaseQueryProvider) -> str:
        """注册项键：提供者 `key`。

        Args:
            provider: 查询提供者。

        Returns:
            str: 提供者标识。
        """
        return provider.key

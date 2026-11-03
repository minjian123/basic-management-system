"""语言清单能力域缺省实现（Null Object）：固定返回种子清单，不读库、不读缓存。"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.i18n.locale import LocaleInfo
from bms_core.i18n.registry import BaseLocaleRegistry, seed_locale_infos

__all__ = ["NullLocaleRegistry"]


class NullLocaleRegistry(BaseLocaleRegistry, BaseNullObject):
    """占位语言清单：种子语言（`zh-CN` 默认 / `en-US`），RTL 恒否。"""

    async def list_locales(self, *, enabled_only: bool = False) -> ConcurrentStableList[LocaleInfo]:
        """返回种子清单。

        Args:
            enabled_only: 是否只返回启用语言（种子全部启用，等价）。

        Returns:
            ConcurrentStableList[LocaleInfo]: 种子清单条目。
        """
        del enabled_only  # 种子清单全部启用，无需过滤
        return seed_locale_infos()

    async def refresh(self) -> None:
        """把快照重置为种子清单（无 IO）。"""
        self._replace_snapshot(seed_locale_infos())

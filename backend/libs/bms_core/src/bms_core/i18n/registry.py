"""语言清单能力域（`locale_registry`）：清单查询 / 默认语言 / RTL / 语言解析。

- 契约（`BaseLocaleRegistry`）：异步方法读清单（缓存 / 库），**同步方法读进程内快照**——`BaseTranslator`
  的 `resolve_locale`、请求语言依赖与字典失效遍历都在同步路径上，不能为取清单引入 IO。
- 快照由 `refresh()` 原子替换（装配期一次、写路径后一次、失效端点一次）；跨实例一致性由缓存版本号 +
  各实例下次刷新保证；快照为空时一律回退 `DEFAULT_LOCALE` / 种子清单，不抛错。
- 种子清单（`SEED_LOCALES`）是**出厂兜底**：无库环境、契约测试、快照未加载时都用它。
"""

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.i18n.locale import LOCALE_DISABLED, LOCALE_ENABLED, LocaleInfo, match_locale

__all__ = [
    "SEED_DEFAULT_LOCALE",
    "SEED_LOCALES",
    "BaseLocaleRegistry",
    "get_locale_registry",
    "seed_locale_infos",
]

SEED_DEFAULT_LOCALE = DEFAULT_LOCALE
"""出厂默认语言（与 `SUPPORTED_LOCALES` 的首项一致）。"""

SEED_LOCALES: ConcurrentStableList[tuple[str, str, bool, bool, int]] = ConcurrentStableList(
    (
        ("zh-CN", "简体中文", False, True, 0),
        ("en-US", "English", False, False, 10),
    )
)
"""种子语言清单：`(code, name, rtl, is_default, sort)`（平台默认，随种子下发到各租户库）。"""


def seed_locale_infos() -> ConcurrentStableList[LocaleInfo]:
    """构造种子语言清单值对象（每次返回新实例，供快照替换）。

    Returns:
        ConcurrentStableList[LocaleInfo]: 种子清单条目。
    """
    return ConcurrentStableList(
        LocaleInfo(
            code=code,
            name=name,
            rtl=rtl,
            is_default=is_default,
            status=LOCALE_ENABLED,
            sort=sort,
        )
        for code, name, rtl, is_default, sort in SEED_LOCALES
    )


class BaseLocaleRegistry(BasePluggable, ABC):
    """语言清单契约：清单查询（异步）+ 语言解析（同步快照）。"""

    key: str = "locale_registry"
    plugin_key: str = "locale_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self) -> None:
        """初始化空快照（首个 `refresh()` 前回退种子 / 默认语言）。"""
        self._snapshot: ConcurrentStableList[LocaleInfo] = ConcurrentStableList()
        self._default: str = SEED_DEFAULT_LOCALE

    @abstractmethod
    async def list_locales(self, *, enabled_only: bool = False) -> ConcurrentStableList[LocaleInfo]:
        """查询语言清单（实现侧走缓存 / 库）。

        Args:
            enabled_only: 是否只返回启用语言。

        Returns:
            ConcurrentStableList[LocaleInfo]: 清单条目（按 `sort` 升序）。
        """

    @abstractmethod
    async def refresh(self) -> None:
        """强制回源并替换进程内快照（装配期与写路径后调用）。"""

    def snapshot(self) -> ConcurrentStableList[LocaleInfo]:
        """取进程内快照（不可变副本；空快照回退种子清单）。

        Returns:
            ConcurrentStableList[LocaleInfo]: 清单条目。
        """
        if not self._snapshot:
            return seed_locale_infos()
        return ConcurrentStableList(self._snapshot)

    def default_locale(self) -> str:
        """取系统默认语言（快照标记；无标记回退种子默认语言）。

        Returns:
            str: 默认语言标识。
        """
        return self._default or SEED_DEFAULT_LOCALE

    def is_rtl(self, locale: str) -> bool:
        """判定语言是否为 RTL（快照；未知语言按非 RTL）。

        Args:
            locale: 语言标识。

        Returns:
            bool: RTL 为 True。
        """
        target = (locale or "").strip().lower()
        for item in self.snapshot():
            if item.code.lower() == target:
                return item.rtl
        return False

    def resolve_locale(self, accept_language: str | None = None) -> str:
        """按 `Accept-Language` 解析语言（同步纯解析，无 IO）。

        Args:
            accept_language: 请求头原值（可空）。

        Returns:
            str: 命中语言（启用范围内）或默认语言。
        """
        enabled: ConcurrentStableList[str] = ConcurrentStableList(item.code for item in self.snapshot() if item.enabled)
        if not enabled:
            enabled = ConcurrentStableList(SUPPORTED_LOCALES)
        return match_locale(accept_language, enabled, self.default_locale())

    async def ensure_supported(self, locale: str | None) -> str:
        """归一语言：未登记 / 已停用回退默认语言（不抛错）。

        Args:
            locale: 待归一语言（可空）。

        Returns:
            str: 生效语言（清单原始形态）。
        """
        target = (locale or "").strip().lower()
        if target:
            for item in await self.list_locales(enabled_only=True):
                if item.code.lower() == target:
                    return item.code
        return self.default_locale()

    def _replace_snapshot(self, locales: ConcurrentStableList[LocaleInfo]) -> None:
        """替换进程内快照并重算默认语言（实现侧在回源后调用）。

        Args:
            locales: 回源的完整清单（含停用）。
        """
        ordered: ConcurrentStableList[LocaleInfo] = ConcurrentStableList()
        for item in sorted(locales, key=lambda row: (row.sort, row.code.lower())):
            ordered.add(replace(item, status=item.status or LOCALE_ENABLED))
        self._snapshot = ordered
        default = next((item.code for item in ordered if item.is_default), "")
        if not default:
            default = next((item.code for item in ordered if item.status != LOCALE_DISABLED), "")
        self._default = default or SEED_DEFAULT_LOCALE


def get_locale_registry(request: Request) -> BaseLocaleRegistry:
    """依赖注入提供者（应用级单例；公共依赖经 `bms_core.api.deps` 统一导出）。

    Args:
        request: 请求对象（取装配 settings）。

    Returns:
        BaseLocaleRegistry: 应用装配的语言清单实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseLocaleRegistry",
        resolve_plugin(
            "locale_registry",
            settings.locale_registry.provider,
            expected_version=BaseLocaleRegistry.contract_version,
        ),
    )

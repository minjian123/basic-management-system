"""i18n：国际化能力域（翻译 / 语言清单 / 语言包缓存三个契约与占位实现）。

**导入即登记**：本模块在导入期显式加载 `null` 模块，使三个 Null 实现（`NullTranslator` /
`NullI18nCacheRegion` / `NullLocaleRegistry`）在任何 `import bms_core.i18n.*` 时就完成
`BasePluggable` 自动登记——早于插件注册表构建。否则在「先构建注册表、后调
`register_platform_plugins`」的服务里（该函数遇已构建即提前返回），`.null` 模块永不导入，
`locale_registry` 等端口会因找不到缺省实现而在装配期抛 `KeyError` 并导致服务拒启。
"""

from bms_core.i18n import null as _null  # noqa: F401  # pyright: ignore[reportUnusedImport]  导入即登记（见模块 docstring）

__all__ = []

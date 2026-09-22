"""文件服务测试支撑：离线全量装配快照构建（不进入 lifespan）。"""

from collections.abc import Mapping
from typing import cast

from bms_core.core.assembly import register_platform_plugins
from bms_core.core.config import Settings
from bms_core.core.plugin import PluginImpl, build_plugin_registry
from bms_file.main import ApplicationFactory


def build_snapshot() -> Mapping[str, Mapping[str, PluginImpl]]:
    """构建离线全量装配快照（应用工厂 → 平台实现登记 → 注册表构建；不进入 lifespan）。

    Returns:
        Mapping[str, Mapping[str, PluginImpl]]: 两级映射快照。
    """
    app = ApplicationFactory().create(None)
    settings = cast("Settings", app.state.settings)
    register_platform_plugins(settings, app, app.state.resources)
    return build_plugin_registry()

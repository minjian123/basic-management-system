"""文件服务测试支撑：离线全量装配快照构建（不进入 lifespan）。"""

from typing import cast

from bms_core.core.assembly import register_platform_plugins
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.plugin import PluginImpl, build_plugin_registry
from bms_file.main import ApplicationFactory


def build_snapshot() -> ConcurrentStableDict[str, ConcurrentStableDict[str, PluginImpl]]:
    """构建离线全量装配快照（应用工厂 → 平台实现登记 → 注册表构建；不进入 lifespan）。

    Returns:
        ConcurrentStableDict[str, ConcurrentStableDict[str, PluginImpl]]: 两级映射快照。
    """
    app = ApplicationFactory().create(None)
    settings = cast("Settings", app.state.settings)
    # DIAG(临时·CI 取证，定位后删除)
    if settings.permission.provider:
        print(
            f"[DIAG-permission] stage=build-snapshot provider={settings.permission.provider!r} "
            f"app_env={settings.app.env!r} settings_id={id(settings)}"
        )
    register_platform_plugins(settings, app, app.state.resources)
    return build_plugin_registry()

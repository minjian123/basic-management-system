"""自建应用壳用例的收尾助手：把进程级插件注册表归还给装配态应用。

装配常驻（13_10）后全系统应用在会话级只建一次，进程级插件注册表由**第一个**装配的应用登记。
用例若为「启动失败分支」自建应用壳（`ApplicationFactory().create()`），注册表会换代到该壳
（工厂闭包持有壳的 `app.state`），后继用例解析插件即读不到槽位。用例收尾调用本助手重建，
把归属还给装配态应用。

口径：自建壳只用于**装配失败分支 / 破坏性全局操作**，业务语义用例一律复用装配实例。
"""

from __future__ import annotations

from fastapi import FastAPI

from bms_core.core.assembly import register_platform_plugins
from bms_core.core.plugin import default_plugin_registry

__all__ = ["restore_registry_for"]


def restore_registry_for(app: FastAPI) -> None:
    """把默认插件注册表重建到指定应用名下。

    Args:
        app: 装配态应用实例（收尾时归还给它的 `settings` 与 `resources`）。
    """
    registry = default_plugin_registry()
    registry.reset()
    register_platform_plugins(app.state.settings, app, app.state.resources)

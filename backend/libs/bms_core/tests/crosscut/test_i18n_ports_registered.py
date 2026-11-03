"""i18n 能力域端口登记冒烟（启动级）：注册表快照必须自带三个端口的缺省实现。

**为什么不 import `bms_core.i18n`**：服务启动的真实顺序是「构建插件注册表 → 装配能力」，
若 `.null` 模块要等到装配期才被导入，`NullLocaleRegistry` 就赶不上收集，`resolve_plugin`
会在装配阶段抛 `KeyError` 并使服务拒启（`services/file` 实测）。

本用例刻意**不**提前导入 i18n 包，只取全局快照——这样它拦的正是「依赖导入顺序」的缺陷，
而不是被测试文件自己的 import 洗白。
"""

from __future__ import annotations

import pytest

from bms_core.core.plugin import NULL_PLUGIN_NAME, plugin_registry_snapshot

pytestmark = [pytest.mark.kiwi_id(2404)]

_REQUIRED_PORTS = ("translator", "locale_registry", "i18n_cache_region")
"""i18n 能力域三个端口（新增端口必须同时扩本清单）。"""


@pytest.mark.parametrize("port", _REQUIRED_PORTS)
def test_i18n_port_has_null_impl(port: str) -> None:
    """每个端口在未显式导入 i18n 包时也应已登记 `null` 实现。

    Args:
        port: 端口标识（`plugin_key`）。
    """
    snapshot = plugin_registry_snapshot()
    assert port in snapshot, f"端口未登记：{port}（缺省实现未在注册表构建前被收集）"
    assert NULL_PLUGIN_NAME in snapshot[port], f"端口缺 `{NULL_PLUGIN_NAME}` 实现：{port}"

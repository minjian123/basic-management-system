"""pytest 插件入口（13_04）：经 `addopts = "-p bms_core.testing.plugin"` 全局加载。

为什么不用各 conftest 写 `pytest_plugins`：pytest 7+ 禁止**非顶层 conftest** 声明
`pytest_plugins`，而本项目有 10 个测试根（每个工程一个 conftest），故统一由 `-p` 加载。

注意：`pytest_plugins` 在「由 `-p` 加载的插件模块」中**不会**再被处理（该机制只对 conftest 生效），
故这里的夹具必须显式导入到本模块命名空间，pytest 才会收集注册。
"""

from bms_core.testing.fixtures import (
    clear_tenant_cache,
    isolate_settings,
    platform_db,
    reset_plugin_registry,
    reset_request_context,
)

__all__ = (
    "clear_tenant_cache",
    "isolate_settings",
    "platform_db",
    "reset_plugin_registry",
    "reset_request_context",
)

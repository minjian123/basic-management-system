"""装配常驻的依赖提供者（Kiwi 2283）：优先取应用装配实例，未装配时回退插件解析。

装配常驻后，服务持有的是**装配期**实例（`app.state.<能力>`）；依赖提供者若每次请求重新
`resolve_plugin`，在插件注册表被复位的测试环境里会解析出第二个实例，缓存失效 / 版本递增
就失效在不同的对象上（i18n 下发、菜单元数据实测）。本文件锁住「同源取实例 + 回退」两条分支。

用例只用**自带最小应用壳**（不经全系统装配），因此以普通命名空间承载应用状态，不改装配结果。
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from bms_core.cache.base import CacheRegion, get_cache_region
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.assembly import register_platform_plugins
from bms_core.core.config import Settings
from bms_core.core.plugin import default_plugin_registry
from bms_core.core.resources import ResourceManager
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.i18n.cache import I18nCacheRegion, MemoryI18nCacheRegion, get_i18n_cache_region
from bms_core.i18n.invalidate import I18nInvalidator, get_i18n_invalidator
from bms_core.i18n.registry import BaseLocaleRegistry

pytestmark = [pytest.mark.kiwi_id(2283)]


class _AppShell:
    """最小应用壳：只带 `state` 命名空间，供依赖提供者读取。"""

    def __init__(self, state: SimpleNamespace) -> None:
        """注入状态命名空间（不在用例里写装配态）。"""
        object.__setattr__(self, "state", state)


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    """解除插件注册表冻结（与全局测试夹具同口径）。

    Yields:
        None: 用例运行期。
    """
    default_plugin_registry().reset()
    try:
        yield
    finally:
        default_plugin_registry().reset()


def _request(app: object) -> Request:
    """构造只带 `app` 的最小请求（依赖提供者只读应用状态，不触 ASGI 链路）。"""
    return Request({"type": "http", "app": app, "headers": []})


def test_prefers_assembled_instances() -> None:
    """已装配：三个提供者都返回应用状态上的同一实例（不再重新解析）。"""
    settings = Settings()
    cache = MemoryCacheRegion()
    i18n_cache = MemoryI18nCacheRegion()
    app = _AppShell(SimpleNamespace(settings=settings, cache=cache, i18n_cache_region=i18n_cache))

    request = _request(app)

    assert get_cache_region(request) is cache
    assert get_i18n_cache_region(request) is i18n_cache
    invalidator = get_i18n_invalidator(request)
    assert isinstance(invalidator, I18nInvalidator)
    assert invalidator._cache is i18n_cache  # pyright: ignore[reportPrivateUsage]
    assert isinstance(invalidator._registry, BaseLocaleRegistry)  # pyright: ignore[reportPrivateUsage]


def test_falls_back_to_plugin_registry() -> None:
    """未装配（单测自带应用壳）：回退到插件解析，仍按配置 provider 取实例。"""
    settings = Settings()
    app = _AppShell(SimpleNamespace(settings=settings, engine_registry=EngineRegistry(EngineFactory(settings))))
    register_platform_plugins(settings, cast("FastAPI", app), ResourceManager())

    request = _request(app)

    assert isinstance(get_cache_region(request), CacheRegion)
    assert isinstance(get_i18n_cache_region(request), I18nCacheRegion)
    assert isinstance(get_i18n_invalidator(request), I18nInvalidator)

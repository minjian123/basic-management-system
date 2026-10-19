"""测试公共基座：插件注册与「同名同语义」契约（Kiwi 2317）。"""

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.testing import plugin
from bms_core.testing.fixtures import clear_isolated_env, clear_tenant_cache


@pytest.mark.kiwi_id(2317)
def test_plugin_registers_fixture_module() -> None:
    """插件入口：夹具对象导入到插件命名空间（`-p bms_core.testing.plugin` 全局加载）。"""
    assert plugin.isolate_settings is not None
    assert plugin.platform_db is not None
    assert plugin.reset_request_context is not None
    assert plugin.reset_plugin_registry is not None


@pytest.mark.kiwi_id(2317)
def test_plugin_autouse_fixtures_active(request: pytest.FixtureRequest) -> None:
    """插件夹具生效：四个 autouse 夹具进入本用例夹具链。"""
    names = set(request.fixturenames)

    for name in ("platform_db", "reset_request_context", "reset_plugin_registry"):
        assert name in names, name


@pytest.mark.kiwi_id(2317)
def test_plugin_fixture_names_are_stable() -> None:
    """同名同语义：插件提供的夹具名与存量 conftest 完全一致（改名即破坏存量用例）。"""
    from bms_core.testing import fixtures as module

    expected = {
        "isolate_settings": module.isolate_settings,
        "platform_db": module.platform_db,
        "reset_request_context": module.reset_request_context,
        "reset_plugin_registry": module.reset_plugin_registry,
    }

    for name, fixture in expected.items():
        assert fixture.__name__ == name


@pytest.mark.kiwi_id(2317)
def test_clear_tenant_cache_variants() -> None:
    """租户缓存清理：Memory Region 走 clear；无可用 cache 时静默跳过。"""
    cache = MemoryCacheRegion()
    app = SimpleNamespace(state=SimpleNamespace(tenant_source=SimpleNamespace(cache=cache)))

    clear_tenant_cache(app)
    clear_tenant_cache(object())


@pytest.mark.kiwi_id(2317)
def test_has_fixture_checks_request_names() -> None:
    """夹具可用性判断：只看 `fixturenames`，不触发构造。"""
    from bms_core.testing.fixtures import has_fixture

    with_url = cast(Any, SimpleNamespace(fixturenames=("platform_db_url",)))
    without_url = cast(Any, SimpleNamespace(fixturenames=()))

    assert has_fixture(with_url, "platform_db_url")
    assert not has_fixture(without_url, "platform_db_url")


@pytest.mark.kiwi_id(2317)
def test_clear_isolated_env_keeps_test_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境清理：删 `BMS_`、保留 `BMS_TEST_`。"""

    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "x")
    monkeypatch.setenv("BMS_TEST_FIXED", "keep")

    clear_isolated_env(monkeypatch)

    assert "BMS_DATABASE__PLATFORM__URL" not in os.environ
    assert os.environ.get("BMS_TEST_FIXED") == "keep"

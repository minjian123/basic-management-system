"""测试公共基座：插件注册与「同名同语义」契约（Kiwi 2317）。"""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableList
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
def test_platform_db_fixture_skips_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """平台库夹具在无 `platform_db_url` 时直接结束（不进 setup 注入）。"""
    from bms_core.testing import fixtures

    class _NoUrl:
        """无平台库的假请求：任何夹具都解析为空。"""

        def getfixturevalue(self, name: str) -> None:
            """固定返回 None（模拟套件未提供夹具）。

            Args:
                name: 夹具名（忽略）。

            Returns:
                None: 固定 None。
            """
            return None

    func = cast(Any, fixtures.platform_db).__wrapped__
    generator = func(None, _NoUrl(), monkeypatch)
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)


@pytest.mark.kiwi_id(2317)
def test_apply_platform_db_skips_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """无平台库的套件：不注入 URL、返回 False；有则注入并重置配置单例。"""
    from bms_core.testing.fixtures import apply_platform_db

    assert apply_platform_db(None, monkeypatch) is False
    assert apply_platform_db("sqlite+aiosqlite:///tmp/app.db", monkeypatch) is True
    assert os.environ["BMS_DATABASE__PLATFORM__URL"] == "sqlite+aiosqlite:///tmp/app.db"


@pytest.mark.kiwi_id(2317)
def test_resolve_fixture_handles_missing(request: pytest.FixtureRequest) -> None:
    """夹具解析：存在则返回其值；套件未提供时返回 None 而不抛错（平台库夹具的跳过分支）。"""
    from bms_core.testing.fixtures import resolve_fixture

    assert resolve_fixture(request, "definitely_missing_fixture_xyz") is None
    assert resolve_fixture(request, "tmp_path") is not None


@pytest.mark.kiwi_id(2317)
def test_clear_isolated_env_keeps_test_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境清理：删 `BMS_`、保留 `BMS_TEST_`。"""

    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", "x")
    monkeypatch.setenv("BMS_TEST_FIXED", "keep")

    clear_isolated_env(monkeypatch)

    assert "BMS_DATABASE__PLATFORM__URL" not in os.environ
    assert os.environ.get("BMS_TEST_FIXED") == "keep"


@pytest.mark.kiwi_id(2317)
def test_configure_creates_basetemp_parent(tmp_path: Path) -> None:
    """`pytest_configure` 补齐 `--basetemp` 父目录（pytest 只 mkdir 末级、不递归建父目录）。

    背景：`addopts` 里的 `--basetemp=.cache/pytest` 指向仓内缓存目录，父目录 `.cache`
    不存在时 xdist 起 worker 即 `FileNotFoundError` 崩掉。
    """
    basetemp: Path = tmp_path / "nested" / "pytest"
    config = cast(Any, SimpleNamespace(option=SimpleNamespace(basetemp=str(basetemp))))

    plugin.pytest_configure(config)

    assert basetemp.parent.is_dir()


@pytest.mark.kiwi_id(2317)
def test_configure_without_basetemp_skips_makedirs(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设 `--basetemp` 时不建目录（仅把空基址交给测试基座）。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def record(value: str) -> None:
        """记录交给测试基座的基址。

        Args:
            value: basetemp 基址。
        """
        seen.append(value)

    monkeypatch.setattr(plugin.fixtures, "configure_sqlite_basetemp", record)

    plugin.pytest_configure(cast(Any, SimpleNamespace(option=SimpleNamespace(basetemp=""))))

    assert list(seen) == [""]

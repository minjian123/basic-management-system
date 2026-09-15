"""提供者经 resolve_plugin 与健康注册表插件化测试（Kiwi 535）。"""

import ast
import importlib
import pkgutil
import re
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

import app as app_pkg
from app.core import plugin as plugin_module
from app.core.base import BaseObject
from app.core.config import PluginSelection, Settings
from app.core.exceptions import ConflictError
from app.core.plugin import BasePluggable, PluginRegistry, plugin_registry_snapshot, resolve_plugin
from app.core.registry import BaseProviderRegistry
from app.health.base import BaseHealthCheck, BaseHealthCheckRegistry, HealthCheckResult
from app.health.registry import HealthCheckRegistry
from app.main import create_app, lifespan
from app.storage.base import BaseObjectStorage, get_object_storage
from app.storage.null import NullObjectStorage

_BACKEND = Path(__file__).resolve().parents[2]


def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """导入 app 全量模块并把应用侧插件子类收集进隔离注册表（替换进程级默认实例）。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        PluginRegistry: 隔离注册表。
    """
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)
    registry = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    pending = list(BasePluggable.__subclasses__())
    while pending:
        cls = pending.pop()
        if cls.__module__.startswith("app."):
            registry.collect(cls)
        pending.extend(cls.__subclasses__())
    return registry


class _NamedCheck(BaseHealthCheck):
    """测试用检查项。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def key(self) -> str:
        return self._name

    def describe(self) -> str:
        return f"测试检查项 {self._name}"

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(name=self._name, ok=True)


@pytest.mark.kiwi_id(565)
async def test_provider_resolves_from_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """提供者经注册表解析：路由依赖与 `resolve_plugin` / `app.state` 取到同一实例。"""
    _isolated_registry(monkeypatch)
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(storage=PluginSelection(provider="")))
    app = create_app()

    @app.get("/storage-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        storage: Annotated[BaseObjectStorage, Depends(get_object_storage)],
    ) -> dict[str, str]:
        return {"type": type(storage).__name__}

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/storage-probe")
        assert resp.json() == {"type": "NullObjectStorage"}
        assert isinstance(app.state.object_storage, NullObjectStorage)
        assert resolve_plugin("object_storage", "") is app.state.object_storage


@pytest.mark.kiwi_id(565)
async def test_config_switch_with_no_consumer_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置切换零改动：`storage.provider=custom` 后既有路由（消费方代码未改）返回自定义实现。"""

    class CustomStorage(BaseObject):
        """测试用对象存储实现。"""

        contract_version = "0.1.0"

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "custom", lambda: CustomStorage())
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(storage=PluginSelection(provider="custom")))
    app = create_app()

    @app.get("/storage-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        storage: Annotated[BaseObjectStorage, Depends(get_object_storage)],
    ) -> dict[str, str]:
        return {"type": type(storage).__name__}

    async with lifespan(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/storage-probe")
        assert resp.json() == {"type": "CustomStorage"}
        assert isinstance(app.state.object_storage, CustomStorage)


@pytest.mark.kiwi_id(565)
async def test_health_registry_pluginized() -> None:
    """健康注册表插件化：`local` 真实探针接入 `/readyz`；`null` 缺省仍登记；解析同实例。"""
    app = create_app()
    async with lifespan(app):
        registry = app.state.health_check_registry
        assert isinstance(registry, HealthCheckRegistry)
        assert registry.keys() == ("redis", "database")
        assert (
            resolve_plugin(
                "health_check_registry",
                "local",
                expected_version=BaseHealthCheckRegistry.contract_version,
            )
            is registry
        )
        snapshot = plugin_registry_snapshot()
        assert set(snapshot["health_check_registry"]) == {"local", "null"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/readyz")
        assert set(resp.json()["checks"]) == {"redis", "database"}


@pytest.mark.kiwi_id(565)
def test_provider_registry_base_semantics() -> None:
    """基类语义：重名拒重（`ConflictError`）/ 未命中 `None` / `keys` 保序 / `values` 对应。"""
    registry = HealthCheckRegistry()
    assert isinstance(registry, BaseProviderRegistry)
    first = _NamedCheck("redis")
    second = _NamedCheck("database")
    registry.register(first)
    registry.register(second)
    assert registry.keys() == ("redis", "database")
    assert registry.values() == (first, second)
    assert registry.get("redis") is first
    assert registry.get("missing") is None
    with pytest.raises(ConflictError, match="重复登记"):
        registry.register(_NamedCheck("redis"))


@pytest.mark.kiwi_id(565)
def test_providers_have_no_direct_state_bypass() -> None:
    """直连残留护栏：能力域提供者均经 `resolve_plugin`，且不再直读 `app.state.<能力属性>`。"""
    offenders: list[str] = []
    checked = 0
    for path in sorted((_BACKEND / "app").rglob("*.py")):
        if any(part in {"api", "db", "core"} for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("get_"):
                continue
            argument_names = [argument.arg for argument in node.args.args]
            if "request" not in argument_names:
                continue
            checked += 1
            segment = ast.get_source_segment(source, node) or ""
            bypass = re.search(r"app\.state\.(?!settings)", segment) is not None
            if "resolve_plugin(" not in segment or bypass:
                offenders.append(f"{path.relative_to(_BACKEND)}::{node.name}")
    assert checked >= 34
    assert not offenders, offenders

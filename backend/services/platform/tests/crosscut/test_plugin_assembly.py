"""插件配置分区与启动装配测试（Kiwi 533）：默认装配 / 配置切换 / 依赖注入 / 缓存 / 生命周期 / 日志。"""

import importlib
import pkgutil
from typing import cast

import pytest

import bms_core as app_pkg
from bms_core.core import plugin as plugin_module
from bms_core.core.base import BaseObject
from bms_core.core.config import LogSettings, PluginSelection, Settings
from bms_core.core.logging import configure_logging
from bms_core.core.plugin import BasePluggable, PluginRegistry, resolve_plugin
from bms_core.health.registry import HealthCheckRegistry
from bms_core.masking.null import NullMasker
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker
from bms_core.storage.local import LocalObjectStorage
from bms_platform.main import ApplicationFactory, lifespan


def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """导入 app 全量模块并把应用侧插件子类收集进隔离注册表（替换进程级默认实例）。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        PluginRegistry: 隔离注册表。
    """
    for info in pkgutil.walk_packages(app_pkg.__path__, prefix="bms_core."):
        if ".tests" in info.name or info.name.endswith("main"):
            continue
        importlib.import_module(info.name)
    registry = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    pending = list(BasePluggable.__subclasses__())
    while pending:
        cls = pending.pop()
        if cls.__module__.startswith("bms_core."):
            registry.collect(cls)
        pending.extend(cls.__subclasses__())
    return registry


@pytest.mark.kiwi_id(533)
async def test_default_assembly_wires_null_implementations() -> None:
    """默认装配：lifespan 后各能力 `app.state` 为配置实现（对象存储缺省 local，其余占位）。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.object_storage, LocalObjectStorage)
        assert isinstance(app.state.masker, NullMasker)
        assert isinstance(app.state.permission_checker, NullPermissionChecker)
        assert isinstance(app.state.health_check_registry, HealthCheckRegistry)
        assert resolve_plugin("object_storage", "local") is app.state.object_storage


@pytest.mark.kiwi_id(533)
async def test_config_switch_takes_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置切换：`storage.provider` 指向测试实现后装配随实现生效且缓存复用。"""

    class CustomStorage(BaseObject):
        """测试用对象存储实现（结构化路径）。"""

        contract_version = "0.1.0"

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "custom", lambda: CustomStorage())
    settings = Settings(storage=PluginSelection(provider="custom"))
    monkeypatch.setattr("bms_platform.main.get_settings", lambda: settings)
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.object_storage, CustomStorage)
        assert resolve_plugin("object_storage", "custom") is app.state.object_storage


@pytest.mark.kiwi_id(533)
async def test_masker_factory_injects_permission_checker(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入工厂：缺省掩码器拿到解析后的权限检查器（`check_plain` 行为可证）。"""

    class DenyChecker(BasePermissionChecker):
        """测试用拒绝式权限检查器。"""

        def check(self, code: str) -> bool:
            """恒定拒绝。

            Args:
                code: 权限码（忽略）。

            Returns:
                bool: False。
            """
            del code
            return False

    registry = _isolated_registry(monkeypatch)
    registry.register("permission", "deny", lambda: DenyChecker())
    settings = Settings(permission=PluginSelection(provider="deny"))
    monkeypatch.setattr("bms_platform.main.get_settings", lambda: settings)
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        masker = cast("NullMasker", app.state.masker)
        assert masker.check_plain() is False


@pytest.mark.kiwi_id(533)
async def test_setup_and_aclose_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """生命周期：装配调用 `setup()`；lifespan 退出后经 `ResourceManager` 触发 `aclose()`。"""
    calls = {"setup": 0, "closed": 0}

    class Probe(BasePluggable):
        """测试用插件实现（记录生命周期调用）。"""

        async def setup(self) -> None:
            """记录 setup。"""
            calls["setup"] += 1

        async def aclose(self) -> None:
            """记录释放。"""
            calls["closed"] += 1

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "probe", Probe)
    settings = Settings(storage=PluginSelection(provider="probe"))
    monkeypatch.setattr("bms_platform.main.get_settings", lambda: settings)
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert calls["setup"] == 1
        assert isinstance(app.state.object_storage, Probe)
    assert calls["closed"] == 1


@pytest.mark.kiwi_id(533)
async def test_startup_log_excludes_options(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """启动日志：含各能力 provider；`options` 值不出现在输出。"""
    settings = Settings(
        storage=PluginSelection(provider="", options={"secret_key": "top-secret"}),
    )
    monkeypatch.setattr("bms_platform.main.get_settings", lambda: settings)
    app = ApplicationFactory().create(None)
    configure_logging(Settings(log=LogSettings(level="INFO", format="json")))
    async with lifespan(app):
        pass
    out = capsys.readouterr().out
    assert "插件装配完成" in out
    assert "object_storage" in out
    assert "top-secret" not in out

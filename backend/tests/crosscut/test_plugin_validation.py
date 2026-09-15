"""启动校验与 CI 离线校验测试（Kiwi 534）：拒启路径 / 依赖隔离 / CI 脚本。"""

import importlib
import os
import pkgutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import app as app_pkg
from app.core import plugin as plugin_module
from app.core.base import BaseObject
from app.core.config import PluginSelection, Settings
from app.core.exceptions import PluginError
from app.core.plugin import BasePluggable, PluginRegistry
from app.main import create_app, lifespan

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


def _prepare_app(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    """以自定义配置装配应用（替换 `app.main.get_settings`）。

    Args:
        monkeypatch: pytest 补丁夹具。
        settings: 自定义配置。
    """
    monkeypatch.setattr("app.main.get_settings", lambda: settings)


@pytest.mark.kiwi_id(534)
async def test_illegal_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """非法 provider 拒启：lifespan 抛出 `PluginError`（含键与 provider）。"""
    _isolated_registry(monkeypatch)
    _prepare_app(monkeypatch, Settings(storage=PluginSelection(provider="ghost")))
    app = create_app()
    with pytest.raises(PluginError, match="未注册的 object_storage 实现：ghost"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(534)
async def test_contract_version_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """契约版本不符拒启：实现主版本与端口不一致。"""

    class BadVersionImpl(BaseObject):
        """测试用版本不兼容实现。"""

        contract_version = "2.0.0"

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "badver", lambda: BadVersionImpl())
    _prepare_app(monkeypatch, Settings(storage=PluginSelection(provider="badver")))
    app = create_app()
    with pytest.raises(PluginError, match="插件契约版本不兼容"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(534)
async def test_setup_failure_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖不可用拒启：`setup()` 抛错包装为 `PluginError`。"""

    class FailingSetupImpl(BaseObject):
        """测试用 setup 失败实现。"""

        contract_version = "0.1.0"

        async def setup(self) -> None:
            """模拟依赖不可达。"""
            raise RuntimeError("依赖不可达")

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "failing", lambda: FailingSetupImpl())
    _prepare_app(monkeypatch, Settings(storage=PluginSelection(provider="failing")))
    app = create_app()
    with pytest.raises(PluginError, match="插件 setup 失败"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(534)
async def test_factory_import_failure_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """实现依赖缺失拒启：工厂导入失败包装为 `PluginError`。"""

    def factory() -> object:
        """模拟延迟导入不存在模块。

        Returns:
            object: 不可达（先抛 ImportError）。
        """
        return importlib.import_module("app.no_such_plugin_module")

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "ghostimport", factory)
    _prepare_app(monkeypatch, Settings(storage=PluginSelection(provider="ghostimport")))
    app = create_app()
    with pytest.raises(PluginError, match="插件实例化失败"):
        async with lifespan(app):
            pass


@pytest.mark.kiwi_id(534)
async def test_unselected_factory_not_imported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """依赖隔离：未选中 provider 的工厂不被调用（探针模块不进 `sys.modules`）。"""
    probe = 'from app.core.base import BaseObject\n\n\nclass ProbeImpl(BaseObject):\n    contract_version = "0.1.0"\n'
    (tmp_path / "plugin_probe_used.py").write_text(probe, encoding="utf-8")
    (tmp_path / "plugin_probe_unused.py").write_text(probe, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]

    def make_factory(probe_name: str) -> Callable[[], object]:
        """构造导入指定探针模块的工厂。

        Args:
            probe_name: 探针模块名。

        Returns:
            Callable[[], object]: 零参工厂。
        """

        def factory() -> object:
            """导入探针模块并实例化。

            Returns:
                object: 探针实现实例。
            """
            module = importlib.import_module(probe_name)
            return module.ProbeImpl()

        return factory

    registry = _isolated_registry(monkeypatch)
    registry.register("object_storage", "used", make_factory("plugin_probe_used"))
    registry.register("object_storage", "unused", make_factory("plugin_probe_unused"))
    _prepare_app(monkeypatch, Settings(storage=PluginSelection(provider="used")))
    app = create_app()
    async with lifespan(app):
        assert "plugin_probe_used" in sys.modules
        assert "plugin_probe_unused" not in sys.modules


def _script_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """构造 CI 脚本子进程环境（剔除进程内 `BMS_` 残留）。

    Args:
        extra: 额外环境变量。

    Returns:
        dict[str, str]: 环境变量映射。
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("BMS_")}
    env.update(extra or {})
    return env


@pytest.mark.kiwi_id(534)
def test_check_plugins_script_passes() -> None:
    """CI 离线校验：默认配置通过（退出码 0）。"""
    result = subprocess.run(
        [sys.executable, "-m", "ops.check_plugins"],
        cwd=_BACKEND,
        env=_script_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[插件装配] 校验通过" in result.stdout


@pytest.mark.kiwi_id(534)
def test_check_plugins_script_rejects_illegal_provider() -> None:
    """CI 离线校验：非法 provider 拦截（退出码 1 + 明细）。"""
    result = subprocess.run(
        [sys.executable, "-m", "ops.check_plugins"],
        cwd=_BACKEND,
        env=_script_env({"BMS_STORAGE__PROVIDER": "ghost"}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ghost" in result.stdout

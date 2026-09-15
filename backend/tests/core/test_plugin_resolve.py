"""插件解析器与契约版本测试（Kiwi 530）：resolve / 实例缓存 / 缺省回退 / 版本兼容。"""

from abc import ABC, abstractmethod

import pytest

from app.core import plugin as plugin_module
from app.core.base import BaseObject
from app.core.capability import BaseNullObject
from app.core.config import Settings
from app.core.exceptions import PluginError
from app.core.logging import configure_logging
from app.core.plugin import (
    BasePluggable,
    PluginRegistry,
    resolve_plugin,
)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """隔离注册表：以独立实例替换进程级默认实例，用例内类定义不污染真实默认注册表。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        PluginRegistry: 隔离的注册表实例。
    """
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)
    return isolated


@pytest.mark.kiwi_id(530)
def test_resolve_reuses_single_instance(registry: PluginRegistry) -> None:
    """同 provider 复用唯一实例；不同键 / 实现名各自独立。"""

    class ImplA(BasePluggable):
        plugin_key = "test_resolve_a"
        plugin_name = "impl"

    class ImplB(BasePluggable):
        plugin_key = "test_resolve_b"
        plugin_name = "impl"

    first = registry.resolve("test_resolve_a", "impl")
    assert first is registry.resolve("test_resolve_a", "impl")
    assert isinstance(first, ImplA)
    assert isinstance(registry.resolve("test_resolve_b", "impl"), ImplB)
    assert first is not registry.resolve("test_resolve_b", "impl")


@pytest.mark.kiwi_id(530)
def test_resolve_null_fallback(registry: PluginRegistry) -> None:
    """缺省回退：`None` 与空串均解析到 `null` 登记实现（同实例复用）。"""

    class Port(BasePluggable, ABC):
        plugin_key = "test_resolve_null"

        @abstractmethod
        def work(self) -> None:
            """抽象能力方法。"""

    class NullPort(Port, BaseNullObject):
        def work(self) -> None:
            """空实现。"""

    assert isinstance(registry.resolve("test_resolve_null", None), NullPort)
    assert registry.resolve("test_resolve_null", "") is registry.resolve("test_resolve_null", None)


@pytest.mark.kiwi_id(530)
def test_resolve_unregistered_raises(registry: PluginRegistry) -> None:
    """未注册实现：`PluginError`（含键名与已注册实现名）。"""

    class Impl(BasePluggable):
        plugin_key = "test_resolve_known"
        plugin_name = "impl"

    assert Impl.plugin_name == "impl"
    with pytest.raises(PluginError, match="未注册的 test_resolve_known 实现：nope（已注册：impl）"):
        registry.resolve("test_resolve_known", "nope")
    with pytest.raises(PluginError, match="未注册的 test_ghost 实现"):
        registry.resolve("test_ghost", "impl")


@pytest.mark.kiwi_id(530)
def test_resolve_factory_cached(registry: PluginRegistry) -> None:
    """组合路径工厂：仅调用一次，结果缓存复用。"""
    calls: list[int] = []

    def factory() -> object:
        """零参工厂（结构化实现入口）。

        Returns:
            object: 实现实例。
        """
        calls.append(1)
        return BaseObject()

    registry.register("test_resolve_factory", "factory", factory)
    first = registry.resolve("test_resolve_factory", "factory")
    assert registry.resolve("test_resolve_factory", "factory") is first
    assert len(calls) == 1


@pytest.mark.kiwi_id(530)
def test_contract_version_compatible(registry: PluginRegistry) -> None:
    """版本兼容：主版本一致（minor / patch 差异）放行。"""

    class Impl(BasePluggable):
        plugin_key = "test_resolve_ver"
        plugin_name = "impl"
        contract_version = "0.9.3"

    instance = registry.resolve("test_resolve_ver", "impl", expected_version="0.1.0")
    assert isinstance(instance, Impl)


@pytest.mark.kiwi_id(530)
def test_contract_version_mismatch_rejected_and_logged(
    registry: PluginRegistry, capsys: pytest.CaptureFixture[str]
) -> None:
    """版本不兼容：告警日志 + `PluginError`（不缓存失败实例）。"""
    configure_logging(Settings())

    class Impl(BasePluggable):
        plugin_key = "test_resolve_bad_ver"
        plugin_name = "impl"
        contract_version = "2.0.0"

    with pytest.raises(PluginError, match="插件契约版本不兼容") as excinfo:
        registry.resolve("test_resolve_bad_ver", "impl", expected_version="0.1.0")
    out = capsys.readouterr().out
    assert "插件契约版本不兼容" in out
    assert "test_resolve_bad_ver" in out
    assert "2.0.0" in out
    assert "2" in str(excinfo.value)
    assert isinstance(Impl(), Impl)


@pytest.mark.kiwi_id(530)
def test_missing_contract_version_rejected(registry: PluginRegistry) -> None:
    """结构化实现缺失 `contract_version`：传期望版本即拒；未传则跳过。"""

    class Structural(BaseObject):
        """组合路径实现（无 contract_version）。"""

    def factory() -> object:
        """零参工厂。

        Returns:
            object: 结构化实现。
        """
        return Structural()

    registry.register("test_resolve_structural", "impl", factory)
    with pytest.raises(PluginError, match="缺少 contract_version"):
        registry.resolve("test_resolve_structural", "impl", expected_version="0.1.0")
    assert isinstance(registry.resolve("test_resolve_structural", "impl"), Structural)


@pytest.mark.kiwi_id(530)
def test_invalid_expected_version_rejected(registry: PluginRegistry) -> None:
    """期望版本格式非法：非 `X.Y.Z` 即拒。"""

    class Impl(BasePluggable):
        plugin_key = "test_resolve_fmt"
        plugin_name = "impl"

    assert Impl.plugin_name == "impl"
    with pytest.raises(PluginError, match="期望契约版本格式非法"):
        registry.resolve("test_resolve_fmt", "impl", expected_version="1.0")


@pytest.mark.kiwi_id(530)
def test_invalid_actual_version_rejected(registry: PluginRegistry) -> None:
    """实现版本格式非法（工厂实例，构建期不经校验）：解析期即拒。"""

    class BadImpl(BaseObject):
        contract_version = "v1"

    def factory() -> object:
        """零参工厂（返回格式非法的实现实例）。

        Returns:
            object: 实现实例。
        """
        return BadImpl()

    registry.register("test_resolve_bad_fmt", "impl", factory)
    assert BadImpl.contract_version == "v1"
    with pytest.raises(PluginError, match="实现契约版本格式非法"):
        registry.resolve("test_resolve_bad_fmt", "impl", expected_version="0.1.0")


@pytest.mark.kiwi_id(530)
def test_build_clears_instance_cache(registry: PluginRegistry) -> None:
    """构建清缓存：快照重建后解析得到新实例。"""

    class Impl(BasePluggable):
        plugin_key = "test_resolve_rebuild"
        plugin_name = "impl"

    assert Impl.plugin_name == "impl"
    first = registry.resolve("test_resolve_rebuild", "impl")
    registry.build()
    second = registry.resolve("test_resolve_rebuild", "impl")
    assert first is not second


@pytest.mark.kiwi_id(530)
def test_module_entrypoint_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """模块级入口：`resolve_plugin` 薄封装按同一语义工作。"""
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)

    class Impl(BasePluggable):
        plugin_key = "test_resolve_entry"
        plugin_name = "impl"

    first = resolve_plugin("test_resolve_entry", "impl")
    assert isinstance(first, Impl)
    assert resolve_plugin("test_resolve_entry", "impl") is first

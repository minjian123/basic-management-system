"""插件化中间层与注册表测试（Kiwi 529）：BasePluggable 契约 / 双轨登记 / 唯一性拒重 / 只读快照。"""

from abc import ABC, abstractmethod
from typing import cast

import pytest

from app.core import plugin as plugin_module
from app.core.base import BaseObject
from app.core.capability import BaseAsyncResource, BaseNullObject
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConfigError, PluginError
from app.core.plugin import (
    DEFAULT_CONTRACT_VERSION,
    NULL_PLUGIN_NAME,
    BasePluggable,
    PluginImpl,
    PluginRegistry,
)
from app.core.resources import ResourceManager


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


@pytest.mark.kiwi_id(529)
def test_base_pluggable_contract(registry: PluginRegistry) -> None:
    """BasePluggable 契约：字段默认、继承链、describe 标识（含 key 回退）。"""
    del registry
    assert issubclass(BasePluggable, BaseAsyncResource)

    class Impl(BasePluggable):
        plugin_key = "test_contract"
        plugin_name = "demo"

    class Fallback(BasePluggable):
        key = "test_fallback"
        plugin_name = "demo2"

    implex = Impl()
    assert BasePluggable.plugin_key == ""
    assert BasePluggable.plugin_name == ""
    assert implex.contract_version == DEFAULT_CONTRACT_VERSION == "0.1.0"
    assert implex.describe() == "test_contract:demo@0.1.0"
    assert Fallback().describe() == "test_fallback:demo2@0.1.0"


@pytest.mark.kiwi_id(529)
def test_abstract_port_not_registered(registry: PluginRegistry) -> None:
    """抽象端口不登记：抽象子类在构建期被剔除。"""

    class Port(BasePluggable, ABC):
        plugin_key = "test_abstract"

        @abstractmethod
        def work(self) -> None:
            """抽象能力方法。"""

    snapshot = registry.build()
    assert "test_abstract" not in snapshot
    assert Port.plugin_key == "test_abstract"


@pytest.mark.kiwi_id(529)
def test_null_registration_and_explicit_name(registry: PluginRegistry) -> None:
    """Null 缺省登记：未声明登记为 null；显式 plugin_name 优先；describe 带占位后缀。"""

    class Port(BasePluggable, ABC):
        plugin_key = "test_null"

        @abstractmethod
        def work(self) -> None:
            """抽象能力方法。"""

    class NullPort(Port, BaseNullObject):
        def work(self) -> None:
            """空实现。"""

    class NamedNull(NullPort):
        plugin_name = "fallback"

    snapshot = registry.build()
    assert snapshot["test_null"][NULL_PLUGIN_NAME] is NullPort
    assert snapshot["test_null"]["fallback"] is NamedNull
    assert NullPort().describe() == "test_null:null@0.1.0（占位实现，待回补真实实现）"
    assert NamedNull().describe() == "test_null:fallback@0.1.0（占位实现，待回补真实实现）"


@pytest.mark.kiwi_id(529)
def test_unnamed_non_null_not_registered(registry: PluginRegistry) -> None:
    """无名非 Null 实例化子类不登记（实工具类），且不报错。"""

    class Unnamed(BasePluggable):
        plugin_key = "test_unnamed"

    assert Unnamed.plugin_name == ""
    snapshot = registry.build()
    assert "test_unnamed" not in snapshot


@pytest.mark.kiwi_id(529)
def test_snapshot_readonly_and_lazy_build(registry: PluginRegistry) -> None:
    """只读快照：未构建自动构建、排序稳定、写入抛 TypeError。"""

    class Impl(BasePluggable):
        plugin_key = "test_auto"
        plugin_name = "impl"

    snapshot = registry.snapshot()
    assert snapshot["test_auto"]["impl"] is Impl
    assert list(snapshot) == sorted(snapshot)
    with pytest.raises(TypeError):
        cast("dict[str, object]", snapshot["test_auto"])["impl"] = object()
    with pytest.raises(TypeError):
        cast("dict[str, dict[str, object]]", snapshot)["test_auto"] = {}


@pytest.mark.kiwi_id(529)
def test_explicit_factory_registration(registry: PluginRegistry) -> None:
    """显式登记（组合路径）：零参工厂登记进同一注册表。"""

    class StructuralImpl(BaseObject):
        """组合路径实现（不继承 BasePluggable）。"""

        def work(self) -> str:
            """能力方法。

            Returns:
                str: 固定结果。
            """
            return "ok"

    def factory() -> object:
        """零参工厂（延迟导入 / 结构化实现入口）。

        Returns:
            object: 实现实例。
        """
        return StructuralImpl()

    registry.register("test_composition", "structural", factory)
    snapshot = registry.build()
    assert snapshot["test_composition"]["structural"] is factory


@pytest.mark.kiwi_id(529)
def test_duplicate_rejected(registry: PluginRegistry) -> None:
    """唯一性拒重：同名同键两实现构建期 PluginError（含双方类名，不静默覆盖）。"""

    class DupA(BasePluggable):
        plugin_key = "test_dup"
        plugin_name = "same"

    class DupB(BasePluggable):
        plugin_key = "test_dup"
        plugin_name = "same"

    assert (DupA.plugin_key, DupA.plugin_name) == (DupB.plugin_key, DupB.plugin_name)
    with pytest.raises(PluginError, match="重名") as excinfo:
        registry.build()
    message = str(excinfo.value)
    assert "DupA" in message and "DupB" in message
    assert isinstance(excinfo.value, ConfigError)
    assert excinfo.value.code == ErrorCode.PLUGIN


@pytest.mark.kiwi_id(529)
def test_cross_track_duplicate_rejected(registry: PluginRegistry) -> None:
    """跨轨拒重：显式登记与自动登记同键同名即拒。"""

    class Impl(BasePluggable):
        plugin_key = "test_cross"
        plugin_name = "impl"

    registry.register("test_cross", "impl", lambda: object())
    assert Impl.plugin_name == "impl"
    with pytest.raises(PluginError, match="重名") as excinfo:
        registry.build()
    assert "Impl" in str(excinfo.value)


@pytest.mark.kiwi_id(529)
def test_invalid_contract_version_rejected(registry: PluginRegistry) -> None:
    """契约版本格式：非 X.Y.Z 构建期 PluginError。"""

    class BadVersion(BasePluggable):
        plugin_key = "test_bad_version"
        plugin_name = "bad"
        contract_version = "1.0"

    assert BadVersion.contract_version == "1.0"
    with pytest.raises(PluginError, match="契约版本格式非法"):
        registry.build()


@pytest.mark.kiwi_id(529)
def test_empty_key_candidate_rejected(registry: PluginRegistry) -> None:
    """候选键校验：`plugin_key` 与 `key` 均为空的实例化子类构建期报错。"""

    class EmptyKey(BasePluggable):
        key = ""
        plugin_name = "impl"

    assert EmptyKey.key == ""
    with pytest.raises(PluginError, match="缺少 plugin_key"):
        registry.build()


@pytest.mark.kiwi_id(529)
def test_explicit_registration_validation(registry: PluginRegistry) -> None:
    """显式登记校验：键 / 名缺失、抽象类与不可调用 impl 均入明细。"""

    class AbstractImpl(BasePluggable, ABC):
        plugin_key = "test_abstract_explicit"
        plugin_name = "impl"

        @abstractmethod
        def work(self) -> None:
            """抽象能力方法。"""

    registry.register("", "name", lambda: object())
    registry.register("key", "", lambda: object())
    registry.register("key2", "name2", cast("PluginImpl", 42))
    registry.register("key3", "name3", AbstractImpl)
    assert AbstractImpl.plugin_name == "impl"
    with pytest.raises(PluginError) as excinfo:
        registry.build()
    message = str(excinfo.value)
    assert "plugin_key / plugin_name" in message
    assert "不可实例化" in message
    assert "不可调用" in message


@pytest.mark.kiwi_id(529)
def test_sealed_registry_rejects_register(registry: PluginRegistry) -> None:
    """运行期只读：构建后再显式登记即拒。"""

    class Impl(BasePluggable):
        plugin_key = "test_sealed"
        plugin_name = "impl"

    assert snapshot_has(registry, "test_sealed", "impl") is Impl
    with pytest.raises(PluginError, match="只读"):
        registry.register("test_other", "impl", lambda: object())


def snapshot_has(registry: PluginRegistry, key: str, name: str) -> PluginImpl:
    """取快照中指定实现（辅助断言）。

    Args:
        registry: 注册表。
        key: 登记键。
        name: 登记名。

    Returns:
        PluginImpl: 实现类或零参工厂。
    """
    return registry.snapshot()[key][name]


@pytest.mark.kiwi_id(529)
def test_module_entrypoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """模块级入口：构建 / 快照薄封装与默认注册表接线。"""
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)

    class Impl(BasePluggable):
        plugin_key = "test_entry"
        plugin_name = "impl"

    snapshot = plugin_module.build_plugin_registry()
    assert snapshot["test_entry"]["impl"] is Impl
    assert plugin_module.plugin_registry_snapshot() is snapshot
    with pytest.raises(PluginError, match="只读"):
        plugin_module.register_plugin("test_entry", "other", lambda: object())


@pytest.mark.kiwi_id(529)
async def test_lifecycle_defaults_and_resource_manager(registry: PluginRegistry) -> None:
    """生命周期：默认 setup / aclose 空实现；aclose 经 ResourceManager 逆序回收。"""
    del registry
    closed: list[str] = []

    class Plain(BasePluggable):
        plugin_key = "test_lifecycle_plain"
        plugin_name = "plain"

    class Closing(BasePluggable):
        plugin_key = "test_lifecycle"
        plugin_name = "closing"

        def __init__(self, name: str) -> None:
            self.name = name

        async def aclose(self) -> None:
            """记录释放顺序。"""
            closed.append(self.name)

    plain = Plain()
    assert await plain.setup() is None
    assert await plain.aclose() is None

    manager = ResourceManager()
    manager.register(Closing("a"))
    manager.register(Closing("b"))
    await manager.aclose()
    assert closed == ["b", "a"]

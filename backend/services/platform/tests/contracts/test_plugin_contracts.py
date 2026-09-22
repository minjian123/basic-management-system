"""插件注册表契约套件（Kiwi 567）：快照枚举 / 语义抽查 / 类实现遍历 / 工厂只读。"""

import re
from typing import cast

import pytest

from bms_core.core import plugin as plugin_module
from bms_core.core.assembly import PLUGIN_WIRINGS
from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import BasePluggable, PluginRegistry
from tests.contracts.support import build_snapshot

pytestmark = pytest.mark.kiwi_id(567)

_SNAPSHOT = build_snapshot()
_CASES: tuple[tuple[str, str, object], ...] = tuple(
    (plugin_key, plugin_name, impl) for plugin_key, bucket in _SNAPSHOT.items() for plugin_name, impl in bucket.items()
)
_CLASS_CASES = tuple(case for case in _CASES if isinstance(case[2], type))
_FACTORY_CASES = tuple(case for case in _CASES if not isinstance(case[2], type))
_CLASS_IDS = [f"{plugin_key}:{plugin_name}" for plugin_key, plugin_name, _ in _CLASS_CASES]


def _port_version(plugin_key: str) -> str:
    return next(wiring.port.contract_version for wiring in PLUGIN_WIRINGS if wiring.plugin_key == plugin_key)


def test_snapshot_integrity() -> None:
    """快照键集与能力清单一致，条目枚举互证；命名 / 版本 / null 基线齐备。"""
    assert set(_SNAPSHOT) == {wiring.plugin_key for wiring in PLUGIN_WIRINGS}
    assert len(_CASES) == sum(len(bucket) for bucket in _SNAPSHOT.values())
    for plugin_key, plugin_name, impl in _CASES:
        assert plugin_name
        if isinstance(impl, type):
            impl_type = cast("type[BasePluggable]", impl)
            version = impl_type.contract_version
            if plugin_name == "null":
                assert issubclass(impl_type, BaseNullObject)
        else:
            version = _port_version(plugin_key)
        assert re.fullmatch(r"\d+\.\d+\.\d+", version)


def test_duplicate_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """同能力同实现名重复登记：构建期拒绝（不静默覆盖）。"""
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)

    class FirstImpl(BasePluggable):
        plugin_key = "contract_sample"
        plugin_name = "impl"

    class SecondImpl(BasePluggable):
        plugin_key = "contract_sample"
        plugin_name = "impl"

    assert FirstImpl.plugin_name == SecondImpl.plugin_name
    with pytest.raises(PluginError, match="重名"):
        isolated.build()


def test_resolve_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注册即拒 / 空 provider 解析为 null / 同 provider 同实例（实例缓存）。"""
    isolated = PluginRegistry()
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", isolated)

    class NullSample(BasePluggable, BaseNullObject):
        plugin_key = "contract_null_sample"

    isolated.build()
    instance = isolated.resolve("contract_null_sample", "")
    assert isinstance(instance, NullSample)
    assert isolated.resolve("contract_null_sample", "") is instance
    with pytest.raises(PluginError, match="未注册"):
        isolated.resolve("contract_null_sample", "ghost")


@pytest.mark.parametrize(("plugin_key", "plugin_name", "impl"), _CLASS_CASES, ids=_CLASS_IDS)
async def test_class_impl_contract(plugin_key: str, plugin_name: str, impl: object) -> None:
    """全部类实现：零参实例化 + 生命周期幂等 + 描述与版本格式。"""
    instance = cast("type[BasePluggable]", impl)()
    await instance.setup()
    await instance.setup()
    await instance.aclose()
    await instance.aclose()
    description = instance.describe()
    assert plugin_key in description
    assert plugin_name in description
    assert re.fullmatch(r"\d+\.\d+\.\d+", instance.contract_version)
    if plugin_name == "null":
        assert isinstance(instance, BaseNullObject)


def test_factory_entries_read_only() -> None:
    """工厂实现登记齐备且只读（不实例化，交由装配 / 行为用例覆盖）。"""
    assert _FACTORY_CASES
    wiring_keys = {wiring.plugin_key for wiring in PLUGIN_WIRINGS}
    for plugin_key, plugin_name, impl in _FACTORY_CASES:
        assert plugin_key in wiring_keys
        assert plugin_name
        assert not isinstance(impl, type)
        assert callable(impl)

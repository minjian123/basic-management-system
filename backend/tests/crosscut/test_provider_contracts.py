"""提供者契约与组合轨边界套件（Kiwi 651 / 652）：BaseProvider 契约 + 不混入插件继承轨。"""

import pytest

from app.core.plugin import BasePluggable
from app.core.provider import BaseProvider
from app.dashboard.base import BaseDashboardCardProvider
from app.fieldtype.base import BaseFieldType
from app.health.base import BaseHealthCheck
from app.query.base import BaseQueryProvider
from tests.contracts.support import (
    DictQueryProvider,
    NamedCheck,
    TextFieldType,
    TodoCardProvider,
    build_snapshot,
)

_PROVIDER_PORTS = (BaseFieldType, BaseQueryProvider, BaseDashboardCardProvider, BaseHealthCheck)


@pytest.mark.kiwi_id(651)
def test_provider_contract_semantics() -> None:
    """4 类端口均继承 BaseProvider；实现类 key / describe 齐备；健康 name 别名等价 key。"""
    for port in _PROVIDER_PORTS:
        assert issubclass(port, BaseProvider)
    implementations = (TextFieldType(), DictQueryProvider(), TodoCardProvider(), NamedCheck("dependency"))
    for provider in implementations:
        assert provider.key
        description = provider.describe()
        assert description
        assert provider.key in description
    check = NamedCheck("dependency")
    assert check.name == check.key == "dependency"


@pytest.mark.kiwi_id(652)
def test_provider_composition_track_boundary() -> None:
    """组合轨边界：提供者非 BasePluggable 子类；插件快照不含提供者条目。"""
    for port in _PROVIDER_PORTS:
        assert not issubclass(port, BasePluggable)
    snapshot = build_snapshot()
    plugin_impls = {impl for bucket in snapshot.values() for impl in bucket.values()}
    implementations = (TextFieldType(), DictQueryProvider(), TodoCardProvider(), NamedCheck("dependency"))
    assert {type(provider) for provider in implementations}.isdisjoint(plugin_impls)
    assert BaseProvider not in plugin_impls

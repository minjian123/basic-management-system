"""体系基类与四段继承链（09_01，Kiwi 2214）。"""

import asyncio
import dataclasses

import pytest

from bms_core.api.base import BaseRouter
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseAsyncResource, BaseCapability, BasePlaceholder
from bms_core.core.logging import BaseLogger
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject, BaseValueObject
from bms_core.core.plugin import BasePluggable
from bms_core.core.provider import BaseProvider
from bms_core.models.base import BaseModel
from bms_core.schemas.base import BaseSchema


@dataclasses.dataclass(frozen=True)
class _Point(BaseValueObject):
    """测试用不可变值对象。"""

    x: int
    y: int = 0


@dataclasses.dataclass
class _Draft(BaseDataContract):
    """测试用可变数据契约。"""

    title: str = ""


class _Widget(BaseFrameworkObject):
    """测试用框架对象。"""

    object_kind = "widget"


@pytest.mark.kiwi_id(2214)
def test_system_roots_are_direct_children_of_base_object() -> None:
    """三个体系基类直接继承根系（严禁上帝基类：只有体系根可直挂 `BaseObject`）。"""
    assert BaseValueObject.__bases__ == (BaseObject,)
    assert BaseDataContract.__bases__ == (BaseObject,)
    assert BaseFrameworkObject.__bases__ == (BaseObject,)


@pytest.mark.kiwi_id(2214)
def test_value_object_frozen_semantics() -> None:
    """值对象体系：frozen（不可赋值）+ dataclass 相等 / 哈希。"""
    point = _Point(1)
    assert point == _Point(1)
    assert hash(point) == hash(_Point(1))
    with pytest.raises(dataclasses.FrozenInstanceError):
        point.x = 2  # type: ignore[misc]


@pytest.mark.kiwi_id(2214)
def test_data_contract_mutable() -> None:
    """数据契约体系：可变数据类。"""
    draft = _Draft(title="a")
    draft.title = "b"
    assert draft.title == "b"


@pytest.mark.kiwi_id(2214)
def test_framework_object_kind_and_aclose() -> None:
    """框架对象体系：`object_kind` 统一标识 + `aclose` 钩子位默认空操作。"""
    assert BaseFrameworkObject.object_kind == "framework"
    assert _Widget.object_kind == "widget"
    asyncio.run(_Widget().aclose())


@pytest.mark.kiwi_id(2214)
def test_four_segment_inheritance() -> None:
    """四段继承链：框架类基类挂框架对象层、数据契约基类挂数据契约层，且均在根系之下。"""
    for cls in (BasePlaceholder, BaseCapability, BaseAsyncResource, BaseLogger, BaseRouter):
        assert issubclass(cls, BaseFrameworkObject)
        assert issubclass(cls, BaseObject)
    for cls in (BaseSchema, BaseModel):
        assert issubclass(cls, BaseDataContract)
        assert issubclass(cls, BaseObject)
    assert issubclass(BasePluggable, BaseCapability)
    assert issubclass(BaseProvider, BaseCapability)

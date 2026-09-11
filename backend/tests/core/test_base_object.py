"""BaseObject 公共方法测试（Kiwi 14）。"""

import dataclasses
from dataclasses import dataclass

import pytest

from app.core.base import BaseObject
from app.models.demo import Demo
from app.repositories.base_repository import BaseRepository
from app.schemas.base import BaseSchema
from app.services.base_service import BaseService


@dataclass
class Point(BaseObject):
    """嵌套点实体。"""

    id: int
    x: int


@dataclass
class Nested(BaseObject):
    """嵌套/容器测试实体。"""

    name: str
    point: Point
    tags: list[object]


class Entity(BaseObject):
    """主键/身份测试实体。"""

    def __init__(self, item_id: int | None, name: str = "x") -> None:
        self.id = item_id
        self.name = name


@pytest.mark.kiwi_id(14)
def test_to_dict_reflects_public_fields_recursively() -> None:
    """to_dict 取公开字段并递归转换嵌套对象与容器。"""
    nested = Nested(name="n", point=Point(id=1, x=2), tags=[Point(id=3, x=4), {"a": Point(id=5, x=6)}])
    assert nested.to_dict() == {
        "name": "n",
        "point": {"id": 1, "x": 2},
        "tags": [{"id": 3, "x": 4}, {"a": {"id": 5, "x": 6}}],
    }


@pytest.mark.kiwi_id(14)
def test_to_json_sorts_keys_and_falls_back_to_str() -> None:
    """to_json 默认按键排序；不可序列化值降级 str；可关闭排序。"""
    obj = Nested(name="n", point=Point(id=1, x=2), tags=[object()])
    assert obj.to_json().startswith('{"name": "n"')
    assert "object object at" in obj.to_json()
    assert obj.to_json(sort_keys=False).startswith('{"name": "n"')


@pytest.mark.kiwi_id(14)
def test_str_and_repr_with_mro_precedence() -> None:
    """__str__/__repr__ 统一（纯 Python 类）；dataclass 生成方法按 MRO 约定优先。"""
    entity = Entity(1)
    assert str(entity) == repr(entity)
    assert str(entity).startswith("Entity(")

    nested = Nested(name="n", point=Point(id=1, x=2), tags=[])
    assert repr(nested).startswith("Nested(name=")  # dataclass 生成的 __repr__ 优先


@pytest.mark.kiwi_id(14)
def test_equality_by_primary_key_and_identity() -> None:
    """有主键按主键相等；无主键按身份。"""
    assert Entity(1) == Entity(1)
    assert Entity(1) != Entity(2)
    assert Entity(None) != Entity(None)
    assert Entity(1) != object()
    same = Entity(None)
    assert same == same


@pytest.mark.kiwi_id(14)
def test_hash_consistency() -> None:
    """相等对象哈希一致；无主键按身份哈希。"""
    assert hash(Entity(1)) == hash(Entity(1))
    bare = Entity(None)
    assert hash(bare) == object.__hash__(bare)


@pytest.mark.kiwi_id(14)
def test_public_fields_fallback_when_fields_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """dataclasses.fields 不可用时回退 __dict__ 公开字段。"""

    def boom(*args: object, **kwargs: object) -> object:
        raise TypeError("boom")

    monkeypatch.setattr(dataclasses, "fields", boom)
    assert Demo(id=1, name="甲").to_dict() == {"id": 1, "name": "甲"}


@pytest.mark.kiwi_id(14)
def test_demo_model_inherits_base_object() -> None:
    """demo 模型继承根基类，to_dict/to_json 可用。"""
    demo = Demo(id=1, name="甲")
    assert isinstance(demo, BaseObject)
    assert demo.to_dict() == {"id": 1, "name": "甲"}
    assert demo.to_json() == '{"id": 1, "name": "甲"}'


@pytest.mark.kiwi_id(14)
def test_bases_inherit_base_object() -> None:
    """三套基类继承根基类（继承约定生效）。"""
    assert issubclass(BaseRepository, BaseObject)
    assert issubclass(BaseService, BaseObject)
    assert issubclass(BaseSchema, BaseObject)

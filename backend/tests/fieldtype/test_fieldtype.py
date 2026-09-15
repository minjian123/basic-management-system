"""表单字段类型注册表基座契约测试（Kiwi 59）：契约 / 标识 / 常量 / 注册表模板 / 占位恒定通过 / 依赖解析。"""

from collections.abc import Mapping
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_field_type_registry
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import NotFoundError
from app.fieldtype.base import COLUMN_TYPE_DIALECTS, NULL_COLUMN_TYPE, BaseFieldType, BaseFieldTypeRegistry
from app.fieldtype.null import NullFieldTypeRegistry
from app.main import create_app, lifespan


class _FakeFieldType(BaseFieldType):
    """测试用字段类型提供者。"""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    def validate(self, value: object, *, options: Mapping[str, object] | None = None) -> tuple[str, ...]:
        return () if value else ("required",)

    def render_metadata(self) -> Mapping[str, object]:
        return {"component": "input", "type": self._key}

    def column_type(self, dialect: str) -> str:
        return f"{self._key}:{dialect}"


class _InMemoryRegistry(BaseFieldTypeRegistry):
    """测试用内存注册表：验证聚合模板（真实注册表随回补阶段）。"""

    def __init__(self) -> None:
        self._providers: dict[str, BaseFieldType] = {}

    def register(self, provider: BaseFieldType) -> None:
        self._providers[provider.key] = provider

    def get(self, key: str) -> BaseFieldType | None:
        return self._providers.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._providers)


@pytest.mark.kiwi_id(59)
def test_inheritance_and_keys() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseFieldType, BaseObject)
    assert issubclass(BaseFieldTypeRegistry, BaseCapability)
    assert issubclass(NullFieldTypeRegistry, BaseFieldTypeRegistry)
    assert issubclass(NullFieldTypeRegistry, BaseNullObject)
    assert BaseFieldTypeRegistry.key == "field_type_registry"

    registry = NullFieldTypeRegistry()
    assert registry.placeholder is True
    assert "占位实现" in registry.describe()


@pytest.mark.kiwi_id(59)
def test_constants() -> None:
    """方言清单与占位列类型常量。"""
    assert COLUMN_TYPE_DIALECTS == ("mysql", "postgresql", "dm", "sqlite")
    assert len(set(COLUMN_TYPE_DIALECTS)) == len(COLUMN_TYPE_DIALECTS)
    assert NULL_COLUMN_TYPE == "varchar(255)"


@pytest.mark.kiwi_id(59)
def test_registry_template_resolution() -> None:
    """聚合模板：注册后解析并委托校验 / 类型映射；keys 顺序＝注册顺序；未命中抛 NotFoundError。"""
    registry = _InMemoryRegistry()
    registry.register(_FakeFieldType("text"))
    registry.register(_FakeFieldType("number"))

    assert registry.keys() == ("text", "number")
    assert registry.validate("text", "abc") == ()
    assert registry.validate("text", "") == ("required",)
    assert registry.column_type("number", "mysql") == "number:mysql"

    with pytest.raises(NotFoundError):
        registry.validate("missing", "x")
    with pytest.raises(NotFoundError):
        registry.column_type("missing", "mysql")


@pytest.mark.kiwi_id(59)
def test_null_registry_fixed() -> None:
    """占位注册表：注册空操作、get None、keys 空、校验恒定通过、类型映射固定。"""
    registry = NullFieldTypeRegistry()
    registry.register(_FakeFieldType("text"))
    assert registry.get("text") is None
    assert registry.keys() == ()
    assert registry.validate("text", "") == ()
    assert registry.column_type("text", "mysql") == NULL_COLUMN_TYPE


@pytest.mark.kiwi_id(59)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位注册表；路由经 get_field_type_registry 取到同一实例。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.field_type_registry, NullFieldTypeRegistry)

        @app.get("/fieldtype-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            registry: Annotated[BaseFieldTypeRegistry, Depends(get_field_type_registry)],
        ) -> dict[str, object]:
            violations = registry.validate("text", "")
            return {"key": registry.key, "type": type(registry).__name__, "violations": list(violations)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/fieldtype-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "field_type_registry", "type": "NullFieldTypeRegistry", "violations": []}

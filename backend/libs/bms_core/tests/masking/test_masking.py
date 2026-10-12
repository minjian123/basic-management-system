"""数据脱敏基座契约测试（Kiwi 39）：继承 / 注册 / 占位直通 / 权限联动 / 序列化掩码。"""

from typing import Annotated, ClassVar

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core import plugin as plugin_module
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.context import get_current_masker, reset_current_masker, set_current_masker
from bms_core.core.plugin import PluginRegistry
from bms_core.masking.base import MASK_STRATEGIES, BaseMasker, MaskRule, get_masker
from bms_core.masking.null import NullMasker
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker
from bms_core.schemas.base import (
    BaseSchema,
    MaskedFields,
    _mask_sequence,  # pyright: ignore[reportPrivateUsage]
)


class DenyChecker(BasePermissionChecker):
    """测试用拒绝实现：不持任何权限码。"""

    def check(self, code: str) -> bool:
        """恒定拒绝。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: False。
        """
        return False


class FixedMasker(NullMasker):
    """测试用固定掩码器：所有字段值掩码为 `***`（不区分策略）。"""

    def mask(self, field: str, value: object, strategy: str | None = None) -> object:
        """固定掩码。

        Args:
            field: 字段名（本实现不区分）。
            value: 原始值（本实现不使用）。
            strategy: 字段策略（本实现不区分）。

        Returns:
            object: 固定掩码串 `***`。
        """
        del field, value, strategy
        return "***"


class UserResponse(BaseSchema):
    """测试用响应模型：手机号声明为敏感字段。"""

    masked_fields: ClassVar[MaskedFields] = ConcurrentStableSet[str]({"phone"})

    id: int
    name: str
    phone: str


class SequenceResponse(BaseSchema):
    """测试用响应模型：容器型敏感字段（逐元素掩码并保持容器形态）。"""

    masked_fields: ClassVar[MaskedFields] = ConcurrentStableSet[str]({"secrets"})

    secrets: object = None


def _mask_sequence_value(value: object) -> object:
    """经契约序列化链掩码单个容器值（返回掩码后的容器）。"""
    return SequenceResponse.model_construct(secrets=value).model_dump()["secrets"]


def test_masking_covers_sequence_container_forms() -> None:
    """脱敏递归：集合类 / 元组 / frozenset / 集合 / 列表容器逐元素掩码且形态保持。"""
    token = set_current_masker(FixedMasker(checker=NullPermissionChecker()))
    try:
        stable_list = _mask_sequence_value(ConcurrentStableList(["a"]))
        assert isinstance(stable_list, ConcurrentStableList)
        assert list(stable_list) == ["***"]

        stable_set = _mask_sequence_value(ConcurrentStableSet(["a"]))
        assert isinstance(stable_set, ConcurrentStableSet)
        assert list(stable_set) == ["***"]

        assert _mask_sequence_value(["a"]) == ["***"]
        assert _mask_sequence_value(("a",)) == ["***"]  # 序列化链把元组归一为列表
    finally:
        reset_current_masker(token)


def test_mask_sequence_preserves_container_forms() -> None:
    """脱敏序列容器形态：元组 / frozenset / 集合 / 列表经掩码后保持原容器。"""
    masker = FixedMasker(checker=NullPermissionChecker())
    masked = ConcurrentStableDict[str, str]({"secrets": "custom"})

    assert _mask_sequence(masked, "secrets", ("a",), masker, 1) == ("***",)
    assert _mask_sequence(masked, "secrets", frozenset({"a"}), masker, 1) == frozenset({"***"})
    assert _mask_sequence(masked, "secrets", {"a"}, masker, 1) == {"***"}
    assert _mask_sequence(masked, "secrets", ["a"], masker, 1) == ["***"]


def test_masking_stops_at_depth_limit() -> None:
    """脱敏递归深度上限：超深嵌套原样返回（不无限递归）。"""
    token = set_current_masker(FixedMasker(checker=NullPermissionChecker()))
    try:
        nested: object = "leaf"
        for _ in range(7):
            nested = [nested]
        assert isinstance(_mask_sequence_value(nested), list)
    finally:
        reset_current_masker(token)


def _build_app(masker: BaseMasker, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """构造带掩码依赖的测试应用（隔离注册表 + 配置解析注入测试掩码器）。

    Args:
        masker: 测试掩码器（登记为 provider `test`）。
        monkeypatch: pytest 补丁夹具。

    Returns:
        FastAPI: 测试应用实例。
    """
    registry = PluginRegistry()
    registry.register("masking", "test", lambda: masker)
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    app = FastAPI()
    app.state.settings = Settings(masking=PluginSelection(provider="test"))

    @app.get("/user")
    async def user(_: Annotated[BaseMasker, Depends(get_masker)]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]  # bare-collections:allow（FastAPI 端点返回注解）
        return UserResponse(id=1, name="甲", phone="13800001111").model_dump()

    return app


@pytest.mark.kiwi_id(39)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseMasker, BaseCapability)
    assert issubclass(NullMasker, BaseMasker)
    assert issubclass(NullMasker, BaseNullObject)
    assert BaseMasker.key == "masking"

    masker = NullMasker(checker=NullPermissionChecker())
    assert masker.placeholder is True
    assert "占位实现" in masker.describe()
    assert MASK_STRATEGIES == ("phone", "id_card", "email", "bank_card", "name", "address", "custom")


@pytest.mark.kiwi_id(39)
def test_register_rules() -> None:
    """字段注册：默认策略 / 指定策略 / 重复注册以最后一次为准 / 快照按字段名排序。"""
    masker = NullMasker(checker=NullPermissionChecker())
    assert masker.masked_fields == frozenset()

    default_rule = masker.register("phone")
    assert default_rule == MaskRule(field="phone", strategy="custom")
    masker.register("id_card", "id_card")
    masker.register("phone", "custom2")

    assert masker.masked_fields == frozenset({"phone", "id_card"})
    assert [rule.field for rule in masker.rules()] == ["id_card", "phone"]
    assert [rule.strategy for rule in masker.rules()] == ["id_card", "custom2"]


@pytest.mark.kiwi_id(39)
def test_null_masker_passthrough() -> None:
    """占位实现原样返回（不掩码、不解密），未注册字段同样原样返回。"""
    masker = NullMasker(checker=NullPermissionChecker())
    masker.register("phone")
    assert masker.mask("phone", "13800001111") == "13800001111"
    assert masker.reveal("phone", "13800001111") == "13800001111"
    assert masker.mask("name", "甲") == "甲"


@pytest.mark.kiwi_id(39)
def test_check_plain_uses_injected_checker() -> None:
    """明文判定在基座内：经注入检查器取值，调用方不传权限参数。"""
    assert NullMasker(checker=NullPermissionChecker()).check_plain() is True
    assert NullMasker(checker=DenyChecker()).check_plain() is False


@pytest.mark.kiwi_id(39)
async def test_get_masker_injects_context_and_masks(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖提供者：注入上下文后序列化自动掩码；请求结束上下文复位。"""
    app = _build_app(FixedMasker(checker=NullPermissionChecker()), monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/user")
        assert resp.status_code == 200
        assert resp.json() == {"id": "1", "name": "甲", "phone": "***"}

    assert get_current_masker() is None


@pytest.mark.kiwi_id(39)
async def test_serialization_passthrough_without_masker(monkeypatch: pytest.MonkeyPatch) -> None:
    """无掩码器直通：未注入上下文时序列化与既有行为一致（占位期默认）。"""
    app = _build_app(NullMasker(checker=NullPermissionChecker()), monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/user")
        assert resp.json() == {"id": "1", "name": "甲", "phone": "13800001111"}

    payload = UserResponse(id=1, name="甲", phone="13800001111")
    assert payload.model_dump() == {"id": "1", "name": "甲", "phone": "13800001111"}

    token = set_current_masker(FixedMasker(checker=NullPermissionChecker()))
    assert payload.model_dump() == {"id": "1", "name": "甲", "phone": "***"}
    reset_current_masker(token)
    assert payload.model_dump() == {"id": "1", "name": "甲", "phone": "13800001111"}
    assert BaseSchema.masked_fields == frozenset()

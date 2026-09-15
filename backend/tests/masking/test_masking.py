"""数据脱敏基座契约测试（Kiwi 39）：继承 / 注册 / 占位直通 / 权限联动 / 序列化掩码。"""

from typing import Annotated, ClassVar

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.context import get_current_masker, reset_current_masker, set_current_masker
from app.masking.base import MASK_STRATEGIES, BaseMasker, MaskRule, get_masker
from app.masking.null import NullMasker
from app.permission.base import BasePermissionChecker
from app.permission.null import NullPermissionChecker
from app.schemas.base import BaseSchema


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

    def mask(self, field: str, value: object) -> object:
        """固定掩码。

        Args:
            field: 字段名（本实现不区分）。
            value: 原始值（本实现不使用）。

        Returns:
            object: 固定掩码串 `***`。
        """
        del field, value
        return "***"


class UserResponse(BaseSchema):
    """测试用响应模型：手机号声明为敏感字段。"""

    masked_fields: ClassVar[frozenset[str]] = frozenset({"phone"})

    id: int
    name: str
    phone: str


def _build_app(masker: BaseMasker) -> FastAPI:
    """构造带掩码依赖的测试应用。

    Args:
        masker: 装配到 `app.state` 的掩码器。

    Returns:
        FastAPI: 测试应用实例。
    """
    app = FastAPI()
    app.state.masker = masker

    @app.get("/user")
    async def user(_: Annotated[BaseMasker, Depends(get_masker)]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
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
    assert MASK_STRATEGIES == ("phone", "id_card", "email", "bank_card", "name", "custom")


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
async def test_get_masker_injects_context_and_masks() -> None:
    """依赖提供者：注入上下文后序列化自动掩码；请求结束上下文复位。"""
    app = _build_app(FixedMasker(checker=NullPermissionChecker()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/user")
        assert resp.status_code == 200
        assert resp.json() == {"id": "1", "name": "甲", "phone": "***"}

    assert get_current_masker() is None


@pytest.mark.kiwi_id(39)
async def test_serialization_passthrough_without_masker() -> None:
    """无掩码器直通：未注入上下文时序列化与既有行为一致（占位期默认）。"""
    app = _build_app(NullMasker(checker=NullPermissionChecker()))
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

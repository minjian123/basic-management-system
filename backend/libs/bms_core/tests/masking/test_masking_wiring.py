"""脱敏接入用例（Kiwi 2225）：声明归一化 / 序列化自动掩码（嵌套与列表）/ 策略解析链 /
明文口径 fail-closed / 掩码器全局注入 / 文本掩码辅助。

覆盖范围见 Kiwi 用例 text；既有 Kiwi 39（契约）与 2212（基座实现）断言不变，仅按需同步替身签名。
"""

from contextvars import Token
from typing import Annotated, cast

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import Field
from support_app import ApplicationFactory

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import get_current_masker, reset_current_masker, set_current_masker
from bms_core.masking.base import BaseMasker
from bms_core.masking.default import DefaultMasker
from bms_core.masking.text import mask_text
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)


class _AllowChecker(BasePermissionChecker):
    """测试用允许实现：恒定持权限码（**非**占位，模拟 RBAC 就绪后持 `data:plain`）。"""

    def check(self, code: str) -> bool:
        """恒定允许。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: True。
        """
        del code
        return True


class _DenyChecker(BasePermissionChecker):
    """测试用拒绝实现：不持任何权限码（非占位实现）。"""

    def check(self, code: str) -> bool:
        """恒定拒绝。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: False。
        """
        del code
        return False


class _SetDeclared(BaseSchema):
    """集合写法声明：字段名同名内置策略（`phone` → `phone` 策略）。"""

    masked_fields = ConcurrentStableSet({"phone"})

    id: int
    phone: str
    note: str = ""


class _MapDeclared(BaseSchema):
    """映射写法声明：字段名与策略名解耦（`mobile` → `phone` 策略、`mail` → `email` 策略）。"""

    masked_fields = ConcurrentStableDict({"mobile": "phone", "mail": "email"})

    id: int
    mobile: str
    mail: str


class _Inner(BaseSchema):
    """嵌套子模型：自身声明敏感字段。"""

    masked_fields = ConcurrentStableSet({"phone"})

    phone: str


class _Outer(BaseSchema):
    """外层模型：声明 `phone`（覆盖裸字典键）与 `phones`（列表逐元素）并嵌套子模型 / 字典。"""

    masked_fields = ConcurrentStableDict({"phone": "phone", "phones": "phone"})

    id: int
    inner: _Inner
    items: Annotated[ConcurrentStableList[_Inner], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    phones: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    meta: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )


class _Deep(BaseSchema):
    """深嵌套承载体：声明 `phone` 以验证递归深度上限。"""

    masked_fields = ConcurrentStableSet({"phone"})

    payload: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )


def _deny_masker() -> DefaultMasker:
    """构造无权限码的真实掩码器（缺省占位检查器 → fail-closed）。

    Returns:
        DefaultMasker: 掩码器实例。
    """
    return DefaultMasker(checker=NullPermissionChecker())


def _nested(depth: int) -> ConcurrentStableDict[str, object]:
    """构造 `depth` 层嵌套的字典（最内层含命名字段 `phone`）。

    Args:
        depth: 嵌套层数（最外层计 1）。

    Returns:
        ConcurrentStableDict[str, object]: 嵌套字典。
    """
    current: ConcurrentStableDict[str, object] = ConcurrentStableDict({"phone": "13800001111", "keep": "x"})
    for _ in range(depth - 1):
        current = ConcurrentStableDict({"nested": current})
    return current


def _use(masker: DefaultMasker) -> Token[BaseMasker | None]:
    """把掩码器写入请求上下文（返回复位令牌）。

    Args:
        masker: 掩码器实例。

    Returns:
        Token[BaseMasker | None]: 上下文复位令牌。
    """
    return set_current_masker(masker)


@pytest.mark.kiwi_id(2225)
def test_declaration_forms_and_serialization_masking() -> None:
    """集合 / 映射两种声明的字段各自掩码；未声明字段与默认空声明原样。"""
    token = _use(_deny_masker())
    try:
        assert _SetDeclared(id=1, phone="13812345678", note="hi").model_dump() == {
            "id": "1",
            "phone": "138****5678",
            "note": "hi",
        }
        assert _MapDeclared(id=2, mobile="13812345678", mail="zhangsan@example.com").model_dump() == {
            "id": "2",
            "mobile": "138****5678",
            "mail": "z***@example.com",
        }
        assert _Inner(phone="13812345678").model_dump() == {"phone": "138****5678"}
        assert BaseSchema.masked_fields == frozenset()
    finally:
        reset_current_masker(token)


@pytest.mark.kiwi_id(2225)
def test_nested_model_list_and_plain_dict_masking() -> None:
    """嵌套子模型 / 列表元素 / 声明字段为列表 / 裸字典键均掩码，且容器类型保持。"""
    token = _use(_deny_masker())
    try:
        payload = _Outer(
            id=1,
            inner=_Inner(phone="13800001111"),
            items=ConcurrentStableList([_Inner(phone="13900002222")]),
            phones=ConcurrentStableList(["13800001111", "13900002222"]),
            meta=ConcurrentStableDict({"phone": "13800003333", "keep": "plain"}),
        )
        dump = payload.model_dump()
    finally:
        reset_current_masker(token)

    assert dump["inner"] == {"phone": "138****1111"}
    assert dump["items"] == [{"phone": "139****2222"}]
    assert [str(item) for item in cast("ConcurrentStableList[str]", dump["phones"])] == [
        "138****1111",
        "139****2222",
    ]
    meta = cast("ConcurrentStableDict[str, object]", dump["meta"])
    assert meta["phone"] == "138****3333"
    assert meta["keep"] == "plain"
    assert isinstance(dump["phones"], ConcurrentStableList)
    assert isinstance(meta, ConcurrentStableDict)


@pytest.mark.kiwi_id(2225)
def test_recursion_depth_limit_keeps_value() -> None:
    """浅层掩码、超深（≥ 上限）原样返回，不抛错。"""
    token = _use(_deny_masker())
    try:
        shallow = _Deep(payload=_nested(1)).model_dump()
        deep = _Deep(payload=_nested(8)).model_dump()
    finally:
        reset_current_masker(token)

    shallow_inner = cast("ConcurrentStableDict[str, object]", shallow["payload"])
    assert shallow_inner["phone"] == "138****1111"

    cursor: object = deep["payload"]
    for _ in range(7):
        cursor = cast("ConcurrentStableDict[str, object]", cursor)["nested"]
    assert cast("ConcurrentStableDict[str, object]", cursor)["phone"] == "13800001111"


@pytest.mark.kiwi_id(2225)
def test_strategy_resolution_chain() -> None:
    """解析链：注册 / 规则覆盖 > 声明 > 字段名同名内置 > 未命中原样；未知策略兜底全掩码。"""
    masker = _deny_masker()
    assert masker.mask("unregistered", "13800001111") == "13800001111"
    assert masker.mask("phone", "13800001111") == "138****1111"
    assert masker.mask("mobile", "13800001111", strategy="phone") == "138****1111"

    overridden = DefaultMasker(checker=NullPermissionChecker(), rules=ConcurrentStableDict({"mobile": "custom"}))
    assert overridden.mask("mobile", "13800001111", strategy="phone") == "***"
    assert masker.mask("mystery", "value", strategy="unknown") == "***"
    assert masker.mask("phone", None) is None


@pytest.mark.kiwi_id(2225)
def test_plain_permission_fail_closed() -> None:
    """占位检查器一律掩码（`data:plain` 静默不生效）；非占位按权限放行 / 掩码。"""
    placeholder = _deny_masker()
    assert placeholder.check_plain() is False
    assert placeholder.mask("phone", "13800001111") == "138****1111"

    allowed = DefaultMasker(checker=_AllowChecker())
    assert allowed.check_plain() is True
    assert allowed.mask("phone", "13800001111") == "13800001111"

    denied = DefaultMasker(checker=_DenyChecker())
    assert denied.check_plain() is False
    assert denied.mask("phone", "13800001111") == "138****1111"


_wired_router = APIRouter()


@_wired_router.get("/wired/user")
async def _wired_user() -> _SetDeclared:  # pyright: ignore[reportUnusedFunction]
    """测试用路由：**不**显式声明 `Depends(get_masker)`，验证全局注入生效。

    Returns:
        _SetDeclared: 含敏感字段的响应模型。
    """
    return _SetDeclared(id=1, phone="13800001111", note="hi")


@pytest.mark.kiwi_id(2225)
async def test_application_factory_masks_wired_route() -> None:
    """应用工厂全局依赖：未显式挂掩码器的路由也自动掩码，请求结束上下文复位。"""
    app = ApplicationFactory().create(None)
    app.state.settings.masking.provider = "default"
    app.include_router(_wired_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/wired/user")

    assert resp.status_code == 200
    assert resp.json() == {"id": "1", "phone": "138****1111", "note": "hi"}
    assert get_current_masker() is None


@pytest.mark.kiwi_id(2225)
def test_mask_text_builtin_dispatch() -> None:
    """文本掩码辅助：内置策略分派（含 email 特例与未知策略兜底 custom），不做值探测。"""
    assert mask_text("13800001111", "phone") == "138****1111"
    assert mask_text("zhangsan@example.com", "email") == "z***@example.com"
    assert mask_text("张三", "name", mask_char="#") == "张#"
    assert mask_text("EMP-0001") == "***"
    assert mask_text("value", "unknown") == "***"

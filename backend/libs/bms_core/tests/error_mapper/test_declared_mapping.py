"""声明式错误码映射的渲染接线（07D 需求 02-2）：统一单点改写。

覆盖详细设计 §3.5 用例 9~11：
- 声明映射命中：`build_error_response` 出目标码 + 目标状态 + 目标文案键；
- 声明优先于插件（同时配置时以声明为准）；
- 未命中不改写（码 / 状态 / 文案逐字节不变）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.api.errors import build_error_response
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import TenantSuspendedError
from bms_core.error_mapper.base import apply_error_mapper
from bms_core.services.module_registry import (
    ErrorCodeRecord,
    error_code_mapping_view,
    register_error_code_records,
    reset_error_code_records,
)

_PRODUCT_CODE = 390011


pytestmark = pytest.mark.kiwi_id(2450)


def _record(*, maps_from: ConcurrentStableFrozenList[int] | None = None) -> ErrorCodeRecord:
    """构造一条产品错误码（承载 `80002`）。

    Args:
        maps_from: 承接的基座码（缺省 `[80002]`）。

    Returns:
        ErrorCodeRecord: 错误码记录。
    """
    return ErrorCodeRecord(
        code=_PRODUCT_CODE,
        domain="demo",
        http_status=403,
        message_key="demo.error.tenant_suspended",
        severity="warning",
        description="租户已停用",
        product_key="demo",
        segment="39",
        maps_from=ConcurrentStableFrozenList((80002,)) if maps_from is None else maps_from,
    )


def _scope(*, provider: str = "demo") -> Any:
    """构造最小 ASGI scope（带装配 settings）。

    Args:
        provider: `[error_mapper].provider` 取值。

    Returns:
        Any: ASGI scope。
    """
    settings = SimpleNamespace(
        translator=SimpleNamespace(provider="null"),
        error_mapper=SimpleNamespace(provider=provider),
    )
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/demo",
        "headers": [],
        "state": {},
        "app": app,
    }


@pytest.fixture(autouse=True)
def _reset_records() -> Iterator[None]:
    """每例前后清空装载的码与映射视图。

    Yields:
        None: 用例运行期。
    """
    reset_error_code_records()
    yield
    reset_error_code_records()


def test_declared_mapping_view_registered() -> None:
    """装载后映射视图含 `80002 → 390011`。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    assert error_code_mapping_view().get(80002) == _PRODUCT_CODE


def test_apply_mapper_hits_declaration() -> None:
    """声明命中：改写为目标码，状态取目标码声明值，`data` 保留。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    mapped = apply_error_mapper(TenantSuspendedError(data={"reason": "demo"}), "demo")
    assert mapped.code == _PRODUCT_CODE
    assert mapped.http_status == 403
    assert mapped.data == {"reason": "demo"}


async def test_build_error_response_uses_target_code() -> None:
    """统一渲染单点输出目标码（声明优先，插件缺省不影响）。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    response = await build_error_response(_scope(), TenantSuspendedError())
    body = cast("dict[str, Any]", response.body and json.loads(bytes(response.body)))
    assert response.status_code == 403
    assert body["code"] == _PRODUCT_CODE
    assert body["message"] == "demo.error.tenant_suspended"


async def test_unmapped_error_is_unchanged() -> None:
    """未声明映射的异常不改写（仍是 80002 / 403）。"""
    register_error_code_records(ConcurrentStableList((_record(maps_from=ConcurrentStableFrozenList()),)))
    response = await build_error_response(_scope(), TenantSuspendedError())
    body = cast("dict[str, Any]", response.body and json.loads(bytes(response.body)))
    assert body["code"] == int(ErrorCode.TENANT_SUSPENDED)
    assert response.status_code == 403


def test_declaration_wins_over_provider() -> None:
    """声明优先于插件：即便 provider 未注册也不再回退原码。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    mapped = apply_error_mapper(TenantSuspendedError(), "not_registered_provider")
    assert mapped.code == _PRODUCT_CODE

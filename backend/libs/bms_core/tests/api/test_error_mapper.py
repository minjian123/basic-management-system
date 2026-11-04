"""产品码覆盖能力域（msg 任务 `01-1-1`；Kiwi 2411）：未配置不覆盖 / 配置后单点改写 / 解析失败原样返回。

覆盖：`NullErrorMapper` 恒等、未配置实现名不解析插件、已登记实现改写异常、实现名未登记时原样返回、
`build_error_response()` 单点生效（配置 / 无该配置段 / 无应用上下文三条路径）。
"""

import json
import types
from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.responses import JSONResponse
from starlette.types import Scope

from bms_core.api.errors import build_error_response
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import BizError, TenantSuspendedError
from bms_core.core.plugin import default_plugin_registry, register_plugin
from bms_core.error_mapper.base import BaseErrorMapper, apply_error_mapper
from bms_core.error_mapper.null import NullErrorMapper

pytestmark = pytest.mark.kiwi_id(2411)

_MAPPED_CODE = 350011
"""测试用产品码（形态同 msg 段位，不与平台码冲突）。"""


class _DemoMapper(BaseErrorMapper):
    """测试用覆盖器：停用类异常改写为产品码，其余原样返回。

    不声明 `plugin_name`（避免 `__init_subclass__` 自动收集与本用例的显式登记重名）。
    """

    def map(self, exc: BizError) -> BizError:
        """按异常类型改写。

        Args:
            exc: 原始业务异常。

        Returns:
            BizError: 停用类 → 产品码异常；其余原样。
        """
        if isinstance(exc, TenantSuspendedError):
            return BizError(_MAPPED_CODE, exc.message, http_status=403)
        return exc


_DEMO_PROVIDER = "demo"
"""测试用实现名（显式登记，不走自动收集）。"""


@pytest.fixture
def registered_mapper() -> Iterator[None]:
    """在默认注册表登记测试实现（用例结束后复位，不污染其他用例）。

    Yields:
        None: 用例运行期。
    """
    registry = default_plugin_registry()
    registry.reset()
    try:
        register_plugin("error_mapper", _DEMO_PROVIDER, _DemoMapper)
        yield
    finally:
        registry.reset()


def _scope(*, provider: str | None = None, with_settings: bool = True) -> Scope:
    """构造 ASGI 作用域（按需带 `[error_mapper]` 配置段）。

    Args:
        provider: 覆盖实现名；`None` 表示配置对象上**不存在**该段。
        with_settings: 是否挂应用上下文（含 settings）。

    Returns:
        Scope: 作用域字典。
    """
    scope: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"path": "/api/v1/msg/topics", "method": "GET", "headers": ConcurrentStableList()}
    )
    if not with_settings:
        return cast("Scope", scope)
    if provider is None:
        settings = types.SimpleNamespace(translator=types.SimpleNamespace(provider=""))
    else:
        settings = types.SimpleNamespace(
            translator=types.SimpleNamespace(provider=""),
            error_mapper=types.SimpleNamespace(provider=provider),
        )
    scope.set("app", types.SimpleNamespace(state=types.SimpleNamespace(settings=settings, metrics=None)))
    return cast("Scope", scope)


def _code(response: JSONResponse) -> int:
    """取响应体业务码。

    Args:
        response: 统一响应对象。

    Returns:
        int: 业务码。
    """
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        cast("dict[str, object]", json.loads(bytes(response.body)))
    )
    return cast("int", body["code"])


def test_null_mapper_returns_original() -> None:
    """空实现恒等：未接真实覆盖时渲染结果与接入前一致。"""
    exc = TenantSuspendedError()
    assert NullErrorMapper().map(exc) is exc


def test_unconfigured_provider_skips_registry() -> None:
    """未配置实现名：不解析插件（注册表未构建也安全），原样返回。"""
    exc = TenantSuspendedError()
    default_plugin_registry().reset()
    assert apply_error_mapper(exc) is exc
    assert apply_error_mapper(exc, "") is exc


def test_registered_mapper_rewrites(registered_mapper: None) -> None:
    """已登记实现：按产品码改写（判定分支命中 / 未命中两种）。"""
    del registered_mapper
    suspended = TenantSuspendedError()
    mapped = apply_error_mapper(suspended, _DEMO_PROVIDER)
    assert mapped.code == _MAPPED_CODE
    other = BizError(10001)
    assert apply_error_mapper(other, _DEMO_PROVIDER) is other


def test_unregistered_provider_returns_original() -> None:
    """实现名未登记：原样返回（错误响应路径不再抛错，避免 500 掩盖原始错误）。"""
    default_plugin_registry().reset()
    exc = TenantSuspendedError()
    assert apply_error_mapper(exc, "not-registered") is exc


async def test_build_error_response_applies_mapper(registered_mapper: None) -> None:
    """渲染单点生效：配置实现名后，停用异常对外出产品码与产品状态。"""
    del registered_mapper
    response = await build_error_response(_scope(provider=_DEMO_PROVIDER), TenantSuspendedError())
    assert (response.status_code, _code(response)) == (403, _MAPPED_CODE)


async def test_build_error_response_without_mapper_section() -> None:
    """配置对象无 `error_mapper` 段：按不覆盖处理（旧装配零改动）。"""
    response = await build_error_response(_scope(provider=None), TenantSuspendedError())
    assert (response.status_code, _code(response)) == (403, 80002)


async def test_build_error_response_without_app() -> None:
    """无应用上下文：按不覆盖处理（单测 / 非标准装配路径）。"""
    response = await build_error_response(_scope(with_settings=False), TenantSuspendedError())
    assert (response.status_code, _code(response)) == (403, 80002)

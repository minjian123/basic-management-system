"""统一渲染单点：视图补全 / 文案分档 / 未登记码观测（07B `02_05`）。

覆盖：命中视图（状态以声明为准 + 文案取 `message_key`）、平台码 `error.{code}` 口径、
显式文案优先、未登记码保留自值并计数、占位 translator 不告警不计指标、真实 translator
命中 / 缺失回退 / 抛错回退，以及无应用上下文与无指标器的降级。

新增用例的 Kiwi 编号由 07B `05_01` 统一登记后回填（本批不标 `kiwi_id`）。
"""

# pyright: reportUnusedFunction=false
import json
import types
from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.responses import JSONResponse
from starlette.types import Scope

from bms_core.api import errors as errors_module
from bms_core.api.errors import (
    METRIC_ERROR_CODE_UNKNOWN,
    METRIC_ERROR_CODE_UNRESOLVED,
    build_error_response,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import BizError, NotFoundError
from bms_core.services.module_registry import (
    ErrorCodeRecord,
    register_error_code_records,
    reset_error_code_records,
)


class _Metrics:
    """指标器替身：记录 `(指标名, 标签)`。"""

    def __init__(self) -> None:
        self.calls: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, str]]] = ConcurrentStableList()

    async def counter(self, name: str, *, value: float = 1.0, labels: object | None = None) -> None:
        """记录计数器调用（值忽略）。"""
        del value
        self.calls.add((name, ConcurrentStableDict(cast("dict[str, str]", labels or {}))))

    def names(self) -> ConcurrentStableList[str]:
        """取已记录的指标名序列。

        Returns:
            ConcurrentStableList[str]: 指标名。
        """
        return ConcurrentStableList(name for name, _ in self.calls)


class _Translator:
    """翻译器替身：可返回译文 / 原样键名 / 抛错。"""

    def __init__(self, text: object = "部门不存在（译文）") -> None:
        self.text = text
        self.locales: ConcurrentStableList[str | None] = ConcurrentStableList()

    def resolve_locale(self, accept_language: str | None = None) -> str:
        """解析语言（记录入参）。"""
        self.locales.add(accept_language)
        return "en-US"

    async def translate(self, key: str, *, locale: str | None = None, params: object | None = None) -> str:
        """取词（`text` 为异常时抛出，为字符串时返回）。"""
        del locale, params
        if isinstance(self.text, Exception):
            raise self.text
        return str(self.text) if self.text else key


def _record(**overrides: object) -> ErrorCodeRecord:
    """构造一条产品错误码记录（缺省为合法 demo 码）。

    Args:
        **overrides: 字段覆盖。

    Returns:
        ErrorCodeRecord: 记录。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "code": 390001,
            "domain": "org",
            "http_status": 404,
            "message_key": "demo.error.dept_not_found",
            "severity": "warning",
            "description": "部门不存在",
            "product_key": "demo",
            "segment": "39",
        }
    )
    for key, value in overrides.items():
        payload.set(key, value)
    return ErrorCodeRecord(**payload)  # pyright: ignore[reportArgumentType]


def _scope(
    *,
    metrics: object | None = None,
    provider: str = "",
    accept_language: str | None = None,
    with_app: bool = True,
    trace_id: str | None = None,
) -> Scope:
    """构造 ASGI 作用域（可带 / 不带应用上下文）。

    Args:
        metrics: 指标器替身。
        provider: translator 实现名（空 = 占位）。
        accept_language: `Accept-Language` 请求头。
        with_app: 是否挂应用上下文。
        trace_id: 请求态链路 id。

    Returns:
        Scope: 作用域字典。
    """
    scope: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"path": "/api/v1/demos", "method": "GET", "headers": ConcurrentStableList()}
    )
    headers: ConcurrentStableList[tuple[bytes, bytes]] = ConcurrentStableList()
    if accept_language is not None:
        headers.add((b"accept-language", accept_language.encode()))
    scope.set("headers", headers)
    if trace_id is not None:
        scope.set("state", ConcurrentStableDict({"trace_id": trace_id}))
    if with_app:
        settings = types.SimpleNamespace(translator=types.SimpleNamespace(provider=provider))
        scope.set("app", types.SimpleNamespace(state=types.SimpleNamespace(settings=settings, metrics=metrics)))
    return cast("Scope", scope)


def _body(response: JSONResponse) -> ConcurrentStableDict[str, object]:
    """解析响应体。

    Args:
        response: 统一响应对象。

    Returns:
        ConcurrentStableDict[str, object]: 响应 JSON。
    """
    return ConcurrentStableDict(cast("dict[str, object]", json.loads(bytes(response.body))))


def _patch_translator(monkeypatch: pytest.MonkeyPatch, translator: object) -> None:
    """把「真实 translator」替换为替身（`None` 表示占位期）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        translator: 替身（`_Translator` 或 None）。
    """

    def _resolve(scope: Scope) -> object:
        del scope
        return translator

    monkeypatch.setattr(errors_module, "_real_translator", _resolve)


@pytest.fixture(autouse=True)
def _isolate_records() -> Iterator[None]:
    """每例前后清空注入错误码记录。

    Yields:
        None: 用例运行期。
    """
    reset_error_code_records()
    yield
    reset_error_code_records()


async def test_hit_uses_declared_status_and_message_key() -> None:
    """命中视图：状态以声明为准（异常自带 200 也改 404），文案取 `message_key`（占位期）。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    metrics = _Metrics()
    response = await build_error_response(_scope(metrics=metrics), BizError(390001, data={"k": 1}))
    assert response.status_code == 404
    body = _body(response)
    assert (body["code"], body["message"], body["data"]) == (390001, "demo.error.dept_not_found", {"k": 1})
    assert metrics.names() == []


async def test_platform_code_uses_error_code_key() -> None:
    """平台码：文案键 `error.{code}` 与改造前一致（平台端零改造）。"""
    response = await build_error_response(_scope(), NotFoundError())
    assert response.status_code == 404
    assert _body(response)["message"] == "error.10002"


async def test_explicit_message_wins() -> None:
    """异常显式给文案：以显式值为准（既有文案零改动）。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    response = await build_error_response(_scope(), BizError(390001, "部门已停用"))
    assert _body(response)["message"] == "部门已停用"


async def test_unknown_code_keeps_exception_values_and_counts() -> None:
    """未登记码：保留异常自带状态与文案，并计数（不兜底 10000/500）。"""
    metrics = _Metrics()
    response = await build_error_response(_scope(metrics=metrics), BizError(999999, "boom", http_status=418))
    assert response.status_code == 418
    assert _body(response)["message"] == "boom"
    assert metrics.calls[0][0] == METRIC_ERROR_CODE_UNKNOWN
    assert metrics.calls[0][1]["code"] == "999999"


async def test_unknown_code_without_message_falls_back_to_key() -> None:
    """未登记码且未给文案：回落 `error.{code}`（现状口径不变）。"""
    response = await build_error_response(_scope(), BizError(999999))
    assert response.status_code == 200
    assert _body(response)["message"] == "error.999999"


async def test_real_translator_hit_returns_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 translator 命中：响应文案为译文，不产生回退指标。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    translator = _Translator("Dept not found")
    _patch_translator(monkeypatch, translator)
    metrics = _Metrics()
    response = await build_error_response(_scope(metrics=metrics, accept_language="en-US,en"), BizError(390001))
    assert _body(response)["message"] == "Dept not found"
    assert metrics.names() == []
    assert translator.locales == ["en-US,en"]


async def test_real_translator_missing_falls_back_to_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 translator 未命中（原样返回键名）：回退 `description` 并计数。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    _patch_translator(monkeypatch, _Translator(""))
    metrics = _Metrics()
    response = await build_error_response(_scope(metrics=metrics), BizError(390001))
    assert _body(response)["message"] == "部门不存在"
    assert metrics.calls[0][0] == METRIC_ERROR_CODE_UNRESOLVED


async def test_real_translator_error_falls_back_to_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 translator 抛错：按文案缺失处置（不得让渲染再抛）。"""
    register_error_code_records(ConcurrentStableList((_record(),)))
    _patch_translator(monkeypatch, _Translator(RuntimeError("boom")))
    response = await build_error_response(_scope(), BizError(390001))
    assert _body(response)["message"] == "部门不存在"


def test_real_translator_detects_placeholder_and_custom_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 translator 判定：空 / `null` 实现视为占位，自定义实现解析注册插件。"""
    assert errors_module._real_translator(_scope(provider="")) is None  # pyright: ignore[reportPrivateUsage]
    assert errors_module._real_translator(_scope(provider="null")) is None  # pyright: ignore[reportPrivateUsage]
    sentinel = _Translator()

    def _resolve_plugin(*args: object, **kwargs: object) -> _Translator:
        del args, kwargs
        return sentinel

    monkeypatch.setattr(errors_module, "resolve_plugin", _resolve_plugin)
    assert errors_module._real_translator(_scope(provider="custom")) is sentinel  # pyright: ignore[reportPrivateUsage]


async def test_missing_metrics_and_app_context_tolerated() -> None:
    """无指标器 / 无应用上下文：渲染照常完成（降级不抛）。"""
    response = await build_error_response(_scope(with_app=False), BizError(999999, "boom"))
    assert response.status_code == 200
    assert _body(response)["message"] == "boom"
    response = await build_error_response(_scope(metrics=None), BizError(999999, "boom"))
    assert response.status_code == 200


async def test_request_id_and_trace_headers() -> None:
    """响应头：回写请求 id 与链路 id（视图路径同样生效）。"""
    scope = _scope(trace_id="trace-1")
    cast("dict[str, object]", scope)["headers"] = [(b"x-request-id", b"req-9")]
    response = await build_error_response(scope, NotFoundError())
    assert response.headers["x-request-id"] == "req-9"
    assert response.headers["x-trace-id"] == "trace-1"

"""全局异常处理器集成测试（Kiwi 20）。"""

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.errors import register_exception_handlers

API = "/api/v1/demos"


@pytest.mark.kiwi_id(20)
async def test_not_found_returns_unified_response(client: AsyncClient) -> None:
    """资源不存在 → HTTP 404 + 统一响应 code=10002。"""
    resp = await client.get(f"{API}/9999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 10002
    assert body["data"] is None


@pytest.mark.kiwi_id(20)
async def test_validation_error_returns_param_error(client: AsyncClient) -> None:
    """参数校验失败 → 统一参数异常 code=10001。"""
    resp = await client.post(API, json={"name": ""})
    assert resp.status_code == 200
    assert resp.json()["code"] == 10001


@pytest.mark.kiwi_id(20)
async def test_request_id_header_echoed(client: AsyncClient) -> None:
    """`X-Request-Id` 请求头回写到响应头。"""
    resp = await client.get(f"{API}/9999", headers={"X-Request-Id": "abc123"})
    assert resp.headers.get("x-request-id") == "abc123"


@pytest.mark.kiwi_id(20)
async def test_uncaught_exception_returns_500_without_stack() -> None:
    """未捕获异常 → 500 统一响应，不泄露堆栈细节。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("secret-detail")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 10000
    assert body["data"] is None
    assert "secret-detail" not in resp.text

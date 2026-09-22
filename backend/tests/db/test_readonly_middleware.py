"""只读标记中间件与请求方法判定测试（Kiwi 984）。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from app.api.middleware import ReadOnlyMiddleware
from app.core.context import is_read_only
from app.db.routing import is_read_method


@pytest.mark.kiwi_id(984)
def test_is_read_method() -> None:
    """只读方法：GET / HEAD / OPTIONS 为只读，其余为写；大小写不敏感。"""
    assert is_read_method("GET") is True
    assert is_read_method("head") is True
    assert is_read_method("Options") is True
    assert is_read_method("POST") is False
    assert is_read_method(None) is False


@pytest.mark.kiwi_id(984)
async def test_middleware_sets_and_resets_marker() -> None:
    """中间件：请求内按方法设标记，请求结束复位。"""
    app = FastAPI()
    app.add_middleware(ReadOnlyMiddleware)

    @app.get("/ro")
    async def _ro() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ro": is_read_only()}

    @app.post("/rw")
    async def _rw() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ro": is_read_only()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/ro")).json() == {"ro": True}
        assert (await client.post("/rw")).json() == {"ro": False}
    assert is_read_only() is False


@pytest.mark.kiwi_id(984)
async def test_middleware_passthrough_non_http() -> None:
    """非 HTTP 作用域直通（不设只读标记）。"""
    seen: list[str] = []

    async def _app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(str(scope["type"]))

    async def _receive() -> Message:
        return {"type": "lifespan.startup"}

    async def _send(message: Message) -> None:
        del message

    middleware = ReadOnlyMiddleware(_app)
    await middleware({"type": "lifespan"}, _receive, _send)
    assert seen == ["lifespan"]

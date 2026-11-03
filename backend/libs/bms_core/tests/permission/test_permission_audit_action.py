"""权限依赖记录审计动作码护栏（06_01）：校验前写入请求态、拒绝亦留痕。"""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.responses import JSONResponse

from bms_core.permission import base as permission_base
from bms_core.permission.base import require_permission

pytestmark = pytest.mark.kiwi_id(2407)


class _Checker:
    """权限检查器替身（无 `aprepare`，仅实现 require）。"""

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed

    def require(self, code: str) -> None:
        """按预设放行 / 拒绝。"""
        if not self.allowed:
            raise PermissionError(code)


def _install_checker(monkeypatch: pytest.MonkeyPatch, *, allowed: bool) -> None:
    """替换全局权限检查器（替身按鸭子类型放宽，避开 lambda 未知参数告警）。"""
    checker: Any = _Checker(allowed=allowed)

    def provider(_request: Request) -> Any:
        return checker

    monkeypatch.setattr(permission_base, "get_permission_checker", provider)


def _app(*, allowed: bool) -> FastAPI:
    """构造带权限依赖的测试应用。"""
    app = FastAPI()

    @app.get("/api/v1/protected")
    async def protected(
        request: Request,
        _: Annotated[None, Depends(require_permission("user:create"))],
    ) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"action": request.scope["state"]["audit_action"]})

    @app.exception_handler(PermissionError)
    async def _denied(request: Request, exc: PermissionError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"code": 30001, "message": str(exc)}, status_code=403)

    return app


async def test_permission_dependency_records_action_without_aprepare(monkeypatch: pytest.MonkeyPatch) -> None:
    """检查器无 `aprepare` 时跳过预加载，仍记录动作码并放行。"""
    _install_checker(monkeypatch, allowed=True)
    async with AsyncClient(transport=ASGITransport(app=_app(allowed=True)), base_url="http://test") as client:
        response = await client.get("/api/v1/protected")
    assert response.status_code == 200
    assert response.json() == {"action": "user:create"}


async def test_permission_denied_still_records_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """拒绝时请求态仍留有动作码（便于审计拒绝尝试）。"""
    _install_checker(monkeypatch, allowed=False)
    scope: dict[str, Any] = {  # bare-collections:allow（ASGI scope）
        "type": "http",
        "method": "GET",
        "path": "/api/v1/protected",
        "state": {},
    }
    request = Request(scope)
    dependency = require_permission("user:create")
    with pytest.raises(PermissionError):
        await dependency(request)
    assert scope["state"]["audit_action"] == "user:create"

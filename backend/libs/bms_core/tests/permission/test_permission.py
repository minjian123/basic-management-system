"""权限校验基座契约测试（Kiwi 39）：继承 / 恒定允许 / 强制校验 / 依赖工厂与解析。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api.errors import register_exception_handlers
from bms_core.core import plugin as plugin_module
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import PermissionError
from bms_core.core.plugin import PluginRegistry
from bms_core.permission.base import BasePermissionChecker, get_permission_checker, require_permission
from bms_core.permission.null import NullPermissionChecker


class DenyChecker(BasePermissionChecker):
    """测试用拒绝实现：一律不持权限码。"""

    def check(self, code: str) -> bool:
        """恒定拒绝。

        Args:
            code: 权限码（本实现不校验）。

        Returns:
            bool: False。
        """
        return False


def _build_app(checker: BasePermissionChecker, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """构造带权限校验路由的测试应用（隔离注册表 + 配置解析注入测试检查器）。

    Args:
        checker: 测试检查器（登记为 provider `test`）。
        monkeypatch: pytest 补丁夹具。

    Returns:
        FastAPI: 测试应用实例。
    """
    registry = PluginRegistry()
    registry.register("permission", "test", lambda: checker)
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    app = FastAPI()
    app.state.settings = Settings(permission=PluginSelection(provider="test"))
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected(_: Annotated[None, Depends(require_permission("data:plain"))]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    @app.get("/checker")
    async def checker_key(c: Annotated[BasePermissionChecker, Depends(get_permission_checker)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"key": c.key}

    return app


@pytest.mark.kiwi_id(39)
def test_inheritance_and_key() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BasePermissionChecker, BaseCapability)
    assert issubclass(NullPermissionChecker, BasePermissionChecker)
    assert issubclass(NullPermissionChecker, BaseNullObject)
    assert BasePermissionChecker.key == "permission"


@pytest.mark.kiwi_id(39)
def test_null_checker_allows() -> None:
    """占位检查器恒定允许（不读权限数据）。"""
    checker = NullPermissionChecker()
    assert checker.placeholder is True
    assert "占位实现" in checker.describe()
    assert checker.check("data:plain") is True
    assert checker.require("data:plain") is None


@pytest.mark.kiwi_id(39)
def test_require_raises_permission_error() -> None:
    """拒绝实现下强制校验抛 PermissionError（30001 / 403）。"""
    with pytest.raises(PermissionError) as excinfo:
        DenyChecker().require("data:plain")
    assert excinfo.value.code == 30001
    assert excinfo.value.http_status == 403


@pytest.mark.kiwi_id(39)
async def test_require_permission_dependency_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖工厂：占位检查器下放行，检查器可经依赖解析取到。"""
    app = _build_app(NullPermissionChecker(), monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        protected = await client.get("/protected")
        assert protected.status_code == 200
        assert protected.json() == {"ok": True}

        checker = await client.get("/checker")
        assert checker.json() == {"key": "permission"}


@pytest.mark.kiwi_id(39)
async def test_require_permission_dependency_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖工厂：拒绝实现下返回 403 统一响应（code 30001）。"""
    app = _build_app(DenyChecker(), monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/protected")
        assert resp.status_code == 403
        body = resp.json()
        assert body["code"] == 30001
        assert body["data"] is None

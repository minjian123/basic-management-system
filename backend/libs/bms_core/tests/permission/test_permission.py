"""权限校验基座契约测试（Kiwi 39）：继承 / 恒定允许 / 强制校验 / 依赖工厂与解析。"""

from typing import Annotated, Any, cast

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
from bms_core.permission import guard as guard_module
from bms_core.permission.base import (
    BasePermissionChecker,
    get_permission_checker,
    prepare_permission_dependency,
    require_permission,
)
from bms_core.permission.guard import (
    BasePermissionGuard,
    PermissionGuardContext,
    guards_allow,
    register_permission_guard,
    registered_permission_guards,
    reset_permission_guards,
)
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
    async def protected(_: Annotated[None, Depends(require_permission("data:plain"))]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]  # bare-collections:allow（FastAPI 端点返回注解）
        return {"ok": True}

    @app.get("/checker")
    async def checker_key(c: Annotated[BasePermissionChecker, Depends(get_permission_checker)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]  # bare-collections:allow（FastAPI 端点返回注解）
        return {"key": c.key}

    @app.get("/prepared")
    async def prepared_only(_: Annotated[None, Depends(prepare_permission_dependency())]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]  # bare-collections:allow（FastAPI 端点返回注解）
        """仅预加载、不校验的端点（逐码自行判定的消费面，如 `/api/v1/menus/my`）。

        Returns:
            dict[str, bool]: 固定响应。
        """
        return {"ok": True}

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


@pytest.mark.kiwi_id(2320)
async def test_prepare_permission_dependency_only_preloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """仅预加载依赖：不校验权限码（未持码亦放行），供逐码自行判定的端点复用。"""
    app = _build_app(DenyChecker(), monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/prepared")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


@pytest.mark.kiwi_id(39)
def test_guard_registry_skips_empty_slot_and_resets() -> None:
    """校验链注册表：空值槽位跳过（不经公开登记通道）；清空后为空链且空链恒通过。"""

    class _AllowGuard(BasePermissionGuard):
        """恒定放行的校验环节替身。"""

        key = "unit_allow_guard"

        def allow(self, context: PermissionGuardContext) -> bool:
            """恒定放行。

            Args:
                context: 校验上下文（本实现不校验）。

            Returns:
                bool: True。
            """
            del context
            return True

    reset_permission_guards()
    try:
        register_permission_guard(_AllowGuard())
        guard_module._GUARDS.set("ghost", cast("Any", None))  # pyright: ignore[reportPrivateUsage]
        assert [guard.key for guard in registered_permission_guards()] == ["unit_allow_guard"]
        assert guards_allow(PermissionGuardContext(code="data:plain")) is True
    finally:
        reset_permission_guards()
    assert registered_permission_guards() == ()
    assert guards_allow(PermissionGuardContext(code="data:plain")) is True

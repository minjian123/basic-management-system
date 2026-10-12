"""默认路由登记表便捷入口用例（`bms_core/api/base.py`）：取用 / 登记 / 统一前缀聚合并挂载。"""

from __future__ import annotations

from bms_core.api.base import API_PREFIX, BaseRouter, build_api_router, register_router, router_registry


def test_default_router_registry_helpers() -> None:
    """默认登记表：取用单例、登记路由并按统一前缀聚合挂载。"""
    assert router_registry() is not None

    router = BaseRouter(key="unit_probe_router", prefix="/unit-probe", tags=("unit-probe",))

    @router.get("/ping")
    async def _ping() -> None:  # pyright: ignore[reportUnusedFunction]
        """探针端点（占位，供挂载断言）。"""

    register_router(router)
    parent = build_api_router(prefix=API_PREFIX)
    assert len(parent.routes) == 1

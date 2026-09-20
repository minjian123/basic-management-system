"""接口路由基座契约测试（Kiwi 779）：基类继承 / 默认响应 / 注册唯一性 / 统一挂载 / 参数绑定 / 鉴权占位。"""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.base import (
    API_PREFIX,
    DEFAULT_RESPONSES,
    BaseRouter,
    RouterRegistry,
    cursor_query,
    page_query,
    require_auth,
    router_registry,
    sort_query,
)
from app.core.base import BaseObject
from app.core.exceptions import ConflictError
from app.main import ApplicationFactory
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.schemas.sorting import BaseSortQuery


class _ProbeRouter(BaseRouter):
    """测试用路由子类（标识取类属性）。"""

    key: str = "probe"


@pytest.mark.kiwi_id(779)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链、路由标识与元信息。"""
    assert issubclass(BaseRouter, APIRouter)
    assert issubclass(BaseRouter, BaseObject)
    assert issubclass(RouterRegistry, BaseObject)

    router = _ProbeRouter()
    assert router.key == "probe"
    assert router.describe() == "probe（0 条路由）"

    assert BaseRouter(key="demo").key == "demo"


@pytest.mark.kiwi_id(779)
def test_default_responses_merge_and_override() -> None:
    """默认错误响应合并；调用方同名状态码覆盖默认。"""
    default_router = BaseRouter(key="a")
    for status in DEFAULT_RESPONSES:
        assert status in default_router.responses

    override = BaseRouter(key="b", responses={404: {"description": "自定义"}})
    assert override.responses[404]["description"] == "自定义"

    exempt = BaseRouter(key="c", default_responses=False, responses={400: {"description": "x"}})
    assert 401 not in exempt.responses
    assert exempt.responses[400]["description"] == "x"


@pytest.mark.kiwi_id(779)
def test_registry_register_uniqueness_and_order() -> None:
    """登记唯一性（同 key 拒重）与保序。"""
    registry = RouterRegistry()
    first = BaseRouter(key="one")
    second = BaseRouter(key="two")
    registry.register(first)
    registry.register(second)

    assert registry.keys() == ("one", "two")
    assert registry.routers() == (first, second)
    assert registry.get("one") is first
    assert registry.get("missing") is None

    with pytest.raises(ConflictError):
        registry.register(BaseRouter(key="one"))


@pytest.mark.kiwi_id(779)
async def test_unified_mount_and_prefix() -> None:
    """统一挂载：应用默认登记表挂到 /api/v1；自定义注册表经 mount 挂到指定前缀。"""
    app = ApplicationFactory().create(None)
    paths = set(app.openapi()["paths"])
    assert API_PREFIX + "/demos" in paths
    assert API_PREFIX + "/modules" in paths
    assert API_PREFIX + "/plugins" in paths
    assert router_registry().keys() == (
        "demo",
        "modules",
        "plugins",
        "preference",
        "query_scheme",
        "notification",
        "chat",
        "search",
        "org",
        "dict",
        "file",
    )

    router = BaseRouter(key="probe", prefix="/probe")

    @router.get("/ping")
    async def _ping() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    registry = RouterRegistry()
    registry.register(router)
    parent = APIRouter()
    registry.mount(parent, prefix="/custom")
    probe_app = FastAPI()
    probe_app.include_router(parent)
    async with AsyncClient(transport=ASGITransport(app=probe_app), base_url="http://test") as client:
        resp = await client.get("/custom/probe/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


@pytest.mark.kiwi_id(779)
async def test_parameter_binding_factories() -> None:
    """分页 / 排序 / 游标参数绑定工厂回带请求契约。"""
    app = FastAPI()
    router = BaseRouter(key="bind", prefix="/bind")

    @router.get("/page")
    async def _page(query: Annotated[BasePageQuery, Depends(page_query)]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return query.model_dump(mode="json")

    @router.get("/sort")
    async def _sort(query: Annotated[BaseSortQuery, Depends(sort_query)]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return query.model_dump(mode="json")

    @router.get("/cursor")
    async def _cursor(query: Annotated[BaseCursorQuery, Depends(cursor_query)]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return query.model_dump(mode="json")

    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = (await client.get("/bind/page", params={"page": 2, "size": 5, "order_by": "status,created_at"})).json()
        assert page["page"] == 2
        assert page["size"] == 5
        assert page["order_by"] == "status,created_at"

        sort = (await client.get("/bind/sort", params={"order_by": "id", "order": ["asc"]})).json()
        assert sort["order_by"] == "id"
        assert sort["order"] == ["asc"]

        cursor = (await client.get("/bind/cursor", params={"cursor": "c1", "limit": 3})).json()
        assert cursor["cursor"] == "c1"
        assert cursor["limit"] == 3


@pytest.mark.kiwi_id(779)
async def test_unified_response_and_error(client: AsyncClient) -> None:
    """统一响应包裹与业务异常转 404 统一响应（路径前缀经基座挂载不变）。"""
    ok = await client.get(f"{API_PREFIX}/demos")
    assert ok.status_code == 200
    assert ok.json() == {"code": 0, "message": "ok", "data": []}

    missing = await client.get(f"{API_PREFIX}/demos/999")
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002


@pytest.mark.kiwi_id(779)
async def test_auth_placeholder_dependency() -> None:
    """鉴权占位：require_auth 恒定放行、可作路由级依赖。"""
    assert require_auth() is None

    app = FastAPI()
    router = BaseRouter(key="guarded", prefix="/guarded", dependencies=[Depends(require_auth)])

    @router.get("/ping")
    async def _ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/guarded/ping")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

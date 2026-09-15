"""归档策略基座契约测试（Kiwi 58）：契约 / 标识 / 常量 / 结果契约 / 占位不归档与在线库 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_archive_policy, get_archive_query_router
from app.archive.base import ARCHIVE_LOCATIONS, ArchiveResult, BaseArchivePolicy, BaseArchiveQueryRouter
from app.archive.null import NullArchivePolicy, NullArchiveQueryRouter
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app, lifespan


@pytest.mark.kiwi_id(58)
def test_inheritance_and_keys() -> None:
    """两契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseArchivePolicy, BaseCapability)
    assert issubclass(NullArchivePolicy, BaseArchivePolicy)
    assert issubclass(NullArchivePolicy, BaseNullObject)
    assert BaseArchivePolicy.key == "archive_policy"

    assert issubclass(BaseArchiveQueryRouter, BaseCapability)
    assert issubclass(NullArchiveQueryRouter, BaseArchiveQueryRouter)
    assert issubclass(NullArchiveQueryRouter, BaseNullObject)
    assert BaseArchiveQueryRouter.key == "archive_query_router"

    for placeholder in (NullArchivePolicy(), NullArchiveQueryRouter()):
        assert placeholder.placeholder is True
        assert "占位实现" in placeholder.describe()


@pytest.mark.kiwi_id(58)
def test_constants() -> None:
    """数据位置清单常量。"""
    assert ARCHIVE_LOCATIONS == ("online", "archive")


@pytest.mark.kiwi_id(58)
def test_result_defaults_and_frozen() -> None:
    """`ArchiveResult` 默认值与不可变。"""
    result = ArchiveResult(matched=0, archived=0)
    assert result.detail is None

    field = "archived"
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, 1)


@pytest.mark.kiwi_id(58)
async def test_null_policy_never_archives() -> None:
    """占位策略恒定不归档（不搬数据）。"""
    policy = NullArchivePolicy()
    assert await policy.matches({"id": 1}) is False
    assert await policy.archive([{"id": 1}]) == ArchiveResult(matched=0, archived=0)


@pytest.mark.kiwi_id(58)
def test_null_router_online() -> None:
    """占位查询路由恒定在线库。"""
    router = NullArchiveQueryRouter()
    assert router.resolve(table="sys_user") == "online"


@pytest.mark.kiwi_id(58)
async def test_dependency_providers_resolve() -> None:
    """依赖解析：应用装配两占位单例；路由经两提供者取到同一实例。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.archive_policy, NullArchivePolicy)
        assert isinstance(app.state.archive_query_router, NullArchiveQueryRouter)

        @app.get("/archive-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            policy: Annotated[BaseArchivePolicy, Depends(get_archive_policy)],
            router: Annotated[BaseArchiveQueryRouter, Depends(get_archive_query_router)],
        ) -> dict[str, object]:
            result = await policy.archive([])
            return {
                "policy_key": policy.key,
                "archived": result.archived,
                "router_key": router.key,
                "loc": router.resolve(table="t"),
            }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/archive-probe")

        assert resp.status_code == 200
        assert resp.json() == {
            "policy_key": "archive_policy",
            "archived": 0,
            "router_key": "archive_query_router",
            "loc": "online",
        }

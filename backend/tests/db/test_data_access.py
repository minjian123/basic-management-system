"""数据访问底座测试（Kiwi 25）：引擎 / 会话 / 只读标记 / 乐观锁 / 分页。"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import Settings
from app.core.context import is_read_only, reset_read_only, set_read_only
from app.core.exceptions import ConcurrentConflictError
from app.db.engine import EngineFactory
from app.db.session import build_session_factory, get_db
from app.repositories.base_memory_repository import BaseMemoryRepository
from app.schemas.pagination import BaseCursorQuery, BasePageQuery
from app.services.base_service import BaseService


@dataclass
class Item:
    """测试实体。"""

    id: int
    name: str


class ItemRepository(BaseMemoryRepository[Item]):
    """测试仓储：只实现构造钩子。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Item:
        return Item(id=item_id, name=str(values["name"]))

    def _apply(self, item: Item, values: dict[str, object]) -> Item:
        return Item(id=item.id, name=str(values["name"]))

    def binding_default(self) -> str:
        """暴露默认（上下文）数据源绑定钩子。"""
        return self._resolve_binding()

    def guard(self) -> AbstractAsyncContextManager[None]:
        """暴露乐观锁转译上下文。"""
        return self._guard_version()


def _memory_settings() -> Settings:
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    return settings


@pytest.mark.kiwi_id(25)
async def test_engine_factory_creates_and_caches() -> None:
    """引擎工厂：创建并缓存；覆盖平台 / 归档 / 租户分支；不建连；可释放。"""
    factory = EngineFactory(_memory_settings())
    engine = factory.create("platform")
    assert isinstance(engine, AsyncEngine)
    assert factory.create("platform") is engine
    assert isinstance(factory.create("archive"), AsyncEngine)
    assert isinstance(factory.create("tenant_demo"), AsyncEngine)
    await factory.aclose()

    server_settings = Settings()
    server_settings.database.platform.url = "postgresql+psycopg://user@localhost/bms"
    server_factory = EngineFactory(server_settings)
    assert isinstance(server_factory.create("platform"), AsyncEngine)
    await server_factory.aclose()


@pytest.mark.kiwi_id(25)
async def test_session_factory_and_get_db_dependency() -> None:
    """会话工厂产出会话；get_db 依赖可用。"""
    factory = EngineFactory(_memory_settings())
    engine = factory.create("platform")
    session_factory = build_session_factory(engine)
    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        assert (await session.execute(text("SELECT 1"))).scalar() == 1

    app = FastAPI()
    app.state.engine_factory = factory

    @app.get("/db")
    async def read(session: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"value": (await session.execute(text("SELECT 1"))).scalar() or 0}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/db")
        assert resp.status_code == 200
        assert resp.json() == {"value": 1}
    await factory.aclose()


@pytest.mark.kiwi_id(25)
def test_read_only_context_marker() -> None:
    """只读标记：设置 / 读取 / 复位；绑定钩子读取上下文。"""
    repo = ItemRepository()
    assert is_read_only() is False
    assert repo.binding_default() == "default"
    token = set_read_only()
    assert is_read_only() is True
    assert repo.binding_default() == "default"
    reset_read_only(token)
    assert is_read_only() is False


@pytest.mark.kiwi_id(25)
async def test_version_guard_translates_conflict() -> None:
    """乐观锁转译：StaleDataError → ConcurrentConflictError。"""
    with pytest.raises(ConcurrentConflictError):
        async with ItemRepository().guard():
            raise StaleDataError("版本冲突")


@pytest.mark.kiwi_id(25)
async def test_pagination_page_and_cursor() -> None:
    """分页：页码切片与游标推进。"""
    service = BaseService(ItemRepository())
    for name in ["甲", "乙", "丙", "丁", "戊"]:
        await service.create(name=name)

    page = await service.page(BasePageQuery(page=2, size=2))
    assert [item.name for item in page.list] == ["丙", "丁"]
    assert (page.total, page.page, page.size) == (5, 2, 2)

    first = await service.cursor_page(BaseCursorQuery(limit=2))
    assert [item.name for item in first.list] == ["甲", "乙"]
    assert first.has_more is True
    assert first.next_cursor == "2"

    last = await service.cursor_page(BaseCursorQuery(cursor="4", limit=2))
    assert [item.name for item in last.list] == ["戊"]
    assert last.has_more is False
    assert last.next_cursor is None

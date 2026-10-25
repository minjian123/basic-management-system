"""查询方案真实存储用例（Kiwi 963，02-4-27）：落库 CRUD / 三级默认解析 / 个人方案 owner 过滤。

测试库：临时 SQLite 文件（按 `platform:tenant` 链表集幂等建表）。
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.orm.exc import StaleDataError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ConcurrentConflictError, NotFoundError
from bms_core.db.bootstrap import apply_unit_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.listing.base import QueryScheme, QuerySchemeScope, QuerySchemeTarget
from bms_core.listing.store import SqlQuerySchemeStore, _to_scheme  # pyright: ignore[reportPrivateUsage]


def _build_schema(url: str) -> None:
    """对目标库幂等建 `platform:tenant` 链表集（与启动期 / `ops.init_schema` 同一表集派生点）。

    Args:
        url: 数据库 URL。
    """
    asyncio.run(apply_unit_schema("platform", "tenant", url, target="listing_test"))


@contextmanager
def _as_user(user_id: int | None) -> Generator[None]:
    """切换当前用户上下文（个人方案归属）。

    Args:
        user_id: 用户 ID（None 表示未登录）。

    Yields:
        None: 作用域内用户生效。
    """
    token = current_user_id.set(user_id)
    try:
        yield
    finally:
        current_user_id.reset(token)


_OPEN_ENGINES: ConcurrentStableList[EngineRegistry] = ConcurrentStableList()
"""用例内构造的引擎注册表（用例结束统一 `aclose`，避免连接在事件循环关闭后被 GC）。"""


@pytest.fixture(autouse=True)
async def _close_open_engines() -> AsyncIterator[None]:  # pyright: ignore[reportUnusedFunction]
    """用例结束释放本模块内构造的引擎注册表。

    Yields:
        None: 用例运行期。
    """
    yield
    for registry in list(_OPEN_ENGINES):
        await registry.aclose()
    _OPEN_ENGINES.clear()


@pytest.fixture
def scheme_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SqlQuerySchemeStore]:
    """临时库 + 查询方案真实存储。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        SqlQuerySchemeStore: 存储实例。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'scheme_test.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    _build_schema(url)
    registry = EngineRegistry(EngineFactory(get_settings()))
    _OPEN_ENGINES.add(registry)
    store = SqlQuerySchemeStore(engines=registry)
    yield store
    get_settings.cache_clear()


@pytest.mark.kiwi_id(963)
async def test_query_scheme_crud_and_default_resolution(scheme_store: SqlQuerySchemeStore) -> None:
    """方案 CRUD 与三级默认解析（个人 > 租户 > 平台）与 owner 过滤。"""
    with _as_user(1001):
        personal = await scheme_store.save(
            QueryScheme(
                name="我的常用",
                scope=QuerySchemeScope.USER,
                target=QuerySchemeTarget.ITEMS,
                data_source_key="region",
                conditions=ConcurrentStableDict({"logic": "AND", "children": []}),
                is_default=True,
            )
        )
        assert personal.id is not None
        listed = await scheme_store.list(QuerySchemeTarget.ITEMS)
        assert [scheme.name for scheme in listed] == ["我的常用"]
        resolved = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved is not None
        assert resolved.name == "我的常用"

        platform = await scheme_store.save(
            QueryScheme(
                name="平台默认",
                scope=QuerySchemeScope.PLATFORM,
                target=QuerySchemeTarget.ITEMS,
                data_source_key="region",
                is_default=True,
            )
        )
        assert platform.id is not None
        # 个人优先于平台
        resolved2 = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved2 is not None
        assert resolved2.name == "我的常用"
        # 更新（乐观锁正常路径）与删除
        personal.name = "我的常用改"
        updated = await scheme_store.save(personal)
        assert updated.name == "我的常用改"
        assert await scheme_store.get(personal.id or 0) is not None
        assert await scheme_store.delete(personal.id or 0) is True
        assert await scheme_store.get(personal.id or 0) is None

    with _as_user(2002):
        # 他人个人方案不可见；平台方案可见
        listed_other = await scheme_store.list(QuerySchemeTarget.ITEMS)
        assert [scheme.name for scheme in listed_other] == ["平台默认"]
        resolved_other = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS)
        assert resolved_other is not None
        assert resolved_other.name == "平台默认"


async def test_query_scheme_field_key_filters_and_missing_paths(scheme_store: SqlQuerySchemeStore) -> None:
    """`field_key` 过滤、更新不存在方案拒 10002、删除不存在返 False、无默认方案返 None。"""
    with _as_user(1001):
        await scheme_store.save(
            QueryScheme(
                name="带字段键",
                scope=QuerySchemeScope.USER,
                target=QuerySchemeTarget.ITEMS,
                data_source_key="region",
                field_key="purchase_order",
                is_default=True,
            )
        )
        by_field = await scheme_store.list(QuerySchemeTarget.ITEMS, field_key="purchase_order")
        assert [scheme.name for scheme in by_field] == ["带字段键"]
        assert await scheme_store.list(QuerySchemeTarget.ITEMS, field_key="absent") == ()
        resolved = await scheme_store.resolve_default(QuerySchemeTarget.ITEMS, field_key="purchase_order")
        assert resolved is not None and resolved.name == "带字段键"
        assert await scheme_store.resolve_default(QuerySchemeTarget.ITEMS, field_key="absent") is None

    with pytest.raises(NotFoundError):
        await scheme_store.save(
            QueryScheme(
                id=987654321,
                name="不存在",
                scope=QuerySchemeScope.USER,
                target=QuerySchemeTarget.ITEMS,
                data_source_key="region",
            )
        )
    assert await scheme_store.delete(987654321) is False


def test_to_scheme_falls_back_on_invalid_scope() -> None:
    """非法作用域取值回落个人作用域。"""
    row = SimpleNamespace(
        id=1,
        name="异常方案",
        scope="bogus",
        owner_id=None,
        target="items",
        data_source_key="region",
        field_key=None,
        provider_key=None,
        conditions=None,
        params=None,
        layout=None,
        is_default=False,
        shared=False,
        status="enabled",
    )
    assert _to_scheme(cast("Any", row)).scope is QuerySchemeScope.USER


class _StaleSession:
    """会话替身：登记新增后提交即报乐观锁冲突。"""

    def add(self, row: object) -> None:
        """登记新增行（占位）。

        Args:
            row: ORM 行。
        """
        del row

    async def commit(self) -> None:
        """提交即报乐观锁冲突。

        Raises:
            StaleDataError: 乐观锁冲突。
        """
        raise StaleDataError("stale")


@asynccontextmanager
async def _stale_scope(*args: object, **kwargs: object) -> AsyncGenerator[object]:
    """会话作用域替身：产出恒冲突会话。

    Args:
        args: 位置参数（忽略）。
        kwargs: 关键字参数（忽略）。

    Yields:
        object: 恒冲突会话替身。
    """
    del args, kwargs
    yield _StaleSession()


async def test_save_translates_stale_data_error(
    scheme_store: SqlQuerySchemeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """乐观锁冲突（`StaleDataError`）→ 10004 / 409 语义。"""
    monkeypatch.setattr("bms_core.listing.store.session_scope", _stale_scope)
    with pytest.raises(ConcurrentConflictError):
        await scheme_store.save(
            QueryScheme(
                name="冲突方案",
                scope=QuerySchemeScope.PLATFORM,
                target=QuerySchemeTarget.ITEMS,
                data_source_key="region",
            )
        )

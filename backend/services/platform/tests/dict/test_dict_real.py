"""字典真实取数 / 翻译 / 缓存 / 高级查询 / 写路径用例（Kiwi 963，02-4-27）。

覆盖：迁移建表与索引 / 种子幂等 / `by_type` 三态与过滤与 locale 回退与停用不可见 / `batch` 多类型合并 /
缓存版本比对与失效 / 翻译子集回填与未命中不占位 / 写路径 CRUD 与冲突与失效 / 高级查询（attrs / 条件引擎 /
business 提供者 / 非法条件拒绝）/ HTTP 端点（含 `Accept-Language`）/ Redis 字典缓存（fakeredis 注入）。

测试库：临时 SQLite 文件（跑 Alembic 首个迁移建表 + 幂等种子）。
"""

import sqlite3
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from bms_core.api.deps import (
    get_dict_query_service,
    get_dict_service,
    get_dict_source,
    get_dict_translator,
    get_query_provider_registry,
)
from bms_core.application import service_lifespan as lifespan
from bms_core.core.config import get_settings
from bms_core.core.exceptions import BizError, ParamError
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import BACKEND_ROOT
from bms_core.db.registry import EngineRegistry
from bms_core.dict.base import DictBatchQuery, DictQuery, DictTranslateQuery
from bms_core.dict.cache import MemoryDictCacheRegion, RedisDictCacheRegion
from bms_core.dict.models import SysDictItem, SysDictType
from bms_core.dict.providers import BuiltinDictQueryProvider
from bms_core.dict.query import DictAdvQueryPayload, DictQueryService
from bms_core.dict.seed import seed_dicts
from bms_core.dict.service import DictAttrPayload, DictItemPayload, DictService, DictTypePayload
from bms_core.dict.sql import SqlDictSource, SqlDictTranslator, current_dict_locale
from bms_core.query.local import LocalQueryProviderRegistry
from bms_platform.main import ApplicationFactory

EXPECTED_TABLES = {
    "sys_dict_type",
    "sys_dict_item",
    "sys_dict_type_i18n",
    "sys_dict_item_i18n",
    "sys_dict_attr",
    "sys_dict_attr_i18n",
    "sys_query_scheme",
}

EXPECTED_INDEXES = (
    "idx_dict_item_value",
    "idx_dict_item_parent_sort",
    "idx_dict_item_label",
)

EXPECTED_UNIQUE_CONSTRAINTS = (
    "uq_dict_item_code_deleted_at",
    "uq_dict_type_code_deleted_at",
    "uq_scheme_scope_name_deleted_at",
)


def _run_migrations(url: str) -> None:
    """对目标库执行 Alembic 首个迁移（同步入口；测试 fixture 调用）。

    Args:
        url: 数据库 URL。
    """
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))  # 绝对定位，与运行目录无关
    cfg.cmd_opts = SimpleNamespace(x=[f"url={url}"])  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(cfg, "head")


@pytest.fixture
def dict_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库：建库（迁移）+ 配置覆盖（真实实现 provider）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'dict_test.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    monkeypatch.setenv("BMS_DICT_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_DICT_TRANSLATOR__PROVIDER", "sql")
    monkeypatch.setenv("BMS_DICT_CACHE_REGION__PROVIDER", "memory")
    monkeypatch.setenv("BMS_QUERY_SCHEME_STORE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_FIELD_TYPE_REGISTRY__PROVIDER", "local")
    monkeypatch.setenv("BMS_QUERY_PROVIDER_REGISTRY__PROVIDER", "local")
    get_settings.cache_clear()
    _run_migrations(url)
    yield url
    get_settings.cache_clear()


@pytest.fixture
async def dict_client(dict_db_url: str) -> AsyncIterator[AsyncClient]:
    """装配真实实现的应用客户端（ASGITransport）。

    Args:
        dict_db_url: 测试库 URL（fixture 依赖触发建库）。

    Yields:
        AsyncClient: 应用客户端。
    """
    engine = create_async_engine(dict_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_dicts(session)
    await engine.dispose()
    app = ApplicationFactory().create(None)
    # 依赖覆盖：把真实实现绑定到当前测试库（插件工厂为进程级实例，跨测试创建多应用时不宜复用其 app 引用）
    engines = EngineRegistry(EngineFactory(get_settings()))
    source = SqlDictSource(engines=engines, cache=MemoryDictCacheRegion())
    translator = SqlDictTranslator(engines=engines, cache=source.cache)
    service = DictService(engines=engines, cache=source.cache)
    query_service = DictQueryService(engines=engines)
    registry = LocalQueryProviderRegistry()
    registry.register(BuiltinDictQueryProvider(engines=engines))
    app.dependency_overrides[get_dict_source] = lambda: source
    app.dependency_overrides[get_dict_translator] = lambda: translator
    app.dependency_overrides[get_dict_service] = lambda: service
    app.dependency_overrides[get_dict_query_service] = lambda: query_service
    app.dependency_overrides[get_query_provider_registry] = lambda: registry
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _engines() -> EngineRegistry:
    """构造引擎注册表（取覆盖后的配置）。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    return EngineRegistry(EngineFactory(get_settings()))


async def _seed(dict_db_url: str) -> None:
    """对测试库写入幂等种子。

    Args:
        dict_db_url: 测试库 URL。
    """
    engine = create_async_engine(dict_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_dicts(session)
    await engine.dispose()


@pytest.mark.kiwi_id(963)
def test_migration_creates_tables_and_indexes(dict_db_url: str) -> None:
    """迁移建表与索引：七表齐备、关键索引存在。"""
    db_path = dict_db_url.split("///")[-1]
    con = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        con.close()
    assert tables >= EXPECTED_TABLES
    for name in EXPECTED_INDEXES:
        assert name in indexes


@pytest.mark.kiwi_id(963)
async def test_seed_idempotent(dict_db_url: str) -> None:
    """种子幂等：首次新增 > 0，二次执行新增 0。"""
    engine = create_async_engine(dict_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            first = await seed_dicts(session)
        async with factory() as session:
            second = await seed_dicts(session)
    finally:
        await engine.dispose()
    assert first > 0
    assert second == 0


@pytest.mark.kiwi_id(963)
async def test_by_type_version_filters_locale_and_disabled(dict_db_url: str) -> None:
    """`by_type`：版本三态 / 关键字 / 按值子集 / 探针截断 / 级联父值 / locale 回退 / 停用不可见。"""
    await _seed(dict_db_url)
    cache = MemoryDictCacheRegion()
    source = SqlDictSource(engines=_engines(), cache=cache)

    first = await source.by_type(DictQuery(dict_type="user_status"))
    assert first.version >= 0
    assert first.items is not None
    assert [item.value for item in first.items] == ["enabled", "disabled"]
    assert first.total == 2

    current = await source.by_type(DictQuery(dict_type="user_status", version=first.version))
    assert current.items is None

    keyword = await source.by_type(DictQuery(dict_type="user_status", keyword="启"))
    assert keyword.items is not None
    assert [item.value for item in keyword.items] == ["enabled"]

    subset = await source.by_type(DictQuery(dict_type="user_status", values=("disabled",)))
    assert subset.items is not None
    assert [item.value for item in subset.items] == ["disabled"]

    probe = await source.by_type(DictQuery(dict_type="user_status", limit=1))
    assert probe.items is not None
    assert len(probe.items) == 1
    assert probe.has_more is True
    assert probe.total == 2

    top = await source.by_type(DictQuery(dict_type="region", parent_id=""))
    assert top.items is not None
    assert [item.value for item in top.items] == ["zj"]
    children = await source.by_type(DictQuery(dict_type="region", parent_id="zj"))
    assert children.items is not None
    assert [item.value for item in children.items] == ["hz"]

    token = current_dict_locale.set("en-US")
    try:
        localized = await source.by_type(DictQuery(dict_type="user_status"))
        assert localized.items is not None
        assert localized.items[0].label == "Enabled"
    finally:
        current_dict_locale.reset(token)

    service = DictService(engines=_engines(), cache=cache)
    item_id = (await _find_item_ids(dict_db_url, "user_status", ("disabled",)))["disabled"]
    await service.update_item(
        item_id,
        DictItemPayload(code="disabled", label="停用", value="disabled", status="disabled"),
    )
    after = await source.by_type(DictQuery(dict_type="user_status"))
    assert after.items is not None
    assert [item.value for item in after.items] == ["enabled"]


@pytest.mark.kiwi_id(963)
async def test_cache_version_invalidate_and_batch(dict_db_url: str) -> None:
    """缓存版本比对与失效（改条目后展示同步）+ `batch` 多类型合并与版本一致。"""
    await _seed(dict_db_url)
    cache = MemoryDictCacheRegion()
    engines = _engines()
    source = SqlDictSource(engines=engines, cache=cache)
    service = DictService(engines=engines, cache=cache)

    first = await source.by_type(DictQuery(dict_type="user_status"))
    assert first.items is not None
    cached = await cache.aget_type("demo", "zh-CN", "user_status")
    assert isinstance(cached, dict)
    assert cached["version"] == first.version

    batch = await source.batch(DictBatchQuery(types=("user_status", "user_gender")))
    assert batch.items["user_status"] is not None
    assert batch.items["user_gender"] is not None
    assert len(batch.items["user_gender"].items or ()) == 3
    again = await source.batch(DictBatchQuery(types=("user_status", "user_gender"), version=batch.version))
    assert again.items["user_status"] is None
    assert again.items["user_gender"] is None

    item_id = (await _find_item_ids(dict_db_url, "user_status", ("disabled",)))["disabled"]
    await service.update_item(
        item_id,
        DictItemPayload(code="disabled", label="已停用", value="disabled", status="disabled"),
    )
    after = await source.by_type(DictQuery(dict_type="user_status"))
    assert after.version == first.version + 1
    assert after.items is not None
    assert [item.value for item in after.items] == ["enabled"]


@pytest.mark.kiwi_id(963)
async def test_translate_subset_and_write_path(dict_db_url: str) -> None:
    """翻译子集回填（未命中不占位）+ 写路径 CRUD 与冲突。"""
    await _seed(dict_db_url)
    cache = MemoryDictCacheRegion()
    engines = _engines()
    translator = SqlDictTranslator(engines=engines, cache=cache)
    service = DictService(engines=engines, cache=cache)

    mapping = await translator.translate(DictTranslateQuery(dict_type="user_status", values=("enabled", "ghost")))
    assert mapping == {"enabled": "启用"}
    subset = await cache.avalue_subset("demo", "zh-CN", "user_status", ("enabled", "ghost"))
    assert subset == {"enabled": "启用"}

    created_type = await service.create_type(DictTypePayload(type="demo_status", name="演示状态"))
    assert created_type.id > 0
    with pytest.raises(BizError):
        await service.create_type(DictTypePayload(type="demo_status", name="重复"))
    item = await service.create_item(
        "demo_status",
        DictItemPayload(code="a", label="甲", value="a", color="success"),
    )
    with pytest.raises(BizError):
        await service.create_item("demo_status", DictItemPayload(code="a", label="重复", value="a"))
    updated = await service.update_item(item.id, DictItemPayload(code="a", label="甲改", value="a"))
    assert updated.label == "甲改"
    attr = await service.upsert_attr(
        "demo_status",
        DictAttrPayload(attr_key="score", name="分值", data_type="number"),
    )
    assert attr.id > 0
    await service.delete_attr(attr.id)
    await service.delete_item(item.id)
    await service.delete_type(created_type.id)


@pytest.mark.kiwi_id(963)
async def test_advanced_query_engine_and_provider(dict_db_url: str) -> None:
    """高级查询：attrs / 条件引擎（属性过滤 / 分页 / 非法拒绝）。"""
    await _seed(dict_db_url)
    engines = _engines()
    service = DictService(engines=engines, cache=MemoryDictCacheRegion())
    query_service = DictQueryService(engines=engines)

    attrs = await query_service.load_attrs("region")
    assert [attr.attr_key for attr in attrs] == ["level"]

    ids = await _find_item_ids(dict_db_url, "region", ("zj", "hz"))
    await service.update_item(ids["zj"], DictItemPayload(code="zj", label="浙江省", value="zj", attr_json={"level": 1}))
    await service.update_item(
        ids["hz"],
        DictItemPayload(code="hz", label="杭州市", value="hz", parent_id="zj", attr_json={"level": 2}),
    )

    result = await query_service.advanced_query(
        "region",
        DictAdvQueryPayload(
            conditions={"logic": "AND", "children": [{"field": "attr.level", "operator": "eq", "value": 1}]},
        ),
    )
    assert result.total == 1
    assert result.items[0].value == "zj"
    assert result.items[0].attr == {"level": 1}

    paged = await query_service.advanced_query("region", DictAdvQueryPayload(page=1, size=1))
    assert paged.total == 3
    assert len(paged.items) == 1

    with pytest.raises(ParamError):
        await query_service.advanced_query(
            "region",
            DictAdvQueryPayload(conditions={"logic": "AND", "children": [{"field": "attr.ghost", "operator": "eq"}]}),
        )
    with pytest.raises(ParamError):
        await query_service.advanced_query(
            "region",
            DictAdvQueryPayload(conditions={"logic": "AND", "children": [{"field": "value", "operator": "between"}]}),
        )


@pytest.mark.kiwi_id(963)
async def test_http_endpoints(dict_client: AsyncClient) -> None:
    """HTTP 端点：取数 / 版本一致 / 批量 / 属性 / 提供者 / 高级查询 / 写接口与失效 / locale。"""
    resp = await dict_client.get("/api/v1/dicts/user_status")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 2
    version = data["version"]

    same = await dict_client.get(f"/api/v1/dicts/user_status?version={version}")
    assert same.json()["data"]["items"] is None

    batch = await dict_client.post("/api/v1/dicts/batch", json={"types": ["user_status", "user_gender"]})
    assert batch.status_code == 200
    assert set(batch.json()["data"]["items"]) == {"user_status", "user_gender"}

    attrs = await dict_client.get("/api/v1/dicts/region/attrs")
    assert attrs.status_code == 200
    assert attrs.json()["data"][0]["attr_key"] == "level"

    providers = await dict_client.get("/api/v1/dicts/query-providers")
    assert providers.status_code == 200
    assert [item["key"] for item in providers.json()["data"]] == ["builtin"]

    adv = await dict_client.post(
        "/api/v1/dicts/biz_type/advanced-query",
        json={"target": "items", "conditions": {"logic": "AND", "children": []}, "page": 1, "size": 10},
    )
    assert adv.status_code == 200
    assert adv.json()["data"]["total"] == 3

    business = await dict_client.post(
        "/api/v1/dicts/biz_type/advanced-query",
        json={"target": "business", "provider": "builtin", "params": {"keyword": "采购"}},
    )
    assert business.status_code == 200
    assert business.json()["data"]["total"] == 1

    missing = await dict_client.post(
        "/api/v1/dicts/biz_type/advanced-query",
        json={"target": "business", "provider": "ghost"},
    )
    assert missing.status_code == 404

    localized = await dict_client.get("/api/v1/dicts/user_status", headers={"accept-language": "en-US"})
    assert localized.json()["data"]["items"][0]["label"] == "Enabled"

    created = await dict_client.post("/api/v1/dicts/types", json={"type": "http_demo", "name": "HTTP 演示"})
    assert created.status_code == 200
    type_id = created.json()["data"]["id"]
    item = await dict_client.post(
        "/api/v1/dicts/types/http_demo/items",
        json={"code": "x", "label": "项", "value": "x"},
    )
    assert item.status_code == 200
    item_id = item.json()["data"]["id"]
    after_write = await dict_client.get("/api/v1/dicts/http_demo")
    assert after_write.json()["data"]["version"] > version
    assert after_write.json()["data"]["total"] == 1
    updated = await dict_client.put(
        f"/api/v1/dicts/items/{item_id}",
        json={"code": "x", "label": "项改", "value": "x"},
    )
    assert updated.status_code == 200
    assert (await dict_client.get("/api/v1/dicts/http_demo")).json()["data"]["items"][0]["label"] == "项改"
    assert (await dict_client.delete(f"/api/v1/dicts/items/{item_id}")).status_code == 200
    assert (await dict_client.delete(f"/api/v1/dicts/types/{type_id}")).status_code == 200


@pytest.mark.kiwi_id(963)
async def test_plugin_wiring_resolves_sql_provider(dict_db_url: str) -> None:
    """装配接线：`dict_source` / `dict_translator` / `dict_cache_region` 按配置解析到真实实现。

    注：插件工厂为进程级登记实例，多应用场景下其 `app` 引用可能来自首次装配（测试隔离由依赖覆盖承担）；
    本用例只断言装配解析结果（类型与 provider 名），不访问数据库。
    """
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert app.state.plugin_providers["dict_source"] == "sql"
        assert app.state.plugin_providers["dict_translator"] == "sql"
        assert app.state.plugin_providers["dict_cache_region"] == "memory"
        assert isinstance(app.state.dict_source, SqlDictSource)
        assert isinstance(app.state.dict_translator, SqlDictTranslator)
        assert isinstance(app.state.dict_cache_region, MemoryDictCacheRegion)


@pytest.mark.kiwi_id(963)
async def test_redis_cache_region_with_fake_client() -> None:
    """Redis 字典缓存（fakeredis 注入）：类型 key 读写、版本 INCR、子集、失效、锁。"""
    fakeredis = pytest.importorskip("fakeredis")
    from bms_core.cache.redis import RedisCacheRegion

    sync_client = fakeredis.FakeRedis(decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    region = RedisDictCacheRegion(
        redis_region=RedisCacheRegion(domain="dict", sync_client=sync_client, async_client=async_client)
    )
    await region.aset_type(None, "zh-CN", "user_status", {"version": 1, "items": []})
    assert await region.aget_type(None, "zh-CN", "user_status") == {"version": 1, "items": []}
    assert await region.aincrease_version(None) == 1
    assert await region.aincrease_version(None) == 2
    assert await region.aversion(None) == 2
    await region.aset_value_subset(None, "zh-CN", "user_status", {"enabled": "启用"})
    assert await region.avalue_subset(None, "zh-CN", "user_status", ("enabled",)) == {"enabled": "启用"}
    await region.adrop_type(None, "zh-CN", "user_status")
    assert await region.aget_type(None, "zh-CN", "user_status") is None
    token = "t1"
    assert await region.alock(None, "zh-CN", "user_status", token) is True
    assert await region.alock(None, "zh-CN", "user_status", "t2") is False
    assert await region.arelease_lock(None, "zh-CN", "user_status", token) is True


async def _find_item_ids(db_url: str, dict_type: str, values: tuple[str, ...]) -> dict[str, int]:
    """按类型 + value 批量查条目 ID（测试辅助）。

    Args:
        db_url: 数据库 URL。
        dict_type: 字典类型码。
        values: 条目值序列。

    Returns:
        dict[str, int]: value → ID。
    """
    engine = create_async_engine(db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            type_row = (
                await session.execute(select(SysDictType).where(SysDictType.type == dict_type))
            ).scalar_one_or_none()
            assert type_row is not None
            rows = (
                await session.execute(
                    select(SysDictItem).where(
                        SysDictItem.type_id == type_row.id,
                        SysDictItem.value.in_(values),
                        SysDictItem.deleted_at.is_(None),
                    )
                )
            ).scalars()
            return {row.value: row.id for row in rows}
    finally:
        await engine.dispose()

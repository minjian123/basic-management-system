"""config 域运行期用例（Kiwi 2207，03_08）：SQL 取数 / 写失效 / 缓存域 / HTTP 取数。

测试库：共享租户库（`tenant_db`）。写入的配置键按命名空间生成，用例结束删除本用例自造行，
不清理他人数据；读断言只认本命名空间的键。

覆盖：`SqlConfigSource` 命中·未命中·缓存回源·DB 异常降级 / `ConfigService.set`·`drop` 后缓存失效
即时生效 / `HttpConfigSource` 契约调用与降级 / 内存与 Redis 缓存域 key 与版本 /
`NullConfigSource` 恒空 / `BaseConfigSource.get` 默认。
"""

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion, RedisConfigCacheRegion
from bms_core.config.http import HttpConfigSource
from bms_core.config.models import SysConfig
from bms_core.config.null import NullConfigCacheRegion, NullConfigSource
from bms_core.config.service import ConfigService
from bms_core.config.sql import SqlConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.testing.namespace import Namespace

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


def _engines() -> EngineRegistry:
    """构造引擎注册表（取覆盖后的配置）。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    registry = EngineRegistry(EngineFactory(get_settings()))
    _OPEN_ENGINES.add(registry)
    return registry


def _broken_engines() -> EngineRegistry:
    """构造指向不可达库的引擎注册表（触发 DB 异常降级）。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    settings = get_settings().model_copy(deep=True)
    settings.database.tenants.url = "sqlite+aiosqlite" + ":////nonexistent-dir/config_broken.db"
    registry = EngineRegistry(EngineFactory(settings))
    _OPEN_ENGINES.add(registry)
    return registry


@pytest.fixture
async def config_keys(
    shared_tenant_engine: AsyncEngine,
    tenant_db: str,
    ns: Namespace,
) -> AsyncIterator[ConcurrentStableDict[str, str]]:
    """在共享租户库写入本用例自造的配置行（用例结束删除）。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        tenant_db: 租户库连接串（夹具副作用：注入配置并重置单例）。
        ns: 本用例命名空间。

    Yields:
        ConcurrentStableDict[str, str]: 本用例自造的参数键 → 值。
    """
    del tenant_db
    keys: ConcurrentStableDict[str, str] = ConcurrentStableDict(
        {ns.code("threshold"): "3", ns.code("channel"): "false"}
    )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        for key, value in keys.items():
            session.add(SysConfig(config_key=key, value=value))
        await session.commit()
    try:
        yield keys
    finally:
        async with factory() as session:
            cleanup_keys = (*keys, ns.code("new"))
            rows = (
                (await session.execute(select(SysConfig).where(SysConfig.config_key.in_(cleanup_keys)))).scalars().all()
            )
            for row in rows:
                await session.delete(row)
            await session.commit()


@pytest.mark.kiwi_id(2207)
async def test_sql_source_read_cache_and_degrade(
    config_keys: ConcurrentStableDict[str, str],
    shared_tenant_engine: AsyncEngine,
    ns: Namespace,
) -> None:
    """SQL 取数：命中 / 未命中省略 / 缓存回源 / DB 异常降级空结果。"""
    cache = MemoryConfigCacheRegion()
    source = SqlConfigSource(engines=_engines(), cache=cache)

    values = await source.get_many(ConcurrentStableList(config_keys))
    assert dict(values) == dict(config_keys)
    assert await source.get(ns.code("missing"), "fallback") == "fallback"

    # 缓存回源：改库后缓存仍可读到已缓存键
    channel = next(key for key in config_keys if key.endswith("-channel"))
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(update(SysConfig).where(SysConfig.config_key == channel).values(value="true"))
        await session.commit()
    # 旧值仍在缓存（未失效）
    stale = await source.get_many(ConcurrentStableList((channel,)))
    assert stale[channel] == "false"

    # DB 异常降级：无库 URL 时返回空结果（不抛）
    broken = SqlConfigSource(engines=_broken_engines(), cache=NullConfigCacheRegion())
    assert await broken.get_many(ConcurrentStableList(config_keys)) == {}


@pytest.mark.kiwi_id(2207)
async def test_service_set_remark_and_drop_missing(config_keys: ConcurrentStableDict[str, str], ns: Namespace) -> None:
    """写服务：带备注更新已有键、`drop` 不存在的键（无操作）。"""
    cache = MemoryConfigCacheRegion()
    service = ConfigService(engines=_engines(), cache=cache)
    key = next(iter(config_keys))
    await service.set(config_key=key, value="9", remark="覆盖")
    new_key = ns.code("new")
    await service.set(config_key=new_key, value="1")
    await service.drop(config_key=ns.code("missing"))
    source = SqlConfigSource(engines=_engines(), cache=cache)
    assert (await source.get_many(ConcurrentStableList((key,))))[key] == "9"
    got = await source.get_many(ConcurrentStableList((new_key,)))
    assert got[new_key] == "1"


@pytest.mark.kiwi_id(2207)
async def test_service_invalidate_immediate_effect(config_keys: ConcurrentStableDict[str, str]) -> None:
    """写 / 失效：`set` 后读到新值、`drop` 后回落默认（缺失省略）。"""
    key = next(iter(config_keys))
    cache = MemoryConfigCacheRegion()
    engines = _engines()
    source = SqlConfigSource(engines=engines, cache=cache)
    service = ConfigService(engines=engines, cache=cache)

    _ = await source.get_many(ConcurrentStableList((key,)))  # 预热缓存
    await service.set(config_key=key, value="5")
    assert (await source.get_many(ConcurrentStableList((key,))))[key] == "5"
    await service.set(config_key=key, value="7", remark="调阈值")
    assert (await source.get_many(ConcurrentStableList((key,))))[key] == "7"
    await service.drop(config_key=key)
    assert key not in await source.get_many(ConcurrentStableList((key,)))


class _FakeServiceClient(BaseServiceClient):
    """测试替身：按请求返回固定 `values` 或抛不可用。"""

    def __init__(self, values: object, *, fail: bool = False) -> None:
        self._values = values
        self._fail = fail
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录请求并返回统一响应（或抛不可用）。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 统一响应。

        Raises:
            ServiceUnavailableError: 配置为不可达。
        """
        self.requests.add(request)
        if self._fail:
            raise ServiceUnavailableError("down")
        body = {"code": 0, "message": "ok", "data": {"values": self._values}}
        return ServiceResponse(status_code=200, content=json.dumps(body).encode())


@pytest.mark.kiwi_id(2207)
async def test_http_source_and_degrade() -> None:
    """跨服务取数：解析 `values`；不可达 / 非法响应降级空结果。"""
    client = _FakeServiceClient({"a": "1", "b": "2", "c": "3"})
    source = HttpConfigSource(client=client)
    assert dict(await source.get_many(ConcurrentStableList(("a", "b")))) == {"a": "1", "b": "2"}
    assert client.requests[0].path.endswith("/platform/internal/configs/resolve")

    assert await HttpConfigSource(client=_FakeServiceClient({}, fail=True)).get_many(ConcurrentStableList(("a",))) == {}
    assert await HttpConfigSource(client=_FakeServiceClient([])).get_many(ConcurrentStableList(("a",))) == {}


@pytest.mark.kiwi_id(2207)
async def test_null_source_and_cache_defaults() -> None:
    """占位实现：Null 取数恒空、Null 缓存恒未命中；内存缓存 key 与版本。"""
    null_source = NullConfigSource()
    assert await null_source.get_many(ConcurrentStableList(("x",))) == {}
    assert await null_source.get("x", "d") == "d"

    cache = MemoryConfigCacheRegion()
    await cache.aset_value("demo", "k", "v")
    assert await cache.aget_value("demo", "k") == "v"
    assert cache.config_key("demo", "k") == "bms:demo:config:k"
    assert cache.version_key("demo") == "bms:demo:config:version"
    assert await cache.aincrease_version("demo") == 1
    await cache.adrop_value("demo", "k")
    assert await cache.aget_value("demo", "k") is None

    null_cache = NullConfigCacheRegion()
    await null_cache.aset_value("demo", "k", "v")
    assert await null_cache.aget_value("demo", "k") is None
    assert await null_cache.aincrease_version("demo") == 1


@pytest.mark.kiwi_id(2207)
async def test_redis_cache_region_roundtrip() -> None:
    """Redis 缓存域（fakeredis 注入）：值读写与版本 `INCR`、删除。"""
    fakeredis = pytest.importorskip("fakeredis")
    from bms_core.cache.redis import RedisCacheRegion

    sync_client = fakeredis.FakeRedis(decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    region = RedisConfigCacheRegion(
        redis_region=RedisCacheRegion(domain="config", sync_client=sync_client, async_client=async_client)
    )
    await region.aset_value(None, "k", "v")
    assert await region.aget_value(None, "k") == "v"
    assert await region.aincrease_version(None) == 1
    assert await region.aincrease_version(None) == 2
    await region.adrop_value(None, "k")
    assert await region.aget_value(None, "k") is None


def test_config_capability_is_pluggable() -> None:
    """能力域契约面：`BaseConfigSource` / `ConfigCacheRegion` 为插件基类。"""
    assert isinstance(SqlConfigSource(engines=_engines()), BaseConfigSource)
    assert isinstance(MemoryConfigCacheRegion(), ConfigCacheRegion)
    assert isinstance(_MappingSource(), BaseConfigSource)


class _MappingSource(BaseConfigSource):
    """内存取数实现（用例内联）。"""

    def __init__(self, values: ConcurrentStableDict[str, str] | None = None) -> None:
        self._values = dict(values or {})

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """返回预置映射的子集。

        Args:
            keys: 参数键序列（插入序）。

        Returns:
            ConcurrentStableDict[str, str]: 命中键 → 值（插入序）。
        """
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})

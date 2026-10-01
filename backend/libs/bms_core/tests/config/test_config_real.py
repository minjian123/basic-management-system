"""config 域真实实现用例（Kiwi 2207，03_08）：迁移 / 种子 / SQL 取数与缓存 / 写失效 / 跨服务读 / 缓存域。

覆盖：`sys_config` 迁移建表与模型一致 / 平台默认种子幂等 / `SqlConfigSource` 命中·未命中·缓存回源·DB 异常降级 /
`ConfigService.set`·`drop` 后缓存失效即时生效 / `HttpConfigSource` 契约调用与降级 / 内存与 Redis 缓存域 key 与版本 /
`NullConfigSource` 恒空 / `BaseConfigSource.get` 默认。

测试库：临时 SQLite 文件（跑 Alembic `platform:tenant` 链建表 + 幂等种子）。
"""

import json
import sqlite3
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion, RedisConfigCacheRegion
from bms_core.config.http import HttpConfigSource
from bms_core.config.models import SysConfig
from bms_core.config.null import NullConfigCacheRegion, NullConfigSource
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS, seed_configs
from bms_core.config.service import ConfigService
from bms_core.config.sql import SqlConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.db.engine import EngineFactory
from bms_core.db.migration import BACKEND_ROOT
from bms_core.db.registry import EngineRegistry
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

EXPECTED_TABLES = {
    "sys_config",
}

EXPECTED_COLUMNS = {
    "id",
    "config_key",
    "value",
    "remark",
    "created_at",
    "created_by",
    "updated_at",
    "updated_by",
    "deleted_at",
    "version",
}


def _run_migrations(url: str) -> None:
    """对目标库执行 Alembic `platform:tenant` 链迁移。

    Args:
        url: 数据库 URL。
    """
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.cmd_opts = SimpleNamespace(x=[f"url={url}"])  # pyright: ignore[reportAttributeAccessIssue]
    command.upgrade(cfg, "head")


@pytest.fixture
def config_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库：迁移建表 + 配置覆盖。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'config_test.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "memory")
    get_settings.cache_clear()
    _run_migrations(url)
    yield url
    get_settings.cache_clear()


_OPEN_ENGINES: ConcurrentStableList[EngineRegistry] = ConcurrentStableList()
"""用例内构造的引擎注册表（用例结束统一 `aclose`，避免连接在事件循环关闭后被 GC）。"""


@pytest.fixture(autouse=True)
async def _close_open_engines() -> AsyncIterator[None]:
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


async def _seed(url: str) -> None:
    """对测试库写入幂等种子。

    Args:
        url: 测试库 URL。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_configs(session)
    await engine.dispose()


@pytest.mark.kiwi_id(2207)
def test_migration_creates_sys_config(config_db_url: str) -> None:
    """迁移建表：`sys_config` 表与关键列齐备。"""
    db_path = config_db_url.split("///")[-1]
    con = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in con.execute("PRAGMA table_info(sys_config)")}
    finally:
        con.close()
    assert tables >= EXPECTED_TABLES
    assert columns == EXPECTED_COLUMNS


@pytest.mark.kiwi_id(2207)
async def test_seed_configs_idempotent(config_db_url: str) -> None:
    """平台默认种子幂等：首次新增全量、二次执行 0 行。"""
    engine = create_async_engine(config_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            first = await seed_configs(session)
        async with factory() as session:
            second = await seed_configs(session)
    finally:
        await engine.dispose()
    assert first == len(PLATFORM_CONFIG_DEFAULTS)
    assert second == 0


@pytest.mark.kiwi_id(2207)
async def test_sql_source_read_cache_and_degrade(config_db_url: str) -> None:
    """SQL 取数：命中 / 未命中省略 / 缓存回源 / DB 异常降级空结果。"""
    await _seed(config_db_url)
    cache = MemoryConfigCacheRegion()
    source = SqlConfigSource(engines=_engines(), cache=cache)

    values = await source.get_many(
        ConcurrentStableList(("captcha.scene.login.fail_threshold", "captcha.channel.sms", "missing.key"))
    )
    assert values == {"captcha.scene.login.fail_threshold": "3", "captcha.channel.sms": "false"}
    assert await source.get("missing.key", "fallback") == "fallback"

    # 缓存回源：删库后缓存仍可读到已缓存键
    engine = create_async_engine(config_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        row = (
            await session.execute(select(SysConfig).where(SysConfig.config_key == "captcha.channel.sms"))
        ).scalar_one()
        row.value = "true"
        await session.commit()
    await engine.dispose()
    # 旧值仍在缓存（未失效）
    stale = await source.get_many(ConcurrentStableList(("captcha.channel.sms",)))
    assert stale["captcha.channel.sms"] == "false"

    # DB 异常降级：无库 URL 时返回空结果（不抛）
    broken = SqlConfigSource(engines=_broken_engines(), cache=NullConfigCacheRegion())
    assert await broken.get_many(ConcurrentStableList(("captcha.channel.sms",))) == {}


def _broken_engines() -> EngineRegistry:
    """构造指向不可达库的引擎注册表（触发 DB 异常降级）。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    settings = get_settings().model_copy(deep=True)
    settings.database.tenants.url = "sqlite+aiosqlite:////nonexistent-dir/config_broken.db"
    registry = EngineRegistry(EngineFactory(settings))
    _OPEN_ENGINES.add(registry)
    return registry


@pytest.mark.kiwi_id(2207)
async def test_service_invalidate_immediate_effect(config_db_url: str) -> None:
    """写 / 失效：`set` 后读到新值、`drop` 后回落默认（缺失省略）。"""
    await _seed(config_db_url)
    cache = MemoryConfigCacheRegion()
    engines = _engines()
    source = SqlConfigSource(engines=engines, cache=cache)
    service = ConfigService(engines=engines, cache=cache)

    key = "captcha.scene.login.fail_threshold"
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

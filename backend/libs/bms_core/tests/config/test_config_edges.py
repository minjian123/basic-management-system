"""config 域边界与分支用例（Kiwi 2207，03_08）：缓存同步方法 / 跨服务降级 / 空取数 / 依赖提供者。

补齐真实实现中非常规路径：Redis / 内存缓存域同步读写与生命周期、`HttpConfigSource` 各降级分支、
`SqlConfigSource` 空键与缓存属性、`NullConfigCacheRegion` 删除、`ConfigCacheRegion` 基类缺省版本接口、
`get_config_source` / `get_config_cache_region` 提供者解析。
"""

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm.exc import StaleDataError

from bms_core.api.deps import get_config_cache_region, get_config_source
from bms_core.cache.redis import RedisCacheRegion
from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion, RedisConfigCacheRegion
from bms_core.config.http import HttpConfigSource
from bms_core.config.null import NullConfigCacheRegion, NullConfigSource
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS, seed_configs
from bms_core.config.service import ConfigService
from bms_core.config.sql import SqlConfigSource
from bms_core.core.config import get_settings
from bms_core.core.context import current_tenant
from bms_core.core.exceptions import ConcurrentConflictError
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

from .test_config_real import _engines, _run_migrations  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2207)
def test_memory_cache_sync_methods() -> None:
    """内存缓存域同步读写 / 删除 / 版本 / 版本一致性判定。"""
    region = MemoryConfigCacheRegion()
    region.set("k", "v")
    assert region.get("k") == "v"
    assert region.delete("k") is True
    assert region.get("k") is None
    assert region.bump_version("demo") == 1
    assert region.get_global_version() >= 1
    assert region.is_version_current(region.get_global_version(), tenant=None) is True


@pytest.mark.kiwi_id(2207)
async def test_memory_cache_async_methods() -> None:
    """内存缓存域异步读写 / 版本。"""
    region = MemoryConfigCacheRegion()
    await region.aset_value("demo", "k", "v")
    assert await region.aget_value("demo", "k") == "v"
    assert await region.aversion("demo") == 0
    assert await region.aincrease_version("demo") == 1
    await region.adrop_value("demo", "k")
    assert await region.aget_value("demo", "k") is None


@pytest.mark.kiwi_id(2207)
async def test_redis_cache_sync_methods_and_lifecycle() -> None:
    """Redis 缓存域同步方法 / 生命周期 / 异步读回填与版本解析。"""
    fakeredis = pytest.importorskip("fakeredis")
    sync_client = fakeredis.FakeRedis(decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    shared = RedisCacheRegion(domain="config", sync_client=sync_client, async_client=async_client)
    region = RedisConfigCacheRegion(redis_region=shared)
    await region.setup()
    assert region.redis_region is shared

    region.set("bms:demo:config:k", "v")
    assert region.get("bms:demo:config:k") == "v"
    assert region.delete("bms:demo:config:k") is True
    assert region.get_global_version() == 0

    # 同步读回填：新实例 L1 为空，命中 Redis 层后回填
    region2 = RedisConfigCacheRegion(redis_region=shared)
    region2.set("bms:demo:config:k2", "v2")
    region._l1.delete("bms:demo:config:k2")  # pyright: ignore[reportPrivateUsage]
    assert region.get("bms:demo:config:k2") == "v2"

    await region.aset_value("demo", "k3", "v3")
    fresh = RedisConfigCacheRegion(redis_region=shared)
    assert await fresh.aget_value("demo", "k3") == "v3"
    await region.adrop_value("demo", "k3")
    assert await region.aget_value("demo", "k3") is None

    assert await region.aversion("demo") == 0
    assert await region.aincrease_version("demo") == 1
    assert await region.aversion("demo") == 1
    await region.aclose()


@pytest.mark.kiwi_id(2207)
async def test_base_cache_region_default_versions() -> None:
    """`ConfigCacheRegion` 基类缺省版本接口（经 Null 实现）。"""
    region = NullConfigCacheRegion()
    assert await region.aversion(None) == 0
    assert await region.aincrease_version(None) == 1
    assert await region.adrop_value(None, "k") is None


class _RawClient(BaseServiceClient):
    """测试替身：返回固定状态码与原始响应体。"""

    def __init__(self, status_code: int, content: bytes) -> None:
        self._status_code = status_code
        self._content = content

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """返回构造的响应。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 构造响应。
        """
        del request
        return ServiceResponse(status_code=self._status_code, content=self._content)


@pytest.mark.kiwi_id(2207)
async def test_http_source_degrade_branches() -> None:
    """跨服务取数各降级分支：非 2xx / 非对象体 / 缺 data / values 非对象。"""
    status = HttpConfigSource(client=_RawClient(500, b"{}"))
    assert await status.get_many(("a",)) == {}

    not_object = HttpConfigSource(client=_RawClient(200, b"[]"))
    assert await not_object.get_many(("a",)) == {}

    no_data = HttpConfigSource(client=_RawClient(200, json.dumps({"code": 0}).encode()))
    assert await no_data.get_many(("a",)) == {}

    bad_values = HttpConfigSource(client=_RawClient(200, json.dumps({"data": {"values": []}}).encode()))
    assert await bad_values.get_many(("a",)) == {}

    assert await HttpConfigSource(client=_RawClient(200, b"{}")).get_many(()) == {}


def test_sql_source_cache_property_and_empty_keys() -> None:
    """SQL 取数空键与缓存属性。"""
    source = SqlConfigSource(engines=_engines())
    assert isinstance(source.cache, MemoryConfigCacheRegion)


@pytest.mark.kiwi_id(2207)
async def test_sql_source_empty_keys() -> None:
    """SQL 取数空键序列返回空映射（不查库）。"""
    assert await SqlConfigSource(engines=_engines()).get_many(()) == {}


@pytest.mark.kiwi_id(2207)
async def test_null_delete_and_source_get() -> None:
    """Null 缓存删除与 Null 取数单键默认。"""
    assert NullConfigCacheRegion().delete("k") is False
    assert await NullConfigSource().get("k", "d") == "d"


@pytest.mark.kiwi_id(2207)
async def test_config_providers_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖提供者解析：provider 空 → Null 实现。"""
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "")
    get_settings.cache_clear()
    settings = get_settings()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    assert isinstance(get_config_source(request), BaseConfigSource)  # type: ignore[arg-type]
    assert isinstance(get_config_cache_region(request), ConfigCacheRegion)  # type: ignore[arg-type]
    get_settings.cache_clear()


@pytest.fixture
def config_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库（迁移 + 覆盖配置）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'config_edges.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    _run_migrations(url)
    yield url
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2207)
async def test_service_set_remark_and_drop_missing(config_db_url: str) -> None:
    """写服务：带备注更新已有键、`drop` 不存在的键（无操作）。"""
    engine = create_async_engine(config_db_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed_configs(session)
    await engine.dispose()

    cache = MemoryConfigCacheRegion()
    service = ConfigService(engines=_engines(), cache=cache)
    key = PLATFORM_CONFIG_DEFAULTS[0].config_key
    await service.set(config_key=key, value="9", remark="覆盖")
    await service.set(config_key="captcha.channel.new", value="1")
    await service.drop(config_key="not.exists.key")
    source = SqlConfigSource(engines=_engines(), cache=cache)
    assert (await source.get_many((key,)))[key] == "9"
    assert (await source.get_many(("captcha.channel.new",)))["captcha.channel.new"] == "1"


class _VersionRegion:
    """测试替身：`aget` 返回固定版本值。"""

    def __init__(self, value: object) -> None:
        self._value = value

    async def aget(self, key: str) -> object:
        """返回固定值。

        Args:
            key: 缓存 key（忽略）。

        Returns:
            object: 固定值。
        """
        del key
        return self._value


@pytest.mark.kiwi_id(2207)
async def test_redis_aversion_parsing() -> None:
    """Redis 版本解析：布尔 / 整数 / 非数值三态。"""
    boolean = RedisConfigCacheRegion(redis_region=cast("RedisCacheRegion", _VersionRegion(True)))
    assert await boolean.aversion("demo") == 0
    integer = RedisConfigCacheRegion(redis_region=cast("RedisCacheRegion", _VersionRegion(7)))
    assert await integer.aversion("demo") == 7
    textual = RedisConfigCacheRegion(redis_region=cast("RedisCacheRegion", _VersionRegion("9")))
    assert await textual.aversion("demo") == 9


@pytest.mark.kiwi_id(2207)
async def test_http_source_with_tenant() -> None:
    """跨服务取数：携带租户上下文时透传 `X-Tenant-Id`。"""
    client = _RawClient(200, json.dumps({"data": {"values": {"a": "1"}}}).encode())
    token = current_tenant.set("demo")
    try:
        assert dict(await HttpConfigSource(client=client).get_many(("a",))) == {"a": "1"}
    finally:
        current_tenant.reset(token)


class _StaleSession:
    """测试替身：`commit` 抛乐观锁冲突。"""

    async def commit(self) -> None:
        """抛冲突。

        Raises:
            StaleDataError: 乐观锁冲突。
        """
        raise StaleDataError("stale")


@pytest.mark.kiwi_id(2207)
async def test_service_commit_conflict() -> None:
    """写服务提交遇乐观锁冲突转统一错误。"""
    service = ConfigService(engines=_engines())
    with pytest.raises(ConcurrentConflictError):
        await service._commit(_StaleSession())  # pyright: ignore[reportPrivateUsage, reportArgumentType]

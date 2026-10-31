"""参数缓存跨实例一致性集成用例：真 Redis + 两套取数实例（各自 L1，共享 Redis）。

前置（未就绪自动跳过，CI 不受影响）：

```bash
export BMS_REDIS__URL=redis://192.168.0.107:6379/0
.venv/Scripts/python.exe -m pytest libs/bms_core/tests/integration/test_config_cache_real.py -v
```

覆盖《详细设计 · 系统参数》§4.3 的实证（设计约束：缓存一致性 / 多实例结论必须真库实测）：

1. 实例 A 取数写入共享层后，实例 B（L1 为空）**不重复回源**（命中 Redis 载荷）；
2. 写库 + `invalidate_config`（DEL 参数键 + `INCR bms:{tenant}:config:version`）后，
   实例 B 的**下一次读**因版本不符回源，读到新值——即「改完即生效」，无需重启；
3. 失效后同实例再读命中新载荷（L1 已按新版本回填），不再回源。
"""

# pyright: reportUnknownMemberType=false
# 说明：redis-py 的 `from_url` / `keys` 在严格模式下返回 partially-unknown（stub 未参数化）。

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.cache.redis import RedisCacheRegion
from bms_core.config.cache import RedisConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.config.seed import seed_configs
from bms_core.config.service import invalidate_config
from bms_core.config.sql import SqlConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.bootstrap import apply_unit_schema
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry

pytestmark = pytest.mark.kiwi_id(2373)

_REAL_REDIS_URL = os.environ.get("BMS_REDIS__URL", "")
"""真 Redis 连接串：**导入时**读取（autouse 的设置隔离夹具会清 `BMS_*` 环境变量）。"""

_CONFIG_KEY = "password.max_age_days"
"""被测参数键。"""


def _redis_url() -> str:
    """取真 Redis 连接串（未配置则跳过）。

    Returns:
        str: 连接串。
    """
    if not _REAL_REDIS_URL:
        pytest.skip("未配置 BMS_REDIS__URL（真 Redis 集成用例跳过）")
    return _REAL_REDIS_URL


async def _probe(url: str) -> AsyncRedis:
    """连接并探活。

    Args:
        url: 连接串。

    Returns:
        AsyncRedis: 可用客户端。

    Raises:
        pytest.skip: 连不上（本机无该 Redis）。
    """
    client: AsyncRedis = AsyncRedis.from_url(url, decode_responses=False)
    try:
        await client.ping()
    except Exception as exc:  # 环境不可用时跳过，不让 CI 红
        await client.aclose()
        pytest.skip(f"真 Redis 不可达，跳过：{exc}")
    return client


async def _purge(client: AsyncRedis) -> None:
    """清理参数域键（用例前后各一次，避免污染共享实例）。

    Args:
        client: Redis 客户端。
    """
    keys = await client.keys("bms:*config*")
    if keys:
        await client.delete(*keys)


@pytest.fixture
def config_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """临时租户库（`platform:tenant` 链表集）+ 配置覆盖。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        str: 测试库 URL。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'config_real.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "redis")
    get_settings.cache_clear()
    asyncio.run(apply_unit_schema("platform", "tenant", url, target="config_real"))
    asyncio.run(_seed(url))
    yield url
    get_settings.cache_clear()


@pytest.fixture
async def engines() -> AsyncIterator[EngineRegistry]:
    """引擎注册表（用例结束释放）。

    Yields:
        EngineRegistry: 引擎注册表。
    """
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        yield registry
    finally:
        await registry.aclose()


class _CountingSource(SqlConfigSource):
    """计次取数实现（统计回源次数，验证 L1 / 共享层命中）。"""

    def __init__(self, *, engines: EngineRegistry, cache: RedisConfigCacheRegion) -> None:
        super().__init__(engines=engines, cache=cache)
        self.loads = 0

    async def _load(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """回源计次后委托父类。

        Args:
            keys: 缺失参数键。

        Returns:
            ConcurrentStableDict[str, str]: 回源结果。
        """
        self.loads += 1
        return await super()._load(keys)


async def _seed(url: str) -> None:
    """写入平台默认种子（让被测键存在未覆盖行）。

    Args:
        url: 测试库 URL。
    """
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await seed_configs(session)
    finally:
        await engine.dispose()


async def _set_value(url: str, value: str) -> None:
    """直接改库（模拟所有者域写库）。

    Args:
        url: 测试库 URL。
        value: 新参数值。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(SysConfig).where(SysConfig.config_key == _CONFIG_KEY).values(value=value, is_overridden=True)
            )
    finally:
        await engine.dispose()


def _region(url: str) -> RedisConfigCacheRegion:
    """构造独立实例缓存域（各持 L1，共享同一 Redis）。

    Args:
        url: Redis 连接串。

    Returns:
        RedisConfigCacheRegion: 缓存域。
    """
    return RedisConfigCacheRegion(redis_region=RedisCacheRegion(domain="config", url=url))


async def test_cross_instance_invalidation_with_real_redis(config_db: str, engines: EngineRegistry) -> None:
    """真 Redis：B 先命中共享层不回源；A 失效后 B 下一次读回源读到新值。"""
    url = _redis_url()
    client = await _probe(url)
    await _purge(client)
    try:
        await _set_value(config_db, "90")
        source_a = _CountingSource(engines=engines, cache=_region(url))
        source_b = _CountingSource(engines=engines, cache=_region(url))

        first = await source_a.get_many(ConcurrentStableList((_CONFIG_KEY,)))
        assert first[_CONFIG_KEY] == "90"
        assert source_a.loads == 1

        shared_hit = await source_b.get_many(ConcurrentStableList((_CONFIG_KEY,)))
        assert shared_hit[_CONFIG_KEY] == "90"
        assert source_b.loads == 0

        await _set_value(config_db, "30")
        await invalidate_config(source_a.cache, _CONFIG_KEY)

        refreshed = await source_b.get_many(ConcurrentStableList((_CONFIG_KEY,)))
        assert refreshed[_CONFIG_KEY] == "30"
        assert source_b.loads == 1

        cached_again = await source_b.get_many(ConcurrentStableList((_CONFIG_KEY,)))
        assert cached_again[_CONFIG_KEY] == "30"
        assert source_b.loads == 1
    finally:
        await _purge(client)
        await client.aclose()


async def test_negative_cache_prevents_repeated_source(config_db: str, engines: EngineRegistry) -> None:
    """真 Redis：缺失键写负缓存，同实例第二次读不再回源、也不返回该键。"""
    url = _redis_url()
    client = await _probe(url)
    await _purge(client)
    try:
        source = _CountingSource(engines=engines, cache=_region(url))
        absent: ConcurrentStableList[str] = ConcurrentStableList(("custom.absent",))
        assert await source.get_many(absent) == ConcurrentStableDict()
        assert source.loads == 1

        assert await source.get_many(absent) == ConcurrentStableDict()
        assert source.loads == 1
    finally:
        await _purge(client)
        await client.aclose()

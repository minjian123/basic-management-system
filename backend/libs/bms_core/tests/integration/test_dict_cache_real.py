"""字典缓存跨实例一致性集成用例：真 Redis + 两个出口实例（各自 L1，共享 Redis）。

前置（未就绪自动跳过，CI 不受影响）：

```bash
export BMS_REDIS__URL=redis://192.168.0.107:6379/0
.venv/Scripts/python.exe -m pytest libs/bms_core/tests/integration/test_dict_cache_real.py -v
```

覆盖《详细设计 · 字典》§4.3 的实证（设计约束：多实例 / 缓存一致性必须真库真实例，不接受只有替身的结论）：

1. 实例 A 取数写入共享层后，实例 B（L1 为空）直接命中 Redis 快照，**不重复回源**；
2. 所有者域写完数据调 `DictInvalidator`（DEL 各语言键 + `INCR bms:{tenant}:dict:version`）后，
   实例 B 的**下一次请求**因版本不符回源，读到新值——即「改数据后下一次请求即生效」，无需重启；
3. 失效只影响传入的 key（同租户其他字典的快照仍命中）。
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# 说明：redis-py 的 `from_url` / `keys` 在严格模式下返回 partially-unknown（stub 未参数化），
# 本文件只做「连真 Redis 跑一轮」的集成装配，不做类型推断上的业务判定。

from __future__ import annotations

import os

import pytest
from redis.asyncio import Redis as AsyncRedis

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRecord, DataSourceRegistry
from bms_core.dict.base import DictQuery
from bms_core.dict.cache import RedisDictCacheRegion
from bms_core.dict.invalidate import DictInvalidator
from bms_core.dict.outlet import DataSourceOutlet, RoutedDataSource
from bms_core.redis.base import clear_shared_redis_client, set_shared_redis_client
from bms_core.redis.redis import RedisRedisClient

pytestmark = pytest.mark.kiwi_id(2372)

_REAL_REDIS_URL = os.environ.get("BMS_REDIS__URL", "")
"""真 Redis 连接串：**导入时**读取（autouse 的设置隔离夹具会清 `BMS_*` 环境变量）。"""

_ROLE = "role"
"""被测字典标识（全局库位＝无租户上下文）。"""


def _redis_url() -> str:
    """取真 Redis 连接串（未配置则跳过）。

    Returns:
        str: 连接串。
    """
    url = _REAL_REDIS_URL
    if not url:
        pytest.skip("未配置 BMS_REDIS__URL（真 Redis 集成用例跳过）")
    return url


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


async def _install_shared(url: str) -> RedisRedisClient:
    """登记进程共享 Redis 客户端（字典缓存域经共享客户端访问 Redis，而非自建连接）。

    Args:
        url: 连接串。

    Returns:
        RedisRedisClient: 已登记且探活的客户端。

    Raises:
        pytest.skip: 连不上（本机无该 Redis）。
    """
    shared = RedisRedisClient(url)
    try:
        await shared.setup()
    except Exception as exc:  # 环境不可用时跳过，不让 CI 红
        await shared.aclose()
        pytest.skip(f"真 Redis 共享客户端不可用，跳过：{exc}")
    set_shared_redis_client(shared)
    return shared


async def _uninstall_shared(shared: RedisRedisClient) -> None:
    """注销并关闭共享客户端（用例隔离）。"""
    clear_shared_redis_client()
    await shared.aclose()


async def _purge(client: AsyncRedis) -> None:
    """清理字典域键（用例前后各一次，避免污染开发服务器的共享实例）。"""
    keys = await client.keys("bms:*dict*")
    if keys:
        await client.delete(*keys)


class _MutableProvider(BaseDictDataSource):
    """可变更行的提供者（模拟所有者域：数据改了、缓存要失效）。"""

    def __init__(self) -> None:
        self.rows: ConcurrentStableList[DataSourceItem] = ConcurrentStableList(
            (DataSourceItem(id=1, value="admin", label="管理员", code="admin", status="enabled"),)
        )
        self.calls = 0

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 固定 `platform`。
        """
        return "platform"

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """取数并计次。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            ConcurrentStableList[DataSourceItem]: 当前行。
        """
        self.calls += 1
        return self.rows


def _source(provider: _MutableProvider, cache: RedisDictCacheRegion) -> RoutedDataSource:
    """构造一个出口实例（各自独立缓存域＝各自 L1，共享同一 Redis）。

    Args:
        provider: 提供者。
        cache: 该实例的字典缓存域。

    Returns:
        RoutedDataSource: 出口实例。
    """
    record = DataSourceRecord(data_source_key=_ROLE, name="角色", data_source="platform")
    outlet = DataSourceOutlet(
        DataSourceRegistry(ConcurrentStableList((record,))),
        ConcurrentStableDict({"platform": provider}),
    )
    return RoutedDataSource(outlet, cache)


async def test_invalidation_visible_to_other_instance() -> None:
    """A 失效后，B 的下一请求读到新值（版本键跨实例生效）。"""
    url = _redis_url()
    client = await _probe(url)
    shared = await _install_shared(url)
    await _purge(client)
    provider = _MutableProvider()
    cache_a = RedisDictCacheRegion(url=url)
    cache_b = RedisDictCacheRegion(url=url)
    try:
        instance_a = _source(provider, cache_a)
        instance_b = _source(provider, cache_b)

        first = await instance_a.by_type(DictQuery(data_source_key=_ROLE))
        assert first.items is not None and [item.label for item in first.items] == ["管理员"]
        assert provider.calls == 1

        # B 的 L1 是空的：应命中 A 写进 Redis 的快照，不回源
        second = await instance_b.by_type(DictQuery(data_source_key=_ROLE))
        assert second.items is not None and [item.label for item in second.items] == ["管理员"]
        assert provider.calls == 1

        # 所有者域改数据 → 先提交、后失效
        provider.rows = ConcurrentStableList(
            (DataSourceItem(id=1, value="admin", label="超级管理员", code="admin", status="enabled"),)
        )
        version = await DictInvalidator(cache_a).invalidate(ConcurrentStableList((_ROLE,)))
        assert version >= 1

        third = await instance_b.by_type(DictQuery(data_source_key=_ROLE))
        assert third.items is not None and [item.label for item in third.items] == ["超级管理员"]
        assert provider.calls == 2
    finally:
        await cache_a.aclose()
        await cache_b.aclose()
        await _purge(client)
        await _uninstall_shared(shared)
        await client.aclose()


async def test_invalidation_bumps_tenant_wide_version() -> None:
    """版本键是**租户级**：任一 dict 失效后，同租户其他字典的旧快照也判陈旧（下一次请求重载一次）。

    这是设计口径（需求 01-1 §3 的单一 `INCR bms:{tenant}:dict:version`）：失效粒度＝租户全域，
    逐 key 的 DEL 只负责省重算与回收内存。写入是低频操作（管理端改字典），代价可接受；
    要求「只失效某一个 key」需改为按 key 版本，属后续优化（设计 §8 开放项）。
    """
    url = _redis_url()
    client = await _probe(url)
    shared = await _install_shared(url)
    await _purge(client)
    provider = _MutableProvider()
    cache_a = RedisDictCacheRegion(url=url)
    cache_b = RedisDictCacheRegion(url=url)
    try:
        user_record = DataSourceRecord(data_source_key="user", name="用户", data_source="platform")
        outlet = DataSourceOutlet(
            DataSourceRegistry(ConcurrentStableList((user_record,))),
            ConcurrentStableDict({"platform": provider}),
        )
        instance_a = RoutedDataSource(outlet, cache_a)
        instance_b = RoutedDataSource(outlet, cache_b)
        await instance_a.by_type(DictQuery(data_source_key="user"))
        assert provider.calls == 1

        await DictInvalidator(cache_a).invalidate(ConcurrentStableList((_ROLE,)))
        await instance_b.by_type(DictQuery(data_source_key="user"))
        assert provider.calls == 2  # 版本 +1 后旧快照判陈旧，重载一次
    finally:
        await cache_a.aclose()
        await cache_b.aclose()
        await _purge(client)
        await _uninstall_shared(shared)
        await client.aclose()

"""一致性屏障契约与 Redis 实现用例（Kiwi 2246）：等待收敛 / 超时 / 单调 / 降级。

测试用 `fakeredis`（异步客户端，与真实 redis-py 同接口）。
"""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import Request
from redis.asyncio import Redis

import bms_core.consistency.base as base_module
from bms_core.consistency.base import (
    DEFAULT_BARRIER_POLL_MS,
    DEFAULT_BARRIER_TIMEOUT_MS,
    BaseConsistencyBarrier,
    build_consistency_key,
    get_consistency_barrier,
)
from bms_core.consistency.null import NullConsistencyBarrier
from bms_core.consistency.redis import RedisConsistencyBarrier
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ConsistencyBarrierTimeout

_REDIS_URL = "redis://localhost:6379/0"


class _BrokenClient:
    """恒抛连接异常的客户端替身（验证降级）。"""

    async def get(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")

    async def set(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")

    async def eval(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")


@pytest.mark.kiwi_id(2246)
def test_contract_and_key() -> None:
    """契约继承、占位标记、常量与键口径。"""
    assert issubclass(BaseConsistencyBarrier, BaseCapability)
    assert issubclass(NullConsistencyBarrier, BaseConsistencyBarrier)
    assert issubclass(NullConsistencyBarrier, BaseNullObject)
    assert BaseConsistencyBarrier.key == "consistency_barrier"
    assert DEFAULT_BARRIER_TIMEOUT_MS == 3000
    assert DEFAULT_BARRIER_POLL_MS == 100
    assert build_consistency_key(scope="perm", tenant="t1") == "bms:t1:consistency:perm"
    assert build_consistency_key(scope="perm") == "bms:global:consistency:perm"

    barrier = NullConsistencyBarrier()
    assert barrier.placeholder is True
    assert "consistency_barrier" in barrier.describe()


@pytest.mark.kiwi_id(2246)
async def test_null_barrier_noop() -> None:
    """占位屏障：即返回、不报错、无版本。"""
    barrier = NullConsistencyBarrier()
    await barrier.await_applied(scope="perm", target_version=99, tenant="t1")  # 不等待、不报错
    assert await barrier.applied_version(scope="perm", tenant="t1") == 0
    await barrier.mark_applied(scope="perm", version=5, tenant="t1")


@pytest.mark.kiwi_id(2246)
async def test_redis_mark_then_await_immediate() -> None:
    """已达成：`mark_applied` 后 `await_applied` 立即返回。"""
    client = FakeRedis(decode_responses=True)
    barrier = RedisConsistencyBarrier(_REDIS_URL, client=client)
    assert isinstance(barrier, BaseConsistencyBarrier)

    assert await barrier.applied_version(scope="perm", tenant="t1") == 0
    await barrier.mark_applied(scope="perm", version=3, tenant="t1")
    assert await barrier.applied_version(scope="perm", tenant="t1") == 3
    await barrier.await_applied(scope="perm", target_version=3, tenant="t1", timeout_ms=200, poll_ms=10)
    await client.aclose()


@pytest.mark.kiwi_id(2246)
async def test_redis_await_waits_until_converged() -> None:
    """未达成：有界轮询等待，收敛后返回。"""
    client = FakeRedis(decode_responses=True)
    barrier = RedisConsistencyBarrier(_REDIS_URL, client=client)

    async def _converge() -> None:
        await asyncio.sleep(0.05)
        await barrier.mark_applied(scope="org", version=7, tenant="t1")

    task = asyncio.create_task(_converge())
    await barrier.await_applied(scope="org", target_version=7, tenant="t1", timeout_ms=2000, poll_ms=10)
    await task
    assert await barrier.applied_version(scope="org", tenant="t1") == 7
    await client.aclose()


@pytest.mark.kiwi_id(2246)
async def test_redis_await_timeout_raises() -> None:
    """未收敛超时：抛 `ConsistencyBarrierTimeout`（10011 / 409）。"""
    client = FakeRedis(decode_responses=True)
    barrier = RedisConsistencyBarrier(_REDIS_URL, client=client)
    with pytest.raises(ConsistencyBarrierTimeout) as exc_info:
        await barrier.await_applied(scope="perm", target_version=5, tenant="t1", timeout_ms=60, poll_ms=20)
    assert exc_info.value.code == 10011
    assert exc_info.value.http_status == 409
    await client.aclose()


@pytest.mark.kiwi_id(2246)
async def test_redis_mark_monotonic() -> None:
    """版本单调：旧版本标记不回退已应用版本。"""
    client = FakeRedis(decode_responses=True)
    barrier = RedisConsistencyBarrier(_REDIS_URL, client=client)
    await barrier.mark_applied(scope="perm", version=5, tenant="t1")
    await barrier.mark_applied(scope="perm", version=3, tenant="t1")
    assert await barrier.applied_version(scope="perm", tenant="t1") == 5
    await barrier.mark_applied(scope="perm", version=6, tenant="t1")
    assert await barrier.applied_version(scope="perm", tenant="t1") == 6
    await client.aclose()


@pytest.mark.kiwi_id(2246)
async def test_redis_unavailable_fails_closed() -> None:
    """Redis 不可用：fail-closed（抛 `RedisUnavailableError` 10012 / 503），不再放行（03_04）。"""
    from bms_core.core.exceptions import RedisUnavailableError

    barrier = RedisConsistencyBarrier(_REDIS_URL, client=cast("Redis", _BrokenClient()))
    with pytest.raises(RedisUnavailableError) as exc_info:
        await barrier.await_applied(scope="perm", target_version=99, tenant="t1", timeout_ms=50, poll_ms=10)
    assert exc_info.value.code == 10012
    assert exc_info.value.http_status == 503
    with pytest.raises(RedisUnavailableError):
        await barrier.mark_applied(scope="perm", version=1, tenant="t1")
    with pytest.raises(RedisUnavailableError):
        await barrier.applied_version(scope="perm", tenant="t1")


class _AlreadyUnavailableClient:
    """已判定不可用的客户端替身：直接抛 `RedisUnavailableError`（验证直通不重复包装）。"""

    async def get(self, *args: object, **kwargs: object) -> None:
        """直接抛 `RedisUnavailableError`。"""
        from bms_core.core.exceptions import RedisUnavailableError

        raise RedisUnavailableError("上游已判定不可用")

    async def eval(self, *args: object, **kwargs: object) -> None:
        """直接抛 `RedisUnavailableError`。"""
        from bms_core.core.exceptions import RedisUnavailableError

        raise RedisUnavailableError("上游已判定不可用")


class _RawValueClient:
    """返回固定原始值的客户端替身（验证版本号解析兜底）。"""

    def __init__(self, value: object) -> None:
        """初始化。

        Args:
            value: `get` 返回的原始值。
        """
        self._value = value

    async def get(self, *args: object, **kwargs: object) -> object:
        """返回固定值。"""
        return self._value


@pytest.mark.kiwi_id(2246)
async def test_redis_client_lazily_uses_shared_client() -> None:
    """未注入客户端：惰性取进程共享客户端（同一实例复用，不各自建连）。"""
    barrier = RedisConsistencyBarrier(_REDIS_URL)

    assert barrier.client is barrier.client
    assert await barrier.applied_version(scope="lazy", tenant="t1") == 0


@pytest.mark.kiwi_id(2246)
async def test_redis_already_unavailable_error_passes_through() -> None:
    """客户端已抛 `RedisUnavailableError`：原样直通（不重复包装为新的错误对象）。"""
    from bms_core.core.exceptions import RedisUnavailableError

    barrier = RedisConsistencyBarrier(_REDIS_URL, client=cast("Redis", _AlreadyUnavailableClient()))

    with pytest.raises(RedisUnavailableError, match="上游已判定不可用"):
        await barrier.applied_version(scope="perm", tenant="t1")
    with pytest.raises(RedisUnavailableError, match="上游已判定不可用"):
        await barrier.mark_applied(scope="perm", version=1, tenant="t1")


@pytest.mark.kiwi_id(2246)
async def test_redis_version_parsing_falls_back_to_zero() -> None:
    """版本号解析兜底：脏值（非数字 / 非标量）按「无记录」处理，不抛错。"""
    for raw in ("not-a-number", ["x"]):
        barrier = RedisConsistencyBarrier(_REDIS_URL, client=cast("Redis", _RawValueClient(raw)))
        assert await barrier.applied_version(scope="perm", tenant="t1") == 0


@pytest.mark.kiwi_id(2246)
def test_get_consistency_barrier_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入提供者：按配置解析应用级屏障实例（不触发进程级插件注册表构建）。"""
    resolved: ConcurrentStableList[tuple[str, str | None, str | None]] = ConcurrentStableList()

    def _fake_resolve(plugin_key: str, provider: str | None = None, *, expected_version: str | None = None) -> object:
        """替身：记录解析入参并返回占位屏障。"""
        resolved.add((plugin_key, provider, expected_version))
        return NullConsistencyBarrier()

    monkeypatch.setattr(base_module, "resolve_plugin", _fake_resolve)
    settings = get_settings()
    settings.consistency_barrier.provider = "redis"
    request = cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))

    barrier = get_consistency_barrier(request)
    assert isinstance(barrier, NullConsistencyBarrier)
    assert resolved == [("consistency_barrier", "redis", BaseConsistencyBarrier.contract_version)]

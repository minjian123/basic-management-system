"""流程状态存储能力域测试（Kiwi 2197）：键构造、内存 / Redis / Null 三实现与依赖解析。"""

from types import SimpleNamespace
from typing import cast

import fakeredis.aioredis
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.idp.state import base as state_base
from bms_core.idp.state import redis as redis_module
from bms_core.idp.state.base import DEFAULT_IDP_STATE_TTL, build_idp_state_key, get_idp_state_store
from bms_core.idp.state.memory import MemoryIdpStateStore
from bms_core.idp.state.null import NullIdpStateStore
from bms_core.idp.state.redis import RedisIdpStateStore


@pytest.mark.kiwi_id(2197)
def test_build_idp_state_key() -> None:
    """流程状态键形态：`bms:{租户}:idpstate:{state}`；无租户回落 global。"""
    assert build_idp_state_key("abc", tenant="demo") == "bms:demo:idpstate:abc"
    assert build_idp_state_key("abc") == "bms:global:idpstate:abc"
    assert DEFAULT_IDP_STATE_TTL == 300


@pytest.mark.kiwi_id(2202)
def test_build_idp_state_key_namespace() -> None:
    """命名空间：键形 `bms:{租户}:{命名空间}:{state}`；缺省 `idpstate` 行为不变。"""
    assert build_idp_state_key("abc", tenant="demo", namespace="oidccode") == "bms:demo:oidccode:abc"
    assert build_idp_state_key("abc", namespace="oidccode") == "bms:global:oidccode:abc"
    assert build_idp_state_key("abc", tenant="demo") == "bms:demo:idpstate:abc"


@pytest.mark.kiwi_id(2202)
async def test_memory_store_namespace_isolation() -> None:
    """内存实现：同 state 不同命名空间互不影响。"""
    store = MemoryIdpStateStore()
    await store.save("same", ConcurrentStableDict({"v": "code"}), tenant="demo", namespace="oidccode", ttl=60)
    await store.save("same", ConcurrentStableDict({"v": "state"}), tenant="demo", namespace="idpstate", ttl=60)
    assert await store.consume("same", tenant="demo", namespace="oidccode") == {"v": "code"}
    assert await store.consume("same", tenant="demo", namespace="idpstate") == {"v": "state"}


@pytest.mark.kiwi_id(2202)
async def test_redis_store_namespace_key() -> None:
    """Redis 实现：命名空间进入键形（`bms:{租户}:{命名空间}:{state}`）。"""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisIdpStateStore(client=client)
    await store.save("c1", ConcurrentStableDict({"v": 1}), tenant="demo", namespace="oidccode", ttl=60)
    assert await client.get("bms:demo:oidccode:c1") is not None
    assert await store.consume("c1", tenant="demo", namespace="oidccode") == {"v": 1}
    assert await store.consume("c1", tenant="demo", namespace="idpstate") is None
    await store.aclose()


@pytest.mark.kiwi_id(2197)
async def test_memory_store_one_time_and_expiry() -> None:
    """内存实现：一次性消费、TTL 到期视作未命中、删除幂等与清空。"""
    store = MemoryIdpStateStore()
    await store.save("s1", ConcurrentStableDict({"tenant": "demo", "nonce": "n1"}), tenant="demo", ttl=60)
    assert await store.consume("s1", tenant="demo") == {"tenant": "demo", "nonce": "n1"}
    assert await store.consume("s1", tenant="demo") is None

    await store.save("s2", ConcurrentStableDict({"tenant": "demo"}), ttl=0)
    assert await store.consume("s2") is None

    await store.save("s3", ConcurrentStableDict({"tenant": "demo"}), ttl=60)
    await store.delete("s3")
    await store.delete("s3")
    assert await store.consume("s3") is None

    await store.save("s4", ConcurrentStableDict({"tenant": "demo"}), ttl=60)
    store.clear()
    assert await store.consume("s4") is None


@pytest.mark.kiwi_id(2197)
async def test_redis_store_roundtrip_and_tenant_key() -> None:
    """Redis 实现（fakeredis）：存取 + 一次性 GETDEL + 租户键隔离 + 关闭。"""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisIdpStateStore(client=client)
    await store.save("r1", ConcurrentStableDict({"tenant": "demo", "nonce": "n"}), tenant="demo", ttl=60)
    assert await client.get("bms:demo:idpstate:r1") is not None
    assert await store.consume("r1", tenant="demo") == {"tenant": "demo", "nonce": "n"}
    assert await store.consume("r1", tenant="demo") is None
    assert await store.consume("r1", tenant="other") is None

    await store.save("r2", ConcurrentStableDict({"x": 1}), ttl=0)
    assert await store.consume("r2") == {"x": 1}

    await store.save("r3", ConcurrentStableDict({"x": 1}), ttl=60)
    await store.delete("r3")
    assert await store.consume("r3") is None
    await store.aclose()
    await store.aclose()


@pytest.mark.kiwi_id(2197)
async def test_redis_store_degrades_and_dirty_value() -> None:
    """Redis 实现：客户端异常按未命中降级；脏值（非 JSON / 非对象）按未命中。"""

    class _Broken:
        async def getdel(self, key: str) -> object:
            raise RuntimeError("redis down")

    store = RedisIdpStateStore(client=cast("object", _Broken()))  # type: ignore[arg-type]
    assert await store.consume("x", tenant="demo") is None

    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    good = RedisIdpStateStore(client=client)
    await client.set("bms:global:idpstate:bad", "{not-json")
    assert await good.consume("bad") is None
    await client.set("bms:global:idpstate:list", "[1,2]")
    assert await good.consume("list") is None
    await good.aclose()


@pytest.mark.kiwi_id(2197)
async def test_null_store_behaviour() -> None:
    """Null 实现：写删空操作、消费恒定未命中（fail-closed）。"""
    store = NullIdpStateStore()
    await store.save("n1", ConcurrentStableDict({"tenant": "demo"}), tenant="demo", ttl=60)
    assert await store.consume("n1", tenant="demo") is None
    await store.delete("n1")
    assert await store.consume("n1") is None


@pytest.mark.kiwi_id(2197)
def test_resolve_store_by_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖提供者：按 `settings.idp_state_store.provider` 经 `resolve_plugin` 解析（应用级单例）。"""
    calls: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList()
    sentinel = object()

    def _fake_resolve(key: str, provider: str, *, expected_version: str = "") -> object:
        calls.add((key, provider, expected_version))
        return sentinel

    monkeypatch.setattr(state_base, "resolve_plugin", _fake_resolve)
    settings = Settings()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    store = get_idp_state_store(cast("object", request))  # type: ignore[arg-type]
    assert store is sentinel
    assert calls == [("idp_state_store", settings.idp_state_store.provider, "0.1.0")]


@pytest.mark.kiwi_id(2197)
async def test_redis_store_dirty_raw_and_lazy_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis 实现：非 str/bytes 原始值按未命中；客户端懒建走 `from_url`。"""

    class _Weird:
        async def getdel(self, key: str) -> object:
            return 123

    weird = RedisIdpStateStore(client=cast("object", _Weird()))  # type: ignore[arg-type]
    assert await weird.consume("x") is None

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    urls: ConcurrentStableList[str] = ConcurrentStableList()

    def _from_url(url: str, **kwargs: object) -> object:
        urls.add(url)
        return client

    monkeypatch.setattr(redis_module.AsyncRedis, "from_url", staticmethod(_from_url))
    lazy = RedisIdpStateStore(url="redis://fake:6379/0")
    await lazy.save("lazy", ConcurrentStableDict({"x": 1}), ttl=60)
    assert await lazy.consume("lazy") == {"x": 1}
    assert urls == ["redis://fake:6379/0"]
    await lazy.aclose()

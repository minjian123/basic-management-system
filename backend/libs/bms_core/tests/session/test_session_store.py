"""会话存储能力域测试（Kiwi 2194）：键构造、内存 / Redis / Null 三实现与黑名单。"""

import fakeredis.aioredis
import pytest

from bms_core.session.base import build_session_key
from bms_core.session.memory import MemorySessionStore
from bms_core.session.null import NullSessionStore
from bms_core.session.redis import RedisSessionStore


@pytest.mark.kiwi_id(2194)
def test_build_session_key() -> None:
    """会话键形态：`bms:{租户}:sess:{会话 id}`；无租户回落 global。"""
    assert build_session_key("123", tenant="demo") == "bms:demo:sess:123"
    assert build_session_key("123") == "bms:global:sess:123"


@pytest.mark.kiwi_id(2194)
async def test_memory_store_roundtrip_and_expiry() -> None:
    """内存实现：存取删 + TTL 到期视作未命中 + 黑名单。"""
    store = MemorySessionStore()
    await store.save("s1", {"user_id": 1}, tenant="demo", ttl=60)
    assert await store.load("s1", tenant="demo") == {"user_id": 1}
    await store.delete("s1", tenant="demo")
    assert await store.load("s1", tenant="demo") is None

    await store.save("s2", {"user_id": 2}, ttl=0)
    assert await store.load("s2") is None

    await store.blacklist("bk", ttl=60)
    assert await store.is_blacklisted("bk") is True
    await store.blacklist("bk2", ttl=0)
    assert await store.is_blacklisted("bk2") is False
    assert await store.is_blacklisted("absent") is False
    store.clear()
    assert await store.is_blacklisted("bk") is False


@pytest.mark.kiwi_id(2194)
async def test_redis_store_roundtrip_and_blacklist() -> None:
    """Redis 实现（fakeredis）：存取删 + 租户键 + 黑名单 + 关闭。"""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisSessionStore(client=client)
    await store.save("r1", {"user_id": 1, "tenant": "demo"}, tenant="demo", ttl=60)
    assert await store.load("r1", tenant="demo") == {"user_id": 1, "tenant": "demo"}
    assert await store.load("r1", tenant="other") is None
    await store.delete("r1", tenant="demo")
    assert await store.load("r1", tenant="demo") is None

    await store.blacklist("bkr", ttl=60)
    assert await store.is_blacklisted("bkr") is True
    await store.aclose()


@pytest.mark.kiwi_id(2194)
async def test_redis_store_degrades_on_failure() -> None:
    """Redis 实现：客户端异常时读取降级为未命中（不抛业务错）。"""

    class _Broken:
        async def get(self, key: str) -> object:
            raise RuntimeError("redis down")

        async def exists(self, key: str) -> int:
            raise RuntimeError("redis down")

    store = RedisSessionStore(client=_Broken())  # type: ignore[arg-type]
    assert await store.load("x", tenant="demo") is None
    assert await store.is_blacklisted("bk") is False


@pytest.mark.kiwi_id(2194)
async def test_null_store_behaviour() -> None:
    """Null 实现：写删空操作、读回显占位、黑名单恒 False。"""
    store = NullSessionStore()
    await store.save("n1", {"a": 1})
    assert await store.load("n1") == {"session_id": "n1"}
    await store.delete("n1")
    await store.blacklist("bk", ttl=10)
    assert await store.is_blacklisted("bk") is False


@pytest.mark.kiwi_id(2194)
async def test_redis_store_lazy_client_and_ttl_branch() -> None:
    """Redis 实现：懒建客户端（不建连）与 ttl<=0 不设过期分支。"""
    store = RedisSessionStore(url="redis://localhost:6379/0")
    assert store.client is not None
    await store.aclose()


@pytest.mark.kiwi_id(2194)
async def test_redis_store_load_variants() -> None:
    """Redis 实现：bytes / 非字符串 / 非法 JSON 的负载解析分支。"""

    class _Stub:
        def __init__(self, value: object) -> None:
            self._value = value
            self.store: dict[str, object] = {}

        async def get(self, key: str) -> object:
            return self._value

        async def set(self, key: str, value: object, ex: int | None = None) -> None:
            self.store[key] = (value, ex)

    assert await RedisSessionStore(client=_Stub(b'{"a": 1}')).load("x") == {"a": 1}  # type: ignore[arg-type]
    assert await RedisSessionStore(client=_Stub(123)).load("x") is None  # type: ignore[arg-type]
    assert await RedisSessionStore(client=_Stub("{bad")).load("x") is None  # type: ignore[arg-type]
    assert await RedisSessionStore(client=_Stub("[1, 2]")).load("x") is None  # type: ignore[arg-type]

    stub = _Stub(None)
    await RedisSessionStore(client=stub).save("x", {"a": 1}, tenant="demo", ttl=0)  # type: ignore[arg-type]
    assert stub.store == {"bms:demo:sess:x": ('{"a": 1}', None)}

    # 未显式传 tenant：从负载取租户拼键
    await RedisSessionStore(client=stub).save("y", {"tenant": "acme"}, ttl=0)  # type: ignore[arg-type]
    assert "bms:acme:sess:y" in stub.store

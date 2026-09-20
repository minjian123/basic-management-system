"""分布式锁基座契约测试（Kiwi 40）：继承 / key 拼接 / 占位恒定成功 / hold 上下文与失败语义 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_distributed_lock
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import ConcurrentConflictError
from app.lock.base import DEFAULT_LOCK_TTL, DEFAULT_WAIT, BaseDistributedLock, build_lock_key
from app.lock.null import NullDistributedLock
from app.main import ApplicationFactory, lifespan


class RecordingLock(BaseDistributedLock):
    """记录型测试锁：记录调用序列，`acquire` 结果可配（供 hold 上下文用例）。"""

    def __init__(self, *, acquire_ok: bool = True) -> None:
        """初始化。

        Args:
            acquire_ok: `acquire` 是否成功（False 模拟未取到锁）。
        """
        super().__init__()
        self.calls: list[tuple[str, object]] = []
        self._acquire_ok = acquire_ok

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """记录调用并返回固定令牌（或 None）。

        Args:
            key: 锁 key。
            ttl: 锁 TTL。
            wait: 等待时长。

        Returns:
            str | None: 令牌或 None。
        """
        self.calls.append(("acquire", (key, ttl, wait)))
        return "token-1" if self._acquire_ok else None

    async def release(self, key: str, token: str) -> bool:
        """记录释放调用。

        Args:
            key: 锁 key。
            token: 锁令牌。

        Returns:
            bool: True。
        """
        self.calls.append(("release", (key, token)))
        return True

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """记录续租调用。

        Args:
            key: 锁 key。
            token: 锁令牌。
            ttl: 新的 TTL。

        Returns:
            bool: True。
        """
        self.calls.append(("extend", (key, token, ttl)))
        return True


@pytest.mark.kiwi_id(40)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseDistributedLock, BaseCapability)
    assert issubclass(NullDistributedLock, BaseDistributedLock)
    assert issubclass(NullDistributedLock, BaseNullObject)
    assert BaseDistributedLock.key == "distributed_lock"

    lock = NullDistributedLock()
    assert lock.placeholder is True
    assert "占位实现" in lock.describe()


@pytest.mark.kiwi_id(40)
def test_build_lock_key() -> None:
    """锁 key 拼接：租户形态 / 全局形态；默认 TTL 与等待时长常量就位。"""
    assert build_lock_key(tenant="t1", resource="engine:create") == "bms:t1:lock:engine:create"
    assert build_lock_key(tenant=None, resource="ddl:sys_user") == "bms:global:lock:ddl:sys_user"
    assert (DEFAULT_LOCK_TTL, DEFAULT_WAIT) == (30, 0.0)


@pytest.mark.kiwi_id(40)
async def test_null_lock_always_succeeds() -> None:
    """占位实现恒定成功：acquire 返回非空令牌，release / extend 成功（不连 Redis）。"""
    lock = NullDistributedLock()
    key = build_lock_key(tenant=None, resource="demo")

    token = await lock.acquire(key)
    assert isinstance(token, str)
    assert token
    assert await lock.release(key, token) is True
    assert await lock.extend(key, token, ttl=60) is True

    # 未持锁的 key 亦恒定成功（占位不校验持有状态）
    assert await lock.release(build_lock_key(tenant="t2", resource="demo"), "other-token") is True


@pytest.mark.kiwi_id(40)
async def test_hold_runs_critical_section_and_releases() -> None:
    """hold 上下文：进入可用令牌、参数透传、退出自动释放。"""
    lock = RecordingLock()
    key = build_lock_key(tenant="t1", resource="critical")
    ran = False

    async with lock.hold(key, ttl=5, wait=0.5) as token:
        ran = True
        assert token == "token-1"

    assert ran is True
    assert lock.calls == [("acquire", (key, 5, 0.5)), ("release", (key, "token-1"))]


@pytest.mark.kiwi_id(40)
async def test_hold_raises_conflict_when_not_acquired() -> None:
    """hold 未取到锁：抛 ConcurrentConflictError（10004 / 409），临界区不执行。"""
    lock = RecordingLock(acquire_ok=False)
    key = build_lock_key(tenant="t1", resource="critical")
    ran = False

    with pytest.raises(ConcurrentConflictError) as excinfo:
        async with lock.hold(key):
            ran = True

    assert ran is False
    assert excinfo.value.code == 10004
    assert excinfo.value.http_status == 409
    assert lock.calls == [("acquire", (key, DEFAULT_LOCK_TTL, DEFAULT_WAIT))]


@pytest.mark.kiwi_id(40)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位锁；路由经 get_distributed_lock 取到实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.distributed_lock, NullDistributedLock)

        @app.get("/lock")
        async def lock_info(lock: Annotated[BaseDistributedLock, Depends(get_distributed_lock)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
            return {"key": lock.key, "type": type(lock).__name__, "same": str(lock is app.state.distributed_lock)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/lock")

        assert resp.status_code == 200
        assert resp.json() == {"key": "distributed_lock", "type": "NullDistributedLock", "same": "True"}

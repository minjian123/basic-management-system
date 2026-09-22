"""幂等基座契约测试（Kiwi 43）：继承 / 常量与 key 口径 / 占位恒定首次 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_idempotency_store
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.idempotency.base import (
    DEFAULT_IDEMPOTENCY_TTL,
    IDEMPOTENCY_HEADER,
    IdempotencyStore,
    build_idempotency_key,
)
from bms_core.idempotency.null import NullIdempotencyStore


@pytest.mark.kiwi_id(43)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(IdempotencyStore, BaseCapability)
    assert issubclass(NullIdempotencyStore, IdempotencyStore)
    assert issubclass(NullIdempotencyStore, BaseNullObject)
    assert IdempotencyStore.key == "idempotency"

    store = NullIdempotencyStore()
    assert store.placeholder is True
    assert "占位实现" in store.describe()


@pytest.mark.kiwi_id(43)
def test_constants_and_build_key() -> None:
    """幂等键请求头、默认 TTL 与 key 口径。"""
    assert IDEMPOTENCY_HEADER == "Idempotency-Key"
    assert DEFAULT_IDEMPOTENCY_TTL == 86400
    assert build_idempotency_key(key="abc-1", tenant="t1") == "bms:t1:idem:abc-1"
    assert build_idempotency_key(key="abc-1") == "bms:global:idem:abc-1"


@pytest.mark.kiwi_id(43)
async def test_null_store_always_first() -> None:
    """占位幂等存储恒定首次（不连 Redis、不缓存结果）。"""
    store = NullIdempotencyStore()
    key = build_idempotency_key(key="abc-1", tenant="t1")
    assert await store.begin(key) is True
    assert await store.begin(key) is True
    assert await store.load(key) is None
    assert await store.save(key, {"ok": True}) is None


@pytest.mark.kiwi_id(43)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位幂等存储；路由经 get_idempotency_store 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.idempotency_store, NullIdempotencyStore)

        @app.post("/idem")
        async def idem_probe(  # pyright: ignore[reportUnusedFunction]
            store: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
        ) -> dict[str, object]:
            key = build_idempotency_key(key="abc-1", tenant="t1")
            first = await store.begin(key)
            await store.save(key, {"ok": True})
            return {"key": store.key, "type": type(store).__name__, "first": first, "cached": await store.load(key)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/idem")

        assert resp.status_code == 200
        assert resp.json() == {"key": "idempotency", "type": "NullIdempotencyStore", "first": True, "cached": None}

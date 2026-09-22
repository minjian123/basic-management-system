"""审计哈希链基座契约测试（Kiwi 57）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回与恒定通过 / 依赖解析。"""

import re
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_hash_chain
from bms_core.audit.hashchain import GENESIS_HASH, HASH_ALGORITHM, BaseHashChain, ChainVerifyResult, HashChainEntry
from bms_core.audit.null import NullHashChain
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_platform.main import ApplicationFactory, lifespan


@pytest.mark.kiwi_id(57)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseHashChain, BaseCapability)
    assert issubclass(NullHashChain, BaseHashChain)
    assert issubclass(NullHashChain, BaseNullObject)
    assert BaseHashChain.key == "hash_chain"

    chain = NullHashChain()
    assert chain.placeholder is True
    assert "占位实现" in chain.describe()


@pytest.mark.kiwi_id(57)
def test_constants() -> None:
    """链头与算法常量。"""
    assert GENESIS_HASH == "0" * 64
    assert re.fullmatch(r"0{64}", GENESIS_HASH) is not None
    assert HASH_ALGORITHM == "sha256"


@pytest.mark.kiwi_id(57)
def test_data_contracts_defaults_and_frozen() -> None:
    """`HashChainEntry` / `ChainVerifyResult` 默认值与不可变。"""
    entry = HashChainEntry(prev_hash=GENESIS_HASH, record={"a": 1}, record_hash="h1")
    assert entry.prev_hash == GENESIS_HASH
    assert ChainVerifyResult(valid=True).broken_index is None

    field = "valid"
    with pytest.raises(FrozenInstanceError):
        setattr(entry, field, False)


@pytest.mark.kiwi_id(57)
def test_null_compute_fixed() -> None:
    """占位计算固定返回占位哈希（不计算）。"""
    chain = NullHashChain()
    assert chain.compute(GENESIS_HASH, {"a": 1}) == "null-record-hash"


@pytest.mark.kiwi_id(57)
def test_null_verify_always_valid() -> None:
    """占位校验恒定通过。"""
    chain = NullHashChain()
    entries = (HashChainEntry(prev_hash=GENESIS_HASH, record={"a": 1}, record_hash="h1"),)
    assert chain.verify(entries) == ChainVerifyResult(valid=True, broken_index=None)
    assert chain.verify(()) == ChainVerifyResult(valid=True)


@pytest.mark.kiwi_id(57)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位哈希链；路由经 get_hash_chain 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.hash_chain, NullHashChain)

        @app.get("/hash-chain-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            chain: Annotated[BaseHashChain, Depends(get_hash_chain)],
        ) -> dict[str, object]:
            digest = chain.compute(GENESIS_HASH, {"a": 1})
            return {"key": chain.key, "type": type(chain).__name__, "digest": digest}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/hash-chain-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "hash_chain", "type": "NullHashChain", "digest": "null-record-hash"}

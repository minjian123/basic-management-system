"""审计哈希链实现护栏：规范化 / 单条计算 / 逐条校验 / 断裂定位（06_01）。"""

import hashlib

import pytest

from bms_core.audit.hashchain import GENESIS_HASH, ChainVerifyResult, HashChainEntry
from bms_core.audit.sha256 import Sha256HashChain, canonical_json
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList

pytestmark = pytest.mark.kiwi_id(2407)


def test_canonical_json_is_stable_and_sorted() -> None:
    """规范化：键排序、紧凑分隔符、非 ASCII 直出；集合类与普通映射同值同字节。"""
    plain = {"b": 2, "a": "中文", "c": [1, None]}
    stable = ConcurrentStableDict[str, object]({"c": ConcurrentStableList([1, None]), "a": "中文", "b": 2})
    assert canonical_json(stable) == '{"a":"中文","b":2,"c":[1,null]}'
    assert canonical_json(stable) == canonical_json(ConcurrentStableDict[str, object](plain))


def test_compute_matches_expected_sha256_and_genesis() -> None:
    """计算：空 prev 回落 GENESIS_HASH；结果等于 SHA256(prev + 规范化记录)。"""
    chain = Sha256HashChain()
    record = ConcurrentStableDict[str, object]({"id": "1", "action": "user:create"})
    expected = hashlib.sha256(f"{GENESIS_HASH}{canonical_json(record)}".encode()).hexdigest()
    assert chain.compute("", record) == expected
    assert chain.compute(GENESIS_HASH, record) == expected
    assert len(expected) == 64


def test_verify_valid_chain_and_broken_index() -> None:
    """校验：完整链通过；篡改记录哈希 / 前序哈希均定位到对应序号。"""
    chain = Sha256HashChain()
    first = ConcurrentStableDict[str, object]({"id": "1"})
    first_prev = GENESIS_HASH
    first_hash = chain.compute(first_prev, first)
    second = ConcurrentStableDict[str, object]({"id": "2"})
    second_hash = chain.compute(first_hash, second)
    entries = ConcurrentStableList(
        (
            HashChainEntry(prev_hash=first_prev, record=ConcurrentStableFrozenDict(first), record_hash=first_hash),
            HashChainEntry(prev_hash=first_hash, record=ConcurrentStableFrozenDict(second), record_hash=second_hash),
        )
    )
    assert chain.verify(entries) == ChainVerifyResult(valid=True)

    tampered = ConcurrentStableList(
        (
            entries[0],
            HashChainEntry(
                prev_hash=first_hash,
                record=ConcurrentStableFrozenDict(second),
                record_hash="0" * 64,
            ),
        )
    )
    assert chain.verify(tampered) == ChainVerifyResult(valid=False, broken_index=1)

    broken_prev = ConcurrentStableList(
        (
            entries[0],
            HashChainEntry(
                prev_hash="f" * 64,
                record=ConcurrentStableFrozenDict(second),
                record_hash=second_hash,
            ),
        )
    )
    assert chain.verify(broken_prev).broken_index == 1


def test_verify_empty_chain_is_valid() -> None:
    """空链视为完整（无记录可篡改）。"""
    assert Sha256HashChain().verify(ConcurrentStableList()).valid is True

"""雪花 ID 位段与生成器测试（Kiwi 2393）：126 位、WorkerId 边界、单调、回绕与回拨。"""

import types

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.id import (
    MAX_ID,
    MAX_WORKER_ID,
    SEQ_BITS,
    TIMESTAMP_BITS,
    WORKER_BITS,
    IdGeneratorFactory,
    SnowflakeGenerator,
)


def _fake_time_module(values: ConcurrentStableList[float]) -> types.SimpleNamespace:
    """构造只暴露 `time.time()` 的假 time 模块（值用尽后回落最后一个）。

    Args:
        values: 依次返回的时间戳（秒）。

    Returns:
        types.SimpleNamespace: 假 time 模块。
    """
    seq = iter(values)
    fallback = values[-1]
    return types.SimpleNamespace(time=lambda: next(seq, fallback))


@pytest.mark.kiwi_id(2393)
def test_bit_layout_and_max_id() -> None:
    """位段 48 + 40 + 38 = 126；MAX_ID 为 38 位十进制（DECIMAL(38,0) 上限内）。"""
    assert (TIMESTAMP_BITS, WORKER_BITS, SEQ_BITS) == (48, 40, 38)
    assert TIMESTAMP_BITS + WORKER_BITS + SEQ_BITS == 126
    assert MAX_ID == (1 << 126) - 1
    assert MAX_ID.bit_length() == 126
    assert len(str(MAX_ID)) == 38
    assert MAX_WORKER_ID == (1 << 40) - 1


@pytest.mark.kiwi_id(2393)
def test_worker_id_bounds() -> None:
    """WorkerId 0 与 2^40-1 合法，越界抛 ValueError。"""
    assert SnowflakeGenerator(0).next_id() > 0
    assert SnowflakeGenerator(MAX_WORKER_ID).next_id() > 0
    with pytest.raises(ValueError):
        SnowflakeGenerator(MAX_WORKER_ID + 1)
    with pytest.raises(ValueError):
        SnowflakeGenerator(-1)
    with pytest.raises(ValueError):
        IdGeneratorFactory().create(MAX_WORKER_ID + 1)


@pytest.mark.kiwi_id(2393)
def test_id_segments_and_monotonic() -> None:
    """同进程连续 ID 严格递增，且机器段等于 WorkerId、总位宽不超过 126。"""
    generator = SnowflakeGenerator(worker_id=7)
    ids = [generator.next_id() for _ in range(500)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert all(((identifier >> SEQ_BITS) & MAX_WORKER_ID) == 7 for identifier in ids)
    assert all(identifier <= MAX_ID for identifier in ids)


@pytest.mark.kiwi_id(2393)
def test_sequence_wrap_waits_next_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    """序列回绕（压缩到 2 位）后等待下一毫秒，不重复、不回退。"""
    monkeypatch.setattr("bms_core.core.id._SEQ_MASK", 1)
    start = 2_000_000_000.0
    monkeypatch.setattr(
        "bms_core.core.id.time",
        _fake_time_module(ConcurrentStableList([start, start, start, start + 0.001])),
    )
    generator = SnowflakeGenerator(worker_id=0)
    first = generator.next_id()
    second = generator.next_id()
    third = generator.next_id()
    assert len({first, second, third}) == 3
    assert third > second > first
    assert (third >> (SEQ_BITS + WORKER_BITS)) == (first >> (SEQ_BITS + WORKER_BITS)) + 1


def test_reconfigure_validates_worker_id() -> None:
    """重设 WorkerId：越界直接拒绝（保持生成器实例身份不变）。"""
    generator = SnowflakeGenerator(worker_id=1)
    generator.reconfigure(2)
    with pytest.raises(ValueError, match="worker_id 必须在"):
        generator.reconfigure(MAX_WORKER_ID + 1)


@pytest.mark.kiwi_id(2393)
def test_clock_rollback_within_limit_and_beyond(monkeypatch: pytest.MonkeyPatch) -> None:
    """小幅回拨（≤5ms）追平继续发号；大幅回拨抛 RuntimeError。"""
    base = 2_000_000_000.0
    monkeypatch.setattr(
        "bms_core.core.id.time",
        _fake_time_module(ConcurrentStableList([base, base - 0.004, base])),
    )
    generator = SnowflakeGenerator(worker_id=1)
    first = generator.next_id()
    second = generator.next_id()
    assert second > first

    monkeypatch.setattr(
        "bms_core.core.id.time",
        _fake_time_module(ConcurrentStableList([base, base - 1.0, base])),
    )
    other = SnowflakeGenerator(worker_id=1)
    other.next_id()
    with pytest.raises(RuntimeError):
        other.next_id()

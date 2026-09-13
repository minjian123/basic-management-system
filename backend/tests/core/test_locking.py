"""并发锁原语测试（Kiwi 16）。"""

import pytest

from app.core.locking import LockGuard, LockStrategy, ReadWriteLock


@pytest.mark.kiwi_id(16)
def test_read_write_lock_read_read_write() -> None:
    """读写锁：读可重入（并行），写独占。"""
    lock = ReadWriteLock()
    with lock.read(), lock.read():
        pass
    with lock.write():
        pass


@pytest.mark.kiwi_id(16)
def test_lock_guard_strategies() -> None:
    """策略守卫：RW / RLCK / SNAPSHOT 读写上下文均可用。"""
    for strategy in (LockStrategy.RW, LockStrategy.RLCK, LockStrategy.SNAPSHOT):
        guard = LockGuard(strategy)
        with guard.read(), guard.read():
            pass
        with guard.write():
            pass

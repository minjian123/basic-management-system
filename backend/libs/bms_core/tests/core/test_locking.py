"""并发锁原语测试（Kiwi 16）。"""

import threading
import time

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.locking import LockGuard, LockStrategy, ReadWriteLock


@pytest.mark.kiwi_id(16)
def test_locking_components_inherit_base_object() -> None:
    """锁组件纳入 L0 继承体系。"""
    assert issubclass(ReadWriteLock, BaseObject)
    assert issubclass(LockGuard, BaseObject)


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


@pytest.mark.kiwi_id(16)
def test_read_write_lock_write_reentrant_same_thread() -> None:
    """同线程写重入（2026-10-16 加固）：嵌套 `write()` 放行；重入期间仍独占（其他线程读等待）。"""
    lock = ReadWriteLock()
    other_read = threading.Event()

    def read_once() -> None:
        with lock.read():
            other_read.set()

    with lock.write(), lock.write():
        thread = threading.Thread(target=read_once)
        thread.start()
        assert not other_read.wait(0.1)
    thread.join(5)
    assert other_read.is_set()


@pytest.mark.kiwi_id(16)
def test_read_write_lock_read_inside_write_same_thread() -> None:
    """持写线程可直通 `read()`（免计数）：退出后无残留计数，后续独占写不受影响。"""
    lock = ReadWriteLock()
    with lock.write(), lock.read(), lock.write():
        pass
    entered = threading.Event()

    def write_once() -> None:
        with lock.write():
            entered.set()

    thread = threading.Thread(target=write_once)
    thread.start()
    thread.join(5)
    assert entered.is_set()


@pytest.mark.kiwi_id(16)
def test_read_write_lock_nested_read_ignores_waiting_writer() -> None:
    """已持读线程的嵌套读不受等待写者影响（挂起缺陷回归）；未持读的新读者仍按写优先排队。"""
    lock = ReadWriteLock()
    holder_in_read = threading.Event()
    writer_queued = threading.Event()
    nested_done = threading.Event()
    fresh_checked = threading.Event()
    writer_done = threading.Event()
    fresh_entered = threading.Event()

    def holder() -> None:
        with lock.read():
            holder_in_read.set()
            writer_queued.wait(5)  # 等写者进入排队后，再尝试同线程嵌套读
            with lock.read():
                nested_done.set()
            fresh_checked.wait(5)  # 主线程确认新读者被排队后再释放

    def write_once() -> None:
        with lock.write():
            writer_done.set()

    def fresh_read() -> None:
        with lock.read():
            fresh_entered.set()

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    assert holder_in_read.wait(5)
    writer = threading.Thread(target=write_once, daemon=True)
    writer.start()
    deadline = time.monotonic() + 5
    with lock._condition:  # pyright: ignore[reportPrivateUsage]  # 等写者进入排队（写优先）
        while lock._waiting_writers == 0:  # pyright: ignore[reportPrivateUsage]
            assert time.monotonic() < deadline, "写者未进入等待"
            lock._condition.wait(timeout=0.1)  # pyright: ignore[reportPrivateUsage]
    writer_queued.set()
    assert nested_done.wait(5)
    fresh = threading.Thread(target=fresh_read, daemon=True)
    fresh.start()
    assert not fresh_entered.wait(0.2)
    fresh_checked.set()
    holder_thread.join(5)
    writer.join(5)
    fresh.join(5)
    assert writer_done.is_set() and fresh_entered.is_set()


@pytest.mark.kiwi_id(16)
def test_read_write_lock_upgrade_waits_other_readers() -> None:
    """读→写升级：等其余读者退出后升级；升级完成时其余读者已全部退出。"""
    lock = ReadWriteLock()
    other_ready = threading.Event()
    other_release = threading.Event()
    wait_observed = threading.Event()

    def other_reader() -> None:
        with lock.read():
            other_ready.set()
            other_release.wait(5)

    def release_when_upgrading() -> None:
        deadline = time.monotonic() + 5
        with lock._condition:  # pyright: ignore[reportPrivateUsage]
            while time.monotonic() < deadline:
                if lock._upgraders_waiting > 0:  # pyright: ignore[reportPrivateUsage]
                    wait_observed.set()
                    break
                lock._condition.wait(timeout=0.1)  # pyright: ignore[reportPrivateUsage]
        other_release.set()

    other = threading.Thread(target=other_reader, daemon=True)
    other.start()
    assert other_ready.wait(5)
    releaser = threading.Thread(target=release_when_upgrading, daemon=True)
    releaser.start()
    with lock.read(), lock.write():
        assert lock._readers == 0  # pyright: ignore[reportPrivateUsage]  # 其余读者已退出
    other.join(5)
    releaser.join(5)
    assert wait_observed.is_set()
    assert not other.is_alive() and not releaser.is_alive()


@pytest.mark.kiwi_id(16)
def test_read_write_lock_upgrade_direct_when_sole_reader() -> None:
    """唯一读者读→写升级直接放行；升级期间其他线程写被排斥、退出后恢复读计数。"""
    lock = ReadWriteLock()
    blocked_writer_entered = threading.Event()

    def write_once() -> None:
        with lock.write():
            blocked_writer_entered.set()

    with lock.read():
        writer = threading.Thread(target=write_once, daemon=True)
        writer.start()
        with lock.write():
            assert not blocked_writer_entered.wait(0.1)
            assert lock._readers == 0  # pyright: ignore[reportPrivateUsage]
    writer.join(5)
    assert blocked_writer_entered.is_set()


@pytest.mark.kiwi_id(16)
def test_read_write_lock_reentrancy_preserves_exclusivity() -> None:
    """重入加固不减互斥：混合读写（含重入与单升级者）并发下无跨线程重叠。"""
    lock = ReadWriteLock()
    guard = threading.Lock()
    active_readers = 0
    active_writers = 0
    violations = ConcurrentStableList[str]()
    finished = ConcurrentStableList[str]()
    iterations = 60

    def reader() -> None:
        nonlocal active_readers
        for _ in range(iterations):
            with lock.read(), lock.read():
                with guard:
                    if active_writers:
                        violations.add("reader-vs-writer")
                    active_readers += 1
                time.sleep(0)
                with guard:
                    active_readers -= 1
        finished.add("reader")

    def writer() -> None:
        nonlocal active_writers
        for _ in range(iterations):
            with lock.write(), lock.write():
                with guard:
                    if active_writers or active_readers:
                        violations.add("writer-not-exclusive")
                    active_writers += 1
                time.sleep(0)
                with guard:
                    active_writers -= 1
        finished.add("writer")

    def upgrader() -> None:
        nonlocal active_writers
        for _ in range(iterations):
            with lock.read():
                time.sleep(0)
                with lock.write():
                    with guard:
                        if active_writers or active_readers:
                            violations.add("upgrade-not-exclusive")
                        active_writers += 1
                    time.sleep(0)
                    with guard:
                        active_writers -= 1
        finished.add("upgrader")

    threads = [
        threading.Thread(target=reader, daemon=True),
        threading.Thread(target=reader, daemon=True),
        threading.Thread(target=writer, daemon=True),
        threading.Thread(target=upgrader, daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(finished) == len(threads)  # 线程内异常会吞掉完成标记，防「假绿」
    assert not violations

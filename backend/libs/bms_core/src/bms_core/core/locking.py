"""core 层并发锁原语：锁策略、读写锁与策略守卫（公共横切）。

- 供进程内并发集合（`ConcurrentSorted*`）与后续需要锁的模块复用
  （连接并发保护、幂等、限流等），避免各处自研锁。
- 锁内禁止 IO 与外部回调（调用方约束）。
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum

from bms_core.core.objects import BaseFrameworkObject


class LockStrategy(StrEnum):
    """进程内并发结构的锁策略。"""

    RW = "rw"
    """读写锁（默认）：读并行、写独占、写优先防饿死。"""

    RLCK = "rlock"
    """单锁：实现最简，读写互斥。"""

    SHARDED = "sharded"
    """分片锁：按键哈希分桶（仅 dict/set；list 自动降级为读写锁）。"""

    SNAPSHOT = "snapshot"
    """快照替换：读无锁、写复制后原子替换（读极多写极少）。"""


class ReadWriteLock(BaseFrameworkObject):
    """读写锁：读并行、写独占、写优先（有等待写者时新读者排队，防饿死）。

    **同线程重入（2026-10-16 加固）**：锁持有线程可安全嵌套进入——防「持锁期间同步回调
    再入同一锁」自锁死（如 GC 终结器在锁内触发嵌套日志 / 解引用集合时的偶发挂起）。
    重入为防御性兜底，不改变「锁内禁止 IO 与外部回调」的调用方约束：

    - `write()` 可重入：持写线程再次 `write()` 直接放行（最外层负责释放），重入期间仍独占；
    - 持写线程可 `read()`：写已独占，免计数直通；
    - `read()` 可嵌套：已持读线程的嵌套 `read()` 不受等待写者影响，按次数计数；
    - 读→写**升级**：持读线程申请 `write()`，等其余读者全部退出后升级为写（写优先保证
      等待期间无新读者进入），释放时恢复原读计数；
    - **不支持**：多线程「同时」升级互等（与「锁内禁止外部回调」同类使用约束，须避免）。
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0
        self._upgraders_waiting = 0
        self._writer_thread: int | None = None
        self._local = threading.local()

    @contextmanager
    def read(self) -> Generator[None]:
        """读上下文：无写者且无等待写者时进入，可并行；同线程可嵌套、持写线程可直通。"""
        ident = threading.get_ident()
        if self._writer and self._writer_thread == ident:
            yield
            return
        depth = getattr(self._local, "depth", 0)
        with self._condition:
            if depth > 0:
                # 同线程嵌套读：本线程持读期间不会有写者，直接计数放行（不受等待写者影响）
                self._readers += 1
            else:
                while self._writer or self._waiting_writers:
                    self._condition.wait()
                self._readers += 1
        self._local.depth = depth + 1
        try:
            yield
        finally:
            with self._condition:
                self._readers -= 1
                self._local.depth = depth
                if self._readers == 0 or self._upgraders_waiting:
                    self._condition.notify_all()

    @contextmanager
    def write(self) -> Generator[None]:
        """写上下文：独占（无读者且无写者）；同线程可重入、持读线程可升级。"""
        ident = threading.get_ident()
        if self._writer and self._writer_thread == ident:
            yield
            return
        depth = getattr(self._local, "depth", 0)
        with self._condition:
            self._waiting_writers += 1
            try:
                if depth > 0:
                    # 读→写升级：等其余读者退出；读者退出时若见升级者等待会唤醒（防丢唤醒）
                    self._upgraders_waiting += 1
                    try:
                        while self._writer or self._readers != depth:
                            self._condition.wait()
                    finally:
                        self._upgraders_waiting -= 1
                else:
                    while self._writer or self._readers:
                        self._condition.wait()
            finally:
                self._waiting_writers -= 1
            if depth > 0:
                self._readers -= depth
                self._local.depth = 0
            self._writer = True
            self._writer_thread = ident
        try:
            yield
        finally:
            with self._condition:
                self._writer = False
                self._writer_thread = None
                if depth > 0:
                    self._readers += depth
                    self._local.depth = depth
                self._condition.notify_all()


class LockGuard(BaseFrameworkObject):
    """按策略统一读/写上下文（SNAPSHOT 读不取锁、写取互斥锁）。"""

    def __init__(self, strategy: LockStrategy) -> None:
        self.strategy = strategy
        self._rw: ReadWriteLock | None = ReadWriteLock() if strategy is LockStrategy.RW else None
        self._lock = threading.RLock()

    @contextmanager
    def read(self) -> Generator[None]:
        """读上下文。"""
        if self._rw is not None:
            with self._rw.read():
                yield
        elif self.strategy is LockStrategy.SNAPSHOT:
            yield
        else:
            with self._lock:
                yield

    @contextmanager
    def write(self) -> Generator[None]:
        """写上下文。"""
        if self._rw is not None:
            with self._rw.write():
                yield
        else:
            with self._lock:
                yield

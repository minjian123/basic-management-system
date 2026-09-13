"""core 层并发锁原语：锁策略、读写锁与策略守卫（公共横切）。

- 供进程内并发集合（`ConcurrentSorted*`）与后续需要锁的模块复用
  （连接并发保护、幂等、限流等），避免各处自研锁。
- 锁内禁止 IO 与外部回调（调用方约束）。
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from enum import StrEnum

from app.core.base import BaseObject


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


class ReadWriteLock(BaseObject):
    """读写锁：读并行、写独占、写优先（有等待写者时新读者排队，防饿死）。"""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    @contextmanager
    def read(self) -> Generator[None]:
        """读上下文：无写者且无等待写者时进入，可并行。"""
        with self._condition:
            while self._writer or self._waiting_writers:
                self._condition.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._condition:
                self._readers -= 1
                if self._readers == 0:
                    self._condition.notify_all()

    @contextmanager
    def write(self) -> Generator[None]:
        """写上下文：独占（无读者且无写者）。"""
        with self._condition:
            self._waiting_writers += 1
            while self._writer or self._readers:
                self._condition.wait()
            self._waiting_writers -= 1
            self._writer = True
        try:
            yield
        finally:
            with self._condition:
                self._writer = False
                self._condition.notify_all()


class LockGuard(BaseObject):
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

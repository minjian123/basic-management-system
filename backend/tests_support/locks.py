"""跨进程测试锁（薄壳）：实现单源在 `bms_core.testing.locks`。

单库化（04-6-2）后共享库上的「先查后写 / 先查后建」必须串行；实现落在基座库，产品仓与
本仓的测试侧统一引用，避免两份实现各配一把锁、互相看不见。
"""

from bms_core.testing.locks import DEFAULT_TIMEOUT, file_lock

__all__ = ("DEFAULT_TIMEOUT", "file_lock")

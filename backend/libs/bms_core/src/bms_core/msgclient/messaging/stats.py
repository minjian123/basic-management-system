"""消息收发客户端计数器（msg 03-6 详细设计 §10）：只做本地排障。

**为什么不接 Prometheus**：服务端指标才是权威口径（客户端看不到 ISR、HW、复制延迟）。
这里只回答「我发了多少、重试了几次、改投了几次、为什么失败」，进程内可见即可，由调用方按需暴露。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict

__all__ = ["ClientStats"]


class ClientStats:
    """进程内计数器（键为「指标名 + 标签串」，与 Prometheus 样本标识同构）。

    Attributes:
        _counters: 指标键 → 累计次数（插入序，便于断言与排障输出稳定）。
    """

    def __init__(self) -> None:
        """初始化空计数器。"""
        self._counters: ConcurrentStableDict[str, int] = ConcurrentStableDict()

    def incr(self, name: str, **labels: str) -> None:
        """自增一个指标（无标签时键就是指标名）。

        Args:
            name: 指标名（如 `requests_total`）。
            labels: 标签键值（如 `op="publish"`）。
        """
        key = name if not labels else f"{name}{{{','.join(f'{key}={value}' for key, value in labels.items())}}}"
        self._counters.set(key, self._counters.get(key, 0) + 1)

    def snapshot(self) -> ConcurrentStableFrozenDict[str, int]:
        """取当前计数快照（不可变，调用方随便存）。

        Returns:
            ConcurrentStableFrozenDict[str, int]: 指标键 → 次数。
        """
        return ConcurrentStableFrozenDict({key: value for key, value in self._counters.items()})

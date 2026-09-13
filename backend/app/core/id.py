"""core 层雪花 ID 生成器：标准雪花（时间戳 + WorkerId + 序列）。

- 位宽 41 + 10 + 12 = 63 位（正数）：约 69 年、1024 个 Worker、单 Worker 4096 ID/ms
  （≈ 400 万/秒），支持分布式与高并发；ID 超过 JS 安全整数，接口按字符串输出。
- WorkerId 由部署 / 配置注入（环境变量 `BMS_WORKER_ID` 或 `configure_id_generator`），
  部署须保证全局唯一；Redis 自动注册 WorkerId 作为后续回补。
- 进程内线程安全；同毫秒序列用尽等待下一毫秒；时钟小幅回拨等待追平，超阈值抛错。
"""

import os
import threading
import time

_EPOCH_MS = 1_600_000_000_000  # 自定义基点（约 2020-09-13 UTC），固定不变
_WORKER_BITS = 10
_SEQ_BITS = 12
_MAX_WORKER_ID = (1 << _WORKER_BITS) - 1
_SEQ_MASK = (1 << _SEQ_BITS) - 1
_WORKER_SHIFT = _SEQ_BITS
_TIMESTAMP_SHIFT = _SEQ_BITS + _WORKER_BITS
_MAX_ROLLBACK_MS = 5


class SnowflakeGenerator:
    """标准雪花生成器（单实例线程安全）。"""

    def __init__(self, worker_id: int = 0) -> None:
        """初始化生成器。

        Args:
            worker_id: 工作节点编号（0 ~ 1023）。

        Raises:
            ValueError: worker_id 越界。
        """
        if not 0 <= worker_id <= _MAX_WORKER_ID:
            raise ValueError(f"worker_id 必须在 0 ~ {_MAX_WORKER_ID} 之间")
        self._worker_id = worker_id
        self._lock = threading.Lock()
        self._last_ts = -1
        self._seq = 0

    def next_id(self) -> int:
        """生成下一个 ID。

        Returns:
            int: 雪花 ID。

        Raises:
            RuntimeError: 时钟回拨超过允许阈值。
        """
        with self._lock:
            ts = int(time.time() * 1000)
            if ts < self._last_ts:
                if self._last_ts - ts > _MAX_ROLLBACK_MS:
                    raise RuntimeError("时钟回拨过大，拒绝生成雪花 ID")
                ts = self._last_ts
            if ts == self._last_ts:
                self._seq = (self._seq + 1) & _SEQ_MASK
                if self._seq == 0:
                    while ts <= self._last_ts:
                        ts = int(time.time() * 1000)
            else:
                self._seq = 0
            self._last_ts = ts
            return ((ts - _EPOCH_MS) << _TIMESTAMP_SHIFT) | (self._worker_id << _WORKER_SHIFT) | self._seq


def initial_worker_id() -> int:
    """从环境变量读取初始 WorkerId（`BMS_WORKER_ID`，非法回退 0）。

    Returns:
        int: WorkerId。
    """
    try:
        value = int(os.environ.get("BMS_WORKER_ID", "0"))
    except ValueError:
        return 0
    return value if 0 <= value <= _MAX_WORKER_ID else 0


_generator = SnowflakeGenerator(initial_worker_id())
_configure_lock = threading.Lock()


def configure_id_generator(worker_id: int) -> None:
    """配置全局生成器的 WorkerId（部署 / 配置基座调用）。

    Args:
        worker_id: 工作节点编号（0 ~ 1023）。
    """
    global _generator
    with _configure_lock:
        _generator = SnowflakeGenerator(worker_id)


def generate_id() -> int:
    """生成下一个全局唯一 ID。

    Returns:
        int: 雪花 ID。
    """
    return _generator.next_id()

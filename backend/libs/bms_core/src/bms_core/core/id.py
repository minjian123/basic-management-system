"""core 层雪花 ID 生成器：标准雪花（时间戳 + WorkerId + 序列）。

- 位宽 41 + 10 + 12 = 63 位（正数）：约 69 年、1024 个 Worker、单 Worker 4096 ID/ms
  （≈ 400 万/秒），支持分布式与高并发；ID 超过 JS 安全整数，接口按字符串输出。
- WorkerId 由配置基座注入（`BMS_APP__WORKER_ID`，启动期经默认生成器重设生效），
  部署须保证全局唯一；Redis 自动注册 WorkerId 作为后续回补。
- 进程内线程安全；同毫秒序列用尽等待下一毫秒；时钟小幅回拨等待追平，超阈值抛错。
- 工厂链：`IdGeneratorFactory → BaseIdFactory → BaseFactory → BasePluggable`（02-54）。
"""

import threading
import time

from bms_core.core.base import BaseObject
from bms_core.core.factory import BaseIdFactory

_EPOCH_MS = 1_600_000_000_000  # 自定义基点（约 2020-09-13 UTC），固定不变
_WORKER_BITS = 10
_SEQ_BITS = 12
_MAX_WORKER_ID = (1 << _WORKER_BITS) - 1
_SEQ_MASK = (1 << _SEQ_BITS) - 1
_WORKER_SHIFT = _SEQ_BITS
_TIMESTAMP_SHIFT = _SEQ_BITS + _WORKER_BITS
_MAX_ROLLBACK_MS = 5


def _validate_worker_id(worker_id: int) -> None:
    """校验 WorkerId 取值。

    Args:
        worker_id: 工作节点编号。

    Raises:
        ValueError: 越界。
    """
    if not 0 <= worker_id <= _MAX_WORKER_ID:
        raise ValueError(f"worker_id 必须在 0 ~ {_MAX_WORKER_ID} 之间")


class SnowflakeGenerator(BaseObject):
    """标准雪花生成器（单实例线程安全）。"""

    def __init__(self, worker_id: int = 0) -> None:
        """初始化生成器。

        Args:
            worker_id: 工作节点编号（0 ~ 1023）。

        Raises:
            ValueError: worker_id 越界。
        """
        _validate_worker_id(worker_id)
        self._worker_id = worker_id
        self._lock = threading.Lock()
        self._last_ts = -1
        self._seq = 0

    def reconfigure(self, worker_id: int) -> None:
        """重设 WorkerId（配置基座启动接线；保持生成器实例身份不变）。

        Args:
            worker_id: 工作节点编号（0 ~ 1023）。

        Raises:
            ValueError: worker_id 越界。
        """
        _validate_worker_id(worker_id)
        with self._lock:
            self._worker_id = worker_id

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


class IdGeneratorFactory(BaseIdFactory[int, SnowflakeGenerator]):
    """雪花 ID 生成器工厂：按 WorkerId 产出生成器实例。"""

    key: str = "id_generator"

    def validate(self, options: int) -> None:
        """校验 WorkerId。

        Args:
            options: 工作节点编号。

        Raises:
            ValueError: 越界。
        """
        _validate_worker_id(options)

    def create(self, options: int = 0) -> SnowflakeGenerator:
        """创建生成器。

        Args:
            options: 工作节点编号（0 ~ 1023）；缺省 0。

        Returns:
            SnowflakeGenerator: 生成器实例。
        """
        self.validate(options)
        return SnowflakeGenerator(options)


id_generator: SnowflakeGenerator = IdGeneratorFactory().create(0)
"""进程级默认生成器实例（配置基座经 `reconfigure` 重设 WorkerId；ORM 默认值取 `next_id`）。"""

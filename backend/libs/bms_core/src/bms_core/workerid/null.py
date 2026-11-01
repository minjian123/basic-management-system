"""WorkerId 注册缺省实现 `NullWorkerIdRegistry`（插件名 `null`，03_06）。

用途：`[worker_id].enabled=false`（单测公共夹具）与 `provider=null`（应急旁路）—— 不访问 Redis，
直接采用 `[app].worker_id`；生产环境若仍为 0 由 `assert_ready()` 拒启（与启用态同一判据）。
"""

from __future__ import annotations

from bms_core.workerid.base import SOURCE_CONFIG, SOURCE_NONE, BaseWorkerIdRegistry

__all__ = ["NullWorkerIdRegistry"]


class NullWorkerIdRegistry(BaseWorkerIdRegistry):
    """旁路实现：直接用配置值，无租约、无心跳、无释放。"""

    def acquire(self) -> None:
        """采用 `[app].worker_id`（幂等）。"""
        if self._source != SOURCE_NONE:
            return
        self._apply(self._settings.app.worker_id, SOURCE_CONFIG, None)
        self._log_acquired()

    def release(self) -> None:
        """清除生效标记（无租约可释放；幂等）。"""
        self._source = SOURCE_NONE

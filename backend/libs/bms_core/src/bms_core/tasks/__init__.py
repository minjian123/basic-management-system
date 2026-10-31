"""tasks：任务调度基座（执行体契约 + cron + 执行体登记 + 内置任务）。

- `BaseTask` / `NullTask`：历史插件位（`task` 能力域，一进程一任务的语义），01_02 起不再扩容；
- 调度器 / 执行器（`scheduler` / `worker` / `store` / `queue`）住在本包，宿主为 `ops/task_scheduler.py`，
  **不进插件装配面**（详见《详细设计 · 任务调度》§4.7）。
"""

from bms_core.tasks.base import BaseTask

__all__ = ["BaseTask"]

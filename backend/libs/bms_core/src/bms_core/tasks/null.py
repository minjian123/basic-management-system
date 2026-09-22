"""tasks 能力域缺省实现（Null Object）：任务不执行（05 补缺）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.tasks.base import BaseTask

__all__ = ["NullTask"]


class NullTask(BaseTask, BaseNullObject):
    """占位任务：执行体空操作（不入调度、不落执行记录）。"""

    @property
    def name(self) -> str:
        """任务名（占位固定 `null_task`）。

        Returns:
            str: 占位任务名。
        """
        return "null_task"

    def run(self, *args: object, **kwargs: object) -> object:
        """任务执行体（占位空操作）。

        Args:
            *args: 位置参数（占位忽略）。
            **kwargs: 关键字参数（占位忽略）。

        Returns:
            object: None。
        """
        return None

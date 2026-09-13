"""tasks：Celery 任务基座契约（调度入库与执行记录在阶段六回补）。"""

from abc import ABC, abstractmethod

from app.core.base import BaseObject


class BaseTask(BaseObject, ABC):
    """任务调度基座契约：名称 / 队列 / 执行体。"""

    queue: str = "default"

    @property
    @abstractmethod
    def name(self) -> str:
        """任务名（`sys_task.name` 唯一标识）。"""

    @abstractmethod
    def run(self, *args: object, **kwargs: object) -> object:
        """任务执行体（调度入库 / 执行记录回补）。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            object: 执行结果。
        """

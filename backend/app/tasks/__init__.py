"""tasks：Celery 任务基座契约（调度入库与执行记录在阶段六回补）。"""

from app.tasks.base import BaseTask

__all__ = ["BaseTask"]

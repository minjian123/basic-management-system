"""tasks：Celery 任务基座契约（调度入库与执行记录在阶段六回补）。"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin


class BaseTask(BasePluggable, ABC):
    """任务调度基座契约：名称 / 队列 / 执行体。"""

    key: str = "task"
    plugin_key: str = "task"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

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


def get_task(request: Request) -> BaseTask:
    """依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

    Args:
        request: 应用请求（取装配 settings）。

    Returns:
        BaseTask: 应用装配的任务实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTask",
        resolve_plugin(
            "task",
            settings.task.provider,
            expected_version=BaseTask.contract_version,
        ),
    )

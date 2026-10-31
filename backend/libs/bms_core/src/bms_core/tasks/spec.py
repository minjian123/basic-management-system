"""任务运行期数据契约：运行规格 / 执行结果 / 执行上下文。

- `TaskRunSpec`：队列载荷解码结果（一次待执行任务的定位信息），**只带定位不带定义全量**——
  执行前按 `log_id` 回读记录，避免「改了定义但队列里是旧定义」的歧义；
- `TaskResult`：执行体返回值（三终态 `success` / `failed` / `skipped` 由执行器统一落库并发事件）；
- `TaskContext`：执行体拿到的上下文（规格 + 已解析参数 + 租户库会话开合口）。

本模块**不含 IO**：参数解析是纯函数，会话开合由执行器注入可调用对象（执行体不自己建连接）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TaskArgsInvalidError
from bms_core.core.roots import BaseDataContract, BaseValueObject
from bms_core.models.base import to_stable_value
from bms_core.models.platform.task import (
    TASK_RUN_FAILED,
    TASK_RUN_SKIPPED,
    TASK_RUN_SUCCESS,
    TASK_TRIGGER_SCHEDULE,
)

__all__ = [
    "TaskArgs",
    "TaskContext",
    "TaskHandler",
    "TaskResult",
    "TaskRunSpec",
    "parse_task_args",
]

TaskArgs = ConcurrentStableDict[str, object] | ConcurrentStableList[Any]
"""任务参数（JSON 对象或数组；解析后统一为稳定集合类）。"""

TaskHandler = Callable[["TaskContext"], Awaitable["TaskResult"]]
"""执行体签名：`async def handler(ctx) -> TaskResult`。"""


def parse_task_args(raw: str | None) -> TaskArgs | None:
    """解析任务参数原文（JSON 对象或数组）。

    Args:
        raw: 参数原文（`sys_task.args`；空 / None 表示无参）。

    Returns:
        TaskArgs | None: 解析结果（稳定集合类）；无参返回 None。

    Raises:
        TaskArgsInvalidError: 非 JSON、或顶层既非对象也非数组（`70004`）。
    """
    if raw is None or not raw.strip():
        return None
    try:
        loaded: object = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TaskArgsInvalidError(f"任务参数不是合法 JSON：{exc.msg}") from exc
    if isinstance(loaded, dict):
        mapping: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {str(key): to_stable_value(item) for key, item in cast("dict[object, object]", loaded).items()}
        )
        return mapping
    if isinstance(loaded, list):
        return ConcurrentStableList(to_stable_value(item) for item in cast("list[object]", loaded))
    raise TaskArgsInvalidError("任务参数顶层须为 JSON 对象或数组")


@dataclass(frozen=True)
class TaskRunSpec(BaseValueObject):
    """一次待执行任务的运行规格（队列载荷的领域形态）。"""

    db_key: str
    """租户库键（执行体取库会话的依据）。"""

    task_id: int
    """任务定义主键（`sys_task.id`）。"""

    log_id: int
    """执行记录主键（`sys_task_log.id`；执行器按它回写状态）。"""

    run_id: str
    """本次执行标识（UUID；日志与事件串联）。"""

    code: str
    """任务代码（`sys_task.code`，同时是内置 handler 注册键）。"""

    handler: str
    """执行体点分路径（`module:attr`）。"""

    args_json: str | None = None
    """参数原文（解析延后到执行前，避免载荷与记录不一致）。"""

    trigger_source: str = TASK_TRIGGER_SCHEDULE
    """触发来源（`schedule` / `manual`）。"""


@dataclass(frozen=True)
class TaskResult(BaseValueObject):
    """执行体返回值（执行器据此落执行记录并决定终态）。"""

    status: str
    """终态（`success` / `failed` / `skipped`）。"""

    message: str = ""
    """给运营看的一句话说明（`skipped` 必填归口说明）。"""

    output: str | None = None
    """成功输出摘要（按 `result_max_chars` 截断后落 `sys_task_log.result`）。"""

    @classmethod
    def success(cls, message: str = "", output: str | None = None) -> TaskResult:
        """构造成功结果。

        Args:
            message: 说明。
            output: 输出摘要。

        Returns:
            TaskResult: 成功结果。
        """
        return cls(status=TASK_RUN_SUCCESS, message=message, output=output)

    @classmethod
    def failed(cls, message: str, output: str | None = None) -> TaskResult:
        """构造失败结果（执行体主动判定失败；异常由执行器捕获后转此态）。

        Args:
            message: 失败摘要。
            output: 附加输出。

        Returns:
            TaskResult: 失败结果。
        """
        return cls(status=TASK_RUN_FAILED, message=message, output=output)

    @classmethod
    def skipped(cls, message: str) -> TaskResult:
        """构造跳过结果（已调度但执行体判定无需执行，`message` 写归口说明）。

        Args:
            message: 跳过原因。

        Returns:
            TaskResult: 跳过结果。
        """
        return cls(status=TASK_RUN_SKIPPED, message=message)


@dataclass
class TaskContext(BaseDataContract):
    """执行上下文：规格 + 已解析参数 + 租户库会话开合口。"""

    run: TaskRunSpec
    """运行规格。"""

    args: TaskArgs | None = None
    """已解析参数（无参为 None）。"""

    open_session: Callable[[], AbstractAsyncContextManager[Any]] | None = field(default=None, repr=False)
    """租户库会话开合口（执行器注入；执行体不自建连接 / 不另起事件循环）。"""

    def session(self) -> AbstractAsyncContextManager[Any]:
        """取租户库会话上下文（`async with ctx.session() as session:`）。

        Returns:
            AbstractAsyncContextManager[Any]: 会话上下文。

        Raises:
            RuntimeError: 执行器未注入会话开合口（装配缺失，属编码错误而非业务错误）。
        """
        if self.open_session is None:
            raise RuntimeError("任务执行上下文未注入会话开合口（open_session）")
        return self.open_session()

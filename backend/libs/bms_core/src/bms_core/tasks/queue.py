"""任务队列：Redis LIST 承载的待执行消息（`LPUSH` 入队 / `BRPOP` 出队）。

- **单条全局队列**：`BRPOP` 天然「一个消费者拿一条」，多副本无需再分片；租户隔离靠载荷里的 `db_key`；
- **载荷只带定位**（任务 id / 记录 id / 运行 id / handler / 参数原文），不带宽定义：
  执行前可按 `log_id` 回读记录，避免「改了定义但队列里是旧定义」的歧义；
- **脏消息不抛异常**：`pop` 返回 `TaskPopOutcome`（超时 / 正常 / 不可解析三态），
  由执行器决定记日志与指标——队列层不做业务判定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenSet
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.models.platform.task import TASK_TRIGGER_MANUAL, TASK_TRIGGER_SCHEDULE
from bms_core.redis.base import shared_async_client
from bms_core.tasks.spec import TaskRunSpec

__all__ = ["DEFAULT_QUEUE_KEY", "TaskPopOutcome", "TaskQueue"]

DEFAULT_QUEUE_KEY = "bms:global:task:queue"
"""缺省队列键（`[task_scheduler].queue_key` 可覆盖）。"""

_KEY_DB = "db_key"
_KEY_TASK_ID = "task_id"
_KEY_LOG_ID = "log_id"
_KEY_RUN_ID = "run_id"
_KEY_CODE = "code"
_KEY_HANDLER = "handler"
_KEY_ARGS = "args_json"
_KEY_TRIGGER = "trigger_source"

_TRIGGER_SOURCES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    (TASK_TRIGGER_SCHEDULE, TASK_TRIGGER_MANUAL)
)


@dataclass(frozen=True)
class TaskPopOutcome(BaseValueObject):
    """出队结果：正常 / 超时 / 不可解析三态。"""

    spec: TaskRunSpec | None = None
    """解析成功的运行规格；超时与不可解析为 None。"""

    error: str | None = None
    """不可解析原因（超时为 None）。"""

    @property
    def timed_out(self) -> bool:
        """是否「队列空、等待超时」。

        Returns:
            bool: 超时 True。
        """
        return self.spec is None and self.error is None


class TaskQueue(BaseFrameworkObject):
    """待执行消息队列（惰性取共享 Redis 客户端）。"""

    def __init__(self, *, client: AsyncRedis | None = None, key: str = DEFAULT_QUEUE_KEY) -> None:
        """初始化。

        Args:
            client: 异步客户端（测试注入 `fakeredis`；缺省取进程共享客户端）。
            key: 队列键。
        """
        self._client = client
        self._key = key

    @property
    def key(self) -> str:
        """队列键。

        Returns:
            str: 队列键。
        """
        return self._key

    def _redis(self) -> AsyncRedis:
        """取异步客户端（显式注入优先）。

        Returns:
            AsyncRedis: 客户端实例。
        """
        return self._client if self._client is not None else shared_async_client()

    async def push(self, spec: TaskRunSpec) -> None:
        """入队（`LPUSH`；配合 `BRPOP` 即先进先出）。

        Args:
            spec: 运行规格。
        """
        await self._redis().lpush(self._key, encode_spec(spec))

    async def pop(self, timeout: int = 1) -> TaskPopOutcome:
        """出队（`BRPOP`，阻塞至多 `timeout` 秒）。

        Args:
            timeout: 阻塞秒数。

        Returns:
            TaskPopOutcome: 三态结果。
        """
        item = await self._redis().brpop([self._key], timeout=timeout)
        if item is None:
            return TaskPopOutcome()
        spec, error = decode_spec(item[1])
        return TaskPopOutcome(spec=spec, error=error)


def encode_spec(spec: TaskRunSpec) -> str:
    """把运行规格编码为队列载荷（JSON）。

    Args:
        spec: 运行规格。

    Returns:
        str: JSON 文本。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            _KEY_DB: spec.db_key,
            _KEY_TASK_ID: spec.task_id,
            _KEY_LOG_ID: spec.log_id,
            _KEY_RUN_ID: spec.run_id,
            _KEY_CODE: spec.code,
            _KEY_HANDLER: spec.handler,
            _KEY_ARGS: spec.args_json,
            _KEY_TRIGGER: spec.trigger_source,
        }
    )
    return json.dumps(dict(payload), ensure_ascii=False)


def decode_spec(raw: str | bytes) -> tuple[TaskRunSpec | None, str | None]:
    """解析队列载荷。

    Args:
        raw: 载荷原文（Redis 返回值可能是 bytes）。

    Returns:
        tuple[TaskRunSpec | None, str | None]: （规格, 错误原因）；成功时错误为 None。
    """
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return None, "队列载荷不是合法 JSON"
    if not isinstance(loaded, dict):
        return None, "队列载荷不是 JSON 对象"
    mapping: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {str(key): value for key, value in loaded.items()}
    )
    for required in (_KEY_DB, _KEY_RUN_ID, _KEY_CODE, _KEY_HANDLER, _KEY_TASK_ID, _KEY_LOG_ID):
        if mapping.get(required) in (None, ""):
            return None, f"队列载荷缺字段：{required}"
    task_id = mapping.get(_KEY_TASK_ID)
    log_id = mapping.get(_KEY_LOG_ID)
    if not isinstance(task_id, int) or not isinstance(log_id, int):
        return None, "队列载荷的 task_id / log_id 须为整数"
    trigger = mapping.get(_KEY_TRIGGER)
    args_json = mapping.get(_KEY_ARGS)
    return (
        TaskRunSpec(
            db_key=str(mapping.get(_KEY_DB)),
            task_id=task_id,
            log_id=log_id,
            run_id=str(mapping.get(_KEY_RUN_ID)),
            code=str(mapping.get(_KEY_CODE)),
            handler=str(mapping.get(_KEY_HANDLER)),
            args_json=args_json if isinstance(args_json, str) else None,
            trigger_source=str(trigger) if trigger in _TRIGGER_SOURCES else TASK_TRIGGER_SCHEDULE,
        ),
        None,
    )

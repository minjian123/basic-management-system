"""任务调度域服务：校验（cron / args / handler 白名单）、启停、手动触发与变更通知。

- **写路径后置通知**：任一写操作提交后 `TaskChangeSignal.publish()`（fire-and-forget），
  失败只记 warn——调度正确性由 beat 周期轮询兜底，不因通知失败回滚业务；
- **手动触发**：不受启停状态限制（应急执行），冷却窗口经 Redis `SET NX EX` 防误点；
  Redis 不可用时**跳过冷却**（限流属可降级域：宁可能多触发一次，也不要因缓存故障拒掉应急执行）；
- **乐观锁**：修改以 `version` 为条件更新，版本不匹配按并发冲突（`10004`）拒绝。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings, get_settings
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RedisUnavailableError,
    TaskDefinitionDuplicateError,
    TaskHandlerNotRegisteredError,
    TaskNotFoundError,
    TaskTriggerTooFrequentError,
)
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.task import (
    TASK_RUN_RUNNING,
    TASK_STATUS_DISABLED,
    TASK_STATUS_ENABLED,
    TASK_TRIGGER_MANUAL,
    SysTask,
)
from bms_core.redis.base import shared_async_client
from bms_core.tasks.cron import next_fire, parse_cron
from bms_core.tasks.handlers import is_allowed_handler
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.signal import TaskChangeSignal
from bms_core.tasks.spec import TaskRunSpec, parse_task_args
from bms_platform.domains.task.repositories.task import TaskLogRepository, TaskRepository
from bms_platform.domains.task.schemas.task import (
    TaskCreateRequest,
    TaskItem,
    TaskLogItem,
    TaskLogPage,
    TaskPage,
    TaskTriggerResult,
    TaskUpdateRequest,
)

__all__ = ["TASK_STATUSES", "TaskService"]

_LOGGER = get_logger("bms")

TASK_STATUSES = ConcurrentStableList([TASK_STATUS_ENABLED, TASK_STATUS_DISABLED])
"""任务状态取值域（`sys_task.status`）。"""

TRIGGER_KEY_PREFIX = "bms:global:task:trigger"
"""手动触发冷却键前缀（完整键 `bms:global:task:trigger:{任务 id}`）。"""


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class TaskService(BaseFrameworkObject):
    """任务定义管理服务（事务边界由调用方经工作单元开启）。"""

    def __init__(
        self,
        repository: TaskRepository,
        logs: TaskLogRepository,
        uow: UnitOfWork,
        *,
        queue: TaskQueue,
        signal: TaskChangeSignal,
        settings: TaskSchedulerSettings | None = None,
        redis: AsyncRedis | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 任务定义仓储。
            logs: 执行记录仓储。
            uow: 工作单元。
            queue: 待执行队列（手动触发入队）。
            signal: 变更信号（写路径后置通知）。
            settings: 调度参数（白名单 / 冷却 / 截断）。
            redis: 冷却计数用的 Redis 客户端（缺省取共享客户端）。
        """
        self._repo = repository
        self._logs = logs
        self._uow = uow
        self._queue = queue
        self._signal = signal
        self._settings = settings if settings is not None else get_settings().task_scheduler
        self._redis = redis

    async def page(self, *, page: int, size: int, name: str | None, status: str | None) -> TaskPage:
        """分页查询任务定义。

        Args:
            page: 页码。
            size: 每页条数。
            name: 名称关键字。
            status: 状态。

        Returns:
            TaskPage: 分页结果。
        """
        async with self._uow.begin():
            rows, total = await self._repo.page_filtered(page=page, size=size, name=name, status=status)
        page_items: ConcurrentStableList[TaskItem] = ConcurrentStableList(TaskItem.model_validate(row) for row in rows)
        return TaskPage(list=page_items, total=total, page=page, size=size)

    async def logs_page(self, task_id: int, *, page: int, size: int) -> TaskLogPage:
        """分页查询某任务的执行记录。

        Args:
            task_id: 任务主键。
            page: 页码。
            size: 每页条数。

        Returns:
            TaskLogPage: 分页结果。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
        """
        async with self._uow.begin():
            await self._require(task_id)
            rows, total = await self._logs.page_by_task(task_id=task_id, page=page, size=size)
        log_items: ConcurrentStableList[TaskLogItem] = ConcurrentStableList(
            TaskLogItem.model_validate(row) for row in rows
        )
        return TaskLogPage(list=log_items, total=total, page=page, size=size)

    async def create(self, request: TaskCreateRequest) -> TaskItem:
        """新建任务定义。

        Args:
            request: 新建请求。

        Returns:
            TaskItem: 新建的任务。

        Raises:
            TaskHandlerNotRegisteredError: handler 不在白名单（`70003`）。
            TaskArgsInvalidError: 参数不可解析（`70004`）。
            TaskCronInvalidError: cron 非法或永不触发（`70002`）。
            TaskDefinitionDuplicateError: 代码或名称重复（`70005`）。
        """
        self._validate(request.handler, request.cron, request.args)
        if request.status not in TASK_STATUSES:
            raise ParamError(f"任务状态非法：{request.status}")
        now = _utc_now()
        async with self._uow.begin():
            if await self._repo.get_by_code(request.code) is not None:
                raise TaskDefinitionDuplicateError(f"任务代码已存在：{request.code}")
            if await self._repo.get_by_name(request.name) is not None:
                raise TaskDefinitionDuplicateError(f"任务名已存在：{request.name}")
            task = await self._repo.create(
                code=request.code,
                name=request.name,
                handler=request.handler,
                cron=request.cron,
                args=request.args,
                remark=request.remark,
                status=request.status,
                enabled=request.status == TASK_STATUS_ENABLED,
                next_run_at=self._next_run_at(request.cron, now) if request.status == TASK_STATUS_ENABLED else None,
            )
        await self._signal.publish()
        return TaskItem.model_validate(task)

    async def update(self, task_id: int, request: TaskUpdateRequest) -> TaskItem:
        """修改任务定义（乐观锁）。

        Args:
            task_id: 任务主键。
            request: 修改请求（`version` 为当前版本）。

        Returns:
            TaskItem: 修改后的任务。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
            ConcurrentConflictError: 版本不匹配（`10004`）。
            TaskHandlerNotRegisteredError: handler 不在白名单（`70003`）。
            TaskArgsInvalidError: 参数不可解析（`70004`）。
            TaskCronInvalidError: cron 非法或永不触发（`70002`）。
        """
        async with self._uow.begin():
            task = await self._require(task_id)
            handler = request.handler if request.handler is not None else task.handler
            cron = request.cron if request.cron is not None else task.cron
            args = request.args if request.args is not None else task.args
            self._validate(handler, cron, args)
            if await self._name_taken(request.name, task_id):
                raise TaskDefinitionDuplicateError(f"任务名已存在：{request.name}")
            now = _utc_now()
            values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
                {
                    "handler": handler,
                    "cron": cron,
                    "args": args,
                    "next_run_at": self._next_run_at(cron, now) if task.status == TASK_STATUS_ENABLED else None,
                }
            )
            if request.name is not None:
                values["name"] = request.name
            if request.remark is not None:
                values["remark"] = request.remark
            updated = await self._repo.update_checked(
                task_id, expected_version=request.version, now=now, **dict(values)
            )
            if not updated:
                raise ConcurrentConflictError(f"任务已被他人修改：{task_id}")
            detail = await self._require(task_id)
        await self._signal.publish()
        return TaskItem.model_validate(detail)

    async def delete(self, task_id: int) -> None:
        """软删除任务定义（执行记录不随删物理删除）。

        Args:
            task_id: 任务主键。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
        """
        async with self._uow.begin():
            await self._require(task_id)
            await self._repo.soft_delete(task_id)
        await self._signal.publish()

    async def set_enabled(self, task_id: int, *, enabled: bool) -> TaskItem:
        """启用 / 停用任务（停用清空 `next_run_at`，不再产生执行记录）。

        Args:
            task_id: 任务主键。
            enabled: 是否启用。

        Returns:
            TaskItem: 变更后的任务。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
        """
        now = _utc_now()
        status = TASK_STATUS_ENABLED if enabled else TASK_STATUS_DISABLED
        async with self._uow.begin():
            task = await self._require(task_id)
            next_run_at = None
            if enabled and task.cron is not None:
                next_run_at = self._next_run_at(task.cron, now)
            await self._repo.update_checked(
                task_id,
                expected_version=task.version,
                now=now,
                status=status,
                enabled=enabled,
                next_run_at=next_run_at,
            )
            detail = await self._require(task_id)
        await self._signal.publish()
        return TaskItem.model_validate(detail)

    async def trigger(self, task_id: int) -> TaskTriggerResult:
        """手动触发一次（不受启停限制；冷却窗口内重复触发拒绝）。

        Args:
            task_id: 任务主键。

        Returns:
            TaskTriggerResult: 执行记录与运行标识。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
            TaskTriggerTooFrequentError: 冷却窗口内重复触发（`70006`）。
        """
        await self._guard_cooldown(task_id)
        run_id = uuid4().hex
        now = _utc_now()
        async with self._uow.begin():
            task = await self._require(task_id)
            record = await self._logs.create(
                task_id=task_id,
                run_id=run_id,
                trigger_source=TASK_TRIGGER_MANUAL,
                status=TASK_RUN_RUNNING,
                retry_count=0,
                started_at=now,
            )
            log_id = int(record.id)
        spec = TaskRunSpec(
            db_key=self._db_key(),
            task_id=task_id,
            log_id=log_id,
            run_id=run_id,
            code=task.code,
            handler=task.handler,
            args_json=task.args,
            trigger_source=TASK_TRIGGER_MANUAL,
        )
        await self._queue.push(spec)
        return TaskTriggerResult(log_id=log_id, run_id=run_id)

    async def _require(self, task_id: int) -> SysTask:
        """取任务或抛不存在。

        Args:
            task_id: 任务主键。

        Returns:
            SysTask: 任务记录。

        Raises:
            TaskNotFoundError: 任务不存在（`70001`）。
        """
        task = await self._repo.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在或已删除：{task_id}")
        return task

    async def _name_taken(self, name: str | None, task_id: int) -> bool:
        """判断改名是否与他人重复。

        Args:
            name: 新名称（None 表示不改）。
            task_id: 当前任务主键。

        Returns:
            bool: 被占用 True。
        """
        if name is None:
            return False
        existing = await self._repo.get_by_name(name)
        return existing is not None and int(existing.id) != task_id

    def _validate(self, handler: str, cron: str | None, args: str | None) -> None:
        """校验执行体白名单 / cron / 参数。

        Args:
            handler: 执行体路径。
            cron: 调度表达式。
            args: 参数原文。

        Raises:
            TaskHandlerNotRegisteredError: handler 不在白名单（`70003`）。
            TaskArgsInvalidError: 参数不可解析（`70004`）。
            TaskCronInvalidError: cron 非法或永不触发（`70002`）。
        """
        if not is_allowed_handler(handler, self._settings.allowed_handler_prefixes):
            raise TaskHandlerNotRegisteredError(f"handler 不在白名单内：{handler}")
        parse_task_args(args)
        if cron is not None:
            self._next_run_at(cron, _utc_now())

    def _next_run_at(self, cron: str | None, now: datetime) -> datetime | None:
        """按 cron 计算下次到期时间（naive UTC）。

        Args:
            cron: 调度表达式（None 表示仅手动）。
            now: 当前时刻（naive）。

        Returns:
            datetime | None: 下次到期；无 cron 返回 None。

        Raises:
            TaskCronInvalidError: cron 非法或永不触发（`70002`）。
        """
        if cron is None:
            return None
        return next_fire(parse_cron(cron), now.replace(tzinfo=UTC)).replace(tzinfo=None)

    async def _guard_cooldown(self, task_id: int) -> None:
        """手动触发冷却（`SET NX EX`；Redis 不可用时跳过）。

        Args:
            task_id: 任务主键。

        Raises:
            TaskTriggerTooFrequentError: 冷却窗口内重复触发（`70006`）。
        """
        seconds = self._settings.trigger_cooldown_seconds
        if seconds <= 0:
            return
        key = f"{TRIGGER_KEY_PREFIX}:{task_id}"
        try:
            client = self._redis if self._redis is not None else shared_async_client()
            acquired = await client.set(key, "1", nx=True, ex=seconds)
        except (RedisUnavailableError, RedisError) as exc:
            _LOGGER.warning("手动触发冷却不可用（本次放行）", task_id=task_id, error=str(exc))
            return
        if not acquired:
            raise TaskTriggerTooFrequentError(f"任务触发过于频繁：{task_id}")

    def _db_key(self) -> str:
        """取当前租户库键（队列载荷用）。

        Returns:
            str: 当前租户上下文库键。
        """
        return current_tenant_context().db_key

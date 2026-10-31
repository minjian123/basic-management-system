"""任务调度接口端点：`/api/v1/tasks`（任务定义 / 启停 / 手动触发 / 执行记录）。

- **鉴权**：模块级 `require_auth`；查询挂 `task:query`，维护与启停挂 `task:manage`，
  手动触发挂 `task:trigger`（权限码与 `tenant/seed/menu.py` 的 `task` 业务三动作一致）；
- **库**：任务定义 / 执行记录在 platform 服务**租户库**（`get_uow`）；队列与信号走 Redis；
- **写路径**：成功后经 `TaskChangeSignal` 唤醒 beat（失败只 warn，调度正确性由周期轮询兜底）。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_uow
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.signal import TaskChangeSignal
from bms_platform.domains.task.repositories.task import TaskLogRepository, TaskRepository
from bms_platform.domains.task.schemas.task import TaskCreateRequest, TaskUpdateRequest
from bms_platform.domains.task.services.task import TaskService

router = BaseRouter(
    key="task",
    prefix="/tasks",
    tags=["task"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("task:query"))
_REQUIRE_MANAGE = Depends(require_permission("task:manage"))
_REQUIRE_TRIGGER = Depends(require_permission("task:trigger"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
NameQuery = Annotated[str | None, Query(description="任务名关键字（模糊匹配）")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled/disabled）")]


def _service(uow: UnitOfWork) -> TaskService:
    """构造任务服务（请求级租户库会话 + Redis 队列 / 信号）。

    Args:
        uow: 请求级工作单元（platform 服务租户库）。

    Returns:
        TaskService: 任务服务实例。
    """
    session = cast("DbSession", uow.session)
    return TaskService(
        TaskRepository(session),
        TaskLogRepository(session),
        uow,
        queue=TaskQueue(),
        signal=TaskChangeSignal(),
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_tasks(uow: UowDep, page: PageDep, name: NameQuery = None, status: StatusQuery = None) -> ApiResponse:
    """任务列表（分页 + 名称 / 状态筛选）。

    Args:
        uow: 工作单元。
        page: 分页参数。
        name: 名称关键字。
        status: 状态。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    result = await _service(uow).page(page=page.page, size=page.size, name=name, status=status)
    return ApiResponse.ok(result)


@router.post("", dependencies=[_REQUIRE_MANAGE])
async def create_task(uow: UowDep, request: TaskCreateRequest) -> ApiResponse:
    """新建任务（校验 cron / 参数 / handler 白名单与唯一性）。

    Args:
        uow: 工作单元。
        request: 新建请求。

    Returns:
        ApiResponse: 统一响应，data 为新建任务。
    """
    return ApiResponse.ok(await _service(uow).create(request))


@router.put("/{task_id}", dependencies=[_REQUIRE_MANAGE])
async def update_task(uow: UowDep, task_id: int, request: TaskUpdateRequest) -> ApiResponse:
    """修改任务（乐观锁：`version` 不匹配即并发冲突）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。
        request: 修改请求。

    Returns:
        ApiResponse: 统一响应，data 为修改后的任务。
    """
    return ApiResponse.ok(await _service(uow).update(task_id, request))


@router.delete("/{task_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_task(uow: UowDep, task_id: int) -> ApiResponse:
    """删除任务（软删除；执行记录保留）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow).delete(task_id)
    return ApiResponse.ok()


@router.post("/{task_id}/enable", dependencies=[_REQUIRE_MANAGE])
async def enable_task(uow: UowDep, task_id: int) -> ApiResponse:
    """启用定时调度（重算下次到期）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。

    Returns:
        ApiResponse: 统一响应，data 为变更后的任务。
    """
    return ApiResponse.ok(await _service(uow).set_enabled(task_id, enabled=True))


@router.post("/{task_id}/disable", dependencies=[_REQUIRE_MANAGE])
async def disable_task(uow: UowDep, task_id: int) -> ApiResponse:
    """停用定时调度（清空下次到期，不再产生执行记录）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。

    Returns:
        ApiResponse: 统一响应，data 为变更后的任务。
    """
    return ApiResponse.ok(await _service(uow).set_enabled(task_id, enabled=False))


@router.post("/{task_id}/trigger", dependencies=[_REQUIRE_TRIGGER])
async def trigger_task(uow: UowDep, task_id: int) -> ApiResponse:
    """手动触发一次（不受启停限制；冷却窗口内拒绝）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。

    Returns:
        ApiResponse: 统一响应，data 为执行记录与运行标识。
    """
    return ApiResponse.ok(await _service(uow).trigger(task_id))


@router.get("/{task_id}/logs", dependencies=[_REQUIRE_QUERY])
async def list_task_logs(uow: UowDep, task_id: int, page: PageDep) -> ApiResponse:
    """任务执行记录（分页，按开始时间倒序）。

    Args:
        uow: 工作单元。
        task_id: 任务主键。
        page: 分页参数。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    return ApiResponse.ok(await _service(uow).logs_page(task_id, page=page.page, size=page.size))

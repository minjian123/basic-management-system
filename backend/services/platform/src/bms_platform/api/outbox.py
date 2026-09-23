"""死信看板路由：事件死信列表 / 详情 / 重投 / 忽略（平台服务，前缀 `/api/v1/outbox`）。

- 会话取 `get_db`（按请求租户库；平台上下文回落平台库），读 `sys_` 共享前缀合法。
- 存储取发件箱存储基座（`get_outbox_store`，插件键 `outbox_store`）。
- 鉴权挂 `require_auth` 登录态占位（真实平台管理权限码随 RBAC 阶段回补）。
- 重投：死信状态 `pending → replayed`，并把对应发件箱记录（`source=outbox`）重置为待投递；
  非法状态（非 `pending`）抛 `ConflictError`（10003），不存在抛 `NotFoundError`（10002 / 404）。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_db, get_outbox_store
from bms_core.core.exceptions import ConflictError, NotFoundError
from bms_core.db.session import DbSession
from bms_core.outbox.base import (
    DEAD_LETTER_SOURCE_OUTBOX,
    DEAD_LETTER_STATUS_IGNORED,
    DEAD_LETTER_STATUS_PENDING,
    DEAD_LETTER_STATUS_REPLAYED,
    BaseOutboxStore,
)
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.schemas.outbox import DeadLetterResponse

router = BaseRouter(
    key="outbox",
    prefix="/outbox",
    tags=["outbox"],
    dependencies=[Depends(require_auth)],
)

DbDep = Annotated[DbSession, Depends(get_db)]
StoreDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StatusQuery = Annotated[str | None, Query(description="处置状态筛选（pending / replayed / ignored）；缺省全部")]
SourceQuery = Annotated[str | None, Query(description="来源筛选（outbox / consumer）；缺省全部")]
DeadLetterIdPath = Annotated[int, Path(description="死信记录主键")]


@router.get("/dead-letters")
async def list_dead_letters(
    session: DbDep,
    store: StoreDep,
    query: PageDep,
    status: StatusQuery = None,
    source: SourceQuery = None,
) -> ApiResponse:
    """死信列表（只读，分页 + 筛选，按主键倒序）。

    Args:
        session: 请求数据库会话。
        store: 发件箱存储。
        query: 分页请求（page / size）。
        status: 处置状态筛选；缺省全部。
        source: 来源筛选；缺省全部。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await store.list_dead_letters(
        session,
        status=status,
        source=source,
        offset=(query.page - 1) * query.size,
        limit=query.size,
    )
    page = BasePageResponse[DeadLetterResponse](
        list=[DeadLetterResponse.model_validate(row) for row in rows],
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/dead-letters/{dead_letter_id}")
async def get_dead_letter(session: DbDep, store: StoreDep, dead_letter_id: DeadLetterIdPath) -> ApiResponse:
    """死信详情（只读；未命中 404）。

    Args:
        session: 请求数据库会话。
        store: 发件箱存储。
        dead_letter_id: 死信记录主键。

    Returns:
        ApiResponse: 统一响应，data 为死信记录（`DeadLetterResponse`）。

    Raises:
        NotFoundError: 死信记录不存在。
    """
    record = await store.get_dead_letter(session, dead_letter_id)
    if record is None:
        raise NotFoundError(f"死信记录不存在：{dead_letter_id}")
    return ApiResponse.ok(DeadLetterResponse.model_validate(record))


@router.post("/dead-letters/{dead_letter_id}/replay")
async def replay_dead_letter(session: DbDep, store: StoreDep, dead_letter_id: DeadLetterIdPath) -> ApiResponse:
    """死信重投：状态置 `replayed`，并把对应发件箱记录重置为待投递。

    Args:
        session: 请求数据库会话。
        store: 发件箱存储。
        dead_letter_id: 死信记录主键。

    Returns:
        ApiResponse: 统一响应，data 为更新后的死信记录。

    Raises:
        NotFoundError: 死信记录不存在。
        ConflictError: 死信状态非 `pending`。
    """
    async with session.begin():
        record = await store.get_dead_letter(session, dead_letter_id)
        if record is None:
            raise NotFoundError(f"死信记录不存在：{dead_letter_id}")
        if record.status != DEAD_LETTER_STATUS_PENDING:
            raise ConflictError(f"死信状态非待处置，不可重投：{record.status}")
        await store.set_dead_letter_status(session, dead_letter_id, DEAD_LETTER_STATUS_REPLAYED)
        if record.source == DEAD_LETTER_SOURCE_OUTBOX:
            await store.replay(session, event_id=record.event_id)
        updated = await store.get_dead_letter(session, dead_letter_id)
    assert updated is not None  # 同事务内刚更新，必然存在
    return ApiResponse.ok(DeadLetterResponse.model_validate(updated))


@router.post("/dead-letters/{dead_letter_id}/ignore")
async def ignore_dead_letter(session: DbDep, store: StoreDep, dead_letter_id: DeadLetterIdPath) -> ApiResponse:
    """死信忽略：状态置 `ignored`。

    Args:
        session: 请求数据库会话。
        store: 发件箱存储。
        dead_letter_id: 死信记录主键。

    Returns:
        ApiResponse: 统一响应，data 为更新后的死信记录。

    Raises:
        NotFoundError: 死信记录不存在。
        ConflictError: 死信状态非 `pending`。
    """
    async with session.begin():
        record = await store.get_dead_letter(session, dead_letter_id)
        if record is None:
            raise NotFoundError(f"死信记录不存在：{dead_letter_id}")
        if record.status != DEAD_LETTER_STATUS_PENDING:
            raise ConflictError(f"死信状态非待处置，不可忽略：{record.status}")
        await store.set_dead_letter_status(session, dead_letter_id, DEAD_LETTER_STATUS_IGNORED)
        updated = await store.get_dead_letter(session, dead_letter_id)
    assert updated is not None  # 同事务内刚更新，必然存在
    return ApiResponse.ok(DeadLetterResponse.model_validate(updated))

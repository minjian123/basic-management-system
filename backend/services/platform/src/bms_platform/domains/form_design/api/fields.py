"""租户自建字段管理端点：`/api/v1/form-design/fields`（10_01）。

- **鉴权**：`formdesign:query`（列表）/ `formdesign:manage`（新建 / 编辑 / 重试）；
- **新建即建列**：登记元数据（`ddl_status=pending`）→ 提交 → 执行 DDL → `active` / `failed`；
- **失败可重试**：`POST /{id}/retry` 复用同一元数据与列名；
- **停用不删列**：编辑置 `status=disabled`，不生成 `DROP COLUMN`。
"""

from typing import Annotated, cast

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_cache_region,
    get_distributed_lock,
    get_option_set_registry,
    get_outbox_store,
    get_platform_uow,
    get_uow,
)
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.lock.base import BaseDistributedLock
from bms_core.models.platform.form_design import SysFieldExt
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import require_permission
from bms_core.registry.forms import FormRegistry
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.form_design.schemas.field import (
    ExtFieldCreateRequest,
    ExtFieldItem,
    ExtFieldListResponse,
    ExtFieldUpdateRequest,
)
from bms_platform.domains.form_design.services.field_ext import ExtFieldService
from bms_platform.services.i18n_text import request_locale
from bms_platform.wiring import build_form_design_service

__all__ = ["router"]

router = BaseRouter(
    key="form_design_field",
    prefix="/form-design",
    tags=["form-design"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("formdesign:query"))
_REQUIRE_MANAGE = Depends(require_permission("formdesign:manage"))

FormCodeQuery = Annotated[str, Query(min_length=1, max_length=64, description="表单标识（业务码）")]


def _service(
    request: Request,
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
    outbox: Annotated[BaseOutboxStore, Depends(get_outbox_store)],
    lock: Annotated[BaseDistributedLock, Depends(get_distributed_lock)],
    option_sets: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
) -> ExtFieldService:
    """构造请求级自建字段服务（与布局服务共用同一装配，避免两套依赖漂移）。

    Args:
        request: 请求对象（取租户上下文）。
        tenant_uow: 租户库工作单元。
        platform_uow: 平台库工作单元（只读元数据）。
        cache: 缓存 Region。
        outbox: 事务性发件箱。
        lock: 分布式锁（DDL 单租户串行）。
        option_sets: 选项集注册表。

    Returns:
        ExtFieldService: 自建字段服务实例。
    """
    design = build_form_design_service(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        cache=cache,
        outbox=outbox,
        lock=lock,
        option_set_registry=option_sets,
        registry=cast("FormRegistry", request.app.state.form_registry),
    )
    return design.ext_field_service(lock)


ServiceDep = Annotated[ExtFieldService, Depends(_service)]


async def _to_item(service: ExtFieldService, row: SysFieldExt) -> ExtFieldItem:
    """把自建字段行转响应项（名称按当前 locale 优先，缺省回落主表文案）。

    Args:
        service: 自建字段服务（取多语言名）。
        row: 自建字段行。

    Returns:
        ExtFieldItem: 响应项。
    """
    locale = request_locale()
    names = await service.names(ConcurrentStableList((row,)), locales=ConcurrentStableList((locale, "zh-CN")))
    label = names.get(row.id) or row.name
    texts: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    if names.get(row.id) is not None:
        texts.set("zh-CN", str(names[row.id]))
    return ExtFieldItem(
        id=str(row.id),
        form_code=row.form_code,
        field_key=row.field_key,
        name=label,
        type=row.type,
        option_set_key=row.option_set_key,
        column_name=row.column_name,
        table_name=row.table_name,
        ddl_status=row.ddl_status,
        sort=row.sort,
        status=row.status,
        names=texts,
    )


def _require_id(raw: str, label: str) -> int:
    """解析路径里的雪花主键（非数字即参数错）。

    Args:
        raw: 路径参数。
        label: 名称（错误提示用）。

    Returns:
        int: 主键。

    Raises:
        ParamError: 形态非法（10001）。
    """
    if not raw.isdigit():
        raise ParamError(f"{label}主键非法：{raw}")
    return int(raw)


@router.get("/fields", dependencies=[_REQUIRE_QUERY])
async def list_fields(service: ServiceDep, form_code: FormCodeQuery) -> ApiResponse[ExtFieldListResponse]:
    """列示该表单的自建字段（含 `ddl_status`）。

    需要 `formdesign:query`；业务码不存在或不可定制返回 `40401`。

    Args:
        service: 自建字段服务。
        form_code: 表单标识（业务码）。

    Returns:
        ApiResponse[ExtFieldListResponse]: 统一响应，data 为自建字段清单。
    """
    rows = await service.list_fields(form_code)
    items: ConcurrentStableList[ExtFieldItem] = ConcurrentStableList()
    for row in rows:
        items.add(await _to_item(service, row))
    return ApiResponse.ok(ExtFieldListResponse(items=items))


@router.post("/fields", dependencies=[_REQUIRE_MANAGE])
async def create_field(service: ServiceDep, payload: ExtFieldCreateRequest) -> ApiResponse[ExtFieldItem]:
    """新建自建字段并触发动态 DDL。

    需要 `formdesign:manage`；字段键非法 `10001`、冲突 `40402`、类型 / 选项集非法 `40404`、
    建列失败随行返回 `ddl_status=failed`（可重试）。

    Args:
        service: 自建字段服务。
        payload: 新建请求。

    Returns:
        ApiResponse[ExtFieldItem]: 统一响应，data 为新建字段（含建列状态）。
    """
    row = await service.create_field(
        form_code=payload.form_code,
        field_key=payload.field_key,
        name=payload.name,
        field_type=payload.type,
        option_set_key=payload.option_set_key,
        sort=payload.sort,
    )
    return ApiResponse.ok(await _to_item(service, row))


@router.put("/fields/{field_id}", dependencies=[_REQUIRE_MANAGE])
async def update_field(service: ServiceDep, field_id: str, payload: ExtFieldUpdateRequest) -> ApiResponse[ExtFieldItem]:
    """编辑自建字段（停用不删列）。

    需要 `formdesign:manage`；字段不存在 `10002`；选项集非法 `40404`。

    Args:
        service: 自建字段服务。
        field_id: 字段主键（字符串化雪花 ID）。
        payload: 编辑请求。

    Returns:
        ApiResponse[ExtFieldItem]: 统一响应，data 为更新后的字段。
    """
    row = await service.update_field(
        field_id=_require_id(field_id, "字段"),
        name=payload.name,
        status=payload.status,
        option_set_key=payload.option_set_key,
        sort=payload.sort,
    )
    return ApiResponse.ok(await _to_item(service, row))


@router.post("/fields/{field_id}/retry", dependencies=[_REQUIRE_MANAGE])
async def retry_field(service: ServiceDep, field_id: str) -> ApiResponse[ExtFieldItem]:
    """重试建列（复用同一元数据与列名）。

    需要 `formdesign:manage`；字段不存在 `10002`。

    Args:
        service: 自建字段服务。
        field_id: 字段主键（字符串化雪花 ID）。

    Returns:
        ApiResponse[ExtFieldItem]: 统一响应，data 为重试后的字段。
    """
    row = await service.retry_field(field_id=_require_id(field_id, "字段"))
    return ApiResponse.ok(await _to_item(service, row))

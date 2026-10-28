"""服务目录只读路由：清单（分页 + 筛选）与明细（只读，无写接口）。

- 数据源为平台库 `sys_module`（服务目录单一权威），经 `get_platform_read_db` 平台库只读会话取数
  （带租户上下文的请求仍读平台库）。
- 清单：`GET /api/v1/modules`——分页 + `status` / `group` 筛选，响应 `ModuleResponse` 分页结构。
- 快照：`GET /api/v1/modules/snapshot`——**全量清单（不分页）**，供各服务**启动接库校验**对账
  （06_01 起非目录权威服务经 `service_client` 调本接口，见 `bms_core/catalog/loader.py`）。
  **同一端点的带参分支**（07B `02_02`）：`?with=products,collaborations` 除清单外一并下发产品段与
  能力段（服务启动对账、跨服务查询与前端取址共用同一份）；**不新开端点**，缺省契约逐字段不变。
- 明细：`GET /api/v1/modules/{service_key}`——`service_key` 优先、未命中回退 `module_key`；
  未登记统一 `NotFoundError`（10002 / 404 + 统一响应体）。
- 鉴权挂 `require_auth_or_service`（双模：登录态**或**东西向非网关服务身份）——本模块为「前端与服务共用」
  只读端点，快照供各服务启动接库校验直连取数（东西向服务 JWT），清单 / 明细供登录用户读取；
  网关代发的 `sub=gateway` 票据不算服务身份（回落登录态路径），无免登录面（缺陷 #111 修复）。
- 只读边界：仅 GET、不含密钥 / 敏感项（响应字段集固定为 `ModuleResponse`；带参形态的能力段**不含**
  服务内部路径与授权信息）。
"""

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth_or_service
from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import NotFoundError, ParamError
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.module import (
    CatalogSnapshotResponse,
    CollaborationSnapshotItem,
    ModuleResponse,
    ProductSnapshotItem,
)
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.services.module_registry import (
    CollaborationKind,
    CollaborationRecord,
    CollaborationStatus,
    collaboration_catalog_view,
    product_catalog_view,
    tenant_base_module_keys,
)
from bms_platform.domains.platform_registry.repositories.module_repository import ModuleRepository

router = BaseRouter(
    key="modules",
    prefix="/modules",
    tags=["module"],
    dependencies=[Depends(require_auth_or_service)],
)

PlatformDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled / disabled / planned）；缺省全部")]
GroupQuery = Annotated[str | None, Query(description="归属分组筛选（foundation / capability / product）；缺省全部")]
ServiceKeyPath = Annotated[str, Path(description="服务标识（service_key；未命中回退 module_key）")]
WithQuery = Annotated[
    str | None,
    Query(
        alias="with",
        description="附带段（逗号分隔多值：modules / products / collaborations）；缺省保持原数组契约",
    ),
]

SNAPSHOT_SEGMENTS: ConcurrentStableSet[str] = ConcurrentStableSet(("modules", "products", "collaborations"))
"""带参快照可接受的段名（集合外的值按参数非法拒绝，不静默回退数组契约）。"""

CATALOG_SNAPSHOT_VERSION = "2"
"""带参快照的契约版本（形态变更时递增；缺省数组形态不带该字段）。

`"2"`（2026-10-28，`03_02`）：能力段增 `kind` 字段（前端按「业务域 + 种类」取址）。
"""


@router.get("")
async def list_modules(
    session: PlatformDbDep,
    query: PageDep,
    status: StatusQuery = None,
    group: GroupQuery = None,
) -> ApiResponse:
    """服务目录清单（只读，分页 + 筛选）。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（page / size / order_by / order；排序白名单逐项校验、非法忽略）。
        status: 状态筛选；缺省返回全部。
        group: 归属分组筛选；缺省返回全部。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await ModuleRepository(session).page_catalog(query, group=group, status=status)
    page = BasePageResponse[ModuleResponse](
        list=_module_responses(rows),
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/snapshot")
async def catalog_snapshot(
    session: PlatformDbDep,
    with_: WithQuery = None,
    # bare-collections:allow: OpenAPI 数组形态（Pydantic 不支持并发集合泛型）
) -> ApiResponse[CatalogSnapshotResponse] | ApiResponse[list[ModuleResponse]]:
    """服务目录快照（只读，全量清单不分页；带参分支一并下发产品段与能力段）。

    供各服务启动接库校验对账（`validate_catalog`）：字段与 `sys_module` 登记一致，
    响应 `data` 为清单数组（**注意**：路径须先于 `/modules/{service_key}` 注册，避免被明细路由吞掉）。

    带参分支（`?with=products,collaborations`）：`data` 为
    `{modules, products, collaborations, snapshot_version, warnings}`——产品段与能力段来自**运行时视图**
    （产品清单装载的内存投影，不落库），因此必须在装载完成后才有效；未装载时为空数组并在 `warnings`
    给出提示（不静默）。`with` 取值集合外的值按参数非法拒绝（10001），不静默回退数组契约。

    **契约形态**：返回注解为两分支联合（`ApiResponse[CatalogSnapshotResponse]` 为带参形态、
    `ApiResponse[list[ModuleResponse]]` 为缺省数组形态），使公开契约与前端生成类型同时覆盖两种形态
    （`03_02` 消费）。

    Args:
        session: 平台库只读会话。
        with_: 附带段（逗号分隔多值；缺省保持原数组契约）。

    Returns:
        ApiResponse: 统一响应。缺省形态 data 为服务目录记录数组（`ModuleResponse`）；
        带参形态 data 为 `CatalogSnapshotResponse`。

    Raises:
        ParamError: `with` 出现未支持的段名（10001）。
    """
    rows = await ModuleRepository(session).list_catalog()
    modules = _module_responses(rows)
    segments = _requested_segments(with_)
    if not segments:
        # 缺省形态保持原契约：`data` 为纯数组（逐字段与改造前一致）
        return ApiResponse.ok(modules.to_list())
    warnings: ConcurrentStableList[str] = ConcurrentStableList()
    payload = CatalogSnapshotResponse(
        modules=modules,
        products=_product_segment(segments),
        collaborations=_collaboration_segment(segments, warnings),
        snapshot_version=CATALOG_SNAPSHOT_VERSION,
        warnings=warnings,
    )
    return ApiResponse.ok(payload)


@router.get("/{service_key}")
async def get_module(session: PlatformDbDep, service_key: ServiceKeyPath) -> ApiResponse:
    """单条服务目录明细（只读；未登记 404）。

    Args:
        session: 平台库只读会话。
        service_key: 服务标识（service_key 优先，未命中回退 module_key）。

    Returns:
        ApiResponse: 统一响应，data 为服务目录记录（`ModuleResponse`）。

    Raises:
        NotFoundError: 未登记（10002 / 404，全局处理器统一转响应）。
    """
    repository = ModuleRepository(session)
    row = await repository.get_by_service_key(service_key)
    if row is None:
        row = await repository.get_by_key(service_key)
    if row is None:
        raise NotFoundError(f"服务未登记：{service_key}")
    return ApiResponse.ok(_module_response(row))


def _module_responses(rows: Iterable[object]) -> ConcurrentStableList[ModuleResponse]:
    """目录行 → 响应清单（派生恒开通标记）。`tenant_base` 按恒开通清单派生，不直接取库列。

    Args:
        rows: 库中目录行（`sys_module` 行或同构对象，插入序）。

    Returns:
        ConcurrentStableList[ModuleResponse]: 响应清单（顺序与入参一致）。
    """
    base_keys = ConcurrentStableSet(tenant_base_module_keys())
    return ConcurrentStableList(_module_response(row, base_keys=base_keys) for row in rows)


def _module_response(row: object, *, base_keys: ConcurrentStableSet[str] | None = None) -> ModuleResponse:
    """单个目录行 → 响应（`tenant_base` 按恒开通清单派生）。

    Args:
        row: 库中目录行（`sys_module` 行或同构对象）。
        base_keys: 恒开通模块键集合（批量转换时复用，避免逐行重算）。

    Returns:
        ModuleResponse: 目录响应（其余字段与行逐字段一致）。
    """
    keys = ConcurrentStableSet(tenant_base_module_keys()) if base_keys is None else base_keys
    payload = ModuleResponse.model_validate(row)
    return payload.model_copy(update={"tenant_base": payload.module_key in keys})


def _requested_segments(raw: str | None) -> ConcurrentStableSet[str]:
    """解析 `with` 查询参数为段名集合。

    Args:
        raw: 原始参数（逗号分隔多值；None / 空串 / 仅逗号视为未请求）。

    Returns:
        ConcurrentStableSet[str]: 请求的段名集合（空集表示走缺省数组契约）。

    Raises:
        ParamError: 出现未支持的段名（10001，不静默回退）。
    """
    segments: ConcurrentStableSet[str] = ConcurrentStableSet()
    for item in (raw or "").split(","):
        name = item.strip()
        if not name:
            continue
        if name not in SNAPSHOT_SEGMENTS:
            raise ParamError(f"快照附带段不支持：{name}（取值 {'/'.join(SNAPSHOT_SEGMENTS)}）")
        segments.add(name)
    return segments


def _product_segment(segments: ConcurrentStableSet[str]) -> ConcurrentStableList[ProductSnapshotItem]:
    """取产品段（仅请求时下发）。

    Args:
        segments: 请求的段名集合。

    Returns:
        ConcurrentStableList[ProductSnapshotItem]: 产品段（只含 `product_key` / `name` / `status`）。
    """
    if "products" not in segments:
        return ConcurrentStableList()
    records = product_catalog_view()
    return ConcurrentStableList(
        ProductSnapshotItem(product_key=record.product_key, name=record.name, status=record.status)
        for record in records
    )


def _collaboration_segment(
    segments: ConcurrentStableSet[str], warnings: ConcurrentStableList[str]
) -> ConcurrentStableList[CollaborationSnapshotItem]:
    """取能力段（仅请求时下发；`disabled` 与 `codes` 类不下发）。

    Args:
        segments: 请求的段名集合。
        warnings: 警示收集器。

    Returns:
        ConcurrentStableList[CollaborationSnapshotItem]: 能力段（不含 `path` 与授权信息）。
    """
    if "collaborations" not in segments:
        return ConcurrentStableList()
    records = collaboration_catalog_view()
    if not records:
        warnings.add("能力目录为空（产品清单未装载或未声明 [[collaborations]] 段）")
    visible: ConcurrentStableList[CollaborationSnapshotItem] = ConcurrentStableList()
    for record in records:
        if not _is_visible(record):
            continue
        visible.add(
            CollaborationSnapshotItem(
                name=record.name,
                domain=record.domain,
                kind=str(record.kind),
                product_key=record.product_key,
                frontend_prefix=record.frontend_prefix,
                contract_version=record.contract_version,
                status=record.status,
                replacement=record.replacement,
            )
        )
    return visible


def _is_visible(record: CollaborationRecord) -> bool:
    """能力是否下发到前端快照（`enabled` / `deprecated` 可见，`disabled` 与 `codes` 类不可见）。

    Args:
        record: 能力记录。

    Returns:
        bool: 可见为 True。
    """
    return record.kind != CollaborationKind.CODES and record.status in (
        CollaborationStatus.ENABLED,
        CollaborationStatus.DEPRECATED,
    )

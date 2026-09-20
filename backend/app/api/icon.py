"""自定义图标占位路由：`/api/v1/icons`（清单 / 详情 / 新增 / 更新 / 删除）。

- 五端点统一经图标注册表出口（占位实现固定返回），**均需登录**（自定义图标管理属配置类操作），
  权限码（`icon:manage`）由上层声明、基座不内建。
- 图标键格式经 `is_valid_icon_code` 在路由层显式校验（非法抛参数错误 10001），避免与契约层错误码重复；
  详情 / 更新未命中由资源不存在错误统一转 404 / 10002。
- 三个写接口（新增 / 更新 / 删除）按需接幂等基座（02-25）：读 `Idempotency-Key` 头（缺失即跳过），
  作用域绑当前租户位，重复请求复用首次结果。
- 真实落库 CRUD、SVG 上传与清洗、引用检查随通用能力 / 文件管理 / 菜单管理阶段，本路由只做校验与委托。
"""

from typing import Annotated

from fastapi import Depends, Header, Path, Query

from app.api.base import BaseRouter, require_auth
from app.api.deps import get_icon_registry, get_idempotency_store, get_tenant
from app.api.tenant import current_code_of
from app.core.exceptions import ParamError
from app.db.tenant import TenantContext
from app.icon.base import ICON_CODE_MAX_LENGTH, BaseIconRegistry, IconDraft, IconInfo, IconPatch, is_valid_icon_code
from app.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from app.schemas.common import ApiResponse
from app.schemas.icon import (
    IconCreateRequest,
    IconDeleteResponse,
    IconListResponse,
    IconResponse,
    IconUpdateRequest,
)

router = BaseRouter(
    key="icon",
    prefix="/icons",
    tags=["icon"],
    dependencies=[Depends(require_auth)],
)

RegistryDep = Annotated[BaseIconRegistry, Depends(get_icon_registry)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
IconCodePath = Annotated[
    str,
    Path(min_length=1, max_length=ICON_CODE_MAX_LENGTH, description="图标键（kebab-case，见详情）"),
]
CategoryQuery = Annotated[str | None, Query(description="图标分组（缺省全部）")]
StatusQuery = Annotated[str | None, Query(description="图标状态（active 启用 / disabled 停用；缺省全部）")]
KeywordQuery = Annotated[str | None, Query(description="关键字（匹配图标键 / 名称 / 标签）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复提交复用首次结果）"),
]


def _to_response(info: IconInfo) -> IconResponse:
    """把能力域图标定义映射为路由响应契约（字段一一对应）。

    Args:
        info: 能力域图标定义。

    Returns:
        IconResponse: 路由响应契约。
    """
    return IconResponse(
        id=info.id,
        code=info.code,
        name=info.name,
        category=info.category,
        tags=info.tags,
        svg=info.svg,
        status=info.status,
        icon_key=info.icon_key,
    )


def _require_valid_code(code: str) -> None:
    """校验图标键格式（非法抛参数错误）。

    Args:
        code: 图标键。

    Raises:
        ParamError: 图标键不符合 kebab-case 规范（10001）。
    """
    if not is_valid_icon_code(code):
        raise ParamError(f"图标键格式非法：{code}")


@router.get("")
async def list_icons(
    registry: RegistryDep,
    category: CategoryQuery = None,
    status: StatusQuery = None,
    keyword: KeywordQuery = None,
) -> ApiResponse:
    """取图标清单（可按分组 / 状态过滤，关键字匹配图标键 / 名称 / 标签）。

    Args:
        registry: 图标注册表基座。
        category: 图标分组查询参数（可选）。
        status: 图标状态查询参数（可选）。
        keyword: 关键字查询参数（可选）。

    Returns:
        ApiResponse: 统一响应，data 为图标清单（`IconListResponse`）。
    """
    icons = await registry.list(category=category, status=status, keyword=keyword)
    return ApiResponse.ok(IconListResponse(icons=[_to_response(item) for item in icons]))


@router.get("/{code}")
async def get_icon(registry: RegistryDep, code: IconCodePath) -> ApiResponse:
    """取单图标定义。

    Args:
        registry: 图标注册表基座。
        code: 图标键。

    Returns:
        ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。

    Raises:
        ParamError: 图标键格式非法（10001）。
    """
    _require_valid_code(code)
    return ApiResponse.ok(_to_response(await registry.get(code)))


@router.post("")
async def create_icon(
    registry: RegistryDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    req: IconCreateRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """新增自定义图标（可按幂等键复用首次结果）。

    Args:
        registry: 图标注册表基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        req: 新增请求（图标键 / 名称 / 分组 / 标签 / SVG 内容）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。

    Raises:
        ParamError: 图标键格式非法（10001）。
    """
    _require_valid_code(req.code)
    draft = IconDraft(code=req.code, name=req.name, category=req.category, tags=req.tags, svg=req.svg)
    if not idempotency_key:
        return ApiResponse.ok(_to_response(await registry.create(draft)))
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(IconResponse.model_validate(payload))
    info = await registry.create(draft)
    await idempotency.save(key, info.model_dump(mode="json"))
    return ApiResponse.ok(_to_response(info))


@router.put("/{code}")
async def update_icon(
    registry: RegistryDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    code: IconCodePath,
    req: IconUpdateRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """更新自定义图标（未提供字段保持不变；可按幂等键复用首次结果）。

    Args:
        registry: 图标注册表基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        code: 图标键。
        req: 更新请求（全字段可选）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为图标定义（`IconResponse`）。

    Raises:
        ParamError: 图标键格式非法（10001）。
    """
    _require_valid_code(code)
    patch = IconPatch(
        name=req.name,
        category=req.category,
        tags=req.tags,
        svg=req.svg,
        status=req.status,
    )
    if not idempotency_key:
        return ApiResponse.ok(_to_response(await registry.update(code, patch)))
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(IconResponse.model_validate(payload))
    info = await registry.update(code, patch)
    await idempotency.save(key, info.model_dump(mode="json"))
    return ApiResponse.ok(_to_response(info))


@router.delete("/{code}")
async def delete_icon(
    registry: RegistryDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    code: IconCodePath,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """删除自定义图标（可按幂等键复用首次结果）。

    Args:
        registry: 图标注册表基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        code: 图标键。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为删除结果（`IconDeleteResponse`）。

    Raises:
        ParamError: 图标键格式非法（10001）。
    """
    _require_valid_code(code)
    if not idempotency_key:
        return ApiResponse.ok(IconDeleteResponse(deleted=await registry.delete(code)))
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(IconDeleteResponse.model_validate(payload))
    result = IconDeleteResponse(deleted=await registry.delete(code))
    await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(result)

"""平台服务内部端点：权限快照失效 + 数据来源只读出口（服务间调用，不经网关）。

- **鉴权**：三条路由一律按**能力分配记录**判定（07B `03_01` 收编）——
  - `router`（`/invalidate`）：`platform.permission_meta.invalidate`（岗位 / 部门 / 角色分配变更后触发）；
  - `read_router`（`/subject`、`/metadata`）：`platform.permission_meta.subject` /
    `platform.permission_meta.metadata`（`04_01` 下沉后 identity 侧「经契约取数」的数据来源实现取用）。
  均只接受服务 JWT（`aud=service`）；用户票据与网关服务票据（`sub=gateway`）一律拒；无有效分配即 403。
- **失效语义**：租户权限版本 +1（`user_ids` 为空即全租户）；给定用户时顺带删除其旧版本缓存键，
  使授权 / 主体链变更**即时生效**（未走事件订阅前的先行通道，事件轨见《02_04 详细设计》§9）。
- **只读语义**：返回聚合所需**原始数据**（角色 / 类型 / 授权 / 数据范围 / 字段收窄）与元数据索引——
  算法仍在各服务进程内的基座引擎里跑，本出口只供数，不返回「算好的结果」。
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter
from bms_core.api.capability import require_capability
from bms_core.api.deps import current_tenant_id_of, get_cache_region, get_tenant
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.tenant import TenantContext
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.engine import invalidate_permission_cache
from bms_core.permission.sources import PermissionMetadata, PermissionSubjectData
from bms_core.schemas.common import ApiResponse
from bms_platform.capabilities import (
    CAPABILITY_PLATFORM_PERMISSION_INVALIDATE,
    CAPABILITY_PLATFORM_PERMISSION_METADATA,
    CAPABILITY_PLATFORM_PERMISSION_SUBJECT,
)
from bms_platform.domains.permission_meta.permission.checker import build_platform_source
from bms_platform.domains.permission_meta.schemas.permission import (
    PermissionDataScopeItem,
    PermissionFieldItem,
    PermissionGrantItem,
    PermissionInvalidateRequest,
    PermissionInvalidateResult,
    PermissionMetadataResult,
    PermissionSubjectRequest,
    PermissionSubjectResult,
)

router = BaseRouter(
    key="platform_internal_permission",
    prefix="/platform/internal/permissions",
    tags=["platform-internal"],
    dependencies=[Depends(require_capability(CAPABILITY_PLATFORM_PERMISSION_INVALIDATE))],
)
"""权限失效入口：调用方资格由**能力分配**派生（新增消费方只需授予分配，不改代码）。"""

read_router = BaseRouter(
    key="platform_internal_permission_read",
    prefix="/platform/internal/permissions",
    tags=["platform-internal"],
)
"""数据来源只读出口：**逐路由**声明各自能力（两项只读能力不同，不能挂在路由组上）。"""

TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]


@router.post("/invalidate", response_model=ApiResponse[PermissionInvalidateResult], summary="失效权限快照")
async def invalidate_permissions(
    payload: PermissionInvalidateRequest,
    tenant: TenantDep,
    cache: CacheDep,
) -> ApiResponse[PermissionInvalidateResult]:
    """失效当前租户的权限快照（版本 +1；可指定用户）。

    Args:
        payload: 失效请求（`user_ids` 空 = 全租户）。
        tenant: 请求级租户上下文（由服务 JWT 的 tenant claim 解析）。
        cache: 缓存能力域。

    Returns:
        ApiResponse[PermissionInvalidateResult]: 递增后的权限版本号。
    """
    version = await invalidate_permission_cache(
        cache,
        tenant_id=current_tenant_id_of(tenant),
        user_ids=tuple(payload.user_ids) if payload.user_ids else None,  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定
    )
    return ApiResponse(data=PermissionInvalidateResult(version=version))


@read_router.post(
    "/subject",
    response_model=ApiResponse[PermissionSubjectResult],
    summary="按用户取权限数据",
    dependencies=[Depends(require_capability(CAPABILITY_PLATFORM_PERMISSION_SUBJECT))],
)
async def read_permission_subject(
    payload: PermissionSubjectRequest,
    request: Request,
) -> ApiResponse[PermissionSubjectResult]:
    """按用户返回聚合所需原始数据（角色 / 类型 / 授权 / 数据范围 / 字段收窄）。

    Args:
        payload: 请求（用户主键）。
        request: 当前请求（构造请求级数据来源）。

    Returns:
        ApiResponse[PermissionSubjectResult]: 原始数据。
    """
    source = await build_platform_source(request)
    data = await source.load_subject(user_id=payload.user_id)
    return ApiResponse(data=_to_subject_result(data))


@read_router.get(
    "/metadata",
    response_model=ApiResponse[PermissionMetadataResult],
    summary="取权限元数据",
    dependencies=[Depends(require_capability(CAPABILITY_PLATFORM_PERMISSION_METADATA))],
)
async def read_permission_metadata(
    request: Request,
    locale: str = DEFAULT_LOCALE,
) -> ApiResponse[PermissionMetadataResult]:
    """返回元数据索引（菜单 → 表单、权限码 id → 权限码）。

    Args:
        request: 当前请求（构造请求级数据来源）。
        locale: 语言标识（缺省取实现缺省值）。

    Returns:
        ApiResponse[PermissionMetadataResult]: 元数据索引。
    """
    source = await build_platform_source(request)
    metadata = await source.load_metadata(locale=locale)
    return ApiResponse(data=_to_metadata_result(metadata))


def _to_subject_result(data: PermissionSubjectData | None) -> PermissionSubjectResult:
    """把基座中性数据转成内部契约响应。

    Args:
        data: 基座数据契约。

    Returns:
        PermissionSubjectResult: 内部契约响应。
    """
    if data is None:
        # 未知用户 / 该用户无主体数据：返回**空聚合输入**（五个契约字段齐全），
        # 不把 `null` 透给调用方（消费方按空主体继续算，无需为「查无此人」分支特判）
        return PermissionSubjectResult()
    result = PermissionSubjectResult(role_ids=ConcurrentStableList(data.role_ids))
    for role_id in data.role_ids:
        role_type = data.role_types.get(role_id)
        if role_type is not None:
            result.role_types.set(str(role_id), role_type)
    for grant in data.grants:
        result.grants.add(PermissionGrantItem(perm_type=grant.perm_type, target_id=grant.target_id))
    for rule in data.data_scope_rules:
        result.data_scope_rules.add(
            PermissionDataScopeItem(
                data_source_key=rule.data_source_key,
                policy_type=rule.policy_type,
                config=rule.config,
            )
        )
    for perm in data.field_perms:
        result.field_perms.add(
            PermissionFieldItem(
                form_id=perm.form_id,
                field_key=perm.field_key,
                visible=perm.visible,
                editable=perm.editable,
            )
        )
    return result


def _to_metadata_result(metadata: PermissionMetadata) -> PermissionMetadataResult:
    """把基座中性元数据转成内部契约响应。

    Args:
        metadata: 基座元数据契约。

    Returns:
        PermissionMetadataResult: 内部契约响应。
    """
    result = PermissionMetadataResult(version=metadata.version)
    for menu_id in metadata.menu_forms:
        # 遍历键必在集合内（并发稳定字典按当前快照遍历），无需防御性 None 分支
        result.menu_forms.set(str(menu_id), ConcurrentStableList(metadata.menu_forms.get(menu_id) or ()))
    for permission_id in metadata.permission_codes:
        result.permission_codes.set(str(permission_id), str(metadata.permission_codes.get(permission_id) or ""))
    return result

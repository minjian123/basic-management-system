"""渲染路径端点：`/api/v1/forms/{form_code}/layout-effective` 与动态校验自测（10_01）。

- **登录即可**（无权限码）：渲染路径按当前用户角色集解析布局 + 字段权限叠加；
- **下发即干净**：`visible=false` 的字段连同其布局引用一并剔除；
- **选项集快照**：枚举字段的 `optionSetKey` 与 `optionSets` 一次下发，前端零额外请求；
- **动态校验自测**：`POST /validate` 与业务接口同源（同一 `BaseFormValidator`），供端到端验证规则口径。
"""

from typing import Annotated, cast

from fastapi import Depends, Request

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
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import ParamError
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.formdesign.validator import BaseFormValidator
from bms_core.lock.base import BaseDistributedLock
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.outbox.base import BaseOutboxStore
from bms_core.registry.forms import FormRegistry
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.form_design.schemas.effective import (
    EffectiveField,
    EffectiveFieldPermission,
    FormValidateRequest,
    FormValidateResponse,
    LayoutEffectiveResponse,
    OptionSetSnapshotModel,
    ValidateFieldError,
)
from bms_platform.domains.form_design.services.layout import FormDesignService
from bms_platform.wiring import build_form_design_service, build_local_form_validator

__all__ = ["effective_router", "validate_router"]

effective_router = BaseRouter(
    key="form_design_effective",
    prefix="/forms",
    tags=["form-design"],
    dependencies=[Depends(require_auth)],
)

validate_router = BaseRouter(
    key="form_design_validate",
    prefix="/forms",
    tags=["form-design"],
    dependencies=[Depends(require_auth)],
)


def _service(
    request: Request,
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
    outbox: Annotated[BaseOutboxStore, Depends(get_outbox_store)],
    lock: Annotated[BaseDistributedLock, Depends(get_distributed_lock)],
    option_sets: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
) -> FormDesignService:
    """构造请求级表单定制服务（租户库 + 平台库双会话）。

    Args:
        tenant_uow: 租户库工作单元。
        platform_uow: 平台库工作单元（只读元数据）。
        cache: 缓存 Region。
        outbox: 事务性发件箱。
        lock: 分布式锁。
        option_sets: 选项集注册表。

    Returns:
        FormDesignService: 服务实例。
    """
    return build_form_design_service(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        cache=cache,
        outbox=outbox,
        lock=lock,
        option_set_registry=option_sets,
        registry=cast("FormRegistry", request.app.state.form_registry),
    )


ServiceDep = Annotated[FormDesignService, Depends(_service)]


def _validator(
    request: Request,
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    option_sets: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
) -> BaseFormValidator:
    """构造请求级表单动态校验器（与写入路径规则同源）。

    **为什么不走插件注册表**：注册表在应用装配期构建（早于任何请求），而校验器需请求级会话；
    直接在依赖里构造既满足「每次请求独立会话」的口径，也避免每次校验再解析一次插件。

    Args:
        request: 请求对象（取表单标识清单）。
        tenant_uow: 租户库工作单元。
        platform_uow: 平台库工作单元。
        option_sets: 选项集注册表。

    Returns:
        BaseFormValidator: 校验器实例。
    """
    return build_local_form_validator(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        option_set_registry=option_sets,
        registry=cast("FormRegistry", request.app.state.form_registry),
    )


@effective_router.get("/{form_code}/layout-effective")
async def layout_effective(
    request: Request,
    service: ServiceDep,
    form_code: str,
) -> ApiResponse[LayoutEffectiveResponse]:
    """当前用户生效布局（渲染路径，登录即可）。

    三级解析（角色视图 → 租户覆盖 → 平台默认 → 空布局回退）+ 字段权限叠加（权限优先）；
    业务码不存在或不可定制返回 `40401`。

    Args:
        request: 请求对象（取角色集）。
        service: 表单定制服务。
        form_code: 表单标识（业务码）。

    Returns:
        ApiResponse[LayoutEffectiveResponse]: 统一响应，data 为生效布局与字段清单。
    """
    if form_code == "":
        raise ParamError("表单标识不得为空")
    role_types = await service.role_types(get_current_user_id())
    assembled = await service.effect(form_code, level="role", role_types=role_types)
    fields: ConcurrentStableList[EffectiveField] = ConcurrentStableList()
    for item in assembled.fields:
        fields.add(
            EffectiveField(
                key=str(item.get("key")),
                label=str(item.get("label")),
                type=str(item.get("type")),
                group=str(item.get("group")),
                sort=int(item.get("sort") or 0),
                status=str(item.get("status")),
                disabled=bool(item.get("disabled")),
                attrs=cast("ConcurrentStableDict[str, object]", item.get("attrs") or ConcurrentStableDict()),
            )
        )
    permissions: ConcurrentStableDict[str, EffectiveFieldPermission] = ConcurrentStableDict()
    for field_key, narrowing in assembled.permissions.items():
        permissions.set(
            field_key,
            EffectiveFieldPermission(
                visible=bool(narrowing.get("visible", True)),
                editable=bool(narrowing.get("editable", True)),
            ),
        )
    snapshots: ConcurrentStableList[OptionSetSnapshotModel] = ConcurrentStableList()
    for snapshot in assembled.option_sets:
        snapshots.add(
            OptionSetSnapshotModel(
                option_set_key=str(snapshot.get("optionSetKey")),
                items=cast(
                    "ConcurrentStableList[ConcurrentStableDict[str, object]]",
                    snapshot.get("items") or ConcurrentStableList(),
                ),
            )
        )
    return ApiResponse.ok(
        LayoutEffectiveResponse(
            layout=assembled.layout_config(),
            fields=fields,
            level="role",
            source=assembled.source,
            readonly=True,
            fallback=assembled.fallback,
            option_sets=snapshots,
            permissions=permissions,
        )
    )


@validate_router.post("/{form_code}/validate")
async def validate_values(
    request: Request,
    form_code: str,
    payload: FormValidateRequest,
    validator: Annotated[BaseFormValidator, Depends(_validator)],
) -> ApiResponse[FormValidateResponse]:
    """动态校验自测端点（与业务接口同源，登录即可）。

    按当前生效布局 / 属性校验字段值；失败项返回 `field_key` + `rule`（前端按 rule 取词）。

    Args:
        request: 请求对象（取角色集）。
        form_code: 表单标识（业务码）。
        payload: 待校验值。
        validator: 表单动态校验器（应用级注入）。

    Returns:
        ApiResponse[FormValidateResponse]: 统一响应，data 为校验结果。
    """
    del request
    result = await validator.validate(form_code, payload.values)
    errors: ConcurrentStableList[ValidateFieldError] = ConcurrentStableList()
    for error in result.errors:
        errors.add(ValidateFieldError(field_key=error.field_key, rule=error.rule, message=error.message))
    return ApiResponse.ok(FormValidateResponse(valid=result.valid, errors=errors))

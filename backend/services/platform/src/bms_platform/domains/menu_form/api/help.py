"""页面内帮助端点（`GET /api/v1/help/context`，08_02）。

- **鉴权**：仅 `require_auth`（登录即可）——需求 09-1 与概要 17 §5 明示前台读接口不挂权限码，
  属《后端开发规范》§7.2「新增接口必须声明权限码」的显式例外（详见任务 08_02 详细设计 §5.4）；
- **库**：锚点在**平台服务库**（五张元数据表），故取 `get_platform_uow`；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`），新增端点属非破坏性变更；
- **语言**：请求语言经既有 locale 依赖解析，内容侧按该语言取文案（缺省回退由内容侧负责）。
"""

from datetime import date
from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_cache_region, get_config_source, get_platform_uow
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.config import Settings, get_settings
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.help.content import BaseHelpContentResolver, get_help_content_resolver
from bms_core.help.context import HelpContextInput
from bms_core.help.coverage import HelpCoverageScope
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.api.locale import accept_locale, locale_scope
from bms_platform.domains.menu_form.schemas.coverage import HelpCoverageResponse
from bms_platform.domains.menu_form.schemas.help import HelpContextResponse
from bms_platform.services.metadata_cache import menu_cache_ttl
from bms_platform.wiring import build_help_context_service, build_help_coverage_service

help_router = BaseRouter(
    key="sys_help",
    prefix="/help",
    tags=["help"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
ResolverDep = Annotated[BaseHelpContentResolver, Depends(get_help_content_resolver)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_REQUIRE_HELP_MANAGE = Depends(require_permission("help:manage"))
"""覆盖率台账读权限（概要 17 §5；12_01 内容维护共用同一权限码）。"""


@help_router.get("/context")
async def help_context(
    request: Request,
    uow: UowDep,
    cache: CacheDep,
    config: ConfigDep,
    resolver: ResolverDep,
    module_key: Annotated[
        str | None, Query(min_length=1, max_length=64, description="模块键（菜单锚点第 2 段）")
    ] = None,
    form_key: Annotated[str | None, Query(min_length=1, max_length=64, description="表单键（业务码）")] = None,
    field_key: Annotated[
        str | None, Query(min_length=1, max_length=64, description="字段键（需同时提供 form_key）")
    ] = None,
    action_code: Annotated[
        str | None, Query(min_length=1, max_length=129, description="动作码或完整权限码（业务码:动作码）")
    ] = None,
    product_key: Annotated[
        str | None, Query(min_length=1, max_length=64, description="产品段（仅模块级消歧；可空）")
    ] = None,
) -> ApiResponse[HelpContextResponse]:
    """按字段 → 动作 → 表单 → 模块 → 全局逐级解析页面内帮助。

    Args:
        request: 请求对象（解析语言 / 透传内容侧实现）。
        uow: 请求级工作单元（平台库）。
        cache: 缓存 Region（锚点索引）。
        config: 系统参数读取基座（缓存 TTL）。
        resolver: 内容侧解析实现。
        module_key: 模块键。
        form_key: 表单键（业务码）。
        field_key: 字段键。
        action_code: 动作码或完整权限码。
        product_key: 产品段（模块级消歧）。

    Returns:
        ApiResponse: 统一响应，data 为解析结果（未命中时 `matched=false` + 分类列表）。
    """
    service = build_help_context_service(
        uow=uow,
        cache=cache,
        resolver=resolver,
    )
    context = HelpContextInput.of(
        product_key=product_key,
        module_key=module_key,
        form_key=form_key,
        field_key=field_key,
        action_code=action_code,
    )
    return ApiResponse.ok(
        await service.resolve(
            context,
            locale=accept_locale(request),
            ttl=await menu_cache_ttl(config),
            request=request,
        )
    )


@help_router.get("/coverage", dependencies=[_REQUIRE_HELP_MANAGE])
async def help_coverage(
    uow: UowDep,
    settings: SettingsDep,
    product_key: Annotated[str | None, Query(min_length=1, max_length=64, description="产品过滤")] = None,
    module_key: Annotated[str | None, Query(min_length=1, max_length=64, description="模块过滤")] = None,
    kind: Annotated[
        str | None,
        Query(pattern="^(action|menu)$", description="明细类别过滤（action / menu；不影响摘要与对账）"),
    ] = None,
    include_covered: Annotated[bool, Query(description="明细是否包含已覆盖行")] = False,
    include_reference: Annotated[bool, Query(description="是否返回表单 / 字段参考统计")] = True,
) -> ApiResponse[HelpCoverageResponse]:
    """帮助覆盖率台账（按产品 / 模块分组，缺口精确到动作码）。

    Args:
        uow: 请求级工作单元（平台库）。
        settings: 应用配置（豁免文件路径）。
        product_key: 产品过滤。
        module_key: 模块过滤。
        kind: 明细类别过滤。
        include_covered: 明细是否包含已覆盖行。
        include_reference: 是否返回参考统计。

    Returns:
        ApiResponse: 统一响应，data 为覆盖率台账。
    """
    service = build_help_coverage_service(uow=uow, exemption_paths=settings.help_coverage.exemption_paths)
    scope = HelpCoverageScope(
        product_keys=ConcurrentStableFrozenList((product_key,)) if product_key else ConcurrentStableFrozenList(),
        module_keys=ConcurrentStableFrozenList((module_key,)) if module_key else ConcurrentStableFrozenList(),
        kinds=ConcurrentStableFrozenList((kind,)) if kind else ConcurrentStableFrozenList(),
        include_covered=include_covered,
    )
    return ApiResponse.ok(
        await service.load(
            as_of=date.today(),
            scope=scope,
            include_reference=include_reference,
        )
    )

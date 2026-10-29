"""产品声明注册通道（07B `02_06`）：`/api/v1/platform/internal/declarations`（服务间调用）。

- **上报**（`PUT`）：产品启动时提交自身清单文本（**单次全量**），平台校验 + 整体对账 + 落库 + 视图投影；
  同内容重复上报幂等（全 `unchanged`），内容变化覆盖并记变更日志，本次未声明者退役；
- **快照**（`GET /snapshot`）：按类别下发八类声明的**完整要素**（含访问面路径 / 分支标识与动作名 /
  承载服务键），供消费方启动期拉取；面向浏览器的目录出口仍不含内部路径（口径不变）；
- **鉴权**：服务身份（`aud=service`）；上报的服务键须与令牌 `sub` 一致（谁的服务谁注册），
  跨产品撞键由注册服务判定并拒绝；
- **失败语义**：校验不过 / 撞键 → 409 级拒绝（`CatalogError`），调用方（产品）据此拒启——断链在启动期暴露。
"""

from typing import Annotated

from fastapi import Depends

from bms_core.api.base import AuthContext, BaseRouter, require_auth_or_service
from bms_core.api.deps import get_platform_read_db, get_platform_uow
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    declaration_wire,
    from_manifest,
)
from bms_core.registry.products import parse_manifest_text
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import service_catalog_view
from bms_platform.domains.platform_registry.schemas.declaration import DeclarationSubmitRequest
from bms_platform.domains.platform_registry.services.declaration_registry import DeclarationRegistryService
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

router = BaseRouter(
    key="platform_internal_declarations",
    prefix="/platform/internal/declarations",
    tags=["platform-internal"],
    dependencies=[Depends(require_auth_or_service)],
)

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
UowDep = Annotated[DbUnitOfWork, Depends(get_platform_uow)]
ContextDep = Annotated[AuthContext, Depends(require_auth_or_service)]


@router.put("")
async def submit_declarations(
    req: DeclarationSubmitRequest,
    uow: UowDep,
    context: ContextDep,
) -> ApiResponse:
    """全量上报本产品声明（幂等；冲突即拒）。

    Args:
        req: 上报请求（产品键 / 服务键 / 清单文本）。
        uow: 平台库工作单元（写事务边界）。
        context: 入站身份（服务键须与请求一致）。

    Returns:
        ApiResponse: 统一响应，data 为逐类计数与警示。

    Raises:
        ParamError: 产品键与清单不符、服务键与身份或清单不符（10001）。
        CatalogError: 校验不过或跨产品撞键（拒绝注册）。
    """
    _assert_registrant(req, context)
    manifest = parse_manifest_text(req.manifest_toml, source=f"remote:{req.product_key}")
    if manifest.product_key != req.product_key:
        raise ParamError(f"清单归属与请求不一致：清单 {manifest.product_key}，请求 {req.product_key}")
    payload = from_manifest(manifest)
    if payload.service_key != req.service_key:
        raise ParamError(f"服务键与清单不一致：清单 {payload.service_key}，请求 {req.service_key}")
    report = await DeclarationRegistryService(uow.session).register(payload)
    # 默认拓扑补齐（07C `02_01`）：注册可能带来新的业务域，默认拓扑须覆盖全部已登记域，
    # 否则这些域的能力寻址会在运行期被判「未登记拓扑」。幂等：无新域时只做覆盖校验、不写新版本。
    await TenantTopologyService(uow.session).ensure_default()
    await uow.commit()
    body = {
        "product_key": report.product_key,
        "created": dict(report.created),
        "updated": dict(report.updated),
        "unchanged": dict(report.unchanged),
        "retired": dict(report.retired),
        "warnings": list(report.warnings),
        "snapshot_version": report.snapshot_version,
    }
    return ApiResponse.ok(body)


@router.get("/snapshot")
async def declaration_snapshot(session: ReadDbDep) -> ApiResponse:
    """下发注册表快照（服务身份专用；八类完整要素）。

    Args:
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应，data 为 `{snapshot_version, declarations}`。
    """
    view = await DeclarationRegistryService(session).snapshot()
    declarations = {
        kind: [dict(declaration_wire(kind, record)) for record in view.of(kind)] for kind in DECLARATION_KINDS
    }
    body = {"snapshot_version": str(len(service_catalog_view())), "declarations": declarations}
    return ApiResponse.ok(body)


def _assert_registrant(req: DeclarationSubmitRequest, context: AuthContext) -> None:
    """校验注册方身份与请求一致（谁的服务谁注册；平台可代注册自身）。

    Args:
        req: 上报请求。
        context: 入站身份。

    Raises:
        ParamError: 服务身份与请求的服务键不一致（10001）。
    """
    subject = str(context.subject or "").strip()
    if subject and subject not in (req.service_key, "platform"):
        raise ParamError(f"服务身份不得代其他服务注册：令牌 {subject}，请求 {req.service_key}")

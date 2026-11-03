"""审计内部端点：链校验与分片预创建（06_01，服务间调用，不经网关）。

- **鉴权**：`require_service()`（只接受服务 JWT；用户票据 / 网关票据一律拒）。
- **链校验**：供巡检任务与 14_01 归档前强制校验调用；返回断裂定位。
- **分片预创建**：供内置任务每月预建下月分片（幂等）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_hash_chain, get_platform_write_db
from bms_core.audit.hashchain import BaseHashChain
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.log.schemas.log import (
    EnsureShardsRequest,
    EnsureShardsResult,
    VerifyRequest,
    VerifyResult,
)
from bms_platform.domains.log.services.shard_bootstrap import ensure_audit_shards
from bms_platform.domains.log.services.verify import LOG_TYPES, AuditChainVerifier

router = BaseRouter(
    key="audit_internal",
    prefix="/platform/internal/audit",
    tags=["audit-internal"],
    dependencies=[Depends(require_service())],
)

DbDep = Annotated[DbSession, Depends(get_platform_write_db)]
ChainDep = Annotated[BaseHashChain, Depends(get_hash_chain)]


@router.post("/verify")
async def verify_chain(session: DbDep, chain: ChainDep, req: VerifyRequest) -> ApiResponse[VerifyResult]:
    """校验某类日志的哈希链（缺省校验台账全部月份）。

    Args:
        session: 平台库会话。
        chain: 哈希链实现。
        req: 校验请求（日志类型 + 可选月份）。

    Returns:
        ApiResponse: 统一响应，data 为校验结果。

    Raises:
        ParamError: 日志类型未登记（10001）。
    """
    if req.log_type not in LOG_TYPES:
        raise ParamError(f"日志类型非法：{req.log_type}（应为 {'/'.join(LOG_TYPES)}）")
    outcome = await AuditChainVerifier(session, chain).verify(req.log_type, req.months)
    result = VerifyResult(
        log_type=req.log_type,
        valid=outcome.valid,
        checked_months=outcome.checked_months,
        checked_records=outcome.checked_records,
        broken_month=outcome.broken_month,
        broken_index=outcome.broken_index,
        broken_record_id=outcome.broken_record_id,
    )
    return ApiResponse.ok(result)


@router.post("/shards/ensure")
async def ensure_shards(session: DbDep, req: EnsureShardsRequest) -> ApiResponse[EnsureShardsResult]:
    """确保审计分片存在（当月 + 未来 N 月，两类日志）。

    Args:
        session: 平台库会话。
        req: 预创建请求（提前月数）。

    Returns:
        ApiResponse: 统一响应，data 为已确保月份。
    """
    async with session.begin():
        months = await ensure_audit_shards(session, months_ahead=req.months_ahead)
    return ApiResponse.ok(EnsureShardsResult(months=ConcurrentStableList(months)))

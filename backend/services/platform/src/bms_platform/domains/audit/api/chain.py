"""数据变更审计链校验端点：`/api/v1/audit/chain/verify`（06_02）。

- **鉴权**：`require_auth` + `log:manage`（链校验属审计管理员的管理动作，与只读查询分权）。
- **口径**：同步逐条重算并返回断裂定位（`valid=false` + 月份 / 序号 / 记录 ID），**不抛业务错**——
  链被篡改是「查到事实」，不是接口失败；内部端点（服务 JWT）同形，供 14_01 归档前强制校验复用。
- **限流**：本任务不加接口级限流（审计管理员专属 + 网关统一限流），差异见实施记录。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_hash_chain, get_platform_read_db
from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.audit.schemas.data_change import ChainVerifyView
from bms_platform.domains.audit.services.data_change import DataChangeChainService

router = BaseRouter(
    key="audit_chain",
    prefix="/audit/chain",
    tags=["audit"],
    dependencies=[Depends(require_auth)],
)

_MANAGE = Depends(require_permission("log:manage"))
DbDep = Annotated[DbSession, Depends(get_platform_read_db)]
ChainDep = Annotated[BaseHashChain, Depends(get_hash_chain)]
MonthsQuery = Annotated[str | None, Query(description="校验月份（yyyyMM，逗号分隔；空 = 台账全部）")]


def parse_months(raw: str | None) -> ConcurrentStableList[str] | None:
    """解析月份参数（逗号分隔；空 / 全空白返回 None）。

    Args:
        raw: 原始查询参数。

    Returns:
        ConcurrentStableList[str] | None: 月份清单或 None。
    """
    if raw is None:
        return None
    months = ConcurrentStableList(part.strip() for part in raw.split(",") if part.strip())
    return months or None


@router.get("/verify", dependencies=[_MANAGE])
async def verify_data_audit_chain(
    session: DbDep, chain: ChainDep, months: MonthsQuery = None
) -> ApiResponse[ChainVerifyView]:
    """校验字段级变更审计的哈希链完整性。

    Args:
        session: 平台库只读会话。
        chain: 哈希链实现。
        months: 指定月份（逗号分隔；空 = 台账全部月份）。

    Returns:
        ApiResponse: 统一响应，data 为校验结果（含断裂定位）。
    """
    outcome = await DataChangeChainService(session, chain).verify(parse_months(months))
    return ApiResponse.ok(
        ChainVerifyView(
            log_type=LOG_TYPE_DATA_AUDIT,
            valid=outcome.valid,
            checked_months=outcome.checked_months,
            checked_records=outcome.checked_records,
            broken_month=outcome.broken_month,
            broken_index=outcome.broken_index,
            broken_record_id=outcome.broken_record_id,
        )
    )

"""平台服务 schemas 层：权限快照失效内部契约（`02_04`）。"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema


class PermissionInvalidateRequest(BaseSchema):
    """权限快照失效请求（服务间内部契约）。"""

    user_ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="受影响用户主键（空 = 全租户版本 +1）"
    )


class PermissionInvalidateResult(BaseSchema):
    """权限快照失效结果（服务间内部契约）。"""

    version: int = Field(description="递增后的租户权限版本号")

"""组织主数据服务 schemas 层：账号锁定相关内部契约（服务间调用，不经网关）。"""

from pydantic import Field

from bms_core.schemas.base import BaseSchema


class InactiveScanRequest(BaseSchema):
    """不活跃账号扫描请求（空体；租户经服务 JWT `tenant` claim 解析）。"""


class InactiveScanResult(BaseSchema):
    """不活跃账号扫描结果。"""

    scanned: int = Field(description="扫描候选账号数")
    locked: int = Field(description="本次锁定账号数")

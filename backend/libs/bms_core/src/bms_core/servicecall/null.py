"""servicecall 能力域缺省实现（Null Object）：恒定成功、不外呼。"""

from bms_core.core.capability import BaseNullObject
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

__all__ = ["NullServiceClient"]


class NullServiceClient(BaseServiceClient, BaseNullObject):
    """占位服务间调用客户端：恒定返回成功空响应（不外呼，未配置真实实现时使用）。"""

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """恒定返回成功空响应（不外呼）。

        Args:
            request: 调用请求（占位忽略）。

        Returns:
            ServiceResponse: 成功响应（`status_code=200`、空头 / 空体）。
        """
        del request
        return ServiceResponse(status_code=200)

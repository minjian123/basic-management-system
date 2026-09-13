"""统一响应模型：`{code, message, data}`。"""

from typing import Any

from app.schemas.base import BaseSchema


class ApiResponse(BaseSchema):
    """统一响应体：`code=0` 成功，非 0 业务错误码。

    - `data` 为业务数据；失败时为 `null`；分页载荷复用分页契约基类。
    - 雪花 ID 在 JSON 中以字符串输出（见《数据库开发规范》「字段规范」节）。
    """

    code: int = 0
    message: str = "ok"
    data: Any = None

    @classmethod
    def ok(cls, data: Any = None) -> ApiResponse:
        """构造成功响应。

        Args:
            data: 业务数据。

        Returns:
            ApiResponse: `{code:0, message:"ok", data}`。
        """
        return cls(code=0, message="ok", data=data)

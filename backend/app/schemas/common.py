"""统一响应模型：`{code, message, data}`（泛型）。"""

from typing import Any

from app.schemas.base import BaseSchema


class ApiResponse[DataT = Any](BaseSchema):
    """统一响应体：`code=0` 成功，非 0 业务错误码。

    - `data` 为业务数据（泛型）；失败时为 `null`；分页载荷复用分页契约基类。
    - 雪花 ID 在 JSON 中以字符串输出（`BaseSchema` 统一序列化口径）。
    """

    code: int = 0
    message: str = "ok"
    data: DataT | None = None

    @classmethod
    def ok(cls, data: DataT | None = None) -> ApiResponse[DataT]:
        """构造成功响应。

        Args:
            data: 业务数据。

        Returns:
            ApiResponse[DataT]: `{code:0, message:"ok", data}`。
        """
        return cls(code=0, message="ok", data=data)

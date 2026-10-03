"""平台服务 schemas 层：用户扩展信息请求 / 响应模型（继承 `BaseSchema`）。

具名插槽样例插件的后端契约（`/api/v1/user-extensions`）：读列表 + 新增 / 更新一条。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema


class UserExtensionCreateRequest(BaseSchema):
    """新增用户扩展信息请求。"""

    user_id: int = Field(gt=0, description="用户主键")
    label: str = Field(min_length=1, max_length=64, description="扩展标签（用户维度内唯一）")
    remark: str | None = Field(default=None, max_length=255, description="备注")


class UserExtensionUpdateRequest(BaseSchema):
    """更新用户扩展信息请求（整体替换：`label` 必填、`remark` 传 null 即清空）。"""

    label: str = Field(min_length=1, max_length=64, description="扩展标签（用户维度内唯一）")
    remark: str | None = Field(default=None, max_length=255, description="备注（null 即清空）")


class UserExtensionItem(BaseSchema):
    """用户扩展信息行。"""

    id: int = Field(description="主键（雪花 ID，JSON 以字符串输出）")
    user_id: int = Field(description="用户主键")
    label: str = Field(description="扩展标签")
    remark: str | None = Field(description="备注")
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")


class UserExtensionList(BaseSchema):
    """用户扩展信息列表（按用户列示，保序）。"""

    items: Annotated[ConcurrentStableList[UserExtensionItem], CONTRACT_COLLECTION] = Field(description="扩展信息行列表")

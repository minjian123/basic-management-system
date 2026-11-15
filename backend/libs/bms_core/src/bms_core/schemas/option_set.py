"""选项集只读快照契约：`GET /api/v1/option-sets` 的响应形状。

- 条目与后端 `OptionItem` 同构（`value` 唯一真值来源；`label_key` 供前端 i18n 回退）。
- 列表字段用插入序集合类（`CONTRACT_COLLECTION`），与项目集合口径一致。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema

__all__ = ["OptionSetItemResponse", "OptionSetListResponse", "OptionSetResponse"]


class OptionSetItemResponse(BaseSchema):
    """选项项（与 `bms_core.optionset.base.OptionItem` 对齐）。"""

    value: str = Field(description="选项值（常量字符串，唯一真值来源）")
    label: str = Field(default="", description="展示文本（当前 locale）")
    label_key: str | None = Field(default=None, description="i18n key（缺翻译回退 label）")
    color: str | None = Field(default=None, description="语义色（只读标签用）")
    disabled: bool = Field(default=False, description="是否不可新增选择（存量值仍可回显）")
    sort: int = Field(default=0, description="展示顺序（升序；同序保声明顺序）")


class OptionSetResponse(BaseSchema):
    """单个选项集快照。"""

    option_set_key: str = Field(description="选项集标识（点分小写）")
    name: str = Field(description="名称")
    namespace: str = Field(description="命名空间（标识首段）")
    version: int = Field(description="内容版本")
    items: Annotated[ConcurrentStableList[OptionSetItemResponse], CONTRACT_COLLECTION] = Field(
        description="条目清单（按 sort 升序、同 value 去重）"
    )


class OptionSetListResponse(BaseSchema):
    """选项集快照集合。"""

    items: Annotated[ConcurrentStableList[OptionSetResponse], CONTRACT_COLLECTION] = Field(
        description="选项集清单（请求顺序）"
    )

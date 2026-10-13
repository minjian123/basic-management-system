"""schemas 层表单标识契约：表单标识清单响应（与 `bms_core.registry.forms` 对齐）。

- `FormKeyResponse`：**表单标识登记记录响应**（`GET /api/v1/form-keys` 清单条目），字段与
  `FormRecord` 一一对应；枚举字段（类型 / 状态）用强类型枚举，生成前端联合字面量。
- `FormKeyListResponse`：**表单标识清单响应**（保序）——列表字段一律用插入序集合类
  （`Annotated[ConcurrentStableList[...], CONTRACT_COLLECTION]`，见《后端开发规范》「集合与排序」）。

契约口径：`form_key` 清单为**构建期清单 + 各项目装载注入、运行期只读**（`FormRegistry`），
本模块只定义**对外响应形状**，不承载登记逻辑。
"""

from typing import Annotated

from pydantic import Field, computed_field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.registry.forms import FormKind, FormStatus
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema

__all__ = ["FormKeyListResponse", "FormKeyResponse"]


class FormKeyResponse(BaseSchema):
    """表单标识登记记录响应（与 `FormRecord` 对齐）。"""

    form_key: str = Field(description="表单标识（业务码字符串，全局唯一、保存后不变）")
    name: str = Field(description="名称（通用页面展示）")
    kind: FormKind = Field(description="类型（dict 字典 / form 表单）")
    table: str = Field(description="物理表名（该标识所在实体表）")
    data_source_key: str | None = Field(default=None, description="数据源标识（`form_key → data_source_key` 多对一）")
    status: FormStatus = Field(default=FormStatus.ENABLED, description="状态（enabled / disabled）")

    @computed_field
    @property
    def is_dict(self) -> bool:
        """是否字典（由 `kind` 派生；供界面按数据形态套用字典记录页骨架，避免前端各写一套判定）。"""
        return self.kind == FormKind.DICT


class FormKeyListResponse(BaseSchema):
    """表单标识清单响应（保序：构建期清单序 + 注入序）。"""

    items: Annotated[ConcurrentStableList[FormKeyResponse], CONTRACT_COLLECTION] = Field(
        description="表单标识登记记录清单"
    )

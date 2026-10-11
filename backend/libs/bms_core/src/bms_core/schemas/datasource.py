"""schemas 层统一数据源契约：数据源登记清单响应（与 `bms_core.datasource.registry` 对齐）。

- `DataSourceResponse`：**数据源登记记录响应**（`GET /api/v1/data-sources` 清单条目），字段与
  `DataSourceRecord` 一一对应；枚举字段（类型 / 来源 / 策略 / 状态）用强类型枚举，生成前端联合字面量。
- `DataSourceListResponse`：**登记清单响应**（保序）——列表字段一律用插入序集合类
  （`Annotated[ConcurrentStableList[...], CONTRACT_COLLECTION]`，见《后端开发规范》「集合与排序」）。

契约口径：数据源登记为**构建期清单 + 各项目装载注入、运行期只读**（`DataSourceRegistry`），
本模块只定义**对外响应形状**，不承载登记逻辑。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.registry import (
    DataSourceKind,
    DataSourceOrigin,
    DataSourceStatus,
    DataSourceStrategy,
)
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema

__all__ = ["DataSourceListResponse", "DataSourceResponse"]


class DataSourceResponse(BaseSchema):
    """数据源登记记录响应（与 `DataSourceRecord` 对齐）。"""

    data_source_key: str = Field(description="数据源标识（业务码字符串，全局唯一）")
    name: str = Field(description="名称（数据权限左列 / 通用页面显示）")
    kind: DataSourceKind = Field(description="类型（dict 字典 / form 表单，预留其它）")
    data_source: str = Field(description="数据出口标识（统一出口按此路由到具体实现）")
    origin: DataSourceOrigin = Field(description="来源（platform 平台内建 / product 产品提供）")
    product_key: str | None = Field(default=None, description="产品标识（origin=product 时非空）")
    path: str | None = Field(default=None, description="产品取数路径（origin=product 时前端经网关直取）")
    allowlist: tuple[str, ...] = Field(default=(), description="数据权限可匹配字段白名单")
    cascade: bool = Field(default=False, description="是否级联（有无上级字段）")
    strategies: tuple[DataSourceStrategy, ...] = Field(
        default=(DataSourceStrategy.SELECT,), description="可用策略集合（select / region / match / extension）"
    )
    status: DataSourceStatus = Field(default=DataSourceStatus.ENABLED, description="状态（enabled / disabled）")


class DataSourceListResponse(BaseSchema):
    """统一数据源登记清单响应（保序：构建期清单序 + 注入序）。"""

    items: Annotated[ConcurrentStableList[DataSourceResponse], CONTRACT_COLLECTION] = Field(
        description="数据源登记记录清单"
    )

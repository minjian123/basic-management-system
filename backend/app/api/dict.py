"""字典占位路由：`/api/v1/dicts`（登录即可；真实取数 / 缓存随通用能力·字典模块阶段）。

- 单类型取数 `GET /dicts/{dict_type}`（版本 / 关键字 / 级联父值 / 按值子集 / 上限）。
- 批量合并取数 `POST /dicts/batch`（表单页多字典字段合并一次请求）。
- 后端翻译经 `BaseDictTranslator` 契约取用，不暴露路由；高级查询归 02-4-9 / 02-4-20。
- 契约口径见 `app/dict/base.py`：版本比对只作优化、租户隔离实现侧拼接。
"""

from typing import Annotated

from fastapi import Depends, Query

from app.api.base import BaseRouter, require_auth
from app.api.deps import get_dict_source
from app.dict.base import (
    BaseDictSource,
    DictBatchQuery,
    DictQuery,
)
from app.schemas.common import ApiResponse

router = BaseRouter(
    key="dict",
    prefix="/dicts",
    tags=["dict"],
    dependencies=[Depends(require_auth)],
)

SourceDep = Annotated[BaseDictSource, Depends(get_dict_source)]


def parse_values(raw: str) -> tuple[str, ...]:
    """解析逗号分隔的 value 列表（`values=a,b,c`）。

    Args:
        raw: 逗号分隔字符串。

    Returns:
        tuple[str, ...]: value 元组（去空白项）。
    """
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@router.post("/batch")
async def batch_dicts(source: SourceDep, query: DictBatchQuery) -> ApiResponse:
    """批量合并取字典（一次请求多类型；版本一致的类型 items 返回 null）。

    Args:
        source: 字典取数契约。
        query: 批量取数参数（types / version / locale）。

    Returns:
        ApiResponse: 统一响应，data 为批量结果。
    """
    return ApiResponse.ok(await source.batch(query))


@router.get("/{dict_type}")
async def get_dict_by_type(
    source: SourceDep,
    dict_type: str,
    version: Annotated[int | None, Query(description="客户端本地版本号（一致时 items 返回 null）")] = None,
    keyword: Annotated[str | None, Query(description="关键字（label / value / code）")] = None,
    parent_id: Annotated[str | None, Query(description="级联父值（引用父条目 value）")] = None,
    values: Annotated[str | None, Query(description="指定 value 子集（逗号分隔）")] = None,
    limit: Annotated[int | None, Query(ge=1, description="返回条数上限（探针传 2001）")] = None,
) -> ApiResponse:
    """按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 上限）。

    Args:
        source: 字典取数契约。
        dict_type: 字典类型码。
        version: 客户端本地版本号。
        keyword: 关键字。
        parent_id: 级联父值。
        values: 逗号分隔的 value 子集。
        limit: 返回条数上限。

    Returns:
        ApiResponse: 统一响应，data 为单类型取数结果。
    """
    query = DictQuery(
        dict_type=dict_type,
        version=version,
        keyword=keyword,
        parent_id=parent_id,
        values=parse_values(values) if values else None,
        limit=limit,
    )
    return ApiResponse.ok(await source.by_type(query))

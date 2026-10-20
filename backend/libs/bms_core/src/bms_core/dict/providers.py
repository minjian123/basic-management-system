"""字典域内建查询提供者（02_09 改指）：`target=business` 的只读示例（经统一出口取数）。

- `BuiltinDictQueryProvider`（`key=builtin`）：经**统一出口**按字典标识取条目（`data_source_key` / `keyword` /
  分页），作为高级查询「筛选（business）」模式的默认提供者；自定义提供者经 `BaseQueryProviderRegistry`
  登记接入（02-4-9 契约），未注册 provider 查询抛 404。
- 删除 / 租户过滤由出口与实现侧保证；只读约束（不写库）。
"""

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.dict.base import BaseDataSource, DictItem, DictQuery
from bms_core.dict.query import DictQueryProviderInfo
from bms_core.query.base import BaseQueryProvider, QueryResult

__all__ = ["BuiltinDictQueryProvider"]

PAGE_SIZE_MAX = 100
"""页长上限。"""


class BuiltinDictQueryProvider(BaseQueryProvider):
    """字典条目只读查询提供者（`target=business` 示例；经统一出口取数）。"""

    def __init__(self, *, source: BaseDataSource) -> None:
        """初始化。

        Args:
            source: 字典统一出口取数契约。
        """
        self._source = source

    @property
    def key(self) -> str:
        """提供者标识。

        Returns:
            str: 提供者 key。
        """
        return "builtin"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 提供者说明。
        """
        return "字典条目查询（内建示例提供者）"

    def info(self) -> DictQueryProviderInfo:
        """提供者清单项（供 `GET /dicts/query-providers`）。

        Returns:
            DictQueryProviderInfo: 清单项（含参数 schema 子集）。
        """
        return DictQueryProviderInfo(
            key=self.key,
            name="字典条目查询（内建）",
            target="business",
            data_source_keys=ConcurrentStableList(()),
            param_schema=ConcurrentStableDict(
                {
                    "type": "object",
                    "properties": {
                        "data_source_key": {"type": "string", "description": "字典标识"},
                        "keyword": {"type": "string", "description": "关键字（label / value / code）"},
                        "page": {"type": "integer", "minimum": 1},
                        "size": {"type": "integer", "minimum": 1, "maximum": PAGE_SIZE_MAX},
                    },
                    "required": ["data_source_key"],
                }
            ),
        )

    async def query(self, params: ConcurrentStableDict[str, object]) -> QueryResult:
        """只读查询字典条目（按标识 + 关键字 + 分页；经统一出口）。

        Args:
            params: 查询参数（`data_source_key` / `keyword` / `page` / `size`）。

        Returns:
            QueryResult: 结果行（条目字段）与总数。

        Raises:
            ParamError: 缺少 `data_source_key`。
        """
        data_source_key = params.get("data_source_key")
        if not isinstance(data_source_key, str) or data_source_key == "":
            raise ParamError("缺少 data_source_key 参数")
        keyword = params.get("keyword")
        page = _as_page(params.get("page"))
        size = min(max(1, _as_page(params.get("size"), default=20)), PAGE_SIZE_MAX)
        result = await self._source.by_type(DictQuery(data_source_key=data_source_key))
        items = tuple(result.items or ())
        if isinstance(keyword, str) and keyword.strip():
            text = keyword.strip()
            items = tuple(item for item in items if text in item.label or text in item.value or text in item.code)
        total = len(items)
        page_items = items[(page - 1) * size : (page - 1) * size + size]
        return QueryResult(rows=ConcurrentStableFrozenList(_to_row(item) for item in page_items), total=total)


def _to_row(item: DictItem) -> ConcurrentStableFrozenDict[str, object]:
    """条目 → 结果行（只读字段映射）。

    Args:
        item: 字典条目。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 结果行。
    """
    return ConcurrentStableFrozenDict(
        {
            "value": item.value,
            "label": item.label,
            "code": item.code,
            "parent_id": item.parent_id,
            "sort": item.sort,
            "status": item.status,
            "color": item.color,
        }
    )


def _as_page(value: object, *, default: int = 1) -> int:
    """参数 → 页码 / 页长（非法回落默认）。

    Args:
        value: 原始值。
        default: 默认值。

    Returns:
        int: 归一值。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default

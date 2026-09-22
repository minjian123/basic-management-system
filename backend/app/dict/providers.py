"""字典域内建查询提供者：`target=business` 的只读示例（发现—选择—调用链路演示）。

- `BuiltinDictQueryProvider`（`key=builtin`）：对字典条目表做只读查询（`dict_type` / `keyword` / 分页），
  作为高级查询「筛选（business）」模式的默认提供者；自定义提供者经 `BaseQueryProviderRegistry` 登记接入
  （02-4-9 契约），未注册 provider 查询抛 404。
- 数据权限 / 租户过滤由实现侧（会话按租户库）保证；只读约束（不写库）。
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from sqlalchemy import and_, func, or_, select

from app.core.exceptions import ParamError
from app.db.registry import EngineRegistry
from app.db.session import DbSession, session_scope
from app.dict.models import SysDictItem, SysDictItemI18n, SysDictType
from app.dict.query import DictQueryProviderInfo
from app.i18n.base import DEFAULT_LOCALE
from app.query.base import BaseQueryProvider, QueryResult

__all__ = ["BuiltinDictQueryProvider"]

PAGE_SIZE_MAX = 100
"""页长上限。"""


class BuiltinDictQueryProvider(BaseQueryProvider):
    """字典条目只读查询提供者（`target=business` 示例）。"""

    def __init__(self, *, engines: EngineRegistry) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
        """
        self._engines = engines

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
            dict_types=(),
            param_schema={
                "type": "object",
                "properties": {
                    "dict_type": {"type": "string", "description": "字典类型码"},
                    "keyword": {"type": "string", "description": "关键字（label / value / code）"},
                    "page": {"type": "integer", "minimum": 1},
                    "size": {"type": "integer", "minimum": 1, "maximum": PAGE_SIZE_MAX},
                },
                "required": ["dict_type"],
            },
        )

    async def query(self, params: Mapping[str, object]) -> QueryResult:
        """只读查询字典条目（按类型 + 关键字 + 分页）。

        Args:
            params: 查询参数（`dict_type` / `keyword` / `page` / `size`）。

        Returns:
            QueryResult: 结果行（条目字段）与总数。

        Raises:
            ParamError: 缺少 `dict_type`。
        """
        dict_type = params.get("dict_type")
        if not isinstance(dict_type, str) or dict_type == "":
            raise ParamError("缺少 dict_type 参数")
        keyword = params.get("keyword")
        page = _as_page(params.get("page"))
        size = min(max(1, _as_page(params.get("size"), default=20)), PAGE_SIZE_MAX)
        async with self._session() as session:
            type_row = (
                await session.execute(
                    select(SysDictType).where(
                        SysDictType.type == dict_type,
                        SysDictType.status == "enabled",
                        SysDictType.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if type_row is None:
                return QueryResult(rows=(), total=0)
            conditions = [
                SysDictItem.type_id == type_row.id,
                SysDictItem.status == "enabled",
                SysDictItem.deleted_at.is_(None),
            ]
            if isinstance(keyword, str) and keyword.strip():
                pattern = f"%{keyword.strip()}%"
                conditions.append(
                    or_(
                        SysDictItem.label.like(pattern),
                        SysDictItem.value.like(pattern),
                        SysDictItem.code.like(pattern),
                    )
                )
            total = int(
                (await session.execute(select(func.count()).select_from(SysDictItem).where(*conditions))).scalar_one()
            )
            stmt = (
                select(SysDictItem, SysDictItemI18n.label)
                .outerjoin(
                    SysDictItemI18n,
                    and_(SysDictItemI18n.dict_item_id == SysDictItem.id, SysDictItemI18n.locale == DEFAULT_LOCALE),
                )
                .where(*conditions)
                .order_by(SysDictItem.sort, SysDictItem.id)
                .offset((page - 1) * size)
                .limit(size)
            )
            rows = (await session.execute(stmt)).all()
        result_rows: list[dict[str, object]] = []
        for item, i18n_label in rows:
            result_rows.append(
                {
                    "value": item.value,
                    "label": str(i18n_label or item.label),
                    "code": item.code,
                    "parent_id": item.parent_id,
                    "sort": item.sort,
                    "status": item.status,
                    "color": item.color,
                }
            )
        return QueryResult(rows=tuple(result_rows), total=total)

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（统一会话入口：按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话（异步会话，或同步方言下的同步门面）。
        """
        async with session_scope(self._engines) as session:
            yield session


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

"""导出定义契约 / 注册表 / 查询解析测试。"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.export_definition import (
    EXPORT_ORDERS,
    BaseExportDefinition,
    ExportDefinitionRegistry,
    ExportQuery,
    parse_ids,
)

pytestmark = pytest.mark.kiwi_id(2402)

_DEMO_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (ColumnSpec(key="name", title="姓名"), ColumnSpec(key="phone", title="手机号"))
)


class _Definition(BaseExportDefinition):
    """测试导出定义。"""

    biz = "demo"
    title = "演示"
    masked_fields = ConcurrentStableDict({"phone": "phone"})

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return _DEMO_COLUMNS

    async def count(self, session: DbSession, query: ExportQuery) -> int:
        del session, query
        return 0

    async def fetch(
        self,
        session: DbSession,
        query: ExportQuery,
        *,
        offset: int,
        limit: int,
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        del session, query, offset, limit
        return ConcurrentStableList()


def test_query_defaults_and_orders() -> None:
    """查询缺省值：无筛选 / 升序 / 空集合。"""
    query = ExportQuery()
    assert query.keyword is None
    assert query.status is None
    assert tuple(query.ids) == ()
    assert query.order == "asc"
    assert dict(query.params) == {}
    assert EXPORT_ORDERS == ("asc", "desc")


def test_parse_ids_ok_and_dedup() -> None:
    """ids 解析：逗号分隔、去重保序、空值不限定。"""
    assert tuple(parse_ids(None)) == ()
    assert tuple(parse_ids("  ")) == ()
    assert tuple(parse_ids(" 3, 1 ,3,2 ")) == (3, 1, 2)


@pytest.mark.parametrize("raw", ["abc", "1,-2", "0", "1.5"])
def test_parse_ids_invalid(raw: str) -> None:
    """ids 非法项拒绝（10001）。"""
    with pytest.raises(ParamError):
        parse_ids(raw)


def test_register_and_get() -> None:
    """正常登记后可取；快照含业务键。"""
    registry = ExportDefinitionRegistry()
    definition = _Definition()
    registry.register(definition)
    assert registry.get("demo") is definition
    snapshot = registry.all()
    assert snapshot["demo"] is definition
    assert len(snapshot) == 1


def test_register_rejects_duplicate() -> None:
    """重名拒绝。"""
    registry = ExportDefinitionRegistry()
    registry.register(_Definition())
    with pytest.raises(ValueError, match="重复"):
        registry.register(_Definition())


class _InvalidBiz(_Definition):
    biz = "Demo"


class _EmptyTitle(_Definition):
    biz = "demo2"
    title = " "


class _EmptyColumns(_Definition):
    biz = "demo3"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return ConcurrentStableFrozenList()


class _DuplicateKey(_Definition):
    biz = "demo4"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return ConcurrentStableFrozenList(
            (ColumnSpec(key="name", title="姓名"), ColumnSpec(key="name", title="手机号"))
        )


class _DuplicateTitle(_Definition):
    biz = "demo5"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return ConcurrentStableFrozenList((ColumnSpec(key="name", title="姓名"), ColumnSpec(key="phone", title="姓名")))


class _MaskedNotInColumns(_Definition):
    biz = "demo6"
    masked_fields = ConcurrentStableDict({"email": "email"})


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        (_InvalidBiz, "标识非法"),
        (_EmptyTitle, "标题为空"),
        (_EmptyColumns, "列集为空"),
        (_DuplicateKey, "列键重复"),
        (_DuplicateTitle, "列标题重复"),
        (_MaskedNotInColumns, "脱敏字段不在列集内"),
    ],
)
def test_register_rejects_invalid_definition(factory: type[_Definition], reason: str) -> None:
    """非法定义构建期拒绝（fail-fast）。"""
    with pytest.raises(ValueError, match=reason):
        ExportDefinitionRegistry().register(factory())

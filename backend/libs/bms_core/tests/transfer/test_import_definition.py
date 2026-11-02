"""导入定义契约 / 注册表 / 汇总测试。"""

from __future__ import annotations

from typing import cast

import pytest

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.db.session import DbSession
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.definition import (
    BaseImportDefinition,
    ImportBatchUnitOfWork,
    ImportDefinitionRegistry,
    ImportRowContext,
    ImportSummary,
)
from bms_core.transfer.importer import ParsedRow, RowError

pytestmark = pytest.mark.kiwi_id(2401)

_DEMO_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (ColumnSpec(key="name", title="姓名", required=True),)
)


class _Definition(BaseImportDefinition):
    """测试定义。"""

    biz = "demo"
    title = "演示"
    write_permission = "demo:create"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return _DEMO_COLUMNS

    async def validate_row(
        self, row: ParsedRow, preloaded: object, *, config: BaseConfigSource | None
    ) -> ConcurrentStableFrozenList[RowError]:
        del preloaded, config
        if row.values.get("name") == "坏":
            return ConcurrentStableFrozenList((RowError(row=row.row_no, message="坏值", field="name"),))
        return ConcurrentStableFrozenList()

    async def write_row(self, row: ParsedRow, ctx: ImportRowContext) -> None:
        del row, ctx


class _CustomColumns(_Definition):
    """列集可替换的测试定义。"""

    def __init__(self, columns: ConcurrentStableFrozenList[ColumnSpec]) -> None:
        self._columns = columns

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return self._columns

    async def validate_row(
        self, row: ParsedRow, preloaded: object, *, config: BaseConfigSource | None
    ) -> ConcurrentStableFrozenList[RowError]:
        del row, preloaded, config
        return ConcurrentStableFrozenList()


def test_registry_register_get_all() -> None:
    """登记 / 取 / 全量快照；重名即拒。"""
    registry = ImportDefinitionRegistry()
    definition = _Definition()
    registry.register(definition)
    assert registry.get("demo") is definition
    assert registry.get("missing") is None
    assert registry.all()["demo"] is definition
    with pytest.raises(ValueError, match="重复"):
        registry.register(_Definition())


def test_registry_rejects_invalid() -> None:
    """非法业务标识 / 空标题 / 空列集 / 重复列键 / 重复列标题。"""
    registry = ImportDefinitionRegistry()
    bad_biz = _Definition()
    bad_biz.biz = "Bad-Biz"
    with pytest.raises(ValueError, match="标识非法"):
        registry.register(bad_biz)

    empty_title = _Definition()
    empty_title.title = ""
    with pytest.raises(ValueError, match="标题为空"):
        registry.register(empty_title)

    with pytest.raises(ValueError, match="列集为空"):
        registry.register(_CustomColumns(ConcurrentStableFrozenList()))

    with pytest.raises(ValueError, match="列键重复"):
        registry.register(
            _CustomColumns(
                ConcurrentStableFrozenList((ColumnSpec(key="name", title="姓名"), ColumnSpec(key="name", title="名称")))
            )
        )

    with pytest.raises(ValueError, match="列标题重复"):
        registry.register(
            _CustomColumns(
                ConcurrentStableFrozenList((ColumnSpec(key="a", title="姓名"), ColumnSpec(key="b", title="姓名")))
            )
        )


async def test_default_preload_and_write_row() -> None:
    """默认预取返回 None；默认写路径未实现。"""
    definition = _Definition()
    assert await definition.preload(None, ConcurrentStableList()) is None  # type: ignore[arg-type]

    class _Bare(BaseImportDefinition):
        biz = "bare"
        title = "空"

        @property
        def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
            return _DEMO_COLUMNS

        async def validate_row(
            self, row: ParsedRow, preloaded: object, *, config: BaseConfigSource | None
        ) -> ConcurrentStableFrozenList[RowError]:
            del row, preloaded, config
            return ConcurrentStableFrozenList()

    with pytest.raises(NotImplementedError):
        await _Bare().write_row(
            ParsedRow(row_no=2, values=ConcurrentStableFrozenDict[str, object]()),
            ImportRowContext(
                session=None,  # type: ignore[arg-type]
                uow=None,  # type: ignore[arg-type]
                actor=None,
                tenant_id=None,
                tenant_code=None,
            ),
        )


async def test_batch_unit_of_work_joins_outer_transaction() -> None:
    """批次工作单元：begin 为空上下文、commit / rollback 不触发会话事务。"""
    session = cast("DbSession", object())
    uow = ImportBatchUnitOfWork(session)
    assert uow.session is session
    async with uow.begin() as value:
        assert value is None
    assert await uow.commit() is None
    assert await uow.rollback() is None


def test_summary_output() -> None:
    """汇总字段与作业输出一致。"""
    summary = ImportSummary(total=10, success_count=0, fail_count=2, blocked_count=8, committed=False)
    output = summary.to_output()
    assert output["total"] == 10
    assert output["fail_count"] == 2
    assert output["committed"] is False

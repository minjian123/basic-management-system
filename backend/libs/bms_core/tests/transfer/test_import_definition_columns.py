"""导入定义列集钩子（Kiwi 2526）：`columns_for` 默认回退静态列集，既有定义零改动。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.db.session import DbSession
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.definition import BaseImportDefinition
from bms_core.transfer.importer import ParsedRow, RowError

pytestmark = pytest.mark.kiwi_id(2526)

_COLUMNS = ConcurrentStableFrozenList((ColumnSpec(key="a", title="甲"), ColumnSpec(key="b", title="乙")))


class _DemoDefinition(BaseImportDefinition):
    """最小演示定义（只实现必需面，覆盖默认列集钩子）。"""

    biz = "demo"
    title = "演示"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """静态列集。"""
        return _COLUMNS

    async def validate_row(
        self, row: ParsedRow, preloaded: object, *, config: object | None
    ) -> ConcurrentStableFrozenList[RowError]:
        """行校验（演示恒通过）。"""
        del row, preloaded, config
        return ConcurrentStableFrozenList(())


async def test_columns_for_defaults_to_static_columns() -> None:
    """未覆写时 `columns_for` 返回静态列集（既有定义零改动、行为不变）。"""
    definition = _DemoDefinition()
    columns = await definition.columns_for(session=None)  # type: ignore[arg-type]
    assert columns is _COLUMNS


async def test_columns_for_override_is_used() -> None:
    """覆写后取派生列集（`users` 定义即此形态）。"""

    class _Derived(_DemoDefinition):
        async def columns_for(self, session: DbSession) -> ConcurrentStableFrozenList[ColumnSpec]:
            del session
            return ConcurrentStableFrozenList((ColumnSpec(key="b", title="乙"),))

    columns = await _Derived().columns_for(session=None)  # type: ignore[arg-type]
    assert [spec.key for spec in columns] == ["b"]

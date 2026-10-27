"""冲突预检用例（07B `02_03` 详设 §3.5；用例 5 / 26 的真实实现验证）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：`precheck_conflicts` 在真实 SQLite 库上按 `db_key` 只读比对——无行不报冲突、
同值不报、异值报（含「现有 / 期望」明细）、**一次列全全部冲突**（不止第一个）、
未实现 `expected_rows` 的种子跳过、表未登记跳过。
"""

from pathlib import Path
from typing import Any, cast

from sqlalchemy import Table, text

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed import orchestrator


class _Engines:
    """同步引擎提供者替身：按 db_key 返回同一 SQLite 同步引擎。"""

    def __init__(self, url: str) -> None:
        """初始化。

        Args:
            url: SQLite 文件路径（同步方言）。
        """
        from sqlalchemy import create_engine

        self._engine = create_engine(url)

    async def get_sync(self, db_key: str, *, read_only: bool = False) -> Any:
        """取同步引擎（忽略 db_key / read_only）。

        Args:
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            Any: 同步引擎。
        """
        del db_key, read_only
        return self._engine


def _plan(*records: SeedRecord) -> ConcurrentStableList[orchestrator.SeedPlanItem]:
    """构造编排计划。

    Args:
        *records: 种子记录。

    Returns:
        ConcurrentStableList[SeedPlanItem]: 计划。
    """
    return orchestrator.build_plan(ConcurrentStableList(records), tenant="demo")


def _record(name: str, *, module: str) -> SeedRecord:
    """构造种子记录。

    Args:
        name: 种子名。
        module: 入口模块（`expected_rows` 来源）。

    Returns:
        SeedRecord: 种子记录。
    """
    return SeedRecord(
        name=name,
        module=module,
        entry="seed_menu_entry",
        service="platform",
        db_key="platform_platform",
        after=ConcurrentStableFrozenList(),
        source="platform",
    )


def _prepare_db(tmp_path: Path) -> str:
    """建真实 SQLite 库并建 `sys_business` / `sys_role` 表（空表）。

    Args:
        tmp_path: 临时目录。

    Returns:
        str: 同步连接串。
    """
    from sqlalchemy import create_engine

    from bms_core.models.base import Base
    from bms_core.models.platform.menu_form import SysMenu
    from bms_core.models.platform.permission_meta import SysAction, SysBusiness
    from bms_core.models.platform.role import SysRole

    url = f"sqlite:///{tmp_path / 'conflict.db'}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                cast("Table", SysBusiness.__table__),
                cast("Table", SysAction.__table__),
                cast("Table", SysMenu.__table__),
                cast("Table", SysRole.__table__),
            ],
        )
    finally:
        engine.dispose()
    return url


def _insert_business(url: str, *, code: str, name: str) -> None:
    """插入一行业务码。

    Args:
        url: 连接串。
        code: 业务码。
        name: 名称。
    """
    from sqlalchemy import create_engine

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_business (form_key, code, name, status, id, created_at, updated_at, version) "
                    "VALUES ('business', :code, :name, 'enabled', 1, '2026-01-01', '2026-01-01', 1)"
                ),
                {"code": code, "name": name},
            )
    finally:
        engine.dispose()


async def test_no_conflict_when_table_empty(tmp_path: Path) -> None:
    """目标表为空 → 无冲突（待新建，不算冲突）。"""
    url = _prepare_db(tmp_path)
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("seed-menu", module="bms_core.tenant.seed.menu")),
        engines=_Engines(url),
    )
    assert list(conflicts) == []


async def test_no_conflict_when_values_match(tmp_path: Path) -> None:
    """目标行已存在且值一致 → 无冲突（该行按「跳过」计）。"""
    url = _prepare_db(tmp_path)
    _insert_business(url, code="sys", name="平台运维总控")
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("seed-menu", module="bms_core.tenant.seed.menu")),
        engines=_Engines(url),
    )
    assert list(conflicts) == []


async def test_conflict_reported_with_existing_and_expected(tmp_path: Path) -> None:
    """用例 5：目标行存在且值不一致 → 冲突明细含「现有 / 期望」。"""
    url = _prepare_db(tmp_path)
    _insert_business(url, code="sys", name="被改过的名字")
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("seed-menu", module="bms_core.tenant.seed.menu")),
        engines=_Engines(url),
    )
    assert len(conflicts) == 1
    text_ = conflicts[0]
    assert "seed-menu" in text_
    assert "sys_business" in text_
    assert "code='sys'" in text_
    assert "被改过的名字" in text_
    assert "平台运维总控" in text_


async def test_conflicts_list_all_not_only_first(tmp_path: Path) -> None:
    """用例 5 强断言：**一次列全全部冲突**（不止第一个）。"""
    url = _prepare_db(tmp_path)
    _insert_business(url, code="sys", name="改1")
    from sqlalchemy import create_engine

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_business (form_key, code, name, status, id, created_at, updated_at, version) "
                    "VALUES ('business', 'tenant', '改2', 'enabled', 2, '2026-01-01', '2026-01-01', 1)"
                )
            )
    finally:
        engine.dispose()
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("seed-menu", module="bms_core.tenant.seed.menu")),
        engines=_Engines(url),
    )
    assert len(conflicts) >= 2
    joined = " ".join(conflicts)
    assert "code='sys'" in joined
    assert "code='tenant'" in joined


async def test_seed_without_expected_rows_is_skipped(tmp_path: Path) -> None:
    """未实现 `expected_rows` 的种子跳过预检（仅靠唯一约束兜底），不报冲突。"""
    url = _prepare_db(tmp_path)
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("x", module="bms_core.core.concurrent")),
        engines=_Engines(url),
    )
    assert list(conflicts) == []


async def test_unregistered_table_is_skipped(tmp_path: Path) -> None:
    """`expected_rows` 指向未登记表 → 跳过（不抛错）。"""
    from bms_core.tenant.seed.contract import ExpectedRow

    url = _prepare_db(tmp_path)
    record = _record("fake", module="fake.module")

    def _rows() -> ConcurrentStableList[ExpectedRow]:
        """替身期望行（指向未登记表）。

        Returns:
            ConcurrentStableList[ExpectedRow]: 期望行。
        """
        from bms_core.core.concurrent import ConcurrentStableFrozenDict

        return ConcurrentStableList(
            [
                ExpectedRow(
                    table="no_such_table",
                    key=ConcurrentStableFrozenDict({"code": "x"}),
                    values=ConcurrentStableFrozenDict({"name": "y"}),
                )
            ]
        )

    original = orchestrator.expected_rows_of
    orchestrator.expected_rows_of = lambda _record: _rows()  # type: ignore[assignment]
    try:
        conflicts = await orchestrator.precheck_conflicts(_plan(record), engines=_Engines(url))
    finally:
        orchestrator.expected_rows_of = original  # type: ignore[assignment]
    assert list(conflicts) == []


async def test_conflict_on_role_table(tmp_path: Path) -> None:
    """用例 26 同口径（角色表）：`seed-rbac-role` 的期望角色名被改 → 报冲突。"""
    from sqlalchemy import create_engine

    url = _prepare_db(tmp_path)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO sys_role "
                    "(form_key, code, name, role_type, status, id, created_at, updated_at, version) "
                    "VALUES ('role', 'system_admin', '被改名', 'system', 'enabled', 1, '2026-01-01', '2026-01-01', 1)"
                )
            )
    finally:
        engine.dispose()
    conflicts = await orchestrator.precheck_conflicts(
        _plan(_record("seed-rbac-role", module="bms_core.tenant.seed.rbac")),
        engines=_Engines(url),
    )
    assert len(conflicts) == 1
    assert "system_admin" in conflicts[0]
    assert "被改名" in conflicts[0]

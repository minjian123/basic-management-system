"""零散分支补齐用例（07B `02_03`；覆盖率收尾）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：迁移清单注册校验的失败分支、种子声明 `tables` 结构非法、`_module_exists` 的
`ModuleNotFoundError` 分支、`config` 缺省 URL 分支、事务基类缺省统计回退、菜单 / 归属清退分支。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import CatalogError
from bms_core.registry.products import _seed_tables  # pyright: ignore[reportPrivateUsage]
from bms_core.tenant.seed import config as config_seed
from bms_core.tenant.seed import orchestrator
from bms_core.transaction.base import BaseTransactionParticipant, BranchOp

# ---- 迁移清单注册校验失败分支 ----


def _stub_14(_name: Any) -> Any:
    """替身（"resolve_series"）。"""
    return object()


def _stub_15(_series: Any) -> Any:
    """替身（"has_revisions"）。"""
    return True


def test_validate_series_registry_reports_unresolvable_series(monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移清单解析失败 → 记入错误（不中断整轮校验）。"""
    from bms_core.core.exceptions import ConfigError
    from bms_core.db import migration

    def _fail(_name: str) -> None:
        """替身：解析清单抛 ConfigError。

        Args:
            _name: 清单名。

        Raises:
            ConfigError: 恒定抛出。
        """
        raise ConfigError("清单不存在")

    monkeypatch.setattr(migration, "resolve_series", _fail)
    errors = migration.validate_series_registry()
    assert any("解析失败" in error for error in errors)


def test_validate_series_registry_reports_alembic_config_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """`alembic_config` 构造失败 → 记入错误。"""
    from bms_core.core.exceptions import ConfigError
    from bms_core.db import migration

    monkeypatch.setattr(migration, "resolve_series", _stub_14)
    monkeypatch.setattr(migration, "has_revisions", _stub_15)

    def _fail(_series: object) -> None:
        """替身：构造配置抛 ConfigError。

        Args:
            _series: 清单（忽略）。

        Raises:
            ConfigError: 恒定抛出。
        """
        raise ConfigError("配置非法")

    monkeypatch.setattr(migration, "alembic_config", _fail)
    errors = migration.validate_series_registry()
    assert "配置非法" in errors


# ---- 种子声明 tables 结构非法 ----


def test_seed_tables_rejects_non_string_key() -> None:  # pyright: ignore[reportPrivateUsage]
    """`[seeds.tables]` 值非字符串 → `CatalogError`。"""
    with pytest.raises(CatalogError, match="tables 项须为"):
        _seed_tables({"sys_business": 123}, scope="seeds")  # pyright: ignore[reportPrivateUsage]


def test_seed_tables_rejects_empty_key() -> None:  # pyright: ignore[reportPrivateUsage]
    """`[seeds.tables]` 值为空串 → `CatalogError`。"""
    with pytest.raises(CatalogError, match="tables 项须为"):
        _seed_tables({"sys_business": ""}, scope="seeds")  # pyright: ignore[reportPrivateUsage]


def test_seed_tables_accepts_valid_mapping() -> None:  # pyright: ignore[reportPrivateUsage]
    """合法映射正常解析（表名 → 自然键）。"""
    result = _seed_tables({"sys_business": "code"}, scope="seeds")  # pyright: ignore[reportPrivateUsage]
    assert dict(result) == {"sys_business": "code"}


def test_seed_tables_returns_empty_for_none() -> None:  # pyright: ignore[reportPrivateUsage]
    """未声明 `tables` → 空映射。"""
    assert dict(_seed_tables(None, scope="seeds")) == {}  # pyright: ignore[reportPrivateUsage]


# ---- _module_exists 的 ModuleNotFoundError 分支 ----


def test_module_exists_handles_nested_missing_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    """`find_spec` 抛 `ModuleNotFoundError`（父包缺失）→ False。"""
    import importlib.util

    def _raise(_name: str) -> None:
        """替身：抛 ModuleNotFoundError。

        Args:
            _name: 模块名。

        Raises:
            ModuleNotFoundError: 恒定抛出。
        """
        raise ModuleNotFoundError("父包缺失")

    monkeypatch.setattr(importlib.util, "find_spec", _raise)
    assert orchestrator._module_exists("absent.child") is False  # pyright: ignore[reportPrivateUsage]


# ---- config 缺省 URL 分支 ----


def test_config_database_url_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 `BMS_MIGRATION_URL` 时回落到配置的租户库模板。"""
    monkeypatch.delenv("BMS_MIGRATION_URL", raising=False)
    url = config_seed._database_url()  # pyright: ignore[reportPrivateUsage]
    assert url


# ---- 事务基类缺省统计回退 ----


async def test_base_participant_default_stats_returns_zero() -> None:
    """`BaseTransactionParticipant.execute_branch_with_stats` 缺省回退：调 `execute_branch` + 零统计。"""

    class _Impl(BaseTransactionParticipant):
        """最小参与方实现（只覆写抽象方法）。"""

        plugin_name = "impl"

        @property
        def enabled(self) -> bool:
            """恒真。"""
            return True

        async def execute_branch(self, *, xid: str, db_key: str, ops: ConcurrentStableList[BranchOp]) -> str:
            """返回 prepared。

            Args:
                xid: 分支标识。
                db_key: 库键。
                ops: 操作清单。

            Returns:
                str: 固定 prepared。
            """
            del xid, db_key, ops
            return "prepared"

        async def commit_branch(self, *, xid: str, db_key: str) -> str:
            """返回 committed。

            Args:
                xid: 分支标识。
                db_key: 库键。

            Returns:
                str: 固定 committed。
            """
            del xid, db_key
            return "committed"

        async def rollback_branch(self, *, xid: str, db_key: str) -> str:
            """返回 rolled_back。

            Args:
                xid: 分支标识。
                db_key: 库键。

            Returns:
                str: 固定 rolled_back。
            """
            del xid, db_key
            return "rolled_back"

        async def branch_state(self, *, xid: str, db_key: str) -> str:
            """返回 active。

            Args:
                xid: 分支标识。
                db_key: 库键。

            Returns:
                str: 固定 active。
            """
            del xid, db_key
            return "active"

        async def recover_branches(self, *, db_key: str) -> ConcurrentStableList[str]:
            """返回空。

            Args:
                db_key: 库键。

            Returns:
                ConcurrentStableList[str]: 空清单。
            """
            del db_key
            return ConcurrentStableList()

    participant = _Impl()
    state, stats = await participant.execute_branch_with_stats(
        xid="t|a", db_key="platform_platform", ops=ConcurrentStableList()
    )
    assert state == "prepared"
    assert (stats.created, stats.updated, stats.skipped) == (0, 0, 0)


# ---- 表归属清退分支 ----


def test_retire_absent_soft_deletes_unknown_rows() -> None:
    """`_retire_absent` 软删不在清单的登记行（幂等）。"""
    from bms_core.models.ownership import SysTableOwnership
    from bms_core.tenant.seed import tables as tables_seed

    row = SysTableOwnership(table_name="ghost", owner="platform", datasource="platform", status="enabled")
    retired = tables_seed._retire_absent([row], ConcurrentStableSet())  # pyright: ignore[reportPrivateUsage]
    assert retired == 1
    assert row.deleted_at is not None


def test_retire_absent_keeps_known_rows() -> None:
    """清单内的行不清退。"""
    from bms_core.models.ownership import SysTableOwnership
    from bms_core.tenant.seed import tables as tables_seed

    row = SysTableOwnership(table_name="sys_business", owner="platform", datasource="platform", status="enabled")
    assert tables_seed._retire_absent([row], ConcurrentStableSet(["sys_business"])) == 0  # pyright: ignore[reportPrivateUsage]
    assert row.deleted_at is None


# ---- 菜单种子：空输入分支 ----


def test_menu_expected_rows_skips_empty_values() -> None:
    """菜单期望行不含空名称（防御性：常量清单为空值时跳过）。"""
    from bms_core.tenant.seed import menu as menu_seed

    rows = menu_seed.expected_rows()
    assert all(row.values.get("name") for row in rows)

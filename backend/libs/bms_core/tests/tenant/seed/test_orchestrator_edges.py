"""编排器边界分支用例（07B `02_03`；覆盖率补齐，对应详设 §3.5 / §3.6 / §3.8 的边角路径）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。
"""

from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.services.module_registry import SeedRecord
from bms_core.tenant.seed import orchestrator
from bms_core.transaction.base import BRANCH_PREPARED, BranchStats


def _record(name: str, *, after: ConcurrentStableFrozenList[str] | None = None) -> SeedRecord:
    """构造种子记录。

    Args:
        name: 种子名。
        after: 依赖的种子名。

    Returns:
        SeedRecord: 记录。
    """
    return SeedRecord(
        name=name,
        module="ops.seed_menu",
        entry="seed_menu_entry",
        service="platform",
        db_key="platform_platform",
        after=after if after is not None else ConcurrentStableFrozenList(),
        source="platform",
    )


def _plan(*names: str) -> ConcurrentStableList[orchestrator.SeedPlanItem]:
    """构造计划。

    Args:
        *names: 种子名。

    Returns:
        ConcurrentStableList[SeedPlanItem]: 计划。
    """
    return orchestrator.build_plan(ConcurrentStableList(_record(name) for name in names), tenant="demo")


class _Manager:
    """事务管理器替身。"""

    async def begin(self, *, branches: ConcurrentStableList[Any], **_kwargs: Any) -> Any:
        """开启事务。

        Args:
            branches: 分支声明。
            **_kwargs: 忽略。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import BranchRef, GlobalTransaction

        return GlobalTransaction(
            global_txn_id="t",
            caller_service="platform",
            state="active",
            branches=ConcurrentStableFrozenList(
                BranchRef(branch_id=spec.branch_id, service=spec.service, db_key=spec.db_key, xid=f"t|{spec.branch_id}")
                for spec in branches
            ),
        )

    async def commit(self, global_txn_id: str) -> Any:
        """提交。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> Any:
        """回滚。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _Runner:  # pyright: ignore[reportUnusedClass]
    """分支执行器替身：按序 prepared。"""

    async def execute_branch_with_stats(self, *, xid: str, db_key: str, ops: Any) -> Any:
        """执行分支。

        Args:
            xid: 分支标识。
            db_key: 库键。
            ops: 操作清单。

        Returns:
            Any: （prepared, 统计）。
        """
        del xid, db_key, ops
        return BRANCH_PREPARED, BranchStats()


# ---- require_closure 边界 ----


def test_require_closure_skips_unknown_names() -> None:
    """闭包展开跳过不在执行集合内的名字（不抛错，由 `select_seeds` 前置校验报）。"""
    records = ConcurrentStableList([_record("a")])
    closure = orchestrator.require_closure(records, ConcurrentStableList(["ghost"]))
    assert list(closure) == []


def test_require_closure_deduplicates() -> None:
    """同一依赖被多条路径引用时只登记一次。"""
    records = ConcurrentStableList(
        [
            _record("a"),
            _record("b", after=ConcurrentStableFrozenList(["a"])),
            _record("c", after=ConcurrentStableFrozenList(["a"])),
        ]
    )
    closure = orchestrator.require_closure(records, ConcurrentStableList(["b", "c"]))
    assert list(closure).count("a") == 1


# ---- 拓扑排序边界 ----


def test_topological_order_stops_when_no_progress() -> None:
    """全部种子互相依赖（有环且未被前置拦截）时无法推进：返回已完成部分。"""
    records = ConcurrentStableList(
        [
            _record("a", after=ConcurrentStableFrozenList(["b"])),
            _record("b", after=ConcurrentStableFrozenList(["a"])),
        ]
    )
    assert list(orchestrator.topological_order(records)) == []


# ---- 执行器兼容 / 缺失 ----


async def test_run_branch_raises_for_runner_without_any_method() -> None:
    """执行器两个方法都没有 → `ParamError`（不静默成功）。"""
    with pytest.raises(ParamError, match="既未实现"):
        await orchestrator._run_branch(  # pyright: ignore[reportPrivateUsage]
            object(),  # type: ignore[arg-type]
            xid="t|a",
            db_key="platform_platform",
            ops=ConcurrentStableFrozenList(),
        )


async def test_execute_plan_uses_plain_runner_fallback() -> None:
    """执行器只实现 `execute_branch`：可编排，统计为 0。"""

    class _Plain:
        """仅 `execute_branch` 的执行器。"""

        async def execute_branch(self, *, xid: str, db_key: str, ops: Any) -> str:
            """执行分支。

            Args:
                xid: 分支标识。
                db_key: 库键。
                ops: 操作清单。

            Returns:
                str: 分支状态。
            """
            del xid, db_key, ops
            return BRANCH_PREPARED

    reports = await orchestrator.execute_plan(
        _plan("a"),
        tenant="demo",
        caller_service="platform",
        manager=_Manager(),
        branch_runner=_Plain(),  # type: ignore[arg-type]
    )
    assert reports[0].status == "ok"
    assert reports[0].created == 0


# ---- _first_unfinished 边界 ----


def test_first_unfinished_returns_minus_one_when_all_prepared() -> None:
    """全部 prepared → -1（异常定位无目标）。"""
    reports = ConcurrentStableList([orchestrator.SeedReport(name="a", source="platform", status="prepared")])
    assert orchestrator._first_unfinished(reports) == -1  # pyright: ignore[reportPrivateUsage]


def test_first_unfinished_returns_first_pending_index() -> None:
    """有 pending 项 → 返回其下标。"""
    reports = ConcurrentStableList(
        [
            orchestrator.SeedReport(name="a", source="platform", status="prepared"),
            orchestrator.SeedReport(name="b", source="platform", status="pending"),
        ]
    )
    assert orchestrator._first_unfinished(reports) == 1  # pyright: ignore[reportPrivateUsage]


# ---- 结构前置 ----


async def test_ensure_structure_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """建表失败 → 返回错误明细（调用方据此中止，不进事务）。"""
    import bms_core.db.bootstrap as bootstrap

    async def _fail(_settings: Any) -> Any:
        """替身：建表抛异常。

        Args:
            _settings: 配置（忽略）。

        Raises:
            RuntimeError: 恒定抛出。
        """
        raise RuntimeError("建表炸了")

    monkeypatch.setattr(bootstrap, "ensure_unit_schema", _fail)
    errors = await orchestrator.ensure_structure(_plan("a"), tenant="demo")
    assert errors
    assert "结构就绪失败" in errors[0]


async def test_ensure_structure_logs_created_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """建表成功且新建了表 → 记日志、无错误。"""
    import bms_core.db.bootstrap as bootstrap

    async def _ok(_settings: Any) -> Any:
        """替身：新建 2 张表。

        Args:
            _settings: 配置（忽略）。

        Returns:
            Any: 新建表清单。
        """
        return ["t1", "t2"]

    monkeypatch.setattr(bootstrap, "ensure_unit_schema", _ok)
    assert list(await orchestrator.ensure_structure(_plan("a"), tenant="demo")) == []


async def test_ensure_structure_no_new_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    """建表成功但无新表（幂等）→ 无错误、不记 created 日志。"""
    import bms_core.db.bootstrap as bootstrap

    async def _ok(_settings: Any) -> Any:
        """替身：无新表。

        Args:
            _settings: 配置（忽略）。

        Returns:
            Any: 空清单。
        """
        return []

    monkeypatch.setattr(bootstrap, "ensure_unit_schema", _ok)
    assert list(await orchestrator.ensure_structure(_plan("a"), tenant="demo")) == []

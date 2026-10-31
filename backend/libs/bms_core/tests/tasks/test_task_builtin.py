"""内置任务护栏：清单与 cron 合法 / 未落地执行体返回 skipped + 归口说明。

孤儿分片清理已随 03_01 落地（触发型），其行为由 `test_builtin_cleanup.py` 覆盖。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.task import TASK_RUN_SKIPPED
from bms_core.tasks.builtin import (
    BUILTIN_TASK_SPECS,
    builtin_spec_of,
    run_archive_audit_logs,
    run_precreate_shard_tables,
    run_purge_soft_deleted,
)
from bms_core.tasks.cron import is_valid_cron
from bms_core.tasks.handlers import builtin_handlers
from bms_core.tasks.spec import TaskContext, TaskRunSpec

pytestmark = pytest.mark.kiwi_id(2371)


def _ctx() -> TaskContext:
    """构造无参执行上下文。

    Returns:
        TaskContext: 执行上下文。
    """
    return TaskContext(
        run=TaskRunSpec(db_key="tenant_platform_demo", task_id=1, log_id=1, run_id="r", code="c", handler="m:f")
    )


def test_builtin_specs_are_four_and_cron_valid() -> None:
    """四条内置任务：代码 / 名称 / cron / handler / 归口齐备，cron 全部可解析。"""
    assert isinstance(BUILTIN_TASK_SPECS, ConcurrentStableList)
    assert [spec.code for spec in BUILTIN_TASK_SPECS] == [
        "cleanup_orphan_parts",
        "archive_audit_logs",
        "precreate_shard_tables",
        "purge_soft_deleted",
    ]
    for spec in BUILTIN_TASK_SPECS:
        assert is_valid_cron(spec.cron) is True
        assert spec.handler.startswith("bms_core.tasks.builtin:")
        assert spec.owner
        assert spec.summary


def test_builtin_specs_match_handler_registry() -> None:
    """清单与 handler 注册表一一对应（改一处漏一处即失败）。"""
    registry = builtin_handlers()
    for spec in BUILTIN_TASK_SPECS:
        assert registry[spec.code] == spec.handler


def test_builtin_spec_of_hit_and_miss() -> None:
    """按代码取内置定义：命中返回定义，非内置返回 None。"""
    hit = builtin_spec_of("archive_audit_logs")
    assert hit is not None
    assert hit.name == "审计日志归档"
    assert builtin_spec_of("biz_some_product_task") is None


async def test_all_builtin_runners_skip_with_owner() -> None:
    """占位执行体统一返回 skipped，且说明里写明归口任务号。"""
    cases = (
        (run_archive_audit_logs, "06_01"),
        (run_precreate_shard_tables, "13"),
        (run_purge_soft_deleted, "13"),
    )
    for runner, owner in cases:
        result = await runner(_ctx())
        assert result.status == TASK_RUN_SKIPPED
        assert owner in result.message
        assert "占位实现" in result.message

"""作业处理器注册表护栏（Kiwi 2385）：装载 / 重复 / 类型一致 / 声明对账 / 路径解析。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import JobHandlerNotRegisteredError, JobTypeNotRegisteredError
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.registry import JobHandlerRegistry, resolve_handler_path

pytestmark = pytest.mark.kiwi_id(2385)


class _Handler(BaseJobHandler):
    job_type = "demo.echo"

    async def run(self, ctx: JobContext) -> JobResult:
        _ = ctx
        return JobResult.success()


class _Other(BaseJobHandler):
    job_type = "demo.other"

    async def run(self, ctx: JobContext) -> JobResult:
        _ = ctx
        return JobResult.success()


def test_load_and_get() -> None:
    """装载后可取；未注册类型抛 71002。"""
    registry = JobHandlerRegistry()
    registry.load({"demo.echo": _Handler()})
    assert isinstance(registry.get("demo.echo"), _Handler)
    assert registry.has("demo.echo") is True
    assert set(registry.job_types()) == {"demo.echo"}
    with pytest.raises(JobTypeNotRegisteredError):
        registry.get("demo.missing")


def test_register_rejects_type_mismatch() -> None:
    """注册键与 `handler.job_type` 不一致：拒绝。"""
    registry = JobHandlerRegistry()
    with pytest.raises(JobHandlerNotRegisteredError, match="不一致"):
        registry.register("demo.wrong", _Handler())


def test_register_rejects_duplicate() -> None:
    """同类型登记不同实例：拒绝（同实例幂等）。"""
    handler = _Handler()
    registry = JobHandlerRegistry()
    registry.register("demo.echo", handler)
    registry.register("demo.echo", handler)
    with pytest.raises(JobHandlerNotRegisteredError, match="重复"):
        registry.register("demo.echo", _Handler())


def test_reconcile_reports_missing_and_undeclared() -> None:
    """声明缺代码 → 错误；代码缺声明 → 告警；路径不一致 → 错误。"""
    registry = JobHandlerRegistry()
    registry.load({"demo.echo": _Handler(), "demo.other": _Other()})
    errors, warnings = registry.reconcile(
        {
            "demo.echo": f"{_Handler.__module__}:{_Handler.__qualname__}",
            "demo.absent": "some.module:Handler",
        }
    )
    assert any("demo.absent" in item for item in errors)
    assert any("demo.other" in item for item in warnings)

    errors, _ = registry.reconcile({"demo.echo": "wrong.module:Handler"})
    assert any("路径与代码侧不一致" in item for item in errors)


def test_resolve_handler_path_imports_and_instantiates() -> None:
    """声明路径可导入并实例化。"""
    handler = resolve_handler_path(f"{_Handler.__module__}:{_Handler.__qualname__}")
    assert isinstance(handler, _Handler)


def test_resolve_handler_path_rejects_bad_format() -> None:
    """非 `module:attr` 形态：抛 71006。"""
    with pytest.raises(JobHandlerNotRegisteredError):
        resolve_handler_path("no-separator")


_ = ConcurrentStableDict

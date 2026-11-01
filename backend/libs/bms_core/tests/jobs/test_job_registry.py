"""作业处理器注册表用例：路径解析 / 登记校验 / 声明对账 / 批量装载。"""

from __future__ import annotations

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import JobHandlerNotRegisteredError, JobTypeNotRegisteredError
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.registry import JobHandlerRegistry, resolve_handler_path

pytestmark = pytest.mark.kiwi_id(2382)


class _Echo(BaseJobHandler):
    """示例处理器。"""

    job_type = "demo.echo"

    async def run(self, ctx: JobContext) -> JobResult:
        """返回成功。"""
        del ctx
        return JobResult(status="succeeded")


class _Other(BaseJobHandler):
    """另一处理器（类型不同）。"""

    job_type = "demo.other"

    async def run(self, ctx: JobContext) -> JobResult:
        """返回成功。"""
        del ctx
        return JobResult(status="succeeded")


class _Third(BaseJobHandler):
    """第三个处理器（用于缺声明告警）。"""

    job_type = "demo.third"

    async def run(self, ctx: JobContext) -> JobResult:
        """返回成功。"""
        del ctx
        return JobResult(status="succeeded")


class _NotHandler:
    """非处理器替身。"""


def test_split_handler_path_rejects_bad_format() -> None:
    """路径格式：缺模块 / 缺属性 / 多冒号均拒绝。"""
    for bad in ("", "mod", ":attr", "mod:", "a:b:c"):
        with pytest.raises(JobHandlerNotRegisteredError, match="module:attr"):
            resolve_handler_path(bad)


def test_resolve_handler_path_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """路径解析：模块不可导入 / 属性缺失 / 已实例 / 不可调用 / 构造失败 / 非处理器。"""
    from bms_core.jobs import registry as registry_module

    def _raise_import(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(registry_module, "import_module", _raise_import)
    with pytest.raises(JobHandlerNotRegisteredError, match="不可导入"):
        resolve_handler_path("missing.module:attr")

    class _Module:
        instance = _Echo()
        plain = 42

    def _import(name: str) -> object:
        del name
        return _Module

    monkeypatch.setattr(registry_module, "import_module", _import)
    assert isinstance(resolve_handler_path("m:instance"), _Echo)

    with pytest.raises(JobHandlerNotRegisteredError, match="属性不存在"):
        resolve_handler_path("m:absent")
    with pytest.raises(JobHandlerNotRegisteredError, match="不可调用"):
        resolve_handler_path("m:plain")

    def _boom() -> BaseJobHandler:
        raise RuntimeError("装配失败")

    _Module.boom = _boom  # type: ignore[attr-defined]
    with pytest.raises(JobHandlerNotRegisteredError, match="无法实例化"):
        resolve_handler_path("m:boom")

    _Module.not_handler = _NotHandler  # type: ignore[attr-defined]
    with pytest.raises(JobHandlerNotRegisteredError, match="未继承 BaseJobHandler"):
        resolve_handler_path("m:not_handler")

    _Module.factory = _Echo  # type: ignore[attr-defined]
    assert isinstance(resolve_handler_path("m:factory"), _Echo)


def test_register_validations() -> None:
    """登记：空类型 / 非处理器 / 类型不一致 / 重复登记均拒绝。"""
    registry = JobHandlerRegistry()
    with pytest.raises(JobHandlerNotRegisteredError, match="不得为空"):
        registry.register("", _Echo())
    with pytest.raises(JobHandlerNotRegisteredError, match="未继承"):
        registry.register("demo.echo", _NotHandler())  # type: ignore[arg-type]
    with pytest.raises(JobHandlerNotRegisteredError, match="不一致"):
        registry.register("demo.other", _Echo())

    handler = _Echo()
    registry.register("demo.echo", handler)
    registry.register("demo.echo", handler)
    with pytest.raises(JobHandlerNotRegisteredError, match="重复登记"):
        registry.register("demo.echo", _Echo())


def test_get_has_and_snapshot() -> None:
    """取处理器：未注册报 71002；`has` / `job_types` / `handlers` 返回快照。"""
    registry = JobHandlerRegistry()
    handler = _Echo()
    registry.register("demo.echo", handler)
    assert registry.get("demo.echo") is handler
    with pytest.raises(JobTypeNotRegisteredError, match="未在本服务注册"):
        registry.get("demo.absent")
    assert registry.has("demo.echo") is True
    assert registry.has("demo.absent") is False
    assert registry.job_types() == {"demo.echo"}
    assert isinstance(registry.handlers(), ConcurrentStableDict)


def test_load_batch() -> None:
    """批量登记：逐条校验并登记。"""
    registry = JobHandlerRegistry()
    registry.load({"demo.echo": _Echo(), "demo.other": _Other()})
    assert registry.job_types() == {"demo.echo", "demo.other"}


def test_reconcile_reports_errors_and_warnings() -> None:
    """对账：声明缺代码 / 路径不符记错误，代码缺声明记告警。"""
    registry = JobHandlerRegistry()
    registry.register("demo.echo", _Echo())
    registry.register("demo.other", _Other())
    registry.register("demo.third", _Third())
    declared = {
        "demo.echo": "m:wrong_handler",
        "demo.missing": "m:handler",
        "demo.other": "",
    }
    errors, warnings = registry.reconcile(declared)
    assert any("路径与代码侧不一致" in item for item in errors)
    assert any("demo.missing" in item for item in errors)
    assert warnings == ["代码侧 handler 未在清单声明：demo.third"]


def test_from_declarations_builds_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """批量装载：按声明逐条解析并登记。"""
    from bms_core.jobs import registry as registry_module

    def _resolve(path: str) -> _Echo:
        del path
        return _Echo()

    monkeypatch.setattr(registry_module, "resolve_handler_path", _resolve)
    registry = JobHandlerRegistry.from_declarations([("demo.echo", "m:h")])
    assert registry.has("demo.echo") is True

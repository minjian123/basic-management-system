"""任务运行期契约护栏：参数解析 / 结果三态 / 上下文会话口。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TaskArgsInvalidError
from bms_core.models.platform.task import TASK_RUN_FAILED, TASK_RUN_SKIPPED, TASK_RUN_SUCCESS, TASK_TRIGGER_SCHEDULE
from bms_core.tasks.spec import TaskContext, TaskResult, TaskRunSpec, parse_task_args

pytestmark = pytest.mark.kiwi_id(2371)


def _spec() -> TaskRunSpec:
    """构造最小运行规格。

    Returns:
        TaskRunSpec: 运行规格。
    """
    return TaskRunSpec(db_key="tenant_platform_demo", task_id=1, log_id=2, run_id="run-1", code="c", handler="m:f")


def test_parse_args_none_and_blank() -> None:
    """空 / None 表示无参。"""
    assert parse_task_args(None) is None
    assert parse_task_args("") is None
    assert parse_task_args("   ") is None


def test_parse_args_object_and_array() -> None:
    """对象与数组分别解析为稳定字典 / 稳定列表。"""
    obj = parse_task_args('{"keep_days": 7}')
    assert isinstance(obj, ConcurrentStableDict)
    assert obj["keep_days"] == 7
    arr = parse_task_args("[1, 2, 3]")
    assert isinstance(arr, ConcurrentStableList)
    assert list(arr) == [1, 2, 3]


def test_parse_args_converts_nested_collections() -> None:
    """嵌套容器递归转为稳定集合类（不做浅转换）。"""
    parsed = parse_task_args('{"filters": {"codes": ["a"]}}')
    assert isinstance(parsed, ConcurrentStableDict)
    filters = parsed["filters"]
    assert isinstance(filters, ConcurrentStableDict)
    assert isinstance(filters["codes"], ConcurrentStableList)


@pytest.mark.parametrize("raw", ["{", '{"a": }', '"just-a-string"', "42", "null"])
def test_parse_args_rejects_invalid(raw: str) -> None:
    """非法 JSON / 顶层非对象非数组一律 `70004`。"""
    with pytest.raises(TaskArgsInvalidError):
        parse_task_args(raw)


def test_task_result_factories() -> None:
    """三态构造：成功带输出、失败带摘要、跳过必带归口说明。"""
    assert TaskResult.success("ok", "out").status == TASK_RUN_SUCCESS
    assert TaskResult.success("ok", "out").output == "out"
    assert TaskResult.failed("boom").status == TASK_RUN_FAILED
    assert TaskResult.failed("boom").message == "boom"
    assert TaskResult.skipped("归口 03_01").status == TASK_RUN_SKIPPED
    assert TaskResult.skipped("归口 03_01").message == "归口 03_01"


def test_run_spec_defaults() -> None:
    """规格缺省：无参、来源为定时调度。"""
    spec = _spec()
    assert spec.args_json is None
    assert spec.trigger_source == TASK_TRIGGER_SCHEDULE


def test_context_session_requires_opener() -> None:
    """未注入会话开合口即报编码错误（不当成业务失败）。"""
    ctx = TaskContext(run=_spec())
    with pytest.raises(RuntimeError):
        ctx.session()


async def test_context_session_delegates_to_opener() -> None:
    """注入开合口后按上下文取会话（执行体不自建连接）。"""
    opened: ConcurrentStableList[str] = ConcurrentStableList()

    @asynccontextmanager
    async def opener() -> AsyncGenerator[Any]:
        opened.append("enter")
        try:
            yield "session"
        finally:
            opened.append("exit")

    ctx = TaskContext(run=_spec(), args=parse_task_args('{"a": 1}'), open_session=opener)
    async with ctx.session() as session:
        assert session == "session"
    assert list(opened) == ["enter", "exit"]
    assert ctx.args is not None

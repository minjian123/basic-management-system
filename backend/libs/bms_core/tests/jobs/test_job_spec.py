"""作业规格与执行上下文用例：负载解析 / 截断 / 能力缺失防护。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import JobPayloadInvalidError
from bms_core.jobs.base import JobContext, JobResult
from bms_core.jobs.spec import dump_payload, now_utc, parse_job_payload, truncate_text

pytestmark = pytest.mark.kiwi_id(2375)


def _context(**overrides: object) -> JobContext:
    """构造最小执行上下文。"""
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"job_id": 1, "job_type": "demo.echo", "service_key": "platform", "db_key": "platform"}
    )
    fields.update(overrides)
    return JobContext(**dict(fields))  # type: ignore[arg-type]


def test_parse_payload_empty_and_invalid() -> None:
    """负载解析：空 / 纯空白返回空对象；非 JSON / 顶层非对象报 71005。"""
    assert parse_job_payload(None) == ConcurrentStableDict()
    assert parse_job_payload("   ") == ConcurrentStableDict()
    with pytest.raises(JobPayloadInvalidError, match="不是合法 JSON"):
        parse_job_payload("{bad")
    with pytest.raises(JobPayloadInvalidError, match="顶层须为 JSON 对象"):
        parse_job_payload("[1, 2]")


def test_parse_payload_normalizes_values() -> None:
    """负载解析：键转字符串、嵌套集合转插入序集合类，序列化稳定。"""
    payload = parse_job_payload('{"n": 1, "items": [{"a": 1}]}')
    assert payload["n"] == 1
    assert dump_payload(payload) == '{"items":[{"a":1}],"n":1}'


def test_truncate_text() -> None:
    """截断：None 原样返回；未超限原样；超限保留尾部省略号。"""
    assert truncate_text(None, 5) is None
    assert truncate_text("abc", 5) == "abc"
    assert truncate_text("abcdef", 5) == "abcd…"


async def test_context_requires_callbacks() -> None:
    """上下文：会话 / 进度 / 错误写入缺失时抛装配错误；取消检查缺失按未取消。"""
    context = _context()
    with pytest.raises(RuntimeError, match="open_session"):
        context.session()
    with pytest.raises(RuntimeError, match="progress_reporter"):
        await context.report_progress(1)
    with pytest.raises(RuntimeError, match="error_writer"):
        await context.add_error("bad")


async def test_context_opens_session() -> None:
    """上下文：注入会话开合口后按原样返回上下文管理器。"""

    @asynccontextmanager
    async def _open() -> AsyncGenerator[object]:
        yield object()

    async with _context(open_session=_open).session() as session:
        assert session is not None


async def test_context_calls_injected_callbacks() -> None:
    """上下文：注入后按约定转调（进度取整、取消检查透传）。"""
    progress: ConcurrentStableList[tuple[int, int | None]] = ConcurrentStableList()
    errors: ConcurrentStableList[tuple[str, int | None]] = ConcurrentStableList()

    async def report(done: int, total: int | None) -> None:
        progress.append((done, total))

    async def write(message: str, *, row_no: int | None = None, **kwargs: object) -> None:
        del kwargs
        errors.append((message, row_no))

    async def cancelled() -> bool:
        return True

    context = _context(progress_reporter=report, error_writer=write, cancel_checker=cancelled)
    await context.report_progress(1.0, 3.0)  # type: ignore[arg-type]
    await context.add_error("bad", row_no=2)
    assert progress == [(1, 3)]
    assert errors == [("bad", 2)]
    assert await context.should_cancel() is True
    assert await _context().should_cancel() is False


def test_now_utc_is_naive() -> None:
    """当前时间：UTC 且不带时区（与表列同形）。"""
    assert now_utc().tzinfo is None


def test_job_result_factories() -> None:
    """结果工厂：成功 / 失败（可重试标记）/ 取消三种终态。"""
    assert JobResult.success(message="ok").status == "succeeded"
    failed = JobResult.failed("bad", retryable=False)
    assert failed.status == "failed" and failed.retryable is False
    assert JobResult.canceled("stop").status == "canceled"

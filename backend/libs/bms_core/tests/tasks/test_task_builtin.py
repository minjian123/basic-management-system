"""内置任务护栏：清单与 cron 合法 / 未落地执行体返回 skipped + 归口说明。

孤儿分片清理已随 03_01 落地（触发型），其行为由 `test_builtin_cleanup.py` 覆盖；
审计分片预创建与审计链巡检已随 06_01 落地（触发型），行为见下方用例。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.models.platform.task import TASK_RUN_FAILED, TASK_RUN_SKIPPED, TASK_RUN_SUCCESS
from bms_core.tasks import builtin
from bms_core.tasks.builtin import (
    BUILTIN_TASK_SPECS,
    builtin_spec_of,
    run_archive_audit_logs,
    run_precreate_shard_tables,
    run_purge_soft_deleted,
    run_verify_audit_chain,
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


def test_builtin_specs_are_eight_and_cron_valid() -> None:
    """八条内置任务：代码 / 名称 / cron / handler / 归口齐备，cron 全部可解析。"""
    assert isinstance(BUILTIN_TASK_SPECS, ConcurrentStableList)
    assert [spec.code for spec in BUILTIN_TASK_SPECS] == [
        "cleanup_orphan_parts",
        "cleanup_export_artifacts",
        "cleanup_print_artifacts",
        "archive_audit_logs",
        "precreate_shard_tables",
        "verify_audit_chain",
        "purge_soft_deleted",
        "purge_deleted_tenants",
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


async def test_placeholder_runners_skip_with_owner() -> None:
    """占位执行体统一返回 skipped，且说明里写明归口任务号。"""
    cases = (
        (run_archive_audit_logs, "06_01"),
        (run_purge_soft_deleted, "13"),
    )
    for runner, owner in cases:
        result = await runner(_ctx())
        assert result.status == TASK_RUN_SKIPPED
        assert owner in result.message
        assert "占位实现" in result.message


async def test_precreate_and_verify_call_platform_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """审计分片预创建 / 链校验：成功路径读到 data；失败路径转 failed。"""
    calls: list[tuple[str, ConcurrentStableDict[str, object]]] = []  # bare-collections:allow（测试记录容器）

    async def _ok(
        *, path: str, body: ConcurrentStableDict[str, object], ctx: TaskContext, label: str
    ) -> tuple[bool, str, ConcurrentStableDict[str, object]]:
        del ctx, label
        calls.append((path, body))
        if path == builtin.AUDIT_VERIFY_PATH:
            return True, "", ConcurrentStableDict({"valid": True, "checked_records": 3})
        return True, "", ConcurrentStableDict({"months": ["202611", "202612"]})

    monkeypatch.setattr(builtin, "_post_platform", _ok)
    created = await run_precreate_shard_tables(_ctx())
    assert created.status == TASK_RUN_SUCCESS
    assert "202611" in (created.output or "")

    verified = await run_verify_audit_chain(_ctx())
    assert verified.status == TASK_RUN_SUCCESS
    assert len(calls) == 3

    async def _broken(
        *, path: str, body: ConcurrentStableDict[str, object], ctx: TaskContext, label: str
    ) -> tuple[bool, str, ConcurrentStableDict[str, object]]:
        del path, body, ctx, label
        return (
            True,
            "",
            ConcurrentStableDict(
                {"valid": False, "broken_month": "202611", "broken_index": 1, "broken_record_id": "9"}
            ),
        )

    monkeypatch.setattr(builtin, "_post_platform", _broken)
    broken = await run_verify_audit_chain(_ctx())
    assert broken.status == TASK_RUN_FAILED
    assert "202611" in broken.message

    async def _fail(
        *, path: str, body: ConcurrentStableDict[str, object], ctx: TaskContext, label: str
    ) -> tuple[bool, str, ConcurrentStableDict[str, object]]:
        del path, body, ctx, label
        return False, "下游不可用", ConcurrentStableDict[str, object]()

    monkeypatch.setattr(builtin, "_post_platform", _fail)
    assert (await run_precreate_shard_tables(_ctx())).status == TASK_RUN_FAILED
    assert (await run_verify_audit_chain(_ctx())).status == TASK_RUN_FAILED


class _Response:
    """服务调用响应替身。"""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def payload(self) -> object:
        """返回预设载荷。"""
        return self._payload


class _Client:
    """服务调用客户端替身（可抛错 / 返回预设响应）。"""

    def __init__(self, *, response: _Response | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[object] = []  # bare-collections:allow（测试记录容器）

    async def call(self, request: object) -> _Response:
        """记录请求并返回预设响应。"""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


async def test_post_platform_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务间调用：不可达 / HTTP 错误 / 非法响应 / 业务码 / 成功（data 对象或非对象）。"""
    ctx = TaskContext(
        run=TaskRunSpec(
            db_key="platform",
            task_id=1,
            log_id=1,
            run_id="r",
            code="c",
            handler="m:f",
            tenant_id=42,
        )
    )

    def _with(client: _Client) -> None:
        monkeypatch.setattr(builtin, "build_service_client", lambda: client)

    _with(_Client(error=ServiceUnavailableError("down")))
    ok, message, _ = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert (ok, "调用失败" in message) == (False, True)

    _with(_Client(response=_Response(500, None)))
    ok, message, _ = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert (ok, "HTTP 500" in message) == (False, True)

    _with(_Client(response=_Response(200, None)))
    ok, _, _ = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert ok is False

    _with(_Client(response=_Response(200, {"code": 90201, "message": "bad"})))
    ok, message, _ = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert (ok, "bad" in message) == (False, True)

    _with(_Client(response=_Response(200, {"code": 0, "data": {"a": 1}})))
    ok, _, data = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert ok is True
    assert data["a"] == 1

    _with(_Client(response=_Response(200, {"code": 0, "data": []})))
    ok, _, data = await builtin._post_platform(  # pyright: ignore[reportPrivateUsage]
        path="/api/v1/x", body=ConcurrentStableDict[str, object](), ctx=ctx, label="测试"
    )
    assert ok is True
    assert data == {}

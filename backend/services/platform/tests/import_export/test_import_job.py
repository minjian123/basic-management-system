"""导入作业用例：异步成功 / 校验拒绝 / 源文件缺失 / 取消 / 进度。"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from io import BytesIO
from typing import cast

import pytest
import pytest_asyncio
from openpyxl import Workbook
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import NotFoundError
from bms_core.db.session import DbSession
from bms_core.jobs.base import JobContext
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysAccountLock, SysUser
from bms_core.outbox.null import NullOutboxStore
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.servicecall.null import NullServiceClient
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.definition import (
    BaseImportDefinition,
    ImportDefinitionRegistry,
    ImportRowContext,
)
from bms_core.transfer.importer import ParsedRow, RowError
from bms_core.transfer.limits import ImportLimits
from bms_core.transfer.openpyxl import OpenpyxlImporter
from bms_core.transfer.source import ImportSourceStore
from bms_platform.domains.import_export.jobs import ImportExecuteJob
from bms_platform.domains.user.imports import UserImportDefinition
from bms_platform.domains.user.services.users_admin import UserAdminService
from bms_platform.imports import build_import_definitions

pytestmark = [pytest.mark.kiwi_id(2401), pytest.mark.usefixtures("serial_db_write")]

_USER_HEADERS = ["登录账号", "姓名", "邮箱", "手机号", "状态", "初始密码"]

SessionContext = Callable[[], AbstractAsyncContextManager[AsyncSession]]
JobBuilder = Callable[..., tuple[ImportExecuteJob, ConcurrentStableDict[str, object]]]
JobEnv = tuple[JobBuilder, SessionContext, "_SourceStore"]


class _Config(BaseConfigSource):
    """固定值参数源（作业侧只读角色码格式）。"""

    plugin_name = ""

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """返回空参数（回落代码默认）。

        Args:
            keys: 参数键序列。

        Returns:
            ConcurrentStableDict[str, str]: 空映射。
        """
        del keys
        return ConcurrentStableDict()


class _SourceStore(ImportSourceStore):
    """内存源文件存储（记录读写删）。"""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}  # bare-collections:allow（内存源文件存储）
        self.deleted: list[str] = []  # bare-collections:allow（内存源文件存储）

    async def put(self, key: str, data: bytes) -> None:
        """写入源文件。"""
        self.data[key] = data

    async def get(self, key: str) -> bytes:
        """读取源文件。"""
        if key not in self.data:
            raise NotFoundError(f"对象不存在：{key}")
        return self.data[key]

    async def delete(self, key: str) -> None:
        """删除源文件（幂等）。"""
        self.deleted.append(key)
        self.data.pop(key, None)


def _xlsx(rows: Sequence[Sequence[object]]) -> bytes:  # bare-collections:allow（测试数据构造）
    """构造用户导入 xlsx。"""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "数据"
    sheet.append(_USER_HEADERS)
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _policy() -> DefaultPasswordPolicy:
    """密码策略（空参数源 / 下限迭代）。"""
    return DefaultPasswordPolicy(config=_Config(), hasher=Pbkdf2PasswordHasher(iterations=100000))


def _unused(*_args: object, **_kwargs: object) -> UserAdminService:
    """未使用的写服务工厂（校验用例不写库）。"""
    raise AssertionError("不应调用写路径")


@pytest_asyncio.fixture
async def job_env(shared_tenant_engine: AsyncEngine) -> AsyncIterator[JobEnv]:
    """作业执行环境（注册表 / 会话 / 源文件）。"""
    tables: list[Table] = cast(  # bare-collections:allow（SQLAlchemy 表清单）
        "list[Table]",
        [
            SysUser.__table__,
            SysRole.__table__,
            SysUserRole.__table__,
            SysAccountLock.__table__,
        ],
    )
    await ensure_tables(shared_tenant_engine, tables)
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    config = _Config()
    hasher = Pbkdf2PasswordHasher(iterations=100000)
    policy = DefaultPasswordPolicy(config=config, hasher=hasher)
    registry = build_import_definitions(
        hasher=hasher,
        policy=policy,
        outbox=NullOutboxStore(),
        service_client=NullServiceClient(),
        audit=None,
        config=config,
    )
    source = _SourceStore()

    @asynccontextmanager
    async def session_context() -> AsyncGenerator[AsyncSession]:
        async with factory() as session, session.begin():
            yield session

    def make_job(
        *,
        batch_size: int = 200,
        cancel: bool = False,
        definitions: ImportDefinitionRegistry | None = None,
        source_store: ImportSourceStore | None = None,
    ) -> tuple[ImportExecuteJob, ConcurrentStableDict[str, object]]:
        captured: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "progress": [],
                "errors": [],
            }
        )

        def definitions_factory(**_: object) -> ImportDefinitionRegistry:
            return definitions if definitions is not None else registry

        async def report(done: int, total: int | None) -> None:
            cast("list[tuple[int, int | None]]", captured["progress"]).append((done, total))

        async def add_error(
            message: str,
            *,
            row_no: int | None = None,
            column_key: str | None = None,
            item_ref: str | None = None,
        ) -> None:
            cast("list[tuple[str, int | None, str | None]]", captured["errors"]).append(
                (message, row_no, column_key or item_ref)
            )

        async def should_cancel() -> bool:
            return cancel

        captured["report"] = report
        captured["add_error"] = add_error
        captured["should_cancel"] = should_cancel
        job = ImportExecuteJob(
            definitions_factory=definitions_factory,
            importer=OpenpyxlImporter(),
            source_store=source_store if source_store is not None else source,
            config=config,
            limits=ImportLimits(batch_size=batch_size),
        )
        return job, captured

    yield make_job, session_context, source


def _context(
    captured: ConcurrentStableDict[str, object],
    session_context: SessionContext,
    payload: ConcurrentStableDict[str, object],
) -> JobContext:
    """按捕获回调构造作业上下文。"""
    return JobContext(
        job_id=1,
        job_type=ImportExecuteJob.job_type,
        service_key="platform",
        db_key="tenant_demo",
        payload=payload,
        tenant_id=1001,
        open_session=cast("Callable[[], AbstractAsyncContextManager[DbSession]]", session_context),
        progress_reporter=cast("object", captured["report"]),  # type: ignore[arg-type]
        error_writer=cast("object", captured["add_error"]),  # type: ignore[arg-type]
        cancel_checker=cast("object", captured["should_cancel"]),  # type: ignore[arg-type]
    )


def _payload(key: str) -> ConcurrentStableDict[str, object]:
    """构造作业负载。"""
    return ConcurrentStableDict[str, object](
        {
            "biz": "users",
            "source_key": key,
            "actor": 1001,
            "tenant_code": "demo",
            "report_token": "token",
        }
    )


async def test_job_success_and_progress(job_env: JobEnv) -> None:
    """合法行异步执行成功；进度上报；源文件删除。"""
    make_job, session_context, source = job_env
    key = "demo/imports/source/job-ok.xlsx"
    source.data[key] = _xlsx([["jobzhangsan", "张三", "", "", "启用", ""]])
    job, captured = make_job()
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "succeeded"
    assert result.output is not None
    assert result.output["committed"] is True
    assert cast("list[tuple[int, int | None]]", captured["progress"]) == [(1, 1)]
    assert source.deleted == [key]


async def test_job_validation_rejected(job_env: JobEnv) -> None:
    """任一行非法 → failed、不可重试、错误明细逐行写入。"""
    make_job, session_context, source = job_env
    key = "demo/imports/source/job-bad.xlsx"
    source.data[key] = _xlsx([["", "张三", "", "", "启用", ""]])
    job, captured = make_job()
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "failed"
    assert result.retryable is False
    assert result.output is not None
    assert result.output["committed"] is False
    assert result.output["fail_count"] == 1
    errors = cast("list[tuple[str, int | None, str | None]]", captured["errors"])
    assert errors and errors[0][1] == 2
    assert source.deleted == [key]


async def test_job_source_missing(job_env: JobEnv) -> None:
    """源文件缺失 → failed、不可重试。"""
    make_job, session_context, _source = job_env
    job, captured = make_job()
    result = await job.run(_context(captured, session_context, _payload("demo/imports/source/missing.xlsx")))
    assert result.status == "failed"
    assert result.retryable is False


async def test_job_canceled(job_env: JobEnv) -> None:
    """批次边界检查取消 → canceled，整批回滚。"""
    make_job, session_context, source = job_env
    key = "demo/imports/source/job-cancel.xlsx"
    source.data[key] = _xlsx([["jobcanceluser", "李四", "", "", "启用", ""]])
    job, captured = make_job(batch_size=1, cancel=True)
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "canceled"
    assert source.deleted == [key]


async def test_user_definition_columns_and_validation(shared_tenant_engine: AsyncEngine) -> None:
    """用户定义列集固定；状态非法 / 密码策略 / 文件内重复逐项报错。"""
    data = _xlsx(
        [
            ["u1", "甲", "", "", "非法状态", "123"],
            ["u1", "乙", "", "", "启用", ""],
        ]
    )
    definition = UserImportDefinition(service_factory=_unused, policy=_policy())
    rows = await OpenpyxlImporter().parse_rows(data, columns=definition.columns)
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        preload = await definition.preload(session, rows)
        first = await definition.validate_row(rows[0], preload, config=None)
        second = await definition.validate_row(rows[1], preload, config=None)
    fields = {error.field for error in first}
    assert "status" in fields
    assert "password" in fields
    assert {error.field for error in second} == {"username"}


async def test_job_progress_each_batch(job_env: JobEnv) -> None:
    """批次边界上报进度（非仅最终一次）。"""
    make_job, session_context, source = job_env
    key = "demo/imports/source/job-progress.xlsx"
    source.data[key] = _xlsx([["progress1", "甲", "", "", "启用", ""], ["progress2", "乙", "", "", "启用", ""]])
    job, captured = make_job(batch_size=1)
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "succeeded"
    assert cast("list[tuple[int, int | None]]", captured["progress"]) == [(1, 2), (2, 2), (2, 2)]


class _FailDefinition(BaseImportDefinition):
    """写路径恒失败的测试定义。"""

    biz = "users"
    title = "失败"

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        return ConcurrentStableFrozenList(
            (
                ColumnSpec(key="username", title="登录账号"),
                ColumnSpec(key="name", title="姓名"),
                ColumnSpec(key="email", title="邮箱"),
                ColumnSpec(key="phone", title="手机号"),
                ColumnSpec(key="status", title="状态"),
                ColumnSpec(key="password", title="初始密码"),
            )
        )

    async def validate_row(
        self, row: ParsedRow, preloaded: object, *, config: BaseConfigSource | None
    ) -> ConcurrentStableFrozenList[RowError]:
        del row, preloaded, config
        return ConcurrentStableFrozenList()

    async def write_row(self, row: ParsedRow, ctx: ImportRowContext) -> None:
        del row, ctx
        raise RuntimeError("db down")


async def test_job_write_failure(job_env: JobEnv) -> None:
    """写入失败 → failed、不可重试、整批 blocked、批次级错误。"""
    make_job, session_context, source = job_env
    registry = ImportDefinitionRegistry()
    registry.register(_FailDefinition())
    key = "demo/imports/source/job-write-fail.xlsx"
    source.data[key] = _xlsx([["failuser", "甲", "", "", "启用", ""]])
    job, captured = make_job(definitions=registry)
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "failed"
    assert result.retryable is False
    assert result.output is not None
    assert result.output["blocked_count"] == 1
    assert cast("list[tuple[str, int | None, str | None]]", captured["errors"])[0][0].startswith("整批写入失败")


async def test_job_source_delete_failure_does_not_break(job_env: JobEnv) -> None:
    """源文件删除失败只 warning，终态仍成功。"""
    make_job, session_context, _source = job_env
    source = _DeleteFailStore()
    key = "demo/imports/source/job-delete-fail.xlsx"
    source.data[key] = _xlsx([["deletefail", "甲", "", "", "启用", ""]])
    job, captured = make_job(source_store=source)
    result = await job.run(_context(captured, session_context, _payload(key)))
    assert result.status == "succeeded"


class _DeleteFailStore(_SourceStore):
    """删除恒失败的源文件存储。"""

    async def delete(self, key: str) -> None:
        raise RuntimeError("storage down")


def test_config_source_branches() -> None:
    """无服务客户端回落占位；有客户端走 HTTP 取数。"""
    from bms_core.config.http import HttpConfigSource
    from bms_core.config.null import NullConfigSource
    from bms_core.core.config import get_settings
    from bms_platform.domains.import_export.jobs import _config_source  # pyright: ignore[reportPrivateUsage]

    settings = get_settings()
    assert isinstance(_config_source(settings, NullServiceClient()), NullConfigSource)  # pyright: ignore[reportPrivateUsage]
    assert isinstance(_config_source(settings, _DummyClient()), HttpConfigSource)  # pyright: ignore[reportPrivateUsage]


class _DummyClient(BaseServiceClient):
    """非空服务客户端替身。"""

    plugin_name = ""

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        del request
        return ServiceResponse(status_code=200)


def test_idem_scope_and_payload_edges() -> None:
    """幂等作用域超长哈希；负载空 / 非法 / 非对象均回落空映射。"""
    from bms_platform.domains.import_export.services.imports import (  # pyright: ignore[reportPrivateUsage]
        _idem_scope,  # pyright: ignore[reportPrivateUsage]
        _parse_payload,  # pyright: ignore[reportPrivateUsage]
    )

    assert _idem_scope("users", "abc") == "users:abc"  # pyright: ignore[reportPrivateUsage]
    assert len(_idem_scope("users", "x" * 200)) == 64  # pyright: ignore[reportPrivateUsage]
    assert not _parse_payload(None)  # pyright: ignore[reportPrivateUsage]
    assert not _parse_payload("not-json")  # pyright: ignore[reportPrivateUsage]
    assert not _parse_payload("[]")  # pyright: ignore[reportPrivateUsage]
    assert _parse_payload('{"biz": "users"}')["biz"] == "users"  # pyright: ignore[reportPrivateUsage]


def test_summary_from_record_terminal_and_running() -> None:
    """作业终态汇总解析；未终态返回零值。"""
    from bms_core.models.job import SysJob
    from bms_platform.domains.import_export.services.imports import _summary_from_record  # pyright: ignore[reportPrivateUsage]

    base = {
        "job_type": "platform.import.execute",
        "service_key": "platform",
        "domain_key": "import_export",
        "payload": "{}",
    }
    running = SysJob(**base, status="running")
    summary = _summary_from_record(running, ConcurrentStableDict[str, object]({"total": 3}), 0)  # pyright: ignore[reportPrivateUsage]
    assert summary.total == 3
    assert summary.committed is False

    failed = SysJob(
        **base,
        status="failed",
        result='{"total": 2, "success_count": 0, "fail_count": 1, "blocked_count": 1}',
    )
    summary = _summary_from_record(  # pyright: ignore[reportPrivateUsage]
        failed,
        ConcurrentStableDict[str, object]({"total": 2, "success_count": 0, "fail_count": 1, "blocked_count": 1}),
        1,
    )
    assert summary.fail_count == 1
    assert summary.blocked_count == 1


async def test_safe_helpers_swallow_failures() -> None:
    """源文件删除 / 幂等释放失败不抛错（只 warning）。"""
    from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore
    from bms_platform.domains.import_export.services.imports import (  # pyright: ignore[reportPrivateUsage]
        _safe_delete,  # pyright: ignore[reportPrivateUsage]
        _safe_release,  # pyright: ignore[reportPrivateUsage]
    )

    class _ReleaseFail(IdempotencyStore):
        plugin_name = ""

        async def begin(self, key: str, *, ttl: int = 86400) -> bool:
            del key, ttl
            return True

        async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
            del key
            return None

        async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = 86400) -> None:
            del key, payload, ttl

        async def release(self, key: str) -> None:
            del key
            raise RuntimeError("redis down")

    await _safe_delete(_DeleteFailStore(), "k")  # pyright: ignore[reportPrivateUsage]
    await _safe_release(_ReleaseFail(), "k")  # pyright: ignore[reportPrivateUsage]


def test_parse_job_result_edges() -> None:
    """`sys_job.result` 空 / 非法 / 非对象回落空；合法对象正常解析。"""
    from bms_platform.domains.import_export.services.report import parse_job_result

    assert not parse_job_result(None)
    assert not parse_job_result("not-json")
    assert not parse_job_result("[]")
    assert parse_job_result('{"total": 1}')["total"] == 1

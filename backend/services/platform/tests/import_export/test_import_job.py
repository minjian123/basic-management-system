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
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import NotFoundError
from bms_core.db.session import DbSession
from bms_core.jobs.base import JobContext
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysAccountLock, SysUser
from bms_core.outbox.null import NullOutboxStore
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.servicecall.null import NullServiceClient
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.definition import ImportDefinitionRegistry
from bms_core.transfer.limits import ImportLimits
from bms_core.transfer.openpyxl import OpenpyxlImporter
from bms_core.transfer.source import ImportSourceStore
from bms_platform.domains.import_export.jobs import ImportExecuteJob
from bms_platform.domains.user.imports import UserImportDefinition
from bms_platform.domains.user.services.users_admin import UserAdminService
from bms_platform.imports import build_import_definitions

pytestmark = pytest.mark.kiwi_id(2401)

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

    def definitions_factory(**_: object) -> ImportDefinitionRegistry:
        return registry

    def make_job(  # bare-collections:allow（测试捕获容器）
        *, batch_size: int = 200, cancel: bool = False
    ) -> tuple[ImportExecuteJob, ConcurrentStableDict[str, object]]:
        captured: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "progress": [],
                "errors": [],
            }
        )

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
            source_store=source,
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

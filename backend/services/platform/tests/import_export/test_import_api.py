"""导入 API 用例：模板 / 同步执行 / 全量原子 / 幂等 / 状态 / 错误明细 / 文件安全。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.api.deps import (
    get_audit_capturer,
    get_cache_region,
    get_config_source,
    get_idempotency_store,
    get_importer,
    get_object_storage,
    get_outbox_store,
    get_password_hasher,
    get_password_policy,
    get_permission_checker,
    get_rate_limiter,
    get_service_client,
    get_uow,
)
from bms_core.audit.null import NullAuditCapturer
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.session import DbUnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore
from bms_core.idempotency.redis import RedisIdempotencyStore
from bms_core.models.job import JOB_STATUS_FAILED, JOB_STATUS_QUEUED, SysJob, SysJobError
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysAccountLock, SysUser
from bms_core.outbox.null import NullOutboxStore
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.local import LocalObjectStorage
from bms_core.testing.fixtures import clear_tenant_cache
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.openpyxl import OpenpyxlImporter
from bms_platform.domains.import_export.services.report import report_key, token_payload
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers
from tests_support.permission_admin import setup_min_tenant

pytestmark = [pytest.mark.kiwi_id(2401), pytest.mark.usefixtures("serial_db_write")]

API = "/api/v1/imports"
_USER_HEADERS = ["登录账号", "姓名", "邮箱", "手机号", "状态", "初始密码"]
_ROLE_HEADERS = ["角色码", "角色名称", "状态"]


class _Config(BaseConfigSource):
    """固定值参数源。"""

    plugin_name = ""

    def __init__(self, values: ConcurrentStableDict[str, str] | None = None) -> None:
        self._values = values or ConcurrentStableDict()

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})


class _DenyUserCreate(BasePermissionChecker):
    """仅拒绝 `user:create`（验证业务写权限二次校验）。"""

    plugin_name = ""

    def check(self, code: str) -> bool:
        return code != "user:create"


def _xlsx(  # bare-collections:allow
    headers: Sequence[str], rows: Sequence[Sequence[object]], *, sheet_name: str = "数据"
) -> bytes:
    """构造测试 xlsx。"""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = sheet_name
    sheet.append(list(headers))
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _data(response: object) -> ConcurrentStableDict[str, object]:
    """取统一响应 data。"""
    payload = cast("ConcurrentStableDict[str, object]", response.json())  # type: ignore[attr-defined]
    assert payload["code"] == 0, payload
    return cast("ConcurrentStableDict[str, object]", payload["data"])


def _code(response: object) -> int:
    """取业务码。"""
    payload = cast("ConcurrentStableDict[str, object]", response.json())  # type: ignore[attr-defined]
    return int(cast("int", payload["code"]))


@dataclass
class _ApiEnv:
    """导入 API 测试环境。"""

    client: AsyncClient
    app: FastAPI
    config: _Config
    limiter: MemoryRateLimiter
    redis: FakeRedis
    cache: MemoryCacheRegion
    factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def api_env(
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_ApiEnv]:
    """带依赖替身的导入 API 环境（自建应用，确保租户库环境在装配前生效）。"""
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    # 作业侧按 `[storage].options.root` 解析对象存储；与 API 依赖覆盖指向同一目录，避免 inline 作业读不到源文件
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    await ensure_tables(
        shared_tenant_engine,
        cast(
            "list[Table]",
            [
                SysUser.__table__,
                SysRole.__table__,
                SysUserRole.__table__,
                SysAccountLock.__table__,
                SysJob.__table__,
                SysJobError.__table__,
            ],
        ),
    )
    await setup_min_tenant(shared_tenant_db_url)
    get_settings.cache_clear()

    service_app = ApplicationFactory().create(None)
    clear_tenant_cache(service_app)
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    hasher = Pbkdf2PasswordHasher(iterations=100000)
    config = _Config()
    policy = DefaultPasswordPolicy(config=config, hasher=hasher)
    redis = FakeRedis(decode_responses=True)
    idempotency = RedisIdempotencyStore("redis://localhost:6379/0", client=redis)
    cache = MemoryCacheRegion(domain="cache")
    limiter = MemoryRateLimiter()

    async def _uow() -> AsyncIterator[DbUnitOfWork]:
        async with factory() as session:
            yield DbUnitOfWork(session)

    service_app.dependency_overrides[get_uow] = _uow
    service_app.dependency_overrides[get_importer] = OpenpyxlImporter
    service_app.dependency_overrides[get_object_storage] = lambda: LocalObjectStorage(root=tmp_path / "storage")
    service_app.dependency_overrides[get_idempotency_store] = lambda: idempotency
    service_app.dependency_overrides[get_config_source] = lambda: config
    service_app.dependency_overrides[get_cache_region] = lambda: cache
    service_app.dependency_overrides[get_permission_checker] = NullPermissionChecker
    service_app.dependency_overrides[get_audit_capturer] = NullAuditCapturer
    service_app.dependency_overrides[get_outbox_store] = NullOutboxStore
    service_app.dependency_overrides[get_password_hasher] = lambda: hasher
    service_app.dependency_overrides[get_password_policy] = lambda: policy
    service_app.dependency_overrides[get_service_client] = NullServiceClient
    service_app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        async with (
            service_app.router.lifespan_context(service_app),
            AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client,
        ):
            client.headers.update(auth_headers())
            yield _ApiEnv(
                client=client,
                app=service_app,
                config=config,
                limiter=limiter,
                redis=redis,
                cache=cache,
                factory=factory,
            )
    finally:
        service_app.dependency_overrides.clear()
        clear_tenant_cache(service_app)


@pytest_asyncio.fixture
async def api(api_env: _ApiEnv) -> AsyncClient:
    """导入 API 客户端（多数用例只需 client）。"""
    return api_env.client


async def test_template_users_and_roles(api: AsyncClient) -> None:
    """模板可下载，列头与定义一致。"""
    for biz, headers in (("users", _USER_HEADERS), ("roles", _ROLE_HEADERS)):
        response = await api.get(f"{API}/{biz}/template")
        assert response.status_code == 200
        assert response.content[:2] == b"PK", (response.headers.get("content-type"), response.content[:200])
        workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
        try:
            rows = list(workbook["数据"].iter_rows(values_only=True))
        finally:
            workbook.close()
        assert rows == [tuple(headers)]


async def test_execute_users_success_and_idempotent(api: AsyncClient) -> None:
    """合法用户导入落库；同幂等键重复返回首次结果。"""
    data = _xlsx(
        _USER_HEADERS,
        [["zhangsan", "张三", "zhangsan@example.com", "13800000000", "启用", "Abcd1234!x"]],
    )
    headers = {"Idempotency-Key": "users-ok-1"}
    response = await api.post(f"{API}/users/execute", files={"file": ("users.xlsx", data)}, headers=headers)
    assert response.status_code == 200
    payload = _data(response)
    assert payload["committed"] is True
    assert payload["success_count"] == 1
    assert payload["fail_count"] == 0
    assert payload["duplicate"] is False

    again = await api.post(f"{API}/users/execute", files={"file": ("users.xlsx", data)}, headers=headers)
    replay = _data(again)
    assert replay["duplicate"] is True
    assert replay["success_count"] == 1


async def test_execute_users_invalid_is_atomic(api: AsyncClient) -> None:
    """任一行非法 → 整批不落库；返回 committed / blocked_count。"""
    data = _xlsx(
        _USER_HEADERS,
        [
            ["lisi", "李四", "bad-email", "", "启用", ""],
            ["wangwu", "王五", "", "", "启用", ""],
        ],
    )
    response = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "users-bad-1"},
    )
    assert response.status_code == 200
    payload = _data(response)
    assert payload["committed"] is False
    assert payload["success_count"] == 0
    assert payload["fail_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["report_token"]


async def test_execute_roles_success(api: AsyncClient) -> None:
    """合法角色导入落库（恒 custom）。"""
    data = _xlsx(_ROLE_HEADERS, [["sales_manager", "销售经理", "启用"]])
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": "roles-ok-1"},
    )
    payload = _data(response)
    assert payload["committed"] is True
    assert payload["success_count"] == 1


async def test_error_report_download(api: AsyncClient) -> None:
    """错误明细 token 可下载 xlsx。"""
    data = _xlsx(_USER_HEADERS, [["", "张三", "", "", "启用", ""]])
    response = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "users-report-1"},
    )
    token = cast("str", _data(response)["report_token"])
    report = await api.get(f"{API}/users/error-report/{token}")
    assert report.status_code == 200, (_data(response), token, report.json())
    workbook = load_workbook(BytesIO(report.content), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        assert sheet is not None
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    assert rows[0] == ("行号", "列", "原因")
    assert rows[1][0] == 2


async def test_missing_idempotency_and_unknown_biz(api: AsyncClient) -> None:
    """缺幂等键 50305；未知业务 50307。"""
    data = _xlsx(_USER_HEADERS, [["zhaoliu", "赵六", "", "", "启用", ""]])
    missing = await api.post(f"{API}/users/execute", files={"file": ("users.xlsx", data)})
    assert _code(missing) == 50305
    unknown = await api.get(f"{API}/unknown/template")
    assert _code(unknown) == 50307


async def test_file_safety(api: AsyncClient) -> None:
    """非 xlsx → 文件级错误。"""
    bad = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.txt", b"not xlsx")},
        headers={"Idempotency-Key": "bad-file-1"},
    )
    assert _code(bad) == 50302


async def test_roles_invalid_is_atomic(api: AsyncClient) -> None:
    """角色码格式非法 / 文件内重复 → 整批不落库。"""
    data = _xlsx(
        _ROLE_HEADERS,
        [["Bad-Code", "非法", "启用"], ["dup_role", "重复一", "启用"], ["dup_role", "重复二", "启用"]],
    )
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": "roles-bad-1"},
    )
    payload = _data(response)
    assert payload["committed"] is False
    assert payload["success_count"] == 0
    assert payload["fail_count"] == 3
    assert payload["report_token"]


async def test_template_mismatch_and_row_limit(api_env: _ApiEnv) -> None:
    """表头不匹配 50301；行数超限 50304。"""
    api = api_env.client
    bad = _xlsx(["姓名"], [["张三"]])
    mismatch = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", bad)},
        headers={"Idempotency-Key": "mismatch-1"},
    )
    assert _code(mismatch) == 50301

    api_env.app.dependency_overrides[get_config_source] = lambda: _Config(
        ConcurrentStableDict({"import.upload.max_rows": "1"})
    )
    data = _xlsx(
        _USER_HEADERS,
        [["limit1", "甲", "", "", "启用", ""], ["limit2", "乙", "", "", "启用", ""]],
    )
    limited = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "limit-1"},
    )
    assert _code(limited) == 50304


async def test_file_extension_and_size(api_env: _ApiEnv) -> None:
    """非 .xlsx 扩展名 50302；超过大小上限 50303。"""
    api = api_env.client
    good = _xlsx(_USER_HEADERS, [["ext1", "甲", "", "", "启用", ""]])
    wrong_ext = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xls", good)},
        headers={"Idempotency-Key": "ext-1"},
    )
    assert _code(wrong_ext) == 50302

    api_env.app.dependency_overrides[get_config_source] = lambda: _Config(
        ConcurrentStableDict({"import.upload.max_size": "10"})
    )
    too_large = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", good)},
        headers={"Idempotency-Key": "size-1"},
    )
    assert _code(too_large) == 50303


async def test_async_submit_and_status(api_env: _ApiEnv) -> None:
    """行数超同步阈值 → 异步提交；状态可查；跨业务取作业 50307；错误明细未生成 50306。"""
    api_env.app.dependency_overrides[get_config_source] = lambda: _Config(
        ConcurrentStableDict({"import.sync_max_rows": "1"})
    )
    data = _xlsx(
        _USER_HEADERS,
        [["async1", "甲", "", "", "启用", ""], ["async2", "乙", "", "", "启用", ""]],
    )
    response = await api_env.client.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "async-1"},
    )
    payload = _data(response)
    assert payload["async"] is True
    assert payload["committed"] is False
    job_id = cast("str", payload["job_id"])
    status = await api_env.client.get(f"{API}/users/jobs/{job_id}")
    status_data = _data(status)
    assert status_data["status"] in {"queued", "running"}
    cross = await api_env.client.get(f"{API}/roles/jobs/{job_id}")
    assert _code(cross) == 50307
    missing = await api_env.client.get(f"{API}/users/error-report/not-a-token")
    assert _code(missing) == 50306


async def test_rate_limit(api_env: _ApiEnv) -> None:
    """用户维度限流：第 2 次请求 10005。"""
    api_env.app.dependency_overrides[get_config_source] = lambda: _Config(
        ConcurrentStableDict({"import.rate_limit.limit": "1", "import.rate_limit.window": "60"})
    )
    first = await api_env.client.get(f"{API}/users/template")
    assert first.status_code == 200
    second = await api_env.client.get(f"{API}/users/template")
    assert _code(second) == 10005


async def test_business_write_permission(api_env: _ApiEnv) -> None:
    """持入口权限但缺业务写权限 → 30001。"""
    api_env.app.dependency_overrides[get_permission_checker] = _DenyUserCreate
    data = _xlsx(_USER_HEADERS, [["perm1", "甲", "", "", "启用", ""]])
    response = await api_env.client.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "perm-1"},
    )
    assert _code(response) == 30001


class _ConflictIdempotencyStore(IdempotencyStore):
    """幂等键已被占用且无首次结果（处理中）。"""

    plugin_name = ""

    async def begin(self, key: str, *, ttl: int = 86400) -> bool:
        del key, ttl
        return False

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        del key
        return None

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int = 86400) -> None:
        del key, payload, ttl

    async def release(self, key: str) -> None:
        del key


class _BrokenReleaseStore(_ConflictIdempotencyStore):
    """begin 成功但 release 抛错（验证不覆盖原始异常）。"""

    async def begin(self, key: str, *, ttl: int = 86400) -> bool:
        del key, ttl
        return True

    async def release(self, key: str) -> None:
        del key
        raise RuntimeError("redis down")


async def test_invalid_xlsx_and_missing_job(api_env: _ApiEnv) -> None:
    """扩展名合法但内容非 xlsx → 50302；作业不存在 → 50307。"""
    bad = await api_env.client.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", b"not-a-zip")},
        headers={"Idempotency-Key": "bad-zip-1"},
    )
    assert _code(bad) == 50302

    missing = await api_env.client.get(f"{API}/users/jobs/999999999")
    assert _code(missing) == 50307


async def test_idempotency_conflict_and_release_failure(api_env: _ApiEnv) -> None:
    """处理中返回 10003；内部失败释放异常不覆盖原始错误。"""
    api_env.app.dependency_overrides[get_idempotency_store] = _ConflictIdempotencyStore
    data = _xlsx(_USER_HEADERS, [["conflict1", "甲", "", "", "启用", ""]])
    conflict = await api_env.client.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": "conflict-1"},
    )
    assert _code(conflict) == 10003

    api_env.app.dependency_overrides[get_idempotency_store] = _BrokenReleaseStore
    bad = await api_env.client.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", b"not-a-zip")},
        headers={"Idempotency-Key": "release-1"},
    )
    assert _code(bad) == 50302


async def test_error_report_branches(api_env: _ApiEnv) -> None:
    """错误明细：业务不符 / 作业缺失 / 未终态 / 无错误 四类 404/409。"""
    cache = api_env.cache
    await cache.aset(report_key(cache, "demo", "wrong-biz"), token_payload(1, "roles"))
    wrong_biz = await api_env.client.get(f"{API}/users/error-report/wrong-biz")
    assert _code(wrong_biz) == 50306

    await cache.aset(report_key(cache, "demo", "missing-job"), token_payload(999999999, "users"))
    missing_job = await api_env.client.get(f"{API}/users/error-report/missing-job")
    assert _code(missing_job) == 50306

    async with api_env.factory() as session:
        queued = SysJob(
            job_type="platform.import.execute",
            service_key="platform",
            domain_key="import_export",
            payload='{"biz": "users"}',
            status=JOB_STATUS_QUEUED,
        )
        session.add(queued)
        await session.commit()
        queued_id = int(queued.id)
    await cache.aset(report_key(cache, "demo", "not-ready"), token_payload(queued_id, "users"))
    not_ready = await api_env.client.get(f"{API}/users/error-report/not-ready")
    assert _code(not_ready) == 50308

    async with api_env.factory() as session:
        failed = SysJob(
            job_type="platform.import.execute",
            service_key="platform",
            domain_key="import_export",
            payload='{"biz": "users"}',
            status=JOB_STATUS_FAILED,
        )
        session.add(failed)
        await session.commit()
        failed_id = int(failed.id)
    await cache.aset(report_key(cache, "demo", "no-errors"), token_payload(failed_id, "users"))
    no_errors = await api_env.client.get(f"{API}/users/error-report/no-errors")
    assert _code(no_errors) == 50306


async def test_status_malformed_payload_and_terminal_summary(api_env: _ApiEnv) -> None:
    """状态端点：坏负载 50307；终态汇总从 result 解析。"""
    async with api_env.factory() as session:
        bad = SysJob(
            job_type="platform.import.execute",
            service_key="platform",
            domain_key="import_export",
            payload="[]",
            status=JOB_STATUS_QUEUED,
        )
        good = SysJob(
            job_type="platform.import.execute",
            service_key="platform",
            domain_key="import_export",
            payload='{"biz": "users"}',
            status="succeeded",
            result='{"total": 2, "success_count": 2, "fail_count": 0, "blocked_count": 0, "committed": true}',
        )
        session.add_all([bad, good])
        await session.commit()
        bad_id = int(bad.id)
        good_id = int(good.id)
    malformed = await api_env.client.get(f"{API}/users/jobs/{bad_id}")
    assert _code(malformed) == 50307
    status = _data(await api_env.client.get(f"{API}/users/jobs/{good_id}"))
    assert status["committed"] is True
    assert status["success_count"] == 2
    assert status["fail_count"] == 0

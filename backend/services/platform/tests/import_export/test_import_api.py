"""导入 API：模板 / 同步执行 / 全量原子 / 幂等 / 状态 / 错误明细 / 文件安全（Kiwi 2401 / 2551-2553）。

重写口径（13_11）：

- **自建应用壳是必要例外**：本文件要换 `idempotency` / `config_source` / `outbox` 等实现并指定存储根，
  装配态应用做不到；壳用完经 `restore_registry_for` 把插件注册表归还装配态应用。
- **不再写系统管理员豁免**（`setup_min_tenant`）：默认主体只授 `import:execute` + 两个业务写权限码
  （自定义角色、非豁免层级），业务写权限分支另用专用主体验证。
- 断言只针对本用例命名空间数据（账号 / 角色码带 `ns` 前缀）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import Table
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.cache.base import CacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.plugin import resolve_plugin
from bms_core.db.session import DbSession
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE, IdempotencyStore, build_idempotency_key
from bms_core.jobs.base import JobResult
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission
from bms_core.models.job import JOB_STATUS_FAILED, JOB_STATUS_QUEUED, SysJob, SysJobError
from bms_core.models.platform.role import SysRole, SysUserRole
from bms_core.models.platform.user import SysAccountLock, SysUser
from bms_core.testing.fixtures import clear_tenant_cache
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_platform.domains.import_export.services import imports as import_flow
from bms_platform.domains.import_export.services.report import report_key, token_payload
from bms_platform.main import ApplicationFactory
from tests_support.auth import TEST_TENANT_ID, auth_headers
from tests_support.config_values import temporary_config_values
from tests_support.permission_grants import IMPORT_EXECUTE, grant_permissions, reset_permission_state
from tests_support.plugin_registry import restore_registry_for

pytestmark = pytest.mark.kiwi_id(2401)

API = "/api/v1/imports"

_DEFAULT_SUBJECT = 1001

_DEFAULT_PERMISSIONS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (IMPORT_EXECUTE, "user:create", "role:create")
)
"""默认主体所需权限：入口 + 两条导入的业务写权限码。"""

_DEFAULT_ROLE_CODE = "__test_import_default"

_NO_WRITE_SUBJECT = "900103"
"""只持「导入执行」入口权限、不持「创建用户」权限的主体。"""

_NO_WRITE_ROLE_CODE = "__test_import_no_write"
_USER_HEADERS = ["登录账号", "姓名", "邮箱", "手机号", "状态", "初始密码"]
_ROLE_HEADERS = ["角色码", "角色名称", "状态"]


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
    """导入 API 测试环境（自建壳，只读已装配系统的租户库引擎）。"""

    client: AsyncClient
    app: FastAPI
    engine: AsyncEngine
    cache: CacheRegion
    factory: async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def api_env(
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service_app: FastAPI,
) -> AsyncIterator[_ApiEnv]:
    """导入 API 环境：自建壳换实现（收尾归还插件注册表），只给专用主体授真实权限码。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        shared_tenant_db_url: 共享租户库连接串。
        tmp_path: 临时目录（存储根）。
        monkeypatch: 补丁夹具。
        service_app: 装配态应用（收尾归还注册表用）。

    Yields:
        _ApiEnv: 测试环境。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    # 作业侧按 `[storage].options.root` 解析对象存储；与 API 取同一实现与目录
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("BMS_CACHE__PROVIDER", "memory")
    # 幂等去重走真实实现（共享客户端已由测试基座替换为 fakeredis）
    monkeypatch.setenv("BMS_IDEMPOTENCY__PROVIDER", "redis")
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "memory")
    # 导入用例无跨服务调用、无 outbox 投递：显式选占位实现，避免写路线程与外部依赖
    monkeypatch.setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    monkeypatch.setenv("BMS_OUTBOX_STORE__PROVIDER", "")
    # 参数按真实运行取租户库 `sys_config`；缓存域选占位，写入后立即生效（用例改后恢复原值）
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "")
    # 权限走真实 RBAC：业务写权限用例按真实授权数据断言
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "rbac")
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
                SysConfig.__table__,
            ],
        ),
    )
    get_settings.cache_clear()

    created = ApplicationFactory().create(None)
    clear_tenant_cache(created)
    settings = get_settings()
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    cache = cast("CacheRegion", resolve_plugin("cache", settings.cache.provider))

    try:
        async with (
            created.router.lifespan_context(created),
            AsyncClient(transport=ASGITransport(app=created), base_url="http://test") as client,
        ):
            client.headers.update(auth_headers())
            # 授权：默认主体打卡口 + 两条业务写权限；另备「只持入口」主体验证业务写拒绝
            await grant_permissions(
                _DEFAULT_SUBJECT,
                ConcurrentStableList(_DEFAULT_PERMISSIONS),
                role_code=_DEFAULT_ROLE_CODE,
            )
            await reset_permission_state(created)
            yield _ApiEnv(
                client=client,
                app=created,
                engine=shared_tenant_engine,
                cache=cache,
                factory=factory,
            )
    finally:
        clear_tenant_cache(created)
        # 自建壳把进程级注册表换代到壳：收尾归还装配态应用，避免后继用例解析到壳的工厂
        restore_registry_for(service_app)


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


async def test_execute_users_success_and_idempotent(api: AsyncClient, ns: Namespace) -> None:
    """合法用户导入落库；同幂等键重复返回首次结果。"""
    username = f"{ns.prefix}u1"
    data = _xlsx(
        _USER_HEADERS,
        [[username, "张三", f"{username}@example.com", "13800000000", "启用", "Abcd1234!x"]],
    )
    headers = {"Idempotency-Key": f"{ns.prefix}-users-ok-1"}
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


async def test_execute_users_invalid_is_atomic(api: AsyncClient, ns: Namespace) -> None:
    """任一行非法 → 整批不落库；返回 committed / blocked_count。"""
    data = _xlsx(
        _USER_HEADERS,
        [
            [f"{ns.prefix}u2", "李四", "bad-email", "", "启用", ""],
            [f"{ns.prefix}u3", "王五", "", "", "启用", ""],
        ],
    )
    response = await api.post(
        f"{API}/users/execute",
        files={"file": ("users.xlsx", data)},
        headers={"Idempotency-Key": f"{ns.prefix}-users-bad-1"},
    )
    assert response.status_code == 200
    payload = _data(response)
    assert payload["committed"] is False
    assert payload["success_count"] == 0
    assert payload["fail_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["report_token"]


async def test_execute_roles_success(api: AsyncClient, ns: Namespace) -> None:
    """合法角色导入落库（恒 custom）。"""
    data = _xlsx(_ROLE_HEADERS, [[f"{ns.prefix}_r1", "销售经理", "启用"]])
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": f"{ns.prefix}-roles-ok-1"},
    )
    payload = _data(response)
    assert payload["committed"] is True
    assert payload["success_count"] == 1


async def test_error_report_download(api_env: _ApiEnv) -> None:
    """错误明细 token 可下载 xlsx（token 与错误行由准备阶段写入真实存储）。"""
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
        job_id = int(failed.id)
        session.add(SysJobError(job_id=job_id, row_no=2, column_key="username", message="登录账号不能为空"))
        await session.commit()
    token = "report-download-1"
    await api_env.cache.aset(report_key(api_env.cache, "demo", token), token_payload(job_id, "users"))
    report = await api_env.client.get(f"{API}/users/error-report/{token}")
    assert report.status_code == 200, report.json()
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


async def test_roles_invalid_is_atomic(api: AsyncClient, ns: Namespace) -> None:
    """角色码格式非法 / 文件内重复 → 整批不落库。"""
    duplicate = f"{ns.prefix}_dup"
    data = _xlsx(
        _ROLE_HEADERS,
        [["Bad-Code", "非法", "启用"], [duplicate, "重复一", "启用"], [duplicate, "重复二", "启用"]],
    )
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": f"{ns.prefix}-roles-bad-1"},
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

    data = _xlsx(
        _USER_HEADERS,
        [["limit1", "甲", "", "", "启用", ""], ["limit2", "乙", "", "", "启用", ""]],
    )
    async with temporary_config_values(api_env.engine, ConcurrentStableDict({"import.upload.max_rows": "1"})):
        limited = await api_env.client.post(
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

    async with temporary_config_values(api_env.engine, ConcurrentStableDict({"import.upload.max_size": "10"})):
        too_large = await api_env.client.post(
            f"{API}/users/execute",
            files={"file": ("users.xlsx", good)},
            headers={"Idempotency-Key": "size-1"},
        )
    assert _code(too_large) == 50303


async def test_async_submit_and_status(api_env: _ApiEnv) -> None:
    """行数超同步阈值 → 异步提交；状态可查；跨业务取作业 50307；错误明细未生成 50306。"""
    data = _xlsx(
        _USER_HEADERS,
        [["async1", "甲", "", "", "启用", ""], ["async2", "乙", "", "", "启用", ""]],
    )
    async with temporary_config_values(api_env.engine, ConcurrentStableDict({"import.sync_max_rows": "1"})):
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
    async with temporary_config_values(
        api_env.engine,
        ConcurrentStableDict({"import.rate_limit.limit": "1", "import.rate_limit.window": "60"}),
    ):
        first = await api_env.client.get(f"{API}/users/template")
        assert first.status_code == 200
        second = await api_env.client.get(f"{API}/users/template")
        assert _code(second) == 10005


async def test_business_write_permission(api_env: _ApiEnv) -> None:
    """持入口权限但缺业务写权限 → 30001（真实授权：只授导入执行，不授创建用户）。"""
    await grant_permissions(
        int(_NO_WRITE_SUBJECT),
        ConcurrentStableList([IMPORT_EXECUTE]),
        role_code=_NO_WRITE_ROLE_CODE,
    )
    await reset_permission_state(api_env.app)
    data = _xlsx(_USER_HEADERS, [["perm1", "甲", "", "", "启用", ""]])
    client = AsyncClient(transport=ASGITransport(app=api_env.app), base_url="http://test")
    client.headers.update(auth_headers(subject=_NO_WRITE_SUBJECT))
    async with client:
        response = await client.post(
            f"{API}/users/execute",
            files={"file": ("users.xlsx", data)},
            headers={"Idempotency-Key": "perm-1"},
        )
    assert _code(response) == 30001


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


async def test_idempotency_conflict(api_env: _ApiEnv) -> None:
    """同一幂等键正在处理中 → 10003（用真实存储先占位，构造「另一个请求在处理」）。"""
    settings = get_settings()
    store = cast("IdempotencyStore", resolve_plugin("idempotency", settings.idempotency.provider))
    key = build_idempotency_key(
        key=import_flow._idem_scope("users", "conflict-1"),  # pyright: ignore[reportPrivateUsage]
        tenant=TEST_TENANT_ID,
    )
    assert await store.begin(key)
    try:
        data = _xlsx(_USER_HEADERS, [["conflict1", "甲", "", "", "启用", ""]])
        conflict = await api_env.client.post(
            f"{API}/users/execute",
            files={"file": ("users.xlsx", data)},
            headers={"Idempotency-Key": "conflict-1"},
        )
        assert _code(conflict) == 10003
    finally:
        await store.release(key)


class _BrokenReleaseStore(IdempotencyStore):
    """begin 成功但 release 抛错（内部故障注入，只用于组件级断言）。"""

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


async def test_safe_release_swallows_failure() -> None:
    """幂等键释放失败只告警、不抛错（内部故障不覆盖原始异常）：组件级直接断言。"""
    await import_flow._safe_release(  # pyright: ignore[reportPrivateUsage]
        _BrokenReleaseStore(), "bms:1001:idem:users:release-1"
    )


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


@pytest.mark.kiwi_id(2551)
async def test_execute_inline_retries_on_write_contention(
    api: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同步导入撞写锁：整批重试后成功（作业记录不重复）。"""
    original = JobRunner.run_inline
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _flaky(
        runner: JobRunner,
        session: DbSession,
        submission: JobSubmission,
        *,
        db_key: str,
        tenant_id: int | None = None,
    ) -> tuple[SysJob, JobResult]:
        calls.append("call")
        if len(calls) == 1:
            raise OperationalError("INSERT INTO sys_role", {}, Exception("database is locked"))
        return await original(runner, session, submission, db_key=db_key, tenant_id=tenant_id)

    monkeypatch.setattr(JobRunner, "run_inline", _flaky)
    data = _xlsx(_ROLE_HEADERS, [[f"{ns.prefix}_retry", "重试经理", "启用"]])
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": f"{ns.prefix}-roles-retry-1"},
    )
    payload = _data(response)
    assert payload["committed"] is True
    assert payload["success_count"] == 1
    assert len(calls) == 2


@pytest.mark.kiwi_id(2552)
async def test_execute_inline_does_not_retry_other_errors(
    api: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非锁竞争异常不重试：只调一次，异常原样上抛。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _boom(
        runner: JobRunner,
        session: DbSession,
        submission: JobSubmission,
        *,
        db_key: str,
        tenant_id: int | None = None,
    ) -> tuple[SysJob, JobResult]:
        del runner, session, submission, db_key, tenant_id
        calls.append("call")
        raise InvalidRequestError("unexpected failure")

    monkeypatch.setattr(JobRunner, "run_inline", _boom)
    data = _xlsx(_ROLE_HEADERS, [[f"{ns.prefix}_boom", "异常经理", "启用"]])
    with pytest.raises(InvalidRequestError):
        await api.post(
            f"{API}/roles/execute",
            files={"file": ("roles.xlsx", data)},
            headers={"Idempotency-Key": f"{ns.prefix}-roles-boom-1"},
        )
    assert len(calls) == 1


@pytest.mark.kiwi_id(2553)
async def test_execute_inline_gives_up_after_retry_limit(
    api: AsyncClient, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """连续撞锁：重试到上限后上抛，不无限重试。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _always_locked(
        runner: JobRunner,
        session: DbSession,
        submission: JobSubmission,
        *,
        db_key: str,
        tenant_id: int | None = None,
    ) -> tuple[SysJob, JobResult]:
        del runner, session, submission, db_key, tenant_id
        calls.append("call")
        raise OperationalError("INSERT INTO sys_role", {}, Exception("database is locked"))

    monkeypatch.setattr(JobRunner, "run_inline", _always_locked)
    data = _xlsx(_ROLE_HEADERS, [[f"{ns.prefix}_locked", "锁死经理", "启用"]])
    response = await api.post(
        f"{API}/roles/execute",
        files={"file": ("roles.xlsx", data)},
        headers={"Idempotency-Key": f"{ns.prefix}-roles-locked-1"},
    )
    # 重试耗尽后由统一异常映射收敛为 503（10006 数据库繁忙），不把底层驱动异常透给调用方
    assert response.status_code == 503
    assert _code(response) == 10006
    assert len(calls) == 3


_existing_marks = pytestmark if isinstance(pytestmark, list) else [pytestmark]  # pyright: ignore[reportUnknownVariableType, reportUnnecessaryIsInstance]
pytestmark = [*_existing_marks, pytest.mark.xdist_group("platform-writes-core")]  # pyright: ignore[reportUnknownVariableType]

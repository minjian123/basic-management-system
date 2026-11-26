"""导出 API：同步 Excel / 脱敏与明文 / 选中导出 / 排序 / 异步受理 / 列表 PDF / 边界码位（Kiwi 2402）。

重写口径（13_11）：

- **自建应用壳是必要例外**：本文件要换 `rate_limiter` / `masking` / `config_source` 的实现并指定
  存储根，装配态应用做不到；壳用完经 `restore_registry_for` 把插件注册表归还装配态应用。
- **不再写系统管理员豁免**（`setup_min_tenant`）：只给专用主体授真实权限码（自定义角色、非豁免层级），
  默认主体验证导出、两个专用主体验证掩码与明文两态。
- 导出参数写共享租户库 `sys_config`（`temporary_config_values` 退出还原）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import get_settings
from bms_core.core.plugin import resolve_plugin
from bms_core.models.job import SysJob
from bms_core.models.platform.role import SysRole
from bms_core.models.platform.user import SysUser
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.testing.fixtures import clear_tenant_cache
from bms_core.testing.gates import write_window
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers
from tests_support.config_values import temporary_config_values
from tests_support.permission_grants import (
    DATA_PLAIN,
    EXPORT_DOWNLOAD,
    grant_permissions,
    reset_permission_state,
)
from tests_support.plugin_registry import restore_registry_for

pytestmark = pytest.mark.kiwi_id(2402)

API = "/api/v1/exports"

_DEFAULT_SUBJECT = 1001
"""默认测试主体：只授「导出下载」，用于常规导出断言。"""

_MASKED_SUBJECT = "900101"
"""仅持「导出下载」权限的主体（自定义角色，非豁免层级 → 无明文查看权限）。"""

_PLAIN_SUBJECT = "900102"
"""另持「明文查看」权限的主体（自定义角色）。"""

_DEFAULT_PERMISSIONS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    (EXPORT_DOWNLOAD, "user:query", "role:query")
)
"""默认主体所需权限：导出入口 + 导出取数走的两张列表读接口。"""

_MASKED_ROLE_CODE = "__test_export_masked"
_PLAIN_ROLE_CODE = "__test_export_plain"
_DEFAULT_ROLE_CODE = "__test_export_download"


def _data(response: object) -> ConcurrentStableDict[str, object]:
    """取统一响应 data。"""
    payload = cast("ConcurrentStableDict[str, object]", response.json())  # type: ignore[attr-defined]
    assert payload["code"] == 0, payload
    return cast("ConcurrentStableDict[str, object]", payload["data"])


def _code(response: object) -> int:
    """取业务码。"""
    payload = cast("ConcurrentStableDict[str, object]", response.json())  # type: ignore[attr-defined]
    return int(cast("int", payload["code"]))


def _sheet_rows(content: bytes) -> ConcurrentStableList[ConcurrentStableFrozenList[object]]:
    """读取导出 xlsx 的全部行。"""
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        rows: ConcurrentStableList[ConcurrentStableFrozenList[object]] = ConcurrentStableList()
        for row in workbook["数据"].iter_rows(values_only=True):
            rows.add(ConcurrentStableFrozenList(row))
        return rows
    finally:
        workbook.close()


def _subject_client(app: FastAPI, subject: str) -> AsyncClient:
    """构造指定主体身份的客户端（带真实签名令牌）。

    Args:
        app: 已装配应用。
        subject: 用户主体（令牌 `sub`）。

    Returns:
        AsyncClient: 异步客户端（调用方负责关闭）。
    """
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.headers.update(auth_headers(subject=subject))
    return client


@dataclass
class _Env:
    """导出 API 测试环境（自建壳，只读已装配系统的租户库引擎）。"""

    client: AsyncClient
    app: FastAPI
    engine: AsyncEngine
    limiter: MemoryRateLimiter
    factory: async_sessionmaker[AsyncSession]
    seed: str


def _body_rows(
    rows: ConcurrentStableList[ConcurrentStableFrozenList[object]],
) -> ConcurrentStableList[ConcurrentStableFrozenList[object]]:
    """去掉表头后的数据行。

    Args:
        rows: 含表头的全部行。

    Returns:
        ConcurrentStableList[ConcurrentStableFrozenList[object]]: 数据行。
    """
    body: ConcurrentStableList[ConcurrentStableFrozenList[object]] = ConcurrentStableList()
    for index, row in enumerate(rows):
        if index:
            body.add(row)
    return body


def _first_id(response: object) -> str:
    """取列表响应首行主键。

    Args:
        response: 列表接口响应。

    Returns:
        str: 首行主键字符串。
    """
    data = _data(response)
    items = cast("ConcurrentStableList[ConcurrentStableDict[str, object]]", data["list"])
    return str(items[0]["id"])


@pytest_asyncio.fixture
async def env(
    shared_tenant_engine: AsyncEngine,
    ns: Namespace,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service_app: FastAPI,
) -> AsyncIterator[_Env]:
    """导出 API 环境：自建壳换实现（收尾归还插件注册表），只给专用主体授真实权限码。

    Args:
        shared_tenant_engine: 共享租户库引擎。
        ns: 用例命名空间。
        shared_tenant_db_url: 共享租户库连接串。
        tmp_path: 临时目录（存储根）。
        monkeypatch: 补丁夹具。
        service_app: 装配态应用（收尾归还注册表用）。

    Yields:
        _Env: 测试环境。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    # 限流走进程内实现（断言 429，不依赖 Redis）；掩码走默认实现；权限走真实 RBAC
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "memory")
    monkeypatch.setenv("BMS_MASKING__PROVIDER", "default")
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "rbac")
    # 参数按真实运行取租户库 `sys_config`（用例改后恢复原值）
    monkeypatch.setenv("BMS_CONFIG_SOURCE__PROVIDER", "sql")
    monkeypatch.setenv("BMS_CONFIG_CACHE_REGION__PROVIDER", "memory")
    get_settings.cache_clear()
    await ensure_tables(
        shared_tenant_engine,
        cast("list[Table]", [SysUser.__table__, SysRole.__table__, SysJob.__table__]),
    )
    get_settings.cache_clear()

    created = ApplicationFactory().create(None)
    clear_tenant_cache(created)
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    seed = ns.code("export")
    limiter = cast("MemoryRateLimiter", resolve_plugin("rate_limiter", get_settings().rate_limiter.provider))
    # 限流计数是插件级实例（跨用例复用）：先清空，避免上一用例的窗口残留把首次请求判成超限
    limiter.clear()

    try:
        async with (
            created.router.lifespan_context(created),
            AsyncClient(transport=ASGITransport(app=created), base_url="http://test") as client,
        ):
            client.headers.update(auth_headers())
            # 造数是本文件唯一的写：只把这一段放进写门（13_08，替代整条用例持门）
            async with write_window("tenant_demo"), factory() as session:
                session.add_all(
                    [
                        SysUser(
                            form_key=f"{seed}-{index}",
                            username=f"user{index}",
                            password_hash="x",
                            name=f"用户{index}",
                            status="enabled",
                            phone=f"1380000000{index}",
                            email=f"{seed}-{index}@example.com",
                        )
                        for index in range(1, 4)
                    ]
                )
                session.add(
                    SysRole(
                        form_key=f"{seed}-role",
                        code="r_demo",
                        name="演示角色",
                        status="enabled",
                        role_type="custom",
                    )
                )
                await session.commit()
            # 授权：默认主体只持导出下载；两个专用主体分别验证掩码 / 明文（真实 RBAC 判定）
            await grant_permissions(
                _DEFAULT_SUBJECT,
                ConcurrentStableList(_DEFAULT_PERMISSIONS),
                role_code=_DEFAULT_ROLE_CODE,
            )
            await grant_permissions(
                int(_MASKED_SUBJECT),
                ConcurrentStableList([EXPORT_DOWNLOAD]),
                role_code=_MASKED_ROLE_CODE,
            )
            await grant_permissions(
                int(_PLAIN_SUBJECT),
                ConcurrentStableList([EXPORT_DOWNLOAD, DATA_PLAIN]),
                role_code=_PLAIN_ROLE_CODE,
            )
            # 写授权数据后清装配级缓存与进程级快照（首次请求前）
            await reset_permission_state(created)
            yield _Env(
                client=client,
                app=created,
                engine=shared_tenant_engine,
                limiter=limiter,
                factory=factory,
                seed=seed,
            )
    finally:
        clear_tenant_cache(created)
        # 自建壳把进程级注册表换代到壳：收尾归还装配态应用，避免后继用例解析到壳的工厂
        restore_registry_for(service_app)


async def test_export_excel_stream_and_rows(env: _Env) -> None:
    """同步导出 Excel：文件流 + 行数 = 列表总数（含表头）。

    统计范围限定为本夹具的命名空间派生关键字（`ns.code("export")` 命中邮箱）：测试基座是多 worker
    共用一份 SQLite，全库行数会被其他 worker 的并发写入改变；也不能用固定前缀——同一库跨多轮运行
    会累积到同一批行，超过导出上限后「导出行数 = 列表总数」不再成立。
    """
    filters = {"kw": env.seed}
    response = await env.client.get(f"{API}/users", params=filters)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    rows = _sheet_rows(response.content)
    assert tuple(rows[0]) == ("登录账号", "姓名", "手机号", "邮箱", "状态", "最近登录")
    listed = await env.client.get("/api/v1/users", params={"size": 1, **filters})
    total = int(cast("int", _data(listed)["total"]))
    assert len(rows) == total + 1


async def test_export_masks_sensitive_columns(env: _Env) -> None:
    """无 `data:plain`：手机号 / 邮箱掩码，其余列原样。"""
    async with _subject_client(env.app, _MASKED_SUBJECT) as client:
        response = await client.get(f"{API}/users")
    rows = _sheet_rows(response.content)
    body = _body_rows(rows)
    masked = [row for row in body if isinstance(row[2], str) and row[2]]
    assert masked
    phone, email = masked[0][2], masked[0][3]
    assert isinstance(phone, str) and "*" in phone
    assert isinstance(email, str) and "*" in email


async def test_export_plain_with_data_plain(env: _Env) -> None:
    """持 `data:plain`：明文导出。"""
    async with _subject_client(env.app, _PLAIN_SUBJECT) as client:
        response = await client.get(f"{API}/users")
    rows = _sheet_rows(response.content)
    body = _body_rows(rows)
    phones = [row[2] for row in body if isinstance(row[2], str) and row[2]]
    emails = [row[3] for row in body if isinstance(row[3], str) and row[3]]
    assert phones and all("*" not in str(phone) for phone in phones)
    assert emails and all("*" not in str(email) for email in emails)


async def test_export_ids_selection(env: _Env) -> None:
    """ids 选中导出：只含选中行。"""
    listed = await env.client.get("/api/v1/users", params={"size": 1})
    target = _first_id(listed)
    response = await env.client.get(f"{API}/users", params={"ids": target})
    rows = _sheet_rows(response.content)
    assert len(rows) == 2


async def test_export_order_desc(env: _Env) -> None:
    """排序参数生效（用户名倒序）。"""
    response = await env.client.get(f"{API}/users", params={"order_by": "username", "order": "desc"})
    rows = _sheet_rows(response.content)
    listed = await env.client.get("/api/v1/users", params={"size": 1, "order_by": "username", "order": "desc"})
    listed_body = cast("ConcurrentStableList[ConcurrentStableDict[str, object]]", _data(listed)["list"])
    assert _body_rows(rows)[0][0] == listed_body[0]["username"]


async def test_export_empty(env: _Env) -> None:
    """0 行：回空结果，不生成文件。"""
    response = await env.client.get(f"{API}/users", params={"kw": "not-exists-user"})
    assert response.status_code == 200
    data = _data(response)
    assert data["empty"] is True


async def test_export_unknown_biz(env: _Env) -> None:
    """未注册业务：50401。"""
    response = await env.client.get(f"{API}/not-exists")
    assert response.status_code == 400
    assert _code(response) == 50401


async def test_export_ids_invalid(env: _Env) -> None:
    """ids 非法：10001。"""
    response = await env.client.get(f"{API}/users", params={"ids": "abc"})
    assert response.status_code == 200
    assert _code(response) == 10001


async def test_export_async_over_threshold(env: _Env) -> None:
    """超同步阈值：回异步受理 + 建作业。"""
    async with temporary_config_values(env.engine, ConcurrentStableDict({"export.sync_max_rows": "1"})):
        response = await env.client.get(f"{API}/users")
    assert response.status_code == 200
    data = _data(response)
    assert data["async"] is True
    assert int(cast("int", data["job_id"])) > 0
    assert str(data["status_url"]).startswith("/api/v1/exports/jobs/")
    async with env.factory() as session:
        statement = SysJob.__table__.select().where(SysJob.job_type == "platform.export.execute")
        jobs = (await session.execute(statement)).all()
    assert len(jobs) >= 1


async def test_export_over_max_rows(env: _Env) -> None:
    """超过单次行数上限：50404。"""
    async with temporary_config_values(env.engine, ConcurrentStableDict({"export.max_rows": "2"})):
        response = await env.client.get(f"{API}/users")
    assert response.status_code == 400
    assert _code(response) == 50404


async def test_export_job_status_missing(env: _Env) -> None:
    """作业不存在：50402。"""
    response = await env.client.get(f"{API}/jobs/999999")
    assert response.status_code == 404
    assert _code(response) == 50402


async def test_export_list_pdf(env: _Env) -> None:
    """列表 PDF 同步：返回产物限时取址。"""
    listed = await env.client.get("/api/v1/users", params={"size": 1})
    target = _first_id(listed)
    response = await env.client.get(f"{API}/users/pdf", params={"ids": target, "paper": "A4", "watermark": "内部资料"})
    assert response.status_code == 200, response.text
    data = _data(response)
    assert data["async"] is False
    artifact = cast("ConcurrentStableDict[str, object]", data["artifact"])
    assert str(artifact["object_key"]).startswith("demo/prints/list/")
    assert str(artifact["url"]).startswith("file://")
    assert int(cast("int", artifact["expires_in"])) > 0


async def test_export_list_pdf_bad_paper(env: _Env) -> None:
    """纸张非法：10001。"""
    listed = await env.client.get("/api/v1/users", params={"size": 1})
    target = _first_id(listed)
    response = await env.client.get(f"{API}/users/pdf", params={"ids": target, "paper": "B5"})
    assert response.status_code == 200
    assert _code(response) == 10001


async def test_export_list_pdf_bad_paper_without_rows(env: _Env) -> None:
    """纸张非法：即使筛选无数据也先报 10001（校验前置，不被「无数据可导出」吞成成功）。"""
    response = await env.client.get(f"{API}/users/pdf", params={"ids": "1", "paper": "B5"})
    assert response.status_code == 200
    assert _code(response) == 10001


async def test_export_roles_no_masking(env: _Env) -> None:
    """roles 无敏感列：无 `data:plain` 也原样。"""
    async with _subject_client(env.app, _MASKED_SUBJECT) as client:
        response = await client.get(f"{API}/roles")
    rows = _sheet_rows(response.content)
    assert tuple(rows[0]) == ("角色编码", "角色名称", "角色类型", "状态", "创建时间")
    body = _body_rows(rows)
    codes: ConcurrentStableSet[object] = ConcurrentStableSet(row[0] for row in body)
    assert "r_demo" in codes
    demo = next(row for row in body if row[0] == "r_demo")
    assert demo[2] == "自定义"


async def test_export_requires_auth(env: _Env) -> None:
    """未登录：401（端点级 `export:download` 的实际判定由 RBAC 覆盖）。"""
    async with AsyncClient(transport=ASGITransport(app=env.app), base_url="http://test") as anonymous:
        response = await anonymous.get(f"{API}/users")
    assert response.status_code == 401


async def test_export_rate_limited(env: _Env) -> None:
    """超限流阈值：429。"""
    async with temporary_config_values(
        env.engine, ConcurrentStableDict({"export.rate_limit.limit": "1", "export.rate_limit.window": "60"})
    ):
        first = await env.client.get(f"{API}/users")
        assert first.status_code == 200
        second = await env.client.get(f"{API}/users")
    assert second.status_code == 429


async def test_export_status_filter(env: _Env) -> None:
    """状态筛选参数透传导出取数（与列表同口径）。"""
    response = await env.client.get(f"{API}/users", params={"status": "enabled"})
    assert response.status_code == 200
    rows = _sheet_rows(response.content)
    body = _body_rows(rows)
    assert body
    assert all(str(row[4]) == "启用" for row in body)


async def test_export_roles_ids_selection(env: _Env) -> None:
    """角色导出按 ids 选中（仓储 ids 条件）。"""
    listed = await env.client.get("/api/v1/roles", params={"size": 1})
    target = _first_id(listed)
    response = await env.client.get(f"{API}/roles", params={"ids": target})
    rows = _sheet_rows(response.content)
    assert len(rows) == 2


async def test_export_job_status_success(env: _Env) -> None:
    """异步导出后查状态：回作业状态与进度（产物未生成时 artifact 为空）。"""
    async with temporary_config_values(env.engine, ConcurrentStableDict({"export.sync_max_rows": "1"})):
        accepted = await env.client.get(f"{API}/users")
    job_id = int(cast("int", _data(accepted)["job_id"]))
    response = await env.client.get(f"{API}/jobs/{job_id}")
    assert response.status_code == 200, response.text
    data = _data(response)
    assert int(cast("int", data["job_id"])) == job_id
    assert str(data["status"])
    assert str(data["kind"]) == "excel"
    assert data["artifact"] is None


async def test_export_list_pdf_empty(env: _Env) -> None:
    """列表 PDF 0 行：回空结果，不落产物。"""
    response = await env.client.get(f"{API}/users/pdf", params={"kw": "not-exists-user"})
    assert response.status_code == 200
    assert _data(response)["empty"] is True


async def test_export_list_pdf_async(env: _Env) -> None:
    """列表 PDF 超同步上限：转后台作业并回受理。"""
    async with temporary_config_values(env.engine, ConcurrentStableDict({"export.pdf.sync_max_docs": "1"})):
        response = await env.client.get(f"{API}/users/pdf")
    assert response.status_code == 200, response.text
    data = _data(response)
    assert data["async"] is True
    assert int(cast("int", data["job_id"])) > 0


_existing_marks = pytestmark if isinstance(pytestmark, list) else [pytestmark]  # pyright: ignore[reportUnknownVariableType, reportUnnecessaryIsInstance]
pytestmark = [*_existing_marks, pytest.mark.xdist_group("platform-writes-core")]  # pyright: ignore[reportUnknownVariableType]

"""导出 API 用例：同步 Excel / 脱敏与明文 / 选中导出 / 排序 / 异步受理 / 列表 PDF / 边界码位。"""

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

from bms_core.api.deps import (
    get_audit_capturer,
    get_config_source,
    get_exporter,
    get_masker,
    get_object_storage,
    get_permission_checker,
    get_print_exporter,
    get_rate_limiter,
    get_uow,
)
from bms_core.audit.null import NullAuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import get_settings
from bms_core.db.session import DbUnitOfWork
from bms_core.masking.default import DefaultMasker
from bms_core.models.job import SysJob
from bms_core.models.platform.role import SysRole
from bms_core.models.platform.user import SysUser
from bms_core.permission.base import BasePermissionChecker
from bms_core.permission.null import NullPermissionChecker
from bms_core.print.exporter import StoragePrintExporter
from bms_core.print.templates import BuiltinPrintTemplateProvider
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.storage.local import LocalObjectStorage
from bms_core.testing.fixtures import clear_tenant_cache
from bms_core.testing.schema import ensure_tables
from bms_core.transfer.openpyxl_exporter import OpenpyxlExporter
from bms_platform.main import ApplicationFactory
from tests_support.auth import auth_headers
from tests_support.permission_admin import setup_min_tenant

pytestmark = [pytest.mark.kiwi_id(2402), pytest.mark.usefixtures("serial_db_write")]

API = "/api/v1/exports"
_TENANT_SEED = "t-export"


class _Config(BaseConfigSource):
    """固定值参数源。"""

    plugin_name = ""

    def __init__(self, values: ConcurrentStableDict[str, str] | None = None) -> None:
        self._values = values or ConcurrentStableDict()

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})

    def override(self, key: str, value: str) -> None:
        """覆盖一个参数值（测试用）。

        Args:
            key: 参数键。
            value: 参数值。
        """
        self._values.set(key, value)


class _PlainAllowed(BasePermissionChecker):
    """放行全部权限码（含 `data:plain`；非占位实现，`check_plain` 不 fail-closed）。"""

    plugin_name = ""

    def check(self, code: str) -> bool:
        return True


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


@dataclass
class _Env:
    """导出 API 测试环境。"""

    client: AsyncClient
    app: FastAPI
    config: _Config
    limiter: MemoryRateLimiter
    factory: async_sessionmaker[AsyncSession]


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


def _masker(allow_plain: bool) -> DefaultMasker:
    """构造掩码器（按需放行明文）。"""
    return DefaultMasker(checker=_PlainAllowed() if allow_plain else NullPermissionChecker())


@pytest_asyncio.fixture
async def env(
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_Env]:
    """带依赖替身的导出 API 环境。"""
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    monkeypatch.setenv("BMS_STORAGE__OPTIONS__ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    await ensure_tables(
        shared_tenant_engine,
        cast("list[Table]", [SysUser.__table__, SysRole.__table__, SysJob.__table__]),
    )
    await setup_min_tenant(shared_tenant_db_url)
    get_settings.cache_clear()

    service_app = ApplicationFactory().create(None)
    clear_tenant_cache(service_app)
    factory = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    config = _Config()
    limiter = MemoryRateLimiter()
    storage = LocalObjectStorage(root=tmp_path / "storage")

    async def _uow() -> AsyncIterator[DbUnitOfWork]:
        async with factory() as session:
            yield DbUnitOfWork(session)

    service_app.dependency_overrides[get_uow] = _uow
    service_app.dependency_overrides[get_config_source] = lambda: config
    service_app.dependency_overrides[get_object_storage] = lambda: storage
    service_app.dependency_overrides[get_exporter] = OpenpyxlExporter
    service_app.dependency_overrides[get_permission_checker] = NullPermissionChecker
    service_app.dependency_overrides[get_audit_capturer] = NullAuditCapturer
    service_app.dependency_overrides[get_rate_limiter] = lambda: limiter
    service_app.dependency_overrides[get_masker] = lambda: _masker(False)
    service_app.dependency_overrides[get_print_exporter] = lambda: StoragePrintExporter(
        storage=storage, templates=BuiltinPrintTemplateProvider()
    )
    try:
        async with (
            service_app.router.lifespan_context(service_app),
            AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client,
        ):
            client.headers.update(auth_headers())
            async with factory() as session:
                session.add_all(
                    [
                        SysUser(
                            form_key=f"{_TENANT_SEED}-{index}",
                            username=f"user{index}",
                            password_hash="x",
                            name=f"用户{index}",
                            status="enabled",
                            phone=f"1380000000{index}",
                            email=f"user{index}@example.com",
                        )
                        for index in range(1, 4)
                    ]
                )
                session.add(
                    SysRole(
                        form_key=f"{_TENANT_SEED}-role",
                        code="r_demo",
                        name="演示角色",
                        status="enabled",
                        role_type="custom",
                    )
                )
                await session.commit()
            yield _Env(client=client, app=service_app, config=config, limiter=limiter, factory=factory)
    finally:
        service_app.dependency_overrides.clear()
        clear_tenant_cache(service_app)


async def test_export_excel_stream_and_rows(env: _Env) -> None:
    """同步导出 Excel：文件流 + 行数 = 列表总数（含表头）。"""
    response = await env.client.get(f"{API}/users")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    rows = _sheet_rows(response.content)
    assert tuple(rows[0]) == ("登录账号", "姓名", "手机号", "邮箱", "状态", "最近登录")
    listed = await env.client.get("/api/v1/users", params={"size": 1})
    total = int(cast("int", _data(listed)["total"]))
    assert len(rows) == total + 1


async def test_export_masks_sensitive_columns(env: _Env) -> None:
    """无 `data:plain`：手机号 / 邮箱掩码，其余列原样。"""
    response = await env.client.get(f"{API}/users")
    rows = _sheet_rows(response.content)
    body = _body_rows(rows)
    masked = [row for row in body if isinstance(row[2], str) and row[2]]
    assert masked
    phone, email = masked[0][2], masked[0][3]
    assert isinstance(phone, str) and "*" in phone
    assert isinstance(email, str) and "*" in email


async def test_export_plain_with_data_plain(env: _Env) -> None:
    """持 `data:plain`：明文导出。"""
    env.app.dependency_overrides[get_masker] = lambda: _masker(True)
    response = await env.client.get(f"{API}/users")
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
    env.config.override("export.sync_max_rows", "1")
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
    env.config.override("export.max_rows", "2")
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
    assert _code(response) == 10001


async def test_export_roles_no_masking(env: _Env) -> None:
    """roles 无敏感列：无 `data:plain` 也原样。"""
    response = await env.client.get(f"{API}/roles")
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
    env.config.override("export.rate_limit.limit", "1")
    first = await env.client.get(f"{API}/users")
    assert first.status_code == 200
    second = await env.client.get(f"{API}/users")
    assert second.status_code == 429

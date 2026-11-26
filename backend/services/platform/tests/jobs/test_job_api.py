"""作业管理面护栏（Kiwi 2387）：路由挂载 / 未认证拒绝 / 权限门禁生效。

权限码 `job:query` / `job:manage` 由种子下发；本套件不种 `job` 业务码，故「已登录但未授权」应为 403，
恰好验证权限依赖确实挂在管理面（而不是裸奔）。投影读写行为由 `test_job_monitor` 覆盖。
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests_support.auth import auth_headers

pytestmark = pytest.mark.kiwi_id(2387)

_UNAUTHORIZED_SUBJECT = "900201"
"""专用无权限主体：任何用例都不给它授角色 / 权限。"""

API = "/api/v1/jobs"


async def test_routes_are_mounted(service_app: FastAPI) -> None:
    """OpenAPI 中包含作业管理面 5 个端点与服务内部面。"""
    paths = set(service_app.openapi().get("paths", {}).keys())
    assert f"{API}/types" in paths, sorted(paths)
    assert API in paths
    assert f"{API}/{{job_id}}" in paths
    assert f"{API}/{{job_id}}/cancel" in paths
    assert f"{API}/{{job_id}}/retry" in paths
    assert f"{API}/internal" in paths
    assert f"{API}/internal/{{job_id}}" in paths


async def test_anonymous_is_rejected(service_app: FastAPI) -> None:
    """未登录访问作业列表 / 类型目录：401。"""
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
        for path in (API, f"{API}/types"):
            response = await client.get(path)
            assert response.status_code == 401, (path, response.text)


async def test_authenticated_without_permission_is_forbidden(service_app: FastAPI) -> None:
    """已登录但未授予 `job:*`：403（权限门禁挂在管理面）。

    用**专用无权限主体**：同进程里别的用例会把 1001 授成系统管理员，拿它断言 403 会随顺序变红。
    """
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as subject:
        subject.headers.update(auth_headers(subject=_UNAUTHORIZED_SUBJECT))
        for path in (API, f"{API}/types", f"{API}/999999999999"):
            response = await subject.get(path)
            assert response.status_code == 403, (path, response.text)


_existing_marks = pytestmark if isinstance(pytestmark, list) else [pytestmark]  # pyright: ignore[reportUnknownVariableType, reportUnnecessaryIsInstance]
pytestmark = [*_existing_marks, pytest.mark.xdist_group("platform-writes-core")]  # pyright: ignore[reportUnknownVariableType]

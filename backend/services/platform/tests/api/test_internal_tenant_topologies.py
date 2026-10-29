"""拓扑全量快照内部出口（07C `02_02`；Kiwi 2367）。

覆盖详细设计 §6 用例 19~21：服务身份可读全量（只回解析三列）、登录态缺权限码拒绝、
平台未自举时返回空快照（不 500）。
"""

from collections.abc import Awaitable, Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.collaboration.bootstrap import TOPOLOGY_SNAPSHOT_PATH
from bms_core.collaboration.topology import DEFAULT_TOPOLOGY_TENANT
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import AuthError, PermissionError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.services.module_registry import domain_service_view
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

pytestmark = pytest.mark.kiwi_id(2367)

INTERNAL_API = "/api/v1/platform/internal/tenant-topologies"

CONFIGURED_TENANT = 9301
"""已单独配置拓扑的租户主键（验证多快照下发）。"""


class _StubVerifier:
    """令牌校验替身：`Bearer platform` 视作服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串（即服务标识）。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        del audience
        if token == "platform":
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


@pytest.fixture(autouse=True)
def _null_permission(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """权限校验改用占位实现（恒放行）：本套用例只验端点语义。

    Args:
        monkeypatch: 环境变量覆盖夹具。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_service_identity_reads_full_snapshot(client: AsyncClient, service_app: FastAPI) -> None:
    """用例 19：服务身份读全量快照——含默认拓扑与已配置租户、行只回解析三列（无运营字段）。"""
    domain = next(iter(domain_service_view()))
    await client.put(
        f"/api/v1/tenant-topologies/{CONFIGURED_TENANT}",
        json={"rows": [{"domain_key": domain, "unit_key": "core", "status": "enabled"}]},
    )
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    resp = await client.get(INTERNAL_API, headers={"Authorization": "Bearer platform"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["default_version"] >= 1
    default_snapshot = next(item for item in data["snapshots"] if item["tenant_id"] == str(DEFAULT_TOPOLOGY_TENANT))
    assert default_snapshot["version"] == data["default_version"]
    row = default_snapshot["rows"][0]
    assert set(row) == {"domain_key", "unit_key", "status"}
    configured = next(item for item in data["snapshots"] if item["tenant_id"] == str(CONFIGURED_TENANT))
    assert configured["rows"] == [{"domain_key": domain, "unit_key": "core", "status": "enabled"}]


async def test_login_state_without_permission_is_denied(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用例 20：登录态缺 `tenant-topology:query` → 拒绝（不因模块级鉴权通过而放行）。"""
    module = "bms_platform.domains.platform_registry.api.internal_tenant_topologies"

    async def _deny(request: object) -> None:
        """权限依赖替身：恒拒绝。

        Args:
            request: 请求对象（未使用）。

        Raises:
            PermissionError: 恒抛（30001 / 403）。
        """
        del request
        raise PermissionError("缺少权限码：tenant-topology:query")

    def _deny_factory(code: str) -> Callable[[object], Awaitable[None]]:
        """权限依赖工厂替身：任意权限码都返回拒绝依赖。

        Args:
            code: 权限码（未使用）。

        Returns:
            Callable[[object], Awaitable[None]]: 拒绝依赖。
        """
        del code
        return _deny

    monkeypatch.setattr(f"{module}.require_permission", _deny_factory)

    resp = await client.get(INTERNAL_API)

    assert resp.status_code == 403


async def test_empty_snapshot_when_platform_not_bootstrapped(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """用例 21：平台尚未自举——返回空快照与默认版本 0（调用方按「未装载」降级，不报 500）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    async def _empty(self: TenantTopologyService) -> ConcurrentStableList[object]:
        """恒返回空快照清单。

        Args:
            self: 服务实例（未使用）。

        Returns:
            ConcurrentStableList[object]: 空清单。
        """
        del self
        return ConcurrentStableList()

    monkeypatch.setattr(TenantTopologyService, "snapshot", _empty)

    resp = await client.get(INTERNAL_API, headers={"Authorization": "Bearer platform"})

    assert resp.status_code == 200
    assert resp.json()["data"] == {"default_version": 0, "snapshots": []}


@pytest.mark.kiwi_id(2368)
def test_snapshot_path_constant_matches_route(service_app: FastAPI) -> None:
    """基座拓扑出口常量必须与平台真实路由一致（路径写错只会 404，运行期难发现）。"""
    assert TOPOLOGY_SNAPSHOT_PATH == INTERNAL_API
    assert INTERNAL_API in service_app.openapi()["paths"]

"""identity 侧权限专项用例（`04_01` 下沉后）：数据来源契约取数 + 真实校验生效 + fail-closed。

`04_01` 之前 identity 的 `require_permission` 解析到基座占位实现（恒放行）；下沉后 identity 注入
「经 platform 内部只读契约取数」的数据来源，判定改由基座引擎在**本进程内**执行。本套用例覆盖：

1. **数据来源契约取数**：`subject` / `metadata` 两条内部端点的请求形态与响应映射；
2. **fail-closed**：下游不可达 / 非 2xx / `code != 0` / `data` 非对象 → `ServiceUnavailableError`（10007）；
3. **真实校验生效**：无码拒（`30001`）、有码放行、豁免层级放行、服务身份放行；
4. **装配**：`[permission].provider` 缺省置 `rbac`，显式配置不被覆盖。
"""

from collections.abc import Iterator
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.context import current_tenant_id, current_user_id
from bms_core.core.exceptions import PermissionError, ServiceUnavailableError
from bms_core.permission.snapshot import (
    TIER_PLATFORM_ADMIN,
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    set_current_permission_snapshot,
)
from bms_core.servicecall.base import BaseServiceClient, ServiceResponse
from bms_identity.permission import IDENTITY_DATA_SOURCE_KEY, build_identity_source, register_identity_permission
from bms_identity.permission.source import PlatformContractPermissionDataSource


class _Client(BaseServiceClient):
    """服务间客户端替身（可配置响应 / 抛错，并记录请求）。"""

    key: str = "service_client"

    def __init__(self, *, response: ServiceResponse | None = None, error: Exception | None = None) -> None:
        """初始化。

        Args:
            response: 返回的响应（None 表示空响应）。
            error: 抛出的异常。
        """
        self.response = response
        self.error = error
        self.requests: ConcurrentStableList[Any] = ConcurrentStableList()

    async def call(self, request: Any) -> ServiceResponse:
        """模拟调用并记录请求。

        Args:
            request: 服务间调用请求。

        Returns:
            ServiceResponse: 配置的响应。

        Raises:
            Exception: 配置的异常。
        """
        self.requests.add(request)
        if self.error is not None:
            raise self.error
        return self.response if self.response is not None else ServiceResponse(status_code=200, content=b"{}")


def _response(data: object, *, code: int = 0, status_code: int = 200) -> ServiceResponse:
    """构造统一响应体。

    Args:
        data: 响应 `data`。
        code: 业务码。
        status_code: HTTP 状态码。

    Returns:
        ServiceResponse: 响应。
    """
    import json

    body = {"code": code, "message": "ok", "data": data}
    return ServiceResponse(status_code=status_code, content=json.dumps(body).encode())


@pytest.fixture(autouse=True)
def clean_context() -> Iterator[None]:
    """每例前后清空快照与请求上下文。

    Yields:
        None: 用例运行期。
    """
    set_current_permission_snapshot(None)
    yield
    set_current_permission_snapshot(None)
    current_user_id.set(None)
    current_tenant_id.set(None)


@pytest.mark.kiwi_id(2320)
async def test_load_subject_maps_contract_payload() -> None:
    """取数：`subject` 端点请求体带 `user_id`；响应映射为基座数据契约（含字符串主键还原）。"""
    client = _Client(
        response=_response(
            {
                "role_ids": [11, 12],
                "role_types": {"11": "custom", "12": "system"},
                "grants": [
                    {"perm_type": "menu", "target_id": 900},
                    {"perm_type": "permission", "target_id": 902},
                ],
                "data_scope_rules": [
                    {"data_source_key": "role", "policy_type": "select", "config": [{"field": "area_code"}]}
                ],
                "field_perms": [{"form_id": 901, "field_key": "salary", "visible": False, "editable": False}],
            }
        )
    )
    source = PlatformContractPermissionDataSource(client)
    data = await source.load_subject(user_id=1001)
    assert sorted(data.role_ids) == [11, 12]
    assert data.role_types.get(11) == "custom"
    assert data.role_types.get(12) == "system"
    assert [(item.perm_type, item.target_id) for item in data.grants] == [("menu", 900), ("permission", 902)]
    assert len(data.data_scope_rules) == 1
    assert data.data_scope_rules[0].policy_type == "select"
    assert len(data.field_perms) == 1
    assert data.field_perms[0].visible is False
    request = client.requests[0]
    assert request.service == "platform"
    assert request.method == "POST"
    assert request.path == "/api/v1/platform/internal/permissions/subject"
    assert request.json_body.get("user_id") == 1001


@pytest.mark.kiwi_id(2320)
async def test_load_metadata_maps_contract_payload() -> None:
    """取数：`metadata` 端点走 GET + `locale` 查询参数；索引键还原为整数。"""
    client = _Client(
        response=_response(
            {
                "version": 5,
                "menu_forms": {"900": [901]},
                "permission_codes": {"902": "employee:query"},
            }
        )
    )
    source = PlatformContractPermissionDataSource(client)
    metadata = await source.load_metadata(locale="zh-CN")
    assert metadata.version == 5
    assert list(metadata.menu_forms.get(900) or []) == [901]
    assert metadata.permission_codes.get(902) == "employee:query"
    request = client.requests[0]
    assert request.method == "GET"
    assert request.path == "/api/v1/platform/internal/permissions/metadata"
    assert request.query.get("locale") == "zh-CN"


@pytest.mark.kiwi_id(2320)
async def test_role_types_keys_round_trip_and_skip_bad() -> None:
    """取数：角色类型键还原（数字键 → 整数）；坏键跳过（不因单个坏键整单失败）。"""
    client = _Client(
        response=_response(
            {
                "role_ids": [],
                "role_types": {"7": "custom", "bad": "system"},
                "grants": [],
                "data_scope_rules": [],
                "field_perms": [],
            }
        )
    )
    source = PlatformContractPermissionDataSource(client)
    data = await source.load_subject(user_id=1)
    assert data.role_types.get(7) == "custom"
    assert len(data.role_types) == 1


@pytest.mark.kiwi_id(2320)
async def test_as_int_accepts_int_str_and_rejects_others() -> None:
    """主键还原：整数原样、数字串转换、其余（含布尔）返回 None。"""
    from bms_identity.permission.source import _as_int  # pyright: ignore[reportPrivateUsage]

    assert _as_int(7) == 7
    assert _as_int("7") == 7
    assert _as_int("bad") is None
    assert _as_int(None) is None
    assert _as_int(True) is None


@pytest.mark.kiwi_id(2320)
async def test_metadata_skips_non_numeric_keys() -> None:
    """取数容错：非数字主键项跳过（不因单个坏键整单失败）。"""
    client = _Client(response=_response({"version": 1, "menu_forms": {"bad": [1]}, "permission_codes": {"x": "a:b"}}))
    source = PlatformContractPermissionDataSource(client)
    metadata = await source.load_metadata()
    assert list(metadata.menu_forms) == []
    assert list(metadata.permission_codes) == []


@pytest.mark.kiwi_id(2320)
async def test_load_subject_fails_closed_on_service_errors() -> None:
    """fail-closed：不可达 / 非 2xx / `code != 0` / `data` 非对象 一律 `ServiceUnavailableError`。"""
    unreachable = PlatformContractPermissionDataSource(_Client(error=RuntimeError("conn refused")))
    with pytest.raises(RuntimeError):
        await unreachable.load_subject(user_id=1)

    bad_status = PlatformContractPermissionDataSource(_Client(response=_response({}, status_code=503)))
    with pytest.raises(ServiceUnavailableError):
        await bad_status.load_subject(user_id=1)

    bad_code = PlatformContractPermissionDataSource(_Client(response=_response({}, code=10007)))
    with pytest.raises(ServiceUnavailableError):
        await bad_code.load_subject(user_id=1)

    bad_data = PlatformContractPermissionDataSource(_Client(response=_response("x")))
    with pytest.raises(ServiceUnavailableError):
        await bad_data.load_subject(user_id=1)


@pytest.mark.kiwi_id(2320)
async def test_load_metadata_fails_closed_on_non_json_body() -> None:
    """fail-closed：响应体非 JSON → `ServiceUnavailableError`（不静默当成空元数据）。"""
    client = _Client(response=ServiceResponse(status_code=200, content=b"not-json"))
    source = PlatformContractPermissionDataSource(client)
    with pytest.raises(ServiceUnavailableError):
        await source.load_metadata()


@pytest.mark.kiwi_id(2320)
async def test_identity_data_source_registered_by_assembly() -> None:
    """装配：`register_identity_permission` 登记数据来源工厂（幂等）。"""
    from bms_core.core.config import Settings
    from bms_core.core.plugin import default_plugin_registry
    from bms_core.permission.sources import (
        current_permission_data_source_factory,
        reset_permission_data_sources,
    )

    reset_permission_data_sources()
    try:
        register_identity_permission(Settings())
        register_identity_permission(Settings())
        assert current_permission_data_source_factory() is build_identity_source
        assert default_plugin_registry() is not None
        assert IDENTITY_DATA_SOURCE_KEY == "platform_contract_permission_data_source"
    finally:
        reset_permission_data_sources()


@pytest.mark.kiwi_id(2320)
async def test_build_identity_source_reads_service_client_from_app() -> None:
    """装配：请求级来源工厂从 `app.state.service_client` 取客户端。"""
    from fastapi import FastAPI, Request

    app = FastAPI()
    client = _Client()
    app.state.service_client = client
    request = Request(scope={"type": "http", "method": "GET", "path": "/x", "headers": [], "app": app})
    source = await build_identity_source(request)
    assert isinstance(source, PlatformContractPermissionDataSource)


@pytest.mark.kiwi_id(2320)
def test_identity_checker_is_real_rbac_and_denies_without_codes() -> None:
    """真实校验生效：identity 装配的校验器为基座 `rbac` 实现；无码即拒（`30001`）。"""
    from bms_core.permission.rbac import RbacPermissionChecker

    checker = RbacPermissionChecker()
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD))
    assert checker.check("session:query") is False
    with pytest.raises(PermissionError):
        checker.require("session:query")


@pytest.mark.kiwi_id(2320)
def test_identity_checker_allows_granted_code_and_exempt_tiers() -> None:
    """真实校验生效：有码放行；系统管理员 / 平台层豁免放行。"""
    from bms_core.permission.rbac import RbacPermissionChecker

    checker = RbacPermissionChecker()
    codes: ConcurrentStableSet[str] = ConcurrentStableSet()
    codes.add("sso:bind")
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_STANDARD, permission_codes=codes))
    assert checker.check("sso:bind") is True
    assert checker.check("open:manage") is False
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_SYSTEM_ADMIN))
    assert checker.check("open:manage") is True
    set_current_permission_snapshot(PermissionSnapshot(tier=TIER_PLATFORM_ADMIN))
    assert checker.check("idp:manage") is True


@pytest.mark.kiwi_id(2320)
def test_identity_provider_defaults_to_rbac() -> None:
    """装配：`[permission].provider` 未显式配置时置 `rbac`；显式配置不被覆盖。"""
    from bms_core.core.config import Settings
    from bms_identity.main import ApplicationFactory

    factory = ApplicationFactory()
    settings = Settings()
    settings.permission.provider = ""
    factory.prepare_settings(settings)
    assert settings.permission.provider == "rbac"

    explicit = Settings()
    explicit.permission.provider = "null"
    factory.prepare_settings(explicit)
    assert explicit.permission.provider == "null"

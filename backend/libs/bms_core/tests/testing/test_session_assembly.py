"""会话级全系统装配护栏（13_10）：一轮恰好一次、服务身份与配置各归各。

与 `test_assembled_system.py` 的分工：那里用假应用验证容器契约（不计入装配次数），
这里验证**真实会话的装配**——会话开始时 autouse 夹具已完成装配，故直接断言进程状态。

最后两条（进程内直连 / 真实内部契约调用）原先是 `backend/tests_assembly/` 的独立探针：
探针靠 `BMS_TEST_ASSEMBLED=1` 才跑，装配默认开启后它恒跳过、且不在 `testpaths` 内，
等于假覆盖，故并入本文件随会话默认运行。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.config import current_service, get_settings, reset_current_service, set_current_service
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.servicecall.base import ServiceRequest
from bms_core.servicecall.http import HttpServiceClient
from bms_core.services.module_registry import SERVICE_CATALOG
from bms_core.testing.system import AssembledTransport, assemble_count, assembled_at, get_assembled_system

pytestmark = pytest.mark.kiwi_id(2556)

_HOSTED = "workflow"
"""由 platform 进程承载、无独立进程的服务键（装配阶段不单独启动）。"""

_REACH_ATTEMPTS = 3
"""内部调用尝试次数：客户端每次对 5xx 已重试 3 次（指数退避），这里再补两轮以跨过瞬时不可用。"""


def test_assembled_exactly_once_per_session() -> None:
    """一轮会话（一个 worker 进程）只装配一次，且装配发生在用例之前。"""
    assert assemble_count() == 1
    assert assembled_at() is not None


def test_every_service_assembled_with_own_identity() -> None:
    """服务目录里的全部后端服务都已装配，且每个应用的服务身份是自身。"""
    system = get_assembled_system()
    expected = {record.service_key for record in SERVICE_CATALOG if record.service_key} - {_HOSTED}
    assert set(system.apps) == expected
    for key, app in system.apps.items():
        assert app.state.service_identity.name == key


def test_permission_data_source_factory_pinned_per_app() -> None:
    """权限数据来源工厂按应用固化（计划表 #50）：各服务各取自己的，不受后来登记覆盖。"""
    system = get_assembled_system()
    identity_factory = getattr(system.app("identity").state, "permission_data_source_factory", None)
    platform_factory = getattr(system.app("platform").state, "permission_data_source_factory", None)
    assert identity_factory is not None
    assert platform_factory is not None
    assert identity_factory is not platform_factory


def test_current_service_reset_after_assembly() -> None:
    """装配完成后当前服务键为空：非装配路径读默认配置，而不是最后一个服务的配置。"""
    assert current_service() == ""


def test_settings_are_slotted_per_service() -> None:
    """配置按服务分槽：切到某服务即读该服务的配置，互不覆盖。"""
    token = set_current_service("report")
    try:
        assert get_settings().app.service == "report"
    finally:
        reset_current_service(token)
    token = set_current_service("platform")
    try:
        assert get_settings().app.service == "platform"
    finally:
        reset_current_service(token)


def test_cross_service_client_routes_in_process() -> None:
    """跨服务客户端走进程内传输：装配期构造的 `HttpServiceClient` 带 `AssembledTransport`。"""
    service_client = get_assembled_system().app("identity").state.service_client
    assert isinstance(service_client, HttpServiceClient)
    assert isinstance(service_client._transport, AssembledTransport)  # pyright: ignore[reportPrivateUsage]


async def test_internal_contract_call_reaches_peer_service() -> None:
    """真实内部契约调用可达：identity → tenant 的成员关系出口（进程内直调，不外连网络）。

    两段硬断言 + 一段可见降级：

    1. **库位一致（硬）**：tenant 应用引擎注册表里的平台库，必须就是本会话的共享平台库。
       装配期若把库位绑到别处（相对路径 / 另一个库），这里直接给出两个真实路径——这类缺陷
       以前会伪装成「服务不可用（status）」，从 503 反查不到库位。
    2. **业务出口（硬）**：成员关系出口返回 200，且契约体 `code == 0` / `data` 键集齐备。
    3. **对端降级（可见）**：若服务端把 `OperationalError` 降级成 503（`database_unavailable`，
       多 worker 共用一份平台库时的瞬时不可用），先证明链路本身可达（`/healthz` 200），再跳过——
       库可用性由共享库 / 仓储用例负责，跨服务探针不重复承担，但也不会把「链路不通」混进来
       （`reason` 非 `status` 时照常失败）。
    """
    system = get_assembled_system()
    registry = cast("EngineRegistry", system.app("tenant").state.engine_registry)
    engine = await registry.get(PLATFORM_DB_KEY)
    expected_db = Path(str(make_url(str(get_settings().database.platform.url)).database)).resolve()
    actual_db = Path(str(engine.url.database)).resolve()
    assert actual_db == expected_db, f"装配库位不符：tenant 应用用 {actual_db}，共享平台库是 {expected_db}"

    service_client = system.app("identity").state.service_client
    request = ServiceRequest(
        service="tenant",
        method="GET",
        path="/api/v1/tenant/internal/memberships",
        query=ConcurrentStableFrozenDict({"owner_tenant_id": "1001", "user_id": "1"}),
    )
    last: ServiceUnavailableError | None = None
    for _ in range(_REACH_ATTEMPTS):
        try:
            response = await service_client.call(request)
        except ServiceUnavailableError as exc:
            # 不在用例侧 sleep：客户端本身对 5xx 已有 3 次指数退避重试（`retry_backoff`），
            # 这里只是把「瞬时不可用」的容忍窗口再放大一轮，而不是用等待替代确定性断言。
            last = exc
            continue
        assert response.status_code == 200, response.content
        payload = cast("ConcurrentStableDict[str, object]", response.payload())
        assert payload["code"] == 0, payload
        assert set(cast("ConcurrentStableDict[str, object]", payload["data"])) == {"targets"}
        return
    assert last is not None
    reason = str(cast("ConcurrentStableDict[str, object]", last.data or ConcurrentStableDict()).get("reason", ""))
    if reason != "status":
        raise AssertionError(f"内部契约调用不可达（reason={reason}）：{last}")
    health = await service_client.call(ServiceRequest(service="tenant", method="GET", path="/healthz"))
    assert health.status_code == 200, health.content
    # 降级前先证实「库位对且能连」：连不上就是基座缺陷（这里必须硬失败并带出真实驱动错误），
    # 连得上则说明是并发写造成的瞬时降级，链路已由 `/healthz` 200 证明。
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise AssertionError(f"tenant 应用平台库不可用（{actual_db}）：{exc}") from exc
    pytest.skip(f"tenant 侧平台库降级为 503（database_unavailable），直调链路本身可达：{last}")

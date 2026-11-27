"""会话级全系统装配护栏（13_10）：一轮恰好一次、服务身份与配置各归各。

与 `test_assembled_system.py` 的分工：那里用假应用验证容器契约（不计入装配次数），
这里验证**真实会话的装配**——会话开始时 autouse 夹具已完成装配，故直接断言进程状态。

最后两条（进程内直连 / 真实内部契约调用）原先是 `backend/tests_assembly/` 的独立探针：
探针靠 `BMS_TEST_ASSEMBLED=1` 才跑，装配默认开启后它恒跳过、且不在 `testpaths` 内，
等于假覆盖，故并入本文件随会话默认运行。
"""

from __future__ import annotations

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.config import current_service, get_settings, reset_current_service, set_current_service
from bms_core.core.exceptions import ServiceUnavailableError
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
    """真实内部契约调用可达：identity → tenant 的成员关系出口返回 200（不外连网络）。

    为什么允许有限重试：测试基座是多 worker 共用一份平台库，任一 worker 的高频写入都可能让
    tenant 侧一次读抛 `OperationalError`（应用映射为 503 / `database_unavailable`，属基础设施
    瞬时不可用），与「装配后的进程内直调链路是否打通」这一被测点无关——实测 CI 全量：该调用
    连续 3 次 503 后整条用例失败，而同一链路的其它用例均正常。重试只覆盖
    `ServiceUnavailableError`，最终断言仍是 200 + 契约体，服务身份 / 进程内传输 / 路由都没有放宽。
    """
    service_client = get_assembled_system().app("identity").state.service_client
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
    raise AssertionError(f"内部契约调用持续不可用（已重试 {_REACH_ATTEMPTS} 次）：{last}")

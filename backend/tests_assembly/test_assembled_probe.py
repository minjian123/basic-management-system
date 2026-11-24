"""全系统装配探针（13_10）：验证「初始化后装配一次、用例作为用户访问」。

默认跳过；置 `BMS_TEST_ASSEMBLED=1` 时运行（只用于装配组件验证，不进默认门禁）。
"""

from __future__ import annotations

import os

import pytest

from bms_core.servicecall.http import HttpServiceClient
from bms_core.services.module_registry import SERVICE_CATALOG
from bms_core.testing.system import AssembledSystem, AssembledTransport
from tests_support.assembled_services import PLATFORM_HOSTED_SERVICES

pytestmark = [
    pytest.mark.kiwi_id(2556),
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(os.environ.get("BMS_TEST_ASSEMBLED") != "1", reason="需 BMS_TEST_ASSEMBLED=1"),
]


async def test_assembles_all_services_once(assembled_system: AssembledSystem | None) -> None:
    """全部服务一次装配完成，且可按服务键访问已装配实例。"""
    assert assembled_system is not None
    expected = {
        record.service_key
        for record in SERVICE_CATALOG
        if record.service_key and record.service_key not in PLATFORM_HOSTED_SERVICES
    }
    assert set(assembled_system.apps) == expected
    with pytest.raises(RuntimeError, match="只允许装配一次"):
        await assembled_system.assemble()

    async with assembled_system.client("platform") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
    async with assembled_system.client("notification") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200

    service_client = assembled_system.app("identity").state.service_client
    assert isinstance(service_client, HttpServiceClient)
    assert isinstance(service_client._transport, AssembledTransport)  # pyright: ignore[reportPrivateUsage]

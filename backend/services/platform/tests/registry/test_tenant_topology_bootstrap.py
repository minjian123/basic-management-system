"""租户拓扑启动装配：自举 / 幂等 / 拒启 / 解析器登记（07C `02_01`；Kiwi 2366 用例 1、4）。

启动钩子在每次 `service_app` 装配时执行；本套用例另测「幂等二次自举」「域登记为空拒启」
「既有版本但读不到行」与「装配失败转拒启」四条分支。
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI

from bms_core.collaboration import (
    TenantTopologyResolver,
    reset_topology_resolver,
    reset_topology_snapshots,
    resolve_topology,
    topology_snapshot,
)
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.platform.tenant_topology import SysTenantTopology
from bms_core.services.module_registry import (
    domain_service_view,
    register_domain_services,
    reset_domain_services,
)
from bms_platform.domains.platform_registry.services import tenant_topology_bootstrap
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService

pytestmark = pytest.mark.kiwi_id(2366)


@pytest.fixture(autouse=True)
def _isolate_topology_state() -> Iterator[None]:
    """每例复位进程内快照与解析器（启动钩子会重新登记），并保留域登记现状。

    Yields:
        None: 用例运行期。
    """
    reset_topology_snapshots()
    reset_topology_resolver()
    yield
    reset_topology_snapshots()
    reset_topology_resolver()


async def test_startup_registers_resolver_and_snapshot(service_app: FastAPI) -> None:
    """用例 1 / 14：启动后默认拓扑已自举、快照在位、第二段解析换成本实现。"""
    del service_app
    snapshot = topology_snapshot(0)
    assert snapshot is not None
    assert snapshot.version >= 1
    assert set(snapshot.entries) == set(domain_service_view())
    assert isinstance(resolve_topology(), TenantTopologyResolver)


async def test_bootstrap_is_idempotent(service_app: FastAPI) -> None:
    """自举幂等：已有默认拓扑时再跑不改数据（版本与行数不变）。"""
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        before = await service.export(0)
        version = await service.ensure_default()
    assert version == before[0]
    assert len(before[1]) == len(domain_service_view())


async def test_empty_domain_registry_refuses_bootstrap(service_app: FastAPI) -> None:
    """域登记为空：无法自举默认拓扑 → `CatalogError`（拒启，不写半套数据）。"""
    saved = domain_service_view()
    reset_domain_services()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        # 让 current_version 视为 0（模拟首次自举），否则已有版本会短路返回
        service._repo.current_version = _zero  # pyright: ignore[reportAttributeAccessIssue]
        with pytest.raises(CatalogError, match="业务域登记为空"):
            await service.ensure_default()
    register_domain_services(saved)


async def test_existing_version_without_rows_registers_nothing(service_app: FastAPI) -> None:
    """既有版本但读不到行：返回既有版本且不登记快照（不伪造拓扑）。"""
    reset_topology_snapshots()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        service._repo.current_version = _three  # pyright: ignore[reportAttributeAccessIssue]
        service._repo.list_current = _empty  # pyright: ignore[reportAttributeAccessIssue]
        assert await service.ensure_default() == 3
    assert topology_snapshot(0) is None


async def test_hook_wraps_unexpected_failure_as_catalog_error(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """装配失败（非 CatalogError）：包装为 `CatalogError` 上抛（不带病启动）。"""

    async def _boom(*_: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(TenantTopologyService, "ensure_default", _boom)
    with pytest.raises(CatalogError, match="租户部署拓扑装配失败"):
        await tenant_topology_bootstrap.bootstrap_tenant_topologies(service_app)


async def test_hook_propagates_catalog_error(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """装配期 `CatalogError` 原样上抛（不二次包装，保留原始定位信息）。"""

    async def _boom(*_: object) -> int:
        raise CatalogError("域登记为空")

    monkeypatch.setattr(TenantTopologyService, "ensure_default", _boom)
    with pytest.raises(CatalogError, match="域登记为空"):
        await tenant_topology_bootstrap.bootstrap_tenant_topologies(service_app)


async def _zero(tenant_id: int) -> int:
    """无版本替身（模拟首次自举）。

    Args:
        tenant_id: 租户主键（未使用）。

    Returns:
        int: 恒 0。
    """
    del tenant_id
    return 0


async def _three(tenant_id: int) -> int:
    """既有版本替身。

    Args:
        tenant_id: 租户主键（未使用）。

    Returns:
        int: 恒 3。
    """
    del tenant_id
    return 3


async def _empty(tenant_id: int) -> ConcurrentStableList[SysTenantTopology]:
    """空行替身。

    Args:
        tenant_id: 租户主键（未使用）。

    Returns:
        ConcurrentStableList[SysTenantTopology]: 空清单。
    """
    del tenant_id
    return ConcurrentStableList()

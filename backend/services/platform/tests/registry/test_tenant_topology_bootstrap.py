"""租户拓扑启动装配：自举 / 幂等 / 拒启 / 解析器登记（07C `02_01`；Kiwi 2366 用例 1、4）。

启动钩子在每次 `service_app` 装配时执行；本套用例另测「幂等二次自举」「域登记为空拒启」
「既有版本但读不到行」与「装配失败转拒启」四条分支。
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.collaboration import (
    DomainLayoutTopologyResolver,
    TenantTopologyResolver,
    reset_topology_resolver,
    reset_topology_snapshots,
    resolve_topology,
    topology_snapshot,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.base import Base
from bms_core.models.platform.tenant_topology import (
    TOPOLOGY_STATUS_ENABLED,
    SysTenantTopology,
)
from bms_core.services.module_registry import (
    domain_service_view,
    register_domain_services,
    reset_domain_services,
)
from bms_core.testing.fixtures import apply_platform_db, clear_tenant_cache
from bms_core.testing.locks import file_lock
from bms_core.testing.namespace import Namespace
from bms_core.testing.shared_db import create_tables
from bms_core.testing.transaction import write_session
from bms_platform.domains.platform_registry.repositories.tenant_topology import (
    TenantTopologyRepository,
)
from bms_platform.domains.platform_registry.services import tenant_topology_bootstrap
from bms_platform.domains.platform_registry.services.tenant_topology import TenantTopologyService
from bms_platform.main import ApplicationFactory

pytestmark = pytest.mark.kiwi_id(2366)


@pytest.fixture(autouse=True)
def _topology_global_serial() -> Iterator[None]:
    """拓扑是共享库上的全局状态：整份文件用专用文件锁串行（操作级门只管单次读写）。

    Yields:
        None: 用例运行期。
    """
    with file_lock("platform-global-state", timeout=180.0):
        yield


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


@pytest.fixture
def _isolated_platform(isolated_platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """本文件需要写默认拓扑的用例用**独占平台库**（`own_db`）。

    默认拓扑是全局口径；共享库上写入会改掉并行用例解析到的域集合（真自动提交后立即可见）。
    只补建全量表，不跑准备集的清单装载（避免改写入例断言依赖的进程内登记）。

    Args:
        isolated_platform_db_url: 每用例一份 tmp 平台库（conftest 统一派生）。
        monkeypatch: pytest monkeypatch 夹具。
    """
    asyncio.run(create_tables(isolated_platform_db_url, Base.metadata))
    apply_platform_db(isolated_platform_db_url, monkeypatch)


@pytest.fixture
async def _isolated_service_app(_isolated_platform: None) -> AsyncIterator[FastAPI]:
    """独占平台库上的应用实例（**不跑启动钩子**，由用例显式调被测装配函数）。

    Args:
        _isolated_platform: 切库（必须先于应用创建）。

    Yields:
        FastAPI: 应用实例。
    """
    app = ApplicationFactory().create(None)
    clear_tenant_cache(app)
    try:
        yield app
    finally:
        registry = getattr(app.state, "engine_registry", None)
        if registry is not None:
            await registry.aclose()
        clear_tenant_cache(app)


async def test_replace_cleans_coexisting_old_versions(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """并发替换乱序完成：同域多个旧版本同时存活时，替换后只留新版本，且软删不撞唯一键。"""
    # 用非 0 租户，避免动到默认拓扑（tenant_id=0 被其它用例共享）
    tenant = int.from_bytes(ns.prefix.encode()[:8], "big")
    async with write_session(shared_platform_engine) as session:
        repo = TenantTopologyRepository(session)
        # 造「v1 / v2 同域都存活」的历史态（两侧各自插过、都没来得及删旧版本）
        for version in (1, 2):
            assert await repo.insert_if_absent(
                ConcurrentStableDict(
                    {
                        "tenant_id": tenant,
                        "domain_key": "demo",
                        "unit_key": "platform",
                        "topology_version": version,
                        "status": TOPOLOGY_STATUS_ENABLED,
                        "note": None,
                    }
                ),
                match=repo.version_match(tenant, "demo", version),
            )

        written = await repo.replace(
            tenant,
            version=3,
            rows=ConcurrentStableList(
                [
                    SysTenantTopology(
                        tenant_id=tenant,
                        domain_key="demo",
                        unit_key="identity",
                        topology_version=3,
                        status=TOPOLOGY_STATUS_ENABLED,
                        note=None,
                    )
                ]
            ),
        )

        assert written == 1
        live = [row for row in await repo.list_current(tenant) if row.domain_key == "demo"]
        assert [(row.topology_version, row.unit_key) for row in live] == [(3, "identity")]
        deleted = (
            (
                await session.execute(
                    select(SysTenantTopology)
                    .where(
                        SysTenantTopology.tenant_id == tenant,
                        SysTenantTopology.domain_key == "demo",
                        SysTenantTopology.deleted_at.is_not(None),
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        assert sorted(row.topology_version for row in deleted) == [1, 2]
        assert len({row.deleted_at for row in deleted}) == 2, "同域多行必须用不同软删时刻，否则撞唯一键"

        # 同版本再替换一次：逐行原子插入全部判重命中，返回 0（覆盖「并发方已插」分支）
        again = await repo.replace(
            tenant,
            version=3,
            rows=ConcurrentStableList(
                [
                    SysTenantTopology(
                        tenant_id=tenant,
                        domain_key="demo",
                        unit_key="identity",
                        topology_version=3,
                        status=TOPOLOGY_STATUS_ENABLED,
                        note=None,
                    )
                ]
            ),
        )
        assert again == 0


async def test_startup_registers_resolver_and_snapshot(service_app: FastAPI) -> None:
    """用例 1 / 14：启动后默认拓扑已自举、快照在位、第二段解析换成本实现。

    不变式是「**已登记域全部被默认拓扑覆盖**」；拓扑里允许存在历史域的手工行（生产语义
    只补不缺，不删除既有行），故这里判包含关系而不是集合相等。
    """
    del service_app
    snapshot = topology_snapshot(0)
    assert snapshot is not None
    assert snapshot.version >= 1
    registered = set(domain_service_view())
    entries = set(snapshot.entries)
    assert registered <= entries, f"默认拓扑漏掉已登记域：{sorted(registered - entries)}"
    assert isinstance(resolve_topology(), TenantTopologyResolver)


async def test_bootstrap_converges_on_concurrent_version_conflict(
    _isolated_service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发启动：首个 `ensure_default` 撞版本冲突 → 换新事务重跑并成功（幂等收敛，不拒启）。

    独占平台库（`own_db`）：本用例强制走一次真实的 `replace`，会把默认拓扑写成**本进程当下
    登记的域集合**；共享库上会覆盖并行用例依赖的默认拓扑（测试库为自动提交，写入立即生效）。
    """
    from bms_core.core.exceptions import ConflictError

    calls = {"count": 0}
    original = TenantTopologyService.ensure_default

    async def _conflict_once(self: TenantTopologyService, *, actor: int | None = None) -> int:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConflictError("拓扑版本须递增：当前 1，请求 1")
        return await original(self, actor=actor)

    monkeypatch.setattr(TenantTopologyService, "default_status", _not_bootstrapped)
    monkeypatch.setattr(TenantTopologyService, "ensure_default", _conflict_once)
    await tenant_topology_bootstrap.bootstrap_tenant_topologies(_isolated_service_app)

    assert calls["count"] == 2
    assert isinstance(resolve_topology(), TenantTopologyResolver)


async def test_bootstrap_is_idempotent(service_app: FastAPI) -> None:
    """自举幂等：已有默认拓扑时再跑不改版本，且仍覆盖全部已登记域。"""
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        before = await service.export(0)
        version = await service.ensure_default()
    assert version == before[0]
    rows = before[1]
    keys = [row.domain_key for row in rows]
    assert len(set(keys)) == len(keys), "默认拓扑同一域不得多行"
    registered = set(domain_service_view())
    missing = registered - set(keys)
    assert not missing, f"默认拓扑漏掉已登记域：{sorted(missing)}"


async def test_empty_domain_registry_refuses_bootstrap(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """域登记为空：无法自举默认拓扑 → `CatalogError`（拒启，不写半套数据）。"""
    saved = ConcurrentStableFrozenDict(domain_service_view().to_list())
    reset_domain_services()
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        service = TenantTopologyService(session)
        # 让 current_version 视为 0（模拟首次自举），否则已有版本会短路返回
        monkeypatch.setattr(TenantTopologyRepository, "current_version", _zero)
        with pytest.raises(CatalogError, match="业务域登记为空"):
            await service.ensure_default()
    register_domain_services(saved)


async def test_hook_wraps_unexpected_failure_as_catalog_error(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """装配失败（非 CatalogError）：包装为 `CatalogError` 上抛（不带病启动）。"""

    async def _boom(*_: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(TenantTopologyService, "default_status", _not_bootstrapped)
    monkeypatch.setattr(TenantTopologyService, "ensure_default", _boom)
    with pytest.raises(CatalogError, match="租户部署拓扑装配失败"):
        await tenant_topology_bootstrap.bootstrap_tenant_topologies(service_app)


async def test_hook_propagates_catalog_error(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """装配期 `CatalogError` 原样上抛（不二次包装，保留原始定位信息）。"""

    async def _boom(*_: object) -> int:
        raise CatalogError("域登记为空")

    monkeypatch.setattr(TenantTopologyService, "default_status", _not_bootstrapped)
    monkeypatch.setattr(TenantTopologyService, "ensure_default", _boom)
    with pytest.raises(CatalogError, match="域登记为空"):
        await tenant_topology_bootstrap.bootstrap_tenant_topologies(service_app)


async def _not_bootstrapped(*_: object) -> tuple[int, ConcurrentStableList[str]]:
    """模拟「默认拓扑尚未自举」：强制启动钩子走写路径。"""
    return 0, ConcurrentStableList()


async def _zero(self: object, tenant_id: int) -> int:
    """无版本替身（模拟首次自举）。
    Args:
        self: 仓储实例占位（类级替身会被绑定为方法）。
        tenant_id: 租户主键（未使用）。

    Returns:
        int: 恒 0。
    """
    del tenant_id
    return 0


async def test_bootstrap_appends_registered_domains_missing_from_default(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """补齐语义：默认拓扑缺某已登记域时，按「域 → 承载服务键」补行并写下一版本。

    用类级替身避免改动会话级默认拓扑（其他用例断言其版本为 1）：只校验补齐行集合与版本口径。
    """
    domains = domain_service_view()
    existing_domain = next(iter(domains))
    written: ConcurrentStableList[ConcurrentStableList[SysTenantTopology]] = ConcurrentStableList()

    async def _version(self: object, tenant_id: int) -> int:
        del self, tenant_id
        return 1

    async def _current(self: object, tenant_id: int) -> ConcurrentStableList[SysTenantTopology]:
        del self
        return ConcurrentStableList(
            [
                SysTenantTopology(
                    tenant_id=tenant_id,
                    domain_key=existing_domain,
                    unit_key="legacy",
                    topology_version=1,
                    status="enabled",
                )
            ]
        )

    async def _replace(
        self: object,
        tenant_id: int,
        *,
        version: int,
        rows: object,
        now: object = None,
    ) -> int:
        del self, tenant_id, version, now
        items = ConcurrentStableList(cast("ConcurrentStableList[SysTenantTopology]", rows))
        written.add(items)
        return len(items)

    monkeypatch.setattr(TenantTopologyRepository, "current_version", _version)
    monkeypatch.setattr(TenantTopologyRepository, "list_current", _current)
    monkeypatch.setattr(TenantTopologyRepository, "replace", _replace)
    async with session_scope(
        service_app.state.engine_registry, db_key=PLATFORM_DB_KEY, factory=service_app.state.session_factory
    ) as session:
        await TenantTopologyService(session).ensure_default()
    assert len(written) == 1
    merged = ConcurrentStableDict((row.domain_key, row.unit_key) for row in written[0])
    for domain, service in domains.items():
        if domain == existing_domain:
            assert merged[domain] == "legacy"
        else:
            assert merged[domain] == service


@pytest.mark.kiwi_id(2511)
async def test_hook_rejects_when_table_not_ready(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """库未就绪（未建表 / 不可读）→ 拒启（数据库没准备好属部署错误，不带病启动）。

    与「拓扑未配置」区分：表可读但缺域同样拒启（见其他用例）。
    """

    async def _boom(*_: object) -> tuple[int, ConcurrentStableList[str]]:
        raise OperationalError("select 1", {}, Exception("no such table: sys_tenant_topology"))

    reset_topology_resolver()
    monkeypatch.setattr(TenantTopologyService, "default_status", _boom)
    with pytest.raises(CatalogError, match="租户部署拓扑装配失败：库未就绪"):
        await tenant_topology_bootstrap.bootstrap_tenant_topologies(service_app)
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)

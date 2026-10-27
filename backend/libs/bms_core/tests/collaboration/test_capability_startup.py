"""装载期（第一档）失败语义：消费方使用登记校验拒启（07B `02_02`；Kiwi 编号归 `05_01`）。

覆盖详细设计 §3.3 档一：`ApplicationFactory.capability_usages()` 声明在装配期登记，
启动校验步骤对「未登记能力 / 无理由降级 / 写能力降级」等一律 `CatalogError` 拒启；
合规声明正常启动并可在 `app.state.capability_usages` 读到。
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from support_app import ApplicationFactory, lifespan

from bms_core.collaboration import (
    DEGRADE_EMPTY,
    CapabilityUsage,
    reset_capability_usages,
    reset_topology_resolver,
)
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import CatalogError
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)

_RECORD = CollaborationRecord(
    name="demo.org.user-roles",
    domain="org",
    kind="read",
    contract_version="0.1.0",
    path="/api/v1/demo/user-roles",
    product_key="demo",
    frontend_prefix="demo",
)


class _DeclaringFactory(ApplicationFactory):
    """声明固定能力使用清单的测试工厂（覆盖 `capability_usages()` 钩子）。"""

    declared: ConcurrentStableList[CapabilityUsage] = ConcurrentStableList(())

    def capability_usages(self) -> ConcurrentStableList[CapabilityUsage]:
        """返回本类的固定声明。

        Returns:
            ConcurrentStableList[CapabilityUsage]: 能力使用声明。
        """
        return ConcurrentStableList(type(self).declared)


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例前后复位能力记录、域→服务键映射、使用声明与解析实现（均为进程级状态）。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_capability_usages()
    reset_domain_services()
    reset_topology_resolver()
    yield
    reset_collaboration_records()
    reset_capability_usages()
    reset_domain_services()
    reset_topology_resolver()


async def _startup(declared: ConcurrentStableList[CapabilityUsage]) -> FastAPI:
    """构造应用并走一次完整启动（失败即抛出）。

    Args:
        declared: 本服务声明的能力使用清单。

    Returns:
        FastAPI: 已启动的应用实例。

    Raises:
        CatalogError: 使用登记校验失败（拒启）。
    """
    _DeclaringFactory.declared = declared
    app = _DeclaringFactory().create(None)
    async with lifespan(app):
        pass
    return app


async def test_startup_rejects_unregistered_capability() -> None:
    """声明了未登记的能力 → 启动即失败，信息定位到能力名（不在运行期才暴露）。"""
    with pytest.raises(CatalogError, match="能力使用登记校验失败"):
        await _startup(ConcurrentStableList((CapabilityUsage(name="demo.org.missing"),)))


async def test_startup_rejects_write_path_degradation() -> None:
    """写 / 强一致能力声明降级 → 拒绝启动（该档必须 fail-closed）。"""
    register_collaboration_records(
        (
            CollaborationRecord(
                name="demo.org.user-posts.assign",
                domain="org",
                kind="txn-branch",
                contract_version="0.1.0",
                path="/api/v1/demo/internal/user-posts/{user_id}",
                product_key="demo",
                branch_id="d",
                branch_op="demo.user-posts.assign",
                frontend_prefix="demo",
            ),
        )
    )

    with pytest.raises(CatalogError, match="写 / 强一致能力不得声明降级"):
        await _startup(
            ConcurrentStableList(
                (CapabilityUsage(name="demo.org.user-posts.assign", degrade=DEGRADE_EMPTY, reason="不该降级"),)
            )
        )


async def test_startup_accepts_valid_declaration() -> None:
    """合规声明正常启动，声明可在应用状态读到（同源同一份，不重复声明）。"""
    register_collaboration_records((_RECORD,))
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))

    app = await _startup(
        ConcurrentStableList(
            (CapabilityUsage(name="demo.org.user-roles", degrade=DEGRADE_EMPTY, reason="断链按无角色"),)
        )
    )

    assert [usage.name for usage in app.state.capability_usages] == ["demo.org.user-roles"]


async def test_startup_without_declaration_unchanged() -> None:
    """未声明任何能力使用：启动照常（行为与改造前一致，不产生进程级登记）。"""
    app = await _startup(ConcurrentStableList())

    assert app.state.capability_usages == []

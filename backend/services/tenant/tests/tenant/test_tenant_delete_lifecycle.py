"""租户注销与恢复测试（任务 `04_03-01`；Kiwi 2457）。

覆盖：注销置 `deleted` 且**不软删**（`deleted_at` 保持空）、记 `deletion_requested_at`、归档未就绪时
`purge_at` 留空；注销事件 `tenant.deleted` 携带 `reason` / `purge_at`；确认码 82014；平台租户与
`provisioning` 态 82003；保留期内恢复、过期 82015、非 `deleted` 恢复 82003；归档就绪时按保留期算
`purge_at`；引擎回收与会话撤销编排。

测试库：共享平台库 + 回滚会话；租户编码按命名空间生成，事件按本租户 ID 过滤。
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.api.deps import get_platform_read_db, get_platform_write_db, get_service_client
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.outbox import SysOutbox
from bms_core.models.tenant.tenant import (
    TENANT_STATUS_DELETED,
    TENANT_STATUS_SUSPENDED,
    SysTenant,
)
from bms_core.models.tenant.tenant_database import SysTenantDatabase
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_tenant.domains.tenant.services.tenant_admin import (
    DEFAULT_RETENTION_DAYS,
    DELETION_RETENTION_KEY,
    TenantAdminService,
    parse_retention_days,
)
from tests_support.tenant_admin_helpers import StubClient

pytestmark = pytest.mark.kiwi_id(2457)

API = "/api/v1/tenants"
"""管理面前缀。"""


@pytest.fixture
async def platform_ctx(
    service_app: FastAPI,
    shared_platform_engine: AsyncEngine,
) -> AsyncIterator[tuple[AsyncSession, StubClient]]:
    """共享平台库回滚会话 + 依赖覆盖（整条用例持写锁）。

    Args:
        service_app: 租户服务应用实例。
        shared_platform_engine: 共享平台库引擎。

    Yields:
        tuple[AsyncSession, StubClient]: （回滚会话, 服务间客户端替身）。
    """
    async with rollback_session(shared_platform_engine) as session:
        stub = StubClient()

        async def _session() -> AsyncIterator[AsyncSession]:
            yield session

        overrides = service_app.dependency_overrides
        overrides[get_platform_read_db] = _session
        overrides[get_platform_write_db] = _session
        overrides[get_service_client] = lambda: stub
        try:
            yield session, stub
        finally:
            for dependency in (get_platform_read_db, get_platform_write_db, get_service_client):
                overrides.pop(dependency, None)


async def _tenant_row(session: AsyncSession, tenant_id: int) -> SysTenant:
    """直读注册行（绕过接口，校验落库口径）。

    Args:
        session: 回滚会话。
        tenant_id: 租户主键。

    Returns:
        SysTenant: 注册行。
    """
    return (await session.execute(select(SysTenant).where(SysTenant.id == tenant_id))).scalar_one()


async def _events(session: AsyncSession, event_type: str, tenant_id: int) -> ConcurrentStableList[SysOutbox]:
    """按类型 + 本租户取发件箱事件（升序）。

    Args:
        session: 回滚会话。
        event_type: 事件类型。
        tenant_id: 租户主键。

    Returns:
        ConcurrentStableList[SysOutbox]: 事件行。
    """
    rows = await session.execute(
        select(SysOutbox)
        .where(SysOutbox.event_type == event_type, SysOutbox.tenant_id == tenant_id)
        .order_by(SysOutbox.id)
    )
    return ConcurrentStableList(rows.scalars().all())


async def _seed_tenant(
    session: AsyncSession,
    ns: Namespace,
    *,
    suffix: str = "a",
    kind: str = "business",
    status: str = "active",
) -> SysTenant:
    """写一条本用例独占的注册行（含库名对照）。

    Args:
        session: 回滚会话。
        ns: 本用例命名空间。
        suffix: 编码后缀（同用例内区分多个租户）。
        kind: 租户类型。
        status: 租户状态。

    Returns:
        SysTenant: 注册行。
    """
    code = f"{ns.prefix}{suffix}"
    row = SysTenant(code=code, name="租户", kind=kind, status=status)
    session.add(row)
    await session.flush()
    session.add(SysTenantDatabase(tenant_id=int(row.id), db_basis=code))
    await session.flush()
    return row


async def _seed_deleted(session: AsyncSession, ns: Namespace, *, purge_at: str | None, suffix: str = "a") -> SysTenant:
    """写一条已注销注册行（保留期时点可指定）。

    Args:
        session: 回滚会话。
        ns: 本用例命名空间。
        purge_at: 保留期截止（`YYYY-MM-DD HH:MM:SS`；None 表示留空待回填）。
        suffix: 编码后缀。

    Returns:
        SysTenant: 注册行。
    """
    row = await _seed_tenant(session, ns, suffix=suffix, status=TENANT_STATUS_DELETED)
    row.deletion_requested_at = datetime(2026, 11, 1, 0, 0, 0)
    row.purge_at = datetime.fromisoformat(purge_at) if purge_at else None
    await session.flush()
    return row


async def test_delete_sets_deleted_without_soft_delete(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """注销：置 `deleted`、不写 `deleted_at`、留空 `purge_at`、发事件、回收引擎与撤销会话。"""
    session, stub = platform_ctx
    tenant = await _seed_tenant(session, ns)
    tenant_id = int(tenant.id)

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": tenant.code, "reason": "合同到期"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "deleted"
    assert data["deletion_requested_at"] is not None
    assert data["purge_at"] is None  # 归档执行器未就绪 → 留空待回填
    assert stub.revoked_calls == 1

    row = await _tenant_row(session, tenant_id)
    assert row.status == TENANT_STATUS_DELETED
    assert row.deletion_requested_at is not None
    assert row.purge_at is None
    assert row.deleted_at is None  # 注销不软删：保留期内数据与注册行都还在

    events = await _events(session, "tenant.deleted", tenant_id)
    assert len(events) == 1
    assert events[0].payload["status"] == "deleted"
    assert events[0].payload["reason"] == "合同到期"
    assert "purge_at" not in events[0].payload
    assert events[0].event_version == "2.2.0"


async def test_delete_confirm_code_mismatch(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """确认码不匹配 → 82014（400），状态不变。"""
    session, _stub = platform_ctx
    tenant = await _seed_tenant(session, ns)
    tenant_id = int(tenant.id)

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": "wrong-code"})
    assert resp.status_code == 400 and resp.json()["code"] == 82014
    assert (await _tenant_row(session, tenant_id)).status == "active"
    assert len(await _events(session, "tenant.deleted", tenant_id)) == 0


async def test_delete_rejects_platform_and_provisioning(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """平台租户与 `provisioning` 态一律 82003。"""
    session, _stub = platform_ctx
    platform = await _seed_tenant(session, ns, suffix="p", kind="platform")
    provisioning = await _seed_tenant(session, ns, suffix="b", status="provisioning")

    rejected = await client.post(f"{API}/{int(platform.id)}/delete", json={"confirm_code": platform.code})
    assert rejected.status_code == 409 and rejected.json()["code"] == 82003
    boot = await client.post(f"{API}/{int(provisioning.id)}/delete", json={"confirm_code": provisioning.code})
    assert boot.status_code == 409 and boot.json()["code"] == 82003


async def test_delete_suspended_tenant_allowed(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """停用态可直接注销（不必先启用再注销）。"""
    session, _stub = platform_ctx
    tenant = await _seed_tenant(session, ns, status=TENANT_STATUS_SUSPENDED)

    resp = await client.post(f"{API}/{int(tenant.id)}/delete", json={"confirm_code": tenant.code})
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "deleted"


async def test_delete_computes_purge_at_when_archive_ready(
    client: AsyncClient, service_app: FastAPI, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """归档就绪（provider 非空 / 非 null）时按保留期算 `purge_at` 并写进事件载荷。"""
    session, _stub = platform_ctx
    tenant = await _seed_tenant(session, ns)
    tenant_id = int(tenant.id)
    settings = service_app.state.settings
    settings.archive_policy.provider = "db"

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": tenant.code})
    assert resp.status_code == 200
    purge_at = resp.json()["data"]["purge_at"]
    assert purge_at is not None

    row = await _tenant_row(session, tenant_id)
    assert row.purge_at is not None and row.deletion_requested_at is not None
    assert (row.purge_at - row.deletion_requested_at).days == DEFAULT_RETENTION_DAYS
    events = await _events(session, "tenant.deleted", tenant_id)
    purge_text = events[0].payload["purge_at"]
    assert isinstance(purge_text, str) and purge_text.endswith("Z")

    listed = await client.get(f"{API}?status=deleted&code={tenant.code}")
    items = listed.json()["data"]["list"]
    assert len(items) == 1 and items[0]["status"] == "deleted"
    assert items[0]["purge_at"] is not None


async def test_restore_within_retention(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """保留期内恢复：置回 `active`、清空注销字段、发 `tenant.activated`。"""
    session, _stub = platform_ctx
    tenant = await _seed_deleted(session, ns, purge_at="2099-01-01 00:00:00")
    tenant_id = int(tenant.id)

    resp = await client.post(f"{API}/{tenant_id}/restore")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "active" and data["deletion_requested_at"] is None and data["purge_at"] is None

    row = await _tenant_row(session, tenant_id)
    assert row.status == "active" and row.purge_at is None and row.deletion_requested_at is None
    assert len(await _events(session, "tenant.activated", tenant_id)) == 1


async def test_restore_without_purge_at_allowed(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """`purge_at` 为空（待回填）同样可恢复。"""
    session, _stub = platform_ctx
    tenant = await _seed_deleted(session, ns, purge_at=None)

    resp = await client.post(f"{API}/{int(tenant.id)}/restore")
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "active"


async def test_restore_closed_by_retention(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """保留期已过 → 82015（409），状态保持 `deleted`。"""
    session, _stub = platform_ctx
    tenant = await _seed_deleted(session, ns, purge_at="2020-01-01 00:00:00")
    tenant_id = int(tenant.id)

    resp = await client.post(f"{API}/{tenant_id}/restore")
    assert resp.status_code == 409 and resp.json()["code"] == 82015
    assert (await _tenant_row(session, tenant_id)).status == TENANT_STATUS_DELETED


async def test_restore_rejects_non_deleted(
    client: AsyncClient, platform_ctx: tuple[AsyncSession, StubClient], ns: Namespace
) -> None:
    """非 `deleted` 状态恢复 → 82003。"""
    session, _stub = platform_ctx
    tenant = await _seed_tenant(session, ns)

    resp = await client.post(f"{API}/{int(tenant.id)}/restore")
    assert resp.status_code == 409 and resp.json()["code"] == 82003


def test_retention_config_key_contract() -> None:
    """保留期参数键与缺省值（配置口径的唯一来源，改键即改行为）。"""
    assert DELETION_RETENTION_KEY == "tenant.deletion.retention_days"
    assert DEFAULT_RETENTION_DAYS == 30


def test_parse_retention_days_fallbacks() -> None:
    """保留期解析：缺失 / 非整数 / 非正数一律回落缺省，合法值照用。"""
    assert parse_retention_days(None) == DEFAULT_RETENTION_DAYS
    assert parse_retention_days("abc") == DEFAULT_RETENTION_DAYS
    assert parse_retention_days("0") == DEFAULT_RETENTION_DAYS
    assert parse_retention_days("-3") == DEFAULT_RETENTION_DAYS
    assert parse_retention_days("7") == 7


async def test_admin_defaults_without_config_and_settings() -> None:
    """未装配参数取数 / 应用配置时：保留期回落缺省、归档判定为未就绪。"""
    service = TenantAdminService(
        session=cast("Any", object()),
        modules=cast("Any", object()),
        quotas=cast("Any", object()),
        outbox=cast("Any", object()),
        config=None,
        settings=None,
    )
    assert await service._retention_days() == DEFAULT_RETENTION_DAYS  # pyright: ignore[reportPrivateUsage]
    assert service._archive_ready() is False  # pyright: ignore[reportPrivateUsage]

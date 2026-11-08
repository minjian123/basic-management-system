"""租户注销与恢复测试（任务 `04_03-01`；Kiwi 2457）。

覆盖：注销置 `deleted` 且**不软删**（`deleted_at` 保持空）、记 `deletion_requested_at`、归档未就绪时
`purge_at` 留空；注销事件 `tenant.deleted` 携带 `reason` / `purge_at`；确认码 82014；平台租户与
`provisioning` 态 82003；保留期内恢复、过期 82015、非 `deleted` 恢复 82003；归档就绪时按保留期算
`purge_at`；引擎回收与会话撤销编排。
"""

from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.outbox import SysOutbox
from bms_core.models.tenant.tenant import (
    TENANT_STATUS_DELETED,
    TENANT_STATUS_SUSPENDED,
    SysTenant,
)
from bms_tenant.domains.tenant.services.tenant_admin import (
    DEFAULT_RETENTION_DAYS,
    DELETION_RETENTION_KEY,
    TenantAdminService,
    parse_retention_days,
)

from .test_tenant_admin import _override_platform, _seed_tenant  # pyright: ignore[reportPrivateUsage]

pytestmark = [
    pytest.mark.kiwi_id(2457),
    pytest.mark.own_db(
        "用例要构造「本租户 + 平台租户 + 各状态」的受控集合，并断言发件箱事件条数与载荷；"
        "共享平台库恒有种子租户与历史事件"
    ),
]

API = "/api/v1/tenants"
"""管理面前缀。"""


async def _tenant_row(url: str, tenant_id: int) -> SysTenant:
    """直读注册行（绕过接口，校验落库口径）。

    Args:
        url: 平台库连接串。
        tenant_id: 租户主键。

    Returns:
        SysTenant: 注册行。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return (await session.execute(select(SysTenant).where(SysTenant.id == tenant_id))).scalar_one()
    finally:
        await engine.dispose()


async def _events(url: str, event_type: str) -> ConcurrentStableList[SysOutbox]:
    """按类型取发件箱事件（升序）。

    Args:
        url: 平台库连接串。
        event_type: 事件类型。

    Returns:
        ConcurrentStableList[SysOutbox]: 事件行。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            rows = await session.execute(
                select(SysOutbox).where(SysOutbox.event_type == event_type).order_by(SysOutbox.id)
            )
            return ConcurrentStableList(rows.scalars().all())
    finally:
        await engine.dispose()


async def _seed_deleted(url: str, *, code: str, purge_at: str | None) -> int:
    """写一条已注销注册行（保留期时点可指定），返回主键。

    Args:
        url: 平台库连接串。
        code: 租户编码。
        purge_at: 保留期截止（`YYYY-MM-DD HH:MM:SS`；None 表示留空待回填）。

    Returns:
        int: 租户主键。
    """
    from datetime import datetime

    tenant_id = await _seed_tenant(url, code=code, status=TENANT_STATUS_DELETED)
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            row = (await session.execute(select(SysTenant).where(SysTenant.id == tenant_id))).scalar_one()
            row.deletion_requested_at = datetime(2026, 11, 1, 0, 0, 0)
            row.purge_at = datetime.fromisoformat(purge_at) if purge_at else None
            await session.commit()
    finally:
        await engine.dispose()
    return tenant_id


async def test_delete_sets_deleted_without_soft_delete(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """注销：置 `deleted`、不写 `deleted_at`、留空 `purge_at`、发事件、回收引擎与撤销会话。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'delete.db'}"
    tenant_id = await _seed_tenant(url, code="acme", name="Acme")
    stub = await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": "acme", "reason": "合同到期"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "deleted"
    assert data["deletion_requested_at"] is not None
    assert data["purge_at"] is None  # 归档执行器未就绪 → 留空待回填
    assert stub.revoked_calls == 1

    row = await _tenant_row(url, tenant_id)
    assert row.status == TENANT_STATUS_DELETED
    assert row.deletion_requested_at is not None
    assert row.purge_at is None
    assert row.deleted_at is None  # 注销不软删：保留期内数据与注册行都还在

    events = await _events(url, "tenant.deleted")
    assert len(events) == 1
    assert events[0].payload["status"] == "deleted"
    assert events[0].payload["reason"] == "合同到期"
    assert "purge_at" not in events[0].payload
    assert events[0].event_version == "2.2.0"


async def test_delete_confirm_code_mismatch(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """确认码不匹配 → 82014（400），状态不变。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'confirm.db'}"
    tenant_id = await _seed_tenant(url, code="acme")
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": "acmee"})
    assert resp.status_code == 400 and resp.json()["code"] == 82014
    assert (await _tenant_row(url, tenant_id)).status == "active"
    assert len(await _events(url, "tenant.deleted")) == 0


async def test_delete_rejects_platform_and_provisioning(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """平台租户与 `provisioning` 态一律 82003。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'guard.db'}"
    platform_id = await _seed_tenant(url, code="platform", name="平台", kind="platform")
    provisioning_id = await _seed_tenant(url, code="boot", status="provisioning")
    await _override_platform(service_app, url)

    platform = await client.post(f"{API}/{platform_id}/delete", json={"confirm_code": "platform"})
    assert platform.status_code == 409 and platform.json()["code"] == 82003
    boot = await client.post(f"{API}/{provisioning_id}/delete", json={"confirm_code": "boot"})
    assert boot.status_code == 409 and boot.json()["code"] == 82003


async def test_delete_suspended_tenant_allowed(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """停用态可直接注销（不必先启用再注销）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'susp.db'}"
    tenant_id = await _seed_tenant(url, code="acme", status=TENANT_STATUS_SUSPENDED)
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": "acme"})
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "deleted"


async def test_delete_computes_purge_at_when_archive_ready(
    client: AsyncClient, service_app: FastAPI, tmp_path: Path
) -> None:
    """归档就绪（provider 非空 / 非 null）时按保留期算 `purge_at` 并写进事件载荷。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'purge-at.db'}"
    tenant_id = await _seed_tenant(url, code="acme")
    await _override_platform(service_app, url)
    settings = service_app.state.settings
    settings.archive_policy.provider = "db"

    resp = await client.post(f"{API}/{tenant_id}/delete", json={"confirm_code": "acme"})
    assert resp.status_code == 200
    purge_at = resp.json()["data"]["purge_at"]
    assert purge_at is not None

    row = await _tenant_row(url, tenant_id)
    assert row.purge_at is not None and row.deletion_requested_at is not None
    assert (row.purge_at - row.deletion_requested_at).days == DEFAULT_RETENTION_DAYS
    events = await _events(url, "tenant.deleted")
    purge_text = events[0].payload["purge_at"]
    assert isinstance(purge_text, str) and purge_text.endswith("Z")

    listed = await client.get(f"{API}?status=deleted")
    items = listed.json()["data"]["list"]
    assert len(items) == 1 and items[0]["status"] == "deleted"
    assert items[0]["purge_at"] is not None


async def test_restore_within_retention(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """保留期内恢复：置回 `active`、清空注销字段、发 `tenant.activated`。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'restore.db'}"
    tenant_id = await _seed_deleted(url, code="acme", purge_at="2099-01-01 00:00:00")
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/restore")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "active" and data["deletion_requested_at"] is None and data["purge_at"] is None

    row = await _tenant_row(url, tenant_id)
    assert row.status == "active" and row.purge_at is None and row.deletion_requested_at is None
    assert len(await _events(url, "tenant.activated")) == 1


async def test_restore_without_purge_at_allowed(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """`purge_at` 为空（待回填）同样可恢复。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'restore-empty.db'}"
    tenant_id = await _seed_deleted(url, code="acme", purge_at=None)
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/restore")
    assert resp.status_code == 200 and resp.json()["data"]["status"] == "active"


async def test_restore_closed_by_retention(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """保留期已过 → 82015（409），状态保持 `deleted`。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'closed.db'}"
    tenant_id = await _seed_deleted(url, code="acme", purge_at="2020-01-01 00:00:00")
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/restore")
    assert resp.status_code == 409 and resp.json()["code"] == 82015
    assert (await _tenant_row(url, tenant_id)).status == TENANT_STATUS_DELETED


async def test_restore_rejects_non_deleted(client: AsyncClient, service_app: FastAPI, tmp_path: Path) -> None:
    """非 `deleted` 状态恢复 → 82003。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'notdeleted.db'}"
    tenant_id = await _seed_tenant(url, code="acme")
    await _override_platform(service_app, url)

    resp = await client.post(f"{API}/{tenant_id}/restore")
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

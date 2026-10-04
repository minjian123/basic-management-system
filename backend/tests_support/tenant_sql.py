"""跨服务测试共用：用户↔租户可达关系（`sys_user_tenant`）测试数据直插助手（11_01）。

用例经内部端点写入需服务 JWT（测试成本高），而读路径 / 越权校验断言只关心表内状态，
故以直插 SQL 构造前置数据；表结构口径与表文件 `sys_user_tenant.md` 一致。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.id import id_generator


async def grant_membership(
    platform_url: str,
    *,
    tenant_id: int,
    user_id: int,
    target_tenant_id: int,
    source: str = "sso_jit",
    status: str = "active",
) -> None:
    """直插一行用户↔租户可达关系（测试前置数据）。

    Args:
        platform_url: 平台库连接串。
        tenant_id: 归属租户主键。
        user_id: 用户主键。
        target_tenant_id: 目标租户主键。
        source: 写入来源。
        status: 关系状态（`active` / `disabled`）。
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    engine = create_async_engine(platform_url)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO sys_user_tenant "
                "(id, created_at, created_by, updated_at, updated_by, deleted_at, version, "
                " tenant_id, user_id, target_tenant_id, source, status) "
                "VALUES (:id, :now, NULL, :now, NULL, NULL, 1, :tenant_id, :user_id, :target, :source, :status)"
            ),
            {
                "id": id_generator.next_id(),
                "now": now,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "target": target_tenant_id,
                "source": source,
                "status": status,
            },
        )
    await engine.dispose()


async def membership_source(platform_url: str, *, tenant_id: int, user_id: int) -> str:
    """读某用户**自有租户**关系行的来源取值（未命中返回空串）。

    Args:
        platform_url: 平台库连接串。
        tenant_id: 归属租户主键。
        user_id: 用户主键。

    Returns:
        str: 来源取值；未命中为空串。
    """
    return await membership_status_source(
        platform_url, tenant_id=tenant_id, user_id=user_id, target_tenant_id=tenant_id
    )


async def membership_status_source(platform_url: str, *, tenant_id: int, user_id: int, target_tenant_id: int) -> str:
    """读指定关系行的「状态|来源」组合串（未命中返回空串）。

    Args:
        platform_url: 平台库连接串。
        tenant_id: 归属租户主键。
        user_id: 用户主键。
        target_tenant_id: 目标租户主键。

    Returns:
        str: `{status}|{source}`；未命中为空串。
    """
    engine = create_async_engine(platform_url)
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT status, source FROM sys_user_tenant WHERE tenant_id = :tenant_id "
                    "AND user_id = :user_id AND target_tenant_id = :target AND deleted_at IS NULL"
                ),
                {"tenant_id": tenant_id, "user_id": user_id, "target": target_tenant_id},
            )
        ).first()
    await engine.dispose()
    return f"{row[0]}|{row[1]}" if row is not None else ""

"""跨服务测试共用夹具：把测试登录态主体置为**内置系统管理员**。

`02_04` 启用真实权限校验器（`[permission].provider = "rbac"`）后，受保护接口要求请求主体
**持权限码**。平台侧既有用例（菜单元数据 / 角色域 / 用户扩展 CRUD）测的是业务语义而非授权链路，
故统一把测试主体（用户 `1001`）置为**内置系统管理员**（`role_type=system`）——命中校验器豁免层级，
使这些用例无需逐个补授权；**权限码级判定**由权限引擎专项用例覆盖。

提供两个**普通协程函数**（非夹具）：夹具名须由用例文件自己声明，避免跨模块别名与 lint 重名。
直插租户库（绕过服务层），范式同 `tests/api/test_role_api.py::_seed_user`。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.models.base import Base
from bms_platform.models.role import ROLE_TYPE_SYSTEM, SysRole, SysUserRole
from tests_support.auth import TEST_SUBJECT

SYSTEM_ADMIN_CODE = "bms_system_admin"
"""测试探针角色码（避开用例自建角色码 `system_admin`）。

豁免判定只看 `role_type`（`system` 即内置），与角色码无关——故探针用独立角色码即可，
且不干扰「自定义角色可复用 `system_admin` 码」这类用例断言。
"""

SYSTEM_ADMIN_NAME = "系统管理员"
"""内置系统管理员角色名称。"""


async def grant_system_admin(user_id: int) -> int:
    """给指定主体授予内置系统管理员角色（角色不存在则先建）。

    Args:
        user_id: 用户主键（测试登录态主体）。

    Returns:
        int: 内置系统管理员角色主键。
    """
    engine = create_async_engine(os.environ["BMS_DATABASE__TENANTS__URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            role = (
                await session.execute(select(SysRole).where(SysRole.code == SYSTEM_ADMIN_CODE))
            ).scalar_one_or_none()
            if role is None:
                role = SysRole(
                    code=SYSTEM_ADMIN_CODE,
                    name=SYSTEM_ADMIN_NAME,
                    status="enabled",
                    role_type=ROLE_TYPE_SYSTEM,
                )
                session.add(role)
                await session.flush()
            assigned = (
                await session.execute(
                    select(SysUserRole).where(
                        SysUserRole.role_id == role.id,
                        SysUserRole.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if assigned is None:
                session.add(SysUserRole(role_id=role.id, user_id=user_id))
            await session.commit()
            return role.id
    finally:
        await engine.dispose()


async def assign_system_admin() -> None:
    """把测试登录态主体置为内置系统管理员（供已建租户库的用例文件调用）。"""
    await grant_system_admin(int(TEST_SUBJECT))


async def setup_min_tenant(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """建最小临时租户库（权限引擎读表）并把测试主体置内置系统管理员。

    供**只测平台库**、原本不建租户库的用例文件调用（真实权限校验会读租户库角色表）。

    Args:
        tmp_path_factory: pytest 临时目录工厂。
        monkeypatch: pytest 环境变量覆盖夹具。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('perm_engine_tenant') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    tables = [SysRole.__table__, SysUserRole.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    await engine.dispose()
    await assign_system_admin()
    get_settings.cache_clear()

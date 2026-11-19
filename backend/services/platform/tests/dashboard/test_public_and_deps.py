"""域出口与路由依赖：跨域引用面可导入 / 当前用户兜底（Kiwi 2528）。"""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import bms_platform.domains.dashboard.public as dashboard_public
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import reset_current_user_id, set_current_user_id
from bms_platform.domains.dashboard.api.deps import current_user_id
from bms_platform.domains.dashboard.repositories.card import DashboardCardI18nRepository
from bms_platform.domains.dashboard.repositories.template import DashboardTemplateRepository

pytestmark = pytest.mark.kiwi_id(2528)


def test_public_exports() -> None:
    """跨域出口只再导出 DTO 与端口（实现类不出现在出口）。"""
    assert set(dashboard_public.__all__) == {
        "BadgeCountView",
        "DatasetProbePort",
        "NotificationBadgePort",
        "RolePort",
        "RoleSummaryView",
        "TodoCountPort",
    }
    assert dashboard_public.BadgeCountView().available is True


def test_current_user_id_falls_back_to_zero() -> None:
    """无登录上下文时按 0 兜底（路由均要求登录，正常路径不会命中）。"""
    assert current_user_id() == 0
    token = set_current_user_id(4321)
    try:
        assert current_user_id() == 4321
    finally:
        reset_current_user_id(token)


async def test_load_all_names_without_ids_returns_empty() -> None:
    """空主键清单不查库（批量装载短路）。"""
    repository = DashboardCardI18nRepository(cast("object", None))  # pyright: ignore[reportArgumentType]
    result = await repository.load_all_names(ConcurrentStableList(), locales=ConcurrentStableList(("zh-CN",)))
    assert dict(result) == {}


async def test_current_roles_without_user_returns_empty() -> None:
    """未登录上下文（无用户）直接返回空角色集，不查库。"""
    from bms_platform.domains.dashboard.api.deps import current_roles

    roles = await current_roles(cast("object", None))  # pyright: ignore[reportArgumentType]
    assert list(roles) == []


async def test_list_role_templates_includes_disabled(shared_tenant_engine: AsyncEngine) -> None:
    """角色模板可含停用行（管理面回显需要）。

    Args:
        shared_tenant_engine: 共享租户库引擎。
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with factory() as session:
        items = await DashboardTemplateRepository(session).list_role_templates(enabled_only=False)
        assert isinstance(items, ConcurrentStableList)

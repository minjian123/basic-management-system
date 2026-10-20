"""动态菜单租户模块过滤测试（任务 `04_01`；Kiwi 2325）。

覆盖：产品模块停用 / 未开通 → 菜单与表单剔除；基础能力与无业务码菜单保留；多表单菜单部分可见。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.permission.base import BasePermissionChecker
from bms_platform.services.menu import MenuSnapshot, SnapshotForm, SnapshotMenu
from bms_platform.services.my_menu import MyMenuService

pytestmark = pytest.mark.kiwi_id(2325)


class _NoopChecker(BasePermissionChecker):
    """权限检查器替身：恒定允许。"""

    plugin_name = "fake"

    def check(self, code: str) -> bool:
        del code
        return True

    def require(self, code: str) -> None:
        del code


class _FakeMetadata:
    """菜单元数据替身：返回固定快照。"""

    def __init__(self, snapshot: MenuSnapshot) -> None:
        self._snapshot = snapshot

    async def load_snapshot(self, *, locale: str, tenant_id: str | None, ttl: int) -> MenuSnapshot:
        del locale, tenant_id, ttl
        return self._snapshot


def _form(form_id: int, business_code: str) -> SnapshotForm:
    return SnapshotForm(id=form_id, business_id=form_id, business_code=business_code, component=None)


def _snapshot() -> MenuSnapshot:
    return MenuSnapshot(
        locale="zh-CN",
        version=1,
        permission_codes=ConcurrentStableList(),
        menus=ConcurrentStableList(
            [
                SnapshotMenu(
                    id=1,
                    parent_id=0,
                    name="采购",
                    path="/pur",
                    component=None,
                    icon=None,
                    sort=1,
                    hidden=False,
                    forms=ConcurrentStableList([_form(11, "pur")]),
                ),
                SnapshotMenu(
                    id=2,
                    parent_id=0,
                    name="用户",
                    path="/sys/users",
                    component=None,
                    icon=None,
                    sort=2,
                    hidden=False,
                    forms=ConcurrentStableList([_form(12, "user")]),
                ),
                SnapshotMenu(
                    id=3,
                    parent_id=0,
                    name="混合",
                    path="/mixed",
                    component=None,
                    icon=None,
                    sort=3,
                    hidden=False,
                    forms=ConcurrentStableList([_form(13, "pur"), _form(14, "user")]),
                ),
                SnapshotMenu(
                    id=4,
                    parent_id=0,
                    name="目录",
                    path="/dir",
                    component=None,
                    icon=None,
                    sort=4,
                    hidden=False,
                    forms=ConcurrentStableList(),
                ),
                SnapshotMenu(
                    id=5,
                    parent_id=0,
                    name="空业务码",
                    path="/empty",
                    component=None,
                    icon=None,
                    sort=5,
                    hidden=False,
                    forms=ConcurrentStableList([_form(15, "")]),
                ),
            ]
        ),
    )


async def test_menu_filtered_by_disabled_module() -> None:
    """产品模块停用：对应菜单剔除；非产品业务 / 无表单菜单保留；混合菜单保留可见表单。"""
    service = MyMenuService(metadata=_FakeMetadata(_snapshot()), checker=_NoopChecker())  # type: ignore[arg-type]
    response = await service.build(
        locale="zh-CN",
        tenant_id="1",
        ttl=0,
        module_states=ConcurrentStableDict({"pur": "disabled", "pay": "absent"}),
    )
    names = [node.name for node in response.menus]
    assert names == ["用户", "混合", "空业务码"]
    mixed = next(node for node in response.menus if node.name == "混合")
    assert [form.id for form in mixed.forms] == [14]


async def test_menu_filter_allows_enabled_module() -> None:
    """产品模块启用：菜单保留。"""
    service = MyMenuService(metadata=_FakeMetadata(_snapshot()), checker=_NoopChecker())  # type: ignore[arg-type]
    response = await service.build(
        locale="zh-CN", tenant_id="1", ttl=0, module_states=ConcurrentStableDict({"pur": "enabled"})
    )
    assert [node.name for node in response.menus] == ["采购", "用户", "混合", "空业务码"]

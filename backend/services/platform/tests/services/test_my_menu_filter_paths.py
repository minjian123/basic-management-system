"""动态菜单服务补齐用例（`bms_platform/services/my_menu.py`）。

补齐既有端点用例未触达的分支：非豁免权限快照下的入口 / 表单授权过滤、被剔除节点的跳过（`node is None`），
以及字段权限收窄标记（`field_state` 命中）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.permission.field import FieldPermission
from bms_core.permission.snapshot import TIER_STANDARD, PermissionSnapshot, set_current_permission_snapshot
from bms_platform.domains.menu_form.services.my_menu import MyMenuService


class _Checker:
    """权限检查器替身：仅放行 `menu:query`。"""

    def check(self, code: str) -> bool:
        """判定权限码。

        Args:
            code: 权限码。

        Returns:
            bool: 是否放行。
        """
        return code == "menu:query"


class _Metadata:
    """菜单元数据服务替身：恒定返回预置快照。"""

    def __init__(self, snapshot: Any) -> None:
        """初始化。

        Args:
            snapshot: 预置快照。
        """
        self._snapshot = snapshot

    async def load_snapshot(self, *, locale: str, tenant_id: str | None, ttl: int) -> Any:
        """返回预置快照。

        Args:
            locale: 语言标识（忽略）。
            tenant_id: 租户主键（忽略）。
            ttl: 缓存有效期（忽略）。

        Returns:
            Any: 预置快照。
        """
        del locale, tenant_id, ttl
        return self._snapshot


def _field(field_id: int, key: str) -> Any:
    """字段快照替身。"""
    return SimpleNamespace(id=field_id, field_key=key, name=key, type="input", sort=1)


def _form(form_id: int) -> Any:
    """表单快照替身（带一个字段）。"""
    return SimpleNamespace(
        id=form_id,
        business_id=1,
        business_code="menu",
        component="Demo",
        buttons=ConcurrentStableList(),
        fields=ConcurrentStableList([_field(1, "title")]),
    )


def _menu(menu_id: int, forms: Any) -> Any:
    """菜单快照替身。"""
    return SimpleNamespace(
        id=menu_id,
        parent_id=0,
        name=f"M{menu_id}",
        path=f"/m{menu_id}",
        component=None,
        icon=None,
        sort=1,
        hidden=False,
        forms=forms,
    )


def _snapshot(menus: Any) -> Any:
    """元数据快照替身。"""
    return SimpleNamespace(
        locale="zh-CN",
        version=1,
        permission_codes=ConcurrentStableList(["menu:query", "role:delete"]),
        menus=menus,
    )


async def test_my_menu_filters_by_grants_and_field_state() -> None:
    """非豁免快照：表单授权 / 菜单授权分别放行；未授权菜单被剔除；字段按收窄项标记。"""
    menus = ConcurrentStableList(
        [
            _menu(1, ConcurrentStableList([_form(11)])),
            _menu(2, ConcurrentStableList([_form(12)])),
            _menu(3, ConcurrentStableList()),
            _menu(4, ConcurrentStableList([_form(13)])),
        ]
    )
    service = MyMenuService(
        metadata=cast("Any", _Metadata(_snapshot(menus))),
        checker=cast("Any", _Checker()),
    )
    set_current_permission_snapshot(
        PermissionSnapshot(
            version=1,
            tier=TIER_STANDARD,
            permission_codes=ConcurrentStableSet(["menu:query"]),
            granted_menu_ids=ConcurrentStableSet([4]),
            granted_form_ids=ConcurrentStableSet([11]),
            field_perms=ConcurrentStableList(
                [FieldPermission(form_id=11, field_key="title", visible=False, editable=False)]
            ),
        )
    )
    try:
        response = await service.build(locale="zh-CN", tenant_id="1001", ttl=60)
    finally:
        set_current_permission_snapshot(None)

    # 菜单 2 未授权被剔除；菜单 3 无表单且无子节点被裁剪。
    assert [node.id for node in response.menus] == [1, 4]
    assert [code for code in response.permissions] == ["menu:query"]

    narrowed = response.menus[0].forms[0].fields[0]
    assert narrowed.field_key == "title"
    assert narrowed.visible is False
    assert narrowed.editable is False


async def test_my_menu_without_snapshot_keeps_all_links() -> None:
    """未预加载权限快照（占位实现 / 服务身份）：入口与字段一律放行（全开）。"""
    menus = ConcurrentStableList([_menu(1, ConcurrentStableList([_form(11)]))])
    service = MyMenuService(
        metadata=cast("Any", _Metadata(_snapshot(menus))),
        checker=cast("Any", _Checker()),
    )
    set_current_permission_snapshot(None)
    response = await service.build(locale="zh-CN", tenant_id="1001", ttl=60)

    assert [node.id for node in response.menus] == [1]
    field = response.menus[0].forms[0].fields[0]
    assert field.visible is True
    assert field.editable is True

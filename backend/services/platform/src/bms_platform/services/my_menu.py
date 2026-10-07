"""平台服务 services 层：动态菜单服务（`GET /api/v1/menus/my`）。

按当前用户权限过滤菜单树并下发表单元数据：

- **菜单可见**＝其关联表单 → 业务的**业务码**被授予（多表单时任一命中即保留；`BasePermissionChecker`；
  当前 provider 为占位实现，真实权限计算随 `02_04` 注入，接口与前端零改动）；
  目录节点（无表单）在其存在可见子节点时保留；
- **按钮**按动作权限码 `{业务码}:{动作码}` 标记 `visible`；
- **字段**按字段权限标记 `visible` / `editable`——字段权限授予存 `sys_role_field`（归角色管理 `02_03`），
  占位阶段按「默认全部可见可编辑」，真实收窄随 `02_04`；
- 菜单 `hidden` 仅隐藏侧栏入口，不剔除响应（路由可直达）。

未过滤的元数据经 `MenuMetadataService.load_snapshot`（按 locale 维度缓存、版本号失效）。
"""

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.permission.base import BasePermissionChecker
from bms_platform.schemas.menu import (
    MyMenuButton,
    MyMenuField,
    MyMenuForm,
    MyMenuNode,
    MyMenuResponse,
)
from bms_platform.services.menu import MenuMetadataService, SnapshotForm, SnapshotMenu


class MyMenuService(BaseFrameworkObject):
    """动态菜单服务（过滤 + 权限标记）。"""

    def __init__(self, *, metadata: MenuMetadataService, checker: BasePermissionChecker) -> None:
        """初始化。

        Args:
            metadata: 菜单元数据服务（快照装载）。
            checker: 权限检查器（应用装配；当前占位实现恒允许）。
        """
        self._metadata = metadata
        self._checker = checker

    async def build(self, *, locale: str, tenant_id: str | None, ttl: int) -> MyMenuResponse:
        """构建当前用户的动态菜单响应。

        Args:
            locale: 语言标识。
            tenant_id: 租户主键字符串（缓存键租户位）。
            ttl: 元数据缓存有效期（秒）。

        Returns:
            MyMenuResponse: 菜单树 + 表单元数据 + 权限码集合。
        """
        snapshot = await self._metadata.load_snapshot(locale=locale, tenant_id=tenant_id, ttl=ttl)
        permissions = ConcurrentStableList(
            code for code in tuple(snapshot.business_codes) + tuple(snapshot.action_codes) if self._checker.check(code)
        )
        nodes = ConcurrentStableDict[int, MyMenuNode](
            {menu.id: self._to_node(menu) for menu in snapshot.menus if self._is_link_visible(menu)}
        )
        children_by_parent = ConcurrentStableDict[int, ConcurrentStableList[MyMenuNode]]()
        for menu in snapshot.menus:
            node = nodes.get(menu.id)
            if node is None:
                continue
            bucket = children_by_parent.get(menu.parent_id)
            if bucket is None:
                bucket = ConcurrentStableList[MyMenuNode]()
                children_by_parent.set(menu.parent_id, bucket)
            bucket.add(node)
        for menu_id, node in nodes.items():
            bucket = children_by_parent.get(menu_id)
            node.children = ConcurrentStableList(bucket) if bucket is not None else ConcurrentStableList()
        roots = ConcurrentStableList(
            node for menu in snapshot.menus if (node := nodes.get(menu.id)) is not None and menu.parent_id not in nodes
        )
        return MyMenuResponse(
            locale=snapshot.locale,
            version=snapshot.version,
            permissions=permissions,
            menus=self._prune_empty(roots),
        )

    def _is_link_visible(self, menu: SnapshotMenu) -> bool:
        """挂接链与业务权限判定（目录节点由「存在可见子节点」决定）。

        关联多个表单时：任一表单挂接的业务码被授予即保留该入口。

        Args:
            menu: 菜单快照。

        Returns:
            bool: 是否保留该节点。
        """
        if not menu.forms:
            return True
        return any(self._checker.check(form.business_code) for form in menu.forms)

    def _to_node(self, menu: SnapshotMenu) -> MyMenuNode:
        """菜单快照 → 动态菜单节点（含表单 / 按钮 / 字段标记）。

        Args:
            menu: 菜单快照。

        Returns:
            MyMenuNode: 动态菜单节点。
        """
        return MyMenuNode(
            id=menu.id,
            parent_id=menu.parent_id,
            name=menu.name,
            path=menu.path,
            component=menu.component,
            icon=menu.icon,
            sort=menu.sort,
            hidden=menu.hidden,
            forms=ConcurrentStableList(self._to_form(menu.id, form) for form in menu.forms),
            children=ConcurrentStableList(),
        )

    def _to_form(self, menu_id: int, form: SnapshotForm) -> MyMenuForm:
        """表单快照 → 动态菜单表单元数据（按动作 / 字段权限标记）。

        Args:
            menu_id: 关联的菜单入口 ID。
            form: 表单快照。

        Returns:
            MyMenuForm: 表单元数据。
        """
        return MyMenuForm(
            id=form.id,
            menu_id=menu_id,
            business_id=form.business_id,
            business_code=form.business_code,
            component=form.component,
            buttons=ConcurrentStableList(
                MyMenuButton(
                    id=button.id,
                    action_id=button.action_id,
                    action_code=button.action_code,
                    name=button.name,
                    type=button.type,
                    sort=button.sort,
                    visible=self._checker.check(button.action_code),
                )
                for button in form.buttons
            ),
            fields=ConcurrentStableList(
                MyMenuField(
                    id=field.id,
                    field_key=field.field_key,
                    name=field.name,
                    type=field.type,
                    sort=field.sort,
                    visible=True,
                    editable=True,
                )
                for field in form.fields
            ),
        )

    @staticmethod
    def _prune_empty(nodes: ConcurrentStableList[MyMenuNode]) -> ConcurrentStableList[MyMenuNode]:
        """剔除无表单且无可见子节点的目录节点（挂接链断裂即不可见）。

        Args:
            nodes: 待裁剪的节点列表。

        Returns:
            ConcurrentStableList[MyMenuNode]: 裁剪后的节点列表。
        """
        kept = ConcurrentStableList[MyMenuNode]()
        for node in nodes:
            node.children = MyMenuService._prune_empty(node.children)
            if node.forms or node.children:
                kept.add(node)
        return kept

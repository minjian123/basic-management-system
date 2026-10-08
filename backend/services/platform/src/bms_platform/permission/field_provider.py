"""平台服务：基础版字段权限 provider（`static_field_permission`）。

口径（《02_04 详细设计》§6）：

- **默认全开**：只登记收窄项，未出现的字段可见可编辑；
- **多角色从严**：同字段多角色命中时 `visible` / `editable` 取**逻辑与**（任一角色不可见即不可见）；
- **两库合流**：收窄项在租户库（`sys_role_field`），字段键在平台库（`sys_field`）——
  本实现按需构造，故为**工厂**（会话请求级）。

后代档位（`enterprise` / `enterprise_hr`）登记同名工厂即可替换（条件化 / 按值域求值），
引擎与消费方不改。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.db.session import DbSession
from bms_core.permission.field import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
    BaseFieldPermissionProvider,
    FieldPermission,
    register_field_permission_provider_factory,
)
from bms_platform.repositories.menu import FieldRepository
from bms_platform.repositories.role import RoleFieldRepository


class StaticFieldPermissionProvider(BaseFieldPermissionProvider):
    """静态收窄字段权限求值器（`sys_role_field` 两态；多角色从严合并）。"""

    key: str = DEFAULT_FIELD_PERMISSION_PROVIDER_KEY

    def __init__(self, tenant_session: DbSession, meta_session: DbSession) -> None:
        """初始化。

        Args:
            tenant_session: 租户库会话（角色字段收窄项）。
            meta_session: 平台库会话（字段键解析：`field_id → field_key`）。
        """
        self._role_fields = RoleFieldRepository(tenant_session)
        self._fields = FieldRepository(meta_session)

    async def resolve(
        self, *, role_ids: ConcurrentStableSet[int], form_ids: ConcurrentStableSet[int]
    ) -> ConcurrentStableList[FieldPermission]:
        """求值字段权限收窄项（多角色从严合并）。

        Args:
            role_ids: 角色 id 集合（空集合返回空列表）。
            form_ids: 待求值表单 id 集合（空集合表示不限定表单）。

        Returns:
            ConcurrentStableList[FieldPermission]: 收窄项列表（无收窄返回空列表）。
        """
        result: ConcurrentStableList[FieldPermission] = ConcurrentStableList()
        if not role_ids:
            return result
        rows = await self._role_fields.list_by_roles(role_ids)
        if not rows:
            return result
        field_keys = await self._field_keys()
        merged: ConcurrentStableDict[tuple[int, str], tuple[bool, bool]] = ConcurrentStableDict()
        for row in rows:
            if form_ids and row.form_id not in form_ids:
                continue
            field_key = field_keys.get(row.field_id)
            if not field_key:
                continue
            key = (row.form_id, field_key)
            prior = merged.get(key)
            visible = bool(row.visible) if prior is None else prior[0] and bool(row.visible)
            editable = bool(row.editable) if prior is None else prior[1] and bool(row.editable)
            merged.set(key, (visible, editable))
        for key in merged:
            state = merged.get(key)
            if state is None:  # pragma: no cover - 防御：遍历期键必在
                continue
            result.add(FieldPermission(form_id=key[0], field_key=key[1], visible=state[0], editable=state[1]))
        return result

    async def _field_keys(self) -> ConcurrentStableDict[int, str]:
        """取字段键映射（`field_id → field_key`）。

        Returns:
            ConcurrentStableDict[int, str]: 字段键映射。
        """
        keys: ConcurrentStableDict[int, str] = ConcurrentStableDict()
        for field in await self._fields.list_all():
            keys.set(field.id, field.field_key)
        return keys


def build_static_field_provider(tenant_session: DbSession, meta_session: DbSession) -> BaseFieldPermissionProvider:
    """基础版字段权限 provider 工厂（装配期登记；请求内按会话构造）。

    Args:
        tenant_session: 租户库会话。
        meta_session: 平台库会话。

    Returns:
        BaseFieldPermissionProvider: 静态收窄求值器。
    """
    return StaticFieldPermissionProvider(tenant_session, meta_session)


def register_static_field_provider() -> None:
    """登记基础版字段权限 provider 工厂（缺省登记；后代可登记同名工厂覆盖）。"""
    register_field_permission_provider_factory(DEFAULT_FIELD_PERMISSION_PROVIDER_KEY, build_static_field_provider)

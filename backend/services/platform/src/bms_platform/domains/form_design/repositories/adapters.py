"""端口适配器：把基座能力域实现适配为本域 `Protocol`（装配面注入用）。

- `MetaSnapshotAdapter`：`MetadataRepository` → `FormMetadataPort`（平台库会话）；
- `OptionSetAdapter`：选项集注册表 → `OptionSetPort`；
- `FieldPermissionAdapter`：字段权限求值器 → `PermissionPort`（多角色从严合并）。

适配器只做**形状转换**，不含业务规则（规则在服务层与基座）。
"""

from __future__ import annotations

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.permission.field import BaseFieldPermissionProvider, FieldPermission
from bms_platform.domains.form_design.ports import RoleSummaryReader, RoleSummaryView
from bms_platform.domains.form_design.repositories.metadata import BusinessFormSnapshot, MetadataRepository

__all__ = [
    "FieldPermissionAdapter",
    "OptionSetAdapter",
    "PlatformMetadataAdapter",
    "RoleQueryAdapter",
]


class PlatformMetadataAdapter(BaseFrameworkObject):
    """`FormMetadataPort` 适配：委托平台库元数据仓储。"""

    def __init__(self, repository: MetadataRepository) -> None:
        """初始化。

        Args:
            repository: 平台库元数据只读仓储。
        """
        self._repository = repository

    async def load(self, form_code: str) -> BusinessFormSnapshot | None:
        """按业务码装载表单元数据。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            BusinessFormSnapshot | None: 快照；不可定制返回 None。
        """
        return await self._repository.load(form_code)


class OptionSetAdapter(BaseFrameworkObject):
    """`OptionSetPort` 适配：委托选项集注册表（只读）。"""

    def __init__(self, registry: BaseOptionSetRegistry) -> None:
        """初始化。

        Args:
            registry: 选项集注册表（应用级单例）。
        """
        self._registry = registry

    def resolve_items(self, option_set_key: str) -> ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]:
        """解析选项集条目（只读快照）。

        Args:
            option_set_key: 选项集标识。

        Returns:
            ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]: 条目清单。
        """
        info = self._registry.resolve(option_set_key)
        items: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
        for item in info.items:
            record: ConcurrentStableDict[str, object] = ConcurrentStableDict({"value": item.value, "label": item.label})
            if item.label_key is not None:
                record.set("labelKey", item.label_key)
            if item.color is not None:
                record.set("color", item.color)
            if item.disabled:
                record.set("disabled", True)
            record.set("sort", item.sort)
            items.add(record)
        return ConcurrentStableFrozenList(items)

    def is_registered(self, option_set_key: str) -> bool:
        """标识是否已登记。

        Args:
            option_set_key: 选项集标识。

        Returns:
            bool: 已登记为 True。
        """
        return self._registry.get(option_set_key) is not None


class FieldPermissionAdapter(BaseFrameworkObject):
    """`PermissionPort` 适配：委托字段权限求值器（多角色从严合并，与权限引擎同口径）。"""

    def __init__(self, provider: BaseFieldPermissionProvider) -> None:
        """初始化。

        Args:
            provider: 字段权限求值器。
        """
        self._provider = provider

    async def resolve(
        self,
        *,
        form_id: int,
        role_ids: ConcurrentStableList[int],
    ) -> ConcurrentStableDict[str, ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]]:
        """按角色集解析字段权限收窄项。

        Args:
            form_id: 表单主键。
            role_ids: 角色集。

        Returns:
            ConcurrentStableDict[str, ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]]:
                字段键 → 收窄项清单（同字段多条时按任一收窄即收窄合并）。
        """
        narrowings: ConcurrentStableList[FieldPermission] = await self._provider.resolve(
            role_ids=ConcurrentStableSet(role_ids),
            form_ids=ConcurrentStableSet((form_id,)),
        )
        merged: ConcurrentStableDict[str, ConcurrentStableList[ConcurrentStableDict[str, object]]] = (
            ConcurrentStableDict()
        )
        for item in narrowings:
            bucket = merged.get(item.field_key)
            if bucket is None:
                created: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
                merged.set(item.field_key, created)
                bucket = created
            record: ConcurrentStableDict[str, object] = ConcurrentStableDict(
                {"visible": item.visible, "editable": item.editable}
            )
            bucket.add(record)
        result: ConcurrentStableDict[str, ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]] = (
            ConcurrentStableDict()
        )
        for field_key, bucket in merged.items():
            result.set(field_key, ConcurrentStableFrozenList(bucket))
        return result


class RoleQueryAdapter[SummaryT: RoleSummaryView](BaseFrameworkObject):
    """`RolePort` 适配：委托角色读面（按用户取角色摘要）。"""

    def __init__(self, roles: RoleSummaryReader[SummaryT]) -> None:
        """初始化。

        Args:
            roles: 角色读面实现（`RoleQueryService`；经 `RoleSummaryReader` 泛型注入，避免域间 import）。
        """
        self._roles = roles

    async def roles_of_user(self, user_id: int) -> ConcurrentStableList[tuple[str, int]]:
        """取用户直接分配的角色（`(role_type, role_id)`）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色类型与主键（无分配返回空）。
        """
        summaries = await self._roles.list_by_user(user_id)
        result: ConcurrentStableList[tuple[str, int]] = ConcurrentStableList()
        for item in summaries:
            result.add((str(item.role_type), int(item.id)))
        return result

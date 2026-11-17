"""表单定制域端口（Protocol）：域实现只依赖这些接口，具体实现由装配面注入。

**为什么需要端口**（域边界纪律）：本域要读**平台库**的表单 / 字段 / 业务码元数据（`menu_form` 域）
与**租户库**的字段权限（`role` 域），但域实现之间零 import——读取能力一律经装配面注入的 Protocol，
依赖方向恒为「装配 → 域」。
"""

from typing import Protocol

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)

__all__ = [
    "FormMetadataPort",
    "FormMetadataSnapshot",
    "OptionSetPort",
    "PermissionPort",
    "RolePort",
    "RoleSummaryReader",
    "RoleSummaryView",
]


class RoleSummaryView(Protocol):
    """角色摘要只读视图（`role` 域 `RoleSummary` 的结构化契约，避免跨域 import）。"""

    @property
    def id(self) -> int:
        """角色主键。"""
        ...

    @property
    def role_type(self) -> str:
        """角色类型（`platform_admin` / `system` / `security` / `audit` / `custom`）。"""
        ...


class RoleSummaryReader[SummaryT: RoleSummaryView](Protocol):
    """角色读面实现（`role` 域 `RoleQueryService` 的结构化契约）。

    泛型参数即摘要类型：实现方（`RoleQueryService`）返回自己的 `ConcurrentStableList[RoleSummary]`，
    适配器按同一参数接收，无需把摘要类型写成 `object` 或跨域 import 具体类。
    """

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SummaryT]:
        """按用户取直接分配的角色摘要（按角色主键升序；未分配返回空）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SummaryT]: 角色摘要。
        """
        ...


class FormFieldSnapshot(Protocol):
    """平台字段快照。"""

    @property
    def field_key(self) -> str:
        """字段键。"""
        ...

    @property
    def name(self) -> str:
        """字段名（默认文案）。"""
        ...

    @property
    def type(self) -> str:
        """字段类型。"""
        ...

    @property
    def sort(self) -> int:
        """同表单内排序。"""
        ...

    @property
    def status(self) -> str:
        """状态（`enabled` / `disabled`）。"""
        ...


class FormMetadataSnapshot(Protocol):
    """表单元数据快照（平台库只读）。"""

    @property
    def form_code(self) -> str:
        """表单标识（业务码）。"""
        ...

    @property
    def form_id(self) -> int:
        """表单主键（`sys_form.id`）。"""
        ...

    @property
    def table_name(self) -> str | None:
        """派生物理表名（来自表单标识清单 `form_key → table`；不可解析为 None）。"""
        ...

    @property
    def fields(self) -> ConcurrentStableList[FormFieldSnapshot]:
        """平台字段清单。"""
        ...


class FormMetadataPort(Protocol):
    """表单元数据读面（平台库；`menu_form` 域提供实现）。"""

    async def load(self, form_code: str) -> FormMetadataSnapshot | None:
        """按业务码装载表单元数据（含平台字段与物理表名）。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            FormMetadataSnapshot | None: 快照；业务码不存在或不可定制返回 None。
        """
        ...


class RolePort(Protocol):
    r"""角色集读面（当前用户的直接角色；\`role\` 域提供实现）。"""

    async def roles_of_user(self, user_id: int) -> ConcurrentStableList[tuple[str, int]]:
        r"""取用户直接分配的角色（\`(role_type, role_id)\` 插入序）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[tuple[str, int]]: 角色类型与主键（无分配返回空）。
        """
        ...


class PermissionPort(Protocol):
    """字段权限读面（租户库；`role` 域提供实现）。"""

    async def resolve(
        self,
        *,
        form_id: int,
        role_ids: ConcurrentStableList[int],
    ) -> ConcurrentStableDict[str, ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]]:
        """按角色集解析字段权限收窄项（多角色从严合并）。

        Args:
            form_id: 表单主键。
            role_ids: 角色集（主体链结果）。

        Returns:
            ConcurrentStableDict[str, ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]]:
                字段键 → 收窄项清单（`visible` / `editable` / `required`）。
        """
        ...


class OptionSetPort(Protocol):
    """选项集读面（注册表；基座提供实现）。"""

    def resolve_items(self, option_set_key: str) -> ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]:
        """解析选项集条目（只读快照）。

        Args:
            option_set_key: 选项集标识。

        Returns:
            ConcurrentStableFrozenList[ConcurrentStableDict[str, object]]: 条目（`value` / `label` / `color` 等）。

        Raises:
            NotFoundError: 标识未注册（10002）。
        """
        ...

    def is_registered(self, option_set_key: str) -> bool:
        """标识是否已登记。

        Args:
            option_set_key: 选项集标识。

        Returns:
            bool: 已登记为 True。
        """
        ...

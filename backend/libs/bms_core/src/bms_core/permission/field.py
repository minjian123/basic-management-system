"""字段权限 provider（域 `permission`）。

字段权限 = **按表单收窄**（`sys_role_field`：`role_id` + `form_id` + `field_id` + `visible` + `editable`），
**默认全部可见可编辑**、只登记收窄项；读时不返回不可见字段、写时拒绝不可编辑字段。

- **基础版**（`smb`）默认实现：`StaticFieldPermissionProvider`（platform 侧，静态收窄两态）；
- **后代**（`enterprise` / `enterprise_hr`）可换「条件化 / 按值域」求值器——**同一协议**，引擎主流程不改
  （见《02_04 详细设计》§11.2 接缝 2）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject

DEFAULT_FIELD_PERMISSION_PROVIDER_KEY = "static_field_permission"
"""基础版字段权限 provider 标识（platform 侧静态收窄实现）。"""


@dataclass
class FieldPermission(BaseDataContract):
    """字段权限收窄项（只登记收窄项；未出现的字段默认全开）。"""

    form_id: int
    """表单 id（平台实体）。"""
    field_key: str
    """字段键（`sys_field.field_key`）。"""
    visible: bool = True
    """读时是否返回（False = 不返回不渲染）。"""
    editable: bool = True
    """写时是否接受（False = 含该字段的写入即拒）。"""


class BaseFieldPermissionProvider(BaseFrameworkObject, ABC):
    """字段权限求值契约（按角色集合 + 表单集合**批量**求值）。"""

    key: str = "field_permission"
    """provider 标识（装配登记用）。"""

    @abstractmethod
    async def resolve(
        self, *, role_ids: ConcurrentStableSet[int], form_ids: ConcurrentStableSet[int]
    ) -> ConcurrentStableList[FieldPermission]:
        """求值字段权限收窄项（批量，避免逐表单查询）。

        Args:
            role_ids: 角色 id 集合（主体链收敛结果）。
            form_ids: 待求值表单 id 集合（空集合表示不限定表单）。

        Returns:
            ConcurrentStableList[FieldPermission]: 收窄项列表（无收窄返回空列表）。
        """


_PROVIDERS: ConcurrentStableDict[str, BaseFieldPermissionProvider] = ConcurrentStableDict()
"""字段权限 provider 注册表（key → 实例；登记顺序即输出顺序）。"""


def register_field_permission_provider(provider: BaseFieldPermissionProvider) -> None:
    """登记字段权限 provider（同 key 覆盖；装配期调用）。

    Args:
        provider: provider 实例。
    """
    _PROVIDERS.set(provider.key, provider)


def current_field_permission_provider() -> BaseFieldPermissionProvider | None:
    """取当前生效的字段权限 provider（未登记返回 `None`，引擎按「全开」处置）。

    Returns:
        BaseFieldPermissionProvider | None: 最后登记的 provider；无登记为 None。
    """
    latest: BaseFieldPermissionProvider | None = None
    for key in _PROVIDERS:
        latest = _PROVIDERS.get(key)
    return latest


def reset_field_permission_providers() -> None:
    """清空 provider 注册表（用例隔离用）。"""
    for key in tuple(_PROVIDERS):
        _PROVIDERS.delete(key)

"""权限数据来源接缝（域 `permission`）。

下沉后的计算主流程（`permission/engine.py`）**只依赖本接缝**取数，不 import 任何服务包、不碰任何 ORM：

- **元数据来源**（`load_metadata`）：菜单 → 表单关联、权限码 id → 权限码字符串——用于把授权行解析成
  入口授权集合与权限码集合；
- **数据来源**（`load_subject`）：角色集合、角色类型（豁免层级判定）、授权行、数据范围规则——用于聚合与
  快照计算。

两者都返回**基座中性结构**（本模块的数据契约），服务侧只负责「取数 + 映射」，算法与结构归基座：
platform 直查本库（一次查全）、identity 经 platform 内部只读契约一次取回。

**登记是进程级注册表**（与角色解析器链 `permission/resolver.py` 同构）：服务在 `prepare_settings`
钩子里登记自身实现（早于插件注册表冻结）；用例经 `reset_permission_data_sources()` 隔离。

后代档位（`enterprise` / `enterprise_hr`）新增数据维度时**扩本接缝的数据契约 + 走快照 `extensions`**，
不改主流程（见《02_04 详细设计》§11.2）。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseDataContract, BaseFrameworkObject
from bms_core.i18n.base import DEFAULT_LOCALE
from bms_core.permission.field import FieldPermission

DEFAULT_PERMISSION_DATA_SOURCE_KEY = "permission_data_source"
"""数据来源标识缺省值（单实现服务直接用缺省键；多实现并存时按需自定）。"""


@dataclass
class PermissionGrant(BaseDataContract):
    """授权行（`sys_role_permission` 的中性映射：授权类型 + 目标主键）。"""

    perm_type: str
    """授权类型：`menu`（菜单入口）/ `form`（表单）/ `permission`（权限码）。"""
    target_id: int
    """目标主键（菜单 id / 表单 id / 权限码 id，按 `perm_type` 解释）。"""


@dataclass
class DataScopeRule(BaseDataContract):
    """数据范围规则（`sys_data_scope` 的中性映射：字典类型 + 策略 + 规则行）。"""

    data_source_key: str
    """字典类型主键（字符串化；同类型内多规则并集）。"""
    policy_type: str
    """策略类型（`select` / `region` / `match` / `extension`；由策略注册表求值）。"""
    config: ConcurrentStableList[ConcurrentStableDict[str, object]] = field(
        default_factory=lambda: ConcurrentStableList[ConcurrentStableDict[str, object]]()
    )
    """规则行（`config` 原样，交策略求值器解析）。"""


@dataclass
class PermissionSubjectData(BaseDataContract):
    """按用户取回的聚合输入（角色 / 类型 / 授权 / 数据范围规则 / 字段收窄）。"""

    role_ids: ConcurrentStableSet[int] = field(default_factory=lambda: ConcurrentStableSet[int]())
    """主体链收敛后的角色主键集合（直接角色 ∪ 各解析器来源）。"""
    role_types: ConcurrentStableDict[int, str] = field(default_factory=lambda: ConcurrentStableDict[int, str]())
    """角色主键 → 角色类型（`custom` / `system` / `security` / `audit`；豁免层级判定用）。"""
    grants: ConcurrentStableList[PermissionGrant] = field(
        default_factory=lambda: ConcurrentStableList[PermissionGrant]()
    )
    """授权行列表（角色集合 → `sys_role_permission`）。"""
    data_scope_rules: ConcurrentStableList[DataScopeRule] = field(
        default_factory=lambda: ConcurrentStableList[DataScopeRule]()
    )
    """数据范围规则列表（角色集合 → `sys_data_scope`）。"""
    field_perms: ConcurrentStableList[FieldPermission] = field(
        default_factory=lambda: ConcurrentStableList[FieldPermission]()
    )
    """字段权限收窄项（**空表示全开**）。

    由数据来源实现经**字段权限 provider 接缝**（`permission/field.py`）求值后填入：接缝仍可替换，
    而引擎只消费结果、不碰两库会话（字段键在元数据库、收窄项在租户库）。
    """


@dataclass
class PermissionMetadata(BaseDataContract):
    """权限元数据（菜单 / 表单 / 权限码索引，用于授权行的两段解析）。"""

    version: int = 0
    """元数据版本号（排障与缓存对齐用）。"""
    menu_forms: ConcurrentStableDict[int, ConcurrentStableList[int]] = field(
        default_factory=lambda: ConcurrentStableDict[int, ConcurrentStableList[int]]()
    )
    """菜单 id → 关联表单 id 列表（菜单授权连带授予其表单查看权限）。"""
    permission_codes: ConcurrentStableDict[int, str] = field(default_factory=lambda: ConcurrentStableDict[int, str]())
    """权限码 id → 权限码字符串（`业务码:动作码`）。"""


class BasePermissionDataSource(BaseFrameworkObject, ABC):
    """权限数据来源契约（服务侧实现：直查本库 / 经契约取数）。"""

    key: str = DEFAULT_PERMISSION_DATA_SOURCE_KEY
    """实现标识（注册表键；同键覆盖）。"""

    @abstractmethod
    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """取用户的聚合输入（角色 / 类型 / 授权 / 数据范围规则）。

        实现约定：**失败应抛异常**（不静默返回空集）——空集等于「无任何权限」，与「取数失败」是
        两种不同语义，静默吞错会把故障伪装成「无权限」而难以排障。

        Args:
            user_id: 用户主键。

        Returns:
            PermissionSubjectData: 聚合输入。
        """

    @abstractmethod
    async def load_metadata(self, *, locale: str = DEFAULT_LOCALE) -> PermissionMetadata:
        """取权限元数据（菜单 → 表单、权限码 id → 权限码）。

        Args:
            locale: 语言标识（元数据按 locale 本地化，仅影响展示名，不影响索引）。

        Returns:
            PermissionMetadata: 元数据索引。
        """


_SOURCES: ConcurrentStableDict[str, BasePermissionDataSource] = ConcurrentStableDict()
"""数据来源注册表（key → 实例；登记顺序即查找顺序）。"""

PermissionDataSourceFactory = Callable[[Request], Awaitable[BasePermissionDataSource]]
"""请求级数据来源工厂：`(request) → 数据来源`（需要请求级会话的实现用；可异步建会话）。"""

_FACTORIES: ConcurrentStableDict[str, PermissionDataSourceFactory] = ConcurrentStableDict()
"""数据来源**请求级工厂**注册表（key → 工厂）。

需要请求级会话的实现（如 platform 直查本库：会话随请求开启）登记工厂而非实例；校验器
`aprepare` 优先取工厂，其次取实例。不需要请求态的跨服务实现（如 identity 经契约取数）登记实例即可。
"""


def register_permission_data_source(source: BasePermissionDataSource) -> None:
    """登记数据来源实现（同 key 覆盖；服务 `prepare_settings` 期调用）。

    Args:
        source: 数据来源实例。
    """
    _SOURCES.set(source.key, source)


def register_permission_data_source_factory(key: str, factory: PermissionDataSourceFactory) -> None:
    """登记请求级数据来源工厂（同 key 覆盖；服务 `prepare_settings` 期调用）。

    Args:
        key: 实现标识（注册表键）。
        factory: 工厂 `(request) → 数据来源实例`。
    """
    _FACTORIES.set(key, factory)


def current_permission_data_source() -> BasePermissionDataSource | None:
    """取当前生效的**实例型**数据来源（未登记返回 `None`）。

    Returns:
        BasePermissionDataSource | None: 最后登记的实例；无登记为 None。
    """
    latest: BasePermissionDataSource | None = None
    for key in _SOURCES:
        latest = _SOURCES.get(key)
    return latest


def current_permission_data_source_factory() -> PermissionDataSourceFactory | None:
    """取当前生效的**请求级工厂**（未登记返回 `None`）。

    Returns:
        PermissionDataSourceFactory | None: 最后登记的工厂；无登记为 None。
    """
    latest: PermissionDataSourceFactory | None = None
    for key in _FACTORIES:
        latest = _FACTORIES.get(key)
    return latest


def has_permission_data_source() -> bool:
    """是否已登记任一数据来源（实例或工厂）——启动期 fail-closed 判定用。

    Returns:
        bool: 已登记为 True。
    """
    return current_permission_data_source() is not None or current_permission_data_source_factory() is not None


def reset_permission_data_sources() -> None:
    """清空数据来源注册表（实例与工厂；用例隔离用）。"""
    for key in tuple(_SOURCES):
        _SOURCES.delete(key)
    for key in tuple(_FACTORIES):
        _FACTORIES.delete(key)

"""listing 能力域：列表偏好协议与查询方案契约（真实持久化随通用能力阶段回补）。

- `LIST_PREF_KEY_PREFIX` / `LIST_DENSITIES` / `build_list_pref_key`：列表偏好键 `list.{form_key}`（读写经
  02-50 `BasePreferenceStore`）。
- `ListColumnPreference` / `ListPreference`：列表偏好数据契约（`columns` / `page_size` / `density` / `query`）。
- `QuerySchemeScope` / `QuerySchemeTarget` / `QueryScheme`：查询方案作用域（个人 / 租户 / 平台）、目标
  （字典条目 `items` / 列表筛选 `business`）与数据契约。
- `BaseQuerySchemeStore`：能力域中间层契约（`key = "query_scheme_store"`）——`list` / `get` / `save` /
  `delete` / `resolve_default`（三级优先级）。
- `get_query_scheme_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：一份 `sys_query_scheme` 供字典高级查询（`target=items`）与列表筛选（`target=business`，
`field_key=form_key`）共用；三级优先级 **个人 > 租户 > 平台**；个人方案免权限码，租户 / 共享方案维护需
`query:scheme`（真实随 RBAC 阶段）。真实落库 / 筛选执行随通用能力 / 列表接口阶段。
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema

__all__ = [
    "LIST_DENSITIES",
    "LIST_PREF_KEY_PREFIX",
    "BaseQuerySchemeStore",
    "ListColumnPreference",
    "ListPreference",
    "QueryScheme",
    "QuerySchemeScope",
    "QuerySchemeTarget",
    "build_list_pref_key",
    "get_query_scheme_store",
]

LIST_PREF_KEY_PREFIX = "list"
"""列表偏好键前缀（域）：`list.{form_key}`。"""

LIST_DENSITIES: tuple[str, ...] = ("default", "small")
"""表格密度取值（对齐《概要设计 · 用户喜好》§2.2）。"""


def build_list_pref_key(form_key: str) -> str:
    """构建列表偏好键（`list.{form_key}`，经 02-50 用户偏好基座读写）。

    Args:
        form_key: 表单 / 列表标识。

    Returns:
        str: 列表偏好键。
    """
    return f"{LIST_PREF_KEY_PREFIX}.{form_key}"


class ListColumnPreference(BaseSchema):
    """单列偏好：字段 / 显隐 / 顺序 / 宽度。"""

    prop: str = Field(description="列字段标识")
    visible: bool = Field(default=True, description="是否可见")
    order: int = Field(default=0, description="显示顺序")
    width: int | None = Field(default=None, description="列宽（像素）")


class ListPreference(BaseSchema):
    """列表偏好：列配置 / 每页条数 / 密度 / 上次筛选条件。"""

    columns: list[ListColumnPreference] = Field(default_factory=list[ListColumnPreference], description="列偏好列表")
    page_size: int = Field(default=20, ge=1, le=200, description="每页条数")
    density: str = Field(default="default", description="表格密度（取 LIST_DENSITIES）")
    query: dict[str, object] = Field(default_factory=dict, description="上次筛选条件（JSON）")


class QuerySchemeScope(StrEnum):
    """查询方案作用域。"""

    USER = "user"
    TENANT = "tenant"
    PLATFORM = "platform"


class QuerySchemeTarget(StrEnum):
    """查询方案目标。"""

    ITEMS = "items"
    BUSINESS = "business"


class QueryScheme(BaseSchema):
    """查询方案数据契约（一份 `sys_query_scheme` 供字典高级查询与列表筛选共用）。"""

    id: int | None = Field(default=None, description="方案 ID（新建为空，落库生成）")
    name: str = Field(description="方案名")
    scope: QuerySchemeScope = Field(default=QuerySchemeScope.USER, description="作用域（个人 / 租户 / 平台）")
    owner_id: int | None = Field(default=None, description="归属用户 ID（个人方案）")
    target: QuerySchemeTarget = Field(description="目标（items 字典条目 / business 列表筛选）")
    dict_type: str | None = Field(default=None, description="字典类型（target=items 时填）")
    field_key: str | None = Field(default=None, description="表单标识（target=business 时为 form_key）")
    provider_key: str | None = Field(default=None, description="查询提供者键（字典高级查询可选）")
    conditions: dict[str, object] | None = Field(default=None, description="条件组 JSON")
    params: dict[str, object] | None = Field(default=None, description="额外参数 JSON")
    layout: dict[str, object] | None = Field(default=None, description="展示配置 JSON")
    is_default: bool = Field(default=False, description="是否默认方案")
    shared: bool = Field(default=False, description="是否共享")
    status: str = Field(default="enabled", description="状态")


class BaseQuerySchemeStore(BasePluggable, ABC):
    """查询方案存储契约：列表 / 读取 / 保存 / 删除 / 默认解析。"""

    key: str = "query_scheme_store"
    plugin_key: str = "query_scheme_store"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def list(
        self,
        target: QuerySchemeTarget,
        *,
        field_key: str | None = None,
    ) -> tuple[QueryScheme, ...]:
        """列查询方案。

        Args:
            target: 方案目标。
            field_key: 表单标识（列表筛选维度；可选）。

        Returns:
            tuple[QueryScheme, ...]: 方案元组。
        """

    @abstractmethod
    async def get(self, scheme_id: int) -> QueryScheme | None:
        """取单个方案（未命中返回 None）。

        Args:
            scheme_id: 方案 ID。

        Returns:
            QueryScheme | None: 方案；未命中为 None。
        """

    @abstractmethod
    async def save(self, scheme: QueryScheme) -> QueryScheme:
        """保存 / 更新方案。

        Args:
            scheme: 方案（`id` 为空表示新建）。

        Returns:
            QueryScheme: 落库后的方案（占位原样返回）。
        """

    @abstractmethod
    async def delete(self, scheme_id: int) -> bool:
        """删除方案。

        Args:
            scheme_id: 方案 ID。

        Returns:
            bool: 是否删除到既有方案。
        """

    @abstractmethod
    async def resolve_default(
        self,
        target: QuerySchemeTarget,
        *,
        field_key: str | None = None,
    ) -> QueryScheme | None:
        """按三级优先级（个人 > 租户 > 平台）解析默认方案。

        Args:
            target: 方案目标。
            field_key: 表单标识（列表筛选维度；可选）。

        Returns:
            QueryScheme | None: 命中最高优先级的默认方案；无则 None。
        """


def get_query_scheme_store(request: Request) -> BaseQuerySchemeStore:
    """取应用级查询方案存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseQuerySchemeStore: 应用装配的查询方案存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseQuerySchemeStore",
        resolve_plugin(
            "query_scheme_store",
            settings.query_scheme_store.provider,
            expected_version=BaseQuerySchemeStore.contract_version,
        ),
    )

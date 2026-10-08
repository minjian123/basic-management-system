"""数据权限扩展权限注册表（域 `data_scope_extension`）。

扩展权限 = 预设 / 二次开发注册的后端筛选器（如「本部门及下级部门」）：

- 每条含稳定 `key`、展示名与「是否需要参数」标记；
- 角色数据权限配置页的「扩展权限」明细表按本注册表下发（**未注册即不显示该 Tab**）；
- 参数由该扩展权限功能自带界面提供、以 JSON 落库并交其自行解析（见《组件设计 · 权限配置》「数据权限」节）。

平台缺省**无注册项** ⇒ 取数接口返回空清单 ⇒ 界面不显示扩展权限 Tab；真实扩展由各业务模块在
**导入期**登记（范式同租户源注册表 `db/tenant_source.py`：模块级注册表 + 保序读取）。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseDataContract
from bms_core.scope.base import ScopeCondition


@dataclass
class DataScopeExtensionInfo(BaseDataContract):
    """扩展权限描述（注册项）：稳定 key、展示名与是否需要参数。"""

    key: str
    label: str
    has_params: bool = False


_EXTENSIONS: ConcurrentStableDict[str, DataScopeExtensionInfo] = ConcurrentStableDict()
"""扩展权限注册表（key → 描述；登记顺序即输出顺序）。"""


def register_data_scope_extension(extension: DataScopeExtensionInfo) -> None:
    """登记一条扩展权限（同 key 覆盖；模块导入期调用）。

    Args:
        extension: 扩展权限描述。
    """
    _EXTENSIONS.set(extension.key, extension)


def reset_data_scope_extensions() -> None:
    """清空扩展权限描述注册表（用例隔离用）。"""
    for key in tuple(_EXTENSIONS):
        _EXTENSIONS.delete(key)


def registered_data_scope_extensions() -> tuple[DataScopeExtensionInfo, ...]:
    """已登记扩展权限清单（保序；空清单表示平台未注册任何扩展）。

    Returns:
        tuple[DataScopeExtensionInfo, ...]: 扩展权限描述元组。
    """
    return tuple(cast("DataScopeExtensionInfo", _EXTENSIONS.get(key)) for key in _EXTENSIONS)


ScopeExtensionResolver = Callable[
    [ConcurrentStableList[ConcurrentStableDict[str, object]]], ConcurrentStableList[ScopeCondition]
]
"""扩展权限求值器：`config`（扩展自带结构的 JSON 行）→ 作用域条件列表。

扩展权限的 `config` 结构由扩展方自定义（`has_params=True` 时含参数），故求值也归扩展方：
注册求值器即接入读过滤（写校验复用 `ScopeCondition` 判定）。
"""


_RESOLVERS: ConcurrentStableDict[str, ScopeExtensionResolver] = ConcurrentStableDict()
"""扩展权限求值器注册表（key → 求值器）。"""


def register_scope_extension_resolver(key: str, resolver: ScopeExtensionResolver) -> None:
    """登记扩展权限求值器（同 key 覆盖；模块导入期调用）。

    Args:
        key: 扩展权限稳定 key（与 `register_data_scope_extension` 的 `key` 对应）。
        resolver: 求值器（`config` → 作用域条件）。
    """
    _RESOLVERS.set(key, resolver)


def scope_extension_resolver(key: str) -> ScopeExtensionResolver | None:
    """取扩展权限求值器（未注册返回 None——调用方按「未注册即不生效 + 上报」处置）。

    Args:
        key: 扩展权限稳定 key。

    Returns:
        ScopeExtensionResolver | None: 求值器；未注册为 None。
    """
    return _RESOLVERS.get(key)


def reset_scope_extension_resolvers() -> None:
    """清空扩展权限求值器注册表（用例隔离用）。"""
    for key in tuple(_RESOLVERS):
        _RESOLVERS.delete(key)

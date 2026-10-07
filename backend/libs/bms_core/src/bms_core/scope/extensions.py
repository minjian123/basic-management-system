"""数据权限扩展权限注册表（域 `data_scope_extension`）。

扩展权限 = 预设 / 二次开发注册的后端筛选器（如「本部门及下级部门」）：

- 每条含稳定 `key`、展示名与「是否需要参数」标记；
- 角色数据权限配置页的「扩展权限」明细表按本注册表下发（**未注册即不显示该 Tab**）；
- 参数由该扩展权限功能自带界面提供、以 JSON 落库并交其自行解析（见《组件设计 · 权限配置》「数据权限」节）。

平台缺省**无注册项** ⇒ 取数接口返回空清单 ⇒ 界面不显示扩展权限 Tab；真实扩展由各业务模块在
**导入期**登记（范式同租户源注册表 `db/tenant_source.py`：模块级注册表 + 保序读取）。
"""

from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseDataContract


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


def registered_data_scope_extensions() -> tuple[DataScopeExtensionInfo, ...]:
    """已登记扩展权限清单（保序；空清单表示平台未注册任何扩展）。

    Returns:
        tuple[DataScopeExtensionInfo, ...]: 扩展权限描述元组。
    """
    return tuple(cast("DataScopeExtensionInfo", _EXTENSIONS.get(key)) for key in _EXTENSIONS)

"""数据范围阈值读取（`[data_scope].options`，`04-4` 收口）。

阈值只有**一处口径**：运行期护栏（`scope/rbac.py` 的 `in` 元素上限）与配置期校验
（platform 写入口 `RoleGrantService`）都经本模块读取，避免两处各写一份而漂移。

阈值为**装配期定型**（provider / 写入口构造时读取一次，改配置需重启并重建缓存仓）；
阈值不进规则指纹（见 `04-3` 决策 7）。
"""

from __future__ import annotations

from bms_core.core.config import Settings
from bms_core.permission.cache import int_option

__all__ = [
    "DEFAULT_MAX_IN_VALUES",
    "OPTION_MAX_IN_VALUES",
    "data_scope_max_in_values",
]

DEFAULT_MAX_IN_VALUES = 1000
"""单条 `in` 条件允许的值元素上限（超出即整体退化为永假；<= 0 表示不限制）。"""

OPTION_MAX_IN_VALUES = "max_in_values"
"""`[data_scope].options` 的阈值键名（装配期定型，改配置需重启）。"""


def data_scope_max_in_values(settings: Settings) -> int:
    """取数据范围 `in` 元素上限。

    Args:
        settings: 应用配置（读 `[data_scope].options.max_in_values`）。

    Returns:
        int: 阈值（<= 0 表示不限制）。
    """
    return int_option(settings.data_scope.options, OPTION_MAX_IN_VALUES, DEFAULT_MAX_IN_VALUES)

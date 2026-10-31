"""系统参数规则表（02_02）：键格式 / 值类型 / 参数依赖 / 敏感前缀。

- **纯常量与纯函数**：不读库、不读配置、不碰缓存，供基座（种子 / 读路径）与平台服务（管理面）共用。
- **键格式**：点分小写（段内 snake_case），首段字母开头；单段键合法（如 `role.code_pattern`）。
- **值类型**：按平台默认清单同键的默认值推断（`true` / `false` → 布尔；纯整数 → 数字；其余文本）。
  租户自建键（清单无该项）不做类型推断，只校验长度。
- **参数依赖**：登记式（`CONFIG_DEPENDS`），保存后的最终状态必须满足依赖；新增一条依赖 = 加一行。
- **敏感前缀**：命中的参数在管理面标记 `is_sensitive`（页面提示 + 审计强制留痕）。
"""

import re
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseValueObject

__all__ = [
    "CONFIG_DEPENDS",
    "CONFIG_KEY_MAX_LENGTH",
    "CONFIG_KEY_PATTERN",
    "CONFIG_VALUE_MAX_LENGTH",
    "SENSITIVE_PREFIXES",
    "ConfigDependency",
    "infer_value_kind",
    "is_config_key_valid",
    "is_sensitive_key",
    "is_value_valid",
]

CONFIG_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
"""参数键格式：点分小写，段内 snake_case，首字符为小写字母。"""

CONFIG_KEY_MAX_LENGTH = 128
"""参数键最大长度（与 `sys_config.code` 列宽一致）。"""

CONFIG_VALUE_MAX_LENGTH = 20000
"""参数值最大长度（`TEXT` 承载，避免无界写入）。"""

SENSITIVE_PREFIXES = ("password.", "account.", "session.", "ai.")
"""安全敏感参数键前缀（页面敏感提示 + 审计留痕）。"""


@dataclass(frozen=True)
class ConfigDependency(BaseValueObject):
    """参数依赖声明：`config_key` 的取值受 `depends_on` 的期望值约束。"""

    config_key: str
    """被约束的参数键。"""

    depends_on: str
    """依赖的参数键。"""

    expected: str
    """依赖项必须等于该值（文本比较）。"""


CONFIG_DEPENDS: ConcurrentStableDict[str, ConfigDependency] = ConcurrentStableDict(
    (
        (
            "ai.auto_approve",
            ConfigDependency(config_key="ai.auto_approve", depends_on="ai.auto_execute", expected="true"),
        ),
    )
)
"""参数依赖表（概要 §6.3：`ai.auto_approve` 依赖 `ai.auto_execute` 开启）。"""


def is_config_key_valid(config_key: str) -> bool:
    """判断参数键是否合法（格式 + 长度）。

    Args:
        config_key: 参数键。

    Returns:
        bool: 合法 True。
    """
    return (
        bool(config_key)
        and len(config_key) <= CONFIG_KEY_MAX_LENGTH
        and CONFIG_KEY_PATTERN.match(config_key) is not None
    )


def is_sensitive_key(config_key: str) -> bool:
    """判断参数是否为安全敏感项（按前缀）。

    Args:
        config_key: 参数键。

    Returns:
        bool: 敏感 True。
    """
    return config_key.startswith(SENSITIVE_PREFIXES)


def infer_value_kind(default_value: str | None) -> str:
    """按平台默认值推断参数值类型。

    Args:
        default_value: 平台默认值（None 表示清单无此项，即租户自建键）。

    Returns:
        str: `bool` / `int` / `text`（自建键返回 `text`，不做类型约束）。
    """
    if default_value is None:
        return "text"
    lowered = default_value.strip().lower()
    if lowered in {"true", "false"}:
        return "bool"
    if re.fullmatch(r"-?\d+", lowered):
        return "int"
    return "text"


def is_value_valid(value: str, *, kind: str) -> bool:
    """按类型校验参数值（长度 + 类型形态）。

    Args:
        value: 参数值原文。
        kind: 值类型（`infer_value_kind` 的返回值）。

    Returns:
        bool: 合法 True。
    """
    if len(value) > CONFIG_VALUE_MAX_LENGTH:
        return False
    lowered = value.strip().lower()
    if kind == "bool":
        return lowered in {"true", "false"}
    if kind == "int":
        return re.fullmatch(r"-?\d+", lowered) is not None
    return True

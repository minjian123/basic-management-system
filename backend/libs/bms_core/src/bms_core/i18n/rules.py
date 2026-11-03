"""国际化规则（纯常量 + 纯函数，无 IO）：语言标识 / 文案 key / 归一 / 模块前缀。

前后端共用同一套口径（前端轻校验、后端强制）：

- 语言标识：IETF 语言标签（`zh-CN` / `en-US` / `ar-SA` / `zh-Hant-TW`），长度 ≤ 16；
  存**标准形态**（主语言小写、2 位区域大写、4 位脚本首字母大写），比较一律大小写不敏感。
- 文案 key：点分小写、至少两段（`模块.页面.字段`，如 `common.confirm`、`error.44001`），长度 ≤ 128。
- 文案值：≤ 4000 字符（与前端 `MESSAGE_VALUE_MAX` 对齐，避免无界写入）。
"""

import re

from bms_core.core.concurrent import ConcurrentStableList

__all__ = [
    "MESSAGE_KEY_MAX",
    "MESSAGE_VALUE_MAX",
    "is_locale_code_valid",
    "is_message_key_valid",
    "is_message_value_valid",
    "message_module",
    "normalize_locale",
]

LOCALE_CODE_MAX = 16
"""语言标识最大长度。"""

MESSAGE_KEY_MAX = 128
"""文案 key 最大长度。"""

MESSAGE_VALUE_MAX = 4000
"""文案值最大长度（与前端 `MESSAGE_VALUE_MAX` 对齐）。"""

_LOCALE_CODE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
"""IETF 语言标签（简化校验：主语言 2~3 位字母 + 可选子标签）。"""

_MESSAGE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
"""文案 key（点分小写、至少两段）。"""


def is_locale_code_valid(code: str) -> bool:
    """校验语言标识格式。

    Args:
        code: 语言标识（可含首尾空白）。

    Returns:
        bool: 合法 True。
    """
    text = (code or "").strip()
    return bool(text) and len(text) <= LOCALE_CODE_MAX and _LOCALE_CODE_RE.match(text) is not None


def normalize_locale(code: str) -> str:
    """归一语言标识为标准形态（`zh-cn` → `zh-CN`、`zh-hant-tw` → `zh-Hant-TW`）。

    Args:
        code: 语言标识（可含首尾空白）。

    Returns:
        str: 标准形态；空串原样返回。
    """
    parts = [part for part in (code or "").strip().split("-") if part]
    if not parts:
        return ""
    normalized: ConcurrentStableList[str] = ConcurrentStableList((parts[0].lower(),))
    for part in parts[1:]:
        if len(part) == 2:
            normalized.add(part.upper())
        elif len(part) == 4:
            normalized.add(part[:1].upper() + part[1:].lower())
        else:
            normalized.add(part)
    return "-".join(normalized)


def is_message_key_valid(key: str) -> bool:
    """校验文案 key 格式。

    Args:
        key: 文案 key。

    Returns:
        bool: 合法 True。
    """
    text = (key or "").strip()
    return bool(text) and len(text) <= MESSAGE_KEY_MAX and _MESSAGE_KEY_RE.match(text) is not None


def is_message_value_valid(value: str) -> bool:
    """校验文案值长度（空串合法：表示该语言缺失）。

    Args:
        value: 文案值。

    Returns:
        bool: 合法 True。
    """
    return len(value or "") <= MESSAGE_VALUE_MAX


def message_module(key: str) -> str:
    """取文案 key 的模块前缀（首段，派生不落列）。

    Args:
        key: 文案 key。

    Returns:
        str: 模块前缀；无点分时返回全串。
    """
    return (key or "").split(".")[0]

"""表单定制标识符白名单：字段键 / 物理列名 / 物理表名的**唯一登记处**（防注入第一道）。

**为什么单列一个模块**（任务 10_01）：DDL 由 SQLAlchemy `AddColumn` 参数化编译，本已不拼字符串；
但标识符（表名 / 列名）不是参数、只能进 DDL 文本，因此必须在**登记阶段**就把它们收窄到白名单形态，
做到「非法标识根本到不了编译层」。本模块是这条收窄的唯一实现，服务层与用例同源引用。

口径（对齐《命名规范》）：

- `field_key`：`^[a-z][a-z0-9_]{0,59}$`（小写字母开头，仅小写字母 / 数字 / 下划线，≤ 60）；
- `column_name`：`ext_` + `field_key` 的蛇形（前端 `extColumnName` 同算法），`^ext_[a-z][a-z0-9_]{0,59}$`；
- `table_name`：`^[a-z][a-z0-9_]{0,63}$`（表名单数 snake_case，平台 / 产品前缀）；
- **SQL 保留字**：`field_key` / `column_name` 不得与保留字相同（避免 DDL 需引号包裹、跨方言行为不一）。
"""

import re

from bms_core.core.concurrent import ConcurrentStableFrozenSet
from bms_core.core.exceptions import ParamError

__all__ = [
    "COLUMN_NAME_MAX_LENGTH",
    "COLUMN_NAME_PATTERN",
    "EXT_COLUMN_PREFIX",
    "FIELD_KEY_MAX_LENGTH",
    "FIELD_KEY_PATTERN",
    "SQL_RESERVED_WORDS",
    "TABLE_NAME_PATTERN",
    "derive_column_name",
    "normalize_field_key",
    "validate_column_name",
    "validate_field_key",
    "validate_table_name",
]

FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_]{0,59}$"
"""字段键格式（小写字母开头、仅小写字母 / 数字 / 下划线、≤ 60）。"""

COLUMN_NAME_PATTERN = r"^ext_[a-z][a-z0-9_]{0,59}$"
"""物理列名格式（`ext_` + 字段键蛇形）。"""

TABLE_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
"""物理表名格式（小写字母开头、仅小写字母 / 数字 / 下划线、≤ 64）。"""

EXT_COLUMN_PREFIX = "ext_"
"""自建字段物理列名前缀。"""

FIELD_KEY_MAX_LENGTH = 60
"""字段键最大长度（派生列名 `ext_` + 60 = 64，与列名上限一致）。"""

COLUMN_NAME_MAX_LENGTH = 64
"""物理列名最大长度（MySQL / PostgreSQL 标识符 64 字节内）。"""

_FIELD_KEY_RE = re.compile(FIELD_KEY_PATTERN)
_COLUMN_NAME_RE = re.compile(COLUMN_NAME_PATTERN)
_TABLE_NAME_RE = re.compile(TABLE_NAME_PATTERN)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9_]+")

SQL_RESERVED_WORDS: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    {
        "all",
        "and",
        "as",
        "asc",
        "between",
        "by",
        "case",
        "cast",
        "check",
        "column",
        "constraint",
        "create",
        "cross",
        "current",
        "database",
        "default",
        "delete",
        "desc",
        "distinct",
        "drop",
        "else",
        "end",
        "exists",
        "false",
        "from",
        "full",
        "grant",
        "group",
        "having",
        "in",
        "index",
        "inner",
        "insert",
        "into",
        "is",
        "join",
        "key",
        "left",
        "like",
        "limit",
        "not",
        "null",
        "on",
        "or",
        "order",
        "outer",
        "primary",
        "references",
        "right",
        "row",
        "select",
        "set",
        "table",
        "then",
        "true",
        "union",
        "unique",
        "update",
        "user",
        "using",
        "value",
        "values",
        "when",
        "where",
        "with",
    }
)
"""SQL 保留字（自建字段键 / 列名不得使用；`user` / `value` 等在部分方言需引号包裹）。"""


def derive_column_name(field_key: str) -> str:
    """由字段键派生物理列名（`ext_` + 蛇形；与前端 `extColumnName` 同算法）。

    Args:
        field_key: 字段键。

    Returns:
        str: 物理列名（`ext_` 前缀）。字段键非法时结果可能仍含非法字符，由 `validate_field_key`
            先行把关——本函数只做派生、不做校验（派生与校验分离，便于前端同算法预览）。
    """
    snake = _NON_ALNUM_RE.sub("_", field_key.strip().lower())
    snake = snake.strip("_")
    while "__" in snake:
        snake = snake.replace("__", "_")
    return f"{EXT_COLUMN_PREFIX}{snake}"


def normalize_field_key(field_key: str) -> str:
    """归一字段键（去空白 + 小写）。

    Args:
        field_key: 原始字段键。

    Returns:
        str: 归一后的字段键。
    """
    return field_key.strip().lower()


def validate_field_key(field_key: str) -> str:
    """校验字段键（白名单形态 + 非保留字）。

    Args:
        field_key: 字段键（调用方已 `normalize_field_key` 或原样传入，本函数内部再归一）。

    Returns:
        str: 归一后的字段键。

    Raises:
        ParamError: 形态非法或命中 SQL 保留字（10001）。
    """
    normalized = normalize_field_key(field_key)
    if _FIELD_KEY_RE.fullmatch(normalized) is None:
        raise ParamError(f"字段键非法（须小写字母开头、仅小写字母 / 数字 / 下划线、≤ 60）：{field_key!r}")
    if normalized in SQL_RESERVED_WORDS:
        raise ParamError(f"字段键不得使用 SQL 保留字：{normalized}")
    return normalized


def validate_column_name(column_name: str) -> str:
    """校验物理列名（白名单形态 + 非保留字）。

    Args:
        column_name: 物理列名。

    Returns:
        str: 归一后的列名。

    Raises:
        ParamError: 形态非法或去前缀后命中 SQL 保留字（10001）。
    """
    normalized = column_name.strip().lower()
    if _COLUMN_NAME_RE.fullmatch(normalized) is None:
        raise ParamError(f"物理列名非法（须 ext_ + 小写字母开头、≤ 64）：{column_name!r}")
    if normalized[len(EXT_COLUMN_PREFIX) :] in SQL_RESERVED_WORDS:
        raise ParamError(f"物理列名不得使用 SQL 保留字：{normalized}")
    return normalized


def validate_table_name(table_name: str) -> str:
    """校验物理表名（白名单形态）。

    Args:
        table_name: 物理表名。

    Returns:
        str: 归一后的表名。

    Raises:
        ParamError: 形态非法（10001）。
    """
    normalized = table_name.strip().lower()
    if _TABLE_NAME_RE.fullmatch(normalized) is None:
        raise ParamError(f"物理表名非法（须小写字母开头、仅小写字母 / 数字 / 下划线、≤ 64）：{table_name!r}")
    return normalized

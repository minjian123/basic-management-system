"""原始 SQL 的表名与操作提取（仅标准库；静态校验与运行时守卫同源复用）。

- `operation_of`：语句操作归类（read / write / ddl / unknown）。
- `extract_tables`：提取语句涉及的表名（去注释 / 去标识符引号 / schema 限定取末段）。
- `analyze`：按操作归类产出 `TableRef` 列表。

口径：尽力提取、宁漏不误——无法识别表名（DDL / 复杂语句）时返回空，不臆造表名。
"""

import re
from dataclasses import dataclass

from bms_core.core.base import BaseObject

__all__ = ["TableRef", "analyze", "extract_tables", "operation_of"]

_READ_KEYWORDS: frozenset[str] = frozenset({"select", "with"})
_WRITE_KEYWORDS: frozenset[str] = frozenset({"insert", "update", "delete", "replace", "merge", "upsert"})
_DDL_KEYWORDS: frozenset[str] = frozenset({"create", "drop", "alter", "truncate", "rename", "comment"})

_IGNORED_TABLES: frozenset[str] = frozenset(
    {"select", "where", "set", "values", "on", "as", "dual", "only", "lateral", "from", "join"}
)
"""非表名 token（子查询 / 关键字误命中防护）。"""

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_IDENTIFIER_QUOTES = re.compile(r"[`\"\[\]]")
_FIRST_WORD = re.compile(r"[a-z]+")
_TABLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfrom\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)", re.IGNORECASE),
    re.compile(r"\bjoin\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)", re.IGNORECASE),
    re.compile(r"\binto\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)", re.IGNORECASE),
    re.compile(r"\bupdate\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)", re.IGNORECASE),
)


@dataclass(frozen=True)
class TableRef(BaseObject):
    """SQL 中引用的表（表名 + 操作）。"""

    table: str
    """表名（小写；schema 限定取末段）。"""

    operation: str
    """操作归类：read / write / ddl / unknown。"""


def _clean(statement: str) -> str:
    """去注释与标识符引号（保留字面量内容；用于表名提取）。

    Args:
        statement: 原始 SQL。

    Returns:
        str: 清洗后的 SQL。
    """
    text = _BLOCK_COMMENT.sub(" ", statement)
    text = _LINE_COMMENT.sub(" ", text)
    return _IDENTIFIER_QUOTES.sub("", text)


def operation_of(statement: str) -> str:
    """语句操作归类。

    Args:
        statement: SQL 语句。

    Returns:
        str: `read` / `write` / `ddl` / `unknown`。
    """
    cleaned = _clean(statement).lstrip("( \t\r\n")
    match = _FIRST_WORD.match(cleaned.lower())
    word = match.group(0) if match else ""
    if word in _READ_KEYWORDS:
        return "read"
    if word in _WRITE_KEYWORDS:
        return "write"
    if word in _DDL_KEYWORDS:
        return "ddl"
    return "unknown"


def extract_tables(statement: str) -> tuple[str, ...]:
    """提取语句涉及的表名（保序去重）。

    Args:
        statement: SQL 语句。

    Returns:
        tuple[str, ...]: 表名元组（小写；schema 限定取末段）。
    """
    cleaned = _clean(statement)
    found: list[str] = []
    for pattern in _TABLE_PATTERNS:
        for raw in pattern.findall(cleaned):
            table = raw.split(".")[-1].lower()
            if table in _IGNORED_TABLES or table in found:
                continue
            found.append(table)
    return tuple(found)


def analyze(statement: str) -> tuple[TableRef, ...]:
    """按操作归类产出表引用列表。

    Args:
        statement: SQL 语句。

    Returns:
        tuple[TableRef, ...]: 表引用元组（同表仅出现一次）。
    """
    operation = operation_of(statement)
    return tuple(TableRef(table=table, operation=operation) for table in extract_tables(statement))

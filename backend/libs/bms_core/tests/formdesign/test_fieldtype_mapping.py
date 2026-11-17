"""自建字段四库类型映射（Kiwi 2526）：8 类型 × 4 方言 ADD COLUMN 编译逐字断言。"""

import pytest
from alembic.ddl.base import AddColumn
from sqlalchemy import Column

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db import dialects  # noqa: F401 - 注册 dmxa 方言
from bms_core.fieldtype.mapping import (
    EXT_FIELD_TYPE_KEYS,
    ext_column_type,
    ext_column_type_name,
    is_ext_field_type,
)

pytestmark = pytest.mark.kiwi_id(2526)

_EXPECTED: ConcurrentStableList[tuple[str, str, str]] = ConcurrentStableList(
    (
        ("text", "sqlite", "VARCHAR(255)"),
        ("text", "mysql", "VARCHAR(255)"),
        ("text", "postgresql", "VARCHAR(255)"),
        ("text", "dm", "VARCHAR2(255 CHAR)"),
        ("longtext", "sqlite", "TEXT"),
        ("longtext", "mysql", "TEXT"),
        ("longtext", "postgresql", "TEXT"),
        ("longtext", "dm", "TEXT"),
        ("number", "sqlite", "NUMERIC(18, 4)"),
        ("number", "mysql", "NUMERIC(18, 4)"),
        ("number", "postgresql", "NUMERIC(18, 4)"),
        ("number", "dm", "NUMERIC(18, 4)"),
        ("datetime", "sqlite", "DATETIME"),
        ("datetime", "mysql", "DATETIME"),
        ("datetime", "postgresql", "TIMESTAMP WITHOUT TIME ZONE"),
        ("datetime", "dm", "DATETIME"),
        ("option", "sqlite", "VARCHAR(64)"),
        ("option", "mysql", "VARCHAR(64)"),
        ("option", "postgresql", "VARCHAR(64)"),
        ("option", "dm", "VARCHAR2(64 CHAR)"),
        ("option_multi", "sqlite", "TEXT"),
        ("option_multi", "mysql", "TEXT"),
        ("option_multi", "postgresql", "TEXT"),
        ("option_multi", "dm", "TEXT"),
        ("switch", "sqlite", "SMALLINT"),
        ("switch", "mysql", "SMALLINT"),
        ("switch", "postgresql", "SMALLINT"),
        ("switch", "dm", "SMALLINT"),
        ("file", "sqlite", "VARCHAR(255)"),
        ("file", "mysql", "VARCHAR(255)"),
        ("file", "postgresql", "VARCHAR(255)"),
        ("file", "dm", "VARCHAR2(255 CHAR)"),
    )
)
"""期望列类型（8 类型 × 4 方言逐条；与设计文档映射表同源）。"""


def _compile(field_type: str, dialect_name: str) -> str:
    """编译某类型在某方言下的 ADD COLUMN（达梦经 dmxa 方言）。

    Args:
        field_type: 自建字段类型。
        dialect_name: 方言名（sqlite / mysql / postgresql / dm）。

    Returns:
        str: DDL 文本。
    """
    if dialect_name == "sqlite":
        from sqlalchemy.dialects import sqlite

        dialect = sqlite.dialect()
    elif dialect_name == "mysql":
        from sqlalchemy.dialects import mysql

        dialect = mysql.dialect()
    elif dialect_name == "postgresql":
        from sqlalchemy.dialects import postgresql

        dialect = postgresql.dialect()
    else:
        from dmSQLAlchemy.dmpython import DMDialect_dmPython

        dialect = DMDialect_dmPython()
    column = Column(f"ext_{field_type}", ext_column_type(field_type), nullable=True)
    return str(AddColumn("biz_demo", column).compile(dialect=dialect))


@pytest.mark.parametrize("field_type", list(EXT_FIELD_TYPE_KEYS))
def test_ext_column_type_matches_four_dialects(field_type: str) -> None:
    """8 类型 × 4 方言的列类型落点与设计表逐字一致（「DDL 四库一致」的机器证据）。

    Args:
        field_type: 自建字段类型（参数化）。
    """
    cases = [(name, expected) for kind, name, expected in _EXPECTED if kind == field_type]
    assert len(cases) == 4, f"{field_type} 缺少方言期望"
    for dialect_name, expected_type in cases:
        sql = _compile(field_type, dialect_name)
        assert expected_type in sql, f"{field_type}/{dialect_name}: {sql}"


def test_ext_column_type_name_and_whitelist() -> None:
    r"""逻辑类型名与白名单判定（文档登记与 \`40404\` 判据同源）。"""
    assert ext_column_type_name("number") == "DECIMAL(18,4)"
    assert ext_column_type_name("longtext") == "TEXT"
    assert is_ext_field_type("text") is True
    assert is_ext_field_type("richtext") is False


def test_ext_column_type_rejects_unknown() -> None:
    r"""白名单外类型抛 \`NotFoundError\`（10002；调用方应先判 \`40404\`）。"""
    from bms_core.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        ext_column_type("richtext")
    with pytest.raises(NotFoundError):
        ext_column_type_name("richtext")


def test_add_column_ddl_carries_only_whitelisted_tokens() -> None:
    """DDL 文本只由白名单标识符 + 方言类型构成（不拼用户输入）。"""
    assert _compile("text", "sqlite") == "ALTER TABLE biz_demo ADD COLUMN ext_text VARCHAR(255)"

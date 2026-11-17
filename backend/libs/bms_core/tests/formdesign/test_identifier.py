"""标识符白名单与注入拒收（Kiwi 2526）：字段键 / 列名 / 表名的登记期拦截。"""

import pytest

from bms_core.core.exceptions import ParamError
from bms_core.formdesign.identifier import (
    derive_column_name,
    normalize_field_key,
    validate_column_name,
    validate_field_key,
    validate_table_name,
)

pytestmark = pytest.mark.kiwi_id(2526)


def test_derive_column_name_snake_case() -> None:
    """列名派生：驼峰 / 空格 / 点 / 连字符统一转下划线（与前端 `extColumnName` 同算法）。"""
    assert derive_column_name("projectNo") == "ext_projectno"
    assert derive_column_name("Project No.") == "ext_project_no"
    assert derive_column_name("  a--b  ") == "ext_a_b"


def test_validate_field_key_normalizes_and_accepts() -> None:
    """合法字段键：去空白 + 小写后通过。"""
    assert normalize_field_key(" Name ") == "name"
    assert validate_field_key(" Project_No ") == "project_no"


@pytest.mark.parametrize(
    "raw",
    [
        "1abc",
        "a-b",
        "a b",
        "a;drop table users",
        "a'--",
        'a"or"1"="1',
        "a/*x*/",
        "select",
        "user",
        "a" * 61,
        "",
    ],
)
def test_validate_field_key_rejects_injection_and_reserved(raw: str) -> None:
    """注入形态 / 保留字 / 超长 / 空 一律在登记阶段拒收（10001）。"""
    with pytest.raises(ParamError):
        validate_field_key(raw)


@pytest.mark.parametrize(
    "raw",
    ["ext_x'--", "ext_1a", "ext_a;b", "ext_a b", "x_ext_a", "ext_" + "a" * 61],
)
def test_validate_column_name_rejects(raw: str) -> None:
    """列名须 `ext_` 前缀 + 合法蛇形；注入形态拒收（10001）。"""
    with pytest.raises(ParamError):
        validate_column_name(raw)


def test_validate_column_name_accepts_and_rejects_reserved() -> None:
    """合法列名通过；去前缀命中保留字拒收。"""
    assert validate_column_name("ext_project_no") == "ext_project_no"
    with pytest.raises(ParamError):
        validate_column_name("ext_select")


@pytest.mark.parametrize("raw", ["sys_user; drop", "sys-user", "1abc", "sys_user'--", "a" * 65])
def test_validate_table_name_rejects(raw: str) -> None:
    """表名白名单拒绝注入与非法形态（10001）。"""
    with pytest.raises(ParamError):
        validate_table_name(raw)


def test_validate_table_name_accepts() -> None:
    """合法表名通过并小写归一。"""
    assert validate_table_name("Biz_Demo") == "biz_demo"


def test_derive_column_name_collapses_repeated_underscores() -> None:
    """连续下划线折叠为单个（`a__b` → `ext_a_b`），保证列名稳定可读。"""
    assert derive_column_name("a__b") == "ext_a_b"
    assert derive_column_name("a___b") == "ext_a_b"

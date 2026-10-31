"""系统参数规则表用例（Kiwi 2373）：键格式 / 值类型推断与校验 / 敏感前缀 / 依赖表。

规则为纯函数（无 IO），用例只断言判定结果与登记内容，不触碰库与缓存。
"""

import pytest

from bms_core.config.rules import (
    CONFIG_DEPENDS,
    CONFIG_KEY_MAX_LENGTH,
    CONFIG_VALUE_MAX_LENGTH,
    infer_value_kind,
    is_config_key_valid,
    is_sensitive_key,
    is_value_valid,
)

pytestmark = pytest.mark.kiwi_id(2373)


@pytest.mark.parametrize(
    "config_key",
    ("password.max_age_days", "role.code_pattern", "captcha.scene.login.ttl", "custom", "a.b.c"),
)
def test_key_format_accepts_dotted_lowercase(config_key: str) -> None:
    """合法键：点分小写（单段也合法）。

    Args:
        config_key: 参数键。
    """
    assert is_config_key_valid(config_key) is True


@pytest.mark.parametrize("config_key", ("Password.Max", "1password", "password.", ".password", "pass word", ""))
def test_key_format_rejects_illegal(config_key: str) -> None:
    """非法键：大写 / 数字开头 / 空段 / 空格 / 空串。

    Args:
        config_key: 参数键。
    """
    assert is_config_key_valid(config_key) is False


def test_key_length_limit() -> None:
    """键长度上限与列宽一致（128）。"""
    assert is_config_key_valid("a" * (CONFIG_KEY_MAX_LENGTH - 1)) is True
    assert is_config_key_valid("a" * (CONFIG_KEY_MAX_LENGTH + 1)) is False


@pytest.mark.parametrize(
    ("key", "expected"),
    (
        ("password.min_length", True),
        ("account.inactive_lock_days", True),
        ("session.max_active", True),
        ("ai.auto_execute", True),
        ("file.upload.max_size", False),
        ("menu.tree_cache_ttl", False),
    ),
)
def test_sensitive_prefix(key: str, expected: bool) -> None:
    """敏感判定：按前缀（password / account / session / ai）。

    Args:
        key: 参数键。
        expected: 期望结果。
    """
    assert is_sensitive_key(key) is expected


@pytest.mark.parametrize(
    ("default_value", "kind"),
    (("true", "bool"), ("FALSE", "bool"), ("90", "int"), ("-1", "int"), ("^[a-z]+$", "text"), (None, "text")),
)
def test_infer_value_kind(default_value: str | None, kind: str) -> None:
    """类型推断：布尔 / 整数 / 文本；清单无此项（租户自建）按文本。

    Args:
        default_value: 平台默认值。
        kind: 期望类型。
    """
    assert infer_value_kind(default_value) == kind


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    (
        ("true", "bool", True),
        ("yes", "bool", False),
        ("90", "int", True),
        ("9.5", "int", False),
        ("任意文本", "text", True),
        ("x" * (CONFIG_VALUE_MAX_LENGTH + 1), "text", False),
    ),
)
def test_value_validation(value: str, kind: str, expected: bool) -> None:
    """值校验：类型形态 + 长度上限。

    Args:
        value: 参数值。
        kind: 值类型。
        expected: 期望结果。
    """
    assert is_value_valid(value, kind=kind) is expected


def test_dependency_table_contents() -> None:
    """依赖表：`ai.auto_approve` 依赖 `ai.auto_execute` 开启。"""
    dependency = CONFIG_DEPENDS.get("ai.auto_approve")
    assert dependency is not None
    assert dependency.depends_on == "ai.auto_execute"
    assert dependency.expected == "true"

"""密码策略真实实现用例（Kiwi 2209，03_05）。

覆盖：复杂度四规则（长度 / 大小写 / 数字 / 符号 / 不得含用户名）正反与缺失项顺序；按租户配置覆盖即时生效；
非法值回落默认；有效期（`password.max_age_days`）；历史比对（PBKDF2）与 `history_count`；Null 回落。
"""

from datetime import datetime, timedelta
from typing import cast

import pytest

from bms_core.config.base import BaseConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.password.base import PASSWORD_HISTORY_COUNT
from bms_core.password.default import (
    DEFAULT_MAX_AGE_DAYS,
    DefaultPasswordPolicy,
    resolve_inactive_lock_days,
)
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher


class _MappingSource(BaseConfigSource):
    """内存取数替身（返回预置键值子集；值可为任意类型以覆盖非法分支）。"""

    def __init__(self, values: ConcurrentStableDict[str, object] | None = None) -> None:
        self._values = dict(values or {})

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """返回预置映射的子集。

        Args:
            keys: 参数键序列（插入序）。

        Returns:
            ConcurrentStableDict[str, str]: 命中键 → 值（插入序）。
        """
        return ConcurrentStableDict({key: cast("str", self._values[key]) for key in keys if key in self._values})


def _hasher() -> Pbkdf2PasswordHasher:
    """低迭代 PBKDF2（测试提速；仍满足下限）。

    Returns:
        Pbkdf2PasswordHasher: 哈希实现。
    """
    return Pbkdf2PasswordHasher(iterations=100_000)


def _policy(config: BaseConfigSource | None = None) -> DefaultPasswordPolicy:
    """构造密码策略（默认 Null 取数 + 低迭代哈希）。

    Args:
        config: 参数取数实现（缺省 Null）。

    Returns:
        DefaultPasswordPolicy: 密码策略实例。
    """
    return DefaultPasswordPolicy(config=config or NullConfigSource(), hasher=_hasher())


@pytest.mark.kiwi_id(2209)
async def test_validate_default_accepts_strong_password() -> None:
    """默认规则下合规密码通过（空元组）。"""
    assert await _policy().validate("Str0ng!Pass", username="admin") == ()


@pytest.mark.kiwi_id(2209)
async def test_validate_reports_violations_in_order() -> None:
    """四规则缺失项与顺序（长度 / 大小写 / 数字 / 符号 / 用户名）。"""
    violations = await _policy().validate("ab", username="admin")
    assert violations == ("too_short", "need_upper", "need_digit", "need_symbol")

    no_lower = await _policy().validate("AB1!", username=None)
    assert no_lower == ("too_short", "need_lower")

    with_username = await _policy().validate("Admin123!", username="admin")
    assert with_username == ("username_included",)

    too_long = await _policy().validate("A1!" + "a" * 200, username=None)
    assert too_long == ("too_long",)


@pytest.mark.kiwi_id(2209)
async def test_validate_true_string_config_values() -> None:
    """真值字符串配置直通（`true` / `1` / `yes` / `on`）。"""
    for raw in ("true", "1", "yes", "on"):
        source = _MappingSource(ConcurrentStableDict({"password.require_symbol": raw}))
        violations = await _policy(source).validate("Abcdefg1", username=None)
        assert violations == ("need_symbol",)


@pytest.mark.kiwi_id(2209)
async def test_validate_reads_tenant_overrides() -> None:
    """按租户覆盖复杂度规则即时生效。"""
    source = _MappingSource(
        ConcurrentStableDict(
            {
                "password.min_length": "3",
                "password.require_upper": "false",
                "password.require_lower": "false",
                "password.require_digit": "false",
                "password.require_symbol": "false",
                "password.forbid_username": "false",
            }
        )
    )
    assert await _policy(source).validate("abc", username="abc") == ()


@pytest.mark.kiwi_id(2209)
async def test_validate_invalid_values_fall_back() -> None:
    """非法 / 越界配置回落默认（不抛错）。"""
    source = _MappingSource(
        ConcurrentStableDict(
            {
                "password.min_length": "abc",
                "password.max_length": "0",
                "password.require_symbol": "maybe",
            }
        )
    )
    violations = await _policy(source).validate("Ab1", username=None)
    assert "too_short" in violations and "need_symbol" in violations


@pytest.mark.kiwi_id(2209)
async def test_expired_uses_max_age_days() -> None:
    """有效期：超期 True / 未超 False；按租户 max_age_days 覆盖。"""
    now = datetime(2026, 9, 27, tzinfo=None)
    fresh = now - timedelta(days=DEFAULT_MAX_AGE_DAYS - 1)
    stale = now - timedelta(days=DEFAULT_MAX_AGE_DAYS + 1)
    policy = _policy()
    assert await policy.expired(fresh, now=now) is False
    assert await policy.expired(stale, now=now) is True

    shorter = _policy(_MappingSource(ConcurrentStableDict({"password.max_age_days": "10"})))
    assert await shorter.expired(now - timedelta(days=11), now=now) is True
    assert await shorter.expired(now - timedelta(days=9), now=now) is False


@pytest.mark.kiwi_id(2209)
async def test_reused_matches_history_hashes() -> None:
    """历史比对：命中旧哈希 True、未命中 False、空历史 False。"""
    hasher = _hasher()
    policy = DefaultPasswordPolicy(config=NullConfigSource(), hasher=hasher)
    old = hasher.hash("OldPass1!")
    assert await policy.reused("OldPass1!", history=[old]) is True
    assert await policy.reused("NewPass2!", history=[old]) is False
    assert await policy.reused("OldPass1!", history=[]) is False


@pytest.mark.kiwi_id(2209)
async def test_history_count_override_and_default() -> None:
    """历史条数：默认平台值；按租户覆盖生效；非法回落默认。"""
    assert await _policy().history_count() == PASSWORD_HISTORY_COUNT
    assert await _policy(_MappingSource(ConcurrentStableDict({"password.history_count": "3"}))).history_count() == 3
    assert (
        await _policy(_MappingSource(ConcurrentStableDict({"password.history_count": "0"}))).history_count()
        == PASSWORD_HISTORY_COUNT
    )


@pytest.mark.kiwi_id(2209)
async def test_resolve_inactive_lock_days() -> None:
    """未登录锁定天数：默认 180；按租户覆盖；非法回落。"""
    assert await resolve_inactive_lock_days(NullConfigSource()) == 180
    assert (
        await resolve_inactive_lock_days(_MappingSource(ConcurrentStableDict({"account.inactive_lock_days": "30"})))
        == 30
    )
    assert (
        await resolve_inactive_lock_days(_MappingSource(ConcurrentStableDict({"account.inactive_lock_days": "-1"})))
        == 180
    )


@pytest.mark.kiwi_id(2209)
async def test_null_policy_contract_and_defaults() -> None:
    """Null 取数恒空；`NullPasswordPolicy` 恒定通过且派生 `history_count` 取默认（向后兼容）。"""
    from bms_core.password.null import NullPasswordPolicy

    assert await NullConfigSource().get_many(ConcurrentStableList(("password.min_length",))) == {}
    null_policy = NullPasswordPolicy()
    assert await null_policy.validate("x") == ()
    assert await null_policy.expired(datetime(2000, 1, 1, tzinfo=None)) is False
    assert await null_policy.reused("x", history=["h"]) is False
    assert await null_policy.history_count() == PASSWORD_HISTORY_COUNT


@pytest.mark.kiwi_id(2209)
async def test_expired_boundary_and_boolean_config_values() -> None:
    """有效期边界（恰好等于阈值不过期）；布尔配置值直通。"""
    now = datetime(2026, 9, 27, tzinfo=None)
    exactly = now - timedelta(days=DEFAULT_MAX_AGE_DAYS)
    assert await _policy().expired(exactly, now=now) is False

    bool_source = _MappingSource(ConcurrentStableDict({"password.require_upper": False}))
    assert "need_upper" not in await _policy(bool_source).validate("lower1!", username=None)

"""密码策略基座契约（Kiwi 41）：继承 / 恒定允许 / 违规码常量 / 依赖解析。

重写口径（13_11）：依赖解析读装配态应用，不再自建壳、不往应用挂探针路由。
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.password.base import PASSWORD_VIOLATIONS, BasePasswordPolicy
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.password.null import NullPasswordPolicy


@pytest.mark.kiwi_id(41)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BasePasswordPolicy, BaseCapability)
    assert issubclass(NullPasswordPolicy, BasePasswordPolicy)
    assert issubclass(NullPasswordPolicy, BaseNullObject)
    assert BasePasswordPolicy.key == "password_policy"

    policy = NullPasswordPolicy()
    assert policy.placeholder is True
    assert "占位实现" in policy.describe()


@pytest.mark.kiwi_id(41)
def test_violation_codes() -> None:
    """违规原因码清单：七项、无重复、均为非空字符串。"""
    assert PASSWORD_VIOLATIONS == (
        "too_short",
        "too_long",
        "need_upper",
        "need_lower",
        "need_digit",
        "need_symbol",
        "username_included",
    )
    assert len(set(PASSWORD_VIOLATIONS)) == len(PASSWORD_VIOLATIONS)
    assert all(code for code in PASSWORD_VIOLATIONS)


@pytest.mark.kiwi_id(41)
async def test_null_policy_always_allows() -> None:
    """占位实现恒定允许：validate 返回空元组、expired / reused 恒定 False。"""
    policy = NullPasswordPolicy()
    assert await policy.validate("123", username="admin") == ()
    assert await policy.validate("") == ()

    long_ago = datetime.now(UTC) - timedelta(days=365)
    assert await policy.expired(long_ago) is False
    assert await policy.expired(long_ago, now=datetime.now(UTC)) is False

    assert await policy.reused("whatever", history=ConcurrentStableList(["a", "b"])) is False
    assert await policy.reused("whatever", history=ConcurrentStableList()) is False


@pytest.mark.kiwi_id(41)
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态密码策略是默认实现，且装配器记录的提供者与本应用一致。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    policy = service_app.state.password_policy
    assert isinstance(policy, DefaultPasswordPolicy)
    assert service_app.state.plugin_providers["password_policy"] == "default"

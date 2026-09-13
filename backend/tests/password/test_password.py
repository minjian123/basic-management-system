"""密码策略基座契约测试（Kiwi 41）：继承 / 恒定允许 / 违规码常量 / 依赖解析。"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_password_policy
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app
from app.password.base import (
    PASSWORD_VIOLATIONS,
    BasePasswordPolicy,
    NullPasswordPolicy,
)


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

    assert await policy.reused("whatever", history=("a", "b")) is False
    assert await policy.reused("whatever", history=()) is False


@pytest.mark.kiwi_id(41)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位密码策略；路由经 get_password_policy 取到实例。"""
    app = create_app()
    assert isinstance(app.state.password_policy, NullPasswordPolicy)

    @app.get("/policy")
    async def policy_info(policy: Annotated[BasePasswordPolicy, Depends(get_password_policy)]) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"key": policy.key, "type": type(policy).__name__}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/policy")

    assert resp.status_code == 200
    assert resp.json() == {"key": "password_policy", "type": "NullPasswordPolicy"}

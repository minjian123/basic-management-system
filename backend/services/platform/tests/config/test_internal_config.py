"""系统参数内部读端点用例（Kiwi 2207，03_08）。

覆盖：`POST /api/v1/platform/internal/configs/resolve` 服务 JWT 鉴权（白名单服务放行 / 网关与无票据拒绝）与响应映射。
"""

from collections.abc import Mapping, Sequence

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_config_source
from bms_core.config.base import BaseConfigSource
from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier

API = "/api/v1/platform/internal/configs/resolve"


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001/401）。
        """
        if token == "identity":
            return VerifiedToken(subject="identity", service="identity", token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


class _FakeConfigSource(BaseConfigSource):
    """测试替身：固定键值。"""

    async def get_many(self, keys: Sequence[str]) -> Mapping[str, str]:
        """返回预置键值子集。

        Args:
            keys: 参数键序列。

        Returns:
            Mapping[str, str]: 命中键 → 值。
        """
        pool = {"captcha.scene.login.fail_threshold": "3", "captcha.channel.sms": "false"}
        return {key: pool[key] for key in keys if key in pool}


@pytest.fixture(autouse=True)
def _override_deps(service_app: FastAPI) -> None:  # pyright: ignore[reportUnusedFunction]
    """覆盖令牌校验器与参数取数（避免真实外呼 / 连库）。"""
    service_app.dependency_overrides[get_token_verifier] = _StubVerifier
    service_app.dependency_overrides[get_config_source] = _FakeConfigSource


@pytest.mark.kiwi_id(2207)
async def test_resolve_requires_service_identity(client: AsyncClient) -> None:
    """内部端点：白名单服务 JWT 放行并返回存在键；网关 / 无票据拒绝。"""
    ok = await client.post(
        API,
        json={"keys": ["captcha.scene.login.fail_threshold", "missing"]},
        headers={"Authorization": "Bearer identity"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["values"] == {"captcha.scene.login.fail_threshold": "3"}

    gateway = await client.post(
        API, json={"keys": ["captcha.channel.sms"]}, headers={"Authorization": "Bearer gateway"}
    )
    assert gateway.status_code == 401

    anonymous = await client.post(API, json={"keys": ["captcha.channel.sms"]}, headers={"Authorization": ""})
    assert anonymous.status_code == 401

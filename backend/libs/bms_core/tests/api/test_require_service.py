"""服务身份依赖 `require_service` 测试（Kiwi 2250）：产品服务身份入站白名单（复用既有基座）。

`require_service` 是产品服务**服务间入站**的统一入口（东向内部端点）：按 `aud=service` 全校验服务 JWT，
并限定签发方服务标识白名单——产品服务（如 `mdm-org`）与平台服务同构复用，无需另起认证基座。
"""

from collections.abc import Awaitable, Callable

import pytest

from bms_core.api.base import require_service
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import AuthError
from bms_core.oauth.token import TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken

pytestmark = pytest.mark.kiwi_id(2250)


class _StubVerifier(BaseTokenVerifier):
    """占位校验器：记录期望受众并返回注入的服务身份声明。"""

    plugin_name = "stub-require-service"

    def __init__(self, *, service: str = "mdm-org", error: Exception | None = None) -> None:
        """初始化。

        Args:
            service: 返回的服务标识（签发方）。
            error: 注入异常（非空时 `verify` 抛出）。
        """
        self._service = service
        self._error = error
        self.audiences: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按注入结果返回服务身份声明或抛错。

        Args:
            token: 令牌串（忽略）。
            audience: 期望受众（记录以供断言）。

        Returns:
            VerifiedToken: 注入的服务身份声明。

        Raises:
            Exception: 注入的异常。
        """
        assert token
        self.audiences.add(audience)
        if self._error is not None:
            raise self._error
        return VerifiedToken(subject=self._service, token_type="service", service=self._service)


_Dependency = Callable[..., Awaitable[VerifiedToken]]


async def _call(
    dependency: _Dependency,
    *,
    authorization: str | None,
    verifier: BaseTokenVerifier,
) -> VerifiedToken:
    """调用依赖函数（显式传入校验器，绕开依赖注入）。

    Args:
        dependency: `require_service(...)` 产出的依赖函数。
        authorization: `Authorization` 头。
        verifier: 统一校验器替身。

    Returns:
        VerifiedToken: 依赖返回的身份声明。
    """
    return await dependency(verifier=verifier, authorization=authorization)


async def test_product_service_identity_in_whitelist_passes() -> None:
    """产品服务身份在白名单内：放行，且按 `aud=service` 全校验。"""
    verifier = _StubVerifier(service="mdm-org")
    verified = await _call(require_service("mdm-org"), authorization="Bearer tok", verifier=verifier)
    assert verified.service == "mdm-org"
    assert verifier.audiences == [TOKEN_AUDIENCE_SERVICE]


async def test_service_identity_out_of_whitelist_rejected() -> None:
    """签发方不在白名单（如经网关误信的 `gateway` 服务 JWT）：拒绝（20001 / 401）。"""
    verifier = _StubVerifier(service="gateway")
    with pytest.raises(AuthError) as excinfo:
        await _call(require_service("mdm-org"), authorization="Bearer tok", verifier=verifier)
    assert excinfo.value.code == 20001
    assert excinfo.value.http_status == 401


async def test_missing_credentials_rejected() -> None:
    """缺少服务身份凭证：拒绝（20001 / 401），不进入校验。"""
    verifier = _StubVerifier()
    with pytest.raises(AuthError):
        await _call(require_service("mdm-org"), authorization=None, verifier=verifier)
    assert verifier.audiences == []


async def test_empty_whitelist_accepts_any_verified_service() -> None:
    """白名单为空 = 不限定调用方（仍须通过服务 JWT 全校验）。"""
    verifier = _StubVerifier(service="platform")
    verified = await _call(require_service(), authorization="Bearer tok", verifier=verifier)
    assert verified.service == "platform"

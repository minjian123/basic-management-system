"""入站能力判定依赖用例（07B `03_01`）：`require_capability` / `require_capability_or_service`。

覆盖判定顺序：网关代发票据拒 → 白名单放行 → 能力分配判定；以及「票据无签发方」与「无凭证」两条拒法。
"""

from typing import Any

import pytest

from bms_core.api import capability as capability_module
from bms_core.api.capability import require_capability, require_capability_or_service
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import AuthError, PermissionError
from bms_core.oauth.verify import VerifiedToken

_CAPABILITY = "platform.user.query"


class _Verifier:
    """令牌校验替身：按令牌串返回固定身份声明。"""

    def __init__(self, *, service: str) -> None:
        """初始化。

        Args:
            service: 返回的签发方服务标识（空串表示票据缺签发方）。
        """
        self._service = service

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """返回固定身份。

        Args:
            token: 令牌串（未使用）。
            audience: 目标受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。
        """
        del token, audience
        return VerifiedToken(subject="svc", service=self._service, scopes=ConcurrentStableFrozenList())


class _Metrics:
    """指标器替身（计数不落库）。"""

    def increment(self, *_args: object, **_kwargs: object) -> None:
        """忽略计数。

        Args:
            *_args: 位置参数（未使用）。
            **_kwargs: 关键字参数（未使用）。
        """


async def _call(dependency: Any, *, authorization: str | None, service: str) -> VerifiedToken:
    """执行一次依赖调用。

    Args:
        dependency: `require_capability(...)` 产出的依赖函数。
        authorization: `Authorization` 头。
        service: 校验替身返回的签发方。

    Returns:
        VerifiedToken: 依赖返回值。
    """
    return await dependency(
        verifier=_Verifier(service=service),
        metrics=_Metrics(),
        authorization=authorization,
    )


async def test_missing_credentials_rejected() -> None:
    """无票据：401（缺少服务身份凭证）。"""
    with pytest.raises(AuthError, match="缺少服务身份凭证"):
        await _call(require_capability(_CAPABILITY), authorization=None, service="mdm")


async def test_token_without_issuer_rejected() -> None:
    """票据无签发方：401（服务身份缺少签发方标识）。"""
    with pytest.raises(AuthError, match="服务身份缺少签发方标识"):
        await _call(require_capability(_CAPABILITY), authorization="Bearer tok", service="")


async def test_gateway_token_rejected() -> None:
    """网关代发的服务票据不得作为能力消费方：403。"""
    with pytest.raises(PermissionError, match="网关代发的服务票据"):
        await _call(require_capability(_CAPABILITY), authorization="Bearer tok", service="gateway")


async def test_whitelisted_service_passes_without_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """白名单内的平台内部服务：不参与能力分配，直接放行。"""
    called: ConcurrentStableList[str] = ConcurrentStableList()

    async def _never(*_args: object, **_kwargs: object) -> None:
        """记录误调用。

        Args:
            *_args: 位置参数（未使用）。
            **_kwargs: 关键字参数（未使用）。
        """
        called.append("access")

    monkeypatch.setattr(capability_module, "check_capability_access", _never)

    verified = await _call(
        require_capability_or_service(_CAPABILITY, "identity"),
        authorization="Bearer tok",
        service="identity",
    )

    assert verified.service == "identity"
    assert called == []


async def test_service_outside_whitelist_checked_by_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """不在白名单：按能力分配判定，判定通过即放行。"""
    seen: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()

    async def _granted(capability: str, consumer: str, **kwargs: object) -> None:
        """记录判定入参（视为已授权）。

        Args:
            capability: 能力名。
            consumer: 消费方服务键。
            **kwargs: 其它参数（未使用）。
        """
        del kwargs
        seen.append((capability, consumer))

    monkeypatch.setattr(capability_module, "check_capability_access", _granted)

    verified = await _call(require_capability(_CAPABILITY), authorization="Bearer tok", service="mdm")

    assert verified.service == "mdm"
    assert seen == [(_CAPABILITY, "mdm")]


async def test_service_without_grant_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """不在白名单且无有效分配：403（能力分配判定拒绝后原样上抛）。"""
    from bms_core.core.exceptions import PermissionError as BmsPermissionError

    async def _denied(_capability: str, _consumer: str, **kwargs: object) -> None:
        """模拟分配判定失败。

        Args:
            _capability: 能力名（未使用）。
            _consumer: 消费方（未使用）。
            **kwargs: 其它参数（未使用）。
        """
        del kwargs
        raise BmsPermissionError("无该能力分配")

    monkeypatch.setattr(capability_module, "check_capability_access", _denied)

    with pytest.raises(BmsPermissionError, match="无该能力分配"):
        await _call(require_capability(_CAPABILITY), authorization="Bearer tok", service="mdm")


async def test_or_service_token_without_issuer_rejected() -> None:
    """白名单变体：票据无签发方同样 401。"""
    with pytest.raises(AuthError, match="服务身份缺少签发方标识"):
        await _call(
            require_capability_or_service(_CAPABILITY, "identity"),
            authorization="Bearer tok",
            service="",
        )


async def test_or_service_falls_back_to_grant_when_not_whitelisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """白名单变体：不在白名单的调用方仍按能力分配判定，通过即放行。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    async def _granted(capability: str, consumer: str, **kwargs: object) -> None:
        """记录判定入参（视为已授权）。

        Args:
            capability: 能力名。
            consumer: 消费方服务键。
            **kwargs: 其它参数（未使用）。
        """
        del kwargs
        seen.add(f"{capability}:{consumer}")

    monkeypatch.setattr(capability_module, "check_capability_access", _granted)

    verified = await _call(
        require_capability_or_service(_CAPABILITY, "identity"),
        authorization="Bearer tok",
        service="mdm",
    )

    assert verified.service == "mdm"
    assert list(seen) == [f"{_CAPABILITY}:mdm"]


def test_bearer_token_rejects_other_schemes() -> None:
    """非 Bearer 方案 / 空令牌：取不到令牌（401 分支）。"""
    from bms_core.api.capability import _bearer_token  # pyright: ignore[reportPrivateUsage]

    assert _bearer_token("Basic abc") is None
    assert _bearer_token("Bearer   ") is None
    assert _bearer_token("Bearer abc") == "abc"


async def test_or_service_missing_credentials_rejected() -> None:
    """白名单变体：无票据 401。"""
    with pytest.raises(AuthError, match="缺少服务身份凭证"):
        await _call(
            require_capability_or_service(_CAPABILITY, "identity"),
            authorization=None,
            service="identity",
        )


async def test_or_service_gateway_token_rejected() -> None:
    """白名单变体：网关代发票据即使给了白名单也拒（403）。"""
    with pytest.raises(PermissionError, match="网关代发的服务票据"):
        await _call(
            require_capability_or_service(_CAPABILITY, "gateway"),
            authorization="Bearer tok",
            service="gateway",
        )

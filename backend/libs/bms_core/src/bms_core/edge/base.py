"""边缘信任能力域：请求净化与可信身份契约（真实用户 JWT 校验随 07_03 回补）。

- 身份头契约（网关注入 / 后端信任）见 `bms_core/edge/headers.py`（两端口径唯一来源）。
- `EdgeIdentity`：信任判定通过后解析出的可信身份（用户 id / 外部主体 / 租户 / scope / 服务身份）。
- `EdgeTrustDecision`：信任判定结果（是否信任 + 身份 + 原因）。
- `BaseEdgeTrust`：能力域中间层契约（`key = plugin_key = "edge"`）——`evaluate(headers) -> EdgeTrustDecision`；
  后端两侧口径：**只信任来自网关 / 带服务身份的流量**，不信任则后端剥除伪造头后按授权面拒绝。
- `get_edge_trust`：依赖注入提供者（按 `[edge].provider` 解析）。
- `require_edge_identity`：授权下沉依赖——读请求态 `edge_identity`（`EdgeGuardMiddleware` 写入），
  缺失即抛 `AuthError`（20001 / 401）；后端据此**只做授权、不重复认证**。

实现口径（07_03）：缺省 `provider` 空串解析到 `NullEdgeTrust`（恒定不信任，不引入假身份）；
`marker` 为网关标记头过渡实现（`MarkerEdgeTrust`）；**默认真实实现 `service_jwt`**（`ServiceJwtEdgeTrust`，
本地 JWKS 验签入站服务 JWT，网关凭服务 JWT 向内部证明、东西向同理）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.exceptions import AuthError
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.edge.headers import (
    SERVICE_IDENTITY_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
    USER_SUBJECT_HEADER,
)

__all__ = [
    "BaseEdgeTrust",
    "EdgeIdentity",
    "EdgeTrustDecision",
    "get_edge_trust",
    "require_edge_identity",
]


@dataclass(frozen=True)
class EdgeIdentity(BaseObject):
    """可信边缘身份（网关注入、后端信任）。"""

    user_id: int | None = None
    """网关验证过的内部用户标识；无 / 非法为 None（外部身份映射后填充）。"""

    subject: str | None = None
    """网关验证过的外部用户主体（IdP `sub`，字符串）；无为空（阶段六映射前唯一用户标识）。"""

    tenant_code: str | None = None
    """网关验证过的租户编码；无为空。"""

    scopes: tuple[str, ...] = ()
    """网关验证过的 scope 集合（逗号分隔头解析）。"""

    service_identity: str | None = None
    """服务身份（服务间调用）；无为空。"""

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> EdgeIdentity:
        """按身份头解析可信身份（规范化头名大小写）。

        Args:
            headers: 请求头映射（`str -> str`；键按大小写不敏感读取）。

        Returns:
            EdgeIdentity: 解析出的身份（缺失项为 None / 空元组；`user_id` 非法记 None）。
        """
        normalized = {key.lower(): value for key, value in headers.items()}
        raw_user_id = normalized.get(USER_ID_HEADER.lower())
        try:
            user_id = int(raw_user_id) if raw_user_id else None
        except ValueError:
            user_id = None
        subject = normalized.get(USER_SUBJECT_HEADER.lower()) or None
        raw_scopes = normalized.get(USER_SCOPES_HEADER.lower(), "")
        scopes = tuple(scope.strip() for scope in raw_scopes.split(",") if scope.strip())
        tenant_code = normalized.get(TENANT_ID_HEADER.lower()) or None
        service_identity = normalized.get(SERVICE_IDENTITY_HEADER.lower()) or None
        return cls(
            user_id=user_id,
            subject=subject,
            tenant_code=tenant_code,
            scopes=scopes,
            service_identity=service_identity,
        )


@dataclass(frozen=True)
class EdgeTrustDecision(BaseObject):
    """边缘信任判定结果。"""

    trusted: bool
    """是否来自可信边缘（网关注入 / 带服务身份）。"""

    identity: EdgeIdentity | None = None
    """可信身份；不信任为 None。"""

    reason: str | None = None
    """判定说明（诊断 / 日志用）；信任可为 None。"""


class BaseEdgeTrust(BasePluggable, ABC):
    """边缘信任契约：按请求头判定可信来源并解析身份。"""

    key: str = "edge"
    plugin_key: str = "edge"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def evaluate(self, headers: Mapping[str, str]) -> EdgeTrustDecision:
        """判定请求是否来自可信边缘并解析身份。

        Args:
            headers: 请求头映射（`str -> str`）。

        Returns:
            EdgeTrustDecision: 判定结果（不抛错）。
        """


def get_edge_trust(request: Request) -> BaseEdgeTrust:
    """取应用级边缘信任实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseEdgeTrust: 应用装配的边缘信任实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseEdgeTrust",
        resolve_plugin(
            "edge",
            settings.edge.provider,
            expected_version=BaseEdgeTrust.contract_version,
        ),
    )


def require_edge_identity(request: Request) -> EdgeIdentity:
    """授权下沉依赖：取可信边缘身份，缺失即未认证 / 网关旁路。

    Args:
        request: 请求对象（请求态由 `EdgeGuardMiddleware` 写入 `edge_identity`）。

    Returns:
        EdgeIdentity: 可信身份。

    Raises:
        AuthError: 无可信身份（未认证或网关旁路；20001 / 401）。
    """
    identity = cast("EdgeIdentity | None", request.scope.get("state", {}).get("edge_identity"))
    if identity is None:
        raise AuthError("缺少可信边缘身份（未认证或网关旁路）")
    return identity

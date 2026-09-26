"""security 能力域：安全原语（口令哈希 / 令牌编解码 / 会话安全）插件契约。

- 三能力域：`password_hasher`（口令哈希）/ `token_codec`（令牌编解码）/ `session_security`（会话安全）——
  各一插件键、各带真实实现与 fail-closed 的 Null 实现（`security/null.py`）。
- `BaseSecurity`：安全域中间层（统一密钥只走环境变量 / Secret、签名算法白名单、不落日志）。
- 提供者：`get_password_hasher` / `get_token_codec` / `get_session_security`（应用级单例，经配置解析实现）。
- 真实实现：`Pbkdf2PasswordHasher`（`security/pbkdf2.py`）、`JwtTokenCodec`（`security/jwt.py`）、
  `DefaultSessionSecurity`（`security/session.py`）。

与相邻域分工：`bms_core/password`（策略判定）、`bms_core/session`（会话存储）只做策略 / 存取，
不持有哈希、令牌与会话标识语义；本域原语为纯计算 / 无外部依赖（密钥与配置由装配注入）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "BasePasswordHasher",
    "BaseSecurity",
    "BaseSessionSecurity",
    "BaseTokenCodec",
    "get_password_hasher",
    "get_session_security",
    "get_token_codec",
]


class BaseSecurity(BasePluggable, ABC):
    """安全域中间层基类：统一安全约定（密钥只走环境变量、不落日志、算法白名单）。"""

    key: str = "security"
    plugin_key: str = "security"


class BasePasswordHasher(BaseSecurity, ABC):
    """口令哈希契约：哈希 / 校验 / 参数升级判定（PBKDF2 真实实现见 `security/pbkdf2.py`）。"""

    key: str = "password_hasher"
    plugin_key: str = "password_hasher"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def hash(self, password: str) -> str:
        """生成口令哈希（自描述串，供后续校验与重哈希判定）。

        Args:
            password: 口令明文。

        Returns:
            str: 哈希串。
        """

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """校验口令（常量时间比对；串非法恒 `False`，不抛错防探测）。

        Args:
            password: 口令明文。
            hashed: 存储的哈希串。

        Returns:
            bool: 校验通过为 True。
        """

    @abstractmethod
    def needs_rehash(self, hashed: str) -> bool:
        """哈希串是否需按当前参数重算（参数升级 / 串非法为 True）。

        Args:
            hashed: 存储的哈希串。

        Returns:
            bool: 需重算为 True。
        """


class BaseTokenCodec(BaseSecurity, ABC):
    """令牌编解码契约：通用 JWT 编解码（`aud` / `iss` 等业务声明由调用方传入）。"""

    key: str = "token_codec"
    plugin_key: str = "token_codec"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def encode(self, claims: dict[str, object], *, expires_in: int | None = None) -> str:
        """签发令牌（自动补 `iat`；`expires_in` 非空补 `exp`）。

        Args:
            claims: 声明（`sub` / `aud` / `iss` / `type` 等由调用方给定）。
            expires_in: 有效期（秒；None 不写 `exp`）。

        Returns:
            str: JWT 紧凑串。

        Raises:
            ConfigError: 未配置可用签名私钥（40001）。
        """

    @abstractmethod
    def decode(self, token: str) -> dict[str, object]:
        """校验并解析令牌（签名 / 算法白名单 / `exp`）。

        Args:
            token: JWT 紧凑串。

        Returns:
            dict[str, object]: 声明。

        Raises:
            AuthError: 验签 / 声明校验失败（20001 / 401）。
        """


class BaseSessionSecurity(BaseSecurity, ABC):
    """会话安全契约：会话 id / 会话指纹 / 取消黑名单键。"""

    key: str = "session_security"
    plugin_key: str = "session_security"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def new_session_id(self) -> str:
        """生成会话 id（与 `sys_session.id`、JWT `jti` 同值）。

        Returns:
            str: 会话 id。
        """

    @abstractmethod
    def fingerprint(self, *, ip: str | None, user_agent: str | None) -> str:
        """生成会话指纹（不落原始 ip / user-agent）。

        Args:
            ip: 客户端 IP（可空）。
            user_agent: 客户端 UA（可空）。

        Returns:
            str: 指纹（十六进制）。
        """

    @abstractmethod
    def blacklist_key(self, session_id: str) -> str:
        """会话黑名单 Redis 键（登出 / 强踢；`bms:global:token:blacklist:{jti}`）。

        Args:
            session_id: 会话 id（JWT `jti`）。

        Returns:
            str: Redis 键。
        """


def get_password_hasher(request: Request) -> BasePasswordHasher:
    """取应用级口令哈希实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BasePasswordHasher: 应用装配的哈希实现实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BasePasswordHasher",
        resolve_plugin(
            "password_hasher",
            settings.password_hasher.provider,
            expected_version=BasePasswordHasher.contract_version,
        ),
    )


def get_token_codec(request: Request) -> BaseTokenCodec:
    """取应用级令牌编解码实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTokenCodec: 应用装配的编解码实现实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTokenCodec",
        resolve_plugin(
            "token_codec",
            settings.token_codec.provider,
            expected_version=BaseTokenCodec.contract_version,
        ),
    )


def get_session_security(request: Request) -> BaseSessionSecurity:
    """取应用级会话安全实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseSessionSecurity: 应用装配的会话安全实现实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseSessionSecurity",
        resolve_plugin(
            "session_security",
            settings.session_security.provider,
            expected_version=BaseSessionSecurity.contract_version,
        ),
    )

"""流程状态存储能力域：SSO 流程状态（state）一次性存取契约。

- `DEFAULT_IDP_STATE_TTL`：默认流程状态 TTL（秒，5 分钟，与 `[sso].state_ttl_seconds` 口径一致）。
- `IdpFlowState`：流程状态载荷（租户 / IdP / nonce / PKCE verifier / 回调地址 / 创建时间）。
- `BaseIdpStateStore`：能力域中间层契约（`key = "idp_state_store"`）——异步 `save` / `consume` / `delete`。
- `get_idp_state_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：`consume` 为**一次性原子消费**（Redis `GETDEL`；memory `pop` + 惰性过期），未命中返回 None
（state 缺失 / 已消费 / 过期三态合一，上层统一按回调校验失败处理）；键形 `bms:{租户}:{命名空间}:{state}`；
写入 / 删除失败向上暴露异常，由调用方决定语义。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "DEFAULT_IDP_STATE_TTL",
    "IDP_STATE_DEFAULT_NAMESPACE",
    "IDP_STATE_KEY_PREFIX",
    "BaseIdpStateStore",
    "IdpFlowState",
    "build_idp_state_key",
    "get_idp_state_store",
]

DEFAULT_IDP_STATE_TTL = 300
"""默认流程状态 TTL（秒，5 分钟；与 `[sso].state_ttl_seconds` 默认值一致）。"""

IDP_STATE_KEY_PREFIX = "bms"
"""流程状态键前缀（`bms:{租户}:{命名空间}:{state}`，与缓存 / 会话 / 限流键同前缀）。"""

IDP_STATE_DEFAULT_NAMESPACE = "idpstate"
"""默认命名空间（SSO 授权流程状态）；OIDC Provider 授权码等复用本存储时另立命名空间隔离。"""


def build_idp_state_key(
    state: str, *, tenant_code: str | None = None, namespace: str = IDP_STATE_DEFAULT_NAMESPACE
) -> str:
    """构建流程状态 Redis 键（规范 `bms:{租户}:{命名空间}:{state}`）。

    Args:
        state: 防 CSRF 的流程状态 / 一次性码（高熵随机串）。
        tenant_code: 租户编码；None 表示无租户维度（global 域）。
        namespace: 命名空间（默认 `idpstate`；不同用途用独立命名空间隔离，互不覆盖）。

    Returns:
        str: 流程状态键。
    """
    return f"{IDP_STATE_KEY_PREFIX}:{tenant_code or 'global'}:{namespace}:{state}"


@dataclass(frozen=True)
class IdpFlowState(BaseValueObject):
    """SSO 流程状态载荷（授权跳转写入，回调一次性消费）。"""

    tenant_code: str = ""
    """租户编码（回调时校验请求上下文一致性）。"""

    idp_key: str = ""
    """IdP 标识（回调时校验路由与状态一致）。"""

    nonce: str = ""
    """OIDC nonce（ID Token 校验）。"""

    code_verifier: str = ""
    """PKCE code_verifier（换码时提交；仅存服务端）。"""

    redirect_uri: str = ""
    """授权 / 换码使用的 redirect_uri（与 authorize 时一致）。"""

    created_at: str = ""
    """创建时间（ISO 8601 字符串；审计与超时排查）。"""


class BaseIdpStateStore(BasePluggable, ABC):
    """流程状态存储契约：写入 / 一次性消费 / 删除。"""

    key: str = "idp_state_store"
    plugin_key: str = "idp_state_store"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def save(
        self,
        state: str,
        payload: Mapping[str, object],
        *,
        tenant_code: str | None = None,
        ttl: int = DEFAULT_IDP_STATE_TTL,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """写入流程状态（同 state 覆盖；真实实现 `SET ... EX ttl`）。

        Args:
            state: 流程状态（state）。
            payload: 状态数据（`IdpFlowState` 字段）。
            tenant_code: 租户编码（定位 `bms:{租户}:{命名空间}:{state}` 键；None 为 global 域）。
            ttl: 有效期（秒，默认 `DEFAULT_IDP_STATE_TTL`）。
            namespace: 命名空间（默认 `idpstate`；不同用途独立隔离）。
        """

    @abstractmethod
    async def consume(
        self,
        state: str,
        *,
        tenant_code: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> Mapping[str, object] | None:
        """一次性原子消费流程状态（取出即删除；未命中返回 None）。

        Args:
            state: 流程状态（state）。
            tenant_code: 租户编码（定位键；None 为 global 域）。
            namespace: 命名空间（默认 `idpstate`）。

        Returns:
            Mapping[str, object] | None: 状态数据；缺失 / 已消费 / 过期返回 None。
        """

    @abstractmethod
    async def delete(
        self,
        state: str,
        *,
        tenant_code: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """删除流程状态（幂等，不存在不报错）。

        Args:
            state: 流程状态（state）。
            tenant_code: 租户编码（定位键；None 为 global 域）。
            namespace: 命名空间（默认 `idpstate`）。
        """


def get_idp_state_store(request: Request) -> BaseIdpStateStore:
    """取应用级流程状态存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseIdpStateStore: 应用装配的流程状态存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseIdpStateStore",
        resolve_plugin(
            "idp_state_store",
            settings.idp_state_store.provider,
            expected_version=BaseIdpStateStore.contract_version,
        ),
    )

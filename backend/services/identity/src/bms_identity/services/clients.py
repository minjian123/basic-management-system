"""认证与身份服务 services 层：客户端注册与管理（`sys_client` 最小接口）。

- create：字段校验（含 **scope 登记集合校验**，见 `bms_core/oauth/scopes.py`）→ 服务端生成
  `client_id`（`bms_` 前缀）与 `client_secret`（公共客户端不生成）→ `password_hasher.hash` 落库 →
  返回明文一次。
- reset_secret：重生成密钥并更新哈希（旧值即时失效），新明文仅本次返回。
- set_status：启停（写操作审计占位）。
- list / get：只读（永不返回 secret 与哈希）。
"""

from __future__ import annotations

import json
import secrets

from bms_core.audit.base import AuditCapturer
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ClientInvalidError, ClientNotFoundError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.oauth.base import GRANT_TYPES
from bms_core.oauth.oidc_provider import OIDC_GRANT_AUTHORIZATION_CODE, OIDC_SCOPE_OPENID
from bms_core.oauth.scopes import validate_scopes
from bms_core.schemas.pagination import BasePageQuery
from bms_core.security.base import BasePasswordHasher
from bms_identity.models.client import SysClient
from bms_identity.repositories.client import SysClientRepository

__all__ = ["ClientSecret", "ClientService"]

_CLIENT_ID_PREFIX = "bms_"
_ALLOWED_STATUS = ("enabled", "disabled")
_REDIRECT_SCHEMES = ("http://", "https://")


class ClientSecret(BaseFrameworkObject):
    """客户端凭据（明文仅在创建 / 重置响应返回一次）。"""

    def __init__(self, *, client: SysClient, secret: str) -> None:
        """初始化。

        Args:
            client: 客户端行。
            secret: 明文密钥（公共客户端为空串）。
        """
        self.client = client
        self.secret = secret


class ClientService(BaseFrameworkObject):
    """客户端注册与管理服务（每请求装配：会话 / 工作单元 / 哈希器 / 审计占位）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        password_hasher: BasePasswordHasher,
        audit: AuditCapturer,
    ) -> None:
        """初始化。

        Args:
            session: identity 服务租户库会话。
            uow: 工作单元（写事务边界）。
            password_hasher: 口令哈希实现（密钥哈希 / 校验）。
            audit: 审计捕获占位（真实落库随审计阶段）。
        """
        self._repo = SysClientRepository(session)
        self._uow = uow
        self._hasher = password_hasher
        self._audit = audit

    async def create(
        self,
        *,
        name: str,
        redirect_uris: ConcurrentStableList[str],
        grant_types: ConcurrentStableList[str],
        scopes: ConcurrentStableList[str],
        ip_whitelist: ConcurrentStableList[str],
        public: bool,
    ) -> ClientSecret:
        """注册客户端（`client_secret` 仅本次明文返回）。

        Args:
            name: 应用名称。
            redirect_uris: 回调地址白名单。
            grant_types: 授权类型。
            scopes: scope 集合。
            ip_whitelist: IP / CIDR 白名单。
            public: 是否公共客户端（不生成密钥）。

        Returns:
            ClientSecret: 客户端行 + 明文密钥。

        Raises:
            ClientInvalidError: 字段非法（80112/400）。
        """
        grants, redirects, allowed_scopes, ips = _validate(
            grant_types=grant_types,
            redirect_uris=redirect_uris,
            scopes=scopes,
            ip_whitelist=ip_whitelist,
        )
        client_id = _new_client_id()
        secret = "" if public else secrets.token_urlsafe(32)
        async with self._uow.begin():
            client = await self._repo.create(
                client_id=client_id,
                client_secret_hash=None if public else self._hasher.hash(secret),
                name=name,
                redirect_uris=json.dumps(list(redirects), ensure_ascii=False),
                grant_types=json.dumps(list(grants), ensure_ascii=False),
                scopes=json.dumps(list(allowed_scopes), ensure_ascii=False),
                ip_whitelist=json.dumps(list(ips), ensure_ascii=False),
                status="enabled",
            )
        self._record(client, "created")
        return ClientSecret(client=client, secret=secret)

    async def list(
        self,
        query: BasePageQuery,
        *,
        status: str | None = None,
        name: str | None = None,
    ) -> tuple[ConcurrentStableList[SysClient], int]:
        """客户端分页查询。

        Args:
            query: 页码分页请求。
            status: 状态过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            tuple[ConcurrentStableList[SysClient], int]: 当前页客户端与总数。
        """
        items = await self._repo.list_filtered(query, status=status, name=name)
        total = await self._repo.count_filtered(status=status, name=name)
        return items, total

    async def get(self, client_id: int) -> SysClient:
        """按主键取客户端。

        Args:
            client_id: 客户端主键。

        Returns:
            SysClient: 客户端行。

        Raises:
            ClientNotFoundError: 不存在（80111/404）。
        """
        row = await self._repo.get(client_id)
        if row is None:
            raise ClientNotFoundError("客户端不存在")
        return row

    async def set_status(self, client_id: int, status: str) -> SysClient:
        """启停客户端。

        Args:
            client_id: 客户端主键。
            status: 目标状态（enabled/disabled）。

        Returns:
            SysClient: 更新后的客户端行。

        Raises:
            ClientInvalidError: 状态取值非法（80112/400）。
            ClientNotFoundError: 不存在（80111/404）。
        """
        if status not in _ALLOWED_STATUS:
            raise ClientInvalidError("状态取值非法")
        async with self._uow.begin():
            row = await self._repo.update(client_id, status=status)
        if row is None:
            raise ClientNotFoundError("客户端不存在")
        self._record(row, "status_changed")
        return row

    async def reset_secret(self, client_id: int) -> ClientSecret:
        """重置客户端密钥（新明文仅本次返回；公共客户端重建为机密需显式创建）。

        Args:
            client_id: 客户端主键。

        Returns:
            ClientSecret: 客户端行 + 新明文密钥。

        Raises:
            ClientNotFoundError: 不存在（80111/404）。
            ClientInvalidError: 公共客户端无密钥可重置（80112/400）。
        """
        secret = secrets.token_urlsafe(32)
        async with self._uow.begin():
            row = await self._repo.get(client_id)
            if row is None:
                raise ClientNotFoundError("客户端不存在")
            if not row.client_secret_hash:
                raise ClientInvalidError("公共客户端无密钥可重置")
            updated = await self._repo.update(client_id, client_secret_hash=self._hasher.hash(secret))
        if updated is None:  # pragma: no cover - 事务内已确认存在
            raise ClientNotFoundError("客户端不存在")
        self._record(updated, "secret_reset")
        return ClientSecret(client=updated, secret=secret)

    def _record(self, client: SysClient, action: str) -> None:
        """写操作审计占位（`AuditCapturer` 占位实现为空操作；真实落库随审计阶段）。

        Args:
            client: 客户端行。
            action: 动作标识（created / status_changed / secret_reset）。
        """
        self._audit.capture(table="sys_client", model_id=client.id, changes=ConcurrentStableList(), actor=None)


def _new_client_id() -> str:
    """生成客户端标识（`bms_` + 随机串）。

    Returns:
        str: 客户端标识。
    """
    return f"{_CLIENT_ID_PREFIX}{secrets.token_urlsafe(24)}"


def _validate(
    *,
    grant_types: ConcurrentStableList[str],
    redirect_uris: ConcurrentStableList[str],
    scopes: ConcurrentStableList[str],
    ip_whitelist: ConcurrentStableList[str],
) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str], ConcurrentStableList[str]]:
    """校验并归一化客户端字段。

    Args:
        grant_types: 授权类型。
        redirect_uris: 回调地址白名单。
        scopes: scope 集合。
        ip_whitelist: IP / CIDR 白名单。

    Returns:
        tuple: (授权类型, 回调地址, scope, IP 白名单) 归一化结果。

    Raises:
        ClientInvalidError: 任一字段非法（80112/400），含 scope 不在开放接口登记集合。
    """
    grants = _dedupe(grant_types)
    if not grants or any(item not in GRANT_TYPES for item in grants):
        raise ClientInvalidError("授权类型非法")
    redirects = _dedupe(redirect_uris)
    if OIDC_GRANT_AUTHORIZATION_CODE in grants:
        if not redirects:
            raise ClientInvalidError("授权码客户端须登记回调地址")
        if any(not item.startswith(_REDIRECT_SCHEMES) for item in redirects):
            raise ClientInvalidError("回调地址须为 http / https")
    allowed_scopes = _dedupe(scopes)
    if not allowed_scopes or any(not item for item in allowed_scopes):
        raise ClientInvalidError("scope 集合非法")
    if OIDC_GRANT_AUTHORIZATION_CODE in grants and OIDC_SCOPE_OPENID not in allowed_scopes:
        raise ClientInvalidError("授权码客户端 scope 须含 openid")
    unknown_scopes = validate_scopes(allowed_scopes)
    if unknown_scopes:
        raise ClientInvalidError("scope 未登记：" + "、".join(unknown_scopes))
    ips = _dedupe(ip_whitelist)
    return grants, redirects, allowed_scopes, ips


def _dedupe(values: ConcurrentStableList[str]) -> ConcurrentStableList[str]:
    """去重并去空白（保持首次出现顺序）。

    Args:
        values: 原始值序列。

    Returns:
        ConcurrentStableList[str]: 去重结果。
    """
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    for value in values:
        item = (value or "").strip()
        if item and item not in seen:
            seen.add(item)
    return seen

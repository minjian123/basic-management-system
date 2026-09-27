"""认证与身份服务 services 层：JIT 自动建号与身份映射写路径（需求 02-2）。

- **开关**：IdP 行 `config.jit_enabled` 优先，行缺配回落全局 `[sso].jit_enabled`（皆缺省 false）。
- **白名单**：域名经行 `config.allowed_email_domains`（非空即要求邮箱域名命中）；租户经全局
  `[sso].jit_allowed_tenants`（非空即要求租户命中）；空 = 不限制。
- **并发**：`distributed_lock` 按映射键（`{tenant}:{provider_key}:{subject}`）串行化；锁内二次查映射命中即复用；
  映射 `(idp_key, external_id)` 唯一约束作跨进程兜底（冲突回读复用）。
- **建号**：用户名来源 `preferred_username → email 本地部分 → sub` 并清洗；撞名加后缀 `_2.._5`（超出拒绝）；
  经 org 内部接口建号（占位口令，不可本地登录）。
- **事件**：首次建号在平台库与映射插入**同事务**写 `identity.user.jit_created`（Outbox，仅首登发）。
- 错误语义：未启用 / 白名单拒绝 / 用尽后缀 → `20054`；锁或映射冲突 → `20055`；org 建号不可达 → `20053`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast

from sqlalchemy.exc import IntegrityError

from bms_core.core.base import BaseObject
from bms_core.core.config import SsoSettings
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ConfigError,
    ServiceUnavailableError,
    SsoIdentityConflictError,
    SsoIdentityUnmatchedError,
    SsoProviderUnavailableError,
)
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.lock.base import BaseDistributedLock, build_lock_key
from bms_core.outbox.base import BaseOutboxStore
from bms_identity.repositories.user_identity import UserIdentityRepository
from bms_identity.schemas.sso import OrgProfileUser
from bms_identity.services.org_client import OrgCredentialClient

__all__ = [
    "ExternalIdentity",
    "JitResult",
    "JitService",
    "derive_username",
    "jit_enabled_for",
]

JIT_EVENT_TYPE = "identity.user.jit_created"
"""JIT 首登建号事件类型（契约见事件模型清单 / `platform_events.py`）。"""

USERNAME_MAX_ATTEMPTS = 5
"""用户名撞名后缀尝试上限（`base` / `base_2` … `base_5`）。"""

USERNAME_MAX_LENGTH = 64
"""用户名最大长度（与 `sys_user.username` 列宽一致）。"""

_USERNAME_SANITIZE_RE = re.compile(r"[^a-z0-9._-]")
_USERNAME_FALLBACK = "user"
_LOGGER = get_logger("bms")


@dataclass(frozen=True)
class ExternalIdentity(BaseObject):
    """外部身份声明（ID Token / userinfo 归一化结果；JIT 建号与映射的输入）。"""

    subject: str
    """外部主体标识（OIDC 取 `sub`）。"""

    username: str = ""
    """外部用户名（`preferred_username` / userinfo `username`；可空）。"""

    name: str = ""
    """显示名（`name` claim；可空）。"""

    email: str | None = None
    """邮箱（`email` claim；可空）。"""

    locale: str | None = None
    """语言偏好（`locale` claim；可空）。"""

    timezone: str | None = None
    """时区偏好（`zoneinfo` claim；可空）。"""


@dataclass(frozen=True)
class JitResult(BaseObject):
    """JIT 建号结果（`created` 表示本次是否新建）。"""

    user_id: int
    """本地用户主键。"""

    created: bool
    """是否本次新建（False = 并发命中既有映射复用）。"""


class JitService(BaseObject):
    """JIT 建号编排：开关 / 白名单 / 锁 / 建号 / 映射与事件。"""

    def __init__(
        self,
        *,
        lock: BaseDistributedLock,
        org_client: OrgCredentialClient,
        outbox_store: BaseOutboxStore,
        sso_settings: SsoSettings,
    ) -> None:
        """初始化。

        Args:
            lock: 分布式锁（JIT 临界区串行化）。
            org_client: org 内部接口客户端（建号）。
            outbox_store: 事务性发件箱（首登建号事件）。
            sso_settings: SSO 配置（全局开关 / 白名单 / 锁参数）。
        """
        self._lock = lock
        self._org = org_client
        self._outbox = outbox_store
        self._sso = sso_settings

    def enabled(self, config: str) -> bool:
        """JIT 是否启用（行配置优先，缺配回落全局）。

        Args:
            config: IdP 行配置 JSON 原文（行会话已释放，传值不解引用 ORM）。

        Returns:
            bool: 是否启用 JIT。
        """
        return jit_enabled_for(config, self._sso)

    async def provision(
        self,
        *,
        tenant: str,
        idp_key: str,
        config: str,
        identity: ExternalIdentity,
        platform_session: DbSession,
    ) -> JitResult:
        """首登建号 + 映射写入（锁内二次查；唯一约束兜底）。

        Args:
            tenant: 生效租户编码。
            idp_key: 租户内 IdP 标识（协议行 `idp_key`）。
            config: IdP 行配置 JSON 原文（开关 / 白名单来源）。
            identity: 外部身份声明。
            platform_session: 平台库可写会话（映射 + 事件同事务）。

        Returns:
            JitResult: 本地用户主键与是否新建。

        Raises:
            SsoIdentityUnmatchedError: JIT 未启用 / 白名单拒绝 / 用尽用户名后缀（20054/403）。
            SsoIdentityConflictError: 锁未取到或映射冲突回读未命中（20055/409）。
            SsoProviderUnavailableError: org 建号接口不可达（20053/503）。
        """
        if not self.enabled(config):
            raise SsoIdentityUnmatchedError()
        self._enforce_whitelist(tenant, config, idp_key, identity)

        lock_key = build_lock_key(tenant=tenant, resource=f"jit:{idp_key}:{identity.subject}")
        try:
            async with self._lock.hold(
                lock_key,
                ttl=self._sso.jit_lock_ttl_seconds,
                wait=self._sso.jit_lock_wait_seconds,
            ):
                return await self._provision_locked(
                    tenant=tenant,
                    idp_key=idp_key,
                    identity=identity,
                    platform_session=platform_session,
                )
        except ConcurrentConflictError as exc:
            _LOGGER.warning("JIT 并发冲突（未取到锁）", tenant=tenant, idp_key=idp_key)
            raise SsoIdentityConflictError() from exc

    async def _provision_locked(
        self,
        *,
        tenant: str,
        idp_key: str,
        identity: ExternalIdentity,
        platform_session: DbSession,
    ) -> JitResult:
        """锁内建号：二次查映射 → org 建号 → 映射 + 事件同事务。

        Args:
            tenant: 租户编码。
            idp_key: IdP 标识。
            identity: 外部身份声明。
            platform_session: 平台库可写会话。

        Returns:
            JitResult: 本地用户主键与是否新建。

        Raises:
            SsoIdentityUnmatchedError: 用尽用户名后缀（20054/403）。
            SsoIdentityConflictError: 映射冲突回读未命中（20055/409）。
            SsoProviderUnavailableError: org 建号接口不可达（20053/503）。
        """
        mapping_key = f"{tenant}:{idp_key}"
        repo = UserIdentityRepository(platform_session)
        existing = await repo.get_by_key_external(mapping_key, identity.subject)
        if existing is not None:
            return JitResult(user_id=existing.user_id, created=False)

        user = await self._create_org_user(tenant, identity)
        try:
            await repo.create(
                idp_key=mapping_key,
                external_id=identity.subject,
                tenant_id=tenant,
                user_id=user.id,
            )
            await self._outbox.enqueue(
                platform_session,
                EventEnvelope(
                    event_type=JIT_EVENT_TYPE,
                    payload={"user_id": str(user.id), "idp_key": mapping_key},
                    tenant_id=tenant,
                    aggregate_key=mapping_key,
                ),
            )
            await platform_session.commit()
        except IntegrityError:
            await platform_session.rollback()
            existing = await repo.get_by_key_external(mapping_key, identity.subject)
            if existing is None:
                raise SsoIdentityConflictError() from None
            _LOGGER.warning("JIT 映射并发冲突，复用既有映射", tenant=tenant, idp_key=idp_key)
            return JitResult(user_id=existing.user_id, created=False)
        _LOGGER.info("JIT 建号成功", tenant=tenant, idp_key=idp_key, user_id=user.id)
        return JitResult(user_id=user.id, created=True)

    async def _create_org_user(self, tenant: str, identity: ExternalIdentity) -> OrgProfileUser:
        """经 org 建号（用户名撞名换后缀，最多 `USERNAME_MAX_ATTEMPTS` 次）。

        Args:
            tenant: 租户编码。
            identity: 外部身份声明。

        Returns:
            OrgProfileUser: 新建用户概要。

        Raises:
            SsoIdentityUnmatchedError: 用尽后缀仍撞名（20054/403）。
            SsoProviderUnavailableError: org 建号接口不可达（20053/503）。
        """
        base = derive_username(identity)
        name = identity.name or identity.username or base
        for attempt in range(USERNAME_MAX_ATTEMPTS):
            candidate = base if attempt == 0 else f"{base}_{attempt + 1}"
            try:
                result = await self._org.create_user(
                    tenant,
                    username=candidate,
                    name=name,
                    locale=identity.locale,
                    timezone=identity.timezone,
                )
            except ServiceUnavailableError as exc:
                _LOGGER.warning("JIT 建号接口不可用", tenant=tenant, error=str(exc))
                raise SsoProviderUnavailableError("org 建号接口不可用") from exc
            if result.created and result.user is not None:
                return result.user
        _LOGGER.warning("JIT 用尽用户名后缀", tenant=tenant, base=base)
        raise SsoIdentityUnmatchedError()

    def _enforce_whitelist(self, tenant: str, config: str, provider_key: str, identity: ExternalIdentity) -> None:
        """白名单校验：租户全局 + 域名行配置（空 = 不限制）。

        Args:
            tenant: 租户编码。
            config: IdP 行配置 JSON 原文（域名白名单来源）。
            provider_key: 租户内 IdP 标识（日志）。
            identity: 外部身份声明。

        Raises:
            SsoIdentityUnmatchedError: 白名单外（20054/403）。
        """
        allowed_tenants = self._sso.jit_allowed_tenants
        if allowed_tenants and tenant not in allowed_tenants:
            _LOGGER.warning("JIT 租户不在白名单", tenant=tenant)
            raise SsoIdentityUnmatchedError()
        domains = allowed_email_domains(config, provider_key)
        if not domains:
            return
        email = (identity.email or "").strip().lower()
        if "@" not in email or email.rsplit("@", 1)[1] not in domains:
            _LOGGER.warning("JIT 域名不在白名单", tenant=tenant, idp_key=provider_key)
            raise SsoIdentityUnmatchedError()


def jit_enabled_for(config: str, settings: SsoSettings) -> bool:
    """解析 JIT 开关：行 `config.jit_enabled` 优先，缺配回落全局。

    Args:
        config: IdP 行配置 JSON 原文。
        settings: SSO 配置。

    Returns:
        bool: 是否启用 JIT。
    """
    value = _row_config(config, "provider").get("jit_enabled")
    if isinstance(value, bool):
        return value
    return settings.jit_enabled


def allowed_email_domains(config: str, provider_key: str) -> frozenset[str]:
    """取行配置的邮箱域名白名单（小写去重；未配置返回空集）。

    Args:
        config: IdP 行配置 JSON 原文。
        provider_key: 租户内 IdP 标识（错误提示用）。

    Returns:
        frozenset[str]: 域名集合（空 = 不限制）。

    Raises:
        ConfigError: 配置项类型非法（40001）。
    """
    raw = _row_config(config, provider_key).get("allowed_email_domains")
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise ConfigError(f"身份源行配置 allowed_email_domains 必须是数组：{provider_key}")
    domains: list[str] = []
    for item in cast("list[object]", raw):
        text = str(item).strip().lower()
        if text:
            domains.append(text)
    return frozenset(domains)


def derive_username(identity: ExternalIdentity) -> str:
    """派生并清洗本地用户名（`preferred_username → email 本地部分 → sub → user`）。

    Args:
        identity: 外部身份声明。

    Returns:
        str: 清洗后的用户名（非空）。
    """
    for source in (identity.username, _email_local(identity.email), identity.subject):
        cleaned = clean_username(source)
        if cleaned:
            return cleaned
    return _USERNAME_FALLBACK


def clean_username(raw: str | None) -> str:
    """清洗用户名：小写、仅保留 `[a-z0-9._-]`、去首尾分隔符、截断 64。

    Args:
        raw: 原始用户名。

    Returns:
        str: 清洗后用户名（可能为空）。
    """
    if not raw:
        return ""
    text = _USERNAME_SANITIZE_RE.sub("", raw.strip().lower())
    return text.strip("._-")[:USERNAME_MAX_LENGTH]


def _email_local(email: str | None) -> str:
    """取邮箱本地部分。

    Args:
        email: 邮箱地址（可空）。

    Returns:
        str: `@` 前部分；无邮箱返回空串。
    """
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[0]


def _row_config(config: str, provider_key: str) -> dict[str, object]:
    """解析 IdP 行配置 JSON（必须是对象）。

    Args:
        config: IdP 行配置 JSON 原文。
        provider_key: 租户内 IdP 标识（错误提示用）。

    Returns:
        dict[str, object]: 配置对象。

    Raises:
        ConfigError: 非法 JSON / 非对象（40001）。
    """
    try:
        parsed = json.loads(config or "{}")
    except ValueError as exc:
        raise ConfigError(f"身份源行配置非法 JSON：{provider_key}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"身份源行配置必须是 JSON 对象：{provider_key}")
    return cast("dict[str, object]", parsed)

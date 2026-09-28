"""认证与身份服务 services 层：外部 IdP 配置管理（CRUD / 启停 / 连通性测试）。

- 写入校验：`validate_provider_config`（必填 / 类型 / 枚举 / 未知键 / 密钥引用 / SSRF）→ `20064`。
- 凭据零明文：响应经 `mask_provider_config` 脱敏（密钥引用只返 `env:***`）。
- 启停：`status` 仅 `enabled` / `disabled`（非法 `20064`）。
- 连通性测试：`probe()` 分协议探测；不可达 / 不可探测统一 `IdpTestFailedError`（`20066`，`data` 携结果）；
  测试限流按「租户 + 操作者」（`[idp_manage].test_rate_limit`）。
- 写操作落 `AuditCapturer` 占位；测试为只读、不落审计。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from sqlalchemy.exc import IntegrityError

from bms_core.audit.base import AuditCapturer
from bms_core.core.config import IdpManageSettings
from bms_core.core.exceptions import (
    ConfigError,
    IdpConfigInvalidError,
    IdpKeyConflictError,
    IdpNotFoundError,
    IdpTestFailedError,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idp.base import IdpProbeResult
from bms_core.idp.registry import IdentityProviderSpec
from bms_core.idp.schema import has_secret, mask_provider_config, validate_provider_config
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.schemas.pagination import BasePageQuery
from bms_identity.models.identity_provider import SysIdentityProvider
from bms_identity.repositories.identity_provider import IdentityProviderRepository
from bms_identity.schemas.identity_provider import IdpProviderItem
from bms_identity.services.provider_registry import ProviderRegistry

__all__ = ["IdentityProviderService"]

_ALLOWED_STATUS = ("enabled", "disabled")
_TEST_DIMENSION = "idp_test"
_TABLE = "sys_identity_provider"


class IdentityProviderService(BaseFrameworkObject):
    """外部 IdP 配置管理服务（每请求装配：会话 / 工作单元 / 审计 / 限流 / 实例桥接）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        audit: AuditCapturer,
        rate_limiter: BaseRateLimiter,
        provider_registry: ProviderRegistry,
        idp_manage: IdpManageSettings,
    ) -> None:
        """初始化。

        Args:
            session: identity 服务租户库会话。
            uow: 工作单元（写事务边界）。
            audit: 审计捕获占位（真实落库随审计阶段）。
            rate_limiter: 限流基座（连通性测试防滥用）。
            provider_registry: IdP 行实例化桥接（连通性测试）。
            idp_manage: 管理面配置（测试限流阈值 / 内网放行开关）。
        """
        self._repo = IdentityProviderRepository(session)
        self._uow = uow
        self._audit = audit
        self._limiter = rate_limiter
        self._registry = provider_registry
        self._manage = idp_manage

    async def list(
        self,
        query: BasePageQuery,
        *,
        status: str | None = None,
        type: str | None = None,
        name: str | None = None,
    ) -> tuple[list[SysIdentityProvider], int]:
        """管理面分页查询。

        Args:
            query: 页码分页请求。
            status: 状态过滤（可选）。
            type: 协议类型过滤（可选）。
            name: 名称模糊过滤（可选）。

        Returns:
            tuple[list[SysIdentityProvider], int]: 当前页 IdP 行与总数。
        """
        items = await self._repo.list_filtered(query, status=status, type=type, name=name)
        total = await self._repo.count_filtered(status=status, type=type, name=name)
        return items, total

    async def get(self, provider_id: int) -> SysIdentityProvider:
        """按主键取 IdP 配置。

        Args:
            provider_id: 主键。

        Returns:
            SysIdentityProvider: IdP 行。

        Raises:
            IdpNotFoundError: 不存在（20063/404）。
        """
        row = await self._repo.get(provider_id)
        if row is None:
            raise IdpNotFoundError("IdP 配置不存在")
        return row

    async def create(
        self,
        *,
        name: str,
        idp_key: str,
        type: str,
        icon: str,
        config: Mapping[str, object],
        status: str,
        sort: int,
        actor: int | None,
    ) -> SysIdentityProvider:
        """新建 IdP 配置。

        Args:
            name: 显示名。
            idp_key: 租户内标识。
            type: 协议类型。
            icon: 图标。
            config: 协议配置对象。
            status: 状态（enabled/disabled）。
            sort: 排序值。
            actor: 操作者用户 ID（可选）。

        Returns:
            SysIdentityProvider: 新建行。

        Raises:
            IdpConfigInvalidError: 配置 / 状态非法（20064/400）。
            IdpKeyConflictError: 标识重复（20065/409）。
        """
        _ensure_status(status)
        normalized = self._validate(type, config)
        try:
            async with self._uow.begin():
                if await self._repo.get_by_key(idp_key) is not None:
                    raise IdpKeyConflictError("IdP 标识已存在")
                row = await self._repo.create(
                    name=name,
                    idp_key=idp_key,
                    type=type,
                    icon=icon,
                    config=json.dumps(normalized, ensure_ascii=False),
                    status=status,
                    sort=sort,
                )
        except IntegrityError:  # pragma: no cover - 并发兜底（预检 + 唯一约束双重防护）
            raise IdpKeyConflictError("IdP 标识已存在") from None
        self._record(row, actor)
        return row

    async def update(
        self,
        provider_id: int,
        *,
        name: str | None,
        icon: str | None,
        config: Mapping[str, object] | None,
        sort: int | None,
        actor: int | None,
    ) -> SysIdentityProvider:
        """修改 IdP 配置（局部更新；`type` / `idp_key` 不可改）。

        Args:
            provider_id: 主键。
            name: 显示名（可选）。
            icon: 图标（可选）。
            config: 协议配置对象（可选，全量替换）。
            sort: 排序值（可选）。
            actor: 操作者用户 ID（可选）。

        Returns:
            SysIdentityProvider: 更新后的行。

        Raises:
            IdpConfigInvalidError: 配置非法（20064/400）。
            IdpNotFoundError: 不存在（20063/404）。
        """
        async with self._uow.begin():
            row = await self._repo.get(provider_id)
            if row is None:
                raise IdpNotFoundError("IdP 配置不存在")
            values: dict[str, object] = {}
            if name is not None:
                values["name"] = name
            if icon is not None:
                values["icon"] = icon
            if sort is not None:
                values["sort"] = sort
            if config is not None:
                values["config"] = json.dumps(self._validate(row.type, config), ensure_ascii=False)
            updated = await self._repo.update(provider_id, **values)
        if updated is None:  # pragma: no cover - 事务内已确认存在
            raise IdpNotFoundError("IdP 配置不存在")
        self._record(updated, actor)
        return updated

    async def set_status(self, provider_id: int, status: str, *, actor: int | None) -> SysIdentityProvider:
        """启停 IdP 配置。

        Args:
            provider_id: 主键。
            status: 目标状态（enabled/disabled）。
            actor: 操作者用户 ID（可选）。

        Returns:
            SysIdentityProvider: 更新后的行。

        Raises:
            IdpConfigInvalidError: 状态非法（20064/400）。
            IdpNotFoundError: 不存在（20063/404）。
        """
        _ensure_status(status)
        async with self._uow.begin():
            row = await self._repo.update(provider_id, status=status)
            if row is None:
                raise IdpNotFoundError("IdP 配置不存在")
        self._record(row, actor)
        return row

    async def delete(self, provider_id: int, *, actor: int | None) -> None:
        """软删除 IdP 配置（标识软删后可复用）。

        Args:
            provider_id: 主键。
            actor: 操作者用户 ID（可选）。

        Raises:
            IdpNotFoundError: 不存在（20063/404）。
        """
        async with self._uow.begin():
            deleted = await self._repo.soft_delete(provider_id)
        if not deleted:
            raise IdpNotFoundError("IdP 配置不存在")
        self._record_id(provider_id, actor)

    async def test_draft(
        self,
        *,
        type: str,
        config: Mapping[str, object],
        idp_key: str,
        tenant: str,
        actor: int | None,
    ) -> IdpProbeResult:
        """草稿连通性测试（不落库）。

        Args:
            type: 协议类型。
            config: 协议配置对象。
            idp_key: 租户内标识（派生回调地址用）。
            tenant: 生效租户编码（限流维度）。
            actor: 操作者用户 ID（限流维度；可选）。

        Returns:
            IdpProbeResult: 探测结果（可达）。

        Raises:
            IdpConfigInvalidError: 配置非法（20064/400）。
            IdpTestFailedError: 不可达 / 不可探测（20066/502）。
            RateLimitError: 限流命中（10005/429）。
        """
        normalized = self._validate(type, config)
        await self._enforce_test_rate_limit(tenant, actor)
        spec = self._registry.spec_for_config(idp_key=idp_key, type=type, config=normalized)
        return await self._probe(spec)

    async def test_saved(self, provider_id: int, *, tenant: str, actor: int | None) -> IdpProbeResult:
        """已保存行连通性测试。

        Args:
            provider_id: 主键。
            tenant: 生效租户编码（限流维度）。
            actor: 操作者用户 ID（限流维度；可选）。

        Returns:
            IdpProbeResult: 探测结果（可达）。

        Raises:
            IdpConfigInvalidError: 存量配置非法 / SSRF 拒绝（20064/400）。
            IdpNotFoundError: 不存在（20063/404）。
            IdpTestFailedError: 不可达 / 不可探测（20066/502）。
            RateLimitError: 限流命中（10005/429）。
        """
        row = await self.get(provider_id)
        self._validate(row.type, _row_config(row))
        await self._enforce_test_rate_limit(tenant, actor)
        return await self._probe(self._registry.spec_for(row))

    def item(self, row: SysIdentityProvider) -> IdpProviderItem:
        """IdP 行 → 响应项（`config` 脱敏；密钥引用不返明文）。

        Args:
            row: IdP 行。

        Returns:
            IdpProviderItem: 响应项。

        读取侧对存量脏配置（非法 JSON）容错为空对象（不阻断列表 / 详情）。
        """
        try:
            config = _row_config(row)
        except IdpConfigInvalidError:
            config = {}
        return IdpProviderItem(
            id=row.id,
            name=row.name,
            idp_key=row.idp_key,
            type=row.type,
            icon=row.icon or "",
            config=mask_provider_config(row.type, config),
            secret_configured=has_secret(row.type, config),
            status=row.status,
            sort=row.sort,
        )

    def _validate(self, type: str, config: Mapping[str, object]) -> dict[str, object]:
        """按协议校验配置（未知键拒绝 + SSRF）。

        Args:
            type: 协议类型。
            config: 协议配置对象。

        Returns:
            dict[str, object]: 归一化配置。

        Raises:
            IdpConfigInvalidError: 配置非法（20064/400）。
        """
        return validate_provider_config(type, config, allow_private_hosts=self._manage.allow_private_hosts)

    async def _probe(self, spec: IdentityProviderSpec) -> IdpProbeResult:
        """构造实例并探测（构造失败转 `20066`）。

        Args:
            spec: 实例规格。

        Returns:
            IdpProbeResult: 探测结果（可达）。

        Raises:
            IdpTestFailedError: 实例化失败 / 不可达 / 不可探测（20066/502）。
        """
        try:
            instance = self._registry.instance_for_spec(spec)
        except ConfigError as exc:
            raise IdpTestFailedError(
                "IdP 配置无法实例化",
                data=IdpProbeResult(reachable=False, protocol=spec.type, detail=str(exc)),
            ) from exc
        result = await instance.probe()
        if not result.reachable:
            raise IdpTestFailedError(result.detail or "IdP 连通性测试失败", data=result)
        return result

    async def _enforce_test_rate_limit(self, tenant: str, actor: int | None) -> None:
        """连通性测试限流（每租户 + 操作者每分钟上限）。

        Args:
            tenant: 租户编码。
            actor: 操作者用户 ID（可选）。
        """
        target = f"{tenant}:{actor if actor is not None else 'anonymous'}"
        await self._limiter.require(
            build_rate_limit_key(dimension=_TEST_DIMENSION, target=target, tenant=tenant),
            RateLimitRule(limit=self._manage.test_rate_limit),
        )

    def _record(self, row: SysIdentityProvider, actor: int | None) -> None:
        """写操作审计占位。

        Args:
            row: IdP 行。
            actor: 操作者用户 ID（可选）。
        """
        self._audit.capture(table=_TABLE, model_id=row.id, changes=[], actor=actor)

    def _record_id(self, provider_id: int, actor: int | None) -> None:
        """软删除审计占位（行已删除，只记主键）。

        Args:
            provider_id: 主键。
            actor: 操作者用户 ID（可选）。
        """
        self._audit.capture(table=_TABLE, model_id=provider_id, changes=[], actor=actor)


def _ensure_status(status: str) -> None:
    """校验状态取值。

    Args:
        status: 目标状态。

    Raises:
        IdpConfigInvalidError: 取值非法（20064/400）。
    """
    if status not in _ALLOWED_STATUS:
        raise IdpConfigInvalidError("状态取值非法（应为 enabled / disabled）")


def _row_config(row: SysIdentityProvider) -> dict[str, object]:
    """解析行配置 JSON（非法转 `20064`）。

    Args:
        row: IdP 行。

    Returns:
        dict[str, object]: 配置对象。

    Raises:
        IdpConfigInvalidError: 非法 JSON / 非对象（20064/400）。
    """
    try:
        parsed: object = json.loads(row.config or "{}")
    except ValueError as exc:
        raise IdpConfigInvalidError("IdP 配置非法 JSON") from exc
    if not isinstance(parsed, dict):
        raise IdpConfigInvalidError("IdP 配置必须是 JSON 对象")
    return cast("dict[str, object]", parsed)

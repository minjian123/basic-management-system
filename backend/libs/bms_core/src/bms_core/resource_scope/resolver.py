"""作用域解析与校验能力域（07D `01_02`）：三路径一套解析、四步固定校验。

- **唯一实现**：管理面（HTTP 依赖 `require_scope`）、数据面帧入口（`require`）、异步路径
  （`per_round` / `batch` / `require_sync`）全部委托 `resolve()`，不写第二套解析。
- **解析顺序**：`tenant_id`（交 `BaseTenantGuard`，**不复制租户解析链**）→ `module_key`（形态 + 登记态）
  → `resource_type`（形态 + 前缀归属 + 注册与有效态）→ `resource_key`（pattern / 长度 / 归属）。
- **校验顺序固定**：租户可用性 → 模块登记态 → 资源类型注册与归属 → 产品规则（`verify` 钩子）。
  前三步基座统一，产品只追加最后一步；顺序不可调、不可跳。
- **模块登记态口径**：只判 `sys_module.status`（进程内 `service_catalog_view`，不回源）；租户级模块开关
  由 `tenant_module` 门禁（82008）在权限链路判定，属另一层，**不进本链**（避免作用域判定依赖 fail-open 契约）。
- **失败语义**：租户两类沿用 `80001` / `80002`、租户源不可达沿用 `10007`（503，fail-closed）；
  模块 / 资源四类用 `82009` ~ `82012`。对外消息不区分「是否存在」，类型「已停用」与「未注册」同码，
  内部日志用不同事件名区分。
- **空实现**：`NullScopeResolver`（`null.py`）调用即 `ConfigError`——占位恒放行会让「配置写错」变成
  「作用域全放行」，与 `NullTenantGuard` 同口径。
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import reset_scope_context, set_scope_context
from bms_core.core.exceptions import (
    ConfigError,
    ParamError,
    ScopeModuleDisabledError,
    ScopeModuleNotRegisteredError,
    ScopeResourceOutOfBoundsError,
    ScopeResourceTypeNotRegisteredError,
)
from bms_core.core.factory import BasePluginFactory
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.tenant import TenantContext
from bms_core.resource_scope.base import (
    MODULE_KEY_RE,
    RESOURCE_TYPE_KEY_RE,
    SCOPE_RESOURCE_DISABLED,
    SCOPE_RESOURCE_ENABLED,
    ResourceScopeKey,
    ScopeResourceTypeRecord,
    find_scope_resource_type,
)
from bms_core.resource_scope.rules import EMPTY_SCOPE_RULE_CHAIN, ScopeRuleChain, build_scope_rule_chain
from bms_core.services.module_registry import ModuleRecord, ModuleStatus, service_catalog_view
from bms_core.tenant.guard import BaseTenantGuard, TenantTarget

__all__ = [
    "SOURCE_SCOPE_RESOLVER",
    "BaseScopeResolver",
    "ResolvedScope",
    "SourceScopeResolver",
    "SourceScopeResolverFactory",
    "get_scope_resolver",
    "require_scope",
]

SOURCE_SCOPE_RESOLVER = "source"
"""默认实现名（复用租户可用性守卫，装配期登记）。"""

SCOPE_RESOURCE_SOURCES: ConcurrentStableList[str] = ConcurrentStableList(("path", "query"))
"""管理面依赖工厂支持的取参位置（请求体需业务层直调 `resolve`，不由工厂自动读流）。"""

OWNER_TENANT_PARAM = "owner_tenant_id"
"""管理面 `owner=True` 时读取的查询参数名（资源归属租户，可选）。"""

_LOGGER = get_logger("bms.scope_resolver")


@dataclass(frozen=True)
class ResolvedScope(BaseValueObject):
    """解析成功的作用域（不可变）：租户上下文 + 三级标识 + 命中的类型记录 + 产品扩展位。

    Attributes:
        tenant: 已通过可用性判定的租户上下文。
        key: 三级标识（`01_1` 值对象）。
        resource_type: 命中的资源类型记录；模块级作用域为 `None`。
        extensions: 产品自定义扩展（只读映射；`compare=False`，不参与相等与哈希）。
    """

    tenant: TenantContext
    key: ResourceScopeKey
    resource_type: ScopeResourceTypeRecord | None = None
    extensions: Mapping[str, object] = field(  # bare-collections:allow（只读映射，构造即冻结）
        default_factory=dict[str, object], compare=False
    )

    def __post_init__(self) -> None:
        """冻结扩展位为只读映射（构造后不可改）。

        Raises:
            TypeError: 扩展位不是映射形态。
        """
        if not isinstance(self.extensions, MappingProxyType):
            object.__setattr__(self, "extensions", MappingProxyType(dict(self.extensions)))

    @property
    def tenant_id(self) -> int:
        """租户主键（取自三级标识）。

        Returns:
            int: 租户雪花主键。
        """
        return self.key.tenant_id

    @property
    def module_key(self) -> str:
        """模块键。

        Returns:
            str: 模块注册键。
        """
        return self.key.module_key

    @property
    def resource_key(self) -> str | None:
        """资源标识（模块级作用域为 `None`）。

        Returns:
            str | None: 资源标识。
        """
        return self.key.resource_key

    @property
    def effective_status(self) -> str:
        """有效状态（无类型时恒启用；有类型时由记录两态派生，已通过校验必为启用）。

        Returns:
            str: `enabled` / `disabled`。
        """
        if self.resource_type is None:
            return SCOPE_RESOURCE_ENABLED
        return SCOPE_RESOURCE_ENABLED if self.resource_type.is_active() else SCOPE_RESOURCE_DISABLED

    def as_text(self) -> str:
        """作用域文本形态（日志 / 缓存键 / 审计定位用）。

        Returns:
            str: `{tenant_id}/{module_key}/{resource_key}`。
        """
        return self.key.as_text()

    def with_extensions(self, **values: object) -> ResolvedScope:
        """附加产品扩展位，返回**新实例**（原实例不变）。

        Args:
            **values: 扩展键值（覆盖同名键；不传则复制原扩展位）。

        Returns:
            ResolvedScope: 新作用域（`tenant` / `key` / `resource_type` 不变）。
        """
        merged: dict[str, object] = dict(self.extensions)  # bare-collections:allow（局部缓冲，随即冻结）
        merged.update(values)
        return ResolvedScope(tenant=self.tenant, key=self.key, resource_type=self.resource_type, extensions=merged)


class BaseScopeResolver(BasePluggable, ABC):
    """作用域解析与校验契约（能力域 `scope_resolver`）：三入口一套判定。

    子类只实现 `resolve`（默认实现见 `SourceScopeResolver`）；`require` / `per_round` / `batch` /
    `require_sync` 共用它，`verify` 为产品扩展钩子。
    """

    key: str = "scope_resolver"
    plugin_key: str = "scope_resolver"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, rule_chain: ScopeRuleChain | None = None) -> None:
        """初始化（可选注入第四步规则链）。

        Args:
            rule_chain: 有序规则链；`None` 表示空链（不做第四步产品规则，与改造前等价）。
        """
        self._rule_chain: ScopeRuleChain = EMPTY_SCOPE_RULE_CHAIN if rule_chain is None else rule_chain

    @property
    def rule_chain(self) -> ScopeRuleChain:
        """第四步规则链（`scope_rule` 扩展点声明驱动）。

        Returns:
            ScopeRuleChain: 规则链（空链表示无产品规则）。
        """
        return self._rule_chain

    @abstractmethod
    async def resolve(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """唯一判定点：解析三级 + 四步校验 + 产品规则。

        Args:
            target: 租户定位；`None` 表示取**完整**请求租户上下文（无主键的演示兜底一律拒）。
            module_key: 模块注册键（须已登记且启用）。
            resource_type: 资源类型标识 `{module_key}.{kind}`；模块级作用域可不传。
            resource_key: 资源标识；`None` 表示模块级作用域。非空时必须提供 `resource_type`。
            owner_tenant_id: 调用方声明的资源归属租户；传入则须等于当前租户。

        Returns:
            ResolvedScope: 已通过校验的作用域。

        Raises:
            ParamError: 参数形态非法或自洽失败（10001）。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
            ScopeModuleNotRegisteredError: 模块键未登记（82009 / 400）。
            ScopeModuleDisabledError: 模块键已登记未启用（82010 / 403）。
            ScopeResourceTypeNotRegisteredError: 资源类型未注册或已停用（82011 / 400）。
            ScopeResourceOutOfBoundsError: 资源取值越界或归属不符（82012 / 403）。
        """
        ...

    async def require(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """单次校验（数据面帧入口逐帧调用）。

        Args:
            target: 租户定位（语义同 `resolve`）。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Returns:
            ResolvedScope: 已通过校验的作用域。
        """
        return await self.resolve(
            target,
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )

    async def per_round(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """异步循环守卫：每轮调用一次（结论与 `require` 相同，语义显式）。

        通过后写入上下文（覆盖上一轮），供本轮循环体取用。

        Args:
            target: 租户定位（语义同 `resolve`）。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Returns:
            ResolvedScope: 已通过校验的作用域。
        """
        scope = await self.require(
            target,
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )
        set_scope_context(scope)
        return scope

    @asynccontextmanager
    async def batch(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> AsyncGenerator[ResolvedScope]:
        """批处理前置检查：进入时校验一次并写入上下文，批内不再回源，退出复位。

        Args:
            target: 租户定位（语义同 `resolve`）。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Yields:
            ResolvedScope: 已通过校验的作用域。
        """
        scope = await self.require(
            target,
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )
        token = set_scope_context(scope)
        try:
            yield scope
        finally:
            reset_scope_context(token)

    @asynccontextmanager
    async def frame(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> AsyncGenerator[ResolvedScope]:
        """数据面帧入口：逐帧判定，帧内写入上下文，退出复位。

        与 `require` 的区别：`require` 是纯判定、返回后无法复位，若由它写上下文会把上一帧的作用域
        残留给下一帧；本入口用 `Token` 在 `finally` 复位，异常路径同样复位（嵌套按 LIFO 正确）。

        Args:
            target: 租户定位（语义同 `resolve`）。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Yields:
            ResolvedScope: 已通过校验的作用域。
        """
        scope = await self.require(
            target,
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )
        token = set_scope_context(scope)
        try:
            yield scope
        finally:
            reset_scope_context(token)

    def require_sync(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """同步执行体入口（内部 `asyncio.run` 承载异步判定）。

        Args:
            target: 租户定位（语义同 `resolve`）。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Returns:
            ResolvedScope: 已通过校验的作用域。

        Raises:
            ConfigError: 当前线程已有运行中的事件循环（同步入口不可用）。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.require(
                    target,
                    module_key=module_key,
                    resource_type=resource_type,
                    resource_key=resource_key,
                    owner_tenant_id=owner_tenant_id,
                )
            )
        raise ConfigError("require_sync 不可在运行中的事件循环内调用；请改用 `await require(...)`")

    def verify(self, scope: ResolvedScope) -> None:
        """第四步：产品规则（`scope_rule` 规则链；缺省空链）。

        子类覆写本方法仍生效：需要规则链同时执行的，覆写内应调 `super().verify(scope)`
        （既有写法「只覆写不调 super」保持原语义，规则链不执行）。

        Args:
            scope: 已通过前四步校验的作用域。

        Raises:
            BizError: 规则拒绝（原样冒泡）。
            InternalError: 规则抛非业务异常（fail-closed）。
        """
        self._rule_chain.verify(scope)


class SourceScopeResolver(BaseScopeResolver):
    """默认实现：租户判定复用 `BaseTenantGuard`，模块 / 资源判定走进程内只读视图。"""

    plugin_name: str = SOURCE_SCOPE_RESOLVER

    def __init__(
        self,
        *,
        guard_provider: Callable[[], BaseTenantGuard],
        rule_chain: ScopeRuleChain | None = None,
    ) -> None:
        """初始化。

        Args:
            guard_provider: 租户可用性守卫提供者（**惰性取**，避免捕获装配期的旧实例）。
            rule_chain: 第四步规则链（`scope_rule` 扩展点声明驱动；`None` 为空链）。
        """
        super().__init__(rule_chain=rule_chain)
        self._guard_provider = guard_provider

    async def resolve(
        self,
        target: TenantTarget | None = None,
        *,
        module_key: str,
        resource_type: str | None = None,
        resource_key: str | None = None,
        owner_tenant_id: int | None = None,
    ) -> ResolvedScope:
        """解析三级并顺序校验（首个失败即抛）。

        Args:
            target: 租户定位。
            module_key: 模块注册键。
            resource_type: 资源类型标识。
            resource_key: 资源标识。
            owner_tenant_id: 资源归属租户。

        Returns:
            ResolvedScope: 已通过校验的作用域。

        Raises:
            ParamError: 参数形态非法或自洽失败（10001）。
            ConfigError: 租户上下文缺少主键。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
            ScopeModuleNotRegisteredError: 模块键未登记（82009 / 400）。
            ScopeModuleDisabledError: 模块键已登记未启用（82010 / 403）。
            ScopeResourceTypeNotRegisteredError: 资源类型未注册或已停用（82011 / 400）。
            ScopeResourceOutOfBoundsError: 资源取值越界或归属不符（82012 / 403）。
        """
        if resource_key is not None and resource_type is None:
            raise ParamError("作用域资源标识与类型标识须同时提供：模块级作用域请勿传 resource_key")
        context = await self._guard_provider().require(target)
        if context.tenant_id is None:
            raise ConfigError("租户上下文缺少主键（tenant_id），无法构成三级作用域")
        record = _check_module_and_type(module_key, resource_type)
        if resource_key is not None:
            _check_resource_key(
                record=cast("ScopeResourceTypeRecord", record),
                resource_key=resource_key,
                owner_tenant_id=owner_tenant_id,
                tenant_id=context.tenant_id,
            )
        scope = ResolvedScope(
            tenant=context,
            key=ResourceScopeKey(
                tenant_id=context.tenant_id,
                module_key=module_key,
                resource_key=resource_key,
            ),
            resource_type=record,
        )
        self.verify(scope)
        return scope


def _check_module_and_type(module_key: str, resource_type: str | None) -> ScopeResourceTypeRecord | None:
    """校验模块登记态与资源类型（形态 → 登记 → 归属 → 有效态）。

    Args:
        module_key: 模块注册键。
        resource_type: 资源类型标识；`None` 表示模块级作用域（只校验模块键）。

    Returns:
        ScopeResourceTypeRecord | None: 命中的类型记录（模块级为 `None`）。

    Raises:
        ParamError: 模块键或类型标识形态非法（10001）。
        ScopeModuleNotRegisteredError: 模块键未登记（82009 / 400）。
        ScopeModuleDisabledError: 模块键已登记未启用（82010 / 403）。
        ScopeResourceTypeNotRegisteredError: 类型未注册 / 不属于本模块 / 已停用（82011 / 400）。
    """
    if not MODULE_KEY_RE.fullmatch(module_key):
        raise ParamError(f"作用域模块键形态非法（snake_case）：{module_key}")
    module = _find_module(module_key)
    if module is None:
        _LOGGER.warning("scope_module_unknown", module_key=module_key)
        raise ScopeModuleNotRegisteredError(f"作用域不可用：模块键未登记（{module_key}）")
    if module.status != ModuleStatus.ENABLED:
        _LOGGER.warning("scope_module_disabled", module_key=module_key, status=module.status)
        raise ScopeModuleDisabledError(f"作用域不可用：模块键未启用（{module_key}）")
    if resource_type is None:
        return None
    if not RESOURCE_TYPE_KEY_RE.fullmatch(resource_type):
        raise ParamError(f"资源类型标识形态非法（{{module_key}}.{{kind}}）：{resource_type}")
    prefix, kind = resource_type.split(".", 1)
    if prefix != module_key:
        _LOGGER.warning(
            "scope_resource_type_cross_module",
            module_key=module_key,
            resource_type=resource_type,
        )
        raise ScopeResourceTypeNotRegisteredError(f"作用域不可用：资源类型未注册（{resource_type}）")
    record = find_scope_resource_type(module_key, kind)
    if record is None:
        _LOGGER.warning("scope_resource_type_unknown", module_key=module_key, resource_type=resource_type)
        raise ScopeResourceTypeNotRegisteredError(f"作用域不可用：资源类型未注册（{resource_type}）")
    if not record.is_active():
        _LOGGER.warning(
            "scope_resource_type_inactive",
            module_key=module_key,
            resource_type=resource_type,
            status=record.status,
            admin_status=record.admin_status,
        )
        raise ScopeResourceTypeNotRegisteredError(f"作用域不可用：资源类型未注册（{resource_type}）")
    return record


def _check_resource_key(
    *,
    record: ScopeResourceTypeRecord,
    resource_key: str,
    owner_tenant_id: int | None,
    tenant_id: int,
) -> None:
    """校验资源取值归属与形态（归属先于形态，避免用 pattern 反推归属）。

    Args:
        record: 命中的类型记录。
        resource_key: 资源标识。
        owner_tenant_id: 调用方声明的归属租户（可选）。
        tenant_id: 当前租户主键。

    Raises:
        ScopeResourceOutOfBoundsError: 归属不符或取值不满足类型规则（82012 / 403）。
    """
    if owner_tenant_id is not None and owner_tenant_id != tenant_id:
        _LOGGER.warning(
            "scope_resource_cross_tenant",
            resource_type=record.resource_type_key,
            tenant_id=tenant_id,
            owner_tenant_id=owner_tenant_id,
        )
        raise ScopeResourceOutOfBoundsError(f"作用域不可用：资源越界（{record.resource_type_key}）")
    if not record.accepts(resource_key):
        _LOGGER.warning(
            "scope_resource_out_of_bounds",
            resource_type=record.resource_type_key,
        )
        raise ScopeResourceOutOfBoundsError(f"作用域不可用：资源越界（{record.resource_type_key}）")


def _find_module(module_key: str) -> ModuleRecord | None:
    """在服务目录视图内查模块登记记录（进程内，不回源）。

    Args:
        module_key: 模块注册键。

    Returns:
        ModuleRecord | None: 登记记录；未登记为 `None`。
    """
    for record in service_catalog_view():
        if record.module_key == module_key:
            return record
    return None


def _guard_reader(app: object) -> Callable[[], BaseTenantGuard]:
    """构造惰性租户守卫读取器（每次判定按当前配置解析，不捕获实例）。

    Args:
        app: 应用实例（读取 `app.state.settings`）。

    Returns:
        Callable[[], BaseTenantGuard]: 零参读取器。

    Raises:
        ConfigError: 应用未装配 settings。
    """

    def _read() -> BaseTenantGuard:
        state = getattr(app, "state", None)
        settings = getattr(state, "settings", None)
        if settings is None:
            raise ConfigError("应用未装配 settings（app.state.settings 缺失），作用域解析不可用")
        return cast(
            "BaseTenantGuard",
            resolve_plugin(
                "tenant_guard",
                cast("Settings", settings).tenant_guard.provider,
                expected_version=BaseTenantGuard.contract_version,
            ),
        )

    return _read


class SourceScopeResolverFactory(BasePluginFactory[SourceScopeResolver]):
    """默认实现工厂（装配期登记 `scope_resolver:source`）。"""

    plugin_key: str = "scope_resolver"
    plugin_name: str = SOURCE_SCOPE_RESOLVER

    def __init__(self, app: object) -> None:
        """初始化。

        Args:
            app: 应用实例（惰性读取 `app.state.settings`）。
        """
        self._app = app

    def create(self, options: None = None) -> SourceScopeResolver:
        """构造解析器（守卫在每次判定时解析，不捕获实例）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SourceScopeResolver: 解析器实例。
        """
        del options
        requirements = getattr(getattr(self._app, "state", None), "extension_requirements", None)
        chain = build_scope_rule_chain(requirements or ())
        return SourceScopeResolver(guard_provider=_guard_reader(self._app), rule_chain=chain)


def get_scope_resolver(request: Request) -> BaseScopeResolver:
    """取应用级作用域解析器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseScopeResolver: 已装配的解析器实现。

    Raises:
        PluginError: 配置的实现名未登记 / 契约版本不兼容。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseScopeResolver",
        resolve_plugin(
            "scope_resolver",
            settings.scope_resolver.provider,
            expected_version=BaseScopeResolver.contract_version,
        ),
    )


def require_scope(
    module_key: str,
    resource_type: str,
    *,
    resource_from: str = "path",
    resource_param: str = "resource_key",
    owner: bool = False,
) -> Callable[[Request], Awaitable[ResolvedScope]]:
    """管理面依赖工厂：按路由声明解析并校验三级作用域。

    用法：`Depends(require_scope("msg", "msg.topic", resource_from="path"))`。
    请求体里的资源标识**不由本工厂读**（会消费请求流）；该场景由业务层直调 `resolver.resolve(...)`。

    Args:
        module_key: 模块注册键。
        resource_type: 资源类型标识 `{module_key}.{kind}`。
        resource_from: 取参位置（`path` / `query`）。
        resource_param: 取参名（缺省 `resource_key`）。
        owner: 是否读取查询参数 `owner_tenant_id` 做归属校验。

    Returns:
        Callable[[Request], Awaitable[ResolvedScope]]: FastAPI 依赖函数。

    Raises:
        ConfigError: `resource_from` 取值不在 `SCOPE_RESOURCE_SOURCES` 内（装配期即错）。
    """
    if resource_from not in SCOPE_RESOURCE_SOURCES:
        raise ConfigError(f"作用域取参位置非法（仅支持 {', '.join(SCOPE_RESOURCE_SOURCES)}）：{resource_from}")

    async def _dependency(request: Request) -> ResolvedScope:
        """解析当前请求的作用域。

        Args:
            request: 请求对象。

        Returns:
            ResolvedScope: 已通过校验的作用域。
        """
        resource_key = read_scope_resource(request, resource_from=resource_from, param=resource_param)
        owner_tenant_id = read_scope_owner(request) if owner else None
        scope = await get_scope_resolver(request).require(
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )
        set_scope_context(scope)
        return scope

    return _dependency


def read_scope_resource(request: Request, *, resource_from: str, param: str) -> str:
    """按位置读取资源标识。

    Args:
        request: 请求对象。
        resource_from: 取参位置（`path` / `query`）。
        param: 取参名。

    Returns:
        str: 资源标识。

    Raises:
        ParamError: 取值缺失（10001）。
    """
    source = request.path_params if resource_from == "path" else request.query_params
    value = source.get(param)
    if not value:
        raise ParamError(f"作用域资源标识缺失（{resource_from}.{param}）")
    return str(value)


def read_scope_owner(request: Request) -> int | None:
    """读取可选的归属租户查询参数。

    Args:
        request: 请求对象。

    Returns:
        int | None: 归属租户主键；未提供为 `None`。

    Raises:
        ParamError: 取值非整数（10001）。
    """
    raw = request.query_params.get(OWNER_TENANT_PARAM)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ParamError(f"资源归属租户形态非法（须为雪花 id 十进制）：{raw}") from exc

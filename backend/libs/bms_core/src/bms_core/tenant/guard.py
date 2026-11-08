"""租户可用性守卫能力域：异步路径（消费 / 任务 / 批处理）的停用拦截（任务 `04_02`）。

- **为什么需要**：停用校验原本只在 HTTP / RPC 入口（`TenantMiddleware` + 租户解析）生效；消息消费、
  定时任务、事件消费与批量作业不经过中间件，停用租户仍可能产生副作用。本能力域提供**同一套判定**的
  异步入口，与 HTTP 入口得出同一结论、同一错误码。
- **取数复用**：默认实现 `SourceTenantGuard` 直接复用租户源 `TenantLookup`（`by_id` / `by_code` /
  `by_domain`）——即 `RemoteTenantSource` / `LocalTenantSource`，其全局版本戳
  `bms:global:tenant:version` 已保证停用**即时生效**，**不新建缓存、不新建状态判断**；状态判定只在租户源。
- **三种使用形态**：HTTP 依赖（沿用中间件，不改）；异步循环守卫 `per_round`（每轮校验）；批处理前置
  `batch`（进入校验一次、批内不重复回源）。判定逻辑只有 `require` 一份，两者是其语义入口。
- **同步入口** `require_sync`：供同步执行体（`BaseTask.run` 形态）使用；检测到运行中事件循环即
  `ConfigError`（不降级、不放行）。
- **分支语义与 HTTP 一致**：未知租户 `TenantNotFoundError`（80001 / 404）、已停用
  `TenantSuspendedError`（80002 / 403）、租户源不可达 `ServiceUnavailableError`（10007 / 503，
  fail-closed 不静默放行），全部由租户源抛出、本层原样冒泡。
- **空实现**：`NullTenantGuard` 调用即 `ConfigError`（fail-closed）——插件装配对每条接线无条件解析
  `provider or null`，若占位恒放行，则「配置写错 = 异步路径全放行」。
- **产品扩展**：产品继承默认实现并覆写 `verify(context, scope)` 补自有规则（如消息平台按 `scope`＝命名空间
  校验），经 `configure_plugins()` 登记自己的实现名，**不改本文件**。
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import get_tenant_context
from bms_core.core.exceptions import ConfigError, ParamError, TenantNotFoundError, TenantSuspendedError
from bms_core.core.factory import BasePluginFactory
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.tenant import TenantContext, TenantLookup, is_tenant_code, is_tenant_domain, is_tenant_id

__all__ = [
    "READONLY_METHODS",
    "SOURCE_TENANT_GUARD",
    "BaseTenantGuard",
    "SourceTenantGuard",
    "SourceTenantGuardFactory",
    "TenantTarget",
    "get_tenant_guard",
    "readonly_route_allowed",
    "tenant_source_reader",
]

SOURCE_TENANT_GUARD = "source"
"""默认实现名（复用租户源，装配期登记）。"""

_LOGGER = get_logger("bms.tenant_guard")

READONLY_METHODS = frozenset({"GET", "HEAD"})
"""只读通道允许的 HTTP 方法（写方法永不进只读通道；不按业务语义猜「是不是查询」）。"""


def readonly_route_allowed(
    *, service_key: str | None, method: str, path: str, routes: ConcurrentStableList[str]
) -> bool:
    """判定本次请求是否走管理面只读通道（任务 `04_03` §4.11）。

    三条件同时成立才放行：方法 ∈ `{GET, HEAD}`、路径命中本服务登记的只读前缀、配置非空。
    缺省（`routes` 为空 / 条目无 `服务键:` 前缀 / 服务键不匹配）一律**不放行**——fail-closed，
    配置写错的后果是「只读窗口里读不到」，而不是「把写通道也打开了」。

    Args:
        service_key: 当前服务键（`ServiceIdentity.name`；取不到时只认不带服务键的条目）。
        method: HTTP 方法。
        path: 请求路径。
        routes: 配置项 `[tenant_guard].readonly_routes`，形如 `"msg:/api/v1/msg/admin/"`。

    Returns:
        bool: 命中返回 True。
    """
    if method.upper() not in READONLY_METHODS:
        return False
    if not routes:
        return False
    for entry in routes:
        owner, separator, prefix = entry.partition(":")
        if not separator or not prefix:
            _LOGGER.warning("tenant_readonly_route_malformed", entry=entry)
            continue
        if service_key is not None and owner.strip() != service_key:
            continue
        if path.startswith(prefix):
            return True
    return False


@dataclass(frozen=True)
class TenantTarget(BaseValueObject):
    """租户定位（值对象）：异步路径要校验「哪个租户」。

    三个标识**恰好一个**非空——`tenant_id`（雪花 id 十进制字符串，内部身份）、`code`（租户编码，
    运维 / 脚本友好）、`domain`（子域名）。形态先于取数：形态非法即 `ParamError`（10001），不送租户源、
    不派生出库键。
    """

    tenant_id: str | None = None
    """租户主键（雪花 id 十进制字符串）。"""

    code: str | None = None
    """租户编码（字母开头、字母数字下划线、长度 ≤ 64）。"""

    domain: str | None = None
    """租户子域名（≥ 两段 DNS 标签）。"""

    def __post_init__(self) -> None:
        """校验「三选一」与标识形态。

        Raises:
            ParamError: 提供的标识数不为 1，或形态非法。
        """
        provided = sum(1 for value in (self.tenant_id, self.code, self.domain) if value)
        if provided != 1:
            raise ParamError("租户标识须在 tenant_id / code / domain 中恰提供一个")
        if self.tenant_id is not None and not is_tenant_id(self.tenant_id):
            raise ParamError(f"租户主键形态非法（应为雪花 id 十进制字符串）：{self.tenant_id}")
        if self.code is not None and not is_tenant_code(self.code):
            raise ParamError(f"租户编码形态非法（字母开头、字母数字下划线、长度 ≤ 64）：{self.code}")
        if self.domain is not None and not is_tenant_domain(self.domain):
            raise ParamError(f"租户域名形态非法（≥ 两段 DNS 标签）：{self.domain}")

    @property
    def label(self) -> str:
        """日志与错误消息用的租户标识（主键优先，其次编码，最后域名）。

        Returns:
            str: 标识文本（三字段互斥，必有一值）。
        """
        return self.tenant_id or self.code or cast("str", self.domain)

    @classmethod
    def from_context(cls, context: TenantContext) -> TenantTarget:
        """由租户上下文派生定位（主键优先，缺失回落编码）。

        Args:
            context: 租户上下文。

        Returns:
            TenantTarget: 租户定位。

        Raises:
            ParamError: 上下文既无主键也无编码。
        """
        if context.tenant_id is not None:
            return cls(tenant_id=str(context.tenant_id))
        if context.code:
            return cls(code=context.code)
        raise ParamError("租户上下文缺少可用标识（tenant_id / code）")


class BaseTenantGuard(BasePluggable, ABC):
    """租户可用性守卫契约（能力域 `tenant_guard`）：三入口一套判定。

    子类只实现取数判定 `resolve`（默认实现见 `SourceTenantGuard`）；`require` / `per_round` /
    `batch` 三个入口共用它，`verify` 为产品扩展钩子。
    """

    key: str = "tenant_guard"
    plugin_key: str = "tenant_guard"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    async def require(
        self,
        target: TenantTarget | None = None,
        *,
        scope: str | None = None,
        readonly: bool = False,
    ) -> TenantContext:
        """单次校验（一次解析 + 状态判定 + 扩展校验）。

        Args:
            target: 租户定位；`None` 表示取**完整**请求租户上下文（无主键的演示兜底一律拒）。
            scope: 业务范围标识（产品自定义语义，如消息平台的命名空间）；原样转交 `verify`，
                基座不解释。
            readonly: 管理面只读通道（任务 `04_03`）：`True` 时停用 / 注销**不拒**、返回带真实
                `status` 的上下文；`verify` 照常调用（产品扩展校验不跳过）。缺省 `False`。

        Returns:
            TenantContext: 可用租户上下文。

        Raises:
            ConfigError: 未给定位且无完整租户上下文（含演示兜底）。
            ParamError: 租户标识形态非法（由 `TenantTarget` 抛出）。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        located = self._target(target)
        # 只在只读通道时携带关键字：产品自实现的 `resolve`（未声明 `readonly`）在常规路径上零影响。
        context = await (self.resolve(located, readonly=True) if readonly else self.resolve(located))
        self.verify(context, scope)
        return context

    async def per_round(
        self,
        target: TenantTarget | None = None,
        *,
        scope: str | None = None,
        readonly: bool = False,
    ) -> TenantContext:
        """异步循环守卫：每轮调用一次（结论与 `require` 相同，语义显式、便于检索）。

        Args:
            target: 租户定位（语义同 `require`）。
            scope: 业务范围标识（语义同 `require`）。
            readonly: 只读通道（语义同 `require`）。

        Returns:
            TenantContext: 可用租户上下文。

        Raises:
            ConfigError: 未给定位且无完整租户上下文。
            ParamError: 租户标识形态非法。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        return await self.require(target, scope=scope, readonly=readonly)

    @asynccontextmanager
    async def batch(
        self,
        target: TenantTarget | None = None,
        *,
        scope: str | None = None,
        readonly: bool = False,
    ) -> AsyncGenerator[TenantContext]:
        """批处理前置检查：进入时校验一次，批内不再回源。

        Args:
            target: 租户定位（语义同 `require`）。
            scope: 业务范围标识（语义同 `require`）。
            readonly: 只读通道（语义同 `require`）。

        Yields:
            TenantContext: 可用租户上下文。

        Raises:
            ConfigError: 未给定位且无完整租户上下文。
            ParamError: 租户标识形态非法。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        context = await self.require(target, scope=scope, readonly=readonly)
        yield context

    def require_sync(
        self,
        target: TenantTarget | None = None,
        *,
        scope: str | None = None,
        readonly: bool = False,
    ) -> TenantContext:
        """同步执行体入口（内部 `asyncio.run` 承载异步判定）。

        Args:
            target: 租户定位（语义同 `require`）。
            scope: 业务范围标识（语义同 `require`）。
            readonly: 只读通道（语义同 `require`）。

        Returns:
            TenantContext: 可用租户上下文。

        Raises:
            ConfigError: 当前线程已有运行中的事件循环（同步入口不可用），或未给定位且无完整上下文。
            ParamError: 租户标识形态非法。
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.require(target, scope=scope, readonly=readonly))
        raise ConfigError("require_sync 不可在运行中的事件循环内调用；请改用 `await require(...)`")

    def verify(self, context: TenantContext, scope: str | None = None) -> None:
        """扩展钩子（缺省空实现）：产品在绑定判定后追加自有规则。

        Args:
            context: 已通过租户可用性判定的上下文。
            scope: 业务范围标识（产品自定义语义；基座不解释，`None` 表示调用方未指定）。

        Raises:
            BizError: 产品自定义拒绝（由子类抛出，基类原样冒泡）。
        """
        return None

    @abstractmethod
    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """取数 + 状态判定（唯一判定点，三入口共用）。

        Args:
            target: 已校验形态的租户定位。
            readonly: 只读通道（`True` 时停用 / 注销不抛错，返回真实状态的上下文）。

        Returns:
            TenantContext: 可用租户上下文。

        Raises:
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        ...

    @staticmethod
    def _target(target: TenantTarget | None) -> TenantTarget:
        """定位缺省化：未显式传入时取完整请求上下文（拒演示兜底）。

        Args:
            target: 调用方传入的定位。

        Returns:
            TenantTarget: 实际使用的定位。

        Raises:
            ConfigError: 未给定位且无完整租户上下文。
            ParamError: 上下文标识形态非法。
        """
        if target is not None:
            return target
        context = get_tenant_context()
        if context is None or context.tenant_id is None:
            raise ConfigError("异步路径未提供租户标识，且无含主键的请求租户上下文：请显式传入 TenantTarget")
        return TenantTarget.from_context(context)


class SourceTenantGuard(BaseTenantGuard):
    """默认实现：复用租户源（`TenantLookup`），不建缓存、不复制状态判定。"""

    plugin_name: str = SOURCE_TENANT_GUARD

    def __init__(self, *, source_provider: Callable[[], TenantLookup]) -> None:
        """初始化。

        Args:
            source_provider: 租户源提供者（**惰性取**，避免捕获装配期的旧应用实例）。
        """
        self._source_provider = source_provider

    async def resolve(self, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
        """经租户源取上下文（状态判定在租户源内，停用即抛并回收引擎）。

        Args:
            target: 租户定位。
            readonly: 只读通道（停用 / 注销不抛错，也不回收引擎——只读窗口内仍要能读）。

        Returns:
            TenantContext: 可用租户上下文。

        Raises:
            TenantNotFoundError: 未知租户（80001 / 404）。
            TenantSuspendedError: 租户已停用（80002 / 403）。
            ServiceUnavailableError: 租户源不可达（10007 / 503）。
        """
        source = self._source_provider()
        try:
            return await _lookup(source, target, readonly=readonly)
        except TenantSuspendedError:
            _LOGGER.warning("tenant_guard_blocked", tenant=target.label)
            raise
        except TenantNotFoundError:
            _LOGGER.warning("tenant_guard_unknown", tenant=target.label)
            raise


async def _lookup(source: TenantLookup, target: TenantTarget, *, readonly: bool = False) -> TenantContext:
    """按定位分派租户源取数（三者互斥，由 `TenantTarget` 保证）。

    Args:
        source: 租户源。
        target: 租户定位。
        readonly: 只读通道（透传给租户源；`True` 时停用 / 注销不抛错）。

    Returns:
        TenantContext: 租户上下文。
    """
    if target.tenant_id is not None:
        return await (source.by_id(target.tenant_id, readonly=True) if readonly else source.by_id(target.tenant_id))
    if target.code is not None:
        return await (source.by_code(target.code, readonly=True) if readonly else source.by_code(target.code))
    domain = cast("str", target.domain)
    return await (source.by_domain(domain, readonly=True) if readonly else source.by_domain(domain))


def tenant_source_reader(app: object) -> Callable[[], TenantLookup]:
    """构造惰性租户源读取器（守卫工厂与产品子类工厂复用）。

    Args:
        app: 应用实例（读取 `app.state.tenant_source`）。

    Returns:
        Callable[[], TenantLookup]: 零参读取器（每次判定时取当前租户源）。
    """

    def _read() -> TenantLookup:
        """取应用装配的租户源。

        Returns:
            TenantLookup: 租户源。

        Raises:
            ConfigError: 租户源未装配（`app.state.tenant_source` 缺失）。
        """
        state = getattr(app, "state", None)
        source = getattr(state, "tenant_source", None)
        if source is None:
            raise ConfigError("租户源未装配（app.state.tenant_source 缺失），租户可用性守卫不可用")
        return cast("TenantLookup", source)

    return _read


class SourceTenantGuardFactory(BasePluginFactory[SourceTenantGuard]):
    """默认实现工厂（装配期登记 `tenant_guard:source`）。"""

    plugin_key: str = "tenant_guard"
    plugin_name: str = SOURCE_TENANT_GUARD

    def __init__(self, app: object) -> None:
        """初始化。

        Args:
            app: 应用实例（惰性读取 `app.state.tenant_source`）。
        """
        self._app = app

    def create(self, options: None = None) -> SourceTenantGuard:
        """构造守卫（租户源在每次判定时读取，不捕获实例）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            SourceTenantGuard: 守卫实例。
        """
        del options
        return SourceTenantGuard(source_provider=tenant_source_reader(self._app))


def get_tenant_guard(request: Request) -> BaseTenantGuard:
    """取应用级租户可用性守卫（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTenantGuard: 已装配的守卫实现。

    Raises:
        PluginError: 配置的实现名未登记 / 契约版本不兼容。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTenantGuard",
        resolve_plugin(
            "tenant_guard",
            settings.tenant_guard.provider,
            expected_version=BaseTenantGuard.contract_version,
        ),
    )

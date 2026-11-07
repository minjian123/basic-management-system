"""资源级 ACL 接入约束（07D `02_05`）：单点判定端口 + 固定顺序的组合依赖。

**定位**：资源级 ACL 是**产品特有扩展**，不是第五类标准扩展点；基座**不实现通用 ACL 引擎**，
只给约束、判定顺序与上收条件（架构 41 §4.2-4、§8 红线六）。

**判定顺序固定**（不可调、不可跳）：

```
① 基座 RBAC（功能级，require_permission） → ② 三级标识形态 → ③ 产品资源级 ACL → ④ 作用域归属
```

- **ACL 不得前置**：①未完成就查资源会泄露资源存在性；
- **②只做形态**：构造 `ResourceScopeKey` 校验形态，**不查登记表**（登记态判定全在 ④，避免在 ACL 前
  暴露「资源是否登记 / 是否存在」）；
- **④最终兜底**：即使 ACL 对跨租户 / 跨模块资源返回「允许」，④仍拒绝——「不因 ACL 放行」由顺序
  天然保证，不依赖实现自觉；
- **未声明不启用**：产品未声明 `resource_acl` 扩展点则 ③ 跳过（多数产品无资源级授权模型）；
  一经声明（必需或可选）且实现存在，③必执行；声明必需但实现缺失 → 装配期拒启（`extension` 能力域）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.config import Settings
from bms_core.core.context import get_current_tenant_id, get_current_user_id
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.extension.base import RESOURCE_ACL_KEY, ExtensionRequirement
from bms_core.permission.base import require_permission
from bms_core.resource_scope.base import ResourceScopeKey
from bms_core.resource_scope.resolver import (
    ResolvedScope,
    get_scope_resolver,
    read_scope_owner,
    read_scope_resource,
)

__all__ = [
    "AclContext",
    "BaseResourceAcl",
    "get_resource_acl",
    "require_resource_access",
]


@dataclass(frozen=True)
class AclContext(BaseValueObject):
    """ACL 判定入参：已过 RBAC 的请求上下文 + 三级标识（形态已校验，**未做登记态判定**）。"""

    tenant_id: int
    """当前租户主键（必要条件：无租户上下文的调用不构成资源级判定）。"""

    module_key: str
    """模块注册键。"""

    resource_type: str | None = None
    """资源类型标识（模块级判定可为空）。"""

    resource_key: str | None = None
    """资源标识（模块级判定为空）。"""

    user_id: int | None = None
    """操作人主键（服务身份为 `None`）。"""

    roles: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList[str]())
    """角色键（**本期恒为空**：权限检查器未暴露角色集合，产品如需角色按 `user_id` 自取）。

    保留该字段是为了上收（基座统一授权）时补注入而不改契约；不得据此替代 RBAC 判定
    ——本上下文只在 RBAC 通过后才产生。
    """


class BaseResourceAcl(BasePluggable, ABC):
    """资源级 ACL 契约（能力域 `resource_acl`）：允许即返回，拒绝抛 `BizError`。"""

    key: str = RESOURCE_ACL_KEY
    plugin_key: str = RESOURCE_ACL_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def check(self, ctx: AclContext, *, action: str) -> None:
        """判定主体能否对该资源执行动作。

        Args:
            ctx: 判定入参（租户 / 模块 / 资源 / 操作人）。
            action: 动作名（缺省取权限码动词，如 `consume` / `replay`）。

        Raises:
            ResourceAccessDeniedError: 拒绝（82013 / 403；不区分资源是否存在）。
        """
        ...


def get_resource_acl(request: Request) -> BaseResourceAcl:
    """取应用级资源级 ACL 实现（依赖注入提供者）。

    Args:
        request: 请求对象（取装配 settings）。

    Returns:
        BaseResourceAcl: 配置的实现。

    Raises:
        PluginError: 实现名未登记 / 契约版本不兼容。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseResourceAcl",
        resolve_plugin(
            RESOURCE_ACL_KEY,
            settings.resource_acl.provider,
            expected_version=BaseResourceAcl.contract_version,
        ),
    )


def _declared(request: Request) -> bool:
    """产品是否声明了 `resource_acl` 扩展点。

    Args:
        request: 请求对象（读 `app.state.extension_requirements`）。

    Returns:
        bool: 已声明为 True（未声明即不启用，见模块文档）。
    """
    requirements = getattr(request.app.state, "extension_requirements", None)
    if not requirements:
        return False
    return any(isinstance(item, ExtensionRequirement) and item.plugin_key == RESOURCE_ACL_KEY for item in requirements)


def _tenant_id_required() -> int:
    """取当前租户主键（缺失即拒：资源级判定必须有租户上下文）。

    Returns:
        int: 租户主键。

    Raises:
        ParamError: 无租户上下文（10001）。
    """
    raw = get_current_tenant_id()
    if not raw:
        raise ParamError("资源级授权判定缺少租户上下文")
    try:
        return int(raw)
    except ValueError as exc:
        raise ParamError(f"租户上下文主键非法：{raw!r}") from exc


def require_resource_access(
    permission: str,
    *,
    module_key: str,
    resource_type: str | None = None,
    action: str | None = None,
    resource_from: str = "path",
    resource_param: str = "resource_key",
    owner: bool = False,
) -> Callable[[Request], Awaitable[ResolvedScope]]:
    """组合依赖：RBAC → 形态 → 资源级 ACL → 作用域归属（顺序固定）。

    用法：`Depends(require_resource_access("msg:consume", module_key="msg",
    resource_type="msg.topic", action="subscribe"))`。

    Args:
        permission: 功能级权限码（必填；RBAC 未过即终止）。
        module_key: 模块注册键。
        resource_type: 资源类型标识（`{module_key}.{kind}`）。
        action: ACL 动作（缺省取权限码动词）。
        resource_from: 资源标识取参位置（`path` / `query`）。
        resource_param: 取参名（缺省 `resource_key`）。
        owner: 是否读取查询参数 `owner_tenant_id` 做归属校验。

    Returns:
        Callable[[Request], Awaitable[ResolvedScope]]: FastAPI 依赖函数。
    """
    rbac_dependency = require_permission(permission)

    async def _dependency(request: Request) -> ResolvedScope:
        """按固定顺序判定并返回作用域。

        Args:
            request: 请求对象。

        Returns:
            ResolvedScope: 已通过四级判定的作用域。

        Raises:
            PermissionError: 功能级权限不足（30001 / 403）。
            TenantModuleDisabledError: 产品模块未开通（82008 / 403）。
            ParamError: 资源标识缺失或形态非法（10001）。
            BizError: 产品 ACL 拒绝（82013 或产品自定义码）。
            ConfigError: 声明了 ACL 但实现为占位 / 解析失败。
            其余见 `BaseScopeResolver`（租户与作用域四类码）。
        """
        await rbac_dependency(request)
        resource_key = read_scope_resource(request, resource_from=resource_from, param=resource_param)
        if _declared(request):
            ctx = AclContext(
                tenant_id=_tenant_id_required(),
                module_key=module_key,
                resource_type=resource_type,
                resource_key=resource_key,
                user_id=get_current_user_id(),
            )
            # ② 形态校验（不查登记表）：只保证交给 ACL 的标识是合法形态，登记态判定在 ④
            ResourceScopeKey(tenant_id=ctx.tenant_id, module_key=module_key, resource_key=resource_key)
            get_resource_acl(request).check(ctx, action=action or permission.split(":")[-1])
        owner_tenant_id = read_scope_owner(request) if owner else None
        return await get_scope_resolver(request).require(
            module_key=module_key,
            resource_type=resource_type,
            resource_key=resource_key,
            owner_tenant_id=owner_tenant_id,
        )

    return _dependency

"""租户模块门禁能力域：按租户模块状态拦截接口（任务 `04_01`）。

- **判定语义**：只拦「可勾选产品模块」（`TENANT_OPTIONAL_MODULE_KEYS`）；基础能力模块恒开通。
- **状态来源**：tenant 服务 `sys_tenant_module`（开通清单与启停状态），经内部只读契约取数；
  主链路（`require_permission`）按权限码业务段 → 模块映射调用本门禁。
- **降级口径**：回源失败 **fail-open + WARNING**（只影响模块拦截这一层；权限码判定仍由本地快照负责），
  避免 tenant 服务故障拖垮全站请求。
- **实现选择**：`[tenant_module].provider`（空串 = 占位实现全部放行；`remote` = 真实实现）。
"""

from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.exceptions import TenantModuleDisabledError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.services.module_registry import is_optional_module

__all__ = [
    "TENANT_MODULE_STATE_ABSENT",
    "TENANT_MODULE_STATE_DISABLED",
    "TENANT_MODULE_STATE_ENABLED",
    "BaseTenantModuleGate",
    "get_tenant_module_gate",
]

_LOGGER = get_logger("bms.tenant_module")

TENANT_MODULE_STATE_ENABLED = "enabled"
"""模块状态：已开通且启用。"""

TENANT_MODULE_STATE_DISABLED = "disabled"
"""模块状态：已开通但停用。"""

TENANT_MODULE_STATE_ABSENT = "absent"
"""模块状态：未开通（无开通清单行）。"""


class BaseTenantModuleGate(BasePluggable, ABC):
    """租户模块门禁契约：取模块状态 / 拒绝停用模块。"""

    key: str = "tenant_module"
    plugin_key: str = "tenant_module"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def state(self, *, tenant_id: int, tenant_code: str | None, module_key: str) -> str:
        """取租户某模块状态。

        Args:
            tenant_id: 租户主键。
            tenant_code: 租户编码（服务间调用令牌租户位；可空）。
            module_key: 模块标识。

        Returns:
            str: `enabled` / `disabled` / `absent`（基础模块与非产品模块恒 `enabled`）。
        """

    async def ensure(self, *, tenant_id: int | None, tenant_code: str | None, module_key: str) -> None:
        """校验模块可用（停用 / 未开通即拒绝）。

        Args:
            tenant_id: 租户主键；None（无租户上下文，如平台内部通道）直接放行。
            tenant_code: 租户编码。
            module_key: 模块标识。

        Raises:
            TenantModuleDisabledError: 模块已停用或未开通（`82008` / 403）。
        """
        if tenant_id is None or not is_optional_module(module_key):
            return
        state = await self.state(tenant_id=tenant_id, tenant_code=tenant_code, module_key=module_key)
        if state == TENANT_MODULE_STATE_ENABLED:
            return
        _LOGGER.warning("tenant_module_blocked", tenant_id=tenant_id, module_key=module_key, state=state)
        raise TenantModuleDisabledError(f"租户模块未开通或已停用：{module_key}")


def get_tenant_module_gate(request: Request) -> BaseTenantModuleGate:
    """取应用级租户模块门禁（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTenantModuleGate: 应用装配的门禁实现。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTenantModuleGate",
        resolve_plugin(
            "tenant_module",
            settings.tenant_module.provider,
            expected_version=BaseTenantModuleGate.contract_version,
        ),
    )

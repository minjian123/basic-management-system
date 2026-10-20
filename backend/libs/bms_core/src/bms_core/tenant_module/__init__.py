"""租户模块门禁能力域（任务 `04_01`）。

- `base`：契约与依赖注入提供者；
- `null`：占位实现（全部放行）；
- `remote`：真实实现（tenant 服务内部契约 + 缓存 + fail-open）。
"""

from bms_core.tenant_module.base import BaseTenantModuleGate, get_tenant_module_gate

__all__ = ["BaseTenantModuleGate", "get_tenant_module_gate"]

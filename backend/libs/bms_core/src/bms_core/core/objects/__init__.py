"""core 层对象体系：三个体系根 + 值对象体系的角色链层（统一再导出）。

- **体系根**（落点 `roots.py`）：`BaseValueObject` / `BaseDataContract` / `BaseFrameworkObject`。
- **角色链层**（一链一模块）：值对象体系按**公共段**分出各自独立的角色链，链长不限、不设固定层数
  ——`options.py`（选项链）等；后续批次按链增补模块，本文件同步再导出。

对外统一从本包导入（`from bms_core.core.objects import BaseValueObject`），链层落点与登记见
《后端基类清单》§10「值对象体系角色链」。
"""

from __future__ import annotations

from bms_core.core.objects.auth_results import BaseAuthorizeUrlResultContract, BaseLoginResultContract
from bms_core.core.objects.identity import BaseIdentityProfileContract, BaseRequestIdentityContract
from bms_core.core.objects.options import BaseOptionsContract
from bms_core.core.objects.roots import (
    FRAMEWORK_OBJECT_KIND,
    BaseDataContract,
    BaseFrameworkObject,
    BaseValueObject,
)
from bms_core.core.objects.tenant import BaseTenantViewContract
from bms_core.core.objects.tokens import (
    BaseOidcTokenSpecContract,
    BaseRefreshableTokenContract,
    BaseSecretMaterialContract,
    BaseTokenClaimsContract,
    BaseTokenContract,
    BaseTokenSpecContract,
)

__all__ = [
    "FRAMEWORK_OBJECT_KIND",
    "BaseAuthorizeUrlResultContract",
    "BaseDataContract",
    "BaseFrameworkObject",
    "BaseIdentityProfileContract",
    "BaseLoginResultContract",
    "BaseOidcTokenSpecContract",
    "BaseOptionsContract",
    "BaseRefreshableTokenContract",
    "BaseRequestIdentityContract",
    "BaseSecretMaterialContract",
    "BaseTenantViewContract",
    "BaseTokenClaimsContract",
    "BaseTokenContract",
    "BaseTokenSpecContract",
    "BaseValueObject",
]

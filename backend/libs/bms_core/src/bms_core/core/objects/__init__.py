"""core 层对象体系：三个体系根 + 值对象体系的角色链层（统一再导出）。

- **体系根**（落点 `roots.py`）：`BaseValueObject` / `BaseDataContract` / `BaseFrameworkObject`。
- **角色链层**（一链一模块）：值对象体系按**公共段**分出各自独立的角色链，链长不限、不设固定层数
  ——`options.py`（选项链）等；后续批次按链增补模块，本文件同步再导出。

对外统一从本包导入（`from bms_core.core.objects import BaseValueObject`），链层落点与登记见
《后端基类清单》§10「值对象体系角色链」。
"""

from __future__ import annotations

from bms_core.core.objects.auth_results import BaseAuthorizeUrlResultContract, BaseLoginResultContract
from bms_core.core.objects.captchas import BaseCaptchaContract
from bms_core.core.objects.decisions import BaseDecisionContract
from bms_core.core.objects.delivery import BaseDeliveryResultContract
from bms_core.core.objects.event_contracts import BaseSnapshotRoundTripContract
from bms_core.core.objects.event_records import BaseEventRecordContract
from bms_core.core.objects.field_rules import BaseFieldRuleContract
from bms_core.core.objects.health import BaseHealthResultContract
from bms_core.core.objects.identity import BaseIdentityProfileContract, BaseRequestIdentityContract
from bms_core.core.objects.llm import BaseLlmResultContract
from bms_core.core.objects.options import BaseOptionsContract
from bms_core.core.objects.outbound import BaseHttpResponseContract
from bms_core.core.objects.ownership import BaseOwnershipContract
from bms_core.core.objects.processes import BaseProcessContract
from bms_core.core.objects.registry_records import BaseRegistryRecordContract
from bms_core.core.objects.reports import BaseOpsReportContract
from bms_core.core.objects.roots import (
    FRAMEWORK_OBJECT_KIND,
    BaseDataContract,
    BaseFrameworkObject,
    BaseValueObject,
)
from bms_core.core.objects.search import BaseSearchContract
from bms_core.core.objects.seeds import BaseI18nSeedContract
from bms_core.core.objects.specs import BaseFieldSpecContract
from bms_core.core.objects.tally import BaseTallyContract
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
    "BaseCaptchaContract",
    "BaseDataContract",
    "BaseDecisionContract",
    "BaseDeliveryResultContract",
    "BaseEventRecordContract",
    "BaseFieldRuleContract",
    "BaseFieldSpecContract",
    "BaseFrameworkObject",
    "BaseHealthResultContract",
    "BaseHttpResponseContract",
    "BaseI18nSeedContract",
    "BaseIdentityProfileContract",
    "BaseLlmResultContract",
    "BaseLoginResultContract",
    "BaseOidcTokenSpecContract",
    "BaseOpsReportContract",
    "BaseOptionsContract",
    "BaseOwnershipContract",
    "BaseProcessContract",
    "BaseRefreshableTokenContract",
    "BaseRegistryRecordContract",
    "BaseRequestIdentityContract",
    "BaseSearchContract",
    "BaseSecretMaterialContract",
    "BaseSnapshotRoundTripContract",
    "BaseTallyContract",
    "BaseTenantViewContract",
    "BaseTokenClaimsContract",
    "BaseTokenContract",
    "BaseTokenSpecContract",
    "BaseValueObject",
]

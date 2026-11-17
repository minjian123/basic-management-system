"""表单定制业务域公共出口（D2 唯一跨域引用面）。

对外提供：只读 DTO（`FieldSpec` / `EffectiveLayoutView` / `ExtFieldSummary` / `ImportColumn`）与
领域服务接口（`FormDesignPort`）。**本模块只做再导出**，不承载业务规则；实现类、仓储与路由不出现在出口。
"""

from typing import Protocol

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_platform.domains.form_design.dto import (
    EffectiveLayoutView as EffectiveLayoutView,
)
from bms_platform.domains.form_design.dto import (
    ExtFieldSummary as ExtFieldSummary,
)
from bms_platform.domains.form_design.dto import (
    FieldSpec as FieldSpec,
)
from bms_platform.domains.form_design.dto import (
    ImportColumn as ImportColumn,
)
from bms_platform.domains.form_design.ports import (
    FormMetadataPort as FormMetadataPort,
)
from bms_platform.domains.form_design.ports import (
    OptionSetPort as OptionSetPort,
)
from bms_platform.domains.form_design.ports import (
    PermissionPort as PermissionPort,
)

__all__ = [
    "EffectiveLayoutView",
    "ExtFieldSummary",
    "FieldSpec",
    "FormMetadataPort",
    "ImportColumn",
    "ImportColumnProvider",
    "OptionSetPort",
    "PermissionPort",
]


class ImportColumnProvider(Protocol):
    r"""导入列派生协议（\`user\` 等业务域消费；实现由装配面注入）。

    设计意图：布局与自建字段的读取属 \`form_design\` 域，消费方不得 import 本域模型或实现；
    装配面构造实现后以本协议注入，跨域边界保持单向。
    """

    async def layout_keys_and_specs(
        self, form_code: str
    ) -> tuple[ConcurrentStableFrozenList[str], ConcurrentStableDict[str, object]]:
        """取某表单的布局字段序与自建字段列规格。

        Args:
            form_code: 表单标识（业务码）。

        Returns:
            tuple: （字段键序, 自建字段列规格）。
        """
        ...

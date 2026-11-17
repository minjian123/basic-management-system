"""表单定制领域纯函数与能力域出口（10_01）。

- `layout`：布局结构归一 / 空布局回退 / 三级解析 / 失效引用（与前端 `domain/form-layout.ts` 同语义）。
- `attrs`：字段属性归一 / 规则编译 / 默认值 / 合法性校验。
- `identifier`：字段键 / 物理列名 / 物理表名白名单（防注入第一道）。
- `validator`：动态校验能力域契约（`BaseFormValidator` + `NullFormValidator` + 提供者）。
  真实实现读租户库的表，按域边界落在服务侧（`bms_platform.domains.form_design`）。
- `import_columns`：导入模板列派生助手（按生效布局生成列集）。

**与 `fieldtype/mapping.py` 的分工**：本包只管「布局与属性的语义」，跨四库类型映射归
`fieldtype/mapping.py`（自建字段专用，不动内建 `fieldtype/local.py`）。
"""

from bms_core.formdesign.validator import (
    FORM_VALIDATOR_PLUGIN_KEY as FORM_VALIDATOR_PLUGIN_KEY,
)
from bms_core.formdesign.validator import (
    BaseFormValidator as BaseFormValidator,
)
from bms_core.formdesign.validator import (
    FieldError as FieldError,
)
from bms_core.formdesign.validator import (
    NullFormValidator as NullFormValidator,
)
from bms_core.formdesign.validator import (
    ValidationResult as ValidationResult,
)
from bms_core.formdesign.validator import (
    build_validation_error_payload as build_validation_error_payload,
)
from bms_core.formdesign.validator import (
    get_form_validator as get_form_validator,
)

__all__ = [
    "FORM_VALIDATOR_PLUGIN_KEY",
    "BaseFormValidator",
    "FieldError",
    "NullFormValidator",
    "ValidationResult",
    "build_validation_error_payload",
    "get_form_validator",
]

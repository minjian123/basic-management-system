"""菜单表单业务域公共出口（D2 唯一跨域引用面）。

对外提供：菜单表单仓储（菜单 / 表单 / 菜单-表单 / 按钮 / 字段）、元数据快照服务与快照契约
（权限元数据域做权限聚合、角色域做授权校验时使用）。**本模块只做再导出**，不承载业务规则。
"""

from bms_core.models.platform.menu_form import (
    SysButton as SysButton,
)
from bms_core.models.platform.menu_form import (
    SysField as SysField,
)
from bms_core.models.platform.menu_form import (
    SysFieldI18n as SysFieldI18n,
)
from bms_core.models.platform.menu_form import (
    SysForm as SysForm,
)
from bms_core.models.platform.menu_form import (
    SysMenu as SysMenu,
)
from bms_core.models.platform.menu_form import (
    SysMenuForm as SysMenuForm,
)
from bms_core.models.platform.menu_form import (
    SysMenuI18n as SysMenuI18n,
)
from bms_platform.domains.menu_form.repositories.menu import (
    ButtonRepository as ButtonRepository,
)
from bms_platform.domains.menu_form.repositories.menu import (
    FieldRepository as FieldRepository,
)
from bms_platform.domains.menu_form.repositories.menu import (
    FormRepository as FormRepository,
)
from bms_platform.domains.menu_form.repositories.menu import (
    MenuFormRepository as MenuFormRepository,
)
from bms_platform.domains.menu_form.repositories.menu import (
    MenuRepository as MenuRepository,
)
from bms_platform.domains.menu_form.services.menu import (
    MenuFormService as MenuFormService,
)
from bms_platform.domains.menu_form.services.menu import (
    MenuSnapshot as MenuSnapshot,
)
from bms_platform.domains.menu_form.services.menu import (
    SnapshotButton as SnapshotButton,
)
from bms_platform.domains.menu_form.services.menu import (
    SnapshotField as SnapshotField,
)
from bms_platform.domains.menu_form.services.menu import (
    SnapshotForm as SnapshotForm,
)
from bms_platform.domains.menu_form.services.menu import (
    SnapshotMenu as SnapshotMenu,
)

__all__ = [
    "ButtonRepository",
    "FieldRepository",
    "FormRepository",
    "MenuFormRepository",
    "MenuFormService",
    "MenuRepository",
    "MenuSnapshot",
    "SnapshotButton",
    "SnapshotField",
    "SnapshotForm",
    "SnapshotMenu",
    "SysButton",
    "SysField",
    "SysFieldI18n",
    "SysForm",
    "SysMenu",
    "SysMenuForm",
    "SysMenuI18n",
]

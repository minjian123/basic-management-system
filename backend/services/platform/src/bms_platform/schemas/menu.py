"""平台服务 schemas 层：菜单与权限元数据请求 / 响应模型（继承 `BaseSchema`）。

覆盖：业务 / 动作权限码（只读）、菜单 / 表单 / 按钮 / 字段维护，以及动态菜单接口
（`GET /api/v1/menus/my`：菜单树 + 表单元数据 + 权限码集合）的嵌套契约。

集合字段一律 `Annotated[集合类, CONTRACT_COLLECTION]`（出口经基座规整为内置容器）。
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)

I18nNames = Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION]
"""多语言名称映射（locale → 文案）。"""

EnabledStatus = Literal["enabled", "disabled"]
"""启用状态取值。"""

ButtonType = Literal["toolbar", "interface"]
"""按钮形态取值。"""


# --------------------------------------------------------------------------- 请求


class MenuCreateRequest(BaseSchema):
    """新增菜单请求（含 i18n 名称）。"""

    parent_id: int = Field(default=0, ge=0, description="父菜单 ID（0 为根）")
    name: str = Field(min_length=1, max_length=128, description="菜单名（默认文案）")
    path: str = Field(min_length=1, max_length=255, description="前端路由路径（/ 开头）")
    component: str | None = Field(default=None, max_length=255, description="视图组件标识（可空 = 目录节点）")
    icon: str | None = Field(default=None, max_length=64, description="完整 icon key")
    sort: int = Field(default=0, description="同级排序（升序）")
    hidden: bool = Field(default=False, description="仅隐藏侧栏入口（权限仍生效）")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(default_factory=CONTRACT_STABLE_DICT, description="多语言名称（locale → 文案）")


class MenuUpdateRequest(BaseSchema):
    """更新菜单请求（整体替换）。"""

    parent_id: int = Field(ge=0, description="父菜单 ID（0 为根）")
    name: str = Field(min_length=1, max_length=128, description="菜单名（默认文案）")
    path: str = Field(min_length=1, max_length=255, description="前端路由路径（/ 开头）")
    component: str | None = Field(default=None, max_length=255, description="视图组件标识")
    icon: str | None = Field(default=None, max_length=64, description="完整 icon key")
    sort: int = Field(default=0, description="同级排序（升序）")
    hidden: bool = Field(default=False, description="仅隐藏侧栏入口")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(default_factory=CONTRACT_STABLE_DICT, description="多语言名称（locale → 文案）")


class FormCreateRequest(BaseSchema):
    """新增表单请求（挂菜单 / 挂业务）。"""

    menu_id: int = Field(gt=0, description="所属菜单 ID")
    business_id: int = Field(gt=0, description="所属业务码 ID")
    component: str | None = Field(default=None, max_length=255, description="表单视图组件标识")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")


class FormUpdateRequest(BaseSchema):
    """更新表单请求。"""

    business_id: int = Field(gt=0, description="所属业务码 ID")
    component: str | None = Field(default=None, max_length=255, description="表单视图组件标识")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")


class ButtonCreateRequest(BaseSchema):
    """新增按钮请求（挂表单 / 挂动作）。"""

    form_id: int = Field(gt=0, description="所属表单 ID")
    action_id: int = Field(gt=0, description="挂接动作码 ID")
    name: str = Field(min_length=1, max_length=128, description="按钮名（界面可见文本）")
    type: ButtonType = Field(default="toolbar", description="按钮形态（toolbar/interface）")
    sort: int = Field(default=0, description="同表内排序（升序）")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")


class ButtonUpdateRequest(BaseSchema):
    """更新按钮请求。"""

    action_id: int = Field(gt=0, description="挂接动作码 ID")
    name: str = Field(min_length=1, max_length=128, description="按钮名")
    type: ButtonType = Field(default="toolbar", description="按钮形态（toolbar/interface）")
    sort: int = Field(default=0, description="同表内排序（升序）")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")


class FieldCreateRequest(BaseSchema):
    """新增字段请求。"""

    form_id: int = Field(gt=0, description="所属表单 ID")
    field_key: str = Field(min_length=1, max_length=64, description="字段键（表单内唯一）")
    name: str = Field(min_length=1, max_length=128, description="字段名（默认文案）")
    type: str = Field(min_length=1, max_length=32, description="字段类型（组件语义键）")
    sort: int = Field(default=0, description="同表内排序（升序）")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(default_factory=CONTRACT_STABLE_DICT, description="多语言名称（locale → 文案）")


class FieldUpdateRequest(BaseSchema):
    """更新字段请求。"""

    name: str = Field(min_length=1, max_length=128, description="字段名（默认文案）")
    type: str = Field(min_length=1, max_length=32, description="字段类型（组件语义键）")
    sort: int = Field(default=0, description="同表内排序（升序）")
    status: EnabledStatus = Field(default="enabled", description="状态（enabled/disabled）")
    i18n: I18nNames = Field(default_factory=CONTRACT_STABLE_DICT, description="多语言名称（locale → 文案）")


# --------------------------------------------------------------------------- 元数据响应


class MenuItem(BaseSchema):
    """菜单节点（平台维护视图，树形嵌套）。"""

    id: int = Field(description="菜单主键（雪花 ID，JSON 以字符串输出）")
    parent_id: int = Field(description="父菜单 ID（0 为根）")
    name: str = Field(description="菜单名（默认文案）")
    path: str = Field(description="前端路由路径")
    component: str | None = Field(description="视图组件标识")
    icon: str | None = Field(description="完整 icon key")
    sort: int = Field(description="同级排序")
    hidden: bool = Field(description="仅隐藏侧栏入口")
    status: str = Field(description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")
    children: Annotated[ConcurrentStableList[MenuItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="子菜单（树形）"
    )


class MenuTree(BaseSchema):
    """菜单树（平台维护视图）。"""

    items: Annotated[ConcurrentStableList[MenuItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="根级菜单（子节点嵌套）"
    )


class FormItem(BaseSchema):
    """表单行。"""

    id: int = Field(description="表单主键")
    menu_id: int = Field(description="所属菜单 ID")
    business_id: int = Field(description="所属业务码 ID")
    component: str | None = Field(description="表单视图组件标识")
    status: str = Field(description="状态（enabled/disabled）")
    created_at: datetime = Field(description="创建时间（UTC）")
    updated_at: datetime = Field(description="更新时间（UTC）")


class FormList(BaseSchema):
    """表单清单。"""

    items: Annotated[ConcurrentStableList[FormItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="表单行列表"
    )


class ButtonItem(BaseSchema):
    """按钮行。"""

    id: int = Field(description="按钮主键")
    form_id: int = Field(description="所属表单 ID")
    action_id: int = Field(description="挂接动作码 ID")
    name: str = Field(description="按钮名")
    type: str = Field(description="按钮形态（toolbar/interface）")
    sort: int = Field(description="同表内排序")
    status: str = Field(description="状态（enabled/disabled）")


class ButtonList(BaseSchema):
    """按钮清单。"""

    items: Annotated[ConcurrentStableList[ButtonItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="按钮行列表"
    )


class FieldItem(BaseSchema):
    """字段行。"""

    id: int = Field(description="字段主键")
    form_id: int = Field(description="所属表单 ID")
    field_key: str = Field(description="字段键（表单内唯一）")
    name: str = Field(description="字段名（默认文案）")
    type: str = Field(description="字段类型（组件语义键）")
    sort: int = Field(description="同表内排序")
    status: str = Field(description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")


class FieldList(BaseSchema):
    """字段清单。"""

    items: Annotated[ConcurrentStableList[FieldItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段行列表"
    )


class BusinessItem(BaseSchema):
    """业务权限码行。"""

    id: int = Field(description="业务码主键")
    code: str = Field(description="业务权限码")
    name: str = Field(description="名称（默认文案）")
    status: str = Field(description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")


class BusinessList(BaseSchema):
    """业务权限码清单。"""

    items: Annotated[ConcurrentStableList[BusinessItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="业务码行列表"
    )


class ActionItem(BaseSchema):
    """动作权限码行。"""

    id: int = Field(description="动作码主键")
    code: str = Field(description="动作码")
    name: str = Field(description="名称（默认文案）")
    business_id: int = Field(description="归属业务码 ID")
    status: str = Field(description="状态（enabled/disabled）")
    i18n: I18nNames = Field(description="多语言名称（locale → 文案）")


class ActionList(BaseSchema):
    """动作权限码清单。"""

    items: Annotated[ConcurrentStableList[ActionItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="动作码行列表"
    )


# --------------------------------------------------------------------------- 动态菜单


class MyMenuButton(BaseSchema):
    """动态菜单下的按钮元数据（按动作权限标记可见）。"""

    id: int = Field(description="按钮主键")
    action_id: int = Field(description="挂接动作码 ID")
    action_code: str = Field(description="动作权限码（{业务码}:{动作码}）")
    name: str = Field(description="按钮名")
    type: str = Field(description="按钮形态（toolbar/interface）")
    sort: int = Field(description="同表内排序")
    visible: bool = Field(description="当前用户是否持有该动作权限")


class MyMenuField(BaseSchema):
    """动态菜单下的字段元数据（按字段权限标记可见 / 可编辑）。"""

    id: int = Field(description="字段主键")
    field_key: str = Field(description="字段键")
    name: str = Field(description="字段名（按 locale 本地化，缺省回退默认文案）")
    type: str = Field(description="字段类型（组件语义键）")
    sort: int = Field(description="同表内排序")
    visible: bool = Field(description="字段是否可见")
    editable: bool = Field(description="字段是否可编辑")


class MyMenuForm(BaseSchema):
    """动态菜单下的表单元数据。"""

    id: int = Field(description="表单主键")
    menu_id: int = Field(description="所属菜单 ID")
    business_id: int = Field(description="所属业务码 ID")
    business_code: str = Field(description="业务权限码")
    component: str | None = Field(description="表单视图组件标识")
    buttons: Annotated[ConcurrentStableList[MyMenuButton], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="按钮元数据（按动作权限标记）"
    )
    fields: Annotated[ConcurrentStableList[MyMenuField], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段元数据（按字段权限标记）"
    )


class MyMenuNode(BaseSchema):
    """动态菜单节点（过滤后菜单树，含表单元数据）。"""

    id: int = Field(description="菜单主键")
    parent_id: int = Field(description="父菜单 ID（0 为根）")
    name: str = Field(description="菜单名（按 locale 本地化，缺省回退默认文案）")
    path: str = Field(description="前端路由路径")
    component: str | None = Field(description="视图组件标识")
    icon: str | None = Field(description="完整 icon key")
    sort: int = Field(description="同级排序")
    hidden: bool = Field(description="仅隐藏侧栏入口（路由可直达）")
    form: MyMenuForm | None = Field(description="表单元数据（挂接链完整时非空）")
    children: Annotated[ConcurrentStableList[MyMenuNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="子菜单（树形）"
    )


class MyMenuResponse(BaseSchema):
    """动态菜单响应：菜单树 + 表单元数据 + 当前用户权限码集合。"""

    locale: str = Field(description="解析后的语言标识")
    version: int = Field(description="元数据版本号（缓存版本）")
    permissions: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="当前用户权限码集合（业务码 + 动作码）"
    )
    menus: Annotated[ConcurrentStableList[MyMenuNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="过滤后的菜单树（子节点嵌套）"
    )


MenuItem.model_rebuild()
MyMenuNode.model_rebuild()

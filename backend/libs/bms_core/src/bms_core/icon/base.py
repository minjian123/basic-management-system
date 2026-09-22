"""自定义图标能力域：图标注册表契约、图标键助手与依赖注入提供者（真实落库与清洗随对应阶段回补）。

- 取值集合：来源前缀 `ICON_SOURCES`（平台官方 / 业务自绘 / 租户自定义 / 移动端）、状态
  `ICON_STATUSES`（启用 / 停用）。
- 口径常量：图标键长度上限 `ICON_CODE_MAX_LENGTH`、名称上限 `ICON_NAME_MAX_LENGTH`、
  SVG 内容字节上限 `ICON_SVG_MAX_BYTES`、缺省状态 `DEFAULT_ICON_STATUS`、来源分隔与占位标识前缀。
- 图标键：`build_icon_key`（`{来源}:{图标键}`，本域来源恒为 `custom`）——前端 icon key 一律由基座派生，
  业务与前端不得自拼前缀；`is_valid_icon_code` 校验图标键 kebab-case 规范与长度上限。
- 数据契约：`IconDraft`（新增入参）/ `IconPatch`（更新入参，全字段可选）/ `IconInfo`（图标定义）。
- `BaseIconRegistry`（`key = plugin_key = "icon_registry"`）：异步 `list` / `get` / `create` / `update` /
  `delete`——租户自定义图标清单维护；删除的引用检查（被菜单 / 卡片引用则不可删）归消费方实现。
- 提供者 `get_icon_registry`（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：图标键为**契约唯一业务标识**（响应中的标识为字符串化主键，仅作归档关联、不用于定位）；分组为开放
字符串、标签供搜索；SVG 存内联内容（类型 / 大小校验与内容清洗归文件管理阶段）；平台官方与业务自绘图标随
代码发布、不落本域表。真实落库 CRUD、清单缓存与引用检查随通用能力与菜单管理阶段回补。
"""

import re
from abc import ABC, abstractmethod
from typing import cast

from fastapi import Request
from pydantic import Field

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_ICON_STATUS",
    "ICON_CODE_MAX_LENGTH",
    "ICON_CUSTOM_SOURCE",
    "ICON_KEY_SEPARATOR",
    "ICON_NAME_MAX_LENGTH",
    "ICON_SOURCES",
    "ICON_STATUSES",
    "ICON_SVG_MAX_BYTES",
    "NULL_ICON_ID_PREFIX",
    "BaseIconRegistry",
    "IconDraft",
    "IconInfo",
    "IconPatch",
    "build_icon_key",
    "get_icon_registry",
    "is_valid_icon_code",
]

ICON_SOURCES: tuple[str, ...] = ("el", "biz", "custom", "van")
"""图标来源前缀取值集合（平台官方 / 业务自绘 / 租户自定义 / 移动端，对齐前端图标 key 口径）。"""

ICON_CUSTOM_SOURCE = "custom"
"""租户自定义图标来源前缀（本域承载的唯一来源）。"""

ICON_KEY_SEPARATOR = ":"
"""图标键前缀分隔符（`{来源}:{图标键}`）。"""

ICON_STATUSES: tuple[str, ...] = ("active", "disabled")
"""图标状态取值集合（启用 / 停用）。"""

DEFAULT_ICON_STATUS = "active"
"""缺省图标状态（新增默认启用）。"""

ICON_CODE_MAX_LENGTH = 64
"""图标键长度上限（字符）。"""

ICON_NAME_MAX_LENGTH = 128
"""图标名称长度上限（字符）。"""

ICON_SVG_MAX_BYTES = 102400
"""SVG 内容字节上限（100KB，对齐前端上传要求；清洗与校验随文件管理阶段）。"""

NULL_ICON_ID_PREFIX = "null-"
"""占位图标标识前缀（占位实现由图标键派生，逐键唯一且便于断言）。"""

_ICON_CODE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
"""图标键规范：首段字母开头、段间单连字符、全小写字母数字（如 `purchase-order`）。"""


def is_valid_icon_code(code: str) -> bool:
    """校验图标键是否符合 kebab-case 规范与长度上限。

    Args:
        code: 图标键。

    Returns:
        bool: 合法为 True。
    """
    if not code or len(code) > ICON_CODE_MAX_LENGTH:
        return False
    return bool(_ICON_CODE_RE.fullmatch(code))


def build_icon_key(code: str, *, source: str = ICON_CUSTOM_SOURCE) -> str:
    """派生图标键（格式 `{来源}:{图标键}`）。

    Args:
        code: 图标键（kebab-case，租户内唯一）。
        source: 图标来源前缀（缺省租户自定义；业务与前端不得自拼前缀）。

    Returns:
        str: 完整 icon key（前端落库到菜单 / 卡片配置的值）。
    """
    return f"{source}{ICON_KEY_SEPARATOR}{code}"


class IconDraft(BaseSchema):
    """图标新增入参（图标键 / 名称 / 分组 / 标签 / SVG 内容）。"""

    code: str = Field(max_length=ICON_CODE_MAX_LENGTH, description="图标键（kebab-case，租户内唯一）")
    name: str = Field(max_length=ICON_NAME_MAX_LENGTH, description="图标名称（默认文案）")
    category: str = Field(description="图标分组（分类）")
    tags: list[str] = Field(default_factory=list[str], description="标签（搜索用）")
    svg: str = Field(description="SVG 内容（内联；类型 / 大小校验与清洗随文件管理阶段）")


class IconPatch(BaseSchema):
    """图标更新入参（全字段可选；None 表示该项不变）。"""

    name: str | None = Field(default=None, max_length=ICON_NAME_MAX_LENGTH, description="图标名称")
    category: str | None = Field(default=None, description="图标分组")
    tags: list[str] | None = Field(default=None, description="标签（搜索用）")
    svg: str | None = Field(default=None, description="SVG 内容")
    status: str | None = Field(default=None, description="状态（active 启用 / disabled 停用）")


class IconInfo(BaseSchema):
    """图标定义（图标键为业务标识；`icon_key` 为派生值，前端直接落库）。"""

    id: str = Field(description="图标标识（字符串化主键；非业务标识，不用于定位）")
    code: str = Field(description="图标键（契约唯一业务标识）")
    name: str = Field(description="图标名称")
    category: str = Field(description="图标分组")
    tags: list[str] = Field(default_factory=list[str], description="标签（搜索用）")
    svg: str = Field(description="SVG 内容")
    status: str = Field(default=DEFAULT_ICON_STATUS, description="状态（active 启用 / disabled 停用）")
    icon_key: str = Field(description="图标键派生值（custom:{图标键}，经 build_icon_key 派生）")


class BaseIconRegistry(BasePluggable, ABC):
    """图标注册表契约：租户自定义图标清单维护（真实落库 CRUD 随通用能力阶段）。"""

    key: str = "icon_registry"
    plugin_key: str = "icon_registry"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def list(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> list[IconInfo]:
        """取图标清单（可按分组 / 状态过滤，关键字匹配图标键 / 名称 / 标签）。

        Args:
            category: 图标分组（None 表示全部）。
            status: 图标状态（None 表示全部）。
            keyword: 关键字（None 表示不过滤）。

        Returns:
            list[IconInfo]: 图标清单（占位为空清单，消费方以空态回退）。
        """

    @abstractmethod
    async def get(self, code: str) -> IconInfo:
        """取单图标定义。

        Args:
            code: 图标键。

        Returns:
            IconInfo: 图标定义。

        Raises:
            NotFoundError: 图标键未命中（10002 / 404）。
        """

    @abstractmethod
    async def create(self, draft: IconDraft) -> IconInfo:
        """新增图标（图标键租户内唯一）。

        Args:
            draft: 新增入参（图标键 / 名称 / 分组 / 标签 / SVG 内容）。

        Returns:
            IconInfo: 新增后的图标定义。

        Raises:
            ConflictError: 图标键重复（10003）。
        """

    @abstractmethod
    async def update(self, code: str, patch: IconPatch) -> IconInfo:
        """更新图标（按图标键定位；未提供字段保持不变）。

        Args:
            code: 图标键。
            patch: 更新入参（全字段可选）。

        Returns:
            IconInfo: 更新后的图标定义。

        Raises:
            NotFoundError: 图标键未命中（10002 / 404）。
        """

    @abstractmethod
    async def delete(self, code: str) -> bool:
        """删除图标（引用检查在实现侧：被菜单 / 卡片引用时拒绝并提示先停用）。

        Args:
            code: 图标键。

        Returns:
            bool: 是否删除了既有图标。
        """


def get_icon_registry(request: Request) -> BaseIconRegistry:
    """取应用级图标注册表（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseIconRegistry: 应用装配的图标注册表实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseIconRegistry",
        resolve_plugin(
            "icon_registry",
            settings.icon_registry.provider,
            expected_version=BaseIconRegistry.contract_version,
        ),
    )

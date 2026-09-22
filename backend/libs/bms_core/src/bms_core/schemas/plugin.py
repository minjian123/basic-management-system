"""schemas 层插件清单契约：插件注册实现与能力分组响应。"""

from typing import Literal

from bms_core.schemas.base import BaseSchema


class PluginImplementationResponse(BaseSchema):
    """单个注册实现（清单条目）。"""

    plugin_name: str
    """实现名（如 `local` / `null`）。"""

    contract_version: str
    """契约版本：类实现读类属性；工厂 / 结构化实现报端口契约版本。"""

    status: Literal["active", "registered"]
    """状态：当前选中 `active`；其余已注册 `registered`。"""


class PluginGroupResponse(BaseSchema):
    """按能力分组的插件清单（`plugin_key` 维度）。"""

    plugin_key: str
    """能力域键（注册表键）。"""

    provider: str
    """当前配置选中的实现名（空配置 → `null`）。"""

    implementations: list[PluginImplementationResponse]
    """已注册实现（`plugin_name` 升序）；不含 `options` 密钥。"""

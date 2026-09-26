"""schemas 层插件清单契约：插件注册实现、能力分组与跨服务聚合响应。"""

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


class PluginAggregateServiceResponse(BaseSchema):
    """跨服务插件聚合视图的单个服务条目。"""

    service_key: str
    """服务标识（服务目录启用服务）。"""

    service_title: str
    """服务显示名（服务目录登记）。"""

    status: Literal["ok", "unreachable"]
    """取数结果：`ok` 可调用；`unreachable` 调用失败（条目保留、组为空，不使整请求失败）。"""

    groups: list[PluginGroupResponse]
    """该服务插件清单分组（复用清单契约）；不含 `options` 密钥。"""


class PluginAggregateResponse(BaseSchema):
    """跨服务插件聚合视图（平台超管统一查看面）。"""

    placeholder: bool
    """占位标记：触发前恒 `true`（`services` 为空）；真实实现接入后置 `false`。"""

    services: list[PluginAggregateServiceResponse]
    """各启用服务的插件清单聚合（`service_key` 升序）。"""

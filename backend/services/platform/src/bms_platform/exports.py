"""平台导出定义装配（服务根，`shared_paths`）：登记 users / roles 导出定义。

**为什么在服务根**：导出域不能直接 import 用户 / 角色域实现（D1），定义本身在各自域内，由本装配面
统一登记。API 与异步作业 worker 共用同一装配函数，保证「同一定义、同一取数」。
"""

from __future__ import annotations

from bms_core.transfer.export_definition import ExportDefinitionRegistry
from bms_platform.domains.role.exports import RolesExportDefinition
from bms_platform.domains.user.exports import UsersExportDefinition

__all__ = ["build_export_definitions"]


def build_export_definitions() -> ExportDefinitionRegistry:
    """构造平台首批导出定义（users / roles）。

    Returns:
        ExportDefinitionRegistry: 已登记 users / roles 的注册表。
    """
    registry = ExportDefinitionRegistry()
    registry.register(UsersExportDefinition())
    registry.register(RolesExportDefinition())
    return registry

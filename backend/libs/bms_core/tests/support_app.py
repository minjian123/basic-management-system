"""基座测试支撑：最小测试服务应用工厂（无业务路由），供共享能力域测试构造应用与探针。

共享能力域实现留 `bms_core`，其测试不依赖具体服务；本模块提供等价于服务应用工厂的测试应用，
使原经 `bms_platform.main` 构造应用的契约测试可迁入基座测试并保持断言不变。

**权限 / 数据范围强制占位**：`get_settings()` 是进程级单例，服务套件（platform / identity）在
`prepare_settings` 里会把它改成 `provider = rbac`；同进程跑基座用例时若沿用该残留，基座测试应用
（不登记任何数据来源）会在装配期按「`rbac` 却无取数实现」拒绝启动。故本工厂显式把两个能力置回
**占位实现**——基座测试应用本就不接入真实 RBAC，这样用例结果与套件执行顺序无关。

**豁免数据来源兜底**：插件注册表里已登记的工厂（如 `masking:default`）会持有**构造时的 settings
快照**；同进程先跑过服务套件时，它可能仍按 `rbac` 解析权限校验器。故本工厂另登记一个「豁免主体」
数据来源（系统管理员层级，判定恒真，与占位实现行为等价），使 `rbac` 被解析到时也能正常装配。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bms_core.application import BaseServiceApplicationFactory, service_lifespan
from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.config import Settings, get_settings
from bms_core.permission.sources import (
    BasePermissionDataSource,
    PermissionMetadata,
    PermissionSubjectData,
    register_permission_data_source,
    register_permission_data_source_factory,
)

EXEMPT_ROLE_ID = 1
"""豁免主体角色主键（测试替身固定值）。"""

EXEMPT_DATA_SOURCE_KEY = "core_test_exempt_source"
"""基座测试用豁免数据来源标识。"""


class ExemptPermissionDataSource(BasePermissionDataSource):
    """豁免主体数据来源替身（系统管理员角色类型 → 校验恒真，与占位实现行为等价）。"""

    key: str = EXEMPT_DATA_SOURCE_KEY

    async def load_subject(self, *, user_id: int) -> PermissionSubjectData:
        """返回系统管理员角色的聚合输入。

        Args:
            user_id: 用户主键（忽略）。

        Returns:
            PermissionSubjectData: 聚合输入。
        """
        del user_id
        data = PermissionSubjectData(role_ids=ConcurrentStableSet([EXEMPT_ROLE_ID]))
        data.role_types.set(EXEMPT_ROLE_ID, "system")
        return data

    async def load_metadata(self, *, locale: str = "zh-CN") -> PermissionMetadata:
        """返回空元数据。

        Args:
            locale: 语言标识（忽略）。

        Returns:
            PermissionMetadata: 空元数据。
        """
        del locale
        return PermissionMetadata()


class ApplicationFactory(BaseServiceApplicationFactory):
    """基座测试用应用工厂（无业务路由，装配全部内建插件）。"""

    key: str = "application_factory"
    service_name: str = "core_test"
    service_title: str = "BMS 基座测试服务"
    version: str = "0.1.0"

    def prepare_settings(self, settings: Settings) -> None:
        """强制权限与数据范围回落占位实现（免受其他套件对全局配置的单例改动影响）。

        Args:
            settings: 应用配置（可变）。
        """
        _force_placeholder_permission(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """测试用 lifespan（转调共享 `service_lifespan`，兼容 `async with lifespan(app)` 用法）。

    `service_lifespan` 取的是**进程级单例** `get_settings()`；同进程先跑过服务套件时，此处再兜一次
    占位实现并登记豁免来源，确保基座测试应用始终可装配。

    Args:
        app: 应用实例。

    Yields:
        None: 应用运行期。
    """
    _force_placeholder_permission(get_settings())
    register_permission_data_source(ExemptPermissionDataSource())
    register_permission_data_source_factory(EXEMPT_DATA_SOURCE_KEY, _build_exempt_source)
    async with service_lifespan(app):
        yield


async def _build_exempt_source(request: object) -> ExemptPermissionDataSource:
    """豁免数据来源的请求级工厂（与真实服务工厂同签名，供请求态装配路径使用）。

    Args:
        request: 当前请求（忽略）。

    Returns:
        ExemptPermissionDataSource: 豁免来源。
    """
    del request
    return ExemptPermissionDataSource()


def _force_placeholder_permission(settings: Settings) -> None:
    """把权限与数据范围能力置回占位实现（基座测试应用不接入真实 RBAC）。

    Args:
        settings: 应用配置（可变）。
    """
    settings.permission.provider = ""
    settings.data_scope.provider = ""

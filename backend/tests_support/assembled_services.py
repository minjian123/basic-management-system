"""全系统装配的服务工厂映射（13_10）。

服务键以 `SERVICE_CATALOG` 为唯一来源；本模块只负责「键 → 应用工厂」的接线，
不复制清单内容。装配容器（`bms_core.testing.system.AssembledSystem`）由测试插件在
初始化之后调用一次。
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenSet
from bms_core.services.module_registry import SERVICE_CATALOG

_MODULE_BY_SERVICE: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "platform": "bms_platform.main",
        "identity": "bms_identity.main",
        "tenant": "bms_tenant.main",
        "txn": "bms_txn.main",
        "ai": "bms_ai.main",
        "file": "bms_file.main",
        "notification": "bms_notification.main",
        "report": "bms_report.main",
        "search": "bms_search.main",
    }
)
"""服务键 → 应用工厂模块（`bms_<服务>.main:ApplicationFactory`）。"""

PLATFORM_HOSTED_SERVICES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet({"workflow"})
"""由 platform 进程承载、无独立服务进程的服务键（装配阶段不需要单独启动）。"""


def _factory(module_name: str) -> Callable[[], FastAPI]:
    """构造服务应用工厂（延迟导入，避免装配前拉入全部服务）。

    Args:
        module_name: 工厂模块名（如 `bms_platform.main`）。

    Returns:
        Callable[[], FastAPI]: 零参工厂（返回未进入 lifespan 的应用）。
    """

    def create() -> FastAPI:
        module = importlib.import_module(module_name)
        factory = module.ApplicationFactory
        return factory().create(None)

    return create


def service_factories() -> ConcurrentStableDict[str, Callable[[], FastAPI]]:
    """按服务目录顺序给出全部服务工厂（只含本仓后端服务）。

    Returns:
        ConcurrentStableDict[str, Callable[[], FastAPI]]: 服务键 → 工厂（插入序）。

    Raises:
        RuntimeError: 服务目录出现未登记工厂的服务（新增服务必须同步接线）。
    """
    factories: ConcurrentStableDict[str, Callable[[], FastAPI]] = ConcurrentStableDict()
    for record in SERVICE_CATALOG:
        service_key = record.service_key
        if not service_key:
            continue
        if service_key in PLATFORM_HOSTED_SERVICES:
            continue
        module_name = _MODULE_BY_SERVICE.get(service_key)
        if module_name is None:
            raise RuntimeError(f"服务目录新增了未接线工厂的服务：{service_key}")
        factories[service_key] = _factory(module_name)
    return factories

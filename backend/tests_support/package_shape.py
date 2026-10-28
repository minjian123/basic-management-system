"""服务包形态护栏：域公共出口可导入、模型模块清单可解析。

07C「业务域分包」给每个域一个 `public.py` 作为唯一跨域引用面（D2），`models/__init__.py` 声明
`MODEL_MODULES` 供迁移链解析模型。这两类模块都是**纯声明**、不承载运行期逻辑，业务用例通常不会
触达；单服务跑覆盖率门禁时即整模块计为未覆盖（2026-10-28 `service-test` 实测，9 个服务全挂）。

本模块把「遍历域 / 解析清单」的实现收在一处，服务侧测试只写两三行断言，避免每个服务各写一份。
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.migration import service_model_modules


def domain_exports(package: str) -> ConcurrentStableDict[str, ModuleType]:
    """导入并返回包下全部域公共出口（`<package>.domains.<域>.public`）。

    Args:
        package: 服务包名（如 `bms_file`）。

    Returns:
        ConcurrentStableDict[str, ModuleType]: 模块全名 → 已导入模块（按域名字典序）。

    Raises:
        ModuleNotFoundError: 某域缺 `public.py`（D2 要求每域一个出口）。
    """
    domains = importlib.import_module(f"{package}.domains")
    exports: ConcurrentStableDict[str, ModuleType] = ConcurrentStableDict()
    for info in sorted(pkgutil.iter_modules(domains.__path__), key=lambda item: item.name):
        if not info.ispkg:
            continue
        name = f"{package}.domains.{info.name}.public"
        exports.set(name, importlib.import_module(name))
    return exports


def model_modules(service: str) -> ConcurrentStableList[str]:
    """按迁移链同一入口解析服务私有模型模块清单，并把每个声明模块导入一遍。

    入口是 `bms_core.db.migration.service_model_modules`（迁移与开发库建表都用它），因此这里
    同时验证「`models` 子包已声明 `MODEL_MODULES`」与「清单里的模块真实可导入」。

    Args:
        service: 服务标识（如 `file`；包名由 `service_package` 按前缀推出）。

    Returns:
        ConcurrentStableList[str]: 模型模块全名（无私有模型为空清单）。
    """
    names = ConcurrentStableList(service_model_modules(service))
    for name in names:
        importlib.import_module(name)
    return names

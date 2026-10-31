"""执行体登记与解析（handler 白名单：防任务定义写入任意代码路径）。

- `builtin_handlers()`：任务代码 → 点分路径（`module:attr`），唯一来源是内置任务清单；
- `is_allowed_handler()`：**不导入**的静态判定（格式 + 模块前缀白名单），供创建 / 更新任务的接口校验；
- `resolve_handler()`：执行前解析成可调用对象，解析前再做一次白名单校验（防历史脏数据）。

白名单口径：模块名必须**等于**某个允许前缀，或以「前缀 + `.`」开头——避免
`bms_core.tasks.builtinx` 这类前缀撞名。前缀来源为 `[task_scheduler].allowed_handler_prefixes`。
"""

from __future__ import annotations

from importlib import import_module

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TaskHandlerNotRegisteredError
from bms_core.tasks.builtin import BUILTIN_TASK_SPECS
from bms_core.tasks.spec import TaskHandler

__all__ = ["builtin_handlers", "is_allowed_handler", "resolve_handler"]

_SEPARATOR = ":"
"""点分路径分隔符（`module:attr`）。"""


def builtin_handlers() -> ConcurrentStableDict[str, str]:
    """内置 handler 注册表（任务代码 → 点分路径）。

    Returns:
        ConcurrentStableDict[str, str]: 注册表（代码 → `module:attr`）。
    """
    return ConcurrentStableDict({spec.code: spec.handler for spec in BUILTIN_TASK_SPECS})


def _split_handler(path: str) -> tuple[str, str]:
    """拆分点分路径为（模块, 属性）。

    Args:
        path: 点分路径（`module:attr`）。

    Returns:
        tuple[str, str]: 模块名与属性名。

    Raises:
        TaskHandlerNotRegisteredError: 格式非法（`70003`）。
    """
    module, _, attr = path.partition(_SEPARATOR)
    if not module or not attr or _SEPARATOR in attr or not module.replace(".", "").replace("_", "").isalnum():
        raise TaskHandlerNotRegisteredError(f"handler 须为 `module:attr` 形式：{path}")
    return module, attr


def is_allowed_handler(path: str, allowed_prefixes: ConcurrentStableList[str]) -> bool:
    """静态判定 handler 是否在白名单内（不导入模块）。

    Args:
        path: 点分路径（`module:attr`）。
        allowed_prefixes: 允许的模块前缀清单。

    Returns:
        bool: 允许 True；格式非法 / 前缀越界 False。
    """
    try:
        module, _ = _split_handler(path)
    except TaskHandlerNotRegisteredError:
        return False
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in allowed_prefixes)


def resolve_handler(path: str, allowed_prefixes: ConcurrentStableList[str]) -> TaskHandler:
    """解析执行体（导入 + 白名单校验 + 可调用校验）。

    Args:
        path: 点分路径（`module:attr`）。
        allowed_prefixes: 允许的模块前缀清单。

    Returns:
        TaskHandler: 可调用执行体。

    Raises:
        TaskHandlerNotRegisteredError: 前缀越界 / 模块不可导入 / 属性缺失或不可调用（`70003`）。
    """
    if not is_allowed_handler(path, allowed_prefixes):
        raise TaskHandlerNotRegisteredError(f"handler 不在白名单内：{path}")
    module_name, attr = _split_handler(path)
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise TaskHandlerNotRegisteredError(f"handler 模块不可导入：{module_name}") from exc
    target = getattr(module, attr, None)
    if target is None or not callable(target):
        raise TaskHandlerNotRegisteredError(f"handler 属性不可调用：{path}")
    return target  # pyright: ignore[reportReturnType] - 运行时按 callable 校验，鸭子类型

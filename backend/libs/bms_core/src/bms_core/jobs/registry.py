"""作业处理器注册表：本服务 handler 装载、解析与声明对账。

- **代码侧唯一登记点**：每服务 `job_handlers()` 返回 `job_type → BaseJobHandler`，注册表校验
  类型唯一、继承 `BaseJobHandler`、`job_type` 与注册键一致；
- **声明对账**：平台装载期 / CI 用清单（`[[jobs]]`）与本服务注册表对账——声明缺代码或路径不符即拒，
  代码缺声明只告警（防漏声明，由 CI 兜底）；
- **隔离**：注册表只含本服务 handler，不跨服务导入；跨服务作业经内部端点提交。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import import_module

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import JobHandlerNotRegisteredError, JobTypeNotRegisteredError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.jobs.base import BaseJobHandler

__all__ = ["JobHandlerRegistry", "resolve_handler_path"]


def _split_handler_path(path: str) -> tuple[str, str]:
    """拆分 `module:attr` 点分路径。

    Args:
        path: 点分路径。

    Returns:
        tuple[str, str]: 模块名与属性名。

    Raises:
        JobHandlerNotRegisteredError: 格式非法（`71006`）。
    """
    module, _, attr = path.partition(":")
    if not module or not attr or ":" in attr:
        raise JobHandlerNotRegisteredError(f"handler 须为 `module:attr` 形式：{path}")
    return module, attr


def resolve_handler_path(path: str) -> BaseJobHandler:
    """按声明路径导入并实例化作业处理器。

    Args:
        path: `module:attr`（属性应为 `BaseJobHandler` 子类，或返回处理器的零参工厂）。

    Returns:
        BaseJobHandler: 处理器实例。

    Raises:
        JobHandlerNotRegisteredError: 模块不可导入 / 属性缺失 / 不可实例化 / 非 `BaseJobHandler`（`71006`）。
    """
    module_name, attr = _split_handler_path(path)
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise JobHandlerNotRegisteredError(f"作业 handler 模块不可导入：{module_name}") from exc
    target = getattr(module, attr, None)
    if target is None:
        raise JobHandlerNotRegisteredError(f"作业 handler 属性不存在：{path}")
    if isinstance(target, BaseJobHandler):
        return target
    if not callable(target):
        raise JobHandlerNotRegisteredError(f"作业 handler 属性不可调用：{path}")
    try:
        candidate = target()
    except Exception as exc:  # 构造失败属装配错误（不吞异常类型，转统一 71006）
        raise JobHandlerNotRegisteredError(f"作业 handler 无法实例化：{path}（{type(exc).__name__}）") from exc
    if not isinstance(candidate, BaseJobHandler):
        raise JobHandlerNotRegisteredError(f"作业 handler 未继承 BaseJobHandler：{path}")
    return candidate


class JobHandlerRegistry(BaseFrameworkObject):
    """本服务作业处理器注册表（装配期一次性装载，运行期只读）。"""

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._handlers: ConcurrentStableDict[str, BaseJobHandler] = ConcurrentStableDict()

    def load(self, handlers: Mapping[str, BaseJobHandler]) -> None:
        """装载处理器（校验类型唯一 / 继承基类 / 键与 `job_type` 一致）。

        Args:
            handlers: `job_type → handler`。

        Raises:
            JobHandlerNotRegisteredError: 非 `BaseJobHandler`、`job_type` 为空或与键不一致（`71006`）。
        """
        for job_type, handler in handlers.items():
            self.register(job_type, handler)

    def register(self, job_type: str, handler: BaseJobHandler) -> None:
        """登记单个处理器（重复登记同值幂等，异值拒绝）。

        Args:
            job_type: 作业类型（注册键）。
            handler: 处理器。

        Raises:
            JobHandlerNotRegisteredError: 非法处理器 / 类型不一致 / 重复登记（`71006`）。
        """
        if not job_type:
            raise JobHandlerNotRegisteredError("作业类型不得为空")
        if not isinstance(handler, BaseJobHandler):  # pyright: ignore[reportUnnecessaryIsInstance] - 运行期 duck typing 防护
            raise JobHandlerNotRegisteredError(f"handler 未继承 BaseJobHandler：{job_type}")
        if handler.job_type and handler.job_type != job_type:
            raise JobHandlerNotRegisteredError(f"handler.job_type（{handler.job_type}）与注册键（{job_type}）不一致")
        existing = self._handlers.get(job_type)
        if existing is not None and existing is not handler:
            raise JobHandlerNotRegisteredError(f"作业类型重复登记：{job_type}")
        self._handlers.set(job_type, handler)

    def get(self, job_type: str) -> BaseJobHandler:
        """取处理器。

        Args:
            job_type: 作业类型。

        Returns:
            BaseJobHandler: 处理器实例。

        Raises:
            JobTypeNotRegisteredError: 本服务未注册该类型（`71002`）。
        """
        handler = self._handlers.get(job_type)
        if handler is None:
            raise JobTypeNotRegisteredError(f"作业类型未在本服务注册：{job_type}")
        return handler

    def has(self, job_type: str) -> bool:
        """判断是否注册某作业类型。

        Args:
            job_type: 作业类型。

        Returns:
            bool: 已注册 True。
        """
        return job_type in self._handlers

    def job_types(self) -> ConcurrentStableSet[str]:
        """取已注册作业类型集合（插入序）。

        Returns:
            ConcurrentStableSet[str]: 作业类型集合。
        """
        return ConcurrentStableSet(self._handlers.keys())

    def handlers(self) -> ConcurrentStableDict[str, BaseJobHandler]:
        """取处理器映射副本（插入序）。

        Returns:
            ConcurrentStableDict[str, BaseJobHandler]: 处理器映射。
        """
        return ConcurrentStableDict(self._handlers)

    def reconcile(self, declared: Mapping[str, str]) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
        """与本服务声明对账（声明 = `job_type → handler 点分路径`）。

        Args:
            declared: 声明映射（取自 `[[jobs]]` 清单或 `sys_job_type` 本服务子集）。

        Returns:
            tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （阻断性错误, 告警）。
        """
        errors: ConcurrentStableList[str] = ConcurrentStableList()
        warnings: ConcurrentStableList[str] = ConcurrentStableList()
        declared_types = ConcurrentStableSet(declared.keys())
        for job_type, path in declared.items():
            handler = self._handlers.get(job_type)
            if handler is None:
                errors.add(f"声明存在但代码侧 handler 缺失：{job_type}（{path}）")
                continue
            actual = f"{type(handler).__module__}:{type(handler).__qualname__}"
            if path and path != actual:
                errors.add(f"声明 handler 路径与代码侧不一致：{job_type}（声明 {path}，代码 {actual}）")
        for job_type in self._handlers:
            if job_type not in declared_types:
                warnings.add(f"代码侧 handler 未在清单声明：{job_type}")
        return errors, warnings

    @classmethod
    def from_declarations(cls, declared: Iterable[tuple[str, str]]) -> JobHandlerRegistry:
        """按声明清单（`(job_type, path)`）导入并构造注册表。

        Args:
            declared: 声明序列。

        Returns:
            JobHandlerRegistry: 已装载的注册表。
        """
        registry = cls()
        for job_type, path in declared:
            registry.register(job_type, resolve_handler_path(path))
        return registry

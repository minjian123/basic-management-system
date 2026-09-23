"""数据所有权守卫真实实现：SQLAlchemy 执行前按**表级归属**检测跨服务库访问（06_03 口径）。

- 挂载点：SQLAlchemy `Engine` 类级 `before_cursor_execute` 事件——异步引擎底层同步引擎同属
  `Engine`，一处覆盖异步 / 同步方言 / 达梦同步门面。
- 模式：`off` 不解析；`warn` 记录 + 计数 + `warning` 日志；`enforce` 抛 `DataOwnershipError`（10008 / 500）。
- 计数：线程安全计数（触及 / 越界 / 阻断）经 `snapshot()` 暴露；命中时经 `metrics` 能力域上报
  `bms_boundary_cross_access_total`（缺省 null 时空操作）。
- 生命周期：`setup()` / `aclose()` 引用计数式安装 / 卸载监听；测试可显式 `install()` / `uninstall()`。
"""

import asyncio
import threading

from sqlalchemy import Engine, event
from sqlalchemy.engine import Connection

from bms_core.boundary.assess import OwnershipViolation, assess_statement
from bms_core.boundary.base import (
    BOUNDARY_METRIC_CROSS_ACCESS,
    DEFAULT_OWNERSHIP_MODE,
    OWNERSHIP_MODES,
    BaseDataOwnershipGuard,
    OwnershipStats,
)
from bms_core.boundary.exceptions import OwnershipException
from bms_core.core.exceptions import ConfigError, DataOwnershipError
from bms_core.core.logging import get_logger
from bms_core.metrics.base import BaseMetrics

__all__ = ["TableOwnershipGuard"]

_LOGGER = get_logger("bms")


class TableOwnershipGuard(BaseDataOwnershipGuard):
    """表级归属守卫（真实实现，插件名 `table`）。"""

    plugin_name: str = "table"

    def __init__(
        self,
        service: str,
        *,
        mode: str = DEFAULT_OWNERSHIP_MODE,
        exceptions: tuple[OwnershipException, ...] = (),
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            service: 当前服务标识（为空时不检测）。
            mode: 运行模式（`OWNERSHIP_MODES` 之一）。
            exceptions: 只读例外登记条目。
            metrics: 指标器（None 表示不上报）。

        Raises:
            ConfigError: 运行模式非法。
        """
        if mode not in OWNERSHIP_MODES:
            raise ConfigError(f"数据所有权运行模式非法：{mode!r}（允许 {'、'.join(OWNERSHIP_MODES)}）")
        self._service = service
        self._mode = mode
        self._exceptions = exceptions
        self._metrics = metrics
        self._lock = threading.Lock()
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._statements = 0
        self._violations = 0
        self._blocked = 0

    def assess(self, statement: str, *, service: str) -> tuple[OwnershipViolation, ...]:
        """判定语句是否越界访问他服务表。

        Args:
            statement: SQL 语句。
            service: 当前服务标识。

        Returns:
            tuple[OwnershipViolation, ...]: 越界项（无越界返回空元组）。
        """
        return assess_statement(statement, service=service, exceptions=self._exceptions)

    def snapshot(self) -> OwnershipStats:
        """取计数快照。

        Returns:
            OwnershipStats: 计数快照。
        """
        with self._lock:
            return OwnershipStats(statements=self._statements, violations=self._violations, blocked=self._blocked)

    async def setup(self) -> None:
        """装配钩子：安装 SQLAlchemy 监听。"""
        self.install()

    async def aclose(self) -> None:
        """释放钩子：卸载 SQLAlchemy 监听。"""
        self.uninstall()

    def install(self) -> None:
        """安装 `before_cursor_execute` 监听（幂等）。

        守卫为**进程级单例**（插件注册表缓存实例，生产单进程单应用）；重复安装 / 卸载按
        `event.contains` 幂等，不重复挂载。
        """
        if not event.contains(Engine, "before_cursor_execute", self._dispatch):
            event.listen(Engine, "before_cursor_execute", self._dispatch)

    def uninstall(self) -> None:
        """卸载监听（幂等）。"""
        if event.contains(Engine, "before_cursor_execute", self._dispatch):
            event.remove(Engine, "before_cursor_execute", self._dispatch)

    def _dispatch(
        self,
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        """SQL 执行前判定并处置越界（warn 记录计数 / enforce 抛错）。

        Args:
            conn: 数据库连接。
            cursor: 游标。
            statement: SQL 语句。
            parameters: 绑定参数。
            context: 执行上下文。
            executemany: 是否批量执行。

        Raises:
            DataOwnershipError: `enforce` 模式下命中越界（10008 / 500）。
        """
        if self._mode == "off" or not self._service:
            return
        del conn, cursor, parameters, context, executemany
        self._statements += 1
        try:
            violations = self.assess(statement, service=self._service)
        except Exception as exc:  # 解析异常绝不阻断数据库执行（守卫自身失败静默降级）
            _LOGGER.warning("data_ownership_assess_failed", error=repr(exc))
            return
        if not violations:
            return
        with self._lock:
            self._violations += len(violations)
        for violation in violations:
            self._report_metric(violation)
            _LOGGER.warning(
                "cross_service_access",
                service=violation.service,
                table=violation.table,
                prefix=violation.prefix,
                owner=violation.owner,
                operation=violation.operation,
                mode=self._mode,
            )
        if self._mode == "enforce":
            with self._lock:
                self._blocked += len(violations)
            first = violations[0]
            raise DataOwnershipError(f"跨服务库访问被拒：{first.service} 访问 {first.table}（归属 {first.owner}）")

    def _report_metric(self, violation: OwnershipViolation) -> None:
        """上报越界计数（有运行事件循环且配置了指标器时）。

        Args:
            violation: 越界项。
        """
        metrics = self._metrics
        if metrics is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        labels = {
            "service": violation.service,
            "prefix": violation.prefix,
            "owner": violation.owner,
            "operation": violation.operation,
        }
        task = loop.create_task(metrics.counter(BOUNDARY_METRIC_CROSS_ACCESS, labels=labels))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

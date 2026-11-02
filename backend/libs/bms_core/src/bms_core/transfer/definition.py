"""导入导出能力域 · 业务导入定义契约与注册表（04_01）。

- `BaseImportDefinition`：业务定义的最小面——业务标识 / 标题 / 列集 / 预检 / 单行写入。
- `ImportDefinitionRegistry`：进程内 `biz → 定义`（构建期登记、运行期只读；重名即拒）。
- `ImportRowContext`：编排传给定义的执行上下文（会话 / 工作单元 / 操作人 / 审计 / 配额 / 作业）。
- `ImportSummary`：执行汇总（全量原子语义：`committed` / `blocked_count`）。

口径：定义只依赖共享基座与**本域**写服务；跨域写经所有者域服务层（由服务根装配注入工厂），
不直接写他域表。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from bms_core.audit.base import AuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.base import JobContext
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.importer import ParsedRow, RowError

__all__ = [
    "BaseImportDefinition",
    "ImportBatchUnitOfWork",
    "ImportDefinitionRegistry",
    "ImportRowContext",
    "ImportSummary",
]

_BIZ_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
"""业务标识格式（路径段；小写字母开头）。"""


@dataclass(frozen=True)
class ImportSummary(BaseValueObject):
    """导入执行汇总（全量原子语义）。"""

    total: int
    """数据行数（跳过整行为空的行）。"""

    success_count: int
    """实际落库行数。"""

    fail_count: int
    """有错误的行数（按行去重）。"""

    blocked_count: int
    """合法但因整批拒绝未落库的行数。"""

    committed: bool
    """是否已落库。"""

    def to_output(self) -> ConcurrentStableDict[str, object]:
        """转作业结果摘要（落 `sys_job.result`）。

        Returns:
            ConcurrentStableDict[str, object]: 汇总字段。
        """
        return ConcurrentStableDict[str, object](
            {
                "total": self.total,
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "blocked_count": self.blocked_count,
                "committed": self.committed,
            }
        )


class ImportRowContext(BaseFrameworkObject):
    """定义写单行时的执行上下文（由编排构造）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        actor: int | None,
        tenant_id: int | None,
        tenant_code: str | None,
        audit: AuditCapturer | None = None,
        quota: TenantQuotaClient | None = None,
        job_ctx: JobContext | None = None,
        config: BaseConfigSource | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 当前会话。
            uow: 当前工作单元。
            actor: 操作人（用户主键）。
            tenant_id: 租户主键。
            tenant_code: 租户编码。
            audit: 审计捕获器（None 表示不记录）。
            quota: 租户配额客户端（仅 users 使用）。
            job_ctx: 异步作业上下文（同步内联为 None）。
            config: 系统参数取数（角色码格式等）。
        """
        self.session = session
        self.uow = uow
        self.actor = actor
        self.tenant_id = tenant_id
        self.tenant_code = tenant_code
        self.audit = audit
        self.quota = quota
        self.job_ctx = job_ctx
        self.config = config


class BaseImportDefinition(BaseFrameworkObject, ABC):
    """业务导入定义：列集 + 预检 + 单行写入。"""

    biz: str = ""
    """业务标识（路径段，如 users / roles）。"""

    title: str = ""
    """业务中文名（模板 / 错误明细文件名）。"""

    write_permission: str | None = None
    """业务写权限码（None = 仅入口 `import:execute`）。"""

    quota_key: str | None = None
    """租户配额维度（None = 不占配额；users 为 `user_count`）。"""

    @property
    @abstractmethod
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导入列集（固定列序）。"""

    async def preload(self, session: DbSession, rows: ConcurrentStableList[ParsedRow]) -> object:
        """批量预取（库内已存在键等），返回值给 `validate_row` 使用。

        Args:
            session: 当前会话。
            rows: 全部数据行。

        Returns:
            object: 定义自定义的预取结果（默认 None）。
        """
        del session, rows
        return None

    @abstractmethod
    async def validate_row(
        self,
        row: ParsedRow,
        preloaded: object,
        *,
        config: BaseConfigSource | None,
    ) -> ConcurrentStableFrozenList[RowError]:
        """业务行校验（通用校验已由导入器完成）。

        Args:
            row: 已通过通用校验的行。
            preloaded: `preload` 返回的预取结果。
            config: 系统参数取数。

        Returns:
            ConcurrentStableFrozenList[RowError]: 该行错误（空表示通过）。
        """

    async def write_row(self, row: ParsedRow, ctx: ImportRowContext) -> None:
        """写入单行（由所有者域服务承担；默认未实现）。

        Args:
            row: 已通过校验的行。
            ctx: 执行上下文。

        Raises:
            NotImplementedError: 定义未实现写路径。
        """
        del row, ctx
        raise NotImplementedError(f"导入定义未实现写路径：{self.biz}")


class ImportBatchUnitOfWork(UnitOfWork):
    """导入批次工作单元：把单行服务的事务边界并入外层批次事务。

    导入的全量原子由编排持有（同步 savepoint / 异步作业事务），单行业务服务（`UserAdminService` /
    `RoleService`）内部 `uow.begin()` 若真正开启事务会与外层冲突、且逐行提交破坏原子性；本实现
    把 `begin()` 收窄为空上下文、`commit()` / `rollback()` 交由外层事务决定。
    """

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 批次所在会话。
        """
        self._session = session

    @property
    def session(self) -> DbSession:
        """当前会话。

        Returns:
            DbSession: 批次所在会话。
        """
        return self._session

    def begin(self) -> AbstractAsyncContextManager[object]:
        """返回空事务上下文（并入外层批次事务）。

        Returns:
            AbstractAsyncContextManager[object]: 空上下文。
        """
        return _joined_transaction()

    async def commit(self) -> None:
        """空提交（由外层批次事务提交）。"""

    async def rollback(self) -> None:
        """空回滚（由外层批次事务回滚）。"""


class _joined_transaction(AbstractAsyncContextManager[object]):
    """空事务上下文（不触发会话事务）。"""

    async def __aenter__(self) -> object:
        """进入（无操作）。

        Returns:
            object: None。
        """
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        """退出（不处理异常，交外层）。

        Returns:
            bool: False。
        """
        return False


class ImportDefinitionRegistry(BaseFrameworkObject):
    """导入定义注册表（进程内、构建期登记、运行期只读）。"""

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._definitions: ConcurrentStableDict[str, BaseImportDefinition] = ConcurrentStableDict()

    def register(self, definition: BaseImportDefinition) -> None:
        """登记定义（重名 / 非法 biz / 空列集即拒）。

        Args:
            definition: 导入定义。

        Raises:
            ValueError: 业务标识非法 / 重复 / 标题为空 / 列集为空 / 列键重复。
        """
        biz = definition.biz.strip()
        if _BIZ_PATTERN.fullmatch(biz) is None:
            raise ValueError(f"导入业务标识非法：{definition.biz!r}")
        if biz in self._definitions:
            raise ValueError(f"导入业务标识重复：{biz}")
        if not definition.title.strip():
            raise ValueError(f"导入业务标题为空：{biz}")
        columns = definition.columns
        if not columns:
            raise ValueError(f"导入业务列集为空：{biz}")
        keys = ConcurrentStableDict[str, bool]()
        titles = ConcurrentStableDict[str, bool]()
        for column in columns:
            if column.key in keys:
                raise ValueError(f"导入列键重复：{biz}:{column.key}")
            if column.title in titles:
                raise ValueError(f"导入列标题重复：{biz}:{column.title}")
            keys.set(column.key, True)
            titles.set(column.title, True)
        self._definitions.set(biz, definition)

    def get(self, biz: str) -> BaseImportDefinition | None:
        """按业务标识取定义。

        Args:
            biz: 业务标识。

        Returns:
            BaseImportDefinition | None: 定义；未登记返回 None。
        """
        return self._definitions.get(biz)

    def all(self) -> ConcurrentStableFrozenDict[str, BaseImportDefinition]:
        """取全部定义（只读快照）。

        Returns:
            ConcurrentStableFrozenDict[str, BaseImportDefinition]: 业务标识 → 定义。
        """
        return ConcurrentStableFrozenDict[str, BaseImportDefinition](dict(self._definitions))

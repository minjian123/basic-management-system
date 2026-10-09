"""分支驱动端口：TM 经各服务**参与端点**驱动分支（核验 / 提交 / 回滚）。

- TM **只做协议、不承载业务语义**（详设 05_07 §3.3）：分支执行由**调用方**完成，
  TM 只在决定点前后驱动 `commit` / `rollback` 并核验分支状态。
- 缺省实现 `UnavailableBranchDriver` **明确失败**（未接入参与端点时不静默成功）；
  真实 HTTP 实现随参与端点一并落地（详设 §9 第 5 项）。
"""

from abc import ABC, abstractmethod

from bms_core.core.exceptions import TransactionUnavailableError
from bms_core.core.objects import BaseFrameworkObject

__all__ = ["BranchDriver", "UnavailableBranchDriver"]

_UNAVAILABLE = "参与端点未接入：分支驱动不可用（[transaction_manager].provider 未启用或参与方未挂端点）"


class BranchDriver(BaseFrameworkObject, ABC):
    """分支驱动契约：核验 / 提交 / 回滚单个分支（作用于参与方服务）。"""

    @abstractmethod
    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验分支状态（TM 决定点前调用）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键（不透明，随请求透传）。
            xid: 分支事务标识。

        Returns:
            str: 分支状态（`active` / `prepared` / `committed` / `rolled_back` / `rejected`）。
        """

    @abstractmethod
    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交分支（决定点之后）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键。
            xid: 分支事务标识。

        Returns:
            str: 分支状态（`committed`）。
        """

    @abstractmethod
    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚分支（决定点之前 / 到期回滚）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键。
            xid: 分支事务标识。

        Returns:
            str: 分支状态（`rolled_back`）。
        """


class UnavailableBranchDriver(BranchDriver):
    """缺省驱动：明确抛出 `TransactionUnavailableError`（`10013` / 503）。

    **不静默成功**——避免「TM 以为已驱动、参与方实际未提交」造成假一致。
    """

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """拒绝核验分支。

        Args:
            service: 参与方服务键（占位忽略）。
            db_key: 分支目标库键（占位忽略）。
            xid: 分支事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(_UNAVAILABLE)

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """拒绝提交分支。

        Args:
            service: 参与方服务键（占位忽略）。
            db_key: 分支目标库键（占位忽略）。
            xid: 分支事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(_UNAVAILABLE)

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """拒绝回滚分支。

        Args:
            service: 参与方服务键（占位忽略）。
            db_key: 分支目标库键（占位忽略）。
            xid: 分支事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(_UNAVAILABLE)

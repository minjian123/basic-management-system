"""分支驱动端口：TM 经各服务**参与端点**驱动分支（核验 / 提交 / 回滚）。

- TM **只做协议、不承载业务语义**（详设 05_07 §3.3）：分支执行由**调用方**完成，
  TM 只在决定点前后驱动 `commit` / `rollback` 并核验分支状态。
- `HttpBranchDriver`：经服务间调用契约调参与端点（服务身份由客户端附上）；
- `UnavailableBranchDriver`：**明确失败**（参与端点未接入时不静默成功）。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ServiceUnavailableError, TransactionUnavailableError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["BRANCHES_PATH", "BranchDriver", "HttpBranchDriver", "UnavailableBranchDriver"]

_UNAVAILABLE = "参与端点未接入：分支驱动不可用（[transaction_manager].provider 未启用或参与方未挂端点）"

BRANCHES_PATH = "/api/v1/txn/branches"
"""参与端点基路径（参与方经 `build_branch_router()` 挂载）。"""


def _branch_state(response: ServiceResponse, *, action: str) -> str:
    """校验参与端点响应并取分支状态（非 2xx / 业务非 0 即失败）。

    Args:
        response: 调用响应。
        action: 动作名（错误文案）。

    Returns:
        str: 分支状态。

    Raises:
        ServiceUnavailableError: 传输 / 业务失败（10007 / 503）。
    """
    if response.status_code // 100 != 2:
        raise ServiceUnavailableError(f"{action}失败：HTTP {response.status_code}")
    payload = response.payload()
    if not isinstance(payload, dict):
        raise ServiceUnavailableError(f"{action}响应非法（非 JSON 对象）")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError(f"{action}业务失败：{body.get('message')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise ServiceUnavailableError(f"{action}响应缺少 data")
    return str(cast("dict[str, object]", data).get("state", ""))


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


class HttpBranchDriver(BranchDriver):
    """经参与端点驱动分支（服务身份由服务间调用客户端附上）。

    参与方未挂端点 / 未启用强一致时调用失败 ⇒ 由协调器留痕、恢复器退避重驱动（**不静默放弃**）。
    """

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例（取 `state.service_client`，延迟取用）。
        """
        self._app = app

    @property
    def _client(self) -> BaseServiceClient:
        """取服务间调用客户端（未装配即明确失败）。

        Returns:
            BaseServiceClient: 客户端。

        Raises:
            ServiceUnavailableError: 未装配（10007 / 503）。
        """
        client = getattr(self._app.state, "service_client", None)
        if client is None:
            raise ServiceUnavailableError("服务间调用客户端未装配（[service_client].provider 为空）")
        return cast("BaseServiceClient", client)

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验分支状态（`GET /api/v1/txn/branches/{xid}`）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键。
            xid: 分支事务标识。

        Returns:
            str: 分支状态。
        """
        response = await self._client.call(
            ServiceRequest(
                service=service,
                method="GET",
                path=f"{BRANCHES_PATH}/{xid}",
                query=ConcurrentStableDict({"db_key": db_key}),
            )
        )
        return _branch_state(response, action="分支状态核验")

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交分支（`POST /api/v1/txn/branches/{xid}/commit`）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键。
            xid: 分支事务标识。

        Returns:
            str: 分支状态。
        """
        response = await self._client.call(
            ServiceRequest(
                service=service,
                method="POST",
                path=f"{BRANCHES_PATH}/{xid}/commit",
                query=ConcurrentStableDict({"db_key": db_key}),
            )
        )
        return _branch_state(response, action="分支提交")

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚分支（`POST /api/v1/txn/branches/{xid}/rollback`）。

        Args:
            service: 参与方服务键。
            db_key: 分支目标库键。
            xid: 分支事务标识。

        Returns:
            str: 分支状态。
        """
        response = await self._client.call(
            ServiceRequest(
                service=service,
                method="POST",
                path=f"{BRANCHES_PATH}/{xid}/rollback",
                query=ConcurrentStableDict({"db_key": db_key}),
            )
        )
        return _branch_state(response, action="分支回滚")


class UnavailableBranchDriver(BranchDriver):
    """缺省驱动：明确抛出 `TransactionUnavailableError`（`10013` / 503）。

    **不静默成功**——避免「TM 以为已驱动、参与方实际未提交」造成假一致；
    运维 CLI 与用例可显式以其构造协调器。
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

"""跨服务事务管理器契约：全局事务开启 / 提交 / 回滚 / 查询。

- 鉴权：**服务身份**（`require_service()`，任意已登记服务均可发起；TM 不感知租户 / 业务）。
- 分支寻址：`service` + **不透明 `db_key`**（TM 只存储与回传、不解释）。
- 契约计入 `txn` 服务公开契约（`deploy/contracts/txn.json`）。
"""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema

__all__ = ["BeginGlobalTxnRequest", "BranchSpecRequest", "BranchView", "GlobalTxnView"]


class BranchSpecRequest(BaseSchema):
    """分支声明（调用方给出；TM 只作寻址）。"""

    branch_id: str = Field(
        min_length=1, max_length=16, description="分支标识（同一全局事务内唯一；同时作为 XA `bqual`）"
    )
    service: str = Field(min_length=1, max_length=64, description="参与方服务键（分支执行端点的服务身份）")
    db_key: str = Field(min_length=1, max_length=128, description="**不透明库键**（平台 / 租户 / 归档库均可）")


class BeginGlobalTxnRequest(BaseSchema):
    """开启全局事务请求（`caller_service` 取自服务身份，不由请求体声明）。"""

    branches: Annotated[ConcurrentStableList[BranchSpecRequest], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分支声明清单（非空）"
    )
    timeout_seconds: float | None = Field(
        default=None, gt=0, description="全局提交截止（秒）；缺省取 `[transaction_manager].deadline_seconds`"
    )


class BranchView(BaseSchema):
    """分支视图（含 `xid` 与驱动痕迹）。"""

    branch_id: str = Field(description="分支标识")
    service: str = Field(description="参与方服务键")
    db_key: str = Field(description="不透明库键")
    xid: str = Field(description="XA 事务标识（由 TM 生成）")
    state: str = Field(description="分支状态（active / prepared / committed / rolled_back / rejected）")
    retry_count: int = Field(description="TM 驱动重试次数")
    last_error: str | None = Field(default=None, description="最近一次驱动失败原因")


class GlobalTxnView(BaseSchema):
    """全局事务视图（`begin` / `commit` / `rollback` / `status` 统一返回）。"""

    global_txn_id: str = Field(description="全局事务标识（同时作为 XA `gtrid`）")
    caller_service: str = Field(description="发起方服务键")
    state: str = Field(description="全局事务状态（TXN_*）")
    deadline_at: datetime = Field(description="提交决定截止时间（UTC）")
    decided_at: datetime | None = Field(default=None, description="提交决定点时间（UTC；非空即已过决定点）")
    branches: Annotated[ConcurrentStableList[BranchView], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分支清单"
    )

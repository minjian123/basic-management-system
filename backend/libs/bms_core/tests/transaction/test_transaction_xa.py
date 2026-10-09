"""跨服务事务 XA 提供者与参与端点用例（强一致专项 05_07；Kiwi 2271）。

覆盖：① 管理器经服务间契约调 TM（路径 / 方法 / 载荷）、响应解析与失败语义；
② 参与方未登记 `op` 即**否决**（不触碰引擎）；③ 参与端点路由器形状（5 端点与鉴权口径）。
"""

import json
from typing import cast

import pytest
from starlette.routing import Route

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError, TransactionUnavailableError
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.transaction.api import build_branch_router
from bms_core.transaction.base import (
    TM_SERVICE_NAME,
    TRANSACTION_MANAGER_KEY,
    TRANSACTION_PARTICIPANT_KEY,
    BranchHandlerRegistry,
    BranchSpec,
)
from bms_core.transaction.xa import XA_PLUGIN_NAME, XaTransactionManager, XaTransactionParticipant

pytestmark = [pytest.mark.kiwi_id(2271)]


def _ok(data: ConcurrentStableDict[str, object]) -> ServiceResponse:
    """构造业务成功响应。"""
    body = json.dumps({"code": 0, "message": "ok", "data": dict(data)}).encode()
    return ServiceResponse(status_code=200, content=body)


class _FakeClient(BaseServiceClient):
    """服务间调用替身：记录请求并返回预设响应。"""

    plugin_name: str = "fake"

    def __init__(self, response: ServiceResponse) -> None:
        """初始化。

        Args:
            response: 预设响应。
        """
        self.response = response
        self.calls: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录并返回预设响应。"""
        self.calls.add(request)
        return self.response


class _UnusedEngines:
    """引擎提供者替身：被调用即断言失败（未登记 `op` 不应触碰引擎）。"""

    async def get_sync(self, db_key: str = "platform", *, read_only: bool = False) -> object:
        """恒定断言失败。"""
        del db_key, read_only
        raise AssertionError("未登记 op 不应触碰引擎")


async def test_manager_begin_sends_branches_to_tm() -> None:
    """开启：`POST /api/v1/txn/global`、目标服务 `txn`、分支声明随载荷下发、快照可解析。"""
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "global_txn_id": "1001",
            "caller_service": "platform",
            "state": "active",
            "branches": [
                {"branch_id": "b1", "service": "platform", "db_key": "platform", "xid": "1001|b1", "state": "active"}
            ],
        }
    )
    client = _FakeClient(_ok(data))
    manager = XaTransactionManager(client)

    snapshot = await manager.begin(
        caller_service="platform", branches=(BranchSpec(branch_id="b1", service="platform", db_key="platform"),)
    )

    assert manager.enabled is True
    request = client.calls[0]
    assert request.service == TM_SERVICE_NAME
    assert request.method == "POST"
    assert request.path == "/api/v1/txn/global"
    assert request.json_body is not None
    assert request.json_body["branches"] == [{"branch_id": "b1", "service": "platform", "db_key": "platform"}]
    assert snapshot.global_txn_id == "1001"
    assert snapshot.branches[0].xid == "1001|b1"


@pytest.mark.parametrize(
    ("method", "http", "path_suffix"),
    [("commit", "POST", "/commit"), ("rollback", "DELETE", ""), ("status", "GET", "")],
)
async def test_manager_paths_per_action(method: str, http: str, path_suffix: str) -> None:
    """终态动作：提交 `POST .../commit`、回滚 `DELETE ...`、查询 `GET ...`。"""
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"global_txn_id": "1001", "caller_service": "platform", "state": "committed", "branches": []}
    )
    client = _FakeClient(_ok(data))
    manager = XaTransactionManager(client)

    await getattr(manager, method)("1001")

    request = client.calls[0]
    assert request.method == http
    assert request.path == f"/api/v1/txn/global/1001{path_suffix}"


async def test_manager_rejects_business_failure() -> None:
    """TM 业务失败（`code != 0`）⇒ `ServiceUnavailableError`（10007 / 503）。"""
    body = json.dumps({"code": 10013, "message": "未启用", "data": None}).encode()
    manager = XaTransactionManager(_FakeClient(ServiceResponse(status_code=200, content=body)))

    with pytest.raises(ServiceUnavailableError):
        await manager.status("1001")


async def test_manager_rejects_non_json() -> None:
    """TM 响应非 JSON ⇒ `TransactionUnavailableError`（10013 / 503）。"""
    manager = XaTransactionManager(_FakeClient(ServiceResponse(status_code=200, content=b"<html>")))

    with pytest.raises(TransactionUnavailableError):
        await manager.status("1001")


async def test_participant_rejects_unregistered_op() -> None:
    """分支执行：`op` 未登记 ⇒ **否决**（`rejected`），且不触碰引擎。"""
    participant = XaTransactionParticipant(_UnusedEngines(), BranchHandlerRegistry())  # type: ignore[arg-type]

    state = await participant.execute_branch(
        xid="1001|b1", db_key="platform", op="unknown.op", args=ConcurrentStableDict[str, object]()
    )

    assert state == "rejected"
    assert participant.enabled is True


def test_branch_router_shape() -> None:
    """参与端点：5 条路由（执行 / 提交 / 回滚 / 状态 / 悬挂列举），前缀与鉴权口径就位。"""
    router = build_branch_router()
    routes = sorted(
        (sorted(cast("Route", route).methods or []).pop(), cast("Route", route).path) for route in router.routes
    )

    assert routes == [
        ("GET", "/txn/branches"),
        ("GET", "/txn/branches/{xid}"),
        ("POST", "/txn/branches"),
        ("POST", "/txn/branches/{xid}/commit"),
        ("POST", "/txn/branches/{xid}/rollback"),
    ]


def test_provider_names_reserved() -> None:
    """提供者名与能力域键就位（装配按 `[transaction_manager].provider` 解析）。"""
    assert XA_PLUGIN_NAME == "xa"
    assert TRANSACTION_MANAGER_KEY == "transaction_manager"
    assert TRANSACTION_PARTICIPANT_KEY == "transaction_participant"

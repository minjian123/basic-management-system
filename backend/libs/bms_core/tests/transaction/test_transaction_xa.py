"""跨服务事务 XA 提供者与参与端点用例（强一致专项 05_07；Kiwi 2271）。

覆盖：① 管理器经服务间契约调 TM（路径 / 方法 / 载荷）、响应解析与失败语义；
② 参与方未登记 `op` 即**否决**（不触碰引擎）；③ 参与端点路由器形状（5 端点与鉴权口径）。
"""

import json
from typing import Any, cast

import pytest
from fastapi import FastAPI
from starlette.routing import Route

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ServiceUnavailableError, TransactionUnavailableError
from bms_core.db.session import DbSession
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.transaction.api import build_branch_router
from bms_core.transaction.base import (
    TM_SERVICE_NAME,
    TRANSACTION_MANAGER_KEY,
    TRANSACTION_PARTICIPANT_KEY,
    BranchHandlerRegistry,
    BranchOp,
    BranchSpec,
)
from bms_core.transaction.xa import (
    XA_PLUGIN_NAME,
    XaTransactionManager,
    XaTransactionManagerFactory,
    XaTransactionParticipant,
    XaTransactionParticipantFactory,
)

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
        xid="1001|b1",
        db_key="platform",
        ops=(BranchOp(op="unknown.op", args=ConcurrentStableDict[str, object]()),),
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


def _ok_raw(data: object) -> ServiceResponse:
    """构造业务成功响应（`data` 为任意 JSON 值）。"""
    body = json.dumps({"code": 0, "message": "ok", "data": data}).encode()
    return ServiceResponse(status_code=200, content=body)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (ServiceResponse(status_code=503, content=b"{}"), ServiceUnavailableError),
        (ServiceResponse(status_code=200, content=b"[]"), TransactionUnavailableError),
        (ServiceResponse(status_code=200, content=json.dumps({"code": 0}).encode()), TransactionUnavailableError),
    ],
)
async def test_manager_rejects_malformed_response(response: ServiceResponse, expected: type[Exception]) -> None:
    """TM 响应非法：非 2xx（10007）/ 载荷非对象 / 缺 data（10013）。"""
    manager = XaTransactionManager(_FakeClient(response))
    with pytest.raises(expected):
        await manager.status("1001")


async def test_manager_rejects_snapshot_without_identity() -> None:
    """快照缺全局事务标识 / 状态 → 10013。"""
    manager = XaTransactionManager(_FakeClient(_ok_raw({"state": "active"})))
    with pytest.raises(TransactionUnavailableError):
        await manager.status("1001")


async def test_manager_tolerates_missing_and_non_mapping_branches() -> None:
    """快照分支：`branches` 非列表按无分支处理；列表内非对象项跳过。"""
    manager = XaTransactionManager(_FakeClient(_ok_raw({"global_txn_id": "1", "state": "active", "branches": None})))
    assert (await manager.status("1001")).branches == ()

    manager = XaTransactionManager(
        _FakeClient(
            _ok_raw(
                {
                    "global_txn_id": "1",
                    "state": "active",
                    "branches": [1, {"branch_id": "b1", "retry_count": 2}],
                }
            )
        )
    )
    snapshot = await manager.status("1001")
    assert [branch.branch_id for branch in snapshot.branches] == ["b1"]
    assert snapshot.branches[0].retry_count == 2


async def test_manager_begin_passes_timeout() -> None:
    """开启：显式超时随载荷下发。"""
    client = _FakeClient(_ok(ConcurrentStableDict({"global_txn_id": "1", "state": "active", "branches": []})))
    manager = XaTransactionManager(client)

    await manager.begin(caller_service="platform", branches=(), timeout_seconds=5.0)

    request = client.calls[0]
    assert request.json_body is not None
    assert request.json_body["timeout_seconds"] == 5.0


class _FakeTwoPhase:
    """两阶段事务替身（记录 `prepare`）。"""

    def __init__(self) -> None:
        self.prepared = False

    def prepare(self) -> None:
        """标记已 PREPARE。"""
        self.prepared = True


class _FakeConnection:
    """同步连接替身（记录两阶段生命周期调用）。"""

    def __init__(self, *, fail_rollback: bool = False, fail_close: bool = False) -> None:
        self.fail_rollback = fail_rollback
        self.fail_close = fail_close
        self.txn = _FakeTwoPhase()
        self.xid: str | None = None
        self.detached = False
        self.closed = 0
        self.rolled_back = 0

    def begin_twophase(self, xid: str) -> _FakeTwoPhase:
        """开启两阶段事务。"""
        self.xid = xid
        return self.txn

    def detach(self) -> None:
        """分离连接。"""
        self.detached = True

    def rollback(self) -> None:
        """回滚（可配置失败）。"""
        self.rolled_back += 1
        if self.fail_rollback:
            raise RuntimeError("rollback failed")

    def close(self) -> None:
        """关闭（可配置失败）。"""
        self.closed += 1
        if self.fail_close:
            raise RuntimeError("close failed")


class _FakeDialect:
    """方言替身（两阶段驱动 / 悬挂列举）。"""

    def __init__(self, recovered: tuple[object, ...] = ()) -> None:
        self.recovered = recovered
        self.commits: ConcurrentStableList[tuple[str, bool, bool]] = ConcurrentStableList()
        self.rollbacks: ConcurrentStableList[tuple[str, bool, bool]] = ConcurrentStableList()

    def do_commit_twophase(self, connection: object, xid: str, is_prepared: bool, recover: bool) -> None:
        """记录提交驱动。"""
        self.commits.add((xid, is_prepared, recover))

    def do_rollback_twophase(self, connection: object, xid: str, is_prepared: bool, recover: bool) -> None:
        """记录回滚驱动。"""
        self.rollbacks.add((xid, is_prepared, recover))

    def do_recover_twophase(self, connection: object) -> tuple[object, ...]:
        """列举悬挂分支。"""
        return self.recovered


class _FakeEngine:
    """同步引擎替身。"""

    def __init__(self, connection: _FakeConnection, dialect: _FakeDialect) -> None:
        self.dialect = dialect
        self._connection = connection

    def connect(self) -> _FakeConnection:
        """取连接。"""
        return self._connection


class _FakeEngines:
    """引擎提供者替身。"""

    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine

    async def get_sync(self, db_key: str = "platform", *, read_only: bool = False) -> _FakeEngine:
        """取同步引擎。"""
        del db_key, read_only
        return self.engine


async def test_participant_executes_branch_prepares_and_detaches() -> None:
    """分支执行：按序执行 op → `prepare` → 分离连接（close 不回滚已 PREPARE 分支）。"""
    connection = _FakeConnection()
    registry = BranchHandlerRegistry()
    calls: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    async def handler(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
        del session
        calls.add(args)

    registry.register("test.op", handler)
    participant = XaTransactionParticipant(cast("Any", _FakeEngines(_FakeEngine(connection, _FakeDialect()))), registry)

    args = ConcurrentStableDict[str, object]({"k": 1})
    state = await participant.execute_branch(xid="xa-1", db_key="platform", ops=(BranchOp(op="test.op", args=args),))

    assert state == "prepared"
    assert connection.xid == "xa-1"
    assert connection.txn.prepared is True
    assert connection.detached is True
    assert connection.rolled_back == 0
    assert connection.closed >= 1
    assert list(calls) == [args]


async def test_participant_rolls_back_when_handler_fails() -> None:
    """分支执行：任一 op 抛错 → 尽力回滚并向上抛（连接照常关闭）。"""
    connection = _FakeConnection()
    registry = BranchHandlerRegistry()

    async def handler(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
        del session, args
        raise RuntimeError("boom")

    registry.register("test.op", handler)
    participant = XaTransactionParticipant(cast("Any", _FakeEngines(_FakeEngine(connection, _FakeDialect()))), registry)

    with pytest.raises(RuntimeError):
        await participant.execute_branch(
            xid="xa-1", db_key="platform", ops=(BranchOp(op="test.op", args=ConcurrentStableDict[str, object]()),)
        )

    assert connection.rolled_back == 1
    assert connection.closed >= 1


async def test_participant_swallows_rollback_and_close_failures() -> None:
    """分支执行：回滚 / 关闭失败被吞掉（不掩盖原始异常、不向上传播）。"""
    connection = _FakeConnection(fail_rollback=True, fail_close=True)
    registry = BranchHandlerRegistry()

    async def handler(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
        del session, args
        raise RuntimeError("boom")

    registry.register("test.op", handler)
    participant = XaTransactionParticipant(cast("Any", _FakeEngines(_FakeEngine(connection, _FakeDialect()))), registry)

    with pytest.raises(RuntimeError):
        await participant.execute_branch(
            xid="xa-1", db_key="platform", ops=(BranchOp(op="test.op", args=ConcurrentStableDict[str, object]()),)
        )


async def test_participant_drives_terminal_states_and_recovery() -> None:
    """分支终态驱动：提交 / 回滚经新连接方言 API；悬挂列举与分支状态以数据库侧为准。"""
    connection = _FakeConnection()
    dialect = _FakeDialect(recovered=("xa-1",))
    participant = XaTransactionParticipant(
        cast("Any", _FakeEngines(_FakeEngine(connection, dialect))), BranchHandlerRegistry()
    )

    assert await participant.commit_branch(xid="xa-1", db_key="platform") == "committed"
    assert list(dialect.commits) == [("xa-1", True, True)]
    assert await participant.rollback_branch(xid="xa-2", db_key="platform") == "rolled_back"
    assert list(dialect.rollbacks) == [("xa-2", True, True)]
    assert await participant.recover_branches(db_key="platform") == ("xa-1",)
    assert await participant.branch_state(xid="xa-1", db_key="platform") == "prepared"
    assert await participant.branch_state(xid="xa-9", db_key="platform") == "active"


async def test_manager_factory_adapter_forwards_calls() -> None:
    """管理器工厂：经应用 state 延迟取用服务间客户端并转发调用。"""
    app = FastAPI()
    client = _FakeClient(_ok(ConcurrentStableDict({"global_txn_id": "1", "state": "active", "branches": []})))
    app.state.service_client = client
    manager = XaTransactionManagerFactory(Settings(), app).create()

    snapshot = await manager.status("1")

    assert manager.enabled is True
    assert snapshot.global_txn_id == "1"
    assert len(client.calls) == 1


def test_participant_factory_uses_app_registry() -> None:
    """参与方工厂：分支处理器经应用 state 取用；未装配时回落空注册表。"""
    app = FastAPI()
    app.state.branch_handlers = BranchHandlerRegistry()
    assert XaTransactionParticipantFactory(Settings(), app).create() is not None

    bare_app = FastAPI()
    assert XaTransactionParticipantFactory(Settings(), bare_app).create() is not None


async def test_lazy_engine_registry_forwards_to_app_state() -> None:
    """引擎注册表代理：转发到应用装配的注册表（延迟取用）。"""
    app = FastAPI()
    dialect = _FakeDialect(recovered=("xa-1",))
    app.state.engine_registry = cast("Any", _FakeEngines(_FakeEngine(_FakeConnection(), dialect)))
    participant = XaTransactionParticipantFactory(Settings(), app).create()

    assert await participant.recover_branches(db_key="platform") == ("xa-1",)

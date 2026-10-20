"""TM 对外契约端点与分支驱动用例（Kiwi 2271）：请求级装配 + 端点编排 + HTTP 分支驱动。

端点函数直调（请求级装配 = 应用 state 取驱动 / 配置），覆盖开启 / 提交 / 回滚 / 查询四条路径与
「驱动未装配即明确失败」；分支驱动覆盖 HTTP 驱动的三条动作路径、客户端缺省拒绝与响应解析失败语义。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ServiceUnavailableError, TransactionUnavailableError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.transaction.base import TXN_COMMITTED, TXN_ROLLING_BACK
from bms_txn.api.ledger import (
    begin_global_txn,
    commit_global_txn,
    get_global_txn,
    rollback_global_txn,
)
from bms_txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery
from bms_txn.repositories.ledger import GlobalTxnRepository
from bms_txn.schemas.ledger import BeginGlobalTxnRequest, BranchSpecRequest
from bms_txn.services.driver import (
    BranchDriver,
    HttpBranchDriver,
    UnavailableBranchDriver,
    _branch_state,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = [pytest.mark.kiwi_id(2271)]


class _DriverSpy(BranchDriver):
    """分支驱动替身（核验全票 `prepared`，记录提交 / 回滚）。"""

    def __init__(self) -> None:
        self.committed: ConcurrentStableList[str] = ConcurrentStableList()
        self.rolled_back: ConcurrentStableList[str] = ConcurrentStableList()

    async def verify(self, *, service: str, db_key: str, xid: str) -> str:
        """核验（恒 `prepared`）。"""
        del service, db_key, xid
        return "prepared"

    async def commit(self, *, service: str, db_key: str, xid: str) -> str:
        """提交并记录。"""
        del service, db_key
        self.committed.add(xid)
        return "committed"

    async def rollback(self, *, service: str, db_key: str, xid: str) -> str:
        """回滚并记录。"""
        del service, db_key
        self.rolled_back.add(xid)
        return "rolled_back"


class _ClientSpy(BaseServiceClient):
    """服务间调用客户端替身（记录请求并回预设响应）。"""

    plugin_name: str = "fake"

    def __init__(self, response: ServiceResponse) -> None:
        self.response = response
        self.calls: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录并返回预设响应。"""
        self.calls.add(request)
        return self.response


class _RequestStub:
    """请求替身（端点仅取 `app.state`）。"""

    def __init__(self, app: FastAPI) -> None:
        self.app = app


class _TokenStub:
    """服务身份替身（仅取 `service`）。"""

    service = "platform"


@pytest.fixture
async def uow() -> AsyncIterator[DbUnitOfWork]:
    """内存 SQLite 工作单元（建账本三表）。

    Yields:
        DbUnitOfWork: 工作单元。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        tables: ConcurrentStableList[Table] = ConcurrentStableList(
            (
                cast("Table", GlobalTxn.__table__),
                cast("Table", GlobalTxnBranch.__table__),
                cast("Table", GlobalTxnRecovery.__table__),
            )
        )
        for table in tables:
            await connection.run_sync(table.create, checkfirst=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield DbUnitOfWork(session)
    finally:
        await session.close()
        await engine.dispose()


def _request(*, driver: BranchDriver | None = None) -> Any:
    """构造请求替身（应用 state 注入配置与分支驱动）。"""
    app = FastAPI()
    app.state.settings = Settings()
    if driver is not None:
        app.state.branch_driver = driver
    return _RequestStub(app)


def _begin_request() -> BeginGlobalTxnRequest:
    """构造开启请求（两个分支）。"""
    return BeginGlobalTxnRequest(
        branches=ConcurrentStableList(
            [
                BranchSpecRequest(branch_id="p1", service="platform", db_key="platform"),
                BranchSpecRequest(branch_id="m1", service="org", db_key="tenant_demo"),
            ]
        ),
        timeout_seconds=30.0,
    )


async def test_global_txn_endpoints_full_cycle(uow: DbUnitOfWork) -> None:
    """端点编排：开启（分支声明 → `xid`）→ 提交 → 查询 → 终态回滚被吸收。"""
    driver = _DriverSpy()
    request = _request(driver=driver)
    token = cast("Any", _TokenStub())

    began = await begin_global_txn(_begin_request(), uow, token, request)
    assert began.code == 0
    body = began.data
    assert body is not None
    assert body.state == "active"
    assert [item.branch_id for item in body.branches] == ["p1", "m1"]
    assert body.branches[0].xid.endswith("|p1")
    global_txn_id = body.global_txn_id

    committed = await commit_global_txn(global_txn_id, uow, token, request)
    assert committed.data is not None
    assert committed.data.state == TXN_COMMITTED
    assert sorted(driver.committed) == sorted(item.xid for item in body.branches)

    fetched = await get_global_txn(global_txn_id, uow, token, request)
    assert fetched.data is not None
    assert fetched.data.global_txn_id == global_txn_id

    absorbed = await rollback_global_txn(global_txn_id, uow, token, request)
    assert absorbed.data is not None
    assert absorbed.data.state == TXN_COMMITTED


async def test_global_txn_endpoint_without_driver_rolls_back(uow: DbUnitOfWork) -> None:
    """分支驱动未装配：核验与驱动皆明确拒绝 ⇒ 置回滚且**不落终态**（未确认分支由恢复器续行）。"""
    request = _request()
    token = cast("Any", _TokenStub())
    began = await begin_global_txn(_begin_request(), uow, token, request)
    assert began.data is not None

    committed = await commit_global_txn(began.data.global_txn_id, uow, token, request)

    assert committed.data is not None
    assert committed.data.state == TXN_ROLLING_BACK  # 全分支未确认 ⇒ 终态留给恢复器收敛
    async with uow.begin():
        row = await GlobalTxnRepository(uow.session).get_by_global_txn_id(began.data.global_txn_id)
    assert row is not None
    assert row.state == TXN_ROLLING_BACK


def _ok(state: str) -> ServiceResponse:
    """构造参与端点成功响应。"""
    return ServiceResponse(status_code=200, content=json.dumps({"code": 0, "data": {"state": state}}).encode())


async def test_http_branch_driver_sends_actions() -> None:
    """HTTP 驱动：核验 / 提交 / 回滚路径与方法，`db_key` 经查询参数透传。"""
    app = FastAPI()
    client = _ClientSpy(_ok("prepared"))
    app.state.service_client = client
    driver = HttpBranchDriver(app)

    assert await driver.verify(service="platform", db_key="tenant_demo", xid="x1") == "prepared"
    assert await driver.commit(service="platform", db_key="tenant_demo", xid="x1") == "prepared"
    assert await driver.rollback(service="platform", db_key="tenant_demo", xid="x1") == "prepared"

    requests = list(client.calls)
    assert [(item.method, item.path) for item in requests] == [
        ("GET", "/api/v1/txn/branches/x1"),
        ("POST", "/api/v1/txn/branches/x1/commit"),
        ("POST", "/api/v1/txn/branches/x1/rollback"),
    ]
    assert requests[0].query is not None
    assert requests[0].query.get("db_key") == "tenant_demo"


async def test_http_branch_driver_requires_client() -> None:
    """HTTP 驱动：应用未装配服务间客户端时明确失败（不静默成功）。"""
    with pytest.raises(ServiceUnavailableError):
        await HttpBranchDriver(FastAPI()).verify(service="platform", db_key="k", xid="x1")


@pytest.mark.parametrize(
    "response",
    [
        ServiceResponse(status_code=503, content=b"{}"),
        ServiceResponse(status_code=200, content=b"[]"),
        ServiceResponse(status_code=200, content=json.dumps({"code": 7}).encode()),
        ServiceResponse(status_code=200, content=json.dumps({"code": 0}).encode()),
    ],
)
def test_branch_state_failure_branches(response: ServiceResponse) -> None:
    """分支状态解析失败分支：非 2xx / 非对象 / 业务非 0 / 缺 data → 10007。"""
    with pytest.raises(ServiceUnavailableError):
        _branch_state(response, action="分支状态核验")


def test_branch_state_returns_state() -> None:
    """分支状态解析：2xx + `code=0` + `data.state` → 原样返回。"""
    assert _branch_state(_ok("prepared"), action="分支状态核验") == "prepared"


async def test_unavailable_driver_rejects_all_actions() -> None:
    """缺省驱动：核验 / 提交 / 回滚皆明确拒绝（10013）。"""
    driver = UnavailableBranchDriver()
    with pytest.raises(TransactionUnavailableError):
        await driver.verify(service="platform", db_key="k", xid="x1")
    with pytest.raises(TransactionUnavailableError):
        await driver.commit(service="platform", db_key="k", xid="x1")
    with pytest.raises(TransactionUnavailableError):
        await driver.rollback(service="platform", db_key="k", xid="x1")

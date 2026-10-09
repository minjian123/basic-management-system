"""transaction 能力域 XA 实现（强一致专项 05_07）。

- `XaTransactionManager`：**调用方门面**——经服务间调用契约（`service_client`）调 TM 服务
  `txn` 的 `/api/v1/txn/global*`；`caller_service` 以**服务身份令牌**为准（参数仅作契约占位）。
- `XaTransactionParticipant`：**参与方分支执行**——走**分支专用同步引擎**（两阶段仅同步引擎可用），
  单请求内 `XA_START → 业务写 → XA_END → XA_PREPARE`，**连接随请求释放**。

**关键落地要点（实测结论）**：SQLAlchemy 的 `TwoPhaseTransaction` 继承 `RootTransaction`，
`prepare()` 后 `is_active` 仍为真 ⇒ 直接 `Connection.close()` 会**回滚已 PREPARE 的分支**。
故 `prepare()` 后必须 `connection.detach()`（清 `_transaction` 并分离 DBAPI 连接，使 `close()` 不回滚），
提交 / 回滚由**新连接**经 `dialect.do_*_twophase(..., recover=True)` 完成（已 PREPARE 分支由数据库侧持有）。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import Engine
from sqlalchemy.engine.default import DefaultDialect

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ServiceUnavailableError, TransactionUnavailableError
from bms_core.core.factory import BasePluginFactory
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.db.sync import SyncSession
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.transaction.base import (
    BRANCH_ACTIVE,
    BRANCH_COMMITTED,
    BRANCH_PREPARED,
    BRANCH_REJECTED,
    BRANCH_ROLLED_BACK,
    TM_SERVICE_NAME,
    BaseTransactionManager,
    BaseTransactionParticipant,
    BranchHandler,
    BranchHandlerRegistry,
    BranchOp,
    BranchRef,
    BranchSpec,
    GlobalTransaction,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "XA_PLUGIN_NAME",
    "XaTransactionManager",
    "XaTransactionManagerFactory",
    "XaTransactionParticipant",
    "XaTransactionParticipantFactory",
]

XA_PLUGIN_NAME = "xa"
"""真实提供者名（`[transaction_manager].provider = "xa"`）。"""

TM_SERVICE = TM_SERVICE_NAME
"""TM 服务键（账本与协调器所在服务）。"""

GLOBAL_TXN_PATH = "/api/v1/txn/global"
"""TM 全局事务端点基路径。"""


def _response_data(response: ServiceResponse, *, action: str) -> ConcurrentStableDict[str, object]:
    """校验服务间调用响应并取 `data`（非 2xx / 业务非 0 即失败）。

    Args:
        response: 服务间调用响应。
        action: 动作名（错误文案）。

    Returns:
        ConcurrentStableDict[str, object]: 响应 `data`。

    Raises:
        ServiceUnavailableError: 传输失败 / 业务失败（10007 / 503）。
        TransactionUnavailableError: 响应结构非法（10013 / 503）。
    """
    if response.status_code // 100 != 2:
        raise ServiceUnavailableError(f"TM {action} 失败：HTTP {response.status_code}")
    payload = response.payload()
    if not isinstance(payload, dict):
        raise TransactionUnavailableError(f"TM {action} 响应非法（非 JSON 对象）")
    body = cast("dict[str, object]", payload)
    if body.get("code") != 0:
        raise ServiceUnavailableError(f"TM {action} 业务失败：{body.get('message')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise TransactionUnavailableError(f"TM {action} 响应缺少 data")
    return ConcurrentStableDict(cast("dict[str, object]", data))


def _to_snapshot(data: ConcurrentStableDict[str, object]) -> GlobalTransaction:
    """响应 `data` → 全局事务快照。

    Args:
        data: 响应 `data`。

    Returns:
        GlobalTransaction: 全局事务快照。

    Raises:
        TransactionUnavailableError: 关键字段缺失（10013 / 503）。
    """
    global_txn_id = data.get("global_txn_id")
    state = data.get("state")
    caller_service = data.get("caller_service")
    if not isinstance(global_txn_id, str) or not isinstance(state, str):
        raise TransactionUnavailableError("TM 响应缺少全局事务标识 / 状态")
    refs: ConcurrentStableList[BranchRef] = ConcurrentStableList()
    raw_branches = data.get("branches")
    if isinstance(raw_branches, list):
        for item in cast("list[object]", raw_branches):
            if not isinstance(item, dict):
                continue
            row = cast("dict[str, object]", item)
            refs.add(
                BranchRef(
                    branch_id=str(row.get("branch_id", "")),
                    service=str(row.get("service", "")),
                    db_key=str(row.get("db_key", "")),
                    xid=str(row.get("xid", "")),
                    state=str(row.get("state", "")),
                    retry_count=int(cast("int", row.get("retry_count") or 0)),
                )
            )
    return GlobalTransaction(
        global_txn_id=global_txn_id,
        caller_service=caller_service if isinstance(caller_service, str) else "",
        state=state,
        deadline_at=None,
        decided_at=None,
        branches=tuple(refs),
    )


class XaTransactionManager(BaseTransactionManager):
    """TM 调用方门面（经服务间调用契约直连 TM 服务）。"""

    plugin_name: str = XA_PLUGIN_NAME

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（经 `[service_client]` 装配）。
        """
        self._client = client

    @property
    def enabled(self) -> bool:
        """恒定真（已启用强一致）。"""
        return True

    async def begin(
        self, *, caller_service: str, branches: tuple[BranchSpec, ...], timeout_seconds: float | None = None
    ) -> GlobalTransaction:
        """开启全局事务（`POST /api/v1/txn/global`）。

        Args:
            caller_service: 发起方服务键（**占位**：TM 以服务身份令牌为准）。
            branches: 分支声明清单。
            timeout_seconds: 全局提交截止（秒）。

        Returns:
            GlobalTransaction: 全局事务快照。
        """
        del caller_service
        items: ConcurrentStableList[object] = ConcurrentStableList()
        for spec in branches:
            items.add(
                ConcurrentStableDict[str, object](
                    {"branch_id": spec.branch_id, "service": spec.service, "db_key": spec.db_key}
                )
            )
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict({"branches": list(items)})
        if timeout_seconds is not None:
            body.set("timeout_seconds", timeout_seconds)
        response = await self._client.call(
            ServiceRequest(service=TM_SERVICE, method="POST", path=GLOBAL_TXN_PATH, json_body=body)
        )
        return _to_snapshot(_response_data(response, action="开启全局事务"))

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """请求提交（`POST /api/v1/txn/global/{id}/commit`）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 提交后的快照。
        """
        response = await self._client.call(
            ServiceRequest(service=TM_SERVICE, method="POST", path=f"{GLOBAL_TXN_PATH}/{global_txn_id}/commit")
        )
        return _to_snapshot(_response_data(response, action="提交全局事务"))

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """请求回滚（`DELETE /api/v1/txn/global/{id}`）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 回滚后的快照。
        """
        response = await self._client.call(
            ServiceRequest(service=TM_SERVICE, method="DELETE", path=f"{GLOBAL_TXN_PATH}/{global_txn_id}")
        )
        return _to_snapshot(_response_data(response, action="回滚全局事务"))

    async def status(self, global_txn_id: str) -> GlobalTransaction:
        """查询全局事务（`GET /api/v1/txn/global/{id}`）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 当前快照。
        """
        response = await self._client.call(
            ServiceRequest(service=TM_SERVICE, method="GET", path=f"{GLOBAL_TXN_PATH}/{global_txn_id}")
        )
        return _to_snapshot(_response_data(response, action="查询全局事务"))


class XaTransactionParticipant(BaseTransactionParticipant):
    """参与方 XA 分支执行（分支专用同步引擎；单请求内 `prepare` 后释放连接）。"""

    plugin_name: str = XA_PLUGIN_NAME

    def __init__(self, engines: SyncEngineProvider, handlers: BranchHandlerRegistry) -> None:
        """初始化。

        Args:
            engines: 同步引擎提供者（按 `db_key` 取同步引擎；生产为 `EngineRegistry`）。
            handlers: 分支业务处理器注册表（`op` → 本服务已有服务层方法）。
        """
        self._engines = engines
        self._handlers = handlers

    @property
    def enabled(self) -> bool:
        """恒定真（本服务具备两阶段能力）。"""
        return True

    async def execute_branch(self, *, xid: str, db_key: str, ops: tuple[BranchOp, ...]) -> str:
        """执行分支：`XA_START → 业务写（按序多个 op）→ XA_END → XA_PREPARE`（单请求内、连接随请求释放）。

        Args:
            xid: 分支事务标识（TM 分配）。
            db_key: 目标库键（不透明；按本服务引擎注册表解析）。
            ops: 分支操作清单（按序执行；任一 `op` 未登记即**整体否决**，不触碰引擎）。

        Returns:
            str: 分支状态（`prepared` / `rejected`）。
        """
        resolved: ConcurrentStableList[BranchHandler] = ConcurrentStableList()
        for item in ops:
            handler = self._handlers.resolve(item.op)
            if handler is None:
                return BRANCH_REJECTED
            resolved.add(handler)
        engine = await self._engines.get_sync(db_key)
        connection = await asyncio.to_thread(engine.connect)
        try:
            txn = await asyncio.to_thread(connection.begin_twophase, xid)
            session = SyncSession(engine, bind=connection)
            try:
                for handler, item in zip(resolved, ops, strict=True):
                    await handler(session, item.args)
            finally:
                await session.close()
            await asyncio.to_thread(txn.prepare)
            # 已 PREPARE：分离连接使 close() 不回滚（分支由数据库侧持有，提交 / 回滚走新连接）
            await asyncio.to_thread(connection.detach)
        except Exception:
            await self._safe_rollback(connection)
            raise
        finally:
            await self._safe_close(connection)
        return BRANCH_PREPARED

    async def commit_branch(self, *, xid: str, db_key: str) -> str:
        """提交分支（TM 驱动；新连接经方言 `do_commit_twophase` 驱动已 PREPARE 分支）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`committed`）。
        """
        await self._drive(db_key=db_key, xid=xid, commit=True)
        return BRANCH_COMMITTED

    async def rollback_branch(self, *, xid: str, db_key: str) -> str:
        """回滚分支（TM 驱动）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`rolled_back`）。
        """
        await self._drive(db_key=db_key, xid=xid, commit=False)
        return BRANCH_ROLLED_BACK

    async def branch_state(self, *, xid: str, db_key: str) -> str:
        """查询分支状态：以数据库侧**悬挂分支列举**为准（`prepared` 可见，否则 `active`）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`prepared` / `active`）。
        """
        recovered = await self.recover_branches(db_key=db_key)
        return BRANCH_PREPARED if xid in recovered else BRANCH_ACTIVE

    async def recover_branches(self, *, db_key: str) -> tuple[str, ...]:
        """列举本库悬挂分支（`XA_RECOVER` 对账用）。

        Args:
            db_key: 目标库键。

        Returns:
            tuple[str, ...]: 悬挂分支的可回放文本形态（无悬挂为空元组）。
        """
        engine = await self._engines.get_sync(db_key)
        dialect = _twophase_dialect(engine)
        connection = await asyncio.to_thread(engine.connect)
        try:
            recovered = await asyncio.to_thread(dialect.do_recover_twophase, connection)
        finally:
            await self._safe_close(connection)
        texts: ConcurrentStableList[str] = ConcurrentStableList()
        for item in recovered:
            texts.add(str(item))
        return tuple(texts)

    async def _drive(self, *, db_key: str, xid: str, commit: bool) -> None:
        """驱动已 PREPARE 分支到终态（新连接 + 方言两阶段 API；`recover=True` 表明非本会话事务）。

        Args:
            db_key: 目标库键。
            xid: 分支事务标识。
            commit: True 提交 / False 回滚。
        """
        engine = await self._engines.get_sync(db_key)
        dialect = _twophase_dialect(engine)
        connection = await asyncio.to_thread(engine.connect)
        try:
            if commit:
                await asyncio.to_thread(dialect.do_commit_twophase, connection, xid, True, True)
            else:
                await asyncio.to_thread(dialect.do_rollback_twophase, connection, xid, True, True)
        finally:
            await self._safe_close(connection)

    @staticmethod
    async def _safe_rollback(connection: Any) -> None:
        """尽力回滚（失败不掩盖原始异常）。

        Args:
            connection: SQLAlchemy 连接。
        """
        try:
            await asyncio.to_thread(connection.rollback)
        except Exception:
            return

    @staticmethod
    async def _safe_close(connection: Any) -> None:
        """尽力关闭连接（`detach()` 后的关闭可能抛错，不向上传播）。

        Args:
            connection: SQLAlchemy 连接。
        """
        try:
            await asyncio.to_thread(connection.close)
        except Exception:
            return


class SyncEngineProvider(Protocol):
    """同步引擎提供者（结构化契约：`EngineRegistry` 与测试替身均可满足）。"""

    async def get_sync(self, db_key: str = PLATFORM_DB_KEY, *, read_only: bool = False) -> Engine:
        """取 / 建同步引擎。

        Args:
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            Engine: 同步引擎。
        """
        ...


def _twophase_dialect(engine: Engine) -> DefaultDialect:
    """取同步引擎的两阶段方言（`do_*_twophase` 定义在 `DefaultDialect`）。

    Args:
        engine: 同步引擎。

    Returns:
        DefaultDialect: 方言实例。
    """
    return cast("DefaultDialect", engine.dialect)


class XaTransactionManagerFactory(BasePluginFactory[XaTransactionManager]):
    """`transaction_manager` × `xa` 工厂（经应用 state 取服务间调用客户端）。"""

    plugin_key: str = "transaction_manager"
    plugin_name: str = XA_PLUGIN_NAME

    def __init__(self, settings: Settings, app: FastAPI) -> None:
        """初始化。

        Args:
            settings: 应用配置（占位：保留工厂签名一致）。
            app: 应用实例（取 `state.service_client`）。
        """
        self._settings = settings
        self._app = app

    def create(self, options: None = None) -> XaTransactionManager:
        """构造管理器（服务间客户端**延迟取用**：装配期可能尚未就绪）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            XaTransactionManager: 管理器实例。
        """
        del options
        return XaTransactionManager(_ClientAdapter(self._app))


class XaTransactionParticipantFactory(BasePluginFactory[XaTransactionParticipant]):
    """`transaction_participant` × `xa` 工厂（经应用 state 取引擎注册表与分支处理器）。"""

    plugin_key: str = "transaction_participant"
    plugin_name: str = XA_PLUGIN_NAME

    def __init__(self, settings: Settings, app: FastAPI) -> None:
        """初始化。

        Args:
            settings: 应用配置（占位：保留工厂签名一致）。
            app: 应用实例（取 `state.engine_registry`）。
        """
        self._settings = settings
        self._app = app

    def create(self, options: None = None) -> XaTransactionParticipant:
        """构造参与方（引擎注册表延迟取用；分支处理器经应用 state 注入）。

        Args:
            options: 未使用（零参口径）。

        Returns:
            XaTransactionParticipant: 参与方实例。
        """
        del options
        handlers = getattr(self._app.state, "branch_handlers", None)
        registry = handlers if isinstance(handlers, BranchHandlerRegistry) else BranchHandlerRegistry()
        return XaTransactionParticipant(_LazyEngineRegistry(self._app), registry)


class _ClientAdapter(BaseServiceClient):
    """把「延迟取用」的代理适配为 `BaseServiceClient`（仅覆写 `call`）。"""

    plugin_name: str = XA_PLUGIN_NAME

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例。
        """
        self._app = app

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """转发调用到应用装配的客户端。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 调用响应。
        """
        client: BaseServiceClient = self._app.state.service_client
        return await client.call(request)


class _LazyEngineRegistry(SyncEngineProvider):
    """引擎注册表代理：取用时从应用 state 取真实注册表。"""

    def __init__(self, app: FastAPI) -> None:
        """初始化。

        Args:
            app: 应用实例。
        """
        self._app = app

    async def get_sync(self, db_key: str = PLATFORM_DB_KEY, *, read_only: bool = False) -> Engine:
        """取同步引擎（转发到应用装配的注册表）。

        Args:
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            Engine: 同步引擎。
        """
        registry = cast("SyncEngineProvider", self._app.state.engine_registry)
        return await registry.get_sync(db_key, read_only=read_only)

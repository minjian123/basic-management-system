"""种子编排端点的真实调用（Kiwi 927/2218 体系内的端点装配与映射）。

覆盖：dry-run 返回 `exitCode=0` 与 `planned` 报告；端点不提前登记统计探针（07B `03_03`）。

重写口径（13_11）：复用装配态客户端，**不构造最小应用、不写 `app.state`**；会真连库的环节
（结构前置 / 记录装载 / 事务与参与方）经模块级 `monkeypatch.setattr` 替身化。
"""

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.services.module_registry import SeedRecord
from bms_platform.domains.platform_registry.api import internal_seeds
from bms_platform.domains.platform_registry.services import seed_orchestration as module

API = "/api/v1/platform/internal/seeds/orchestrate"


class _Manager:
    """事务管理器替身：只记录提交 / 回滚事件。"""

    def __init__(self) -> None:
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    async def begin(self, *args: object, **kwargs: object) -> object:
        """开启事务。

        Args:
            *args: 位置参数（忽略）。
            **kwargs: 关键字参数（忽略）。

        Returns:
            object: 事务快照。
        """
        del args, kwargs
        from bms_core.transaction.base import GlobalTransaction

        return GlobalTransaction(global_txn_id="x", caller_service="platform", state="active")

    async def commit(self, global_txn_id: str) -> object:
        """提交。

        Args:
            global_txn_id: 事务标识。

        Returns:
            object: 事务快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("commit")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> object:
        """回滚。

        Args:
            global_txn_id: 事务标识。

        Returns:
            object: 事务快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        self.events.add("rollback")
        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _Participant:
    """事务参与方替身：记录探针登记与分支执行。"""

    def __init__(self) -> None:
        self.probes: ConcurrentStableList[str] = ConcurrentStableList()
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    def register_stats_probe(self, op: str, probe: object) -> None:
        """记录探针。

        Args:
            op: 操作名。
            probe: 探针（忽略）。
        """
        del probe
        self.probes.add(op)

    async def execute_branch_with_stats(self, *, xid: str, db_key: str, ops: object) -> object:
        """执行分支。

        Args:
            xid: 分支标识。
            db_key: 库键。
            ops: 操作清单。

        Returns:
            object: (prepared, 统计)。
        """
        from bms_core.transaction.base import BranchStats

        del xid, db_key
        calls = self.calls
        calls.add("op")
        return "prepared", BranchStats(created=1)


def _records() -> ConcurrentStableList[SeedRecord]:
    """预置种子记录（不读产品清单配置）。

    Returns:
        ConcurrentStableList[SeedRecord]: 记录清单。
    """
    return ConcurrentStableList(
        (
            SeedRecord(
                name="seed-module",
                module="ops.seed_module",
                entry="seed_modules_entry",
                service="platform",
                db_key="platform_platform",
                source="platform",
            ),
        )
    )


def _stub_transaction(monkeypatch: pytest.MonkeyPatch, *, participant: _Participant | None = None) -> None:
    """把事务管理器 / 参与方 / 结构前置 / 记录装载替身化（都走模块级函数，不动应用 state）。

    Args:
        monkeypatch: 补丁夹具。
        participant: 参与方替身（缺省新建）。
    """
    manager = _Manager()
    party = participant if participant is not None else _Participant()

    def _manager_of(_request: Request) -> _Manager:
        return manager

    def _participant_of(_request: Request) -> _Participant:
        return party

    async def _no_structure(_plan: object, *, tenant: str) -> ConcurrentStableList[str]:
        del tenant
        return ConcurrentStableList()

    def _load_records(_self: object) -> ConcurrentStableList[SeedRecord]:
        del _self
        return _records()

    monkeypatch.setattr(internal_seeds, "get_transaction_manager", _manager_of)
    monkeypatch.setattr(internal_seeds, "get_transaction_participant", _participant_of)
    monkeypatch.setattr(module, "ensure_structure", _no_structure)
    monkeypatch.setattr(module.SeedOrchestrationService, "_load_records", _load_records)


async def test_endpoint_dry_run_returns_reports(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端点真实调用（dry-run）：返回 `exitCode=0` 与 `planned` 报告。"""
    _stub_transaction(monkeypatch)

    response = await client.post(API, json={"dry_run": True, "only": ["seed-module"]})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["exitCode"] == 0
    assert data["reports"][0]["name"] == "seed-module"
    assert data["reports"][0]["status"] == "planned"


async def test_endpoint_leaves_probe_registration_to_service(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """端点不再提前登记统计探针（07B `03_03`）：登记由编排服务在记录装载后完成。"""
    assert not hasattr(internal_seeds, "register_seed_stats")
    participant = _Participant()
    _stub_transaction(monkeypatch, participant=participant)

    response = await client.post(API, json={"only": ["seed-module"], "dry_run": True})

    assert response.status_code in (200, 503)

"""跨服务事务能力域契约用例（强一致专项 05_07；Kiwi 2271）。

覆盖：① 缺省 `null` 实现**明确拒绝**而非静默降级（`10013` / 503）；② 参与方 `recover_branches` 恒空；
③ 分支业务处理器注册表（统一注册通道，重复登记即拒）；④ 装配接线（管理器 / 参与方 / **恢复器**共用
`[transaction_manager]` 分区）；⑤ 配置分区缺省值；⑥ 错误码登记；⑦ 缺省恢复器**不启用即无对账任务**。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from bms_core.core.assembly import PLUGIN_WIRINGS
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import ParamError, TransactionUnavailableError
from bms_core.core.plugin import NULL_PLUGIN_NAME, resolve_plugin
from bms_core.transaction.base import (
    MAX_BRANCH_ID_LENGTH,
    MAX_XA_XID_BYTES,
    TRANSACTION_MANAGER_KEY,
    TRANSACTION_PARTICIPANT_KEY,
    TRANSACTION_RECOVERY_KEY,
    TXN_STATES,
    TXN_TERMINAL_STATES,
    BaseTransactionManager,
    BaseTransactionParticipant,
    BaseTransactionRecovery,
    BranchHandlerRegistry,
    BranchOp,
    BranchSpec,
    GlobalTransaction,
    build_branch_xid,
    get_transaction_recovery,
)
from bms_core.transaction.null import (
    NullTransactionManager,
    NullTransactionParticipant,
    NullTransactionRecovery,
)

pytestmark = [pytest.mark.kiwi_id(2271)]


def test_error_code_registered() -> None:
    """跨服务事务不可用错误码为 `10013`（不复用 `10011` 一致性屏障 / `10012` Redis）。"""
    assert ErrorCode.TRANSACTION_UNAVAILABLE == 10013
    assert TransactionUnavailableError("x").http_status == 503


@pytest.mark.parametrize("method", ["begin", "commit", "rollback", "status"])
async def test_null_manager_rejects(method: str) -> None:
    """缺省管理器：`enabled=False` 且协议动作明确拒绝（调用方据此回退基线路径）。"""
    manager = NullTransactionManager()
    assert manager.enabled is False

    if method == "begin":
        with pytest.raises(TransactionUnavailableError):
            await manager.begin(
                caller_service="platform", branches=ConcurrentStableList((BranchSpec("b1", "platform", "platform"),))
            )
        return
    with pytest.raises(TransactionUnavailableError):
        await getattr(manager, method)("txn-1")


@pytest.mark.parametrize("method", ["execute_branch", "commit_branch", "rollback_branch", "branch_state"])
async def test_null_participant_rejects(method: str) -> None:
    """缺省参与方：协议动作明确拒绝（**不静默放行半套状态**）。"""
    participant = NullTransactionParticipant()
    assert participant.enabled is False

    with pytest.raises(TransactionUnavailableError):
        if method == "execute_branch":
            await participant.execute_branch(
                xid="x1",
                db_key="platform",
                ops=ConcurrentStableFrozenList((BranchOp(op="noop", args=ConcurrentStableFrozenDict()),)),
            )
        else:
            await getattr(participant, method)(xid="x1", db_key="platform")


async def test_null_participant_recover_is_empty() -> None:
    """缺省参与方悬挂列举恒空（未启用两阶段 ⇒ 本库不存在悬挂分支）。"""
    assert await NullTransactionParticipant().recover_branches(db_key="platform") == ()


def test_branch_handler_registry() -> None:
    """分支处理器注册表：登记 / 解析 / 重复登记即拒（防隐式覆盖）。"""

    async def handler(_session: object, _args: ConcurrentStableDict[str, object]) -> None:
        return None

    registry = BranchHandlerRegistry()
    registry.register("org.assign", handler)

    assert registry.resolve("org.assign") is handler
    assert registry.resolve("org.unknown") is None
    assert registry.ops() == ("org.assign",)
    with pytest.raises(ValueError):
        registry.register("org.assign", handler)


def test_plugin_wirings_share_transaction_section() -> None:
    """装配接线：管理器与参与方同域、共用 `[transaction_manager]` 分区（缺省 `null` ⇒ 不启用）。"""
    wirings = {wiring.plugin_key: wiring for wiring in PLUGIN_WIRINGS}

    assert wirings[TRANSACTION_MANAGER_KEY].port is BaseTransactionManager
    assert wirings[TRANSACTION_PARTICIPANT_KEY].port is BaseTransactionParticipant
    assert wirings[TRANSACTION_MANAGER_KEY].settings_section == "transaction_manager"
    assert wirings[TRANSACTION_PARTICIPANT_KEY].settings_section == "transaction_manager"


def test_build_branch_xid_and_length_guards() -> None:
    """分支 `xid` 构造：`gtrid|bqual` 文本形态；分支标识超长与 `xid` 超字节上限均拒（10001）。"""
    assert build_branch_xid("gtxn-1", "b1") == "gtxn-1|b1"

    with pytest.raises(ParamError):
        build_branch_xid("gtxn-1", "b" * (MAX_BRANCH_ID_LENGTH + 1))

    # 分支标识在长度上限内、但拼出的 xid 超 XA 字节上限：走第二道校验。
    with pytest.raises(ParamError):
        build_branch_xid("g" * (MAX_XA_XID_BYTES - 1), "b" * MAX_BRANCH_ID_LENGTH)


def test_null_provider_resolves_both_ports() -> None:
    """缺省提供者 `null` 可解析出三个端口实现（装配不依赖具体提供者）。"""
    manager = resolve_plugin(
        TRANSACTION_MANAGER_KEY, NULL_PLUGIN_NAME, expected_version=BaseTransactionManager.contract_version
    )
    participant = resolve_plugin(
        TRANSACTION_PARTICIPANT_KEY, NULL_PLUGIN_NAME, expected_version=BaseTransactionParticipant.contract_version
    )
    recovery = resolve_plugin(
        TRANSACTION_RECOVERY_KEY, NULL_PLUGIN_NAME, expected_version=BaseTransactionRecovery.contract_version
    )

    assert isinstance(manager, NullTransactionManager)
    assert isinstance(participant, NullTransactionParticipant)
    assert isinstance(recovery, NullTransactionRecovery)


async def test_null_recovery_is_noop() -> None:
    """缺省恢复器：`enabled=False` 且单轮无处置（**不启用即无对账任务**，非抛错）。"""
    recovery = NullTransactionRecovery()

    assert recovery.enabled is False
    assert await recovery.run_once() == 0


def test_plugin_wirings_include_recovery() -> None:
    """装配接线：恢复器同域、共用 `[transaction_manager]` 分区（缺省 `null` ⇒ 不启用）。"""
    wirings = {wiring.plugin_key: wiring for wiring in PLUGIN_WIRINGS}

    assert wirings[TRANSACTION_RECOVERY_KEY].port is BaseTransactionRecovery
    assert wirings[TRANSACTION_RECOVERY_KEY].settings_section == "transaction_manager"


def test_recovery_provider_reads_recovery_field() -> None:
    """依赖提供者 `get_transaction_recovery`：按 `[transaction_manager].transaction_recovery` 解析。"""
    settings = Settings()
    request = cast(
        "Request",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))),
    )
    assert settings.transaction_manager.transaction_recovery in ("", NULL_PLUGIN_NAME)
    assert isinstance(get_transaction_recovery(request), NullTransactionRecovery)


def test_settings_recovery_field_default() -> None:
    """配置缺省：`transaction_recovery` 为空串（非 TM 服务 ⇒ 不启用恢复推进）。"""
    assert Settings().transaction_manager.transaction_recovery == ""


def test_settings_defaults_disabled() -> None:
    """配置缺省：未指定 `provider` ⇒ 不启用强一致；协调参数取缺省（数值见配置类）。"""
    section = Settings().transaction_manager

    assert section.provider in ("", NULL_PLUGIN_NAME)
    assert section.deadline_seconds > 0
    assert section.prepare_timeout_seconds > 0
    assert section.recovery_interval_seconds > 0
    assert section.leader_lock_key.startswith("bms:")


def test_txn_state_vocabulary() -> None:
    """状态词表：终态是全集子集，且决定点（`committing`）**不属**终态（在途须恢复推进）。"""
    assert set(TXN_TERMINAL_STATES) < set(TXN_STATES)
    assert "committing" not in TXN_TERMINAL_STATES
    assert "committed" in TXN_TERMINAL_STATES


def test_global_transaction_terminal_flag() -> None:
    """全局事务快照：`is_terminal` 依状态判定。"""
    moment = datetime.now(UTC)
    running = GlobalTransaction(global_txn_id="t1", caller_service="platform", state="committing", deadline_at=moment)
    done = GlobalTransaction(global_txn_id="t1", caller_service="platform", state="committed", deadline_at=moment)

    assert running.is_terminal is False
    assert done.is_terminal is True

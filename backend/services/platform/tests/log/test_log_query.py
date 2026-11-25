"""审计日志查询护栏（06_01）：时间范围 / 分片合并 / 筛选 / 详情定位 / 跨度上限。

单库叠加口径（《测试规范》§4）：查询接口按月份分片取数、**没有租户过滤**，故查询的模块 / 登录名
带命名空间派生，分页总数与筛选结果只断言本用例自造的行；「无台账」一类断言用远离真实数据的
时钟（2019）构造，不退化成「整表为空」。
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.config import AuditLogSettings
from bms_core.core.exceptions import (
    LoginLogNotFoundError,
    LogTimeRangeExceededError,
    OperationLogNotFoundError,
)
from bms_core.core.id_bits import EPOCH_MS, TIMESTAMP_SHIFT
from bms_core.testing.namespace import Namespace
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_platform.domains.log.services.query import LoginLogQueryService, OperationLogQueryService
from bms_platform.domains.log.services.writer import AuditLogWriter
from tests.log.helpers import DECEMBER, NOVEMBER, login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2407)


def _ops_module(ns: Namespace) -> str:
    """本用例操作日志的模块命名空间（分页总数与筛选都按它限定）。"""
    return ns.code("ops")


def _role_module(ns: Namespace) -> str:
    """角色模块命名空间（模块 + 动作联合筛选用）。"""
    return ns.code("role")


def _role_action(ns: Namespace) -> str:
    """角色动作命名空间（动作精确筛选用）。"""
    return ns.code("role-create")


def _settings(**overrides: object) -> AuditLogSettings:
    """构造审计日志参数（默认值同基线）。"""
    base: dict[str, object] = {  # bare-collections:allow（测试参数构造）
        "enabled": True,
        "record_methods": ["POST", "PUT", "PATCH", "DELETE"],
        "exclude_paths": [],
        "max_param_bytes": 8192,
        "query_default_days": 30,
        "max_query_days": 366,
        "precreate_months_ahead": 1,
        "chain_verify_months": 2,
    }
    base.update(overrides)
    return AuditLogSettings.model_validate(base)


async def _seed(session: AsyncSession, ns: Namespace) -> None:
    """两个月、两租户、两用户的操作日志 + 登录日志（模块 / 登录名带命名空间）。"""
    chain = Sha256HashChain()
    november = AuditLogWriter(session, chain, clock=lambda: NOVEMBER)
    december = AuditLogWriter(session, chain, clock=lambda: DECEMBER)
    assert await november.write(operation_event(ns.code("e1"), user_id="7", status=200, module=_ops_module(ns))) is True
    assert (
        await november.write(
            operation_event(
                ns.code("e2"),
                user_id="8",
                module=_role_module(ns),
                action=_role_action(ns),
            )
        )
        is True
    )
    assert (
        await december.write(
            operation_event(
                ns.code("e3"),
                user_id="7",
                status=500,
                tenant_id="2002",
                occurred_at=DECEMBER,
                module=_ops_module(ns),
            )
        )
        is True
    )
    assert await november.write(login_event(ns.code("l1"), username=ns.code("alice"))) is True
    assert await november.write(login_event(ns.code("l3"), username=ns.code("carol"), status="failed")) is True
    assert (
        await december.write(login_event(ns.code("l2"), username=ns.code("bob"), status="failed", occurred_at=DECEMBER))
        is True
    )
    await session.commit()


async def test_operation_page_filters_and_pagination(log_session: AsyncSession, ns: Namespace) -> None:
    """操作日志：时间范围跨月合并 / 用户与模块筛选 / 分页 total。"""
    await _seed(log_session, ns)
    service = OperationLogQueryService(log_session, _settings(), clock=lambda: DECEMBER)
    rows, total = await service.page(
        user_id=None,
        module=_ops_module(ns),
        action=None,
        status=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31, 23, 59),
        page=1,
        size=10,
    )
    assert total == 2
    assert len(rows) == 2
    assert rows[0]["tenant_id"] is not None

    only_user, count = await service.page(
        user_id=7,
        module=_ops_module(ns),
        action=None,
        status=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31),
        page=1,
        size=10,
    )
    assert count == 2
    assert {row["user_id"] for row in only_user} == {7}

    module_rows, module_total = await service.page(
        user_id=None,
        module=_role_module(ns),
        action=_role_action(ns),
        status=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31),
        page=1,
        size=10,
    )
    assert module_total == 1
    assert module_rows[0]["action"] == _role_action(ns)

    page2, _ = await service.page(
        user_id=None,
        module=_ops_module(ns),
        action=None,
        status=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31),
        page=2,
        size=1,
    )
    assert len(page2) == 1


async def test_single_shard_query(log_session: AsyncSession, ns: Namespace) -> None:
    """只有一个月分片时走单表查询分支（不构造 UNION）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(operation_event(ns.code("e1"), module=_ops_module(ns))) is True
    await log_session.commit()
    service = OperationLogQueryService(log_session, _settings(), clock=lambda: NOVEMBER)
    rows, total = await service.page(
        user_id=None,
        module=_ops_module(ns),
        action=None,
        status=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 11, 30),
        page=1,
        size=10,
    )
    assert total == 1
    assert len(rows) == 1


async def test_operation_default_range_and_status_filter(log_session: AsyncSession, ns: Namespace) -> None:
    """缺省范围回看 30 天；状态筛选生效。"""
    await _seed(log_session, ns)
    service = OperationLogQueryService(log_session, _settings(), clock=lambda: DECEMBER)
    rows, total = await service.page(
        user_id=None,
        module=_ops_module(ns),
        action=None,
        status=500,
        occurred_from=None,
        occurred_to=None,
        page=1,
        size=10,
    )
    assert total == 1
    assert rows[0]["status"] == 500


async def test_operation_detail_routing(log_session: AsyncSession, ns: Namespace) -> None:
    """详情：由雪花 ID 反解月份定位分片；不存在 / 无分片均 90201。"""
    await _seed(log_session, ns)
    repo = LogShardRepository(log_session)
    table = repo.table_for(LOG_TYPE_OPERATION, "202611")
    from sqlalchemy import select

    result = await log_session.execute(select(table.c.id).where(table.c.module == _ops_module(ns)).limit(1))
    record_id = int(result.scalar_one())
    service = OperationLogQueryService(log_session, _settings(), clock=lambda: DECEMBER)
    row = await service.detail(record_id)
    assert int(str(row["id"])) == record_id

    with pytest.raises(OperationLogNotFoundError):
        await service.detail(record_id + 1)
    with pytest.raises(OperationLogNotFoundError):
        await service.detail(1)


async def test_login_page_detail_and_filters(log_session: AsyncSession, ns: Namespace) -> None:
    """登录日志：用户名模糊 / 状态 / IP 筛选；详情含失败原因。"""
    await _seed(log_session, ns)
    service = LoginLogQueryService(log_session, _settings(), clock=lambda: DECEMBER)
    rows, total = await service.page(
        username=ns.prefix,
        status="success",
        ip="10.0.0.1",
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31),
        page=1,
        size=10,
    )
    assert total == 1
    assert rows[0]["username"] == ns.code("alice")

    _failed, failed_total = await service.page(
        username=ns.prefix,
        status="failed",
        ip=None,
        occurred_from=datetime(2026, 11, 1),
        occurred_to=datetime(2026, 12, 31),
        page=1,
        size=10,
    )
    assert failed_total == 2

    from sqlalchemy import select

    table = LogShardRepository.table_for(LOG_TYPE_LOGIN, "202611")
    result = await log_session.execute(select(table.c.id).where(table.c.username == ns.code("carol")).limit(1))
    record_id = int(result.scalar_one())
    row = await service.detail(record_id)
    assert row["fail_reason"] == "bad_credentials"
    with pytest.raises(LoginLogNotFoundError):
        await service.detail(record_id + 1)


async def test_range_guards_and_empty_ledger(log_session: AsyncSession, ns: Namespace) -> None:
    """时间跨度上限 / 起止倒置；无台账时返回空页（时钟取在无任何写入的年份）。"""

    def _empty_clock() -> datetime:
        """时钟取在无任何写入的年份（构造「无台账」分支，不依赖整表为空）。"""
        return datetime(2019, 1, 5)

    service = OperationLogQueryService(log_session, _settings(max_query_days=30), clock=_empty_clock)
    with pytest.raises(LogTimeRangeExceededError):
        await service.page(
            user_id=None,
            module=None,
            action=None,
            status=None,
            occurred_from=datetime(2018, 1, 1),
            occurred_to=datetime(2018, 12, 31),
            page=1,
            size=10,
        )
    with pytest.raises(LogTimeRangeExceededError):
        await service.page(
            user_id=None,
            module=None,
            action=None,
            status=None,
            occurred_from=datetime(2018, 12, 31),
            occurred_to=datetime(2018, 12, 1),
            page=1,
            size=10,
        )
    rows, total = await service.page(
        user_id=None,
        module=None,
        action=None,
        status=None,
        occurred_from=None,
        occurred_to=None,
        page=1,
        size=10,
    )
    assert (list(rows), total) == ([], 0)

    # 只给起始时间：结束时间取当前时钟
    only_from, only_from_total = await service.page(
        user_id=None,
        module=None,
        action=None,
        status=None,
        occurred_from=datetime(2018, 12, 20),
        occurred_to=None,
        page=1,
        size=10,
    )
    assert (list(only_from), only_from_total) == ([], 0)

    # 详情：目标月份无分片 → 90301
    future_ms = int(datetime(2030, 1, 1).timestamp() * 1000)
    future_id = (future_ms - EPOCH_MS) << TIMESTAMP_SHIFT
    login_service = LoginLogQueryService(log_session, _settings(), clock=_empty_clock)
    with pytest.raises(LoginLogNotFoundError):
        await login_service.detail(future_id)

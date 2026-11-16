"""数据变更审计 API 护栏（06_02）：列表 / 详情 / 链校验（直接调用路由函数）。"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.audit.helpers import NOVEMBER, data_event

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shard_repository import LogShardRepository
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT, month_key
from bms_core.core.exceptions import DataAuditLogNotFoundError, LogTimeRangeExceededError
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.audit.api import chain as chain_api
from bms_platform.domains.audit.api import data_changes as data_api
from bms_platform.domains.log.services.writer import AuditLogWriter

pytestmark = pytest.mark.kiwi_id(2515)


async def _seed(session: AsyncSession) -> None:
    """按固定时钟写两条数据变更审计记录。"""
    writer = AuditLogWriter(session, Sha256HashChain(), clock=lambda: datetime.now(UTC).replace(tzinfo=None))
    assert await writer.write(data_event("a1", occurred_at=datetime.now(UTC).replace(tzinfo=None))) is True
    assert (
        await writer.write(
            data_event(
                "a2",
                field="code",
                old_value="r1",
                new_value="r2",
                operator_id="8",
                occurred_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        is True
    )
    await session.commit()


async def test_list_filters_and_detail(log_session: AsyncSession) -> None:
    """列表按表名 / 字段 / 操作人筛选；详情含链字段；不存在 90401。"""
    await _seed(log_session)
    page = BasePageQuery()
    all_rows = await data_api.list_data_changes(
        session=log_session,
        page=page,
        table_name=None,
        record_id=None,
        operator_id=None,
        domain_key=None,
        field=None,
        occurred_from=None,
        occurred_to=None,
    )
    assert all_rows.data is not None
    assert all_rows.data.total == 2

    by_field = await data_api.list_data_changes(
        session=log_session,
        page=page,
        table_name="sys_role",
        record_id=None,
        operator_id=8,
        domain_key="role",
        field="code",
        occurred_from=None,
        occurred_to=None,
    )
    assert by_field.data is not None
    assert by_field.data.total == 1
    item = by_field.data.list[0]
    assert item.old_value == "r1"
    assert item.new_value == "r2"
    assert item.record_hash

    detail = await data_api.get_data_change(session=log_session, record_id=item.id)
    assert detail.data is not None
    assert detail.data.prev_hash
    with pytest.raises(DataAuditLogNotFoundError):
        await data_api.get_data_change(session=log_session, record_id=123456789012345678)


async def test_time_range_guard(log_session: AsyncSession) -> None:
    """跨度超上限按参数非法（90203）。"""
    await _seed(log_session)
    too_wide_from = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=400)
    with pytest.raises(LogTimeRangeExceededError):
        await data_api.list_data_changes(
            session=log_session,
            page=BasePageQuery(),
            table_name=None,
            record_id=None,
            operator_id=None,
            domain_key=None,
            field=None,
            occurred_from=too_wide_from,
            occurred_to=None,
        )


async def test_chain_verify_endpoint(log_session: AsyncSession) -> None:
    """链校验端点：正常返回 valid；篡改后同形返回断裂定位。"""
    await _seed(log_session)
    ok = await chain_api.verify_data_audit_chain(session=log_session, chain=Sha256HashChain(), months=None)
    assert ok.data is not None
    assert ok.data.valid is True
    assert ok.data.checked_records == 2
    assert ok.data.log_type == LOG_TYPE_DATA_AUDIT

    table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(NOVEMBER))
    current_month = month_key(datetime.now(UTC).replace(tzinfo=None))
    table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, current_month)
    await log_session.execute(update(table).values(record_hash="f" * 64))
    await log_session.commit()
    broken = await chain_api.verify_data_audit_chain(session=log_session, chain=Sha256HashChain(), months=current_month)
    assert broken.data is not None
    assert broken.data.valid is False
    assert broken.data.broken_month == current_month


def test_parse_months() -> None:
    """月份参数：逗号分隔解析；空串返回 None。"""
    assert chain_api.parse_months(None) is None
    assert chain_api.parse_months("  ") is None
    parsed = chain_api.parse_months("202611,202612")
    assert parsed is not None
    assert list(parsed) == ["202611", "202612"]

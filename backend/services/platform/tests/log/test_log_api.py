"""审计日志 API 层护栏（06_01）：查询 / 详情 / 内部校验 / 分片预创建（直接调用路由函数）。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.exceptions import ParamError
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.log.api import internal_audit
from bms_platform.domains.log.api import logs as logs_api
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_platform.domains.log.schemas.log import EnsureShardsRequest, VerifyRequest
from bms_platform.domains.log.services.writer import AuditLogWriter
from tests.log.helpers import login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2407)


async def _seed(session: AsyncSession) -> None:
    """按真实时钟写一条操作日志与一条登录日志（当前月分片）。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    writer = AuditLogWriter(session, Sha256HashChain(), clock=lambda: now)
    assert await writer.write(operation_event("e1", occurred_at=now)) is True
    assert await writer.write(login_event("l1", occurred_at=now)) is True
    await session.commit()


async def test_query_and_detail_route_functions(log_session: AsyncSession) -> None:
    """查询 / 详情：出参分页与详情字段完整；雪花 ID JSON 序列化为字符串。"""
    await _seed(log_session)
    page = BasePageQuery()
    operations = await logs_api.list_operation_logs(
        session=log_session,
        page=page,
        user_id=7,
        module=None,
        action=None,
        status=None,
        occurred_from=None,
        occurred_to=None,
    )
    assert operations.code == 0
    assert operations.data is not None
    assert operations.data.total == 1
    item = operations.data.list[0]
    assert item.action == "user:create"
    assert '"id":"' in item.model_dump_json()

    detail = await logs_api.get_operation_log(session=log_session, record_id=item.id)
    assert detail.data is not None
    assert detail.data.record_hash

    logins = await logs_api.list_login_logs(
        session=log_session,
        page=page,
        username="ali",
        status="success",
        ip=None,
        occurred_from=None,
        occurred_to=None,
    )
    assert logins.data is not None
    assert logins.data.total == 1
    login_item = logins.data.list[0]
    assert login_item.username == "alice"
    login_detail = await logs_api.get_login_log(session=log_session, record_id=login_item.id)
    assert login_detail.data is not None
    assert login_detail.data.status == "success"


async def test_internal_verify_route(log_session: AsyncSession) -> None:
    """内部校验端点：两类日志通过；未知类型 10001。"""
    await _seed(log_session)
    chain = Sha256HashChain()
    operation = await internal_audit.verify_chain(
        session=log_session, chain=chain, req=VerifyRequest(log_type=LOG_TYPE_OPERATION)
    )
    assert operation.data is not None
    assert operation.data.valid is True
    assert operation.data.checked_records == 1
    login = await internal_audit.verify_chain(
        session=log_session, chain=chain, req=VerifyRequest(log_type=LOG_TYPE_LOGIN)
    )
    assert login.data is not None
    assert login.data.valid is True
    with pytest.raises(ParamError):
        await internal_audit.verify_chain(session=log_session, chain=chain, req=VerifyRequest(log_type="unknown"))


async def test_internal_ensure_shards(log_session: AsyncSession) -> None:
    """分片预创建端点：当月 + 未来 N 月两类日志分片齐备。"""
    result = await internal_audit.ensure_shards(session=log_session, req=EnsureShardsRequest(months_ahead=1))
    assert result.data is not None
    assert len(result.data.months) == 2
    repo = LogShardRepository(log_session)
    for month in result.data.months:
        assert month in await repo.months(LOG_TYPE_OPERATION)
        assert month in await repo.months(LOG_TYPE_LOGIN)
    table = repo.table_for(LOG_TYPE_OPERATION, next(iter(result.data.months)))
    assert (await log_session.execute(select(table.c.id).limit(1))).first() is None

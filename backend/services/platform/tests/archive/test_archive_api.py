"""归档管理接口：路由函数行为与未授权门禁。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.exceptions import (
    ArchiveDataNotFoundError,
    ArchiveDestroyConfirmRequiredError,
    ArchivePolicyDisabledError,
    ArchivePolicyDuplicateError,
)
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.archive.api import data as data_api
from bms_platform.domains.archive.api import logs as logs_api
from bms_platform.domains.archive.api import policies as policies_api
from bms_platform.domains.archive.schemas.archive import (
    ArchiveDataDestroyRequest,
    ArchiveDataQuery,
    ArchiveLogDestroyRequest,
    ArchivePolicyCreateRequest,
    ArchivePolicyUpdateRequest,
)
from tests.archive.helpers import FakeStorage, new_pair, utc

pytestmark = [pytest.mark.kiwi_id(2516)]


class _Checker:
    """权限检查器替身（审计管理员：跨租户）。"""

    def check(self, code: str) -> bool:
        return code == "log:query"


@pytest.fixture
async def platform_session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """平台库会话（附带归档库）。"""
    platform, archive, platform_engine, archive_engine = await new_pair(tmp_path)
    try:
        yield platform
    finally:
        await platform.close()
        await archive.close()
        await platform_engine.dispose()
        await archive_engine.dispose()


async def test_authenticated_without_permission_is_forbidden(client: AsyncClient) -> None:
    """未授予 archive:* 的已登录用户：403。"""
    response = await client.get("/api/v1/archive/policies", params={"page": 1, "size": 10})
    assert response.status_code == 403


async def _reset(session: AsyncSession) -> None:
    """结束隐式只读事务（直调路由时模拟每请求独立会话）。"""
    if session.in_transaction():
        await session.rollback()


async def test_policy_routes(platform_session: AsyncSession) -> None:
    """策略路由：新增 / 列表 / 修改 / 重复 / 停用触发 / 删除。"""
    uow = DbUnitOfWork(platform_session)
    payload = ArchivePolicyCreateRequest(
        table_name="sys_table_ownership",
        time_field="created_at",
        threshold_days=30,
        retention_days=10,
        target="archive_db",
        batch_size=10,
        require_chain=False,
        remark="接口测试",
    )
    created = await policies_api.create_policy(payload, uow)
    assert created.code == 0
    policy_id = int(created.data.id)  # type: ignore[union-attr]

    listed = await policies_api.list_policies(uow, BasePageQuery(), None, None)
    assert listed.data.total == 1  # type: ignore[union-attr]

    await _reset(platform_session)
    with pytest.raises(ArchivePolicyDuplicateError):
        await policies_api.create_policy(payload, uow)

    await _reset(platform_session)
    updated = await policies_api.update_policy(
        policy_id,
        ArchivePolicyUpdateRequest(status="disabled", version=created.data.version),  # type: ignore[union-attr]
        uow,
    )
    assert updated.code == 0

    await _reset(platform_session)
    with pytest.raises(ArchivePolicyDisabledError):
        await policies_api.trigger_policy(policy_id, uow, None)

    await _reset(platform_session)
    enabled = await policies_api.update_policy(
        policy_id,
        ArchivePolicyUpdateRequest(status="enabled", version=updated.data.version),  # type: ignore[union-attr]
        uow,
    )
    assert enabled.code == 0
    await _reset(platform_session)
    triggered = await policies_api.trigger_policy(policy_id, uow, "api-test-key")
    assert triggered.code == 0

    await _reset(platform_session)
    off = await policies_api.update_policy(
        policy_id,
        ArchivePolicyUpdateRequest(status="disabled", version=enabled.data.version),  # type: ignore[union-attr]
        uow,
    )
    assert off.code == 0
    await _reset(platform_session)
    deleted = await policies_api.delete_policy(policy_id, uow)
    assert deleted.code == 0


async def test_log_and_data_routes(tmp_path: Path) -> None:
    """执行记录 / 数据查询 / 下载 / 销毁路由的错误分支。"""
    platform, archive, platform_engine, archive_engine = await new_pair(tmp_path)
    try:
        uow = DbUnitOfWork(platform)
        storage = FakeStorage()
        logs = await logs_api.list_logs(platform, storage, BasePageQuery(), None, None, None, None, None, None)
        assert logs.data.total == 0  # type: ignore[union-attr]

        with pytest.raises(ArchiveDataNotFoundError):
            await logs_api.get_log(999, platform, storage)
        with pytest.raises(ArchiveDataNotFoundError):
            await logs_api.download(999, platform, storage)
        await _reset(platform)
        with pytest.raises(ArchiveDestroyConfirmRequiredError):
            await logs_api.destroy_log(999, ArchiveLogDestroyRequest(confirm=False), uow, storage)

        queried = await data_api.query_data(
            archive,
            storage,
            _Checker(),
            BasePageQuery(),
            source_table=ArchiveDataQuery().source_table,
            source_id=None,
            source_month=None,
            tenant_id=None,
            stored_from=utc(2026, 1),
            stored_to=utc(2026, 12),
        )
        assert queried.data.total == 0  # type: ignore[union-attr]

        await _reset(platform)
        with pytest.raises(ArchiveDestroyConfirmRequiredError):
            await data_api.destroy_data(
                ArchiveDataDestroyRequest(source_table="sys_operation_log", source_id="1", confirm=False),
                uow,
                archive,
                storage,
            )
    finally:
        await platform.close()
        await archive.close()
        await platform_engine.dispose()
        await archive_engine.dispose()

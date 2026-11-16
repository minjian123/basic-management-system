"""归档数据合规销毁（批次文件 / 单条归档行）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ArchiveDataNotFoundError,
    ArchiveDestroyConfirmRequiredError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_TARGET_DESTROY,
    SysArchiveLog,
)
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.repositories.log import ArchiveLogRepository
from bms_platform.domains.archive.repositories.record import ArchiveRecordRepository
from bms_platform.domains.archive.services.cold import delete_cold_file

__all__ = ["ArchiveDisposeService"]


class ArchiveDisposeService(BaseFrameworkObject):
    """归档数据销毁服务（平台库留痕 + 归档库删行 + 对象存储删文件）。"""

    def __init__(
        self,
        platform_session: DbSession,
        archive_session: DbSession,
        *,
        storage: BaseObjectStorage,
        clock: datetime | None = None,
    ) -> None:
        """初始化。

        Args:
            platform_session: 平台库会话。
            archive_session: 归档库会话。
            storage: 对象存储。
            clock: 当前时刻（测试可注入）。
        """
        self._platform = platform_session
        self._archive = archive_session
        self._logs = ArchiveLogRepository(platform_session)
        self._records = ArchiveRecordRepository(archive_session)
        self._storage = storage
        self._clock = clock or _utc_now()

    async def destroy_log(self, log_id: int, *, confirm: bool, operator_id: int | None) -> SysArchiveLog:
        """销毁某批冷化文件（数据 + 清单）。

        Args:
            log_id: 执行记录主键。
            confirm: 二次确认。
            operator_id: 操作人。

        Returns:
            SysArchiveLog: 销毁留痕记录。

        Raises:
            ArchiveDestroyConfirmRequiredError: 未确认（93006）。
            ArchiveDataNotFoundError: 记录不存在 / 无文件 / 已处置（93005）。
        """
        if not confirm:
            raise ArchiveDestroyConfirmRequiredError("合规销毁须二次确认（confirm=true）")
        log = await self._logs.get(log_id)
        if log is None or log.file_key is None or log.disposed_at is not None:
            raise ArchiveDataNotFoundError("归档文件不存在（未冷化或已处置）")
        await delete_cold_file(self._storage, log.file_key)
        await self._logs.mark_disposed(log_id, dispose_type="destroy", now=self._clock)
        record = await self._new_log(
            policy_id=int(log.policy_id) if log.policy_id is not None else None,
            table_name=log.table_name,
            target=ARCHIVE_TARGET_DESTROY,
            tenant_id=log.tenant_id,
            operator_id=operator_id,
            file_key=log.file_key,
            detail=ConcurrentStableDict({"destroyed_log_id": str(log_id), "dispose_type": "destroy"}),
        )
        return record

    async def destroy_record(
        self, *, source_table: str, source_id: str, confirm: bool, operator_id: int | None
    ) -> SysArchiveLog:
        """销毁单条归档行。

        Args:
            source_table: 源逻辑表名。
            source_id: 源行主键。
            confirm: 二次确认。
            operator_id: 操作人。

        Returns:
            SysArchiveLog: 销毁留痕记录。

        Raises:
            ArchiveDestroyConfirmRequiredError: 未确认（93006）。
            ArchiveDataNotFoundError: 归档行不存在（93005）。
        """
        if not confirm:
            raise ArchiveDestroyConfirmRequiredError("合规销毁须二次确认（confirm=true）")
        record = await self._records.get_by_source(source_table, source_id)
        if record is None:
            raise ArchiveDataNotFoundError(f"归档数据不存在：{source_table}/{source_id}")
        policy_id = int(record.policy_id)
        tenant_id = record.tenant_id
        await self._records.delete_ids(ConcurrentStableList((int(record.id),)))
        await self._archive.commit()
        return await self._new_log(
            policy_id=policy_id,
            table_name=source_table,
            target=ARCHIVE_TARGET_DESTROY,
            tenant_id=tenant_id,
            operator_id=operator_id,
            file_key=None,
            detail=ConcurrentStableDict({"source_id": source_id, "dispose_type": "destroy"}),
        )

    async def _new_log(
        self,
        *,
        policy_id: int | None,
        table_name: str,
        target: str,
        tenant_id: int | None,
        operator_id: int | None,
        file_key: str | None,
        detail: ConcurrentStableDict[str, object],
    ) -> SysArchiveLog:
        """写一条销毁留痕记录（running → success）。"""
        now = self._clock
        tenant_part = "all" if tenant_id is None else str(tenant_id)
        log = SysArchiveLog(
            policy_id=policy_id,
            table_name=table_name,
            batch_key=f"{policy_id or 'none'}:{target}:{tenant_part}:{uuid4().hex}",
            target=target,
            tenant_id=tenant_id,
            archived_count=1,
            file_key=file_key,
            status=ARCHIVE_LOG_STATUS_RUNNING,
            started_at=now,
            operator_id=operator_id,
        )
        await self._logs.add(log)
        await self._logs.finish(
            int(log.id),
            status=ARCHIVE_LOG_STATUS_SUCCESS,
            finished_at=now,
            cost_time=0,
            archived_count=1,
            detail=json.dumps(dict(detail), ensure_ascii=False),
            file_key=file_key,
        )
        await self._platform.commit()
        return log


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)

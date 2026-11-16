"""归档数据查询 / 执行记录 / 冷化文件取回服务。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ArchiveDataNotFoundError, ArchiveQueryRangeExceededError, ParamError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import SysArchiveLog, SysArchiveRecord
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.repositories.log import ArchiveLogRepository
from bms_platform.domains.archive.repositories.record import ArchiveRecordRepository
from bms_platform.domains.archive.schemas.archive import ArchiveDataQuery, PresignedDownload

__all__ = ["ArchiveQueryService"]


class ArchiveQueryService(BaseFrameworkObject):
    """归档只读查询（平台库取记录 / 归档库取数据）。"""

    def __init__(
        self,
        platform_session: DbSession,
        archive_session: DbSession,
        *,
        settings: Settings,
        storage: BaseObjectStorage,
        clock: datetime | None = None,
    ) -> None:
        """初始化。

        Args:
            platform_session: 平台库会话。
            archive_session: 归档库会话。
            settings: 应用配置。
            storage: 对象存储（预签名取回）。
            clock: 当前时刻（测试可注入）。
        """
        self._logs = ArchiveLogRepository(platform_session)
        self._records = ArchiveRecordRepository(archive_session)
        self._settings = settings
        self._storage = storage
        self._clock = clock or _utc_now()

    async def list_logs(
        self,
        *,
        page: int,
        size: int,
        policy_id: int | None = None,
        table_name: str | None = None,
        target: str | None = None,
        status: str | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> tuple[ConcurrentStableList[SysArchiveLog], int]:
        """分页查询执行记录。

        Args:
            page: 页码。
            size: 每页条数。
            policy_id: 策略筛选。
            table_name: 表名筛选。
            target: 目标筛选。
            status: 状态筛选。
            started_from: 开始时间下限（UTC）。
            started_to: 开始时间上限（UTC）。

        Returns:
            tuple[ConcurrentStableList[SysArchiveLog], int]: （当前页, 总数）。
        """
        return await self._logs.page(
            page=page,
            size=size,
            policy_id=policy_id,
            table_name=table_name,
            target=target,
            status=status,
            started_from=started_from,
            started_to=started_to,
        )

    async def get_log(self, log_id: int) -> SysArchiveLog:
        """取执行记录详情。

        Args:
            log_id: 记录主键。

        Returns:
            SysArchiveLog: 执行记录。

        Raises:
            ArchiveDataNotFoundError: 记录不存在（93005）。
        """
        log = await self._logs.get(log_id)
        if log is None:
            raise ArchiveDataNotFoundError(f"归档执行记录不存在：{log_id}")
        return log

    async def query_data(
        self,
        query: ArchiveDataQuery,
        *,
        page: int,
        size: int,
        allow_cross_tenant: bool,
    ) -> tuple[ConcurrentStableList[SysArchiveRecord], int]:
        """查询归档数据（只查归档库）。

        Args:
            query: 筛选条件。
            page: 页码。
            size: 每页条数。
            allow_cross_tenant: 是否允许跨租户（审计管理员）。

        Returns:
            tuple[ConcurrentStableList[SysArchiveRecord], int]: （当前页, 总数）。

        Raises:
            ArchiveQueryRangeExceededError: 时间跨度超限（93008）。
            ParamError: 普通用户缺少租户上下文。
        """
        stored_from, stored_to = self._resolve_window(query)
        tenant_id = self._resolve_tenant(query.tenant_id, allow_cross_tenant=allow_cross_tenant)
        return await self._records.page(
            page=page,
            size=size,
            source_table=query.source_table,
            source_id=query.source_id,
            source_month=query.source_month,
            tenant_id=tenant_id,
            stored_from=stored_from,
            stored_to=stored_to,
        )

    async def download(self, log_id: int) -> PresignedDownload:
        """为冷化文件生成预签名下载地址。

        Args:
            log_id: 执行记录主键。

        Returns:
            PresignedDownload: 预签名结果。

        Raises:
            ArchiveDataNotFoundError: 记录不存在 / 无冷化文件 / 已处置（93005）。
        """
        log = await self.get_log(log_id)
        if log.file_key is None or log.disposed_at is not None:
            raise ArchiveDataNotFoundError("归档文件不存在（未冷化或已处置）")
        presigned = await self._storage.presign(log.file_key)
        return PresignedDownload(
            url=presigned.url,
            expires_in=presigned.expires_in,
            method=presigned.method,
            file_key=log.file_key,
        )

    def decode(self, record: SysArchiveRecord) -> ConcurrentStableDict[str, object]:
        """把归档行载荷反序列化为对象。

        Args:
            record: 归档行。

        Returns:
            ConcurrentStableDict[str, object]: 源行字段。
        """
        try:
            loaded = json.loads(record.payload)
        except json.JSONDecodeError:  # pragma: no cover - 写入侧保证合法 JSON
            return ConcurrentStableDict()
        if not isinstance(loaded, dict):  # pragma: no cover - 写入侧保证对象
            return ConcurrentStableDict()
        return ConcurrentStableDict({str(key): value for key, value in cast("dict[str, object]", loaded).items()})

    def _resolve_window(self, query: ArchiveDataQuery) -> tuple[datetime, datetime]:
        """收敛查询时间窗（缺省回看 / 最大跨度）。"""
        to = query.stored_to or self._clock
        start = query.stored_from or (to - timedelta(days=self._settings.archive_options.query_default_days))
        if start > to:
            raise ParamError("归档查询起始时间不得晚于结束时间")
        if (to - start).days > self._settings.archive_options.query_max_days:
            raise ArchiveQueryRangeExceededError(
                f"归档查询时间范围过大（上限 {self._settings.archive_options.query_max_days} 天）"
            )
        return start, to

    def _resolve_tenant(self, requested: int | None, *, allow_cross_tenant: bool) -> int | None:
        """解析租户过滤（普通用户强制本租户；审计管理员可跨租户）。"""
        if allow_cross_tenant:
            return requested
        current = get_current_tenant_id()
        if not current:
            raise ParamError("缺少租户上下文，无法查询归档数据")
        return int(current)


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)

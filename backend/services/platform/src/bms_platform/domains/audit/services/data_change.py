"""数据变更审计查询与链校验服务（06_02）。

- **范围收敛**：走基座 `resolve_query_range`（与操作 / 登录日志同一口径：缺省回看
  `[audit_log].query_default_days`、跨度上限 `max_query_days`、超限 `90203`）。
- **分片路由**：取台账中落在 `[起始月-1, 结束月+1]` 的 `data_audit` 分片，`UNION ALL` 查询。
- **详情**：由雪花 ID 反解写入月份定位单一分片；台账无该分片 / 记录不存在 → `90401`。
- **链校验**：基座 `AuditChainVerifier` 对 `data_audit` 重算（与写入共用 `canonical_record`）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.query_range import resolve_query_range
from bms_core.audit.shard_repository import LogShardRepository
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT, month_key, month_shift, shard_of_id
from bms_core.audit.verifier import AuditChainVerifier, ChainVerifyOutcome
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import AuditLogSettings
from bms_core.core.exceptions import DataAuditLogNotFoundError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession

__all__ = ["DataChangeChainService", "DataChangeQueryService"]

_LOG_TYPE = LOG_TYPE_DATA_AUDIT


def _utc_now() -> datetime:
    """当前 UTC naive 时间。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class DataChangeQueryService(BaseFrameworkObject):
    """数据变更审计查询（列表 / 详情）。"""

    def __init__(
        self,
        session: DbSession,
        settings: AuditLogSettings,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """初始化。

        Args:
            session: 平台库只读会话。
            settings: 审计日志参数（`[audit_log]`；范围口径与操作 / 登录日志共用）。
            clock: 当前时钟（测试可注入）。
        """
        self._repo = LogShardRepository(session)
        self._settings = settings
        self._clock = clock

    async def page(
        self,
        *,
        table_name: str | None,
        record_id: int | None,
        operator_id: int | None,
        domain_key: str | None,
        field: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        page: int,
        size: int,
    ) -> tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]:
        """分页查询数据变更审计。

        Args:
            table_name: 被审计表名（精确）。
            record_id: 被审计记录主键（精确）。
            operator_id: 操作人主键（精确）。
            domain_key: 业务域（精确）。
            field: 变更字段名（精确）。
            occurred_from: 事件时间下界。
            occurred_to: 事件时间上界。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[ConcurrentStableDict[str, object]], int]: （当前页, 总数）。
        """
        start, end = resolve_query_range(self._settings, occurred_from, occurred_to, now=self._clock())
        months = await self._repo.months_between(
            _LOG_TYPE,
            month_shift(month_key(start), -1),
            month_shift(month_key(end), 1),
        )
        conditions: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "table_name": table_name,
                "record_id": record_id,
                "operator_id": operator_id,
                "domain_key": domain_key,
                "field": field,
            }
        )
        return await self._repo.page(
            _LOG_TYPE,
            months,
            conditions=conditions,
            fuzzy=ConcurrentStableDict[str, str](),
            occurred_from=start,
            occurred_to=end,
            offset=(page - 1) * size,
            limit=size,
        )

    async def detail(self, record_id: int) -> ConcurrentStableDict[str, object]:
        """按主键取单条（定位单一分片）。

        Args:
            record_id: 主键（雪花 ID）。

        Returns:
            ConcurrentStableDict[str, object]: 行值。

        Raises:
            DataAuditLogNotFoundError: 分片 / 记录不存在（90401）。
        """
        month = shard_of_id(record_id)
        months = await self._repo.months_between(_LOG_TYPE, month, month)
        if not months:
            raise DataAuditLogNotFoundError()
        row = await self._repo.get(_LOG_TYPE, month, record_id)
        if row is None:
            raise DataAuditLogNotFoundError()
        return row


class DataChangeChainService(BaseFrameworkObject):
    """数据变更审计链校验（复用基座校验器，只校验 `data_audit` 一类）。"""

    def __init__(self, session: DbSession, hash_chain: BaseHashChain) -> None:
        """初始化。

        Args:
            session: 平台库只读会话。
            hash_chain: 哈希链实现。
        """
        self._verifier = AuditChainVerifier(session, hash_chain)

    async def verify(self, months: ConcurrentStableList[str] | None = None) -> ChainVerifyOutcome:
        """校验数据变更审计链完整性。

        Args:
            months: 指定月份（None = 台账全部月份）。

        Returns:
            ChainVerifyOutcome: 校验结果（含断裂定位）。
        """
        return await self._verifier.verify(_LOG_TYPE, months)

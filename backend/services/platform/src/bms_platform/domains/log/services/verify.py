"""审计链校验服务：按分片逐条重算并定位断裂（06_01）。

- **口径**：与写入共用 `canonical_record`（字段集合 / 值形态固定），`record_hash = SHA256(prev_hash + 规范化记录)`。
- **跨月衔接**：按月份升序维护每个租户的链尾；每月首条 `prev_hash` 必须等于更早分片同租户末条
  （无则 `GENESIS_HASH`）。
- **定位**：返回首个断裂的月份 / 序号（该月内从 0 起）/ 记录 ID，供告警与人工核查。
- **性能**：当前实现按分片整月加载（审计量级与 90 天热表可控）；大数据量游标分批归 15_01。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bms_core.audit.hashchain import GENESIS_HASH, BaseHashChain
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, canonical_record

__all__ = ["AuditChainVerifier", "ChainVerifyOutcome"]


@dataclass(frozen=True)
class ChainVerifyOutcome(BaseValueObject):
    """链校验结果（断裂定位）。"""

    valid: bool
    """链是否完整。"""

    checked_months: ConcurrentStableList[str]
    """实际校验的月份。"""

    checked_records: int
    """校验的记录数。"""

    broken_month: str | None = None
    """断裂分片月份（完整为 None）。"""

    broken_index: int | None = None
    """断裂位置（该月内从 0 起）。"""

    broken_record_id: int | None = None
    """断裂记录主键。"""


class AuditChainVerifier(BaseFrameworkObject):
    """审计链校验器（操作 / 登录共用）。"""

    def __init__(self, session: DbSession, hash_chain: BaseHashChain) -> None:
        """初始化。

        Args:
            session: 平台库只读会话。
            hash_chain: 哈希链实现。
        """
        self._repo = LogShardRepository(session)
        self._session = session
        self._chain = hash_chain

    async def verify(self, log_type: str, months: ConcurrentStableList[str] | None = None) -> ChainVerifyOutcome:
        """校验某类日志的链完整性。

        Args:
            log_type: 日志类型（`operation` / `login`）。
            months: 指定月份（None = 台账全部月份）。

        Returns:
            ChainVerifyOutcome: 校验结果。
        """
        available = await self._repo.months(log_type)
        targets = (
            available if months is None else ConcurrentStableList(month for month in available if month in set(months))
        )
        last_by_tenant = await self._tails_before(log_type, targets[0]) if targets else ConcurrentStableDict[str, str]()
        checked = 0
        for month in targets:
            table = self._repo.table_for(log_type, month)
            result = await self._session.execute(select(table).order_by(table.c.id))
            for index, row in enumerate(result.mappings().all()):
                values = ConcurrentStableDict(dict(row))
                tenant_key = "global" if values.get("tenant_id") is None else str(values["tenant_id"])
                expected_prev = last_by_tenant.get(tenant_key, GENESIS_HASH)
                if values.get("prev_hash") != expected_prev:
                    return self._broken(month, index, values, targets, checked)
                expected_hash = self._chain.compute(expected_prev, canonical_record(log_type, values))
                if values.get("record_hash") != expected_hash:
                    return self._broken(month, index, values, targets, checked)
                last_by_tenant[tenant_key] = str(values["record_hash"])
                checked += 1
        return ChainVerifyOutcome(valid=True, checked_months=targets, checked_records=checked)

    async def _tails_before(self, log_type: str, month: str) -> ConcurrentStableDict[str, str]:
        """取指定月份之前各租户的链尾（只更新状态，不参与计数 / 校验）。

        Args:
            log_type: 日志类型。
            month: 目标起始月份（不含）。

        Returns:
            ConcurrentStableDict[str, str]: 租户键 → 链尾哈希。
        """
        tails: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        for earlier in await self._repo.months(log_type):  # pragma: no branch - 台账非空才会走到本方法
            if earlier >= month:
                break
            table = self._repo.table_for(log_type, earlier)
            result = await self._session.execute(select(table).order_by(table.c.id))
            for row in result.mappings().all():
                values = ConcurrentStableDict(dict(row))
                tenant_key = "global" if values.get("tenant_id") is None else str(values["tenant_id"])
                tails[tenant_key] = str(values["record_hash"])
        return tails

    @staticmethod
    def _broken(
        month: str,
        index: int,
        values: ConcurrentStableDict[str, object],
        months: ConcurrentStableList[str],
        checked: int,
    ) -> ChainVerifyOutcome:
        """构造断裂结果。"""
        record_id = values.get("id")
        return ChainVerifyOutcome(
            valid=False,
            checked_months=months,
            checked_records=checked,
            broken_month=month,
            broken_index=index,
            broken_record_id=int(str(record_id)) if record_id is not None else None,
        )


LOG_TYPES = ConcurrentStableList((LOG_TYPE_OPERATION, LOG_TYPE_LOGIN))
"""可校验的日志类型（供端点缺省全量校验）。"""

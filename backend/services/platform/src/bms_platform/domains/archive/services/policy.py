"""归档策略服务：校验、CRUD、执行中互斥。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm.exc import StaleDataError

from bms_core.audit.shards import LOGIC_TABLES
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    ArchivePolicyDuplicateError,
    ArchivePolicyRunningError,
    ParamError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.base import Base
from bms_core.models.platform.archive import (
    ARCHIVE_POLICY_STATUS_DISABLED,
    ARCHIVE_POLICY_STATUS_ENABLED,
    ARCHIVE_TARGET_ARCHIVE_DB,
    ARCHIVE_TARGETS,
    SysArchivePolicy,
)
from bms_core.services.table_registry import table_record
from bms_platform.domains.archive.repositories.log import ArchiveLogRepository
from bms_platform.domains.archive.repositories.policy import ArchivePolicyRepository
from bms_platform.domains.archive.schemas.archive import ArchivePolicyCreateRequest, ArchivePolicyUpdateRequest

__all__ = ["AUDIT_SHARD_TABLES", "ArchivePolicyService"]

AUDIT_SHARD_TABLES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {table_name: log_type for log_type, table_name in LOGIC_TABLES.items()}
)
"""审计分片逻辑表 → 日志类型（整月归档特批表）。"""


class ArchivePolicyService(BaseFrameworkObject):
    """归档策略服务（平台库会话；事务由 API 工作单元负责）。"""

    def __init__(self, session: DbSession, settings: Settings) -> None:
        """初始化。

        Args:
            session: 平台库会话。
            settings: 应用配置（取批次缺省 / 上限）。
        """
        self._session = session
        self._settings = settings
        self._policies = ArchivePolicyRepository(session)
        self._logs = ArchiveLogRepository(session)

    async def create(self, request: ArchivePolicyCreateRequest) -> SysArchivePolicy:
        """新增策略。

        Args:
            request: 新增请求。

        Returns:
            SysArchivePolicy: 已 flush 的策略。

        Raises:
            ArchivePolicyDuplicateError: 同表已有在用策略（93001）。
            ParamError: 表 / 字段 / 目标 / 批次校验不通过。
        """
        batch_size = request.batch_size or self._settings.archive_options.batch_size_default
        await self._validate(
            table_name=request.table_name,
            time_field=request.time_field,
            target=request.target,
            require_chain=request.require_chain,
            batch_size=batch_size,
        )
        if await self._policies.by_table(request.table_name) is not None:
            raise ArchivePolicyDuplicateError(f"归档策略已存在：{request.table_name}")
        policy = SysArchivePolicy(
            table_name=request.table_name,
            time_field=request.time_field,
            threshold_days=request.threshold_days,
            retention_days=request.retention_days,
            target=request.target,
            batch_size=batch_size,
            status=request.status,
            require_chain=request.require_chain,
            remark=request.remark,
        )
        self._policies.add(policy)
        try:
            await self._session.flush()
        except StaleDataError as exc:  # pragma: no cover - 新增路径不会触发乐观锁
            raise ArchivePolicyDuplicateError("归档策略写入冲突") from exc
        return policy

    async def update(self, policy_id: int, request: ArchivePolicyUpdateRequest) -> SysArchivePolicy:
        """修改策略。

        Args:
            policy_id: 策略主键。
            request: 修改请求（乐观锁 `version` 必填）。

        Returns:
            SysArchivePolicy: 更新后的策略。

        Raises:
            ArchiveDataNotFoundError: 策略不存在。
            ArchivePolicyRunningError: 策略执行中（93002）。
            ParamError: 校验不通过。
        """
        policy = await self._require(policy_id)
        if await self._logs.running(policy_id):
            raise ArchivePolicyRunningError("策略执行中，暂不可修改")
        if request.version != policy.version:
            from bms_core.core.exceptions import ConcurrentConflictError

            raise ConcurrentConflictError("归档策略已被其他操作修改，请刷新后重试")
        time_field = request.time_field or policy.time_field
        target = request.target or policy.target
        batch_size = request.batch_size or policy.batch_size
        require_chain = policy.require_chain if request.require_chain is None else request.require_chain
        status = request.status or policy.status
        if status not in (ARCHIVE_POLICY_STATUS_ENABLED, ARCHIVE_POLICY_STATUS_DISABLED):
            raise ParamError(f"非法策略状态：{status}")
        await self._validate(
            table_name=policy.table_name,
            time_field=time_field,
            target=target,
            require_chain=require_chain,
            batch_size=batch_size,
        )
        policy.time_field = time_field
        policy.threshold_days = request.threshold_days if request.threshold_days is not None else policy.threshold_days
        policy.retention_days = request.retention_days if request.retention_days is not None else policy.retention_days
        policy.target = target
        policy.batch_size = batch_size
        policy.status = status
        policy.require_chain = require_chain
        if request.remark is not None:
            policy.remark = request.remark
        await self._session.flush()
        return policy

    async def delete(self, policy_id: int) -> None:
        """删除策略（仅停用且未执行中；软删）。

        Args:
            policy_id: 策略主键。

        Raises:
            ArchiveDataNotFoundError: 策略不存在。
            ArchivePolicyRunningError: 策略执行中（93002）。
            ParamError: 策略未停用。
        """
        policy = await self._require(policy_id)
        if await self._logs.running(policy_id):
            raise ArchivePolicyRunningError("策略执行中，暂不可删除")
        if policy.status != ARCHIVE_POLICY_STATUS_DISABLED:
            raise ParamError("仅停用的归档策略可删除")
        policy.soft_delete()
        await self._session.flush()

    async def list(
        self,
        *,
        page: int,
        size: int,
        table_name: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableDict[str, object], ConcurrentStableList[SysArchivePolicy]]:
        """分页查询策略。

        Args:
            page: 页码。
            size: 每页条数。
            table_name: 表名筛选。
            status: 状态筛选。

        Returns:
            tuple[ConcurrentStableDict[str, object], ConcurrentStableList[SysArchivePolicy]]: （分页元数据, 当前页）。
        """
        rows, total = await self._policies.page(page=page, size=size, table_name=table_name, status=status)
        return ConcurrentStableDict({"page": page, "size": size, "total": total}), rows

    async def _require(self, policy_id: int) -> SysArchivePolicy:
        """取策略，不存在抛 93005。"""
        from bms_core.core.exceptions import ArchiveDataNotFoundError

        policy = await self._policies.get(policy_id)
        if policy is None:
            raise ArchiveDataNotFoundError(f"归档策略不存在：{policy_id}")
        return policy

    async def _validate(
        self,
        *,
        table_name: str,
        time_field: str,
        target: str,
        require_chain: bool,
        batch_size: int,
    ) -> None:
        """校验策略指向的表 / 字段 / 目标 / 批次。

        Args:
            table_name: 逻辑表名。
            time_field: 时间字段。
            target: 归档目标。
            require_chain: 是否强制链校验。
            batch_size: 单批条数。

        Raises:
            ParamError: 任一条件不满足。
        """
        if target not in ARCHIVE_TARGETS:
            raise ParamError(f"非法归档目标：{target}（允许 {', '.join(ARCHIVE_TARGETS)}）")
        if batch_size < 1 or batch_size > self._settings.archive_options.max_batch_rows:
            raise ParamError(f"归档批次须在 1 ~ {self._settings.archive_options.max_batch_rows} 之间")
        record = table_record(table_name)
        if record is None or record.datasource != "platform" or record.owner != "platform":
            raise ParamError(f"仅支持平台库已登记表：{table_name}")
        log_type = AUDIT_SHARD_TABLES.get(table_name)
        if log_type is not None:
            if time_field != "occurred_at":
                raise ParamError("审计分片表的归档时间字段固定为 occurred_at")
            if target != ARCHIVE_TARGET_ARCHIVE_DB:
                raise ParamError("审计分片表仅支持两段式归档（archive_db）")
            if not require_chain:
                raise ParamError("审计分片表必须开启哈希链校验（require_chain=true）")
            return
        if record.status != "enabled":
            raise ParamError(f"表尚未定稿，不可归档：{table_name}")
        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise ParamError(f"表无 ORM 模型，不可归档：{table_name}")
        column = table.columns.get(time_field)
        if column is None:
            raise ParamError(f"时间字段不存在：{table_name}.{time_field}")
        if not isinstance(column.type, DateTime):
            raise ParamError(f"时间字段必须为时间类型：{table_name}.{time_field}")


def utc_now() -> datetime:
    """当前 UTC naive 时间（服务层统一口径）。

    Returns:
        datetime: 当前时刻。
    """
    from datetime import UTC

    return datetime.now(UTC).replace(tzinfo=None)

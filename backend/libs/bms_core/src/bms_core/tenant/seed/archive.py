"""归档策略种子：内置审计日志 90 天归档策略（幂等 upsert，按 `table_name` 对账）。

- 三类审计日志（操作 / 登录 / 字段级变更）随平台库种子入库，默认 90 天阈值、归档库保留 180 天、
  两段式归档、强制链校验；
- 开放接口日志（`sys_open_log`）当前尚无表 / 模型，策略随开放接口任务接入后追加（14_01 开放项）；
- 幂等：按 `table_name` 命中即校正阈值 / 保留期 / 目标 / 批次 / 链校验开关 / 备注，不覆盖启停状态。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import (
    ARCHIVE_POLICY_STATUS_ENABLED,
    ARCHIVE_TARGET_ARCHIVE_DB,
    SysArchivePolicy,
)

__all__ = ["ARCHIVE_POLICY_SEEDS", "ArchivePolicySeed", "seed_archive_policies_entry"]


@dataclass(frozen=True)
class ArchivePolicySeed(BaseValueObject):
    """单条归档策略种子。"""

    table_name: str
    time_field: str
    threshold_days: int
    retention_days: int
    target: str
    batch_size: int
    require_chain: bool
    remark: str


ARCHIVE_POLICY_SEEDS: ConcurrentStableList[ArchivePolicySeed] = ConcurrentStableList(
    (
        ArchivePolicySeed(
            table_name="sys_operation_log",
            time_field="occurred_at",
            threshold_days=90,
            retention_days=180,
            target=ARCHIVE_TARGET_ARCHIVE_DB,
            batch_size=1000,
            require_chain=True,
            remark="操作日志 90 天归档（链校验后整月迁出）",
        ),
        ArchivePolicySeed(
            table_name="sys_login_log",
            time_field="occurred_at",
            threshold_days=90,
            retention_days=180,
            target=ARCHIVE_TARGET_ARCHIVE_DB,
            batch_size=1000,
            require_chain=True,
            remark="登录日志 90 天归档（链校验后整月迁出）",
        ),
        ArchivePolicySeed(
            table_name="sys_data_audit_log",
            time_field="occurred_at",
            threshold_days=90,
            retention_days=180,
            target=ARCHIVE_TARGET_ARCHIVE_DB,
            batch_size=1000,
            require_chain=True,
            remark="字段级变更审计 90 天归档（链校验后整月迁出）",
        ),
    )
)
"""内置归档策略（四类审计日志中的三类；开放接口日志待表落地后追加）。"""


async def seed_archive_policies_entry(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
    """写入 / 校正内置归档策略（幂等）。

    Args:
        session: 平台库会话（编排层负责事务）。
        args: 种子参数（保留位；当前未使用）。
    """
    _ = args
    for seed in ARCHIVE_POLICY_SEEDS:
        existing = (
            (
                await session.execute(
                    select(SysArchivePolicy).where(
                        SysArchivePolicy.table_name == seed.table_name,
                        SysArchivePolicy.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            session.add(
                SysArchivePolicy(
                    table_name=seed.table_name,
                    time_field=seed.time_field,
                    threshold_days=seed.threshold_days,
                    retention_days=seed.retention_days,
                    target=seed.target,
                    batch_size=seed.batch_size,
                    status=ARCHIVE_POLICY_STATUS_ENABLED,
                    require_chain=seed.require_chain,
                    remark=seed.remark,
                )
            )
            continue
        existing.time_field = seed.time_field
        existing.threshold_days = seed.threshold_days
        existing.retention_days = seed.retention_days
        existing.target = seed.target
        existing.batch_size = seed.batch_size
        existing.require_chain = seed.require_chain
        existing.remark = seed.remark
    await session.flush()

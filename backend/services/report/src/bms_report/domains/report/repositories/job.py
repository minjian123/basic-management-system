"""报表域作业记录仓储：过期打印作业的读取 / 更晚引用判定 / 产物过期标记（04_03）。

- 读侧只碰 `sys_job`（作业记录与产物 key 同库，不跨库）；
- **事务边界归调用方**：本仓储只 `flush` 不 `commit`；
- **不在事务外读 ORM 属性**：`list_succeeded_before` 在会话活跃期内把行解析成不可变
  `JobArtifact`（回滚 / 关会话后读 ORM 属性会触发 `MissingGreenlet`，且会盖掉原始异常）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseValueObject
from bms_core.models.job import JOB_STATUS_SUCCEEDED, SysJob
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["JobArtifact", "PrintJobRepository"]

_EXPIRED_FIELD = "expired_at"
"""`sys_job.result` 里表示「产物已清理」的时间字段。"""


@dataclass(frozen=True)
class JobArtifact(BaseValueObject):
    """过期打印作业的产物快照（会话内取值，事务外只用此对象）。"""

    job_id: int
    """作业主键。"""

    object_keys: ConcurrentStableList[str]
    """产物对象 key（已去重；空集合表示该作业未记产物）。"""

    expired: bool
    """是否已标记 `expired_at`（已标记只跳过，不重复删对象）。"""


class PrintJobRepository(BaseDbRepository[SysJob]):
    """打印作业读侧（租户库 / 平台库；作业与产物同库）。"""

    model = SysJob

    async def list_succeeded_before(
        self,
        job_type: str,
        before: datetime,
        *,
        limit: int,
        offset: int = 0,
    ) -> ConcurrentStableList[JobArtifact]:
        """按类型 + 成功终态 + 完成时间取过期作业的产物快照。

        过滤全部下推到 SQL（类型 / 状态 / 完成时间三列）；产物 key 的解析留在应用层
        （JSON 列跨方言语法不一致，不在 SQL 层解析）。

        Args:
            job_type: 作业类型。
            before: 完成时间上界（UTC naive；早于该时刻视为过期）。
            limit: 单批上限。
            offset: 偏移（分批推进；已标记的行仍会被扫到，由调用方按批推进）。

        Returns:
            ConcurrentStableList[JobArtifact]: 作业产物快照（按完成时间 / 主键升序）。
        """
        statement = (
            select(SysJob)
            .where(
                SysJob.job_type == job_type,
                SysJob.status == JOB_STATUS_SUCCEEDED,
                SysJob.finished_at.is_not(None),
                SysJob.finished_at < before,
            )
            .order_by(SysJob.finished_at.asc(), SysJob.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(
            JobArtifact(
                job_id=int(row.id),
                object_keys=object_keys_of(row.result),
                expired=is_expired(row.result),
            )
            for row in rows
        )

    async def has_newer_reference(self, job_type: str, object_key: str, *, after_job_id: int) -> bool:
        """判断是否存在「更晚且引用同一产物 key」的成功作业（重打覆盖的防误删判据）。

        比较基准用主键（雪花 ID 单调，是可靠全序；`finished_at` 可能同秒并列）。
        `contains(..., autoescape=True)` 自动转义 `%` / `_`，避免 key 里的下划线被当作通配符。

        Args:
            job_type: 作业类型。
            object_key: 产物对象 key（精确匹配 JSON 里的 `"object_key": "<key>"`）。
            after_job_id: 基准作业主键（只找比它更新的作业）。

        Returns:
            bool: 存在更晚引用返回 True。
        """
        statement = (
            select(SysJob.id)
            .where(
                SysJob.job_type == job_type,
                SysJob.status == JOB_STATUS_SUCCEEDED,
                SysJob.id > after_job_id,
                SysJob.result.contains(f'"{object_key}"', autoescape=True),
            )
            .limit(1)
        )
        return (await self._session.execute(statement)).first() is not None

    async def mark_expired(self, job_id: int) -> bool:
        """在作业结果上追加 `expired_at`（已标记则原样返回，不重复写）。

        Args:
            job_id: 作业主键。

        Returns:
            bool: 本次写入返回 True；作业不存在或已标记返回 False。
        """
        record = await self.get(job_id)
        if record is None:
            return False
        raw = record.result
        if is_expired(raw):
            return False
        record.result = with_expired(raw)
        await self._session.flush()
        return True


def object_keys_of(raw: str | None) -> ConcurrentStableList[str]:
    """从作业结果里取产物 key 集合（去重；无 `items` 返回空集合）。

    Args:
        raw: `sys_job.result` 文本。

    Returns:
        ConcurrentStableList[str]: 产物对象 key（保持结果内顺序）。
    """
    keys: ConcurrentStableList[str] = ConcurrentStableList()
    loaded = _parse_object(raw)
    items = loaded.get("items")
    if not isinstance(items, list):
        return keys
    seen: ConcurrentStableSet[str] = ConcurrentStableSet()
    for item in cast("list[object]", items):
        if not isinstance(item, dict):
            continue
        payload = cast("dict[str, object]", item)
        key = payload.get("object_key")
        if isinstance(key, str) and key and key not in seen:
            seen.add(key)
            keys.add(key)
    return keys


def is_expired(raw: str | None) -> bool:
    """结果里是否已标记 `expired_at`。

    Args:
        raw: 结果文本。

    Returns:
        bool: 已标记为 True。
    """
    return bool(_parse_object(raw).get(_EXPIRED_FIELD))


def with_expired(raw: str | None) -> str:
    """在结果 JSON 上追加 `expired_at`（已存在原样返回）。

    Args:
        raw: 原结果文本。

    Returns:
        str: 新结果文本。
    """
    parsed = _parse_object(raw)
    if parsed.get(_EXPIRED_FIELD):
        return raw or "{}"
    parsed.set(_EXPIRED_FIELD, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return json.dumps(dict(parsed), ensure_ascii=False)


def _parse_object(raw: str | None) -> ConcurrentStableDict[str, object]:
    """把结果文本解析为有序字典（空 / 非法 / 非对象一律返回空字典）。

    Args:
        raw: 结果文本。

    Returns:
        ConcurrentStableDict[str, object]: 解析结果。
    """
    parsed: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if not raw:
        return parsed
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return parsed
    if not isinstance(loaded, dict):
        return parsed
    for key, value in cast("dict[object, object]", loaded).items():
        parsed.set(str(key), value)
    return parsed

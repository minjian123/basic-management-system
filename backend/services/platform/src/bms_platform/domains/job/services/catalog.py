"""作业类型目录服务：声明投影写入（`sys_job_type`）与查询。

- 目录是 `[[jobs]]` 声明的**只读投影**：`content_hash` 未变不写，退役用 `status=retired` 表达（不删行）；
- 平台装载（启动钩子）与产品注册通道共用同一写入逻辑；
- 平台不手写产品记录。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.roots import BaseValueObject
from bms_core.jobs.spec import now_utc
from bms_core.models.platform.job import SysJobType
from bms_core.registry.products import JobDeclaration
from bms_platform.domains.job.repositories.job import JobTypeRepository

__all__ = ["JobCatalogService", "JobSyncReport", "declaration_hash"]


@dataclass(frozen=True)
class JobSyncReport(BaseValueObject):
    """目录同步结果。"""

    created: int = 0
    """新增条数。"""

    updated: int = 0
    """内容变更条数。"""

    unchanged: int = 0
    """内容未变条数。"""

    retired: int = 0
    """退役条数。"""


def declaration_hash(declaration: JobDeclaration) -> str:
    """计算声明要素稳定哈希（未变不写）。

    Args:
        declaration: 作业类型声明。

    Returns:
        str: 64 位十六进制哈希。
    """
    payload = {
        "job_type": declaration.job_type,
        "service": declaration.service,
        "domain": declaration.domain,
        "handler": declaration.handler,
        "description": declaration.description,
        "timeout_seconds": declaration.timeout_seconds,
        "max_attempts": declaration.max_attempts,
        "backoff_seconds": declaration.backoff_seconds,
        "concurrency": declaration.concurrency,
        "payload_version": declaration.payload_version,
        "status": declaration.status,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


class JobCatalogService(BaseFrameworkObject):
    """作业类型目录读写（事务边界由调用方开启）。"""

    def __init__(self, repository: JobTypeRepository) -> None:
        """初始化。

        Args:
            repository: 类型目录仓储。
        """
        self._repo = repository

    async def page(
        self, *, page: int, size: int, service_key: str | None = None, status: str | None = None
    ) -> tuple[ConcurrentStableList[object], int]:
        """分页查询类型目录。

        Args:
            page: 页码。
            size: 每页条数。
            service_key: 提供方服务筛选。
            status: 目录状态筛选。

        Returns:
            tuple[ConcurrentStableList[object], int]: （当页记录, 总数）。
        """
        rows, total = await self._repo.page_filtered(page=page, size=size, service_key=service_key, status=status)
        return ConcurrentStableList(rows), total

    async def sync(self, declarations: ConcurrentStableList[JobDeclaration], *, source: str) -> JobSyncReport:
        """同步声明到目录（同事务内完成）。

        Args:
            declarations: 声明清单。
            source: 声明来源（`platform` / `product`）。

        Returns:
            JobSyncReport: 同步结果。
        """
        now = now_utc()
        created = 0
        updated = 0
        unchanged = 0
        known: ConcurrentStableSet[str] = ConcurrentStableSet()
        for declaration in declarations:
            known.add(declaration.job_type)
            content_hash = declaration_hash(declaration)
            existing = await self._repo.get_by_type(declaration.job_type)
            values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
                {
                    "service_key": declaration.service,
                    "domain_key": declaration.domain,
                    "handler": declaration.handler,
                    "description": declaration.description,
                    "timeout_seconds": declaration.timeout_seconds,
                    "max_attempts": declaration.max_attempts,
                    "backoff_seconds": declaration.backoff_seconds,
                    "concurrency": declaration.concurrency,
                    "payload_version": declaration.payload_version,
                    "status": declaration.status,
                    "source": source,
                    "content_hash": content_hash,
                }
            )
            if existing is None:
                await self._repo.create_declaration(job_type=declaration.job_type, **dict(values))
                created += 1
                continue
            if existing.content_hash == content_hash and existing.status == declaration.status:
                unchanged += 1
                continue
            await self._repo.update_declaration(declaration.job_type, now=now, **dict(values))
            updated += 1
        retired = await self._repo.retire_missing(known_types=known, now=now)
        return JobSyncReport(created=created, updated=updated, unchanged=unchanged, retired=retired)

    async def list_all(self) -> ConcurrentStableList[SysJobType]:
        """取全部目录行（供缓存 / 诊断）。

        Returns:
            ConcurrentStableList[SysJobType]: 目录行。
        """
        return ConcurrentStableList(await self._repo.list_all())

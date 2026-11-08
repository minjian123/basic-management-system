"""租户物理清理编排（任务 `04_03-02`）：保留期回填 + 到期清理 + `tenant.purged`。

- **扫描**（`scan`）：同一轮先回填「归档已就绪但 `purge_at` 仍为空」的注销租户（从当下起算保留期），
  再取已到期租户作为清理目标；两段都只做只读 + 回填，真正删库在作业里做（失败互不影响）。
- **清理**（`purge`）：复核状态与到期 → 逐服务删租户库（单库失败不中断、记失败服务名）→
  全部成功才删 `sys_tenant_database` 对照行与 `sys_tenant` 注册行 → 同事务落 `tenant.purged` 与审计。
- **幂等**：注册行已不存在 / 已被恢复 / 未到期 → `skipped`，零副作用；重复执行不重复发事件。
- **失败不丢重试依据**：任一库删除失败即**不删注册行**，交作业框架重试（删库本身幂等：库不存在视为成功）。

清理留痕**不新增表**：作业执行记录 + `tenant.purged` 事件 + 审计日志（`sys.operation.logged`）三处。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from bms_core.audit.events import build_operation_event
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.plugin import NULL_PLUGIN_NAME
from bms_core.core.roots import BaseValueObject
from bms_core.db.admin import drop_database, resolve_target
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_tenant_db_key
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.models.tenant.tenant import TENANT_STATUS_DELETED
from bms_core.outbox.base import BaseOutboxStore
from bms_core.tenant.provisioning import enabled_tenant_services
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.services.tenant_admin import (
    DELETION_RETENTION_KEY,
    parse_retention_days,
)

__all__ = [
    "DEFAULT_PURGE_BATCH_SIZE",
    "PURGED_EVENT",
    "PurgeOutcome",
    "PurgeScanOutcome",
    "PurgeTarget",
    "TenantPurgeService",
]

PURGED_EVENT = "tenant.purged"
"""物理清理完成事件（独立 `1.0.0`；此刻才授权产品删数据）。"""

DEFAULT_PURGE_BATCH_SIZE = 50
"""单轮扫描批大小缺省值（作业负载可覆盖）。"""

_LOGGER = get_logger("bms.tenant_purge")


@dataclass(frozen=True)
class PurgeTarget(BaseValueObject):
    """待清理租户（扫描结果；作业提交用）。"""

    tenant_id: int
    """租户主键。"""

    code: str
    """租户编码（幂等键与日志定位用）。"""

    version: int
    """注册行版本戳（幂等键第三段：恢复后再注销会变，避免旧作业挡住新一次清理）。"""


@dataclass(frozen=True)
class PurgeScanOutcome(BaseValueObject):
    """扫描结果。"""

    backfilled: int = 0
    """本轮回填 `purge_at` 的租户数。"""

    targets: ConcurrentStableList[PurgeTarget] = field(default_factory=lambda: ConcurrentStableList[PurgeTarget]())
    """本轮到期需清理的租户（按到期时刻升序）。"""


@dataclass(frozen=True)
class PurgeOutcome(BaseValueObject):
    """单个租户的清理结果。"""

    status: str
    """结果：`purged`（已清理）/ `skipped`（无需清理）/ `failed`（有库删除失败）。"""

    reason: str = ""
    """跳过 / 失败原因（`missing` / `status=...` / `purge_at_empty` / `not_due` / 失败摘要）。"""

    db_basis: str = ""
    """库名基（删库定位；跳过且行不存在时为空）。"""

    dropped_services: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """已删库的服务标识（库不存在也算成功，`drop_database` 本身幂等）。"""

    failed_services: ConcurrentStableList[str] = field(default_factory=lambda: ConcurrentStableList[str]())
    """删除失败的服务标识（非空即整体失败，保留注册行待重试）。"""


ServicesProvider = Callable[[], ConcurrentStableList[str]]
"""服务清单提供者（缺省 `enabled_tenant_services`；测试注入受控清单）。"""

DropDatabase = Callable[[str, str], Awaitable[bool]]
"""删库执行器：`(service, db_basis)`（缺省按配置解析连接串后走运维通道 `drop_database`）。"""


class TenantPurgeService(BaseFrameworkObject):
    """租户物理清理编排（会话绑定；`purge` / `scan` 尾部自行提交事务）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        outbox: BaseOutboxStore,
        settings: Settings | None = None,
        services: ServicesProvider | None = None,
        drop: DropDatabase | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（注册行与发件箱所在库）。
            outbox: 事务性发件箱（`tenant.purged` 与审计同事务）。
            settings: 应用配置（判归档是否就绪、解析各服务租户库连接串）；None 表示未装配。
            services: 服务清单提供者（None 取服务目录已启用服务）。
            drop: 删库执行器（None 走运维通道 `drop_database`，需 `settings`）。
            clock: 时钟（测试注入固定 `now`，不用 sleep）。
        """
        self._session = session
        self._repo = TenantRegistryRepository(session)
        self._outbox = outbox
        self._settings = settings
        self._services = services
        self._drop = drop
        self._clock = clock if clock is not None else _utc_now

    async def scan(self, *, batch_size: int = DEFAULT_PURGE_BATCH_SIZE) -> PurgeScanOutcome:
        """扫描一轮：先回填保留期，再取到期租户（本方法不删库、不提交作业）。

        Args:
            batch_size: 单批上限（回填与到期各自取一批）。

        Returns:
            PurgeScanOutcome: 回填数与到期目标清单。
        """
        now = self._clock()
        backfilled = 0
        if self._archive_ready():
            retention = timedelta(days=await self._retention_days())
            for row in await self._repo.purge_pending(limit=batch_size):
                await self._repo.backfill_purge_at(row, purge_at=now + retention)
                backfilled += 1
                _LOGGER.info("tenant_purge_backfilled", tenant_id=int(row.id), purge_at=(now + retention).isoformat())
        targets: ConcurrentStableList[PurgeTarget] = ConcurrentStableList()
        for row in await self._repo.purge_due(now=now, limit=batch_size):
            targets.add(PurgeTarget(tenant_id=int(row.id), code=row.code, version=int(row.version)))
        await self._session.commit()
        return PurgeScanOutcome(backfilled=backfilled, targets=targets)

    async def purge(self, tenant_id: int) -> PurgeOutcome:
        """清理单个到期租户（逐库删 → 删注册行 → 落 `tenant.purged` 与审计）。

        Args:
            tenant_id: 租户主键。

        Returns:
            PurgeOutcome: 清理结果（`purged` / `skipped` / `failed`）。
        """
        started = time.monotonic()
        now = self._clock()
        row = await self._repo.by_id(tenant_id)
        if row is None:
            return PurgeOutcome(status="skipped", reason="missing")
        if row.status != TENANT_STATUS_DELETED:
            return PurgeOutcome(status="skipped", reason=f"status={row.status}")
        if row.purge_at is None:
            return PurgeOutcome(status="skipped", reason="purge_at_empty")
        if row.purge_at > now:
            return PurgeOutcome(status="skipped", reason="not_due")
        # 回滚 / 提交后 ORM 属性会过期，删行前先把要用的值取到局部量。
        basis = await self._repo.db_basis(tenant_id) or row.code
        code = row.code
        dropped, failed = await self._drop_all(basis)
        if failed:
            # 不删注册行：删库可能已部分成功，保留注册行才有重试依据（重跑幂等）。
            _LOGGER.warning(
                "tenant_purge_partial_failure",
                tenant_id=tenant_id,
                db_key=basis,
                dropped=len(dropped),
                failed=len(failed),
            )
            return PurgeOutcome(
                status="failed",
                reason="库删除失败：" + "、".join(failed),
                db_basis=basis,
                dropped_services=dropped,
                failed_services=failed,
            )
        await self._repo.purge_row(tenant_id)
        await self._enqueue_events(
            tenant_id=tenant_id,
            code=code,
            db_basis=basis,
            dropped=len(dropped),
            cost_time_ms=int((time.monotonic() - started) * 1000),
        )
        await self._session.commit()
        _LOGGER.info("tenant_purged", tenant_id=tenant_id, db_key=basis, dropped_services=len(dropped))
        return PurgeOutcome(status="purged", db_basis=basis, dropped_services=dropped)

    async def _drop_all(self, basis: str) -> tuple[ConcurrentStableList[str], ConcurrentStableList[str]]:
        """逐服务删租户库（单库失败不中断）。

        Args:
            basis: 租户库名基。

        Returns:
            tuple[ConcurrentStableList[str], ConcurrentStableList[str]]: （成功服务, 失败服务）。

        Raises:
            ConfigError: 既未注入删库执行器、也未装配应用配置（无法解析连接串，属装配错误）。
        """
        drop_one = self._resolve_drop()
        services = self._services() if self._services is not None else enabled_tenant_services()
        dropped: ConcurrentStableList[str] = ConcurrentStableList()
        failed: ConcurrentStableList[str] = ConcurrentStableList()
        for service in services:
            try:
                await drop_one(service, basis)
                dropped.add(service)
            except Exception as exc:  # 单库失败不中断：继续删其余库，失败清单交作业重试
                failed.add(service)
                _LOGGER.warning("tenant_purge_drop_failed", db_key=basis, service=service, error=type(exc).__name__)
        return dropped, failed

    def _resolve_drop(self) -> DropDatabase:
        """取删库执行器（注入优先，否则按配置走运维通道）。

        Returns:
            DropDatabase: `(service, db_basis)` 删库执行器。

        Raises:
            ConfigError: 既未注入执行器、也未装配应用配置。
        """
        if self._drop is not None:
            return self._drop
        if self._settings is None:
            raise ConfigError("清理作业未装配应用配置，无法解析各服务租户库连接串")
        # 清理要删**各服务**的租户库（不止本服务），故连接串解析须允许跨服务归属；
        # 只解析地址、不建业务引擎，删库仍走运维通道（与开通编排同口径）。
        factory = EngineFactory(self._settings, allow_cross_service=True)

        async def _ops_drop(service: str, db_basis: str) -> bool:
            return await drop_database(
                resolve_target(factory.resolved_url(build_tenant_db_key(db_basis, service=service)))
            )

        return _ops_drop

    async def _enqueue_events(
        self, *, tenant_id: int, code: str, db_basis: str, dropped: int, cost_time_ms: int
    ) -> None:
        """同事务落 `tenant.purged` 与审计（清理留痕三处中的两处，第三处是作业执行记录）。

        Args:
            tenant_id: 租户主键。
            code: 租户编码（聚合键，与既有租户事件一致按编码串行）。
            db_basis: 库名基。
            dropped: 已删库的服务数。
            cost_time_ms: 清理耗时（毫秒）。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "tenant_id": str(tenant_id),
                "db_key": db_basis,
                "status": "purged",
                "dropped_services": dropped,
                "failed_services": 0,
            }
        )
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=PURGED_EVENT,
                payload=payload,
                tenant_id=str(tenant_id),
                aggregate_key=code,
            ),
        )
        extensions: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"db_basis": db_basis, "dropped_services": dropped, "failed_services": 0}
        )
        await self._outbox.enqueue(
            self._session,
            build_operation_event(
                tenant_id=str(tenant_id),
                user_id=None,
                username="system",
                module="tenant",
                action="tenant:purge",
                method="JOB",
                path="job:tenant.purge",
                query=None,
                params=None,
                ip=None,
                user_agent=None,
                cost_time=cost_time_ms,
                status=200,
                error_msg=None,
                extensions=extensions,
            ),
        )

    async def _retention_days(self) -> int:
        """取保留期天数（平台库 `sys_config`；缺失 / 非法回落缺省 30）。

        Returns:
            int: 保留期天数（恒 > 0）。
        """
        return parse_retention_days(await self._repo.config_value(DELETION_RETENTION_KEY))

    def _archive_ready(self) -> bool:
        """归档能力是否就绪（provider 为空 / null 即未就绪，回填继续等待）。

        Returns:
            bool: 就绪为 True。
        """
        if self._settings is None:
            return False
        provider = self._settings.archive_policy.provider
        return provider not in ("", NULL_PLUGIN_NAME)


def _utc_now() -> datetime:
    """当前 UTC 时刻（与库内 DATETIME 同口径：naive UTC）。

    Returns:
        datetime: 当前 UTC 时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)

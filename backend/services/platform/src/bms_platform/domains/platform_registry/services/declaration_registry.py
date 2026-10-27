"""产品声明注册服务（07B `02_06`）：注册表落库 + 权威视图投影。

- **注册**（`register`）：校验 → 整体对账 → 落库 → 视图投影 → 返回逐类计数；冲突 / 校验不过即拒（fail-closed）；
- **快照**（`snapshot`）：把注册表现状按类别聚合，供服务身份出口下发（消费方启动期拉取）；
- **投影**（`project_registry`）：落库后按注册表快照**整体重建**进程内视图族（能力 / 服务行 / 种子 /
  错误码 / 使用声明等），使 `resolve_capability` 等取用入口无需感知来源变化，且退役项不会残留在视图；
- **授权基线**：注册只改声明；声明基线授权的落库仍由既有启动钩子（`02_04`）在注册之后统一重算。
"""

from typing import Any

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import CatalogError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.registry.declarations import (
    DECLARATION_KINDS,
    DeclarationPayload,
    DeclarationReport,
    RegistrySnapshot,
    plan_declarations,
    validate_declarations,
)
from bms_core.registry.projection import project_registry
from bms_core.services.module_registry import (
    domain_service_view,
    service_catalog_view,
)
from bms_platform.domains.platform_registry.repositories.declaration_repository import DeclarationRepository

__all__ = ["DeclarationRegistryService"]

_LOGGER = get_logger("bms.platform.declaration")
"""日志通道名。"""


class DeclarationRegistryService(BaseFrameworkObject):
    """注册表服务（会话绑定；事务边界由调用方负责）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 平台服务库会话（注册表所在库）。
        """
        self._session = session
        self._repo = DeclarationRepository(session)

    async def register(self, payload: DeclarationPayload) -> DeclarationReport:
        """执行一次全量注册（校验 → 对账 → 落库 → 投影）。

        Args:
            payload: 注册载荷（八类声明全集）。

        Returns:
            DeclarationReport: 逐类计数 + 警示（`snapshot_version` 为服务行数派生值）。

        Raises:
            CatalogError: 校验不过或跨产品撞键（拒绝注册，不写库）。
        """
        current = await self._repo.load_snapshot()
        warnings: ConcurrentStableList[str] = ConcurrentStableList()
        errors = validate_declarations(
            payload,
            current,
            domain_services=domain_service_view(),
            consumer_keys=self._consumer_keys(current, payload),
            warnings=warnings,
        )
        if errors:
            raise CatalogError(f"产品声明注册被拒（{payload.product_key}）：" + "；".join(errors))
        plan, conflicts = plan_declarations(payload, current)
        if conflicts:
            raise CatalogError(f"产品声明注册冲突（{payload.product_key}）：" + "；".join(conflicts))
        await self._repo.apply(plan, product_key=payload.product_key)
        # 投影按「注册表快照整体重建」：声明演进（同键换内容）与退役都能如实反映到视图，
        # 不走逐条增量（视图层的「同键异值即拒」不应为投影放宽）
        project_registry(await self._repo.load_snapshot())
        counts = plan.counts()
        _LOGGER.info(
            "declaration_registered",
            product_key=payload.product_key,
            service_key=payload.service_key,
            counts=dict(counts),
        )
        return DeclarationReport(
            product_key=payload.product_key,
            created=self._kind_counts(plan.created),
            updated=self._kind_counts(plan.updated),
            unchanged=self._kind_counts(plan.unchanged),
            retired=ConcurrentStableDict({kind: len(plan.retired.get(kind) or ()) for kind in DECLARATION_KINDS}),
            warnings=ConcurrentStableFrozenList(warnings),
            snapshot_version=str(len(service_catalog_view())),
        )

    async def snapshot(self) -> RegistrySnapshot:
        """取注册表全量现状（服务身份出口用）。

        Returns:
            RegistrySnapshot: 注册表现状（八类记录）。
        """
        return await self._repo.load_snapshot()

    @staticmethod
    def _kind_counts(records: ConcurrentStableDict[str, ConcurrentStableList[Any]]) -> ConcurrentStableDict[str, int]:
        """按类别统计条数。

        Args:
            records: `{类别: 记录列表}`。

        Returns:
            ConcurrentStableDict[str, int]: `{类别: 条数}`。
        """
        return ConcurrentStableDict({kind: len(records.get(kind) or ()) for kind in DECLARATION_KINDS})

    @staticmethod
    def _consumer_keys(current: RegistrySnapshot, payload: DeclarationPayload) -> ConcurrentStableSet[str]:
        """取可作默认消费方 / 使用声明方的标识集合（注册表现状 + 本次声明）。

        Args:
            current: 注册表现状。
            payload: 本次声明。

        Returns:
            ConcurrentStableSet[str]: 服务键与产品键集合。
        """
        keys: ConcurrentStableSet[str] = ConcurrentStableSet()
        for record in current.of("services"):
            if record.service_key:
                keys.add(str(record.service_key))
        for record in current.of("products"):
            keys.add(str(record.product_key))
        for record in payload.services:
            if record.service_key:
                keys.add(str(record.service_key))
        for record in payload.products:
            keys.add(str(record.product_key))
        keys.add(payload.product_key)
        keys.add(payload.service_key)
        return keys

"""回收站恢复服务：通用引擎 + 字段级审计 + 恢复后缓存失效。"""

from __future__ import annotations

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.audit.tables import is_audited_table
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableFrozenSet, ConcurrentStableList
from bms_core.core.config import RecycleSettings
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_id_str
from bms_core.help.cache import bump_content_version
from bms_core.recycle.engine import RecycleEngine
from bms_core.recycle.registry import recycle_spec_of
from bms_core.recycle.spec import RecycleRestoreOutcome
from bms_platform.services.metadata_cache import bump_metadata_version

__all__ = ["RecycleRestoreService"]

_LOGGER = get_logger("bms.platform.recycle")

_METADATA_MODULES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(("permission_meta", "form_design"))
"""恢复后需要递增元数据版本的模块（图标 / 表单定制；按模块键判定，不写死表名）。"""


class RecycleRestoreService(BaseFrameworkObject):
    """回收站恢复服务（事务边界由调用方工作单元开启）。"""

    def __init__(
        self,
        session: DbSession,
        settings: RecycleSettings,
        *,
        audit: AuditCapturer | None = None,
        cache: CacheRegion | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            settings: 回收站运行参数。
            audit: 字段级审计捕获器（None 不留痕）。
            cache: 缓存 Region（恢复后版本失效；None 不失效）。
        """
        self._engine = RecycleEngine(session, settings)
        self._audit = audit
        self._cache = cache

    async def restore(self, table_name: str, row_id: int) -> RecycleRestoreOutcome:
        """恢复单行并做留痕与缓存失效。

        Args:
            table_name: 逻辑表名。
            row_id: 主键。

        Returns:
            RecycleRestoreOutcome: 恢复结果。

        Raises:
            RecycleError: 未纳管 / 不存在 / 已恢复 / 唯一冲突（95001~95004）。
        """
        outcome = await self._engine.restore(table_name, row_id)
        self._audit_if_needed(outcome)
        await self._invalidate_cache(outcome.table)
        return outcome

    def _audit_if_needed(self, outcome: RecycleRestoreOutcome) -> None:
        """非白名单表显式留痕 `deleted_at`（白名单表已由 ORM 事件捕获）。"""
        if self._audit is None or is_audited_table(outcome.table):
            return
        try:
            self._audit.capture(
                table=outcome.table,
                model_id=outcome.id,
                changes=ConcurrentStableList((FieldChange(field="deleted_at", old=outcome.old_deleted_at, new=None),)),
            )
        except Exception as exc:  # 留痕失败不得反噬已提交的恢复
            _LOGGER.warning(
                "recycle_audit_capture_failed",
                table=outcome.table,
                row_id=str(outcome.id),
                error_type=type(exc).__name__,
            )

    async def _invalidate_cache(self, table_name: str) -> None:
        """按表族递增缓存版本（失败只告警，不回滚恢复）。"""
        if self._cache is None:
            return
        tenant = current_tenant_id_str()
        spec = recycle_spec_of(table_name)
        module_key = "" if spec is None else spec.module_key
        try:
            if module_key == "help":
                await bump_content_version(self._cache, tenant=tenant)
            if module_key == "dashboard":
                await self._cache.aincrease(self._cache.build_key("version", tenant=tenant))
            if module_key in _METADATA_MODULES:
                await bump_metadata_version(self._cache)
        except Exception as exc:  # 缓存不可用不阻断恢复，按 TTL 自然过期
            _LOGGER.warning(
                "recycle_cache_invalidate_failed",
                table=table_name,
                error_type=type(exc).__name__,
            )

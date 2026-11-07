"""作用域资源类型运营期服务（07D `01_01`）：运营期停用 / 启用 + 视图重建。

口径：

- **只写运营态**：只改 `admin_status` / `disabled_at` / `disabled_by`，**不碰声明态 `status`**——
  声明权威在注册通道，运营期停用不该被下一次注册重放冲掉，也不该反向改写产品声明；
- **幂等**：目标运营态与现值一致时不写库、不记审计（重复点击不产生重复审计事件）；
- **审计**：字段级变更经 `AuditCapturer` 进审计链（操作人来自登录态）；
- **生效**：提交后按库**整表重建**进程内视图，同进程立刻按新有效态判定；跨进程靠下次注册 /
  启动快照收敛（与其余注册数据同口径，**不引入推送通道**）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConfigError, NotFoundError, ParamError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.resource_scope import (
    SCOPE_RESOURCE_ADMIN_STATUSES,
    SCOPE_RESOURCE_DISABLED,
    SCOPE_RESOURCE_RETIRED,
    ScopeResourceTypeRecord,
    register_scope_resource_types,
    reset_scope_resource_types,
)
from bms_platform.domains.platform_registry.repositories.scope_resource import ScopeResourceTypeRepository

__all__ = ["ScopeResourceTypeService"]

_TABLE = "sys_scope_resource_type"
"""逻辑表名（审计事件定位用；须在 `TABLE_OWNERSHIP` 登记，审计按表归属派生业务域）。"""

_LOGGER = get_logger("bms.platform.scope_resource")


class ScopeResourceTypeService(BaseFrameworkObject):
    """作用域资源类型运营期服务（会话绑定；事务边界由本服务经工作单元控制）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        audit: AuditCapturer | None = None,
        uow: DbUnitOfWork | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台服务库会话（注册表所在库）。
            audit: 审计捕获器（None 表示不写审计——只读路径）。
            uow: 平台库工作单元（写路径必填）。
        """
        self._session = session
        self._repo = ScopeResourceTypeRepository(session)
        self._audit = audit
        self._uow = uow

    async def list_records(self) -> ConcurrentStableList[ScopeResourceTypeRecord]:
        """运营视图：未退役的全部类型（含已停用，便于运营核对与恢复）。

        Returns:
            ConcurrentStableList[ScopeResourceTypeRecord]: 类型记录（插入序）。
        """
        rows = await self._repo.list_declared()
        return ConcurrentStableList(ScopeResourceTypeRecord.from_row(row) for row in rows)

    async def set_admin_status(
        self, resource_type_key: str, admin_status: str, *, actor: int | None = None
    ) -> ScopeResourceTypeRecord:
        """设置运营态（停用 / 恢复），幂等。

        Args:
            resource_type_key: 类型标识（`{module_key}.{kind}`）。
            admin_status: 目标运营态（`enabled` / `disabled`）。
            actor: 操作人（`sys_user.id`；审计用）。

        Returns:
            ScopeResourceTypeRecord: 变更后的类型记录。

        Raises:
            ParamError: 运营态取值非法 / 类型已退役（10001）。
            NotFoundError: 类型未登记（10002）。
        """
        if admin_status not in SCOPE_RESOURCE_ADMIN_STATUSES:
            raise ParamError(f"运营态取值非法（enabled / disabled）：{admin_status}")
        record = await self._write_admin_status(resource_type_key, admin_status, actor=actor)
        await self.rebuild_view()
        return record

    async def rebuild_view(self) -> None:
        """按库整表重建进程内视图（停用后可立刻按新有效态判定）。"""
        rows = await self._repo.list_declared()
        records = ConcurrentStableList(ScopeResourceTypeRecord.from_row(row) for row in rows)
        reset_scope_resource_types()
        register_scope_resource_types(records)
        _LOGGER.info("scope_resource_view_rebuilt", count=len(records))

    async def _write_admin_status(
        self, resource_type_key: str, admin_status: str, *, actor: int | None
    ) -> ScopeResourceTypeRecord:
        """写运营态（单事务；返回变更后的记录值对象）。

        Args:
            resource_type_key: 类型标识。
            admin_status: 目标运营态。
            actor: 操作人。

        Returns:
            ScopeResourceTypeRecord: 变更后的记录。

        Raises:
            ParamError: 类型已退役（10001）。
            NotFoundError: 类型未登记（10002）。
        """
        async with self._write_scope():
            row = await self._repo.get_by_key(resource_type_key)
            if row is None:
                raise NotFoundError(f"作用域资源类型未登记：{resource_type_key}")
            if str(row.status) == SCOPE_RESOURCE_RETIRED:
                raise ParamError(f"作用域资源类型已退役，不可停用 / 恢复：{resource_type_key}")
            if str(row.admin_status) != admin_status:
                previous = str(row.admin_status)
                row.admin_status = admin_status
                if admin_status == SCOPE_RESOURCE_DISABLED:
                    row.disabled_at = datetime.now(UTC)
                    row.disabled_by = actor
                await self._repo.flush()
                self._capture(row.id, previous=previous, current=admin_status, actor=actor)
            return ScopeResourceTypeRecord.from_row(row)

    @asynccontextmanager
    async def _write_scope(self) -> AsyncGenerator[None]:
        """写事务边界：先回滚只读查询遗留的空事务（autobegin），再统一开启写事务。

        Yields:
            None: 事务运行期。

        Raises:
            ConfigError: 写路径缺少工作单元（装配错误）。
        """
        if self._uow is None:
            raise ConfigError("作用域资源类型写路径缺少工作单元（请经 get_platform_uow 注入）")
        await self._session.rollback()
        async with self._uow.begin():
            yield

    def _capture(self, model_id: int, *, previous: str, current: str, actor: int | None) -> None:
        """写审计留痕（运营态字段级变更）。

        Args:
            model_id: 记录主键。
            previous: 变更前运营态。
            current: 变更后运营态。
            actor: 操作人。
        """
        if self._audit is None:
            return
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
            [FieldChange(field="admin_status", old=previous, new=current)]
        )
        self._audit.capture(table=_TABLE, model_id=model_id, changes=changes, actor=actor)

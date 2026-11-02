"""角色导入定义（`roles`）：列集 / 预检 / 经 `RoleService` 写单行。

- 只导入角色主数据（角色码 / 名称 / 状态），恒为 `custom`；不开放 `role_type`，不做权限分配。
- 角色码格式复用 `role.code_pattern` 系统参数；全量原子由编排负责。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.definition import BaseImportDefinition, ImportRowContext
from bms_core.transfer.importer import ParsedRow, RowError
from bms_platform.domains.role.repositories.role import RoleRepository
from bms_platform.domains.role.services.role import (
    DEFAULT_ROLE_CODE_PATTERN,
    RoleService,
    resolve_role_code_pattern,
)

__all__ = ["RoleImportDefinition"]

_STATUS_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "enabled": "enabled",
        "disabled": "disabled",
        "启用": "enabled",
        "禁用": "disabled",
    }
)
"""状态 label / 库值 → 库值。"""

_ROLE_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (
        ColumnSpec(
            key="code",
            title="角色码",
            required=True,
            max_length=64,
            note="小写字母开头，2~32 位字母 / 数字 / 下划线 / 连字符；租户内唯一",
            example="sales_manager",
        ),
        ColumnSpec(
            key="name",
            title="角色名称",
            required=True,
            max_length=128,
            note="角色显示名称",
            example="销售经理",
        ),
        ColumnSpec(
            key="status",
            title="状态",
            max_length=16,
            choices=ConcurrentStableFrozenList(("enabled", "disabled", "启用", "禁用")),
            note="enabled/disabled 或 启用/禁用；空=启用",
            example="启用",
        ),
    )
)


@dataclass(frozen=True)
class _RolePreload(BaseValueObject):
    """角色导入预取：库内已存在角色码 + 文件内重复角色码。"""

    existing: ConcurrentStableFrozenSet[str]
    duplicates: ConcurrentStableFrozenSet[str]


class RoleImportDefinition(BaseImportDefinition):
    """角色导入定义（`roles`）。"""

    biz = "roles"
    title = "角色"
    write_permission = "role:create"

    def __init__(
        self,
        *,
        service_factory: Callable[[DbSession, UnitOfWork], RoleService],
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化。

        Args:
            service_factory: 按会话 / 工作单元构造 `RoleService` 的工厂（服务根装配）。
            audit: 审计捕获器（None 表示不记录）。
        """
        self._service_factory = service_factory
        self._audit = audit

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导入列集。

        Returns:
            ConcurrentStableFrozenList[ColumnSpec]: 固定列序。
        """
        return _ROLE_COLUMNS

    async def preload(self, session: DbSession, rows: ConcurrentStableList[ParsedRow]) -> _RolePreload:
        """预取库内已存在角色码并统计文件内重复。

        Args:
            session: 当前会话。
            rows: 全部数据行。

        Returns:
            _RolePreload: 已存在角色码 + 文件内重复角色码。
        """
        codes: ConcurrentStableList[str] = ConcurrentStableList()
        counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for row in rows:
            raw = row.values.get("code")
            if not isinstance(raw, str):
                continue
            code = raw.strip()
            if not code:
                continue
            codes.add(code)
            counts.set(code, counts.get(code, 0) + 1)
        duplicates = ConcurrentStableFrozenSet(code for code in codes if counts.get(code, 0) > 1)
        existing = await RoleRepository(session).list_existing_codes(codes)
        return _RolePreload(existing=ConcurrentStableFrozenSet(existing), duplicates=duplicates)

    async def validate_row(
        self,
        row: ParsedRow,
        preloaded: object,
        *,
        config: BaseConfigSource | None,
    ) -> ConcurrentStableFrozenList[RowError]:
        """角色行业务校验。

        Args:
            row: 已通过通用校验的行。
            preloaded: `preload` 返回的 `_RolePreload`。
            config: 系统参数取数（角色码格式）。

        Returns:
            ConcurrentStableFrozenList[RowError]: 该行错误（空表示通过）。
        """
        state = cast("_RolePreload", preloaded)
        errors: ConcurrentStableList[RowError] = ConcurrentStableList()
        code = str(row.values.get("code") or "").strip()
        pattern = await resolve_role_code_pattern(config) if config is not None else DEFAULT_ROLE_CODE_PATTERN
        if re.fullmatch(pattern, code) is None:
            errors.add(RowError(row=row.row_no, message="角色码格式非法", field="code"))
        if code in state.existing:
            errors.add(RowError(row=row.row_no, message="角色码已存在", field="code"))
        if code in state.duplicates:
            errors.add(RowError(row=row.row_no, message="角色码在文件内重复", field="code"))
        status = _STATUS_LABELS.get(str(row.values.get("status") or "enabled").strip())
        if status is None:
            errors.add(RowError(row=row.row_no, message="状态取值非法", field="status"))
        return ConcurrentStableFrozenList(errors)

    async def write_row(self, row: ParsedRow, ctx: ImportRowContext) -> None:
        """写入单行角色（复用 `RoleService.create_role`；恒为 custom）。

        Args:
            row: 已通过校验的行。
            ctx: 执行上下文。
        """
        service = self._service_factory(ctx.session, ctx.uow)
        status = _STATUS_LABELS.get(str(row.values.get("status") or "enabled").strip(), "enabled")
        role = await service.create_role(
            code=str(row.values.get("code") or "").strip(),
            name=str(row.values.get("name") or "").strip(),
            status=status,
        )
        if self._audit is not None:
            changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
                (
                    FieldChange(field="code", old=None, new=role.code),
                    FieldChange(field="name", old=None, new=role.name),
                    FieldChange(field="status", old=None, new=role.status),
                )
            )
            self._audit.capture(table="sys_role", model_id=int(role.id), changes=changes, actor=ctx.actor)

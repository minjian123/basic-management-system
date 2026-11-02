"""用户导入定义（`users`）：列集 / 预检 / 经 `UserAdminService` 写单行。

- 全量原子由编排负责；本定义只做业务校验与单行写入。
- 密码为空时由 `UserAdminService` 随机生成并强制首登改密；填写时按密码策略预检。
- 审计每成功行 `AuditCapturer.capture`，不含 `password_hash`。
"""

from __future__ import annotations

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
from bms_core.password.base import BasePasswordPolicy
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.definition import BaseImportDefinition, ImportRowContext
from bms_core.transfer.importer import ParsedRow, RowError
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users_admin import UserAdminService

__all__ = ["UserImportDefinition"]

_USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_PHONE_PATTERN = r"^[+]?[0-9][0-9\-\s]{5,31}$"

_STATUS_LABELS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        "enabled": "enabled",
        "disabled": "disabled",
        "启用": "enabled",
        "禁用": "disabled",
    }
)
"""状态 label / 库值 → 库值。"""

_USER_COLUMNS: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
    (
        ColumnSpec(
            key="username",
            title="登录账号",
            required=True,
            max_length=64,
            pattern=_USERNAME_PATTERN,
            note="小写 / 大写字母、数字、下划线、点、连字符；首字符为字母或数字；租户内唯一",
            example="zhangsan",
        ),
        ColumnSpec(
            key="name",
            title="姓名",
            required=True,
            max_length=128,
            note="用户昵称 / 显示名",
            example="张三",
        ),
        ColumnSpec(
            key="email",
            title="邮箱",
            max_length=255,
            pattern=_EMAIL_PATTERN,
            note="可空；填写时必须为合法邮箱",
            example="zhangsan@example.com",
        ),
        ColumnSpec(
            key="phone",
            title="手机号",
            max_length=32,
            pattern=_PHONE_PATTERN,
            note="可空；填写时必须为合法手机号",
            example="13800000000",
        ),
        ColumnSpec(
            key="status",
            title="状态",
            max_length=16,
            choices=ConcurrentStableFrozenList(("enabled", "disabled", "启用", "禁用")),
            note="enabled/disabled 或 启用/禁用；空=启用",
            example="启用",
        ),
        ColumnSpec(
            key="password",
            title="初始密码",
            max_length=128,
            note="可空；空则随机生成；导入后一律强制首登改密",
            example="",
        ),
    )
)


@dataclass(frozen=True)
class _UserPreload(BaseValueObject):
    """用户导入预取：库内已存在账号 + 文件内重复账号。"""

    existing: ConcurrentStableFrozenSet[str]
    duplicates: ConcurrentStableFrozenSet[str]


class UserImportDefinition(BaseImportDefinition):
    """用户导入定义（`users`）。"""

    biz = "users"
    title = "用户"
    write_permission = "user:create"
    quota_key = "user_count"

    def __init__(
        self,
        *,
        service_factory: Callable[[DbSession, UnitOfWork], UserAdminService],
        policy: BasePasswordPolicy,
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化。

        Args:
            service_factory: 按会话 / 工作单元构造 `UserAdminService` 的工厂（服务根装配）。
            policy: 密码策略（预检）。
            audit: 审计捕获器（None 表示不记录）。
        """
        self._service_factory = service_factory
        self._policy = policy
        self._audit = audit

    @property
    def columns(self) -> ConcurrentStableFrozenList[ColumnSpec]:
        """导入列集。

        Returns:
            ConcurrentStableFrozenList[ColumnSpec]: 固定列序。
        """
        return _USER_COLUMNS

    async def preload(self, session: DbSession, rows: ConcurrentStableList[ParsedRow]) -> _UserPreload:
        """预取库内已存在账号并统计文件内重复。

        Args:
            session: 当前会话。
            rows: 全部数据行。

        Returns:
            _UserPreload: 已存在账号 + 文件内重复账号。
        """
        usernames: ConcurrentStableList[str] = ConcurrentStableList()
        counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for row in rows:
            raw = row.values.get("username")
            if not isinstance(raw, str):
                continue
            username = raw.strip()
            if not username:
                continue
            usernames.add(username)
            counts.set(username, counts.get(username, 0) + 1)
        duplicates = ConcurrentStableFrozenSet(username for username in usernames if counts.get(username, 0) > 1)
        existing = await UserRepository(session).list_existing_usernames(usernames)
        return _UserPreload(existing=ConcurrentStableFrozenSet(existing), duplicates=duplicates)

    async def validate_row(
        self,
        row: ParsedRow,
        preloaded: object,
        *,
        config: BaseConfigSource | None,
    ) -> ConcurrentStableFrozenList[RowError]:
        """用户行业务校验。

        Args:
            row: 已通过通用校验的行。
            preloaded: `preload` 返回的 `_UserPreload`。
            config: 系统参数取数（本定义未使用）。

        Returns:
            ConcurrentStableFrozenList[RowError]: 该行错误（空表示通过）。
        """
        del config
        state = cast("_UserPreload", preloaded)
        errors: ConcurrentStableList[RowError] = ConcurrentStableList()
        username = str(row.values.get("username") or "").strip()
        if username in state.existing:
            errors.add(RowError(row=row.row_no, message="登录账号已存在", field="username"))
        if username in state.duplicates:
            errors.add(RowError(row=row.row_no, message="登录账号在文件内重复", field="username"))
        status = _STATUS_LABELS.get(str(row.values.get("status") or "enabled").strip())
        if status is None:
            errors.add(RowError(row=row.row_no, message="状态取值非法", field="status"))
        password = str(row.values.get("password") or "").strip()
        if password:
            violations = await self._policy.validate(password, username=username)
            for violation in violations:
                errors.add(RowError(row=row.row_no, message=f"初始密码{violation}", field="password"))
        return ConcurrentStableFrozenList(errors)

    async def write_row(self, row: ParsedRow, ctx: ImportRowContext) -> None:
        """写入单行用户（复用 `UserAdminService.create_user`）。

        Args:
            row: 已通过校验的行。
            ctx: 执行上下文。
        """
        service = self._service_factory(ctx.session, ctx.uow)
        user, _generated = await service.create_user(
            username=str(row.values.get("username") or "").strip(),
            name=str(row.values.get("name") or "").strip(),
            password=str(row.values.get("password") or "").strip() or None,
            pwd_reset_required=True,
            email=str(row.values.get("email") or "").strip() or None,
            phone=str(row.values.get("phone") or "").strip() or None,
            status=_STATUS_LABELS[str(row.values.get("status") or "enabled").strip()],
        )
        if self._audit is not None:
            changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
                (
                    FieldChange(field="username", old=None, new=user.username),
                    FieldChange(field="name", old=None, new=user.name),
                    FieldChange(field="email", old=None, new=user.email),
                    FieldChange(field="phone", old=None, new=user.phone),
                    FieldChange(field="status", old=None, new=user.status),
                )
            )
            self._audit.capture(table="sys_user", model_id=int(user.id), changes=changes, actor=ctx.actor)

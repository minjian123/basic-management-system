"""组织主数据服务 services 层：用户概要查询与 JIT 建号（服务间内部接口）。"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from bms_core.core.base import BaseObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.services.base_service import BaseService
from bms_org.models.user import SysUser
from bms_org.repositories.user import UserRepository
from bms_org.schemas.users import UserCreateResult, UserProfileResult, UserProfileUser

SSO_PASSWORD_PLACEHOLDER = "!sso"
"""SSO JIT 建号的口令占位（非 PBKDF2 自描述串 → 本地登录校验恒 False，禁止本地口令登录）。"""

_USERNAME_CONFLICT = "username_conflict"
"""用户名撞名原因码（调用侧据此换后缀重试）。"""


class UserProfileService(BaseObject):
    """用户概要服务：按主键取最小概要（不存在返回 `found=false`）。"""

    def __init__(self, users: UserRepository) -> None:
        """初始化。

        Args:
            users: 用户仓储（租户库 `sys_user`）。
        """
        self._users = users

    async def profile(self, user_id: int) -> UserProfileResult:
        """按主键取用户概要。

        Args:
            user_id: 用户主键。

        Returns:
            UserProfileResult: 概要结果（不存在 `found=false`）。
        """
        row = await self._users.get_by_id(user_id)
        if row is None:
            return UserProfileResult(found=False)
        return UserProfileResult(found=True, user=_summary(row))


class UserCreateService(BaseService[SysUser]):
    """JIT 建号服务：单次「用户名空闲即建号」（撞名返回 `created=false`，不抛错）。"""

    def __init__(self, repository: UserRepository, uow: UnitOfWork) -> None:
        """初始化。

        Args:
            repository: 用户仓储（租户库 `sys_user`）。
            uow: 工作单元（写事务边界）。
        """
        super().__init__(repository)
        self._uow = uow

    async def create_user(
        self,
        *,
        username: str,
        name: str,
        locale: str | None = None,
        timezone: str | None = None,
    ) -> UserCreateResult:
        """创建 SSO 最小用户（占位口令 + 启用状态）。

        Args:
            username: 登录账号（调用侧已清洗）。
            name: 昵称 / 显示名。
            locale: 语言偏好（可空）。
            timezone: 时区偏好（可空）。

        Returns:
            UserCreateResult: 建号结果（撞名 `created=false` + `reason=username_conflict`）。
        """
        try:
            async with self._uow.begin():
                existing = await self._repo().get_by_username(username)
                if existing is not None:
                    return UserCreateResult(created=False, reason=_USERNAME_CONFLICT)
                row = await self._repo().create(
                    username=username,
                    password_hash=SSO_PASSWORD_PLACEHOLDER,
                    name=name,
                    status="enabled",
                    locale=locale,
                    timezone=timezone,
                )
        except IntegrityError:
            return UserCreateResult(created=False, reason=_USERNAME_CONFLICT)
        return UserCreateResult(created=True, user=_summary(row))

    def _repo(self) -> UserRepository:
        """取用户仓储（泛型收窄）。

        Returns:
            UserRepository: 用户仓储。
        """
        repository = self._repository
        assert isinstance(repository, UserRepository)
        return repository


def _summary(row: SysUser) -> UserProfileUser:
    """ORM 行 → 用户概要 DTO。

    Args:
        row: 用户行。

    Returns:
        UserProfileUser: 概要 DTO。
    """
    return UserProfileUser(
        id=row.id,
        username=row.username,
        name=row.name,
        status=row.status or "",
        locale=row.locale,
        timezone=row.timezone,
    )

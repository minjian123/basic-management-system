"""平台服务 services 层：用户概要查询与统一建号入口（服务间内部接口）。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.pagination import BasePageQuery
from bms_core.services.base_service import BaseService
from bms_core.tenant.membership import TenantMembershipStore
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import (
    UserCreateResult,
    UserProfileResult,
    UserProfileUser,
    UserResetTargetResult,
)

USER_STATUSES: tuple[str, ...] = ("enabled", "disabled")
"""用户账号状态取值（最小只读查询筛选）。"""

SSO_PASSWORD_PLACEHOLDER = "!sso"
"""SSO JIT 建号的口令占位（非 PBKDF2 自描述串 → 本地登录校验恒 False，禁止本地口令登录）。"""

DEFAULT_CREATE_SOURCE = "sso_jit"
"""建号缺省来源（当前唯一调用方为 SSO JIT；其余建号路径功能落地时显式传参）。"""

_USERNAME_CONFLICT = "username_conflict"
"""用户名撞名原因码（调用侧据此换后缀重试）。"""

_LOGGER = get_logger("bms.platform.users")

CHANNEL_EMAIL = "email"
"""找回密码投递通道：邮件。"""

CHANNEL_SMS = "sms"
"""找回密码投递通道：短信。"""

_PHONE_RE = re.compile(r"^\+?\d{6,20}$")
"""手机号形态（可选国际前缀 + 6~20 位数字；仅用于标识分类，非格式校验）。"""


class UserQueryService(BaseFrameworkObject):
    """最小用户只读查询服务：分页 + 关键字 / 状态筛选（供选择用户弹窗与已分配列表回显）。

    只返回最小字段（`id` / `username` / `name` / `status`），**不返回**口令哈希与联系方式；
    完整用户域 CRUD 归 `02_01`，本服务接口按终态设计、可被复用。
    """

    def __init__(self, users: UserRepository) -> None:
        """初始化。

        Args:
            users: 用户仓储（租户库 `sys_user`）。
        """
        self._users = users

    async def list_users(
        self,
        query: BasePageQuery,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysUser], int]:
        """分页查询用户（账号 / 姓名关键字与状态筛选）。

        Args:
            query: 页码分页请求。
            keyword: 关键字（账号 / 姓名）。
            status: 状态（enabled/disabled）。

        Returns:
            tuple[ConcurrentStableList[SysUser], int]: 当前页用户与总条数。
        """
        rows = await self._users.list_filtered(query, keyword=keyword, status=status)
        total = await self._users.count_filtered(keyword=keyword, status=status)
        return rows, total


class UserProfileService(BaseFrameworkObject):
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


class UserResetTargetService(BaseFrameworkObject):
    """找回密码重置目标解析：标识分类（邮箱 / 手机 / 账号）→ 用户 → 通道与投递目标。

    - 邮箱按小写不敏感匹配（跨库确定性）；手机 / 账号精确匹配；多命中取最早一条。
    - 通道优先邮箱（`email`），无邮箱回落手机（`sms`），皆无为空通道。
    - 可送达 = 账号存在且启用且有可用通道；停用 / 软删 / 无联系方式按不可送达处理（调用侧统一防枚举响应）。
    - 锁定状态不影响解析（锁定中账号允许找回，锁状态不变；解锁归 03_07）。
    """

    def __init__(self, users: UserRepository) -> None:
        """初始化。

        Args:
            users: 用户仓储（租户库 `sys_user`）。
        """
        self._users = users

    async def resolve(self, identifier: str) -> UserResetTargetResult:
        """按标识解析重置目标。

        Args:
            identifier: 账号 / 手机号 / 邮箱。

        Returns:
            UserResetTargetResult: 解析结果（不存在 `found=false`）。
        """
        user = await self._lookup(identifier)
        if user is None:
            return UserResetTargetResult(found=False)
        channel, target = _pick_channel(user)
        return UserResetTargetResult(
            found=True,
            user_id=user.id,
            account=user.username,
            deliverable=user.status == "enabled" and channel != "",
            channel=channel,
            target=target,
        )

    async def _lookup(self, identifier: str) -> SysUser | None:
        """按标识形态取用户（邮箱 / 手机 / 账号）。

        Args:
            identifier: 账号 / 手机号 / 邮箱。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        if "@" in identifier:
            return await self._users.get_by_email(identifier)
        if _PHONE_RE.match(identifier) is not None:
            return await self._users.get_by_phone(identifier)
        return await self._users.get_by_username(identifier)


class UserCreateService(BaseService[SysUser]):
    """统一建号入口：单次「用户名空闲即建号」（撞名返回 `created=false`，不抛错）。

    建号成功后经**关系数据源**维护「用户↔归属租户」可达关系（`source` 标注来源）；
    关系写入失败**不阻断建号**（记 WARNING，交对账巡检补齐）。
    """

    def __init__(
        self,
        repository: UserRepository,
        uow: UnitOfWork,
        *,
        membership: TenantMembershipStore | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 用户仓储（租户库 `sys_user`）。
            uow: 工作单元（写事务边界）。
            membership: 关系数据源（缺省 None＝不维护关系；服务间调用侧注入）。
        """
        super().__init__(repository)
        self._uow = uow
        self._membership = membership

    async def create_user(
        self,
        *,
        username: str,
        name: str,
        locale: str | None = None,
        timezone: str | None = None,
        source: str = DEFAULT_CREATE_SOURCE,
        owner_tenant_id: int | None = None,
    ) -> UserCreateResult:
        """创建最小用户（占位口令 + 启用状态）并按来源维护归属租户关系。

        Args:
            username: 登录账号（调用侧已清洗）。
            name: 昵称 / 显示名。
            locale: 语言偏好（可空）。
            timezone: 时区偏好（可空）。
            source: 建号来源（缺省 `sso_jit`；其余路径功能落地时显式传参）。
            owner_tenant_id: 归属租户主键（缺省 None＝不维护关系）。

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
        await self._ensure_membership(user_id=int(row.id), tenant_id=owner_tenant_id, source=source)
        return UserCreateResult(created=True, user=_summary(row))

    async def _ensure_membership(self, *, user_id: int, tenant_id: int | None, source: str) -> None:
        """建号后维护「用户↔归属租户」可达关系（失败不阻断建号）。

        Args:
            user_id: 新建用户主键。
            tenant_id: 归属租户主键（None＝不维护）。
            source: 建号来源。
        """
        if self._membership is None or tenant_id is None:
            return
        try:
            await self._membership.ensure(
                tenant_id=tenant_id,
                user_id=user_id,
                target_tenant_id=tenant_id,
                source=source,
            )
        except ServiceUnavailableError as exc:
            _LOGGER.warning("user_membership_write_degraded", user_id=user_id, tenant_id=tenant_id, error=repr(exc))

    def _repo(self) -> UserRepository:
        """取用户仓储（泛型收窄）。

        Returns:
            UserRepository: 用户仓储。
        """
        repository = self._repository
        assert isinstance(repository, UserRepository)
        return repository


def _pick_channel(row: SysUser) -> tuple[str, str]:
    """按登记联系方式取投递通道与目标（邮箱优先、手机兜底）。

    Args:
        row: 用户行。

    Returns:
        tuple[str, str]: (通道 `email` / `sms` / 空串, 投递目标)。
    """
    if row.email:
        return CHANNEL_EMAIL, row.email
    if row.phone:
        return CHANNEL_SMS, row.phone
    return "", ""


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
        pwd_reset_required=row.pwd_reset_required,
    )

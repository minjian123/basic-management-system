"""组织主数据服务 services 层：用户概要查询（服务间内部接口）。"""

from __future__ import annotations

from bms_core.core.base import BaseObject
from bms_org.repositories.user import UserRepository
from bms_org.schemas.users import UserProfileResult, UserProfileUser


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
        return UserProfileResult(
            found=True,
            user=UserProfileUser(
                id=row.id,
                username=row.username,
                name=row.name,
                status=row.status or "",
                locale=row.locale,
                timezone=row.timezone,
            ),
        )

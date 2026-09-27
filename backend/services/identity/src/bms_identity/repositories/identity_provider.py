"""认证与身份服务 repositories 层：租户外部 IdP 配置仓储（`sys_identity_provider`）。"""

from __future__ import annotations

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_identity.models.identity_provider import SysIdentityProvider


class IdentityProviderRepository(BaseDbRepository[SysIdentityProvider]):
    """外部 IdP 配置仓储（`sys_identity_provider`）：入口清单 / 按标识取行。"""

    model = SysIdentityProvider
    sortable_fields = frozenset({"id", "name", "sort"})

    async def list_enabled(self) -> list[SysIdentityProvider]:
        """取启用中的 IdP 行（按 `sort` 升序、主键兜底；入口清单主路径）。

        Returns:
            list[SysIdentityProvider]: 启用中的 IdP 行。
        """
        statement = (
            self._select()
            .where(self._column("status") == "enabled")
            .order_by(self._column("sort").asc(), self._column("id").asc())
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_by_key(self, idp_key: str) -> SysIdentityProvider | None:
        """按租户内标识取行（authorize / callback 定位配置）。

        Args:
            idp_key: 租户内稳定标识（路由参数）。

        Returns:
            SysIdentityProvider | None: IdP 行；不存在返回 None。
        """
        statement = self._select().where(self._column("idp_key") == idp_key)
        return (await self._session.execute(statement)).scalar_one_or_none()

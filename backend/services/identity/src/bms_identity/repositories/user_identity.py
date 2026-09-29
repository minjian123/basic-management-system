"""认证与身份服务 repositories 层：SSO 全局身份映射仓储（`sys_user_identity`）。

平台库表：回调在租户定位前即按外部身份命中映射（`idp_key` 已含租户前缀）；
02_01 交付只读查询，02_02 补写路径（`create` 继承基类 CRUD）与按用户反查（`list_by_user`）。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.core.exceptions import SsoIdentityConflictError
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_identity.models.user_identity import SysUserIdentity


class UserIdentityRepository(BaseDbRepository[SysUserIdentity]):
    """SSO 全局身份映射仓储（`sys_user_identity`）：按映射键 + 外部主体取行 / 按用户反查。"""

    model = SysUserIdentity
    sortable_fields = ConcurrentStableSet({"id"})

    async def get_by_key_external(self, idp_key: str, external_id: str) -> SysUserIdentity | None:
        """按映射键与外部主体取映射行（登录回调定位本地用户）。

        Args:
            idp_key: 映射键（`{tenant_id}:{provider_key}`）。
            external_id: 外部身份主体（OIDC 取 `sub`）。

        Returns:
            SysUserIdentity | None: 映射行；不存在返回 None。

        Raises:
            SsoIdentityConflictError: 命中多行（脏数据 / 约束缺口，20055/409）。
        """
        statement = (
            self._select()
            .where(
                self._column("idp_key") == idp_key,
                self._column("external_id") == external_id,
            )
            .limit(2)
        )
        rows = list((await self._session.execute(statement)).scalars().all())
        if len(rows) > 1:
            raise SsoIdentityConflictError()
        return rows[0] if rows else None

    async def list_by_user(self, user_id: int) -> list[SysUserIdentity]:
        """按本地用户反查绑定（`sso:bind` 只读端点）。

        Args:
            user_id: 本地用户主键。

        Returns:
            list[SysUserIdentity]: 绑定映射行（按主键升序；无绑定返回空列表）。
        """
        statement = self._select().where(self._column("user_id") == user_id).order_by(self._column("id"))
        return list((await self._session.execute(statement)).scalars().all())

"""字典平台内建数据源提供者（02_09）：登记项 `origin=platform` 的取数实现。

- `PlatformDictDataProvider`：平台内建字典取数（读平台实体表），本期示例「角色」（`sys_role`）。
  只负责**加载全部启用条目**；版本比对 / 缓存 / 关键字 / 级联 / 按值子集 / 截断由统一出口承载。
- 产品来源字典（`origin=product`）不经本提供者：前端经网关直取产品命名空间。
- 其余平台字典随各自域以追加 `load` 分支 / 独立提供者回补（登记项先占位）。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.dict.base import DictItem
from bms_core.dict.outlet import BaseDictDataProvider

__all__ = ["PlatformDictDataProvider"]

_DICT_KEY_ROLE = "role"
"""本期平台内建示例字典标识（角色）。"""


class PlatformDictDataProvider(BaseDictDataProvider):
    """平台内建字典取数提供者（示例：角色 `sys_role`）。"""

    def __init__(self, *, engines: EngineRegistry) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
        """
        self._engines = engines

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: `platform.*`（按登记项匹配）。
        """
        return "platform"

    async def load(self, dict_key: str, locale: str) -> tuple[DictItem, ...]:
        """加载平台内建字典的启用条目。

        Args:
            dict_key: 字典标识。
            locale: 语言（平台实体表暂不分语言）。

        Returns:
            tuple[DictItem, ...]: 启用条目；未支持标识返回空元组。
        """
        if dict_key == _DICT_KEY_ROLE:
            return await self._load_roles()
        return ()

    async def _load_roles(self) -> tuple[DictItem, ...]:
        """加载启用角色（`sys_role`）。

        Returns:
            tuple[DictItem, ...]: 角色条目（value=角色码 / label=名称）。
        """
        from bms_platform.models.role import SysRole

        async with self._session() as session:
            statement = (
                select(SysRole).where(SysRole.status == "enabled", SysRole.deleted_at.is_(None)).order_by(SysRole.id)
            )
            rows = (await session.execute(statement)).scalars().all()
        return tuple(
            DictItem(
                id=row.id,
                value=row.code,
                label=row.name,
                code=row.code,
                parent_id=None,
                sort=0,
                status=row.status,
                color=None,
            )
            for row in rows
        )

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session

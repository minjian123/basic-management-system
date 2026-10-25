"""平台内建数据源提供者（02_09 起，02_10 泛化）：登记项 `origin=platform` 的取数实现。

- `PlatformDictDataSource`：平台内建字典取数（读平台实体表），**本期示例「角色」（`sys_role`）**，
  其余数据源返回空（决策 13：与 `02_09`「示例各落一」一致；各域随各自任务接入）。
  只负责**加载某数据源全部启用行**；版本比对 / 缓存 / 关键字 / 级联 / 按值子集 / 截断由统一出口承载。
- 产品来源数据源（`origin=product`）不经本提供者：前端经网关直取产品命名空间。
- 通用字典表取数可用可直用 / 可继承实现类 `bms_core/dict/table.py::DictTableDataSource`。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, DataSourceItem
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope

__all__ = ["PlatformDictDataSource"]

_DATA_SOURCE_KEY_ROLE = "role"
"""本期平台内建示例数据源标识（角色）。"""


class PlatformDictDataSource(BaseDictDataSource):
    """平台内建数据源提供者（示例：角色 `sys_role`）。"""

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
            str: `platform`（按登记项匹配）。
        """
        return "platform"

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """加载平台内建数据源的启用行。

        Args:
            data_source_key: 数据源标识。
            locale: 语言（平台实体表暂不分语言）。

        Returns:
            tuple[DataSourceItem, ...]: 启用行；未支持标识返回空元组。
        """
        if data_source_key == _DATA_SOURCE_KEY_ROLE:
            return await self._load_roles()
        return ConcurrentStableList(())

    async def _load_roles(self) -> ConcurrentStableList[DataSourceItem]:
        """加载启用角色（`sys_role`）。

        Returns:
            tuple[DataSourceItem, ...]: 角色条目（value=角色码 / label=名称）。
        """
        from bms_platform.domains.role.public import SysRole

        async with self._session() as session:
            statement = (
                select(SysRole).where(SysRole.status == "enabled", SysRole.deleted_at.is_(None)).order_by(SysRole.id)
            )
            rows = (await session.execute(statement)).scalars().all()
        return ConcurrentStableList(
            DataSourceItem(
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

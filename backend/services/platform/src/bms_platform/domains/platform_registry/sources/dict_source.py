"""平台内建数据源提供者（02_09 起，02_10 泛化，02_01 规格化）：`origin=platform` 的取数实现。

- `PlatformDictDataSource`：**12 个平台内建字典共用一条取数路径**——按 `dict_specs` 的规格分派：
  - `mode=table` → `DictTableDataSource`（库域 / 表 / 列映射 / i18n / 排序全部来自规格，无 per-key 代码）；
  - `mode=port` → 域读面（目前只有 `role` 走 `RoleReferencePort`，保留域内过滤语义）；
  - 未登记标识 → 空行（出口按「未登记」处理）。
- 只负责**加载某数据源全部启用行**；版本比对 / 缓存 / 关键字 / 级联 / 按值子集 / 截断由统一出口承载。
- 新增一个字典：登记清单加一条 + `dict_specs` 加一行，**本文件不动**。
- 产品来源数据源（`origin=product`）不经本提供者：前端经网关直取产品命名空间。
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, DataSourceItem
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.dict.table import DictTableDataSource
from bms_platform.domains.platform_registry.sources.dict_specs import (
    DictSourceMode,
    DictSourceSpec,
    platform_dict_specs,
)
from bms_platform.domains.role.public import RoleReferencePort

__all__ = ["PlatformDictDataSource", "RoleOptionsFactory"]

RoleOptionsFactory = Callable[[DbSession], RoleReferencePort]
"""角色引用面工厂（装配处传入，域实现不依赖装配层）。"""


class PlatformDictDataSource(BaseDictDataSource):
    """平台内建数据源提供者（按 `dict_specs` 规格分派；12 个内建字典共用一条路径）。"""

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        role_options: RoleOptionsFactory,
        specs: ConcurrentStableDict[str, DictSourceSpec] | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
            role_options: 角色引用面工厂（装配处传入）。
            specs: 数据源规格（缺省取平台内建 12 条；装配 / 用例可注入子集）。
        """
        self._engines = engines
        self._role_options = role_options
        self._specs = specs if specs is not None else platform_dict_specs()
        self._table_sources: ConcurrentStableDict[str, DictTableDataSource] = ConcurrentStableDict()

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
        spec = self._specs.get(data_source_key)
        if spec is None:
            return ConcurrentStableList(())
        if spec.mode == DictSourceMode.PORT.value:
            return await self._load_roles()
        return await self._table_source(spec).load(data_source_key, locale)

    def _table_source(self, spec: DictSourceSpec) -> DictTableDataSource:
        """按规格取（并缓存）表源实例。

        Args:
            spec: 数据源规格。

        Returns:
            DictTableDataSource: 该规格对应的表源。
        """
        existing = self._table_sources.get(spec.data_source_key)
        if existing is not None:
            return existing
        created = DictTableDataSource(
            engines=self._engines,
            data_source=self.data_source,
            table=spec.table,
            db_scope=spec.db_scope,
            i18n=spec.i18n,
        )
        self._table_sources.set(spec.data_source_key, created)
        return created

    async def _load_roles(self) -> ConcurrentStableList[DataSourceItem]:
        """加载启用角色（经角色域 `RoleReferencePort`，只取 DTO）。

        Returns:
            tuple[DataSourceItem, ...]: 角色条目（value=角色码 / label=名称）。
        """
        async with self._session() as session:
            rows = await self._role_options(session).list_options()
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

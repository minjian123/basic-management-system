"""平台内建字典的数据源规格（02_01）：12 个 key 的**唯一差异声明**（服务级模块）。

**为什么放在服务根而不是某个域内**：字典出口天然**跨域聚合**（数据权限左列 / 业务码下拉要看全平台实体），
放进 `domains/platform_registry/` 会形成「注册域 import 其余 8 个域的模型」，触发服务边界护栏
（`check_service_boundaries` 跨域 import）。放在服务级后，域内代码只依赖本域，聚合清单留在装配层，
与 `wiring.py` 同口径（装配层允许引用各域）。

口径（详细设计 §4.1 / §4.8）：平台字典不再「一 key 一个提供者类」，而是**一张规格表**：

- 登记层（`DATA_SOURCE_CATALOG`）说「对外有哪几个数据源」；
- 本表说「数据从哪张表、哪个库、按哪几列取」；
- 出口（`bms_core/dict/outlet.py`）承担版本 / 缓存 / 过滤 / 截断。

新增一个平台字典 = `DATA_SOURCE_CATALOG` 加一条 + 本表加一行；改数据来源只改本表一行。
12 张表的列名实测一致（`id` / `code` / `name` / `status` / `parent_id` / `deleted_at`），差异只有
**库域**（平台库 5 张 / 租户库 7 张）、**i18n 附表**（4 张）与**排序列**（仅 `sys_identity_provider` 有 `sort`）。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from sqlalchemy import Table

from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.objects import BaseValueObject
from bms_core.datasource.keys import DataSourceKey
from bms_core.dict.table import DictI18nSpec, DictTableScope
from bms_core.models.identity.client import SysClient
from bms_core.models.identity.identity_provider import SysIdentityProvider
from bms_core.models.platform.catalog import SysModule, SysModuleI18n, SysProduct
from bms_core.models.platform.icon import SysIcon, SysIconI18n
from bms_core.models.platform.permission_meta import SysAction, SysActionI18n, SysBusiness, SysBusinessI18n
from bms_core.models.platform.role import SysRole
from bms_core.models.platform.task import SysTask
from bms_core.models.platform.user import SysUser
from bms_core.models.tenant.tenant import SysTenant

__all__ = ["PLATFORM_DICT_SPECS", "DictSourceMode", "DictSourceSpec", "platform_dict_specs"]


class DictSourceMode(StrEnum):
    """取数方式（表源 / 域读面）。"""

    TABLE = "table"
    PORT = "port"


@dataclass(frozen=True)
class DictSourceSpec(BaseValueObject):
    """单个字典数据源的取数规格。

    Attributes:
        data_source_key: 数据源标识（与 `DATA_SOURCE_CATALOG` 一一对应）。
        table: 物理表（取 `Model.__table__`，列名为 DB 列名）。
        db_scope: 库域（`platform` 平台库 / `tenant` 当前租户库）。
        value_column: 条目值列（缺省 `code`）。
        label_column: 标签列（缺省 `name`）。
        sort_column: 排序列（None → 按 `id` 升序）。
        i18n: 多语言附表规格（无则不区分 locale）。
        mode: 取数方式（`table` 表源 / `port` 域读面，目前仅 `role`）。
    """

    data_source_key: str
    table: Table
    db_scope: str = DictTableScope.TENANT.value
    value_column: str = "code"
    label_column: str = "name"
    sort_column: str | None = None
    i18n: DictI18nSpec | None = None
    mode: str = DictSourceMode.TABLE.value


PLATFORM_DICT_SPECS: ConcurrentStableDict[str, DictSourceSpec] = ConcurrentStableDict(
    (
        # 平台库（sys_* 属平台本体，数据权限左列与业务码下拉的来源）
        (
            DataSourceKey.MODULE.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.MODULE.value,
                table=cast("Table", SysModule.__table__),
                db_scope=DictTableScope.PLATFORM.value,
                i18n=DictI18nSpec(table=cast("Table", SysModuleI18n.__table__), relation_column="module_id"),
            ),
        ),
        (
            DataSourceKey.PRODUCT.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.PRODUCT.value,
                table=cast("Table", SysProduct.__table__),
                db_scope=DictTableScope.PLATFORM.value,
            ),
        ),
        (
            DataSourceKey.BUSINESS.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.BUSINESS.value,
                table=cast("Table", SysBusiness.__table__),
                db_scope=DictTableScope.PLATFORM.value,
                i18n=DictI18nSpec(table=cast("Table", SysBusinessI18n.__table__), relation_column="business_id"),
            ),
        ),
        (
            DataSourceKey.ACTION.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.ACTION.value,
                table=cast("Table", SysAction.__table__),
                db_scope=DictTableScope.PLATFORM.value,
                i18n=DictI18nSpec(table=cast("Table", SysActionI18n.__table__), relation_column="action_id"),
            ),
        ),
        (
            DataSourceKey.TENANT.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.TENANT.value,
                table=cast("Table", SysTenant.__table__),
                db_scope=DictTableScope.PLATFORM.value,
            ),
        ),
        # 租户库（各租户自有数据）
        (
            DataSourceKey.ROLE.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.ROLE.value,
                table=cast("Table", SysRole.__table__),
                mode=DictSourceMode.PORT.value,
            ),
        ),
        (
            DataSourceKey.USER.value,
            DictSourceSpec(data_source_key=DataSourceKey.USER.value, table=cast("Table", SysUser.__table__)),
        ),
        (
            DataSourceKey.CONFIG.value,
            DictSourceSpec(data_source_key=DataSourceKey.CONFIG.value, table=cast("Table", SysConfig.__table__)),
        ),
        (
            DataSourceKey.ICON.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.ICON.value,
                table=cast("Table", SysIcon.__table__),
                i18n=DictI18nSpec(table=cast("Table", SysIconI18n.__table__), relation_column="icon_id"),
            ),
        ),
        (
            DataSourceKey.TASK.value,
            DictSourceSpec(data_source_key=DataSourceKey.TASK.value, table=cast("Table", SysTask.__table__)),
        ),
        (
            DataSourceKey.IDENTITY_PROVIDER.value,
            DictSourceSpec(
                data_source_key=DataSourceKey.IDENTITY_PROVIDER.value,
                table=cast("Table", SysIdentityProvider.__table__),
                sort_column="sort",
            ),
        ),
        (
            DataSourceKey.CLIENT.value,
            DictSourceSpec(data_source_key=DataSourceKey.CLIENT.value, table=cast("Table", SysClient.__table__)),
        ),
    )
)
"""平台内建字典规格（12 条，与 `DataSourceKey` / `DATA_SOURCE_CATALOG` 一一对应）。"""


def platform_dict_specs() -> ConcurrentStableDict[str, DictSourceSpec]:
    """取规格副本（装配期注入提供者；避免外部改动全局常量）。

    Returns:
        ConcurrentStableDict[str, DictSourceSpec]: `data_source_key` → 规格。
    """
    return ConcurrentStableDict(PLATFORM_DICT_SPECS)

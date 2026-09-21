"""字典能力域：字典取数、后端翻译与缓存域三契约（真实取数与缓存随通用能力·字典模块阶段回补）。

- 常量：缓存域 `DICT_CACHE_DOMAIN`（dict）、条目状态 `DICT_STATUSES`（enabled / disabled）、
  探针上限 `DICT_PROBE_LIMIT`（2001）、占位版本 `NULL_DICT_VERSION`；默认语言复用 i18n `DEFAULT_LOCALE`。
- 参数对象：`DictQuery`（单类型取数，locale 由实现从请求上下文解析）/ `DictBatchQuery`（批量合并）/
  `DictTranslateQuery`（后端翻译）。
- 结果契约：`DictItem`（value / label / code / parent_id / sort / status / color）/
  `DictTypeResult`（version / items / has_more / total）/ `DictBatchResult`（version / items）。
- `BaseDictSource`（`key = plugin_key = "dict_source"`）：异步 `by_type`（版本比对 / 关键字 / 级联 /
  按值子集 / 上限）+ `batch`（多类型合并，一次请求）。
- `BaseDictTranslator`（`key = plugin_key = "dict_translator"`）：异步 `translate`（value → label，
  与取数共用同一份 L1 缓存，防 N+1）。
- `DictCacheRegion`（`key = plugin_key = "dict_cache_region"`）：缓存域扩展子类——固定 `domain="dict"`，
  提供 `dict_key` / `version_key` / `is_version_current`；真实 L1 双 Region 随通用能力阶段继承本类回补。
- 提供者 `get_dict_source` / `get_dict_translator` / `get_dict_cache_region`（应用级单例；
  公共依赖经 `app/api/deps.py` 统一导出）。

口径：**版本比对只承担「缓存是否新鲜」判断**——`DictTypeResult.items` 三态：`None`＝版本一致
（前端复用本地缓存）、`()`＝确无数据、非空＝条目集。租户隔离由实现侧拼缓存 key（含租户前缀）、
契约方法不显式传租户参数，调用方不可绕过。普通运行时链路**不返回扩展属性 `attr_json`**（归高级查询
接口 02-4-9 / 02-4-20）。业务与前端只经本出口取数与翻译，**不直连字典表、不自建字典缓存**。
真实取数 / 缓存 / 写路径（删 key + INCR 版本键）/ 高级查询随通用能力·字典模块阶段。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import cast

from fastapi import Request
from pydantic import Field

from app.cache.base import CacheRegion
from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.i18n.base import DEFAULT_LOCALE
from app.schemas.base import BaseSchema

__all__ = [
    "DICT_CACHE_DOMAIN",
    "DICT_PROBE_LIMIT",
    "DICT_STATUSES",
    "NULL_DICT_VERSION",
    "BaseDictSource",
    "BaseDictTranslator",
    "DictBatchQuery",
    "DictBatchResult",
    "DictCacheRegion",
    "DictItem",
    "DictQuery",
    "DictTranslateQuery",
    "DictTypeResult",
    "get_dict_cache_region",
    "get_dict_source",
    "get_dict_translator",
]

DICT_CACHE_DOMAIN = "dict"
"""缓存域简称（`DictCacheRegion.domain`；key `bms:{tenant}:dict:...`）。"""

DICT_STATUSES: tuple[str, ...] = ("enabled", "disabled")
"""字典条目状态（`enabled` 启用 / `disabled` 停用）。"""

DICT_PROBE_LIMIT = 2001
"""探针条数上限（前端首次以 `limit=2001` 判别大小字典；阈值 2000 对齐 06_06）。"""

NULL_DICT_VERSION = 1
"""占位全局版本号（空实现固定下发，供版本比对断言）。"""


class DictQuery(BaseSchema):
    """单类型取数参数对象（`locale` 由实现从请求上下文解析，不入参）。"""

    dict_type: str = Field(description="字典类型码")
    version: int | None = Field(default=None, description="客户端本地版本号；与全局一致时 items 返回空")
    keyword: str | None = Field(default=None, description="关键字（label / value / code，命中列由实现定义）")
    parent_id: str | None = Field(default=None, description="级联父值（引用父条目 value）")
    values: tuple[str, ...] | None = Field(default=None, description="指定 value 子集（超大字典批量翻译用）")
    limit: int | None = Field(default=None, description="返回条数上限（探针传 DICT_PROBE_LIMIT）")


class DictBatchQuery(BaseSchema):
    """批量合并取数参数对象（表单页多字典字段合并为一次请求）。"""

    types: tuple[str, ...] = Field(description="字典类型码序列")
    version: int | None = Field(default=None, description="客户端本地版本号；一致的类型 items 返回空")
    locale: str = Field(default=DEFAULT_LOCALE, description="语言（默认 zh-CN）")


class DictTranslateQuery(BaseSchema):
    """后端翻译参数对象（value → label）。"""

    dict_type: str = Field(description="字典类型码")
    values: tuple[str, ...] = Field(description="待翻译 value 序列")
    locale: str = Field(default=DEFAULT_LOCALE, description="语言（默认 zh-CN）")


class DictItem(BaseSchema):
    """字典条目（普通运行时链路字段；不含扩展属性 `attr_json`）。"""

    value: str = Field(description="条目值")
    label: str = Field(description="条目标签（按 locale）")
    code: str = Field(default="", description="条目编码")
    parent_id: str | None = Field(default=None, description="级联父值（引用父条目 value；None＝顶层）")
    sort: int = Field(default=0, description="排序值")
    status: str = Field(default="enabled", description="状态（enabled / disabled）")
    color: str | None = Field(default=None, description="语义色（供状态标签取色，可空）")


class DictTypeResult(BaseSchema):
    """单类型取数结果（`items=None` 表示版本一致，前端复用本地缓存）。"""

    version: int = Field(default=0, description="当前全局版本号")
    items: tuple[DictItem, ...] | None = Field(
        default=None, description="条目集；None＝版本一致（省流量）；空元组＝确无数据"
    )
    has_more: bool = Field(default=False, description="是否还有更多（超过 limit 截断）")
    total: int = Field(default=0, description="命中总数")


class DictBatchResult(BaseSchema):
    """批量合并取数结果（内层 `DictTypeResult.version` 与批量全局 `version` 同值）。"""

    version: int = Field(default=0, description="当前全局版本号")
    items: dict[str, DictTypeResult | None] = Field(
        default_factory=dict,
        description="按类型的取数结果；None＝该类型版本一致",
    )


class BaseDictSource(BasePluggable, ABC):
    """字典取数契约：单类型取数与批量合并取数。"""

    key: str = "dict_source"
    plugin_key: str = "dict_source"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def by_type(self, query: DictQuery) -> DictTypeResult:
        """按类型取字典（版本比对 / 关键字 / 级联 / 按值子集 / 条数上限）。

        Args:
            query: 单类型取数参数对象。

        Returns:
            DictTypeResult: 取数结果（版本一致时 `items=None`）。
        """

    @abstractmethod
    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        """批量合并取字典（一次请求多类型，表单页多字段合并）。

        Args:
            query: 批量取数参数对象。

        Returns:
            DictBatchResult: 批量结果（版本一致的类型 `items=None`）。
        """


class BaseDictTranslator(BasePluggable, ABC):
    """字典翻译契约：value → label（后端场景，与取数共用同一份 L1 缓存）。"""

    key: str = "dict_translator"
    plugin_key: str = "dict_translator"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def translate(self, query: DictTranslateQuery) -> Mapping[str, str]:
        """按 value 批量翻译为 label（当前 locale）。

        Args:
            query: 翻译参数对象。

        Returns:
            Mapping[str, str]: value → label；未命中 value 回退原值（由实现定义）。
        """


class DictCacheRegion(CacheRegion, ABC):
    """字典缓存域扩展子类：固定 `domain="dict"` 并补充字典 key 与版本判定。

    真实 L1 双 Region（小字典整类型 + 超大字典已查条目局部子集，按版本惰性比对）随通用能力阶段
    继承本类回补；本任务只固化 key 规范与版本语义。
    """

    key: str = "dict_cache_region"
    plugin_key: str = "dict_cache_region"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    def domain(self) -> str:
        """业务域简称（固定 `dict`）。

        Returns:
            str: 字典缓存域简称。
        """
        return DICT_CACHE_DOMAIN

    def dict_key(self, tenant: str | None, locale: str, dict_type: str) -> str:
        """拼字典类型缓存 key（`bms:{tenant}:dict:{locale}:{type}`）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。

        Returns:
            str: 缓存 key。
        """
        return self.build_key(f"{locale}:{dict_type}", tenant=tenant)

    def version_key(self, tenant: str | None) -> str:
        """拼字典全局版本键（`bms:{tenant}:dict:version`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            str: 版本键。
        """
        return self.build_key("version", tenant=tenant)

    def value_key(self, tenant: str | None, locale: str, dict_type: str) -> str:
        """拼字典按值子集缓存键（`bms:{tenant}:dict:{locale}:{type}:v`，整体映射 JSON）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。

        Returns:
            str: 子集缓存 key。
        """
        return self.build_key(f"{locale}:{dict_type}:v", tenant=tenant)

    def is_version_current(self, version: int, *, tenant: str | None) -> bool:
        """版本一致性判定（派生）。

        Args:
            version: 记录时捕获的版本号。
            tenant: 租户标识；None 为全局。

        Returns:
            bool: 一致为 True。
        """
        return not self.is_stale(self.version_key(tenant), version)

    async def aget_type(self, tenant: str | None, locale: str, dict_type: str) -> object | None:
        """读类型缓存（异步；缺省回退同步实现，Redis 子类覆写为真异步）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。

        Returns:
            object | None: 缓存值 `{version, items, has_more, total}`；未命中返回 None。
        """
        return self.get(self.dict_key(tenant, locale, dict_type))

    async def aset_type(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        value: object,
        ttl: int | None = None,
    ) -> None:
        """写类型缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        self.set(self.dict_key(tenant, locale, dict_type), value, ttl)

    async def adrop_type(self, tenant: str | None, locale: str, dict_type: str) -> None:
        """删类型缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
        """
        self.delete(self.dict_key(tenant, locale, dict_type))

    async def avalue_subset(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        values: Sequence[str],
    ) -> Mapping[str, str]:
        """读按值子集缓存（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            values: 待查 value 序列。

        Returns:
            Mapping[str, str]: value → label（仅命中项）。
        """
        cached = self.get(self.value_key(tenant, locale, dict_type))
        if not isinstance(cached, Mapping):
            return {}
        payload = cast("Mapping[str, object]", cached)
        result: dict[str, str] = {}
        for value in values:
            if value in payload:
                result[value] = str(payload[value])
        return result

    async def aset_value_subset(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        mapping: Mapping[str, str],
    ) -> None:
        """回填按值子集缓存（异步；与既有映射合并后整体写入）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            mapping: 待回填的 value → label 映射。
        """
        key = self.value_key(tenant, locale, dict_type)
        current = self.get(key)
        merged: dict[str, str] = {}
        if isinstance(current, Mapping):
            payload = cast("Mapping[str, object]", current)
            merged.update({str(item): str(label) for item, label in payload.items()})
        merged.update({str(item): str(label) for item, label in mapping.items()})
        self.set(key, merged)

    async def aversion(self, tenant: str | None) -> int:
        """读全局版本号（异步；缺省回退同步实现）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 当前版本号。
        """
        return self.get_global_version()

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增全局版本号（异步；缺省回退为当前版本 + 1）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 递增后的版本号。
        """
        return self.get_global_version() + 1

    async def alock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
        ttl: int = 5,
    ) -> bool:
        """类型取数互斥锁（异步；防击穿；缺省恒获锁）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。
            ttl: 锁有效期（秒）。

        Returns:
            bool: 获锁为 True。
        """
        return True

    async def arelease_lock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
    ) -> bool:
        """释放类型取数互斥锁（异步；缺省空操作，Redis / 内存子类覆写比对令牌）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。

        Returns:
            bool: 释放到为 True。
        """
        return True


def get_dict_source(request: Request) -> BaseDictSource:
    """取应用级字典取数契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseDictSource: 应用装配的字典取数实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseDictSource",
        resolve_plugin(
            "dict_source",
            settings.dict_source.provider,
            expected_version=BaseDictSource.contract_version,
        ),
    )


def get_dict_translator(request: Request) -> BaseDictTranslator:
    """取应用级字典翻译契约（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseDictTranslator: 应用装配的字典翻译实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseDictTranslator",
        resolve_plugin(
            "dict_translator",
            settings.dict_translator.provider,
            expected_version=BaseDictTranslator.contract_version,
        ),
    )


def get_dict_cache_region(request: Request) -> DictCacheRegion:
    """取应用级字典缓存域扩展（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        DictCacheRegion: 应用装配的字典缓存域实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "DictCacheRegion",
        resolve_plugin(
            "dict_cache_region",
            settings.dict_cache_region.provider,
            expected_version=DictCacheRegion.contract_version,
        ),
    )

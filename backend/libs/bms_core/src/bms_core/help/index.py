"""帮助锚点索引：自然键归集、缓存键与缓存读写（08_02）。

解析链需要「按业务码 / 字段键 / 权限码动作 / 模块段」快速定位锚点。五张元数据表量级很小（百级），
但逐级查询会在每次页面帮助请求上产生 5 组 SQL；因此把归集结果做成**索引**，按**元数据版本号**缓存
（与 `my_menus` 同一版本源，任一写路径递增即失效），请求期只做内存查表。

本模块只承载索引值对象与缓存读写；DB 归集在 `bms_core/repositories/help_anchor.py`，
候选链与解析编排在 `bms_core/help/context.py`。

缓存载荷用**内部契约模型**（`BaseSchema`）承载：结构校验交给 pydantic，脏缓存 / 旧结构一律解析失败
（返回 `None`），由调用方按未命中重建——避免手写逐字段校验分支。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.cache.base import CacheRegion, build_cache_key
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.objects import BaseValueObject
from bms_core.core.serialization import normalize_collections
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema

__all__ = [
    "HELP_CACHE_DOMAIN",
    "HelpAnchorIndex",
    "HelpMenuAnchor",
    "decode_help_anchor_index",
    "encode_help_anchor_index",
    "help_anchor_index_key",
    "load_cached_help_anchor_index",
]

HELP_CACHE_DOMAIN = "help"
"""帮助能力域缓存域名（键第二段）。"""


def help_anchor_index_key(version: int) -> str:
    """锚点索引缓存键（锚点属平台库，键不带租户维度）。

    Args:
        version: 元数据版本号（变更即 +1，旧版本键自然过期）。

    Returns:
        str: `bms:global:help:anchors:{version}`。
    """
    return build_cache_key(tenant=None, domain=HELP_CACHE_DOMAIN, business_key=f"anchors:{version}")


@dataclass(frozen=True)
class HelpMenuAnchor(BaseValueObject):
    """菜单上的模块级锚点（模块级无自然键列，按锚点段匹配）。

    Attributes:
        product: 锚点产品段。
        module_key: 锚点模块段。
        help_key: 锚点原值。
        model_id: 菜单主键（多产品同名段时稳定排序用）。
    """

    product: str
    module_key: str
    help_key: str
    model_id: int


@dataclass(frozen=True)
class HelpAnchorIndex(BaseValueObject):
    """锚点索引（按自然键归集；空集合表示该层级无已登记锚点）。

    Attributes:
        menus: 菜单模块级锚点（按菜单主键升序）。
        forms: 业务码 → 表单锚点。
        fields:（业务码, 字段键）→ 字段锚点。
        buttons:（业务码, 动作码）→ 按钮锚点。
        actions: 动作码 → 全局动词兜底锚点。
    """

    menus: ConcurrentStableFrozenList[HelpMenuAnchor] = field(default_factory=lambda: ConcurrentStableFrozenList())
    forms: ConcurrentStableFrozenDict[str, str] = field(default_factory=lambda: ConcurrentStableFrozenDict())
    fields: ConcurrentStableFrozenDict[tuple[str, str], str] = field(
        default_factory=lambda: ConcurrentStableFrozenDict()
    )
    buttons: ConcurrentStableFrozenDict[tuple[str, str], str] = field(
        default_factory=lambda: ConcurrentStableFrozenDict()
    )
    actions: ConcurrentStableFrozenDict[str, str] = field(default_factory=lambda: ConcurrentStableFrozenDict())


class _MenuAnchorPayload(BaseSchema):
    """缓存载荷：菜单锚点条目（`menu_pk` 而非 `model_id`，避免 ID 序列化口径干扰）。"""

    product: str = Field(min_length=1, description="产品段")
    module_key: str = Field(min_length=1, description="模块段")
    help_key: str = Field(min_length=1, description="锚点值")
    menu_pk: int = Field(description="菜单主键")


class _PairAnchorPayload(BaseSchema):
    """缓存载荷：单键锚点条目（业务码 → 表单 / 动作码 → 兜底）。"""

    key: str = Field(min_length=1, description="自然键")
    help_key: str = Field(min_length=1, description="锚点值")


class _CompositeAnchorPayload(BaseSchema):
    """缓存载荷：复合键锚点条目（业务码 + 字段键 / 动作码）。"""

    business: str = Field(min_length=1, description="业务码")
    code: str = Field(min_length=1, description="字段键或动作码")
    help_key: str = Field(min_length=1, description="锚点值")


class _HelpAnchorIndexPayload(BaseSchema):
    """缓存载荷根：五类锚点清单（段缺失即整份判为脏缓存；不认识的段忽略）。"""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, extra="ignore")

    menus: Annotated[ConcurrentStableList[_MenuAnchorPayload], CONTRACT_COLLECTION] = Field(description="菜单锚点")
    forms: Annotated[ConcurrentStableList[_PairAnchorPayload], CONTRACT_COLLECTION] = Field(description="表单锚点")
    fields: Annotated[ConcurrentStableList[_CompositeAnchorPayload], CONTRACT_COLLECTION] = Field(
        description="字段锚点"
    )
    buttons: Annotated[ConcurrentStableList[_CompositeAnchorPayload], CONTRACT_COLLECTION] = Field(
        description="按钮锚点"
    )
    actions: Annotated[ConcurrentStableList[_PairAnchorPayload], CONTRACT_COLLECTION] = Field(
        description="动作码兜底锚点"
    )


def encode_help_anchor_index(index: HelpAnchorIndex) -> object:
    """索引 → 缓存载荷（JSON 可往返：全部为内置容器与标量）。

    Args:
        index: 锚点索引。

    Returns:
        object: 内置容器构成的载荷（写入缓存区）。
    """
    payload = _HelpAnchorIndexPayload(
        menus=ConcurrentStableList(
            _MenuAnchorPayload(
                product=menu.product,
                module_key=menu.module_key,
                help_key=menu.help_key,
                menu_pk=menu.model_id,
            )
            for menu in index.menus
        ),
        forms=ConcurrentStableList(_PairAnchorPayload(key=key, help_key=value) for key, value in index.forms.items()),
        fields=ConcurrentStableList(
            _CompositeAnchorPayload(business=business, code=code, help_key=value)
            for (business, code), value in index.fields.items()
        ),
        buttons=ConcurrentStableList(
            _CompositeAnchorPayload(business=business, code=code, help_key=value)
            for (business, code), value in index.buttons.items()
        ),
        actions=ConcurrentStableList(
            _PairAnchorPayload(key=key, help_key=value) for key, value in index.actions.items()
        ),
    )
    return normalize_collections(payload.model_dump())


def decode_help_anchor_index(payload: object) -> HelpAnchorIndex | None:
    """缓存载荷 → 索引（脏缓存 / 旧结构返回 `None`，由调用方按未命中重建）。

    Args:
        payload: 缓存读出的载荷。

    Returns:
        HelpAnchorIndex | None: 锚点索引；结构非法返回 None。
    """
    try:
        parsed = _HelpAnchorIndexPayload.model_validate(payload)
    except ValueError:
        return None
    return HelpAnchorIndex(
        menus=ConcurrentStableFrozenList(
            HelpMenuAnchor(
                product=item.product,
                module_key=item.module_key,
                help_key=item.help_key,
                model_id=item.menu_pk,
            )
            for item in parsed.menus
        ),
        forms=ConcurrentStableFrozenDict((item.key, item.help_key) for item in parsed.forms),
        fields=ConcurrentStableFrozenDict(((item.business, item.code), item.help_key) for item in parsed.fields),
        buttons=ConcurrentStableFrozenDict(((item.business, item.code), item.help_key) for item in parsed.buttons),
        actions=ConcurrentStableFrozenDict((item.key, item.help_key) for item in parsed.actions),
    )


async def load_cached_help_anchor_index(
    cache: CacheRegion,
    *,
    version: int,
    ttl: int,
    build: Callable[[], Awaitable[HelpAnchorIndex]],
) -> HelpAnchorIndex:
    """装载锚点索引（缓存优先，未命中 / 脏载荷回源重建）。

    Args:
        cache: 缓存 Region。
        version: 元数据版本号（缓存键组成部分）。
        ttl: 缓存有效期（秒）。
        build: 回源构造器（DB 归集；仅缓存未命中时调用）。

    Returns:
        HelpAnchorIndex: 锚点索引。
    """
    key = help_anchor_index_key(version)
    cached = await cache.aget(key)
    if cached is not None:
        index = decode_help_anchor_index(cached)
        if index is not None:
            return index
    index = await build()
    await cache.aset(key, encode_help_anchor_index(index), ttl)
    return index

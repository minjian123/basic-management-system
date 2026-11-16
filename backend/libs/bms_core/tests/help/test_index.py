"""帮助锚点索引：编码往返、缓存命中与脏载荷重建（08_02；Kiwi 2521）。"""

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.help.index import (
    HelpAnchorIndex,
    HelpMenuAnchor,
    decode_help_anchor_index,
    encode_help_anchor_index,
    help_anchor_index_key,
    load_cached_help_anchor_index,
)

pytestmark = pytest.mark.kiwi_id(2521)


def _index() -> HelpAnchorIndex:
    """构造含五类锚点的索引。

    Returns:
        HelpAnchorIndex: 锚点索引。
    """
    return HelpAnchorIndex(
        menus=ConcurrentStableFrozenList(
            [
                HelpMenuAnchor(
                    product="platform", module_key="probe_module", help_key="platform:probe_module:::", model_id=7
                )
            ]
        ),
        forms=ConcurrentStableFrozenDict({"probe_biz": "platform:probe_module:probe_biz::"}),
        fields=ConcurrentStableFrozenDict(
            {("probe_biz", "probe_field"): "platform:probe_module:probe_biz:probe_field:"}
        ),
        buttons=ConcurrentStableFrozenDict(
            {("probe_biz", "probe_create"): "platform:probe_module:probe_biz::probe_create"}
        ),
        actions=ConcurrentStableFrozenDict({"probe_create": "platform::::probe_create"}),
    )


def test_cache_key_is_versioned_and_global() -> None:
    """缓存键按版本号分代、不带租户维度（锚点属平台库）。"""
    assert help_anchor_index_key(3) == "bms:global:help:anchors:3"


def test_encode_decode_roundtrip() -> None:
    """编码 → 解码保持五类锚点与主键（缓存 JSON 往返语义）。"""
    decoded = decode_help_anchor_index(encode_help_anchor_index(_index()))
    assert decoded is not None
    original = _index()
    assert decoded.menus == original.menus
    assert decoded.menus[0].model_id == 7
    assert dict(decoded.forms) == dict(original.forms)
    assert dict(decoded.fields) == dict(original.fields)
    assert dict(decoded.buttons) == dict(original.buttons)
    assert dict(decoded.actions) == dict(original.actions)


async def test_cached_index_builds_once() -> None:
    """连续两次读取只回源一次（第二次命中缓存）。"""
    cache = MemoryCacheRegion(domain="help")
    builds: ConcurrentStableList[int] = ConcurrentStableList()

    async def build() -> HelpAnchorIndex:
        """计数回源构造器。

        Returns:
            HelpAnchorIndex: 锚点索引。
        """
        builds.add(1)
        return _index()

    first = await load_cached_help_anchor_index(cache, version=1, ttl=60, build=build)
    second = await load_cached_help_anchor_index(cache, version=1, ttl=60, build=build)
    assert len(builds) == 1
    assert dict(second.actions) == dict(first.actions)


async def test_cached_index_rebuilds_on_dirty_payload() -> None:
    """缓存载荷结构不符 → 按未命中重建并回写正确载荷。"""
    cache = MemoryCacheRegion(domain="help")
    await cache.aset(help_anchor_index_key(1), {"menus": "broken"}, 60)
    builds: ConcurrentStableList[int] = ConcurrentStableList()

    async def build() -> HelpAnchorIndex:
        """计数回源构造器。

        Returns:
            HelpAnchorIndex: 锚点索引。
        """
        builds.add(1)
        return _index()

    index = await load_cached_help_anchor_index(cache, version=1, ttl=60, build=build)
    assert len(builds) == 1
    assert dict(index.forms) == {"probe_biz": "platform:probe_module:probe_biz::"}


@pytest.mark.parametrize(
    "payload",
    [
        "not-an-object",
        {"forms": [], "fields": [], "buttons": [], "actions": []},
        {
            "menus": ["not-an-object"],
            "forms": [],
            "fields": [],
            "buttons": [],
            "actions": [],
        },
        {
            "menus": [{"product": "p", "module_key": "m", "help_key": 1, "menu_pk": 1}],
            "forms": [],
            "fields": [],
            "buttons": [],
            "actions": [],
        },
        {
            "menus": [{"product": "p", "module_key": "m", "help_key": "k", "menu_pk": "x"}],
            "forms": [],
            "fields": [],
            "buttons": [],
            "actions": [],
        },
        {"menus": [], "forms": [["only-one"]], "fields": [], "buttons": [], "actions": []},
        {
            "menus": [],
            "forms": [{"key": "", "help_key": "k"}],
            "fields": [],
            "buttons": [],
            "actions": [],
        },
        {"menus": [], "forms": [], "fields": [["only", "two"]], "buttons": [], "actions": []},
    ],
)
def test_decode_rejects_broken_payload(payload: object) -> None:
    """脏缓存 / 旧结构一律返回 None（由调用方重建），不抛异常。"""
    assert decode_help_anchor_index(payload) is None


def test_decode_ignores_unknown_section() -> None:
    """多余段不影响解码（向前兼容）。"""
    payload = ConcurrentStableDict[str, object](
        {"menus": [], "forms": [], "fields": [], "buttons": [], "actions": [], "extra": {}}
    )
    decoded = decode_help_anchor_index(payload)
    assert decoded is not None
    assert decoded.menus == ConcurrentStableFrozenList()

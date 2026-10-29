"""参照拓扑模板：三档展开与非法模板（07C `02_01`；Kiwi 2366 用例 15）。"""

import pytest

from bms_core.collaboration import (
    DEFAULT_UNIT_KEY,
    TEMPLATE_GROUPED,
    TEMPLATE_ISOLATED,
    TEMPLATE_SINGLE,
    TEMPLATES,
    expand_template,
)
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ParamError

pytestmark = pytest.mark.kiwi_id(2366)

_DOMAINS = ("auth", "identity_federation", "org", "platform_registry")


def _units(name: str) -> ConcurrentStableDict[str, str]:
    """按模板展开为 `{域: 单元}`（便于断言）。

    Args:
        name: 模板名。

    Returns:
        ConcurrentStableDict[str, str]: 域的单元映射。
    """
    return ConcurrentStableDict((row.domain_key, row.unit_key) for row in expand_template(name, _DOMAINS))


def test_single_puts_every_domain_into_one_unit() -> None:
    """单体型：全部已登记域落同一个公共单元。"""
    units = _units(TEMPLATE_SINGLE)
    assert set(units) == set(_DOMAINS)
    assert set(units.values()) == {DEFAULT_UNIT_KEY}


def test_grouped_only_splits_registered_product_domains() -> None:
    """分组型：产品域登记后才拆组；平台域仍在公共单元（未登记域不凭空出现）。"""
    units = _units(TEMPLATE_GROUPED)
    assert units["auth"] == DEFAULT_UNIT_KEY
    assert units["platform_registry"] == DEFAULT_UNIT_KEY
    assert all(unit == DEFAULT_UNIT_KEY for unit in units.values())


def test_grouped_maps_product_domains_to_biz_units() -> None:
    """分组型：采购 / 仓储 / 销售域落 `biz-*` 单元（含产品前缀的域标识同样命中）。"""
    rows = expand_template(TEMPLATE_GROUPED, ("auth", "purchase", "biz_warehouse", "sales"))
    units = ConcurrentStableDict((row.domain_key, row.unit_key) for row in rows)
    assert units["purchase"] == "grp-purchase"
    assert units["biz_warehouse"] == "grp-ops"
    assert units["sales"] == "grp-ops"
    assert units["auth"] == DEFAULT_UNIT_KEY


def test_isolated_gives_each_domain_its_own_unit() -> None:
    """独立型：每域一个 `dom-*` 单元（下划线换连字符以符合单元命名）。"""
    units = _units(TEMPLATE_ISOLATED)
    assert units["identity_federation"] == "dom-identity-federation"
    assert units["org"] == "dom-org"
    assert len(set(units.values())) == len(_DOMAINS)


def test_unknown_template_rejected() -> None:
    """未知模板名即拒（10001）。"""
    with pytest.raises(ParamError, match="未知的拓扑模板"):
        expand_template("micro", _DOMAINS)


def test_empty_domain_set_expands_to_nothing() -> None:
    """无已登记域时展开为空（不产生空单元行）。"""
    assert expand_template(TEMPLATE_SINGLE, ()) == []


def test_template_names_are_frozen() -> None:
    """模板名清单固定三档（写入校验与错误提示同源）。"""
    assert list(TEMPLATES) == [TEMPLATE_SINGLE, TEMPLATE_GROUPED, TEMPLATE_ISOLATED]

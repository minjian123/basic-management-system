"""产品权限码种子测试（Kiwi 2254）：产品业务码与动作码登记与幂等键唯一。"""

import pytest

from ops import seed_menu


@pytest.mark.kiwi_id(2254)
def test_org_business_and_actions_seeded() -> None:
    """业务码种子含 `org`；动作码含域级四码与域专属 `move`。"""
    business_codes = {code for code, _zh, _en in seed_menu.BUSINESS_SEEDS}
    assert "org" in business_codes
    actions = {(business, action) for business, action, _zh, _en in seed_menu.ACTION_SEEDS}
    assert {
        ("org", "query"),
        ("org", "create"),
        ("org", "update"),
        ("org", "delete"),
        ("org", "move"),
    } <= actions


@pytest.mark.kiwi_id(2254)
def test_seed_lists_have_unique_keys() -> None:
    """业务码与「业务码 + 动作码」种子不重复（幂等键唯一，重跑不产生重复行）。"""
    business_codes = [code for code, _zh, _en in seed_menu.BUSINESS_SEEDS]
    assert len(business_codes) == len(set(business_codes))
    actions = [(business, action) for business, action, _zh, _en in seed_menu.ACTION_SEEDS]
    assert len(actions) == len(set(actions))

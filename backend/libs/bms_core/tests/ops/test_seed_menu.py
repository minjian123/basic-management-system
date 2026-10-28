"""平台种子去产品化用例（07B `03_03`；Kiwi 2254 改造）：平台种子不含产品条目、动作码字典不变。"""

import pytest

from bms_core.tenant.seed import menu as seed_menu

# 07B `03_03` 改造前的清单规模（凭据：设计 §2.1 实测 44 / 110 / 31）。
_BUSINESS_BEFORE = 44
_PERMISSIONS_BEFORE = 110
_ACTIONS_BEFORE = 31


@pytest.mark.kiwi_id(2254)
def test_platform_seed_has_no_product_entries() -> None:
    """平台种子只播平台自身数据：业务码与权限码清单不含产品条目。"""
    business_codes = {code for code, _zh, _en in seed_menu.BUSINESS_SEEDS}
    assert "mdm" not in business_codes
    permissions = {(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS}
    assert not {business for business, _action in permissions} - business_codes
    assert all(not business.startswith("mdm") for business, _action in permissions)


@pytest.mark.kiwi_id(2254)
def test_platform_seed_counts_drop_by_product_entries() -> None:
    """只移除产品条目：业务码 −1、权限码 −4，平台条目一条不少。"""
    assert len(seed_menu.BUSINESS_SEEDS) == _BUSINESS_BEFORE - 1
    assert len(seed_menu.PERMISSION_SEEDS) == _PERMISSIONS_BEFORE - 4


@pytest.mark.kiwi_id(2254)
def test_action_dictionary_unchanged() -> None:
    """动作码字典由平台权限码派生：移除产品权限码后动词集合不减少。"""
    actions = {code for code, _zh, _en in seed_menu.ACTION_SEEDS}
    assert len(actions) == _ACTIONS_BEFORE
    assert {"query", "create", "update", "delete"} <= actions


@pytest.mark.kiwi_id(2254)
def test_seed_lists_have_unique_keys() -> None:
    """业务码、动作码与「业务码 + 动作码」种子不重复（幂等键唯一，重跑不产生重复行）。"""
    business_codes = [code for code, _zh, _en in seed_menu.BUSINESS_SEEDS]
    assert len(business_codes) == len(set(business_codes))
    actions = [code for code, _zh, _en in seed_menu.ACTION_SEEDS]
    assert len(actions) == len(set(actions))
    permissions = [(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS]
    assert len(permissions) == len(set(permissions))

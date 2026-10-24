"""产品权限码种子测试（Kiwi 2254）：产品业务码与权限码组合登记与幂等键唯一。"""

import pytest

from ops import seed_menu


@pytest.mark.kiwi_id(2254)
def test_mdm_business_and_permissions_seeded() -> None:
    """业务码种子含 `mdm`；权限码含域级四码（部门移动复用 `update`，无专属 `move`）。

    服务标识于 2026-10-23 由 `org` 归并为 `mdm`（mdm 阶段一 `01_05`），种子随之对齐。
    """
    business_codes = {code for code, _zh, _en in seed_menu.BUSINESS_SEEDS}
    assert "mdm" in business_codes
    permissions = {(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS}
    assert {
        ("mdm", "query"),
        ("mdm", "create"),
        ("mdm", "update"),
        ("mdm", "delete"),
    } <= permissions


@pytest.mark.kiwi_id(2254)
def test_seed_lists_have_unique_keys() -> None:
    """业务码、动作码与「业务码 + 动作码」种子不重复（幂等键唯一，重跑不产生重复行）。"""
    business_codes = [code for code, _zh, _en in seed_menu.BUSINESS_SEEDS]
    assert len(business_codes) == len(set(business_codes))
    actions = [code for code, _zh, _en in seed_menu.ACTION_SEEDS]
    assert len(actions) == len(set(actions))
    permissions = [(business, action) for business, action, _zh, _en in seed_menu.PERMISSION_SEEDS]
    assert len(permissions) == len(set(permissions))

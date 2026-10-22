"""菜单种子与内置角色授权的服务侧一致性用例（`02_04` / `02_01`）。

基座实现用例（幂等 / 缺码跳过 / 三权清单 / 预演 / 互斥拒绝绑定）已随 14_04 迁至
`backend/libs/bms_core/tests/tenant/seed/test_rbac.py`（实现已下沉 `bms_core.tenant.seed.rbac`）。
本文件只保留**服务侧**校验：`ops.seed_menu` 的权限码 / 按钮清单与角色授权清单的口径一致。
"""

import pytest


@pytest.mark.kiwi_id(2270)
def test_seed_menu_registers_assign_role() -> None:
    """`user:assign_role` 权限码与「用户管理」页按钮挂接已在菜单元数据种子登记（`02_01`）。"""
    from ops.seed_menu import BUTTON_SEEDS, PERMISSION_SEEDS

    assert ("user", "assign_role", "分配角色", "Assign role") in PERMISSION_SEEDS
    assert ("/sys/users", "分配角色", "assign_role", "interface", 7) in BUTTON_SEEDS

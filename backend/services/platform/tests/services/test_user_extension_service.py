"""用户扩展信息业务服务用例（Kiwi 2238）：并发删除竞态兜底。

端点层用例已覆盖读列表 / 新增 / 更新 / 冲突 / 不存在的常规路径；本文件以替身仓储覆盖
`update_extension` 中「作用域内刚取到行、写回却已消失」的竞态兜底分支（抛 10002）。
"""

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import NotFoundError
from bms_core.models.platform.user import SysUserExtension
from bms_platform.domains.user.repositories.user_extension import UserExtensionRepository
from bms_platform.domains.user.services.user_extension import UserExtensionService


class _VanishingRepository:
    """替身仓储：`get` 命中、`update` 未命中（模拟并发删除）。"""

    async def get(self, item_id: int) -> SysUserExtension | None:
        """返回一行既有记录。

        Args:
            item_id: 记录主键。

        Returns:
            SysUserExtension | None: 记录行。
        """
        return SysUserExtension(id=item_id, user_id=1001, label="vip")

    async def get_by_label(self, user_id: int, label: str) -> SysUserExtension | None:
        """同键探测（无既有行）。

        Args:
            user_id: 用户主键。
            label: 扩展标签。

        Returns:
            SysUserExtension | None: 恒 None。
        """
        del user_id, label
        return None

    async def update(self, item_id: int, **values: object) -> SysUserExtension | None:
        """写回未命中（并发删除）。

        Args:
            item_id: 记录主键。
            **values: 更新字段值。

        Returns:
            SysUserExtension | None: 恒 None。
        """
        del item_id, values
        return None

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SysUserExtension]:
        """按用户列示（替身恒空）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysUserExtension]: 恒空列表。
        """
        del user_id
        return ConcurrentStableList()


@pytest.mark.kiwi_id(2238)
async def test_update_extension_raises_when_row_vanishes() -> None:
    """更新竞态：取行成功但写回未命中 → `NotFoundError`（10002）。"""
    repository = cast("UserExtensionRepository", _VanishingRepository())
    service = UserExtensionService(repository)

    with pytest.raises(NotFoundError) as excinfo:
        await service.update_extension(7, label="vip", remark=None)
    assert excinfo.value.code == 10002

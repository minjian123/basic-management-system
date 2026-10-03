"""平台服务 services 层：用户扩展信息业务服务（读列表 + 新增 / 更新一条）。

具名插槽样例插件的后端契约实现：同用户同标签唯一（冲突抛 10003）、目标缺失抛 10002。
写操作在**同一事务边界**内完成「唯一性探测 + 落库」（探测先于工作单元开启，避免会话重复开启事务）。
"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ConflictError, NotFoundError
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.services.base_transactional_service import BaseTransactionalService
from bms_platform.models.system import SysUserExtension
from bms_platform.repositories.user_extension import UserExtensionRepository


class UserExtensionService(BaseTransactionalService[SysUserExtension]):
    """用户扩展信息业务服务（写路径经工作单元开启事务边界）。"""

    def __init__(self, repository: UserExtensionRepository, uow: UnitOfWork | None = None) -> None:
        """初始化。

        Args:
            repository: 用户扩展信息仓储。
            uow: 请求级工作单元；None 用空实现。
        """
        super().__init__(repository, uow)
        self._extensions = repository

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SysUserExtension]:
        """按用户列示扩展信息（读操作，不包事务）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysUserExtension]: 扩展信息列表（插入序）。
        """
        return await self._extensions.list_by_user(user_id)

    async def create_extension(self, *, user_id: int, label: str, remark: str | None) -> SysUserExtension:
        """新增一条扩展信息（事务内；同用户同标签冲突即拒绝）。

        Args:
            user_id: 用户主键。
            label: 扩展标签。
            remark: 备注。

        Returns:
            SysUserExtension: 新建记录。

        Raises:
            ConflictError: 同用户同标签已存在（10003）。
        """
        async with self._uow.begin():
            if await self._extensions.get_by_label(user_id, label) is not None:
                raise ConflictError(f"扩展标签已存在：{label}")
            return await self._extensions.create(user_id=user_id, label=label, remark=remark)

    async def update_extension(self, extension_id: int, *, label: str, remark: str | None) -> SysUserExtension:
        """更新一条扩展信息（事务内；整体替换 `label` / `remark`）。

        Args:
            extension_id: 扩展信息主键。
            label: 扩展标签（改后与同一用户的其它行冲突即拒绝）。
            remark: 备注（null 即清空）。

        Returns:
            SysUserExtension: 更新后记录。

        Raises:
            NotFoundError: 记录不存在（10002）。
            ConflictError: 改后与既有行同标签（10003）。
        """
        async with self._uow.begin():
            current = await self.get(extension_id)
            if label != current.label and await self._extensions.get_by_label(current.user_id, label) is not None:
                raise ConflictError(f"扩展标签已存在：{label}")
            updated = await self._extensions.update(extension_id, label=label, remark=remark)
            if updated is None:
                raise NotFoundError(f"记录不存在：{extension_id}")
            return updated

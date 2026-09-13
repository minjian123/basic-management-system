"""demo 示例模块：业务服务（继承 BaseTransactionalService，内存实现）。"""

from app.models.demo import Demo
from app.repositories.demo_repository import DemoRepository
from app.services.base_transactional_service import BaseTransactionalService


class DemoService(BaseTransactionalService[Demo]):
    """demo 业务服务（内存实现）：模块命名方法转发基类通用 CRUD。"""

    def __init__(self, repository: DemoRepository) -> None:
        super().__init__(repository)

    def list_demos(self) -> list[Demo]:
        """返回全部 demo。

        Returns:
            list[Demo]: 按 ID 升序的记录列表。
        """
        return self.list()

    def get_demo(self, demo_id: int) -> Demo:
        """按 ID 查询 demo。

        Args:
            demo_id: 记录 ID。

        Returns:
            Demo: 记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        return self.get(demo_id)

    def create_demo(self, name: str) -> Demo:
        """创建 demo。

        Args:
            name: demo 名称。

        Returns:
            Demo: 新建记录。
        """
        return self.create(name=name)

    def update_demo(self, demo_id: int, name: str) -> Demo:
        """更新 demo 名称。

        Args:
            demo_id: 记录 ID。
            name: 新名称。

        Returns:
            Demo: 更新后的记录。

        Raises:
            NotFoundError: 记录不存在。
        """
        return self.update(demo_id, name=name)

    def delete_demo(self, demo_id: int) -> None:
        """删除 demo。

        Args:
            demo_id: 记录 ID。

        Raises:
            NotFoundError: 记录不存在。
        """
        self.delete(demo_id)

"""demo 示例模块：业务服务（内存实现）。"""

from app.models.demo import Demo
from app.repositories.demo_repository import DemoRepository


class DemoService:
    """demo 业务服务（内存实现）。

    03 域落库时替换仓库实现；事务边界（with session.begin()）随数据库接入补充。
    """

    def __init__(self, repository: DemoRepository) -> None:
        self._repository = repository

    def list_demos(self) -> list[Demo]:
        """返回全部 demo。

        Returns:
            list[Demo]: 按 ID 升序的记录列表。
        """
        return self._repository.list()

    def get_demo(self, demo_id: int) -> Demo | None:
        """按 ID 查询 demo。

        Args:
            demo_id: 记录 ID。

        Returns:
            Demo | None: 存在时返回记录，否则 None。
        """
        return self._repository.get(demo_id)

    def create_demo(self, name: str) -> Demo:
        """创建 demo。

        Args:
            name: demo 名称。

        Returns:
            Demo: 新建记录。
        """
        return self._repository.create(name)

    def update_demo(self, demo_id: int, name: str) -> Demo | None:
        """更新 demo 名称。

        Args:
            demo_id: 记录 ID。
            name: 新名称。

        Returns:
            Demo | None: 更新后的记录，不存在时 None。
        """
        return self._repository.update(demo_id, name)

    def delete_demo(self, demo_id: int) -> bool:
        """删除 demo。

        Args:
            demo_id: 记录 ID。

        Returns:
            bool: 删除成功 True，不存在 False。
        """
        return self._repository.delete(demo_id)

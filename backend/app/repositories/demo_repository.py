"""demo 示例模块：内存仓库（占位实现，03 域替换为数据库访问）。"""

from app.models.demo import Demo


class DemoRepository:
    """demo 内存仓库：字典存储 + 自增 ID（接口与数据库实现保持一致）。"""

    def __init__(self) -> None:
        self._items: dict[int, Demo] = {}
        self._next_id = 1

    def list(self) -> list[Demo]:
        """返回全部记录（按 ID 升序）。

        Returns:
            list[Demo]: 记录列表。
        """
        return [self._items[key] for key in sorted(self._items)]

    def get(self, demo_id: int) -> Demo | None:
        """按 ID 查询记录。

        Args:
            demo_id: 记录 ID。

        Returns:
            Demo | None: 存在时返回记录，否则 None。
        """
        return self._items.get(demo_id)

    def create(self, name: str) -> Demo:
        """创建记录并分配自增 ID。

        Args:
            name: 记录名称。

        Returns:
            Demo: 新建记录。
        """
        demo = Demo(id=self._next_id, name=name)
        self._items[demo.id] = demo
        self._next_id += 1
        return demo

    def update(self, demo_id: int, name: str) -> Demo | None:
        """更新记录名称。

        Args:
            demo_id: 记录 ID。
            name: 新名称。

        Returns:
            Demo | None: 更新后的记录，不存在时 None。
        """
        demo = self._items.get(demo_id)
        if demo is None:
            return None
        updated = Demo(id=demo.id, name=name)
        self._items[demo_id] = updated
        return updated

    def delete(self, demo_id: int) -> bool:
        """删除记录。

        Args:
            demo_id: 记录 ID。

        Returns:
            bool: 删除成功 True，不存在 False。
        """
        if demo_id not in self._items:
            return False
        del self._items[demo_id]
        return True

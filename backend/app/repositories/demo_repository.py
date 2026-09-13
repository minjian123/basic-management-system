"""demo 示例模块：内存仓库（继承 BaseRepository，03 域替换为数据库访问）。"""

from app.models.demo import Demo
from app.repositories.base_memory_repository import BaseMemoryRepository


class DemoRepository(BaseMemoryRepository[Demo]):
    """demo 仓库：只声明实体构造规则，通用存取由基类提供。"""

    def _build(self, item_id: int, values: dict[str, object]) -> Demo:
        return Demo(id=item_id, name=str(values["name"]))

    def _apply(self, item: Demo, values: dict[str, object]) -> Demo:
        return Demo(id=item.id, name=str(values["name"]))

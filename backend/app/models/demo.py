"""demo 示例模块：领域模型（内存占位，03 域落库时替换为 SQLAlchemy 模型）。"""

from dataclasses import dataclass

from app.core.base import BaseObject


@dataclass
class Demo(BaseObject):
    """demo 示例实体（内存实现）。

    说明：@dataclass 生成的 __eq__/__repr__ 优先，to_dict/to_json 从根基类继承。
    """

    id: int
    name: str

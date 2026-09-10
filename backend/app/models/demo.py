"""demo 示例模块：领域模型（内存占位，03 域落库时替换为 SQLAlchemy 模型）。"""

from dataclasses import dataclass


@dataclass
class Demo:
    """demo 示例实体（内存实现）。"""

    id: int
    name: str

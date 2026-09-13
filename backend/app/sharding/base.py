"""分片路由能力域：ShardingRouter 抽象（MVP 按月分表，阶段十一回补）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.base import BaseObject


@dataclass
class ShardBinding(BaseObject):
    """分片解析结果：物理库键 + 物理表名。"""

    db_key: str = "default"
    physical_table: str = ""


class ShardingRouter(BaseObject, ABC):
    """分片路由基座契约：分片键 → 物理库 / 表解析。"""

    @abstractmethod
    def resolve(self, logical_table: str, *, shard_key: object | None = None) -> ShardBinding:
        """解析逻辑表到物理绑定。

        Args:
            logical_table: 逻辑表名。
            shard_key: 分片键（如租户、时间）；None 表示不按分片键路由。

        Returns:
            ShardBinding: 物理库 / 表绑定。
        """


class NullShardingRouter(ShardingRouter):
    """占位分片路由：不路由，返回默认库 + 逻辑表名。"""

    def resolve(self, logical_table: str, *, shard_key: object | None = None) -> ShardBinding:
        """不路由解析。

        Args:
            logical_table: 逻辑表名。
            shard_key: 分片键（占位忽略）。

        Returns:
            ShardBinding: `default` + 逻辑表名。
        """
        return ShardBinding(db_key="default", physical_table=logical_table)

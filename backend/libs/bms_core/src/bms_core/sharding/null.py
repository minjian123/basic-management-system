"""sharding 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.sharding.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.sharding.base import ShardBinding, ShardingRouter

__all__ = [
    "NullShardingRouter",
]


class NullShardingRouter(ShardingRouter, BaseNullObject):
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

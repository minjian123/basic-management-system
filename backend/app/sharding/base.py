"""分片路由能力域：ShardingRouter 抽象（MVP 按月分表，阶段十一回补）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable


@dataclass
class ShardBinding(BaseObject):
    """分片解析结果：物理库键 + 物理表名。"""

    db_key: str = "default"
    physical_table: str = ""


class ShardingRouter(BasePluggable, ABC):
    """分片路由基座契约：分片键 → 物理库 / 表解析。"""

    key: str = "sharding"
    plugin_key: str = "sharding"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    def resolve(self, logical_table: str, *, shard_key: object | None = None) -> ShardBinding:
        """解析逻辑表到物理绑定。

        Args:
            logical_table: 逻辑表名。
            shard_key: 分片键（如租户、时间）；None 表示不按分片键路由。

        Returns:
            ShardBinding: 物理库 / 表绑定。
        """

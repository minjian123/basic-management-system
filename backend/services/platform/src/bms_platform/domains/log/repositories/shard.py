"""审计分片仓储（`log` 域再导出）：实现已上移基座 `bms_core.audit.shard_repository`（06_02）。

06_02 把台账读写 / 运行期建表 / 链尾读取 / 跨片查询上移到基座——`log` 域与 `audit` 域共用同一份
仓储，避免两套分片实现漂移；本模块只做再导出，保持 06_01 的调用面与测试导入不变。
"""

from bms_core.audit.shard_repository import LogShardRepository

__all__ = ["LogShardRepository"]

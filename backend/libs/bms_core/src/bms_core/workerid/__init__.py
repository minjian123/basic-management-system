"""WorkerId 动态注册能力域（03_06 / 需求 03-7）：Redis 租约占号 + 心跳续租 + 优雅释放。

对外导出：端口 `BaseWorkerIdRegistry`、真实实现 `RedisWorkerIdRegistry`、旁路实现
`NullWorkerIdRegistry`、上下文管理器（`worker_id_lease` / `worker_id_lease_sync`）、
就绪校验 `ensure_worker_id_ready` 与键口径构造（`build_worker_id_prefix` / `build_worker_id_key`）。
"""

from bms_core.workerid.base import (
    SOURCE_CONFIG,
    SOURCE_FALLBACK,
    SOURCE_NONE,
    SOURCE_REGISTRY,
    WORKER_ID_PLUGIN_KEY,
    WORKER_ID_POOL_MAX,
    WORKER_ID_POOL_MIN,
    BaseWorkerIdRegistry,
    build_holder_token,
    build_worker_id_key,
    build_worker_id_prefix,
    worker_id_unit,
)
from bms_core.workerid.lease import (
    build_worker_id_registry,
    ensure_worker_id_ready,
    worker_id_lease,
    worker_id_lease_sync,
)
from bms_core.workerid.null import NullWorkerIdRegistry
from bms_core.workerid.redis import RedisWorkerIdRegistry

__all__ = [
    "SOURCE_CONFIG",
    "SOURCE_FALLBACK",
    "SOURCE_NONE",
    "SOURCE_REGISTRY",
    "WORKER_ID_PLUGIN_KEY",
    "WORKER_ID_POOL_MAX",
    "WORKER_ID_POOL_MIN",
    "BaseWorkerIdRegistry",
    "NullWorkerIdRegistry",
    "RedisWorkerIdRegistry",
    "build_holder_token",
    "build_worker_id_key",
    "build_worker_id_prefix",
    "build_worker_id_registry",
    "ensure_worker_id_ready",
    "worker_id_lease",
    "worker_id_lease_sync",
    "worker_id_unit",
]

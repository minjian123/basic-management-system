"""文件维护内部契约客户端（跨服务触发型任务共用；03_01）。

- 契约：file 服务 `POST /api/v1/files/internal/cleanup-orphans`（服务 JWT，服务间东西向直连）。
- **归属边界**：内置任务只做「触发 + 落执行记录」，扫描 / 清理 / 置 `orphan` 全在 file 域
  （自有租户库 + 对象存储）；bms_core 不跨库写 file 表。
- 降级：下游不可达 / 非 2xx → 抛 `ServiceUnavailableError`（任务执行为失败态，由调度器按策略重试）。
"""

from dataclasses import dataclass
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.servicecall.base import BaseServiceClient, ServiceCallPolicy, ServiceRequest

__all__ = ["CLEANUP_ORPHANS_PATH", "FILE_SERVICE_KEY", "CleanupSummary", "FileMaintenanceClient"]

FILE_SERVICE_KEY = "file"
"""文件服务标识（`sys_file` 数据权威）。"""

CLEANUP_ORPHANS_PATH = "/api/v1/files/internal/cleanup-orphans"
"""孤儿回收内部契约路径。"""


@dataclass(frozen=True)
class CleanupSummary(BaseValueObject):
    """孤儿回收结果摘要（内部契约响应体）。"""

    scanned: int = 0
    """扫描到的超期记录数。"""

    orphaned: int = 0
    """已置为 orphan 的记录数。"""

    failed: int = 0
    """清理失败的记录数。"""


class FileMaintenanceClient(BaseFrameworkObject):
    """文件维护客户端（当前只承载孤儿回收触发）。"""

    def __init__(self, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def cleanup_orphans(self, limit: int | None = None) -> CleanupSummary:
        """触发文件服务的孤儿回收。

        Args:
            limit: 单批上限（None 由对端取配置）。

        Returns:
            CleanupSummary: 回收结果摘要（缺字段按 0 计）。

        Raises:
            ServiceUnavailableError: 下游不可达 / 非 2xx / 响应非法。
        """
        params: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if limit is not None:
            params.set("limit", limit)
        request = ServiceRequest(
            service=FILE_SERVICE_KEY,
            method="POST",
            path=CLEANUP_ORPHANS_PATH,
            query=ConcurrentStableFrozenDict({key: str(value) for key, value in params.items()}),
            policy=ServiceCallPolicy(),
        )
        response = await self._client.call(request)
        if not 200 <= response.status_code < 300:
            raise ServiceUnavailableError(f"孤儿回收调用失败：HTTP {response.status_code}")
        payload = response.payload()
        if not isinstance(payload, dict):
            raise ServiceUnavailableError("孤儿回收响应不是 JSON 对象")
        body = cast("dict[str, object]", payload).get("data")
        if not isinstance(body, dict):
            raise ServiceUnavailableError("孤儿回收响应缺少 data 对象")
        fields = cast("dict[str, object]", body)
        return CleanupSummary(
            scanned=int(cast("int", fields.get("scanned") or 0)),
            orphaned=int(cast("int", fields.get("orphaned") or 0)),
            failed=int(cast("int", fields.get("failed") or 0)),
        )

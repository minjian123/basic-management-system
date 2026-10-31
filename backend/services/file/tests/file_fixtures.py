"""文件域接口测试支撑：依赖替身（本地存储落到临时目录 / 配额客户端 / 参数源 / 发件箱记录）。

口径：**不覆盖服务实现**，只替换能力域外部依赖——对象与分片落 `tmp_path`（真实读写），
配额与参数走可控替身，发件箱保留真实 SQL 实现并记录事件类型。
"""

import hashlib
from typing import Any, cast

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.serialization import stable_json_dumps
from bms_core.outbox.store import SqlOutboxStore
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.storage.local import LocalObjectStorage
from bms_core.storage.multipart_local import LocalMultipartUpload

__all__ = [
    "PDF_BYTES",
    "FilePorts",
    "RecordingOutbox",
    "StubConfigSource",
    "StubQuotaClient",
    "pdf_part_sha",
]

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
"""合法 PDF 头部（用于类型校验通过的上传样例）。"""

TEXT_BYTES = b"hello,file\n"
"""纯文本样例。"""


def pdf_part_sha(data: bytes) -> str:
    """算分片 / 整文件 SHA256（用例期望值）。

    Args:
        data: 内容。

    Returns:
        str: 十六进制摘要。
    """
    return hashlib.sha256(data).hexdigest()


class StubQuotaClient(BaseServiceClient):
    """配额调用替身（记录调用；可配置超限 / 不可用）。"""

    def __init__(self, *, code: int = 0) -> None:
        """初始化。

        Args:
            code: 返回的业务码（0 成功；82005 超限；10007 服务不可用）。
        """
        self.code = code
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """记录调用并返回预设响应。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 统一响应。
        """
        self.calls.add(request.path)
        status = 409 if self.code == 82005 else 200
        return ServiceResponse(
            status_code=status,
            content=stable_json_dumps(
                {"code": self.code, "message": "stub", "data": {"quota_key": "storage_bytes", "limit": 1, "used": 1}}
            ).encode(),
        )


class StubConfigSource(BaseConfigSource):
    """系统参数替身（固定取值；不声明 `plugin_name` 以免被插件注册表自动收集）。"""

    def __init__(self, values: ConcurrentStableDict[str, str] | None = None) -> None:
        """初始化。

        Args:
            values: 参数键 → 值（None 表示空结果 → 全部回落代码默认）。
        """
        self._values: ConcurrentStableDict[str, str] = (
            values if values is not None else ConcurrentStableDict[str, str]()
        )

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """返回命中键（未登记键不出现）。

        Args:
            keys: 请求键序列。

        Returns:
            ConcurrentStableDict[str, str]: 命中键值。
        """
        return ConcurrentStableDict({key: self._values[key] for key in keys if key in self._values})


class RecordingOutbox(SqlOutboxStore):
    """真实 SQL 发件箱 + 事件类型记录（用于断言事件已随事务写出）。"""

    def __init__(self) -> None:
        """初始化空记录表。"""
        super().__init__()
        self.events: ConcurrentStableList[str] = ConcurrentStableList()

    async def enqueue(self, session: Any, event: Any) -> str:
        """记录事件类型后委托真实写入（同一事务）。

        Args:
            session: 业务会话。
            event: 事件信封。

        Returns:
            str: 事件 ID。
        """
        self.events.add(cast("str", event.event_type))
        return await super().enqueue(session, event)


class FilePorts:
    """一次测试用到的替身集合（便于用例断言）。"""

    def __init__(self, storage: LocalObjectStorage, multipart: LocalMultipartUpload) -> None:
        self.storage = storage
        self.multipart = multipart
        self.quota = StubQuotaClient()
        self.config = StubConfigSource()
        self.outbox = RecordingOutbox()

    def use_quota(self, code: int) -> StubQuotaClient:
        """替换配额替身（超限 / 不可用场景）。

        Args:
            code: 返回码。

        Returns:
            StubQuotaClient: 新替身。
        """
        self.quota = StubQuotaClient(code=code)
        return self.quota

    def use_config(self, values: ConcurrentStableDict[str, str]) -> StubConfigSource:
        """替换参数替身。

        Args:
            values: 参数键值。

        Returns:
            StubConfigSource: 新替身。
        """
        self.config = StubConfigSource(values)
        return self.config

"""分片上传实现基座（会话快照 + 模板方法；03_01）。

- `UploadSession` / `UploadSessionStore`：分片会话快照（Redis `bms:{tenant}:files:upload:{upload_id}`），
  TTL = `[file].session_ttl_seconds`，与 `sys_file.expires_at` 同源。**会话只是加速面**：丢失时上层可用
  同一 `upload_id` 重新 `initiate` 重建快照（分片对象按对象 key 派生，不随会话消失）。
- `StorageMultipartUpload`：`BaseMultipartUpload` 的存储侧模板——会话读写、分片序号 / 尺寸校验、
  会话标识生成与清理编排在此；**怎么落一片、怎么合并**由子类实现（`local` 流式拼接 / `minio` 组合对象）。
- 口径：`check`（秒传判定）在本基座恒返回 `None`——`sha256 → 对象` 的索引属业务库（`sys_file`），
  存储层无此数据；秒传判定由文件域执行（见《03_01 详细设计》§4.7 决策 5）。
"""

import json
from abc import abstractmethod
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from bms_core.cache.base import build_cache_key
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_tenant
from bms_core.core.exceptions import FileChecksumMismatchError, FileSizeExceededError, NotFoundError, ParamError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.core.serialization import stable_json_dumps
from bms_core.redis.base import BaseRedisClient, shared_redis_client
from bms_core.storage.base import (
    DEFAULT_PART_SIZE,
    BaseMultipartUpload,
    ExistingObjectRef,
    MultipartInit,
    MultipartPart,
    MultipartSession,
    StoredObject,
)

__all__ = [
    "PART_KEY_INFIX",
    "UPLOAD_SESSION_DOMAIN",
    "UPLOAD_SESSION_OBJECT",
    "StorageMultipartUpload",
    "UploadSession",
    "UploadSessionStore",
    "build_upload_session_key",
    "part_key",
]

_LOGGER = get_logger("bms")

UPLOAD_SESSION_DOMAIN = "files"
"""会话快照所属域简称（Redis key 第三段；`bms:{tenant}:files:upload:{upload_id}`）。"""

UPLOAD_SESSION_OBJECT = "upload"
"""会话快照业务对象段（Redis key 第四段前缀）。"""

PART_KEY_INFIX = ".part."
"""分片对象 key 中缀（`{object_key}.part.00001`；`00001` 为 5 位补零分片序号）。"""

_PART_NO_WIDTH = 5
"""分片序号补零宽度（字典序即数值序，便于按前缀巡检）。"""

_UPLOAD_ID_FALLBACK = "upload"
"""上层未指定会话标识时的前缀（后接 uuid4 十六进制）。"""


def build_upload_session_key(*, tenant: str | None, upload_id: str) -> str:
    """构建会话快照 key（规范 `bms:{租户|global}:files:upload:{upload_id}`）。

    Args:
        tenant: 租户标识；None 表示全局。
        upload_id: 会话标识。

    Returns:
        str: Redis key。
    """
    business_key = f"{UPLOAD_SESSION_OBJECT}:{upload_id}"
    return build_cache_key(tenant=tenant, domain=UPLOAD_SESSION_DOMAIN, business_key=business_key)


def part_key(object_key: str, part_no: int) -> str:
    """派生分片对象 key（`{object_key}.part.00001`）。

    Args:
        object_key: 目标对象 key。
        part_no: 分片序号（从 1 起）。

    Returns:
        str: 分片对象 key。
    """
    return f"{object_key}{PART_KEY_INFIX}{part_no:0{_PART_NO_WIDTH}d}"


@dataclass(frozen=True)
class UploadSession(BaseValueObject):
    """分片会话快照（Redis 载荷的内存形态）。"""

    key: str
    """目标对象 key。"""

    size: int
    """文件总字节数。"""

    sha256: str
    """整文件 SHA256（客户端声明；合并后按需复算比对）。"""

    mime: str | None
    """内容类型（可空）。"""

    part_size: int
    """分片大小（字节）。"""

    total_parts: int
    """分片总数。"""


class UploadSessionStore(BaseFrameworkObject):
    """分片会话快照存储（Redis；租户位从请求上下文取，调用方不传租户）。"""

    def __init__(self, *, ttl_seconds: int, client: BaseRedisClient | None = None) -> None:
        """初始化。

        Args:
            ttl_seconds: 会话有效期（秒；与 `sys_file.expires_at` 同源）。
            client: Redis 客户端（None 取进程共享实例；测试可注入）。
        """
        self._ttl = ttl_seconds
        self._client = client

    @property
    def ttl_seconds(self) -> int:
        """会话有效期（秒）。

        Returns:
            int: 有效期。
        """
        return self._ttl

    def redis_client(self) -> BaseRedisClient:
        """取 Redis 客户端（注入优先，否则进程共享实例）。

        Returns:
            BaseRedisClient: 客户端实例。
        """
        return self._client if self._client is not None else shared_redis_client()

    def key_of(self, upload_id: str) -> str:
        """会话快照 key。

        Args:
            upload_id: 会话标识。

        Returns:
            str: Redis key。
        """
        return build_upload_session_key(tenant=current_tenant.get(), upload_id=upload_id)

    async def save(self, upload_id: str, session: UploadSession) -> None:
        """写入会话快照（覆盖写；TTL = 会话有效期）。

        Args:
            upload_id: 会话标识。
            session: 会话内容。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "key": session.key,
                "size": session.size,
                "sha256": session.sha256,
                "mime": session.mime,
                "part_size": session.part_size,
                "total_parts": session.total_parts,
            }
        )
        await self.redis_client().async_client().set(self.key_of(upload_id), stable_json_dumps(payload), ex=self._ttl)

    async def load(self, upload_id: str) -> UploadSession | None:
        """读取会话快照。

        Args:
            upload_id: 会话标识。

        Returns:
            UploadSession | None: 命中返回会话；未命中 / 载荷非法返回 None（由调用方判会话无效）。
        """
        raw = await self.redis_client().async_client().get(self.key_of(upload_id))
        if raw is None:
            return None
        try:
            data = cast("dict[str, object]", json.loads(raw))
            return UploadSession(
                key=str(data["key"]),
                size=int(cast("int", data["size"])),
                sha256=str(data["sha256"]),
                mime=None if data["mime"] is None else str(data["mime"]),
                part_size=int(cast("int", data["part_size"])),
                total_parts=int(cast("int", data["total_parts"])),
            )
        except KeyError, TypeError, ValueError:
            _LOGGER.warning("分片会话载荷非法（按会话无效处理）", upload_id=upload_id)
            return None

    async def delete(self, upload_id: str) -> None:
        """删除会话快照（不存在不报错）。

        Args:
            upload_id: 会话标识。
        """
        await self.redis_client().async_client().delete(self.key_of(upload_id))


class StorageMultipartUpload(BaseMultipartUpload):
    """存储侧分片上传模板：会话 + 校验 + 清理编排；落片 / 合并由子类实现。"""

    def __init__(
        self,
        *,
        part_size: int = DEFAULT_PART_SIZE,
        max_parts: int = 10000,
        session_ttl_seconds: int = 86400,
        verify_sha256: bool = True,
        store: UploadSessionStore | None = None,
    ) -> None:
        """初始化。

        Args:
            part_size: 缺省分片大小（字节）。
            max_parts: 单文件分片数上限。
            session_ttl_seconds: 会话有效期（秒）。
            verify_sha256: 合并后是否复算整文件 SHA256 并与声明值比对。
            store: 会话存储（None 按 `session_ttl_seconds` 新建）。
        """
        self._default_part_size = part_size
        self._max_parts = max_parts
        self._verify_sha256 = verify_sha256
        self._store = store if store is not None else UploadSessionStore(ttl_seconds=session_ttl_seconds)

    @property
    def session_store(self) -> UploadSessionStore:
        """会话存储（供测试与上层重建会话时取 TTL）。

        Returns:
            UploadSessionStore: 会话存储。
        """
        return self._store

    async def initiate(self, init: MultipartInit) -> MultipartSession:
        """初始化（或按 `init.upload_id` 重建）分片会话并写入快照。

        Args:
            init: 初始化参数对象。

        Returns:
            MultipartSession: 会话（`upload_id` / `key` / `part_size` / `total_parts`）。

        Raises:
            FileSizeExceededError: 分片总数超上限（`50102`）。
        """
        part_size = init.part_size or self._default_part_size
        total_parts = (init.size + part_size - 1) // part_size
        if total_parts > self._max_parts:
            raise FileSizeExceededError(f"分片总数超上限：{total_parts} > {self._max_parts}（调大分片大小）")
        upload_id = init.upload_id or f"{_UPLOAD_ID_FALLBACK}-{uuid4().hex}"
        session = UploadSession(
            key=init.key,
            size=init.size,
            sha256=init.sha256,
            mime=init.mime,
            part_size=part_size,
            total_parts=total_parts,
        )
        await self._store.save(upload_id, session)
        return MultipartSession(
            upload_id=upload_id,
            key=init.key,
            part_size=part_size,
            total_parts=total_parts,
        )

    async def upload_part(self, upload_id: str, part_no: int, data: bytes) -> MultipartPart:
        """上传单个分片（尺寸按会话精确校验；同片重传为覆盖写）。

        Args:
            upload_id: 会话标识。
            part_no: 分片序号（从 1 起）。
            data: 分片内容。

        Returns:
            MultipartPart: 分片结果。

        Raises:
            NotFoundError: 会话不存在 / 分片序号越界（`50104`）。
            ParamError: 分片字节数与会话预期不符（`10001`）。
        """
        session = await self._require_session(upload_id)
        if not 1 <= part_no <= session.total_parts:
            raise NotFoundError(f"分片序号越界：{part_no}（取值 1 ~ {session.total_parts}）")
        expected = self._expected_part_size(session, part_no)
        if len(data) != expected:
            raise ParamError(f"分片大小不符：part_no={part_no} 收到 {len(data)} 字节，应为 {expected}")
        etag = await self._write_part(session.key, part_no, data)
        return MultipartPart(part_no=part_no, etag=etag, size=len(data))

    async def complete(self, upload_id: str) -> StoredObject:
        """合并分片为最终对象（缺片即拒；合并后按需复算整文件 SHA256）。

        Args:
            upload_id: 会话标识。

        Returns:
            StoredObject: 合并产物元数据。

        Raises:
            NotFoundError: 会话不存在 / 分片缺失（`50104`）。
            FileChecksumMismatchError: 复算 SHA256 与声明不符（`50103`）。
        """
        session = await self._require_session(upload_id)
        await self._ensure_parts_present(session)
        stored = await self._compose(session)
        await self._store.delete(upload_id)
        return stored

    async def abort(self, upload_id: str) -> None:
        """取消会话并清理分片对象（会话不存在抛 `NotFoundError`）。

        Args:
            upload_id: 会话标识。

        Raises:
            NotFoundError: 会话不存在（`50104`）。
        """
        session = await self._require_session(upload_id)
        for part_no in range(1, session.total_parts + 1):
            await self._delete_part(session.key, part_no)
        await self._store.delete(upload_id)

    async def check(self, sha256: str, size: int) -> ExistingObjectRef | None:
        """秒传判定：恒未命中（索引在业务库，判定归文件域）。

        Args:
            sha256: 整文件 SHA256（本实现忽略）。
            size: 文件字节数（本实现忽略）。

        Returns:
            ExistingObjectRef | None: 恒为 None。
        """
        _ = (sha256, size)
        return None

    async def _require_session(self, upload_id: str) -> UploadSession:
        """取会话（未命中抛 `NotFoundError`）。

        Args:
            upload_id: 会话标识。

        Returns:
            UploadSession: 会话。

        Raises:
            NotFoundError: 会话不存在 / 已合并 / 已过期（`50104`）。
        """
        session = await self._store.load(upload_id)
        if session is None:
            raise NotFoundError(f"上传会话不存在或已失效：{upload_id}")
        return session

    def _expected_part_size(self, session: UploadSession, part_no: int) -> int:
        """计算某片的预期字节数（末片扣余量）。

        Args:
            session: 会话。
            part_no: 分片序号。

        Returns:
            int: 预期字节数。
        """
        if part_no < session.total_parts:
            return session.part_size
        return session.size - session.part_size * (session.total_parts - 1)

    async def _ensure_parts_present(self, session: UploadSession) -> None:
        """校验所有分片对象齐备且总字节数与会话一致。

        Args:
            session: 会话。

        Raises:
            NotFoundError: 存在缺失分片（`50104`，消息带缺失序号）。
            FileChecksumMismatchError: 分片总字节数与声明不符（`50103`）。
        """
        missing: ConcurrentStableList[int] = ConcurrentStableList()
        total = 0
        for part_no in range(1, session.total_parts + 1):
            size = await self._part_size(session.key, part_no)
            if size is None:
                missing.append(part_no)
                continue
            total += size
        if missing:
            raise NotFoundError(f"分片缺失：{missing}（先补传再合并）")
        if total != session.size:
            raise FileChecksumMismatchError(f"分片总字节数与声明不符：{total} != {session.size}")

    async def _verify_object_sha256(self, key: str, expected: str) -> None:
        """复算对象整文件 SHA256 并与声明值比对（不符即删对象并抛错）。

        Args:
            key: 对象 key。
            expected: 声明的 SHA256。

        Raises:
            FileChecksumMismatchError: 复算值不符（`50103`）。
        """
        actual = await self._sha256_of(key)
        if actual != expected:
            await self._delete_object(key)
            raise FileChecksumMismatchError(f"整文件校验失败：sha256 {actual} != 声明 {expected}")

    @abstractmethod
    async def _write_part(self, object_key: str, part_no: int, data: bytes) -> str:
        """落一片（返回 etag）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
            data: 分片内容。

        Returns:
            str: 分片 etag。
        """

    @abstractmethod
    async def _part_size(self, object_key: str, part_no: int) -> int | None:
        """取分片字节数（不存在返回 None）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。

        Returns:
            int | None: 字节数；分片不存在为 None。
        """

    @abstractmethod
    async def _compose(self, session: UploadSession) -> StoredObject:
        """按序合并分片为最终对象（并按 `verify_sha256` 决定是否复算）。

        Args:
            session: 会话。

        Returns:
            StoredObject: 合并产物元数据。
        """

    @abstractmethod
    async def _delete_part(self, object_key: str, part_no: int) -> None:
        """删一片（不存在不报错）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
        """

    @abstractmethod
    async def _sha256_of(self, object_key: str) -> str:
        """流式复算对象 SHA256（不整份入内存）。

        Args:
            object_key: 对象 key。

        Returns:
            str: 十六进制摘要。
        """

    @abstractmethod
    async def _delete_object(self, object_key: str) -> None:
        """删除最终对象（校验失败清理用，幂等）。

        Args:
            object_key: 对象 key。
        """

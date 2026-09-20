"""storage 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.storage.base.py 迁入）。

- `NullObjectStorage`：对象存储占位（固定返回、不连 MinIO / 不落盘）。
- `NullMultipartUpload`：分片上传占位——带**内存会话表**（只记会话键与分片粒度，不落盘、不连 MinIO），
  `initiate` 登记会话并返回占位会话标识、`upload_part` 回显分片、`complete` 回显会话 key / size、
  `abort` 清会话、`check` 恒未命中；未知会话 / 越界分片抛 `NotFoundError`（与真实实现口径一致）。
"""

from app.core.capability import BaseNullObject
from app.core.exceptions import NotFoundError
from app.storage.base import (
    DEFAULT_PART_SIZE,
    DEFAULT_PRESIGN_TTL,
    NULL_ETAG,
    NULL_PRESIGNED_URL,
    NULL_UPLOAD_ID,
    BaseMultipartUpload,
    BaseObjectStorage,
    ExistingObjectRef,
    MultipartInit,
    MultipartPart,
    MultipartSession,
    PresignedUrl,
    StoredObject,
)

__all__ = [
    "NullMultipartUpload",
    "NullObjectStorage",
]


class NullObjectStorage(BaseObjectStorage, BaseNullObject):
    """占位对象存储：固定返回（不连 MinIO、不落盘，未接入真实实现时使用）。"""

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """回显对象元数据（占位不写入）。

        Args:
            key: 对象 key（占位透传）。
            data: 对象内容（占位不落盘，仅取长度）。
            content_type: 内容类型（占位透传）。

        Returns:
            StoredObject: 对象元数据（etag 为 `NULL_ETAG`）。
        """
        return StoredObject(key=key, size=len(data), content_type=content_type, etag=NULL_ETAG)

    async def get(self, key: str) -> bytes:
        """返回空字节（占位不读取）。

        Args:
            key: 对象 key（占位忽略）。

        Returns:
            bytes: 空字节。
        """
        return b""

    async def delete(self, key: str) -> None:
        """空操作（占位不删除）。

        Args:
            key: 对象 key（占位忽略）。
        """

    async def exists(self, key: str) -> bool:
        """恒定存在。

        Args:
            key: 对象 key（占位忽略）。

        Returns:
            bool: True。
        """
        return True

    async def presign(
        self,
        key: str,
        *,
        method: str = "GET",
        expires_in: int = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUrl:
        """固定返回预签名结果。

        Args:
            key: 对象 key（占位忽略）。
            method: HTTP 方法（占位透传）。
            expires_in: 有效期（占位透传）。

        Returns:
            PresignedUrl: 占位预签名结果（url 为 `NULL_PRESIGNED_URL`）。
        """
        return PresignedUrl(url=NULL_PRESIGNED_URL, expires_in=expires_in, method=method)


class NullMultipartUpload(BaseMultipartUpload, BaseNullObject):
    """占位分片上传：内存会话表 + 固定返回（不落盘、不连 MinIO、不判定秒传）。

    会话表只保存初始化入参与会话本身（供 `complete` 回显与分片序号范围校验），无 TTL、无容量上限
    （占位期已知项，随真实实现落库 / 缓存销项）；`complete` / `abort` 结束后会话即失效。
    """

    def __init__(self) -> None:
        """初始化空会话表与递增序号。"""
        self._sessions: dict[str, tuple[MultipartInit, MultipartSession]] = {}
        self._sequence = 0

    async def initiate(self, init: MultipartInit) -> MultipartSession:
        """登记会话并返回占位会话标识（`NULL_UPLOAD_ID` 前缀 + 递增序号）。

        Args:
            init: 初始化参数对象（占位只记录，不落盘）。

        Returns:
            MultipartSession: 会话（分片大小缺省取 `DEFAULT_PART_SIZE`，总数按上限取整）。
        """
        self._sequence += 1
        part_size = init.part_size or DEFAULT_PART_SIZE
        total_parts = (init.size + part_size - 1) // part_size
        session = MultipartSession(
            upload_id=f"{NULL_UPLOAD_ID}-{self._sequence}",
            key=init.key,
            part_size=part_size,
            total_parts=total_parts,
        )
        self._sessions[session.upload_id] = (init, session)
        return session

    async def upload_part(self, upload_id: str, part_no: int, data: bytes) -> MultipartPart:
        """回显分片结果（占位不写入；序号越界抛错）。

        Args:
            upload_id: 会话标识。
            part_no: 分片序号（取值 1 ~ 会话分片总数）。
            data: 分片内容（占位不落盘，仅取长度）。

        Returns:
            MultipartPart: 分片结果（etag 为 `NULL_ETAG`）。

        Raises:
            NotFoundError: 会话不存在 / 分片序号越界（10002）。
        """
        _, session = self._require_session(upload_id)
        if not 1 <= part_no <= session.total_parts:
            raise NotFoundError(f"分片序号越界：{part_no}（取值 1 ~ {session.total_parts}）")
        return MultipartPart(part_no=part_no, etag=NULL_ETAG, size=len(data))

    async def complete(self, upload_id: str) -> StoredObject:
        """回显合并产物元数据并结束会话（占位不合并）。

        Args:
            upload_id: 会话标识。

        Returns:
            StoredObject: 合并产物元数据（取会话 key 与初始化字节数，etag 为 `NULL_ETAG`）。

        Raises:
            NotFoundError: 会话不存在（10002）。
        """
        init, session = self._require_session(upload_id)
        del self._sessions[upload_id]
        return StoredObject(key=session.key, size=init.size, content_type=init.mime, etag=NULL_ETAG)

    async def abort(self, upload_id: str) -> None:
        """结束会话（占位无临时分片可清理）。

        Args:
            upload_id: 会话标识。

        Raises:
            NotFoundError: 会话不存在（10002）。
        """
        self._require_session(upload_id)
        del self._sessions[upload_id]

    async def check(self, sha256: str, size: int) -> ExistingObjectRef | None:
        """恒定未命中（占位不判定秒传，避免上层跳过上传）。

        Args:
            sha256: 整文件 SHA256（占位忽略）。
            size: 文件字节数（占位忽略）。

        Returns:
            ExistingObjectRef | None: 恒为 None。
        """
        return None

    def _require_session(self, upload_id: str) -> tuple[MultipartInit, MultipartSession]:
        """取会话（未命中抛 `NotFoundError`）。

        Args:
            upload_id: 会话标识。

        Returns:
            tuple[MultipartInit, MultipartSession]: 初始化入参与会话。

        Raises:
            NotFoundError: 会话不存在（10002）。
        """
        record = self._sessions.get(upload_id)
        if record is None:
            raise NotFoundError(f"上传会话不存在：{upload_id}")
        return record

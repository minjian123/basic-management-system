"""文件域服务：整包上传 / 分片 / 断点续传 / 秒传 / 取址 / 列表 / 删除 / 孤儿回收。

口径（《03_01 详细设计》§4）：

- **写路径顺序不可反**：类型（扩展名 + 嗅探）→ 大小 → 对象写入 → 配额占用 → 元数据落库 → 事件；
  任一步失败按逆序补偿（删对象 / 释放配额），不留「有元数据没对象」或「白占配额」的中间态。
- **分片会话只是加速面**：Redis 快照丢失时按 `sys_file` 重建（同一 `upload_id`），断点续传不受影响；
  分片状态权威在 `sys_file_part`。
- **状态机**：`uploading` → `completed` / `failed` / `orphan`；`completed` 不回退，失败只能重新初始化。
- **分片路径的类型判定**：初始化时按扩展名取白名单规范 MIME（无字节可嗅探），**不做整文件内容嗅探**
  （已知限制，见详细设计 §8）；整包路径则扩展名 + 嗅探双校验。
- **删除**只软删元数据（对象保留、配额不释放），物理清理与配额释放归 13_01。
- **事件**经事务性发件箱与状态同事务写出（`file.uploaded` / `file.deleted` / `file.upload.abandoned`）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import FileSettings, get_settings
from bms_core.core.context import current_tenant, current_user_id
from bms_core.core.exceptions import (
    FileChecksumMismatchError,
    FileObjectMissingError,
    FilePreviewUnsupportedError,
    FileRecordNotFoundError,
    FileSizeExceededError,
    FileTypeNotAllowedError,
    FileUploadSessionInvalidError,
    NotFoundError,
    ParamError,
    TenantQuotaExceededError,
)
from bms_core.core.id import id_generator
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import BaseOutboxStore
from bms_core.storage.base import (
    STORAGE_BUCKET,
    BaseMultipartUpload,
    BaseObjectStorage,
    MultipartInit,
    MultipartPart,
    PresignedUrl,
)
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_file.domains.file.limits import FileLimits
from bms_file.domains.file.models.file import (
    FILE_SOURCE_DEDUP,
    FILE_SOURCE_UPLOAD,
    FILE_STATUS_COMPLETED,
    FILE_STATUS_FAILED,
    FILE_STATUS_ORPHAN,
    FILE_STATUS_UPLOADING,
    SysFile,
)
from bms_file.domains.file.repositories.file import FilePartRepository, FileRepository
from bms_file.domains.file.rules import (
    SNIFF_LENGTH,
    is_previewable,
    normalize_extension,
    object_key_for,
    resolve_mime,
)
from bms_file.domains.file.schemas.file import CleanupResult, FileItem, FilePage, MultipartStatusResult

__all__ = ["QUOTA_KEY", "FileService", "storage_bucket"]

_LOGGER = get_logger("bms")

QUOTA_KEY = "storage_bytes"
"""存储配额维度（tenant 服务记账）。"""

_EVENT_UPLOADED = "file.uploaded"
_EVENT_DELETED = "file.deleted"
_EVENT_ABANDONED = "file.upload.abandoned"


def _now() -> datetime:
    """UTC 当前时间（naive，与库列口径一致）。

    Returns:
        datetime: 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def storage_bucket() -> str:
    """取对象存储桶名（`[storage].options.bucket` 缺省 `bms-files`）。

    Returns:
        str: 桶名。
    """
    configured = get_settings().storage.options.get("bucket")
    return str(configured) if configured else STORAGE_BUCKET


def file_settings() -> FileSettings:
    """取文件域进程级参数（`[file]`）。

    Returns:
        FileSettings: 参数快照。
    """
    return get_settings().file_options


class FileService(BaseFrameworkObject):
    """文件域服务（请求级：工作单元 + 能力域实例 + 参数快照）。"""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        storage: BaseObjectStorage,
        multipart: BaseMultipartUpload,
        config: BaseConfigSource | None,
        quota: TenantQuotaClient,
        outbox: BaseOutboxStore,
        audit: AuditCapturer | None = None,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            uow: 请求级工作单元（file 服务租户库）。
            storage: 对象存储能力域。
            multipart: 分片上传能力域。
            config: 系统参数取数（None 表示全用代码默认）。
            quota: 租户配额客户端。
            outbox: 事务性发件箱。
            audit: 审计捕获器（None 不产生审计事件）。
            metrics: 指标记录器（None 不记录）。
        """
        self._uow = uow
        self._storage = storage
        self._multipart = multipart
        self._config = config
        self._quota = quota
        self._outbox = outbox
        self._audit = audit
        self._metrics = metrics
        self._limits: FileLimits | None = None
        self._session: DbSession = cast("DbSession", uow.session)
        self._files = FileRepository(self._session)
        self._parts = FilePartRepository(self._session)

    # ---- 参数 ----

    async def limits(self) -> FileLimits:
        """取生效参数（请求内一次加载）。

        Returns:
            FileLimits: 生效参数。
        """
        if self._limits is None:
            self._limits = await FileLimits.load(self._config)
        return self._limits

    # ---- 整包上传 ----

    async def upload(self, *, name: str, data: bytes) -> SysFile:
        """整包上传（≤ `file.upload.max_size`）：校验 → 写对象 → 占配额 → 落元数据 → 发事件。

        Args:
            name: 原始文件名（含扩展名）。
            data: 文件内容。

        Returns:
            SysFile: 落库后的文件记录（`completed`）。

        Raises:
            FileSizeExceededError: 空文件 / 超整包上限（`50102`）。
            FileTypeNotAllowedError: 类型不在白名单或内容与扩展名不相容（`50101`）。
            TenantQuotaExceededError: 存储配额超限（`82005`）。
        """
        limits = await self.limits()
        size = len(data)
        if size <= 0:
            raise FileSizeExceededError("空文件不允许上传")
        if size > limits.max_upload_size:
            raise FileSizeExceededError(f"文件超整包上限：{size} > {limits.max_upload_size}（请走分片上传）")
        mime = self._resolve_mime(name=name, head=data[:SNIFF_LENGTH], limits=limits)
        sha256 = hashlib.sha256(data).hexdigest()
        file_id = id_generator.next_id()
        key = object_key_for(tenant=current_tenant.get(), file_id=file_id)

        await self._storage.put(key, data, content_type=mime)
        try:
            await self._quota.consume(QUOTA_KEY, size, ref=key)
        except TenantQuotaExceededError:
            await self._storage.delete(key)
            await self._warn_quota(size)
            raise
        try:
            async with self._uow.begin():
                row = await self._files.create_with_id(
                    file_id,
                    name=name,
                    ext=normalize_extension(name),
                    bucket=storage_bucket(),
                    object_key=key,
                    size=size,
                    mime_type=mime,
                    sha256=sha256,
                    uploader_id=current_user_id.get(),
                    source=FILE_SOURCE_UPLOAD,
                    status=FILE_STATUS_COMPLETED,
                    completed_at=_now(),
                    uploaded_parts=0,
                )
                await self._emit(row, _EVENT_UPLOADED)
        except Exception:
            await self._storage.delete(key)
            await self._quota.release(QUOTA_KEY, size)
            raise
        self._capture(row, action="upload")
        return row

    # ---- 分片上传 ----

    async def initiate(self, *, name: str, size: int, sha256: str, mime: str | None = None) -> SysFile:
        """初始化分片会话（建 `uploading` 记录 + 存储侧会话快照）。

        Args:
            name: 原始文件名（含扩展名）。
            size: 文件字节数。
            sha256: 整文件 SHA256（64 位小写十六进制）。
            mime: 声明的内容类型（仅预检）。

        Returns:
            SysFile: 上传中记录（含 `upload_id` / `total_parts` / `part_size` / `expires_at`）。

        Raises:
            FileSizeExceededError: 超单文件上限（`50102`）。
            FileTypeNotAllowedError: 扩展名不在白名单 / 声明类型不相容（`50101`）。
            ParamError: SHA256 形态非法（`10001`）。
        """
        limits = await self.limits()
        if size > limits.max_file_size:
            raise FileSizeExceededError(f"文件超单文件上限：{size} > {limits.max_file_size}")
        declared_mime = self._ensure_extension(name=name, mime=mime, limits=limits)
        self._ensure_sha256(sha256)
        settings = file_settings()
        file_id = id_generator.next_id()
        key = object_key_for(tenant=current_tenant.get(), file_id=file_id)
        upload_id = f"{file_id}-{id_generator.next_id() % 10**10:010d}"
        expiry = _now() + timedelta(seconds=settings.session_ttl_seconds)

        session = await self._multipart.initiate(
            MultipartInit(
                key=key,
                size=size,
                sha256=sha256,
                mime=declared_mime,
                part_size=settings.part_size,
                upload_id=upload_id,
            )
        )
        async with self._uow.begin():
            row = await self._files.create_with_id(
                file_id,
                name=name,
                ext=normalize_extension(name),
                bucket=storage_bucket(),
                object_key=key,
                size=size,
                mime_type=declared_mime,
                sha256=sha256,
                uploader_id=current_user_id.get(),
                source=FILE_SOURCE_UPLOAD,
                status=FILE_STATUS_UPLOADING,
                upload_id=session.upload_id,
                total_parts=session.total_parts,
                uploaded_parts=0,
                part_size=session.part_size,
                expires_at=expiry,
            )
        return row

    async def upload_part(self, *, upload_id: str, part_no: int, data: bytes, expected_sha256: str) -> MultipartPart:
        """上传单个分片（尺寸 / 校验先行，落库为覆盖写）。

        Args:
            upload_id: 会话标识。
            part_no: 分片序号（从 1 起）。
            data: 分片内容。
            expected_sha256: 客户端声明该分片的 SHA256。

        Returns:
            MultipartPart: 分片结果。

        Raises:
            FileUploadSessionInvalidError: 会话不存在 / 非上传中 / 已过期（`50104`）。
            FileChecksumMismatchError: 分片校验值不符（`50103`）。
        """
        row = await self._require_uploading(upload_id)
        if not 1 <= part_no <= (row.total_parts or 0):
            raise FileUploadSessionInvalidError(f"分片序号越界：{part_no}（取值 1 ~ {row.total_parts}）")
        self._ensure_sha256(expected_sha256)
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_sha256:
            raise FileChecksumMismatchError(f"分片校验失败：part_no={part_no}")

        async def _call() -> MultipartPart:
            return await self._multipart.upload_part(upload_id, part_no, data)

        part = await self._with_session(upload_id, _call, init=self._rebuild_init(row))
        async with self._uow.begin():
            await self._parts.upsert_part(
                file_id=row.id, part_no=part_no, size=len(data), sha256=actual, etag=part.etag
            )
            row.uploaded_parts = await self._parts.count_by_file(row.id)
        return part

    async def status(self, upload_id: str) -> MultipartStatusResult:
        """断点续传状态（已上传 / 缺失分片序号）。

        Args:
            upload_id: 会话标识。

        Returns:
            MultipartStatusResult: 状态结果。

        Raises:
            FileRecordNotFoundError: 会话不存在（`50106`）。
        """
        async with self._uow.begin():
            row = await self._files.get_by_upload_id(upload_id)
            if row is None:
                raise FileRecordNotFoundError(f"上传会话不存在：{upload_id}")
            present = ConcurrentStableList(part.part_no for part in await self._parts.list_by_file(row.id))
            total = row.total_parts or 0
            missing = ConcurrentStableList(no for no in range(1, total + 1) if no not in set(present))
            return MultipartStatusResult(
                file_id=row.id,
                upload_id=upload_id,
                status=row.status,
                part_size=row.part_size or 0,
                total_parts=total,
                uploaded_parts=len(present),
                uploaded=present,
                missing=missing,
                expires_at=row.expires_at,
            )

    async def complete(self, upload_id: str) -> SysFile:
        """合并分片为最终对象：齐全校验 → 存储合并 → 配额 → 落库 → 发事件（幂等）。

        Args:
            upload_id: 会话标识。

        Returns:
            SysFile: 已完成记录（重复调用回既有结果）。

        Raises:
            FileUploadSessionInvalidError: 会话无效 / 已过期 / 缺片（`50104`）。
            FileChecksumMismatchError: 合并校验失败（`50103`）。
            TenantQuotaExceededError: 存储配额超限（`82005`）。
        """
        async with self._uow.begin():
            existing = await self._files.get_by_upload_id(upload_id)
        if existing is not None and existing.status == FILE_STATUS_COMPLETED:
            return existing
        row = await self._require_uploading(upload_id)
        async with self._uow.begin():
            present = {part.part_no for part in await self._parts.list_by_file(row.id)}
        total = row.total_parts or 0
        missing = [no for no in range(1, total + 1) if no not in present]
        if missing:
            raise FileUploadSessionInvalidError(f"分片缺失：{missing}（先补传再合并）")

        async def _call() -> object:
            return await self._multipart.complete(upload_id)

        await self._with_session(upload_id, _call, init=self._rebuild_init(row))
        try:
            await self._quota.consume(QUOTA_KEY, row.size, ref=row.object_key)
        except TenantQuotaExceededError:
            await self._storage.delete(row.object_key)
            await self._mark_failed(row, "存储配额超限")
            await self._warn_quota(row.size)
            raise
        try:
            async with self._uow.begin():
                await self._parts.delete_by_file(row.id)
                row.status = FILE_STATUS_COMPLETED
                row.completed_at = _now()
                row.uploaded_parts = total
                await self._emit(row, _EVENT_UPLOADED)
        except Exception:
            await self._storage.delete(row.object_key)
            await self._quota.release(QUOTA_KEY, row.size)
            raise
        self._capture(row, action="complete")
        return row

    async def abort(self, upload_id: str) -> None:
        """取消会话：清分片对象与分片行，状态置 `failed`。

        Args:
            upload_id: 会话标识。

        Raises:
            FileUploadSessionInvalidError: 会话不存在（`50104`）。
        """
        async with self._uow.begin():
            row = await self._files.get_by_upload_id(upload_id)
        if row is None:
            raise FileUploadSessionInvalidError(f"上传会话不存在：{upload_id}")
        await self._discard(row, "用户取消上传")

    # ---- 秒传 ----

    async def dedup(self, *, name: str, size: int, sha256: str, mime: str | None = None) -> SysFile | None:
        """秒传登记：同租户命中既有对象则复制元数据建行（不重复占配额）。

        Args:
            name: 原始文件名（含扩展名）。
            size: 文件字节数。
            sha256: 整文件 SHA256。
            mime: 声明的内容类型（仅预检）。

        Returns:
            SysFile | None: 命中返回新建记录；未命中 None（调用方走正常上传）。

        Raises:
            FileSizeExceededError: 超单文件上限（`50102`）。
            FileTypeNotAllowedError: 扩展名不在白名单 / 声明类型不相容（`50101`）。
            ParamError: SHA256 形态非法（`10001`）。
        """
        limits = await self.limits()
        if size > limits.max_file_size:
            raise FileSizeExceededError(f"文件超单文件上限：{size} > {limits.max_file_size}")
        self._ensure_extension(name=name, mime=mime, limits=limits)
        self._ensure_sha256(sha256)
        async with self._uow.begin():
            candidate = await self._files.find_completed_by_content(sha256=sha256, size=size)
        if candidate is None or not await self._storage.exists(candidate.object_key):
            return None
        file_id = id_generator.next_id()
        async with self._uow.begin():
            row = await self._files.create_with_id(
                file_id,
                name=name,
                ext=normalize_extension(name),
                bucket=candidate.bucket,
                object_key=candidate.object_key,
                size=candidate.size,
                mime_type=candidate.mime_type,
                sha256=candidate.sha256,
                uploader_id=current_user_id.get(),
                source=FILE_SOURCE_DEDUP,
                status=FILE_STATUS_COMPLETED,
                completed_at=_now(),
                uploaded_parts=0,
            )
            await self._emit(row, _EVENT_UPLOADED)
        self._capture(row, action="dedup")
        return row

    # ---- 查询 / 取址 / 删除 ----

    async def page(
        self,
        *,
        page: int,
        size: int,
        name: str | None = None,
        mime_type: str | None = None,
        uploader_id: int | None = None,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> FilePage:
        """文件列表（筛选 + 分页）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            name: 名称关键字。
            mime_type: 内容类型前缀。
            uploader_id: 上传人。
            status: 状态。
            created_from: 创建时间下限。
            created_to: 创建时间上限。

        Returns:
            FilePage: 分页结果。
        """
        async with self._uow.begin():
            rows, total = await self._files.page_filtered(
                page=page,
                size=size,
                name=name,
                mime_type=mime_type,
                uploader_id=uploader_id,
                status=status,
                created_from=created_from,
                created_to=created_to,
            )
            items = ConcurrentStableList(FileItem.model_validate(row) for row in rows)
            return FilePage(list=items, total=total, page=page, size=size)

    async def presign(self, *, file_id: int, preview: bool = False, expires_in: int | None = None) -> PresignedUrl:
        """生成限时预签名地址（下载 / 预览同口径，后端不代理文件流）。

        Args:
            file_id: 文件主键。
            preview: 是否预览取址（仅图片 / PDF）。
            expires_in: 期望有效期（秒，不得超过参数上限）。

        Returns:
            PresignedUrl: 预签名结果。

        Raises:
            FileRecordNotFoundError: 文件不存在（`50106`）。
            FileUploadSessionInvalidError: 文件未完成（`50104`）。
            FilePreviewUnsupportedError: 类型不支持预览（`50108`）。
            FileObjectMissingError: 对象已丢失（`50109`）。
        """
        limits = await self.limits()
        row = await self._require_file(file_id)
        if row.status != FILE_STATUS_COMPLETED:
            raise FileUploadSessionInvalidError(f"文件未完成，不可取址：{file_id}")
        if preview and not is_previewable(row.mime_type):
            raise FilePreviewUnsupportedError(f"该类型不支持在线预览：{row.mime_type}")
        if not await self._storage.exists(row.object_key):
            raise FileObjectMissingError(f"文件对象已丢失：{file_id}")
        ttl = limits.presign_ttl if expires_in is None else min(expires_in, limits.presign_ttl)
        if ttl <= 0:
            ttl = limits.presign_ttl
        result = await self._storage.presign(row.object_key, method="GET", expires_in=ttl)
        self._capture(row, action="preview" if preview else "download")
        return result

    async def delete(self, file_id: int) -> None:
        """软删除文件元数据（对象保留、配额不释放；物理清理归 13_01）。

        Args:
            file_id: 文件主键。

        Raises:
            FileRecordNotFoundError: 文件不存在 / 已删除（`50106`）。
        """
        async with self._uow.begin():
            row = await self._files.get(file_id)
            if row is None:
                raise FileRecordNotFoundError(f"文件不存在：{file_id}")
            row.soft_delete()
            await self._emit(row, _EVENT_DELETED)
        self._capture(row, action="delete")

    # ---- 孤儿回收 ----

    async def cleanup_orphans(self, *, limit: int | None = None) -> CleanupResult:
        """回收超期未完成的上传：清分片 → 置 `orphan` → 发事件（单条失败不影响整批）。

        Args:
            limit: 单批上限（None 取 `[file].orphan_batch`）。

        Returns:
            CleanupResult: 扫描 / 回收 / 失败条数。
        """
        batch = limit if limit is not None else file_settings().orphan_batch
        async with self._uow.begin():
            rows = await self._files.list_expired_uploading(now=_now(), limit=batch)
        orphaned = 0
        failed = 0
        for row in rows:
            try:
                await self._mark_orphan(row)
                orphaned += 1
            except Exception as exc:  # 单条失败不阻断整批（记 warning + 计数）
                failed += 1
                _LOGGER.warning("孤儿回收单条失败", file_id=row.id, error=str(exc))
        if self._metrics is not None and orphaned:
            await self._metrics.counter("bms_file_orphan_cleaned_total", value=float(orphaned))
        return CleanupResult(scanned=len(rows), orphaned=orphaned, failed=failed)

    async def _mark_orphan(self, row: SysFile) -> None:
        """清理单条超期上传并置 `orphan`。

        Args:
            row: 超期记录。
        """
        if row.upload_id:
            try:
                await self._multipart.abort(row.upload_id)
            except NotFoundError:
                _LOGGER.warning("孤儿回收：会话快照已丢失", file_id=row.id, upload_id=row.upload_id)
        async with self._uow.begin():
            await self._parts.delete_by_file(row.id)
            row.status = FILE_STATUS_ORPHAN
            row.remark = "超期未完成，已回收"
            await self._emit(row, _EVENT_ABANDONED)

    async def _mark_failed(self, row: SysFile, reason: str) -> None:
        """置失败态并清分片记录。

        Args:
            row: 文件记录。
            reason: 失败原因（落 `remark`）。
        """
        async with self._uow.begin():
            await self._parts.delete_by_file(row.id)
            row.status = FILE_STATUS_FAILED
            row.remark = reason

    async def _discard(self, row: SysFile, reason: str) -> None:
        """取消 / 失败清理：会话中止 + 分片行清理 + 置 `failed`。

        Args:
            row: 文件记录。
            reason: 失败原因。
        """
        if row.upload_id:
            try:
                await self._multipart.abort(row.upload_id)
            except NotFoundError:
                _LOGGER.warning("取消上传：会话快照已丢失", file_id=row.id)
        await self._mark_failed(row, reason)

    # ---- 内部工具 ----

    async def _require_file(self, file_id: int) -> SysFile:
        """取文件记录（不存在抛 `50106`）。

        Args:
            file_id: 文件主键。

        Returns:
            SysFile: 文件记录。

        Raises:
            FileRecordNotFoundError: 文件不存在（`50106`）。
        """
        async with self._uow.begin():
            row = await self._files.get(file_id)
        if row is None:
            raise FileRecordNotFoundError(f"文件不存在：{file_id}")
        return row

    async def _require_uploading(self, upload_id: str) -> SysFile:
        """取上传中的记录（不存在 / 非上传中 / 已过期抛 `50104`）。

        Args:
            upload_id: 会话标识。

        Returns:
            SysFile: 上传中记录。

        Raises:
            FileUploadSessionInvalidError: 会话无效（`50104`）。
        """
        async with self._uow.begin():
            row = await self._files.get_by_upload_id(upload_id)
        if row is None or row.status != FILE_STATUS_UPLOADING:
            raise FileUploadSessionInvalidError(f"上传会话不存在或已结束：{upload_id}")
        if row.expires_at is not None and row.expires_at < _now():
            raise FileUploadSessionInvalidError(f"上传会话已过期：{upload_id}")
        return row

    async def _with_session[T](self, upload_id: str, call: Callable[[], Awaitable[T]], *, init: MultipartInit) -> T:
        """调用存储会话；快照丢失时按原标识重建一次后重试（Redis 只是加速面）。

        Args:
            upload_id: 会话标识。
            call: 无参协程工厂。
            init: 会话重建参数（沿用原 `upload_id`）。

        Returns:
            T: 调用结果。

        Raises:
            NotFoundError: 重建后仍不存在（`50104`）。
        """
        try:
            return await call()
        except NotFoundError:
            _LOGGER.warning("分片会话快照丢失，按记录重建", upload_id=upload_id)
            await self._multipart.initiate(init)
            return await call()

    def _rebuild_init(self, row: SysFile) -> MultipartInit:
        """按记录构造会话重建参数（同一 `upload_id` / key / 分片参数）。

        Args:
            row: 文件记录。

        Returns:
            MultipartInit: 初始化参数。
        """
        return MultipartInit(
            key=row.object_key,
            size=row.size,
            sha256=row.sha256,
            mime=row.mime_type,
            part_size=row.part_size,
            upload_id=row.upload_id,
        )

    def _resolve_mime(self, *, name: str, head: bytes, limits: FileLimits) -> str:
        """类型双校验（扩展名 + 嗅探），失败转 `50101`。

        Args:
            name: 原始文件名。
            head: 头部字节。
            limits: 生效参数。

        Returns:
            str: 落库 MIME。

        Raises:
            FileTypeNotAllowedError: 类型不允许（`50101`）。
        """
        try:
            return resolve_mime(name=name, head=head, whitelist=limits.whitelist)
        except ValueError as exc:
            raise FileTypeNotAllowedError(str(exc)) from exc

    def _ensure_extension(self, *, name: str, mime: str | None, limits: FileLimits) -> str:
        """分片 / 秒传场景预检：扩展名在白名单 + 声明 MIME 与扩展名相容。

        Args:
            name: 原始文件名。
            mime: 声明内容类型（可空）。
            limits: 生效参数。

        Returns:
            str: 白名单规范 MIME（落库值）。

        Raises:
            FileTypeNotAllowedError: 扩展名不在白名单 / 声明类型不相容（`50101`）。
        """
        extension = normalize_extension(name)
        entry = limits.whitelist.get(extension) if extension else None
        if entry is None:
            raise FileTypeNotAllowedError(f"扩展名不在白名单：{extension or name}")
        if mime and mime != entry.mime:
            raise FileTypeNotAllowedError(f"声明类型与扩展名不相容：{mime} != {entry.mime}")
        return entry.mime

    @staticmethod
    def _ensure_sha256(value: str) -> None:
        """校验 SHA256 形态（64 位小写十六进制）。

        Args:
            value: 待校验值。

        Raises:
            ParamError: 形态非法（`10001`）。
        """
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ParamError("SHA256 格式非法（应为 64 位小写十六进制）")

    async def _emit(self, row: SysFile, event_type: str) -> None:
        """把事件写入事务性发件箱（与状态同事务）。

        Args:
            row: 文件记录。
            event_type: 事件类型。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"file_id": str(row.id), "sha256": row.sha256, "size": row.size, "upload_id": row.upload_id or ""}
        )
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=event_type,
                payload=payload,
                tenant_id=current_tenant_id_str() or None,
                aggregate_key=str(row.id),
            ),
        )

    def _capture(self, row: SysFile, *, action: str) -> None:
        """产生审计事件（落库归 06；无捕获器时跳过）。

        Args:
            row: 文件记录。
            action: 动作标识（upload / complete / dedup / download / preview / delete）。
        """
        if self._audit is None:
            return
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
            (FieldChange(field="action", old=None, new=action),)
        )
        self._audit.capture(table="sys_file", model_id=row.id, changes=changes, actor=current_user_id.get())

    async def _warn_quota(self, size: int) -> None:
        """配额超限告警（日志 + 指标）。

        Args:
            size: 本次申请字节数。
        """
        _LOGGER.warning("file_quota_exceeded", quota_key=QUOTA_KEY, size=size, tenant=current_tenant.get())
        if self._metrics is not None:
            await self._metrics.counter("bms_file_quota_rejected_total", value=1.0)

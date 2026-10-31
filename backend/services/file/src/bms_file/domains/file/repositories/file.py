"""文件域仓储：元数据筛选分页 / 会话定位 / 秒传候选 / 孤儿扫描 / 分片读写。

口径：

- 软删除与租户过滤由基座 `_select()`（作用域条件）统一施加，本层不重复写 `deleted_at IS NULL`；
- 分片行**只硬删**：删除走 `hard_delete` / 批量 `DELETE`，不做软删（见 `sys_file_part` 表文件 §4）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_file.domains.file.models.file import FILE_STATUS_COMPLETED, FILE_STATUS_UPLOADING, SysFile, SysFilePart

__all__ = ["FilePartRepository", "FileRepository"]


class FileRepository(BaseDbRepository[SysFile]):
    """文件元数据仓储（`sys_file`）。"""

    model = SysFile
    sortable_fields = ConcurrentStableSet({"id", "name", "size", "created_at", "completed_at"})

    async def get_by_upload_id(self, upload_id: str) -> SysFile | None:
        """按会话标识取记录（软删除后不可见）。

        Args:
            upload_id: 会话标识。

        Returns:
            SysFile | None: 记录；不存在 None。
        """
        statement = self._select().where(self._column("upload_id") == upload_id)
        return (await self._session.execute(statement)).scalars().first()

    async def create_with_id(self, item_id: int, **values: object) -> SysFile:
        """按指定主键创建记录（对象 key 需在插入前由主键派生，故先取雪花 ID）。

        Args:
            item_id: 预生成主键（雪花 ID）。
            **values: 创建字段值。

        Returns:
            SysFile: 新建记录。

        Raises:
            ConfigError: 字段不在白名单（沿用基座写入口径）。
        """
        payload = self._write_values(ConcurrentStableDict(values), creating=True)
        item = SysFile(id=item_id, **payload)
        self._session.add(item)
        await self._session.flush()
        return item

    async def page_filtered(
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
    ) -> tuple[ConcurrentStableList[SysFile], int]:
        """按名称 / 类型 / 上传人 / 状态 / 时间范围筛选分页（按创建时间倒序）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            name: 名称关键字（模糊匹配）。
            mime_type: 内容类型（前缀匹配，如 `image/`）。
            uploader_id: 上传人。
            status: 状态。
            created_from: 创建时间下限（含）。
            created_to: 创建时间上限（含）。

        Returns:
            tuple[ConcurrentStableList[SysFile], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if name:
            statement = statement.where(self._column("name").like(f"%{name}%"))
        if mime_type:
            statement = statement.where(self._column("mime_type").like(f"{mime_type}%"))
        if uploader_id is not None:
            statement = statement.where(self._column("uploader_id") == uploader_id)
        if status:
            statement = statement.where(self._column("status") == status)
        if created_from is not None:
            statement = statement.where(self._column("created_at") >= created_from)
        if created_to is not None:
            statement = statement.where(self._column("created_at") <= created_to)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("created_at").desc(), self._column("id").desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def find_completed_by_content(self, *, sha256: str, size: int) -> SysFile | None:
        """按内容（校验值 + 字节数）取最近一条已完成记录（秒传候选）。

        Args:
            sha256: 整文件 SHA256。
            size: 字节数。

        Returns:
            SysFile | None: 命中记录；未命中 None。
        """
        statement = (
            self._select()
            .where(self._column("sha256") == sha256)
            .where(self._column("size") == size)
            .where(self._column("status") == FILE_STATUS_COMPLETED)
            .order_by(self._column("id").desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def count_live_by_content(self, *, sha256: str, size: int) -> int:
        """统计同内容仍存活的记录数（共享对象清理判据，13_01 消费）。

        Args:
            sha256: 整文件 SHA256。
            size: 字节数。

        Returns:
            int: 存活记录数。
        """
        statement = (
            select(func.count())
            .select_from(SysFile)
            .where(SysFile.sha256 == sha256, SysFile.size == size, SysFile.deleted_at.is_(None))
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_expired_uploading(self, *, now: datetime, limit: int) -> ConcurrentStableList[SysFile]:
        """取超期未完成的上传记录（孤儿回收候选，按过期时间升序）。

        Args:
            now: 当前时间（UTC）。
            limit: 单批上限。

        Returns:
            ConcurrentStableList[SysFile]: 候选记录。
        """
        statement = (
            self._select()
            .where(self._column("status") == FILE_STATUS_UPLOADING)
            .where(self._column("expires_at").is_not(None))
            .where(self._column("expires_at") < now)
            .order_by(self._column("expires_at").asc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())


class FilePartRepository(BaseDbRepository[SysFilePart]):
    """分片仓储（`sys_file_part`）：只做硬删。"""

    model = SysFilePart
    sortable_fields = ConcurrentStableSet({"id", "part_no"})

    async def list_by_file(self, file_id: int) -> ConcurrentStableList[SysFilePart]:
        """取某文件的全部已上传分片（按序号升序）。

        Args:
            file_id: 文件主键。

        Returns:
            ConcurrentStableList[SysFilePart]: 分片记录。
        """
        statement = self._select().where(self._column("file_id") == file_id).order_by(self._column("part_no").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_part(self, *, file_id: int, part_no: int) -> SysFilePart | None:
        """取单条分片记录。

        Args:
            file_id: 文件主键。
            part_no: 分片序号。

        Returns:
            SysFilePart | None: 记录；不存在 None。
        """
        statement = self._select().where(self._column("file_id") == file_id, self._column("part_no") == part_no)
        return (await self._session.execute(statement)).scalars().first()

    async def upsert_part(self, *, file_id: int, part_no: int, size: int, sha256: str, etag: str) -> SysFilePart:
        """写入 / 覆盖分片记录（重传同片即覆盖，天然幂等）。

        Args:
            file_id: 文件主键。
            part_no: 分片序号。
            size: 分片字节数。
            sha256: 分片 SHA256。
            etag: 存储侧 etag。

        Returns:
            SysFilePart: 落库记录。
        """
        existing = await self.get_part(file_id=file_id, part_no=part_no)
        if existing is None:
            return await self.create(file_id=file_id, part_no=part_no, size=size, sha256=sha256, etag=etag)
        return await self.update(existing.id, size=size, sha256=sha256, etag=etag) or existing

    async def count_by_file(self, file_id: int) -> int:
        """统计已上传分片数。

        Args:
            file_id: 文件主键。

        Returns:
            int: 分片数。
        """
        statement = select(func.count()).select_from(SysFilePart).where(SysFilePart.file_id == file_id)
        return int((await self._session.execute(statement)).scalar_one())

    async def delete_by_file(self, file_id: int) -> int:
        """物理删除某文件的全部分片行（合并成功 / 取消 / 孤儿回收）。

        Args:
            file_id: 文件主键。

        Returns:
            int: 删除行数。
        """
        statement = delete(SysFilePart).where(SysFilePart.file_id == file_id)
        result = await self._session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

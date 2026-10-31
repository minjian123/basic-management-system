"""文件域模型（`file` 业务域；承载服务 `file`，库类别 `tenant`）。

- 归属：业务域 `file`，表级归属见 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_file.md` / `sys_file_part.md`）；
- 状态口径：`sys_file.status` 四态（`uploading` / `completed` / `failed` / `orphan`），
  `completed` 才允许下载 / 预览，且**不回退**（失败只能重新初始化产生新行）；
- 分片口径：`sys_file_part` 是断点续传的分片状态权威，**只做硬删**（合并 / 取消 / 孤儿回收即物理删），
  因此唯一约束为 `(file_id, part_no)` 而不带 `deleted_at`（规避 NULL 互不相等导致约束失效）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

FILE_STATUS_UPLOADING = "uploading"
"""文件状态：上传中（分片会话已建，尚未合并）。"""

FILE_STATUS_COMPLETED = "completed"
"""文件状态：已完成（可下载 / 预览）。"""

FILE_STATUS_FAILED = "failed"
"""文件状态：失败（校验 / 合并失败或用户取消；可重新初始化）。"""

FILE_STATUS_ORPHAN = "orphan"
"""文件状态：孤儿（超期未完成，已被回收任务清理）。"""

FILE_SOURCE_UPLOAD = "upload"
"""文件来源：用户上传（整包或分片）。"""

FILE_SOURCE_DEDUP = "dedup"
"""文件来源：秒传登记（复用同租户既有对象）。"""

FILE_SOURCE_PRINT = "print"
"""文件来源：单据打印产物（04_02 消费）。"""

FILE_SOURCE_EXPORT = "export"
"""文件来源：列表导出产物（04_02 消费）。"""


class SysFile(BaseModel):
    """文件元数据（`sys_file`）：内容存对象存储，库里只存 key、校验值与状态。"""

    __tablename__ = "sys_file"
    __table_args__ = (
        UniqueConstraint("upload_id", name="uq_sys_file_upload_id"),
        Index("idx_sys_file_uploader_created_at", "uploader_id", "created_at"),
        Index("idx_sys_file_status_expires_at", "status", "expires_at"),
        Index("idx_sys_file_sha256_size", "sha256", "size"),
    )

    name: Mapped[str] = mapped_column(String(255), comment="原始文件名（含扩展名）")
    ext: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="小写扩展名（不含点；无扩展名为空）")
    bucket: Mapped[str] = mapped_column(String(64), default="bms-files", comment="对象存储桶名")
    object_key: Mapped[str] = mapped_column(
        String(512), comment="对象 key（秒传可与既有行相同，非唯一）"
    )
    size: Mapped[int] = mapped_column(BigInteger, comment="文件字节数")
    mime_type: Mapped[str] = mapped_column(String(128), comment="服务端嗅探得到的 MIME")
    sha256: Mapped[str] = mapped_column(String(64), comment="整文件 SHA256（完成后可通过校验）")
    uploader_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="上传人（雪花 ID；系统产物可空）")
    source: Mapped[str] = mapped_column(String(16), default=FILE_SOURCE_UPLOAD, comment="来源：upload/dedup/print/export")
    status: Mapped[str] = mapped_column(String(16), default=FILE_STATUS_UPLOADING, comment="状态（四态）")
    upload_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分片会话标识（整包为空；单列唯一）"
    )
    total_parts: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="分片总数（整包为空）")
    uploaded_parts: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="已上传片数（冗余计数）")
    part_size: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="本次会话分片大小（字节）")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="会话过期时刻（UTC；孤儿判定权威字段）"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时刻（UTC）")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="失败原因 / 备注")


class SysFilePart(BaseModel):
    """文件分片（`sys_file_part`）：断点续传的分片状态权威，只做硬删。"""

    __tablename__ = "sys_file_part"
    __table_args__ = (
        UniqueConstraint("file_id", "part_no", name="uq_sys_file_part_file_id_part_no"),
        Index("idx_sys_file_part_file_id", "file_id"),
    )

    file_id: Mapped[int] = mapped_column(BigInteger, comment="所属文件（逻辑指向 sys_file.id）")
    part_no: Mapped[int] = mapped_column(Integer, comment="分片序号（从 1 起）")
    size: Mapped[int] = mapped_column(Integer, comment="分片字节数")
    sha256: Mapped[str] = mapped_column(String(64), comment="分片 SHA256（服务端复算通过后落库）")
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="存储侧分片 etag（留痕）")

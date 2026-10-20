"""租户配额模型：`sys_tenant_quota`（平台服务库 `bms_tenant`）。

- 语义：一租户 × 一维度一行；`limit_value` 限额、`used_value` 实时用量。
- 无行 = 不限制（平台租户与未配置租户不播种配额）。
- 明细表口径：落 `parent_id`、不落 `form_key`。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant_quota`）。
"""

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

QUOTA_KEY_USER_COUNT = "user_count"
"""配额维度：用户数。"""

QUOTA_KEY_STORAGE_BYTES = "storage_bytes"
"""配额维度：存储字节数。"""

QUOTA_KEY_OPEN_CALLS = "open_calls"
"""配额维度：开放接口调用量（日限额）。"""

QUOTA_KEYS: tuple[str, ...] = (QUOTA_KEY_USER_COUNT, QUOTA_KEY_STORAGE_BYTES, QUOTA_KEY_OPEN_CALLS)
"""配额维度清单（开通播种顺序）。"""


class SysTenantQuota(BaseModel):
    """租户配额（`sys_tenant_quota`）：限额与实时用量。"""

    __tablename__ = "sys_tenant_quota"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "quota_key", "deleted_at", name="uq_sys_tenant_quota_tenant_quota_key_deleted_at"
        ),
    )

    tenant_id: Mapped[int] = mapped_column(BigInteger, comment="租户主键（同库逻辑外键 → sys_tenant.id，只持值）")
    quota_key: Mapped[str] = mapped_column(String(32), comment="配额维度（user_count/storage_bytes/open_calls）")
    limit_value: Mapped[int] = mapped_column(BigInteger, comment="限额（open_calls 为日限额；storage_bytes 单位字节）")
    used_value: Mapped[int] = mapped_column(BigInteger, default=0, comment="已用量（原子增量；释放下限 0）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；本表无层级，按明细系统字段口径保留）"
    )

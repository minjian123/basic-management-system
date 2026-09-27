"""系统参数（`sys_config`）ORM 模型（platform 服务租户库）。

- 通用键值表：`config_key` 唯一（与 `deleted_at` 复合）、`value`（文本承载标量 / 布尔 / JSON 串）、`remark`。
- 平台默认参数经幂等种子写入各租户库（`bms_core.config.seed`）；租户覆盖写同名键。
- 字段 / 索引口径见《数据库设计 · 数据表设计 · sys_config》表文件（字段唯一事实源）。
"""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = ["SysConfig"]


class SysConfig(BaseModel):
    """系统参数（`sys_config`）。"""

    __tablename__ = "sys_config"
    __table_args__ = (UniqueConstraint("config_key", "deleted_at", name="uq_sys_config_config_key_deleted_at"),)

    config_key: Mapped[str] = mapped_column(String(128), comment="参数键（点分小写，唯一）")
    value: Mapped[str] = mapped_column(Text, default="", comment="参数值（文本承载）")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="备注（参数用途说明）")

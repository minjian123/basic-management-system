"""列表查询与偏好 ORM 模型：查询方案表 `sys_query_scheme`（泛化：字典高级查询 + 列表筛选共用）。

- 表声明出自 `02-4-20`（`BaseQuerySchemeStore` / `QueryScheme` 契约）；本文件为真实落库模型。
- `target=items`（字典高级查询，填 `dict_type`）/ `target=business`（列表筛选，`field_key=form_key`）。
"""

from sqlalchemy import JSON, BigInteger, Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

__all__ = ["SysQueryScheme"]


class SysQueryScheme(BaseModel):
    """查询方案（`sys_query_scheme`；个人 / 租户 / 平台三级作用域）。"""

    __tablename__ = "sys_query_scheme"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "owner_id",
            "target",
            "dict_type",
            "field_key",
            "name",
            "deleted_at",
            name="uq_scheme_scope_name_deleted_at",
        ),
        Index("idx_scheme_lookup", "target", "field_key", "status", "scope"),
    )

    name: Mapped[str] = mapped_column(String(64), comment="方案名")
    scope: Mapped[str] = mapped_column(String(16), comment="作用域（user/tenant/platform）")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="归属用户 ID（个人方案）")
    target: Mapped[str] = mapped_column(String(16), comment="目标（items/business）")
    dict_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="字典类型（target=items）")
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="表单标识（target=business）")
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="查询提供者键")
    conditions: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True, comment="条件组 JSON")
    params: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True, comment="额外参数 JSON")
    layout: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True, comment="展示配置 JSON")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认方案")
    shared: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否共享")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")

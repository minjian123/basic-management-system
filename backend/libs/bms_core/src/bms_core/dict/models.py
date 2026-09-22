"""字典域 ORM 模型（租户库）：类型 / 条目 / 扩展属性与各自 i18n 附表。

- 字段与索引口径见《概要设计 · 字典管理》「核心表」节；表名 `sys_dict_*`，逻辑外键（不建物理外键）。
- 普通运行时链路**不返回** `sys_dict_item.attr_json`（扩展属性仅由高级查询接口按命中子集返回）。
- 唯一约束按 `(唯一字段, deleted_at)` 复合口径（软删除释放唯一键）；未删除行的唯一性由服务层校验兜底。
"""

from sqlalchemy import JSON, BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = [
    "SysDictAttr",
    "SysDictAttrI18n",
    "SysDictItem",
    "SysDictItemI18n",
    "SysDictType",
    "SysDictTypeI18n",
]


class SysDictType(BaseModel):
    """字典类型（`sys_dict_type`）。"""

    __tablename__ = "sys_dict_type"
    __table_args__ = (
        UniqueConstraint("type", "deleted_at", name="uq_dict_type_code_deleted_at"),
        Index("idx_dict_type_status_sort", "status", "sort"),
    )

    type: Mapped[str] = mapped_column(String(64), comment="类型编码（唯一）")
    name: Mapped[str] = mapped_column(String(64), comment="类型名称（默认语言）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysDictItem(BaseModel):
    """字典条目（`sys_dict_item`）。"""

    __tablename__ = "sys_dict_item"
    __table_args__ = (
        UniqueConstraint("type_id", "code", "deleted_at", name="uq_dict_item_code_deleted_at"),
        Index("idx_dict_item_value", "type_id", "value"),
        Index("idx_dict_item_parent_sort", "type_id", "parent_id", "sort"),
        Index("idx_dict_item_label", "type_id", "label"),
    )

    type_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="字典类型 ID（逻辑引用 sys_dict_type.id）")
    code: Mapped[str] = mapped_column(String(64), comment="条目编码（类型内唯一）")
    label: Mapped[str] = mapped_column(String(128), comment="条目标签（默认语言）")
    value: Mapped[str] = mapped_column(String(64), comment="条目值")
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="级联父值（引用父条目 value）")
    attr_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True, comment="扩展属性值（普通链路不返回）"
    )
    color: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="语义色（success/warning/danger/info/primary）"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysDictTypeI18n(BaseModel):
    """字典类型多语言附表（`sys_dict_type_i18n`）。"""

    __tablename__ = "sys_dict_type_i18n"
    __table_args__ = (UniqueConstraint("dict_type_id", "locale", name="uq_dict_type_i18n"),)

    dict_type_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="字典类型 ID")
    locale: Mapped[str] = mapped_column(String(16), comment="语言（zh-CN / en-US）")
    label: Mapped[str] = mapped_column(String(64), comment="类型名翻译")


class SysDictItemI18n(BaseModel):
    """字典条目多语言附表（`sys_dict_item_i18n`）。"""

    __tablename__ = "sys_dict_item_i18n"
    __table_args__ = (UniqueConstraint("dict_item_id", "locale", name="uq_dict_item_i18n"),)

    dict_item_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="字典条目 ID")
    locale: Mapped[str] = mapped_column(String(16), comment="语言（zh-CN / en-US）")
    label: Mapped[str] = mapped_column(String(128), comment="条目标签翻译")


class SysDictAttr(BaseModel):
    """字典类型扩展属性定义（`sys_dict_attr`；高级查询可查字段）。"""

    __tablename__ = "sys_dict_attr"
    __table_args__ = (
        UniqueConstraint("type_id", "attr_key", "deleted_at", name="uq_dict_attr_key_deleted_at"),
        Index("idx_dict_attr_sort", "type_id", "status", "sort"),
    )

    type_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="字典类型 ID")
    attr_key: Mapped[str] = mapped_column(String(64), comment="属性键")
    name: Mapped[str] = mapped_column(String(64), comment="属性名（默认语言）")
    data_type: Mapped[str] = mapped_column(String(16), comment="数据类型（text/number/date/enum/bool）")
    operators: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, comment="可用操作符集合（JSON 数组）")
    widget: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="值控件（text/number/date/select/switch）"
    )
    options: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON, nullable=True, comment="enum 选项集（JSON 数组）"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序值")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    scope: Mapped[str] = mapped_column(String(16), default="platform", comment="属性来源（platform/tenant）")


class SysDictAttrI18n(BaseModel):
    """字典扩展属性多语言附表（`sys_dict_attr_i18n`）。"""

    __tablename__ = "sys_dict_attr_i18n"
    __table_args__ = (UniqueConstraint("dict_attr_id", "locale", name="uq_dict_attr_i18n"),)

    dict_attr_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="属性 ID")
    locale: Mapped[str] = mapped_column(String(16), comment="语言（zh-CN / en-US）")
    name: Mapped[str] = mapped_column(String(64), comment="属性名翻译")

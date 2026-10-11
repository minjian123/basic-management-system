"""拆除字典六表（`platform:tenant` 链 0013，02_09）。

Revision ID: 0013_drop_dict_tables
Revises: 0012_data_scope_dict_key
Create Date: 2026-10-11

- 归属链：`platform:tenant`（`platform` 服务租户库）；
- 变更背景（`02_09` 口径返工）：AI 自行编造的「**字典类型 / 字典条目 / 字典属性**」一套（实质「选项类型 /
  条目」）剔除——拆 `sys_dict_type` / `sys_dict_item` / `sys_dict_attr` + 3 张 `_i18n` 附表共六表；取数改由
  **字典数据源登记 + 统一出口**承载；
- 执行序：**先删数据后删表**、幂等（`IF EXISTS` 语义经存在性判断）；子表先于主表；
- 四库兼容：`batch_alter_table` 不需要（drop 不涉方言）；SQLite 经 `op.drop_table`；
- `downgrade` 重建六张**空表**（收口后列名口径：`code` / `name` / `dict_type_id` / `parent_id` BIGINT），
  **不恢复历史数据**。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_drop_dict_tables"
down_revision: str | None = "0012_data_scope_dict_key"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TYPE = "sys_dict_type"
"""字典类型表。"""

ITEM = "sys_dict_item"
"""字典条目表。"""

NODE = "sys_dict_attr"
"""字典扩展属性表。"""

TYPE_I18N = "sys_dict_type_i18n"
"""字典类型多语言附表。"""

ITEM_I18N = "sys_dict_item_i18n"
"""字典条目多语言附表。"""

NODE_I18N = "sys_dict_attr_i18n"
"""字典属性多语言附表。"""

_DROP_ORDER: tuple[str, ...] = (ITEM_I18N, NODE_I18N, ITEM, NODE, TYPE_I18N, TYPE)
"""删除顺序（子表 / 附表先于主表）。"""


def _base_columns() -> list[sa.Column]:
    """公共字段（对齐 `BaseModel`）。

    Returns:
        list[sa.Column]: 公共列定义。
    """
    return [
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
    ]


def _status() -> sa.Column:
    """条目 / 类型状态列。

    Returns:
        sa.Column: 状态列（enabled 缺省）。
    """
    return sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled")


def upgrade() -> None:
    """先删数据后删表、幂等拆六表。"""
    connection = op.get_bind()
    existing = set(sa.inspect(connection).get_table_names())
    if ITEM in existing:
        op.execute(f"DELETE FROM {ITEM}")
    if NODE in existing:
        op.execute(f"DELETE FROM {NODE}")
    if TYPE in existing:
        op.execute(f"DELETE FROM {TYPE}")
    for table in _DROP_ORDER:
        if table in existing:
            op.drop_table(table)


def downgrade() -> None:
    """重建六张空表（收口后列名口径；不恢复历史数据）。"""
    op.create_table(
        TYPE,
        *_base_columns(),
        sa.Column("code", sa.String(length=64), nullable=False, comment="类型编码（唯一）"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="类型名称（默认语言）"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _status(),
        sa.UniqueConstraint("code", "deleted_at", name="uq_dict_type_code_deleted_at"),
    )
    op.create_index("idx_sys_dict_type_deleted_at", TYPE, ["deleted_at"])
    op.create_index("idx_dict_type_status_sort", TYPE, ["status", "sort"])
    op.create_table(
        ITEM,
        *_base_columns(),
        sa.Column("dict_type_id", sa.BigInteger(), nullable=False, index=True, comment="字典类型 ID"),
        sa.Column("code", sa.String(length=64), nullable=False, comment="条目编码"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="条目标签（默认语言）"),
        sa.Column("value", sa.String(length=64), nullable=False, comment="条目值"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True, comment="上级条目 ID"),
        sa.Column("attr_json", sa.JSON(), nullable=True, comment="扩展属性值"),
        sa.Column("color", sa.String(length=32), nullable=True, comment="语义色"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _status(),
        sa.UniqueConstraint("dict_type_id", "code", "deleted_at", name="uq_dict_item_code_deleted_at"),
    )
    op.create_index("idx_dict_item_value", ITEM, ["dict_type_id", "value"])
    op.create_index("idx_dict_item_parent_sort", ITEM, ["dict_type_id", "parent_id", "sort"])
    op.create_index("idx_dict_item_name", ITEM, ["dict_type_id", "name"])
    op.create_index("idx_sys_dict_item_dict_type_id", ITEM, ["dict_type_id"])
    op.create_table(
        TYPE_I18N,
        *_base_columns(),
        sa.Column("dict_type_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("dict_type_id", "locale", name="uq_dict_type_i18n"),
    )
    op.create_table(
        ITEM_I18N,
        *_base_columns(),
        sa.Column("dict_item_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.UniqueConstraint("dict_item_id", "locale", name="uq_dict_item_i18n"),
    )
    op.create_table(
        NODE,
        *_base_columns(),
        sa.Column("dict_type_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("attr_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("operators", sa.JSON(), nullable=True),
        sa.Column("widget", sa.String(length=32), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _status(),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="platform"),
        sa.UniqueConstraint("dict_type_id", "attr_key", "deleted_at", name="uq_dict_attr_key_deleted_at"),
    )
    op.create_index("idx_dict_attr_sort", NODE, ["dict_type_id", "status", "sort"])
    op.create_table(
        NODE_I18N,
        *_base_columns(),
        sa.Column("dict_attr_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.UniqueConstraint("dict_attr_id", "locale", name="uq_dict_attr_i18n"),
    )

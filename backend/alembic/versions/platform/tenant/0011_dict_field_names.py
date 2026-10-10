"""字典系统字段命名收口（`platform:tenant` 链 0011，02_08）。

Revision ID: 0011_dict_field_names
Revises: 0010_dict_item_parent_id_bigint
Create Date: 2026-10-10

- 归属链：`platform:tenant`（`platform` 服务的租户库；字典六表与之同库）；SQLite 经 `batch_alter_table`
  重建表；
- 迁移背景（`02_08` 命名收口，口径见《数据库开发规范》「系统字段」节 §3.1.3 字典清单 / §3.1.4 收口项）：
  `sys_dict_type.type` → **`code`**（代码列）、`sys_dict_item.label` → **`name`**（名称列，主表默认文案列）、
  `sys_dict_item.type_id` / `sys_dict_attr.type_id` → **`dict_type_id`**（主表 ID 口径 `{主表}_id`，与
  `sys_dict_type_i18n.dict_type_id` / `sys_dict_item_i18n.dict_item_id` 同形态）；
- 索引随列重建（索引名含列名）：`idx_dict_item_label` → `idx_dict_item_name`、
  `idx_sys_dict_item_type_id` → `idx_sys_dict_item_dict_type_id`；其余复合索引（`idx_dict_item_value` /
  `idx_dict_item_parent_sort` / `idx_dict_attr_sort`）名称不变、列随改名自动跟随；
- **纯改名**：不改类型与可空性、不动数据、**无数据回填**；API 契约字段名与前端字段名**保持不变**
  （契约侧仍为 `type` / `label` / `type_id`，只改列名与 ORM 属性）；
- 四库兼容：经 `batch_alter_table` 的 `alter_column(new_column_name=...)`，不写方言 SQL、不用方言专用类型；
- 执行序：先删待改名的两个索引（旧列名），再改列名，最后按新列名建索引。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_dict_field_names"
down_revision: str | None = "0010_dict_item_parent_id_bigint"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ITEM = "sys_dict_item"
"""字典条目表。"""

TYPE = "sys_dict_type"
"""字典类型表。"""

NODE = "sys_dict_attr"
"""字典扩展属性表。"""


def upgrade() -> None:
    """字典列名对齐系统字段口径（纯改名 + 索引随列重建）。"""
    op.drop_index("idx_dict_item_label", table_name=ITEM)
    op.drop_index("idx_sys_dict_item_type_id", table_name=ITEM)
    with op.batch_alter_table(TYPE) as batch:
        batch.alter_column("type", new_column_name="code")
    with op.batch_alter_table(NODE) as batch:
        batch.alter_column("type_id", new_column_name="dict_type_id")
    with op.batch_alter_table(ITEM) as batch:
        batch.alter_column("type_id", new_column_name="dict_type_id")
        batch.alter_column("label", new_column_name="name")
    op.create_index("idx_dict_item_name", ITEM, ["dict_type_id", "name"])
    op.create_index("idx_sys_dict_item_dict_type_id", ITEM, ["dict_type_id"])


def downgrade() -> None:
    """列名与索引名回退。"""
    op.drop_index("idx_sys_dict_item_dict_type_id", table_name=ITEM)
    op.drop_index("idx_dict_item_name", table_name=ITEM)
    with op.batch_alter_table(ITEM) as batch:
        batch.alter_column("name", new_column_name="label")
        batch.alter_column("dict_type_id", new_column_name="type_id")
    with op.batch_alter_table(NODE) as batch:
        batch.alter_column("dict_type_id", new_column_name="type_id")
    with op.batch_alter_table(TYPE) as batch:
        batch.alter_column("code", new_column_name="type")
    op.create_index("idx_sys_dict_item_type_id", ITEM, ["type_id"])
    op.create_index("idx_dict_item_label", ITEM, ["type_id", "label"])

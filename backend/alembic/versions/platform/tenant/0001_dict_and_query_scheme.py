"""字典与查询方案表（`platform:tenant` 链首个迁移，02-4-27）：字典六表 + 查询方案表。

Revision ID: 0001_dict_query_scheme
Revises:
Create Date: 2026-09-21

- 归属链：`platform:tenant`（`platform` 服务 × 各租户的租户库 `bms_platform_{tenant}`）；脚本按
  `{服务}/{数据源}` 分目录，`branch_labels` 取链名；
- 字段 / 索引口径与 ORM 模型（`app/dict/models.py` / `app/listing/models.py`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型（`sa.JSON()` 由 SQLAlchemy 按方言映射；达梦差异随阶段二实测）；
- 索引命名对齐 `Base.metadata` 约定（`idx_{表}_{列}`，2026-09-22 随 01_04 修订，原 `ix_*` 作废）；
- 只建表不写种子（种子走 `ops/seed_dict.py` 幂等脚本）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_dict_query_scheme"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("platform:tenant",)
depends_on: Sequence[str] | None = None


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


def upgrade() -> None:
    """建字典六表与查询方案表（含唯一约束与索引）。"""
    op.create_table(
        "sys_dict_type",
        *_base_columns(),
        sa.Column("type", sa.String(length=64), nullable=False, comment="类型编码（唯一）"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="类型名称（默认语言）"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="排序值"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态（enabled/disabled）"
        ),
        sa.UniqueConstraint("type", "deleted_at", name="uq_dict_type_code_deleted_at"),
    )
    op.create_index("idx_sys_dict_type_deleted_at", "sys_dict_type", ["deleted_at"])
    op.create_index("idx_dict_type_status_sort", "sys_dict_type", ["status", "sort"])

    op.create_table(
        "sys_dict_item",
        *_base_columns(),
        sa.Column("type_id", sa.BigInteger(), nullable=False, comment="字典类型 ID（逻辑引用 sys_dict_type.id）"),
        sa.Column("code", sa.String(length=64), nullable=False, comment="条目编码（类型内唯一）"),
        sa.Column("label", sa.String(length=128), nullable=False, comment="条目标签（默认语言）"),
        sa.Column("value", sa.String(length=64), nullable=False, comment="条目值"),
        sa.Column("parent_id", sa.String(length=64), nullable=True, comment="级联父值（引用父条目 value）"),
        sa.Column("attr_json", sa.JSON(), nullable=True, comment="扩展属性值（普通链路不返回）"),
        sa.Column(
            "color", sa.String(length=32), nullable=True, comment="语义色（success/warning/danger/info/primary）"
        ),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="排序值"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态（enabled/disabled）"
        ),
        sa.UniqueConstraint("type_id", "code", "deleted_at", name="uq_dict_item_code_deleted_at"),
    )
    op.create_index("idx_sys_dict_item_deleted_at", "sys_dict_item", ["deleted_at"])
    op.create_index("idx_sys_dict_item_type_id", "sys_dict_item", ["type_id"])
    op.create_index("idx_dict_item_value", "sys_dict_item", ["type_id", "value"])
    op.create_index("idx_dict_item_parent_sort", "sys_dict_item", ["type_id", "parent_id", "sort"])
    op.create_index("idx_dict_item_label", "sys_dict_item", ["type_id", "label"])

    op.create_table(
        "sys_dict_type_i18n",
        *_base_columns(),
        sa.Column("dict_type_id", sa.BigInteger(), nullable=False, comment="字典类型 ID"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言（zh-CN / en-US）"),
        sa.Column("label", sa.String(length=64), nullable=False, comment="类型名翻译"),
        sa.UniqueConstraint("dict_type_id", "locale", name="uq_dict_type_i18n"),
    )
    op.create_index("idx_sys_dict_type_i18n_deleted_at", "sys_dict_type_i18n", ["deleted_at"])
    op.create_index("idx_sys_dict_type_i18n_dict_type_id", "sys_dict_type_i18n", ["dict_type_id"])

    op.create_table(
        "sys_dict_item_i18n",
        *_base_columns(),
        sa.Column("dict_item_id", sa.BigInteger(), nullable=False, comment="字典条目 ID"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言（zh-CN / en-US）"),
        sa.Column("label", sa.String(length=128), nullable=False, comment="条目标签翻译"),
        sa.UniqueConstraint("dict_item_id", "locale", name="uq_dict_item_i18n"),
    )
    op.create_index("idx_sys_dict_item_i18n_deleted_at", "sys_dict_item_i18n", ["deleted_at"])
    op.create_index("idx_sys_dict_item_i18n_dict_item_id", "sys_dict_item_i18n", ["dict_item_id"])

    op.create_table(
        "sys_dict_attr",
        *_base_columns(),
        sa.Column("type_id", sa.BigInteger(), nullable=False, comment="字典类型 ID"),
        sa.Column("attr_key", sa.String(length=64), nullable=False, comment="属性键"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="属性名（默认语言）"),
        sa.Column("data_type", sa.String(length=16), nullable=False, comment="数据类型（text/number/date/enum/bool）"),
        sa.Column("operators", sa.JSON(), nullable=True, comment="可用操作符集合（JSON 数组）"),
        sa.Column("widget", sa.String(length=32), nullable=True, comment="值控件（text/number/date/select/switch）"),
        sa.Column("options", sa.JSON(), nullable=True, comment="enum 选项集（JSON 数组）"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="排序值"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态（enabled/disabled）"
        ),
        sa.Column(
            "scope",
            sa.String(length=16),
            nullable=False,
            server_default="platform",
            comment="属性来源（platform/tenant）",
        ),
        sa.UniqueConstraint("type_id", "attr_key", "deleted_at", name="uq_dict_attr_key_deleted_at"),
    )
    op.create_index("idx_sys_dict_attr_deleted_at", "sys_dict_attr", ["deleted_at"])
    op.create_index("idx_sys_dict_attr_type_id", "sys_dict_attr", ["type_id"])
    op.create_index("idx_dict_attr_sort", "sys_dict_attr", ["type_id", "status", "sort"])

    op.create_table(
        "sys_dict_attr_i18n",
        *_base_columns(),
        sa.Column("dict_attr_id", sa.BigInteger(), nullable=False, comment="属性 ID"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言（zh-CN / en-US）"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="属性名翻译"),
        sa.UniqueConstraint("dict_attr_id", "locale", name="uq_dict_attr_i18n"),
    )
    op.create_index("idx_sys_dict_attr_i18n_deleted_at", "sys_dict_attr_i18n", ["deleted_at"])
    op.create_index("idx_sys_dict_attr_i18n_dict_attr_id", "sys_dict_attr_i18n", ["dict_attr_id"])

    op.create_table(
        "sys_query_scheme",
        *_base_columns(),
        sa.Column("name", sa.String(length=64), nullable=False, comment="方案名"),
        sa.Column("scope", sa.String(length=16), nullable=False, comment="作用域（user/tenant/platform）"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="归属用户 ID（个人方案）"),
        sa.Column("target", sa.String(length=16), nullable=False, comment="目标（items/business）"),
        sa.Column("dict_type", sa.String(length=64), nullable=True, comment="字典类型（target=items）"),
        sa.Column("field_key", sa.String(length=64), nullable=True, comment="表单标识（target=business）"),
        sa.Column("provider_key", sa.String(length=64), nullable=True, comment="查询提供者键"),
        sa.Column("conditions", sa.JSON(), nullable=True, comment="条件组 JSON"),
        sa.Column("params", sa.JSON(), nullable=True, comment="额外参数 JSON"),
        sa.Column("layout", sa.JSON(), nullable=True, comment="展示配置 JSON"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否默认方案"),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否共享"),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态（enabled/disabled）"
        ),
        sa.UniqueConstraint(
            "scope",
            "owner_id",
            "target",
            "dict_type",
            "field_key",
            "name",
            "deleted_at",
            name="uq_scheme_scope_name_deleted_at",
        ),
    )
    op.create_index("idx_sys_query_scheme_deleted_at", "sys_query_scheme", ["deleted_at"])
    op.create_index("idx_scheme_lookup", "sys_query_scheme", ["target", "field_key", "status", "scope"])


def downgrade() -> None:
    """逆序删除查询方案表与字典六表。"""
    op.drop_table("sys_query_scheme")
    op.drop_table("sys_dict_attr_i18n")
    op.drop_table("sys_dict_attr")
    op.drop_table("sys_dict_item_i18n")
    op.drop_table("sys_dict_type_i18n")
    op.drop_table("sys_dict_item")
    op.drop_table("sys_dict_type")

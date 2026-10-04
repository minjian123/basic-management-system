"""菜单元数据表集（权限元数据，`platform:platform` 链 0007，域 03_01 菜单与权限）。

Revision ID: 0007_menu_metadata
Revises: 0006_sys_outbox_tenant_bigint
Create Date: 2026-10-04

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- 建 10 张表：`sys_business` / `sys_business_i18n` / `sys_action` / `sys_action_i18n` /
  `sys_menu` / `sys_menu_i18n` / `sys_form` / `sys_button` / `sys_field` / `sys_field_i18n`；
- 字段 / 索引口径与 ORM 模型（`bms_platform/models/menu.py`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型；索引命名对齐 `Base.metadata` 约定（`idx_{表}_{列}` / `uq_{表}_{列}`）；
- 只建表，不写种子（MVP 元数据与业务 / 动作码经 `ops/seed_menu.py` 幂等 upsert）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_menu_metadata"
down_revision: str | None = "0006_sys_outbox_tenant_bigint"
branch_labels: Sequence[str] | None = None
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
    """建菜单元数据十表（含唯一约束与索引）。"""
    # 业务权限码
    op.create_table(
        "sys_business",
        *_base_columns(),
        sa.Column("code", sa.String(length=64), nullable=False, comment="业务权限码（小写单词）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="名称（默认文案）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("code", "deleted_at", name="uq_sys_business_code_deleted_at"),
    )
    op.create_index("idx_sys_business_deleted_at", "sys_business", ["deleted_at"])

    op.create_table(
        "sys_business_i18n",
        *_base_columns(),
        sa.Column("business_id", sa.BigInteger(), nullable=False, comment="业务码 ID（逻辑外键 → sys_business.id）"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言标识（如 zh-CN）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="业务名的该语言文案"),
        sa.UniqueConstraint(
            "business_id", "locale", "deleted_at", name="uq_sys_business_i18n_business_locale_deleted_at"
        ),
    )
    op.create_index("idx_sys_business_i18n_deleted_at", "sys_business_i18n", ["deleted_at"])

    # 动作权限码
    op.create_table(
        "sys_action",
        *_base_columns(),
        sa.Column("code", sa.String(length=64), nullable=False, comment="动作码（如 query/create/manage）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="名称（默认文案）"),
        sa.Column("business_id", sa.BigInteger(), nullable=False, comment="归属业务码 ID（逻辑外键 → sys_business.id）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("business_id", "code", "deleted_at", name="uq_sys_action_business_code_deleted_at"),
    )
    op.create_index("idx_sys_action_business_id", "sys_action", ["business_id"])
    op.create_index("idx_sys_action_deleted_at", "sys_action", ["deleted_at"])

    op.create_table(
        "sys_action_i18n",
        *_base_columns(),
        sa.Column("action_id", sa.BigInteger(), nullable=False, comment="动作码 ID（逻辑外键 → sys_action.id）"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言标识（如 zh-CN）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="动作名的该语言文案"),
        sa.UniqueConstraint(
            "action_id", "locale", "deleted_at", name="uq_sys_action_i18n_action_locale_deleted_at"
        ),
    )
    op.create_index("idx_sys_action_i18n_deleted_at", "sys_action_i18n", ["deleted_at"])

    # 菜单树
    op.create_table(
        "sys_menu",
        *_base_columns(),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, comment="父菜单 ID（0 为根）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="菜单名（默认文案）"),
        sa.Column("path", sa.String(length=255), nullable=False, comment="前端路由路径（/ 开头）"),
        sa.Column("component", sa.String(length=255), nullable=True, comment="视图组件标识（可空 = 目录节点）"),
        sa.Column("icon", sa.String(length=64), nullable=True, comment="完整 icon key"),
        sa.Column("sort", sa.Integer(), nullable=False, comment="同级排序（升序）"),
        sa.Column("hidden", sa.Boolean(), nullable=False, comment="仅隐藏侧栏入口（权限仍生效）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("path", "deleted_at", name="uq_sys_menu_path_deleted_at"),
    )
    op.create_index("idx_sys_menu_parent_id", "sys_menu", ["parent_id"])
    op.create_index("idx_sys_menu_deleted_at", "sys_menu", ["deleted_at"])

    op.create_table(
        "sys_menu_i18n",
        *_base_columns(),
        sa.Column("menu_id", sa.BigInteger(), nullable=False, comment="菜单 ID（逻辑外键 → sys_menu.id）"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言标识（如 zh-CN）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="菜单名的该语言文案"),
        sa.UniqueConstraint("menu_id", "locale", "deleted_at", name="uq_sys_menu_i18n_menu_locale_deleted_at"),
    )
    op.create_index("idx_sys_menu_i18n_deleted_at", "sys_menu_i18n", ["deleted_at"])

    # 表单 / 按钮 / 字段
    op.create_table(
        "sys_form",
        *_base_columns(),
        sa.Column("menu_id", sa.BigInteger(), nullable=False, comment="所属菜单 ID（逻辑外键 → sys_menu.id）"),
        sa.Column("business_id", sa.BigInteger(), nullable=False, comment="所属业务码 ID（逻辑外键 → sys_business.id）"),
        sa.Column("component", sa.String(length=255), nullable=True, comment="表单视图组件标识"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("menu_id", "deleted_at", name="uq_sys_form_menu_id_deleted_at"),
        sa.UniqueConstraint("business_id", "deleted_at", name="uq_sys_form_business_id_deleted_at"),
    )
    op.create_index("idx_sys_form_deleted_at", "sys_form", ["deleted_at"])

    op.create_table(
        "sys_button",
        *_base_columns(),
        sa.Column("form_id", sa.BigInteger(), nullable=False, comment="所属表单 ID（逻辑外键 → sys_form.id）"),
        sa.Column("action_id", sa.BigInteger(), nullable=False, comment="挂接动作码 ID（逻辑外键 → sys_action.id）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="按钮名（界面可见文本）"),
        sa.Column("type", sa.String(length=16), nullable=False, comment="按钮形态（toolbar/interface）"),
        sa.Column("sort", sa.Integer(), nullable=False, comment="同表内排序（升序）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("form_id", "action_id", "deleted_at", name="uq_sys_button_form_action_deleted_at"),
    )
    op.create_index("idx_sys_button_form_id", "sys_button", ["form_id"])
    op.create_index("idx_sys_button_action_id", "sys_button", ["action_id"])
    op.create_index("idx_sys_button_deleted_at", "sys_button", ["deleted_at"])

    op.create_table(
        "sys_field",
        *_base_columns(),
        sa.Column("form_id", sa.BigInteger(), nullable=False, comment="所属表单 ID（逻辑外键 → sys_form.id）"),
        sa.Column("field_key", sa.String(length=64), nullable=False, comment="字段键（表单内唯一）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="字段名（默认文案）"),
        sa.Column("type", sa.String(length=32), nullable=False, comment="字段类型（组件语义键）"),
        sa.Column("sort", sa.Integer(), nullable=False, comment="同表内排序（升序）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.UniqueConstraint("form_id", "field_key", "deleted_at", name="uq_sys_field_form_key_deleted_at"),
    )
    op.create_index("idx_sys_field_form_id", "sys_field", ["form_id"])
    op.create_index("idx_sys_field_deleted_at", "sys_field", ["deleted_at"])

    op.create_table(
        "sys_field_i18n",
        *_base_columns(),
        sa.Column("field_id", sa.BigInteger(), nullable=False, comment="字段 ID（逻辑外键 → sys_field.id）"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言标识（如 zh-CN）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="字段名的该语言文案"),
        sa.UniqueConstraint("field_id", "locale", "deleted_at", name="uq_sys_field_i18n_field_locale_deleted_at"),
    )
    op.create_index("idx_sys_field_i18n_deleted_at", "sys_field_i18n", ["deleted_at"])


def downgrade() -> None:
    """删菜单元数据十表（含索引）。"""
    for table in (
        "sys_field_i18n",
        "sys_field",
        "sys_button",
        "sys_form",
        "sys_menu_i18n",
        "sys_menu",
        "sys_action_i18n",
        "sys_action",
        "sys_business_i18n",
        "sys_business",
    ):
        op.drop_table(table)

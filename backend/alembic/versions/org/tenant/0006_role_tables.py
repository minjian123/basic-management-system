"""角色域 5 表（`org:tenant` 链，02_03）。

Revision ID: 0006_role_tables
Revises: 0005_sys_outbox
Create Date: 2026-10-06

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- 新建 `sys_role` / `sys_user_role` / `sys_role_permission` / `sys_role_field` / `sys_data_scope`；
- 字段 / 索引口径与 ORM 模型（`bms_org/models/role.py`）逐项一致；
- `source_menu_id` 以 `0` 表示「表单级直接授予」（非 NULL，规避唯一约束在 NULL 上的跨库语义差异）；
- `config` 为 JSON 列，空数组初始值由应用层提供（MySQL 8 不支持 JSON 列服务器默认值）；
- 公共字段对齐 `BaseModel`；各表软删除索引显式建；
- 只建表不写种子（内置管理员角色随租户开通阶段）。
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0006_role_tables"
down_revision: str | None = "0005_sys_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _common_columns() -> tuple[sa.Column[Any], ...]:
    """公共字段（对齐 `BaseModel`；每次调用返回新实例，供多表建表复用）。"""
    return (
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
    )


def upgrade() -> None:
    """建角色域 5 表（含唯一约束、业务索引与软删除索引）。"""
    op.create_table(
        "sys_role",
        *_common_columns(),
        sa.Column("code", sa.String(length=64), nullable=False, comment="角色码（租户内唯一；创建后不可修改）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="角色名称"),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'enabled'"),
            comment="状态（enabled/disabled）",
        ),
        sa.UniqueConstraint("code", "deleted_at", name="uq_sys_role_code_deleted_at"),
    )
    op.create_index("idx_sys_role_deleted_at", "sys_role", ["deleted_at"])
    op.create_index("idx_sys_role_status", "sys_role", ["status"])

    op.create_table(
        "sys_user_role",
        *_common_columns(),
        sa.Column("role_id", sa.BigInteger(), nullable=False, comment="角色主键（逻辑外键 sys_role.id；同库）"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户主键（逻辑外键 sys_user.id；同库）"),
        sa.UniqueConstraint("role_id", "user_id", "deleted_at", name="uq_sys_user_role_role_user_deleted_at"),
    )
    op.create_index("idx_sys_user_role_deleted_at", "sys_user_role", ["deleted_at"])
    op.create_index("idx_sys_user_role_role_id", "sys_user_role", ["role_id"])
    op.create_index("idx_sys_user_role_user_id", "sys_user_role", ["user_id"])

    op.create_table(
        "sys_role_permission",
        *_common_columns(),
        sa.Column("role_id", sa.BigInteger(), nullable=False, comment="角色主键（逻辑外键 sys_role.id；同库）"),
        sa.Column("perm_type", sa.String(length=16), nullable=False, comment="授权类型（menu/form/action）"),
        sa.Column(
            "target_id",
            sa.BigInteger(),
            nullable=False,
            comment="授权目标 ID（平台实体雪花 ID；跨库逻辑外键）",
        ),
        sa.Column(
            "source_menu_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="来源菜单入口 ID（0 = 表单级直接授予）",
        ),
        sa.UniqueConstraint(
            "role_id",
            "perm_type",
            "target_id",
            "source_menu_id",
            "deleted_at",
            name="uq_sys_role_permission_role_type_target_source_deleted_at",
        ),
    )
    op.create_index("idx_sys_role_permission_deleted_at", "sys_role_permission", ["deleted_at"])
    op.create_index("idx_sys_role_permission_role_type", "sys_role_permission", ["role_id", "perm_type"])
    op.create_index("idx_sys_role_permission_target", "sys_role_permission", ["target_id"])

    op.create_table(
        "sys_role_field",
        *_common_columns(),
        sa.Column("role_id", sa.BigInteger(), nullable=False, comment="角色主键（逻辑外键 sys_role.id；同库）"),
        sa.Column("form_id", sa.BigInteger(), nullable=False, comment="表单 ID（平台实体；跨库逻辑外键）"),
        sa.Column("field_id", sa.BigInteger(), nullable=False, comment="字段 ID（平台实体；跨库逻辑外键）"),
        sa.Column(
            "visible", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否可见（false = 读时过滤）"
        ),
        sa.Column(
            "editable", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否可编辑（false = 写时拒绝）"
        ),
        sa.Column(
            "source_menu_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
            comment="来源菜单入口 ID（0 = 表单级直接授予）",
        ),
        sa.UniqueConstraint(
            "role_id",
            "form_id",
            "field_id",
            "source_menu_id",
            "deleted_at",
            name="uq_sys_role_field_role_form_field_source_deleted_at",
        ),
    )
    op.create_index("idx_sys_role_field_deleted_at", "sys_role_field", ["deleted_at"])
    op.create_index("idx_sys_role_field_role_form", "sys_role_field", ["role_id", "form_id"])

    op.create_table(
        "sys_data_scope",
        *_common_columns(),
        sa.Column("role_id", sa.BigInteger(), nullable=False, comment="角色主键（逻辑外键 sys_role.id；同库）"),
        sa.Column(
            "dict_type_id",
            sa.BigInteger(),
            nullable=False,
            comment="字典类型 ID（platform 服务租户库；跨库逻辑外键）",
        ),
        sa.Column(
            "policy_type", sa.String(length=16), nullable=False, comment="策略类型（select/region/match/extension）"
        ),
        sa.Column("config", sa.JSON(), nullable=False, comment="结构化策略配置（只选不编；空数组由应用层给初始值）"),
        sa.UniqueConstraint(
            "role_id", "dict_type_id", "policy_type", "deleted_at", name="uq_sys_data_scope_role_dict_policy_deleted_at"
        ),
    )
    op.create_index("idx_sys_data_scope_deleted_at", "sys_data_scope", ["deleted_at"])
    op.create_index("idx_sys_data_scope_role_id", "sys_data_scope", ["role_id"])


def downgrade() -> None:
    """删除角色域 5 表（逆序）。"""
    op.drop_table("sys_data_scope")
    op.drop_table("sys_role_field")
    op.drop_table("sys_role_permission")
    op.drop_table("sys_user_role")
    op.drop_table("sys_role")

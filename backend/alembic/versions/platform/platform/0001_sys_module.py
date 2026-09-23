"""模块注册表 + 模块名附表（`platform:platform` 链首建，06_02 分链）。

Revision ID: 0001_sys_module
Revises:
Create Date: 2026-09-23

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- **由原 `versions/platform/0001_sys_tenant_module.py` 按表归属拆分**：`sys_tenant` 归 `tenant` 服务
  （链 `tenant:platform`），`sys_module` / `sys_module_i18n` 归 `platform` 服务（本脚本）；
- 字段 / 索引口径与 ORM 模型（`bms_platform/models/catalog.py::SysModule` / `SysModuleI18n`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型（达梦差异随 01_05 实测）；
- 只建表不写种子（种子走 `ops/seed_module.py` 幂等脚本）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_sys_module"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("platform:platform",)
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
    """建服务目录两表（含唯一约束与索引）。"""
    op.create_table(
        "sys_module",
        *_base_columns(),
        sa.Column("module_key", sa.String(length=32), nullable=False, comment="模块简称（如 pur、sys）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="模块名（默认文案）"),
        sa.Column("table_prefix", sa.String(length=32), nullable=False, comment="表前缀（形如 pur_）"),
        sa.Column(
            "errcode_segment",
            sa.String(length=8),
            nullable=True,
            comment="错误码段号（产品 10 起；平台域 01~04；可空——唯一性由启动 / CI 校验，规避达梦多 NULL 差异）",
        ),
        sa.Column("event_domain", sa.String(length=64), nullable=False, comment="事件域（全小写）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled/planned）"),
        sa.UniqueConstraint("module_key", "deleted_at", name="uq_sys_module_key_deleted_at"),
        sa.UniqueConstraint("table_prefix", "deleted_at", name="uq_sys_module_prefix_deleted_at"),
        sa.UniqueConstraint("errcode_segment", "deleted_at", name="uq_sys_module_segment_deleted_at"),
        sa.UniqueConstraint("event_domain", "deleted_at", name="uq_sys_module_domain_deleted_at"),
    )
    op.create_index("idx_sys_module_deleted_at", "sys_module", ["deleted_at"])

    op.create_table(
        "sys_module_i18n",
        *_base_columns(),
        sa.Column("module_id", sa.BigInteger(), nullable=False, comment="模块 ID（逻辑外键 → sys_module.id）"),
        sa.Column("locale", sa.String(length=16), nullable=False, comment="语言标识（如 zh-CN）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="模块名文案"),
        sa.UniqueConstraint(
            "module_id",
            "locale",
            "deleted_at",
            name="uq_sys_module_i18n_module_locale_deleted_at",
        ),
    )
    op.create_index("idx_sys_module_i18n_deleted_at", "sys_module_i18n", ["deleted_at"])


def downgrade() -> None:
    """逆序删除服务目录两表。"""
    op.drop_table("sys_module_i18n")
    op.drop_table("sys_module")

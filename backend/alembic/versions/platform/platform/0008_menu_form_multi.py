"""菜单 ↔ 表单多对多（`platform:platform` 链 0008，02_03 返工）。

Revision ID: 0008_menu_form_multi
Revises: 0007_menu_metadata
Create Date: 2026-10-07

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- 建关联表 `sys_menu_form`（`menu_id` / `form_id` + 公共字段；唯一 `(menu_id, form_id, deleted_at)`）；
- **数据搬迁**：既有 `sys_form.menu_id`（非 0 / 非 NULL）逐行写入关联表——软删的表单随其 `deleted_at`
  一并落软删；按 `(menu_id, form_id)` 判存做幂等；
- 随后经 `batch_alter_table` 删 `sys_form` 的 `menu_id` 列与唯一约束 `uq_sys_form_menu_id_deleted_at`
  （SQLite 经重建表兼容；`uq_sys_form_business_id_deleted_at` 保留）；
- **回滚**：加回 `menu_id`（**可空**）+ 按关联表首个入口回填 + 删关联表。旧 1:1 口径无法表示
  「无入口表单」，故回滚后该类行 `menu_id` 保持 NULL、非空约束不再恢复（保证链可回滚，已在实施记录登记）；
- 字段 / 索引口径与 ORM 模型（`bms_platform/models/menu.py`）逐项一致；雪花 id 取应用生成器、
  时间取 Python 侧 UTC（禁数据库端时间函数）。
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from bms_core.core.id import id_generator

revision: str = "0008_menu_form_multi"
down_revision: str | None = "0007_menu_metadata"
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
    """建 `sys_menu_form` → 搬迁既有 1:1 挂接 → 删 `sys_form.menu_id` 与唯一约束。"""
    op.create_table(
        "sys_menu_form",
        *_base_columns(),
        sa.Column("menu_id", sa.BigInteger(), nullable=False, comment="菜单 ID（逻辑外键 → sys_menu.id；多对多）"),
        sa.Column("form_id", sa.BigInteger(), nullable=False, comment="表单 ID（逻辑外键 → sys_form.id；多对多）"),
        sa.UniqueConstraint("menu_id", "form_id", "deleted_at", name="uq_sys_menu_form_menu_form_deleted_at"),
    )
    op.create_index("idx_sys_menu_form_menu_id", "sys_menu_form", ["menu_id"])
    op.create_index("idx_sys_menu_form_form_id", "sys_menu_form", ["form_id"])
    op.create_index("idx_sys_menu_form_deleted_at", "sys_menu_form", ["deleted_at"])
    _migrate_links()
    with op.batch_alter_table("sys_form") as batch:
        batch.drop_constraint("uq_sys_form_menu_id_deleted_at", type_="unique")
        batch.drop_column("menu_id")


def _migrate_links() -> None:
    """把既有 `sys_form.menu_id` 逐行迁入 `sys_menu_form`（幂等：按 `(menu_id, form_id)` 判存）。"""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, menu_id, deleted_at FROM sys_form WHERE menu_id IS NOT NULL AND menu_id <> 0")
    ).fetchall()
    now = datetime.now(UTC).replace(tzinfo=None)
    for form_id, menu_id, deleted_at in rows:
        exists = connection.execute(
            sa.text("SELECT 1 FROM sys_menu_form WHERE menu_id = :menu_id AND form_id = :form_id"),
            {"menu_id": menu_id, "form_id": form_id},
        ).first()
        if exists:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO sys_menu_form "
                "(id, created_at, created_by, updated_at, updated_by, deleted_at, version, menu_id, form_id) "
                "VALUES (:id, :now, NULL, :now, NULL, :deleted_at, 1, :menu_id, :form_id)"
            ),
            {
                "id": id_generator.next_id(),
                "now": now,
                "deleted_at": deleted_at,
                "menu_id": menu_id,
                "form_id": form_id,
            },
        )


def downgrade() -> None:
    """加回 `sys_form.menu_id`（回填后保留可空）→ 删 `sys_menu_form`。"""
    with op.batch_alter_table("sys_form") as batch:
        batch.add_column(
            sa.Column(
                "menu_id",
                sa.BigInteger(),
                nullable=True,
                comment="所属菜单 ID（逻辑外键 → sys_menu.id；旧 1:1 口径，回滚放宽非空）",
            )
        )
    _restore_menu_id()
    op.drop_index("idx_sys_menu_form_deleted_at", table_name="sys_menu_form")
    op.drop_index("idx_sys_menu_form_form_id", table_name="sys_menu_form")
    op.drop_index("idx_sys_menu_form_menu_id", table_name="sys_menu_form")
    op.drop_table("sys_menu_form")


def _restore_menu_id() -> None:
    """按关联表回填 `sys_form.menu_id`（每表单取首个生效入口；无入口表单保持 NULL）。"""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT form_id, MIN(menu_id) FROM sys_menu_form WHERE deleted_at IS NULL GROUP BY form_id")
    ).fetchall()
    for form_id, menu_id in rows:
        connection.execute(
            sa.text("UPDATE sys_form SET menu_id = :menu_id WHERE id = :form_id"),
            {"menu_id": menu_id, "form_id": form_id},
        )

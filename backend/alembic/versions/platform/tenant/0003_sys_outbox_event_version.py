"""发件箱事件契约版本列（`platform:tenant` 链 0003，05_04）：sys_outbox 增 event_version。

Revision ID: 0003_sys_outbox_event_version
Revises: 0002_sys_outbox
Create Date: 2026-09-23

- 归属链：`platform:tenant`（`platform` 服务 × 各租户的租户库）；脚本四库通用（与该服务平台链同构，
  保证事件版本随租户业务同库同事务）；
- 列口径与 ORM 模型（`bms_core/models/outbox.py::SysOutbox`）逐项一致；
- 存量行补默认 `1.0.0`（未登记契约时的事件缺省版本，登记契约由应用侧按契约版本补齐）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sys_outbox_event_version"
down_revision: str | None = "0002_sys_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """加事件契约版本列（存量行补 `1.0.0`）。"""
    with op.batch_alter_table("sys_outbox") as batch:
        batch.add_column(
            sa.Column(
                "event_version",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'1.0.0'"),
                comment="事件契约版本（X.Y.Z）",
            )
        )


def downgrade() -> None:
    """删事件契约版本列。"""
    with op.batch_alter_table("sys_outbox") as batch:
        batch.drop_column("event_version")

"""发件箱事件契约版本列（`tenant:tenant` 链，06_02 分链）。

Revision ID: 0002_sys_outbox_event_version
Revises: 0001_sys_outbox
Create Date: 2026-09-23

- 归属链：`tenant:tenant`（`tenant` 服务 × 各租户的租户库）；
- 与 `platform:platform/0004_sys_outbox_event_version.py`、`tenant:platform/0003_...` 内容同构；
- 列口径与 ORM 模型（`bms_core/models/outbox.py::SysOutbox`）逐项一致。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_sys_outbox_event_version"
down_revision: str | None = "0001_sys_outbox"
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

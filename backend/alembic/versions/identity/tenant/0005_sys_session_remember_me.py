"""会话记录增「记住我」列（`identity:tenant` 链，05_05）。

Revision ID: 0005_sys_session_remember_me
Revises: 0004_sys_outbox
Create Date: 2026-10-03

- 归属链：`identity:tenant`（`identity` 服务的租户库 `bms_identity_{code}`）；
- `sys_session` 新增可空 `remember_me`（BOOLEAN）：true=14 天持久 / false=会话级 / NULL=历史行（按 14 天处理）；
- 可空口径避免 `server_default` 的方言差异，且存量行语义自然（历史登录均为 14 天）；
- 字段口径与 ORM 模型（`bms_identity/models/session.py::SysSession`）逐项一致。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_sys_session_remember_me"
down_revision: str | None = "0004_sys_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """加 `sys_session.remember_me`（可空）。"""
    op.add_column(
        "sys_session",
        sa.Column(
            "remember_me",
            sa.Boolean(),
            nullable=True,
            comment="是否记住我（true=14 天；false=会话级；NULL=历史行，按 14 天处理）",
        ),
    )


def downgrade() -> None:
    """移除 `sys_session.remember_me`。"""
    op.drop_column("sys_session", "remember_me")

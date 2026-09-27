"""用户联系方式字段（`org:tenant` 链，03_06）。

Revision ID: 0003_sys_user_reset_contact
Revises: 0002_password_policy_and_account_lock
Create Date: 2026-09-28

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- `sys_user` 新增可空 `email`（VARCHAR(255)）/ `phone`（VARCHAR(32)）：找回密码按标识定位与投递通道；
- 维护入口 / 唯一性与格式校验 / 验证码绑定归用户管理阶段（本轮只落列，不建索引）；
- 字段口径与 ORM 模型逐项一致（`bms_org/models/user.py`）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sys_user_reset_contact"
down_revision: str | None = "0002_password_policy_and_account_lock"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """加 `sys_user.email` / `sys_user.phone`（可空）。"""
    op.add_column(
        "sys_user",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
            comment="邮箱（找回密码通道；维护入口归用户管理阶段）",
        ),
    )
    op.add_column(
        "sys_user",
        sa.Column(
            "phone",
            sa.String(length=32),
            nullable=True,
            comment="手机号（找回密码通道；维护入口归用户管理阶段）",
        ),
    )


def downgrade() -> None:
    """移除 `sys_user.phone` / `sys_user.email`。"""
    op.drop_column("sys_user", "phone")
    op.drop_column("sys_user", "email")

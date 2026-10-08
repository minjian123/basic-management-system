"""角色类型列（`platform:tenant` 链，02_03 重开追加子任务 01）。

Revision ID: 0009_role_type
Revises: 0008_user_tables
Create Date: 2026-10-08

- 归属链：`platform:tenant`（platform 服务租户库 `bms_platform_{code}`，与角色 / 授权、用户 / 账号同库）；
- 迁移背景（`02_03` 重开追加子任务「角色码可改与内置判定脱钩」）：内置角色判定由
  「角色码 ∈ `role.protected_codes` 常量」改为**按 `sys_role.role_type` 列**
  （`custom` / `system` / `security` / `audit`），角色码随之放开可改（内部无任何按 code 的引用）；
- 回填口径：按内置角色码缺省清单一次性回填——`system_admin → system`、`security_admin → security`、
  `audit_admin → audit`；未命中行保持缺省 `custom`；回填语句幂等，可重复执行；
- 新增行由服务侧显式写入 `role_type`（新建恒 `custom`）；`server_default` 仅作存量回填与直连兜底；
- 四库兼容：经 `batch_alter_table` 加列，不用方言专用类型；
- `downgrade`：删列（「角色码可改」为应用层行为，无数据回滚项）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_role_type"
down_revision: str | None = "0008_user_tables"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ROLE_TYPE_COLUMN = "role_type"
"""新增列名。"""

BACKFILL: tuple[tuple[str, str], ...] = (
    ("system_admin", "system"),
    ("security_admin", "security"),
    ("audit_admin", "audit"),
)
"""内置角色码 → 角色类型 回填映射（缺省清单，见 `bms_platform/models/role.py` 常量）。"""


def upgrade() -> None:
    """加列（缺省 `custom`）→ 按内置角色码回填角色类型。"""
    with op.batch_alter_table("sys_role") as batch:
        batch.add_column(
            sa.Column(
                ROLE_TYPE_COLUMN,
                sa.String(length=16),
                nullable=False,
                server_default="custom",
                comment="角色类型（custom/system/security/audit；内置判定，不可修改）",
            )
        )
    for code, role_type in BACKFILL:
        op.execute(
            sa.text("UPDATE sys_role SET role_type = :role_type WHERE code = :code").bindparams(
                role_type=role_type, code=code
            )
        )


def downgrade() -> None:
    """删列（角色码可改属应用层行为，无数据回滚项）。"""
    with op.batch_alter_table("sys_role") as batch:
        batch.drop_column(ROLE_TYPE_COLUMN)
